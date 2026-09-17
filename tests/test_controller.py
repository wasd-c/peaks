from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QGuiApplication

from peaks.adapters.persistence import Database, InMemoryPepperProvider, SecretVault
from peaks.adapters.riot.valorant import ValorantRank
from peaks.domain import Account, Game, RankInfo
from peaks.ui.controller import AppController


@pytest.fixture
def services(qapp, tmp_path: Path):
    database = Database(tmp_path / "peaks.sqlite3")
    vault = SecretVault(
        tmp_path / "vault.json",
        pepper_provider=InMemoryPepperProvider(b"controller-pepper-0123456789"),
    )
    controller = AppController(repository=database, vault=vault, demo=False)
    # Tests invoke timer-driven methods directly, keeping the event loop free
    # from background detection and auto-lock races.
    controller._lock_timer.stop()
    controller._detection_timer.stop()
    yield controller, database, vault
    controller.lockNow()
    controller.deleteLater()
    database.close()


def unlock_new_controller(controller: AppController) -> None:
    controller.submitPin("1234")
    assert controller.pinMode == "confirm"
    controller.submitPin("1234")
    assert controller.locked is False


class OverviewProvider:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def account_overview(self, account: dict[str, object]) -> dict[str, object]:
        self.calls.append(account)
        return {
            "puuid": "remote-puuid",
            "ranks": [
                RankInfo(Game.LEAGUE_OF_LEGENDS, "diamond", "II", rating=72),
                RankInfo(Game.TFT, "gold", "I", rating=44),
            ],
        }


def test_setup_confirm_unlock_and_lock_hide_metadata(services) -> None:
    controller, database, vault = services
    database.add_account(Account("owned", "Peak Player", "EUW", "euw1"))
    controller._load_persisted_state()

    # State loaded from SQLite is still hidden until the vault is unlocked.
    assert controller.locked is True
    assert controller.hasPasscode is False
    assert controller.accounts == []
    assert controller.searchHistory == []

    unlock_new_controller(controller)
    assert controller.hasPasscode is True
    assert controller.accounts[0]["id"] == "owned"
    assert vault.is_unlocked is True

    controller.lockNow()
    assert controller.locked is True
    assert controller.accounts == []
    assert controller.followed == []
    assert controller.searchResults == []
    assert vault.is_unlocked is False


def test_pin_confirmation_mismatch_resets_setup(services) -> None:
    controller, _, _ = services
    controller.submitPin("1234")
    controller.submitPin("4321")

    assert controller.pinMode == "create"
    assert "did not match" in controller.pinError
    assert controller.hasPasscode is False


def test_vault_backoff_is_reflected_and_correct_pin_cannot_bypass_it(services) -> None:
    controller, _, vault = services
    vault.setup_pin("1234")
    controller._has_passcode = True
    controller._pin_mode = "unlock"

    controller.submitPin("0000")
    assert controller.locked is True
    assert vault.failed_attempts == 1
    assert "wait" in controller.pinError
    error_before = controller.pinError

    controller.submitPin("1234")
    assert controller.locked is True
    assert "Try again" in controller.pinError
    assert controller.pinError != "Unlocked"
    assert error_before != ""


def test_auto_lock_uses_persisted_timeout_and_grid_is_default(services) -> None:
    controller, database, _ = services
    unlock_new_controller(controller)

    assert controller.viewMode == "grid"
    assert controller.settings["autoLockMinutes"] == 15
    controller.setAutoLock(1)
    controller._last_activity = time.monotonic() - 61
    controller._check_auto_lock()

    assert controller.locked is True
    assert database.get_settings().lock_timeout_seconds == 60


def test_application_deactivation_never_locks_before_timeout(services) -> None:
    controller, _, _ = services
    unlock_new_controller(controller)
    controller.setLockOnBlur(True)  # A persisted legacy value must remain inert.

    controller.eventFilter(
        controller,
        QEvent(QEvent.Type.ApplicationDeactivate),
    )

    assert controller.locked is False
    controller._last_activity = time.monotonic() - 14 * 60
    controller._check_auto_lock()
    assert controller.locked is False

    controller._last_activity = time.monotonic() - 16 * 60
    controller._check_auto_lock()
    assert controller.locked is True


def test_settings_persist_through_controller_and_reload(services, qapp, tmp_path: Path) -> None:
    controller, database, vault = services
    unlock_new_controller(controller)
    controller.setAutoLock(5)
    controller.setLockOnBlur(True)
    controller.setReduceMotion(True)
    assert controller.settings["autoLockMinutes"] == 5

    controller.lockNow()
    controller.deleteLater()
    reloaded = AppController(repository=database, vault=vault, demo=False)
    reloaded._lock_timer.stop()
    reloaded._detection_timer.stop()
    try:
        assert reloaded.settings["autoLockMinutes"] == 5
        assert reloaded.settings["lockOnBlur"] is True
        assert reloaded.settings["reduceMotion"] is True
        assert reloaded.viewMode == "grid"
    finally:
        reloaded.deleteLater()


def test_search_history_dedupes_and_watchlist_is_persisted(services) -> None:
    controller, database, _ = services
    unlock_new_controller(controller)

    controller.runSearch("Player#EUW", "EUW", "VALORANT")
    controller.runSearch("player#euw", "euw", "valorant")
    assert len(controller.searchHistory) == 1
    assert len(database.list_search_history()) == 1

    controller._finish_search(
        [
            {
                "id": "player-puuid",
                "riotId": "Player#EUW",
                "region": "EUW",
                "games": ["VALORANT"],
                "currentRank": "Diamond 2",
                "peakRank": "Ascendant 1",
                "lastGame": "just now",
            }
        ],
        None,
    )
    controller.toggleWatchlist("player-puuid")

    assert controller.followed[0]["id"] == "player-puuid"
    assert controller.toastText == "Added to Watchlist"
    assert database.is_followed("player-puuid", Game.VALORANT) is True
    controller.toggleFollow("player-puuid")
    assert controller.followed == []
    assert controller.toastText == "Removed from Watchlist"
    assert database.is_followed("player-puuid") is False


def test_followed_view_persists_rank_and_timestamps(services) -> None:
    controller, database, _ = services
    unlock_new_controller(controller)
    record = {
        "id": "player-puuid",
        "riotId": "Player#EUW",
        "region": "EUW",
        "games": ["VALORANT"],
        "currentRank": "Diamond II · 62 RR",
        "peakRank": "Ascendant 1",
        "lastGameAt": "2026-08-28T10:00:00Z",
        "updatedAt": "2026-08-28T10:30:00+00:00",
        "followedAt": "2026-08-27T09:00:00Z",
    }

    controller._persist_followed(record)

    saved = database.list_followed()[0]
    assert saved.game is Game.VALORANT
    assert saved.rank is not None
    assert saved.rank.tier == "diamond"
    assert saved.rank.division == "II"
    assert saved.rank.rating == 62
    assert saved.peak_rank is not None
    assert saved.peak_rank.tier == "ascendant"
    assert saved.peak_rank.division == "1"
    assert saved.last_game_at == datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
    assert saved.updated_at == datetime(2026, 8, 28, 10, 30, tzinfo=UTC)
    assert saved.followed_at == datetime(2026, 8, 27, 9, 0, tzinfo=UTC)

    controller.lockNow()
    controller._load_persisted_state()
    restored = controller._followed[0]
    assert restored["currentRank"] == "Diamond II · 62 RR"
    assert restored["peakRank"] == "Ascendant 1"
    assert restored["lastGame"] not in {"No recent game", "Cached"}
    assert restored["lastUpdated"] not in {"Cached", ""}


def test_unlock_derives_owned_secret_flags_from_vault_after_reload(services) -> None:
    controller, database, vault = services
    database.add_account(Account("owned", "Peak Player", "EUW", "euw1", puuid="known-puuid"))
    controller._load_persisted_state()
    unlock_new_controller(controller)
    controller._vault_set("owned", "totp", "JBSWY3DPEHPK3PXP")
    controller._vault_set("owned", "riot_session_cookies", '{"ssid":"saved-session"}')
    controller.lockNow()

    reloaded = AppController(repository=database, vault=vault, demo=False)
    reloaded._lock_timer.stop()
    reloaded._detection_timer.stop()
    try:
        assert reloaded.accounts == []
        reloaded.submitPin("1234")
        assert reloaded.accounts[0]["connected"] is True
        assert reloaded.accounts[0]["totpAvailable"] is True
        assert reloaded.accounts[0]["puuid"] == "known-puuid"

        reloaded.lockNow()
        reloaded.submitPin("1234")
        vault.delete("owned:riot_session_cookies")
        reloaded.lockNow()
        reloaded.submitPin("1234")
        assert reloaded.accounts[0]["connected"] is False
        assert reloaded.accounts[0]["totpAvailable"] is True
    finally:
        reloaded.deleteLater()


def test_searched_player_opens_history_detail_without_becoming_owned(services) -> None:
    controller, _, _ = services
    unlock_new_controller(controller)
    controller._search_results = [
        {
            "id": "searched-puuid",
            "riotId": "Searched#EUW",
            "region": "EUW",
            "owned": False,
            "ranks": [
                {"game": "League", "tier": "Diamond III", "rating": "70 LP", "peak": "Diamond III"},
                {"game": "VALORANT", "tier": "Requires approved VALORANT RSO", "rating": "—"},
            ],
            "matches": [{"id": "match-1", "game": "league_of_legends", "result": "win"}],
        }
    ]

    controller.selectAccount("searched-puuid")

    assert controller.selectedAccount["riotId"] == "Searched#EUW"
    assert controller.selectedAccount["owned"] is False
    assert controller.selectedAccount["matches"][0]["id"] == "match-1"
    assert controller.accounts == []


def test_refresh_accounts_runs_provider_in_worker_and_preserves_local_flags(services, qtbot) -> None:
    controller, database, _ = services
    provider = OverviewProvider()
    controller._provider = provider
    controller._settings["riotApiConfigured"] = True
    controller._accounts = [
        {
            "id": "local-id",
            "riotId": "Local#EUW",
            "region": "EUW",
            "owned": True,
            "connected": True,
            "totpAvailable": True,
            "ranks": [
                {"game": "League", "tier": "Unranked", "rating": "—", "peak": "—"},
                {"game": "VALORANT", "tier": "Gold 1", "rating": "12 RR", "peak": "Gold 1"},
            ],
            "matches": [],
        }
    ]
    unlock_new_controller(controller)
    controller._vault_set("local-id", "totp", "JBSWY3DPEHPK3PXP")
    controller._vault_set("local-id", "riot_access_token", "legacy-session-token")
    controller._refresh_owned_secret_flags()
    controller.refreshAccounts()

    qtbot.waitUntil(lambda: controller.accountRefreshBusy is False, timeout=2_000)
    refreshed = controller.accounts[0]
    games = {rank["game"] for rank in refreshed["ranks"]}
    assert provider.calls[0]["id"] == "local-id"
    assert refreshed["id"] == "local-id"
    assert refreshed["owned"] is True
    assert refreshed["connected"] is True
    assert refreshed["totpAvailable"] is True
    assert refreshed["puuid"] == "remote-puuid"
    assert {"League", "VALORANT", "TFT"}.issubset(games)
    assert database.get_account("local-id").puuid == "remote-puuid"  # type: ignore[union-attr]


class LocalValorantRankDetector:
    def __init__(self, rank: ValorantRank | None) -> None:
        self.rank = rank
        self.calls: list[str] = []

    def owned_valorant_rank(self, puuid: str) -> ValorantRank | None:
        self.calls.append(puuid)
        return self.rank


def test_refresh_accounts_uses_local_valorant_rank_without_developer_key(
    services, qtbot
) -> None:
    controller, database, _ = services
    detector = LocalValorantRankDetector(
        ValorantRank(23, "Ascendant 3", 48, 24, "Immortal 1", "current")
    )
    controller._game_detector = detector
    controller._provider = None
    controller._settings["riotApiConfigured"] = False
    controller._accounts = [
        {
            "id": "local-id",
            "riotId": "Local#EUW",
            "region": "EUW",
            "owned": True,
            "connected": True,
            "totpAvailable": False,
            "puuid": "owned-puuid",
            "ranks": [
                {"game": "League", "tier": "Diamond II", "rating": "72 LP", "peak": "Diamond II"},
                {"game": "TFT", "tier": "Master I", "rating": "100 LP", "peak": "Master I"},
                {"game": "VALORANT", "tier": "Gold 1", "rating": "12 RR", "peak": "Gold 1"},
            ],
            "matches": [],
        }
    ]
    unlock_new_controller(controller)

    controller.refreshAccounts()
    qtbot.waitUntil(lambda: controller.accountRefreshBusy is False, timeout=2_000)

    refreshed = controller.accounts[0]
    ranks = {rank["game"]: rank for rank in refreshed["ranks"]}
    assert detector.calls == ["owned-puuid"]
    assert ranks["VALORANT"]["game"] == "VALORANT"
    assert ranks["VALORANT"]["tier"] == "Ascendant 3"
    assert ranks["VALORANT"]["rating"] == "48 RR"
    assert ranks["VALORANT"]["peak"] == "Immortal 1"
    assert ranks["VALORANT"]["icon"].endswith("/valorant/ranks/ascendant-3.png")
    assert ranks["League"]["tier"] == "Diamond Ii"
    assert ranks["TFT"]["tier"] == "Master I"
    assert refreshed["lastUpdated"] == "Riot Client · just now"
    persisted = database.get_account("local-id")
    assert persisted is not None
    persisted_valorant = persisted.rank_for(Game.VALORANT)
    assert persisted_valorant is not None
    assert persisted_valorant.tier_label == "Ascendant"
    assert persisted_valorant.division == "3"
    assert persisted_valorant.rating == 48
    assert persisted_valorant.peak_label == "Immortal 1"
    assert "Updated local VALORANT rank" in controller.toastText


def test_local_valorant_rank_failure_preserves_cached_snapshot(
    services, qtbot
) -> None:
    controller, _, _ = services
    detector = LocalValorantRankDetector(None)
    controller._game_detector = detector
    controller._provider = None
    controller._settings["riotApiConfigured"] = False
    controller._accounts = [
        {
            "id": "local-id",
            "riotId": "Local#EUW",
            "region": "EUW",
            "owned": True,
            "connected": False,
            "totpAvailable": False,
            "puuid": "owned-puuid",
            "lastUpdated": "Official Riot API",
            "ranks": [
                {"game": "VALORANT", "tier": "Gold 1", "rating": "12 RR", "peak": "Gold 1"}
            ],
            "matches": [],
        }
    ]
    unlock_new_controller(controller)

    controller.refreshAccounts()
    qtbot.waitUntil(lambda: controller.accountRefreshBusy is False, timeout=2_000)

    refreshed = controller.accounts[0]
    assert detector.calls == ["owned-puuid"]
    assert refreshed["ranks"][0]["tier"] == "Gold 1"
    assert refreshed["ranks"][0]["rating"] == "12 RR"
    assert refreshed["lastUpdated"] == "Official Riot API"
    assert controller.toastText == "No matching signed-in Windows Riot Client account found"


class FakeQrApprover:
    def __init__(self) -> None:
        self.calls = 0
        self.session_info_calls = 0

    def session_info(
        self,
        parsed,
        *,
        access_token: str,
        selected_account_puuid: str,
    ):
        assert parsed.suuid
        assert access_token == "stored-session-token"
        assert selected_account_puuid == "owned-puuid"
        self.session_info_calls += 1
        return {"location": "Paris, FR", "device": "Riot Client"}

    def approve(self, parsed, credentials, *, user_approved: bool):
        assert user_approved is True
        assert credentials.puuid == "owned-puuid"
        assert credentials.access_token == "stored-session-token"
        self.calls += 1
        return {"method": "totp", "status": 200}


def test_qr_connect_requires_authenticated_session_info_and_confirmation(services, qtbot) -> None:
    controller, _, _ = services
    unlock_new_controller(controller)
    controller._accounts = [
        {
            "id": "owned",
            "riotId": "Owned#EUW",
            "region": "EUW",
            "owned": True,
            "connected": False,
            "totpAvailable": True,
            "puuid": "owned-puuid",
            "ranks": [],
            "matches": [],
        }
    ]
    controller._vault_set("owned", "totp", "JBSWY3DPEHPK3PXP")
    controller._vault_set("owned", "riot_access_token", "stored-session-token")
    approver = FakeQrApprover()
    controller._qr_approver = approver

    controller._qr_decoded(
        "owned",
        "https://qr.riotgames.com?"
        "suuid=123e4567-e89b-12d3-a456-426614174000&cluster=rcp-be-prod",
        None,
    )
    qtbot.waitUntil(lambda: controller.qrPromptOpen is True, timeout=2_000)
    assert controller.qrPromptOpen is True
    assert approver.calls == 0
    assert approver.session_info_calls == 1

    controller.confirmQr(True)
    qtbot.waitUntil(lambda: controller.accounts[0]["connected"] is True, timeout=2_000)

    assert approver.calls == 1
    assert controller.qrPromptOpen is False


def test_current_match_navigation_is_disabled_without_detection(services) -> None:
    controller, _, _ = services
    unlock_new_controller(controller)

    controller.navigate("current")

    assert controller.page == "overview"


def test_lock_clears_transient_state_and_rejects_late_worker_result(services, qtbot) -> None:
    controller, _, vault = services
    unlock_new_controller(controller)
    controller._accounts = [
        {
            "id": "owned",
            "riotId": "Owned#EUW",
            "owned": True,
            "connected": False,
            "totpAvailable": True,
            "ranks": [],
            "matches": [],
        }
    ]
    vault.put("owned:totp", "JBSWY3DPEHPK3PXP")
    controller.copyTotp("owned")
    clipboard = QGuiApplication.clipboard()
    assert clipboard is not None
    assert clipboard.text().isdigit()

    controller._pending_qr_private = {"accountId": "owned", "parsed": object()}
    controller._pending_qr = {"account": "Owned#EUW"}
    controller._set_qr_prompt(True)
    controller._current_match = {"game": "valorant"}
    controller._game_detected = True

    release = threading.Event()
    callbacks: list[object] = []
    controller._run_worker(
        lambda: release.wait(2),
        lambda result, error: callbacks.append(result),
    )
    controller.lockNow()
    controller.confirmQr(True)  # A stale QML click must be harmless.
    release.set()
    qtbot.waitUntil(lambda: not controller._workers, timeout=2_000)

    assert callbacks == []
    assert controller.pendingQr == {}
    assert controller.qrPromptOpen is False
    assert controller._pending_qr_private == {}
    assert controller.currentMatch == {}
    assert controller.gameDetected is False
    assert clipboard.text() == ""

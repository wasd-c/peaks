from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.bridge import Bridge, _match_stats
from peaks.domain.models import Account, Game, MatchRecord, MatchResult, RankInfo


class FakeRepository:
    def __init__(self) -> None:
        self.accounts: dict[str, Any] = {}
        self.matches: dict[str, list[Any]] = {}

    def get_account(self, account_id: str) -> Any | None:
        return self.accounts.get(account_id)

    def add_account(self, account: Any) -> Any:
        self.accounts[account.account_id] = account
        return account

    def list_accounts(self, owned_only: bool = False) -> list[Any]:
        return [account for account in self.accounts.values() if not owned_only or account.is_owned]

    def add_rank(self, account_id: str, rank: Any) -> Any:
        account = self.accounts[account_id]
        ranks = [value for value in account.ranks if value.game != rank.game]
        self.accounts[account_id] = replace(account, ranks=(*ranks, rank))
        return rank

    def add_match(self, match: Any) -> Any:
        rows = self.matches.setdefault(match.account_id, [])
        rows[:] = [value for value in rows if value.match_id != match.match_id]
        rows.append(match)
        return match

    def list_matches(self, account_id: str, *, limit: int | None = None) -> list[Any]:
        rows = list(self.matches.get(account_id, []))
        return rows[:limit] if limit is not None else rows


class FakeVault:
    def __init__(self) -> None:
        self.entries: dict[str, Any] = {}
        self.values: dict[str, Any] = {}

    def get_entry(self, account_id: str) -> Any | None:
        return self.entries.get(account_id)

    def put_entry(self, entry: Any) -> None:
        self.entries[entry.account_id] = entry

    def delete(self, account_id: str) -> bool:
        return self.entries.pop(account_id, None) is not None

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def put(self, key: str, value: Any) -> None:
        self.values[key] = value


def _result(*, source: str = "browser", cookies: dict[str, str] | None = None) -> Any:
    return SimpleNamespace(
        identity=SimpleNamespace(
            puuid="owned-puuid",
            game_name="Peak Player",
            tag_line="EUW",
        ),
        source=source,
        cookies=cookies,
    )


def _bridge(result: Any) -> tuple[Bridge, FakeRepository, FakeVault]:
    repository = FakeRepository()
    vault = FakeVault()
    bridge = Bridge.__new__(Bridge)
    bridge.demo = False
    bridge._account_onboarding_factory = lambda: SimpleNamespace(add_account=lambda: result)
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda _puuid: None
    )
    bridge._riot_search_service = None
    bridge._logger = logging.getLogger("tests.bridge.onboarding")
    bridge._pin_mode = "unlock"
    bridge._pending_pin = ""
    bridge._locked = False
    bridge.accounts = []
    bridge.followed = []
    bridge.history = []
    bridge.settings = {
        "autoLockMinutes": 15,
        "lockOnBlur": True,
        "reduceMotion": False,
        "riotApiConfigured": False,
        "clipboardClearSeconds": 15,
    }
    bridge._secrets = {}
    bridge._repository = repository
    bridge._vault = vault
    return bridge, repository, vault


def test_browser_onboarding_persists_identity_and_only_allowlisted_cookies() -> None:
    result = _result(
        cookies={
            "ssid": "session-cookie",
            "clid": "client-cookie",
            "sub": "owned-puuid",
        }
    )
    result.refresh_token = "DURABLE-REFRESH"
    bridge, repository, vault = _bridge(result)

    state = bridge.handle("add_account", {})

    assert len(state["accounts"]) == 1
    account = state["accounts"][0]
    assert account["id"].startswith("account-")
    assert account["id"] != "owned-puuid"
    assert "owned-puuid" not in repr(state)
    assert account["riotId"] == "Peak Player#EUW"
    assert account["connected"] is True
    assert account["canConnectQr"] is True
    assert account["canSaveRiotSession"] is True
    assert account["canSetupMfa"] is True
    assert repository.accounts["owned-puuid"].puuid == "owned-puuid"
    secret = vault.entries["owned-puuid"]
    assert dict(secret.cookies) == dict(result.cookies)
    assert secret.access_token is None
    assert secret.refresh_token == "DURABLE-REFRESH"
    assert secret.metadata["riot_session_offline"] is True
    assert "session-cookie" not in repr(secret)
    assert "DURABLE-REFRESH" not in repr(state) + repr(secret)


def test_readding_same_puuid_updates_in_place() -> None:
    bridge, _, _ = _bridge(_result(source="local_client"))

    bridge.handle("add_account", {})
    bridge.handle("add_account", {})

    assert len(bridge.accounts) == 1
    assert bridge.accounts[0]["lastUpdated"] == "Active VALORANT session"


def test_readding_auto_recognized_account_preserves_known_platform_region() -> None:
    bridge, repository, _ = _bridge(_result(source="local_client"))
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "EUW", "owned-puuid")
    )
    bridge._load_database()

    state = bridge.handle("add_account", {})

    assert state["accounts"][0]["region"] == "EUW"
    assert repository.accounts["owned-puuid"].region == "euw"


def test_local_client_onboarding_never_writes_session_secrets() -> None:
    bridge, repository, vault = _bridge(_result(source="local_client"))

    state = bridge.handle("add_account", {})

    assert repository.accounts["owned-puuid"].display_name == "Peak Player#EUW"
    assert vault.entries == {}
    assert bridge.accounts[0]["connected"] is False
    assert state["accounts"][0]["canConnectQr"] is False
    assert state["accounts"][0]["canSaveRiotSession"] is True
    assert state["accounts"][0]["canSetupMfa"] is False
    assert "reusable session was not available" in state["operationNotice"]


def test_browser_onboarding_rejects_non_allowlisted_cookie() -> None:
    bridge, repository, vault = _bridge(
        _result(cookies={"ssid": "session-cookie", "unexpected": "must-not-store"})
    )

    with pytest.raises(ValueError, match="cookies are invalid"):
        bridge.handle("add_account", {})

    assert repository.accounts == {}
    assert vault.entries == {}


def test_locked_bridge_does_not_start_account_onboarding() -> None:
    bridge, repository, vault = _bridge(_result(source="local_client"))
    bridge._locked = True

    with pytest.raises(PermissionError, match="Unlock Peaks"):
        bridge.handle("add_account", {})

    assert repository.accounts == {}
    assert vault.entries == {}


def test_added_account_is_immediately_hydrated_and_persisted() -> None:
    bridge, repository, _ = _bridge(_result(source="local_client"))
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda puuid: (
            {
                "level": 284,
                "ranks": [
                    {
                        "game": "valorant",
                        "tier": "Ascendant 1",
                        "rating": 48,
                        "peak_tier": "Immortal 1",
                    }
                ],
                "matches": [
                    {
                        "match_id": "match-1",
                        "game": "valorant",
                        "played_at": "2026-05-03T03:09:37+00:00",
                        "result": "unknown",
                        "queue": "competitive",
                    }
                ],
            }
            if puuid == "owned-puuid"
            else None
        )
    )

    state = bridge.handle("add_account", {})

    account = state["accounts"][0]
    assert account["connected"] is False
    assert account["level"] == 284
    assert account["ranks"] == [
        {"game": "VALORANT", "tier": "ascendant", "division": "1", "rating": 48}
    ]
    assert account["matches"][0]["id"] == "match-1"
    assert account["matches"][0]["mode"] == "competitive"
    assert repository.accounts["owned-puuid"].rank_for(Game.VALORANT).label == "Ascendant 1"  # type: ignore[union-attr]
    assert repository.accounts["owned-puuid"].level == 284
    assert repository.matches["owned-puuid"][0].match_id == "match-1"


def test_match_snapshot_preserves_newest_first_order_and_deduplicates() -> None:
    account = {
        "matches": [
            {"id": "older", "game": "VALORANT", "result": "Recent match"},
            {"id": "stale", "game": "VALORANT", "result": "Recent match"},
        ]
    }
    snapshot = {
        "matches": [
            {
                "match_id": "newest",
                "game": "valorant",
                "played_at": "2026-05-03T04:00:00+00:00",
                "result": "unknown",
                "queue": "competitive",
            },
            {
                "match_id": "older",
                "game": "valorant",
                "played_at": "2026-05-03T03:00:00+00:00",
                "result": "unknown",
                "queue": "competitive",
            },
        ]
    }

    Bridge._merge_account_snapshot(account, snapshot)

    assert [match["id"] for match in account["matches"]] == ["newest", "older", "stale"]


def test_activity_command_polls_real_service_and_keeps_puuid_out_of_state() -> None:
    bridge, _, _ = _bridge(_result())
    bridge.accounts = [
        {
            "id": "local-account-handle",
            "puuid": "private-provider-puuid",
            "riotId": "Peak Player#EUW",
            "region": "EUW",
            "connected": False,
            "owned": True,
            "ranks": [],
            "matches": [],
        }
    ]
    calls = 0
    expected_status = {
        "detected": True,
        "label": "Verified Riot lockfile found",
        "game": "VALORANT",
    }

    class FakeCurrentGame:
        def __init__(self) -> None:
            self.client_status = dict(expected_status)

        def detect(self) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {
                "game": "VALORANT",
                "mode": "Competitive",
                "map": "Ascent",
                "teams": [],
            }

    bridge._current_game_factory = FakeCurrentGame

    state = bridge.handle("activity", {})

    assert calls == 1
    assert state["gameDetected"] is True
    assert state["currentMatch"]["game"] == "VALORANT"
    assert state["riotClient"] == expected_status
    assert "puuid" not in state["accounts"][0]
    assert "private-provider-puuid" not in repr(state)


@pytest.mark.parametrize(("provider_game", "display_game"), [("League", "League of Legends"), ("TFT", "Teamfight Tactics")])
def test_lobby_activity_normalizes_game_and_preserves_public_roster_fields(provider_game: str, display_game: str) -> None:
    bridge, _, _ = _bridge(_result())

    class CurrentSession:
        detection_available = True

        def __init__(self) -> None:
            self.client_status = {"detected": True, "label": "Connected", "game": provider_game}

        def detect(self) -> dict[str, Any]:
            return {"game": provider_game, "phase": "lobby", "partySize": 2, "partyMax": 8, "teams": [{"name": "Party", "players": [
                {"name": "Visible#EUW", "riotId": "Visible#EUW", "self": True, "ready": True, "leader": True, "role": "MIDDLE", "rank": "Gold II", "puuid": "must-not-reach-renderer"},
                {"name": "Secret#EUW", "riotId": "Secret#EUW", "hidden": True, "puuid": "another-private-identifier"},
            ]}]}

    bridge._current_game_factory = CurrentSession
    state = bridge.handle("activity", {})
    current = state["currentMatch"]
    assert current["game"] == display_game
    assert current["phase"] == "lobby" and current["partySize"] == 2
    player = current["teams"][0]["players"][0]
    assert player["ready"] and player["leader"] and player["self"]
    assert player["role"] == "MIDDLE" and player["rank"] == "Gold II"
    assert "must-not-reach-renderer" not in repr(current)
    assert "another-private-identifier" not in repr(current)
    assert "Secret#EUW" not in repr(current)


def test_first_activity_poll_hydrates_existing_account_and_then_throttles() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    refresh_calls = 0

    def snapshot(_puuid: str) -> dict[str, Any]:
        nonlocal refresh_calls
        refresh_calls += 1
        return {
            "ranks": [{"game": "valorant", "tier": "Ascendant 1", "rating": 47}],
            "matches": [],
        }

    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=snapshot
    )
    bridge._current_game_factory = lambda: SimpleNamespace(
        client_status={"detected": True, "label": "VALORANT active", "game": "VALORANT"},
        detect=lambda: None,
    )

    first = bridge.handle("activity", {})
    second = bridge.handle("activity", {})

    assert refresh_calls == 1
    assert first["accounts"][0]["ranks"][0]["tier"] == "ascendant"
    assert second["accounts"][0]["ranks"] == first["accounts"][0]["ranks"]
    assert repository.accounts["owned-puuid"].rank_for(Game.VALORANT).label == "Ascendant 1"  # type: ignore[union-attr]


def test_database_load_restores_persisted_rank_and_match_views() -> None:
    bridge, repository, _ = _bridge(_result())
    account = Account(
        "owned-puuid",
        "Peak Player",
        "EUW",
        "global",
        "owned-puuid",
        ranks=(RankInfo(Game.VALORANT, "diamond", "2", rating=55),),
        level=197,
    )
    repository.add_account(account)
    repository.add_match(
        MatchRecord(
            "match-1",
            account.account_id,
            Game.VALORANT,
            datetime.now(UTC),
            MatchResult.WIN,
            queue="competitive",
        )
    )

    bridge._load_database()

    loaded = bridge.accounts[0]
    assert loaded["ranks"][0]["game"] == "VALORANT"
    assert loaded["ranks"][0]["tier"] == "diamond"
    assert loaded["ranks"][0]["division"] == "2"
    assert loaded["level"] == 197
    assert loaded["matches"][0]["id"] == "match-1"
    assert loaded["matches"][0]["result"] == "Win"


def test_manual_refresh_uses_restored_official_provider_when_local_is_unavailable() -> None:
    bridge, repository, vault = _bridge(_result())
    repository.add_account(Account("owned-puuid", "Peak Player", "EUW", "EUW", "owned-puuid"))
    bridge._load_database()
    vault.values["configuration:riot_api_key"] = "RGAPI-user-owned-key"

    class FakeProvider:
        def __init__(self) -> None:
            self.key = ""

        def set_api_key(self, value: str) -> None:
            self.key = value

        def clear_api_key(self) -> None:
            self.key = ""

        def account_overview(self, riot_id: str, region: str) -> dict[str, Any]:
            assert (riot_id, region) == ("Peak Player#EUW", "EUW")
            return {
                "ranks": [{"game": "League", "tier": "Gold IV", "rating": "72 LP"}],
                "matches": [],
            }

    provider = FakeProvider()
    bridge._riot_search_service = provider
    bridge._load_sensitive_configuration()

    state = bridge.handle("refresh", {"accountId": "owned-puuid"})

    assert provider.key == "RGAPI-user-owned-key"
    assert state["settings"]["riotApiConfigured"] is True
    assert state["accounts"][0]["ranks"][0] == {
        "game": "League of Legends",
        "tier": "gold",
        "division": "IV",
        "rating": 72,
    }
    assert repository.accounts["owned-puuid"].rank_for(Game.LEAGUE_OF_LEGENDS).label == "Gold IV"  # type: ignore[union-attr]


def test_manual_refresh_never_guesses_official_region_for_auto_added_account() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge.settings["riotApiConfigured"] = True

    class FakeProvider:
        def account_overview(self, _riot_id: str, _region: str) -> dict[str, Any]:
            raise AssertionError("GLOBAL must not be guessed as a League platform")

    bridge._riot_search_service = FakeProvider()

    with pytest.raises(RuntimeError, match="authoritative account region"):
        bridge.handle("refresh", {"accountId": "owned-puuid"})


def test_unknown_official_region_still_allows_local_valorant_refresh() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge.settings["riotApiConfigured"] = True
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda _puuid: {
            "ranks": [{"game": "valorant", "tier": "Diamond 2", "rating": 64}],
            "matches": [],
        }
    )

    class FakeProvider:
        def account_overview(self, _riot_id: str, _region: str) -> dict[str, Any]:
            raise AssertionError("GLOBAL must not be guessed as a League platform")

    bridge._riot_search_service = FakeProvider()

    state = bridge.handle("refresh", {"accountId": "owned-puuid"})

    assert state["accounts"][0]["ranks"][0]["game"] == "VALORANT"
    assert repository.accounts["owned-puuid"].rank_for(Game.VALORANT).label == "Diamond 2"  # type: ignore[union-attr]


def test_native_tft_refresh_repairs_persisted_unranked_without_api_key() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(Account("owned-puuid", "Peak Player", "EUW", "EUW", "owned-puuid", ranks=(RankInfo(Game.TFT, "unranked"),)))
    bridge._load_database()
    bridge.settings["riotApiConfigured"] = False
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_league_snapshot=lambda puuid: {
            "ranks": [{"game": "TFT", "tier": "Gold III", "rating": 68}], "level": 86,
        } if puuid == "owned-puuid" else None,
        owned_valorant_snapshot=lambda _puuid: None,
        valorant_snapshot_failure="valorant_session_inactive",
    )
    state = bridge.handle("refresh", {"accountId": "owned-puuid"})
    rank = repository.accounts["owned-puuid"].rank_for(Game.TFT)
    assert rank is not None and rank.label == "Gold III" and rank.rating == 68
    assert state["accounts"][0]["ranks"] == [{"game": "Teamfight Tactics", "tier": "gold", "division": "III", "rating": 68}]


def test_manual_refresh_reports_service_route_failure_instead_of_account_mismatch() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda _puuid: None,
        valorant_snapshot_failure="service_routes",
    )

    with pytest.raises(RuntimeError, match="current Riot service routes"):
        bridge.handle("refresh", {"accountId": "owned-puuid"})


def test_manual_refresh_reports_inactive_valorant_session() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda _puuid: None,
        valorant_snapshot_failure="valorant_session_inactive",
    )

    with pytest.raises(RuntimeError, match="VALORANT is not active"):
        bridge.handle("refresh", {"accountId": "owned-puuid"})


def test_manual_refresh_reports_valorant_entitlements_startup_delay() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda _puuid: None,
        valorant_snapshot_failure="entitlements_not_ready",
    )

    with pytest.raises(RuntimeError, match="not made VALORANT's entitlement token available"):
        bridge.handle("refresh", {"accountId": "owned-puuid"})


def test_manual_refresh_reports_active_riot_identity_mismatch() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda _puuid: None,
        valorant_snapshot_failure="identity_mismatch",
    )

    with pytest.raises(RuntimeError, match="different Riot account"):
        bridge.handle("refresh", {"accountId": "owned-puuid"})


def test_global_account_recovers_identity_bound_league_region_before_remote_refresh() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(
        Account("owned-puuid", "Peak Player", "EUW", "GLOBAL", "owned-puuid")
    )
    bridge._load_database()
    bridge.settings["riotApiConfigured"] = True
    recovered_puuids: list[str] = []
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_league_platform_region=lambda puuid: recovered_puuids.append(puuid) or "EUW",
        owned_valorant_snapshot=lambda _puuid: None,
    )
    provider_calls: list[tuple[str, str]] = []

    class FakeProvider:
        def account_overview(self, riot_id: str, region: str) -> dict[str, Any]:
            provider_calls.append((riot_id, region))
            return {
                "ranks": [{"game": "League", "tier": "Gold IV", "rating": "72 LP"}],
                "matches": [],
            }

    bridge._riot_search_service = FakeProvider()

    state = bridge.handle("refresh", {"accountId": "owned-puuid"})

    assert recovered_puuids == ["owned-puuid"]
    assert provider_calls == [("Peak Player#EUW", "EUW")]
    assert state["accounts"][0]["region"] == "EUW"
    assert repository.accounts["owned-puuid"].region == "euw"


def _live_match_bridge(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Bridge, SimpleNamespace, list[float], list[str]]:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(Account("owned-puuid", "Peak Player", "EUW", "EUW", "owned-puuid"))
    bridge._load_database()
    clock = [100.0]
    monkeypatch.setattr("peaks.bridge.monotonic", lambda: clock[0])
    bridge._next_owned_account_refresh_at = 999.0
    service = SimpleNamespace(
        detection_available=True,
        active_account_puuid="owned-puuid",
        client_status={"detected": True, "label": "VALORANT active", "game": "VALORANT"},
        value={"id": "observed-match", "phase": "live", "game": "VALORANT", "teams": []},
    )
    service.detect = lambda: service.value
    bridge._current_game_service = service
    calls: list[str] = []
    bridge._account_refresh_factory = lambda: SimpleNamespace(
        owned_valorant_snapshot=lambda puuid: calls.append(puuid) or {"matches": []}
    )
    return bridge, service, clock, calls


def test_match_fetch_progress_is_not_persisted_or_removed_from_live_snapshot() -> None:
    bridge, repository, _ = _bridge(_result())
    snapshot = {"matches": [{
        "match_id": "report",
        "game": "valorant",
        "played_at": "2026-09-16T12:00:00+00:00",
        "metadata": {"enrichmentPending": True, "teams": [{"name": "Blue", "players": [
            {"name": "Player#EUW", "riotId": "Player#EUW", "statsLoading": True, "stats": {"kills": 12}},
        ]}]},
    }]}
    bridge._persist_account_snapshot("owned-puuid", snapshot)
    stored = repository.matches["owned-puuid"][0]
    assert "enrichmentPending" not in stored.metadata
    assert "statsLoading" not in stored.metadata["teams"][0]["players"][0]
    assert stored.metadata["teams"][0]["players"][0]["stats"] == {"kills": 12}
    account: dict[str, Any] = {}
    bridge._merge_account_snapshot(account, snapshot)
    assert account["matches"][0]["enrichmentPending"] is True
    assert account["matches"][0]["teams"][0]["players"][0]["statsLoading"] is True


def test_report_priority_refresh_keeps_owned_identity_binding_and_pending_metadata() -> None:
    bridge, repository, _ = _bridge(_result())
    repository.add_account(Account("owned-puuid", "Peak Player", "EUW", "EUW", "owned-puuid"))
    bridge._load_database()
    calls: list[tuple[str, str | None]] = []

    def snapshot(puuid: str, *, priority_match_id: str | None = None) -> dict[str, Any]:
        calls.append((puuid, priority_match_id))
        return {"matches": [{"match_id": "owned-match", "game": "valorant", "metadata": {"enrichmentPending": True}}]}

    bridge._account_refresh_factory = lambda: SimpleNamespace(owned_valorant_snapshot=snapshot)
    state = bridge.handle("refresh", {"accountId": "owned-puuid", "priorityMatchId": "owned-match"})
    assert calls == [("owned-puuid", "owned-match")]
    assert state["accounts"][0]["matches"][0]["enrichmentPending"] is True
    with pytest.raises(ValueError, match="owned account"):
        bridge.handle("refresh", {"priorityMatchId": "owned-match"})
    with pytest.raises(ValueError, match="valid match"):
        bridge.handle("refresh", {"accountId": "owned-puuid", "priorityMatchId": "../other"})
    assert len(calls) == 1


def test_old_open_report_survives_newest_history_page_refresh() -> None:
    incoming = [{"match_id": f"new-{index}", "game": "valorant"} for index in range(20)]
    incoming.append({"match_id": "old-open-report", "game": "valorant", "metadata": {
        "teams": [{"players": [{"riotId": "Resolved#EUW", "name": "Resolved#EUW"}]}],
    }})
    account: dict[str, Any] = {"matches": [{"id": "old-open-report", "teams": []}]}
    Bridge._merge_account_snapshot(account, {"matches": incoming}, priority_match_id="old-open-report")
    assert len(account["matches"]) == 20
    assert account["matches"][0]["id"] == "new-0"
    assert account["matches"][-1]["id"] == "old-open-report"
    assert account["matches"][-1]["teams"][0]["players"][0]["riotId"] == "Resolved#EUW"


def test_confirmed_match_end_refreshes_exact_owned_account_and_waits_for_final_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge, service, clock, calls = _live_match_bridge(monkeypatch)
    first = bridge.handle("activity", {})
    assert first["currentMatch"]["accountId"] == first["accounts"][0]["id"]
    assert "owned-puuid" not in repr(first)
    assert calls == []

    service.value = None
    bridge.handle("activity", {})
    assert calls == ["owned-puuid"]
    assert bridge._post_match_refresh is not None
    bridge.handle("activity", {})
    assert len(calls) == 1

    def snapshot(puuid: str) -> dict[str, Any]:
        calls.append(puuid)
        return {"matches": [{
            "match_id": "observed-match", "game": "valorant", "result": "win",
            "played_at": "2026-09-04T10:00:00+00:00", "map_name": "Ascent",
        }]}

    bridge._account_refresh_factory = lambda: SimpleNamespace(owned_valorant_snapshot=snapshot)
    clock[0] += 15
    final = bridge.handle("activity", {})
    assert len(calls) == 2
    assert final["accounts"][0]["matches"][0]["id"] == "observed-match"
    assert final["accounts"][0]["matches"][0]["result"] == "Win"
    assert bridge._post_match_refresh is None
    clock[0] += 15
    bridge.handle("activity", {})
    assert len(calls) == 2


def test_transient_detection_failure_preserves_stale_match_without_end_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge, service, _clock, calls = _live_match_bridge(monkeypatch)
    bridge.handle("activity", {})
    service.value = None
    service.detection_available = False
    stale = bridge.handle("activity", {})
    assert stale["currentMatch"]["id"] == "observed-match"
    assert stale["currentMatch"]["isStale"] is True
    assert calls == []
    assert getattr(bridge, "_post_match_refresh", None) is None

    def failed_detect() -> None:
        raise RuntimeError("temporary failure")

    service.detect = failed_detect
    failed = bridge.handle("activity", {})
    assert failed["currentMatch"]["id"] == "observed-match"
    assert failed["currentMatch"]["isStale"] is True
    assert calls == []


@pytest.mark.parametrize("scenario", ["pregame", "unowned", "no_id", "startup_idle"])
def test_unobserved_or_unowned_matches_never_schedule_completion_refresh(
    monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    bridge, service, _clock, calls = _live_match_bridge(monkeypatch)
    if scenario == "pregame":
        service.value["phase"] = "pregame"
    elif scenario == "unowned":
        service.active_account_puuid = "another-puuid"
    elif scenario == "no_id":
        service.value.pop("id")
    else:
        service.value = None
    bridge.handle("activity", {})
    service.value = None
    bridge.handle("activity", {})
    assert calls == []
    assert getattr(bridge, "_post_match_refresh", None) is None


def test_post_match_refresh_has_bounded_attempts_when_history_is_delayed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge, service, clock, calls = _live_match_bridge(monkeypatch)
    bridge.handle("activity", {})
    service.value = None
    for timestamp in (100.0, 115.0, 145.0, 205.0):
        clock[0] = timestamp
        bridge.handle("activity", {})
    assert calls == ["owned-puuid"] * 4
    assert bridge._post_match_refresh is None
    clock[0] = 220.0
    bridge.handle("activity", {})
    assert len(calls) == 4


def test_recorded_analytics_projection_is_bounded_and_excludes_provider_material() -> None:
    stats = _match_stats({
        "kills": 3,
        "subject": "private-provider-puuid",
        "weaponUsage": [{"weapon": "Vandal", "kills": 2, "subject": "private-id"}],
        "roundKills": [3, 0],
    })
    assert stats == {
        "kills": 3,
        "weaponUsage": [{"weapon": "Vandal", "kills": 2}],
        "roundKills": [3, 0],
    }
    assert _match_stats({"roundKills": [1, True, 3]}) == {}
    assert _match_stats({"roundKills": [0] * 129}) == {}
    assert _match_stats({"weaponUsage": [{"weapon": "Vandal", "kills": 1}] * 33}) == {}
    assert _match_stats({"weaponUsage": [{"weapon": "unsafe\nname", "kills": 1}]}) == {}



def test_onboarding_stores_each_games_region_without_conflating_them() -> None:
    result = _result(source="local_client")
    result.identity.league_region = "euw1"
    result.identity.valorant_region = "eu"
    bridge, repository, _ = _bridge(result)
    state = bridge.handle("add_account", {})
    assert state["accounts"][0]["leagueRegion"] == "EUW"
    assert state["accounts"][0]["valorantRegion"] == "EU"
    stored = repository.accounts["owned-puuid"]
    assert (stored.region, stored.valorant_region) == ("euw", "EU")
    bridge._load_database()
    assert bridge.accounts[0]["valorantRegion"] == "EU"



def test_local_valorant_route_fills_only_missing_region_and_preserves_league() -> None:
    bridge, repository, _ = _bridge(_result(source="local_client"))
    repository.add_account(Account("owned-puuid", "Peak Player", "TEST", "EUW", "owned-puuid"))
    bridge._load_database()
    snapshot = {"valorantRegion": "EU"}
    bridge._persist_account_snapshot("owned-puuid", snapshot)
    bridge._merge_account_snapshot(bridge.accounts[0], snapshot)
    assert repository.accounts["owned-puuid"].valorant_region == "EU"
    assert bridge.accounts[0]["valorantRegion"] == "EU"
    assert bridge.accounts[0]["region"] == "EUW"
    # An authoritative account affinity takes precedence over the local shard.
    bridge._persist_account_snapshot("owned-puuid", {"valorantRegion": "NA"})
    bridge._merge_account_snapshot(bridge.accounts[0], {"valorantRegion": "NA"})
    assert repository.accounts["owned-puuid"].valorant_region == "EU"
    assert bridge.accounts[0]["valorantRegion"] == "EU"

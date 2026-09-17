from __future__ import annotations

import json
from pathlib import Path

import pytest

import peaks.ui.controller as controller_module
from peaks.adapters.persistence import Database, InMemoryPepperProvider, SecretVault
from peaks.adapters.riot.session_import import (
    AuthenticatedRiotIdentity,
    ImportedRiotSession,
    RiotSessionImporter,
)
from peaks.ui.controller import AppController

COOKIE_VALUES = {
    "ssid": "ssid-value",
    "clid": "clid-value",
    "csid": "csid-value",
    "tdid": "tdid-value",
    "sub": "cookie-puuid",
}


class FakeSessionImporter:
    def __init__(
        self,
        *,
        imported_puuid: str = "cookie-puuid",
        identity_puuid: str = "cookie-puuid",
        game_name: str | None = "Player",
        tag_line: str | None = "EUW",
    ) -> None:
        self.imported_puuid = imported_puuid
        self.identity_puuid = identity_puuid
        self.game_name = game_name
        self.tag_line = tag_line
        self.import_calls = 0
        self.fetch_calls: list[str] = []
        self.mint_calls: list[dict[str, str]] = []
        self.closed = False

    def import_current_session(self) -> ImportedRiotSession:
        self.import_calls += 1
        cookies = dict(COOKIE_VALUES)
        cookies["sub"] = self.imported_puuid
        return ImportedRiotSession(
            puuid=self.imported_puuid,
            cookies=cookies,
            access_token="short-lived-token",
        )

    def fetch_identity(self, access_token: str) -> AuthenticatedRiotIdentity:
        self.fetch_calls.append(access_token)
        return AuthenticatedRiotIdentity(
            puuid=self.identity_puuid,
            game_name=self.game_name,
            tag_line=self.tag_line,
        )

    def mint_access_token(self, cookies: dict[str, str]) -> str:
        self.mint_calls.append(dict(cookies))
        return "fresh-qr-token"

    def close(self) -> None:
        self.closed = True


class FakeQrApprover:
    def __init__(self) -> None:
        self.session_info_tokens: list[str] = []
        self.approval_tokens: list[str] = []
        self.close_calls = 0

    def session_info(
        self,
        parsed: object,
        *,
        access_token: str,
        selected_account_puuid: str,
    ) -> dict[str, str]:
        assert selected_account_puuid == "cookie-puuid"
        self.session_info_tokens.append(access_token)
        return {"location": "Paris, FR", "device": "Riot Client"}

    def approve(self, parsed: object, credentials: object, *, user_approved: bool) -> dict[str, object]:
        assert user_approved is True
        self.approval_tokens.append(str(getattr(credentials, "access_token", "")))
        return {"status": 200}

    def close(self) -> None:
        self.close_calls += 1


@pytest.fixture
def session_services(qapp, tmp_path: Path):
    database = Database(tmp_path / "peaks.sqlite3")
    vault = SecretVault(
        tmp_path / "vault.json",
        pepper_provider=InMemoryPepperProvider(b"controller-import-pepper-0123456789"),
    )
    controller = AppController(repository=database, vault=vault, demo=False)
    controller._lock_timer.stop()
    controller._detection_timer.stop()
    controller.submitPin("1234")
    controller.submitPin("1234")
    assert controller.locked is False
    yield controller, database, vault
    controller.lockNow()
    controller.deleteLater()
    database.close()


def _account(*, puuid: str | None = None) -> dict[str, object]:
    return {
        "id": "owned",
        "riotId": "Player#EUW",
        "region": "EUW",
        "owned": True,
        "connected": False,
        "puuid": puuid,
        "totpAvailable": False,
        "ranks": [],
        "matches": [],
    }


def test_import_binds_identity_persists_cookies_and_never_token(session_services, qtbot) -> None:
    controller, database, vault = session_services
    importer = FakeSessionImporter()
    controller._session_importer_factory = lambda: importer
    controller._accounts = [_account()]

    controller.importCurrentRiotSession("owned")
    qtbot.waitUntil(lambda: controller.qrBusy is False, timeout=2_000)

    account = controller.accounts[0]
    assert account["puuid"] == "cookie-puuid"
    assert account["connected"] is True
    stored = vault.get("owned:riot_session_cookies")
    assert stored == json.dumps(COOKIE_VALUES, separators=(",", ":"), sort_keys=True)
    assert vault.get("owned:riot_access_token") is None
    assert database.get_account("owned").puuid == "cookie-puuid"  # type: ignore[union-attr]
    assert importer.fetch_calls == ["short-lived-token"]
    assert importer.closed is True


@pytest.mark.parametrize(
    ("imported_puuid", "identity_puuid", "stored_puuid", "game_name", "tag_line", "message"),
    [
        ("cookie-puuid", "other-puuid", None, "Player", "EUW", "identity could not be verified"),
        ("cookie-puuid", "cookie-puuid", "other-puuid", "Player", "EUW", "different account"),
        ("cookie-puuid", "cookie-puuid", None, "Other", "EUW", "does not match"),
        ("cookie-puuid", "cookie-puuid", None, "Player", "NA", "does not match"),
    ],
)
def test_import_rejects_identity_binding_mismatches(
    session_services,
    qtbot,
    imported_puuid: str,
    identity_puuid: str,
    stored_puuid: str | None,
    game_name: str,
    tag_line: str,
    message: str,
) -> None:
    controller, _, vault = session_services
    importer = FakeSessionImporter(
        imported_puuid=imported_puuid,
        identity_puuid=identity_puuid,
        game_name=game_name,
        tag_line=tag_line,
    )
    controller._session_importer_factory = lambda: importer
    controller._accounts = [_account(puuid=stored_puuid)]

    controller.importCurrentRiotSession("owned")
    qtbot.waitUntil(lambda: controller.qrBusy is False, timeout=2_000)

    assert message in controller.toastText
    assert vault.get("owned:riot_session_cookies") is None
    assert controller.accounts[0].get("connected") is False
    assert importer.closed is True


def test_import_off_windows_is_actionable_and_safe(session_services, qtbot) -> None:
    controller, _, vault = session_services

    def unsupported_importer() -> RiotSessionImporter:
        return RiotSessionImporter(platform_name="Darwin", env={})

    controller._session_importer_factory = unsupported_importer
    controller._accounts = [_account()]
    controller.importCurrentRiotSession("owned")
    qtbot.waitUntil(lambda: controller.qrBusy is False, timeout=2_000)

    assert controller.toastText == "Import current Riot session is available on Windows only"
    assert vault.get("owned:riot_session_cookies") is None


def test_qr_mints_fresh_token_and_reuses_it_without_persisting(session_services, qtbot) -> None:
    controller, _, vault = session_services
    importer = FakeSessionImporter()
    approver = FakeQrApprover()
    controller._session_importer_factory = lambda: importer
    controller._qr_approver = approver
    controller._accounts = [_account(puuid="cookie-puuid")]
    vault.put(
        "owned:riot_session_cookies",
        json.dumps(COOKIE_VALUES, separators=(",", ":"), sort_keys=True),
    )

    controller._qr_decoded(
        "owned",
        "https://qr.riotgames.com?suuid=123e4567-e89b-12d3-a456-426614174000&cluster=ec1",
        None,
    )
    qtbot.waitUntil(lambda: controller.qrPromptOpen is True, timeout=2_000)
    assert importer.mint_calls == [COOKIE_VALUES]
    assert approver.session_info_tokens == ["fresh-qr-token"]
    assert vault.get("owned:riot_access_token") is None

    controller.confirmQr(True)
    qtbot.waitUntil(lambda: controller.qrBusy is False, timeout=2_000)
    assert approver.approval_tokens == ["fresh-qr-token"]
    assert importer.closed is True


def test_qr_invalid_cookie_bundle_does_not_fall_back_to_legacy_token(session_services, qtbot) -> None:
    controller, _, vault = session_services
    controller._accounts = [_account(puuid="cookie-puuid")]
    vault.put("owned:riot_session_cookies", '{"unknown":"value"}')
    vault.put("owned:riot_access_token", "legacy-token")

    controller._qr_decoded(
        "owned",
        "https://qr.riotgames.com?suuid=123e4567-e89b-12d3-a456-426614174000&cluster=ec1",
        None,
    )

    assert controller.qrPromptOpen is False
    assert controller.toastText == "The saved Riot session is invalid; import it again"
    assert controller.qrBusy is False


def test_primary_connect_imports_missing_session_then_resumes_qr_scan(
    session_services, qtbot, monkeypatch
) -> None:
    controller, _, vault = session_services
    importer = FakeSessionImporter()
    approver = FakeQrApprover()
    controller._session_importer_factory = lambda: importer
    controller._qr_approver = approver
    controller._accounts = [_account()]
    qr_text = (
        "https://qr.riotgames.com?"
        "suuid=123e4567-e89b-12d3-a456-426614174000&cluster=ec1"
    )
    monkeypatch.setattr(controller_module, "capture_riot_client_windows", lambda: [object()])
    monkeypatch.setattr(controller_module, "decode_qr_images", lambda screenshots: qr_text)

    controller.scanRiotQr("owned")
    qtbot.waitUntil(lambda: controller.qrPromptOpen is True, timeout=2_000)

    assert importer.import_calls == 1
    assert importer.mint_calls == [COOKIE_VALUES]
    assert approver.session_info_tokens == ["fresh-qr-token"]
    assert controller.accounts[0]["puuid"] == "cookie-puuid"
    assert vault.get("owned:riot_access_token") is None

    controller.confirmQr(True)
    qtbot.waitUntil(lambda: controller.qrBusy is False, timeout=2_000)
    assert approver.approval_tokens == ["fresh-qr-token"]


def test_primary_connect_off_windows_import_is_actionable(session_services, qtbot) -> None:
    controller, _, vault = session_services

    def unsupported_importer() -> RiotSessionImporter:
        return RiotSessionImporter(platform_name="Darwin", env={})

    controller._session_importer_factory = unsupported_importer
    controller._accounts = [_account()]
    controller.scanRiotQr("owned")
    qtbot.waitUntil(lambda: controller.qrBusy is False, timeout=2_000)

    assert controller.toastText == "Import current Riot session is available on Windows only"
    assert vault.get("owned:riot_session_cookies") is None


def test_lock_closes_and_drops_qr_approval_service(session_services) -> None:
    controller, _, _ = session_services
    approver = FakeQrApprover()
    controller._qr_approver = approver

    controller.lockNow()

    assert approver.close_calls == 1
    assert controller._qr_approver is None

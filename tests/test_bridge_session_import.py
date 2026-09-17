from __future__ import annotations

import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import pytest
import requests

from peaks.adapters.persistence import InMemoryPepperProvider, SecretVault
from peaks.adapters.riot.session_import import (
    AuthenticatedRiotIdentity,
    RiotSessionImporter,
    SessionAuthorizationHTTPError,
    SessionReauthenticationRequired,
    SessionSettingsError,
)
from peaks.bridge import Bridge
from peaks.domain.models import Account, SecretEntry


class FakeRepository:
    def __init__(self) -> None:
        self.accounts = {
            "owned-puuid": Account(
                "owned-puuid", "Peak Player", "EUW", "global", "owned-puuid"
            )
        }

    def get_account(self, account_id: str) -> Any | None:
        return self.accounts.get(account_id)

    def add_account(self, account: Any) -> Any:
        self.accounts[account.account_id] = account
        return account


class FakeVault:
    def __init__(self) -> None:
        self.entries: dict[str, Any] = {}

    def get_entry(self, account_id: str) -> Any | None:
        return self.entries.get(account_id)

    def put_entry(self, entry: Any) -> None:
        self.entries[entry.account_id] = entry

    def delete(self, account_id: str) -> bool:
        return self.entries.pop(account_id, None) is not None


class FakeImporter:
    def __init__(self, *, local_error: Exception | None = None, puuid: str = "owned-puuid") -> None:
        self.local_error = local_error
        self.puuid = puuid
        self.closed = False
        self.minted_cookies: dict[str, str] | None = None
        self.identity_tokens: list[str] = []

    def import_current_session(self) -> Any:
        if self.local_error is not None:
            raise self.local_error
        return SimpleNamespace(
            puuid=self.puuid,
            cookies={"ssid": "LOCAL-COOKIE-SECRET", "sub": self.puuid},
            access_token="LOCAL-TOKEN-SECRET",
        )

    def mint_access_token(self, cookies: dict[str, str]) -> str:
        self.minted_cookies = dict(cookies)
        return "BROWSER-TOKEN-SECRET"

    def fetch_identity(self, token: str) -> AuthenticatedRiotIdentity:
        self.identity_tokens.append(token)
        return AuthenticatedRiotIdentity(self.puuid, "Peak Player", "EUW")

    def close(self) -> None:
        self.closed = True


class FakeQrApprover:
    def __init__(self) -> None:
        self.session_info_calls: list[tuple[object, str, str]] = []
        self.approval_calls: list[tuple[object, object, bool]] = []
        self.totp_approval_calls: list[tuple[object, object, bool]] = []
        self.closed = False

    def session_info(
        self,
        qr: object,
        *,
        access_token: str,
        selected_account_puuid: str,
    ) -> object:
        self.session_info_calls.append((qr, access_token, selected_account_puuid))
        return SimpleNamespace(device="Riot Client")

    def approve(self, qr: object, credentials: object, *, user_approved: bool) -> object:
        self.approval_calls.append((qr, credentials, user_approved))
        return SimpleNamespace(method="session", status_code=200)

    def approve_totp(
        self,
        qr: object,
        credentials: object,
        *,
        user_approved: bool,
    ) -> object:
        self.totp_approval_calls.append((qr, credentials, user_approved))
        return SimpleNamespace(method="totp", status_code=200)

    def close(self) -> None:
        self.closed = True


def _bridge(importer: FakeImporter) -> tuple[Bridge, FakeRepository, FakeVault, io.StringIO]:
    repository = FakeRepository()
    vault = FakeVault()
    log_stream = io.StringIO()
    logger = logging.getLogger(f"bridge-session-test-{id(importer)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(log_stream)
    logger.addHandler(handler)

    bridge = Bridge.__new__(Bridge)
    bridge.demo = False
    bridge._locked = False
    bridge._pin_mode = "unlock"
    bridge._pending_pin = ""
    bridge._session_importer_factory = lambda: importer
    bridge._riot_browser_login = None
    bridge._logger = logger
    bridge._repository = repository
    bridge._vault = vault
    bridge.accounts = [
        {
            "id": "owned-puuid",
            "riotId": "Peak Player#EUW",
            "region": "GLOBAL",
            "puuid": "owned-puuid",
            "owned": True,
            "connected": False,
            "hasTotp": False,
            "ranks": [],
            "matches": [],
        }
    ]
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
    return bridge, repository, vault, log_stream


def test_import_session_identity_binds_and_saves_only_allowlisted_cookies() -> None:
    importer = FakeImporter()
    bridge, repository, vault, log_stream = _bridge(importer)

    state = bridge.handle("import_session", {"accountId": "owned-puuid"})

    assert state["accounts"][0]["connected"] is True
    assert state["accounts"][0]["canConnectQr"] is True
    assert state["accounts"][0]["canSaveRiotSession"] is True
    assert state["accounts"][0]["canSetupMfa"] is True
    assert repository.accounts["owned-puuid"].puuid == "owned-puuid"
    stored = vault.entries["owned-puuid"]
    assert dict(stored.cookies) == {
        "ssid": "LOCAL-COOKIE-SECRET",
        "sub": "owned-puuid",
    }
    assert stored.access_token is None
    assert stored.refresh_token is None
    assert importer.closed is True
    diagnostic = log_stream.getvalue()
    assert "bridge.session_import.local.complete" in diagnostic
    assert "bridge.session_import.saved source=riot_client" in diagnostic
    assert "LOCAL-COOKIE-SECRET" not in diagnostic
    assert "LOCAL-TOKEN-SECRET" not in diagnostic
    assert "owned-puuid" not in diagnostic


def test_import_session_falls_back_to_browser_and_saves_reusable_cookies() -> None:
    importer = FakeImporter(
        local_error=SessionSettingsError("Riot session settings require an ssid cookie")
    )
    bridge, _, vault, log_stream = _bridge(importer)
    bridge._riot_browser_login = lambda: {
        "ssid": "BROWSER-COOKIE-SECRET",
        "sub": "owned-puuid",
    }

    bridge.handle("import_session", {"accountId": "owned-puuid"})

    stored = vault.entries["owned-puuid"]
    assert dict(stored.cookies) == {
        "ssid": "BROWSER-COOKIE-SECRET",
        "sub": "owned-puuid",
    }
    assert importer.minted_cookies == dict(stored.cookies)
    assert importer.identity_tokens == ["BROWSER-TOKEN-SECRET"]
    diagnostic = log_stream.getvalue()
    assert "fallback=browser" in diagnostic
    assert "bridge.session_import.browser.cookies_captured" in diagnostic
    assert "BROWSER-COOKIE-SECRET" not in diagnostic
    assert "BROWSER-TOKEN-SECRET" not in diagnostic


def test_wrong_browser_identity_never_saves_a_secret_after_local_mismatch() -> None:
    importer = FakeImporter(puuid="different-puuid")
    bridge, _, vault, log_stream = _bridge(importer)
    browser_called = False

    def browser_login() -> dict[str, str]:
        nonlocal browser_called
        browser_called = True
        return {"ssid": "MUST-NOT-BE-USED"}

    bridge._riot_browser_login = browser_login

    with pytest.raises(ValueError, match="different account"):
        bridge.handle("import_session", {"accountId": "owned-puuid"})

    assert browser_called is True
    assert vault.entries == {}
    assert "identity_mismatch" in log_stream.getvalue()


def test_another_account_in_riot_client_can_be_recovered_with_bound_browser_signin() -> None:
    importer = FakeImporter(puuid="different-puuid")
    bridge, _, vault, _ = _bridge(importer)

    def browser_login() -> dict[str, str]:
        importer.puuid = "owned-puuid"
        return {"ssid": "CORRECT-BROWSER-COOKIE", "sub": "owned-puuid"}

    bridge._riot_browser_login = browser_login
    bridge.handle("import_session", {"accountId": "owned-puuid"})

    assert vault.entries["owned-puuid"].cookies["ssid"] == "CORRECT-BROWSER-COOKIE"
    assert bridge.accounts[0]["connected"] is True
    assert bridge.accounts[0]["sessionStatus"] == "ready"


def test_unused_accounts_renew_independently_and_reuse_persisted_rotations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RotatingImporter(FakeImporter):
        def __init__(self) -> None:
            super().__init__()
            self.received: list[dict[str, str]] = []

        def refresh_authorization(self, cookies: dict[str, str]) -> object:
            self.received.append(dict(cookies))
            self.puuid = cookies["sub"]
            return SimpleNamespace(
                access_token="ROTATED-TOKEN-SECRET",
                cookies={**cookies, "ssid": cookies["ssid"] + "-renewed"},
            )

    importer = RotatingImporter()
    bridge, _, vault, log = _bridge(importer)
    bridge.accounts.append({**bridge.accounts[0], "id": "unused-puuid", "puuid": "unused-puuid"})
    for account in bridge.accounts:
        vault.put_entry(SecretEntry(
            account_id=account["id"], totp_secret="TOTP-SECRET",
            cookies={"ssid": "COOKIE-SECRET", "sub": account["puuid"]},
            metadata={"unrelated": "preserved"},
        ))
    now = [100.0]
    monkeypatch.setattr("peaks.bridge.monotonic", lambda: now[0])

    bridge._refresh_saved_sessions_if_due()
    assert len(importer.received) == 1
    bridge._refresh_saved_sessions_if_due()
    assert len(importer.received) == 2
    bridge._refresh_saved_sessions_if_due()
    assert len(importer.received) == 2
    now[0] += 6 * 60 * 60 + 1
    bridge._refresh_saved_sessions_if_due()

    assert importer.received[-1]["ssid"] == "COOKIE-SECRET-renewed"
    for entry in vault.entries.values():
        assert entry.totp_secret == "TOTP-SECRET"
        assert entry.access_token is None and entry.refresh_token is None
        assert entry.metadata["unrelated"] == "preserved"
        assert entry.metadata["riot_session_status"] == "ready"
    presentation = str(bridge.state()) + log.getvalue()
    for secret in ("COOKIE-SECRET", "TOTP-SECRET", "ROTATED-TOKEN-SECRET", "unused-puuid"):
        assert secret not in presentation


def test_rejected_session_is_preserved_but_no_longer_advertised_or_retried() -> None:
    class RejectedImporter(FakeImporter):
        calls = 0

        def refresh_authorization(self, cookies: dict[str, str]) -> object:
            self.calls += 1
            raise SessionReauthenticationRequired("auth")

    importer = RejectedImporter()
    bridge, _, vault, _ = _bridge(importer)
    vault.put_entry(SecretEntry("owned-puuid", cookies={"ssid": "EXPIRED-COOKIE"}))
    bridge._refresh_saved_sessions_if_due()
    bridge._refresh_account_secret_flags()
    bridge._session_refresh_due_at.clear()
    bridge._refresh_saved_sessions_if_due()

    assert importer.calls == 1
    assert vault.entries["owned-puuid"].cookies["ssid"] == "EXPIRED-COOKIE"
    state = bridge.state()["accounts"][0]
    assert state["connected"] is False
    assert state["canConnectQr"] is False
    assert state["canSaveRiotSession"] is True
    assert state["sessionStatus"] == "reauth_required"


def test_network_failure_backs_off_without_invalidating_the_saved_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnavailableImporter(FakeImporter):
        calls = 0

        def refresh_authorization(self, cookies: dict[str, str]) -> object:
            self.calls += 1
            raise SessionAuthorizationHTTPError(503)

    importer = UnavailableImporter()
    bridge, _, vault, _ = _bridge(importer)
    saved = SecretEntry("owned-puuid", cookies={"ssid": "COOKIE-SECRET"})
    vault.put_entry(saved)
    now = [10.0]
    monkeypatch.setattr("peaks.bridge.monotonic", lambda: now[0])
    bridge._refresh_saved_sessions_if_due()
    bridge._refresh_saved_sessions_if_due()
    assert importer.calls == 1
    assert vault.entries["owned-puuid"] is saved
    now[0] += 301
    bridge._refresh_saved_sessions_if_due()
    assert importer.calls == 2


@pytest.mark.parametrize("blocked_by", ["_locked", "_session_import_in_progress"])
def test_session_maintenance_does_not_touch_locked_or_interactively_refreshing_vault(
    blocked_by: str,
) -> None:
    importer = FakeImporter()
    bridge, _, vault, _ = _bridge(importer)
    vault.put_entry(SecretEntry("owned-puuid", cookies={"ssid": "COOKIE-SECRET"}))
    setattr(bridge, blocked_by, True)

    bridge._refresh_saved_sessions_if_due()

    assert importer.minted_cookies is None


def test_session_maintenance_never_persists_another_accounts_rotation() -> None:
    class MismatchedImporter(FakeImporter):
        def refresh_authorization(self, cookies: dict[str, str]) -> object:
            return SimpleNamespace(
                access_token="WRONG-TOKEN", cookies={"ssid": "WRONG-COOKIE", "sub": "other"},
            )

    bridge, _, vault, _ = _bridge(MismatchedImporter())
    vault.put_entry(SecretEntry("owned-puuid", cookies={"ssid": "ORIGINAL-COOKIE"}))

    bridge._refresh_saved_sessions_if_due()

    assert vault.entries["owned-puuid"].cookies == {"ssid": "ORIGINAL-COOKIE"}
    assert bridge.accounts[0]["connected"] is False


def test_late_rotation_cannot_overwrite_a_newer_saved_session() -> None:
    bridge, _, vault, _ = _bridge(FakeImporter())
    previous = SecretEntry("owned-puuid", cookies={"ssid": "OLD-COOKIE"})
    current = SecretEntry("owned-puuid", cookies={"ssid": "NEWER-COOKIE"})
    vault.put_entry(current)

    with pytest.raises(RuntimeError, match="session changed"):
        bridge._save_rotated_session_cookies("owned-puuid", previous, {"ssid": "LATE-COOKIE"})

    assert vault.entries["owned-puuid"] is current


def test_late_refresh_rotation_cannot_overwrite_newer_token_with_unchanged_cookies() -> None:
    bridge, _, vault, _ = _bridge(FakeImporter())
    previous = SecretEntry("owned-puuid", cookies={"ssid": "COOKIE"}, refresh_token="OLD")
    current = SecretEntry("owned-puuid", cookies={"ssid": "COOKIE"}, refresh_token="NEWER")
    vault.put_entry(current)

    with pytest.raises(RuntimeError, match="session changed"):
        bridge._save_rotated_session_cookies(
            "owned-puuid", previous, {"ssid": "COOKIE"}, refresh_token="LATE",
        )

    assert vault.entries["owned-puuid"] is current


def test_explicit_refresh_renews_saved_account_without_touching_another_local_account() -> None:
    class SavedImporter(FakeImporter):
        def import_current_session(self) -> Any:
            raise AssertionError("Must not import a different local account")

    importer = SavedImporter()
    bridge, _, vault, _ = _bridge(importer)
    vault.put_entry(SecretEntry("owned-puuid", cookies={"ssid": "SAVED-COOKIE"}))
    bridge._riot_browser_login = lambda: pytest.fail("Valid session needs no browser")

    bridge.handle("import_session", {"accountId": "owned-puuid"})

    assert importer.minted_cookies == {"ssid": "SAVED-COOKIE"}
    assert vault.entries["owned-puuid"].metadata["riot_session_status"] == "ready"
    assert importer.closed


def test_expired_account_uses_browser_and_clears_persisted_reauthentication_state() -> None:
    class BrowserOnlyImporter(FakeImporter):
        def import_current_session(self) -> Any:
            raise AssertionError("Must not rotate the active local account")

    bridge, _, vault, _ = _bridge(BrowserOnlyImporter())
    vault.put_entry(SecretEntry(
        "owned-puuid", cookies={"ssid": "EXPIRED-COOKIE"},
        metadata={"riot_session_status": "reauth_required"},
    ))
    bridge._riot_browser_login = lambda: {"ssid": "NEW-BROWSER-COOKIE"}

    bridge.handle("import_session", {"accountId": "owned-puuid"})

    assert vault.entries["owned-puuid"].cookies["ssid"] == "NEW-BROWSER-COOKIE"
    assert vault.entries["owned-puuid"].metadata["riot_session_status"] == "ready"
    assert bridge.state()["accounts"][0]["canConnectQr"] is True


@pytest.mark.parametrize("cookies", [{}, {"ssid": "EXPIRED-SIX-MONTH-COOKIE", "sub": "owned-puuid"}])
def test_saved_offline_credential_renews_without_using_expired_cookies(cookies: dict[str, str]) -> None:
    class OfflineImporter(FakeImporter):
        def refresh_from_token(self, refresh_token: str, cookies: dict[str, str]) -> object:
            assert refresh_token == "DURABLE-SECRET"
            return SimpleNamespace(
                access_token="NEW-TOKEN", cookies=cookies, refresh_token="ROTATED-DURABLE-SECRET",
            )

        def mint_access_token(self, cookies: dict[str, str]) -> str:
            raise AssertionError("Expired browser session must not be used")

    bridge, _, vault, log = _bridge(OfflineImporter())
    vault.put_entry(SecretEntry(
        "owned-puuid", cookies=cookies,
        refresh_token="DURABLE-SECRET",
    ))

    bridge._refresh_saved_sessions_if_due()

    assert vault.entries["owned-puuid"].refresh_token == "ROTATED-DURABLE-SECRET"
    assert vault.entries["owned-puuid"].access_token is None
    assert vault.entries["owned-puuid"].metadata["riot_session_offline"] is True
    assert "DURABLE-SECRET" not in str(bridge.state()) + log.getvalue()


def test_local_import_saves_offline_credential_immediately() -> None:
    class OfflineImporter(FakeImporter):
        def import_durable_session_for_identity(self, expected: str) -> Any:
            assert expected == "owned-puuid"
            imported = super().import_current_session()
            imported.refresh_token = "DURABLE-SECRET"
            return imported

        def import_current_session(self) -> Any:
            raise AssertionError("Use the offline import")

    bridge, _, vault, log = _bridge(OfflineImporter())

    bridge.handle("import_session", {"accountId": "owned-puuid"})

    assert vault.entries["owned-puuid"].refresh_token == "DURABLE-SECRET"
    assert vault.entries["owned-puuid"].access_token is None
    assert "DURABLE-SECRET" not in str(bridge.state()) + log.getvalue()


def test_reopened_encrypted_vault_can_approve_qr_without_browser_cookies(tmp_path: Path) -> None:
    """Exercise the real importer and vault with synthetic Riot HTTP responses."""
    class RiotTransport(requests.Session):
        def __init__(self) -> None:
            super().__init__()
            self.endpoints: list[str] = []

        def send(self, request: requests.PreparedRequest, **kwargs: Any) -> requests.Response:
            assert request.url is not None
            self.endpoints.append(request.url)
            assert "Cookie" not in request.headers
            if request.url == "https://auth.riotgames.com/token":
                assert request.method == "POST"
                assert isinstance(request.body, str)
                assert parse_qs(request.body) == {
                    "grant_type": ["refresh_token"], "client_id": ["ritoplus"],
                    "refresh_token": ["SAVED-OFFLINE-SECRET"],
                }
                payload: dict[str, Any] = {
                    "access_token": "FRESH-ACCESS", "refresh_token": "ROTATED-OFFLINE-SECRET",
                }
            else:
                assert request.url == "https://auth.riotgames.com/userinfo"
                assert request.headers["Authorization"] == "Bearer FRESH-ACCESS"
                payload = {"sub": "owned-puuid", "acct": {"game_name": "Peak Player", "tag_line": "EUW"}}
            response = requests.Response()
            response.status_code = 200
            response._content = json.dumps(payload).encode()
            response._content_consumed = True
            return response

    pepper = InMemoryPepperProvider(b"test-pepper-0123456789012345")
    path = tmp_path / "vault.json"
    original = SecretVault(path, pepper_provider=pepper)
    original.setup_pin("2468")
    original.unlock_or_raise("2468")
    before, _, _, _ = _bridge(FakeImporter())
    before._vault = original
    before._save_imported_session(
        before.accounts[0], cookies={}, refresh_token="SAVED-OFFLINE-SECRET",
        identity=AuthenticatedRiotIdentity("owned-puuid", "Peak Player", "EUW"), source="browser",
    )
    original.lock()
    assert "SAVED-OFFLINE-SECRET" not in path.read_text(encoding="utf-8")

    # New vault, bridge and HTTP session: nothing survives in memory from before.
    reopened = SecretVault(path, pepper_provider=pepper)
    reopened.unlock_or_raise("2468")
    after, _, _, log = _bridge(FakeImporter())
    after._vault = reopened
    transport = RiotTransport()
    after._session_importer_factory = lambda: RiotSessionImporter(session=transport)
    after._riot_browser_login = lambda: pytest.fail("Offline renewal must not open a browser")
    after._qr_decoder = lambda _capture: "https://qr.riotgames.com?suuid=offline-qr&cluster=eu"
    approver = FakeQrApprover()
    after._qr_approval_factory = lambda: approver
    after._refresh_account_secret_flags()
    assert after.state()["accounts"][0]["canConnectQr"] is True

    state = after.handle("connect_riot_client", {
        "accountId": "owned-puuid", "qrCaptures": [{"trusted": True}], "qrCaptureState": "ready",
    })

    assert transport.endpoints == ["https://auth.riotgames.com/token", "https://auth.riotgames.com/userinfo"]
    assert approver.approval_calls[0][1].access_token == "FRESH-ACCESS"  # type: ignore[attr-defined]
    assert state["accounts"][0]["connected"] is True
    reopened.lock()
    final_vault = SecretVault(path, pepper_provider=pepper)
    final_vault.unlock_or_raise("2468")
    saved = final_vault.get_entry("owned-puuid")
    assert saved is not None
    assert saved.refresh_token == "ROTATED-OFFLINE-SECRET"
    assert saved.access_token is None
    assert dict(saved.cookies) == {}
    final_vault.lock()
    exposed = path.read_text(encoding="utf-8") + repr(state) + log.getvalue()
    for secret in ("SAVED-OFFLINE-SECRET", "ROTATED-OFFLINE-SECRET", "FRESH-ACCESS"):
        assert secret not in exposed


def test_scan_qr_is_not_reported_as_a_false_success() -> None:
    bridge, _, _, _ = _bridge(FakeImporter())

    with pytest.raises(RuntimeError, match=r"not available.*Import current Riot session"):
        bridge.handle("scan_qr", {"accountId": "owned-puuid"})


def test_connect_riot_client_decodes_and_approves_selected_identity() -> None:
    importer = FakeImporter()
    approver = FakeQrApprover()
    bridge, _, vault, log_stream = _bridge(importer)
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            cookies={"ssid": "COOKIE-SECRET", "sub": "owned-puuid"},
        )
    )
    bridge._qr_decoder = lambda _capture: (
        "https://qr.riotgames.com?suuid=session-1&cluster=eu"
    )
    bridge._qr_approval_factory = lambda: approver

    state = bridge.handle(
        "connect_riot_client",
        {
            "accountId": "owned-puuid",
            "qrCaptures": [{"trusted": True}],
            "qrCaptureState": "ready",
        },
    )

    assert state["operationNotice"] == "Riot Client connected to the selected identity"
    assert state["accounts"][0]["connected"] is True
    assert importer.minted_cookies == {"ssid": "COOKIE-SECRET", "sub": "owned-puuid"}
    assert importer.identity_tokens == ["BROWSER-TOKEN-SECRET"]
    assert len(approver.session_info_calls) == 1
    assert approver.session_info_calls[0][2] == "owned-puuid"
    assert len(approver.approval_calls) == 1
    credentials = approver.approval_calls[0][1]
    assert credentials.puuid == "owned-puuid"  # type: ignore[attr-defined]
    assert credentials.access_token == "BROWSER-TOKEN-SECRET"  # type: ignore[attr-defined]
    assert approver.approval_calls[0][2] is True
    assert importer.closed is True
    assert approver.closed is True
    diagnostic = log_stream.getvalue()
    assert "bridge.riot_qr.capture.decode_complete" in diagnostic
    assert "bridge.riot_qr.session.identity_bound" in diagnostic
    assert "bridge.riot_qr.approval.complete method=session" in diagnostic
    assert "COOKIE-SECRET" not in diagnostic
    assert "BROWSER-TOKEN-SECRET" not in diagnostic
    assert "owned-puuid" not in diagnostic


def test_connect_riot_client_does_not_route_a_qr_through_the_totp_endpoint() -> None:
    importer = FakeImporter()
    approver = FakeQrApprover()
    bridge, _, vault, log_stream = _bridge(importer)
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            totp_secret="JBSWY3DPEHPK3PXP",
            cookies={"ssid": "STALE-COOKIE-SECRET", "sub": "owned-puuid"},
        )
    )
    bridge._refresh_account_secret_flags()
    bridge._qr_decoder = lambda _capture: (
        "https://qr.riotgames.com?suuid=durable-session&cluster=eu"
    )
    bridge._qr_approval_factory = lambda: approver

    state = bridge.handle(
        "connect_riot_client",
        {
            "accountId": "owned-puuid",
            "qrCaptures": [{"trusted": True}],
            "qrCaptureState": "ready",
        },
    )

    assert state["accounts"][0]["canConnectQr"] is True
    assert importer.minted_cookies == {
        "ssid": "STALE-COOKIE-SECRET",
        "sub": "owned-puuid",
    }
    assert importer.identity_tokens == ["BROWSER-TOKEN-SECRET"]
    assert len(approver.session_info_calls) == 1
    assert len(approver.approval_calls) == 1
    assert approver.totp_approval_calls == []
    credentials = approver.approval_calls[0][1]
    assert credentials.puuid == "owned-puuid"  # type: ignore[attr-defined]
    assert credentials.access_token == "BROWSER-TOKEN-SECRET"  # type: ignore[attr-defined]
    assert "bridge.riot_qr.approval.complete method=session" in log_stream.getvalue()
    assert "STALE-COOKIE-SECRET" not in log_stream.getvalue()


def test_cookie_qr_path_persists_identity_bound_riot_rotation() -> None:
    class RotatingImporter(FakeImporter):
        def refresh_authorization(self, cookies: dict[str, str]) -> object:
            self.minted_cookies = dict(cookies)
            return SimpleNamespace(
                access_token="ROTATED-TOKEN-SECRET",
                cookies={
                    **cookies,
                    "ssid": "ROTATED-COOKIE-SECRET",
                    "ccid": "ROTATED-CONTEXT-SECRET",
                },
            )

    importer = RotatingImporter()
    approver = FakeQrApprover()
    bridge, _, vault, log_stream = _bridge(importer)
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            cookies={"ssid": "COOKIE-SECRET", "sub": "owned-puuid"},
        )
    )
    bridge._qr_decoder = lambda _capture: (
        "https://qr.riotgames.com?suuid=rotating-session&cluster=eu"
    )
    bridge._qr_approval_factory = lambda: approver

    bridge.handle(
        "connect_riot_client",
        {
            "accountId": "owned-puuid",
            "qrCaptures": [{"trusted": True}],
            "qrCaptureState": "ready",
        },
    )

    stored = vault.entries["owned-puuid"]
    assert dict(stored.cookies) == {
        "ssid": "ROTATED-COOKIE-SECRET",
        "sub": "owned-puuid",
        "ccid": "ROTATED-CONTEXT-SECRET",
    }
    assert importer.identity_tokens == ["ROTATED-TOKEN-SECRET"]
    assert "bridge.riot_qr.session.cookies_rotated cookie_count=3" in log_stream.getvalue()
    assert "ROTATED-COOKIE-SECRET" not in log_stream.getvalue()


def test_pasted_qr_image_uses_the_same_identity_bound_approval_path() -> None:
    importer = FakeImporter()
    approver = FakeQrApprover()
    bridge, _, vault, _ = _bridge(importer)
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            cookies={"ssid": "COOKIE-SECRET", "sub": "owned-puuid"},
        )
    )
    bridge._qr_decoder = lambda _capture: (
        "https://qr.riotgames.com?suuid=pasted-session&cluster=eu"
    )
    bridge._qr_approval_factory = lambda: approver

    state = bridge.handle(
        "connect_riot_qr_image",
        {
            "accountId": "owned-puuid",
            "qrCaptures": [{"trusted": True}],
            "qrCaptureState": "ready",
        },
    )

    assert state["operationNotice"] == "Pasted Riot QR connected to the selected identity"
    assert len(approver.session_info_calls) == 1
    assert approver.session_info_calls[0][2] == "owned-puuid"
    assert len(approver.approval_calls) == 1
    assert approver.approval_calls[0][2] is True


def test_lockfile_only_identity_cannot_offer_qr_reconnect() -> None:
    bridge, _, _, _ = _bridge(FakeImporter())

    state = bridge.state()
    assert state["accounts"][0]["canConnectQr"] is False
    assert state["accounts"][0]["canSaveRiotSession"] is True
    assert state["accounts"][0]["canSetupMfa"] is False

    with pytest.raises(ValueError, match="reusable Riot session"):
        bridge.handle(
            "connect_riot_client",
            {
                "accountId": "owned-puuid",
                "qrCaptures": [{"trusted": True}],
                "qrCaptureState": "ready",
            },
        )


def test_totp_only_identity_cannot_offer_qr_reconnect() -> None:
    bridge, _, vault, _ = _bridge(FakeImporter())
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            totp_secret="JBSWY3DPEHPK3PXP",
        )
    )
    bridge._refresh_account_secret_flags()

    state = bridge.state()

    assert state["accounts"][0]["hasTotp"] is True
    assert state["accounts"][0]["connected"] is False
    assert state["accounts"][0]["canConnectQr"] is False

    with pytest.raises(ValueError, match="reusable Riot session"):
        bridge.handle(
            "connect_riot_client",
            {
                "accountId": "owned-puuid",
                "qrCaptures": [{"trusted": True}],
                "qrCaptureState": "ready",
            },
        )


def test_connect_riot_client_requires_a_readable_riot_qr() -> None:
    bridge, _, vault, _ = _bridge(FakeImporter())
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            cookies={"ssid": "COOKIE-SECRET", "sub": "owned-puuid"},
        )
    )
    bridge._qr_decoder = lambda _capture: None

    with pytest.raises(ValueError, match="No readable Riot sign-in QR"):
        bridge.handle(
            "connect_riot_client",
            {
                "accountId": "owned-puuid",
                "qrCaptures": [{"trusted": True}],
                "qrCaptureState": "ready",
            },
        )


def test_connect_riot_client_logs_native_window_discovery_failure() -> None:
    bridge, _, vault, log_stream = _bridge(FakeImporter())
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            cookies={"ssid": "COOKIE-SECRET", "sub": "owned-puuid"},
        )
    )

    with pytest.raises(ValueError, match="Riot Client window was not found"):
        bridge.handle(
            "connect_riot_client",
            {
                "accountId": "owned-puuid",
                "qrCaptures": [],
                "qrCaptureState": "window_not_found",
            },
        )

    assert "bridge.riot_qr.capture.received state=window_not_found count=0" in (
        log_stream.getvalue()
    )

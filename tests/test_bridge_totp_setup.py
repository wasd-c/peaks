from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.bridge import Bridge
from peaks.domain.models import SecretEntry

SEED = "JBSWY3DPEHPK3PXP"


class FakeVault:
    def __init__(self, entry: SecretEntry | None = None) -> None:
        self.entry = entry
        self.writes: list[SecretEntry] = []
        self.locked = False

    def get_entry(self, _account_id: str) -> SecretEntry | None:
        return self.entry

    def put_entry(self, entry: SecretEntry) -> None:
        self.entry = entry
        self.writes.append(entry)

    def lock(self) -> None:
        self.locked = True


class FakeSetupService:
    def __init__(self, *, warning: str | None = None) -> None:
        self.warning = warning
        self.prepared: list[dict[str, str]] = []
        self.enabled: list[dict[str, Any]] = []
        self.confirmed: list[tuple[str, str]] = []
        self.cancelled: list[str] = []
        self.closed = False

    def prepare(self, **kwargs: str) -> Any:
        self.prepared.append(kwargs)
        return SimpleNamespace(
            confirmation_id="confirmation-token",
            account_id=kwargs["account_id"],
            riot_id=kwargs["expected_riot_id"],
            expires_in_seconds=300,
        )

    def confirm(
        self,
        *,
        confirmation_id: str,
        account_id: str,
        persist_seed: Any,
    ) -> Any:
        self.confirmed.append((confirmation_id, account_id))
        persist_seed(SEED)
        return SimpleNamespace(
            seed_saved=True,
            verified=self.warning is None,
            warning=self.warning,
        )

    def cancel(self, confirmation_id: str) -> None:
        self.cancelled.append(confirmation_id)

    def enable(self, *, persist_seed: Any, **kwargs: Any) -> Any:
        self.enabled.append(kwargs)
        persist_seed(SEED)
        return SimpleNamespace(
            seed_saved=True,
            verified=self.warning is None,
            warning=self.warning,
        )

    def close(self) -> None:
        self.closed = True


def _bridge(service: FakeSetupService, vault: FakeVault) -> Bridge:
    bridge = Bridge.__new__(Bridge)
    bridge.demo = False
    bridge._riot_mobile_totp_setup_factory = lambda: service
    bridge._riot_mobile_totp_setup_service = None
    bridge._logger = logging.getLogger("tests.bridge.totp")
    bridge._pin_mode = "unlock"
    bridge._pending_pin = ""
    bridge._locked = False
    bridge.accounts = [
        {
            "id": "owned-puuid",
            "riotId": "Peak#EUW",
            "region": "GLOBAL",
            "puuid": "owned-puuid",
            "owned": True,
            "connected": bool(vault.entry and vault.entry.cookies),
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
    bridge._repository = SimpleNamespace()
    bridge._vault = vault
    return bridge


def test_prepare_is_read_only_and_binds_selected_identity() -> None:
    service = FakeSetupService()
    vault = FakeVault(SecretEntry(account_id="owned-puuid", cookies={"ssid": "SESSION"}))
    bridge = _bridge(service, vault)

    proposal = bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    assert proposal["confirmationId"] == "confirmation-token"
    assert proposal["accountId"].startswith("account-")
    assert proposal["accountId"] != "owned-puuid"
    assert proposal["riotId"] == "Peak#EUW"
    assert proposal["expiresInSeconds"] == 300
    assert service.prepared == [
        {
            "account_id": "owned-puuid",
            "expected_puuid": "owned-puuid",
            "expected_riot_id": "Peak#EUW",
            "reusable_sso_cookies": {"ssid": "SESSION"},
        }
    ]
    assert vault.writes == []


def test_confirm_preserves_session_and_stores_only_normalized_seed() -> None:
    service = FakeSetupService()
    previous = SecretEntry(
        account_id="owned-puuid",
        cookies={"ssid": "SESSION"},
        access_token="legacy-token",
        refresh_token="durable-refresh",
        metadata={"source": "browser"},
    )
    vault = FakeVault(previous)
    bridge = _bridge(service, vault)
    bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    response = bridge.handle(
        "confirm_totp_setup",
        {"accountId": "owned-puuid", "confirmationId": "confirmation-token"},
    )

    assert service.confirmed == [("confirmation-token", "owned-puuid")]
    assert response["seedSaved"] is True
    assert response["verified"] is True
    assert response["state"]["accounts"][0]["hasTotp"] is True
    assert response["state"]["accounts"][0]["canSetupMfa"] is False
    stored = vault.entry
    assert stored is not None
    assert stored.totp_secret == SEED
    assert dict(stored.cookies) == {"ssid": "SESSION"}
    assert stored.access_token is None
    assert stored.refresh_token == "durable-refresh"
    assert dict(stored.metadata) == {"source": "browser"}
    assert SEED not in repr(response)
    assert "SESSION" not in repr(response)
    assert "durable-refresh" not in repr(response)


def test_partial_verification_warning_keeps_encrypted_seed() -> None:
    warning = "Riot verification failed; the encrypted seed was retained."
    service = FakeSetupService(warning=warning)
    vault = FakeVault(SecretEntry(account_id="owned-puuid", cookies={"ssid": "SESSION"}))
    bridge = _bridge(service, vault)
    bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    response = bridge.handle(
        "confirm_totp_setup",
        {"accountId": "owned-puuid", "confirmationId": "confirmation-token"},
    )

    assert response["verified"] is False
    assert response["warning"] == warning
    assert vault.entry is not None and vault.entry.totp_secret == SEED
    assert response["state"]["accounts"][0]["hasTotp"] is True


def test_existing_secret_is_never_replaced() -> None:
    service = FakeSetupService()
    vault = FakeVault(SecretEntry(account_id="owned-puuid", totp_secret=SEED))
    bridge = _bridge(service, vault)

    with pytest.raises(ValueError, match="will not replace"):
        bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    assert service.prepared == []
    assert vault.writes == []


def test_prepare_requires_a_reusable_session_and_exposes_no_mfa_capability() -> None:
    service = FakeSetupService()
    bridge = _bridge(service, FakeVault())

    state = bridge.state()
    assert state["accounts"][0]["canSetupMfa"] is False

    with pytest.raises(ValueError, match="Save a reusable Riot session"):
        bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    assert service.prepared == []


def test_cancel_discards_pending_confirmation() -> None:
    service = FakeSetupService()
    bridge = _bridge(
        service,
        FakeVault(SecretEntry(account_id="owned-puuid", cookies={"ssid": "SESSION"})),
    )
    bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    state = bridge.handle("cancel_totp_setup", {"confirmationId": "confirmation-token"})

    assert service.cancelled == ["confirmation-token"]
    assert state["accounts"][0]["hasTotp"] is False


def test_lock_closes_pending_totp_setup_service() -> None:
    service = FakeSetupService()
    vault = FakeVault(SecretEntry(account_id="owned-puuid", cookies={"ssid": "SESSION"}))
    bridge = _bridge(service, vault)
    bridge.handle("prepare_totp_setup", {"accountId": "owned-puuid"})

    bridge.handle("lock", {})

    assert service.closed is True
    assert bridge._riot_mobile_totp_setup_service is None
    assert vault.locked is True


@pytest.mark.parametrize("warning", [None, "Riot verification failed; the encrypted seed was retained."])
def test_enable_mfa_uses_selected_saved_session_and_keeps_secrets_out_of_response(
    warning: str | None,
) -> None:
    service = FakeSetupService(warning=warning)
    vault = FakeVault(SecretEntry(account_id="owned-puuid", cookies={"ssid": "SESSION"}))
    bridge = _bridge(service, vault)
    handle = bridge.state()["accounts"][0]["id"]

    response = bridge.handle("enable_riot_mfa", {"accountId": handle})

    assert service.enabled == [{
        "account_id": "owned-puuid",
        "expected_puuid": "owned-puuid",
        "expected_riot_id": "Peak#EUW",
        "reusable_sso_cookies": {"ssid": "SESSION"},
    }]
    assert service.prepared == []
    assert service.confirmed == []
    assert len(vault.writes) == 1
    assert vault.entry is not None and vault.entry.totp_secret == SEED
    assert dict(vault.entry.cookies) == {"ssid": "SESSION"}
    assert response["seedSaved"] is True
    assert response["verified"] is (warning is None)
    assert response["warning"] == warning
    assert response["state"]["accounts"][0]["hasTotp"] is True
    assert response["state"]["accounts"][0]["canSetupMfa"] is False
    assert "confirmationId" not in response
    assert SEED not in repr(response)
    assert "SESSION" not in repr(response)

    with pytest.raises(ValueError, match="will not replace"):
        bridge.handle("enable_riot_mfa", {"accountId": handle})
    assert len(service.enabled) == 1


@pytest.mark.parametrize("condition", ["locked", "not_owned", "missing_session", "missing_identity"])
def test_enable_mfa_rejects_ineligible_accounts_before_contacting_riot(condition: str) -> None:
    service = FakeSetupService()
    vault = FakeVault(SecretEntry(account_id="owned-puuid", cookies={"ssid": "SESSION"}))
    bridge = _bridge(service, vault)
    if condition == "locked":
        bridge._locked = True
    elif condition == "not_owned":
        bridge.accounts[0]["owned"] = False
    elif condition == "missing_session":
        vault.entry = None
    else:
        bridge.accounts[0]["puuid"] = ""

    with pytest.raises((ValueError, PermissionError)):
        bridge.handle("enable_riot_mfa", {"accountId": "owned-puuid"})
    assert service.enabled == []
    assert vault.writes == []

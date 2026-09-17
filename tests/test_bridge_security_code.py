from collections.abc import Iterator
from pathlib import Path

import pytest

from peaks.adapters import persistence
from peaks.adapters.persistence import InMemoryPepperProvider, SecretVault
from peaks.bridge import Bridge, _execute_bridge_request
from peaks.domain.models import Account, SecretEntry


@pytest.fixture
def security_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Bridge, list[float]]]:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    clock = [100.0]
    pepper = InMemoryPepperProvider(b"test-pepper-0123456789012345")
    monkeypatch.setattr(persistence, "SecretVault", lambda path: SecretVault(
        path, pepper_provider=pepper, clock=lambda: clock[0],
    ))
    bridge = Bridge()
    bridge.handle("pin", {"pin": "5193"})
    bridge.handle("pin", {"pin": "5193"})
    bridge._repository.add_account(Account("owned-puuid", "Private Player", "TEST", "global", "owned-puuid"))
    bridge._vault.put_entry(SecretEntry(
        "owned-puuid", cookies={"ssid": "private-cookie"}, totp_secret="JBSWY3DPEHPK3PXP",
        refresh_token="DURABLE-PRIVATE-TOKEN", metadata={"riot_session_status": "ready"},
    ))
    bridge._load_database()
    bridge._refresh_account_secret_flags()
    try:
        yield bridge, clock
    finally:
        bridge._vault.lock()
        bridge._repository.close()


def test_security_code_rotation_preserves_accounts_and_durable_riot_sessions(
    security_bridge: tuple[Bridge, list[float]],
) -> None:
    bridge, clock = security_bridge
    original = bridge._vault.get_entry("owned-puuid")
    accounts = bridge.state()["accounts"]
    changed = _execute_bridge_request(bridge, {"id": 1, "command": "change_pin", "payload": {
        "oldPin": "5193", "newPin": "6802", "confirmPin": "6802",
    }})
    assert "error" not in changed
    assert changed["result"]["locked"] is False
    assert changed["result"]["accounts"] == accounts
    assert bridge._vault.get_entry("owned-puuid") == original
    assert all(secret not in str(changed) for secret in ("5193", "6802", "DURABLE-PRIVATE-TOKEN"))
    bridge.handle("lock", {})
    with pytest.raises(ValueError, match="not recognized"):
        bridge.handle("pin", {"pin": "5193"})
    clock[0] += 2
    assert bridge.handle("pin", {"pin": "6802"})["locked"] is False
    assert bridge._vault.get_entry("owned-puuid") == original


def test_wrong_current_code_keeps_the_vault_and_enforces_retry_delay(
    security_bridge: tuple[Bridge, list[float]],
) -> None:
    bridge, clock = security_bridge
    original = bridge._vault.get_entry("owned-puuid")
    with pytest.raises(ValueError, match="current passcode"):
        bridge.handle("change_pin", {"oldPin": "1111", "newPin": "6802", "confirmPin": "6802"})
    assert bridge._vault.is_unlocked
    assert bridge._vault.get_entry("owned-puuid") == original
    with pytest.raises(ValueError, match="Try again"):
        bridge.handle("change_pin", {"oldPin": "5193", "newPin": "6802", "confirmPin": "6802"})
    clock[0] += 2
    bridge.handle("change_pin", {"oldPin": "5193", "newPin": "6802", "confirmPin": "6802"})


@pytest.mark.parametrize("payload", [
    {"oldPin": "5193", "newPin": "6802", "confirmPin": "9999"},
    {"oldPin": "5193", "newPin": "123", "confirmPin": "123"},
    {"oldPin": "5193", "newPin": "abcd", "confirmPin": "abcd"},
    {"oldPin": "5193", "newPin": "\uff11\uff12\uff13\uff14", "confirmPin": "\uff11\uff12\uff13\uff14"},
    {"oldPin": "5193", "newPin": "5193", "confirmPin": "5193"},
])
def test_invalid_security_code_does_not_write_the_vault(
    security_bridge: tuple[Bridge, list[float]], payload: dict[str, str],
) -> None:
    bridge, _ = security_bridge
    original = bridge._vault.path.read_bytes()
    with pytest.raises(ValueError):
        bridge.handle("change_pin", payload)
    assert bridge._vault.path.read_bytes() == original
    bridge.handle("lock", {})
    with pytest.raises(PermissionError, match="Unlock"):
        bridge.handle("change_pin", payload)


def test_failed_code_rotation_locks_presentation_and_preserves_old_encrypted_file(
    security_bridge: tuple[Bridge, list[float]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge, _ = security_bridge
    original = bridge._vault.path.read_bytes()

    def fail_write(*_args: object) -> None:
        raise OSError("simulated write failure")

    monkeypatch.setattr("peaks.adapters.persistence.secret_vault._atomic_write_bytes", fail_write)
    with pytest.raises(RuntimeError, match="vault was retained"):
        bridge.handle("change_pin", {"oldPin": "5193", "newPin": "6802", "confirmPin": "6802"})
    assert bridge.state()["locked"] is True
    assert bridge.state()["accounts"] == []
    assert bridge._vault.path.read_bytes() == original
    assert bridge.handle("pin", {"pin": "5193"})["locked"] is False

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest

from peaks.adapters import persistence
from peaks.adapters.persistence import InMemoryPepperProvider, SecretVault
from peaks.adapters.riot import qr_session
from peaks.bridge import Bridge
from peaks.domain.models import Account


@pytest.fixture
def bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Bridge]:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    pepper = InMemoryPepperProvider(b"riot-sign-out-test-pepper-0123456789")
    monkeypatch.setattr(persistence, "SecretVault", lambda path: SecretVault(path, pepper_provider=pepper))
    instance = Bridge()
    instance.handle("pin", {"pin": "2468"})
    instance.handle("pin", {"pin": "2468"})
    instance._repository.add_account(Account("owner", "Player", "TEST", "euw1", puuid="owner-puuid"))
    instance._repository.add_account(Account("friend", "Friend", "TEST", "euw1", puuid="friend-puuid", is_owned=False))
    instance._load_database()
    try:
        yield instance
    finally:
        instance._vault.lock()
        instance._repository.close()


def _renderer_id(bridge: Bridge, internal_id: str) -> str:
    return bridge._renderer_account_id(internal_id)


def test_sign_out_ends_the_followed_riot_session(bridge: Bridge, monkeypatch: pytest.MonkeyPatch) -> None:
    sign_out = Mock(return_value=True)
    monkeypatch.setattr(qr_session, "sign_out_local_riot", sign_out)
    bridge._active_account_id = "owner"
    state = bridge.handle("sign_out_riot", {"accountId": _renderer_id(bridge, "owner")})
    sign_out.assert_called_once_with("owner-puuid", close_games=False)
    assert state["activeAccountId"] is None
    assert state["riotClient"]["sessionState"] == "signed_out"
    assert state["operationNotice"] == "Signed out of Riot Client"


def test_sign_out_during_a_game_needs_confirmation_to_close_it(
    bridge: Bridge, monkeypatch: pytest.MonkeyPatch,
) -> None:
    sign_out = Mock(return_value=True)
    monkeypatch.setattr(qr_session, "sign_out_local_riot", sign_out)
    bridge._active_account_id = "owner"
    bridge._game_detected = True
    bridge._current_match = {"game": "VALORANT"}
    account_id = _renderer_id(bridge, "owner")
    with pytest.raises(RuntimeError, match="will close your current game"):
        bridge.handle("sign_out_riot", {"accountId": account_id})
    with pytest.raises(RuntimeError, match="will close your current game"):
        bridge.handle("sign_out_riot", {"accountId": account_id, "closeGame": "yes"})
    sign_out.assert_not_called()

    state = bridge.handle("sign_out_riot", {"accountId": account_id, "closeGame": True})
    sign_out.assert_called_once_with("owner-puuid", close_games=True)
    assert state["activeAccountId"] is None
    assert state["gameDetected"] is False


def test_sign_out_skips_watched_players(bridge: Bridge, monkeypatch: pytest.MonkeyPatch) -> None:
    sign_out = Mock(return_value=True)
    monkeypatch.setattr(qr_session, "sign_out_local_riot", sign_out)
    with pytest.raises(ValueError):
        bridge.handle("sign_out_riot", {"accountId": _renderer_id(bridge, "friend")})
    sign_out.assert_not_called()


def test_demo_sign_out_clears_the_active_account_until_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEAKS_DEMO", "1")
    demo = Bridge()
    demo.handle("pin", {"pin": "2580"})
    account_id = demo.state()["activeAccountId"]
    assert account_id
    assert demo.state()["gameDetected"] is True
    signed_out = demo.handle("sign_out_riot", {"accountId": account_id, "closeGame": True})
    assert signed_out["activeAccountId"] is None
    assert signed_out["gameDetected"] is False
    demo.handle("connect_riot_client", {"accountId": account_id})
    assert demo.state()["activeAccountId"] == account_id

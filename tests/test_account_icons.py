from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from peaks.adapters import persistence
from peaks.adapters.persistence import Database, InMemoryPepperProvider, SecretVault
from peaks.bridge import Bridge
from peaks.domain.models import Account, AccountIcon, Game

JETT = {"game": "VALORANT", "characterId": "add6443a-41bd-e414-f6ad-e58d267f4e95"}
AHRI = {"game": "League of Legends", "characterId": "Ahri"}


@pytest.fixture
def icon_bridge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Bridge]:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    pepper = InMemoryPepperProvider(b"account-icon-test-pepper-012345678")
    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(path, pepper_provider=pepper),
    )
    bridge = Bridge()
    bridge.handle("pin", {"pin": "2468"})
    bridge.handle("pin", {"pin": "2468"})
    bridge._repository.add_account(Account("owner", "Player", "TEST", "euw1"))
    bridge._load_database()
    try:
        yield bridge
    finally:
        bridge._vault.lock()
        bridge._repository.close()


def _payload(bridge: Bridge, icon: Any) -> dict[str, Any]:
    return {"accountId": bridge.state()["accounts"][0]["id"], "icon": icon}


def test_icon_survives_refresh_restart_and_preserves_identity(icon_bridge: Bridge) -> None:
    before = icon_bridge._repository.get_account("owner")
    assert before is not None
    state = icon_bridge.handle("set_account_icon", _payload(icon_bridge, JETT))
    assert state["accounts"][0]["accountIcon"] == JETT
    assert state["accounts"][0]["id"].startswith("account-")
    assert state["accounts"][0]["riotId"] == "Player#TEST"

    # An older refresh response must not undo a just-selected icon.
    icon_bridge._repository.add_account(replace(before, level=72))
    icon_bridge._persist_account_snapshot("owner", {"level": 73})
    icon_bridge._merge_account_snapshot(icon_bridge.accounts[0], {"level": 73})
    assert icon_bridge.state()["accounts"][0]["accountIcon"] == JETT

    reopened = Bridge()
    try:
        assert reopened.state()["accounts"] == []
        state = reopened.handle("pin", {"pin": "2468"})
        assert state["accounts"][0]["accountIcon"] == JETT
        assert state["accounts"][0]["level"] == 73
        stored = reopened._repository.get_account("owner")
        assert stored is not None and stored.account_icon is not None
        assert Account.from_dict(stored.to_dict()) == stored
        assert stored.with_ranks([]).account_icon == stored.account_icon
        assert stored.puuid == before.puuid and stored.created_at == before.created_at
    finally:
        reopened._vault.lock()
        reopened._repository.close()


def test_reset_cannot_be_undone_by_stale_manual_icon_and_removal_cleans_it(
    icon_bridge: Bridge,
) -> None:
    icon_bridge.handle("set_account_icon", _payload(icon_bridge, AHRI))
    stale = icon_bridge._repository.get_account("owner")
    assert stale is not None and stale.account_icon is not None
    state = icon_bridge.handle("set_account_icon", _payload(icon_bridge, None))
    assert "accountIcon" not in state["accounts"][0]
    icon_bridge._repository.add_account(stale)
    icon_bridge._load_database()
    assert "accountIcon" not in icon_bridge.state()["accounts"][0]

    icon_bridge.handle("set_account_icon", _payload(icon_bridge, AHRI))
    icon_bridge.handle("remove_account", {"accountId": _payload(icon_bridge, None)["accountId"]})
    assert icon_bridge._repository.get_account("owner") is None
    icon_bridge._repository.add_account(replace(stale, account_icon=None))
    assert icon_bridge._repository.get_account("owner").account_icon is None


@pytest.mark.parametrize(
    "icon",
    [
        "https://example.com/icon.png",
        [],
        {},
        {"game": "Teamfight Tactics", "characterId": "Ahri"},
        {"game": "VALORANT", "characterId": "Jett"},
        {"game": "VALORANT", "characterId": "add6443a-41bd-e414-f6ad-e58d267f4e95/evil"},
        {"game": "League of Legends", "characterId": "../../secret"},
        {"game": "League of Legends", "characterId": "C:\\Users\\icon.png"},
        {"game": "League of Legends", "characterId": "https://example.com"},
        {"game": "League of Legends", "characterId": "Ahri\n"},
        {"game": "League of Legends", "characterId": "a" * 65},
        {"game": "League of Legends", "characterId": 103},
        {"game": "League of Legends", "characterId": None},
        {"game": ["League of Legends"], "characterId": "Ahri"},
        {**AHRI, "url": "https://example.com"},
    ],
)
def test_icon_validation_rejects_unsupported_asset_references(
    icon_bridge: Bridge,
    icon: Any,
) -> None:
    with pytest.raises(ValueError):
        icon_bridge.handle("set_account_icon", _payload(icon_bridge, icon))
    assert icon_bridge._repository.get_account("owner").account_icon is None
    assert "accountIcon" not in icon_bridge.state()["accounts"][0]


def test_icon_command_requires_unlock_known_owned_account_and_explicit_selection(
    icon_bridge: Bridge,
) -> None:
    payload = _payload(icon_bridge, AHRI)
    with pytest.raises(ValueError, match="Choose a character"):
        icon_bridge.handle("set_account_icon", {"accountId": payload["accountId"]})
    with pytest.raises(ValueError, match="no longer available"):
        icon_bridge.handle("set_account_icon", {**payload, "accountId": "missing"})
    icon_bridge.accounts[0]["owned"] = False
    with pytest.raises(ValueError, match="Only owned"):
        icon_bridge.handle("set_account_icon", payload)
    icon_bridge.accounts[0]["owned"] = True
    icon_bridge.handle("lock", {})
    with pytest.raises(PermissionError, match="Unlock Peaks"):
        icon_bridge.handle("set_account_icon", payload)
    assert icon_bridge._repository.get_account("owner").account_icon is None


def test_failed_persistence_does_not_change_presented_icon(
    icon_bridge: Bridge,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    icon_bridge.handle("set_account_icon", _payload(icon_bridge, JETT))

    def failed_write(_account_id: str, _icon: AccountIcon | None) -> None:
        raise sqlite3.OperationalError("database is read only")

    monkeypatch.setattr(icon_bridge._repository, "set_account_icon", failed_write)
    with pytest.raises(sqlite3.OperationalError):
        icon_bridge.handle("set_account_icon", _payload(icon_bridge, AHRI))
    assert icon_bridge.state()["accounts"][0]["accountIcon"] == JETT


def test_database_migrates_existing_accounts_without_changing_identity(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE accounts (
                account_id TEXT PRIMARY KEY, game_name TEXT NOT NULL, tag_line TEXT NOT NULL,
                region TEXT NOT NULL, puuid TEXT, is_owned INTEGER NOT NULL,
                created_at TEXT NOT NULL, last_seen_at TEXT, account_level INTEGER,
                valorant_region TEXT
            );
            INSERT INTO accounts VALUES ('owner', 'Player', 'TEST', 'euw1', NULL, 1,
                '2026-09-01T00:00:00Z', NULL, 42, 'EU');
        """)
    with Database(path) as database:
        before = database.get_account("owner")
        assert before is not None and before.account_icon is None
        icon = AccountIcon(Game.LEAGUE_OF_LEGENDS, "MonkeyKing")
        database.set_account_icon("owner", icon)
        assert database.get_account("owner") == replace(before, account_icon=icon)
        with pytest.raises(KeyError):
            database.set_account_icon("missing", icon)
        database.add_account(Account("other", "Other", is_owned=False))
        with pytest.raises(KeyError):
            database.set_account_icon("other", icon)


def test_demo_icon_uses_same_validation_without_writing_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PEAKS_DEMO", "1")
    bridge = Bridge()
    bridge.handle("pin", {"pin": "2580"})
    state = bridge.handle("set_account_icon", _payload(bridge, AHRI))
    assert state["accounts"][0]["accountIcon"] == AHRI
    assert bridge._repository is None


def test_nickname_is_atomic_persistent_and_independent_of_riot_identity(icon_bridge: Bridge) -> None:
    original = icon_bridge._repository.get_account("owner")
    payload = {**_payload(icon_bridge, AHRI), "nickname": "  Ranked main  "}
    state = icon_bridge.handle("set_account_icon", payload)
    assert state["accounts"][0]["nickname"] == "Ranked main"
    assert state["accounts"][0]["riotId"] == "Player#TEST"
    saved = icon_bridge._repository.get_account("owner")
    assert saved.nickname == "Ranked main"
    assert Account.from_dict(saved.to_dict()) == saved
    assert saved.with_ranks([]).nickname == "Ranked main"

    # A concurrent refresh holding the old snapshot must not erase the label.
    icon_bridge._repository.add_account(replace(original, level=21))
    icon_bridge._load_database()
    assert icon_bridge.state()["accounts"][0]["nickname"] == "Ranked main"
    # Older clients changing only the icon must preserve the label as well.
    icon_bridge.handle("set_account_icon", _payload(icon_bridge, JETT))
    assert icon_bridge._repository.get_account("owner").nickname == "Ranked main"
    state = icon_bridge.handle("set_account_icon", {**_payload(icon_bridge, None), "nickname": ""})
    assert "nickname" not in state["accounts"][0]
    assert icon_bridge._repository.get_account("owner").nickname == ""
    icon_bridge._repository.add_account(saved)
    assert icon_bridge._repository.get_account("owner").nickname == ""


@pytest.mark.parametrize("nickname", [None, 42, [], "x" * 65, "Main\n", "Name\u202e"])
def test_invalid_nickname_does_not_partially_change_icon(icon_bridge: Bridge, nickname: Any) -> None:
    icon_bridge.handle("set_account_icon", {**_payload(icon_bridge, AHRI), "nickname": "Main"})
    with pytest.raises(ValueError):
        icon_bridge.handle("set_account_icon", {**_payload(icon_bridge, JETT), "nickname": nickname})
    account = icon_bridge._repository.get_account("owner")
    assert account.nickname == "Main"
    assert account.account_icon.character_id == "Ahri"
    assert icon_bridge.state()["accounts"][0]["accountIcon"] == AHRI


def test_nickname_and_icon_roll_back_together_on_write_failure(
    icon_bridge: Bridge, monkeypatch: pytest.MonkeyPatch,
) -> None:
    icon_bridge.handle("set_account_icon", {**_payload(icon_bridge, AHRI), "nickname": "Main"})

    def failed_write(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.OperationalError("database is read only")

    monkeypatch.setattr(icon_bridge._repository, "set_account_icon", failed_write)
    with pytest.raises(sqlite3.OperationalError):
        icon_bridge.handle("set_account_icon", {**_payload(icon_bridge, JETT), "nickname": "Alt"})
    assert icon_bridge.state()["accounts"][0]["nickname"] == "Main"
    assert icon_bridge.state()["accounts"][0]["accountIcon"] == AHRI

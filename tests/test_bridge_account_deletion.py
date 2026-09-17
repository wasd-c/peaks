from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.persistence import Database, InMemoryPepperProvider, SecretVault
from peaks.bridge import Bridge
from peaks.domain.models import Game, MatchRecord, MatchResult, RankInfo, SecretEntry


def _bridge(repository: Any, vault: SecretVault) -> Bridge:
    bridge = Bridge.__new__(Bridge)
    bridge.demo = False
    bridge._account_onboarding_factory = None
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
    return bridge


def _unlocked_vault(tmp_path: Path) -> SecretVault:
    vault = SecretVault(
        tmp_path / "vault.json",
        pepper_provider=InMemoryPepperProvider(b"bridge-pepper-0123456789012345"),
    )
    vault.setup_pin("2468")
    assert vault.unlock("2468") is True
    return vault


def test_remove_account_deletes_database_children_vault_secrets_and_view(tmp_path: Path) -> None:
    repository = Database(tmp_path / "peaks.sqlite3")
    vault = _unlocked_vault(tmp_path)
    bridge = _bridge(repository, vault)
    result = SimpleNamespace(
        identity=SimpleNamespace(
            puuid="owned-puuid",
            game_name="Peak Player",
            tag_line="EUW",
        ),
        source="browser",
        cookies={"ssid": "session-cookie", "sub": "owned-puuid"},
    )

    try:
        bridge._persist_authenticated_account(result)
        repository.add_rank("owned-puuid", RankInfo(Game.VALORANT, "diamond", "2", 64))
        repository.add_match(
            MatchRecord(
                "match-1",
                "owned-puuid",
                Game.VALORANT,
                datetime.now(UTC),
                MatchResult.WIN,
            )
        )
        vault.put("owned-puuid:riot_session_cookies", {"ssid": "legacy-session"})
        vault.put("owned-puuid:totp", "legacy-totp")

        renderer_account_id = bridge.state()["accounts"][0]["id"]
        assert renderer_account_id != "owned-puuid"
        state = bridge.handle("remove_account", {"accountId": renderer_account_id})

        assert state["accounts"] == []
        assert repository.get_account("owned-puuid") is None
        assert repository.list_ranks("owned-puuid") == []
        assert repository.list_matches("owned-puuid") == []
        remaining_keys = vault.keys()
        assert all(
            key != "owned-puuid" and not key.startswith("owned-puuid:")
            for key in remaining_keys
        )
    finally:
        vault.lock()
        repository.close()


class RefusingRepository:
    def remove_account(self, _account_id: str) -> bool:
        raise OSError("database is read-only")


def test_remove_account_restores_vault_when_database_delete_fails(tmp_path: Path) -> None:
    vault = _unlocked_vault(tmp_path)
    bridge = _bridge(RefusingRepository(), vault)
    bridge.accounts = [
        {
            "id": "owned-puuid",
            "riotId": "Peak Player#EUW",
            "region": "EUW",
            "owned": True,
            "ranks": [],
            "matches": [],
        }
    ]
    vault.put_entry(
        SecretEntry(
            account_id="owned-puuid",
            cookies={"ssid": "session-cookie"},
        )
    )

    try:
        with pytest.raises(RuntimeError, match="could not be deleted from local storage"):
            bridge.handle("remove_account", {"accountId": "owned-puuid"})

        assert [account["id"] for account in bridge.accounts] == ["owned-puuid"]
        restored = vault.get_entry("owned-puuid")
        assert restored is not None
        assert dict(restored.cookies) == {"ssid": "session-cookie"}
    finally:
        vault.lock()


def test_locked_bridge_cannot_delete_account(tmp_path: Path) -> None:
    vault = _unlocked_vault(tmp_path)
    bridge = _bridge(RefusingRepository(), vault)
    bridge.accounts = [{"id": "owned-puuid"}]
    bridge._locked = True

    try:
        with pytest.raises(PermissionError, match="Unlock Peaks"):
            bridge.handle("remove_account", {"accountId": "owned-puuid"})

        assert bridge.accounts == [{"id": "owned-puuid"}]
    finally:
        vault.lock()

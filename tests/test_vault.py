from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peaks.adapters.persistence import (
    Database,
    InMemoryPepperProvider,
    KeyringPepperProvider,
    SecretVault,
    VaultAlreadyInitializedError,
    VaultBackoffError,
    VaultLockedError,
)
from peaks.adapters.persistence.secret_vault import (
    WindowsDpapiPepperProvider,
)
from peaks.domain import (
    Account,
    FollowedAccount,
    Game,
    MatchRecord,
    MatchResult,
    RankInfo,
    SearchEntry,
    SecretEntry,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password


class FailingPepperProvider:
    def get_pepper(self) -> bytes:
        raise RuntimeError("protected storage unavailable")


class CountingPepperProvider:
    def __init__(self, pepper: bytes) -> None:
        self.pepper = pepper
        self.calls = 0

    def get_pepper(self) -> bytes:
        self.calls += 1
        return self.pepper


def test_pin_validation_and_safe_initialization(tmp_path: Path) -> None:
    pepper = InMemoryPepperProvider(b"test-pepper-0123456789012345")
    vault_path = tmp_path / "nested" / "credentials.json"
    vault = SecretVault(vault_path, pepper_provider=pepper)

    with pytest.raises(ValueError):
        vault.setup_pin("123")
    with pytest.raises(ValueError):
        vault.setup_pin("12a4")

    vault.setup_pin("0123")
    original = vault_path.read_bytes()
    with pytest.raises(VaultAlreadyInitializedError):
        vault.setup_pin("9999")
    assert vault_path.read_bytes() == original
    assert vault.has_pin is True
    assert vault.is_unlocked is False
    if os.name != "nt":
        assert vault_path.stat().st_mode & 0o077 == 0


def test_wrong_pin_uses_persistent_exponential_backoff(tmp_path: Path) -> None:
    clock = FakeClock()
    vault = SecretVault(
        tmp_path / "vault.json",
        pepper_provider=InMemoryPepperProvider(b"test-pepper-0123456789012345"),
        clock=clock,
        base_backoff_seconds=5,
        max_backoff_seconds=20,
    )
    vault.setup_pin("1234")

    assert vault.unlock("0000") is False
    assert vault.failed_attempts == 1
    assert vault.retry_after == 5
    assert vault.unlock("1234") is False  # still in backoff
    clock.advance(5)
    assert vault.unlock("0000") is False
    assert vault.failed_attempts == 2
    assert vault.retry_after == 10
    with pytest.raises(VaultBackoffError):
        vault.unlock_or_raise("1234")
    clock.advance(10)
    assert vault.unlock("1234") is True
    assert vault.failed_attempts == 0


def test_encrypted_entries_round_trip_and_lock_wipes_access(tmp_path: Path) -> None:
    path = tmp_path / "vault.json"
    pepper = InMemoryPepperProvider(b"test-pepper-0123456789012345")
    vault = SecretVault(path, pepper_provider=pepper)
    vault.setup_pin("2468")
    vault.unlock_or_raise("2468")
    vault.put_entry(
        SecretEntry(
            account_id="puuid-1",
            totp_secret="JBSWY3DPEHPK3PXP",
            cookies={"sid": "secret-cookie"},
        )
    )
    vault.put("opaque", {"token": "very-secret", "nested": [1, 2]})

    disk = path.read_text(encoding="utf-8")
    assert "secret-cookie" not in disk
    assert "very-secret" not in disk
    assert vault.get_entry("puuid-1").totp_secret == "JBSWY3DPEHPK3PXP"  # type: ignore[union-attr]
    assert vault.keys() == ("opaque", "puuid-1")

    vault.lock()
    assert vault.is_unlocked is False
    with pytest.raises(VaultLockedError):
        vault.get("opaque")

    reopened = SecretVault(path, pepper_provider=pepper)
    reopened.unlock_or_raise("2468")
    assert reopened.get("opaque") == {"token": "very-secret", "nested": [1, 2]}
    reopened.lock()


def test_wrong_pepper_and_pin_rotation(tmp_path: Path) -> None:
    path = tmp_path / "vault.json"
    pepper = InMemoryPepperProvider(b"test-pepper-0123456789012345")
    clock = FakeClock()
    vault = SecretVault(path, pepper_provider=pepper, clock=clock)
    vault.setup_pin("1357")
    vault.unlock_or_raise("1357")
    vault.put("account", {"seed": "secret"})
    vault.change_pin("1357", "9753")
    assert vault.is_unlocked is True
    assert vault.get("account") == {"seed": "secret"}
    vault.lock()

    assert vault.unlock("1357") is False
    clock.advance(1)
    # A fresh instance confirms the new key works once the old-PIN backoff is
    # irrelevant to the key-rotation assertion.
    rotated = SecretVault(path, pepper_provider=pepper, clock=clock)
    rotated.unlock_or_raise("9753")
    assert rotated.get("account") == {"seed": "secret"}

    wrong_pepper = SecretVault(
        path,
        pepper_provider=InMemoryPepperProvider(b"different-pepper-0123456789"),
        clock=clock,
    )
    assert wrong_pepper.unlock("9753") is False


def test_keyring_provider_falls_back_and_persists_a_machine_pepper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = FakeKeyring()
    provider = KeyringPepperProvider(backend=backend)
    first = provider.get_pepper()
    second = provider.get_pepper()

    assert len(first) == 32
    assert first == second
    assert backend.values

    monkeypatch.setattr("peaks.adapters.persistence.secret_vault.os.name", "posix")
    failing = object()
    fallback = InMemoryPepperProvider(b"fallback-pepper-0123456789012345")
    provider = KeyringPepperProvider(backend=failing, fallback=fallback, allow_file_fallback=True)
    assert provider.get_pepper() == fallback.get_pepper()


def test_file_pepper_fallback_is_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("peaks.adapters.persistence.secret_vault.os.name", "posix")
    fallback = InMemoryPepperProvider(b"fallback-pepper-0123456789012345")
    provider = KeyringPepperProvider(backend=object(), fallback=fallback)

    with pytest.raises(RuntimeError, match="explicitly enabled"):
        provider.get_pepper()


def test_windows_never_uses_plaintext_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("peaks.adapters.persistence.secret_vault.os.name", "nt")
    fallback = CountingPepperProvider(b"fallback-pepper-0123456789012345")
    provider = KeyringPepperProvider(
        backend=object(),
        fallback=fallback,
        dpapi_provider=FailingPepperProvider(),
        allow_file_fallback=True,
    )

    with pytest.raises(RuntimeError, match="Windows protected"):
        provider.get_pepper()
    assert fallback.calls == 0


def test_windows_dpapi_provider_fails_closed_off_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("peaks.adapters.persistence.secret_vault.os.name", "posix")
    provider = WindowsDpapiPepperProvider(tmp_path / ".vault-pepper.dpapi")
    with pytest.raises(RuntimeError, match="only on Windows"):
        provider.get_pepper()


def test_database_persists_accounts_ranks_matches_and_search_deduplication(tmp_path: Path) -> None:
    database_path = tmp_path / "profile" / "peaks.sqlite3"
    database = Database(database_path)
    account = Account(
        account_id="puuid-1",
        game_name="Peak Player",
        tag_line="EUW",
        region="EUW1",
        ranks=(RankInfo(Game.LEAGUE_OF_LEGENDS, "diamond", "II", rating=72),),
        level=284,
    )
    database.add_account(account)
    database.add_match(
        MatchRecord(
            match_id="match-1",
            account_id=account.account_id,
            game=Game.LEAGUE_OF_LEGENDS,
            played_at=datetime.now(UTC),
            result=MatchResult.WIN,
            queue="ranked",
        )
    )
    first = database.add_search(SearchEntry("Player", "EUW", "EUW1", Game.LEAGUE_OF_LEGENDS))
    second = database.add_search(SearchEntry("player", "#EUW", "euw1", Game.LEAGUE_OF_LEGENDS))

    assert database_path.exists()
    assert database.get_account(account.account_id).rank_for(Game.LEAGUE_OF_LEGENDS).label == "Diamond II"  # type: ignore[union-attr]
    assert database.get_account(account.account_id).level == 284  # type: ignore[union-attr]
    assert len(database.list_matches(account.account_id)) == 1
    assert first.entry_id == second.entry_id
    assert len(database.list_search_history()) == 1
    database.close()


def test_database_migrates_existing_accounts_to_persist_level(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES ('version', '1');
        CREATE TABLE accounts (
            account_id TEXT PRIMARY KEY,
            game_name TEXT NOT NULL,
            tag_line TEXT NOT NULL DEFAULT '',
            region TEXT NOT NULL,
            puuid TEXT,
            is_owned INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_seen_at TEXT
        );
        INSERT INTO accounts(
            account_id, game_name, tag_line, region, puuid, is_owned, created_at
        ) VALUES ('owned', 'Peak', 'EUW', 'global', 'owned', 1, '2026-08-30T00:00:00Z');
        """
    )
    connection.close()

    database = Database(database_path)
    legacy = database.get_account("owned")
    assert legacy is not None and legacy.level is None

    database.add_account(Account.from_dict({**legacy.to_dict(), "level": 197}))

    assert database.get_account("owned").level == 197  # type: ignore[union-attr]
    database.add_account(Account("owned", "Peak", "EUW", "global", "owned"))
    assert database.get_account("owned").level == 197  # type: ignore[union-attr]
    schema_version = database.connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'version'"
    ).fetchone()[0]
    assert schema_version == "2"
    database.close()


def test_database_settings_followed_order_and_cascade(tmp_path: Path) -> None:
    database = Database(tmp_path / "peaks.sqlite3")
    assert database.get_settings().layout.value == "grid"
    settings = database.update_setting(
        {"lock_timeout_minutes": 5, "layout": "list", "lock_on_blur": False, "reduce_motion": True}
    )
    assert settings.lock_timeout_seconds == 300
    assert settings.layout.value == "list"
    assert settings.lock_on_blur is False
    assert settings.reduce_motion is True

    database.add_account(Account("owned", "Owned", "EU", "euw1"))
    database.add_followed(
        FollowedAccount("followed", "Followed", "EU", "euw1", Game.VALORANT)
    )
    assert database.list_followed()[0].display_name == "Followed#EU"
    database.add_match(
        MatchRecord("m", "owned", Game.VALORANT, datetime.now(UTC), MatchResult.LOSS)
    )
    assert database.remove_account("owned") is True
    assert database.list_matches("owned") == []
    assert database.remove_account("missing") is False
    database.close()

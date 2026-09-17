"""SQLite persistence for non-secret Peaks data.

Only account metadata, preferences, search history, watchlist players, and match
summaries belong here.  Login material is intentionally handled by
``secret_vault.SecretVault`` and never written to this database.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager, suppress
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Self

from peaks.domain.models import (
    Account,
    AccountLayout,
    FollowedAccount,
    Game,
    MatchRecord,
    MatchResult,
    RankInfo,
    RankTier,
    SearchEntry,
    Settings,
    _decode_datetime,
    _encode_datetime,
)


def _default_data_dir() -> Path:
    try:
        from platformdirs import user_data_dir

        return Path(user_data_dir("Peaks", "Peaks"))
    except Exception:  # pragma: no cover - only used if optional dependency is unavailable
        return Path.home() / ".peaks"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _unjson(value: str, default: Any = None) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


class Database(AbstractContextManager["Database"]):
    """Thread-safe, synchronous SQLite repository.

    The constructor opens and initializes the database immediately.  Schema DDL
    runs inside one transaction, so a process interrupted during first launch
    cannot leave a partially initialized schema behind.  ``path`` may be
    ``":memory:"`` for tests.
    """

    SCHEMA_VERSION = 2

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None and str(path) != ":memory:" else None
        self._lock = threading.RLock()
        if self.path is not None:
            self.path = self.path.expanduser()
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._connection = sqlite3.connect(
            ":memory:" if self.path is None else self.path,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        if self.path is not None:
            with suppress(OSError):
                self.path.chmod(0o600)
        self.initialize()

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    def initialize(self) -> None:
        """Initialize the schema idempotently in one transaction."""

        with self._lock:
            # ``executescript`` commits any transaction already open by the
            # sqlite3 module.  Put the transaction in the script itself so the
            # whole first-launch schema remains atomic.
            self._connection.executescript(
                """
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS schema_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS accounts (
                        account_id TEXT PRIMARY KEY,
                        game_name TEXT NOT NULL,
                        tag_line TEXT NOT NULL DEFAULT '',
                        region TEXT NOT NULL,
                        puuid TEXT,
                        is_owned INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        last_seen_at TEXT,
                        account_level INTEGER CHECK(
                            account_level IS NULL OR account_level BETWEEN 0 AND 100000
                        )
                    );
                    CREATE TABLE IF NOT EXISTS ranks (
                        account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
                        game TEXT NOT NULL,
                        tier TEXT NOT NULL,
                        division TEXT,
                        rating INTEGER,
                        wins INTEGER,
                        losses INTEGER,
                        peak_tier TEXT,
                        peak_division TEXT,
                        peak_rating INTEGER,
                        updated_at TEXT,
                        ranked INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (account_id, game)
                    );
                    CREATE TABLE IF NOT EXISTS search_history (
                        entry_id TEXT PRIMARY KEY,
                        game_name TEXT NOT NULL COLLATE NOCASE,
                        tag_line TEXT NOT NULL DEFAULT '' COLLATE NOCASE,
                        region TEXT NOT NULL COLLATE NOCASE,
                        game TEXT NOT NULL,
                        searched_at TEXT NOT NULL,
                        UNIQUE (game_name, tag_line, region, game)
                    );
                    CREATE TABLE IF NOT EXISTS followed_accounts (
                        account_id TEXT NOT NULL,
                        game TEXT NOT NULL,
                        game_name TEXT NOT NULL,
                        tag_line TEXT NOT NULL DEFAULT '',
                        region TEXT NOT NULL,
                        rank_json TEXT,
                        peak_rank_json TEXT,
                        last_game_at TEXT,
                        followed_at TEXT NOT NULL,
                        updated_at TEXT,
                        PRIMARY KEY (account_id, game)
                    );
                    CREATE TABLE IF NOT EXISTS matches (
                        match_id TEXT NOT NULL,
                        account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
                        game TEXT NOT NULL,
                        played_at TEXT NOT NULL,
                        result TEXT NOT NULL,
                        queue TEXT,
                        map_name TEXT,
                        duration_seconds INTEGER,
                        kills INTEGER,
                        deaths INTEGER,
                        assists INTEGER,
                        rank_delta INTEGER,
                        metadata_json TEXT NOT NULL DEFAULT '{}',
                        PRIMARY KEY (match_id, account_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_matches_account_time
                        ON matches(account_id, played_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_search_time
                        ON search_history(searched_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_followed_time
                        ON followed_accounts(last_game_at DESC, followed_at DESC);
                    INSERT OR IGNORE INTO schema_meta(key, value)
                        VALUES ('version', '2');
                    INSERT OR IGNORE INTO settings(key, value)
                        VALUES ('lock_timeout_seconds', '900');
                    INSERT OR IGNORE INTO settings(key, value)
                        VALUES ('layout', '"grid"');
                    INSERT OR IGNORE INTO settings(key, value)
                        VALUES ('streamer_mode', 'false');
                    INSERT OR IGNORE INTO settings(key, value)
                        VALUES ('lock_on_blur', 'true');
                    INSERT OR IGNORE INTO settings(key, value)
                        VALUES ('reduce_motion', 'false');
                    COMMIT;
                    """
            )
            account_columns = {
                str(row["name"])
                for row in self._connection.execute("PRAGMA table_info(accounts)").fetchall()
            }
            if "account_level" not in account_columns:
                self._connection.execute("BEGIN IMMEDIATE")
                try:
                    self._connection.execute(
                        "ALTER TABLE accounts ADD COLUMN account_level INTEGER "
                        "CHECK(account_level IS NULL OR account_level BETWEEN 0 AND 100000)"
                    )
                    self._connection.execute(
                        "INSERT INTO schema_meta(key, value) VALUES ('version', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (str(self.SCHEMA_VERSION),),
                    )
                    self._connection.execute("COMMIT")
                except Exception:
                    self._connection.execute("ROLLBACK")
                    raise
            else:
                self._connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES ('version', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(self.SCHEMA_VERSION),),
                )

    def close(self) -> None:
        with self._lock:
            if self._connection is not None:
                self._connection.close()

    def destroy(self) -> None:
        """Close and delete only Peaks' SQLite database and sidecars."""

        self.close()
        if self.path is None:
            return
        for candidate in (
            self.path,
            Path(f"{self.path}-wal"),
            Path(f"{self.path}-shm"),
            Path(f"{self.path}-journal"),
        ):
            with suppress(FileNotFoundError):
                candidate.unlink()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()

    def _execute(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._connection.execute(sql, parameters)

    def _commit(self) -> None:
        # isolation_level=None means each statement is atomic.  This explicit
        # method exists to make multi-step mutations easy to audit and extend.
        return

    # -- settings ---------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self._execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        return _unjson(row["value"], default)

    def get_settings(self) -> Settings:
        values = {
            row["key"]: _unjson(row["value"])
            for row in self._execute("SELECT key, value FROM settings").fetchall()
        }
        return Settings.from_dict(values)

    def save_settings(self, settings: Settings) -> Settings:
        values = settings.to_dict()
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.executemany(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    [(key, _json(value)) for key, value in values.items()],
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return settings

    def update_setting(self, key: str | Mapping[str, Any], value: Any = None) -> Settings:
        """Update one setting, or a mapping of settings, and return all settings.

        ``lock_timeout_minutes`` is accepted as a UI-friendly alias and is
        normalized to integer seconds.  Unknown settings are retained so new UI
        preferences can roll out without a schema migration.
        """

        changes = dict(key) if isinstance(key, Mapping) else {key: value}
        normalized: dict[str, Any] = {}
        for name, setting in changes.items():
            if name in {"lock_timeout", "lock_timeout_minutes"}:
                setting = round(float(setting) * 60)
                name = "lock_timeout_seconds"
            if name == "layout":
                setting = AccountLayout.parse(setting).value
            if name == "streamer_mode":
                setting = bool(setting)
            if name in {"lock_on_blur", "reduce_motion"}:
                setting = bool(setting)
            normalized[name] = setting
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.executemany(
                    "INSERT INTO settings(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    [(name, _json(setting)) for name, setting in normalized.items()],
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return self.get_settings()

    # -- accounts and ranks ----------------------------------------------

    @staticmethod
    def _account_row(account: Account) -> tuple[Any, ...]:
        return (
            account.account_id,
            account.game_name,
            account.tag_line,
            account.region,
            account.puuid,
            int(account.is_owned),
            _encode_datetime(account.created_at),
            _encode_datetime(account.last_seen_at),
            account.level,
        )

    def add_account(self, account: Account) -> Account:
        with self._lock:
            self._connection.execute(
                """INSERT INTO accounts(
                    account_id, game_name, tag_line, region, puuid, is_owned,
                    created_at, last_seen_at, account_level
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    game_name=excluded.game_name, tag_line=excluded.tag_line,
                    region=excluded.region, puuid=excluded.puuid,
                    is_owned=excluded.is_owned, created_at=excluded.created_at,
                    last_seen_at=excluded.last_seen_at,
                    account_level=COALESCE(excluded.account_level, accounts.account_level)""",
                self._account_row(account),
            )
            for rank in account.ranks:
                self.add_rank(account.account_id, rank)
        return self.get_account(account.account_id) or account

    def add_accounts(self, accounts: Sequence[Account]) -> list[Account]:
        return [self.add_account(account) for account in accounts]

    def update_account(self, account_id: str | Account, **changes: Any) -> Account:
        # Accepting a complete DTO makes controller code concise while the
        # keyword form remains useful for a single field update.
        if isinstance(account_id, Account):
            if changes:
                raise ValueError("Do not combine an Account DTO with field changes")
            return self.add_account(account_id)
        current = self.get_account(account_id)
        if current is None:
            raise KeyError(f"Unknown account: {account_id}")
        if "id" in changes:
            raise ValueError("account id cannot be changed")
        account = replace(current, **changes)
        return self.add_account(account)

    def remove_account(self, account_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
        return cursor.rowcount > 0

    def get_account(self, account_id: str) -> Account | None:
        row = self._execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if row is None:
            return None
        return self._account_from_row(row)

    def list_accounts(self, owned_only: bool = False) -> list[Account]:
        sql = "SELECT * FROM accounts"
        if owned_only:
            sql += " WHERE is_owned = 1"
        sql += " ORDER BY (last_seen_at IS NULL), last_seen_at DESC, game_name COLLATE NOCASE"
        return [self._account_from_row(row) for row in self._execute(sql).fetchall()]

    def _account_from_row(self, row: sqlite3.Row) -> Account:
        ranks = self.list_ranks(row["account_id"])
        return Account(
            account_id=row["account_id"],
            game_name=row["game_name"],
            tag_line=row["tag_line"],
            region=row["region"],
            puuid=row["puuid"],
            is_owned=bool(row["is_owned"]),
            created_at=_decode_datetime(row["created_at"]),
            last_seen_at=_decode_datetime(row["last_seen_at"]),
            ranks=tuple(ranks),
            level=row["account_level"],
        )

    def add_rank(self, account_id: str, rank: RankInfo) -> RankInfo:
        if self.get_account(account_id) is None:
            raise KeyError(f"Unknown account: {account_id}")
        tier = rank.tier.value if isinstance(rank.tier, RankTier) else rank.tier
        peak_tier = rank.peak_tier.value if isinstance(rank.peak_tier, RankTier) else rank.peak_tier
        self._execute(
            """INSERT INTO ranks(
                account_id, game, tier, division, rating, wins, losses,
                peak_tier, peak_division, peak_rating, updated_at, ranked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, game) DO UPDATE SET
                tier=excluded.tier, division=excluded.division,
                rating=excluded.rating, wins=excluded.wins, losses=excluded.losses,
                peak_tier=excluded.peak_tier, peak_division=excluded.peak_division,
                peak_rating=excluded.peak_rating, updated_at=excluded.updated_at,
                ranked=excluded.ranked""",
            (
                account_id,
                rank.game.value,
                str(tier),
                rank.division,
                rank.rating,
                rank.wins,
                rank.losses,
                peak_tier,
                rank.peak_division,
                rank.peak_rating,
                _encode_datetime(rank.updated_at),
                int(rank.ranked),
            ),
        )
        return rank

    def remove_rank(self, account_id: str, game: Game | str) -> bool:
        cursor = self._execute(
            "DELETE FROM ranks WHERE account_id = ? AND game = ?",
            (account_id, Game.parse(game).value),
        )
        return cursor.rowcount > 0

    def list_ranks(self, account_id: str) -> list[RankInfo]:
        rows = self._execute(
            "SELECT * FROM ranks WHERE account_id = ? ORDER BY game", (account_id,)
        ).fetchall()
        return [
            RankInfo(
                game=Game.parse(row["game"]),
                tier=row["tier"],
                division=row["division"],
                rating=row["rating"],
                wins=row["wins"],
                losses=row["losses"],
                peak_tier=row["peak_tier"],
                peak_division=row["peak_division"],
                peak_rating=row["peak_rating"],
                updated_at=_decode_datetime(row["updated_at"]),
                ranked=bool(row["ranked"]),
            )
            for row in rows
        ]

    # -- search history ---------------------------------------------------

    def add_search(self, entry: SearchEntry) -> SearchEntry:
        with self._lock:
            self._connection.execute(
                """INSERT INTO search_history(
                    entry_id, game_name, tag_line, region, game, searched_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_name, tag_line, region, game) DO UPDATE SET
                    searched_at=excluded.searched_at""",
                (
                    entry.entry_id,
                    entry.game_name,
                    entry.tag_line,
                    entry.region,
                    entry.game.value,
                    _encode_datetime(entry.searched_at),
                ),
            )
        result = self._execute(
            """SELECT * FROM search_history WHERE game_name = ? AND tag_line = ?
               AND region = ? AND game = ?""",
            (entry.game_name, entry.tag_line, entry.region, entry.game.value),
        ).fetchone()
        assert result is not None
        return SearchEntry(
            entry_id=result["entry_id"],
            game_name=result["game_name"],
            tag_line=result["tag_line"],
            region=result["region"],
            game=Game.parse(result["game"]),
            searched_at=_decode_datetime(result["searched_at"]) or datetime.now(),
        )

    record_search = add_search

    def list_search_history(self, limit: int | None = None) -> list[SearchEntry]:
        sql = "SELECT * FROM search_history ORDER BY searched_at DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            sql += " LIMIT ?"
            params = (limit,)
        return [
            SearchEntry(
                entry_id=row["entry_id"],
                game_name=row["game_name"],
                tag_line=row["tag_line"],
                region=row["region"],
                game=Game.parse(row["game"]),
                searched_at=_decode_datetime(row["searched_at"]) or datetime.now(),
            )
            for row in self._execute(sql, params).fetchall()
        ]

    def remove_search(self, entry_id: str) -> bool:
        cursor = self._execute("DELETE FROM search_history WHERE entry_id = ?", (entry_id,))
        return cursor.rowcount > 0

    remove_search_history = remove_search

    def clear_search_history(self) -> int:
        cursor = self._execute("DELETE FROM search_history")
        return cursor.rowcount

    # -- followed ---------------------------------------------------------

    def add_followed(self, account: FollowedAccount) -> FollowedAccount:
        rank_payload = account.rank.to_dict() if account.rank else {}
        if account.games or account.ranks:
            # Keep the legacy primary rank shape; optional profile metadata
            # shares its existing JSON column without a schema migration.
            rank_payload["profile_games"] = [game.value for game in account.games]
            rank_payload["profile_ranks"] = [rank.to_dict() for rank in account.ranks]
        rank_json = _json(rank_payload) if rank_payload else None
        peak_json = _json(account.peak_rank.to_dict()) if account.peak_rank else None
        self._execute(
            """INSERT INTO followed_accounts(
                account_id, game, game_name, tag_line, region, rank_json,
                peak_rank_json, last_game_at, followed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, game) DO UPDATE SET
                game_name=excluded.game_name, tag_line=excluded.tag_line,
                region=excluded.region, rank_json=excluded.rank_json,
                peak_rank_json=excluded.peak_rank_json, last_game_at=excluded.last_game_at,
                followed_at=excluded.followed_at, updated_at=excluded.updated_at""",
            (
                account.account_id,
                account.game.value if account.game else "",
                account.game_name,
                account.tag_line,
                account.region,
                rank_json,
                peak_json,
                _encode_datetime(account.last_game_at),
                _encode_datetime(account.followed_at),
                _encode_datetime(account.updated_at),
            ),
        )
        return account

    follow = add_followed

    def remove_followed(self, account_id: str, game: Game | str | None = None) -> bool:
        if game is None:
            cursor = self._execute("DELETE FROM followed_accounts WHERE account_id = ?", (account_id,))
        else:
            cursor = self._execute(
                "DELETE FROM followed_accounts WHERE account_id = ? AND game = ?",
                (account_id, Game.parse(game).value),
            )
        return cursor.rowcount > 0

    unfollow = remove_followed

    def is_followed(self, account_id: str, game: Game | str | None = None) -> bool:
        if game is None:
            row = self._execute(
                "SELECT 1 FROM followed_accounts WHERE account_id = ? LIMIT 1", (account_id,)
            ).fetchone()
        else:
            row = self._execute(
                "SELECT 1 FROM followed_accounts WHERE account_id = ? AND game = ? LIMIT 1",
                (account_id, Game.parse(game).value),
            ).fetchone()
        return row is not None

    def list_followed(self, limit: int | None = None) -> list[FollowedAccount]:
        sql = """SELECT * FROM followed_accounts
                 ORDER BY (last_game_at IS NULL), last_game_at DESC, followed_at DESC"""
        params: tuple[Any, ...] = ()
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            sql += " LIMIT ?"
            params = (limit,)
        return [self._followed_from_row(row) for row in self._execute(sql, params).fetchall()]

    def _followed_from_row(self, row: sqlite3.Row) -> FollowedAccount:
        rank = _unjson(row["rank_json"])
        peak_rank = _unjson(row["peak_rank_json"])
        return FollowedAccount(
            account_id=row["account_id"],
            game_name=row["game_name"],
            tag_line=row["tag_line"],
            region=row["region"],
            game=Game.parse(row["game"]) if row["game"] else None,
            rank=RankInfo.from_dict(rank) if isinstance(rank, Mapping) and rank.get("game") else None,
            games=tuple(Game.parse(game) for game in rank.get("profile_games", ())) if isinstance(rank, Mapping) else (),
            ranks=tuple(RankInfo.from_dict(value) for value in rank.get("profile_ranks", ())) if isinstance(rank, Mapping) else (),
            peak_rank=RankInfo.from_dict(peak_rank) if isinstance(peak_rank, Mapping) else None,
            last_game_at=_decode_datetime(row["last_game_at"]),
            followed_at=_decode_datetime(row["followed_at"]) or datetime.now(),
            updated_at=_decode_datetime(row["updated_at"]),
        )

    # -- matches ----------------------------------------------------------

    def add_match(self, match: MatchRecord) -> MatchRecord:
        if self.get_account(match.account_id) is None:
            raise KeyError(f"Unknown account: {match.account_id}")
        self._execute(
            """INSERT INTO matches(
                match_id, account_id, game, played_at, result, queue, map_name,
                duration_seconds, kills, deaths, assists, rank_delta, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id, account_id) DO UPDATE SET
                game=excluded.game, played_at=excluded.played_at, result=excluded.result,
                queue=excluded.queue, map_name=excluded.map_name,
                duration_seconds=excluded.duration_seconds, kills=excluded.kills,
                deaths=excluded.deaths, assists=excluded.assists,
                rank_delta=excluded.rank_delta, metadata_json=excluded.metadata_json""",
            (
                match.match_id,
                match.account_id,
                match.game.value,
                _encode_datetime(match.played_at),
                match.result.value,
                match.queue,
                match.map_name,
                match.duration_seconds,
                match.kills,
                match.deaths,
                match.assists,
                match.rank_delta,
                _json(dict(match.metadata)),
            ),
        )
        return match

    def list_matches(
        self,
        account_id: str | None = None,
        game: Game | str | None = None,
        limit: int | None = None,
    ) -> list[MatchRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if account_id is not None:
            clauses.append("account_id = ?")
            params.append(account_id)
        if game is not None:
            clauses.append("game = ?")
            params.append(Game.parse(game).value)
        sql = "SELECT * FROM matches"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY played_at DESC"
        if limit is not None:
            if limit < 0:
                raise ValueError("limit cannot be negative")
            sql += " LIMIT ?"
            params.append(limit)
        return [self._match_from_row(row) for row in self._execute(sql, tuple(params)).fetchall()]

    def _match_from_row(self, row: sqlite3.Row) -> MatchRecord:
        return MatchRecord(
            match_id=row["match_id"],
            account_id=row["account_id"],
            game=Game.parse(row["game"]),
            played_at=_decode_datetime(row["played_at"]) or datetime.now(),
            result=MatchResult.parse(row["result"]),
            queue=row["queue"],
            map_name=row["map_name"],
            duration_seconds=row["duration_seconds"],
            kills=row["kills"],
            deaths=row["deaths"],
            assists=row["assists"],
            rank_delta=row["rank_delta"],
            metadata=_unjson(row["metadata_json"], {}),
        )

    def remove_match(self, match_id: str, account_id: str | None = None) -> int:
        if account_id is None:
            cursor = self._execute("DELETE FROM matches WHERE match_id = ?", (match_id,))
        else:
            cursor = self._execute(
                "DELETE FROM matches WHERE match_id = ? AND account_id = ?",
                (match_id, account_id),
            )
        return cursor.rowcount

    def clear_matches(self, account_id: str | None = None) -> int:
        if account_id is None:
            cursor = self._execute("DELETE FROM matches")
        else:
            cursor = self._execute("DELETE FROM matches WHERE account_id = ?", (account_id,))
        return cursor.rowcount


MetadataStore = Database
SQLiteStore = Database

__all__ = ["Database", "MetadataStore", "SQLiteStore"]

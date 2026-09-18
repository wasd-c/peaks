"""Value objects used by the Peaks application.

The domain deliberately has no Qt, HTTP, or operating-system dependencies.  The
adapters can therefore be exercised with fixtures on every supported platform,
while the UI only has to deal with a small set of predictable DTOs.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self
from uuid import uuid4

from peaks.domain.regions import normalize_valorant_region


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for persistence."""

    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _encode_datetime(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _decode_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), UTC)
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid ISO timestamp: {value!r}") from exc


class _StringEnum(StrEnum):
    @classmethod
    def parse(cls, value: Self | str) -> Self:
        if isinstance(value, cls):
            return value
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        for member in cls:
            if normalized in {member.value.lower(), member.name.lower()}:
                return member
        raise ValueError(f"Unknown {cls.__name__}: {value!r}")


class Game(_StringEnum):
    """A Riot title supported by Peaks."""

    LEAGUE_OF_LEGENDS = "league_of_legends"
    VALORANT = "valorant"
    TFT = "tft"

    @classmethod
    def parse(cls, value: Self | str) -> Self:
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "league": cls.LEAGUE_OF_LEGENDS,
            "lol": cls.LEAGUE_OF_LEGENDS,
            "league_of_legends": cls.LEAGUE_OF_LEGENDS,
            "valorant": cls.VALORANT,
            "val": cls.VALORANT,
            "tft": cls.TFT,
            "teamfight_tactics": cls.TFT,
        }
        if normalized in aliases:
            return aliases[normalized]
        return super().parse(value)

    @property
    def label(self) -> str:
        return {
            Game.LEAGUE_OF_LEGENDS: "League of Legends",
            Game.VALORANT: "VALORANT",
            Game.TFT: "Teamfight Tactics",
        }[self]


class AccountLayout(_StringEnum):
    GRID = "grid"
    LIST = "list"


class MatchResult(_StringEnum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: Self | str) -> Self:
        normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "victory": cls.WIN,
            "won": cls.WIN,
            "defeat": cls.LOSS,
            "lost": cls.LOSS,
            "tie": cls.DRAW,
        }
        if normalized in aliases:
            return aliases[normalized]
        return super().parse(value)


class RankTier(_StringEnum):
    """Common rank tiers across LoL, TFT, and VALORANT.

    VALORANT's Ascendant and Radiant tiers are included alongside the LoL/TFT
    tiers.  Unknown provider-specific labels remain valid strings in ``RankInfo``
    and are not silently mapped to the wrong rank.
    """

    UNRANKED = "unranked"
    IRON = "iron"
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    EMERALD = "emerald"
    DIAMOND = "diamond"
    ASCENDANT = "ascendant"
    IMMORTAL = "immortal"
    MASTER = "master"
    GRANDMASTER = "grandmaster"
    CHALLENGER = "challenger"
    RADIANT = "radiant"


@dataclass(frozen=True, slots=True)
class RankInfo:
    """A snapshot of one account's rank in one game."""

    game: Game
    tier: str | RankTier = RankTier.UNRANKED
    division: str | None = None
    rating: int | None = None
    wins: int | None = None
    losses: int | None = None
    peak_tier: str | RankTier | None = None
    peak_division: str | None = None
    peak_rating: int | None = None
    updated_at: datetime | None = None
    ranked: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "game", Game.parse(self.game))
        object.__setattr__(self, "tier", self._normalize_tier(self.tier))
        if self.peak_tier is not None:
            object.__setattr__(self, "peak_tier", self._normalize_tier(self.peak_tier))
        object.__setattr__(self, "updated_at", _as_utc(self.updated_at))
        for name in ("rating", "wins", "losses", "peak_rating"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, int):
                raise TypeError(f"{name} must be an int or None")
            if value is not None and name in {"wins", "losses"} and value < 0:
                raise ValueError(f"{name} cannot be negative")

    @staticmethod
    def _normalize_tier(value: str | RankTier) -> str | RankTier:
        if isinstance(value, RankTier):
            return value
        text = str(value).strip()
        if not text:
            return RankTier.UNRANKED
        try:
            return RankTier.parse(text)
        except ValueError:
            # Riot can add tiers or provider adapters can return a localized
            # label.  Preserve it instead of losing information.
            return text

    @property
    def tier_label(self) -> str:
        tier = self.tier.value if isinstance(self.tier, RankTier) else self.tier
        return " ".join(part.capitalize() for part in tier.replace("_", " ").split())

    @property
    def label(self) -> str:
        return f"{self.tier_label} {self.division}" if self.division else self.tier_label

    @property
    def peak_label(self) -> str | None:
        if self.peak_tier is None:
            return None
        tier = self.peak_tier.value if isinstance(self.peak_tier, RankTier) else self.peak_tier
        label = " ".join(part.capitalize() for part in tier.replace("_", " ").split())
        return f"{label} {self.peak_division}" if self.peak_division else label

    def to_dict(self) -> dict[str, Any]:
        return {
            "game": self.game.value,
            "tier": self.tier.value if isinstance(self.tier, RankTier) else self.tier,
            "division": self.division,
            "rating": self.rating,
            "wins": self.wins,
            "losses": self.losses,
            "peak_tier": (
                self.peak_tier.value
                if isinstance(self.peak_tier, RankTier)
                else self.peak_tier
            ),
            "peak_division": self.peak_division,
            "peak_rating": self.peak_rating,
            "updated_at": _encode_datetime(self.updated_at),
            "ranked": self.ranked,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            game=Game.parse(data["game"]),
            tier=data.get("tier", RankTier.UNRANKED),
            division=data.get("division"),
            rating=data.get("rating"),
            wins=data.get("wins"),
            losses=data.get("losses"),
            peak_tier=data.get("peak_tier"),
            peak_division=data.get("peak_division"),
            peak_rating=data.get("peak_rating"),
            updated_at=_decode_datetime(data.get("updated_at")),
            ranked=bool(data.get("ranked", True)),
        )


# Short alias used by a few consumers and makes account.rank construction terse.
Rank = RankInfo


@dataclass(frozen=True, slots=True)
class AccountIcon:
    """A character asset identifier, never a user-supplied URL or local path."""

    game: Game
    character_id: str

    def __post_init__(self) -> None:
        game = Game.parse(self.game)
        if game not in {Game.VALORANT, Game.LEAGUE_OF_LEGENDS}:
            raise ValueError("Choose a VALORANT agent or League of Legends champion")
        if not isinstance(self.character_id, str):
            raise ValueError("Choose a valid character icon")
        pattern = (
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
            if game is Game.VALORANT else r"[A-Za-z][A-Za-z0-9]{0,63}"
        )
        if re.fullmatch(pattern, self.character_id) is None:
            raise ValueError("Choose a valid character icon")
        object.__setattr__(self, "game", game)
        if game is Game.VALORANT:
            object.__setattr__(self, "character_id", self.character_id.lower())

    def to_dict(self) -> dict[str, str]:
        return {"game": self.game.value, "character_id": self.character_id}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        if not isinstance(data, Mapping) or set(data) != {"game", "character_id"}:
            raise ValueError("Choose a valid character icon")
        return cls(game=Game.parse(data["game"]), character_id=data["character_id"])


def normalize_account_nickname(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Choose an account nickname of up to 64 characters")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ValueError("Choose an account nickname without control characters")
    nickname = value.strip()
    if len(nickname) > 64:
        raise ValueError("Choose an account nickname of up to 64 characters")
    return nickname


@dataclass(frozen=True, slots=True)
class Account:
    """A Riot identity known to the local user."""

    account_id: str
    game_name: str
    tag_line: str = ""
    # Legacy field stores the League/TFT platform only.
    region: str = "global"
    puuid: str | None = None
    is_owned: bool = True
    created_at: datetime | None = None
    last_seen_at: datetime | None = None
    ranks: tuple[RankInfo, ...] = ()
    level: int | None = None
    valorant_region: str | None = None
    account_icon: AccountIcon | None = None
    nickname: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "nickname", normalize_account_nickname(self.nickname))
        object.__setattr__(self, "valorant_region", normalize_valorant_region(self.valorant_region))
        if not self.account_id.strip():
            raise ValueError("account_id cannot be empty")
        if not self.game_name.strip():
            raise ValueError("game_name cannot be empty")
        object.__setattr__(self, "account_id", self.account_id.strip())
        object.__setattr__(self, "game_name", self.game_name.strip())
        object.__setattr__(self, "tag_line", self.tag_line.strip().lstrip("#"))
        object.__setattr__(self, "region", self.region.strip().lower() or "global")
        object.__setattr__(self, "created_at", _as_utc(self.created_at) or utc_now())
        object.__setattr__(self, "last_seen_at", _as_utc(self.last_seen_at))
        object.__setattr__(self, "ranks", tuple(self.ranks))
        if self.account_icon is not None and not isinstance(self.account_icon, AccountIcon):
            raise TypeError("account_icon must be an AccountIcon or None")
        if self.level is not None:
            if isinstance(self.level, bool) or not isinstance(self.level, int):
                raise TypeError("level must be an int or None")
            if not 0 <= self.level <= 100_000:
                raise ValueError("level must be between 0 and 100000")

    @property
    def id(self) -> str:
        """Compatibility alias for adapters that call the key ``id``."""

        return self.account_id

    @property
    def display_name(self) -> str:
        return f"{self.game_name}#{self.tag_line}" if self.tag_line else self.game_name

    def rank_for(self, game: Game | str) -> RankInfo | None:
        target = Game.parse(game)
        return next((rank for rank in self.ranks if rank.game is target), None)

    def with_ranks(self, ranks: tuple[RankInfo, ...] | list[RankInfo]) -> Account:
        return Account(
            account_id=self.account_id,
            game_name=self.game_name,
            tag_line=self.tag_line,
            region=self.region,
            puuid=self.puuid,
            is_owned=self.is_owned,
            created_at=self.created_at,
            last_seen_at=self.last_seen_at,
            ranks=tuple(ranks),
            level=self.level,
            valorant_region=self.valorant_region,
            account_icon=self.account_icon,
            nickname=self.nickname,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "game_name": self.game_name,
            "tag_line": self.tag_line,
            "region": self.region,
            "puuid": self.puuid,
            "is_owned": self.is_owned,
            "created_at": _encode_datetime(self.created_at),
            "last_seen_at": _encode_datetime(self.last_seen_at),
            "ranks": [rank.to_dict() for rank in self.ranks],
            "level": self.level,
            "valorant_region": self.valorant_region,
            "account_icon": self.account_icon.to_dict() if self.account_icon else None,
            "nickname": self.nickname,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            account_id=str(data.get("account_id", data.get("id", ""))),
            game_name=str(data["game_name"]),
            tag_line=str(data.get("tag_line", data.get("tagline", ""))),
            region=str(data.get("region", "global")),
            puuid=data.get("puuid"),
            is_owned=bool(data.get("is_owned", True)),
            created_at=_decode_datetime(data.get("created_at")),
            last_seen_at=_decode_datetime(data.get("last_seen_at")),
            ranks=tuple(RankInfo.from_dict(item) for item in data.get("ranks", [])),
            level=data.get("level"),
            valorant_region=data.get("valorant_region"),
            account_icon=AccountIcon.from_dict(data["account_icon"])
            if data.get("account_icon") is not None else None,
            nickname=data.get("nickname", ""),
        )


@dataclass(frozen=True, slots=True)
class SearchEntry:
    """One deduplicated player lookup in search history."""

    game_name: str
    tag_line: str = ""
    region: str = "global"
    game: Game = Game.VALORANT
    searched_at: datetime = field(default_factory=utc_now)
    entry_id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.game_name.strip():
            raise ValueError("game_name cannot be empty")
        object.__setattr__(self, "game_name", self.game_name.strip())
        object.__setattr__(self, "tag_line", self.tag_line.strip().lstrip("#"))
        object.__setattr__(self, "region", self.region.strip().lower() or "global")
        object.__setattr__(self, "game", Game.parse(self.game))
        object.__setattr__(self, "searched_at", _as_utc(self.searched_at) or utc_now())

    @property
    def id(self) -> str:
        return self.entry_id

    @property
    def display_name(self) -> str:
        return f"{self.game_name}#{self.tag_line}" if self.tag_line else self.game_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "game_name": self.game_name,
            "tag_line": self.tag_line,
            "region": self.region,
            "game": self.game.value,
            "searched_at": _encode_datetime(self.searched_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            entry_id=str(data.get("entry_id", data.get("id", uuid4()))),
            game_name=str(data["game_name"]),
            tag_line=str(data.get("tag_line", data.get("tagline", ""))),
            region=str(data.get("region", "global")),
            game=Game.parse(data.get("game", Game.VALORANT)),
            searched_at=_decode_datetime(data.get("searched_at")) or utc_now(),
        )


@dataclass(frozen=True, slots=True)
class FollowedAccount:
    """A searched identity pinned to the user-facing Watchlist view."""

    account_id: str
    game_name: str
    tag_line: str = ""
    region: str = "global"
    game: Game | None = None
    rank: RankInfo | None = None
    peak_rank: RankInfo | None = None
    last_game_at: datetime | None = None
    followed_at: datetime = field(default_factory=utc_now)
    updated_at: datetime | None = None
    games: tuple[Game, ...] = ()
    ranks: tuple[RankInfo, ...] = ()

    def __post_init__(self) -> None:
        if not self.account_id.strip() or not self.game_name.strip():
            raise ValueError("watchlist account id and game_name are required")
        object.__setattr__(self, "account_id", self.account_id.strip())
        object.__setattr__(self, "game_name", self.game_name.strip())
        object.__setattr__(self, "tag_line", self.tag_line.strip().lstrip("#"))
        object.__setattr__(self, "region", self.region.strip().lower() or "global")
        object.__setattr__(self, "game", Game.parse(self.game) if self.game else None)
        object.__setattr__(self, "games", tuple(dict.fromkeys(Game.parse(game) for game in self.games)))
        object.__setattr__(self, "ranks", tuple(self.ranks))
        object.__setattr__(self, "last_game_at", _as_utc(self.last_game_at))
        object.__setattr__(self, "followed_at", _as_utc(self.followed_at) or utc_now())
        object.__setattr__(self, "updated_at", _as_utc(self.updated_at))

    @property
    def id(self) -> str:
        return self.account_id

    @property
    def display_name(self) -> str:
        return f"{self.game_name}#{self.tag_line}" if self.tag_line else self.game_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "game_name": self.game_name,
            "tag_line": self.tag_line,
            "region": self.region,
            "game": self.game.value if self.game else None,
            "games": [game.value for game in self.games],
            "ranks": [rank.to_dict() for rank in self.ranks],
            "rank": self.rank.to_dict() if self.rank else None,
            "peak_rank": self.peak_rank.to_dict() if self.peak_rank else None,
            "last_game_at": _encode_datetime(self.last_game_at),
            "followed_at": _encode_datetime(self.followed_at),
            "updated_at": _encode_datetime(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        rank = data.get("rank")
        peak_rank = data.get("peak_rank")
        return cls(
            account_id=str(data.get("account_id", data.get("id", ""))),
            game_name=str(data["game_name"]),
            tag_line=str(data.get("tag_line", data.get("tagline", ""))),
            region=str(data.get("region", "global")),
            game=Game.parse(data["game"]) if data.get("game") else None,
            games=tuple(Game.parse(game) for game in data.get("games", ())),
            ranks=tuple(RankInfo.from_dict(rank) for rank in data.get("ranks", ())),
            rank=RankInfo.from_dict(rank) if isinstance(rank, Mapping) else None,
            peak_rank=RankInfo.from_dict(peak_rank) if isinstance(peak_rank, Mapping) else None,
            last_game_at=_decode_datetime(data.get("last_game_at")),
            followed_at=_decode_datetime(data.get("followed_at")) or utc_now(),
            updated_at=_decode_datetime(data.get("updated_at")),
        )


@dataclass(frozen=True, slots=True)
class MatchRecord:
    """A provider-normalized match summary."""

    match_id: str
    account_id: str
    game: Game
    played_at: datetime
    result: MatchResult = MatchResult.UNKNOWN
    queue: str | None = None
    map_name: str | None = None
    duration_seconds: int | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    rank_delta: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.match_id.strip() or not self.account_id.strip():
            raise ValueError("match_id and account_id are required")
        object.__setattr__(self, "match_id", self.match_id.strip())
        object.__setattr__(self, "account_id", self.account_id.strip())
        object.__setattr__(self, "game", Game.parse(self.game))
        object.__setattr__(self, "played_at", _as_utc(self.played_at) or utc_now())
        object.__setattr__(self, "result", MatchResult.parse(self.result))
        object.__setattr__(self, "metadata", dict(self.metadata))
        for name in ("duration_seconds", "kills", "deaths", "assists"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer or None")

    @property
    def won(self) -> bool | None:
        if self.result is MatchResult.WIN:
            return True
        if self.result is MatchResult.LOSS:
            return False
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "account_id": self.account_id,
            "game": self.game.value,
            "played_at": _encode_datetime(self.played_at),
            "result": self.result.value,
            "queue": self.queue,
            "map_name": self.map_name,
            "duration_seconds": self.duration_seconds,
            "kills": self.kills,
            "deaths": self.deaths,
            "assists": self.assists,
            "rank_delta": self.rank_delta,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            match_id=str(data.get("match_id", data.get("id", ""))),
            account_id=str(data["account_id"]),
            game=Game.parse(data["game"]),
            played_at=_decode_datetime(data.get("played_at")) or utc_now(),
            result=MatchResult.parse(data.get("result", MatchResult.UNKNOWN)),
            queue=data.get("queue"),
            map_name=data.get("map_name"),
            duration_seconds=data.get("duration_seconds"),
            kills=data.get("kills"),
            deaths=data.get("deaths"),
            assists=data.get("assists"),
            rank_delta=data.get("rank_delta"),
            metadata=data.get("metadata", {}),
        )


Match = MatchRecord


@dataclass(frozen=True, slots=True)
class Settings:
    """User preferences persisted by :class:`~peaks.adapters.persistence.Database`."""

    lock_timeout_seconds: int = 900
    layout: AccountLayout = AccountLayout.GRID
    streamer_mode: bool = False
    lock_on_blur: bool = True
    reduce_motion: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.lock_timeout_seconds, bool) or not isinstance(
            self.lock_timeout_seconds, int
        ):
            raise TypeError("lock_timeout_seconds must be an integer")
        if self.lock_timeout_seconds < 0:
            raise ValueError("lock_timeout_seconds cannot be negative")
        object.__setattr__(self, "layout", AccountLayout.parse(self.layout))

    @property
    def lock_timeout_minutes(self) -> float:
        return self.lock_timeout_seconds / 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "lock_timeout_seconds": self.lock_timeout_seconds,
            "layout": self.layout.value,
            "streamer_mode": self.streamer_mode,
            "lock_on_blur": self.lock_on_blur,
            "reduce_motion": self.reduce_motion,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        timeout = data.get("lock_timeout_seconds")
        if timeout is None and data.get("lock_timeout_minutes") is not None:
            timeout = round(float(data["lock_timeout_minutes"]) * 60)
        return cls(
            lock_timeout_seconds=900 if timeout is None else int(timeout),
            layout=AccountLayout.parse(data.get("layout", AccountLayout.GRID)),
            streamer_mode=bool(data.get("streamer_mode", False)),
            lock_on_blur=bool(data.get("lock_on_blur", True)),
            reduce_motion=bool(data.get("reduce_motion", False)),
        )


@dataclass(frozen=True, slots=True)
class CurrentMatch:
    """Current-game state, including the explicit disabled no-game state."""

    detected: bool
    game: Game | None = None
    match_id: str | None = None
    mode: str | None = None
    map_name: str | None = None
    started_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.game is not None:
            object.__setattr__(self, "game", Game.parse(self.game))
        object.__setattr__(self, "started_at", _as_utc(self.started_at))
        object.__setattr__(self, "metadata", dict(self.metadata))
        if not self.detected and any((self.game, self.match_id, self.mode, self.map_name)):
            raise ValueError("a no-game CurrentMatch cannot contain game details")

    @classmethod
    def no_game(cls) -> Self:
        return cls(detected=False)

    @property
    def clickable(self) -> bool:
        return self.detected

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "game": self.game.value if self.game else None,
            "match_id": self.match_id,
            "mode": self.mode,
            "map_name": self.map_name,
            "started_at": _encode_datetime(self.started_at),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        game = data.get("game")
        return cls(
            detected=bool(data.get("detected", False)),
            game=Game.parse(game) if game else None,
            match_id=data.get("match_id"),
            mode=data.get("mode"),
            map_name=data.get("map_name"),
            started_at=_decode_datetime(data.get("started_at")),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True, slots=True)
class SecretEntry:
    """Typed credentials payload stored by :class:`SecretVault`.

    All fields are optional because Riot login methods differ by account.  The
    vault also accepts JSON mappings for forward-compatible provider secrets.
    """

    account_id: str = field(repr=False)
    totp_secret: str | None = field(default=None, repr=False)
    cookies: Mapping[str, str] = field(default_factory=dict, repr=False)
    access_token: str | None = field(default=None, repr=False)
    refresh_token: str | None = field(default=None, repr=False)
    metadata: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "totp_secret": self.totp_secret,
            "cookies": dict(self.cookies),
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        return cls(
            account_id=str(data["account_id"]),
            totp_secret=data.get("totp_secret", data.get("totp")),
            cookies={str(key): str(value) for key, value in dict(data.get("cookies", {})).items()},
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            metadata=data.get("metadata", {}),
        )


__all__ = [
    "Account",
    "AccountLayout",
    "CurrentMatch",
    "FollowedAccount",
    "Game",
    "Match",
    "MatchRecord",
    "MatchResult",
    "Rank",
    "RankInfo",
    "RankTier",
    "SearchEntry",
    "SecretEntry",
    "Settings",
    "utc_now",
]

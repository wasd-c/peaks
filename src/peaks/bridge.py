"""Line-delimited JSON bridge between Electron and Peaks' Python services.

The Chromium process receives presentation-safe snapshots only. Authentication
secrets remain in :class:`SecretVault` and commands expose narrow operations
rather than a generic storage API.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import uuid
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

from platformdirs import user_data_path

from peaks.application.demo_data import (
    DEMO_PIN,
    DEMO_TOTP_SEED,
    demo_accounts,
    demo_current_match,
    demo_followed,
    demo_search_history,
    search_demo,
)
from peaks.domain.regions import normalize_league_region, normalize_valorant_region

# Electron starts this module with -m, where __name__ is __main__. Keep its
# diagnostics under the configured peaks logger in both launch modes.
LOGGER = logging.getLogger("peaks.bridge")
RESET_APPLICATION_CONFIRMATION = "clear-encrypted-data"
SESSION_REFRESH_INTERVAL_SECONDS = 6 * 60 * 60
SESSION_REFRESH_RETRY_SECONDS = 5 * 60

# Riot IDs are global and do not identify a League platform shard. Accounts
# authenticated through Riot SSO therefore start at ``GLOBAL`` until an
# authoritative platform is known. Never guess EUW for those accounts.
_RIOT_API_PLATFORM_REGIONS = frozenset(
    {
        "BR",
        "EUNE",
        "EUW",
        "JP",
        "KR",
        "LAN",
        "LAS",
        "ME",
        "NA",
        "OCE",
        "PH",
        "RU",
        "SG",
        "TH",
        "TR",
        "TW",
        "VN",
    }
)


class _SessionIdentityMismatchError(ValueError):
    """A safe, presentation-ready session/account binding failure."""


def _game(value: str) -> str:
    normalized = str(value).strip().casefold().replace("-", "_").replace(" ", "_")
    return {
        "league": "League of Legends",
        "league_of_legends": "League of Legends",
        "lol": "League of Legends",
        "tft": "Teamfight Tactics",
        "teamfight_tactics": "Teamfight Tactics",
        "valorant": "VALORANT",
    }.get(normalized, str(value))


def _rank(value: dict[str, Any]) -> dict[str, Any]:
    parts = str(value.get("tier") or "Unranked").split()
    embedded_division = " ".join(parts[1:]).strip()
    explicit_division = str(value.get("division") or "").strip()
    return {
        "game": _game(value.get("game", "League")),
        "tier": parts[0].lower(),
        "division": embedded_division or explicit_division,
        "rating": _optional_int(value.get("rating")),
    }


def _account_capabilities(value: Mapping[str, Any]) -> dict[str, bool]:
    """Return presentation-only actions derived from encrypted-session flags."""

    owned = bool(value.get("owned", True))
    reusable_session = bool(value.get("connected"))
    puuid = str(value.get("puuid") or "").strip()
    riot_id = str(value.get("riotId") or "").strip()
    identity_complete = bool(puuid and "#" in riot_id)
    return {
        "canConnectQr": (
            owned
            and identity_complete
            and reusable_session
        ),
        "canSaveRiotSession": owned and identity_complete,
        "canSetupMfa": (
            owned
            and identity_complete
            and reusable_session
            and not bool(value.get("hasTotp"))
        ),
    }


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    for part in str(value or "").replace("·", " ").split():
        try:
            return int(part)
        except ValueError:
            continue
    return None


def _played_label(value: object) -> str | None:
    timestamp: datetime | None = None
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, (int, float)):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1_000
        with suppress(OSError, OverflowError, ValueError):
            timestamp = datetime.fromtimestamp(numeric, UTC)
    elif isinstance(value, str) and value:
        with suppress(ValueError):
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    seconds = max(0, int((datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()))
    if seconds < 60:
        return "just now"
    if seconds < 3_600:
        return f"{seconds // 60} min ago"
    if seconds < 86_400:
        return f"{seconds // 3_600}h ago"
    return f"{seconds // 86_400}d ago"


def _played_timestamp(value: object) -> int | None:
    """Retain actual match chronology independently of the relative UI label."""
    from peaks.domain.models import _decode_datetime

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 10_000_000_000:
        value /= 1_000
    with suppress(TypeError, ValueError, OSError, OverflowError):
        played = _decode_datetime(value)
        if played is not None:
            timestamp = round(played.timestamp() * 1_000)
            return timestamp if timestamp > 0 else None
    return None


def _safe_presentation_text(value: object, *, limit: int = 256) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > limit
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in candidate)
    ):
        return None
    return candidate


def _match_stats(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    allowed = {
        "kills",
        "deaths",
        "assists",
        "combatScore",
        "roundsPlayed",
        "roundsAnalyzed",
        "headshots",
        "bodyshots",
        "legshots",
        "damage",
        "gold",
        "minions",
        "vision",
        "level",
        "placement",
        "playersEliminated",
        "health",
        "standing",
        "boardUnits",
        "augmentCount",
    }
    stats: dict[str, Any] = {
        str(key): number
        for key, number in value.items()
        if key in allowed
        and isinstance(number, (int, float))
        and not isinstance(number, bool)
        and 0 <= number <= 100_000_000
        and (key != "health" or number <= 1000)
        and (key != "standing" or (type(number) is int and 1 <= number <= 32))
        and (key != "boardUnits" or (type(number) is int and number <= 64))
        and (key != "augmentCount" or (type(number) is int and number <= 16))
    }
    observed_at = value.get("observedAt")
    if stats and isinstance(observed_at, (int, float)) and not isinstance(observed_at, bool) and 0 < observed_at <= 10**12:
        stats["observedAt"] = observed_at
    weapons = value.get("weaponUsage")
    if isinstance(weapons, (list, tuple)) and len(weapons) <= 32:
        safe_weapons: list[dict[str, Any]] = []
        for item in weapons:
            if not isinstance(item, Mapping):
                continue
            weapon = _safe_presentation_text(item.get("weapon"), limit=80)
            kills = item.get("kills")
            if weapon and isinstance(kills, int) and not isinstance(kills, bool) and 0 <= kills <= 1_000_000:
                safe_weapons.append({"weapon": weapon, "kills": kills})
        if len(safe_weapons) == len(weapons):
            stats["weaponUsage"] = safe_weapons
    rounds = value.get("roundKills")
    if isinstance(rounds, (list, tuple)) and 1 <= len(rounds) <= 128 and all(
        isinstance(kills, int) and not isinstance(kills, bool) and 0 <= kills <= 64
        for kills in rounds
    ):
        stats["roundKills"] = list(rounds)
    return stats


def _match_teams(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    teams: list[dict[str, Any]] = []
    remaining_players = 20
    for team_index, raw_team in enumerate(value[:20], start=1):
        if not isinstance(raw_team, Mapping):
            continue
        raw_players = raw_team.get("players")
        if not isinstance(raw_players, (list, tuple)):
            raw_players = ()
        players: list[dict[str, Any]] = []
        for player_index, raw_player in enumerate(raw_players[:remaining_players], start=1):
            if not isinstance(raw_player, Mapping):
                continue
            hidden = bool(raw_player.get("hidden"))
            riot_id = None if hidden else _safe_presentation_text(raw_player.get("riotId"))
            name = _safe_presentation_text(raw_player.get("name"))
            if hidden:
                name = f"Hidden player {player_index}"
            elif riot_id:
                name = riot_id
            elif name is None:
                name = f"Player {player_index}"
            rank_tier = _optional_int(raw_player.get("rankTier"))
            players.append(
                {
                    "name": name,
                    "riotId": riot_id,
                    "agent": _safe_presentation_text(raw_player.get("agent")),
                    "rank": _safe_presentation_text(raw_player.get("rank")),
                    "rankTier": rank_tier if rank_tier is not None and 0 <= rank_tier <= 27 else 0,
                    "score": _safe_presentation_text(raw_player.get("score"), limit=80),
                    "stats": _match_stats(raw_player.get("stats")),
                    "self": bool(raw_player.get("self")),
                    "hidden": hidden,
                    **_player_enrichment(raw_player, hidden=hidden),
                }
            )
        remaining_players -= len(players)
        score = raw_team.get("score")
        if not isinstance(score, (str, int, float)) or isinstance(score, bool):
            score = None
        teams.append(
            {
                "name": _safe_presentation_text(raw_team.get("name")) or f"Team {team_index}",
                "score": score,
                "won": raw_team.get("won") if isinstance(raw_team.get("won"), bool) else None,
                "players": players,
                **({"grouping": raw_team["grouping"]} if raw_team.get("grouping") in ("duo", "unassigned") else {}),
            }
        )
    return teams


def _player_enrichment(raw: Mapping[str, Any], *, hidden: bool) -> dict[str, Any]:
    """Explicit presentation allowlist; no raw party IDs or provider payloads."""

    result: dict[str, Any] = {}
    for flag in ("ready", "leader"):
        if isinstance(raw.get(flag), bool):
            result[flag] = raw[flag]
    role = _safe_presentation_text(raw.get("role"), limit=40)
    if role:
        result["role"] = role
    level = raw.get("accountLevel")
    if not hidden and isinstance(raw.get("statsLoading"), bool):
        result["statsLoading"] = raw["statsLoading"]
    if isinstance(level, int) and not isinstance(level, bool) and 0 <= level <= 100_000:
        result["accountLevel"] = level
    party = raw.get("partyId")
    if isinstance(party, str) and re.fullmatch(r"party-(?:[1-9]|1\d|20)", party):
        result["partyId"] = party
    for prefix in ("currentRank", "peakRank"):
        tier = raw.get(f"{prefix}Tier")
        name = _safe_presentation_text(raw.get(prefix), limit=40)
        if isinstance(tier, int) and not isinstance(tier, bool) and 0 <= tier <= 27 and name:
            result[prefix] = name
            result[f"{prefix}Tier"] = tier
    season = raw.get("peakRankSeason")
    if "peakRank" in result and isinstance(season, str) and re.fullmatch(r"(?:E[1-9]\d?|V\d{2}):A[1-6]", season):
        result["peakRankSeason"] = season
    overall = raw.get("overallStats")
    if not hidden and isinstance(overall, Mapping) and overall.get("scope") == "recent" and overall.get("source") == "authenticated-client-history":
        count = overall.get("matchesPlayed")
        wins = overall.get("wins")
        if isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= 5:
            stats = _match_stats(overall)
            stats.update(matchesPlayed=count, scope="recent", source="authenticated-client-history")
            if isinstance(wins, int) and not isinstance(wins, bool) and 0 <= wins <= count:
                stats["wins"] = wins
            recent = overall.get("recentKda")
            if isinstance(recent, (list, tuple)) and len(recent) == count and all(
                isinstance(row, Mapping)
                and all(isinstance(row.get(key), int) and not isinstance(row.get(key), bool) and 0 <= row[key] <= 100_000_000 for key in ("kills", "deaths"))
                for row in recent
            ) and all(sum(row[key] for row in recent) == stats.get(key) for key in ("kills", "deaths")):
                stats["recentKda"] = [{"kills": row["kills"], "deaths": row["deaths"]} for row in recent]
            result["overallStats"] = stats
    return result


def _match(value: Any) -> dict[str, Any]:
    data = value.to_dict() if hasattr(value, "to_dict") else dict(value or {})
    timestamp = _played_timestamp(data.get("played_at") or data.get("playedAtTimestamp"))
    result = str(data.get("result", "unknown")).strip().casefold()
    result_label = {
        "win": "Win",
        "victory": "Win",
        "loss": "Defeat",
        "defeat": "Defeat",
        "draw": "Draw",
        "tie": "Draw",
        "top_4": "Top 4",
        "1st place": "Top 4",
        "2nd place": "Top 4",
        "3rd place": "Top 4",
        "4th place": "Top 4",
        "placement": "Placement",
    }.get(result, "Recent match")
    duration = _optional_int(data.get("duration_seconds"))
    metadata = data.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    return {
        "id": str(data.get("match_id", data.get("id", ""))),
        "game": _game(str(data.get("game", "VALORANT"))),
        "result": result_label,
        "mode": str(data.get("queue") or data.get("mode") or "Match"),
        "map": str(data.get("map_name") or data.get("map") or "Map unavailable"),
        "playedAt": _played_label(data.get("played_at")) or data.get("playedAt"),
        **({"playedAtTimestamp": timestamp} if timestamp is not None else {}),
        "duration": f"{duration // 60}m" if duration is not None else None,
        "score": data.get("score") or metadata.get("score"),
        "delta": data.get("rank_delta") or data.get("delta"),
        "performance": data.get("performance"),
        "positive": data.get("positive"),
        "teams": _match_teams(data.get("teams") or metadata.get("teams")),
        "freeForAll": bool(data.get("freeForAll") or metadata.get("freeForAll")),
        **({"teamMode": "duos"} if data.get("teamMode") == "duos" or metadata.get("teamMode") == "duos" else {}),
        **({"enrichmentPending": True} if data.get("enrichmentPending") is True or metadata.get("enrichmentPending") is True else {}),
    }


def _vault_has_pin(vault: Any) -> bool:
    """Read both current property and legacy callable ``has_pin`` contracts.

    Errors intentionally propagate: treating an unreadable vault as uninitialized
    would route an existing profile through passcode creation.
    """
    value = getattr(vault, "has_pin", False)
    return bool(value() if callable(value) else value)


def _account(value: dict[str, Any]) -> dict[str, Any]:
    matches = []
    for match in value.get("matches", []):
        matches.append(
            _match(
                {
                    **match,
                    "match_id": match.get("id"),
                    "queue": match.get("mode"),
                    "map_name": match.get("map"),
                    "playedAt": match.get("played"),
                }
            )
        )
    return {
        **value,
        "level": 284 if value.get("connected") else 117,
        "hasTotp": value.get("totpAvailable", False),
        "ranks": [_rank(rank) for rank in value.get("ranks", [])],
        "matches": matches,
    }


class Bridge:
    def __init__(
        self,
        *,
        account_onboarding_factory: Callable[[], Any] | None = None,
        account_refresh_factory: Callable[[], Any] | None = None,
        session_importer_factory: Callable[[], Any] | None = None,
        qr_approval_factory: Callable[[], Any] | None = None,
        qr_decoder: Callable[[Mapping[str, Any]], str | None] | None = None,
        riot_browser_login: Callable[[], Mapping[str, str] | None] | None = None,
        riot_mobile_totp_setup_factory: Callable[[], Any] | None = None,
        current_game_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.demo = os.getenv("PEAKS_DEMO") == "1"
        self._onboard_preview = self.demo and os.getenv("PEAKS_ONBOARD_PREVIEW") == "1"
        self._account_onboarding_factory = account_onboarding_factory
        self._account_refresh_factory = account_refresh_factory
        self._session_importer_factory = session_importer_factory
        self._qr_approval_factory = qr_approval_factory
        self._qr_decoder = qr_decoder
        self._riot_browser_login = riot_browser_login
        self._riot_mobile_totp_setup_factory = riot_mobile_totp_setup_factory
        self._riot_mobile_totp_setup_service: Any = None
        self._current_game_factory = current_game_factory
        self._current_game_service: Any = None
        self._next_owned_account_refresh_at = 0.0
        self._session_refresh_due_at: dict[str, float] = {}
        self._session_import_in_progress = False
        self._observed_live_match: tuple[str, str, str] | None = None
        self._post_match_refresh: dict[str, Any] | None = None
        self._current_match: dict[str, Any] = {}
        self._game_detected = False
        self._riot_client_status: dict[str, Any] = {
            "detected": False,
            "label": "Not detected",
            "game": "",
        }
        self._riot_search_service: Any = None
        self._logger = LOGGER
        self._diagnostics_path: Path | None = None
        self._pin_mode = "create" if self._onboard_preview else "unlock" if self.demo else "create"
        self._pending_pin = ""
        self._demo_pin = DEMO_PIN
        self._locked = True
        self._renderer_account_handles: dict[str, str] = {}
        if self.demo and os.getenv("PEAKS_DEMO_UNLOCKED") == "1":
            self._locked = False
        self.accounts = [_account(item) for item in demo_accounts()] if self.demo else []
        self.followed = [self._player(item) for item in demo_followed()] if self.demo else []
        self.history = (
            [str(item.get("query", "")) for item in demo_search_history()] if self.demo else []
        )
        self.settings = {
            "autoLockMinutes": 15,
            "lockOnBlur": True,
            "streamerMode": False,
            "reduceMotion": False,
            "riotApiConfigured": False,
            "clipboardClearSeconds": 15,
        }
        self._secrets: dict[str, dict[str, str]] = (
            {"own-aureline": {"totp": DEMO_TOTP_SEED}, "own-peaks": {"totp": DEMO_TOTP_SEED}}
            if self.demo
            else {}
        )
        self._vault: Any = None
        self._repository: Any = None
        if not self.demo:
            self._open_services()

    @staticmethod
    def _player(item: dict[str, Any]) -> dict[str, Any]:
        games = [_game(game) for game in item.get("games", ()) or ()]
        ranks = [_rank(dict(rank)) for rank in item.get("ranks", ()) or () if isinstance(rank, Mapping)]
        matches = [
            _match(match) if "match_id" in match else dict(match)
            for match in item.get("matches", ()) or () if isinstance(match, Mapping)
        ]
        return {**item, "games": games, "ranks": ranks, "matches": matches, **({"game": games[0]} if games else {})}

    @staticmethod
    def _same_player(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
        left_riot_id = str(left.get("riotId", "")).strip().casefold()
        right_riot_id = str(right.get("riotId", "")).strip().casefold()
        if left_riot_id and right_riot_id:
            return left_riot_id == right_riot_id
        return bool(left.get("id")) and left.get("id") == right.get("id")

    @staticmethod
    def _follow_player(item: Mapping[str, Any]) -> dict[str, Any]:
        from peaks.domain.models import RankTier

        riot_id = _safe_presentation_text(item.get("riotId"))
        if riot_id is None or "#" not in riot_id:
            raise ValueError("Choose a visible Riot ID to watch")
        game = _game(str(item["game"])) if item.get("game") else None
        if game is not None and game not in {"League of Legends", "VALORANT", "Teamfight Tactics"}:
            raise ValueError("Choose a supported Riot profile")
        games = [game] if game else []
        for value in list(item.get("games", ()) or ())[:3]:
            label = _game(str(value))
            if label in {"League of Legends", "VALORANT", "Teamfight Tactics"} and label not in games:
                games.append(label)
        ranks: list[dict[str, Any]] = []
        for raw in list(item.get("ranks", ()) or ())[:3]:
            if not isinstance(raw, Mapping):
                continue
            rank = _rank(dict(raw))
            if rank["game"] not in games or rank["tier"] not in {tier.value for tier in RankTier}:
                continue
            division = _safe_presentation_text(rank.get("division"), limit=8) or ""
            rating = _optional_int(rank.get("rating"))
            ranks.append({**rank, "division": division, "rating": rating if rating is not None and 0 <= rating <= 1_000_000 else None})
        player_id = _safe_presentation_text(item.get("id"))
        if player_id is None:
            player_id = f"riot:{game.casefold() if game else 'account'}:{riot_id.casefold()}"
        region = _safe_presentation_text(item.get("region"), limit=32) or "GLOBAL"
        current_rank = _safe_presentation_text(item.get("currentRank"))
        peak_rank = _safe_presentation_text(item.get("peakRank"))
        last_game = _safe_presentation_text(item.get("lastGame"), limit=80)
        last_updated = _safe_presentation_text(item.get("lastUpdated"), limit=80)
        return {
            "id": player_id,
            "riotId": riot_id,
            "region": region,
            **({"game": game} if game else {}),
            "games": games,
            "ranks": ranks,
            "currentRank": current_rank if game else None,
            "peakRank": peak_rank if game else None,
            "lastGame": last_game,
            "lastUpdated": last_updated,
            "followed": True,
            "initials": "".join(part[:1] for part in riot_id.replace("#", " ").split())[
                :2
            ].upper(),
        }

    @staticmethod
    def _followed_view(value: Any) -> dict[str, Any]:
        data = value.to_dict() if hasattr(value, "to_dict") else dict(value or {})
        game = _game(str(data["game"])) if data.get("game") else None
        games = [_game(str(value)) for value in data.get("games", ()) or ()]
        if game and game not in games:
            games.insert(0, game)
        raw_ranks = data.get("ranks", ()) or ([data["rank"]] if isinstance(data.get("rank"), Mapping) else [])
        ranks = [_rank(dict(rank)) for rank in raw_ranks if isinstance(rank, Mapping)]

        def rank_text(raw: object) -> str | None:
            if not isinstance(raw, Mapping):
                return None
            tier = str(raw.get("tier", "Unranked")).replace("_", " ").title()
            division = str(raw.get("division") or "").strip()
            rating = _optional_int(raw.get("rating"))
            label = " ".join(part for part in (tier, division) if part)
            if rating is not None:
                label += f" · {rating} {'RR' if game == 'VALORANT' else 'LP'}"
            return label

        game_name = str(data.get("game_name", "")).strip()
        tag_line = str(data.get("tag_line", "")).strip()
        riot_id = f"{game_name}#{tag_line}" if tag_line else game_name
        return {
            "id": str(data.get("account_id", data.get("id", ""))),
            "riotId": riot_id,
            "region": str(data.get("region", "GLOBAL")).upper(),
            **({"game": game} if game else {}),
            "games": games,
            "ranks": ranks,
            "currentRank": rank_text(data.get("rank")),
            "peakRank": rank_text(data.get("peak_rank")),
            "lastGame": _played_label(data.get("last_game_at")),
            "lastUpdated": _played_label(data.get("updated_at")),
            "followed": True,
            "initials": "".join(part[:1] for part in riot_id.replace("#", " ").split())[
                :2
            ].upper(),
        }

    @staticmethod
    def _followed_domain(player: Mapping[str, Any]) -> Any:
        from peaks.domain.models import FollowedAccount, Game, RankInfo, RankTier

        riot_id = str(player["riotId"])
        game_name, _, tag_line = riot_id.partition("#")
        game = Game.parse(str(player["game"])) if player.get("game") else None

        def parse_rank(value: object) -> RankInfo | None:
            if game is None or not isinstance(value, str) or not value.strip():
                return None
            label, _, points = value.partition("·")
            parts = label.strip().split()
            if not parts or parts[0].casefold() not in {tier.value for tier in RankTier}:
                return None
            return RankInfo(
                game=game,
                tier=parts[0],
                division=" ".join(parts[1:]) or None,
                rating=_optional_int(points),
            )

        ranks = tuple(rank for value in player.get("ranks", ()) or () if (rank := Bridge._domain_rank(value)) is not None)
        primary_rank = next((rank for rank in ranks if rank.game == game), None)
        return FollowedAccount(
            account_id=str(player["id"]),
            game_name=game_name,
            tag_line=tag_line,
            region=str(player.get("region", "GLOBAL")),
            game=game,
            # Structured queues are authoritative. A label must never fill
            # another game's missing rank (for example TFT Gold as League).
            rank=primary_rank if ranks else parse_rank(player.get("currentRank")),
            peak_rank=parse_rank(player.get("peakRank")),
            games=tuple(Game.parse(value) for value in player.get("games", ()) or ()),
            ranks=ranks,
            updated_at=datetime.now(UTC),
        )

    def _open_services(self, *, recover_reset: bool = True) -> None:
        """Open the existing SQLite metadata store and OS-backed vault."""
        repository: Any = None
        try:
            from peaks.adapters.persistence import Database, SecretVault
            from peaks.adapters.persistence.profile_reset import recover_pending_reset
            from peaks.diagnostics import configure_diagnostics

            data = Path(user_data_path("Peaks", "Peaks", ensure_exists=True))
            if recover_reset and recover_pending_reset(data):
                self._logger.info("bridge.profile_reset.recovered")
            try:
                self._diagnostics_path = configure_diagnostics(data)
            except Exception as exc:
                print(
                    f"Peaks diagnostics initialization warning: {type(exc).__name__}",
                    file=sys.stderr,
                )
            self._logger.info("bridge.services.open_start")
            repository = Database(data / "peaks.sqlite3")
            vault = SecretVault(data / "vault.json")
            pin_mode = "unlock" if _vault_has_pin(vault) else "create"

            # Commit the service set only after vault state was read successfully.
            # A partial initialization must never leave a live vault in create mode.
            self._repository = repository
            self._vault = vault
            self._pin_mode = pin_mode
            self._load_database()
            self._logger.info("bridge.services.open_complete pin_mode=%s", pin_mode)
        except Exception as exc:
            if repository is not None and self._repository is not repository:
                with suppress(Exception):
                    repository.close()
            self._logger.warning("bridge.services.open_failed error_type=%s", type(exc).__name__)
            print(f"Peaks service initialization warning: {type(exc).__name__}", file=sys.stderr)

    def _load_database(self) -> None:
        if not self._repository:
            return
        try:
            loaded: list[dict[str, Any]] = []
            for item in self._repository.list_accounts(owned_only=True):
                riot_id = getattr(item, "riot_id", None) or getattr(
                    item, "display_name", "Unknown#000"
                )
                ranks: list[dict[str, Any]] = []
                for rank in getattr(item, "ranks", ()):
                    value = rank.to_dict() if hasattr(rank, "to_dict") else {}
                    if isinstance(value, dict):
                        ranks.append(_rank(value))
                matches: list[dict[str, Any]] = []
                list_matches = getattr(self._repository, "list_matches", None)
                if callable(list_matches):
                    with suppress(Exception):
                        matches = [_match(match) for match in list_matches(str(item.id), limit=20)]
                loaded.append(
                    {
                        "id": str(item.id),
                        "riotId": riot_id,
                        "region": str(item.region).upper(),
                        "leagueRegion": normalize_league_region(item.region),
                        "valorantRegion": normalize_valorant_region(getattr(item, "valorant_region", None)),
                        **({"accountIcon": {
                            "game": item.account_icon.game.label,
                            "characterId": item.account_icon.character_id,
                        }} if getattr(item, "account_icon", None) else {}),
                        **({"nickname": item.nickname} if getattr(item, "nickname", "") else {}),
                        "puuid": getattr(item, "puuid", None),
                        "level": getattr(item, "level", None),
                        "connected": False,
                        "hasTotp": False,
                        "owned": True,
                        "ranks": ranks,
                        "matches": matches,
                        "lastUpdated": _played_label(getattr(item, "last_seen_at", None)),
                    }
                )
            self.accounts = loaded
            list_followed = getattr(self._repository, "list_followed", None)
            if callable(list_followed):
                self.followed = [
                    self._followed_view(item) for item in list_followed(limit=100)
                ]
            get_settings = getattr(self._repository, "get_settings", None)
            if callable(get_settings):
                stored_settings = get_settings()
                timeout_seconds = int(
                    getattr(stored_settings, "lock_timeout_seconds", 900)
                )
                self.settings.update(
                    {
                        "autoLockMinutes": max(0, round(timeout_seconds / 60)),
                        "lockOnBlur": bool(
                            getattr(stored_settings, "lock_on_blur", True)
                        ),
                        "streamerMode": bool(getattr(stored_settings, "streamer_mode", False)),
                        "reduceMotion": bool(
                            getattr(stored_settings, "reduce_motion", False)
                        ),
                    }
                )
        except Exception as exc:
            self._logger.warning("bridge.database.load_failed error_type=%s", type(exc).__name__)

    def _update_settings(self, payload: Mapping[str, Any]) -> None:
        """Validate, persist, then expose renderer-owned preferences."""

        updates: dict[str, Any] = {}
        persisted: dict[str, Any] = {}
        if "autoLockMinutes" in payload:
            value = payload["autoLockMinutes"]
            if isinstance(value, bool):
                raise ValueError("Choose a valid automatic lock interval")
            try:
                minutes = int(value)
            except (TypeError, ValueError):
                raise ValueError("Choose a valid automatic lock interval") from None
            if minutes not in {0, 1, 5, 15, 30, 60}:
                raise ValueError("Choose a valid automatic lock interval")
            updates["autoLockMinutes"] = minutes
            persisted["lock_timeout_minutes"] = minutes
        for renderer_key, storage_key in (
            ("lockOnBlur", "lock_on_blur"),
            ("reduceMotion", "reduce_motion"),
            ("streamerMode", "streamer_mode"),
        ):
            if renderer_key not in payload:
                continue
            value = payload[renderer_key]
            if not isinstance(value, bool):
                raise ValueError("Choose a valid desktop preference")
            updates[renderer_key] = value
            persisted[storage_key] = value

        if persisted and self._repository:
            update_setting = getattr(self._repository, "update_setting", None)
            if callable(update_setting):
                update_setting(persisted)
        self.settings.update(updates)

    def _refresh_account_secret_flags(self) -> None:
        """Hydrate presentation flags only after the encrypted vault is unlocked."""

        if self.demo or not self._vault:
            return
        for account in self.accounts:
            try:
                entry = self._vault.get_entry(str(account.get("id", "")))
            except Exception:
                continue
            has_totp = bool(getattr(entry, "totp_secret", None))
            account["hasTotp"] = has_totp
            session_status = getattr(entry, "metadata", {}).get("riot_session_status", "saved")
            account["sessionStatus"] = session_status
            account["connected"] = (
                self._has_saved_riot_session(entry)
                and session_status != "reauth_required"
            )

    def _load_sensitive_configuration(self) -> None:
        """Configure the official provider only while the vault is unlocked."""

        if self.demo or not self._vault:
            return
        try:
            api_key = self._vault.get("configuration:riot_api_key") or self._vault.get(
                "integration:riot_api_key"
            )
        except Exception as exc:
            self._logger.warning(
                "bridge.provider.key_load_failed error_type=%s", type(exc).__name__
            )
            api_key = None
        if not isinstance(api_key, str) or not api_key.strip():
            self._clear_sensitive_configuration()
            return
        service = self._get_riot_search_service()
        try:
            service.set_api_key(api_key.strip())
        except Exception as exc:
            self._logger.warning(
                "bridge.provider.configure_failed error_type=%s", type(exc).__name__
            )
            self._clear_sensitive_configuration()
            return
        self.settings["riotApiConfigured"] = True
        self._logger.info("bridge.provider.configured")

    def _get_riot_search_service(self) -> Any:
        """Return the keyless local resolver, optionally configured with RGAPI."""

        service = getattr(self, "_riot_search_service", None)
        if service is None:
            from peaks.application.runtime import RiotSearchService

            service = RiotSearchService()
            self._riot_search_service = service
        return service

    def _clear_sensitive_configuration(self) -> None:
        service = getattr(self, "_riot_search_service", None)
        clear = getattr(service, "clear_api_key", None)
        if callable(clear):
            with suppress(Exception):
                clear()
        self.settings["riotApiConfigured"] = False

    def _reset_in_memory_profile(self) -> None:
        """Return presentation state to a fresh, locked local profile."""

        self._clear_sensitive_configuration()
        self._close_totp_setup_service()
        for attribute in ("_current_game_service", "_riot_search_service"):
            service = getattr(self, attribute, None)
            setattr(self, attribute, None)
            close = getattr(service, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()

        self._pending_pin = ""
        self._pin_mode = "create"
        self._locked = True
        self._demo_pin = DEMO_PIN
        self._renderer_account_handles = {}
        self.accounts = []
        self.followed = []
        self.history = []
        self._secrets = {}
        self._current_match = {}
        self._game_detected = False
        self._riot_client_status = {
            "detected": False,
            "label": "Not detected",
            "game": "",
        }
        self._next_owned_account_refresh_at = 0.0
        self._observed_live_match = None
        self._post_match_refresh = None
        self.settings = {
            "autoLockMinutes": 15,
            "lockOnBlur": True,
            "streamerMode": False,
            "reduceMotion": False,
            "riotApiConfigured": False,
            "clipboardClearSeconds": 15,
        }

    def _reset_application(self, confirmation: object) -> dict[str, Any]:
        """Erase the exact Peaks profile files and reopen an empty profile."""

        if not self._locked or self._pin_mode != "unlock":
            raise PermissionError("Lock Peaks before clearing its local data")
        if confirmation != RESET_APPLICATION_CONFIRMATION:
            raise PermissionError("Confirm the local data reset before continuing")

        if self.demo:
            self._reset_in_memory_profile()
            return self.state()

        repository_path = getattr(self._repository, "path", None)
        vault_path = getattr(self._vault, "path", None)
        profile_path = repository_path or vault_path
        profile_dir = (
            Path(profile_path).parent
            if profile_path is not None
            else Path(user_data_path("Peaks", "Peaks", ensure_exists=True))
        )

        from peaks.adapters.persistence.profile_reset import (
            begin_profile_reset,
            clear_profile_files,
        )

        try:
            marker = begin_profile_reset(profile_dir)
        except Exception as exc:
            raise RuntimeError("Peaks could not prepare the secure reset") from exc

        repository = self._repository
        vault = self._vault
        self._repository = None
        self._vault = None
        try:
            self._reset_in_memory_profile()
            destroy_repository = getattr(repository, "destroy", None)
            if callable(destroy_repository):
                destroy_repository()
            else:
                close_repository = getattr(repository, "close", None)
                if callable(close_repository):
                    close_repository()
            destroy_vault = getattr(vault, "destroy", None)
            if callable(destroy_vault):
                destroy_vault()
            else:
                lock_vault = getattr(vault, "lock", None)
                if callable(lock_vault):
                    lock_vault()
            clear_profile_files(profile_dir, keep_marker=True)

            # Keep the marker until both fresh services are usable. A crash or
            # partial failure is finished idempotently on the next launch.
            self._open_services(recover_reset=False)
            if self._repository is None or self._vault is None or self._pin_mode != "create":
                raise RuntimeError("The empty local profile could not be reopened")
            marker.unlink()
        except Exception as exc:
            self._logger.warning(
                "bridge.profile_reset.failed error_type=%s", type(exc).__name__
            )
            raise RuntimeError(
                "Reset could not finish safely. Restart Peaks to complete it."
            ) from exc

        self._logger.info("bridge.profile_reset.complete")
        return self.state()

    @staticmethod
    def _has_saved_riot_session(entry: Any) -> bool:
        return bool(
            getattr(entry, "refresh_token", None)
            or getattr(entry, "cookies", {}).get("ssid")
        )

    @staticmethod
    def _validated_refresh_token(value: Any) -> str | None:
        from peaks.adapters.riot.session_import import MAX_REFRESH_TOKEN_LENGTH

        if value is None:
            return None
        if (
            not isinstance(value, str) or not value or len(value) > MAX_REFRESH_TOKEN_LENGTH
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
        ):
            raise ValueError("Riot authorization returned an invalid refresh token")
        return value

    @staticmethod
    def _validated_session_cookies(
        cookies: Mapping[str, str], *, require_ssid: bool = True,
    ) -> dict[str, str]:
        from peaks.adapters.riot.session_import import ALLOWED_COOKIE_NAMES

        sanitized: dict[str, str] = {}
        for name, value in cookies.items():
            if name not in ALLOWED_COOKIE_NAMES or not isinstance(value, str) or not value:
                raise ValueError("Riot session cookies are invalid")
            sanitized[name] = value
        if require_ssid and "ssid" not in sanitized:
            raise ValueError("Riot session cookies are incomplete")
        return sanitized

    @staticmethod
    def _refresh_session_authorization(
        importer: Any,
        cookies: Mapping[str, str],
        refresh_token: str | None = None,
    ) -> tuple[str, dict[str, str], str | None]:
        """Prefer offline renewal and return credentials for identity-bound storage."""

        token_refresh = getattr(importer, "refresh_from_token", None)
        offline_authorize = getattr(importer, "mint_durable_authorization", None)
        refresh = getattr(importer, "refresh_authorization", None)
        authorization = None
        if refresh_token is not None and callable(token_refresh):
            authorization = token_refresh(refresh_token, cookies)
        elif callable(offline_authorize):
            authorization = offline_authorize(cookies)
        elif callable(refresh):
            authorization = refresh(cookies)
        if authorization is not None:
            access_token = getattr(authorization, "access_token", None)
            refreshed = getattr(authorization, "cookies", None)
            if not isinstance(access_token, str) or not access_token:
                raise ValueError("Riot authorization did not return an access token")
            if not isinstance(refreshed, Mapping):
                raise ValueError("Riot authorization did not return session cookies")
            durable_token = Bridge._validated_refresh_token(getattr(authorization, "refresh_token", None))
            return access_token, Bridge._validated_session_cookies(
                refreshed, require_ssid=durable_token is None,
            ), durable_token

        # Compatibility for injected legacy importers. Production importers
        # expose refresh_authorization and therefore retain cookie rotation.
        access_token = importer.mint_access_token(cookies)
        if not isinstance(access_token, str) or not access_token:
            raise ValueError("Riot authorization did not return an access token")
        return access_token, Bridge._validated_session_cookies(cookies), None

    def _existing_account_for_identity(self, puuid: str, riot_id: str) -> dict[str, Any] | None:
        normalized_puuid = puuid.casefold()
        normalized_riot_id = riot_id.casefold()
        return next(
            (
                account
                for account in self.accounts
                if (
                    str(account.get("puuid") or "").casefold() == normalized_puuid
                    or (
                        not str(account.get("puuid") or "").strip()
                        and str(account.get("riotId") or "").casefold() == normalized_riot_id
                    )
                )
            ),
            None,
        )

    def _renderer_account_id(self, internal_id: str) -> str:
        handles = getattr(self, "_renderer_account_handles", None)
        if not isinstance(handles, dict):
            handles = {}
            self._renderer_account_handles = handles
        handle = handles.get(internal_id)
        if not handle:
            handle = f"account-{uuid.uuid4()}"
            handles[internal_id] = handle
        return handle

    def _internal_account_id(self, candidate: str) -> str:
        candidate = candidate.strip()
        handles = getattr(self, "_renderer_account_handles", {})
        if isinstance(handles, dict):
            for internal_id, renderer_id in handles.items():
                if renderer_id == candidate:
                    return str(internal_id)
        # Internal callers and older renderer sessions can still address the
        # local record directly. New state snapshots never reveal this value.
        return candidate

    @staticmethod
    def _identity_regions(identity: Any, account: Mapping[str, Any]) -> dict[str, Any]:
        league = (
            normalize_league_region(getattr(identity, "league_region", None))
            or normalize_league_region(account.get("leagueRegion"))
            or normalize_league_region(account.get("region"))
        )
        valorant = (
            normalize_valorant_region(getattr(identity, "valorant_region", None))
            or normalize_valorant_region(account.get("valorantRegion"))
        )
        return {
            "region": league or str(account.get("region") or "GLOBAL"),
            "leagueRegion": league,
            "valorantRegion": valorant,
        }

    def _persist_identity_regions(self, account: dict[str, Any], identity: Any) -> None:
        regions = self._identity_regions(identity, account)
        if self._repository:
            stored = self._repository.get_account(str(account["id"]))
            if stored is not None:
                updated = replace(
                    stored, region=regions["region"], valorant_region=regions["valorantRegion"],
                )
                if updated != stored:
                    self._repository.add_account(updated)
        account.update(regions)

    def _persist_authenticated_account(self, result: Any) -> None:
        identity = getattr(result, "identity", None)
        puuid = str(getattr(identity, "puuid", "") or "").strip()
        game_name = str(getattr(identity, "game_name", "") or "").strip()
        tag_line = str(getattr(identity, "tag_line", "") or "").strip().lstrip("#")
        if not puuid or not game_name or not tag_line:
            raise ValueError("Riot account identity is incomplete")

        riot_id = f"{game_name}#{tag_line}"
        existing = self._existing_account_for_identity(puuid, riot_id)
        account_id = str(existing.get("id")) if existing else puuid
        source = str(getattr(result, "source", ""))
        regions = self._identity_regions(identity, existing or {})
        region = regions["region"]
        cookies_value = getattr(result, "cookies", None)
        refresh_token = self._validated_refresh_token(getattr(result, "refresh_token", None))
        cookies = (
            self._validated_session_cookies(cookies_value)
            if isinstance(cookies_value, Mapping)
            else None
        )

        previous_secret: Any = None
        if self._vault:
            previous_secret = self._vault.get_entry(account_id)
        if cookies is not None:
            if not self._vault:
                raise RuntimeError("Secure vault is unavailable")
            from peaks.domain.models import SecretEntry

            self._vault.put_entry(
                SecretEntry(
                    account_id=account_id,
                    totp_secret=getattr(previous_secret, "totp_secret", None),
                    cookies=cookies,
                    # Only the reusable renewal credential belongs in the
                    # encrypted vault. Access tokens remain in memory.
                    access_token=None,
                    refresh_token=refresh_token,
                    metadata={
                        **getattr(previous_secret, "metadata", {}),
                        "riot_session_status": "ready",
                        "riot_session_verified_at": datetime.now(UTC).isoformat(),
                        "riot_session_offline": bool(refresh_token),
                    },
                )
            )
            getattr(self, "_logger", LOGGER).info(
                "bridge.account.secret_saved source=%s cookie_count=%s",
                source if source in {"local_client", "browser"} else "unknown",
                len(cookies),
            )

        try:
            if not self._repository:
                raise RuntimeError("Local account database is unavailable")
            from peaks.domain.models import Account

            stored = self._repository.get_account(account_id)
            self._repository.add_account(
                Account(
                    account_id=account_id,
                    game_name=game_name,
                    tag_line=tag_line,
                    region=region,
                    puuid=puuid,
                    is_owned=True,
                    created_at=getattr(stored, "created_at", None),
                    last_seen_at=datetime.now(UTC),
                    ranks=tuple(getattr(stored, "ranks", ())),
                    level=getattr(stored, "level", None),
                    valorant_region=regions["valorantRegion"],
                )
            )
        except Exception:
            if cookies is not None and self._vault:
                with suppress(Exception):
                    if previous_secret is None:
                        self._vault.delete(account_id)
                    else:
                        self._vault.put_entry(previous_secret)
            raise

        has_saved_session = bool(cookies) or (
            self._has_saved_riot_session(previous_secret)
            and getattr(previous_secret, "metadata", {}).get("riot_session_status") != "reauth_required"
        )
        account = {
            **(existing or {}),
            "id": account_id,
            "riotId": riot_id,
            **regions,
            "puuid": puuid,
            "level": (existing or {}).get("level"),
            "connected": has_saved_session,
            "hasTotp": bool(getattr(previous_secret, "totp_secret", None))
            or bool((existing or {}).get("hasTotp")),
            "owned": True,
            "initials": (game_name[:2] or "RI").upper(),
            "lastUpdated": "Active VALORANT session"
            if source == "local_client"
            else "Riot browser sign-in",
            "ranks": list((existing or {}).get("ranks", [])),
            "matches": list((existing or {}).get("matches", [])),
        }
        if existing is None:
            self.accounts.insert(0, account)
        else:
            self.accounts[self.accounts.index(existing)] = account
        getattr(self, "_logger", LOGGER).info(
            "bridge.account.persisted source=%s reusable_session=%s",
            source if source in {"local_client", "browser"} else "unknown",
            has_saved_session,
        )

    def _add_authenticated_account(self) -> dict[str, Any]:
        if self.demo:
            account_id = f"demo-connected-{uuid.uuid4()}"
            account: dict[str, Any] = {
                "id": account_id,
                "riotId": "SignedIn#DEMO",
                "region": "EUW",
                "puuid": account_id,
                "level": None,
                "connected": True,
                "hasTotp": False,
                "owned": True,
                "ranks": [],
                "matches": [],
                "lastUpdated": "Demo browser sign-in",
            }
            self.accounts.insert(0, account)
            return account

        factory = self._account_onboarding_factory
        if factory is None:
            from peaks.application.account_onboarding import AccountOnboardingService

            factory = AccountOnboardingService
        service = factory()
        result = service.add_account()
        self._persist_authenticated_account(result)
        identity = getattr(result, "identity", None)
        puuid = str(getattr(identity, "puuid", "") or "")
        added = next(
            (account for account in self.accounts if str(account.get("puuid") or "") == puuid),
            None,
        )
        if added is not None:
            updated = self._refresh_owned_accounts(
                account_id=str(added.get("id", "")),
                fail_if_unavailable=False,
            )
            self._next_owned_account_refresh_at = monotonic() + (300 if updated else 60)
            return added
        raise RuntimeError("The authenticated Riot account could not be loaded")

    def _poll_activity(self) -> None:
        """Refresh presentation-safe local game activity for the renderer."""

        if self.demo:
            return
        service = getattr(self, "_current_game_service", None)
        if service is None:
            factory = getattr(self, "_current_game_factory", None)
            if factory is None:
                from peaks.application.runtime import CurrentGameService

                factory = CurrentGameService
            service = factory()
            self._current_game_service = service

        self._logger.info("bridge.activity.start")
        try:
            current = service.detect()
            status = service.client_status
            if not isinstance(status, Mapping):
                status = {}
            label = str(status.get("label") or "Not detected")
            if len(label) > 160 or any(
                ord(character) < 0x20 or ord(character) == 0x7F for character in label
            ):
                label = "Riot Client status unavailable"
            game = str(status.get("game") or "")
            if game not in {"League", "TFT", "VALORANT"}:
                game = ""
            available = bool(getattr(service, "detection_available", bool(current)))
            if available:
                self._current_match = dict(current) if isinstance(current, Mapping) else {}
                active_puuid = getattr(service, "active_account_puuid", None)
                active_account = next(
                    (
                        account for account in self.accounts
                        if active_puuid and account.get("puuid") == active_puuid
                        and account.get("owned", True)
                    ),
                    None,
                )
                internal_id = str(active_account.get("id", "")) if active_account else ""
                if internal_id and self._current_match:
                    self._current_match["accountId"] = self._renderer_account_id(internal_id)
                self._observe_match_transition(internal_id)
            else:
                self._mark_activity_stale()
            self._game_detected = bool(self._current_match.get("game"))
            self._riot_client_status = {
                "detected": bool(status.get("detected")),
                "label": label,
                "game": game,
            }
            self._logger.info(
                "bridge.activity.complete client_detected=%s match_detected=%s game=%s",
                self._riot_client_status["detected"],
                self._game_detected,
                game.casefold() if game else "none",
            )
        except Exception as exc:
            self._mark_activity_stale()
            self._game_detected = bool(self._current_match.get("game"))
            self._riot_client_status = {
                "detected": False,
                "label": "Riot Client status unavailable",
                "game": "",
            }
            self._logger.warning("bridge.activity.failed error_type=%s", type(exc).__name__)

    def _mark_activity_stale(self) -> None:
        """Missing telemetry never proves an observed match has ended."""

        self._current_match = dict(getattr(self, "_current_match", {}))
        if self._current_match:
            self._current_match["isStale"] = True
            self._current_match["status"] = "Game activity temporarily unavailable"

    def _observe_match_transition(self, account_id: str) -> None:
        """Arm only an owned live match, then refresh its exact final record."""

        current = self._current_match
        game = str(current.get("game", ""))
        match_id = str(current.get("id", ""))
        previous = getattr(self, "_observed_live_match", None)
        if previous and (game, match_id) != previous[:2]:
            now = monotonic()
            self._post_match_refresh = {
                "game": previous[0],
                "match_id": previous[1],
                "account_id": previous[2],
                "attempts": 0,
                "next_at": now,
                "expires_at": now + 120,
            }
            self._observed_live_match = None
        if game == "VALORANT" and match_id and account_id and current.get("phase") == "live":
            self._observed_live_match = (game, match_id, account_id)

    def _refresh_completed_match_if_due(self) -> None:
        """Retry final history at most four times over two minutes, without sleeps."""

        pending = getattr(self, "_post_match_refresh", None)
        if self.demo or not pending:
            return
        now = monotonic()
        if now < pending["next_at"]:
            return
        account = next(
            (
                account for account in self.accounts
                if account.get("id") == pending["account_id"] and account.get("owned", True)
            ),
            None,
        )
        if account is None or now > pending["expires_at"] or pending["attempts"] >= 4:
            self._post_match_refresh = None
            return
        try:
            updated = self._refresh_owned_accounts(
                account_id=pending["account_id"], fail_if_unavailable=False
            )
        except Exception as exc:
            updated = 0
            self._logger.info(
                "bridge.match.final_refresh_failed error_type=%s", type(exc).__name__
            )
        pending["attempts"] += 1
        self._next_owned_account_refresh_at = now + (300 if updated else 60)
        recorded = next(
            (
                match for match in account.get("matches", [])
                if match.get("id") == pending["match_id"]
                and str(match.get("game", "")).casefold() == pending["game"].casefold()
            ),
            None,
        )
        # History can precede match details. Keep polling until final result or
        # a recorded FFA roster is available rather than stopping at an ID stub.
        complete = recorded and (
            str(recorded.get("result", "")).casefold() in {"win", "loss", "draw", "victory", "defeat"}
            or (recorded.get("freeForAll") and recorded.get("teams"))
        )
        if complete or pending["attempts"] >= 4:
            self._post_match_refresh = None
        else:
            pending["next_at"] = now + (15, 30, 60)[pending["attempts"] - 1]

    @staticmethod
    def _snapshot_mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, (list, tuple)):
            value = value[0] if len(value) == 1 else {}
        value = value.to_dict() if hasattr(value, "to_dict") else value
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _domain_rank(value: Any) -> Any | None:
        data = value.to_dict() if hasattr(value, "to_dict") else dict(value or {})
        tier_text = str(data.get("tier") or data.get("name") or "").strip()
        if not tier_text or tier_text.casefold().startswith("requires approved"):
            return None
        tier_parts = tier_text.split()
        peak_text = str(data.get("peak_tier") or data.get("peak") or "").strip()
        peak_parts = peak_text.split()
        try:
            from peaks.domain.models import Game, RankInfo

            return RankInfo(
                game=Game.parse(data.get("game", "valorant")),
                tier=tier_parts[0],
                division=" ".join(tier_parts[1:]) or data.get("division"),
                rating=_optional_int(data.get("rating", data.get("rr"))),
                peak_tier=peak_parts[0] if peak_parts else None,
                peak_division=" ".join(peak_parts[1:]) or data.get("peak_division"),
                peak_rating=_optional_int(data.get("peak_rating")),
                updated_at=datetime.now(UTC),
            )
        except (TypeError, ValueError):
            return None

    def _persist_account_snapshot(self, account_id: str, snapshot: Mapping[str, Any]) -> None:
        if not self._repository:
            raise RuntimeError("Local account database is unavailable")
        level = _optional_int(snapshot.get("level"))
        valid_level = level is not None and 0 <= level <= 100_000
        valorant_region = normalize_valorant_region(snapshot.get("valorantRegion"))
        if valid_level or valorant_region:
            get_account = getattr(self._repository, "get_account", None)
            add_account = getattr(self._repository, "add_account", None)
            if callable(get_account) and callable(add_account):
                stored = get_account(account_id)
                if stored is not None:
                    add_account(replace(
                        stored, level=level if valid_level else stored.level,
                        valorant_region=stored.valorant_region or valorant_region,
                    ))
        add_rank = getattr(self._repository, "add_rank", None)
        if callable(add_rank):
            for value in snapshot.get("ranks", ()) or ():
                rank = self._domain_rank(value)
                if rank is not None:
                    add_rank(account_id, rank)
        add_match = getattr(self._repository, "add_match", None)
        if not callable(add_match):
            return
        from peaks.domain.models import MatchRecord

        for value in snapshot.get("matches", ()) or ():
            try:
                data = value.to_dict() if hasattr(value, "to_dict") else dict(value)
                if not data.get("played_at"):
                    continue
                data["account_id"] = account_id
                # Fetch progress belongs to this running session, never to a
                # saved match that may next be opened offline or after restart.
                metadata = dict(data.get("metadata") or {})
                metadata.pop("enrichmentPending", None)
                if isinstance(metadata.get("teams"), (list, tuple)):
                    metadata["teams"] = [
                        {
                            **team,
                            "players": [
                                {key: value for key, value in player.items() if key != "statsLoading"}
                                for player in team.get("players", ())
                                if isinstance(player, Mapping)
                            ],
                        }
                        for team in metadata["teams"]
                        if isinstance(team, Mapping)
                    ]
                data["metadata"] = metadata
                match = MatchRecord.from_dict(data)
                if match.account_id == account_id:
                    add_match(match)
            except (KeyError, TypeError, ValueError):
                continue

    @staticmethod
    def _merge_account_snapshot(
        account: dict[str, Any], snapshot: Mapping[str, Any], *, priority_match_id: str | None = None
    ) -> None:
        level = _optional_int(snapshot.get("level"))
        if level is not None and 0 <= level <= 100_000:
            account["level"] = level
        valorant_region = normalize_valorant_region(snapshot.get("valorantRegion"))
        # The local PD route fills gaps; it must not replace a known Riot Geo
        # affinity with a coarser shared service shard.
        if valorant_region and not normalize_valorant_region(account.get("valorantRegion")):
            account["valorantRegion"] = valorant_region
        ranks = list(account.get("ranks", []))
        by_game = {str(rank.get("game", "")).casefold(): index for index, rank in enumerate(ranks)}
        for raw in snapshot.get("ranks", ()) or ():
            data = raw.to_dict() if hasattr(raw, "to_dict") else dict(raw)
            view = _rank(data)
            key = str(view.get("game", "")).casefold()
            if key in by_game:
                ranks[by_game[key]] = view
            else:
                by_game[key] = len(ranks)
                ranks.append(view)
        account["ranks"] = ranks

        matches = list(account.get("matches", []))
        incoming: list[dict[str, Any]] = []
        incoming_ids: set[str] = set()
        for raw in snapshot.get("matches", ()) or ():
            view = _match(raw)
            match_id = str(view.get("id", ""))
            if not match_id or match_id in incoming_ids:
                continue
            incoming_ids.add(match_id)
            incoming.append(view)
        # Each provider page is newest-first within one game only. Retain the
        # actual chronology across games before applying the history limit;
        # relative display labels cannot establish this ordering.
        merged_matches = (
            incoming + [match for match in matches if str(match.get("id", "")) not in incoming_ids]
        )
        merged_matches.sort(
            key=lambda match: _played_timestamp(match.get("playedAtTimestamp")) or 0,
            reverse=True,
        )
        priority = next((match for match in merged_matches if match.get("id") == priority_match_id), None)
        # A report reached through an older saved page must survive a refresh
        # of the newest page, otherwise the view falls back to its stale copy.
        account["matches"] = (
            [*merged_matches[:19], priority]
            if priority is not None and priority not in merged_matches[:20]
            else merged_matches[:20]
        )
        account["lastUpdated"] = "just now"

    def _refresh_owned_accounts(
        self,
        *,
        account_id: str = "",
        fail_if_unavailable: bool = True,
        priority_match_id: str | None = None,
    ) -> int:
        if self.demo:
            for account in self.accounts:
                if not account_id or str(account.get("id", "")) == account_id:
                    account["lastUpdated"] = "just now"
            return 1

        accounts = [
            account
            for account in self.accounts
            if account.get("owned", True)
            and (not account_id or str(account.get("id", "")) == account_id)
        ]
        if not accounts:
            raise ValueError("Choose an owned account to refresh")

        factory = getattr(self, "_account_refresh_factory", None)
        if factory is None:
            from peaks.application.runtime import CurrentGameService

            local_service = getattr(self, "_current_game_service", None)
            if local_service is None:
                local_service = CurrentGameService()
                self._current_game_service = local_service
        else:
            local_service = factory()
        provider = (
            getattr(self, "_riot_search_service", None)
            if self.settings.get("riotApiConfigured")
            else None
        )
        updated = 0
        unavailable = 0
        unknown_remote_regions = 0
        local_failures: set[str] = set()
        for account in accounts:
            snapshots: list[dict[str, Any]] = []
            region = str(account.get("region") or "").strip().upper()
            puuid = account.get("puuid")
            if region not in _RIOT_API_PLATFORM_REGIONS and isinstance(puuid, str) and puuid:
                recover_region = getattr(local_service, "owned_league_platform_region", None)
                if callable(recover_region):
                    try:
                        recovered = str(recover_region(puuid) or "").strip().upper()
                    except Exception as exc:
                        recovered = ""
                        self._logger.info(
                            "bridge.account.region_recovery_unavailable error_type=%s",
                            type(exc).__name__,
                        )
                    if recovered in _RIOT_API_PLATFORM_REGIONS:
                        stored = self._repository.get_account(str(account.get("id", "")))
                        if stored is not None:
                            self._repository.add_account(replace(stored, region=recovered))
                            account["region"] = recovered
                            account["leagueRegion"] = recovered
                            region = recovered
                            self._logger.info(
                                "bridge.account.region_recovered region=%s",
                                recovered.casefold(),
                            )
            if provider is not None:
                if region not in _RIOT_API_PLATFORM_REGIONS:
                    unknown_remote_regions += 1
                    self._logger.info(
                        "bridge.account.refresh_remote_unavailable reason=region_unknown"
                    )
                else:
                    try:
                        remote = provider.account_overview(
                            str(account.get("riotId", "")),
                            region,
                        )
                        snapshot = self._snapshot_mapping(remote)
                        if snapshot:
                            snapshots.append(snapshot)
                    except Exception as exc:
                        self._logger.info(
                            "bridge.account.refresh_remote_unavailable error_type=%s",
                            type(exc).__name__,
                        )

            local_snapshot: dict[str, Any] = {}
            if isinstance(puuid, str) and puuid:
                league_snapshot = getattr(local_service, "owned_league_snapshot", None)
                if callable(league_snapshot):
                    try:
                        native_league = self._snapshot_mapping(league_snapshot(puuid))
                        if native_league:
                            snapshots.append(native_league)
                    except Exception as exc:
                        self._logger.info(
                            "bridge.account.refresh_league_unavailable error_type=%s",
                            type(exc).__name__,
                        )
                try:
                    snapshot_result = (
                        local_service.owned_valorant_snapshot(puuid, priority_match_id=priority_match_id)
                        if priority_match_id else local_service.owned_valorant_snapshot(puuid)
                    )
                    local_snapshot = self._snapshot_mapping(snapshot_result)
                except Exception as exc:
                    local_failures.add("request_error")
                    self._logger.info(
                        "bridge.account.refresh_local_unavailable error_type=%s",
                        type(exc).__name__,
                    )
                if not local_snapshot:
                    failure = getattr(local_service, "valorant_snapshot_failure", None)
                    if isinstance(failure, str) and failure:
                        local_failures.add(failure)
            if local_snapshot:
                snapshots.append(local_snapshot)

            if not snapshots:
                unavailable += 1
                continue
            for snapshot in snapshots:
                self._persist_account_snapshot(str(account.get("id", "")), snapshot)
                self._merge_account_snapshot(account, snapshot, priority_match_id=priority_match_id)
            updated += 1

        self._logger.info(
            "bridge.account.refresh_complete updated=%s unavailable=%s",
            updated,
            unavailable,
        )
        if not updated and fail_if_unavailable:
            if provider is None:
                if "valorant_session_inactive" in local_failures:
                    raise RuntimeError(
                        "Riot Client is running, but VALORANT is not active or has not "
                        "finished starting. Launch VALORANT, wait for the main menu, and "
                        "try again."
                    )
                if "entitlements_not_ready" in local_failures:
                    raise RuntimeError(
                        "Riot has not made VALORANT's entitlement token available yet. "
                        "The game may still be starting or may have just closed; if it is "
                        "open, wait a few seconds and try again."
                    )
                if "service_routes" in local_failures:
                    raise RuntimeError(
                        "VALORANT and its Riot session were detected, but Peaks could not read "
                        "the current Riot service routes. Restart VALORANT and try again; "
                        "see peaks.log for the diagnostic stage."
                    )
                if "service_version" in local_failures:
                    raise RuntimeError(
                        "VALORANT and its Riot session were detected, but the current client "
                        "version was unavailable. Restart Riot Client and VALORANT, then try again."
                    )
                if "identity_mismatch" in local_failures:
                    raise RuntimeError(
                        "VALORANT is signed in to a different Riot account than the selected "
                        "Peaks account. Switch accounts or add the active account."
                    )
                if "lockfile" in local_failures:
                    raise RuntimeError(
                        "Riot Client is running, but its local lockfile could not be verified. "
                        "Restart Riot Client and VALORANT, then try again."
                    )
                if "no_data" in local_failures:
                    raise RuntimeError(
                        "The active VALORANT account matched, but Riot returned no rank or "
                        "match-history data. Try again shortly and check peaks.log."
                    )
                if local_failures & {
                    "authentication",
                    "credentials",
                    "entitlements",
                    "entitlements_payload",
                    "local_client",
                    "remote_client",
                    "subject",
                }:
                    raise RuntimeError(
                        "VALORANT was detected, but its authenticated Riot session is unavailable. "
                        "Restart Riot Client and VALORANT, then check peaks.log."
                    )
                if "request_error" in local_failures:
                    raise RuntimeError(
                        "The local VALORANT refresh failed unexpectedly; check peaks.log for "
                        "the recorded error type."
                    )
                raise RuntimeError(
                    "No matching signed-in game account was available. Open League of Legends, "
                    "TFT, or VALORANT with the selected Riot account and try again."
                )
            if unknown_remote_regions == len(accounts):
                raise RuntimeError(
                    "League and TFT refresh needs an authoritative account region. "
                    "VALORANT data can still refresh while the matching game account is active."
                )
            raise RuntimeError("Riot account data is unavailable; check peaks.log for details")
        return updated

    def _refresh_owned_accounts_if_due(self) -> None:
        """Periodically hydrate existing owned accounts after unlock.

        The renderer polls activity every 15 seconds. Keep provider and local
        client requests bounded to at most once per minute after a miss and
        once per five minutes after a successful refresh. This also repairs
        accounts created by older builds as soon as their matching VALORANT
        session is available, without making the unlock request block.
        """

        if self.demo or not self.accounts:
            return
        now = monotonic()
        if now < float(getattr(self, "_next_owned_account_refresh_at", 0.0)):
            return
        try:
            updated = self._refresh_owned_accounts(fail_if_unavailable=False)
        except Exception as exc:
            updated = 0
            self._logger.info(
                "bridge.account.background_refresh_failed error_type=%s",
                type(exc).__name__,
            )
        self._next_owned_account_refresh_at = now + (300 if updated else 60)

    def _new_session_importer(self) -> Any:
        factory = getattr(self, "_session_importer_factory", None)
        if factory is None:
            from peaks.adapters.riot.session_import import RiotSessionImporter

            factory = RiotSessionImporter
        return factory()

    def _session_refresh_schedule(self) -> dict[str, float]:
        if not hasattr(self, "_session_refresh_due_at"):
            self._session_refresh_due_at = {}
        return self._session_refresh_due_at

    def _refresh_bound_session(
        self, importer: Any, account: Mapping[str, Any], secret: Any
    ) -> tuple[str, dict[str, str], Any, str | None]:
        saved_refresh = self._validated_refresh_token(getattr(secret, "refresh_token", None))
        cookies = self._validated_session_cookies(dict(secret.cookies), require_ssid=saved_refresh is None)
        token, refreshed, refresh_token = self._refresh_session_authorization(
            importer, cookies, saved_refresh,
        )
        identity = importer.fetch_identity(token)
        self._validate_session_binding(
            account,
            session_puuid=str(refreshed.get("sub") or getattr(identity, "puuid", "") or ""),
            identity=identity,
        )
        return token, refreshed, identity, refresh_token

    def _mark_session_reauthentication_required(self, account: dict[str, Any]) -> None:
        """Retain recovery material, but stop advertising a rejected session."""
        from peaks.domain.models import SecretEntry

        account_id = str(account["id"])
        entry = self._vault.get_entry(account_id)
        if entry is not None:
            self._vault.put_entry(SecretEntry(
                account_id=account_id,
                cookies=entry.cookies,
                totp_secret=entry.totp_secret,
                refresh_token=entry.refresh_token,
                metadata={**entry.metadata, "riot_session_status": "reauth_required"},
            ))
        account["connected"] = False
        account["sessionStatus"] = "reauth_required"

    def _refresh_saved_sessions_if_due(self) -> None:
        """Renew one saved identity per activity poll, including unused accounts.

        Only the unlocked application can access the vault. Offline credentials
        also renew on demand after a restart, without relying on this schedule.
        Transient failures back off; rejected sessions wait for explicit sign-in.
        Maintenance never opens a browser or switches the Riot Client account.
        """
        if (
            self.demo or self._locked or not self._vault
            or getattr(self, "_session_import_in_progress", False)
        ):
            return
        from peaks.adapters.riot.session_import import SessionReauthenticationRequired

        now = monotonic()
        schedule = self._session_refresh_schedule()
        for slot, account in enumerate(self.accounts, start=1):
            account_id = str(account.get("id", ""))
            if (
                not account.get("owned", True) or not account.get("puuid")
                or now < schedule.get(account_id, 0.0)
            ):
                continue
            secret = self._vault.get_entry(account_id)
            if not self._has_saved_riot_session(secret):
                continue
            if secret.metadata.get("riot_session_status") == "reauth_required":
                continue
            importer = None
            schedule[account_id] = now + SESSION_REFRESH_RETRY_SECONDS
            self._logger.info("bridge.session_maintenance.start account_slot=%s", slot)
            try:
                importer = self._new_session_importer()
                _, cookies, identity, refresh_token = self._refresh_bound_session(importer, account, secret)
                self._save_rotated_session_cookies(account_id, secret, cookies, refresh_token=refresh_token)
                self._persist_identity_regions(account, identity)
                self._logger.info("bridge.session_maintenance.complete account_slot=%s", slot)
            except (SessionReauthenticationRequired, _SessionIdentityMismatchError) as exc:
                self._mark_session_reauthentication_required(account)
                self._logger.info(
                    "bridge.session_maintenance.reauthentication_required "
                    "account_slot=%s error_type=%s", slot, type(exc).__name__,
                )
            except Exception as exc:
                self._logger.warning(
                    "bridge.session_maintenance.deferred account_slot=%s error_type=%s",
                    slot, type(exc).__name__,
                )
            finally:
                close = getattr(importer, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()
            # Bound latency and Riot requests, even with a large account list.
            return

    def _new_qr_approver(self) -> Any:
        factory = getattr(self, "_qr_approval_factory", None)
        if factory is None:
            from peaks.application.riot_connect import RiotQRApprovalService

            factory = RiotQRApprovalService
        return factory()

    def _decode_riot_client_qr(self, captures: object) -> str:
        if not isinstance(captures, list) or not captures or len(captures) > 3:
            raise ValueError("Riot Client did not provide a usable window capture")
        decoder = getattr(self, "_qr_decoder", None)
        if decoder is None:
            from peaks.application.qr_decode import decode_bgra_capture

            decoder = decode_bgra_capture
        for capture in captures:
            if not isinstance(capture, Mapping):
                continue
            payload = decoder(capture)
            if payload:
                return payload
        raise ValueError(
            "No readable Riot sign-in QR was found. Show the QR code in Riot Client "
            "at full size, then try Connect again."
        )

    def _connect_riot_client(
        self, account_id: str, captures: object, capture_state: object
    ) -> None:
        account_id = account_id.strip()
        account = next(
            (item for item in self.accounts if str(item.get("id", "")) == account_id),
            None,
        )
        if account is None:
            raise ValueError("Choose an account to connect")
        if not account.get("owned", True):
            raise ValueError("Only owned accounts can connect Riot Client")
        if self.demo:
            account["connected"] = True
            account["lastUpdated"] = "Demo Riot Client connection"
            return
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")

        puuid = str(account.get("puuid") or "").strip()
        if not puuid:
            raise ValueError("The selected account identity is incomplete")
        secret = self._vault.get_entry(account_id)
        saved_cookies = dict(getattr(secret, "cookies", {}) or {})
        if not self._has_saved_riot_session(secret):
            raise ValueError(
                "This identity needs a reusable Riot session before QR Connect. "
                "Choose Save reusable Riot session, then retry while the QR is visible."
            )
        self._validated_session_cookies(
            saved_cookies, require_ssid=not getattr(secret, "refresh_token", None),
        )

        capture_state_text = str(capture_state or "invalid")
        capture_count = len(captures) if isinstance(captures, list) else 0
        self._logger.info(
            "bridge.riot_qr.capture.received state=%s count=%s",
            capture_state_text
            if capture_state_text
            in {"ready", "window_not_found", "window_capture_failed", "capture_error"}
            else "invalid",
            min(capture_count, 3),
        )
        capture_errors = {
            "window_not_found": (
                "Riot Client window was not found. Open Riot Client, show its QR "
                "sign-in screen, and try Connect again."
            ),
            "window_capture_failed": (
                "Riot Client was found, but its sign-in window could not be captured. "
                "Restore the window and try again."
            ),
            "capture_error": (
                "Windows could not capture Riot Client. Restore its window and try again; "
                "the capture stage is recorded in peaks.log."
            ),
        }
        if capture_state_text in capture_errors:
            raise ValueError(capture_errors[capture_state_text])
        if capture_state_text != "ready":
            raise ValueError("Riot Client did not provide a trusted window capture")

        self._logger.info("bridge.riot_qr.capture.decode_start")
        try:
            qr_text = self._decode_riot_client_qr(captures)
        except Exception as exc:
            self._logger.warning(
                "bridge.riot_qr.capture.failed error_type=%s", type(exc).__name__
            )
            raise
        from peaks.adapters.riot.qr import QRParseError, parse_riot_qr

        try:
            qr = parse_riot_qr(qr_text)
        except (QRParseError, TypeError, ValueError):
            self._logger.info("bridge.riot_qr.capture.invalid_payload")
            raise ValueError("The detected code is not a valid Riot sign-in QR") from None
        self._logger.info("bridge.riot_qr.capture.decode_complete")

        approver = self._new_qr_approver()
        importer = self._new_session_importer()
        access_token = ""
        try:
            from peaks.application.riot_connect import (
                AccountBindingError,
                OwnedAccountCredentials,
            )

            self._logger.info("bridge.riot_qr.session.mint_start")
            from peaks.adapters.riot.session_import import SessionReauthenticationRequired

            try:
                access_token, refreshed_cookies, identity, refresh_token = self._refresh_bound_session(
                    importer, account, secret,
                )
                self._save_rotated_session_cookies(
                    account_id,
                    secret,
                    refreshed_cookies,
                    refresh_token=refresh_token,
                )
                self._persist_identity_regions(account, identity)
            except _SessionIdentityMismatchError:
                self._logger.warning("bridge.riot_qr.session.identity_mismatch")
                raise
            except SessionReauthenticationRequired:
                self._mark_session_reauthentication_required(account)
                raise RuntimeError(
                    "Riot requires sign-in again for this account. Choose Sign in to Riot "
                    "again, finish sign-in in the temporary browser, then retry a fresh QR."
                ) from None
            except Exception as exc:
                self._logger.warning(
                    "bridge.riot_qr.session.mint_failed error_type=%s",
                    type(exc).__name__,
                )
                raise RuntimeError(
                    "Riot session renewal is temporarily unavailable. Try again shortly; "
                    "peaks.log contains the failed stage."
                ) from None
            self._logger.info("bridge.riot_qr.session.identity_bound")
            try:
                approver.session_info(
                    qr,
                    access_token=access_token,
                    selected_account_puuid=puuid,
                )
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                self._logger.warning(
                    "bridge.riot_qr.session.details_failed error_type=%s status=%s",
                    type(exc).__name__,
                    status if isinstance(status, int) else "unknown",
                )
                suffix = f" (HTTP {status})" if isinstance(status, int) else ""
                raise RuntimeError(
                    "Riot could not verify the pending QR session"
                    f"{suffix}. Refresh the QR in Riot Client and try again."
                ) from None
            self._logger.info("bridge.riot_qr.session.details_verified")
            credentials = OwnedAccountCredentials(
                puuid=puuid,
                access_token=access_token,
            )

            try:
                result = approver.approve(
                    qr,
                    credentials,
                    # Clicking Connect, selecting, dropping, or pasting the
                    # QR is the explicit approval action in this flow.
                    user_approved=True,
                )
            except AccountBindingError:
                self._logger.warning("bridge.riot_qr.approval.session_binding_changed")
                raise ValueError(
                    "The selected Riot session changed while connecting. Refresh the QR "
                    "and try again."
                ) from None
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                self._logger.warning(
                    "bridge.riot_qr.approval.failed error_type=%s status=%s",
                    type(exc).__name__,
                    status if isinstance(status, int) else "unknown",
                )
                suffix = f" (HTTP {status})" if isinstance(status, int) else ""
                raise RuntimeError(
                    "Riot Client sign-in was not approved"
                    f"{suffix}. Refresh the QR and try again."
                ) from None
            self._logger.info(
                "bridge.riot_qr.approval.complete method=%s",
                str(getattr(result, "method", "unknown")),
            )
            account["connected"] = True
            account["lastUpdated"] = "Riot Client connected just now"
        finally:
            access_token = ""
            for service in (approver, importer):
                close = getattr(service, "close", None)
                if callable(close):
                    with suppress(Exception):
                        close()

    def _login_for_reusable_session(self) -> Mapping[str, str] | None:
        login = getattr(self, "_riot_browser_login", None)
        if login is None:
            from peaks.adapters.riot.browser_login import login_riot_account

            login = login_riot_account
        return login()

    @staticmethod
    def _split_riot_id(riot_id: str) -> tuple[str, str]:
        game_name, separator, tag_line = riot_id.partition("#")
        return game_name.strip(), tag_line.strip().lstrip("#") if separator else ""

    @staticmethod
    def _validate_session_binding(
        account: Mapping[str, Any],
        *,
        session_puuid: str,
        identity: Any,
    ) -> None:
        identity_puuid = str(getattr(identity, "puuid", "") or "").strip()
        if not session_puuid or not identity_puuid or session_puuid != identity_puuid:
            raise _SessionIdentityMismatchError("Riot session identity could not be verified")

        stored_puuid = str(account.get("puuid") or "").strip()
        if stored_puuid and stored_puuid != identity_puuid:
            raise _SessionIdentityMismatchError("This Riot session belongs to a different account")

        stored_name, stored_tag = Bridge._split_riot_id(str(account.get("riotId", "")))
        returned_name = str(getattr(identity, "game_name", "") or "").strip()
        returned_tag = str(getattr(identity, "tag_line", "") or "").strip().lstrip("#")
        if returned_name and stored_name and returned_name.casefold() != stored_name.casefold():
            raise _SessionIdentityMismatchError("This Riot session belongs to a different account")
        if returned_tag and stored_tag and returned_tag.casefold() != stored_tag.casefold():
            raise _SessionIdentityMismatchError("This Riot session belongs to a different account")

    def _save_rotated_session_cookies(
        self,
        account_id: str,
        previous_secret: Any,
        cookies: Mapping[str, str],
        *, refresh_token: str | None = None,
    ) -> None:
        """Persist identity-bound renewal credentials in the encrypted vault."""

        if not self._vault or previous_secret is None:
            raise RuntimeError("Secure vault is unavailable")
        refresh_token = self._validated_refresh_token(refresh_token)
        sanitized = self._validated_session_cookies(cookies, require_ssid=refresh_token is None)
        previous_cookies = self._validated_session_cookies(
            dict(getattr(previous_secret, "cookies", {}) or {}),
            require_ssid=not getattr(previous_secret, "refresh_token", None),
        )
        from peaks.domain.models import SecretEntry

        current = self._vault.get_entry(account_id)
        if (
            current is None or dict(current.cookies) != previous_cookies
            or current.refresh_token != getattr(previous_secret, "refresh_token", None)
        ):
            raise RuntimeError("The saved Riot session changed; retry this action")
        self._vault.put_entry(
            SecretEntry(
                account_id=account_id,
                totp_secret=current.totp_secret,
                cookies=sanitized,
                access_token=None,
                refresh_token=refresh_token,
                metadata={
                    **current.metadata,
                    "riot_session_status": "ready",
                    "riot_session_verified_at": datetime.now(UTC).isoformat(),
                    "riot_session_offline": bool(refresh_token),
                },
            )
        )
        self._session_refresh_schedule()[account_id] = monotonic() + SESSION_REFRESH_INTERVAL_SECONDS
        for account in self.accounts:
            if str(account.get("id", "")) == account_id:
                account["connected"] = True
                account["sessionStatus"] = "ready"
        self._logger.info(
            "bridge.riot_qr.session.cookies_rotated cookie_count=%s",
            len(sanitized),
        )

    def _capture_browser_session(self, importer: Any) -> tuple[dict[str, str], Any]:
        self._logger.info("bridge.session_import.browser.start")
        browser_cookies = self._login_for_reusable_session()
        if browser_cookies is None:
            self._logger.info("bridge.session_import.browser.cancelled")
            raise ValueError("Riot browser sign-in was cancelled, closed, or timed out")
        cookies = self._validated_session_cookies(browser_cookies)
        self._logger.info(
            "bridge.session_import.browser.cookies_captured cookie_count=%s", len(cookies)
        )
        access_token = ""
        try:
            access_token, cookies, refresh_token = self._refresh_session_authorization(importer, cookies)
            identity = importer.fetch_identity(access_token)
        finally:
            access_token = ""
        session_puuid = str(cookies.get("sub") or getattr(identity, "puuid", "") or "")
        self._logger.info("bridge.session_import.browser.identity_received")
        return cookies, (session_puuid, identity, refresh_token)

    def _save_imported_session(
        self,
        account: dict[str, Any],
        *,
        cookies: Mapping[str, str],
        identity: Any,
        source: str,
        refresh_token: str | None = None,
    ) -> None:
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")
        if not self._repository:
            raise RuntimeError("Local account database is unavailable")

        account_id = str(account.get("id", "")).strip()
        if not account_id:
            raise ValueError("Choose an account to connect")
        refresh_token = self._validated_refresh_token(refresh_token)
        sanitized = self._validated_session_cookies(cookies, require_ssid=refresh_token is None)
        previous_secret = self._vault.get_entry(account_id)

        from peaks.domain.models import Account, SecretEntry

        self._vault.put_entry(
            SecretEntry(
                account_id=account_id,
                totp_secret=getattr(previous_secret, "totp_secret", None),
                cookies=sanitized,
                access_token=None,
                refresh_token=refresh_token,
                metadata={
                    **getattr(previous_secret, "metadata", {}),
                    "riot_session_status": "ready",
                    "riot_session_verified_at": datetime.now(UTC).isoformat(),
                    "riot_session_offline": bool(refresh_token),
                },
            )
        )
        try:
            stored = self._repository.get_account(account_id)
            regions = self._identity_regions(identity, account)
            stored_name, stored_tag = self._split_riot_id(str(account.get("riotId", "")))
            game_name = str(getattr(identity, "game_name", "") or stored_name).strip()
            tag_line = str(getattr(identity, "tag_line", "") or stored_tag).strip().lstrip("#")
            puuid = str(getattr(identity, "puuid", "") or "").strip()
            if not game_name or not tag_line or not puuid:
                raise _SessionIdentityMismatchError("Riot session identity could not be verified")
            self._repository.add_account(
                Account(
                    account_id=account_id,
                    game_name=game_name,
                    tag_line=tag_line,
                    region=regions["region"],
                    puuid=puuid,
                    is_owned=True,
                    created_at=getattr(stored, "created_at", None),
                    last_seen_at=datetime.now(UTC),
                    ranks=tuple(getattr(stored, "ranks", ())),
                    level=getattr(stored, "level", None),
                    valorant_region=regions["valorantRegion"],
                    account_icon=getattr(stored, "account_icon", None),
                    nickname=getattr(stored, "nickname", ""),
                )
            )
        except Exception:
            with suppress(Exception):
                if previous_secret is None:
                    self._vault.delete(account_id)
                else:
                    self._vault.put_entry(previous_secret)
            raise

        account.update(regions)
        account["puuid"] = puuid
        account["connected"] = True
        account["sessionStatus"] = "ready"
        self._session_refresh_schedule()[account_id] = monotonic() + SESSION_REFRESH_INTERVAL_SECONDS
        account["hasTotp"] = bool(getattr(previous_secret, "totp_secret", None))
        account["lastUpdated"] = (
            "Current Riot Client session" if source == "riot_client"
            else "Riot session renewed" if source == "saved_session"
            else "Riot browser sign-in"
        )
        self._logger.info(
            "bridge.session_import.saved source=%s cookie_count=%s",
            source,
            len(sanitized),
        )

    def _import_riot_session(self, account_id: str, *, force_sign_in: bool = False) -> None:
        account_id = account_id.strip()
        account = next(
            (item for item in self.accounts if str(item.get("id", "")) == account_id),
            None,
        )
        if account is None:
            raise ValueError("Choose an account to connect")
        if not account.get("owned", True):
            raise ValueError("Only owned accounts can save a Riot session")
        if self.demo:
            account["connected"] = True
            account["lastUpdated"] = "Demo Riot session"
            return

        from peaks.adapters.riot.session_import import (
            RiotSessionImportError,
            SessionReauthenticationRequired,
            SessionSettingsError,
        )

        self._logger.info("bridge.session_import.start")
        importer = self._new_session_importer()
        source = "riot_client"
        refresh_token = None
        try:
            if force_sign_in:
                # The explicit Refresh Riot sign-in action must obtain a new
                # account-site login, even when a saved game token still works.
                # Do not refresh saved credentials or import the local client
                # before this browser flow; neither proves fresh account auth.
                self._logger.info("bridge.session_import.browser.requested")
                cookies, browser_identity = self._capture_browser_session(importer)
                session_puuid, identity, refresh_token = browser_identity
                self._validate_session_binding(
                    account, session_puuid=session_puuid, identity=identity,
                )
                self._save_imported_session(
                    account, cookies=cookies, identity=identity, source="browser",
                    refresh_token=refresh_token,
                )
                return
            try:
                saved = self._vault.get_entry(account_id) if self._vault else None
                if saved is not None and self._has_saved_riot_session(saved):
                    if saved.metadata.get("riot_session_status") == "reauth_required":
                        raise SessionReauthenticationRequired("auth")
                    try:
                        _, cookies, identity, refresh_token = self._refresh_bound_session(importer, account, saved)
                    except (SessionReauthenticationRequired, SessionSettingsError, _SessionIdentityMismatchError):
                        raise
                    except Exception:
                        raise RuntimeError(
                            "Riot session renewal is temporarily unavailable. Try again shortly."
                        ) from None
                    self._save_imported_session(
                        account, cookies=cookies, identity=identity, source="saved_session",
                        refresh_token=refresh_token,
                    )
                    return
                bound_import = getattr(importer, "import_durable_session_for_identity", None)
                if not callable(bound_import):
                    bound_import = getattr(importer, "import_session_for_identity", None)
                imported = (
                    bound_import(str(account["puuid"]))
                    if callable(bound_import) and account.get("puuid")
                    else importer.import_current_session()
                )
                identity = importer.fetch_identity(imported.access_token)
                session_puuid = str(getattr(imported, "puuid", "") or "")
                self._validate_session_binding(
                    account,
                    session_puuid=session_puuid,
                    identity=identity,
                )
                cookies = self._validated_session_cookies(imported.cookies)
                refresh_token = self._validated_refresh_token(getattr(imported, "refresh_token", None))
                self._logger.info(
                    "bridge.session_import.local.complete cookie_count=%s", len(cookies)
                )
            except (RiotSessionImportError, _SessionIdentityMismatchError) as exc:
                self._logger.info(
                    "bridge.session_import.local.unavailable error_type=%s fallback=browser",
                    type(exc).__name__,
                )
                source = "browser"
                try:
                    cookies, browser_identity = self._capture_browser_session(importer)
                    session_puuid, identity, refresh_token = browser_identity
                    self._validate_session_binding(
                        account,
                        session_puuid=session_puuid,
                        identity=identity,
                    )
                except _SessionIdentityMismatchError:
                    self._logger.warning("bridge.session_import.browser.identity_mismatch")
                    raise
                except ValueError:
                    raise
                except Exception as browser_error:
                    self._logger.warning(
                        "bridge.session_import.browser.failed error_type=%s",
                        type(browser_error).__name__,
                    )
                    raise RuntimeError(
                        "Riot browser sign-in could not create a reusable session"
                    ) from None
            self._save_imported_session(
                account,
                cookies=cookies,
                identity=identity,
                source=source,
                refresh_token=refresh_token,
            )
        except _SessionIdentityMismatchError:
            raise
        except ValueError:
            raise
        except Exception as exc:
            self._logger.warning("bridge.session_import.failed error_type=%s", type(exc).__name__)
            raise RuntimeError(
                "Could not save the Riot session securely; check peaks.log for the failed stage"
            ) from None
        finally:
            close = getattr(importer, "close", None)
            if callable(close):
                with suppress(Exception):
                    close()

    def _totp_setup_account(self, account_id: str) -> dict[str, Any]:
        account_id = account_id.strip()
        account = next(
            (item for item in self.accounts if str(item.get("id", "")) == account_id),
            None,
        )
        if account is None:
            raise ValueError("Choose an account for authenticator setup")
        if not account.get("owned", True):
            raise ValueError("Only owned accounts can save an authenticator secret")
        puuid = str(account.get("puuid") or "").strip()
        riot_id = str(account.get("riotId") or "").strip()
        if not puuid or not riot_id or "#" not in riot_id:
            raise ValueError("The selected account identity is incomplete")
        return account

    def _totp_setup_service(self) -> Any:
        if self._riot_mobile_totp_setup_service is None:
            factory = self._riot_mobile_totp_setup_factory
            if factory is None:
                from peaks.application.riot_mobile_totp_setup import (
                    RiotMobileTotpSetupService,
                )

                factory = RiotMobileTotpSetupService
            self._riot_mobile_totp_setup_service = factory()
        return self._riot_mobile_totp_setup_service

    def _close_totp_setup_service(self) -> None:
        service = getattr(self, "_riot_mobile_totp_setup_service", None)
        self._riot_mobile_totp_setup_service = None
        close = getattr(service, "close", None)
        if callable(close):
            with suppress(Exception):
                close()

    def _prepare_riot_mobile_totp(self, account_id: str) -> dict[str, Any]:
        account = self._totp_setup_account(account_id)
        account_id = str(account["id"])
        if self.demo:
            return {
                "confirmationId": f"demo:{account_id}",
                "accountId": account_id,
                "riotId": str(account["riotId"]),
                "expiresInSeconds": 300,
            }
        reusable_cookies = self._totp_setup_cookies(account_id)
        proposal = self._totp_setup_service().prepare(
            account_id=account_id,
            expected_puuid=str(account["puuid"]),
            expected_riot_id=str(account["riotId"]),
            reusable_sso_cookies=reusable_cookies,
        )
        return {
            "confirmationId": str(proposal.confirmation_id),
            "accountId": str(proposal.account_id),
            "riotId": str(proposal.riot_id),
            "expiresInSeconds": int(proposal.expires_in_seconds),
        }

    def _totp_setup_cookies(self, account_id: str) -> dict[str, str]:
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")
        existing = self._vault.get_entry(account_id)
        if getattr(existing, "totp_secret", None):
            raise ValueError(
                "An authenticator secret is already saved for this account; Peaks will not replace it"
            )
        reusable_cookies = dict(getattr(existing, "cookies", {}) or {})
        if not reusable_cookies:
            raise ValueError(
                "Save a reusable Riot session for this account before setting up Riot MFA"
            )
        return self._validated_session_cookies(reusable_cookies)

    def _enable_riot_mfa(self, account_id: str) -> dict[str, Any]:
        """The user's Enable MFA click authorizes enrollment for this account."""
        account = self._totp_setup_account(account_id)
        account_id = str(account["id"])
        if self.demo:
            if account.get("hasTotp"):
                raise ValueError("An authenticator is already saved for this account")
            return self._confirm_riot_mobile_totp(
                account_id=account_id, confirmation_id=f"demo:{account_id}",
            )
        reusable_cookies = self._totp_setup_cookies(account_id)
        result = self._totp_setup_service().enable(
            account_id=account_id,
            expected_puuid=str(account["puuid"]),
            expected_riot_id=str(account["riotId"]),
            reusable_sso_cookies=reusable_cookies,
            persist_seed=lambda seed: self._save_totp_seed(account, seed),
        )
        return {
            "state": self.state(),
            "seedSaved": bool(result.seed_saved),
            "verified": bool(result.verified),
            "warning": result.warning,
        }

    def _save_totp_seed(self, account: dict[str, Any], seed: str) -> None:
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")
        from peaks.adapters.riot.totp import parse_seed
        from peaks.domain.models import SecretEntry

        account_id = str(account["id"])
        normalized = parse_seed(seed)
        previous = self._vault.get_entry(account_id)
        if getattr(previous, "totp_secret", None):
            raise ValueError("An authenticator secret is already saved for this account")
        self._vault.put_entry(
            SecretEntry(
                account_id=account_id,
                totp_secret=normalized,
                cookies=getattr(previous, "cookies", {}),
                access_token=None,
                refresh_token=getattr(previous, "refresh_token", None),
                metadata=getattr(previous, "metadata", {}),
            )
        )
        account["hasTotp"] = True

    def _confirm_riot_mobile_totp(
        self,
        *,
        account_id: str,
        confirmation_id: str,
    ) -> dict[str, Any]:
        account = self._totp_setup_account(account_id)
        account_id = str(account["id"])
        if self.demo:
            if confirmation_id != f"demo:{account_id}":
                raise ValueError("Authenticator setup confirmation expired; start again")
            self._secrets.setdefault(account_id, {})["totp"] = DEMO_TOTP_SEED
            account["hasTotp"] = True
            return {
                "state": self.state(),
                "seedSaved": True,
                "verified": True,
                "warning": None,
            }
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")
        result = self._totp_setup_service().confirm(
            confirmation_id=confirmation_id,
            account_id=account_id,
            persist_seed=lambda seed: self._save_totp_seed(account, seed),
        )
        return {
            "state": self.state(),
            "seedSaved": bool(result.seed_saved),
            "verified": bool(result.verified),
            "warning": result.warning,
        }

    def _cancel_riot_mobile_totp(self, confirmation_id: str) -> None:
        service = self._riot_mobile_totp_setup_service
        if service is not None:
            service.cancel(confirmation_id)

    def _restore_account_secrets(self, snapshot: Mapping[str, Any]) -> None:
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")
        for key, value in snapshot.items():
            self._vault.put(key, value)

    def _remove_account(self, account_id: str) -> None:
        account_id = account_id.strip()
        if not account_id:
            raise ValueError("Choose an account to delete")
        account = next(
            (item for item in self.accounts if str(item.get("id", "")) == account_id),
            None,
        )
        if account is None:
            raise ValueError("That account is no longer available")

        if self.demo:
            self.accounts.remove(account)
            self._secrets.pop(account_id, None)
            return

        if not self._repository:
            raise RuntimeError("Local account database is unavailable")
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")

        try:
            prefix = f"{account_id}:"
            vault_keys = self._vault.keys()
            secret_keys = {key for key in vault_keys if key == account_id or key.startswith(prefix)}
            secret_snapshot = {key: self._vault.get(key) for key in secret_keys}
        except Exception as exc:
            raise RuntimeError("Encrypted account secrets could not be read") from exc

        try:
            for key in secret_snapshot:
                self._vault.delete(key)
        except Exception as exc:
            try:
                self._restore_account_secrets(secret_snapshot)
            except Exception as restore_exc:
                raise RuntimeError(
                    "Account deletion stopped and encrypted secrets could not be restored"
                ) from restore_exc
            raise RuntimeError("Encrypted account secrets could not be deleted") from exc

        try:
            removed = self._repository.remove_account(account_id)
            if not removed:
                raise RuntimeError("The local account record was not found")
        except Exception as exc:
            try:
                self._restore_account_secrets(secret_snapshot)
            except Exception as restore_exc:
                raise RuntimeError(
                    "Account deletion stopped and encrypted secrets could not be restored"
                ) from restore_exc
            raise RuntimeError("Account could not be deleted from local storage") from exc

        self.accounts.remove(account)
        self._secrets.pop(account_id, None)
        handles = getattr(self, "_renderer_account_handles", None)
        if isinstance(handles, dict):
            handles.pop(account_id, None)
        # A pending MFA browser session is bound to an account that may have
        # just been deleted. Drop all one-time confirmations immediately.
        self._close_totp_setup_service()

    def _set_account_icon(self, account_id: str, value: Any, **preferences: Any) -> None:
        account = next(
            (item for item in self.accounts if str(item.get("id", "")) == account_id),
            None,
        )
        if account is None:
            raise ValueError("That account is no longer available")
        if not account.get("owned", True):
            raise ValueError("Only owned accounts can change their icon")

        from peaks.domain.models import AccountIcon, Game, normalize_account_nickname

        nickname = (
            normalize_account_nickname(preferences["nickname"])
            if "nickname" in preferences else None
        )

        icon = None
        if value is not None:
            if (
                not isinstance(value, Mapping)
                or set(value) != {"game", "characterId"}
                or value.get("game") not in ("VALORANT", "League of Legends")
            ):
                raise ValueError("Choose a valid character icon")
            icon = AccountIcon(Game.parse(value["game"]), value["characterId"])
        if not self.demo:
            if not self._repository:
                raise RuntimeError("Local account database is unavailable")
            # Persist before changing the snapshot so a failed write cannot
            # show a selection that disappears the next time Peaks starts.
            self._repository.set_account_icon(
                account_id, icon, **({"nickname": nickname} if nickname is not None else {}),
            )
        if icon is None:
            account.pop("accountIcon", None)
        else:
            account["accountIcon"] = {
                "game": icon.game.label, "characterId": icon.character_id,
            }
        if nickname:
            account["nickname"] = nickname
        elif nickname is not None:
            account.pop("nickname", None)

    def state(self) -> dict[str, Any]:
        visible = not self._locked
        visible_accounts: list[dict[str, Any]] = []
        if visible:
            for account in self.accounts:
                presented = {key: value for key, value in account.items() if key != "puuid"}
                presented.update(_account_capabilities(account))
                if not self.demo:
                    presented["id"] = self._renderer_account_id(
                        str(account.get("id", ""))
                    )
                visible_accounts.append(presented)
        current_match = (
            demo_current_match()
            if self.demo and visible
            else dict(getattr(self, "_current_match", {}))
            if visible
            else {}
        )
        if current_match:
            current_match["game"] = _game(current_match.get("game", ""))
            current_match["teams"] = _match_teams(current_match.get("teams"))
        riot_client = (
            {
                "detected": visible,
                "label": "VALORANT · Competitive" if visible else "Not detected",
                "game": "VALORANT" if visible else "",
            }
            if self.demo
            else dict(
                getattr(
                    self,
                    "_riot_client_status",
                    {"detected": False, "label": "Not detected", "game": ""},
                )
            )
            if visible
            else {"detected": False, "label": "Not detected", "game": ""}
        )
        return {
            "locked": self._locked,
            "hasPasscode": self._pin_mode != "create" or bool(self._pending_pin),
            "pinMode": self._pin_mode,
            "pinError": "",
            "accounts": visible_accounts,
            "followed": self.followed if visible else [],
            "searchHistory": self.history if visible else [],
            "currentMatch": current_match,
            "gameDetected": bool(current_match.get("game")),
            "settings": self.settings,
            "riotClient": riot_client,
        }

    def _change_security_code(self, payload: Mapping[str, Any]) -> None:
        old_pin, new_pin, confirmation = (
            payload.get("oldPin"), payload.get("newPin"), payload.get("confirmPin"),
        )
        if any(not isinstance(value, str) or re.fullmatch(r"[0-9]{4}", value) is None
               for value in (old_pin, new_pin, confirmation)):
            raise ValueError("Enter four digits in each passcode field")
        if new_pin != confirmation:
            raise ValueError("The new passcodes do not match")
        if old_pin == new_pin:
            raise ValueError("Choose a different passcode")
        if self.demo:
            if old_pin != self._demo_pin:
                raise ValueError("The current passcode was not recognized")
            self._demo_pin = str(new_pin)
            return
        if not self._vault:
            raise RuntimeError("Secure vault is unavailable")
        from peaks.adapters.persistence.secret_vault import InvalidPinError

        try:
            self._vault.change_pin(str(old_pin), str(new_pin))
        except InvalidPinError:
            retry = int(self._vault.retry_after) + 1
            raise ValueError(
                f"The current passcode was not accepted. Try again in {retry} seconds."
            ) from None
        except Exception:
            raise RuntimeError("The security code could not be changed. Your vault was retained.") from None
        finally:
            # A failed atomic write can leave the vault locked. Keep the renderer
            # and API-key lifetime consistent with the actual vault state.
            if not self._vault.is_unlocked:
                self._locked = True
                self._clear_sensitive_configuration()
                self._close_totp_setup_service()

    def handle(self, command: str, payload: dict[str, Any]) -> Any:
        if command == "state":
            return self.state()
        if command == "activity":
            if not self._locked:
                self._poll_activity()
                self._refresh_completed_match_if_due()
                self._refresh_owned_accounts_if_due()
                self._refresh_saved_sessions_if_due()
            return self.state()
        if command == "pin":
            pin = str(payload.get("pin", ""))
            if len(pin) != 4 or not pin.isdigit():
                raise ValueError("Enter a four-digit passcode")
            if self.demo:
                if self._pin_mode == "create":
                    self._pending_pin, self._pin_mode = pin, "confirm"
                elif self._pin_mode == "confirm":
                    if pin != self._pending_pin:
                        self._pending_pin, self._pin_mode = "", "create"
                        raise ValueError("Passcodes did not match. Try again.")
                    self._demo_pin = pin
                    self._pending_pin = ""
                    self._pin_mode = "unlock"
                    self._locked = False
                else:
                    if pin != self._demo_pin:
                        raise ValueError("That passcode was not recognized")
                    self._locked = False
            elif self._pin_mode == "create":
                self._pending_pin, self._pin_mode = pin, "confirm"
            elif self._pin_mode == "confirm":
                if pin != self._pending_pin:
                    self._pending_pin, self._pin_mode = "", "create"
                    raise ValueError("Passcodes did not match. Try again.")
                if not self._vault:
                    raise RuntimeError("Secure vault is unavailable")
                self._vault.setup_pin(pin)
                self._vault.unlock(pin)
                self._pending_pin = ""
                self._pin_mode = "unlock"
                self._locked = False
            else:
                if not self._vault or not self._vault.unlock(pin):
                    raise ValueError("That passcode was not recognized")
                self._locked = False
            self._refresh_account_secret_flags()
            self._load_sensitive_configuration()
            self._next_owned_account_refresh_at = 0.0
            return self.state()
        if command == "reset_application":
            return self._reset_application(payload.get("confirmation"))
        if self._locked:
            raise PermissionError("Unlock Peaks to continue")
        if command == "lock":
            self._clear_sensitive_configuration()
            self._close_totp_setup_service()
            if self._vault:
                self._vault.lock()
            self._locked = True
            self._observed_live_match = None
            self._post_match_refresh = None
            self._current_match = {}
            self._game_detected = False
        elif command == "settings":
            self._update_settings(payload)
        elif command == "change_pin":
            self._change_security_code(payload)
        elif command == "add_account":
            account = self._add_authenticated_account()
            result = self.state()
            if not account.get("connected"):
                result["operationNotice"] = (
                    "Account recognized from the active Riot Client; a reusable session was "
                    "not available. Use Save reusable Riot session and complete Riot sign-in."
                )
            return result
        elif command == "remove_account":
            self._remove_account(
                self._internal_account_id(str(payload.get("accountId", "")))
            )
        elif command == "set_account_icon":
            if "icon" not in payload:
                raise ValueError("Choose a character icon or restore the automatic icon")
            self._set_account_icon(
                self._internal_account_id(str(payload.get("accountId", ""))), payload["icon"],
                **({"nickname": payload["nickname"]} if "nickname" in payload else {}),
            )
        elif command == "copy_totp":
            account_id = self._internal_account_id(str(payload.get("accountId", "")))
            totp_seed: str | None = self._secrets.get(account_id, {}).get("totp")
            if self._vault:
                entry = self._vault.get_entry(account_id)
                totp_seed = getattr(entry, "totp_secret", None)
            if not totp_seed:
                raise ValueError("No authenticator secret is stored for this account")
            from peaks.adapters.riot.totp import generate_totp

            code = generate_totp(totp_seed)
            # Electron intentionally owns clipboard access; this response is a one-time value.
            return {
                "code": code,
                "clearAfter": self.settings["clipboardClearSeconds"],
                "state": self.state(),
            }
        elif command == "api_key":
            key = str(payload.get("key", "")).strip()
            if not key:
                raise ValueError("Enter an API key")
            if self._vault:
                self._vault.put("configuration:riot_api_key", key)
            else:
                self._secrets.setdefault("configuration", {})["riot_api_key"] = key
            if self._vault:
                self._load_sensitive_configuration()
            else:
                self.settings["riotApiConfigured"] = True
        elif command in {"toggle_watchlist", "toggle_follow"}:
            raw_player = payload.get("player")
            if not isinstance(raw_player, Mapping):
                raise ValueError("Choose a player to watch")
            player = self._follow_player(raw_player)
            existing = next(
                (candidate for candidate in self.followed if self._same_player(candidate, player)),
                None,
            )
            if existing:
                remove_followed = getattr(self._repository, "remove_followed", None)
                if callable(remove_followed):
                    remove_followed(str(existing.get("id", "")))
                self.followed.remove(existing)
            else:
                add_followed = getattr(self._repository, "add_followed", None)
                if callable(add_followed):
                    add_followed(self._followed_domain(player))
                self.followed.append(player)
            result = self.state()
            result["operationNotice"] = (
                "Removed from Watchlist" if existing else "Added to Watchlist"
            )
            return result
        elif command == "import_session":
            force_sign_in = payload.get("forceSignIn", False)
            if not isinstance(force_sign_in, bool):
                raise ValueError("Riot sign-in refresh option is invalid")
            self._import_riot_session(
                self._internal_account_id(str(payload.get("accountId", ""))),
                force_sign_in=force_sign_in,
            )
        elif command in {"connect_riot_client", "connect_riot_qr_image"}:
            self._connect_riot_client(
                self._internal_account_id(str(payload.get("accountId", ""))),
                payload.get("qrCaptures"),
                payload.get("qrCaptureState"),
            )
            result = self.state()
            result["operationNotice"] = (
                "Pasted Riot QR connected to the selected identity"
                if command == "connect_riot_qr_image"
                else "Riot Client connected to the selected identity"
            )
            return result
        elif command == "enable_riot_mfa":
            return self._enable_riot_mfa(
                self._internal_account_id(str(payload.get("accountId", "")))
            )
        elif command == "prepare_totp_setup":
            internal_account_id = self._internal_account_id(
                str(payload.get("accountId", ""))
            )
            proposal = self._prepare_riot_mobile_totp(internal_account_id)
            proposal["accountId"] = (
                internal_account_id
                if self.demo
                else self._renderer_account_id(internal_account_id)
            )
            return proposal
        elif command == "confirm_totp_setup":
            return self._confirm_riot_mobile_totp(
                account_id=self._internal_account_id(
                    str(payload.get("accountId", ""))
                ),
                confirmation_id=str(payload.get("confirmationId", "")),
            )
        elif command == "cancel_totp_setup":
            self._cancel_riot_mobile_totp(str(payload.get("confirmationId", "")))
        elif command == "scan_qr":
            raise RuntimeError(
                "QR scanning is not available in this desktop shell yet; "
                "use Import current Riot session"
            )
        elif command == "refresh":
            priority_match_id = payload.get("priorityMatchId")
            if priority_match_id is not None and (
                not isinstance(priority_match_id, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", priority_match_id)
                or not payload.get("accountId")
            ):
                raise ValueError("Choose an owned account and a valid match to refresh")
            self._refresh_owned_accounts(
                account_id=self._internal_account_id(
                    str(payload.get("accountId", ""))
                ),
                priority_match_id=priority_match_id,
            )
        return self.state()

    def search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if getattr(self, "_locked", True):
            raise PermissionError("Unlock Peaks to continue")
        query = str(payload.get("query", ""))
        region = str(payload.get("region", ""))
        game = str(payload.get("game", "all"))
        self.history = [query] + [item for item in self.history if item.lower() != query.lower()]
        if self.demo:
            return [
                {**self._player(item), "game": game} for item in search_demo(query, region, game)
            ]
        search = getattr(self._get_riot_search_service(), "search_player", None)
        if not callable(search):
            return []
        return [
            self._player(item)
            for item in search(query, region=region, game=game)
            if isinstance(item, dict)
        ]


def _bridge_response_line(response: Mapping[str, Any]) -> str:
    """Serialize one IPC response using only code-page-safe ASCII bytes.

    JSON escapes round-trip Unicode exactly, while avoiding crashes when a
    Windows development shell starts with a legacy console encoding such as
    CP-1252. Electron decodes the JSON escape back to the original text.
    """

    return json.dumps(response, ensure_ascii=True)


def _configure_bridge_stdio() -> None:
    """Use UTF-8 for Node/Python pipes even in a frozen Windows runtime."""

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


_DIAGNOSTIC_BRIDGE_COMMANDS = frozenset(
    {
        "activity",
        "add_account",
        "api_key",
        "copy_totp",
        "cancel_totp_setup",
        "change_pin",
        "confirm_totp_setup",
        "connect_riot_client",
        "connect_riot_qr_image",
        "enable_riot_mfa",
        "import_session",
        "lock",
        "pin",
        "prepare_totp_setup",
        "refresh",
        "remove_account",
        "set_account_icon",
        "reset_application",
        "scan_qr",
        "search",
        "settings",
        "state",
        "toggle_follow",
        "toggle_watchlist",
    }
)
_COMMANDS_DURING_SESSION_IMPORT = frozenset({"activity", "copy_totp", "lock", "state"})


def _bridge_request_command(request: object) -> str:
    if not isinstance(request, Mapping):
        return ""
    return str(request.get("command", ""))


def _execute_bridge_request(bridge: Bridge, request: object) -> dict[str, Any]:
    command = _bridge_request_command(request)
    diagnostic_command = command if command in _DIAGNOSTIC_BRIDGE_COMMANDS else "unknown"
    request_id = request.get("id") if isinstance(request, Mapping) else None
    try:
        if not isinstance(request, Mapping):
            raise TypeError("Bridge requests must be JSON objects")
        LOGGER.info("bridge.command.start command=%s", diagnostic_command)
        payload = request.get("payload") or {}
        result = bridge.search(payload) if command == "search" else bridge.handle(command, payload)
        LOGGER.info("bridge.command.complete command=%s", diagnostic_command)
        return {"id": request_id, "result": result}
    except Exception as exc:
        LOGGER.warning(
            "bridge.command.failed command=%s error_type=%s",
            diagnostic_command,
            type(exc).__name__,
        )
        return {"id": request_id, "error": str(exc) or type(exc).__name__}


class _BridgeRequestDispatcher:
    """Keep TOTP copy responsive while headed Riot sign-in is in progress."""

    def __init__(
        self,
        bridge: Bridge,
        write_response: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._bridge = bridge
        self._write_response = write_response or self._write_stdout
        self._output_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._session_import_active = False
        self._workers: set[threading.Thread] = set()

    @staticmethod
    def _write_stdout(response: Mapping[str, Any]) -> None:
        print(_bridge_response_line(response), flush=True)

    def _write(self, response: Mapping[str, Any]) -> None:
        with self._output_lock:
            self._write_response(response)

    def write_protocol_error(self, error: Exception) -> None:
        self._write({"id": None, "error": str(error) or type(error).__name__})

    def _run_session_import(self, request: object) -> None:
        try:
            self._write(_execute_bridge_request(self._bridge, request))
        finally:
            worker = threading.current_thread()
            with self._state_lock:
                self._session_import_active = False
                self._bridge._session_import_in_progress = False
                self._workers.discard(worker)

    def dispatch(self, request: object) -> None:
        command = _bridge_request_command(request)
        request_id = request.get("id") if isinstance(request, Mapping) else None
        if command == "import_session":
            with self._state_lock:
                if self._session_import_active:
                    self._write(
                        {
                            "id": request_id,
                            "error": "A Riot session refresh is already in progress",
                        }
                    )
                    return
                self._session_import_active = True
                self._bridge._session_import_in_progress = True
                worker = threading.Thread(
                    target=self._run_session_import,
                    args=(request,),
                    daemon=True,
                    name="peaks-riot-session-import",
                )
                self._workers.add(worker)
            worker.start()
            return

        with self._state_lock:
            import_active = self._session_import_active
        if import_active and command not in _COMMANDS_DURING_SESSION_IMPORT:
            self._write(
                {
                    "id": request_id,
                    "error": "Finish or close the temporary Riot sign-in before this action",
                }
            )
            return
        self._write(_execute_bridge_request(self._bridge, request))

    def wait_for_workers(self, timeout: float = 1.0) -> None:
        with self._state_lock:
            workers = tuple(self._workers)
        for worker in workers:
            worker.join(timeout=timeout)


def main() -> int:
    _configure_bridge_stdio()
    bridge = Bridge()
    dispatcher = _BridgeRequestDispatcher(bridge)
    for line in sys.stdin:
        try:
            request = json.loads(line)
        except Exception as exc:
            LOGGER.warning(
                "bridge.command.failed command=unknown error_type=%s",
                type(exc).__name__,
            )
            dispatcher.write_protocol_error(exc)
            continue
        dispatcher.dispatch(request)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Pure Valorant local-client payload parsers and query adapter."""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote, urlsplit

from .client import (
    DEFAULT_MAX_RESPONSE_BYTES,
    RiotClientError,
    RiotClientHTTP,
    RiotClientUnavailable,
    _read_bounded_response,
    requests_module,
)
from .match_analytics import parse_round_analytics

if TYPE_CHECKING:
    from .valorant_enrichment import ValorantEnrichmentCache
    from .valorant_presence import ValorantParty

LOGGER = logging.getLogger(__name__)

MAX_LIVE_PLAYERS = 20
_SUBJECT_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")

VALORANT_RANK_NAMES: dict[int, str] = {
    0: "Unranked",
    1: "Unranked",
    2: "Unranked",
    3: "Iron 1",
    4: "Iron 2",
    5: "Iron 3",
    6: "Bronze 1",
    7: "Bronze 2",
    8: "Bronze 3",
    9: "Silver 1",
    10: "Silver 2",
    11: "Silver 3",
    12: "Gold 1",
    13: "Gold 2",
    14: "Gold 3",
    15: "Platinum 1",
    16: "Platinum 2",
    17: "Platinum 3",
    18: "Diamond 1",
    19: "Diamond 2",
    20: "Diamond 3",
    21: "Ascendant 1",
    22: "Ascendant 2",
    23: "Ascendant 3",
    24: "Immortal 1",
    25: "Immortal 2",
    26: "Immortal 3",
    27: "Radiant",
}
VALORANT_RANKS = VALORANT_RANK_NAMES


def rank_name(tier: int | str | None) -> str:
    try:
        value = int(tier or 0)
    except (TypeError, ValueError):
        value = 0
    return VALORANT_RANK_NAMES.get(value, "Unranked")


@dataclass(frozen=True, slots=True)
class ValorantPlayer:
    subject: str
    team_id: str | None = None
    character_id: str | None = None
    player_card_id: str | None = None
    incognito: bool = False
    account_level: int | None = None
    party_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValorantPregame:
    match_id: str
    map_id: str | None
    game_pod_id: str | None
    players: tuple[ValorantPlayer, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    queue_id: str | None = None
    mode_id: str | None = None
    free_for_all: bool = False


@dataclass(frozen=True, slots=True)
class ValorantCoregame:
    match_id: str
    map_id: str | None
    game_pod_id: str | None
    players: tuple[ValorantPlayer, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    queue_id: str | None = None
    mode_id: str | None = None
    free_for_all: bool = False


@dataclass(frozen=True, slots=True)
class ValorantRank:
    tier: int
    name: str
    rr: int | None = None
    peak_tier: int = 0
    peak_name: str = "Unranked"
    season_id: str | None = None
    peak_season: str | None = None
    current_available: bool = True


@dataclass(frozen=True, slots=True)
class ValorantMatchPlayer:
    """Sanitized participant details from one completed match.

    Raw subjects are used transiently while parsing and are never stored in
    this view. Completed match identities are independent of live incognito
    status; the renderer applies the user's global Streamer Mode separately.
    """

    riot_id: str | None = None
    team_id: str | None = None
    character_id: str | None = None
    competitive_tier: int = 0
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    combat_score: int | None = None
    rounds_played: int | None = None
    headshots: int | None = None
    bodyshots: int | None = None
    legshots: int | None = None
    damage: int | None = None
    self: bool = False
    hidden: bool = False
    weapon_usage: tuple[tuple[str, int], ...] | None = None
    round_kills: tuple[int, ...] | None = None
    rounds_analyzed: int | None = None
    account_level: int | None = None
    party_id: str | None = None
    current_rank: ValorantRank | None = None
    overall_stats: Mapping[str, Any] | None = None
    stats_loading: bool = False


@dataclass(frozen=True, slots=True)
class ValorantMatchTeam:
    name: str
    score: int | None = None
    won: bool | None = None
    players: tuple[ValorantMatchPlayer, ...] = ()


@dataclass(frozen=True, slots=True)
class ValorantMatchSummary:
    """Privacy-minimized match from the signed-in player's local history.

    The private match-history response contains substantially more account
    material than Peaks needs. Keep the stable summary plus bounded sanitized
    teams; never retain a raw response, access claims, or player subject.
    """

    match_id: str
    queue_id: str | None = None
    started_at_ms: int | None = None
    map_id: str | None = None
    result: str = "unknown"
    own_score: int | None = None
    opponent_score: int | None = None
    duration_seconds: int | None = None
    teams: tuple[ValorantMatchTeam, ...] = ()
    free_for_all: bool = False
    enrichment_pending: bool = False


@dataclass(frozen=True, slots=True)
class ValorantPlayerProfile:
    """Sanitized data for one explicitly resolved Riot identity."""

    rank: ValorantRank | None = None
    level: int | None = None
    matches: tuple[ValorantMatchSummary, ...] = ()


def _string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _mode_identifier(value: object, *, queue: bool = False) -> str | None:
    pattern = r"[A-Za-z0-9_-]{1,80}" if queue else r"[A-Za-z0-9_./-]{1,256}"
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def is_free_for_all(queue_id: str | None, mode_id: str | None = None) -> bool:
    """Only explicitly identified Deathmatch is FFA; team counts are not proof."""
    return (queue_id or "").casefold() == "deathmatch" or (mode_id or "").split(".", 1)[0].casefold() == "/game/gamemodes/deathmatch/deathmatch_gamemode"


def _live_mode_metadata(payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
    matchmaking = payload.get("MatchmakingData")
    queue_id = _mode_identifier(payload.get("QueueID"), queue=True)
    if queue_id is None and isinstance(matchmaking, Mapping):
        queue_id = _mode_identifier(matchmaking.get("QueueID"), queue=True)
    return queue_id, _mode_identifier(payload.get("ModeID")) or _mode_identifier(payload.get("Mode"))


def _bounded_subjects(values: object, *, limit: int = MAX_LIVE_PLAYERS) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    subjects: list[str] = []
    seen: set[str] = set()
    for value in values:
        subject = _string(value)
        if subject is None or not _SUBJECT_PATTERN.fullmatch(subject) or subject in seen:
            continue
        seen.add(subject)
        subjects.append(subject)
        if len(subjects) >= limit:
            break
    return tuple(subjects)


def parse_player_names(payload: object, requested_subjects: object) -> dict[str, str]:
    """Return bounded Riot IDs for requested authorized participants only.

    Live callers must omit subjects whose payload sets ``Incognito``. This
    parser independently drops unrequested response rows and never exposes a
    subject as a display fallback.
    """

    allowed = set(_bounded_subjects(requested_subjects))
    if not allowed or not isinstance(payload, list):
        return {}
    names: dict[str, str] = {}
    for value in payload:
        if not isinstance(value, Mapping):
            continue
        subject = _string(value.get("Subject")) or _string(value.get("subject"))
        if subject not in allowed:
            continue
        game_name = _string(value.get("GameName")) or _string(value.get("gameName"))
        tag_line = _string(value.get("TagLine")) or _string(value.get("tagLine"))
        display_name = _string(value.get("DisplayName")) or _string(
            value.get("displayName")
        )
        candidate: str | None = (
            f"{game_name}#{tag_line}" if game_name and tag_line else display_name
        )
        riot_id = _safe_riot_id(candidate)
        if riot_id is not None:
            names[subject] = riot_id
    return names


def _players(values: object) -> tuple[ValorantPlayer, ...]:
    if not isinstance(values, list):
        return ()
    result: list[ValorantPlayer] = []
    seen: set[str] = set()
    parties: dict[str, str] = {}
    for value in values[:MAX_LIVE_PLAYERS]:
        if not isinstance(value, Mapping):
            continue
        identity = value.get("PlayerIdentity")
        if not isinstance(identity, Mapping):
            identity = {}
        subject = _string(value.get("Subject")) or _string(identity.get("Subject"))
        if subject is None or subject in seen:
            continue
        seen.add(subject)
        result.append(
            ValorantPlayer(
                subject=subject,
                team_id=_string(value.get("TeamID")),
                character_id=_string(value.get("CharacterID")),
                player_card_id=_string(identity.get("PlayerCardID")),
                incognito=bool(identity.get("Incognito", value.get("Incognito", False))),
                account_level=None if identity.get("HideAccountLevel") else _bounded_level(identity.get("AccountLevel")),
                party_id=_party_group(value.get("PartyID"), parties),
            )
        )
    return tuple(result)


def parse_pregame(payload: Mapping[str, Any]) -> ValorantPregame | None:
    """Parse ``/pregame/v1/matches/{id}`` data into a stable view model."""

    if not isinstance(payload, Mapping):
        return None
    match_id = _string(payload.get("ID")) or _string(payload.get("MatchID"))
    if match_id is None:
        return None
    teams = payload.get("Teams")
    raw_teams = list(teams[:MAX_LIVE_PLAYERS]) if isinstance(teams, list) else []
    raw_teams.extend((payload.get("AllyTeam"), payload.get("EnemyTeam")))
    all_players: list[object] = []
    for team in raw_teams:
        if isinstance(team, Mapping) and isinstance(team.get("Players"), list):
            all_players.extend(
                {**player, "TeamID": player.get("TeamID") or team.get("TeamID")}
                for player in team["Players"][:MAX_LIVE_PLAYERS]
                if isinstance(player, Mapping)
            )
    players = _players(all_players or payload.get("Players"))
    queue_id, mode_id = _live_mode_metadata(payload)
    return ValorantPregame(
        match_id,
        _string(payload.get("MapID")),
        _string(payload.get("GamePodID")),
        players,
        payload,
        queue_id,
        mode_id,
        is_free_for_all(queue_id, mode_id),
    )


def parse_coregame(payload: Mapping[str, Any]) -> ValorantCoregame | None:
    """Parse ``/core-game/v1/matches/{id}`` data."""

    if not isinstance(payload, Mapping):
        return None
    match_id = _string(payload.get("ID")) or _string(payload.get("MatchID"))
    if match_id is None:
        return None
    queue_id, mode_id = _live_mode_metadata(payload)
    return ValorantCoregame(
        match_id,
        _string(payload.get("MapID")),
        _string(payload.get("GamePodID")),
        _players(payload.get("Players")),
        payload,
        queue_id,
        mode_id,
        is_free_for_all(queue_id, mode_id),
    )


def _to_int(value: object) -> int | None:
    try:
        return int(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bounded_level(value: object) -> int | None:
    level = _to_int(value)
    return level if level is not None and 0 <= level <= 100_000 else None


def _party_group(value: object, groups: dict[str, str]) -> str | None:
    if not isinstance(value, str) or not _SUBJECT_PATTERN.fullmatch(value):
        return None
    return groups.setdefault(value, f"party-{len(groups) + 1}")


def _season_info(payload: Mapping[str, Any], season_id: str | None) -> Mapping[str, Any]:
    queue_skills = payload.get("QueueSkills")
    competitive = queue_skills.get("competitive") if isinstance(queue_skills, Mapping) else None
    seasons = (
        competitive.get("SeasonalInfoBySeasonID") if isinstance(competitive, Mapping) else None
    )
    if not isinstance(seasons, Mapping):
        return {}
    if season_id is not None:
        value = seasons.get(season_id)
        return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}
    candidates = [value for value in seasons.values() if isinstance(value, Mapping)]
    # JSON object order is not a chronology. With more than one act in the
    # response, callers must resolve the active act from competitive updates
    # instead of projecting whichever map entry happened to be first.
    if len(candidates) == 1:
        return cast(Mapping[str, Any], candidates[0])
    return {}


def parse_rank(payload: Mapping[str, Any], season_id: str | None = None, *, season_labels: Mapping[str, str] | None = None) -> ValorantRank:
    """Parse Valorant MMR payloads, including peak rank history."""

    if not isinstance(payload, Mapping):
        return ValorantRank(0, "Unranked")
    if season_id is None:
        update = payload.get("LatestCompetitiveUpdate")
        if isinstance(update, Mapping):
            season_id = _bounded_season_id(update.get("SeasonID"))
    season = _season_info(payload, season_id)
    if not season and any(
        key in payload for key in ("CompetitiveTier", "RankedRating", "rankedRating")
    ):
        season = payload
    tier = _historical_rank_tier(season.get("CompetitiveTier"), (season_labels or {}).get(season_id or "")) or 0
    rr = _to_int(season.get("RankedRating", season.get("rankedRating")))
    peak_tier = tier
    peak_season = season_id
    # Current and prior season entries use the same shape.  Ignore malformed
    # records and never let an unknown tier become a misleading rank label.
    queue_skills = payload.get("QueueSkills")
    competitive = queue_skills.get("competitive") if isinstance(queue_skills, Mapping) else None
    seasons = competitive.get("SeasonalInfoBySeasonID") if isinstance(competitive, Mapping) else {}
    if isinstance(seasons, Mapping):
        for key, value in seasons.items():
            if not isinstance(value, Mapping):
                continue
            label = (season_labels or {}).get(str(key))
            candidate = _historical_rank_tier(value.get("CompetitiveTier"), label) or 0
            wins = value.get("WinsByTier")
            if isinstance(wins, Mapping):
                for win_tier, count in wins.items():
                    known = _historical_rank_tier(win_tier, label)
                    if known is not None and (_to_int(count) or 0) > 0:
                        candidate = max(candidate, known)
            if candidate > peak_tier or (candidate == peak_tier and peak_season is None):
                peak_tier, peak_season = candidate, _bounded_season_id(key)
    return ValorantRank(tier, rank_name(tier), rr, peak_tier, rank_name(peak_tier), peak_season)


def parse_account_level(
    payload: object,
    *,
    expected_subject: str | None = None,
) -> int | None:
    """Return a bounded own-account level without retaining XP details.

    The private account-XP response may include the account subject.  When it
    does, reject a mismatched subject even though callers already bind the
    request path to the authenticated entitlement identity.
    """

    if not isinstance(payload, Mapping):
        return None
    subject = _string(payload.get("Subject")) or _string(payload.get("subject"))
    if expected_subject is not None and subject is not None and subject != expected_subject:
        return None
    progress = payload.get("Progress")
    if not isinstance(progress, Mapping):
        progress = payload.get("progress")
    if not isinstance(progress, Mapping):
        return None
    level = _to_int(progress.get("Level", progress.get("level")))
    return level if level is not None and 0 <= level <= 100_000 else None


def _known_rank_tier(value: object) -> int | None:
    tier = _to_int(value)
    return tier if tier in VALORANT_RANK_NAMES else None


def _historical_rank_tier(value: object, season_label: str | None) -> int | None:
    tier = _known_rank_tier(value)
    # Ascendant was inserted in E5:A1. Normalize every old candidate before
    # comparison so an old Radiant(24) beats a modern Immortal 3(26).
    if tier is not None and season_label and re.fullmatch(r"E[1-4]:A[1-3]", season_label) and tier > 20:
        return tier + 3 if tier <= 24 else None
    return tier


def _bounded_season_id(value: object) -> str | None:
    season = _string(value)
    if season is None or len(season) > 128:
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in season):
        return None
    return season


def latest_competitive_update_season(
    payload: Mapping[str, Any], *, limit: int = 20
) -> str | None:
    """Return the newest bounded season identifier from own-account updates."""

    bounded_limit = max(1, min(int(limit), 20))
    matches = payload.get("Matches") if isinstance(payload, Mapping) else None
    if not isinstance(matches, list):
        return None
    for value in matches[:bounded_limit]:
        if not isinstance(value, Mapping):
            continue
        if _known_rank_tier(value.get("TierAfterUpdate")) is None:
            continue
        season = _bounded_season_id(value.get("SeasonID"))
        if season is not None:
            return season
    return None


def parse_competitive_updates_rank(
    payload: Mapping[str, Any],
    season_id: str | None = None,
    *,
    limit: int = 20,
) -> ValorantRank | None:
    """Derive current rank from a bounded own-account update page.

    Riot returns ``Matches`` newest-first. Only rank, rating, and season
    fields are inspected; match identifiers, subjects, and raw records are
    never retained. This parser is a fallback for transient primary MMR
    failures, not a public-player lookup.
    """

    bounded_limit = max(1, min(int(limit), 20))
    matches = payload.get("Matches") if isinstance(payload, Mapping) else None
    if not isinstance(matches, list):
        return None

    records: list[tuple[int, int | None, int | None, str | None]] = []
    for value in matches[:bounded_limit]:
        if not isinstance(value, Mapping):
            continue
        after_tier = _known_rank_tier(value.get("TierAfterUpdate"))
        if after_tier is None:
            continue
        record_season = _bounded_season_id(value.get("SeasonID"))
        rating = _to_int(value.get("RankedRatingAfterUpdate"))
        if rating is not None and not 0 <= rating <= 1_000_000:
            rating = None
        before_tier = _known_rank_tier(value.get("TierBeforeUpdate"))
        records.append((after_tier, rating, before_tier, record_season))

    selected = next(
        (
            record
            for record in records
            if season_id is None or record[3] == season_id
        ),
        None,
    )
    if selected is None:
        return None
    tier, rating, _before_tier, current_season = selected
    peak_tier = tier
    peak_season = current_season
    for after_tier, _rating, before_tier, record_season in records:
        for candidate in (after_tier, before_tier):
            if candidate is not None and candidate > peak_tier:
                peak_tier = candidate
                peak_season = record_season
    return ValorantRank(
        tier,
        rank_name(tier),
        rating,
        peak_tier,
        rank_name(peak_tier),
        peak_season or current_season,
    )


def parse_match_history(
    payload: Mapping[str, Any], *, limit: int = 20
) -> tuple[ValorantMatchSummary, ...]:
    """Parse a bounded own-account VALORANT match-history page.

    Unknown or malformed records are dropped.  In particular, raw payloads
    and player identifiers are never retained in the returned value.
    """

    bounded_limit = max(1, min(int(limit), 20))
    history = payload.get("History") if isinstance(payload, Mapping) else None
    if not isinstance(history, list):
        return ()
    rows: list[ValorantMatchSummary] = []
    for value in history[:bounded_limit]:
        if not isinstance(value, Mapping):
            continue
        match_id = _string(value.get("MatchID"))
        if (
            match_id is None
            or len(match_id) > 128
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in match_id)
        ):
            continue
        queue_id = _string(value.get("QueueID"))
        if queue_id is not None and (
            len(queue_id) > 80 or any(ord(char) < 0x20 or ord(char) == 0x7F for char in queue_id)
        ):
            queue_id = None
        started_at_ms = _to_int(value.get("GameStartTime"))
        if started_at_ms is not None and started_at_ms <= 0:
            started_at_ms = None
        rows.append(ValorantMatchSummary(match_id, queue_id, started_at_ms))
    return tuple(rows)


def _mapping_text(value: object, *keys: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    for key in keys:
        text = _string(value.get(key))
        if text is not None:
            return text
    return None


def _mapping_int(value: object, *keys: str) -> int | None:
    if not isinstance(value, Mapping):
        return None
    for key in keys:
        if key in value:
            parsed = _to_int(value.get(key))
            if parsed is not None:
                return parsed
    return None


def _mapping_bool(value: object, *keys: str) -> bool | None:
    if not isinstance(value, Mapping):
        return None
    for key in keys:
        if key not in value:
            continue
        raw = value.get(key)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, int) and raw in {0, 1}:
            return bool(raw)
        if isinstance(raw, str) and raw.casefold() in {"true", "false"}:
            return raw.casefold() == "true"
    return None


def _safe_riot_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > 256
        or any(ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in candidate)
    ):
        return None
    # DisplayName may be an agent name or a privacy placeholder. Only a full
    # Riot ID is enough to skip the authenticated participant name lookup.
    game_name, separator, tag_line = candidate.partition("#")
    if not separator or not game_name.strip() or not tag_line.strip() or "#" in tag_line:
        return None
    return candidate


def _match_player_direct_riot_id(player: Mapping[str, Any]) -> str | None:
    game_name = _mapping_text(player, "gameName", "GameName")
    tag_line = _mapping_text(player, "tagLine", "TagLine")
    if game_name and tag_line:
        return _safe_riot_id(f"{game_name}#{tag_line}")
    return _safe_riot_id(_mapping_text(player, "displayName", "DisplayName"))


def _match_detail_name_subjects(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Resolve identities missing from a completed match, including incognito."""

    info = payload.get("matchInfo", payload.get("MatchInfo"))
    if isinstance(info, Mapping) and _mapping_bool(info, "isCompleted", "IsCompleted") is False:
        return ()
    players = payload.get("players")
    if not isinstance(players, list):
        players = payload.get("Players")
    if not isinstance(players, list):
        return ()
    subjects: list[str] = []
    for player in players[:MAX_LIVE_PLAYERS]:
        if not isinstance(player, Mapping):
            continue
        if _match_player_direct_riot_id(player):
            continue
        subject = _mapping_text(player, "subject", "Subject", "puuid", "Puuid")
        if subject:
            subjects.append(subject)
    return _bounded_subjects(subjects)


def _match_player_damage(player: Mapping[str, Any]) -> int | None:
    rounds = player.get("roundDamage")
    if not isinstance(rounds, list):
        rounds = player.get("RoundDamage")
    if not isinstance(rounds, list):
        return None
    values = [
        damage
        for item in rounds
        if (damage := _mapping_int(item, "damage", "Damage")) is not None
        and 0 <= damage <= 1_000_000
    ]
    return sum(values) if values else None


def _match_players(
    payload: Mapping[str, Any],
    *,
    puuid: str,
    names: Mapping[str, str],
    contexts: list[tuple[str, ValorantMatchPlayer]] | None = None,
) -> tuple[ValorantMatchPlayer, ...]:
    values = payload.get("players")
    if not isinstance(values, list):
        values = payload.get("Players")
    if not isinstance(values, list):
        return ()
    round_analytics = parse_round_analytics(payload)
    result: list[ValorantMatchPlayer] = []
    parties: dict[str, str] = {}
    for player in values[:MAX_LIVE_PLAYERS]:
        if not isinstance(player, Mapping):
            continue
        identity = player.get("playerIdentity")
        if not isinstance(identity, Mapping):
            identity = player.get("PlayerIdentity")
        if not isinstance(identity, Mapping):
            identity = {}
        subject = _mapping_text(player, "subject", "Subject", "puuid", "Puuid")
        direct_riot_id = _match_player_direct_riot_id(player)
        resolved_riot_id = _safe_riot_id(names.get(subject, "")) if subject else None
        riot_id = direct_riot_id or resolved_riot_id
        stats = player.get("stats")
        if not isinstance(stats, Mapping):
            stats = player.get("Stats")
        if not isinstance(stats, Mapping):
            stats = {}
        tier = _known_rank_tier(
            player.get("competitiveTier", player.get("CompetitiveTier"))
        )
        rounds_played = _mapping_int(stats, "roundsPlayed", "RoundsPlayed")
        total_score = _mapping_int(stats, "score", "Score")
        kills = _mapping_int(stats, "kills", "Kills")
        analytics = round_analytics.get(subject or "")
        if analytics is not None and rounds_played is not None:
            accepted_round_counts = {analytics.rounds_analyzed}
            if analytics.surrendered_rounds:
                # Riot can count the started surrender round in roundsPlayed,
                # while adding several event-empty awarded score rows. Keep
                # its official ACS/ADR denominator, not the awarded total.
                accepted_round_counts.add(analytics.rounds_analyzed + 1)
            if rounds_played not in accepted_round_counts:
                analytics = None
        headshots = _mapping_int(stats, "headshots", "Headshots")
        bodyshots = _mapping_int(stats, "bodyshots", "Bodyshots")
        legshots = _mapping_int(stats, "legshots", "Legshots")
        shot_analytics = analytics
        if analytics is not None and any(
            reported is not None and observed is not None and reported != observed
            for reported, observed in (
                (headshots, analytics.headshots),
                (bodyshots, analytics.bodyshots),
                (legshots, analytics.legshots),
            )
        ):
            # Never manufacture a full percentage split from disagreeing
            # top-level counts and a different round-event window.
            shot_analytics = None
        round_kills = getattr(analytics, "round_kills", None)
        weapon_usage = getattr(analytics, "weapon_usage", None)
        if round_kills is not None and kills is not None and sum(round_kills) != kills:
            round_kills = None
            weapon_usage = None
        damage = _mapping_int(stats, "damage", "Damage")
        if damage is None:
            damage = _match_player_damage(player)
        result.append(
            ValorantMatchPlayer(
                riot_id=riot_id,
                team_id=_mapping_text(player, "teamId", "TeamID", "teamID"),
                character_id=_mapping_text(
                    player, "characterId", "CharacterID", "characterID"
                ),
                competitive_tier=tier or 0,
                kills=kills,
                deaths=_mapping_int(stats, "deaths", "Deaths"),
                assists=_mapping_int(stats, "assists", "Assists"),
                combat_score=total_score,
                rounds_played=rounds_played,
                headshots=headshots if headshots is not None else getattr(shot_analytics, "headshots", None),
                bodyshots=bodyshots if bodyshots is not None else getattr(shot_analytics, "bodyshots", None),
                legshots=legshots if legshots is not None else getattr(shot_analytics, "legshots", None),
                damage=damage if damage is not None else getattr(analytics, "damage", None),
                self=subject == puuid,
                hidden=False,
                weapon_usage=weapon_usage,
                round_kills=round_kills,
                rounds_analyzed=analytics.rounds_analyzed if analytics is not None and analytics.surrendered_rounds else None,
                account_level=_bounded_level(player.get("accountLevel", player.get("AccountLevel"))),
                party_id=_party_group(player.get("partyId", player.get("PartyID")), parties),
            )
        )
        if contexts is not None and subject and _SUBJECT_PATTERN.fullmatch(subject):
            contexts.append((subject, result[-1]))
    return tuple(result)


def parse_match_details(
    payload: Mapping[str, Any],
    *,
    puuid: str,
    fallback: ValorantMatchSummary,
    names: Mapping[str, str] | None = None,
    contexts: list[tuple[str, ValorantMatchPlayer]] | None = None,
) -> ValorantMatchSummary:
    """Enrich one own-account history row with sanitized team statistics."""

    if not isinstance(payload, Mapping):
        return fallback
    info = payload.get("matchInfo")
    if not isinstance(info, Mapping):
        info = payload.get("MatchInfo")
    if not isinstance(info, Mapping):
        info = {}
    returned_id = _mapping_text(info, "matchId", "MatchID", "matchID")
    if _mapping_bool(info, "isCompleted", "IsCompleted") is False:
        return fallback
    if returned_id is not None and returned_id != fallback.match_id:
        return fallback
    queue_id = (
        _mapping_text(info, "queueID", "queueId", "QueueID") or fallback.queue_id
    )
    free_for_all = is_free_for_all(queue_id, _mapping_text(info, "gameMode", "GameMode", "modeId", "ModeID"))

    own_team_id: str | None = None
    players = payload.get("players")
    if not isinstance(players, list):
        players = payload.get("Players")
    if isinstance(players, list):
        for player in players:
            subject = _mapping_text(player, "subject", "Subject")
            if subject == puuid:
                own_team_id = _mapping_text(player, "teamId", "TeamID", "teamID")
                break

    own_team: Mapping[str, Any] | None = None
    opponents: list[Mapping[str, Any]] = []
    teams = payload.get("teams")
    if not isinstance(teams, list):
        teams = payload.get("Teams")
    if isinstance(teams, list):
        for team in teams:
            if not isinstance(team, Mapping):
                continue
            team_id = _mapping_text(team, "teamId", "TeamID", "teamID")
            if own_team_id is not None and team_id == own_team_id:
                own_team = team
            else:
                opponents.append(team)

    sanitized_players = _match_players(payload, puuid=puuid, names=names or {}, contexts=contexts)
    if own_team_id is None:
        own_team_id = next(
            (player.team_id for player in sanitized_players if player.self),
            None,
        )
    team_views: list[ValorantMatchTeam] = []
    if free_for_all:
        # Riot may encode each Deathmatch participant with a unique team ID.
        # Those IDs are not meaningful teams and caused the bridge's bounded
        # team projection to drop most of the lobby. Preserve one complete,
        # ordered FFA roster instead.
        team_views.append(
            ValorantMatchTeam(name="Free for all", players=sanitized_players)
        )
    else:
        seen_team_ids: set[str | None] = set()
        raw_teams = teams if isinstance(teams, list) else []
        for index, raw_team in enumerate(raw_teams[:MAX_LIVE_PLAYERS], start=1):
            if not isinstance(raw_team, Mapping):
                continue
            team_id = _mapping_text(raw_team, "teamId", "TeamID", "teamID")
            if team_id in seen_team_ids:
                continue
            seen_team_ids.add(team_id)
            members = tuple(player for player in sanitized_players if player.team_id == team_id)
            label = (
                "Your team"
                if own_team_id is not None and team_id == own_team_id
                else "Opponents"
                if len(raw_teams) == 2
                else f"Team {index}"
            )
            team_views.append(
                ValorantMatchTeam(
                    name=label,
                    score=_mapping_int(
                        raw_team, "roundsWon", "RoundsWon", "numPoints", "NumPoints"
                    ),
                    won=_mapping_bool(raw_team, "won", "Won"),
                    players=members,
                )
            )
        # Missing team summaries do not erase grouping already present on
        # participants (including new multi-team modes with unknown queue IDs).
        remaining_groups: dict[str | None, list[ValorantMatchPlayer]] = {}
        for player in sanitized_players:
            if player.team_id not in seen_team_ids:
                remaining_groups.setdefault(player.team_id, []).append(player)
        for team_id, remaining_members in remaining_groups.items():
            label = "Your team" if team_id is not None and team_id == own_team_id else "Players" if team_id is None else f"Team {len(team_views) + 1}"
            team_views.append(ValorantMatchTeam(name=label, players=tuple(remaining_members)))

    own_score = _mapping_int(own_team, "roundsWon", "RoundsWon", "numPoints", "NumPoints")
    opponent_scores = [
        score
        for team in opponents
        if (score := _mapping_int(
            team, "roundsWon", "RoundsWon", "numPoints", "NumPoints"
        ))
        is not None
    ]
    opponent_score = max(opponent_scores) if opponent_scores else None
    won = own_team.get("won", own_team.get("Won")) if own_team is not None else None
    if won is True:
        result = "win"
    elif won is False:
        result = "loss"
    elif own_score is not None and opponent_score is not None and own_score == opponent_score:
        result = "draw"
    else:
        result = fallback.result

    duration_ms = _mapping_int(info, "gameLengthMillis", "GameLengthMillis")
    duration_seconds = (
        duration_ms // 1_000 if duration_ms is not None and duration_ms >= 0 else None
    )
    started_at_ms = _mapping_int(info, "gameStartMillis", "GameStartTime")
    if started_at_ms is not None and started_at_ms <= 0:
        started_at_ms = None

    return ValorantMatchSummary(
        match_id=fallback.match_id,
        queue_id=queue_id,
        started_at_ms=started_at_ms or fallback.started_at_ms,
        map_id=_mapping_text(info, "mapId", "MapID") or fallback.map_id,
        result=result,
        own_score=own_score,
        opponent_score=opponent_score,
        duration_seconds=duration_seconds,
        teams=tuple(team_views),
        free_for_all=free_for_all,
    )


def parse_pregame_match(payload: Mapping[str, Any]) -> ValorantPregame | None:
    return parse_pregame(payload)


def parse_coregame_match(payload: Mapping[str, Any]) -> ValorantCoregame | None:
    return parse_coregame(payload)


parse_valorant_pregame = parse_pregame
parse_valorant_pregame_payload = parse_pregame
parse_valorant_coregame = parse_coregame
parse_valorant_coregame_payload = parse_coregame
parse_valorant_rank = parse_rank
parse_valorant_competitive_updates_rank = parse_competitive_updates_rank
parse_valorant_match_history = parse_match_history
parse_valorant_match_details = parse_match_details


class ValorantRemoteHTTP:
    """TLS-verified PD/GLZ transport for Valorant's private service APIs.

    The local lockfile endpoint only provides entitlements.  Pregame,
    coregame, and MMR data are served by the region-specific GLZ/PD hosts, so
    callers must provide the short-lived access and entitlements headers
    obtained from the local entitlements endpoint.  Header values are never
    logged or placed in exception messages.
    """

    def __init__(
        self,
        *,
        pd_url: str,
        glz_url: str,
        headers: Mapping[str, str],
        session: Any | None = None,
        timeout: float = 10.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if not 0 < max_response_bytes <= 64 * 1024 * 1024:
            raise ValueError("max_response_bytes must be between 1 and 67108864")
        self.pd_url = self._validate_base_url(pd_url)
        self.glz_url = self._validate_base_url(glz_url)
        self.headers = dict(headers)
        session_value: Any = session
        if session_value is None and requests_module is not None:
            session_value = requests_module.Session()
        if session_value is None:
            raise RiotClientError("requests is required for Valorant service access")
        self._session = session_value
        # These are short-lived authenticated service tokens.  Do not let
        # ambient proxy environment variables redirect them through a proxy.
        if hasattr(self._session, "trust_env"):
            self._session.trust_env = False
        self.timeout = timeout
        self._max_response_bytes = int(max_response_bytes)

    def close(self) -> None:
        """Close the underlying HTTP session."""

        self.headers.clear()
        close = getattr(self._session, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> ValorantRemoteHTTP:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def _validate_base_url(url: str) -> str:
        if not isinstance(url, str):
            raise ValueError("Valorant service URL must be text")
        parsed = urlsplit(url.rstrip("/"))
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError("Valorant service URL must use HTTPS")
        hostname = parsed.hostname
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
        if is_loopback or hostname.casefold() == "localhost":
            raise ValueError("Valorant service URL must not be loopback")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Valorant service URL contains unsupported parts")
        return url.rstrip("/")

    def request(
        self,
        service: str,
        endpoint: str,
        method: str = "GET",
        *,
        json_body: object | None = None,
    ) -> Any:
        if service not in {"pd", "glz", "shared"}:
            raise ValueError("service must be pd, glz or shared")
        if (
            not isinstance(endpoint, str)
            or not endpoint.startswith("/")
            or endpoint.startswith("//")
        ):
            raise ValueError("endpoint must be a local service path")
        method_name = method.upper()
        if method_name not in {"GET", "PUT"}:
            raise ValueError("Valorant remote method must be GET or PUT")
        if method_name == "GET" and json_body is not None:
            raise ValueError("GET requests cannot include a JSON body")
        base_url = self.pd_url if service == "pd" else self.glz_url
        if service == "shared":
            # Never forward session credentials to an arbitrary content host.
            shard = re.fullmatch(r"https://pd\.(na|eu|ap|kr|pbe)\.a\.pvp\.net", self.pd_url)
            if shard is None or endpoint != "/content-service/v3/content" or method_name != "GET":
                raise RiotClientUnavailable("Valorant content service is unavailable")
            base_url = f"https://shared.{shard.group(1)}.a.pvp.net"
        url = f"{base_url}{endpoint}"
        LOGGER.debug("valorant.remote.request.start service=%s", service)
        try:
            # Public service traffic must retain certificate verification.  The
            # only verify=False path is RiotClientHTTP's literal loopback URL.
            request_kwargs: dict[str, object] = {
                "headers": dict(self.headers),
                "timeout": self.timeout,
                "stream": True,
                "allow_redirects": False,
                "verify": True,
            }
            if json_body is not None:
                request_kwargs["json"] = json_body
            response = self._session.request(method_name, url, **request_kwargs)
            _read_bounded_response(response, max_bytes=self._max_response_bytes)
        except RiotClientError:
            LOGGER.info(
                "valorant.remote.request.unavailable service=%s error_type=RiotClientError", service
            )
            raise
        except Exception as exc:
            request_exception = getattr(requests_module, "RequestException", Exception)
            if isinstance(exc, request_exception):
                LOGGER.info(
                    "valorant.remote.request.unavailable service=%s error_type=%s",
                    service,
                    type(exc).__name__,
                )
                raise RiotClientUnavailable("Valorant service is unavailable") from exc
            raise
        LOGGER.debug(
            "valorant.remote.request.complete service=%s status=%s",
            service,
            getattr(response, "status_code", "unknown"),
        )
        return response

    def get_json(self, service: str, endpoint: str) -> Any:
        response = self.request(service, endpoint)
        return self._response_json(service, response)

    def put_json(self, service: str, endpoint: str, payload: object) -> Any:
        response = self.request(service, endpoint, "PUT", json_body=payload)
        return self._response_json(service, response)

    @staticmethod
    def _response_json(service: str, response: Any) -> Any:
        try:
            response.raise_for_status()
            content = getattr(response, "content", None)
            if isinstance(content, (bytes, bytearray, memoryview)):
                return json.loads(bytes(content).decode("utf-8"))
            return response.json()
        except RiotClientError:
            raise
        except Exception as exc:
            # Avoid propagating response text because it can contain claims or
            # other account material.  Keep the status for actionable UI state.
            status = getattr(response, "status_code", "unknown")
            detail_code = None
            if status == 404:
                try:
                    content = getattr(response, "content", None)
                    payload = (
                        json.loads(bytes(content).decode("utf-8"))
                        if isinstance(content, (bytes, bytearray, memoryview))
                        else response.json()
                    )
                    if isinstance(payload, Mapping) and payload.get("errorCode") == "RESOURCE_NOT_FOUND":
                        detail_code = "RESOURCE_NOT_FOUND"
                except Exception:
                    pass
            raise RiotClientError(
                f"Valorant {service} endpoint returned HTTP {status}",
                status_code=status if isinstance(status, int) else None,
                detail_code=detail_code,
            ) from exc


class ValorantClient:
    """Query pregame/coregame/rank state through the local Riot client."""

    def __init__(self, http: RiotClientHTTP | ValorantRemoteHTTP, puuid: str) -> None:
        if not puuid:
            raise ValueError("puuid is required")
        self.http = http
        self.puuid = puuid
        self.activity_available = False
        self._missing_match_endpoints: set[str] = set()
        self.enrichment: ValorantEnrichmentCache | None = None
        self.priority_match_id: str | None = None

    def _get_json(self, service: str, endpoint: str) -> Any:
        if isinstance(self.http, ValorantRemoteHTTP):
            return self.http.get_json(service, endpoint)
        return self.http.get_json(endpoint)

    def _put_json(self, service: str, endpoint: str, payload: object) -> Any:
        put_json = getattr(self.http, "put_json", None)
        if not callable(put_json):
            raise RiotClientUnavailable("Valorant name service is unavailable")
        return put_json(service, endpoint, payload)

    def _match_id(self, endpoint: str) -> str | None:
        try:
            payload = self._get_json("glz", f"{endpoint}/{self.puuid}")
        except (RiotClientError, RiotClientUnavailable) as exc:
            if exc.status_code == 404 and exc.detail_code == "RESOURCE_NOT_FOUND":
                self._missing_match_endpoints.add(endpoint)
            return None
        if not isinstance(payload, Mapping):
            return None
        if payload.get("errorCode") == "RESOURCE_NOT_FOUND":
            self._missing_match_endpoints.add(endpoint)
            return None
        match_id = _string(payload.get("MatchID"))
        if match_id is None or len(match_id) > 128 or any(
            ord(character) < 0x20 or ord(character) == 0x7F for character in match_id
        ):
            return None
        return match_id

    def pregame(self) -> ValorantPregame | None:
        match_id = self._match_id("/pregame/v1/players")
        if not match_id:
            return None
        try:
            payload = self._get_json("glz", f"/pregame/v1/matches/{match_id}")
        except (RiotClientError, RiotClientUnavailable):
            return None
        match = parse_pregame(payload)
        return match if match is not None and match.match_id == match_id else None

    def coregame(self) -> ValorantCoregame | None:
        match_id = self._match_id("/core-game/v1/players")
        if not match_id:
            return None
        try:
            payload = self._get_json("glz", f"/core-game/v1/matches/{match_id}")
        except (RiotClientError, RiotClientUnavailable):
            return None
        match = parse_coregame(payload)
        return match if match is not None and match.match_id == match_id else None

    def rank(self, season_id: str | None = None) -> ValorantRank:
        """Return the current rank, using ``Unranked`` for unavailable data.

        This compatibility method intentionally keeps its historical return
        type.  Callers that need to distinguish a genuine unranked account
        from an unavailable local service should use
        :meth:`rank_optional` instead.
        """

        return self.rank_optional(season_id) or ValorantRank(0, "Unranked", season_id=season_id)

    def account_level_optional(self) -> int | None:
        """Return only this authenticated client's bounded account level."""

        subject = quote(self.puuid, safe="")
        try:
            payload = self._get_json("pd", f"/account-xp/v1/players/{subject}")
        except (RiotClientError, RiotClientUnavailable) as exc:
            LOGGER.info(
                "valorant.account_level.unavailable error_type=%s",
                type(exc).__name__,
            )
            return None
        level = parse_account_level(payload, expected_subject=self.puuid)
        if level is None:
            LOGGER.info("valorant.account_level.unavailable reason=invalid_payload")
            return None
        LOGGER.debug("valorant.account_level.complete")
        return level

    def player_profile(self, subject: str, *, limit: int = 10) -> ValorantPlayerProfile | None:
        """Read a resolved identity without changing the authenticated owner.

        Rank cache entries are subject-specific. Completed-match cache entries
        contain the owner's perspective, so searched history is parsed locally
        and never read from or written into that cache. Only match IDs returned
        by the requested subject's bounded history page authorize detail reads.
        """

        if not isinstance(subject, str) or not _SUBJECT_PATTERN.fullmatch(subject):
            return None
        from .valorant_enrichment import RequestBudget, ValorantEnrichmentCache

        bounded_limit = max(1, min(int(limit), 10))
        cache = self.enrichment or ValorantEnrichmentCache()
        budget = RequestBudget(remaining=24, clock=cache.clock, seconds=12)
        rank: ValorantRank | None = None
        try:
            catalog = cache.catalog(self, budget)
            rank = cache.profile(self, subject, catalog, budget)
        except RiotClientError:
            pass
        level = (
            self.account_level_optional()
            if subject == self.puuid and budget.take()
            else None
        )
        history: tuple[ValorantMatchSummary, ...] = ()
        if budget.take():
            try:
                payload = self._get_json(
                    "pd",
                    f"/match-history/v1/history/{quote(subject, safe='')}"
                    f"?startIndex=0&endIndex={bounded_limit}",
                )
            except RiotClientError:
                pass
            else:
                if isinstance(payload, Mapping):
                    parsed = parse_match_history(payload, limit=bounded_limit)
                    history = tuple({
                        match.match_id: match for match in parsed
                        if _SUBJECT_PATTERN.fullmatch(match.match_id)
                    }.values())

        details: dict[str, Mapping[str, Any]] = {}
        name_subjects: list[str] = []
        for match in history:
            if not budget.take():
                break
            try:
                detail = self._get_json(
                    "pd", f"/match-details/v1/matches/{quote(match.match_id, safe='')}"
                )
            except RiotClientError:
                continue
            if not isinstance(detail, Mapping):
                continue
            info = detail.get("matchInfo", detail.get("MatchInfo"))
            if isinstance(info, Mapping) and (
                _mapping_bool(info, "isCompleted", "IsCompleted") is False
                or _mapping_text(info, "matchId", "MatchID", "matchID") not in {
                    None, match.match_id,
                }
            ):
                continue
            details[match.match_id] = detail
            name_subjects.extend(_match_detail_name_subjects(detail))
        # A single batch resolves shared participants across reports. Larger
        # pages use bounded batches and stop at the same overall request budget.
        unique_subjects = tuple(dict.fromkeys(name_subjects))
        names: dict[str, str] = {}
        for offset in range(0, len(unique_subjects), MAX_LIVE_PLAYERS):
            if not budget.take():
                break
            names.update(self.player_names(unique_subjects[offset:offset + MAX_LIVE_PLAYERS]))

        matches: list[ValorantMatchSummary] = []
        for match in history:
            detail = details.get(match.match_id)
            parsed_match = (
                parse_match_details(detail, puuid=subject, fallback=match, names=names)
                if detail is not None else match
            )
            matches.append(parsed_match)
            if level is None:
                level = next((
                    player.account_level
                    for team in parsed_match.teams for player in team.players
                    if player.self and player.account_level is not None
                ), None)
        if rank is None and level is None and not matches:
            return None
        return ValorantPlayerProfile(rank=rank, level=level, matches=tuple(matches))

    def rank_optional(self, season_id: str | None = None) -> ValorantRank | None:
        """Return rank data or ``None`` when the local service is unavailable.

        The endpoint is a private VALORANT service and must only be queried
        with the PUUID bound to the authenticated local Riot Client session.
        The caller owns that binding check; this method deliberately accepts a
        required PUUID at construction and never resolves other identities.
        """

        if self.enrichment is not None and season_id is None:
            from .valorant_enrichment import RequestBudget

            budget = RequestBudget(clock=self.enrichment.clock)
            return self.enrichment.profile(self, self.puuid, self.enrichment.catalog(self, budget), budget)
        LOGGER.debug("valorant.rank.start")
        subject = quote(self.puuid, safe="")
        primary_payload: Mapping[str, Any] | None = None
        try:
            payload = self._get_json("pd", f"/mmr/v1/players/{subject}")
        except (RiotClientError, RiotClientUnavailable) as exc:
            LOGGER.info("valorant.rank.primary_unavailable error_type=%s", type(exc).__name__)
        else:
            if isinstance(payload, Mapping):
                primary_payload = payload
                queue_skills = payload.get("QueueSkills")
                competitive = (
                    queue_skills.get("competitive")
                    if isinstance(queue_skills, Mapping)
                    else None
                )
                seasons = (
                    competitive.get("SeasonalInfoBySeasonID")
                    if isinstance(competitive, Mapping)
                    else None
                )
                valid_seasons = (
                    [value for value in seasons.values() if isinstance(value, Mapping)]
                    if isinstance(seasons, Mapping)
                    else []
                )
                if season_id is not None or len(valid_seasons) <= 1:
                    rank = parse_rank(payload, season_id)
                    LOGGER.debug("valorant.rank.complete source=primary")
                    return rank
                LOGGER.debug("valorant.rank.primary_requires_active_season")
            else:
                LOGGER.info("valorant.rank.primary_unavailable reason=invalid_payload")

        # Riot's primary MMR endpoint can fail transiently while the signed-in
        # account's bounded competitive-update page remains available. The
        # caller has already bound this client to the entitlement subject, so
        # this remains an own-account-only fallback.
        try:
            updates = self._get_json(
                "pd",
                f"/mmr/v1/players/{subject}/competitiveupdates"
                "?startIndex=0&endIndex=20&queue=competitive",
            )
        except (RiotClientError, RiotClientUnavailable) as exc:
            LOGGER.info("valorant.rank.fallback_unavailable error_type=%s", type(exc).__name__)
            return None
        if not isinstance(updates, Mapping):
            LOGGER.info("valorant.rank.fallback_unavailable reason=invalid_payload")
            return None
        if primary_payload is not None and season_id is None:
            active_season = latest_competitive_update_season(updates, limit=20)
            if active_season is not None and _season_info(primary_payload, active_season):
                rank = parse_rank(primary_payload, active_season)
                LOGGER.debug("valorant.rank.complete source=primary_active_season")
                return rank
        fallback_rank = parse_competitive_updates_rank(updates, season_id, limit=20)
        if fallback_rank is None:
            LOGGER.info("valorant.rank.fallback_unavailable reason=no_rank_updates")
            return None
        LOGGER.debug("valorant.rank.complete source=competitive_updates")
        return fallback_rank

    def match_history(self, *, limit: int = 20) -> tuple[ValorantMatchSummary, ...]:
        """Return recent own history plus an authorized older selected report."""

        bounded_limit = max(1, min(int(limit), 20))
        subject = quote(self.puuid, safe="")
        LOGGER.debug("valorant.match_history.start limit=%s", bounded_limit)
        payload: object = None
        for attempt in range(2):
            try:
                payload = self._get_json(
                    "pd",
                    f"/match-history/v1/history/{subject}"
                    f"?startIndex=0&endIndex={bounded_limit}",
                )
                break
            except (RiotClientError, RiotClientUnavailable) as exc:
                if attempt == 0:
                    LOGGER.info(
                        "valorant.match_history.retry error_type=%s", type(exc).__name__
                    )
                    continue
                LOGGER.info(
                    "valorant.match_history.unavailable error_type=%s", type(exc).__name__
                )
                return ()
        if not isinstance(payload, Mapping):
            LOGGER.info("valorant.match_history.unavailable reason=invalid_payload")
            return ()
        matches = parse_match_history(payload, limit=bounded_limit)
        if self.priority_match_id and all(
            match.match_id != self.priority_match_id for match in matches
        ):
            priority = self._older_owned_history_match(matches, page_size=bounded_limit)
            if priority is not None:
                matches = (*matches, priority)
        if self.enrichment is not None:
            return self.enrichment.match_history(self, matches, priority_match_id=self.priority_match_id)
        enriched: list[ValorantMatchSummary] = []
        detail_failures = 0
        for match in matches:
            match_id = quote(match.match_id, safe="")
            try:
                details = self._get_json("pd", f"/match-details/v1/matches/{match_id}")
            except (RiotClientError, RiotClientUnavailable):
                detail_failures += 1
                enriched.append(match)
                continue
            if not isinstance(details, Mapping):
                detail_failures += 1
                enriched.append(match)
                continue
            missing_names = _match_detail_name_subjects(details)
            names = self.player_names(missing_names) if missing_names else {}
            enriched.append(
                parse_match_details(
                    details,
                    puuid=self.puuid,
                    fallback=match,
                    names=names,
                )
            )
        LOGGER.info(
            "valorant.match_history.complete count=%s detail_failures=%s",
            len(enriched),
            detail_failures,
        )
        return tuple(enriched)

    def _older_owned_history_match(
        self, recent: tuple[ValorantMatchSummary, ...], *, page_size: int
    ) -> ValorantMatchSummary | None:
        """Find a selected older match without permitting arbitrary detail IDs."""

        priority_id = self.priority_match_id
        if not priority_id or not _SUBJECT_PATTERN.fullmatch(priority_id):
            return None
        if self.enrichment is not None:
            cached = self.enrichment.owned_history_match(priority_id)
            if cached is not None:
                return cached
        if len(recent) < page_size:
            return None
        subject = quote(self.puuid, safe="")
        seen = {match.match_id for match in recent}
        deadline = time.monotonic() + 6
        # Five pages total, with only the selected row returned/enriched.
        # A match must appear in this authenticated owner's page before any
        # detail or participant lookup; a supplied match ID is not authority.
        for offset in range(page_size, page_size + 80, 20):
            if time.monotonic() >= deadline:
                break
            try:
                payload = self._get_json(
                    "pd",
                    f"/match-history/v1/history/{subject}"
                    f"?startIndex={offset}&endIndex={offset + 20}",
                )
            except (RiotClientError, RiotClientUnavailable):
                break
            page = parse_match_history(payload, limit=20) if isinstance(payload, Mapping) else ()
            candidate = next((match for match in page if match.match_id == priority_id), None)
            if candidate is not None:
                if self.enrichment is not None:
                    self.enrichment.remember_owned_history_match(candidate)
                return candidate
            new_ids = {match.match_id for match in page} - seen
            if len(page) < 20 or not new_ids:
                break
            seen.update(new_ids)
        return None

    def detect(self) -> ValorantCoregame | ValorantPregame | None:
        """Distinguish an authenticated idle response from missing telemetry."""

        self.activity_available = False
        self._missing_match_endpoints.clear()
        match = self.coregame() or self.pregame()
        self.activity_available = match is not None or self._missing_match_endpoints == {
            "/core-game/v1/players", "/pregame/v1/players"
        }
        return match

    def player_names(self, subjects: object) -> dict[str, str]:
        """Resolve Riot IDs for a bounded authorized participant set.

        Privacy selection belongs to the caller because only the match payload
        carries Riot's ``Incognito`` marker. The response is restricted back to
        the requested subjects before any display values are returned.
        """

        requested = _bounded_subjects(subjects)
        if not requested:
            return {}
        try:
            payload = self._put_json("pd", "/name-service/v2/players", list(requested))
        except (RiotClientError, RiotClientUnavailable) as exc:
            LOGGER.info(
                "valorant.live_names.unavailable error_type=%s",
                type(exc).__name__,
            )
            return {}
        names = parse_player_names(payload, requested)
        LOGGER.debug(
            "valorant.live_names.complete requested=%s resolved=%s",
            len(requested),
            len(names),
        )
        return names

    def live_player_ranks(
        self,
        subjects: object,
        season_id: str | None = None,
    ) -> dict[str, ValorantRank]:
        """Read a bounded live roster's rank emblems without retaining identities."""

        requested = _bounded_subjects(subjects)
        if self.enrichment is not None:
            from .valorant_enrichment import RequestBudget

            budget = RequestBudget(clock=self.enrichment.clock)
            catalog = self.enrichment.catalog(self, budget)
            return {subject: rank for subject in requested if (rank := self.enrichment.profile(self, subject, catalog, budget)) is not None}
        ranks: dict[str, ValorantRank] = {}
        failures = 0
        for subject in requested:
            try:
                payload = self._get_json(
                    "pd",
                    f"/mmr/v1/players/{quote(subject, safe='')}",
                )
            except (RiotClientError, RiotClientUnavailable):
                failures += 1
                continue
            if not isinstance(payload, Mapping):
                failures += 1
                continue
            ranks[subject] = parse_rank(payload, season_id)
        LOGGER.info(
            "valorant.live_ranks.complete requested=%s resolved=%s failures=%s",
            len(requested),
            len(ranks),
            failures,
        )
        return ranks

    def live_player_profiles(self, subjects: object) -> dict[str, dict[str, Any]]:
        return self.enrichment.live_profiles(self, subjects) if self.enrichment else {}

    def own_party(self, *, own_team_subjects: tuple[str, ...] = ()) -> ValorantParty | None:
        """Read only the authenticated player's actual party membership."""

        from .valorant_presence import parse_party, party_identifier

        try:
            player = self._get_json("glz", f"/parties/v1/players/{quote(self.puuid, safe='')}")
            party_id = party_identifier(player, subject=self.puuid)
            if party_id is None:
                return None
            party = self._get_json("glz", f"/parties/v1/parties/{quote(party_id, safe='')}")
            return parse_party(party, subject=self.puuid, expected_id=party_id, own_team_subjects=_bounded_subjects(own_team_subjects))
        except RiotClientError as exc:
            LOGGER.debug("valorant.party.unavailable error_type=%s", type(exc).__name__)
            return None

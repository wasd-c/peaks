"""League of Legends/TFT local-game detection and payload parsers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any, cast
from urllib.parse import quote

from .client import RiotClientError, RiotClientHTTP, RiotClientUnavailable
from .discovery import RiotLockfile, discover_verified_league_lockfile, running_process_names

LEAGUE_LIVE_DATA_PORT = 2999
CURRENT_SUMMONER_PATH = "/lol-summoner/v1/current-summoner"
REGION_LOCALE_PATH = "/riotclient/region-locale"
SUMMONER_LOOKUP_PATH = "/lol-summoner/v1/summoners"
RANKED_STATS_PATH = "/lol-ranked/v1/ranked-stats/"
CURRENT_RANKED_STATS_PATH = "/lol-ranked/v1/current-ranked-stats"
GAMEFLOW_SESSION_PATH = "/lol-gameflow/v1/session"
GAMEFLOW_PHASE_PATH = "/lol-gameflow/v1/gameflow-phase"
LOBBY_PATH = "/lol-lobby/v2/lobby"
CHAMP_SELECT_PATH = "/lol-champ-select/v1/session"
MATCHMAKING_PATH = "/lol-matchmaking/v1/search"

_TFT_QUEUE_IDS = frozenset({1090, 1100, 1110, 1111, 1130, 1150, 1160})
_TFT_DOUBLE_UP_QUEUE_IDS = frozenset({1150, 1160})
_STANDARD_RANKED_QUEUES = frozenset({"RANKED_SOLO_5x5", "RANKED_TFT"})
_SUPPORTED_RANKED_QUEUES = _STANDARD_RANKED_QUEUES | {"RANKED_TFT_DOUBLE_UP", "RANKED_TFT_PAIRS"}
_SESSION_PHASES = {
    "lobby": "lobby", "checkedintotournament": "lobby",
    "matchmaking": "matchmaking", "readycheck": "readycheck",
    "champselect": "pregame", "gamestart": "live",
    "inprogress": "live", "reconnect": "live",
}
_CHAMPION_NAMES: dict[int, str] = {}

_RANK_TIERS = frozenset({"IRON", "BRONZE", "SILVER", "GOLD", "PLATINUM", "EMERALD", "DIAMOND", "MASTER", "GRANDMASTER", "CHALLENGER"})


@dataclass(frozen=True, slots=True)
class LeagueRankedQueue:
    queue_type: str
    tier: str
    rank: str
    league_points: int
    wins: int
    losses: int


def parse_ranked_stats(
    payload: object, *, queue_types: frozenset[str] | None = None,
) -> tuple[LeagueRankedQueue, ...] | None:
    """Read requested queues; unknown/failed payloads are not Unranked.

    TFT Double Up and Hyper Roll are distinct ladders and cannot substitute
    for RANKED_TFT. Standard League/TFT remain the default; Double Up callers
    must explicitly request its ladder. An empty-tier queue is real unranked.
    """
    allowed_queues = _STANDARD_RANKED_QUEUES if queue_types is None else queue_types
    if not allowed_queues or not allowed_queues <= _SUPPORTED_RANKED_QUEUES or not isinstance(payload, Mapping):
        return None
    queues = payload.get("queues")
    if not isinstance(queues, list):
        queue_map = payload.get("queueMap")
        if not isinstance(queue_map, Mapping):
            return None
        queues = list(queue_map.values())
    result: list[LeagueRankedQueue] = []
    seen: set[str] = set()
    for row in queues:
        if not isinstance(row, Mapping):
            continue
        queue = row.get("queueType")
        if not isinstance(queue, str) or queue not in allowed_queues or queue in seen:
            continue
        tier = row.get("tier")
        division = row.get("division")
        if not isinstance(tier, str) or not isinstance(division, str):
            continue
        tier, division = tier.upper(), division.upper()
        if tier in {"", "NONE", "UNRANKED"} and division in {"", "NA", "NONE"}:
            tier, division = "UNRANKED", ""
        elif tier not in _RANK_TIERS or division not in {"I", "II", "III", "IV", "", "NA"}:
            continue
        values = [row.get(key) for key in ("leaguePoints", "wins", "losses")]
        if any(not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1_000_000 for value in values):
            continue
        points, wins, losses = (cast(int, value) for value in values)
        result.append(LeagueRankedQueue(str(queue), tier, "" if division == "NA" else division, points, wins, losses))
        seen.add(str(queue))
    return tuple(result)

# Exact values returned by supported Riot platform shards. This is a format
# normalization table, not an inference from Riot ID tags or IP location.
_PLATFORM_REGION_ALIASES = {
    "br": "BR",
    "br1": "BR",
    "eun": "EUNE",
    "eun1": "EUNE",
    "eune": "EUNE",
    "euw": "EUW",
    "euw1": "EUW",
    "jp": "JP",
    "jp1": "JP",
    "kr": "KR",
    "la1": "LAN",
    "lan": "LAN",
    "la2": "LAS",
    "las": "LAS",
    "me": "ME",
    "me1": "ME",
    "na": "NA",
    "na1": "NA",
    "oc1": "OCE",
    "oce": "OCE",
    "ph": "PH",
    "ph2": "PH",
    "ru": "RU",
    "sg": "SG",
    "sg2": "SG",
    "th": "TH",
    "th2": "TH",
    "tr": "TR",
    "tr1": "TR",
    "tw": "TW",
    "tw2": "TW",
    "vn": "VN",
    "vn2": "VN",
}


@dataclass(frozen=True, slots=True)
class GamePlayer:
    name: str | None
    champion: str | None = None
    team: str | None = None
    summoner_id: str | None = None
    puuid: str | None = field(default=None, repr=False)
    champion_id: int | None = None
    is_self: bool = False
    hidden: bool = False
    account_level: int | None = None
    ready: bool | None = None
    is_leader: bool | None = None
    role: str | None = None
    stats: Mapping[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LiveGame:
    game: str
    game_mode: str | None
    map_name: str | None
    game_time: float | None
    players: tuple[GamePlayer, ...] = ()
    raw: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
    phase: str = "live"
    queue_id: int | None = None
    party_size: int | None = None
    party_max: int | None = None
    game_id: str | None = None
    own_puuid: str | None = field(default=None, repr=False)
    team_mode: str | None = None

    @property
    def is_tft(self) -> bool:
        return self.game == "tft"

    @property
    def is_league(self) -> bool:
        return self.game == "league"


@dataclass(frozen=True, slots=True)
class GameFlowState:
    phase: str

    @property
    def in_game(self) -> bool:
        return self.phase.casefold() in {"inprogress", "in_game", "ingame"}


@dataclass(frozen=True, slots=True)
class LeagueSummonerProfile:
    """Small public profile returned by an authenticated local League client."""

    puuid: str = field(repr=False)
    game_name: str
    tag_line: str
    level: int | None = None
    region: str | None = None

    @property
    def riot_id(self) -> str:
        return f"{self.game_name}#{self.tag_line}"


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: object) -> float | None:
    try:
        result = float(str(value)) if value is not None else None
        return result if result is not None and isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def _integer(value: object, *, minimum: int = 0, maximum: int = 10_000_000) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str) and len(value) <= 12 and value.isascii() and value.isdecimal():
        value = int(value)
    return value if isinstance(value, int) and minimum <= value <= maximum else None


def _identifier(value: object) -> str | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value) if value > 0 else None
    text = _text(value)
    if text and len(text) <= 256 and not any(ord(char) < 32 or ord(char) == 127 for char in text) and text != "0" and text.replace("-", "").strip("0"):
        return text
    return None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def is_tft_double_up(queue_id: object, game_mode: object = None) -> bool:
    """Recognize Riot's Double Up queues without treating every TFT game as duo."""
    identifier = _integer(queue_id)
    if identifier is not None:
        return identifier in _TFT_DOUBLE_UP_QUEUE_IDS
    if not isinstance(game_mode, str):
        return False
    return game_mode.strip().casefold() in {
        "double up", "teamfight tactics (double up)", "tft_pairs", "pairs", "tft_double_up",
        "ranked_tft_pairs", "ranked_tft_double_up",
    }


def _riot_name(value: Mapping[str, Any]) -> str | None:
    game_name = _text(value.get("gameName")) or _text(value.get("riotIdGameName"))
    tag = _text(value.get("tagLine")) or _text(value.get("riotIdTagLine"))
    if game_name and tag:
        return f"{game_name}#{tag}"
    return _text(value.get("riotId")) or _text(value.get("summonerName")) or _text(value.get("displayName")) or game_name or _text(value.get("name"))


def _player(
    value: Mapping[str, Any], *, team: str | None = None,
    own: Mapping[str, Any] | None = None, local_cell: int | None = None,
    selection: bool = False,
) -> GamePlayer:
    own = own or {}
    puuid = _identifier(value.get("puuid"))
    summoner_id = _identifier(value.get("summonerId"))
    name = _riot_name(value)
    is_self = bool(
        (puuid and puuid == _identifier(own.get("puuid")))
        or (summoner_id and summoner_id == _identifier(own.get("summonerId")))
        or (local_cell is not None and value.get("cellId") == local_cell)
        or (name and name == _riot_name(own))
    )
    visibility = (_text(value.get("nameVisibilityType")) or "").casefold()
    hidden = not is_self and (
        value.get("hidden") is True or value.get("isAnonymous") is True
        or (selection and (visibility not in {"", "visible"} or not name))
    )
    if is_self:
        name = _riot_name(own) or name
        puuid = _identifier(own.get("puuid")) or puuid
    if hidden:
        name, puuid, summoner_id = None, None, None
    champion_id = _integer(value.get("championId"), minimum=1)
    if champion_id is None and selection:
        champion_id = _integer(value.get("championPickIntent"), minimum=1)
    stats: dict[str, int | float] = {}
    scores = _mapping(value.get("scores"))
    for key, source in (("kills", "kills"), ("deaths", "deaths"), ("assists", "assists"), ("minions", "creepScore"), ("vision", "wardScore")):
        number = _number(scores.get(source))
        if number is not None:
            stats[key] = int(number) if number.is_integer() else number
    character_level = _integer(value.get("level"), minimum=1, maximum=100)
    if character_level is not None:
        stats["level"] = character_level
    ready = value.get("ready")
    leader = value.get("isLeader", value.get("teamOwner"))
    return GamePlayer(
        name=name,
        champion=_text(value.get("championName")) or _text(value.get("champion")),
        team=team or _text(value.get("team")) or _identifier(value.get("teamId")),
        summoner_id=summoner_id, puuid=puuid, champion_id=champion_id,
        is_self=is_self, hidden=hidden,
        account_level=_integer(own.get("summonerLevel") if is_self else value.get("summonerLevel")),
        ready=ready if isinstance(ready, bool) else None,
        is_leader=leader if isinstance(leader, bool) else None,
        role=_text(value.get("assignedPosition")) or _text(value.get("selectedPosition")) or _text(value.get("firstPositionPreference")) or _text(value.get("position")),
        stats=stats,
    )


def normalize_platform_region(value: object) -> str | None:
    """Normalize an exact LCU platform value without guessing a shard."""

    if not isinstance(value, str) or not value or len(value) > 16:
        return None
    if value != value.strip() or any(
        ord(character) < 0x20 or ord(character) == 0x7F for character in value
    ):
        return None
    return _PLATFORM_REGION_ALIASES.get(value.casefold())


def parse_summoner_profile(
    payload: object,
    *,
    expected_game_name: str,
    expected_tag_line: str,
) -> LeagueSummonerProfile | None:
    """Normalize one exact Riot-ID lookup without accepting fuzzy LCU matches."""

    if not isinstance(payload, Mapping):
        return None
    puuid = _text(payload.get("puuid"))
    game_name = _text(payload.get("gameName")) or _text(payload.get("riotIdGameName"))
    tag_line = _text(payload.get("tagLine")) or _text(payload.get("riotIdTagLine"))
    if not game_name or not tag_line:
        display_name = _text(payload.get("displayName")) or _text(payload.get("riotId"))
        if display_name and "#" in display_name:
            game_name, _, tag_line = display_name.rpartition("#")
    if (
        not puuid
        or not game_name
        or not tag_line
        or len(puuid) > 256
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in puuid)
        or game_name.casefold() != expected_game_name.casefold()
        or tag_line.casefold() != expected_tag_line.casefold()
    ):
        return None
    raw_level = payload.get("summonerLevel")
    level = (
        raw_level
        if isinstance(raw_level, int)
        and not isinstance(raw_level, bool)
        and 0 <= raw_level <= 10_000_000
        else None
    )
    return LeagueSummonerProfile(
        puuid=puuid,
        game_name=game_name,
        tag_line=tag_line,
        level=level,
    )


def _tft_duo_players(
    players: tuple[GamePlayer, ...], rows: tuple[Mapping[str, Any], ...],
) -> tuple[GamePlayer, ...]:
    """Use only explicit client subteam assignments, never roster order.

    LCU's LobbyParticipantDto exposes subteamIndex and intraSubteamPosition.
    Gameflow entries are untyped; when those fields are absent, the roster
    remains available with unknown partners. Invalid/duplicate slots discard
    the whole affected group instead of inventing a partnership.
    """
    identities = [player.puuid or player.summoner_id or player.name for player in players]
    groups: dict[int, list[tuple[int, int | None]]] = {}
    for index, row in enumerate(rows):
        group = _integer(row.get("subteamIndex"), maximum=3)
        if group is not None:
            groups.setdefault(group, []).append((index, _integer(row.get("intraSubteamPosition"), maximum=1)))
    assignments: dict[int, str] = {}
    for group, members in groups.items():
        positions = [position for _, position in members]
        known_identities = [identities[index] for index, _ in members if identities[index] is not None]
        if (
            len(members) <= 2 and None not in positions
            and len(set(positions)) == len(members)
            and all(identities.count(identity) == 1 for identity in known_identities)
        ):
            assignments.update((index, f"duo:{group}") for index, _ in members)
    return tuple(replace(player, team=assignments.get(index)) for index, player in enumerate(players))


def _same_roster_player(player: GamePlayer, other: GamePlayer) -> bool:
    if player.puuid and other.puuid:
        return player.puuid == other.puuid
    if player.summoner_id and other.summoner_id:
        return player.summoner_id == other.summoner_id
    return bool(player.name and player.name == other.name)


def _player_list(payload: Mapping[str, Any], *, duos: bool = False) -> tuple[GamePlayer, ...]:
    values = payload.get("participants") or payload.get("players")
    if not isinstance(values, list):
        return ()
    own = _mapping(payload.get("activePlayer"))
    rows = tuple(value for value in values[:64] if isinstance(value, Mapping))
    players = tuple(_player(value, own=own) for value in rows)
    return _tft_duo_players(players, rows) if duos else players


def classify_live_game(payload: Mapping[str, Any]) -> str | None:
    """Return ``league``/``tft`` for a liveclientdata payload."""

    if not isinstance(payload, Mapping):
        return None
    game_data = payload.get("gameData")
    metadata = game_data if isinstance(game_data, Mapping) else payload
    mode = " ".join(
        str(metadata.get(key, "")) for key in ("gameMode", "game mode", "mapName", "map")
    )
    normalized = mode.casefold().replace("_", " ").replace("-", " ")
    if "tft" in normalized or "teamfight tactics" in normalized:
        return "tft"
    # 2999 returns CLASSIC for League.  Do not classify a random JSON payload
    # as a game merely because it has a ``players`` array.
    if any(token in normalized for token in ("classic", "aram", "urf", "league")):
        return "league"
    return None


def parse_live_game(payload: Mapping[str, Any]) -> LiveGame | None:
    if not isinstance(payload, Mapping):
        return None
    game = classify_live_game(payload)
    if game is None:
        return None
    metadata = payload.get("gameData")
    metadata = metadata if isinstance(metadata, Mapping) else payload
    player_payload: Mapping[str, Any]
    if isinstance(payload.get("allPlayers"), list):
        player_payload = {"players": payload["allPlayers"], "activePlayer": payload.get("activePlayer")}
    else:
        player_payload = payload
    queue_id = _integer(metadata.get("queueId"))
    duos = game == "tft" and is_tft_double_up(queue_id, metadata.get("gameMode"))
    players = _player_list(player_payload, duos=duos)
    if game == "tft":
        # Some TFT clients expose the legacy live-data API. Its active player
        # is the tactician; do not reuse League champion HP or postgame HP.
        health = _mapping(_mapping(payload.get("activePlayer")).get("championStats")).get("currentHealth")
        selves = [index for index, player in enumerate(players) if player.is_self and not player.hidden]
        if isinstance(health, (int, float)) and not isinstance(health, bool) and isfinite(health) and 0 <= health <= 1000 and len(selves) == 1:
            players = tuple(
                replace(player, stats={**player.stats, "health": health}) if index == selves[0] else player
                for index, player in enumerate(players)
            )
    return LiveGame(
        game=game,
        game_mode=_text(metadata.get("gameMode")) or _text(metadata.get("game mode")),
        map_name=_text(metadata.get("mapName")) or _text(metadata.get("map")),
        game_time=_number(metadata.get("gameTime")),
        players=players,
        raw=payload,
        queue_id=queue_id,
        team_mode="duos" if duos else "free-for-all" if game == "tft" else "teams",
    )


def parse_lol_live_game(payload: Mapping[str, Any]) -> LiveGame | None:
    result = parse_live_game(payload)
    return result if result is not None and result.is_league else None


def parse_tft_live_game(payload: Mapping[str, Any]) -> LiveGame | None:
    result = parse_live_game(payload)
    return result if result is not None and result.is_tft else None


def parse_gameflow_phase(payload: object) -> GameFlowState:
    if isinstance(payload, str):
        return GameFlowState(payload)
    if isinstance(payload, Mapping):
        phase = _text(payload.get("phase")) or _text(payload.get("gameflowPhase")) or "None"
        return GameFlowState(phase)
    return GameFlowState("None")


def _session_metadata(
    session: Mapping[str, Any], lobby: Mapping[str, Any], *, phase: str,
    queue_details: Mapping[str, Any],
) -> tuple[str, str | None, str | None, int | None, int | None]:
    data = _mapping(session.get("gameData"))
    config = _mapping(lobby.get("gameConfig"))
    queue = _mapping(data.get("queue"))
    map_data = _mapping(session.get("map"))
    if phase in {"lobby", "matchmaking", "readycheck"} and config:
        # A client may retain the preceding game's gameflow metadata in a new
        # lobby. Its current queue and mode always take precedence.
        queue_id = _integer(config.get("queueId"))
        queue = queue_details if queue_id != _integer(queue.get("id")) else {**queue, **queue_details}
        mode = _text(config.get("gameMode")) or _text(queue.get("gameMode"))
        map_id = _integer(config.get("mapId"))
    else:
        queue = {**queue_details, **queue}
        queue_id = _integer(queue.get("id"))
        mode = _text(queue.get("gameMode")) or _text(map_data.get("gameMode"))
        map_id = _integer(queue.get("mapId")) or _integer(map_data.get("id"))
    if queue_id is None:
        queue_id = _integer(config.get("queueId"))
    descriptors = " ".join(str(value) for value in (mode or "", queue.get("type", ""), queue.get("name", ""))).casefold()
    game = "tft" if queue_id in _TFT_QUEUE_IDS or "tft" in descriptors or "teamfight tactics" in descriptors else "league"
    map_name = {11: "Summoner's Rift", 12: "Howling Abyss"}.get(map_id or 0)
    if game == "tft":
        map_name = "Teamfight Tactics"
    elif phase in {"live", "pregame"}:
        map_name = _text(map_data.get("name")) or map_name
    mode_name = "Double Up" if game == "tft" and is_tft_double_up(queue_id, queue.get("type") or mode) else _text(queue.get("name")) or mode
    sizes = config.get("allowablePremadeSizes") or queue.get("allowablePremadeSizes")
    valid_sizes = [_integer(value, minimum=1, maximum=64) for value in sizes] if isinstance(sizes, list) else []
    party_max = max((value for value in valid_sizes if value is not None), default=None)
    if party_max is None:
        party_max = _integer(config.get("maxLobbySize"), minimum=1, maximum=64) or _integer(queue.get("maximumParticipantListSize"), minimum=1, maximum=64)
    return game, mode_name, map_name, queue_id, party_max


def parse_lcu_session(
    phase: str, *, session: object = None, lobby: object = None,
    selection: object = None, own: object = None, search: object = None,
    queue_details: object = None,
) -> LiveGame | None:
    """Project only public roster fields from the client's own session.

    The full gameflow/lobby payload contains chat passwords and spectator
    credentials, so unlike liveclientdata it is never retained in ``raw``.
    """
    normalized_phase = _SESSION_PHASES.get(phase.casefold())
    if normalized_phase is None:
        return None
    flow, party, champion_select = _mapping(session), _mapping(lobby), _mapping(selection)
    local, matchmaking = _mapping(own), _mapping(search)
    if not local:
        local = _mapping(party.get("localMember"))
    game, mode, map_name, queue_id, party_max = _session_metadata(
        flow, party, phase=normalized_phase, queue_details=_mapping(queue_details),
    )
    if normalized_phase == "lobby" and matchmaking.get("searchState") == "Searching":
        normalized_phase = "matchmaking"
    if normalized_phase == "lobby" and matchmaking.get("searchState") == "Found":
        normalized_phase = "readycheck"
    data = _mapping(flow.get("gameData"))
    config = _mapping(party.get("gameConfig"))
    players: list[GamePlayer] = []
    player_rows: list[Mapping[str, Any]] = []
    if normalized_phase == "pregame" and champion_select:
        local_cell = _integer(champion_select.get("localPlayerCellId"))
        for field, team in (("myTeam", "100"), ("theirTeam", "200")):
            rows = champion_select.get(field)
            if isinstance(rows, list):
                player_rows.extend(row for row in rows[:32] if isinstance(row, Mapping))
                players.extend(
                    _player(row, team=team, own=local, local_cell=local_cell, selection=True)
                    for row in rows[:32] if isinstance(row, Mapping)
                )
    elif normalized_phase == "live":
        for field, team in (("teamOne", "100"), ("teamTwo", "200")):
            rows = data.get(field)
            if isinstance(rows, list):
                player_rows.extend(row for row in rows[:32] if isinstance(row, Mapping))
                players.extend(_player(row, team="Players" if game == "tft" else team, own=local) for row in rows[:32] if isinstance(row, Mapping))
    else:
        custom_teams = config.get("isCustom") is True and any(config.get(key) for key in ("customTeam100", "customTeam200"))
        groups = ((config.get("customTeam100"), "100"), (config.get("customTeam200"), "200")) if custom_teams else ((party.get("members"), "Party"),)
        for rows, team in groups:
            if isinstance(rows, list):
                player_rows.extend(row for row in rows[:32] if isinstance(row, Mapping) and row.get("isSpectator") is not True)
                players.extend(_player(row, team=team, own=local) for row in rows[:32] if isinstance(row, Mapping) and row.get("isSpectator") is not True)
    # A missing roster is a temporary unavailable stage, never permission to
    # resurrect players from a preceding selection or completed match.
    if not players:
        return None
    members = party.get("members")
    party_size = sum(isinstance(member, Mapping) and member.get("isSpectator") is not True for member in members) if isinstance(members, list) else None
    game_time = _number(matchmaking.get("timeInQueue")) if normalized_phase == "matchmaking" else None
    duos = game == "tft" and is_tft_double_up(queue_id, mode)
    return LiveGame(
        game=game, game_mode=mode, map_name=map_name, game_time=game_time,
        players=_tft_duo_players(tuple(players), tuple(player_rows)) if duos else tuple(players), phase=normalized_phase, queue_id=queue_id,
        party_size=party_size, party_max=party_max,
        game_id=(_identifier(data.get("gameId")) or _identifier(champion_select.get("gameId"))) if normalized_phase in {"pregame", "live"} else None,
        own_puuid=_identifier(local.get("puuid")),
        team_mode="duos" if duos else "free-for-all" if game == "tft" else "teams",
    )


class LeagueClient:
    """Find League's live game through 2999 and LCU gameflow as fallback."""

    def __init__(
        self,
        *,
        live_http: RiotClientHTTP | None = None,
        lcu_http: RiotClientHTTP | None = None,
        process_names: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.live_http = live_http
        self.lcu_http = lcu_http
        self.process_names = process_names
        self.activity_available = False

    @classmethod
    def from_discovery(cls, *, process_names: set[str] | None = None) -> LeagueClient:
        # Never attach lockfile credentials to an unverified process.  The
        # resolver is intentionally available only through a live, validated
        # League client owner process on Windows.
        lock = discover_verified_league_lockfile()
        if lock is None:
            return cls(process_names=process_names)
        return cls(live_http=RiotClientHTTP(RiotLockfile("league", 1, LEAGUE_LIVE_DATA_PORT, lock.password)), lcu_http=RiotClientHTTP(lock), process_names=process_names)

    def close(self) -> None:
        for client in (self.live_http, self.lcu_http):
            if client is not None:
                client.close()

    def current_profile(self, expected_puuid: str) -> LeagueSummonerProfile | None:
        """Bind owned reads to the exact account currently signed into LCU."""
        if self.lcu_http is None:
            return None
        payload = self.lcu_http.get_json(CURRENT_SUMMONER_PATH)
        if not isinstance(payload, Mapping) or payload.get("puuid") != expected_puuid:
            return None
        return parse_summoner_profile(
            payload,
            expected_game_name=str(payload.get("gameName") or ""),
            expected_tag_line=str(payload.get("tagLine") or ""),
        )

    def ranked_stats(
        self, puuid: str, *, owned: bool = False,
        queue_types: frozenset[str] | None = None,
    ) -> tuple[LeagueRankedQueue, ...] | None:
        if self.lcu_http is None:
            return None
        if not isinstance(puuid, str) or not puuid or len(puuid) > 256 or any(ord(char) < 32 or ord(char) == 127 for char in puuid):
            return None
        # Owned callers must have checked current_profile in this same client.
        endpoint = CURRENT_RANKED_STATS_PATH if owned else RANKED_STATS_PATH + quote(puuid, safe="")
        return parse_ranked_stats(self.lcu_http.get_json(endpoint), queue_types=queue_types)

    def session_player_profile(self, player: GamePlayer) -> LeagueSummonerProfile | None:
        """Resolve a visible member of the current client-provided roster.

        Current gameflow no longer fills legacy summonerName for many players.
        Anonymous selection entries lose their PUUID during parsing and can
        never reach this read.
        """
        if self.lcu_http is None or player.hidden or not player.puuid:
            return None
        payload = self.lcu_http.get_json("/lol-summoner/v2/summoners/puuid/" + quote(player.puuid, safe=""))
        if not isinstance(payload, Mapping) or payload.get("puuid") != player.puuid:
            return None
        return parse_summoner_profile(
            payload, expected_game_name=str(payload.get("gameName") or ""),
            expected_tag_line=str(payload.get("tagLine") or ""),
        )

    def lookup_summoner(
        self,
        game_name: str,
        tag_line: str,
        *,
        expected_region: str = "",
    ) -> LeagueSummonerProfile | None:
        """Resolve one exact Riot ID through the signed-in, region-bound LCU.

        This is the no-developer-key search path.  It returns only the public
        identity fields already rendered by the League client. It discovers
        the active shard automatically, or enforces an explicit legacy filter.
        """

        if self.lcu_http is None:
            raise RiotClientUnavailable("A verified signed-in League client is required")
        region = expected_region.strip().upper()
        if region and region not in _PLATFORM_REGION_ALIASES.values():
            return None
        try:
            region_payload = self.lcu_http.get_json(REGION_LOCALE_PATH)
            if not isinstance(region_payload, Mapping):
                raise RiotClientUnavailable("The signed-in League client region is unavailable")
            active_region = normalize_platform_region(region_payload.get("region"))
            if active_region is None:
                raise RiotClientUnavailable("The signed-in League client region is unavailable")
            if region and active_region != region:
                raise RiotClientUnavailable("The signed-in League client is on another region")
            payload = self.lcu_http.get_json(
                SUMMONER_LOOKUP_PATH,
                params={"name": f"{game_name}#{tag_line}"},
            )
        except RiotClientError as exc:
            # A real 404 means that exact Riot ID was not found. Connection,
            # authentication, and shard problems must remain distinguishable
            # so the UI can give the user a useful next step.
            if exc.status_code == 404:
                return None
            if isinstance(exc, RiotClientUnavailable):
                raise
            raise RiotClientUnavailable("The signed-in League client lookup failed") from exc
        profile = parse_summoner_profile(
            payload,
            expected_game_name=game_name,
            expected_tag_line=tag_line,
        )
        return replace(profile, region=active_region) if profile is not None else None

    def _has_process(self) -> bool:
        if self.process_names is not None:
            return any("league" in name.casefold() for name in self.process_names)
        names = running_process_names(platform_name="Windows")
        return any("league" in name.casefold() for name in names)

    def current_game(self) -> LiveGame | None:
        if not self._has_process() or self.live_http is None:
            return None
        try:
            return parse_live_game(self.live_http.get_json("/liveclientdata/allgamedata"))
        except (RiotClientError, RiotClientUnavailable):
            return None

    def gameflow(self) -> GameFlowState:
        if self.lcu_http is None:
            return GameFlowState("None")
        try:
            payload = self.lcu_http.get_json(GAMEFLOW_PHASE_PATH)
        except (RiotClientError, RiotClientUnavailable):
            return GameFlowState("None")
        return parse_gameflow_phase(payload)

    def _session_read(self, endpoint: str) -> object:
        if self.lcu_http is None:
            return None
        try:
            return self.lcu_http.get_json(endpoint)
        except (RiotClientError, RiotClientUnavailable):
            return None

    def _with_champion_names(self, game: LiveGame) -> LiveGame:
        if game.is_tft:
            return game
        missing = {player.champion_id for player in game.players if player.champion_id and not player.champion and not _CHAMPION_NAMES.get(player.champion_id)}
        if missing:
            payload = self._session_read("/lol-game-data/assets/v1/champion-summary.json")
            if isinstance(payload, list):
                for row in payload[:1000]:
                    if not isinstance(row, Mapping):
                        continue
                    identifier = _integer(row.get("id"), minimum=1)
                    name = _text(row.get("name"))
                    if identifier is not None and name and len(name) <= 100:
                        _CHAMPION_NAMES[identifier] = name
        return replace(game, players=tuple(
            replace(player, champion=_CHAMPION_NAMES.get(player.champion_id or 0))
            if not player.champion and player.champion_id else player
            for player in game.players
        ))

    def current_session(self) -> LiveGame | None:
        """Read the signed-in League/TFT lobby, selection, or active game.

        Gameflow is authoritative on exit: a lingering live-data endpoint or
        stale lobby must not keep a finished match on screen. All operations
        are GETs through the validated local client; no developer key needed.
        """
        self.activity_available = False
        if not self._has_process():
            return None
        phase_payload = self._session_read(GAMEFLOW_PHASE_PATH)
        phase_known = isinstance(phase_payload, str) or (
            isinstance(phase_payload, Mapping) and isinstance(phase_payload.get("phase"), str)
        )
        if phase_known:
            self.activity_available = True
            phase = parse_gameflow_phase(phase_payload).phase
            if phase.casefold() not in _SESSION_PHASES:
                return None
        else:
            phase = ""
        session = _mapping(self._session_read(GAMEFLOW_SESSION_PATH))
        if isinstance(session.get("phase"), str):
            self.activity_available = True
            if not phase_known:
                phase = str(session["phase"])
                phase_known = True
                if phase.casefold() not in _SESSION_PHASES:
                    return None
        if not phase_known:
            # Older clients can still expose the documented live-data API
            # while gameflow is unavailable; this remains useful for League.
            live = self.current_game()
            if live is not None:
                self.activity_available = True
                return live
            return None
        own = _mapping(self._session_read(CURRENT_SUMMONER_PATH))
        stage = _SESSION_PHASES[phase.casefold()]
        lobby = _mapping(self._session_read(LOBBY_PATH))
        if stage == "live":
            # A retained lobby can supply the real party size during play.
            # Never attach an unrelated lobby to the active game or mistake
            # the full match roster for a premade party.
            lobby_queue = _integer(_mapping(lobby.get("gameConfig")).get("queueId"))
            active_queue = _integer(_mapping(_mapping(session.get("gameData")).get("queue")).get("id"))
            members = lobby.get("members")
            owner = _identifier(own.get("puuid"))
            if lobby_queue is None or lobby_queue != active_queue or not owner or not isinstance(members, list) or not any(
                isinstance(member, Mapping) and _identifier(member.get("puuid")) == owner
                for member in members[:64]
            ):
                lobby = {}
        selection = self._session_read(CHAMP_SELECT_PATH) if stage == "pregame" else None
        search = self._session_read(MATCHMAKING_PATH) if stage in {"lobby", "matchmaking", "readycheck"} else None
        queue_details: object = None
        config = _mapping(lobby.get("gameConfig"))
        queue_id = _integer(config.get("queueId"))
        flow_queue = _mapping(_mapping(session.get("gameData")).get("queue"))
        if queue_id is not None and (queue_id != _integer(flow_queue.get("id")) or not flow_queue.get("name")):
            queue_details = self._session_read(f"/lol-game-queues/v1/queues/{queue_id}")
        fallback = parse_lcu_session(
            phase, session=session, lobby=lobby, selection=selection, own=own,
            search=search, queue_details=queue_details,
        )
        if stage == "live":
            live = self.current_game()
            if live is not None and (fallback is None or live.game == fallback.game):
                players: list[GamePlayer] = []
                for player in live.players:
                    matches = [entry for entry in fallback.players if _same_roster_player(player, entry)] if fallback else []
                    if len(matches) == 1:
                        known = matches[0]
                        player = replace(player, puuid=known.puuid, is_self=player.is_self or known.is_self, account_level=known.account_level)
                        if fallback and fallback.team_mode == "duos":
                            player = replace(player, team=known.team)
                    elif fallback and fallback.team_mode == "duos":
                        player = replace(player, team=None)
                    if player.is_self:
                        player = replace(player, puuid=_identifier(own.get("puuid")) or player.puuid, name=_riot_name(own) or player.name, account_level=_integer(own.get("summonerLevel")))
                    team_mode = fallback.team_mode if fallback else live.team_mode
                    players.append(replace(player, team="Players") if live.is_tft and team_mode != "duos" else player)
                if fallback:
                    live = replace(live, queue_id=fallback.queue_id, game_id=fallback.game_id, party_size=fallback.party_size, party_max=fallback.party_max, game_mode=fallback.game_mode or live.game_mode, map_name=fallback.map_name or live.map_name, team_mode=fallback.team_mode)
                return self._with_champion_names(replace(live, players=tuple(players), own_puuid=_identifier(own.get("puuid"))))
        if fallback is None:
            self.activity_available = False
            return None
        return self._with_champion_names(fallback)

    def detect(self) -> LiveGame | None:
        """Return the active League/TFT game, or ``None`` when no game exists."""

        return self.current_session()


LeagueGameDetector = LeagueClient

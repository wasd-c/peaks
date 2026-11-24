"""Standalone TFT client (patch 18.6+) session state, without the League client.

TFT now runs in its own Unreal client (TFTClient-Win64-Shipping.exe). It has no
local API: no LCU, no live-data port and an empty product lockfile. Its state
comes from three local sources instead:

* the Riot Client's external product session (phase ``Idle``/``Gameplay``);
* TFT.log, which records lobby state transitions (``Frontend``, ``SoloMode``,
  ``Matchmaking``, ``InGame``, ``EndOfGameSummary``) and the matchmaking and
  game-server notifications the client receives, with queue and game IDs;
* TFTEoGStats.json, rewritten after each round with every player's board.

Only fixed markers are parsed from the log. No raw line, credential or chat
leaves this module; player names come from the stats file the game writes.
"""

from __future__ import annotations

import json
import os
import re
import stat
import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .client import RiotClientError, RiotClientHTTP, RiotClientUnavailable
from .discovery import running_process_names
from .league import GamePlayer, LiveGame, is_tft_double_up

TFT_PROCESS_NAME = "TFTClient-Win64-Shipping.exe"
EXTERNAL_SESSIONS_PATH = "/product-session/v1/external-sessions"
ENTITLEMENTS_PATH = "/entitlements/v1/token"
MAX_INITIAL_BYTES = 32 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 256 * 1024
MAX_STATS_BYTES = 1024 * 1024
MAX_ENDED_GAMES = 32
MAX_CACHED_LOGS = 32

_TIME = re.compile(r"^\[(\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]")
_LOBBY_STATE = re.compile(r"Entering LobbyState\[ETFTLobbyState::([A-Za-z]{1,40})\]")
_RMS = re.compile(r"RGIOPRms: Received RMS message ID '[^']{0,64}' for resource '([^']{1,200})' service '[^']{0,64}' payload '")
_PHASE_NAME = re.compile(r'"phaseName":"([A-Z_]{1,40})"')
_QUEUE_ID = re.compile(r'"queueId":(\d{1,7})\b')
_GAME_ID = re.compile(r'"(?:gameId|id)":(\d{1,19})\b')
_GAME_UPDATE = re.compile(r"^lol-gsm-server/v1/gsm/game-update/([A-Z_]{1,40})$")
# Lines worth decoding; every other log line is skipped as bytes.
_MARKERS = (b"Entering LobbyState[", b"RGIOPRms: Received RMS message")

_LOBBY_PHASES = frozenset({"SoloMode", "SocialMode"})
_QUEUE_NAMES = {1090: "Normal", 1100: "Ranked", 1130: "Hyper Roll", 1150: "Double Up", 1160: "Double Up"}


def _timestamp(line: str) -> float | None:
    match = _TIME.match(line)
    if match is None:
        return None
    try:
        return datetime.strptime(match[1], "%Y.%m.%d-%H.%M.%S:%f").replace(tzinfo=UTC).timestamp()
    except ValueError:
        return None


def _first_int(pattern: re.Pattern[str], text: str, maximum: int) -> int | None:
    match = pattern.search(text)
    if match is None:
        return None
    value = int(match[1])
    return value if 0 < value <= maximum else None


@dataclass(slots=True)
class TftLogState:
    """What TFT.log says about the client, in log order."""

    lobby_state: str | None = None
    lobby_state_at: float | None = None
    matchmaking_phase: str | None = None
    matchmaking_queue: int | None = None
    party_queue: int | None = None
    game_id: int | None = None
    game_queue: int | None = None
    game_started_at: float | None = None
    # Finished games: game ID -> UTC time the client left the match.
    ended: OrderedDict[int, float] = field(default_factory=OrderedDict)

    def copy(self) -> TftLogState:
        return replace(self, ended=OrderedDict(self.ended))

    def apply(self, line: str) -> None:
        when = _timestamp(line)
        if (state := _LOBBY_STATE.search(line)) is not None:
            self.lobby_state, self.lobby_state_at = state[1], when
            if state[1] in _LOBBY_PHASES or state[1] in {"Frontend", "InGame"}:
                self.matchmaking_phase = None
            if state[1].startswith("EndOfGame") and self.game_id is not None and self.game_id not in self.ended and when is not None:
                self.ended[self.game_id] = when
                while len(self.ended) > MAX_ENDED_GAMES:
                    self.ended.popitem(last=False)
            return
        rms = _RMS.search(line)
        if rms is None:
            return
        resource, payload = rms[1], line[rms.end():]
        queue = _first_int(_QUEUE_ID, payload, 1_000_000)
        if resource == "teambuilder/v1/tbdGameDtoV1/tft":
            phase = _PHASE_NAME.search(payload)
            self.matchmaking_phase = phase[1] if phase else self.matchmaking_phase
            self.matchmaking_queue = queue or self.matchmaking_queue
        elif resource == "teambuilder/v1/removedFromServiceV1":
            self.matchmaking_phase = None
        elif resource == "parties/v1/notifications/tft" and queue:
            self.party_queue = queue
        elif (update := _GAME_UPDATE.match(resource)) is not None and update[1] == "IN_PROGRESS":
            game = _first_int(_GAME_ID, payload, 2**63 - 1)
            if game is not None:
                if game != self.game_id:
                    self.game_started_at = when
                self.game_id, self.game_queue = game, queue or self.matchmaking_queue
                self.matchmaking_phase = None


@dataclass(slots=True)
class _Tail:
    identity: tuple[int, int] | None = None
    position: int = 0
    pending: bytes = b""
    state: TftLogState = field(default_factory=TftLogState)


_TAILS: OrderedDict[str, _Tail] = OrderedDict()
_TAILS_LOCK = threading.Lock()


def read_log_state(path: Path) -> TftLogState | None:
    """Incrementally parse a TFT log; the first read covers the whole file."""
    key = str(path)
    with _TAILS_LOCK:
        tail = _TAILS.pop(key, None) or _Tail()
        _TAILS[key] = tail
        while len(_TAILS) > MAX_CACHED_LOGS:
            _TAILS.popitem(last=False)
        try:
            with path.open("rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):
                    return None
                identity = (info.st_dev, info.st_ino)
                if identity != tail.identity or info.st_size < tail.position:
                    # A new client start rotates TFT.log; parse it from the start.
                    tail.identity, tail.pending, tail.state = identity, b"", TftLogState()
                    tail.position = max(0, info.st_size - MAX_INITIAL_BYTES)
                    skip_partial = tail.position > 0
                else:
                    skip_partial = False
                handle.seek(tail.position)
                chunk = handle.read(MAX_CHUNK_BYTES if tail.state.lobby_state or tail.position else MAX_INITIAL_BYTES)
                tail.position = handle.tell()
        except OSError:
            return None
        lines = (tail.pending + chunk).split(b"\n")
        tail.pending = lines.pop()[-MAX_LINE_BYTES:]
        if skip_partial and lines:
            lines.pop(0)
        for raw in lines:
            if len(raw) <= MAX_LINE_BYTES and any(marker in raw for marker in _MARKERS):
                tail.state.apply(raw.decode("utf-8", errors="replace"))
        return tail.state.copy()


def default_logs_directory() -> Path | None:
    local = os.environ.get("LOCALAPPDATA")
    return Path(local) / "TFT" / "Saved" / "Logs" if local else None


def read_stats_file(path: Path, game_id: int) -> dict[str, Any] | None:
    """Return TFTEoGStats.json only when it belongs to ``game_id``."""
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_STATS_BYTES:
            return None
        payload = json.loads(path.read_bytes()[:MAX_STATS_BYTES])
    except (OSError, ValueError, RecursionError):
        return None
    if not isinstance(payload, dict) or type(payload.get("gameId")) is not int or payload["gameId"] != game_id:
        return None
    if payload.get("gameMode") != "TFT" or not isinstance(payload.get("statsBlock"), dict):
        return None
    return payload


def queue_name(queue_id: int | None, queue_type: object = None) -> str | None:
    if queue_id in _QUEUE_NAMES:
        return _QUEUE_NAMES[queue_id]
    if isinstance(queue_type, str) and re.fullmatch(r"[A-Z0-9_]{1,64}", queue_type):
        words = [word for word in queue_type.split("_") if word and word != "TFT"]
        return " ".join(word.capitalize() for word in words) or None
    return None


def partner_groups(payload: dict[str, Any] | None) -> dict[int, int]:
    """Map partnerGroupId to a duo index, only for a complete four-pair lobby."""
    rows = payload["statsBlock"].get("players") if payload else None
    if not isinstance(rows, list) or len(rows) != 8:
        return {}
    groups: dict[int, int] = {}
    for row in rows:
        group = row.get("partnerGroupId") if isinstance(row, dict) else None
        if type(group) is not int or group <= 0:
            return {}
        groups[group] = groups.get(group, 0) + 1
    if len(groups) != 4 or any(count != 2 for count in groups.values()):
        return {}
    return {group: index for index, group in enumerate(sorted(groups))}


def is_double_up(queue_id: int | None, payload: dict[str, Any] | None = None) -> bool:
    """Double Up from its queue, its queue type or the pairs the game reports.

    Event queues are renumbered every set, so a new Double Up queue must not
    fall back to the eight-player free-for-all layout.
    """
    if is_tft_double_up(queue_id):
        return True
    queue_type = payload.get("queueType") if payload else None
    if isinstance(queue_type, str) and re.search(r"DOUBLE_?UP|PAIRS", queue_type, re.I):
        return True
    return bool(partner_groups(payload))


def _text(value: object, maximum: int) -> str | None:
    return value.strip() if isinstance(value, str) and 0 < len(value.strip()) <= maximum and value.isprintable() else None


def roster(payload: dict[str, Any], own_puuid: str | None, *, duos: bool) -> tuple[GamePlayer, ...]:
    rows = payload["statsBlock"].get("players")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16:
        return ()
    pairs = partner_groups(payload) if duos else {}
    players = []
    for row in rows:
        if not isinstance(row, dict):
            return ()
        puuid = _text(row.get("PUUID"), 128)
        name, tag = _text(row.get("riotIdGameName"), 64), _text(row.get("riotIdTagLine"), 32)
        own = bool(own_puuid and puuid == own_puuid)
        group = row.get("partnerGroupId")
        players.append(GamePlayer(
            name=f"{name}#{tag}" if name and tag else None,
            puuid=puuid,
            is_self=own,
            hidden=not own and not (name and tag),
            team=f"duo:{pairs[group]}" if type(group) is int and group in pairs else "Players",
        ))
    return tuple(players)


class StandaloneTftClient:
    """Session reader for the standalone TFT client, shaped like LeagueClient."""

    def __init__(
        self,
        riot_http: RiotClientHTTP | None = None,
        *,
        process_names: set[str] | frozenset[str] | None = None,
        logs_directory: Path | None = None,
    ) -> None:
        self.riot_http = riot_http
        self.process_names = process_names
        self.logs_directory = logs_directory if logs_directory is not None else default_logs_directory()
        self.activity_available = False

    @classmethod
    def from_discovery(cls, discovery: Any) -> StandaloneTftClient:
        lockfile = getattr(discovery, "lockfile", None)
        return cls(RiotClientHTTP(lockfile, timeout=2.0) if lockfile is not None else None)

    def close(self) -> None:
        if self.riot_http is not None:
            self.riot_http.close()

    def running(self) -> bool:
        names = self.process_names if self.process_names is not None else running_process_names(platform_name="Windows")
        return any(name.casefold() == TFT_PROCESS_NAME.casefold() for name in names)

    def _read(self, path: str) -> object:
        if self.riot_http is None:
            return None
        try:
            return self.riot_http.get_json(path)
        except (RiotClientError, RiotClientUnavailable):
            return None

    def product_phase(self) -> str | None:
        sessions = self._read(EXTERNAL_SESSIONS_PATH)
        if not isinstance(sessions, dict):
            return None
        for session in list(sessions.values())[:32]:
            if isinstance(session, dict) and session.get("productId") == "teamfighttactics":
                phase = session.get("phase")
                return phase if isinstance(phase, str) and len(phase) <= 40 else None
        return None

    def owner(self) -> str | None:
        token = self._read(ENTITLEMENTS_PATH)
        subject = token.get("subject") if isinstance(token, dict) else None
        return _text(subject, 128)

    def current_session(self) -> LiveGame | None:
        self.activity_available = False
        if not self.running() or self.logs_directory is None:
            return None
        self.activity_available = True
        log = read_log_state(self.logs_directory / "TFT.log")
        if log is None:
            return None
        product_phase = self.product_phase()
        in_game = log.game_id is not None and log.game_id not in log.ended and (
            log.lobby_state == "InGame" or product_phase == "Gameplay"
        )
        own = self.owner()
        if in_game:
            assert log.game_id is not None
            queue = log.game_queue
            payload = read_stats_file(self.logs_directory / "TFTEoGStats.json", log.game_id)
            if payload is not None and type(payload.get("queueId")) is int:
                queue = payload["queueId"]
            duos = is_double_up(queue, payload)
            block = payload["statsBlock"] if payload else {}
            elapsed = block.get("gameLengthSeconds")
            return LiveGame(
                game="tft",
                game_mode=queue_name(queue, payload.get("queueType") if payload else None),
                map_name=None,
                game_time=float(elapsed) if type(elapsed) is int and 0 <= elapsed <= 86_400 else None,
                players=roster(payload, own, duos=duos) if payload else (),
                phase="live",
                queue_id=queue,
                game_id=str(log.game_id),
                own_puuid=own,
                team_mode="duos" if duos else "free-for-all",
            )
        if log.lobby_state == "Matchmaking" or log.matchmaking_phase is not None:
            phase = {"AFK_CHECK": "readycheck", "CHAMPION_SELECT": "pregame"}.get(log.matchmaking_phase or "", "matchmaking")
            queue = log.matchmaking_queue or log.party_queue
        elif log.lobby_state in _LOBBY_PHASES:
            phase, queue = "lobby", log.party_queue
        else:
            return None
        return LiveGame(
            game="tft", game_mode=queue_name(queue), map_name=None, game_time=None,
            phase=phase, queue_id=queue, own_puuid=own,
            team_mode="duos" if is_tft_double_up(queue) else "free-for-all",
        )

    def detect(self) -> LiveGame | None:
        return self.current_session()

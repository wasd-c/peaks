"""Completed TFT reports already delivered by the game to its local client.

TFTEoGStats.json is also rewritten during play, so it cannot prove a final
placement on its own. Two log events can:

* PostEogStatsBlock, sent to the League client before TFT had its own client;
  its body survives the next game replacing the stats file.
* Since patch 18.6 the standalone client posts nothing locally. It logs its
  move to the end-of-game screen instead; the stats file written for that game
  is then final, until the next game replaces it.

Only bounded, owner-bound presentation fields leave this reader; command
lines, headers and raw log content never leave it.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import time
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from peaks.adapters.providers.riot_api import PlatformRouting
from peaks.domain.regions import normalize_league_region

from .tft_client import is_double_up, read_log_state, read_stats_file
from .tft_composition import composition_view

MAX_LOG_FILES = 20
MAX_TAIL_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 1024 * 1024
MAX_AGE_SECONDS = 90 * 86_400
_PLATFORMS = {normalize_league_region(value.value): value.value.upper() for value in PlatformRouting}
_EVENT = re.compile(
    r"^\[(?P<time>\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]"
    r"\[\s*\d+\]RGIOPHttp: UTFTLeagueFoundationClient::PostEogStatsBlock: Query Start"
    r" \| POST https://127\.0\.0\.1:\d{1,5}/lol-end-of-game/v1/gameclient-eog-stats-block"
    r" \| [^\r\n]*? \| RequestBody: (?P<body>\{[^\r\n]+\})$"
)


def platform_match_id(game_id: object, platform: object) -> str | None:
    """Use only an already verified platform, matching Riot's history ID."""
    region = normalize_league_region(platform)
    prefix = _PLATFORMS.get(region) if region else None
    if not prefix or isinstance(game_id, bool) or not isinstance(game_id, (str, int)):
        return None
    text = str(game_id)
    if text.startswith(f"{prefix}_"):
        text = text[len(prefix) + 1:]
    if not re.fullmatch(r"[1-9][0-9]{0,18}", text) or int(text) > 2**63 - 1:
        return None
    return f"{prefix}_{text}"


def _text(value: object, maximum: int = 128) -> str | None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        return None
    if any(ord(char) < 32 or 127 <= ord(char) <= 159 for char in value):
        return None
    return value.strip() or None


def _integer(value: object, low: int, high: int) -> int | None:
    return value if type(value) is int and low <= value <= high else None


def _number(value: object, low: int, high: int) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if low <= value <= high else None


def _report(payload: object, owner: str, platform: str, ended_at: float) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping) or payload.get("gameMode") != "TFT":
        return None
    match_id = platform_match_id(payload.get("gameId"), platform)
    queue = _integer(payload.get("queueId"), 1, 1_000_000)
    block = payload.get("statsBlock")
    # Event queues (Choncc's Treasure is 6080) are new each set: accept any.
    if not match_id or queue is None or not isinstance(block, Mapping):
        return None
    rows = block.get("players")
    duration = _number(block.get("gameLengthSeconds"), 1, 86_400)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 16 or duration is None:
        return None
    if any(not isinstance(row, Mapping) for row in rows):
        return None
    selves = [row for row in rows if row.get("PUUID") == owner]
    if len(selves) != 1:
        return None
    placement = _integer(selves[0].get("ffaStanding"), 1, min(8, len(rows)))
    if placement is None:
        return None
    duos = is_double_up(queue, dict(payload))
    groups: dict[int, list[int]] = {}
    if duos:
        for index, row in enumerate(rows):
            group = _integer(row.get("partnerGroupId"), 1, 255)
            if group is not None:
                groups.setdefault(group, []).append(index)
    valid_pairs = len(rows) == 8 and len(groups) == 4 and all(len(pair) == 2 for pair in groups.values())
    pair_labels = {index: f"Duo {number}" for number, indices in enumerate(groups.values(), 1) for index in indices} if valid_pairs else {}
    standings = [row.get("ffaStanding") for row in rows]
    team_places = duos and len(rows) == 8 and all(standings.count(place) == 2 for place in (1, 2, 3, 4))
    positive_threshold = 2 if team_places else 4
    healths = [_number(row.get("health"), -99, 1000) for row in rows]
    # Once every other player is out, the last one standing has won.
    survivors = [index for index, health in enumerate(healths) if health is None or health > 0]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        own = row.get("PUUID") == owner
        game_name, tag = _text(row.get("riotIdGameName"), 64), _text(row.get("riotIdTagLine"), 32)
        riot_id = f"{game_name}#{tag}" if game_name and tag else None
        hidden = not own and riot_id is None
        health = _number(row.get("health"), -99, 1000)
        # The owner has finished; living opponents still have provisional
        # standings and boards. Do not present those as their final result.
        finished = own or (health is not None and health <= 0) or (not duos and survivors == [index])
        place = _integer(row.get("ffaStanding"), 1, min(8, len(rows))) if finished else None
        stats: dict[str, Any] = {"placement": place} if place is not None else {}
        level = _integer(row.get("level"), 1, 20)
        if level is not None and finished:
            stats["level"] = level
        composition: dict[str, Any] = {}
        board = row.get("boardPieces")
        if finished and not hidden and isinstance(board, list) and len(board) <= 32:
            composition = composition_view({"units": [
                {"character_id": unit.get("championName"), "tier": unit.get("starLevel"), "itemNames": unit.get("itemNames")}
                for unit in board if isinstance(unit, Mapping)
            ]}) if all(isinstance(unit, Mapping) for unit in board) else {}
            if row.get("augments"):
                composition.update(composition_view({"augments": row["augments"]}))
        team = pair_labels.get(index, "Unassigned players") if duos else "Players"
        grouped.setdefault(team, []).append({
            "name": riot_id or ("You" if own else f"Player {index + 1}"),
            "riotId": riot_id, "self": own, "hidden": hidden,
            "stats": stats, **({"composition": composition} if composition else {}),
        })
    return {
        "id": match_id, "game": "tft", "queue": str(queue),
        "map_name": "Teamfight Tactics", "played_at": ended_at - duration,
        "duration_seconds": int(duration),
        "result": ("top_2" if team_places else "top_4") if placement <= positive_threshold else "placement",
        "metadata": {
            "localEndOfGame": True,
            "teams": [{"name": name, "players": players,
                       **({"grouping": "duo" if name.startswith("Duo ") else "unassigned"} if duos else {})}
                      for name, players in grouped.items()],
            **({"teamMode": "duos"} if duos else {"freeForAll": True}),
        },
    }


@lru_cache(maxsize=128)
def _read_log(path_string: str, revision: tuple[int, int, int, int], owner: str, platform: str) -> tuple[tuple[float, dict[str, Any]], ...]:
    path = Path(path_string)
    try:
        with path.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != revision:
                return ()
            offset = max(0, before.st_size - MAX_TAIL_BYTES)
            handle.seek(offset)
            content = handle.read(MAX_TAIL_BYTES)
        if offset:
            content = content.partition(b"\n")[2]
    except OSError:
        return ()
    reports = []
    for line in content.splitlines():
        if len(line) > MAX_REPORT_BYTES or b"UTFTLeagueFoundationClient::PostEogStatsBlock: Query Start" not in line:
            continue
        try:
            event = _EVENT.fullmatch(line.decode("utf-8"))
            if event is None:
                continue
            ended_at = datetime.strptime(event["time"], "%Y.%m.%d-%H.%M.%S:%f").replace(tzinfo=UTC).timestamp()
            report = _report(json.loads(event["body"]), owner, platform, ended_at)
        except (ValueError, TypeError, OverflowError, RecursionError):
            continue
        if report is not None:
            reports.append((ended_at, report))
    return tuple(reports)


def _standalone_report(directory: Path, ended: Mapping[int, float], owner: str, platform: str) -> tuple[float, dict[str, Any]] | None:
    """The stats file of a game the standalone client logged as finished."""
    for game_id, ended_at in sorted(ended.items(), key=lambda item: item[1], reverse=True)[:1]:
        payload = read_stats_file(directory / "TFTEoGStats.json", game_id)
        report = _report(payload, owner, platform, ended_at) if payload is not None else None
        return (ended_at, report) if report is not None else None
    return None


def read_tft_local_history(
    puuid: str, platform: str, *, limit: int = 20,
    directory: Path | None = None, now: float | None = None,
) -> list[dict[str, Any]]:
    """Recover completed owned games without a client or a network request."""
    if not isinstance(puuid, str) or not puuid or _text(puuid, 256) != puuid or not platform_match_id(1, platform):
        return []
    if type(limit) is not int or limit <= 0:
        return []
    observed_now = time.time() if now is None else _number(now, 0, 10**12)
    if observed_now is None:
        return []
    if directory is None:
        local = os.environ.get("LOCALAPPDATA")
        if not local:
            return []
        directory = Path(local) / "TFT" / "Saved" / "Logs"
    candidates = []
    try:
        for path in directory.iterdir():
            if path.name != "TFT.log" and not re.fullmatch(r"TFT-backup-\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}\.log", path.name):
                continue
            try:
                info = path.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_size > 0 and -5 <= observed_now - info.st_mtime <= MAX_AGE_SECONDS:
                candidates.append((info.st_mtime, path, (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)))
    except OSError:
        return []
    found: dict[str, tuple[float, dict[str, Any]]] = {}
    ended: dict[int, float] = {}
    for _, path, revision in sorted(candidates, key=lambda item: item[0], reverse=True)[:MAX_LOG_FILES]:
        state = read_log_state(path)
        if state is not None:
            ended.update(state.ended)
        for ended_at, report in _read_log(str(path), revision, puuid, platform):
            if not -5 <= observed_now - ended_at <= MAX_AGE_SECONDS or report["played_at"] <= 0:
                continue
            previous = found.get(report["id"])
            if previous is None or ended_at > previous[0]:
                found[report["id"]] = (ended_at, report)
    standalone = _standalone_report(directory, ended, puuid, platform)
    if standalone is not None:
        ended_at, report = standalone
        if -5 <= observed_now - ended_at <= MAX_AGE_SECONDS and report["played_at"] > 0 and report["id"] not in found:
            found[report["id"]] = standalone
    ordered = sorted(found.values(), key=lambda item: item[1]["played_at"], reverse=True)
    return [deepcopy(report) for _, report in ordered[:min(limit, 20)]]

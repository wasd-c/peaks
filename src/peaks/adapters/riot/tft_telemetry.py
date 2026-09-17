"""Read TFT's periodically refreshed match snapshot without returning identities.

The current TFT engine rewrites TFTEoGStats.json during play as well as at match
end. Its filename alone does not establish freshness; bind each read to the
active game's ID, queue and owned player before accepting the health value.
"""

from __future__ import annotations

import json
import math
import os
import re
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_SNAPSHOT_BYTES = 1024 * 1024
MAX_SNAPSHOT_AGE_SECONDS = 180
MAX_FUTURE_SECONDS = 5


@dataclass(frozen=True, slots=True)
class TftHealthSnapshot:
    health: int | float
    game_time: float | None
    observed_at: float


@dataclass(frozen=True, slots=True)
class TftPlayerSnapshot:
    health: int | float | None = None
    standing: int | None = None
    board_units: int | None = None
    augment_count: int | None = None
    level: int | None = None
    # Normalized group index, never an upstream identifier.
    duo: int | None = None

    def stats(self, observed_at: float) -> dict[str, int | float]:
        values = {
            "health": self.health, "standing": self.standing,
            "boardUnits": self.board_units, "augmentCount": self.augment_count,
            "level": self.level,
        }
        result: dict[str, int | float] = {key: value for key, value in values.items() if value is not None}
        if result:
            result["observedAt"] = observed_at
        return result


@dataclass(frozen=True, slots=True)
class TftMatchSnapshot:
    # Same order as the caller's visible roster. Missing/ambiguous players stay
    # None, preventing a file's array position from becoming an identity match.
    players: tuple[TftPlayerSnapshot | None, ...]
    game_time: float | None
    observed_at: float


def _identifier(value: object, maximum: int) -> int | None:
    if isinstance(value, str):
        if not re.fullmatch(r"[1-9][0-9]{0,18}", value):
            return None
        value = int(value)
    return value if type(value) is int and 0 < value <= maximum else None


def _number(value: object, maximum: int) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if 0 <= value <= maximum and math.isfinite(value) else None


def _revision(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def _read_snapshot(
    game_id: object,
    queue_id: object,
    own_puuid: object,
    *,
    path: Path | None = None,
    now: float | None = None,
) -> tuple[dict[str, Any], float] | None:
    match = _identifier(game_id, 2**63 - 1)
    queue = _identifier(queue_id, 1_000_000)
    if match is None or queue is None or not isinstance(own_puuid, str):
        return None
    if not 1 <= len(own_puuid) <= 256 or own_puuid.strip() != own_puuid:
        return None
    if any(ord(character) < 32 or 127 <= ord(character) <= 159 for character in own_puuid):
        return None

    observed_now = time.time() if now is None else now
    if isinstance(observed_now, bool) or not isinstance(observed_now, (int, float)):
        return None
    if not 0 <= observed_now <= 10**12 or not math.isfinite(observed_now):
        return None
    if path is None:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        path = Path(local_app_data) / "TFT" / "Saved" / "Logs" / "TFTEoGStats.json"

    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SNAPSHOT_BYTES:
            return None
        age = observed_now - before.st_mtime
        if not -MAX_FUTURE_SECONDS <= age <= MAX_SNAPSHOT_AGE_SECONDS:
            return None
        with path.open("rb") as handle:
            content = handle.read(MAX_SNAPSHOT_BYTES + 1)
        after = path.stat()
        if len(content) != before.st_size or _revision(before) != _revision(after):
            return None
        payload = json.loads(content)
    except (OSError, ValueError, RecursionError):
        return None

    if not isinstance(payload, dict):
        return None
    # The client writes actual integer identifiers, unlike presentation-layer
    # strings accepted from the caller. Booleans and coerced file values fail.
    if type(payload.get("gameId")) is not int or payload["gameId"] != match:
        return None
    if type(payload.get("queueId")) is not int or payload["queueId"] != queue:
        return None
    block = payload.get("statsBlock")
    if not isinstance(block, dict):
        return None
    players = block.get("players")
    if not isinstance(players, list) or not 1 <= len(players) <= 32:
        return None
    if any(not isinstance(player, dict) for player in players):
        return None
    selves = [player for player in players if player.get("PUUID") == own_puuid]
    if len(selves) != 1:
        return None
    return block, before.st_mtime


def read_tft_health(
    game_id: object,
    queue_id: object,
    own_puuid: object,
    *,
    path: Path | None = None,
    now: float | None = None,
) -> TftHealthSnapshot | None:
    """Compatibility projection: fresh self HP, without identities or sentinels."""
    snapshot = _read_snapshot(game_id, queue_id, own_puuid, path=path, now=now)
    if snapshot is None:
        return None
    block, observed_at = snapshot
    owned = next(player for player in block["players"] if player.get("PUUID") == own_puuid)
    health = _number(owned.get("health"), 1000)
    if health is None:
        return None
    elapsed = _number(block.get("gameLengthSeconds"), 86_400)
    return TftHealthSnapshot(
        health=health,
        game_time=float(elapsed) if elapsed is not None else None,
        observed_at=observed_at,
    )


def read_tft_match(
    game_id: object,
    queue_id: object,
    own_puuid: object,
    visible_puuids: tuple[str | None, ...],
    *,
    path: Path | None = None,
    now: float | None = None,
) -> TftMatchSnapshot | None:
    """Project only requested, uniquely identified members of the active match.

    The caller must require a live TFT session and pass None for hidden players.
    No names or identifiers leave this boundary. Standing is the current order,
    not a final placement. The game may refresh this file between rounds.
    """
    if not isinstance(visible_puuids, tuple) or not 1 <= len(visible_puuids) <= 32:
        return None
    if any(subject is not None and (not isinstance(subject, str) or not 1 <= len(subject) <= 256) for subject in visible_puuids):
        return None
    if visible_puuids.count(own_puuid) != 1:
        return None
    snapshot = _read_snapshot(game_id, queue_id, own_puuid, path=path, now=now)
    if snapshot is None:
        return None
    block, observed_at = snapshot
    rows = block["players"]
    subjects = [player.get("PUUID") for player in rows]
    groups: dict[int, list[str]] = {}
    if _identifier(queue_id, 1_000_000) in {1150, 1160}:
        for player in rows:
            group = player.get("partnerGroupId")
            subject = player.get("PUUID")
            if type(group) is int and 1 <= group <= 255 and isinstance(subject, str):
                groups.setdefault(group, []).append(subject)
    valid_groups = [members for _, members in sorted(groups.items()) if len(members) == 2 and all(subjects.count(subject) == 1 and visible_puuids.count(subject) == 1 for subject in members)]
    # Require the complete four-pair partition. An all-zero default or partial
    # payload cannot overwrite the existing, verified lobby pairings.
    duo_indices = {subject: index for index, pair in enumerate(valid_groups) for subject in pair} if len(rows) == 8 and len(valid_groups) == 4 else {}
    projected: list[TftPlayerSnapshot | None] = []
    for subject in visible_puuids:
        if subject is None or subjects.count(subject) != 1 or visible_puuids.count(subject) != 1:
            projected.append(None)
            continue
        row = rows[subjects.index(subject)]
        raw_health = row.get("health")
        health = _number(raw_health, 1000)
        # Eliminations in captured files can overshoot zero. -99 is also used
        # for players whose game ended (including the winner), so omit it.
        if isinstance(raw_health, (int, float)) and not isinstance(raw_health, bool) and -98 <= raw_health < 0:
            health = 0
        standing = row.get("ffaStanding")
        level = row.get("level")
        board = row.get("boardPieces")
        augments = row.get("augments")
        projected.append(TftPlayerSnapshot(
            health=health,
            standing=standing if type(standing) is int and 1 <= standing <= len(rows) else None,
            board_units=len(board) if isinstance(board, list) and len(board) <= 64 and all(isinstance(unit, dict) for unit in board) else None,
            # Empty augment arrays were recorded even in finished normal games;
            # they do not reliably mean that the player has zero augments.
            augment_count=len(augments) if isinstance(augments, list) and 1 <= len(augments) <= 16 and all(isinstance(item, (str, dict)) and bool(item) for item in augments) else None,
            level=level if type(level) is int and 1 <= level <= 20 else None,
            duo=duo_indices.get(subject),
        ))
    elapsed = _number(block.get("gameLengthSeconds"), 86_400)
    return TftMatchSnapshot(tuple(projected), float(elapsed) if elapsed is not None else None, observed_at)

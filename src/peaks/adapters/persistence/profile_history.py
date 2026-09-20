"""Local, non-secret observations and lightweight accumulated match history."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from peaks.domain.models import Game, _decode_datetime

HISTORY_LIMIT = 10_000


def observe_profile(database: Any, account_id: str, kind: str, value: dict[str, Any], *, now: datetime | None = None) -> None:
    """Record actual observations; polling cannot create duplicate streak days."""
    observed = (now or datetime.now().astimezone()).astimezone()
    game = ""
    if kind == "connection":
        clean: dict[str, Any] = {}
    elif kind == "identity":
        name = value.get("riotId")
        if not isinstance(name, str) or "#" not in name or len(name) > 128 or any(ord(c) < 32 for c in name):
            return
        clean = {"riotId": name}
    elif kind == "rank":
        game = Game.parse(value["game"]).label
        rating = value.get("rating")
        if type(rating) is not int or not 0 <= rating <= 1_000_000:
            return
        clean = {"game": game, "tier": str(value.get("tier", ""))[:32], "division": str(value.get("division") or "")[:8], "rating": rating}
    else:
        raise ValueError("Unsupported profile observation")
    encoded = json.dumps(clean, ensure_ascii=False, sort_keys=True)
    with database._lock:
        previous = database._execute(
            "SELECT value_json, day FROM profile_observations WHERE account_id=? AND kind=? AND game=? ORDER BY event_id DESC LIMIT 1",
            (account_id, kind, game),
        ).fetchone()
        day = observed.date().isoformat()
        if previous is not None and (previous['day'] == day if kind == 'connection' else previous['value_json'] == encoded):
            return
        database._execute(
            "INSERT INTO profile_observations(account_id, kind, game, observed_at, day, value_json) VALUES (?, ?, ?, ?, ?, ?)",
            (account_id, kind, game, observed.timestamp() * 1000, day, encoded),
        )


def profile_activity(database: Any, account_id: str) -> dict[str, Any]:
    rows = database._execute(
        "SELECT match_id, game, played_at, result, queue, map_name, duration_seconds, rank_delta FROM matches WHERE account_id=? ORDER BY played_at DESC LIMIT ?",
        (account_id, HISTORY_LIMIT),
    ).fetchall()
    total = database._execute("SELECT COUNT(*) FROM matches WHERE account_id=?", (account_id,)).fetchone()[0]
    matches = []
    for row in rows:
        started = _decode_datetime(row['played_at'])
        if started is None:
            continue
        matches.append({
            "id": row['match_id'], "game": Game.parse(row['game']).label,
            "playedAtTimestamp": started.timestamp() * 1000,
            "durationSeconds": row['duration_seconds'], "result": row['result'],
            "mode": row['queue'], "map": row['map_name'], "delta": str(row['rank_delta']) if row['rank_delta'] is not None else None,
        })
    events = database._execute(
        "SELECT kind, observed_at, day, value_json FROM profile_observations WHERE account_id=? ORDER BY event_id DESC LIMIT ?",
        (account_id, HISTORY_LIMIT),
    ).fetchall()
    return {
        "matches": matches, "totalStoredMatches": total, "historyLimit": HISTORY_LIMIT,
        "connectionDays": sorted({row['day'] for row in events if row['kind'] == 'connection'}),
        "identities": [{**json.loads(row['value_json']), "observedAt": row['observed_at']} for row in reversed(events) if row['kind'] == 'identity'],
        "ranks": [{**json.loads(row['value_json']), "observedAt": row['observed_at']} for row in reversed(events) if row['kind'] == 'rank'],
    }

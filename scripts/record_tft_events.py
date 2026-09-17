"""Passive, bounded TFT log/client diagnostics without private payloads.

No raw log lines, credentials, Riot IDs, chat or screenshots are recorded.
Create STOP in the output directory to stop gracefully. Reading logs does not
control the game or require an API key.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import secrets
import sys
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from peaks.adapters.riot.client import RiotClientError  # noqa: E402
from peaks.adapters.riot.league import LeagueClient  # noqa: E402

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_READ_BYTES = 1024 * 1024
SIGNALS = re.compile(
    r"\b(health|hp|damage|round|stage|combat|planning|carousel|gold|currency|economy|"
    r"level|experience|xp|augment|item|unit|champion|tactician|board|bench|shop|"
    r"win|loss|streak|placement|standing|eliminated|elimination|gameover|gameend|"
    r"connection|reconnect|disconnect)\b", re.I,
)
NUMBERS = re.compile(
    r"\b(health|currentHealth|maxHealth|remainingHealth|hp|damage|round|roundIndex|"
    r"stage|gold|currentGold|level|experience|xp|placement|ffaStanding|standing|"
    r"streak|partnerGroupId)[\"']?\s*[:=]\s*[\"']?(-?\d{1,6}(?:\.\d{1,6})?)(?![\d.])\b",
    re.I,
)
PRIVATE = re.compile(r"\b(?:authorization|password|cookie|bearer|access.token|refresh.token|chat|whisper)\b", re.I)
PHASES = frozenset({"None", "Lobby", "Matchmaking", "ReadyCheck", "ChampSelect", "GameStart", "InProgress", "Reconnect", "WaitingForStats", "PreEndOfGame", "EndOfGame", "TerminatedInError"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def number(value: object, *, minimum: float = 0, maximum: float = 1_000_000) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value if minimum <= value <= maximum else None


def project_log_line(line: str) -> dict[str, object] | None:
    """Save fixed signal names and named numbers, never neighboring text."""
    if len(line) > 65536 or PRIVATE.search(line):
        return None
    signals = sorted({item.casefold() for item in SIGNALS.findall(line)})
    numbers = [{"field": key.casefold(), "value": float(value) if "." in value else int(value)} for key, value in NUMBERS.findall(line)[:32]]
    if not signals and not numbers:
        return None
    stamp = re.match(r"^\[([\d.:-]{15,30})\]", line)
    return {"sourceTime": stamp[1] if stamp else None, "signals": signals, "numbers": numbers}


def project_eog(payload: object, *, alias: Any, own_puuid: str | None = None) -> dict[str, object] | None:
    """Project the TFT stats file, which can refresh during an active match."""
    if not isinstance(payload, Mapping):
        return None
    block = payload.get("statsBlock")
    if not isinstance(block, Mapping) or not isinstance(block.get("players"), list):
        return None
    players = []
    for row in block["players"][:32]:
        if not isinstance(row, Mapping):
            continue
        identifier = row.get("PUUID") or row.get("puuid")
        entry: dict[str, object] = {"self": bool(own_puuid and identifier == own_puuid)}
        if isinstance(identifier, str) and 0 < len(identifier) <= 256:
            entry["player"] = alias(identifier)
        for key in ("health", "ffaStanding", "partnerGroupId", "level"):
            value = number(row.get(key), maximum=255)
            if value is not None:
                entry[key] = value
        for key in ("augments", "boardPieces"):
            if isinstance(row.get(key), list):
                entry[key + "Count"] = len(row[key])
        players.append(entry)
    return {"queueId": number(payload.get("queueId")), "match": alias(str(payload.get("gameId"))) if payload.get("gameId") else None,
            "gameLengthSeconds": number(block.get("gameLengthSeconds")), "players": players}


def project_tft_snapshot(
    payload: object, *, alias: Any, session: object,
    own_puuid: str | None = None, initial: bool = False,
) -> dict[str, object] | None:
    """Bind a periodic file snapshot to the latest observed active session.

    TFTEoGStats.json is the source filename, not an assertion that play ended.
    Current TFT builds also update this file while the match is InProgress.
    """
    stats = project_eog(payload, alias=alias, own_puuid=own_puuid)
    if stats is None:
        return None
    current = (
        isinstance(session, Mapping)
        and session.get("phase") == "InProgress"
        and session.get("gameClientRunning") is True
        and stats.get("match") is not None
        and stats.get("match") == session.get("match")
        and stats.get("queueId") is not None
        and stats.get("queueId") == session.get("queueId")
    )
    return {"source": "TFTEoGStats.json", "initialSnapshot": initial, "currentMatch": current, "stats": stats}


def project_flow(payload: object, *, alias: Any) -> dict[str, object] | None:
    if not isinstance(payload, Mapping):
        return None
    data = payload.get("gameData") if isinstance(payload.get("gameData"), Mapping) else {}
    queue = data.get("queue") if isinstance(data.get("queue"), Mapping) else {}
    game_client = payload.get("gameClient") if isinstance(payload.get("gameClient"), Mapping) else {}
    phase = payload.get("phase")
    return {"phase": phase if isinstance(phase, str) and phase in PHASES else "unknown", "queueId": number(queue.get("id")),
            "match": alias(str(data["gameId"])) if data.get("gameId") else None,
            "gameClientRunning": game_client.get("running") is True,
            "teamSizes": [len(data.get(key, [])) if isinstance(data.get(key), list) else 0 for key in ("teamOne", "teamTwo")]}


class LogTail:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.position = 0
        self.identity: tuple[int, int] | None = None
        self.partial = b""

    def read(self) -> list[dict[str, object]]:
        try:
            stat = self.path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if self.identity != identity or stat.st_size < self.position:
                self.position = max(0, stat.st_size - MAX_READ_BYTES)
                self.partial = b""
                self.identity = identity
            with self.path.open("rb") as handle:
                handle.seek(self.position)
                chunk = handle.read(MAX_READ_BYTES)
                self.position = handle.tell()
            lines = (self.partial + chunk).split(b"\n")
            self.partial = lines.pop()[-65536:]
            return [projected for line in lines if (projected := project_log_line(line.decode("utf-8", errors="replace"))) is not None]
        except OSError:
            return []


def run(output: Path, *, hours: float) -> None:
    output.mkdir(parents=True, exist_ok=False)
    (output / ".gitignore").write_text("*\n", encoding="utf-8")
    salt = secrets.token_bytes(32)
    alias = lambda value: "id-" + hashlib.sha256(salt + value.encode()).hexdigest()[:12]  # noqa: E731
    folder = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "TFT/Saved/Logs"
    tail = LogTail(folder / "TFT.log")
    log_path = output / "events.jsonl"
    counters: dict[str, int] = {}
    previous: dict[str, object] = {}
    client: LeagueClient | None = None
    own_puuid: str | None = None
    last_discovery = -999.0
    last_poll = -999.0
    last_status = -999.0
    last_eog: tuple[int, int] | None = None
    started = time.monotonic()
    written = 0

    def emit(kind: str, data: object) -> None:
        nonlocal written
        encoded = (json.dumps({"at": utc_now(), "kind": kind, "data": data}, separators=(",", ":")) + "\n").encode()
        if written + len(encoded) > MAX_FILE_BYTES:
            return
        with log_path.open("ab") as handle:
            handle.write(encoded)
        written += len(encoded)
        counters[kind] = counters.get(kind, 0) + 1

    emit("recorder_started", {"pid": os.getpid(), "durationHours": hours, "logAvailable": tail.path.is_file(), "startupTail": True})
    try:
        while time.monotonic() - started < hours * 3600 and written < MAX_FILE_BYTES - 65536 and not (output / "STOP").exists():
            now = time.monotonic()
            for row in tail.read():
                emit("tft_log_signal", row)
            if now - last_discovery >= 60:
                if client:
                    client.close()
                client = LeagueClient.from_discovery()
                last_discovery = now
            if now - last_poll >= 3 and client and client.lcu_http:
                last_poll = now
                try:
                    projected = project_flow(client.lcu_http.get_json("/lol-gameflow/v1/session"), alias=alias)
                    if projected != previous.get("flow"):
                        emit("client_session", projected)
                        previous["flow"] = projected
                    own = client.lcu_http.get_json("/lol-summoner/v1/current-summoner")
                    own_puuid = own.get("puuid") if isinstance(own, Mapping) else None
                except RiotClientError as exc:
                    state = {"status": exc.status_code, "error": type(exc).__name__}
                    if state != previous.get("client_error"):
                        emit("client_unavailable", state)
                        previous["client_error"] = state
            try:
                filename = folder / "TFTEoGStats.json"
                stat = filename.stat()
                identity = (stat.st_mtime_ns, stat.st_size)
                if identity != last_eog and stat.st_size <= MAX_READ_BYTES:
                    projected_eog = project_tft_snapshot(
                        json.loads(filename.read_text(encoding="utf-8")), alias=alias,
                        own_puuid=own_puuid, session=previous.get("flow"), initial=last_eog is None,
                    )
                    if projected_eog is not None:
                        emit("tft_stats_snapshot", projected_eog)
                        last_eog = identity
            except (OSError, ValueError):
                pass
            if now - last_status >= 10:
                status = {"pid": os.getpid(), "updatedAt": utc_now(), "elapsedSeconds": round(now - started), "bytes": written, "events": counters, "running": True}
                temporary = output / "status.tmp"
                temporary.write_text(json.dumps(status), encoding="utf-8")
                temporary.replace(output / "status.json")
                last_status = now
            time.sleep(0.5)
    finally:
        if client:
            client.close()
        emit("recorder_stopped", {"events": dict(counters)})
        (output / "status.json").write_text(json.dumps({"pid": os.getpid(), "updatedAt": utc_now(), "events": counters, "running": False}), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hours", type=float, default=6)
    options = parser.parse_args()
    run(options.output, hours=max(0.01, min(options.hours, 12)))

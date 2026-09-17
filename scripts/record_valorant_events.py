"""Bounded, redacted recording of Riot's native events for one play session.

This is a diagnostic tool, not a live K/D estimator. No raw websocket frames,
log lines, names, credentials, chat messages, or screenshots are saved.
Run from the repository's Python environment. Create STOP in the output folder
to stop gracefully; a duration and file-size limit also stop the recorder.
"""

from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import os
import re
import secrets
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from peaks.adapters.riot.client import RiotClientHTTP  # noqa: E402
from peaks.adapters.riot.discovery import default_paths, discover_riot_client  # noqa: E402
from scripts.riot_event_projection import project_game_notification  # noqa: E402

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
LOG_SIGNALS = re.compile(
    r"\b(kill(?:ed|s|feed)?|death(?:s)?|assist(?:s)?|headshots?|scoreboard|round|damage|health|"
    r"Reconcile|OnRoundEnded|OnRoundStarted|WaitingToStart|WaitingToPostMatch|InProgress|InGame|MainMenu|"
    r"(?:on)?(?:spike|bomb)[_-]?(?:plant(?:ed|ing)?|defus(?:e|ed|ing)|detonat(?:e|ed|ion)|explod(?:e|ed)|explosion)|"
    r"spike|bomb|plant(?:ed|ing)?|defus(?:e|ed|ing)|detonat(?:e|ed|ion)|"
    r"round[_-]?(?:phase|time|timer)|buy[_-]?phase|combat|shopping|warmup|overtime|"
    r"(?:weapon[_-]?)?(?:fire|fired|firing|reload(?:ed|ing)?|equip(?:ped|ping)?)|"
    r"(?:on)?ability[_-]?(?:cast|activated|activation|used)|ultimate[_-]?(?:cast|ready|points|charge)|"
    r"ult[_-]?(?:points|charge)|ability|ultimate|"
    r"economy|credits|armor|armour|shield|money|purchase|purchased|buy|sell|"
    r"(?:on)?damage[_-]?(?:dealt|received|taken)|kill[_-]?feed|"
    r"ping|rtt|latency|fps|frame[_-]?(?:rate|time)|packet[_-]?loss|packets[_-]?(?:lost|sent|received))\b",
    re.I,
)
VO_MARKER = re.compile(r"\bPlay_VO_[A-Za-z0-9_]{1,180}\b")
LOG_NUMBER = re.compile(
    r'\b(kills?|deaths?|assists?|headshots?|score|round[_-]?(?:number|index|count|time|timer)?|'
    r'health|hp|damage(?:[_-]?(?:dealt|received|taken))?|credits|money|armor|armour|shield|'
    r'ammo|magazine(?:[_-]?ammo)?|reserve[_-]?ammo|ult(?:imate)?[_-]?(?:points|charge|max)|'
    r'ability[_-]?(?:charges|cooldown)|cooldown|ping(?:[_-]?ms)?|rtt|latency(?:[_-]?ms)?|'
    r'fps|frame[_-]?(?:rate|time)|packet[_-]?loss(?:[_-]?(?:pct|percent))?|'
    r'packets[_-]?(?:lost|sent|received))["\']?\s*[:=]\s*["\']?(\d{1,6}(?:\.\d{1,6})?)(?![\d.])\b',
    re.I,
)
LOG_CATEGORY = re.compile(r"\b(Log[A-Za-z0-9_]{1,64}):")
LOG_TIME = re.compile(r"^\[([0-9.:-]{15,30})\]")
ROUTE_PARTS = frozenset(
    {
        "riot-messaging-service",
        "social",
        "chat",
        "product-session",
        "game-activity",
        "entitlements",
        "auth",
        "account",
        "accounts",
        "session",
        "sessions",
        "presences",
        "presence",
        "message",
        "messages",
        "state",
        "out-of-sync",
        "external-sessions",
        "join-intent-processing-state",
        "friends",
        "friend",
        "contacts",
        "contact",
        "conversations",
        "conversation",
        "voice",
        "token",
        "help",
        "players",
        "matches",
        "core-game",
        "pre-game",
        "party",
        "parties",
        "score",
        "kills",
        "deaths",
        "assists",
    }
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Redactor:
    def __init__(self) -> None:
        self.salt = secrets.token_bytes(32)
        self.subject: str | None = None

    def alias(self, value: str) -> str:
        return "id-" + hashlib.sha256(self.salt + value.encode()).hexdigest()[:12]

    def route(self, value: object) -> str:
        if not isinstance(value, str):
            return "unknown"
        value = value.split("?", 1)[0][:512]
        return "/".join(
            part
            if not part or part in ROUTE_PARTS or re.fullmatch(r"v[1-9][0-9]?", part)
            else self.alias(part)
            for part in value.split("/")
        )

    def project(self, value: object) -> object:
        return project_game_notification(value, alias=self.alias, subject=self.subject)

    def presence(self, payload: object) -> object:
        if not isinstance(payload, dict):
            return {"type": "presence"}
        rows = payload.get("presences", [payload] if "puuid" in payload else [])
        if not isinstance(rows, list):
            return {"type": "presence"}
        result: dict[str, object] = {"count": len(rows)}
        for row in rows[:512]:
            if (
                not isinstance(row, dict)
                or not self.subject
                or row.get("puuid") != self.subject
                or row.get("product") != "valorant"
            ):
                continue
            private = row.get("private")
            if not isinstance(private, str) or len(private) > 65536:
                continue
            try:
                decoded = json.loads(base64.b64decode(private, validate=True))
            except (ValueError, UnicodeError, RecursionError):
                continue
            result["self"] = self.project(decoded)
            break
        return result


def project_log_line(line: str) -> dict[str, object] | None:
    """Keep only known technical markers and named gameplay numeric fields."""
    markers = VO_MARKER.findall(line)
    signals = sorted({value.lower() for value in LOG_SIGNALS.findall(line)})
    numbers = [
        {"field": key.lower(), "value": float(value) if "." in value else int(value)}
        for key, value in LOG_NUMBER.findall(line)[:32]
    ]
    if not markers and not signals and not numbers:
        return None
    category = LOG_CATEGORY.search(line)
    timestamp = LOG_TIME.search(line)
    return {
        "category": category[1] if category else "unknown",
        "gameTime": timestamp[1] if timestamp else None,
        "markers": markers[:8],
        "signals": signals,
        "numbers": numbers,
    }


class LogTail:
    def __init__(self, filename: Path) -> None:
        self.filename = filename
        self.position: int | None = None
        self.identity: tuple[int, int] | None = None
        self.prefix: bytes | None = None
        self.pending = b""

    def read(self) -> list[str]:
        try:
            stat = self.filename.stat()
            identity = (stat.st_dev, stat.st_ino)
            with self.filename.open("rb") as source:
                prefix = source.read(128)
                if self.position is None:
                    # Existing history is excluded; newly created game logs start at 0.
                    self.position = stat.st_size
                elif (
                    identity != self.identity
                    or stat.st_size < self.position
                    or (self.prefix and prefix[: len(self.prefix)] != self.prefix)
                ):
                    self.position = 0
                    self.pending = b""
                self.identity = identity
                self.prefix = prefix
                source.seek(self.position)
                chunk = source.read(MAX_MESSAGE_BYTES)
                self.position = source.tell()
        except OSError:
            # A future file is a new session, so include its initial lines.
            self.position = 0
            return []
        pieces = (self.pending + chunk).split(b"\n")
        self.pending = pieces.pop()[:65536]
        return [piece[:65536].decode("utf-8", errors="replace") for piece in pieces]


class Recorder:
    def __init__(self, output: Path, duration_seconds: int) -> None:
        from PySide6.QtCore import QTimer

        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        self.events = (output / "events.jsonl").open("a", encoding="utf-8", buffering=1)
        self.started = time.monotonic()
        self.started_at = utc_now()
        self.duration = duration_seconds
        self.redactor = Redactor()
        self.socket: Any = None
        self.client: RiotClientHTTP | None = None
        self.connected = False
        self.lock_identity: tuple[int, int] | None = None
        self.next_connect = 0.0
        self.next_poll = 0.0
        self.next_status = 0.0
        self.next_catalog = 0.0
        self.event_names: set[str] = set()
        self.counts: collections.Counter[str] = collections.Counter()
        self.log_categories: collections.Counter[str] = collections.Counter()
        self.last_payload: dict[str, str] = {}
        self.subscriptions = 0
        self.log_tails = [LogTail(filename) for filename in default_paths().valorant_log]
        # Establish EOF before the user starts the next match/game launch.
        for tail in self.log_tails:
            tail.read()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(500)
        self.write(
            "recorder_started",
            {
                "captureVersion": 2,
                "durationSeconds": duration_seconds,
                "pid": os.getpid(),
                "mode": "native_events_and_redacted_log_signals",
            },
        )
        self.tick()

    def write(self, kind: str, payload: object, *, deduplicate: bool = False) -> None:
        self.counts[kind] += 1
        if deduplicate:
            signature = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            if self.last_payload.get(kind) == signature:
                return
            if len(self.last_payload) < 2048 or kind in self.last_payload:
                self.last_payload[kind] = signature
        self.events.write(
            json.dumps({"at": utc_now(), "kind": kind, "data": payload}, ensure_ascii=True) + "\n"
        )

    def connect(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtNetwork import QNetworkProxy, QNetworkRequest
        from PySide6.QtWebSockets import QWebSocket

        discovery = discover_riot_client()
        if discovery.lockfile is None:
            self.write("client_waiting", {"reason": discovery.reason}, deduplicate=True)
            return
        lockfile = discovery.lockfile
        identity = (lockfile.pid, lockfile.port)
        if self.socket is not None:
            self.socket.abort()
            self.socket.deleteLater()
        if self.client is not None:
            self.client.close()
        self.client = RiotClientHTTP(lockfile, timeout=3)
        self.lock_identity = identity
        names = self.read_catalog()
        if not names:
            names = ["OnJsonApiEvent"]
        self.subscriptions = len(names)
        self.write("event_catalog", {"names": names})
        socket = QWebSocket()
        self.socket = socket
        socket.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        socket.setMaxAllowedIncomingMessageSize(MAX_MESSAGE_BYTES)
        # Only the literal loopback endpoint from a PID-validated Riot lockfile.
        socket.sslErrors.connect(lambda _errors: socket.ignoreSslErrors())
        socket.connected.connect(lambda: self.on_connected(socket, names))
        socket.disconnected.connect(lambda: self.on_disconnected(socket))
        socket.textMessageReceived.connect(self.on_message)
        socket.errorOccurred.connect(lambda _error: self.on_socket_error(socket))
        request = QNetworkRequest(QUrl(f"wss://127.0.0.1:{lockfile.port}/"))
        credential = base64.b64encode(f"riot:{lockfile.password}".encode())
        request.setRawHeader(b"Authorization", b"Basic " + credential)
        socket.open(request)

    def read_catalog(self) -> list[str]:
        if self.client is None:
            return []
        try:
            help_data = self.client.get_json("/help")
            events = help_data.get("events", {}) if isinstance(help_data, dict) else {}
            return [
                name
                for name in events
                if isinstance(name, str)
                and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", name)
                and name != "OnJsonApiEvent"
            ][:1024]
        except Exception as exc:
            self.write("help_unavailable", {"errorType": type(exc).__name__}, deduplicate=True)
            return []

    def on_connected(self, socket: Any, names: list[str]) -> None:
        if socket is not self.socket:
            return
        self.connected = True
        self.event_names = set(names)
        self.next_catalog = time.monotonic() + 30
        for name in names:
            socket.sendTextMessage(json.dumps([5, name]))
        self.write("websocket_connected", {"subscriptions": len(names)})

    def on_disconnected(self, socket: Any) -> None:
        if socket is self.socket:
            self.connected = False
            self.write("websocket_disconnected", {}, deduplicate=True)

    def on_socket_error(self, socket: Any) -> None:
        if socket is self.socket:
            self.connected = False
            self.write("websocket_error", {"error": "connection_unavailable"}, deduplicate=True)

    def on_message(self, message: str) -> None:
        if not isinstance(message, str):
            self.counts["invalid_frame"] += 1
            return
        try:
            oversized = (
                len(message) > MAX_MESSAGE_BYTES
                or len(message.encode("utf-8")) > MAX_MESSAGE_BYTES
            )
        except UnicodeError:
            self.counts["invalid_frame"] += 1
            return
        if oversized:
            self.counts["oversized_frame"] += 1
            return
        if not message.strip():
            # Riot acknowledges subscriptions with an empty text frame.
            self.counts["empty_acknowledgement"] += 1
            return
        try:
            frame = json.loads(message)
        except (ValueError, RecursionError):
            self.counts["invalid_frame"] += 1
            return
        if not isinstance(frame, list) or len(frame) < 3 or frame[0] != 8:
            self.counts["other_frame"] += 1
            return
        name = (
            frame[1]
            if isinstance(frame[1], str) and frame[1] in self.event_names
            else "unknown_event"
        )
        payload = frame[2]
        # Session-salted fingerprint distinguishes changed unprojected fields
        # without persisting them. It never suppresses repeated event occurrences.
        fingerprint = self.redactor.alias(message)
        if not isinstance(payload, dict):
            self.write(
                "ws:" + name,
                {"shape": self.redactor.project(payload), "frameFingerprint": fingerprint},
            )
            return
        uri = self.redactor.route(payload.get("uri", ""))
        data = payload.get("data")
        if "/presences" in uri:
            projected = self.redactor.presence(data)
        elif uri == "/riot-messaging-service/v1/message":
            projected = project_game_notification(
                data, alias=self.redactor.alias, subject=self.redactor.subject, decode_json=True
            )
        elif re.search(
            r"auth|token|entitlement|session|account|chat|friend|contact|message|voice", uri, re.I
        ):
            projected = {"type": "omitted_private_payload"}
        else:
            projected = self.redactor.project(data)
        self.write(
            "ws:" + name,
            {
                "uri": uri,
                "eventType": self.redactor.project(payload.get("eventType")),
                "payload": projected,
                "frameFingerprint": fingerprint,
            },
        )

    def poll_presence(self) -> None:
        if self.client is None:
            return
        discovery = discover_riot_client()
        if (
            discovery.lockfile is None
            or (discovery.lockfile.pid, discovery.lockfile.port) != self.lock_identity
        ):
            self.connected = False
            return
        try:
            session = self.client.get_json("/chat/v1/session")
            subject = session.get("puuid") if isinstance(session, dict) else None
            self.redactor.subject = subject if isinstance(subject, str) else None
            presence = self.client.get_json("/chat/v4/presences")
            self.write("self_presence", self.redactor.presence(presence), deduplicate=True)
        except Exception as exc:
            error: dict[str, object] = {"errorType": type(exc).__name__}
            status_code = getattr(exc, "status_code", None)
            if type(status_code) is int and 100 <= status_code <= 599:
                error["statusCode"] = status_code
            self.write("presence_unavailable", error, deduplicate=True)

    def tick(self) -> None:
        now = time.monotonic()
        if (
            (self.output / "STOP").exists()
            or now - self.started >= self.duration
            or self.events.tell() >= MAX_FILE_BYTES
        ):
            self.stop()
            return
        if not self.connected and now >= self.next_connect:
            self.next_connect = now + 10
            try:
                self.connect()
            except Exception as exc:
                self.write(
                    "connect_unavailable", {"errorType": type(exc).__name__}, deduplicate=True
                )
        if now >= self.next_poll:
            self.next_poll = now + 10
            self.poll_presence()
        if self.connected and now >= self.next_catalog:
            self.next_catalog = now + 30
            added = set(self.read_catalog()) - self.event_names
            if added:
                for name in sorted(added):
                    self.socket.sendTextMessage(json.dumps([5, name]))
                self.event_names.update(added)
                self.subscriptions = len(self.event_names)
                self.write("event_catalog_added", {"names": sorted(added)})
        for tail in self.log_tails:
            for line in tail.read():
                self.counts["log_lines_observed"] += 1
                category = LOG_CATEGORY.search(line)
                if category:
                    self.log_categories[category[1]] += 1
                projected = project_log_line(line)
                if projected is not None:
                    self.write("log_signal", projected)
        if now >= self.next_status:
            self.next_status = now + 5
            self.save_status("recording")

    def save_status(self, state: str) -> None:
        summary = {
            "captureVersion": 2,
            "state": state,
            "pid": os.getpid(),
            "startedAt": self.started_at,
            "updatedAt": utc_now(),
            "elapsedSeconds": round(time.monotonic() - self.started),
            "maximumSeconds": self.duration,
            "websocketConnected": self.connected,
            "subscriptions": self.subscriptions,
            "eventCounts": dict(self.counts),
            "logCategories": dict(self.log_categories.most_common(100)),
            "savedBytes": self.events.tell(),
            "overwolf": False,
            "screenshots": False,
            "rawPayloadsSaved": False,
        }
        temporary = self.output / "status.tmp"
        temporary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        temporary.replace(self.output / "status.json")

    def stop(self) -> None:
        from PySide6.QtCore import QCoreApplication

        self.timer.stop()
        self.write("recorder_stopped", {})
        self.connected = False
        self.save_status("stopped")
        if self.socket is not None:
            self.socket.close()
        if self.client is not None:
            self.client.close()
        self.events.close()
        QCoreApplication.quit()


def main() -> int:
    from PySide6.QtCore import QCoreApplication

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minutes", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.minutes <= 240:
        parser.error("minutes must be between 1 and 240")
    app = QCoreApplication([sys.argv[0]])
    _recorder = Recorder(args.output.resolve(), args.minutes * 60)
    # Keep the QObject owners alive for the entire background session.
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

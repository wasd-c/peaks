"""Discovery recording for the standalone TFT client (Unreal, TFTClient.exe).

Since patch 18.6 TFT no longer runs inside the League client, so the League
gameflow and live-data endpoints the older recorder relied on are not assumed.
This recorder discovers instead of presuming:

* the Riot Client's local API: its /help catalog, every websocket event,
  decoded RMS notifications, the player session's product context and the
  external product sessions (to settle how a TFT launch must be prepared);
* TFT's own local server (RGIRemotingServer), found through
  ProgramData/Riot Games/Metadata/teamfighttactics.live/*.lockfile: its /help
  catalog, every websocket event, and periodic GETs of its parameterless
  read endpoints that look game related;
* the legacy live-data port 2999, to see whether the new client serves it;
* TFT.log (RMS resources, map travel, outgoing service calls, TFT messages)
  and TFTEoGStats.json.

Only shapes are saved: keys, numbers, enum-like strings and salted aliases of
identifiers. No credentials, names, chat, raw frames or raw log lines.
Create STOP in the output folder to stop; a duration and size limit apply.
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

from peaks.adapters.riot.client import RiotClientHTTP  # noqa: E402
from peaks.adapters.riot.discovery import RiotLockfile, discover_riot_client  # noqa: E402

MAX_FILE_BYTES = 96 * 1024 * 1024
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
PROGRAM_DATA = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
TFT_LOGS = LOCAL / "TFT" / "Saved" / "Logs"
TFT_LOCKFILE = PROGRAM_DATA / "Riot Games" / "Metadata" / "teamfighttactics.live" / "teamfighttactics.live.lockfile"

UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ENUM_VALUE = re.compile(
    r"^(?:[A-Z][A-Z0-9_]{1,63}|[A-Z][a-zA-Z]{1,40}|[a-z][a-z0-9_-]{1,40}|"
    r"(?:TFT|DA|Set)\d*_[A-Za-z0-9_]{1,80}|[A-Za-z]{1,8}_[A-Za-z0-9_]{1,80}|/[A-Za-z0-9_/.-]{1,160})$"
)
# Values that can name or identify a person are never kept, even if enum-like.
PRIVATE_KEYS = re.compile(
    r"^(?:name|alias|text|body|ip|host)$|gamename|tagline|riotid|summonername|playername|displayname|"
    r"nickname|companionname|message|chat|token|password|secret|auth|cookie|session_?id|email|"
    r"country|ipaddress|address|playerkey",
    re.I,
)
# Game content identifiers stay readable even when their key mentions a name.
PUBLIC_KEYS = re.compile(r"champion|item|unit|trait|augment|map|mode|queue|set|skin|character|piece|product|patchline|phase|state", re.I)
PRIVATE_ROUTE = re.compile(r"auth|token|entitlement|login|password|chat|friend|contact|conversation|voice|rso|purchase|store|wallet|email", re.I)
GAME_ROUTE = re.compile(r"game|match|tft|board|lobby|session|stats|live|round|stage|player|gameflow|queue|party|eog|end", re.I)
LOG_CATEGORY = re.compile(r"\]\s*([A-Za-z][A-Za-z0-9_]{1,64}):")
LOG_TIME = re.compile(r"^\[([0-9.:-]{15,30})\]")
RMS_LINE = re.compile(r"for resource '([^']{1,240})' service '([^']{1,64})' payload '(.{0,65536})'?$")
BROWSE_LINE = re.compile(r"LogNet: Browse: (?:([0-9.]+):\d+)?(/[A-Za-z0-9_/]+)")
HTTP_LINE = re.compile(r"RGIOPHttp: ([A-Za-z0-9_]+::[A-Za-z0-9_]+): Query (Start|Complete|Failed)[^|]*\|\s*([A-Z]+)\s+https?://[^/\s]+(/[^\s?|]*)")
STATUS_CODE = re.compile(r"\b(?:ResponseCode|StatusCode|Status)[:= ]+(\d{3})\b")
EMBEDDED_FIELDS = re.compile(r'\\?"(phaseName|gameState|queueId|gameId|counter|stage|round|phase|state|status|eventType|type)\\?"\s*:\s*\\?"?([A-Za-z0-9_.-]{1,64})')


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class Redactor:
    def __init__(self) -> None:
        self.salt = secrets.token_bytes(32)
        self.subject: str | None = None

    def alias(self, value: str) -> str:
        if self.subject and value == self.subject:
            return "self"
        return "id-" + hashlib.sha256(self.salt + value.encode()).hexdigest()[:12]

    def route(self, value: object) -> str:
        if not isinstance(value, str):
            return "unknown"
        parts = []
        for part in value.split("?", 1)[0][:512].split("/"):
            if UUID.match(part) or re.fullmatch(r"[0-9a-fA-F-]{20,}|\d{5,}|[A-Za-z0-9_-]{32,}", part):
                parts.append(self.alias(part))
            else:
                parts.append(part)
        return "/".join(parts)

    def shape(self, value: object, key: str = "", depth: int = 0) -> object:
        """Keep structure, numbers and enum-like strings; alias identifiers."""
        if depth > 8:
            return "<deep>"
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value if abs(value) < 10**15 else "<bignum>"
        if isinstance(value, str):
            if UUID.match(value) or (re.search(r"puuid|id$|ids$", key, re.I) and 6 <= len(value) <= 128):
                return self.alias(value)
            if PRIVATE_KEYS.search(key) and not PUBLIC_KEYS.search(key):
                return f"<str:{len(value)}>" if value else ""
            if ENUM_VALUE.match(value):
                return value
            if value[:1] in "{[" and len(value) <= MAX_MESSAGE_BYTES:
                try:
                    return {"<json>": self.shape(json.loads(value), key, depth + 1)}
                except (ValueError, RecursionError):
                    pass
            return f"<str:{len(value)}>"
        if isinstance(value, list):
            items = [self.shape(item, key, depth + 1) for item in value[:4]]
            return {"<list>": len(value), "items": items} if len(value) > 4 else items
        if isinstance(value, dict):
            result = {}
            for index, (child_key, child) in enumerate(value.items()):
                if index >= 96:
                    result["<more>"] = len(value) - 96
                    break
                safe_key = str(child_key)[:80]
                if UUID.match(safe_key):
                    safe_key = self.alias(safe_key)
                result[safe_key] = self.shape(child, safe_key, depth + 1)
            return result
        return f"<{type(value).__name__}>"


def read_tft_lockfile() -> RiotLockfile | None:
    try:
        fields = TFT_LOCKFILE.read_text(encoding="utf-8").strip().split(":")
    except OSError:
        return None
    if len(fields) != 5 or not fields[1].isdigit() or not fields[2].isdigit() or fields[4] not in {"http", "https"}:
        return None
    pid, port = int(fields[1]), int(fields[2])
    try:
        import psutil

        process_name = psutil.Process(pid).name()
    except Exception:
        return None
    # Only trust the lockfile while the process it names is a running TFT binary.
    if "tft" not in process_name.casefold() or not 1 <= port <= 65535:
        return None
    return RiotLockfile(name=fields[0][:64], pid=pid, port=port, password=fields[3], protocol=fields[4])


class LogTail:
    def __init__(self, filename: Path) -> None:
        self.filename = filename
        self.position: int | None = None
        self.identity: tuple[int, int] | None = None
        self.pending = b""

    def read(self) -> list[str]:
        try:
            stat = self.filename.stat()
            identity = (stat.st_dev, stat.st_ino)
            with self.filename.open("rb") as source:
                if self.position is None:
                    self.position = stat.st_size  # history before the recording is excluded
                elif identity != self.identity or stat.st_size < self.position:
                    self.position = 0  # TFT rotated its log at client start
                    self.pending = b""
                self.identity = identity
                source.seek(self.position)
                chunk = source.read(MAX_MESSAGE_BYTES)
                self.position = source.tell()
        except OSError:
            self.position = 0
            return []
        pieces = (self.pending + chunk).split(b"\n")
        self.pending = pieces.pop()[:131072]
        return [piece[:131072].decode("utf-8", errors="replace") for piece in pieces]


class Channel:
    """One local Riot API (Riot Client or TFT) and its websocket."""

    def __init__(self, recorder: Recorder, label: str) -> None:
        self.recorder = recorder
        self.label = label
        self.lockfile: RiotLockfile | None = None
        self.client: RiotClientHTTP | None = None
        self.socket: Any = None
        self.connected = False
        self.events: set[str] = set()
        self.get_endpoints: list[str] = []

    def identity(self) -> tuple[int, int] | None:
        return (self.lockfile.pid, self.lockfile.port) if self.lockfile else None

    def ensure(self, lockfile: RiotLockfile | None) -> None:
        if lockfile is None:
            if self.lockfile is not None:
                self.recorder.write(f"{self.label}:gone", {})
                self.close()
            return
        if (lockfile.pid, lockfile.port) == self.identity() and self.connected:
            return
        self.close()
        self.lockfile = lockfile
        self.client = RiotClientHTTP(lockfile, timeout=3)
        self.read_catalog()
        self.open_socket()

    def read_catalog(self) -> None:
        assert self.client is not None
        try:
            catalog = self.client.get_json("/help")
        except Exception as exc:
            self.recorder.write(f"{self.label}:help_unavailable", {"errorType": type(exc).__name__, "status": getattr(exc, "status_code", None)})
            return
        if not isinstance(catalog, dict):
            return
        events = catalog.get("events") if isinstance(catalog.get("events"), dict) else {}
        functions = catalog.get("functions") if isinstance(catalog.get("functions"), dict) else {}
        self.events = {name for name in events if isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", name)}
        self.recorder.save_catalog(self.label, catalog)
        self.recorder.write(f"{self.label}:catalog", {"events": len(events), "functions": len(functions), "types": len(catalog.get("types") or {})})
        # Riot's /help names functions "GetFooV1"; the HTTP route needs /help?format=Full.
        try:
            full = self.client.get_json("/help?format=Full")
        except Exception:
            full = None
        routes: list[str] = []
        if isinstance(full, dict):
            for item in full.get("functions", []) if isinstance(full.get("functions"), list) else []:
                if not isinstance(item, dict):
                    continue
                url, method = item.get("url"), str(item.get("http_method") or item.get("method") or "").upper()
                if isinstance(url, str) and method == "GET" and "{" not in url and GAME_ROUTE.search(url) and not PRIVATE_ROUTE.search(url):
                    routes.append(url)
            self.recorder.save_catalog(self.label + "_full", full)
        self.get_endpoints = sorted(set(routes))[:60]
        self.recorder.write(f"{self.label}:readable_endpoints", {"count": len(self.get_endpoints), "routes": self.get_endpoints})

    def open_socket(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtNetwork import QNetworkProxy, QNetworkRequest
        from PySide6.QtWebSockets import QWebSocket

        assert self.lockfile is not None
        names = sorted(self.events - {"OnJsonApiEvent"})[:2048] or ["OnJsonApiEvent"]
        socket = QWebSocket()
        self.socket = socket
        socket.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        socket.setMaxAllowedIncomingMessageSize(MAX_MESSAGE_BYTES)
        socket.sslErrors.connect(lambda _errors: socket.ignoreSslErrors())  # loopback self-signed cert
        socket.connected.connect(lambda: self.on_connected(socket, names))
        socket.disconnected.connect(lambda: self.on_down(socket, "disconnected"))
        socket.errorOccurred.connect(lambda _error: self.on_down(socket, "error"))
        socket.textMessageReceived.connect(self.on_message)
        scheme = "wss" if self.lockfile.protocol == "https" else "ws"
        request = QNetworkRequest(QUrl(f"{scheme}://127.0.0.1:{self.lockfile.port}/"))
        request.setRawHeader(b"Authorization", b"Basic " + base64.b64encode(f"riot:{self.lockfile.password}".encode()))
        socket.open(request)

    def on_connected(self, socket: Any, names: list[str]) -> None:
        if socket is not self.socket:
            return
        self.connected = True
        for name in names:
            socket.sendTextMessage(json.dumps([5, name]))
        self.recorder.write(f"{self.label}:websocket_connected", {"subscriptions": len(names)})

    def on_down(self, socket: Any, reason: str) -> None:
        if socket is self.socket and self.connected:
            self.connected = False
            self.recorder.write(f"{self.label}:websocket_{reason}", {})

    def on_message(self, message: str) -> None:
        recorder = self.recorder
        if not isinstance(message, str) or not message.strip() or len(message) > MAX_MESSAGE_BYTES:
            return
        try:
            frame = json.loads(message)
        except (ValueError, RecursionError):
            return
        if not isinstance(frame, list) or len(frame) < 3 or frame[0] != 8:
            return
        name = frame[1] if isinstance(frame[1], str) and len(frame[1]) <= 256 else "unknown"
        payload = frame[2]
        if not isinstance(payload, dict):
            recorder.write(f"{self.label}:ws", {"event": name, "payload": recorder.redactor.shape(payload)})
            return
        uri = recorder.redactor.route(payload.get("uri", ""))
        data = payload.get("data")
        if "/presences" in uri:
            projected = recorder.presence(data)
        elif "riot-messaging-service" in uri and isinstance(data, dict):
            projected = recorder.rms(data)
        elif PRIVATE_ROUTE.search(uri) and "product-context" not in uri:
            projected = {"omitted": "private"}
        else:
            projected = recorder.redactor.shape(data)
        recorder.write(f"{self.label}:ws", {"event": name, "uri": uri, "eventType": payload.get("eventType"), "payload": projected}, dedupe_key=f"{self.label}:{uri}")

    def poll_endpoints(self) -> None:
        if self.client is None:
            return
        for route in self.get_endpoints:
            try:
                value: object = self.recorder.redactor.shape(self.client.get_json(route))
            except Exception as exc:
                value = {"errorType": type(exc).__name__, "status": getattr(exc, "status_code", None)}
            self.recorder.write(f"{self.label}:get", {"route": route, "value": value}, dedupe_key=f"get:{self.label}:{route}")

    def close(self) -> None:
        if self.socket is not None:
            self.socket.abort()
            self.socket.deleteLater()
        if self.client is not None:
            self.client.close()
        self.socket = self.client = self.lockfile = None
        self.connected = False


class Recorder:
    def __init__(self, output: Path, duration_seconds: int) -> None:
        from PySide6.QtCore import QTimer

        self.output = output
        (output / "catalogs").mkdir(parents=True, exist_ok=True)
        (output / ".gitignore").write_text("*\n", encoding="utf-8")
        self.events = (output / "events.jsonl").open("a", encoding="utf-8", buffering=1)
        self.started = time.monotonic()
        self.started_at = utc_now()
        self.duration = duration_seconds
        self.redactor = Redactor()
        self.counts: collections.Counter[str] = collections.Counter()
        self.log_categories: collections.Counter[str] = collections.Counter()
        self.last: dict[str, str] = {}
        self.riot = Channel(self, "riot")
        self.tft = Channel(self, "tft")
        self.tail = LogTail(TFT_LOGS / "TFT.log")
        self.tail.read()
        self.eog_identity: tuple[int, int] | None = None
        self.next = collections.defaultdict(float)
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(250)
        self.write("recorder_started", {"captureVersion": 1, "client": "standalone-tft", "durationSeconds": duration_seconds, "pid": os.getpid()})
        self.tick()

    def write(self, kind: str, payload: object, *, dedupe_key: str | None = None) -> None:
        self.counts[kind] += 1
        if dedupe_key is not None:
            signature = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
            if self.last.get(dedupe_key) == signature:
                self.counts[kind + ":unchanged"] += 1
                return
            self.last[dedupe_key] = signature
        if self.events.tell() < MAX_FILE_BYTES:
            self.events.write(json.dumps({"at": utc_now(), "kind": kind, "data": payload}, ensure_ascii=True, default=str) + "\n")

    def save_catalog(self, label: str, catalog: object) -> None:
        # Catalogs are Riot's public API descriptions (names and types), not player data.
        (self.output / "catalogs" / f"{label}.json").write_text(json.dumps(catalog, indent=1)[:32 * 1024 * 1024], encoding="utf-8")

    def presence(self, payload: object) -> object:
        rows = payload.get("presences", [payload] if isinstance(payload, dict) and "puuid" in payload else []) if isinstance(payload, dict) else []
        result: dict[str, object] = {"count": len(rows) if isinstance(rows, list) else 0}
        for row in rows[:512] if isinstance(rows, list) else []:
            if not isinstance(row, dict) or not self.redactor.subject or row.get("puuid") != self.redactor.subject:
                continue
            entry: dict[str, object] = {"product": row.get("product"), "state": row.get("state")}
            private = row.get("private")
            if isinstance(private, str) and 0 < len(private) <= 65536:
                try:
                    entry["private"] = self.redactor.shape(json.loads(base64.b64decode(private, validate=True)))
                except (ValueError, UnicodeError, RecursionError):
                    entry["private"] = "<undecodable>"
            result.setdefault("self", []).append(entry)  # type: ignore[union-attr]
        return result

    def rms(self, data: dict[str, Any]) -> object:
        resource = self.redactor.route(data.get("resource"))
        if PRIVATE_ROUTE.search(resource):
            return {"resource": resource, "service": data.get("service"), "payload": "omitted"}
        body = data.get("payload")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except (ValueError, RecursionError):
                body = f"<str:{len(body)}>"
        return {"resource": resource, "service": data.get("service"), "payload": self.redactor.shape(body)}

    def poll_riot_session(self) -> None:
        client = self.riot.client
        if client is None:
            return
        try:
            chat = client.get_json("/chat/v1/session")
            subject = chat.get("puuid") if isinstance(chat, dict) else None
            self.redactor.subject = subject if isinstance(subject, str) else None
        except Exception:
            pass
        reads = {
            "player_session": ("/player-session-lifecycle/v1/session", ("loginState", "actionRequired", "productContext", "gameSessionId")),
            "external_sessions": ("/product-session/v1/external-sessions", None),
            "self_presence": ("/chat/v4/presences", None),
        }
        for kind, (route, keys) in reads.items():
            try:
                value = client.get_json(route)
            except Exception as exc:
                self.write(f"riot:{kind}", {"errorType": type(exc).__name__, "status": getattr(exc, "status_code", None)}, dedupe_key=kind)
                continue
            if kind == "self_presence":
                projected: object = self.presence(value)
            elif keys and isinstance(value, dict):
                projected = {key: (self.redactor.shape(value.get(key)) if key != "gameSessionId" else bool(value.get(key))) for key in keys}
            elif isinstance(value, dict):
                # Session keys double as the local launch token: always alias them.
                projected = {self.redactor.alias(name): {
                    key: row.get(key) for key in ("productId", "patchlineId", "phase", "exitCode", "exitReason", "isInternal", "version")
                } for name, row in list(value.items())[:16] if isinstance(row, dict)}
            else:
                projected = self.redactor.shape(value)
            self.write(f"riot:{kind}", projected, dedupe_key=kind)

    def poll_processes(self) -> None:
        try:
            import psutil

            names = sorted({p.info["name"] for p in psutil.process_iter(["name"]) if p.info.get("name") and re.search(r"tft|league|riot|vanguard|vgc", p.info["name"], re.I)})
        except Exception:
            names = []
        self.write("processes", {"names": names}, dedupe_key="processes")

    def poll_live_port(self) -> None:
        import requests
        import urllib3

        urllib3.disable_warnings()
        session = requests.Session()
        session.trust_env = False  # never through a proxy
        try:
            response = session.get("https://127.0.0.1:2999/liveclientdata/allgamedata", timeout=1, verify=False)
            body: object = None
            try:
                body = self.redactor.shape(response.json())
            except ValueError:
                body = f"<non-json:{len(response.content)}>"
            self.write("live_port_2999", {"status": response.status_code, "body": body}, dedupe_key="2999")
        except requests.RequestException as exc:
            self.write("live_port_2999", {"unavailable": type(exc).__name__}, dedupe_key="2999")
        finally:
            session.close()

    def poll_eog(self) -> None:
        path = TFT_LOGS / "TFTEoGStats.json"
        try:
            stat = path.stat()
            identity = (stat.st_mtime_ns, stat.st_size)
            if identity == self.eog_identity or stat.st_size > MAX_MESSAGE_BYTES:
                return
            initial = self.eog_identity is None
            self.eog_identity = identity
            self.write("eog_stats_file", {"initialSnapshot": initial, "bytes": stat.st_size, "value": self.redactor.shape(json.loads(path.read_text(encoding="utf-8")))})
        except (OSError, ValueError):
            pass

    def project_log(self, line: str) -> None:
        category = LOG_CATEGORY.search(line)
        if category:
            self.log_categories[category[1]] += 1
        stamp = LOG_TIME.search(line)
        when = stamp[1] if stamp else None
        if (match := RMS_LINE.search(line)) and "Received RMS message" in line:
            resource = self.redactor.route(match[1])
            fields = {} if PRIVATE_ROUTE.search(resource) else {key: (self.redactor.alias(value) if key == "gameId" else value) for key, value in EMBEDDED_FIELDS.findall(match[3][:65536])}
            self.write("log:rms", {"time": when, "resource": resource, "service": match[2], "fields": fields})
        elif match := BROWSE_LINE.search(line):
            self.write("log:travel", {"time": when, "remoteServer": bool(match[1]), "map": match[2], "options": re.findall(r"GameModeName=([A-Za-z0-9_]{1,80})", line)})
        elif match := HTTP_LINE.search(line):
            code = STATUS_CODE.search(line)
            self.write("log:http", {"time": when, "call": match[1], "stage": match[2], "method": match[3], "path": self.redactor.route(match[4]), "status": int(code[1]) if code else None})
        elif "PostEogStatsBlock" in line:
            self.write("log:eog_post", {"time": when})
        elif category and (category[1] in {"LogGameMode", "LogGameState"} or "TFT" in category[1]):
            # Template only: numbers, quoted text and bracketed values are removed.
            message = line[category.end():] if category else line
            if re.search(r"chat|whisper|password|token|auth", message, re.I):
                return
            template = re.sub(r"\[[^\]]{0,200}\]", "[]", message)
            template = re.sub(r"'[^']{0,200}'|\"[^\"]{0,200}\"", "''", template)
            template = re.sub(r"\b\d+(?:\.\d+)?\b", "#", template)
            template = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27}\b", "<uuid>", template, flags=re.I).strip()[:200]
            self.write("log:tft", {"time": when, "category": category[1] if category else None, "template": template, "numbers": [float(n) for n in re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])", message)[:12]]})

    def due(self, name: str, interval: float) -> bool:
        now = time.monotonic()
        if now >= self.next[name]:
            self.next[name] = now + interval
            return True
        return False

    def tick(self) -> None:
        now = time.monotonic()
        if (self.output / "STOP").exists() or now - self.started >= self.duration or self.events.tell() >= MAX_FILE_BYTES:
            self.stop()
            return
        try:
            if self.due("riot_connect", 10):
                discovery = discover_riot_client()
                self.riot.ensure(discovery.lockfile)
            if self.due("tft_connect", 3):
                self.tft.ensure(read_tft_lockfile())
            if self.due("riot_session", 3):
                self.poll_riot_session()
            if self.due("processes", 5):
                self.poll_processes()
            if self.due("live_port", 5):
                self.poll_live_port()
            if self.tft.client is not None and self.due("tft_endpoints", 5):
                self.tft.poll_endpoints()
            if self.due("catalog_refresh", 120) and self.tft.client is not None:
                before = set(self.tft.get_endpoints)
                self.tft.read_catalog()
                if set(self.tft.get_endpoints) != before:
                    self.write("tft:catalog_changed", {"added": sorted(set(self.tft.get_endpoints) - before)})
        except Exception as exc:  # a diagnostic must keep running through client restarts
            self.write("recorder_error", {"errorType": type(exc).__name__}, dedupe_key="error")
        for line in self.tail.read():
            self.counts["log_lines"] += 1
            self.project_log(line)
        if self.due("eog", 1):
            self.poll_eog()
        if self.due("status", 5):
            self.save_status("recording")

    def save_status(self, state: str) -> None:
        summary = {
            "state": state, "pid": os.getpid(), "startedAt": self.started_at, "updatedAt": utc_now(),
            "elapsedSeconds": round(time.monotonic() - self.started), "maximumSeconds": self.duration,
            "riotConnected": self.riot.connected, "tftConnected": self.tft.connected,
            "tftReadableEndpoints": len(self.tft.get_endpoints),
            "eventCounts": dict(self.counts), "logCategories": dict(self.log_categories.most_common(80)),
            "savedBytes": self.events.tell(), "rawPayloadsSaved": False,
        }
        temporary = self.output / "status.tmp"
        temporary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        temporary.replace(self.output / "status.json")

    def stop(self) -> None:
        from PySide6.QtCore import QCoreApplication

        self.timer.stop()
        self.write("recorder_stopped", {})
        self.save_status("stopped")
        self.riot.close()
        self.tft.close()
        self.events.close()
        QCoreApplication.quit()


def main() -> int:
    from PySide6.QtCore import QCoreApplication

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minutes", type=int, default=180)
    args = parser.parse_args()
    if not 1 <= args.minutes <= 360:
        parser.error("minutes must be between 1 and 360")
    app = QCoreApplication([sys.argv[0]])
    _recorder = Recorder(args.output.resolve(), args.minutes * 60)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

"""Strict, anonymous Peaks diagnostics relay. OpenObserve credentials stay server-side."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

EVENTS = frozenset({"app.started", "backend.started", "backend.failed", "backend.stopped", "renderer.failed", "command.completed", "update.state"})
COMMANDS = frozenset({"state", "activity", "refresh", "search", "player", "match", "matches", "account", "settings", "follow", "unfollow"})
UPDATE_STATES = frozenset({"checking", "available", "downloading", "downloaded", "installing", "error", "idle", "up-to-date"})
MAX_BODY = 16_384


def sanitize_batch(value: Any) -> list[dict[str, object]]:
    """Reject unexpected fields, including accidental identity-bearing additions."""
    if not isinstance(value, dict) or set(value) != {"schema", "events"} or type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("schema")
    events = value["events"]
    if not isinstance(events, list) or not 1 <= len(events) <= 32:
        raise ValueError("batch")
    output: list[dict[str, object]] = []
    for raw in events:
        if not isinstance(raw, dict):
            raise ValueError("event")
        name = raw.get("event")
        version = raw.get("version")
        platform = raw.get("platform")
        if not isinstance(name, str) or name not in EVENTS or not isinstance(version, str) or re.fullmatch(r"\d{1,4}\.\d{1,4}\.\d{1,4}", version) is None or platform not in ("win32", "darwin", "linux"):
            raise ValueError("fields")
        allowed = {"event", "version", "platform"}
        result: dict[str, object] = {"event": name, "version": version, "platform": platform, "service": "peaks", "schema": 1}
        if name == "command.completed":
            allowed |= {"command", "outcome", "duration_ms"}
            if not isinstance(raw.get("command"), str) or raw["command"] not in COMMANDS or raw.get("outcome") not in ("success", "failure"):
                raise ValueError("command")
            result["command"] = raw["command"]
            result["outcome"] = raw["outcome"]
            if "duration_ms" in raw:
                duration = raw["duration_ms"]
                if type(duration) is not int or not 0 <= duration <= 300_000 or duration % 100:
                    raise ValueError("duration")
                result["duration_ms"] = duration
        if name == "update.state":
            allowed.add("state")
            if not isinstance(raw.get("state"), str) or raw["state"] not in UPDATE_STATES:
                raise ValueError("state")
            result["state"] = raw["state"]
        if set(raw) - allowed:
            raise ValueError("extra fields")
        output.append(result)
    return output


class RateLimit:
    """Volatile source limits. IPs are never logged or forwarded to OpenObserve."""

    def __init__(self) -> None:
        self.sources: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self.minute = -1
        self.total = 0

    def allow(self, source: str, now: float) -> bool:
        minute = int(now // 60)
        if minute != self.minute:
            self.minute, self.total = minute, 0
            self.sources.clear()
        if self.total >= 600:
            return False
        count = self.sources.get(source, (minute, 0))[1]
        if count >= 6 or (source not in self.sources and len(self.sources) >= 4096):
            return False
        self.total += 1
        self.sources[source] = (minute, count + 1)
        return True


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class Handler(BaseHTTPRequestHandler):
    server_version = "PeaksTelemetry"
    sys_version = ""
    limits = RateLimit()

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Never log request addresses, headers, URLs or bodies.

    def reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self) -> None:
        self.reply(200 if self.path == "/healthz" else 404)

    def do_POST(self) -> None:
        if self.path != "/peaks/v1/events":
            self.reply(404)
            return
        if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Encoding") or self.headers.get_content_type() != "application/json":
            self.reply(415)
            return
        source = self.headers.get("X-Peaks-Source", self.client_address[0])[:128]
        if not self.limits.allow(source, time.monotonic()):
            self.reply(429)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY:
            self.reply(413)
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("length")
            events = sanitize_batch(json.loads(body))
        except (ValueError, TypeError, RecursionError, TimeoutError):
            self.reply(400)
            return
        organization = os.environ.get("OPENOBSERVE_ORGANIZATION", "default")
        auth = os.environ.get("OPENOBSERVE_AUTH_TOKEN", "")
        if not auth or re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", organization) is None:
            self.reply(503)
            return
        request = urllib.request.Request(
            f"http://openobserve:5080/api/{organization}/peaks/_json",
            data=json.dumps(events, separators=(",", ":")).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
            method="POST",
        )
        try:
            # Dedicated internal service, no ambient proxies and no client-selected destination.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=5) as response:
                result = json.loads(response.read(16_384))
                streams = result.get("status", [])
                accepted = response.status == 200 and result.get("code") == 200 and any(item.get("name") == "peaks" and item.get("successful") == len(events) and item.get("failed") == 0 for item in streams)
            self.reply(202 if accepted else 502)
        except (OSError, ValueError, TypeError, AttributeError, urllib.error.URLError):
            self.reply(502)


class PrivateHTTPServer(HTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # Disconnected clients must not put addresses/tracebacks into container logs.


if __name__ == "__main__":
    PrivateHTTPServer(("0.0.0.0", 3009), Handler).serve_forever()

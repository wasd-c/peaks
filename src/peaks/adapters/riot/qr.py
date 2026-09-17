"""Strict parsing of Riot QR-login payload text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


class QRParseError(ValueError):
    """Raised when QR text is not a Riot login payload."""


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
# Riot can change the presentation URL without changing the authentication
# service.  Keep this deliberately small: a QR payload is an instruction to
# approve a login, so accepting an arbitrary HTTPS host would create a useful
# phishing/proxy primitive before the session-info request even runs.
RIOT_QR_HOSTS = frozenset(
    {
        "qr.riotgames.com",
        "qrlogin.riotgames.com",
        "authenticate.riotgames.com",
    }
)


@dataclass(frozen=True, slots=True)
class QRLoginPayload:
    suuid: str
    cluster: str

    def as_tuple(self) -> tuple[str, str]:
        return self.suuid, self.cluster


def _validate_token(name: str, value: str | None) -> str:
    if not value or not _TOKEN_RE.fullmatch(value):
        raise QRParseError(f"invalid {name}")
    return value


def parse_qr_text(text: str) -> QRLoginPayload:
    """Parse ``suuid:cluster`` or a Riot QR URL.

    URL query parameters must contain exactly one value for both fields.  The
    values are constrained to URL-safe opaque tokens; they are never fetched
    or interpreted here.
    """

    if not isinstance(text, str):
        raise QRParseError("QR text must be text")
    raw = text.strip()
    if not raw:
        raise QRParseError("QR text is empty")

    if "://" not in raw:
        bits = raw.split(":")
        if len(bits) != 2:
            raise QRParseError("QR text must contain suuid:cluster")
        return QRLoginPayload(_validate_token("suuid", bits[0]), _validate_token("cluster", bits[1]))

    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise QRParseError("Riot QR URL must use HTTPS")
    if parsed.username or parsed.password or parsed.fragment:
        raise QRParseError("QR URL contains unsupported parts")
    try:
        host = parsed.hostname.lower() if parsed.hostname else None
        port = parsed.port
    except ValueError as exc:
        raise QRParseError("QR URL has an invalid host") from exc
    if host not in RIOT_QR_HOSTS or port is not None:
        raise QRParseError("QR URL host is not an allowlisted Riot host")
    if host == "qrlogin.riotgames.com" and parsed.path not in {"/riotmobile", "/riotmobile/"}:
        raise QRParseError("Riot Mobile QR URL has an invalid path")
    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise QRParseError("QR URL has malformed query parameters") from exc
    suuid = query.get("suuid", [])
    cluster = query.get("cluster", [])
    if len(suuid) != 1 or len(cluster) != 1:
        raise QRParseError("QR URL must contain exactly one suuid and cluster")
    timestamp = query.get("timestamp")
    if timestamp is not None and (
        len(timestamp) != 1 or not re.fullmatch(r"[0-9]{10,16}", timestamp[0])
    ):
        raise QRParseError("QR URL has an invalid timestamp")
    return QRLoginPayload(_validate_token("suuid", suuid[0]), _validate_token("cluster", cluster[0]))


def parse_qr_login(text: str) -> tuple[str | None, str | None]:
    """Compatibility tuple parser matching 2fa-desktop's API."""

    try:
        return parse_qr_text(text).as_tuple()
    except (QRParseError, TypeError):
        return None, None


def validate_qr_text(text: str) -> bool:
    try:
        parse_qr_text(text)
    except (QRParseError, TypeError):
        return False
    return True


validate_qr_login = validate_qr_text

# Name used by the Peaks controller; the typed payload keeps the parsed values
# together and avoids passing a loosely structured dictionary between layers.
parse_riot_qr = parse_qr_text

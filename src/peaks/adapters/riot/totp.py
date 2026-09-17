"""Riot's SHA-256 TOTP and seed parsing helpers.

Riot account seeds are credentials.  This module deliberately contains no
logging and returns a canonical, non-secret representation of a seed only to
the caller that asked for it.  UI and persistence code should keep the result
in the platform secret store.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import time
from dataclasses import dataclass
from typing import Final
from urllib.parse import parse_qs, unquote, urlparse

TOTP_PERIOD: Final[int] = 30
TOTP_DIGITS: Final[int] = 6
TOTP_ALGORITHM: Final[str] = "SHA256"

_BASE32_RE = re.compile(r"^[A-Z2-7]+={0,6}$")
_BASE32_UNPADDED_RE = re.compile(r"^[A-Z2-7]+$")


class SeedParseError(ValueError):
    """Raised when a raw seed or ``otpauth://`` URI is not unambiguous."""


@dataclass(frozen=True, slots=True)
class TOTPConfig:
    """The fixed Riot TOTP configuration.

    ``otpauth`` URIs sometimes contain parameters that alter the usual TOTP
    defaults.  Peaks accepts them only when they describe the Riot-compatible
    SHA-256/30-second/6-digit profile; silently accepting a different profile
    would generate an apparently valid but unusable code.
    """

    period: int = TOTP_PERIOD
    digits: int = TOTP_DIGITS
    algorithm: str = TOTP_ALGORITHM


def _canonical_base32(raw: str) -> str:
    """Validate and return an uppercase, unpadded Base32 seed.

    Human-entered seeds commonly contain spaces or hyphens, so those
    separators are ignored.  Every other character is rejected.  Padding is
    allowed only at the end and must be the exact amount required by Base32.
    """

    if not isinstance(raw, str):
        raise SeedParseError("seed must be text")
    compact = re.sub(r"[\s-]+", "", raw).upper()
    if not compact:
        raise SeedParseError("seed is empty")
    if not _BASE32_RE.fullmatch(compact):
        raise SeedParseError("seed is not valid Base32")

    unpadded, _, padding = compact.partition("=")
    if not _BASE32_UNPADDED_RE.fullmatch(unpadded):
        raise SeedParseError("seed contains invalid Base32 characters")
    # Base32 input can only have lengths whose remainder is 0, 2, 4, 5, or 7.
    remainder = len(unpadded) % 8
    if remainder in (1, 3, 6):
        raise SeedParseError("seed has invalid Base32 length")
    required_padding = (8 - remainder) % 8
    if padding and len(padding) != required_padding:
        raise SeedParseError("seed has invalid Base32 padding")

    encoded = unpadded + ("=" * required_padding)
    try:
        decoded = base64.b32decode(encoded, casefold=False)
    except (binascii.Error, ValueError) as exc:
        raise SeedParseError("seed is not decodable Base32") from exc
    if not decoded:
        raise SeedParseError("seed is empty")
    return unpadded


def _otpauth_seed(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.scheme.lower() != "otpauth" or parsed.netloc.lower() != "totp":
        raise SeedParseError("only otpauth://totp URIs are supported")
    if parsed.fragment or parsed.username or parsed.password:
        raise SeedParseError("otpauth URI contains unsupported URL parts")
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    values = query.get("secret", [])
    if len(values) != 1 or not values[0]:
        raise SeedParseError("otpauth URI must contain exactly one secret")

    # The query parser already decodes percent escapes.  Reject a second layer
    # of escaping rather than accidentally accepting a different secret.
    secret = values[0]
    if unquote(secret) != secret:
        raise SeedParseError("secret is over-encoded")

    algorithm = query.get("algorithm", [TOTP_ALGORITHM])
    digits = query.get("digits", [str(TOTP_DIGITS)])
    period = query.get("period", [str(TOTP_PERIOD)])
    if algorithm != [TOTP_ALGORITHM] or digits != [str(TOTP_DIGITS)] or period != [str(TOTP_PERIOD)]:
        raise SeedParseError("otpauth URI is not Riot-compatible")
    return _canonical_base32(secret)


def parse_seed(value: str) -> str:
    """Parse a raw Base32 seed or a strict Riot-compatible ``otpauth`` URI.

    The returned value is uppercase and unpadded, making it safe to compare
    for migration purposes without retaining multiple representations.
    """

    if not isinstance(value, str):
        raise SeedParseError("seed must be text")
    raw = value.strip()
    if not raw:
        raise SeedParseError("seed is empty")
    if raw.lower().startswith("otpauth://"):
        return _otpauth_seed(raw)
    # A URI-looking value must not fall through as a Base32 string.  This also
    # rejects ``http://`` and qr-login URLs in the seed field.
    if "://" in raw or ":" in raw:
        raise SeedParseError("unsupported seed URI")
    return _canonical_base32(raw)


def extract_seed(value: str) -> str | None:
    """Compatibility helper returning ``None`` instead of raising.

    Unlike the legacy 2fa-desktop helper, malformed input is not returned as a
    seed.  Call :func:`parse_seed` when an explanatory exception is useful.
    """

    try:
        return parse_seed(value)
    except (SeedParseError, TypeError):
        return None


def totp_sha256(
    seed_b32: str,
    period: int = TOTP_PERIOD,
    digits: int = TOTP_DIGITS,
    t: float | int | None = None,
    *,
    timestamp: float | int | None = None,
) -> str:
    """Generate a six-digit, 30-second SHA-256 TOTP.

    ``t`` is retained as a compatibility alias for the original helper.  It
    is useful in deterministic tests and must not be supplied alongside
    ``timestamp``.
    """

    if timestamp is not None and t is not None:
        raise TypeError("pass either timestamp or t, not both")
    if period != TOTP_PERIOD or digits != TOTP_DIGITS:
        raise ValueError("Riot TOTP uses a 30-second period and 6 digits")
    canonical = parse_seed(seed_b32)
    when = timestamp if timestamp is not None else t
    if when is None:
        when = time.time()
    if not isinstance(when, (int, float)) or not int(when) >= 0:
        raise ValueError("timestamp must be a non-negative number")
    counter = int(when) // TOTP_PERIOD
    key = base64.b32decode(canonical + "=" * ((8 - len(canonical) % 8) % 8))
    digest = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
    offset = digest[-1] & 0x0F
    binary = int.from_bytes(digest[offset : offset + 4], "big") & 0x7F_FF_FF_FF
    return f"{binary % (10**TOTP_DIGITS):0{TOTP_DIGITS}d}"


def generate_totp(seed_b32: str, timestamp: float | int | None = None) -> str:
    """Descriptive alias for :func:`totp_sha256`."""

    return totp_sha256(seed_b32, timestamp=timestamp)


def get_code(seed_b32: str, timestamp: float | int | None = None) -> str:
    """Legacy alias used by the 2fa-desktop adapter."""

    return generate_totp(seed_b32, timestamp)

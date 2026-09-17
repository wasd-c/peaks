from __future__ import annotations

import pytest

from peaks.adapters.riot.totp import SeedParseError, extract_seed, parse_seed, totp_sha256


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (59, "119246"),
        (1_111_111_109, "084774"),
        (1_111_111_111, "062674"),
        (1_234_567_890, "819424"),
        (2_000_000_000, "698825"),
        (20_000_000_000, "737706"),
    ],
)
def test_sha256_rfc6238_vectors(timestamp: int, expected: str) -> None:
    # Base32 encoding of RFC 6238's SHA-256 ASCII 32-byte secret.
    seed = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQGEZA"
    assert totp_sha256(seed, timestamp=timestamp) == expected


def test_seed_parser_canonicalizes_raw_and_otpauth() -> None:
    assert parse_seed(" jbsw y3dp-ehpk 3pxp ") == "JBSWY3DPEHPK3PXP"
    assert (
        parse_seed("otpauth://totp/Riot%3Aalice?secret=JBSWY3DPEHPK3PXP&algorithm=SHA256")
        == "JBSWY3DPEHPK3PXP"
    )
    assert extract_seed("not-a-0seed") is None


@pytest.mark.parametrize(
    "value",
    [
        "",
        "ABCDEF",  # remainder 6 cannot be valid Base32
        "A",
        "JBSWY3DPEHPK3PXP=bad",
        "otpauth://hotp/Riot?secret=JBSWY3DPEHPK3PXP",
        "otpauth://totp/Riot?secret=JBSWY3DPEHPK3PXP&algorithm=SHA1",
        "http://example.test/?secret=JBSWY3DPEHPK3PXP",
    ],
)
def test_seed_parser_rejects_ambiguous_or_invalid_values(value: str) -> None:
    with pytest.raises(SeedParseError):
        parse_seed(value)


def test_totp_requires_riot_profile() -> None:
    with pytest.raises(ValueError):
        totp_sha256("JBSWY3DPEHPK3PXP", period=60)

"""Exact Riot routing values, never inferred from tags, country or IP."""

LEAGUE_PLATFORM_ALIASES = {
    "br": "BR",
    "br1": "BR",
    "eun": "EUNE",
    "eun1": "EUNE",
    "eune": "EUNE",
    "euw": "EUW",
    "euw1": "EUW",
    "jp": "JP",
    "jp1": "JP",
    "kr": "KR",
    "la1": "LAN",
    "lan": "LAN",
    "la2": "LAS",
    "las": "LAS",
    "me": "ME",
    "me1": "ME",
    "na": "NA",
    "na1": "NA",
    "oc1": "OCE",
    "oce": "OCE",
    "ph": "PH",
    "ph2": "PH",
    "ru": "RU",
    "sg": "SG",
    "sg2": "SG",
    "th": "TH",
    "th2": "TH",
    "tr": "TR",
    "tr1": "TR",
    "tw": "TW",
    "tw2": "TW",
    "vn": "VN",
    "vn2": "VN",
}
VALORANT_REGIONS = frozenset({"AP", "BR", "EU", "KR", "LATAM", "NA", "PBE"})


def normalize_league_region(value: object) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 16:
        return None
    return LEAGUE_PLATFORM_ALIASES.get(value.casefold())


def normalize_valorant_region(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 16:
        return None
    region = value.upper()
    return region if region in VALORANT_REGIONS else None

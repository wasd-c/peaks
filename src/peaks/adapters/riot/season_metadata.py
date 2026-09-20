"""Credential-free public act names when Riot's content service is unavailable."""

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast

import requests

from peaks.adapters.providers.valorant_metadata import (
    MetadataSession,
    ValorantMetadataClient,
    ValorantMetadataError,
)

from .valorant_enrichment import SeasonCatalog, _date, parse_season_catalog


def parse_public_seasons(rows: Sequence[Mapping[str, Any]], *, now: datetime) -> SeasonCatalog:
    parents = {row.get("uuid"): row for row in rows[:512] if isinstance(row.get("uuid"), str)}
    acts: list[dict[str, Any]] = []
    for row in rows[:512]:
        if row.get("type") != "EAresSeasonType::Act":
            continue
        parent_id = row.get("parentUuid")
        parent = parents.get(parent_id) if isinstance(parent_id, str) else None
        if not parent:
            continue
        name = str(parent.get("displayName", "")).upper().strip()
        episode = re.fullmatch(r"EPISODE\s*0?([1-9]\d?)", name)
        if episode:
            name = f"E{int(episode.group(1))}"
        elif not re.fullmatch(r"V\d{2}", name):
            continue
        start, end = _date(row.get("startTime")), _date(row.get("endTime"))
        begin, finish = _date(parent.get("startTime")), _date(parent.get("endTime"))
        if not start or not end or not begin or not finish or not begin <= start < end <= finish:
            continue
        acts.append({
            "ID": row.get("uuid"), "Name": f"{name} {row.get('displayName', '')}",
            "Type": "act", "IsActive": start <= now < end,
        })
    return parse_season_catalog({"Seasons": acts})


def public_season_catalog() -> SeasonCatalog:
    # A separate session is essential: no Riot authorization, cookies or player
    # identifiers are sent to the public metadata provider.
    try:
        with requests.Session() as session:
            session.trust_env = False
            provider = ValorantMetadataClient(
                session=cast(MetadataSession, session), timeout_seconds=2, max_response_bytes=1_048_576,
            )
            return parse_public_seasons(provider.get_seasons(), now=datetime.now(UTC))
    except (ValorantMetadataError, requests.RequestException):
        return SeasonCatalog()

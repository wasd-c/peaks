"""Normalize the signed-in League client's completed LoL/TFT history pages.

LCU has both legacy games/participantIdentities and product-history data/info
envelopes. Identity must be explicit in every match; a single participant is
never implicitly assumed to be the account owner.
"""

from collections.abc import Mapping
from math import isfinite
from typing import Any


def history_details(payload: object, *, puuid: str, game: str, limit: int = 20) -> list[tuple[str, dict[str, Any], float | None]]:
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get("games", payload.get("matches", []))
    if isinstance(rows, Mapping):
        rows = rows.get("games", [])
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows[:max(0, min(limit, 20))]:
        if not isinstance(row, Mapping):
            continue
        envelope = row.get("json", row)
        if not isinstance(envelope, Mapping):
            continue
        info = envelope.get("info", envelope)
        if not isinstance(info, Mapping):
            continue
        participants = info.get("participants")
        if not isinstance(participants, list) or len(participants) > 20:
            continue
        identities = info.get("participantIdentities", [])
        identity_by_id = {identity.get("participantId"): identity.get("player", {}) for identity in identities if isinstance(identity, Mapping)} if isinstance(identities, list) else {}
        normalized = []
        for participant in participants:
            if not isinstance(participant, Mapping):
                continue
            identity = identity_by_id.get(participant.get("participantId"), {})
            identity = identity if isinstance(identity, Mapping) else {}
            stats = participant.get("stats", {})
            stats = stats if isinstance(stats, Mapping) else {}
            normalized.append({
                **stats, **identity, **participant,
                "puuid": participant.get("puuid", identity.get("puuid")),
                "championName": participant.get("championName") or str(participant.get("championId") or ""),
            })
        if sum(player.get("puuid") == puuid for player in normalized) != 1:
            continue
        metadata = envelope.get("metadata", row.get("metadata", {}))
        metadata = metadata if isinstance(metadata, Mapping) else {}
        match_id = metadata.get("match_id") or row.get("gameId") or row.get("id") or info.get("gameId")
        if not isinstance(match_id, (str, int)) or isinstance(match_id, bool) or len(str(match_id)) > 160:
            continue
        platform = info.get("platformId")
        if isinstance(platform, str) and str(match_id).isdigit():
            match_id = f"{platform}_{match_id}"
        elif str(match_id).isdigit():
            match_id = f"{game.lower()}-{match_id}"
        # Native TFT history also carries its publication/end timestamp in
        # game_datetime. Prefer the explicit start; otherwise a locally saved
        # game jumps forward on the calendar when Riot enriches its report.
        timestamp = None
        for key in ("gameStartTimestamp", "gameCreation", "game_datetime"):
            candidate = info.get(key)
            if isinstance(candidate, str) and candidate.isascii() and candidate.isdigit() and len(candidate) <= 13:
                candidate = int(candidate)
            if isinstance(candidate, (int, float)) and not isinstance(candidate, bool) and isfinite(candidate) and candidate > 0:
                timestamp = float(candidate) / (1_000 if candidate > 10_000_000_000 else 1)
                break
        result.append((str(match_id), {**info, "participants": normalized}, timestamp))
    return result

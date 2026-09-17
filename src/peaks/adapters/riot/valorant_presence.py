"""Sanitized own-player presence facts from validated Riot client responses.

The client roster provides the selected agent. Local chat presence can expose
team scores and party size, but does not document live individual K/D. Never
substitute historical statistics for that missing live telemetry.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .redaction import is_incognito_player

_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


@dataclass(frozen=True, slots=True)
class ValorantPresence:
    ally_score: int | None = None
    enemy_score: int | None = None
    party_size: int | None = None
    party_max: int | None = None
    queue_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValorantPartyMember:
    """Only display facts from the authenticated player's current party."""

    puuid: str
    account_level: int | None = None
    account_level_hidden: bool = False
    incognito: bool = False
    competitive_tier: int | None = None
    is_owner: bool = False
    is_ready: bool | None = None
    team: str | None = None
    player_card_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValorantParty:
    size: int
    maximum: int | None = None
    owner_in_own_team: bool = False
    members: tuple[ValorantPartyMember, ...] = ()
    phase: str | None = None
    queue_id: str | None = None
    map_id: str | None = None
    mode_id: str | None = None
    queue_started_at: str | None = None
    party_id: str | None = None


def _integer(value: object, *, minimum: int = 0, maximum: int = 1_000) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum
        else None
    )


def party_identifier(payload: object, *, subject: str) -> str | None:
    """A party lookup must be bound to the authenticated entitlement subject."""

    if not isinstance(payload, Mapping) or payload.get("Subject") != subject:
        return None
    value = payload.get("CurrentPartyID")
    return value if isinstance(value, str) and _IDENTIFIER.fullmatch(value) else None


def _asset_path(value: object) -> str | None:
    return (
        value
        if isinstance(value, str)
        and re.fullmatch(r"/Game/[A-Za-z0-9_./-]{1,240}", value)
        and ".." not in value
        else None
    )


def _queue_entry_time(value: object) -> str | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # The service also returns an unset zero-date. It is not a queue timer.
    return value if parsed.tzinfo is not None and parsed.year >= 2020 else None


def _custom_teams(custom: Mapping[str, Any], subjects: set[str]) -> dict[str, str]:
    membership = custom.get("Membership")
    if not isinstance(membership, Mapping):
        return {}
    result: dict[str, str] = {}
    for key in ("teamOne", "teamTwo", "teamSpectate", "teamOneCoaches", "teamTwoCoaches"):
        rows = membership.get(key)
        if not isinstance(rows, list) or len(rows) > 20:
            continue
        for row in rows:
            puuid = row.get("Subject") if isinstance(row, Mapping) else None
            if isinstance(puuid, str) and puuid in subjects:
                # Conflicting memberships cannot safely describe a team.
                if puuid in result:
                    return {}
                result[puuid] = key
    return result


def parse_party(
    payload: object, *, subject: str, expected_id: str, own_team_subjects: tuple[str, ...] = ()
) -> ValorantParty | None:
    if (
        not isinstance(payload, Mapping)
        or not _IDENTIFIER.fullmatch(expected_id)
        or payload.get("ID") != expected_id
    ):
        return None
    members = payload.get("Members")
    if not isinstance(members, list) or not 1 <= len(members) <= 20:
        return None
    subjects: set[str] = set()
    owners: list[str] = []
    for member in members:
        value = member.get("Subject") if isinstance(member, Mapping) else None
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value) or value in subjects:
            return None
        identity = member.get("PlayerIdentity")
        if isinstance(identity, Mapping) and identity.get("Subject", value) != value:
            return None
        subjects.add(value)
        if member.get("IsOwner") is True:
            owners.append(value)
    if subject not in subjects:
        return None
    maximum = None
    matchmaking = payload.get("MatchmakingData")
    queue = matchmaking.get("QueueID") if isinstance(matchmaking, Mapping) else None
    queue = queue if isinstance(queue, str) and _IDENTIFIER.fullmatch(queue) else None
    custom = payload.get("CustomGameData")
    # CustomGameData also exists on normal parties; its capacity is meaningful
    # only when the party is explicitly in a custom-game flow.
    if queue == "custom" and isinstance(custom, Mapping):
        maximum = _integer(custom.get("MaxPartySize"), minimum=len(subjects), maximum=20)
    owner_in_own_team = len(owners) == 1 and (
        owners[0] == subject or owners[0] in own_team_subjects
    )
    teams = _custom_teams(custom, subjects) if queue == "custom" and isinstance(custom, Mapping) else {}
    roster: list[ValorantPartyMember] = []
    for member in members:
        identity = member.get("PlayerIdentity")
        identity = identity if isinstance(identity, Mapping) else {}
        hide_level = "HideAccountLevel" in identity and identity.get("HideAccountLevel") is not False
        card = identity.get("PlayerCardID")
        roster.append(
            ValorantPartyMember(
                puuid=member["Subject"],
                account_level=None if hide_level else _integer(identity.get("AccountLevel"), maximum=100_000),
                account_level_hidden=hide_level,
                incognito=is_incognito_player(member),
                competitive_tier=_integer(member.get("CompetitiveTier"), maximum=27),
                is_owner=len(owners) == 1 and member.get("IsOwner") is True,
                is_ready=member.get("IsReady") if isinstance(member.get("IsReady"), bool) else None,
                team=teams.get(member["Subject"]),
                player_card_id=card if isinstance(card, str) and _IDENTIFIER.fullmatch(card) else None,
            )
        )
    # A party remains allocated while its members are in a match. Only these
    # explicit pre-match states may become a lobby when match telemetry is absent.
    state = payload.get("State")
    phase = {"DEFAULT": "lobby", "MATCHMAKING": "matchmaking"}.get(state) if isinstance(state, str) else None
    settings = custom.get("Settings") if queue == "custom" and isinstance(custom, Mapping) else None
    settings = settings if isinstance(settings, Mapping) else {}
    return ValorantParty(
        size=len(subjects),
        maximum=maximum,
        owner_in_own_team=owner_in_own_team,
        members=tuple(roster),
        phase=phase,
        queue_id=queue,
        map_id=_asset_path(settings.get("Map")),
        mode_id=_asset_path(settings.get("Mode")),
        queue_started_at=_queue_entry_time(payload.get("QueueEntryTime")) if phase == "matchmaking" else None,
        party_id=expected_id,
    )


def _private_presence(value: object) -> Mapping[str, Any] | None:
    if not isinstance(value, str) or not 1 <= len(value) <= 65_536:
        return None
    try:
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) > 49_152:
            return None
        payload = json.loads(decoded.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def parse_own_presence(
    payload: object,
    *,
    subject: str,
    match_id: str,
    map_id: str | None,
    phase: str,
    observed_at_ms: int,
    now_ms: int,
    party_owner_in_own_team: bool = False,
) -> ValorantPresence:
    """Project only the authenticated player's matching, fresh game presence.

    Some client versions omit matchId. In those versions a score is accepted
    only after a same-map INGAME presence update newer than Peaks' first
    observation of the GLZ match. A cached previous game cannot become 13-8
    in a new game on the same map merely because it was the last presence.
    """

    rows = payload.get("presences") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return ValorantPresence()
    candidates = [
        row
        for row in rows[:512]
        if isinstance(row, Mapping)
        and row.get("puuid") == subject
        and row.get("product") == "valorant"
    ]
    candidates.sort(key=lambda row: _integer(row.get("time"), maximum=10**15) or 0, reverse=True)
    # The newest own presence is authoritative. An older INGAME row must not
    # outlive a newer MENUS or different-map row merely because it parses.
    for row in candidates[:1]:
        private = _private_presence(row.get("private"))
        if private is None or private.get("isValid") is False:
            continue
        nested = private.get("matchPresenceData")
        match = nested if isinstance(nested, Mapping) else private
        if match.get("isValid") is False:
            continue
        expected_state = "INGAME" if phase == "live" else "PREGAME"
        if match.get("sessionLoopState") != expected_state:
            continue
        party_nested = private.get("partyPresenceData")
        party = party_nested if isinstance(party_nested, Mapping) else private
        if party.get("isValid") is False:
            party = {}
        owner = party if "partyOwnerMatchMap" in party else private
        # The commonly published score is from the party owner's viewpoint.
        # Only use it when the owner is self or a verified current teammate.
        owner_trusted = party_owner_in_own_team or party.get("isPartyOwner") is True
        owner_map = owner.get("partyOwnerMatchMap")
        own_map = match.get("matchMap")
        correlated_map = own_map if own_map is not None else owner_map if owner_trusted else None
        if not map_id or correlated_map != map_id:
            continue
        explicit_id = match.get("matchId", match.get("matchID"))
        if explicit_id is not None and explicit_id != match_id:
            continue
        timestamp = _integer(row.get("time"), maximum=10**15)
        if timestamp is not None and (timestamp > now_ms + 30_000 or timestamp < now_ms - 300_000):
            continue
        if explicit_id is None and (timestamp is None or timestamp < observed_at_ms):
            continue
        party_size = _integer(party.get("partySize"), minimum=1, maximum=20)
        party_max = _integer(party.get("maxPartySize"), minimum=party_size or 1, maximum=20)
        queue_id = match.get("queueId")
        if not isinstance(queue_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", queue_id):
            queue_id = None
        ally = _integer(match.get("matchScoreAllyTeam")) if phase == "live" else None
        enemy = _integer(match.get("matchScoreEnemyTeam")) if phase == "live" else None
        if (
            (ally is None or enemy is None)
            and phase == "live"
            and owner_trusted
            and owner_map == map_id
            and owner.get("partyOwnerSessionLoopState") == "INGAME"
        ):
            ally = _integer(owner.get("partyOwnerMatchScoreAllyTeam"))
            enemy = _integer(owner.get("partyOwnerMatchScoreEnemyTeam"))
        return ValorantPresence(
            ally_score=ally if enemy is not None else None,
            enemy_score=enemy if ally is not None else None,
            party_size=party_size,
            party_max=party_max if party_size is not None else None,
            queue_id=queue_id,
        )
    return ValorantPresence()

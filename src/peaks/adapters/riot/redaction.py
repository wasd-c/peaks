"""Streamer/incognito-safe player identity redaction.

Redaction is intentionally destructive: once an identity is marked incognito,
Peaks does not hash it, retain an alias, or try to match it against another
source.  This prevents a UI consumer from accidentally deanonymizing Riot's
privacy mode.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

_IDENTITY_KEYS = {
    "name",
    "displayname",
    "display_name",
    "gamename",
    "game_name",
    "tagline",
    "riotid",
    "riot_id",
    "summonername",
    "summoner_name",
    "summonerid",
    "summoner_id",
    "puuid",
    "subject",
    "playeruuid",
    "player_uuid",
    "playerid",
    "player_id",
    "accountid",
    "account_id",
    "user_id",
}
_INCOGNITO_KEYS = {"incognito", "streamermode", "streamer_mode", "privacy_mode"}
# Riot has added privacy fields over time and local payloads are not a stable
# public schema.  A privacy-looking field we do not understand must never be
# treated as opt-out: its presence is an instruction to redact.
_UNKNOWN_PRIVACY_FRAGMENTS = ("privacy", "incognito", "streamer", "anonymous")
_REDACTED_IDENTITY_VALUES = {"anonymous", "hidden player", "unknown player", "redacted"}
_SELF_KEYS = {"isself", "is_self", "localplayer", "local_player", "islocalplayer"}


def _normal_key(key: object) -> str:
    return str(key).replace("-", "_").casefold()


def _privacy_marker_state(player: Mapping[str, Any]) -> tuple[bool, bool]:
    """Return ``(privacy_active, marker_was_present)`` for one player record.

    Known markers are accepted only as actual booleans.  A string such as
    ``"false"`` is not a safe opt-out, and an unknown privacy marker is
    treated as active.  This intentionally errs toward a blank identity when
    a Riot payload evolves beyond the fields understood by this client.
    """

    active = False
    present = False
    for key, value in player.items():
        normalized = _normal_key(key)
        compact = normalized.replace("_", "")
        known = normalized in _INCOGNITO_KEYS
        unknown_privacy = any(fragment in compact for fragment in _UNKNOWN_PRIVACY_FRAGMENTS)
        if not (known or unknown_privacy):
            continue
        present = True
        if not known or (not isinstance(value, bool) or value):
            active = True

    identity = player.get("PlayerIdentity") or player.get("playerIdentity")
    if isinstance(identity, Mapping):
        nested_active, nested_present = _privacy_marker_state(identity)
        active = active or nested_active
        present = present or nested_present
    return active, present


def is_incognito_player(player: Mapping[str, Any]) -> bool:
    """Return whether a player must be treated as privacy-protected.

    Empty identity values are also fail-closed.  Riot uses missing/blank
    names for anonymous players, and displaying a blank identity as if it
    were public would create a future deanonymization footgun.
    """

    active, _ = _privacy_marker_state(player)
    if active:
        return True
    for key, value in player.items():
        if _identity_key(key):
            if value in (None, ""):
                return True
            if isinstance(value, str) and value.strip().casefold() in _REDACTED_IDENTITY_VALUES:
                return True
    identity = player.get("PlayerIdentity") or player.get("playerIdentity")
    if isinstance(identity, Mapping):
        return is_incognito_player(identity)
    return False


def _identity_key(key: object) -> bool:
    normalized = _normal_key(key)
    return normalized in _IDENTITY_KEYS


def redact_player(
    player: Mapping[str, Any],
    *,
    streamer_mode: bool = False,
    is_self: bool = False,
    placeholder: str = "Anonymous player",
) -> dict[str, Any]:
    """Return a copy with identity fields removed when privacy applies.

    Global streamer mode may preserve an explicitly marked local player, but
    incognito payloads are always redacted, even for the local player.  This is
    the conservative rule needed when server-provided privacy state is present.
    """

    if not isinstance(player, Mapping):
        raise TypeError("player must be a mapping")
    # A malformed/non-boolean self marker must not bypass streamer redaction.
    # Only an actual ``True`` marker is trusted as the local player signal.
    own_marker = is_self or any(
        value is True for key, value in player.items() if _normal_key(key) in _SELF_KEYS
    )
    incognito = is_incognito_player(player)
    redact = incognito or (streamer_mode and not own_marker)
    if not redact:
        return deepcopy(dict(player))

    result: dict[str, Any] = {}
    for key, value in player.items():
        normalized = _normal_key(key)
        if _identity_key(key):
            # Preserve the shape for simple table renderers while removing the
            # value entirely.  No digest or stable alias is produced.
            result[key] = None
            continue
        if normalized == "playeridentity" and isinstance(value, Mapping):
            nested = {k: deepcopy(v) for k, v in value.items() if not _identity_key(k)}
            result[key] = nested
            continue
        if isinstance(value, Mapping):
            result[key] = redact_player(
                value,
                streamer_mode=streamer_mode,
                is_self=False,
                placeholder=placeholder,
            )
        elif isinstance(value, list):
            result[key] = [
                redact_player(item, streamer_mode=streamer_mode, placeholder=placeholder)
                if isinstance(item, Mapping)
                else deepcopy(item)
                for item in value
            ]
        else:
            result[key] = deepcopy(value)
    # Add a rendering-safe label only when there was an identity field to
    # replace.  The label is deliberately shared and carries no correlation.
    result["display_name"] = placeholder
    result["redacted"] = True
    if incognito:
        result["Incognito"] = True
    return result


def redact_match_payload(
    payload: Mapping[str, Any], *, streamer_mode: bool = False
) -> dict[str, Any]:
    """Redact all player records in a match payload without mutating it."""

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")

    def walk(value: Any, in_player_list: bool = False) -> Any:
        if isinstance(value, Mapping):
            # Riot payloads use Players/participants, while API responses can
            # use ``player`` for an individual record.
            looks_like_player = in_player_list or any(
                _normal_key(key) in _IDENTITY_KEYS or _normal_key(key) in _INCOGNITO_KEYS
                for key in value
            )
            if looks_like_player:
                return redact_player(value, streamer_mode=streamer_mode)
            result: dict[str, Any] = {}
            for key, child in value.items():
                normalized = _normal_key(key)
                child_is_players = normalized in {"players", "participants", "playerlist", "player_list"}
                result[key] = walk(child, in_player_list=child_is_players)
            return result
        if isinstance(value, list):
            return [walk(item, in_player_list=in_player_list) for item in value]
        return deepcopy(value)

    return cast(dict[str, Any], walk(payload))


redact_payload = redact_match_payload
sanitize_match_payload = redact_match_payload
redact_player_identity = redact_player

"""Reject empty TFT damage telemetry instead of presenting a false lobby of 0s."""

from collections.abc import Mapping, Sequence
from typing import Any


def damage_to_players(participant: Mapping[str, Any]) -> int | None:
    values = [participant.get(key) for key in ('total_damage_to_players', 'totalDamageToPlayers', 'damage_to_players')]
    valid = [value for value in values if type(value) is int and 0 <= value <= 100_000]
    return max(valid) if valid else None


def damage_available(participants: Sequence[Mapping[str, Any]]) -> bool:
    recorded = [value for row in participants if (value := damage_to_players(row)) is not None]
    # Finished multi-player TFT histories with no damage anywhere are an
    # incomplete provider field. Individual, genuinely recorded zeros survive.
    return not (len(recorded) >= 2 and max(recorded) == 0)


def clear_empty_lobby_damage(teams: object) -> object:
    """Apply the same rule to previously saved presentation DTOs."""
    if not isinstance(teams, (list, tuple)):
        return teams
    players = [player for team in teams if isinstance(team, Mapping) for player in team.get('players', []) if isinstance(player, Mapping)]
    values = [player.get('stats', {}).get('damage') for player in players if isinstance(player.get('stats'), Mapping)]
    valid = [value for value in values if type(value) is int and value >= 0]
    if len(valid) < 2 or max(valid) > 0:
        return teams
    return [{**team, 'players': [{**player, 'stats': {key: value for key, value in (player.get('stats') or {}).items() if key != 'damage'}} for player in team.get('players', []) if isinstance(player, Mapping)]} for team in teams if isinstance(team, Mapping)]

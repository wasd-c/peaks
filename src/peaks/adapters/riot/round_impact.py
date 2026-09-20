"""Personal round contributions from complete, reconciled match events.

KAST uses a five-second trade window. These are Peaks calculations, not a
provider rating. Subjects never leave the parser except as transient keys.
"""

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .match_analytics import _count, _get


def round_impact(
    payload: Mapping[str, Any], rounds: list[Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    info = _get(payload, "matchInfo")
    queue = _get(info, "queueID") if isinstance(info, Mapping) else None
    if queue not in {"competitive", "unrated", "swiftplay", "spikerush", "premier"}:
        return {}
    players = _get(payload, "players")
    if not isinstance(players, list) or not 2 <= len(players) <= 10 or not rounds:
        return {}
    teams: dict[str, str] = {}
    reported: dict[str, Mapping[str, Any]] = {}
    for player in players:
        if not isinstance(player, Mapping):
            return {}
        subject = _get(player, "subject") or _get(player, "puuid")
        team = _get(player, "teamId") or player.get("TeamID")
        stats = _get(player, "stats")
        if not isinstance(subject, str) or not subject or subject in teams or not isinstance(team, str) or not team or not isinstance(stats, Mapping):
            return {}
        teams[subject] = team
        reported[subject] = stats
    if len(set(teams.values())) != 2:
        return {}

    totals = {subject: Counter[str]() for subject in teams}
    damage_complete = True
    assists_complete = True
    first_complete = True
    winners_complete = True
    for raw_round in rounds:
        records = _get(raw_round, "playerStats")
        if not isinstance(records, list) or len(records) != len(teams):
            return {}
        seen: set[str] = set()
        events: dict[tuple[str, str, int], tuple[str, ...] | None] = {}
        for record in records:
            if not isinstance(record, Mapping):
                return {}
            subject = _get(record, "subject") or _get(record, "puuid")
            if not isinstance(subject, str) or subject not in teams or subject in seen:
                return {}
            seen.add(subject)
            kills = _get(record, "kills")
            if not isinstance(kills, list) or len(kills) > 64:
                return {}
            for event in kills:
                if not isinstance(event, Mapping):
                    return {}
                killer, victim = _get(event, "killer"), _get(event, "victim")
                at = _get(event, "timeSinceRoundStartMillis")
                if at is None:
                    at = _get(event, "roundTime")
                if killer != subject or not isinstance(victim, str) or victim not in teams or teams[killer] == teams[victim] or not _count(at, 86_400_000):
                    return {}
                assistants = _get(event, "assistants")
                valid_assists = isinstance(assistants, list) and len(assistants) <= 5 and all(
                    assistant in teams and teams[assistant] == teams[killer] and assistant != killer
                    for assistant in assistants if isinstance(assistant, str)
                ) and all(isinstance(assistant, str) for assistant in assistants)
                if not valid_assists:
                    assists_complete = False
                value = tuple(sorted(set(assistants))) if valid_assists else None
                key = (killer, victim, at)
                if key in events and events[key] != value:
                    return {}
                events[key] = value
            damage = _get(record, "damage")
            if not isinstance(damage, list) or len(damage) > 64:
                damage_complete = False
                continue
            for event in damage:
                if not isinstance(event, Mapping):
                    damage_complete = False
                    continue
                receiver, amount = _get(event, "receiver"), _get(event, "damage")
                if not isinstance(receiver, str) or receiver not in teams or not _count(amount):
                    damage_complete = False
                    continue
                totals[receiver]["damage_received"] += amount

        ordered = sorted(events, key=lambda event: event[2])
        if len(ordered) > 1 and ordered[0][2] == ordered[1][2]:
            first_complete = False
        elif ordered:
            totals[ordered[0][0]]["first_kills"] += 1
            totals[ordered[0][1]]["first_deaths"] += 1
        winner = _get(raw_round, "winningTeam")
        if winner not in teams.values():
            winners_complete = False
        for subject, team in teams.items():
            own_kills = [event for event in ordered if event[0] == subject]
            deaths = [event for event in ordered if event[1] == subject]
            assists = sum(subject in (events[event] or ()) for event in ordered)
            totals[subject]["kills"] += len(own_kills)
            totals[subject]["deaths"] += len(deaths)
            totals[subject]["assists"] += assists
            traded = any(
                victim == death[0] and teams[killer] == team and 0 < at - death[2] <= 5_000
                for death in deaths for killer, victim, at in ordered
            )
            totals[subject]["kast_rounds"] += bool(own_kills or assists or not deaths or traded)
            totals[subject]["flawless_rounds"] += winner == team and not any(teams[event[1]] == team for event in ordered)
            totals[subject]["aces"] += len({event[1] for event in own_kills}) >= 5

    # Missing events cannot masquerade as survival, a flawless round or a trade.
    for subject, stats in reported.items():
        if any(not _count(_get(stats, field)) or _get(stats, field) != totals[subject][field] for field in ("kills", "deaths")):
            return {}
        if _get(stats, "assists") != totals[subject]["assists"]:
            assists_complete = False
    return {
        subject: {
            "impact_rounds": len(rounds),
            "aces": values["aces"],
            **({"kast_rounds": values["kast_rounds"]} if assists_complete else {}),
            **({"damage_received": values["damage_received"]} if damage_complete else {}),
            **({"first_kills": values["first_kills"], "first_deaths": values["first_deaths"]} if first_complete else {}),
            **({"flawless_rounds": values["flawless_rounds"]} if winners_complete else {}),
        }
        for subject, values in totals.items()
    }

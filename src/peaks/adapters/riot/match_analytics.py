"""Bounded, presentation-only aggregates from VALORANT recorded round events.

Subjects are transient dictionary keys; callers store only the aggregate values.
Weapon names are the public base-item catalog from valorant-api.com/v1/weapons
(2026-09-04). Unknown IDs remain 'Other weapon'; raw IDs never reach the UI.
"""

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

WEAPON_NAMES = {
    "63e6c2b6-4a8e-869c-3d4c-e38355226584": "Odin",
    "55d8a0f4-4274-ca67-fe2c-06ab45efdf58": "Ares",
    "9c82e19d-4575-0200-1a81-3eacf00cf872": "Vandal",
    "ae3de142-4d85-2547-dd26-4e90bed35cf7": "Bulldog",
    "ee8e8d15-496b-07ac-e5f6-8fae5d4c7b1a": "Phantom",
    "ec845bf4-4f79-ddda-a3da-0db3774b2794": "Judge",
    "910be174-449b-c412-ab22-d0873436b21b": "Bucky",
    "44d4e95c-4157-0037-81b2-17841bf2e8e3": "Frenzy",
    "29a0cfab-485b-f5d5-779a-b59f85e204a8": "Classic",
    "410b2e0b-4ceb-1321-1727-20858f7f3477": "Bandit",
    "1baa85b4-4c70-1284-64bb-6481dfc3bb4e": "Ghost",
    "e336c6b8-418d-9340-d77f-7a9e4cfe0702": "Sheriff",
    "42da8ccc-40d5-affc-beec-15aa47b42eda": "Shorty",
    "a03b24d3-4319-996d-0f8c-94bbfba1dfc7": "Operator",
    "4ade7faa-4cf1-8376-95ef-39884480959b": "Guardian",
    "5f0aaf7a-4289-3998-d5ff-eb9a5cf7ef5c": "Outlaw",
    "c4883e50-4494-202c-3ec3-6b8a9284f00b": "Marshal",
    "462080d1-4035-2937-7c09-27aa2a5c27a7": "Spectre",
    "f7e1b454-4ad4-1063-ec0a-159e56b58941": "Stinger",
    "2f59173c-4bed-b6c3-2191-dea9b58be9c7": "Melee",
}


@dataclass(frozen=True, slots=True)
class RoundAnalytics:
    headshots: int | None = None
    bodyshots: int | None = None
    legshots: int | None = None
    damage: int | None = None
    round_kills: tuple[int, ...] | None = None
    weapon_usage: tuple[tuple[str, int], ...] | None = None
    rounds_analyzed: int = 0
    surrendered_rounds: int = 0


def _get(value: Mapping[str, Any], name: str) -> Any:
    return value.get(name, value.get(name[0].upper() + name[1:]))


def _count(value: object, maximum: int = 1_000_000) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum


def _surrender_marker(raw_round: Mapping[str, Any]) -> bool | None:
    markers = [_get(raw_round, name) for name in ("roundResult", "roundResultCode")]
    if not any(isinstance(value, str) and value.casefold() == "surrendered" for value in markers):
        return False
    if any(value is not None and (not isinstance(value, str) or value.casefold() != "surrendered") for value in markers):
        return None
    return True


def _event_empty_round(raw_round: Mapping[str, Any]) -> bool:
    """Explicit surrender metadata alone cannot hide combat or missing data."""
    stats = _get(raw_round, "playerStats")
    if not isinstance(stats, list) or len(stats) > 20:
        return False
    seen: set[str] = set()
    for stat in stats:
        if not isinstance(stat, Mapping):
            return False
        subject = _get(stat, "subject") or _get(stat, "puuid")
        if not isinstance(subject, str) or not 1 <= len(subject) <= 128 or subject in seen:
            return False
        seen.add(subject)
        if _get(stat, "kills") != [] or _get(stat, "damage") != []:
            return False
        score = _get(stat, "score")
        if score is not None and (not _count(score) or score != 0):
            return False
    for name in ("bombPlanter", "bombDefuser"):
        if _get(raw_round, name) not in (None, ""):
            return False
    for name in ("plantRoundTime", "defuseRoundTime"):
        number = _get(raw_round, name)
        if number is not None and (not _count(number) or number != 0):
            return False
    return True


def parse_round_analytics(payload: Mapping[str, Any]) -> dict[str, RoundAnalytics]:
    """Aggregate complete per-player event windows; absence never becomes zero.

    A partial/malformed window cannot award multikill or low-activity tags.
    A round's weapon is the killing weapon in finishingDamage, never the
    purchased/equipped weapon (which would misattribute ability and sidearm kills).
    """
    rounds = _get(payload, "roundResults")
    if not isinstance(rounds, list) or not 1 <= len(rounds) <= 128:
        return {}
    by_subject: dict[str, list[Mapping[str, Any]]] = {}
    seen_rounds: set[int] = set()
    indexed_rounds: list[tuple[int, Mapping[str, Any]]] = []
    for index, raw_round in enumerate(rounds):
        if not isinstance(raw_round, Mapping):
            return {}
        round_index = _get(raw_round, "roundNum")
        if round_index is None:
            round_index = index
        elif not _count(round_index, 1000):
            return {}
        if round_index in seen_rounds:
            return {}
        seen_rounds.add(round_index)
        indexed_rounds.append((round_index, raw_round))
    first_round = min(seen_rounds)
    if first_round not in {0, 1} or sorted(seen_rounds) != list(range(first_round, first_round + len(rounds))):
        return {}
    played_rounds: list[Mapping[str, Any]] = []
    surrendered_rounds = 0
    info = _get(payload, "matchInfo")
    completion = _get(info, "completionState") if isinstance(info, Mapping) else None
    for _round_index, raw_round in sorted(indexed_rounds, key=lambda item: item[0]):
        surrender = _surrender_marker(raw_round)
        if surrender is None:
            return {}
        if surrender and _event_empty_round(raw_round):
            if completion is not None and (not isinstance(completion, str) or completion.casefold() != "surrendered"):
                return {}
            surrendered_rounds += 1
            continue
        # Awarded rows must be a terminal suffix, never gaps in real play.
        if surrendered_rounds:
            return {}
        played_rounds.append(raw_round)
    for raw_round in played_rounds:
        stats = _get(raw_round, "playerStats")
        if not isinstance(stats, list) or len(stats) > 20:
            return {}
        seen_players: set[str] = set()
        for stat in stats:
            if not isinstance(stat, Mapping):
                continue
            subject = _get(stat, "subject") or _get(stat, "puuid")
            if not isinstance(subject, str) or not 1 <= len(subject) <= 128:
                continue
            if subject in seen_players:
                return {}
            seen_players.add(subject)
            if subject not in by_subject and len(by_subject) >= 20:
                continue
            by_subject.setdefault(subject, []).append(stat)

    result: dict[str, RoundAnalytics] = {}
    for subject, records in by_subject.items():
        if len(records) != len(played_rounds):
            continue
        totals = {"headshots": 0, "bodyshots": 0, "legshots": 0, "damage": 0}
        complete_damage = True
        complete_kills = True
        complete_weapons = True
        round_kills: list[int] = []
        weapons: Counter[str] = Counter()
        for record in records:
            damage = _get(record, "damage")
            if not isinstance(damage, list) or len(damage) > 64:
                complete_damage = False
            else:
                for event in damage:
                    if not isinstance(event, Mapping):
                        complete_damage = False
                        continue
                    for field in totals:
                        number = _get(event, field)
                        if not _count(number):
                            complete_damage = False
                        else:
                            totals[field] += number

            kills = _get(record, "kills")
            if not isinstance(kills, list) or len(kills) > 64:
                complete_kills = False
                continue
            count = 0
            seen_events: set[tuple[str, int]] = set()
            for event in kills:
                if not isinstance(event, Mapping):
                    complete_kills = False
                    continue
                killer, victim = _get(event, "killer"), _get(event, "victim")
                time = _get(event, "timeSinceRoundStartMillis")
                if time is None:
                    time = _get(event, "roundTime")
                if killer != subject or not isinstance(victim, str) or not victim or victim == subject:
                    complete_kills = False
                    continue
                if not _count(time, 86_400_000):
                    complete_kills = False
                    continue
                key = (victim, time)
                if key in seen_events:
                    continue
                seen_events.add(key)
                count += 1
                finish = _get(event, "finishingDamage")
                if not isinstance(finish, Mapping):
                    complete_weapons = False
                    continue
                damage_type = _get(finish, "damageType")
                if not isinstance(damage_type, str):
                    complete_weapons = False
                elif damage_type.casefold() == "weapon":
                    item = _get(finish, "damageItem")
                    weapons[WEAPON_NAMES.get(str(item).lower(), "Other weapon")] += 1
                elif damage_type.casefold() == "melee":
                    item = WEAPON_NAMES.get(str(_get(finish, "damageItem")).lower())
                    if item is not None and item != "Melee":
                        complete_weapons = False
                    else:
                        weapons["Melee"] += 1
                elif damage_type.casefold() not in {"ability", "bomb", "fall"}:
                    complete_weapons = False
            round_kills.append(count)

        result[subject] = RoundAnalytics(
            **(totals if complete_damage else {}),
            round_kills=tuple(round_kills) if complete_kills else None,
            weapon_usage=tuple(weapons.most_common(32)) if complete_kills and complete_weapons else None,
            rounds_analyzed=len(played_rounds),
            surrendered_rounds=surrendered_rounds,
        )
    return result

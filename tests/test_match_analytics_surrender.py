from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from peaks.adapters.riot.match_analytics import parse_round_analytics
from peaks.adapters.riot.valorant import ValorantMatchSummary, parse_match_details
from peaks.bridge import _match_stats

VANDAL = "9c82e19d-4575-0200-1a81-3eacf00cf872"


def event(index: int, *, kind: str = "Weapon", item: str = VANDAL) -> dict[str, Any]:
    return {
        "killer": "own",
        "victim": f"opponent-{index}",
        "roundTime": index + 1,
        "finishingDamage": {"damageType": kind, "damageItem": item},
    }


def surrender_match() -> dict[str, Any]:
    rounds = [
        {
            "roundNum": index,
            "roundResult": "Eliminated",
            "roundResultCode": "Elimination",
            "playerStats": [
                {
                    "subject": "own",
                    "kills": [event(index)],
                    "damage": [{"damage": 150, "headshots": 1, "bodyshots": 0, "legshots": 0}],
                }
            ],
        }
        for index in range(11)
    ]
    rounds += [
        {
            "roundNum": index,
            "roundResult": "Surrendered",
            "roundResultCode": "Surrendered",
            "playerStats": [{"subject": "own", "kills": [], "damage": [], "score": 0}],
            "plantRoundTime": 0,
            "defuseRoundTime": 0,
        }
        for index in range(11, 16)
    ]
    return {
        "matchInfo": {"matchId": "synthetic-match", "completionState": "Surrendered"},
        "players": [
            {
                "subject": "own",
                "teamId": "Blue",
                "stats": {"kills": 11, "roundsPlayed": 12, "score": 2400},
            }
        ],
        "roundResults": rounds,
    }


def player(data: dict[str, Any]):
    return (
        parse_match_details(data, puuid="own", fallback=ValorantMatchSummary("synthetic-match"))
        .teams[0]
        .players[0]
    )


def test_melee_finish_keeps_complete_twenty_nine_weapon_plus_one_melee_breakdown() -> None:
    payload = {
        "roundResults": [
            {
                "roundNum": 0,
                "playerStats": [
                    {
                        "subject": "own",
                        "damage": [],
                        "kills": [event(index) for index in range(29)]
                        + [event(29, kind="Melee", item="unlisted-melee-item")],
                    }
                ],
            }
        ]
    }
    analytics = parse_round_analytics(payload)["own"]
    assert analytics.weapon_usage == (("Vandal", 29), ("Melee", 1))
    assert analytics.round_kills == (30,)
    assert "unlisted-melee-item" not in repr(analytics)
    payload["roundResults"][0]["playerStats"][0]["kills"][-1]["finishingDamage"]["damageItem"] = (
        VANDAL
    )
    assert parse_round_analytics(payload)["own"].weapon_usage is None


def test_surrender_awards_are_not_zero_kill_rounds_and_preserve_official_denominator() -> None:
    data = surrender_match()
    analytics = parse_round_analytics(data)["own"]
    assert analytics.round_kills == (1,) * 11
    assert analytics.rounds_analyzed == 11 and analytics.surrendered_rounds == 5
    parsed = player(data)
    assert parsed.round_kills == (1,) * 11 and parsed.weapon_usage == (("Vandal", 11),)
    assert (parsed.rounds_played, parsed.rounds_analyzed, parsed.combat_score) == (12, 11, 2400)
    assert parsed.headshots == 11 and parsed.damage == 1650
    assert _match_stats(
        {"roundsPlayed": 12, "roundsAnalyzed": 11, "roundKills": list(parsed.round_kills)}
    ) == {
        "roundsPlayed": 12,
        "roundsAnalyzed": 11,
        "roundKills": [1] * 11,
    }


def test_surrender_round_with_real_events_stays_in_the_analytics_window() -> None:
    data = surrender_match()
    data["roundResults"][11]["playerStats"][0]["kills"] = [event(11)]
    data["players"][0]["stats"]["kills"] = 12
    parsed = player(data)
    assert parsed.round_kills == (1,) * 12
    assert parsed.rounds_analyzed == parsed.rounds_played == 12


def test_ordinary_zero_kill_round_is_not_filtered_just_because_it_is_empty() -> None:
    data = surrender_match()
    data["roundResults"][10]["playerStats"][0]["kills"] = []
    data["roundResults"][10]["playerStats"][0]["damage"] = []
    data["players"][0]["stats"]["kills"] = 10
    assert player(data).round_kills == (1,) * 10 + (0,)


@pytest.mark.parametrize(
    "change",
    [
        "conflicting-marker",
        "conflicting-completion",
        "interrupted-suffix",
        "missing-damage",
        "missing-kills",
        "duplicate-round",
        "duplicate-player",
    ],
)
def test_surrender_does_not_relax_incomplete_or_conflicting_window_validation(change: str) -> None:
    data = surrender_match()
    if change == "conflicting-marker":
        data["roundResults"][11]["roundResultCode"] = "Elimination"
    elif change == "conflicting-completion":
        data["matchInfo"]["completionState"] = "Completed"
    elif change == "interrupted-suffix":
        data["roundResults"][12]["roundResult"] = data["roundResults"][12]["roundResultCode"] = (
            "Eliminated"
        )
    elif change == "duplicate-round":
        data["roundResults"][12]["roundNum"] = 11
    elif change == "duplicate-player":
        data["roundResults"][12]["playerStats"] *= 2
    else:
        del data["roundResults"][12]["playerStats"][0][
            "damage" if change == "missing-damage" else "kills"
        ]
    assert parse_round_analytics(data) == {}
    assert player(data).round_kills is None and player(data).weapon_usage is None


def test_reported_round_and_kill_counts_still_reject_incomplete_analytics() -> None:
    data = surrender_match()
    for count in (5, 13, 16):
        changed = deepcopy(data)
        changed["players"][0]["stats"]["roundsPlayed"] = count
        assert player(changed).round_kills is None and player(changed).rounds_analyzed is None
    data["players"][0]["stats"]["kills"] = 15
    assert player(data).round_kills is None and player(data).weapon_usage is None


def test_missing_ordinary_round_player_is_not_fixed_by_a_valid_surrender_suffix() -> None:
    data = surrender_match()
    data["roundResults"][4]["playerStats"] = []
    assert parse_round_analytics(data) == {}


def test_empty_match_of_only_awarded_rounds_does_not_claim_played_events() -> None:
    data = surrender_match()
    data["roundResults"] = data["roundResults"][11:]
    for index, row in enumerate(data["roundResults"]):
        row["roundNum"] = index
    assert parse_round_analytics(data) == {}

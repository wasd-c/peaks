from copy import deepcopy

from peaks.adapters.riot.match_analytics import parse_round_analytics

VANDAL = "9c82e19d-4575-0200-1a81-3eacf00cf872"


def kill(victim, time, weapon=VANDAL, damage_type="Weapon"):
    return {
        "killer": "own", "victim": victim, "timeSinceRoundStartMillis": time,
        "finishingDamage": {"damageType": damage_type, "damageItem": weapon},
    }


def payload():
    return {"roundResults": [
        {"roundNum": 0, "playerStats": [{"subject": "own", "kills": [
            kill("a", 1000), kill("b", 2000), kill("c", 3000, "ability", "Ability"),
        ], "damage": [{"headshots": 3, "bodyshots": 6, "legshots": 1, "damage": 450}]}]},
        {"roundNum": 1, "playerStats": [{"subject": "own", "kills": [], "damage": []}]},
    ]}


def test_shots_damage_multikills_and_only_actual_killing_weapons():
    result = parse_round_analytics(payload())["own"]
    assert (result.headshots, result.bodyshots, result.legshots, result.damage) == (3, 6, 1, 450)
    assert result.round_kills == (3, 0)
    assert result.weapon_usage == (("Vandal", 2),)


def test_duplicate_kill_event_is_counted_once():
    data = payload()
    events = data["roundResults"][0]["playerStats"][0]["kills"]
    events.append(deepcopy(events[0]))
    assert parse_round_analytics(data)["own"].round_kills == (3, 0)


def test_missing_round_statistics_and_duplicate_rounds_are_not_zero_activity():
    data = payload()
    data["roundResults"][1]["playerStats"] = []
    assert parse_round_analytics(data) == {}
    data = payload()
    data["roundResults"][1]["roundNum"] = 0
    assert parse_round_analytics(data) == {}


def test_partial_damage_and_kill_evidence_stays_unavailable():
    data = payload()
    del data["roundResults"][0]["playerStats"][0]["damage"][0]["bodyshots"]
    del data["roundResults"][1]["playerStats"][0]["kills"]
    result = parse_round_analytics(data)["own"]
    assert result.headshots is None
    assert result.round_kills is None
    assert result.weapon_usage is None


def test_unknown_weapon_does_not_leak_raw_identifier():
    data = payload()
    data["roundResults"][0]["playerStats"][0]["kills"][0]["finishingDamage"]["damageItem"] = "private-value"
    result = parse_round_analytics(data)["own"]
    assert ("Other weapon", 1) in result.weapon_usage
    assert "private-value" not in repr(result)


def test_invalid_counts_and_oversized_or_absent_payloads_are_rejected():
    data = payload()
    data["roundResults"][0]["playerStats"][0]["damage"][0]["headshots"] = True
    assert parse_round_analytics(data)["own"].headshots is None
    assert parse_round_analytics({}) == {}
    assert parse_round_analytics({"roundResults": [{}] * 129}) == {}


def test_missing_weapon_classification_does_not_claim_zero_weapon_kills():
    data = payload()
    del data["roundResults"][0]["playerStats"][0]["kills"][0]["finishingDamage"]
    result = parse_round_analytics(data)["own"]
    assert result.round_kills == (3, 0)
    assert result.weapon_usage is None
    assert result.headshots == 3


def test_sparse_or_invalid_round_indices_are_not_a_complete_match_window():
    data = payload()
    data["roundResults"][1]["roundNum"] = 2
    assert parse_round_analytics(data) == {}
    data["roundResults"][1]["roundNum"] = "bad"
    assert parse_round_analytics(data) == {}


def test_round_events_are_ordered_by_round_number():
    data = payload()
    data["roundResults"].reverse()
    assert parse_round_analytics(data)["own"].round_kills == (3, 0)

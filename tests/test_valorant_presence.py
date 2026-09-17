from __future__ import annotations

import base64
import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from peaks.adapters.riot.client import RiotClientUnavailable
from peaks.adapters.riot.valorant import ValorantClient, ValorantCoregame, ValorantPlayer
from peaks.adapters.riot.valorant_presence import (
    ValorantParty,
    ValorantPresence,
    parse_own_presence,
    parse_party,
    party_identifier,
)
from peaks.application.runtime import CurrentGameService

MAP = "/Game/Maps/Ascent/Ascent"
NOW = 2_000_000
OBSERVED = NOW - 10_000


def row(private_data: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    return {
        "puuid": "owned",
        "product": "valorant",
        "time": NOW,
        "private": base64.b64encode(json.dumps(private_data).encode()).decode(),
        **overrides,
    }


def private(**overrides: Any) -> dict[str, Any]:
    return {
        "isValid": True,
        "sessionLoopState": "INGAME",
        "matchMap": MAP,
        "matchScoreAllyTeam": 7,
        "matchScoreEnemyTeam": 5,
        "partySize": 2,
        "maxPartySize": 5,
        "privateJwt": "must-never-project",
        "partyId": "private-party-id",
        **overrides,
    }


def parse(rows: list[dict[str, Any]], **overrides: Any) -> ValorantPresence:
    arguments = {
        "subject": "owned",
        "match_id": "current-match",
        "map_id": MAP,
        "phase": "live",
        "observed_at_ms": OBSERVED,
        "now_ms": NOW,
        **overrides,
    }
    return parse_own_presence({"presences": rows}, **arguments)


def test_flat_presence_uses_only_own_subject_and_retains_no_private_data() -> None:
    result = parse([row(private(matchScoreAllyTeam=99), puuid="friend"), row(private())])
    assert result == ValorantPresence(7, 5, 2, 5)
    assert "private" not in repr(result) and "owned" not in repr(result)


def test_nested_presence_matches_current_riot_client_shape() -> None:
    result = parse(
        [
            row(
                {
                    "matchPresenceData": private(),
                    "partyPresenceData": {"partySize": 3, "maxPartySize": 5},
                }
            )
        ]
    )
    assert result == ValorantPresence(7, 5, 3, 5)


def test_queue_is_projected_only_from_the_verified_current_presence() -> None:
    assert parse([row(private(queueId="deathmatch"))]).queue_id == "deathmatch"
    assert parse([row(private(queueId="deathmatch"), time=OBSERVED - 1)]).queue_id is None
    assert parse([row(private(queueId="unsafe\nqueue"))]).queue_id is None


@pytest.mark.parametrize(
    "changed",
    [
        {"sessionLoopState": "MENUS"},
        {"matchMap": "/Game/Maps/Bind/Bind"},
        {"matchId": "previous-match"},
        {"isValid": False},
    ],
)
def test_presence_rejects_different_game_or_invalid_payload(changed: dict[str, Any]) -> None:
    assert parse([row(private(**changed))]) == ValorantPresence()


@pytest.mark.parametrize(
    "changed",
    [
        {"puuid": "someone-else"},
        {"product": "league_of_legends"},
        {"time": OBSERVED - 1},
        {"time": NOW + 30_001},
        {"time": NOW - 300_001},
        {"time": None},
        {"private": "not-base64"},
        {"private": "A" * 65_537},
    ],
)
def test_old_same_map_and_foreign_presence_cannot_become_current_score(
    changed: dict[str, Any],
) -> None:
    assert parse([row(private(), **changed)]) == ValorantPresence()


def test_new_presence_update_unblocks_score_after_first_glz_observation() -> None:
    assert parse([row(private(), time=OBSERVED - 1)]).ally_score is None
    assert parse([row(private(), time=OBSERVED)]).ally_score == 7
    # A provider that explicitly supplies the correct match ID does not need
    # the weaker observation-time correlation to prove the match association.
    assert parse([row(private(matchId="current-match"), time=OBSERVED - 1)]).ally_score == 7


def test_newer_own_menu_presence_blocks_older_in_game_row() -> None:
    assert (
        parse([row(private()), row(private(sessionLoopState="MENUS"), time=NOW + 1)])
        == ValorantPresence()
    )


def test_individual_kda_is_never_inferred_from_unverified_presence_fields() -> None:
    result = parse([row(private(kills=17, deaths=4, matchKills=17, matchDeaths=4))])
    assert not hasattr(result, "kills") and not hasattr(result, "deaths")
    assert parse([row(private(matchScoreAllyTeam=True))]).ally_score is None
    assert parse([row(private(matchScoreEnemyTeam=-1))]).enemy_score is None
    assert parse([row(private(partySize=10, maxPartySize=5))]).party_max is None


def test_pregame_presence_does_not_reuse_live_round_scores() -> None:
    result = parse([row(private(sessionLoopState="PREGAME"))], phase="pregame")
    assert result == ValorantPresence(party_size=2, party_max=5)


@pytest.mark.parametrize("nested", [False, True])
def test_party_owner_scores_require_current_teammate_and_current_match(nested: bool) -> None:
    owner = {
        "partyOwnerMatchMap": MAP,
        "partyOwnerSessionLoopState": "INGAME",
        "partyOwnerMatchScoreAllyTeam": 9,
        "partyOwnerMatchScoreEnemyTeam": 6,
        "partySize": 2,
        "maxPartySize": 5,
    }
    payload = (
        {"matchPresenceData": {"sessionLoopState": "INGAME"}, "partyPresenceData": owner}
        if nested
        else {"sessionLoopState": "INGAME", **owner}
    )
    assert parse([row(payload)]) == ValorantPresence()
    assert parse([row(payload)], party_owner_in_own_team=True) == ValorantPresence(9, 6, 2, 5)
    assert (
        parse([row(payload, time=OBSERVED - 1)], party_owner_in_own_team=True) == ValorantPresence()
    )
    target = payload["partyPresenceData"] if nested else payload
    target["partyOwnerSessionLoopState"] = "MENUS"
    assert parse([row(payload)], party_owner_in_own_team=True).ally_score is None
    target["partyOwnerSessionLoopState"] = "INGAME"
    target["partyOwnerMatchMap"] = "/Game/Maps/Bind/Bind"
    assert parse([row(payload)], party_owner_in_own_team=True) == ValorantPresence()


@pytest.mark.parametrize(
    "owner,teammates,expected", [("owned", (), True), ("duo", ("duo",), True), ("duo", (), False)]
)
def test_party_owner_score_viewpoint_requires_self_or_verified_teammate(
    owner: str,
    teammates: tuple[str, ...],
    expected: bool,
) -> None:
    payload = party_payload(
        Members=[
            {"Subject": "owned", "IsOwner": owner == "owned"},
            {"Subject": "duo", "IsOwner": owner == "duo"},
        ]
    )
    result = parse_party(
        payload, subject="owned", expected_id="own-party", own_team_subjects=teammates
    )
    assert result is not None and result.owner_in_own_team is expected


def party_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "ID": "own-party",
        "Members": [{"Subject": "owned"}, {"Subject": "duo"}],
        "MatchmakingData": {"QueueID": "competitive"},
        "CustomGameData": {"MaxPartySize": 10},
        **overrides,
    }


def test_party_membership_is_subject_bound_and_not_the_five_player_team() -> None:
    assert (
        party_identifier({"Subject": "owned", "CurrentPartyID": "own-party"}, subject="owned")
        == "own-party"
    )
    assert (
        party_identifier({"Subject": "other", "CurrentPartyID": "own-party"}, subject="owned")
        is None
    )
    assert (
        party_identifier({"Subject": "owned", "CurrentPartyID": "../other"}, subject="owned")
        is None
    )
    party = parse_party(party_payload(), subject="owned", expected_id="own-party")
    assert party is not None and party.size == 2 and party.maximum is None
    custom_party = parse_party(
        party_payload(MatchmakingData={"QueueID": "custom"}),
        subject="owned",
        expected_id="own-party",
    )
    assert custom_party is not None and custom_party.size == 2 and custom_party.maximum == 10


@pytest.mark.parametrize(
    "payload",
    [
        party_payload(ID="different"),
        party_payload(Members=[{"Subject": "other"}]),
        party_payload(Members=[{"Subject": "owned"}, {"Subject": "owned"}]),
        party_payload(Members=[{"Subject": "owned"}, {"Subject": "../other"}]),
        party_payload(Members=[]),
    ],
)
def test_party_response_must_match_requested_party_and_contain_self(
    payload: dict[str, Any],
) -> None:
    assert parse_party(payload, subject="owned", expected_id="own-party") is None


def test_party_client_follows_only_current_subjects_returned_party() -> None:
    class HTTP:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, path: str) -> dict[str, Any]:
            self.calls.append(path)
            return (
                {"Subject": "owned", "CurrentPartyID": "own-party"}
                if len(self.calls) == 1
                else party_payload()
            )

    http = HTTP()
    client = ValorantClient(http, "owned")  # type: ignore[arg-type]
    party = client.own_party()
    assert party is not None and party.size == 2 and party.maximum is None
    assert http.calls == ["/parties/v1/players/owned", "/parties/v1/parties/own-party"]

    http.calls = []
    http.get_json = lambda path: {"Subject": "other", "CurrentPartyID": "not-authorized"}  # type: ignore[method-assign]
    assert client.own_party() is None


def test_presence_runtime_maps_score_by_self_team_and_keeps_kda_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = ValorantCoregame(
        "current-match",
        MAP,
        None,
        (
            ValorantPlayer("enemy", "Red", "omen"),
            ValorantPlayer("owned", "Blue", "jett"),
            *(ValorantPlayer(f"ally-{index}", "Blue", "agent") for index in range(4)),
        ),
    )
    client = SimpleNamespace(
        detect=lambda: match, rank=lambda: None, own_party=lambda **kwargs: ValorantParty(2)
    )
    context = MagicMock()
    context.__enter__.return_value = (client, "owned")
    service = CurrentGameService()
    monkeypatch.setattr(service, "_open_valorant_client", lambda discovery: context)
    monkeypatch.setattr(service, "_valorant_agent_names", lambda: {"jett": "Jett", "omen": "Omen"})
    monkeypatch.setattr(service, "_own_valorant_presence", lambda *args: ValorantPresence(7, 5))
    current = service._detect_valorant(object())
    assert current is not None
    assert current["partySize"] == 2 and "partyMax" not in current
    assert [(team["name"], team["score"]) for team in current["teams"]] == [("Red", 5), ("Blue", 7)]
    own_player = next(
        player for team in current["teams"] for player in team["players"] if player["self"]
    )
    assert own_player["agent"] == "Jett" and "stats" not in own_player
    assert "owned" not in repr(current)

    # Missing evidence on a later poll clears scores instead of freezing the
    # last score and advertising it indefinitely as live.
    monkeypatch.setattr(service, "_own_valorant_presence", lambda *args: ValorantPresence())
    assert all(team["score"] == "—" for team in service._detect_valorant(object())["teams"])  # type: ignore[index]

    # FFA or spectator rosters cannot assign the two-team presence score.
    match = replace(
        match, players=tuple(player for player in match.players if player.subject != "owned")
    )
    monkeypatch.setattr(service, "_own_valorant_presence", lambda *args: ValorantPresence(7, 5))
    assert all(team["score"] == "—" for team in service._detect_valorant(object())["teams"])  # type: ignore[index]


def test_local_presence_unavailability_does_not_interrupt_match_detection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Local:
        def __init__(self, lockfile: object, **kwargs: Any) -> None:
            pass

        def __enter__(self) -> Local:
            raise RiotClientUnavailable("Unavailable")

        def __exit__(self, *args: Any) -> None:
            pass

    monkeypatch.setattr("peaks.adapters.riot.client.RiotClientHTTP", Local)
    assert (
        CurrentGameService()._own_valorant_presence(
            SimpleNamespace(lockfile=object()), "owned", ValorantCoregame("match", MAP, None)
        )
        == ValorantPresence()
    )

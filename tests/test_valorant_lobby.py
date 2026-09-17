from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from peaks.adapters.riot.client import RiotClientUnavailable
from peaks.adapters.riot.valorant import ValorantClient
from peaks.adapters.riot.valorant_presence import parse_party


def party_payload(**changes: Any) -> dict[str, Any]:
    return {
        "ID": "our-party",
        "Members": [
            {
                "Subject": "self",
                "CompetitiveTier": 21,
                "PlayerIdentity": {
                    "Subject": "self",
                    "AccountLevel": 120,
                    "Incognito": False,
                    "HideAccountLevel": False,
                    "PlayerCardID": "card-id",
                },
                "IsOwner": True,
                "IsReady": True,
                "Pings": [{"Ping": 11, "GamePodID": "pod"}],
            },
            {
                "Subject": "friend",
                "PlayerIdentity": {"Subject": "friend", "AccountLevel": 45},
                "IsReady": False,
            },
        ],
        "State": "DEFAULT",
        "MatchmakingData": {"QueueID": "competitive"},
        "CustomGameData": {
            "MaxPartySize": 10,
            "Settings": {"Map": "/Game/Maps/Ascent/Ascent", "Mode": "/Game/GameModes/Bomb/BombGameMode"},
            "Membership": {"teamOne": [{"Subject": "self"}], "teamTwo": [{"Subject": "friend"}]},
        },
        "QueueEntryTime": "2026-09-17T12:00:00Z",
        "MUCName": "do-not-project-chat-room",
        "InviteCode": "do-not-project-invite",
        "VoiceRoomID": "do-not-project-voice-room",
        **changes,
    }


def test_own_lobby_contains_only_projected_roster_facts() -> None:
    result = parse_party(party_payload(), subject="self", expected_id="our-party")
    assert result is not None
    assert result.phase == "lobby" and result.queue_id == "competitive"
    assert result.party_id == "our-party" and result.size == 2
    assert result.maximum is None  # Custom capacity is not the matchmaking capacity.
    assert result.map_id is None and result.mode_id is None and result.queue_started_at is None
    own, friend = result.members
    assert own.puuid == "self" and own.account_level == 120 and own.competitive_tier == 21
    assert own.is_owner is True and own.is_ready is True and own.player_card_id == "card-id"
    assert friend.is_ready is False and friend.is_owner is False and friend.account_level == 45
    assert own.team is None and friend.team is None
    assert "do-not-project" not in repr(asdict(result))
    assert "Pings" not in repr(asdict(result))


@pytest.mark.parametrize(
    "state,phase",
    [("DEFAULT", "lobby"), ("MATCHMAKING", "matchmaking"), ("MATCHMADE", None), ("PREGAME", None), ("INGAME", None), ("NEW_STATE", None), (None, None), ([], None)],
)
def test_party_states_cannot_invent_match_or_selection_telemetry(state: object, phase: str | None) -> None:
    result = parse_party(party_payload(State=state), subject="self", expected_id="our-party")
    assert result is not None and result.phase == phase
    assert (result.queue_started_at is not None) is (phase == "matchmaking")


@pytest.mark.parametrize("timestamp", ["", "bad", "0001-01-01T00:00:00Z", "2026-09-17T12:00:00", 1, "x" * 65])
def test_queue_timer_rejects_unset_or_unzoned_values(timestamp: object) -> None:
    result = parse_party(party_payload(State="MATCHMAKING", QueueEntryTime=timestamp), subject="self", expected_id="our-party")
    assert result is not None and result.queue_started_at is None


def test_custom_lobby_retains_actual_teams_map_and_capacity() -> None:
    result = parse_party(party_payload(MatchmakingData={"QueueID": "custom"}), subject="self", expected_id="our-party")
    assert result is not None and result.maximum == 10
    assert result.map_id == "/Game/Maps/Ascent/Ascent"
    assert result.mode_id == "/Game/GameModes/Bomb/BombGameMode"
    assert [member.team for member in result.members] == ["teamOne", "teamTwo"]


def test_unknown_queue_cannot_reuse_stale_custom_settings() -> None:
    result = parse_party(party_payload(MatchmakingData={"QueueID": ""}), subject="self", expected_id="our-party")
    assert result is not None and result.queue_id is None
    assert result.map_id is None and result.mode_id is None and result.maximum is None
    assert all(member.team is None for member in result.members)


def test_custom_membership_projects_only_current_members_and_rejects_ambiguous_teams() -> None:
    payload = party_payload(MatchmakingData={"QueueID": "custom"})
    payload["CustomGameData"]["Membership"]["teamSpectate"] = [{"Subject": "not-in-party"}]
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None and len(result.members) == 2
    payload["CustomGameData"]["Membership"]["teamTwo"].append({"Subject": "self"})
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None and all(member.team is None for member in result.members)


def test_party_respects_identity_privacy_and_does_not_guess_readiness() -> None:
    payload = party_payload()
    payload["Members"][1].update({"IsReady": "true", "CompetitiveTier": True})
    payload["Members"][1]["PlayerIdentity"].update({"Incognito": True, "HideAccountLevel": True})
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None
    friend = result.members[1]
    assert friend.incognito and friend.account_level_hidden and friend.account_level is None
    assert friend.is_ready is None and friend.competitive_tier is None


@pytest.mark.parametrize("marker", ["false", "true", 0, 1, None, {}, []])
def test_malformed_incognito_marker_fails_closed(marker: object) -> None:
    payload = party_payload()
    payload["Members"][1]["PlayerIdentity"]["Incognito"] = marker
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None and result.members[1].incognito is True


@pytest.mark.parametrize("nested", [True, False])
@pytest.mark.parametrize("marker", ["PrivacyModeV2", "AnonymousIdentity", "StreamerMask"])
def test_unknown_privacy_marker_fails_closed_even_when_false(marker: str, nested: bool) -> None:
    payload = party_payload()
    target = payload["Members"][1]["PlayerIdentity"] if nested else payload["Members"][1]
    target[marker] = False
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None and result.members[1].incognito is True


@pytest.mark.parametrize("marker", [True, "false", "true", 0, 1, None, {}, []])
def test_account_level_requires_actual_false_to_opt_out_of_present_privacy_marker(marker: object) -> None:
    payload = party_payload()
    payload["Members"][1]["PlayerIdentity"]["HideAccountLevel"] = marker
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None
    assert result.members[1].account_level_hidden is True
    assert result.members[1].account_level is None


@pytest.mark.parametrize("tier,expected", [(0, 0), (27, 27), (28, None), (99, None), (-1, None), (True, None)])
def test_party_competitive_tier_is_bounded_to_existing_ranks(tier: object, expected: int | None) -> None:
    payload = party_payload()
    payload["Members"][1]["CompetitiveTier"] = tier
    result = parse_party(payload, subject="self", expected_id="our-party")
    assert result is not None and result.members[1].competitive_tier == expected


@pytest.mark.parametrize("change", ["party-id", "foreign-owner", "foreign-identity", "duplicate", "oversized"])
def test_party_binding_failures_never_expose_a_roster(change: str) -> None:
    payload = party_payload()
    if change == "party-id":
        payload["ID"] = "other-party"
    elif change == "foreign-owner":
        payload["Members"] = payload["Members"][1:]
    elif change == "foreign-identity":
        payload["Members"][1]["PlayerIdentity"]["Subject"] = "someone-else"
    elif change == "duplicate":
        payload["Members"].append(payload["Members"][0])
    elif change == "oversized":
        payload["Members"] = [{"Subject": f"member-{index}"} for index in range(21)]
    assert parse_party(payload, subject="self", expected_id="our-party") is None


def test_client_failure_does_not_turn_into_an_empty_or_cached_lobby() -> None:
    class HTTP:
        def get_json(self, path: str) -> object:
            raise RiotClientUnavailable("disconnected")

    client = ValorantClient(HTTP(), "self")  # type: ignore[arg-type]
    assert client.own_party() is None

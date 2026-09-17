from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import peaks.application.runtime as runtime
from peaks.adapters.riot.valorant_presence import ValorantParty, ValorantPartyMember
from peaks.application.runtime import CurrentGameService

OWNER = "private-owner-subject"
FRIEND = "private-friend-subject"
HIDDEN = "private-hidden-subject"


def party(**changes: Any) -> ValorantParty:
    return replace(
        ValorantParty(
            size=3,
            members=(
                ValorantPartyMember(OWNER, account_level=42, competitive_tier=21, is_owner=True, is_ready=True),
                ValorantPartyMember(FRIEND, account_level=90, account_level_hidden=True, is_ready=False),
                ValorantPartyMember(HIDDEN, incognito=True),
            ),
            phase="lobby",
            queue_id="competitive",
            party_id="private-party-identifier",
        ),
        **changes,
    )


def client(current: ValorantParty | None) -> SimpleNamespace:
    return SimpleNamespace(
        detect=MagicMock(return_value=None),
        activity_available=True,
        own_party=MagicMock(return_value=current),
        player_names=MagicMock(return_value={OWNER: "Owner#EU", FRIEND: "Friend#EU", HIDDEN: "Never display#EU", "other": "Unrelated#EU"}),
        live_player_profiles=MagicMock(return_value={
            OWNER: {"currentRank": "Ascendant 3", "peakRank": "Immortal 1", "overallStats": {"kills": 24}},
            FRIEND: {"accountLevel": 999},
            HIDDEN: {"overallStats": {"kills": 99}},
        }),
    )


def test_valorant_party_lobby_looks_up_only_visible_members_and_projects_no_private_ids() -> None:
    source = client(party())
    view = CurrentGameService()._valorant_lobby_view(source, OWNER)
    assert view is not None
    source.player_names.assert_called_once_with((OWNER, FRIEND))
    source.live_player_profiles.assert_called_once_with((OWNER, FRIEND))
    assert view["game"] == "VALORANT" and view["phase"] == "lobby"
    assert view["queue"] == "competitive" and view["partySize"] == 3
    assert "id" not in view and "partyMax" not in view and "elapsed" not in view
    assert "map" not in view
    assert view["streamerMode"] is True
    own, friend, hidden = view["teams"][0]["players"]
    assert own["riotId"] == "Owner#EU" and own["self"] is True
    assert own["leader"] is True and own["ready"] is True and own["accountLevel"] == 42
    assert own["currentRank"] == "Ascendant 3" and own["peakRank"] == "Immortal 1"
    assert friend["ready"] is False and friend["accountLevel"] is None
    assert hidden["hidden"] is True and hidden["riotId"] is None
    assert "overallStats" not in hidden and "ready" not in hidden
    serialized = json.dumps(view)
    for private_value in (OWNER, FRIEND, HIDDEN, "private-party-identifier", "Never display", "Unrelated"):
        assert private_value not in serialized
    assert all(player["partyId"] == "party-1" for player in view["teams"][0]["players"])


def test_valorant_detect_falls_back_to_party_and_clears_previous_match_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    source = client(party())
    context = MagicMock()
    context.__enter__.return_value = (source, OWNER)
    service = CurrentGameService()
    service._valorant_live_match_id = "previous-match"
    service._valorant_live_names["previous-player"] = "Previous#EU"
    service._valorant_live_observed_at_ms = 123
    monkeypatch.setattr(service, "_open_valorant_client", lambda discovery: context)
    view = service._detect_valorant(object())
    assert view is not None and view["phase"] == "lobby"
    assert service.detection_available is True and service.active_account_puuid == OWNER
    assert service._valorant_live_match_id is None and service._valorant_live_observed_at_ms == 0
    assert service._valorant_live_names == {} and service._valorant_live_ranks == {}
    source.own_party.assert_called_once_with()
    context.__exit__.assert_called_once()


def test_valorant_queue_clock_uses_confirmed_entry_timestamp(monkeypatch: pytest.MonkeyPatch) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> FrozenDateTime:
            return cls(2026, 9, 17, 12, 2, 5, tzinfo=UTC)

    monkeypatch.setattr(runtime, "datetime", FrozenDateTime)
    source = client(party(phase="matchmaking", queue_started_at="2026-09-17T12:00:00Z"))
    view = CurrentGameService()._valorant_lobby_view(source, OWNER)
    assert view is not None and view["phase"] == "matchmaking"
    assert view["elapsed"] == "2:05" and view["status"] == "Searching for a match"
    assert "id" not in view


@pytest.mark.parametrize("phase", [None, "live", "pregame", "unknown"])
def test_retained_party_object_cannot_replace_missing_match_with_a_lobby(phase: str | None) -> None:
    source = client(party(phase=phase))
    assert CurrentGameService()._valorant_lobby_view(source, OWNER) is None
    source.player_names.assert_not_called()
    source.live_player_profiles.assert_not_called()


@pytest.mark.parametrize("bad_name", ["", "  ", "x" * 257, "bad\nname", None, 123])
def test_lobby_names_reject_malformed_values_without_losing_members(bad_name: object) -> None:
    source = client(party())
    source.player_names.return_value = {OWNER: bad_name, FRIEND: bad_name}
    view = CurrentGameService()._valorant_lobby_view(source, OWNER)
    assert view is not None
    own, friend, _ = view["teams"][0]["players"]
    assert own["name"] == "You" and own["riotId"] is None
    assert friend["name"] == "Player 2" and friend["riotId"] is None


def test_lobby_enrichment_failure_retains_verified_members_ready_state_and_capacity() -> None:
    source = client(party(maximum=10, map_id="/Game/Maps/Ascent/Ascent", mode_id="/Game/GameModes/Bomb/BombGameMode", queue_id="custom"))
    source.player_names.side_effect = RuntimeError("unavailable")
    source.live_player_profiles.side_effect = RuntimeError("unavailable")
    view = CurrentGameService()._valorant_lobby_view(source, OWNER)
    assert view is not None and view["partyMax"] == 10 and view["map"] == "Ascent"
    assert len(view["teams"][0]["players"]) == 3
    assert view["teams"][0]["players"][0]["ready"] is True
    assert "id" not in view


def test_party_leaving_and_disconnect_do_not_leave_a_stale_roster() -> None:
    source = client(party())
    service = CurrentGameService()
    assert service._valorant_lobby_view(source, OWNER) is not None
    source.own_party.return_value = None
    assert service._valorant_lobby_view(source, OWNER) is None
    source.own_party.side_effect = RuntimeError("disconnected")
    assert service._valorant_lobby_view(source, OWNER) is None


def test_solo_party_has_no_group_marker() -> None:
    solo = party(size=1, members=(ValorantPartyMember(OWNER, is_owner=True),))
    view = CurrentGameService()._valorant_lobby_view(client(solo), OWNER)
    assert view is not None and view["partySize"] == 1
    assert view["teams"][0]["players"][0]["partyId"] is None

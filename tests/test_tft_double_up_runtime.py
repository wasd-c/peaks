from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest

import peaks.application.runtime as runtime
from peaks.adapters.riot.league import GamePlayer, LeagueRankedQueue, LiveGame
from peaks.application.runtime import CurrentGameService, RiotSearchService
from peaks.bridge import _match, _match_teams

OWNER = "private-owner-puuid"
PARTNER = "private-partner-puuid"
DOUBLE_UP_QUEUE = "RANKED_TFT_DOUBLE_UP"


def member(subject: str, name: str, team: str | None = None) -> GamePlayer:
    return GamePlayer(
        name=name,
        puuid=subject,
        team=team,
        is_self=subject == OWNER,
        account_level=100,
    )


def duo_session(
    players: tuple[GamePlayer, ...],
    *,
    phase: str = "live",
    owner: str | None = OWNER,
    queue: int = 1160,
    match: str | None = "match-one",
) -> LiveGame:
    return LiveGame(
        game="tft",
        game_mode="Double Up",
        map_name="Map22",
        game_time=90 if phase == "live" else None,
        phase=phase,
        queue_id=queue,
        game_id=match,
        own_puuid=owner,
        players=players,
        team_mode="duos",
    )


def own_pair(team: str | None = None) -> tuple[GamePlayer, ...]:
    return (
        member(OWNER, "Owner#EUW", team),
        member(PARTNER, "Partner#EUW", team),
    )


def projected_groups(view: dict[str, Any]) -> dict[str, list[str]]:
    return {
        team["name"]: [player["name"] for player in team["players"]]
        for team in view["teams"]
    }


def test_four_explicit_duos_reach_the_renderer_without_private_identifiers() -> None:
    players = own_pair("duo:0") + tuple(
        member(f"private-puuid-{index}", f"Player{index}#EUW", f"duo:{index // 2}")
        for index in range(2, 8)
    )
    view = CurrentGameService()._league_session_view(duo_session(players), object())

    assert view["teamMode"] == "duos"
    assert view["freeForAll"] is False
    assert view["queue"] == "1160"
    assert projected_groups(view) == {
        "Duo 1": ["Owner#EUW", "Partner#EUW"],
        "Duo 2": ["Player2#EUW", "Player3#EUW"],
        "Duo 3": ["Player4#EUW", "Player5#EUW"],
        "Duo 4": ["Player6#EUW", "Player7#EUW"],
    }
    assert all(team["grouping"] == "duo" for team in view["teams"])
    assert sum(player["self"] for team in view["teams"] for player in team["players"]) == 1
    payload = json.dumps(view)
    assert "puuid" not in payload
    assert OWNER not in payload
    assert PARTNER not in payload


def test_unknown_partners_stay_neutral_instead_of_becoming_fake_duos() -> None:
    players = own_pair() + tuple(
        member(f"opponent-{index}", f"Opponent{index}#EUW") for index in range(6)
    )
    session = replace(duo_session(players), party_size=2, party_max=2)
    view = CurrentGameService()._league_session_view(session, object())

    assert view["teamMode"] == "duos"
    assert view["freeForAll"] is False
    assert len(view["teams"]) == 1
    assert view["teams"][0]["grouping"] == "unassigned"
    assert len(view["teams"][0]["players"]) == 8
    assert [player["name"] for player in view["teams"][0]["players"]] == [
        player.name for player in players
    ]


def test_partial_duo_information_does_not_invent_pairs_for_other_players() -> None:
    players = (
        *own_pair("duo:2"),
        member("third", "Third#EUW"), member("fourth", "Fourth#EUW"),
    )
    view = CurrentGameService()._league_session_view(duo_session(players), object())

    assert projected_groups(view) == {
        "Duo 3": ["Owner#EUW", "Partner#EUW"],
        "Unassigned players": ["Third#EUW", "Fourth#EUW"],
    }
    assert [team["grouping"] for team in view["teams"]] == ["duo", "unassigned"]


def test_standard_tft_stays_free_for_all_even_with_two_party_members() -> None:
    session = replace(
        duo_session(own_pair("duo:0")),
        team_mode=None, game_mode="Ranked", queue_id=1100, party_size=2,
    )
    view = CurrentGameService()._league_session_view(session, object())

    assert view["freeForAll"] is True
    assert "teamMode" not in view
    assert projected_groups(view) == {"Players": ["Owner#EUW", "Partner#EUW"]}
    assert "grouping" not in view["teams"][0]


def test_double_up_rank_has_its_own_cache_and_never_uses_standard_gold() -> None:
    calls: list[tuple[str, bool, frozenset[str] | None]] = []
    gold = LeagueRankedQueue("RANKED_TFT", "GOLD", "II", 10, 5, 4)
    silver = LeagueRankedQueue(DOUBLE_UP_QUEUE, "SILVER", "IV", 20, 3, 2)

    def ranked_stats(
        puuid: str, *, owned: bool, queue_types: frozenset[str] | None = None,
    ) -> tuple[LeagueRankedQueue, ...]:
        calls.append((puuid, owned, queue_types))
        return (silver,) if queue_types else (gold,)

    client = SimpleNamespace(ranked_stats=ranked_stats)
    service = CurrentGameService()
    duos = duo_session(own_pair("duo:0")[:1])
    standard = replace(duos, team_mode=None, queue_id=1100, game_mode="Ranked")

    def rank(session: LiveGame) -> str | None:
        return service._league_session_view(session, client)["teams"][0]["players"][0]["rank"]

    assert rank(standard) == "Gold II"
    assert rank(duos) == "Silver IV"
    assert rank(standard) == "Gold II"
    assert rank(duos) == "Silver IV"
    assert calls == [
        (OWNER, True, None), (OWNER, True, frozenset({DOUBLE_UP_QUEUE})),
    ]


@pytest.mark.parametrize("returned", [None, (), (LeagueRankedQueue("RANKED_TFT", "GOLD", "II", 0, 0, 0),)])
def test_unavailable_double_up_rank_does_not_fall_back_to_solo_tft(returned: Any) -> None:
    client = SimpleNamespace(ranked_stats=lambda *_args, **_kwargs: returned)
    view = CurrentGameService()._league_session_view(duo_session(own_pair("duo:0")), client)

    assert all(player["rank"] is None for team in view["teams"] for player in team["players"])


def test_visible_ranks_use_correct_owner_and_skip_hidden_players() -> None:
    calls: list[tuple[str, bool, frozenset[str]]] = []

    def ranked_stats(puuid: str, *, owned: bool, queue_types: frozenset[str]) -> None:
        calls.append((puuid, owned, queue_types))

    players = (*own_pair("duo:0"), replace(member("hidden", "Anonymous"), hidden=True))
    CurrentGameService()._league_session_view(
        duo_session(players), SimpleNamespace(ranked_stats=ranked_stats),
    )
    assert calls == [
        (OWNER, True, frozenset({DOUBLE_UP_QUEUE})),
        (PARTNER, False, frozenset({DOUBLE_UP_QUEUE})),
    ]


def test_explicit_lobby_partners_follow_identities_into_live_roster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [100.0]
    monkeypatch.setattr(runtime.time, "monotonic", lambda: clock[0])
    service = CurrentGameService()
    service._league_session_view(duo_session(own_pair("duo:0"), phase="lobby", match=None), object())
    clock[0] = 220.0
    # Pairing follows identity even when the client returns a different order.
    live = duo_session((member("outsider", "Outsider#EUW"), *reversed(own_pair())))
    view = service._league_session_view(live, object())

    assert projected_groups(view) == {
        "Unassigned players": ["Outsider#EUW"],
        "Duo 1": ["Partner#EUW", "Owner#EUW"],
    }
    # Once bound, the same match can last longer than the lobby handoff window.
    clock[0] = 1_000.0
    assert projected_groups(service._league_session_view(live, object())) == projected_groups(view)


@pytest.mark.parametrize("change", ["owner", "queue", "missing-match", "stale", "missing-owner", "missing-partner", "hidden-partner"])
def test_lobby_assignments_are_not_reused_outside_the_verified_handoff(change: str) -> None:
    service = CurrentGameService()
    service._tft_duo_roster(duo_session(own_pair("duo:0"), phase="lobby", match=None), 100)
    live = duo_session(own_pair())
    now = 110.0
    if change == "owner":
        live = replace(live, own_puuid="different-owner")
    elif change == "queue":
        live = replace(live, queue_id=1150)
    elif change == "missing-match":
        live = replace(live, game_id=None)
    elif change == "stale":
        now = 220.001
    elif change == "missing-owner":
        live = replace(live, players=live.players[1:])
    elif change == "missing-partner":
        live = replace(live, players=live.players[:1])
    else:
        live = replace(live, players=(live.players[0], replace(live.players[1], hidden=True)))

    assert all(player.team is None for player in service._tft_duo_roster(live, now))


def test_bound_assignments_do_not_cross_match_ids() -> None:
    service = CurrentGameService()
    service._tft_duo_roster(duo_session(own_pair("duo:0"), phase="lobby", match=None), 100)
    live = duo_session(own_pair())
    assert all(player.team == "duo:0" for player in service._tft_duo_roster(live, 110))
    assert all(player.team is None for player in service._tft_duo_roster(replace(live, game_id="match-two"), 120))


def test_new_explicit_groups_override_previous_lobby_pairings() -> None:
    service = CurrentGameService()
    service._tft_duo_roster(duo_session(own_pair("duo:0"), phase="lobby", match=None), 100)
    players = (
        member(OWNER, "Owner#EUW", "duo:1"), member("new", "New#EUW", "duo:1"),
        member(PARTNER, "Partner#EUW"),
    )
    result = service._tft_duo_roster(duo_session(players), 110)

    assert [player.team for player in result] == ["duo:1", "duo:1", None]


def test_changing_to_standard_tft_clears_old_duo_assignments() -> None:
    service = CurrentGameService()
    lobby = duo_session(own_pair("duo:0"), phase="lobby", match=None)
    service._league_session_view(lobby, object())
    service._league_session_view(replace(lobby, team_mode=None, queue_id=1100), object())
    live = service._league_session_view(duo_session(own_pair()), object())

    assert live["teams"][0]["grouping"] == "unassigned"


@pytest.mark.parametrize("in_metadata", [False, True])
def test_report_bridge_retains_only_safe_duo_layout_metadata(in_metadata: bool) -> None:
    teams = [
        {"name": "Duo 1", "grouping": "duo", "privateParty": "secret-party", "players": [
            {"name": "Owner#EUW", "self": True, "puuid": OWNER, "team": "private-group"},
            {"name": "Partner#EUW", "puuid": PARTNER},
        ]},
        {"name": "Unassigned players", "grouping": "unassigned", "players": [{"name": "Other#EUW"}]},
    ]
    layout = {"teamMode": "duos", "teams": teams, "freeForAll": False}
    report = _match({"game": "tft", **({"metadata": layout} if in_metadata else layout)})

    assert report["teamMode"] == "duos"
    assert report["freeForAll"] is False
    assert [team["grouping"] for team in report["teams"]] == ["duo", "unassigned"]
    serialized = json.dumps(report)
    assert "puuid" not in serialized
    assert "private-group" not in serialized
    assert "secret-party" not in serialized


def test_bridge_does_not_forward_arbitrary_grouping_metadata() -> None:
    teams = _match_teams([{"grouping": "private-puuid", "name": "Other", "players": []}])
    assert "grouping" not in teams[0]
    assert "teamMode" not in _match({"teamMode": "private-puuid"})


def report_participant(index: int, **fields: Any) -> dict[str, Any]:
    return {
        "puuid": OWNER if index == 0 else f"private-report-puuid-{index}",
        "riotIdGameName": f"Tactician{index}",
        "riotIdTagline": "EUW",
        "placement": index // 2 + 1,
        "level": 8,
        "totalDamageToPlayers": 75,
        **fields,
    }


@pytest.mark.parametrize("partner_key", ["partner_group_id", "partnerGroupId"])
def test_public_double_up_report_uses_explicit_pairs_not_roster_order(partner_key: str) -> None:
    # Non-adjacent partners and opaque upstream IDs must become four safe groups.
    group_ids = [233, 17, 81, 4, 81, 233, 4, 17]
    participants = [
        report_participant(index, **{partner_key: group})
        for index, group in enumerate(group_ids)
    ]
    teams = RiotSearchService._public_match_teams("TFT", participants, puuid=OWNER, duos=True)

    assert projected_groups({"teams": teams}) == {
        "Duo 1": ["Tactician0#EUW", "Tactician5#EUW"],
        "Duo 2": ["Tactician1#EUW", "Tactician7#EUW"],
        "Duo 3": ["Tactician2#EUW", "Tactician4#EUW"],
        "Duo 4": ["Tactician3#EUW", "Tactician6#EUW"],
    }
    assert all(team["grouping"] == "duo" for team in teams)
    assert sum(player["self"] for team in teams for player in team["players"]) == 1
    assert teams[0]["players"][0]["stats"] == {"placement": 1, "level": 8, "damage": 75}
    serialized = json.dumps(teams)
    for private in (OWNER, "private-report-puuid", partner_key, "233", "81"):
        assert private not in serialized


@pytest.mark.parametrize("pair", [None, True, False, -1, 256, "private-pair-id", {}, []])
def test_invalid_report_partner_ids_remain_neutral(pair: Any) -> None:
    participants = [report_participant(index, partner_group_id=pair) for index in range(2)]
    teams = RiotSearchService._public_match_teams("TFT", participants, puuid=OWNER, duos=True)

    assert len(teams) == 1
    assert teams[0]["name"] == "Unassigned players"
    assert teams[0]["grouping"] == "unassigned"
    assert len(teams[0]["players"]) == 2


def test_report_does_not_pair_players_from_placement_team_id_or_party_id() -> None:
    participants = [
        report_participant(index, placement=index // 2 + 1, teamId=index // 2, partyId="same-party")
        for index in range(8)
    ]
    teams = RiotSearchService._public_match_teams("TFT", participants, puuid=OWNER, duos=True)

    assert len(teams) == 1
    assert teams[0]["grouping"] == "unassigned"
    assert len(teams[0]["players"]) == 8


def test_oversized_or_single_member_report_groups_are_not_duos() -> None:
    participants = [
        report_participant(index, partner_group_id=group)
        for index, group in enumerate([8, 8, 8, 91, 71, 71])
    ]
    teams = RiotSearchService._public_match_teams("TFT", participants, puuid=OWNER, duos=True)

    assert projected_groups({"teams": teams}) == {
        "Unassigned players": [f"Tactician{index}#EUW" for index in range(4)],
        "Duo 1": ["Tactician4#EUW", "Tactician5#EUW"],
    }
    assert [team["grouping"] for team in teams] == ["unassigned", "duo"]


def test_report_with_more_than_four_pairs_does_not_claim_valid_duo_layout() -> None:
    participants = [report_participant(index, partner_group_id=index // 2 + 1) for index in range(10)]
    teams = RiotSearchService._public_match_teams("TFT", participants, puuid=OWNER, duos=True)

    assert len(teams) == 1
    assert teams[0]["grouping"] == "unassigned"
    assert len(teams[0]["players"]) == 10


@pytest.mark.parametrize("mode", [{"queue_id": 1160}, {"queueId": 1150}, {"tft_game_type": "TFT_PAIRS"}, {"tft_game_type": "pairs"}])
def test_match_view_and_bridge_keep_four_double_up_report_groups(mode: dict[str, Any]) -> None:
    participants = [report_participant(index, partner_group_id=index // 2 + 21) for index in range(8)]
    row = RiotSearchService._match_view(
        "TFT", "EUW1_123", puuid=OWNER,
        info={**mode, "participants": participants, "gameVariation": "TFT"},
    )
    report = _match(row)

    assert row["metadata"]["teamMode"] == "duos"
    assert report["mode"] == "Double Up"
    assert report["teamMode"] == "duos"
    assert report["freeForAll"] is False
    assert [team["name"] for team in report["teams"]] == [f"Duo {index}" for index in range(1, 5)]
    assert all(team["grouping"] == "duo" and len(team["players"]) == 2 for team in report["teams"])
    assert sum(player["self"] for team in report["teams"] for player in team["players"]) == 1
    serialized = json.dumps(report)
    assert "puuid" not in serialized
    assert "partner_group_id" not in serialized


def test_unknown_double_up_report_pairs_keep_mode_without_inventing_teams() -> None:
    row = RiotSearchService._match_view(
        "TFT", "EUW1_123", puuid=OWNER,
        info={"queue_id": 1160, "participants": [report_participant(index) for index in range(8)]},
    )
    report = _match(row)

    assert report["teamMode"] == "duos"
    assert report["freeForAll"] is False
    assert len(report["teams"]) == 1
    assert report["teams"][0]["grouping"] == "unassigned"


def test_standard_tft_report_ignores_partner_ids_and_keeps_existing_layout() -> None:
    participants = [report_participant(index, partner_group_id=index // 2 + 1) for index in range(8)]
    row = RiotSearchService._match_view(
        "TFT", "EUW1_123", puuid=OWNER,
        info={"queue_id": 1100, "tft_game_type": "standard", "participants": participants},
    )
    report = _match(row)

    assert "teamMode" not in row["metadata"]
    assert "teamMode" not in report
    assert report["mode"] == "standard"
    assert len(report["teams"]) == 1
    assert report["teams"][0]["name"] == "Lobby"
    assert "grouping" not in report["teams"][0]
    assert len(report["teams"][0]["players"]) == 8

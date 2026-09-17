"""Double Up uses explicit client duo assignments and its own rank ladder."""
from __future__ import annotations

from typing import Any, cast

import pytest

from peaks.adapters.riot.client import RiotClientError, RiotClientHTTP
from peaks.adapters.riot.league import (
    CURRENT_SUMMONER_PATH,
    GAMEFLOW_PHASE_PATH,
    GAMEFLOW_SESSION_PATH,
    LeagueClient,
    is_tft_double_up,
    parse_lcu_session,
    parse_live_game,
    parse_ranked_stats,
)


def roster() -> list[dict[str, Any]]:
    return [
        {"puuid": f"player-{index}", "riotId": f"Player{index}#TEST", "subteamIndex": index // 2, "intraSubteamPosition": index % 2}
        for index in range(8)
    ]


def session(players: list[dict[str, Any]], queue: int = 1160) -> dict[str, Any]:
    return {
        "gameData": {
            "gameId": 12345,
            "queue": {"id": queue, "gameMode": "TFT", "name": "Teamfight Tactics (Double Up)", "type": "RANKED_TFT_DOUBLE_UP", "allowablePremadeSizes": list(range(1, 9))},
            "teamOne": players,
            "teamTwo": [],
        },
    }


@pytest.mark.parametrize("queue", [1150, 1160])
def test_four_pairs_come_from_explicit_group_fields_not_roster_order(queue: int) -> None:
    players = roster()
    shuffled = [players[index] for index in (4, 1, 6, 3, 0, 7, 5, 2)]
    game = parse_lcu_session("InProgress", session=session(shuffled, queue), own={"puuid": "player-0"})
    assert game and game.team_mode == "duos" and game.game_mode == "Double Up"
    assert {player.puuid: player.team for player in game.players} == {
        f"player-{index}": f"duo:{index // 2}" for index in range(8)
    }
    assert sum(player.is_self for player in game.players) == 1
    assert game.raw == {}


def test_eight_person_party_is_not_collapsed_to_one_team_or_two_person_capacity() -> None:
    game = parse_lcu_session("Lobby", lobby={
        "gameConfig": {"queueId": 1160, "gameMode": "TFT", "allowablePremadeSizes": list(range(1, 9))},
        "members": roster(),
    })
    assert game and game.team_mode == "duos"
    assert game.party_size == game.party_max == 8
    assert len({player.team for player in game.players}) == 4


@pytest.mark.parametrize("bad_assignment", [
    {}, {"subteamIndex": 0}, {"subteamIndex": -1, "intraSubteamPosition": 0},
    {"subteamIndex": 4, "intraSubteamPosition": 0},
    {"subteamIndex": True, "intraSubteamPosition": 0},
    {"subteamIndex": 0, "intraSubteamPosition": True},
    {"subteamIndex": 0, "intraSubteamPosition": 2},
    {"teamParticipantId": 1, "teamId": 100, "partnerId": "somebody"},
])
def test_unknown_or_invalid_pairing_preserves_the_player_without_guessing(bad_assignment: dict[str, object]) -> None:
    game = parse_lcu_session("InProgress", session=session([{"puuid": "player", "riotId": "Player#TEST", **bad_assignment}]))
    assert game and game.team_mode == "duos" and len(game.players) == 1
    assert game.players[0].team is None


def test_one_explicit_pair_and_six_unknown_players_stay_partial() -> None:
    players = roster()
    for player in players[2:]:
        player.pop("subteamIndex")
        player.pop("intraSubteamPosition")
    game = parse_lcu_session("InProgress", session=session(players))
    assert game and [player.team for player in game.players] == ["duo:0", "duo:0", *([None] * 6)]


def test_duplicate_identity_across_duos_invalidates_both_claimed_teams() -> None:
    players = roster()
    players[2]["puuid"] = players[0]["puuid"]
    game = parse_lcu_session("InProgress", session=session(players))
    assert game and [player.team for player in game.players[:4]] == [None] * 4
    assert [player.team for player in game.players[4:]] == ["duo:2", "duo:2", "duo:3", "duo:3"]


@pytest.mark.parametrize("broken", ["duplicate-slot", "three-members", "duplicate-identity"])
def test_ambiguous_group_is_discarded_without_affecting_other_pairs(broken: str) -> None:
    players = roster()
    if broken == "duplicate-slot":
        players[1]["intraSubteamPosition"] = 0
    elif broken == "three-members":
        players.append({"puuid": "extra", "subteamIndex": 0, "intraSubteamPosition": 0})
    else:
        players[1]["puuid"] = players[0]["puuid"]
    game = parse_lcu_session("InProgress", session=session(players))
    assert game and all(player.team is None for player in game.players[:2])
    assert [player.team for player in game.players[2:8]] == ["duo:1", "duo:1", "duo:2", "duo:2", "duo:3", "duo:3"]


def test_hidden_partner_stays_anonymous_while_preserving_explicit_team() -> None:
    players = roster()
    players[1]["hidden"] = True
    game = parse_lcu_session("InProgress", session=session(players))
    assert game
    hidden = game.players[1]
    assert hidden.hidden and hidden.name is hidden.puuid is hidden.summoner_id is None
    assert hidden.team == game.players[0].team == "duo:0"


def test_standard_tft_ignores_subteams_and_is_free_for_all() -> None:
    game = parse_lcu_session("InProgress", session=session(roster(), queue=1090))
    assert game and game.team_mode == "free-for-all"
    assert {player.team for player in game.players} == {"Players"}


def test_double_up_rank_is_opt_in_and_never_standard_tft_fallback() -> None:
    rows = [{"queueType": queue, "tier": tier, "division": "I", "leaguePoints": 42, "wins": 5, "losses": 3} for queue, tier in (
        ("RANKED_TFT", "GOLD"), ("RANKED_TFT_DOUBLE_UP", "DIAMOND"), ("RANKED_TFT_PAIRS", "SILVER"),
    )]
    default = parse_ranked_stats({"queues": rows})
    double_up = parse_ranked_stats({"queues": rows}, queue_types=frozenset({"RANKED_TFT_DOUBLE_UP"}))
    assert default and [rank.tier for rank in default] == ["GOLD"]
    assert double_up and [(rank.queue_type, rank.tier) for rank in double_up] == [("RANKED_TFT_DOUBLE_UP", "DIAMOND")]
    assert parse_ranked_stats({"queues": rows[:1]}, queue_types=frozenset({"RANKED_TFT_DOUBLE_UP"})) == ()
    assert parse_ranked_stats({"queues": rows}, queue_types=frozenset({"MADE_UP_QUEUE"})) is None


@pytest.mark.parametrize(("queue", "mode", "expected"), [
    (1150, None, True), (1160, None, True), (None, "RANKED_TFT_DOUBLE_UP", True),
    (None, "TFT_PAIRS", True), (None, "Double Up", True),
    (None, "TFT", False), (1090, "Double Up", False), (None, "unrelated doubles", False),
])
def test_double_up_classification(queue: object, mode: object, expected: bool) -> None:
    assert is_tft_double_up(queue, mode) is expected


class FakeHTTP:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads

    def get_json(self, endpoint: str, **_kwargs: object) -> Any:
        if endpoint not in self.payloads:
            raise RiotClientError("Missing synthetic endpoint", status_code=404)
        return self.payloads[endpoint]


def test_live_data_merge_preserves_explicit_duos_without_flattening() -> None:
    players = roster()
    live_rows = [{"puuid": player["puuid"], "riotId": player["riotId"], "team": "ORDER"} for player in reversed(players)]
    lcu = FakeHTTP({GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: session(players), CURRENT_SUMMONER_PATH: {"puuid": "player-0"}})
    live_http = FakeHTTP({"/liveclientdata/allgamedata": {"gameData": {"gameMode": "TFT"}, "allPlayers": live_rows}})
    client = LeagueClient(lcu_http=cast(RiotClientHTTP, lcu), live_http=cast(RiotClientHTTP, live_http), process_names={"LeagueClient.exe"})
    game = client.current_session()
    assert game and game.team_mode == "duos" and game.queue_id == 1160
    assert {player.puuid: player.team for player in game.players} == {f"player-{index}": f"duo:{index // 2}" for index in range(8)}


def test_direct_live_data_accepts_only_explicit_double_up_assignments() -> None:
    game = parse_live_game({"gameData": {"gameMode": "TFT", "queueId": 1160}, "allPlayers": roster()})
    assert game and game.team_mode == "duos"
    assert [player.team for player in game.players] == [f"duo:{index // 2}" for index in range(8)]


def test_live_name_collision_does_not_override_conflicting_puuid() -> None:
    players = roster()
    lcu = FakeHTTP({GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: session(players), CURRENT_SUMMONER_PATH: {"puuid": "player-0"}})
    live_http = FakeHTTP({"/liveclientdata/allgamedata": {"gameData": {"gameMode": "TFT"}, "allPlayers": [{"puuid": "different-player", "riotId": players[0]["riotId"]}]}})
    client = LeagueClient(lcu_http=cast(RiotClientHTTP, lcu), live_http=cast(RiotClientHTTP, live_http), process_names={"LeagueClient.exe"})
    game = client.current_session()
    assert game and game.players[0].puuid == "different-player" and game.players[0].team is None

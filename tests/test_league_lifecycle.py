from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from peaks.adapters.riot.client import RiotClientError, RiotClientHTTP
from peaks.adapters.riot.league import (
    CHAMP_SELECT_PATH,
    CURRENT_SUMMONER_PATH,
    GAMEFLOW_PHASE_PATH,
    GAMEFLOW_SESSION_PATH,
    LOBBY_PATH,
    MATCHMAKING_PATH,
    GamePlayer,
    LeagueClient,
    LeagueRankedQueue,
    LeagueSummonerProfile,
    LiveGame,
    parse_lcu_session,
    parse_live_game,
)
from peaks.application.runtime import CurrentGameService

OWN = {"puuid": "owner-puuid", "summonerId": 14, "gameName": "Owner", "tagLine": "EUW", "summonerLevel": 400}


class FakeHTTP:
    def __init__(self, payloads: dict[str, object] | None = None) -> None:
        self.payloads = payloads or {}
        self.calls: list[str] = []
        self.closed = False

    def get_json(self, endpoint: str, **_kwargs: object) -> Any:
        self.calls.append(endpoint)
        if endpoint not in self.payloads:
            raise RiotClientError("Endpoint unavailable", status_code=404)
        return self.payloads[endpoint]

    def close(self) -> None:
        self.closed = True


def client_with(payloads: dict[str, object], live: dict[str, object] | None = None) -> tuple[LeagueClient, FakeHTTP, FakeHTTP]:
    lcu, live_http = FakeHTTP(payloads), FakeHTTP(live)
    return LeagueClient(lcu_http=cast(RiotClientHTTP, lcu), live_http=cast(RiotClientHTTP, live_http), process_names={"LeagueClient.exe"}), lcu, live_http


def lobby(queue: int = 420, mode: str = "CLASSIC") -> dict[str, object]:
    return {
        "gameConfig": {"queueId": queue, "gameMode": mode, "mapId": 11, "maxLobbySize": 5, "allowablePremadeSizes": [1, 2]},
        "localMember": {**OWN, "summonerName": "Owner", "isLeader": True},
        "members": [
            {**OWN, "summonerName": "Owner", "isLeader": True, "ready": True, "firstPositionPreference": "MIDDLE"},
            {"puuid": "friend-puuid", "summonerId": 15, "summonerName": "Friend", "summonerLevel": 123, "isLeader": False, "ready": False},
        ],
        "multiUserChatPassword": "never-retain-this",
    }


def gameflow(queue: int = 420, mode: str = "CLASSIC", count: int = 2) -> dict[str, object]:
    return {
        "phase": "InProgress",
        "map": {"id": 22 if mode == "TFT" else 11, "name": "Teamfight Tactics" if mode == "TFT" else "Summoner's Rift", "gameMode": mode},
        "gameData": {
            "gameId": 123456789,
            "queue": {"id": queue, "gameMode": mode, "name": "Teamfight Tactics (Normal)" if mode == "TFT" else "Ranked Solo/Duo", "type": "NORMAL_TFT" if mode == "TFT" else "RANKED_SOLO_5x5", "maximumParticipantListSize": 8 if mode == "TFT" else 2},
            "teamOne": [{"puuid": "owner-puuid", "summonerId": 14, "summonerName": "Owner"}] + [{"puuid": f"other-{index}", "summonerId": index + 20, "summonerName": f"Other {index}"} for index in range(count - 1)],
            "teamTwo": [],
            "spectatorKey": "must-not-leave-the-client",
        },
    }


def test_party_members_ready_leader_levels_and_capacity_are_preserved() -> None:
    state = parse_lcu_session("Lobby", lobby=lobby(), own=OWN)
    assert state is not None
    assert (state.game, state.phase, state.party_size, state.party_max) == ("league", "lobby", 2, 2)
    assert state.players[0].name == "Owner#EUW"
    assert state.players[0].is_self and state.players[0].is_leader and state.players[0].ready
    assert state.players[0].role == "MIDDLE"
    assert state.players[1].account_level == 123
    assert not state.players[1].is_self
    assert state.raw == {}
    assert "never-retain" not in repr(state)


def test_lobby_roster_updates_on_join_leave_without_cached_players() -> None:
    payload = lobby()
    initial = parse_lcu_session("Lobby", lobby=payload)
    assert initial and len(initial.players) == 2
    payload["members"] = cast(list[object], payload["members"])[:1]
    updated = parse_lcu_session("Lobby", lobby=payload)
    assert updated and len(updated.players) == updated.party_size == 1


@pytest.mark.parametrize(("phase", "expected"), [("Lobby", "lobby"), ("Matchmaking", "matchmaking"), ("ReadyCheck", "readycheck"), ("CheckedIntoTournament", "lobby")])
def test_lobby_phase_mapping(phase: str, expected: str) -> None:
    state = parse_lcu_session(phase, lobby=lobby(), own=OWN, search={"timeInQueue": 32.5})
    assert state and state.phase == expected
    assert state.game_time == (32.5 if expected == "matchmaking" else None)


@pytest.mark.parametrize(("search", "expected"), [("Searching", "matchmaking"), ("Found", "readycheck"), ("Canceled", "lobby")])
def test_search_state_refines_lobby_phase(search: str, expected: str) -> None:
    state = parse_lcu_session("Lobby", lobby=lobby(), search={"searchState": search})
    assert state and state.phase == expected


@pytest.mark.parametrize("queue", [1090, 1100, 1110, 1111, 1130, 1150, 1160])
def test_tft_queue_ids_identify_lobbies_when_mode_is_missing(queue: int) -> None:
    payload = lobby(queue, "")
    state = parse_lcu_session("Lobby", lobby=payload)
    assert state and state.game == "tft" and state.map_name == "Teamfight Tactics"


def test_future_tft_queue_detected_from_local_metadata() -> None:
    state = parse_lcu_session("Lobby", lobby=lobby(9999, "TFT_NEW_EVENT"), queue_details={"name": "Teamfight Tactics Event"})
    assert state and state.game == "tft"


def test_current_lobby_overrides_previous_tft_game_metadata() -> None:
    state = parse_lcu_session("Lobby", lobby=lobby(420), session=gameflow(1090, "TFT", 8))
    assert state and state.game == "league" and state.queue_id == 420
    assert state.map_name == "Summoner's Rift"


def test_tft_live_fallback_is_actual_eight_player_roster_without_fake_stats() -> None:
    state = parse_lcu_session("InProgress", session=gameflow(1090, "TFT", 8), own=OWN)
    assert state and state.game == "tft" and state.phase == "live"
    assert len(state.players) == 8
    assert {player.team for player in state.players} == {"Players"}
    assert sum(player.is_self for player in state.players) == 1
    assert all(not player.stats and player.champion is None for player in state.players)
    assert state.game_id == "123456789"
    assert state.raw == {}
    assert "must-not-leave" not in repr(state)


def test_selection_respects_hidden_identity_even_when_puuid_was_present() -> None:
    state = parse_lcu_session("ChampSelect", own=OWN, session=gameflow(), selection={
        "localPlayerCellId": 0,
        "myTeam": [
            {"cellId": 0, "nameVisibilityType": "HIDDEN", "championId": 103},
            {"cellId": 1, "gameName": "DoNotExpose", "tagLine": "TAG", "puuid": "private-puuid", "summonerId": 50, "nameVisibilityType": "HIDDEN", "championPickIntent": 99, "assignedPosition": "UTILITY"},
            {"cellId": 2, "gameName": "Visible", "tagLine": "EUW", "puuid": "visible-puuid", "nameVisibilityType": "VISIBLE", "championId": 555},
        ],
        "theirTeam": [{"cellId": 5, "championId": 222, "summonerId": 0, "obfuscatedPuuid": "not-a-real-subject"}],
    })
    assert state and state.phase == "pregame"
    owner, hidden, visible, enemy = state.players
    assert owner.is_self and not owner.hidden and owner.name == "Owner#EUW"
    assert hidden.hidden and hidden.name is hidden.puuid is hidden.summoner_id is None
    assert hidden.champion_id == 99 and hidden.role == "UTILITY"
    assert visible.name == "Visible#EUW" and visible.puuid == "visible-puuid"
    assert enemy.hidden and enemy.puuid is None
    assert enemy.team != owner.team


def test_custom_lobby_uses_real_teams_and_excludes_spectators() -> None:
    payload = lobby()
    config = cast(dict[str, object], payload["gameConfig"])
    config.update({"isCustom": True, "customTeam100": [{**OWN, "summonerName": "Owner"}], "customTeam200": [{"summonerName": "Opponent"}, {"summonerName": "Spectator", "isSpectator": True}]})
    state = parse_lcu_session("Lobby", lobby=payload)
    assert state and len(state.players) == 2
    assert [player.team for player in state.players] == ["100", "200"]


@pytest.mark.parametrize("phase", ["None", "EndOfGame", "WaitingForStats", "PreEndOfGame", "TerminatedInError", "FailedToLaunch"])
def test_inactive_phases_clear_even_with_stale_roster(phase: str) -> None:
    assert parse_lcu_session(phase, session=gameflow(), lobby=lobby()) is None


def test_live_stats_are_actual_numbers_and_account_level_is_distinct() -> None:
    game = parse_live_game({
        "gameData": {"gameMode": "CLASSIC", "gameTime": 50},
        "activePlayer": {"riotId": "Owner#EUW"},
        "allPlayers": [{"riotId": "Owner#EUW", "championName": "Ahri", "team": "ORDER", "level": 5, "scores": {"kills": 2, "deaths": 1, "assists": 3, "creepScore": 34, "wardScore": 3.5}}],
    })
    assert game and game.players[0].is_self
    assert game.players[0].stats == {"kills": 2, "deaths": 1, "assists": 3, "minions": 34, "vision": 3.5, "level": 5}
    assert game.players[0].account_level is None


def test_client_tft_works_when_liveclientdata_is_unavailable() -> None:
    client, lcu, live = client_with({GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: gameflow(1090, "TFT", 8), CURRENT_SUMMONER_PATH: OWN})
    state = client.current_session()
    assert state and state.game == "tft" and len(state.players) == 8
    assert client.activity_available
    assert CHAMP_SELECT_PATH not in lcu.calls
    assert not any("champion-summary" in call for call in lcu.calls)
    client.close()
    assert lcu.closed and live.closed


def test_client_authoritative_exit_does_not_read_stale_live_data() -> None:
    client, _, live = client_with({GAMEFLOW_PHASE_PATH: "None"}, {"/liveclientdata/allgamedata": {"gameData": {"gameMode": "CLASSIC"}}})
    assert client.current_session() is None
    assert client.activity_available
    assert live.calls == []


def test_client_falls_back_to_session_phase_and_queue_details() -> None:
    flow = gameflow()
    flow["phase"] = "Lobby"
    client, lcu, _ = client_with({GAMEFLOW_SESSION_PATH: flow, LOBBY_PATH: lobby(1160, "TFT"), CURRENT_SUMMONER_PATH: OWN, "/lol-game-queues/v1/queues/1160": {"name": "Double Up", "allowablePremadeSizes": [1, 2]}})
    state = client.current_session()
    assert state and state.game == "tft" and state.game_mode == "Double Up"
    assert state.party_max == 2
    assert "/lol-game-queues/v1/queues/1160" in lcu.calls


def test_missing_endpoints_and_rosters_are_unavailable_not_fictional() -> None:
    client, _, _ = client_with({})
    assert client.current_session() is None and not client.activity_available
    client, _, _ = client_with({GAMEFLOW_PHASE_PATH: "ChampSelect"})
    assert client.current_session() is None and not client.activity_available


@pytest.mark.parametrize("phase", ["ChampSelect", "InProgress", "Lobby", "Matchmaking"])
def test_missing_active_roster_is_a_temporary_failure_not_an_authoritative_exit(phase: str) -> None:
    client, _, _ = client_with({GAMEFLOW_PHASE_PATH: phase})
    assert client.current_session() is None
    assert not client.activity_available


def test_client_keeps_documented_live_data_when_lcu_gameflow_is_unavailable() -> None:
    client, _, _ = client_with({}, {"/liveclientdata/allgamedata": {"gameData": {"gameMode": "ARAM"}, "allPlayers": [{"summonerName": "Player", "team": "ORDER"}]}})
    state = client.current_session()
    assert state and state.game == "league" and client.activity_available


def test_champion_names_are_read_from_local_game_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("peaks.adapters.riot.league._CHAMPION_NAMES", {})
    client, lcu, _ = client_with({
        GAMEFLOW_PHASE_PATH: "ChampSelect", CURRENT_SUMMONER_PATH: OWN,
        GAMEFLOW_SESSION_PATH: gameflow(),
        CHAMP_SELECT_PATH: {"localPlayerCellId": 0, "myTeam": [{"cellId": 0, "championId": 103}], "theirTeam": []},
        "/lol-game-data/assets/v1/champion-summary.json": [{"id": 103, "name": "Ahri"}],
    })
    state = client.current_session()
    assert state and state.players[0].champion == "Ahri"
    client.current_session()
    assert lcu.calls.count("/lol-game-data/assets/v1/champion-summary.json") == 1
    assert not any("/summoners/" in path for path in lcu.calls)


def test_live_data_takes_precedence_over_gameflow_roster_and_gains_identity() -> None:
    client, _, _ = client_with({GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: gameflow(), CURRENT_SUMMONER_PATH: OWN}, {
        "/liveclientdata/allgamedata": {"gameData": {"gameMode": "CLASSIC", "gameTime": 500}, "activePlayer": {"riotId": "Owner#EUW"}, "allPlayers": [{"riotId": "Owner#EUW", "championName": "Ahri", "team": "ORDER", "level": 9, "scores": {"kills": 4, "deaths": 2, "assists": 6}}]},
    })
    state = client.current_session()
    assert state and len(state.players) == 1 and state.game_time == 500
    assert state.players[0].puuid == "owner-puuid" and state.players[0].account_level == 400
    assert state.players[0].stats["kills"] == 4
    assert state.game_mode == "Ranked Solo/Duo"


@pytest.mark.parametrize(("queue", "mode"), [(420, "CLASSIC"), (1090, "TFT"), (1160, "TFT")])
def test_live_session_reads_actual_party_without_counting_match_players(queue: int, mode: str) -> None:
    client, lcu, _ = client_with({
        GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: gameflow(queue, mode, 8),
        CURRENT_SUMMONER_PATH: OWN, LOBBY_PATH: lobby(queue, mode),
    })
    state = client.current_session()
    assert state and state.party_size == 2 and len(state.players) == 8
    assert LOBBY_PATH in lcu.calls
    assert "never-retain-this" not in repr(state)


@pytest.mark.parametrize("mismatch", ["queue", "owner"])
def test_live_session_drops_unrelated_party(mismatch: str) -> None:
    party = lobby(1090 if mismatch == "queue" else 420)
    if mismatch == "owner":
        party["members"] = [{"puuid": "different-owner"}]
    client, _, _ = client_with({
        GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: gameflow(),
        CURRENT_SUMMONER_PATH: OWN, LOBBY_PATH: party,
    })
    state = client.current_session()
    assert state and state.party_size is None


def test_game_mode_mismatch_does_not_replace_active_tft_with_old_league_data() -> None:
    client, _, _ = client_with({GAMEFLOW_PHASE_PATH: "InProgress", GAMEFLOW_SESSION_PATH: gameflow(1090, "TFT", 8)}, {"/liveclientdata/allgamedata": {"gameData": {"gameMode": "CLASSIC"}, "allPlayers": [{"summonerName": "Old match"}]}})
    state = client.current_session()
    assert state and state.game == "tft" and len(state.players) == 8


def test_matchmaking_reader_only_reads_and_returns_elapsed_time() -> None:
    client, lcu, _ = client_with({GAMEFLOW_PHASE_PATH: "Matchmaking", LOBBY_PATH: lobby(), CURRENT_SUMMONER_PATH: OWN, MATCHMAKING_PATH: {"timeInQueue": 18, "searchState": "Searching"}})
    state = client.current_session()
    assert state and state.phase == "matchmaking" and state.game_time == 18
    assert MATCHMAKING_PATH in lcu.calls


@pytest.mark.parametrize("phase", ["Lobby", "Matchmaking", "ReadyCheck"])
def test_previous_game_id_never_leaves_adapter_for_new_party(phase: str) -> None:
    state = parse_lcu_session(phase, session=gameflow(), lobby=lobby())
    assert state and state.game_id is None


def test_visible_member_profile_is_bound_to_requested_puuid() -> None:
    endpoint = "/lol-summoner/v2/summoners/puuid/visible-subject"
    client, lcu, _ = client_with({endpoint: {"puuid": "visible-subject", "gameName": "Actual", "tagLine": "EUW", "summonerLevel": 215}})
    profile = client.session_player_profile(GamePlayer(None, puuid="visible-subject"))
    assert profile and profile.riot_id == "Actual#EUW" and profile.level == 215
    assert lcu.calls == [endpoint]


@pytest.mark.parametrize("payload", [
    {"puuid": "different-subject", "gameName": "Wrong", "tagLine": "EUW"},
    {"gameName": "Wrong", "tagLine": "EUW"},
    {"puuid": "visible-subject", "gameName": "Incomplete"},
    [],
])
def test_member_profile_rejects_mismatched_or_incomplete_identity(payload: object) -> None:
    client, _, _ = client_with({"/lol-summoner/v2/summoners/puuid/visible-subject": payload})
    assert client.session_player_profile(GamePlayer(None, puuid="visible-subject")) is None


@pytest.mark.parametrize("member", [GamePlayer("Hidden", puuid="private", hidden=True), GamePlayer(None)])
def test_hidden_or_unresolved_selection_player_cannot_trigger_profile_lookup(member: GamePlayer) -> None:
    client, lcu, _ = client_with({})
    assert client.session_player_profile(member) is None
    assert lcu.calls == []


def test_profile_puuid_is_encoded_as_one_path_component() -> None:
    subject = "visible/subject?part#id"
    endpoint = "/lol-summoner/v2/summoners/puuid/visible%2Fsubject%3Fpart%23id"
    client, lcu, _ = client_with({endpoint: {"puuid": subject, "gameName": "Actual", "tagLine": "EUW"}})
    assert client.session_player_profile(GamePlayer(None, puuid=subject)) is not None
    assert lcu.calls == [endpoint]


def _roster_result_players(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [player for team in result["teams"] for player in team["players"]]


def test_blank_live_names_enrich_in_bounded_batches_without_anonymous_lookups() -> None:
    roster = (
        *(GamePlayer(None, puuid=f"subject-{index}", team="Players", is_self=index == 0) for index in range(8)),
        GamePlayer(None, puuid="hidden-puuid", hidden=True),
        GamePlayer("Anonymous", puuid="anonymous-puuid"),
    )
    game = LiveGame("tft", "Normal", "Teamfight Tactics", None, players=roster, own_puuid="subject-0")
    profile_reader = Mock(side_effect=lambda member: LeagueSummonerProfile(member.puuid, f"Player{member.puuid.rsplit('-', 1)[1]}", "EUW", 200))
    rank_reader = Mock(return_value=(LeagueRankedQueue("RANKED_TFT", "GOLD", "II", 50, 5, 2),))
    client = SimpleNamespace(session_player_profile=profile_reader, ranked_stats=rank_reader)
    service = CurrentGameService()
    first = _roster_result_players(service._league_session_view(game, client))
    assert profile_reader.call_count == rank_reader.call_count == 4
    assert sum(bool(player["riotId"]) for player in first) == 4
    second = _roster_result_players(service._league_session_view(game, client))
    assert profile_reader.call_count == rank_reader.call_count == 8
    assert sum(bool(player["riotId"]) for player in second) == 8
    assert all(player["rank"] == "Gold II" and player["accountLevel"] == 200 for player in second[:8])
    assert second[0]["self"]
    assert all(player["hidden"] for player in second[8:])
    service._league_session_view(game, client)
    assert profile_reader.call_count == rank_reader.call_count == 8
    assert {call.args[0].puuid for call in profile_reader.call_args_list} == {f"subject-{index}" for index in range(8)}
    assert "puuid" not in repr(second)


def test_profile_cache_is_scoped_to_signed_in_subject_and_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = [100.0]
    monkeypatch.setattr("peaks.application.runtime.time.monotonic", lambda: ticks[0])
    game = LiveGame("tft", "Normal", "Teamfight Tactics", None, players=(GamePlayer(None, puuid="visible", team="Players"),), own_puuid="first-owner")
    reader = Mock(return_value=LeagueSummonerProfile("visible", "FullName", "EUW", 300))
    client = SimpleNamespace(session_player_profile=reader)
    service = CurrentGameService()
    service._league_session_view(game, client)
    service._league_session_view(game, client)
    assert reader.call_count == 1
    ticks[0] += 301
    service._league_session_view(game, client)
    assert reader.call_count == 2
    service._league_session_view(replace(game, own_puuid="different-owner"), client)
    assert reader.call_count == 3
    assert set(service._league_profile_cache) == {("different-owner", "visible")}


def test_profile_failures_stay_unavailable_without_losing_real_roster_stats() -> None:
    game = LiveGame("league", "Normal", "Summoner's Rift", None, players=(GamePlayer("Visible", puuid="visible", team="ORDER", stats={"kills": 4, "deaths": 2, "assists": 3}),), own_puuid="owner")
    reader = Mock(side_effect=RiotClientError("Offline"))
    client = SimpleNamespace(session_player_profile=reader)
    service = CurrentGameService()
    first = _roster_result_players(service._league_session_view(game, client))[0]
    assert first["name"] == "Visible" and first["riotId"] is None
    assert first["stats"] == {"kills": 4, "deaths": 2, "assists": 3}
    assert first["accountLevel"] is None and first["rank"] is None
    service._league_session_view(game, client)
    assert reader.call_count == 1


def test_unbound_roster_does_not_use_current_client_for_identity_enrichment() -> None:
    game = LiveGame("tft", "Normal", "Teamfight Tactics", None, players=(GamePlayer(None, puuid="visible"),))
    reader, rank_reader = Mock(), Mock()
    CurrentGameService()._league_session_view(game, SimpleNamespace(session_player_profile=reader, ranked_stats=rank_reader))
    reader.assert_not_called()
    rank_reader.assert_not_called()

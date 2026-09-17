from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from peaks.adapters.riot.league import GamePlayer, LeagueRankedQueue, LiveGame
from peaks.application.runtime import CurrentGameService


def session(*, game="league", phase="lobby"):
    return LiveGame(
        game, "Normal", "Teamfight Tactics" if game == "tft" else "Summoner's Rift", None,
        players=(GamePlayer(name="Owner#EUW", puuid="own", is_self=True, team="Party", ready=True, is_leader=True),
                 GamePlayer(name="Friend#EUW", puuid="friend", team="Party", ready=False)),
        phase=phase, own_puuid="own", party_size=2, party_max=8 if game == "tft" else 5,
    )


def detector(monkeypatch, league_session, valorant_session=None, *, league_available=True, valorant_available=True):
    monkeypatch.setattr("peaks.application.runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr("peaks.adapters.riot.discovery.discover_riot_client", lambda: SimpleNamespace(process_running=True, available=True, reason="Connected", executable=None))
    client = SimpleNamespace(current_game=lambda: None, current_session=lambda: league_session, activity_available=league_available, close=Mock())
    monkeypatch.setattr("peaks.adapters.riot.league.LeagueClient.from_discovery", lambda: client)
    service = CurrentGameService()

    def valorant(_):
        service.detection_available = valorant_available
        service.active_account_puuid = "valorant-own"
        return valorant_session

    service._detect_valorant = Mock(side_effect=valorant)
    return service, client


def test_league_lobby_is_selected_and_self_binding_survives_valorant_probe(monkeypatch):
    service, client = detector(monkeypatch, session())
    result = service.detect()
    assert result["game"] == "League"
    assert result["phase"] == "lobby"
    assert result["partySize"] == 2
    assert service.active_account_puuid == "own"
    assert service.detection_available
    assert result["teams"][0]["players"][0]["leader"]
    assert result["teams"][0]["players"][0]["ready"]
    assert "puuid" not in repr(result)
    client.close.assert_called_once()


def test_active_valorant_takes_priority_over_idle_league_lobby(monkeypatch):
    service, _ = detector(monkeypatch, session(), {"game": "VALORANT", "phase": "live"})
    assert service.detect()["game"] == "VALORANT"
    assert service.active_account_puuid == "valorant-own"


def test_tft_live_returns_without_probing_unrelated_valorant(monkeypatch):
    service, _ = detector(monkeypatch, session(game="tft", phase="live"))
    result = service.detect()
    assert result["game"] == "TFT"
    assert result["freeForAll"]
    assert [team["name"] for team in result["teams"]] == ["Players"]
    assert result["teams"][0]["players"][0]["self"]
    service._detect_valorant.assert_not_called()


@pytest.mark.parametrize("previous,league_available,valorant_available,expected", [
    ("TFT", True, False, True), ("League", False, True, False),
    ("VALORANT", True, False, False), ("VALORANT", False, True, True),
])
def test_disconnected_other_client_cannot_end_active_game(monkeypatch, previous, league_available, valorant_available, expected):
    service, _ = detector(monkeypatch, None, league_available=league_available, valorant_available=valorant_available)
    service._last_session_game = previous
    assert service.detect() is None
    assert service.detection_available is expected


def test_lobby_tie_keeps_current_game_instead_of_flipping_every_poll(monkeypatch):
    service, _ = detector(monkeypatch, session(), {"game": "VALORANT", "phase": "lobby"})
    service._last_session_game = "VALORANT"
    assert service.detect()["game"] == "VALORANT"


def test_tft_ranks_are_read_from_tft_queue_and_cached_without_hidden_lookups():
    players = (*(GamePlayer(name=f"Player{i}#EUW", puuid=f"subject{i}", team="Players") for i in range(8)), GamePlayer(name="Hidden", puuid="private", hidden=True))
    game = LiveGame("tft", "Normal", "Teamfight Tactics", None, players=players, own_puuid="subject0")
    rank_reader = Mock(return_value=(LeagueRankedQueue("RANKED_SOLO_5x5", "DIAMOND", "I", 10, 1, 1), LeagueRankedQueue("RANKED_TFT", "GOLD", "II", 20, 2, 1)))
    service = CurrentGameService()
    client = SimpleNamespace(ranked_stats=rank_reader)
    first = service._league_session_view(game, client)
    assert rank_reader.call_count == 4
    assert first["teams"][0]["players"][0]["rank"] == "Gold II"
    service._league_session_view(game, client)
    assert rank_reader.call_count == 8
    service._league_session_view(game, client)
    assert rank_reader.call_count == 8
    assert all(call.args[0] != "private" for call in rank_reader.call_args_list)


def test_live_league_stats_and_private_selection_identity_survive_normalization():
    game = LiveGame("league", "Ranked", "Summoner's Rift", 120, players=(
        GamePlayer("Owner#EUW", champion="Ahri", team="ORDER", is_self=True, stats={"kills": 5, "deaths": 2, "assists": 4, "minions": 93, "level": 8}),
        GamePlayer("DoNotReveal#EUW", champion="Lux", team="CHAOS", hidden=True),
    ))
    result = CurrentGameService()._league_session_view(game, SimpleNamespace())
    assert result["elapsed"] == "2:00"
    assert result["teams"][0]["players"][0]["stats"]["minions"] == 93
    assert result["teams"][0]["score"] == 5
    assert result["teams"][1]["score"] is None
    assert result["teams"][1]["players"][0]["hidden"]
    assert "DoNotReveal" not in repr(result)


def test_valorant_live_takes_priority_over_league_readycheck(monkeypatch):
    service, _ = detector(monkeypatch, session(phase="readycheck"), {"game": "VALORANT", "phase": "live"})
    assert service.detect()["game"] == "VALORANT"


@pytest.mark.parametrize("previous", ["VALORANT", "League", "TFT"])
def test_unavailable_active_provider_is_not_replaced_by_other_client_lobby(monkeypatch, previous):
    service, _ = detector(monkeypatch, session() if previous == "VALORANT" else None,
                          None if previous == "VALORANT" else {"game": "VALORANT", "phase": "lobby"},
                          league_available=previous == "VALORANT", valorant_available=previous != "VALORANT")
    service._last_session_game = previous
    service._last_session_phase = "live"
    assert service.detect() is None
    assert not service.detection_available


def test_previous_game_id_is_not_reused_for_new_lobby():
    from dataclasses import replace

    lobby = replace(session(), game_id="previous-match-id")
    result = CurrentGameService()._league_session_view(lobby, SimpleNamespace())
    assert "id" not in result

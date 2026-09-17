"""Legacy live-data HP is optional and must belong to the active tactician."""
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from peaks.adapters.riot.league import GamePlayer, LiveGame, parse_live_game
from peaks.adapters.riot.tft_telemetry import TftMatchSnapshot, TftPlayerSnapshot
from peaks.application.runtime import CurrentGameService
from peaks.bridge import _match_teams


def payload(health: Any = 76) -> dict[str, Any]:
    return {
        "gameData": {"gameMode": "TFT"},
        "activePlayer": {"riotId": "Self#TEST", "championStats": {"currentHealth": health}},
        "allPlayers": [{"riotId": "Opponent#TEST"}, {"riotId": "Self#TEST"}],
    }


@pytest.mark.parametrize("health", [0, 1, 76, 76.5, 130, 1000])
def test_only_current_tactician_health_reaches_the_bridge(health: int | float) -> None:
    game = parse_live_game(payload(health))
    assert game and game.players[1].stats == {"health": health}
    assert "health" not in game.players[0].stats
    teams = CurrentGameService._teams(CurrentGameService._safe_players(game.players))
    assert _match_teams(teams)[0]["players"][1]["stats"]["health"] == health


@pytest.mark.parametrize("health", [None, True, "76", -1, 1001, float("inf"), float("nan"), {}, []])
def test_missing_or_invalid_hp_stays_unknown(health: Any) -> None:
    game = parse_live_game(payload(health))
    assert game and all("health" not in player.stats for player in game.players)


@pytest.mark.parametrize("mode", ["CLASSIC", "ARAM"])
def test_league_champion_health_cannot_become_tactician_hp(mode: str) -> None:
    value = payload()
    value["gameData"]["gameMode"] = mode
    game = parse_live_game(value)
    assert game and all("health" not in player.stats for player in game.players)


@pytest.mark.parametrize("roster", [[], [{"riotId": "Other#TEST"}], [{"riotId": "Self#TEST"}, {"riotId": "Self#TEST"}]])
def test_unresolved_or_ambiguous_self_cannot_receive_hp(roster: list[dict[str, Any]]) -> None:
    value = payload()
    value["allPlayers"] = roster
    game = parse_live_game(value)
    assert game and all("health" not in player.stats for player in game.players)


def test_bridge_drops_out_of_range_hp() -> None:
    assert "health" not in _match_teams([{"players": [{"name": "Self#TEST", "stats": {"health": 1001}}]}])[0]["players"][0]["stats"]


def test_current_tft_uses_identity_bound_periodic_health(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = Mock(return_value=TftMatchSnapshot((TftPlayerSnapshot(health=73, standing=2, board_units=6), TftPlayerSnapshot(health=89, standing=1, board_units=7)), 825, 1_800_000_000))
    monkeypatch.setattr("peaks.adapters.riot.tft_telemetry.read_tft_match", reader)
    game = LiveGame("tft", "Ranked", "Teamfight Tactics", None, players=(
        GamePlayer("Self#TEST", puuid="own", is_self=True), GamePlayer("Other#TEST", puuid="other"),
    ), phase="live", queue_id=1100, game_id="123", own_puuid="own")
    result = CurrentGameService()._league_session_view(game, SimpleNamespace())
    reader.assert_called_once_with("123", 1100, "own", ("own", "other"))
    players = result["teams"][0]["players"]
    assert players[0]["stats"] == {"health": 73, "standing": 2, "boardUnits": 6, "observedAt": 1_800_000_000}
    assert players[1]["stats"] == {"health": 89, "standing": 1, "boardUnits": 7, "observedAt": 1_800_000_000}
    assert _match_teams(result["teams"])[0]["players"][1]["stats"] == players[1]["stats"]
    assert "placement" not in players[0]["stats"]
    assert result["elapsed"] == "13:45"


@pytest.mark.parametrize(("game_name", "phase", "members"), [
    ("league", "live", (GamePlayer("Self#TEST", puuid="own", is_self=True),)),
    ("tft", "lobby", (GamePlayer("Self#TEST", puuid="own", is_self=True),)),
    ("tft", "live", (GamePlayer("Other#TEST", puuid="other", is_self=True),)),
    ("tft", "live", (GamePlayer("Hidden", puuid="own", is_self=True, hidden=True),)),
    ("tft", "live", (GamePlayer("Self#TEST", puuid="own", is_self=True),) * 2),
])
def test_other_game_phase_or_unverified_self_cannot_read_tft_stats(monkeypatch: pytest.MonkeyPatch, game_name: str, phase: str, members: tuple[GamePlayer, ...]) -> None:
    reader = Mock()
    monkeypatch.setattr("peaks.adapters.riot.tft_telemetry.read_tft_match", reader)
    game = LiveGame(game_name, "Ranked", "Map", None, players=members, phase=phase, queue_id=1100, game_id="123", own_puuid="own")
    CurrentGameService()._league_session_view(game, SimpleNamespace())
    reader.assert_not_called()


def test_periodic_snapshot_skips_hidden_players_and_preserves_native_health(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = Mock(return_value=TftMatchSnapshot((TftPlayerSnapshot(health=73), None, None), 825, 1_800_000_000))
    monkeypatch.setattr("peaks.adapters.riot.tft_telemetry.read_tft_match", reader)
    game = LiveGame("tft", "Ranked", "Teamfight Tactics", 900, players=(
        GamePlayer("Self#TEST", puuid="own", is_self=True, stats={"health": 60}),
        GamePlayer("Private#TEST", puuid="hidden", hidden=True),
        GamePlayer("Anonymous", puuid="anonymous"),
    ), phase="live", queue_id=1100, game_id="123", own_puuid="own")
    result = CurrentGameService()._league_session_view(game, SimpleNamespace())
    reader.assert_called_once_with("123", 1100, "own", ("own", None, None))
    players = _match_teams(result["teams"])[0]["players"]
    assert players[0]["stats"]["health"] == 60
    assert all(not player["stats"] for player in players[1:])
    assert result["elapsed"] == "15:00"


def test_snapshot_double_up_groups_reach_current_match(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = Mock(return_value=TftMatchSnapshot(tuple(TftPlayerSnapshot(health=80, duo=index // 2) for index in range(8)), 825, 1_800_000_000))
    monkeypatch.setattr("peaks.adapters.riot.tft_telemetry.read_tft_match", reader)
    game = LiveGame("tft", "Double Up", "Teamfight Tactics", None, players=tuple(
        GamePlayer(f"Player{index}#TEST", puuid=f"player-{index}", is_self=index == 0)
        for index in range(8)
    ), phase="live", queue_id=1160, game_id="123", own_puuid="player-0", team_mode="duos")
    result = CurrentGameService()._league_session_view(game, SimpleNamespace())
    assert len(result["teams"]) == 4
    assert all(team["grouping"] == "duo" and len(team["players"]) == 2 for team in result["teams"])
    assert result["teams"][0]["players"][0]["self"]


@pytest.mark.parametrize(("field", "value"), [
    ("standing", 0), ("standing", 33), ("standing", 1.5), ("boardUnits", 65),
    ("boardUnits", True), ("augmentCount", 17), ("observedAt", float("inf")),
])
def test_bridge_rejects_invalid_tft_snapshot_fields(field: str, value: Any) -> None:
    stats = _match_teams([{"players": [{"name": "Self#TEST", "stats": {"health": 73, field: value}}]}])[0]["players"][0]["stats"]
    assert field not in stats

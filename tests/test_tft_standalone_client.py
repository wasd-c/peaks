"""Standalone TFT client (patch 18.6+): sessions and finished games without LCU."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from peaks.adapters.riot.tft_client import (
    TFT_PROCESS_NAME,
    StandaloneTftClient,
    queue_name,
    read_log_state,
)
from peaks.adapters.riot.tft_local_history import read_tft_local_history
from peaks.application.runtime import CurrentGameService

NOW = datetime.now(UTC).timestamp()
GAME = 8051000543
QUEUE = 6080


def stamp(at: float) -> str:
    return "[" + datetime.fromtimestamp(at, UTC).strftime("%Y.%m.%d-%H.%M.%S:%f")[:-3] + "][  1]"


def lobby(state: str, at: float = NOW - 60) -> str:
    return f"{stamp(at)}TFT: [Standalone] TFTLobbySubsystem_2147482172: Entering LobbyState[ETFTLobbyState::{state}]\n"


def rms(resource: str, payload: dict, at: float = NOW - 60) -> str:
    return (f"{stamp(at)}RGIOPRms: Received RMS message ID 'abc' for resource '{resource}' "
            f"service 'svc' payload '{json.dumps(payload, separators=(',', ':'))}'\n")


def matchmaking(phase: str, at: float = NOW - 60) -> str:
    return rms("teambuilder/v1/tbdGameDtoV1/tft", {"counter": 1, "phaseName": phase, "queueId": QUEUE}, at)


IN_PROGRESS = rms("lol-gsm-server/v1/gsm/game-update/IN_PROGRESS", {"id": GAME, "gameState": "IN_PROGRESS", "queueId": QUEUE})
NOISE = f"{stamp(NOW - 60)}LogNet: Browse: 162.0.0.1:7113/Mode_Bootstrap/Bootstrap?PlayerKey=\"secret\"\n"


def stats(game_id: int = GAME, *, owner_health: int = 46, owner_standing: int = 2) -> dict:
    players = []
    for index in range(8):
        own = index == 1
        players.append({
            "PUUID": "owner" if own else f"player-{index}",
            "riotIdGameName": "" if index == 7 else f"Player{index}", "riotIdTagLine": "" if index == 7 else "EUW",
            "health": owner_health if own else (35 if index == 0 else -99),
            "ffaStanding": owner_standing if own else (1 if index == 0 else index + 1),
            "partnerGroupId": 0,
            "boardPieces": [{"championName": "DA_18_Yorick", "starLevel": 2, "itemNames": ["DA_WarmogsArmor"], "price": 1}],
            "augments": [],
        })
    return {"gameId": game_id, "gameMode": "TFT", "isRanked": False, "queueId": QUEUE, "queueType": "CHONCC_TREASURE_TFT",
            "statsBlock": {"gameLengthSeconds": 1546, "setCoreName": "TFTSet18", "players": players}}


def write_stats(directory: Path, value: dict, at: float = NOW - 30) -> None:
    path = directory / "TFTEoGStats.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    os.utime(path, (at, at))


def append(directory: Path, *lines: str) -> None:
    with (directory / "TFT.log").open("a", encoding="utf-8") as handle:
        handle.write("".join(lines))
    os.utime(directory / "TFT.log", (NOW - 1, NOW - 1))


def client(directory: Path, *, running: bool = True, product_phase: str | None = None) -> StandaloneTftClient:
    riot = Mock()

    def get_json(path: str) -> object:
        if path == "/entitlements/v1/token":
            return {"subject": "owner"}
        if path == "/product-session/v1/external-sessions":
            return {"token-like-key": {"productId": "teamfighttactics", "phase": product_phase}} if product_phase else {}
        raise AssertionError(path)

    riot.get_json.side_effect = get_json
    return StandaloneTftClient(riot, process_names={TFT_PROCESS_NAME} if running else {"RiotClientServices.exe"}, logs_directory=directory)


def test_follows_the_client_from_lobby_to_end_of_game(tmp_path: Path) -> None:
    append(tmp_path, lobby("Frontend"), NOISE)
    reader = client(tmp_path)
    assert reader.current_session() is None
    assert reader.activity_available

    append(tmp_path, lobby("SoloMode"), rms("parties/v1/notifications/tft", {"queueId": QUEUE}))
    session = reader.current_session()
    assert (session.phase, session.queue_id, session.game_mode) == ("lobby", QUEUE, None)

    append(tmp_path, lobby("Matchmaking"), matchmaking("MATCHMAKING"))
    assert reader.current_session().phase == "matchmaking"
    append(tmp_path, matchmaking("AFK_CHECK"))
    assert reader.current_session().phase == "readycheck"
    append(tmp_path, matchmaking("MATCHMAKING"))  # someone declined
    assert reader.current_session().phase == "matchmaking"
    append(tmp_path, matchmaking("AFK_CHECK"), matchmaking("CHAMPION_SELECT"))
    assert reader.current_session().phase == "pregame"

    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    live = reader.current_session()
    assert (live.phase, live.game, live.game_id, live.queue_id, live.team_mode) == ("live", "tft", str(GAME), QUEUE, "free-for-all")
    assert live.players == ()  # the first stats snapshot comes after the first round
    assert live.own_puuid == "owner"

    append(tmp_path, lobby("EndOfGameInterstitial", NOW - 5), lobby("EndOfGameSummary", NOW - 5))
    assert reader.current_session() is None
    append(tmp_path, lobby("SoloMode", NOW - 1))
    assert reader.current_session().phase == "lobby"


def test_live_roster_comes_from_the_matching_stats_file(tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    write_stats(tmp_path, stats())
    live = client(tmp_path).current_session()
    assert live.game_mode == "Choncc Treasure"
    assert live.game_time == 1546
    assert len(live.players) == 8
    own = [player for player in live.players if player.is_self]
    assert len(own) == 1 and own[0].name == "Player1#EUW"
    assert live.players[7].hidden and live.players[7].name is None
    assert {player.team for player in live.players} == {"Players"}

    write_stats(tmp_path, stats(game_id=GAME - 1))  # the previous game's file
    assert client(tmp_path).current_session().players == ()


def test_riot_gameplay_phase_confirms_a_match_before_the_lobby_state(tmp_path: Path) -> None:
    append(tmp_path, lobby("Matchmaking"), IN_PROGRESS)
    assert client(tmp_path, product_phase="Gameplay").current_session().phase == "live"


def test_closed_client_reports_nothing(tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    reader = client(tmp_path, running=False)
    assert reader.current_session() is None
    assert not reader.activity_available


def test_log_rotation_at_client_start_resets_state(tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"), NOISE * 50)
    assert read_log_state(tmp_path / "TFT.log").game_id == GAME
    (tmp_path / "TFT.log").unlink()
    append(tmp_path, lobby("Frontend"))
    state = read_log_state(tmp_path / "TFT.log")
    assert (state.lobby_state, state.game_id) == ("Frontend", None)


def test_queue_names() -> None:
    assert queue_name(1100) == "Ranked"
    assert queue_name(6080, "CHONCC_TREASURE_TFT") == "Choncc Treasure"
    assert queue_name(6080) is None


def history(directory: Path) -> list[dict]:
    return read_tft_local_history("owner", "EUW", directory=directory, now=NOW)


def test_finished_standalone_game_becomes_local_history(tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"), lobby("EndOfGameSummary", NOW - 10))
    write_stats(tmp_path, stats(owner_health=-2, owner_standing=2), at=NOW - 12)
    report, = history(tmp_path)
    assert report["id"] == f"EUW1_{GAME}"
    assert report["queue"] == str(QUEUE)
    assert report["result"] == "top_4"
    assert report["duration_seconds"] == 1546
    players = [player for team in report["metadata"]["teams"] for player in team["players"]]
    assert next(player for player in players if player["self"])["stats"] == {"placement": 2}
    # The last player standing has won even though their health stays above zero.
    assert next(player for player in players if player["name"] == "Player0#EUW")["stats"] == {"placement": 1}
    assert "secret" not in json.dumps(report)


def test_game_in_progress_or_from_another_match_is_not_history(tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    write_stats(tmp_path, stats())
    assert history(tmp_path) == []
    append(tmp_path, lobby("EndOfGameSummary", NOW - 10))
    write_stats(tmp_path, stats(game_id=GAME + 1))
    assert history(tmp_path) == []


def test_finished_game_survives_log_rotation(tmp_path: Path) -> None:
    backup = tmp_path / "TFT-backup-2026.11.19-13.46.00.log"
    backup.write_text(IN_PROGRESS + lobby("InGame") + lobby("EndOfGameSummary", NOW - 10), encoding="utf-8")
    os.utime(backup, (NOW - 5, NOW - 5))
    append(tmp_path, lobby("Frontend"))
    write_stats(tmp_path, stats(owner_health=-2), at=NOW - 12)
    assert [report["id"] for report in history(tmp_path)] == [f"EUW1_{GAME}"]


def test_runtime_uses_the_standalone_client_when_league_is_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    write_stats(tmp_path, stats(), at=NOW - 1)
    monkeypatch.setattr("peaks.application.runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr("peaks.adapters.riot.discovery.discover_riot_client", lambda: SimpleNamespace(process_running=True, available=True, reason="Connected", executable=None, lockfile=None))
    league = SimpleNamespace(current_game=lambda: None, current_session=lambda: None, activity_available=False, close=Mock())
    monkeypatch.setattr("peaks.adapters.riot.league.LeagueClient.from_discovery", lambda: league)
    standalone = client(tmp_path)
    standalone.close = Mock()
    monkeypatch.setattr("peaks.adapters.riot.tft_client.StandaloneTftClient.from_discovery", classmethod(lambda cls, discovery: standalone))
    service = CurrentGameService()
    service._detect_valorant = Mock(return_value=None)
    result = service.detect()
    assert (result["game"], result["phase"], result["mode"]) == ("TFT", "live", "Choncc Treasure")
    assert len(result["teams"][0]["players"]) == 8
    assert "owner" not in json.dumps(result)
    service._detect_valorant.assert_not_called()
    standalone.close.assert_called_once()


def double_up(queue_type: str = "TFT_EVENT_SET19", queue_id: int = 7010) -> dict:
    value = stats()
    value.update(queueId=queue_id, queueType=queue_type)
    for index, row in enumerate(value["statsBlock"]["players"]):
        row["partnerGroupId"] = 101 + index // 2  # ids are not guaranteed to be 1..4
    return value


@pytest.mark.parametrize("value", [double_up(), double_up("RANKED_TFT_DOUBLE_UP"), double_up(queue_id=1160)])
def test_double_up_is_recognized_from_pairs_or_queue_type_whatever_the_queue(tmp_path: Path, value: dict) -> None:
    progress = rms("lol-gsm-server/v1/gsm/game-update/IN_PROGRESS", {"id": GAME, "queueId": value["queueId"]})
    append(tmp_path, progress, lobby("InGame"))
    write_stats(tmp_path, value)
    live = client(tmp_path).current_session()
    assert live.team_mode == "duos"
    assert [player.team for player in live.players] == ["duo:0", "duo:0", "duo:1", "duo:1", "duo:2", "duo:2", "duo:3", "duo:3"]


def test_event_modes_without_pairs_stay_free_for_all(tmp_path: Path) -> None:
    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    write_stats(tmp_path, stats())  # Choncc's Treasure: every partnerGroupId is 0
    live = client(tmp_path).current_session()
    assert live.team_mode == "free-for-all"
    assert {player.team for player in live.players} == {"Players"}


def test_partial_pairs_are_not_a_double_up(tmp_path: Path) -> None:
    value = double_up()
    value["statsBlock"]["players"][7]["partnerGroupId"] = 0
    append(tmp_path, IN_PROGRESS, lobby("InGame"))
    write_stats(tmp_path, value)
    assert client(tmp_path).current_session().team_mode == "free-for-all"


def test_double_up_history_keeps_the_pairs(tmp_path: Path) -> None:
    value = double_up()
    for index, row in enumerate(value["statsBlock"]["players"]):
        row["ffaStanding"] = 1 + index // 2
        row["health"] = 10 if index < 2 else -99
    value["statsBlock"]["players"][1]["health"] = -2  # the owner
    append(tmp_path, rms("lol-gsm-server/v1/gsm/game-update/IN_PROGRESS", {"id": GAME, "queueId": 7010}),
           lobby("InGame"), lobby("EndOfGameSummary", NOW - 10))
    write_stats(tmp_path, value, at=NOW - 12)
    report, = history(tmp_path)
    assert report["metadata"]["teamMode"] == "duos"
    assert [team["name"] for team in report["metadata"]["teams"]] == ["Duo 1", "Duo 2", "Duo 3", "Duo 4"]
    assert report["result"] == "top_2"

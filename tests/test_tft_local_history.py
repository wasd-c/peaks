"""The game already has a final report even when Riot history is delayed."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest

from peaks.adapters.riot.tft_local_history import (
    MAX_AGE_SECONDS,
    MAX_TAIL_BYTES,
    platform_match_id,
    read_tft_local_history,
)

NOW = datetime.now(UTC).timestamp()


def payload(game_id: int = 123) -> dict:
    return {
        "gameId": game_id, "gameMode": "TFT", "queueId": 1100,
        "private": "never-persist",
        "statsBlock": {"gameLengthSeconds": 1533, "players": [
            {"PUUID": f"player-{place}" if place != 7 else "owner", "ffaStanding": place,
             "health": 40 if place < 7 else 0, "playerId": 112233,
             "riotIdGameName": f"Player{place}", "riotIdTagLine": "TEST",
             "boardPieces": [{"championName": "DA_18_Ashe", "starLevel": 2,
                              "itemNames": ["TFT_Item_InfinityEdge"], "secret": "never-persist"}]}
            for place in range(1, 9)
        ]},
    }


def line(value: dict, ended_at: float = NOW - 5) -> str:
    timestamp = datetime.fromtimestamp(ended_at, UTC).strftime("%Y.%m.%d-%H.%M.%S:%f")[:-3]
    return (f"[{timestamp}][842]RGIOPHttp: UTFTLeagueFoundationClient::PostEogStatsBlock: Query Start"
            " | POST https://127.0.0.1:12345/lol-end-of-game/v1/gameclient-eog-stats-block"
            " | SessionId: ignored | TraceId: ignored | RequestBody: " + json.dumps(value) + "\n")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    os.utime(path, (NOW, NOW))


def read(directory: Path, **kwargs) -> list[dict]:
    return read_tft_local_history("owner", "EUW", directory=directory, now=NOW, **kwargs)


def test_recovers_own_final_placement_board_and_actual_duration_without_network(tmp_path: Path) -> None:
    write(tmp_path / "TFT.log", line(payload()))
    report, = read(tmp_path)
    assert report["id"] == "EUW1_123"
    assert report["game"] == "tft"
    assert report["result"] == "placement"
    assert report["duration_seconds"] == 1533
    assert report["played_at"] == pytest.approx(NOW - 5 - 1533, abs=0.002)
    players = report["metadata"]["teams"][0]["players"]
    owner = next(row for row in players if row["self"])
    assert owner["stats"] == {"placement": 7}
    assert owner["composition"]["units"] == [{"id": "DA_18_Ashe", "stars": 2, "items": ["TFT_Item_InfinityEdge"]}]
    assert "placement" not in players[0]["stats"]
    assert "composition" not in players[0]
    assert players[-1]["stats"]["placement"] == 8
    assert report["metadata"]["localEndOfGame"] is True
    serialized = json.dumps(report)
    for excluded in ("PUUID", "playerId", "private", "never-persist", "SessionId", "TraceId", "127.0.0.1"):
        assert excluded not in serialized
    assert "damage" not in serialized and "rank_delta" not in report


def test_only_final_log_event_qualifies_not_live_file_or_arbitrary_json(tmp_path: Path) -> None:
    write(tmp_path / "TFTEoGStats.json", json.dumps(payload()))
    write(tmp_path / "TFT.log", json.dumps(payload()) + "\n" + line(payload()).replace("PostEogStatsBlock", "PollLiveStatsBlock"))
    assert read(tmp_path) == []


@pytest.mark.parametrize("change", [
    lambda value: value["statsBlock"]["players"].pop(6),
    lambda value: value["statsBlock"]["players"].append(deepcopy(value["statsBlock"]["players"][6])),
    lambda value: value.update(gameId=True),
    lambda value: value.update(queueId="1100"),
    lambda value: value.update(gameMode="CLASSIC"),
    lambda value: value["statsBlock"].update(gameLengthSeconds=float("nan")),
    lambda value: value["statsBlock"].update(gameLengthSeconds=-1),
    lambda value: value["statsBlock"]["players"][6].update(ffaStanding=True),
    lambda value: value["statsBlock"]["players"][6].update(ffaStanding=9),
])
def test_rejects_wrong_identity_and_invalid_final_evidence(tmp_path: Path, change) -> None:
    value = payload()
    change(value)
    write(tmp_path / "TFT.log", line(value))
    assert read(tmp_path) == []


@pytest.mark.parametrize(("game_id", "platform", "expected"), [
    (123, "EUW", "EUW1_123"), ("EUW1_123", "euw1", "EUW1_123"),
    (123, "EUNE", "EUN1_123"), (123, "KR", "KR_123"),
    (123, "PBE", "PBE1_123"), ("PBE1_123", "pbe1", "PBE1_123"), ("NA1_123", "PBE", None),
    ("NA1_123", "EUW", None), ("tft-123", "EUW", None),
    (True, "EUW", None), (123, "GLOBAL", None), (0, "EUW", None),
])
def test_match_id_uses_verified_platform_only(game_id, platform, expected) -> None:
    assert platform_match_id(game_id, platform) == expected


def test_no_missing_subject_or_guessed_region(tmp_path: Path) -> None:
    write(tmp_path / "TFT.log", line(payload()))
    for owner, region in ((None, "EUW"), ("", "EUW"), ("other", "EUW"), ("owner", "GLOBAL"), ("owner ", "EUW")):
        assert read_tft_local_history(owner, region, directory=tmp_path, now=NOW) == []


def test_rotation_deduplicates_by_game_and_returns_newest_twenty(tmp_path: Path) -> None:
    events = [line(payload(index + 1), NOW - (index + 1) * 60) for index in range(25)]
    write(tmp_path / "TFT.log", "".join(events))
    write(tmp_path / "TFT-backup-2026.09.20-05.00.00.log", events[0])
    reports = read(tmp_path)
    assert [row["id"] for row in reports] == [f"EUW1_{index}" for index in range(1, 21)]
    assert len(read(tmp_path, limit=3)) == 3


def test_cache_tracks_new_end_event_and_cannot_be_mutated_by_callers(tmp_path: Path) -> None:
    path = tmp_path / "TFT.log"
    write(path, line(payload()))
    reports = read(tmp_path)
    reports[0]["metadata"]["teams"][0]["players"].clear()
    assert len(read(tmp_path)[0]["metadata"]["teams"][0]["players"]) == 8
    write(path, line(payload()) + line(payload(456), NOW - 1))
    assert [row["id"] for row in read(tmp_path)] == ["EUW1_456", "EUW1_123"]


def test_reads_only_tail_and_ignores_truncated_or_future_reports(tmp_path: Path) -> None:
    write(tmp_path / "TFT.log", line(payload(987)) + "x" * MAX_TAIL_BYTES + "\n" + line(payload()) + line(payload(456))[:-50])
    assert [row["id"] for row in read(tmp_path)] == ["EUW1_123"]
    write(tmp_path / "TFT.log", line(payload(), NOW + 3600) + line(payload(555), NOW - MAX_AGE_SECONDS - 1))
    assert read(tmp_path) == []


def test_double_up_retains_explicit_pairs_and_native_placement_scale(tmp_path: Path) -> None:
    value = payload()
    value["queueId"] = 1160
    for index, row in enumerate(value["statsBlock"]["players"]):
        row["partnerGroupId"] = index // 2 + 1
        row["health"] = -99
        row["ffaStanding"] = index // 2 + 1
    write(tmp_path / "TFT.log", line(value))
    report, = read(tmp_path)
    assert report["metadata"]["teamMode"] == "duos"
    assert len(report["metadata"]["teams"]) == 4
    assert all(team["grouping"] == "duo" and len(team["players"]) == 2 for team in report["metadata"]["teams"])
    assert report["result"] == "placement"
    assert next(player for team in report["metadata"]["teams"] for player in team["players"] if player["self"])["stats"]["placement"] == 4


def test_winner_does_not_require_zero_health(tmp_path: Path) -> None:
    value = payload()
    value["statsBlock"]["players"][0]["PUUID"] = "owner"
    value["statsBlock"]["players"][6]["PUUID"] = "opponent"
    write(tmp_path / "TFT.log", line(value))
    assert read(tmp_path)[0]["result"] == "top_4"

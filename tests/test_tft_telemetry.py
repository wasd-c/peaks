"""Current TFT file health is fresh, match-bound and stripped of identities."""

from __future__ import annotations

import json
import os
from dataclasses import FrozenInstanceError, asdict
from pathlib import Path
from typing import Any

import pytest

from peaks.adapters.riot.tft_telemetry import MAX_SNAPSHOT_BYTES, read_tft_health, read_tft_match

NOW = 1_800_000_000.0
MATCH = 123456789
QUEUE = 1100
OWN = "owned-player-subject"


def payload() -> dict[str, Any]:
    return {
        "gameId": MATCH,
        "queueId": QUEUE,
        "statsBlock": {
            "gameLengthSeconds": 825,
            "players": [
                {"PUUID": "other-player", "riotIdGameName": "Private opponent", "health": 97},
                {"PUUID": OWN, "riotIdGameName": "Private self", "health": 73},
            ],
        },
    }


def write_snapshot(tmp_path: Path, value: object, *, age: float = 0) -> Path:
    filename = tmp_path / "TFTEoGStats.json"
    filename.write_text(json.dumps(value), encoding="utf-8")
    os.utime(filename, (NOW - age, NOW - age))
    return filename


def test_current_match_owned_health_returns_only_public_numbers(tmp_path: Path) -> None:
    filename = write_snapshot(tmp_path, payload(), age=80)
    result = read_tft_health(str(MATCH), str(QUEUE), OWN, path=filename, now=NOW)
    assert result is not None
    assert asdict(result) == {"health": 73, "game_time": 825.0, "observed_at": NOW - 80}
    assert OWN not in repr(result) and "Private" not in repr(result)
    with pytest.raises(FrozenInstanceError):
        result.health = 999  # type: ignore[misc]


@pytest.mark.parametrize("health", [0, 1, 73.5, 1000])
def test_zero_and_finite_health_values_are_preserved(tmp_path: Path, health: int | float) -> None:
    value = payload()
    value["statsBlock"]["players"][1]["health"] = health
    filename = write_snapshot(tmp_path, value)
    result = read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW)
    assert result is not None and result.health == health


@pytest.mark.parametrize("health", [None, True, False, "73", -1, 1001, float("nan"), float("inf"), -(10**400), 10**400])
def test_invalid_health_is_not_coerced_or_replaced_by_opponent_health(tmp_path: Path, health: object) -> None:
    value = payload()
    value["statsBlock"]["players"][1]["health"] = health
    filename = write_snapshot(tmp_path, value)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


@pytest.mark.parametrize("age", [0, 80, 180, -5])
def test_bounded_periodic_snapshots_are_accepted(tmp_path: Path, age: float) -> None:
    filename = write_snapshot(tmp_path, payload(), age=age)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is not None


@pytest.mark.parametrize("age", [180.1, 86400, -5.1, -300])
def test_stale_and_future_snapshots_are_rejected(tmp_path: Path, age: float) -> None:
    filename = write_snapshot(tmp_path, payload(), age=age)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


@pytest.mark.parametrize(("field", "value"), [
    ("gameId", MATCH + 1), ("gameId", str(MATCH)), ("gameId", True),
    ("queueId", 1160), ("queueId", str(QUEUE)), ("queueId", True),
])
def test_wrong_or_untyped_file_identity_is_rejected(tmp_path: Path, field: str, value: object) -> None:
    source = payload()
    source[field] = value
    filename = write_snapshot(tmp_path, source)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


@pytest.mark.parametrize(("game", "queue", "owner"), [
    (None, QUEUE, OWN), (True, QUEUE, OWN), (0, QUEUE, OWN), (MATCH + 1, QUEUE, OWN),
    (" 123456789", QUEUE, OWN), ("0123456789", QUEUE, OWN), (MATCH, 1160, OWN),
    (MATCH, None, OWN), (MATCH, True, OWN), (MATCH, QUEUE, "wrong-owner"),
    (MATCH, QUEUE, ""), (MATCH, QUEUE, None), (MATCH, QUEUE, " " + OWN),
    (MATCH, QUEUE, OWN + "\n"), (10**50, QUEUE, OWN), (MATCH, 10**50, OWN),
])
def test_invalid_or_different_current_identity_never_reads_another_match(
    tmp_path: Path, game: object, queue: object, owner: object,
) -> None:
    filename = write_snapshot(tmp_path, payload())
    assert read_tft_health(game, queue, owner, path=filename, now=NOW) is None


@pytest.mark.parametrize("mode", ["missing", "duplicate", "lowercase-key", "malformed-player", "oversized"])
def test_self_must_be_exactly_one_well_formed_owned_player(tmp_path: Path, mode: str) -> None:
    value = payload()
    rows = value["statsBlock"]["players"]
    if mode == "missing":
        rows.pop()
    elif mode == "duplicate":
        rows.append(dict(rows[1]))
    elif mode == "lowercase-key":
        rows[1]["puuid"] = rows[1].pop("PUUID")
    elif mode == "malformed-player":
        rows.append(None)
    else:
        rows.extend({"PUUID": f"player-{index}", "health": 100} for index in range(31))
    filename = write_snapshot(tmp_path, value)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


@pytest.mark.parametrize("value", [None, [], "text", {}, {"gameId": MATCH, "queueId": QUEUE, "statsBlock": []}])
def test_malformed_payload_has_no_health(tmp_path: Path, value: object) -> None:
    filename = write_snapshot(tmp_path, value)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


@pytest.mark.parametrize("contents", [b"", b'{"gameId":123', b"\xff\xfe\xff", b"[" * 2000])
def test_partial_invalid_or_too_deep_json_does_not_escape(tmp_path: Path, contents: bytes) -> None:
    filename = tmp_path / "TFTEoGStats.json"
    filename.write_bytes(contents)
    os.utime(filename, (NOW, NOW))
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


def test_oversized_snapshot_is_rejected_before_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    filename = tmp_path / "TFTEoGStats.json"
    filename.write_bytes(b" " * (MAX_SNAPSHOT_BYTES + 1))
    os.utime(filename, (NOW, NOW))

    def forbidden_open(*args: object, **kwargs: object) -> None:
        raise AssertionError("oversized file must not be read")

    monkeypatch.setattr(Path, "open", forbidden_open)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None


def test_rewrite_between_stat_checks_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    filename = write_snapshot(tmp_path, payload())
    original_stat = Path.stat
    reads = 0

    def changing_stat(self: Path, *, follow_symlinks: bool = True) -> os.stat_result:
        nonlocal reads
        if self == filename:
            reads += 1
            if reads == 2:
                os.utime(filename, (NOW + 1, NOW + 1))
        return original_stat(self, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", changing_stat)
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW) is None
    assert reads == 2


@pytest.mark.parametrize("elapsed", [None, True, "825", -1, float("nan"), float("inf"), 86401])
def test_invalid_optional_elapsed_does_not_invent_time(tmp_path: Path, elapsed: object) -> None:
    value = payload()
    value["statsBlock"]["gameLengthSeconds"] = elapsed
    filename = write_snapshot(tmp_path, value)
    result = read_tft_health(MATCH, QUEUE, OWN, path=filename, now=NOW)
    assert result is not None and result.game_time is None and result.health == 73


def test_default_is_fixed_game_log_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "TFT" / "Saved" / "Logs"
    folder.mkdir(parents=True)
    write_snapshot(folder, payload())
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert read_tft_health(MATCH, QUEUE, OWN, now=NOW) is not None
    monkeypatch.delenv("LOCALAPPDATA")
    assert read_tft_health(MATCH, QUEUE, OWN, now=NOW) is None


def test_missing_and_directory_paths_are_unavailable(tmp_path: Path) -> None:
    assert read_tft_health(MATCH, QUEUE, OWN, path=tmp_path / "missing.json", now=NOW) is None
    assert read_tft_health(MATCH, QUEUE, OWN, path=tmp_path, now=NOW) is None


@pytest.mark.parametrize("now", [float("nan"), float("inf"), -1])
def test_invalid_clock_is_unavailable(tmp_path: Path, now: float) -> None:
    filename = write_snapshot(tmp_path, payload())
    assert read_tft_health(MATCH, QUEUE, OWN, path=filename, now=now) is None


def test_roster_projection_uses_identities_not_file_order_and_keeps_only_numbers(tmp_path: Path) -> None:
    value = payload()
    value["statsBlock"]["players"][0].update(ffaStanding=1, boardPieces=[{"characterName": "Private board data"}] * 7, augments=["Known augment"])
    value["statsBlock"]["players"][1].update(ffaStanding=2, boardPieces=[{}] * 6, augments=[], level=6)
    filename = write_snapshot(tmp_path, value, age=45)
    result = read_tft_match(MATCH, QUEUE, OWN, (OWN, "other-player", None, "not-in-file"), path=filename, now=NOW)
    assert result is not None
    own, other, hidden, absent = result.players
    assert own and own.stats(result.observed_at) == {"health": 73, "standing": 2, "boardUnits": 6, "level": 6, "observedAt": NOW - 45}
    assert other and other.stats(result.observed_at) == {"health": 97, "standing": 1, "boardUnits": 7, "augmentCount": 1, "observedAt": NOW - 45}
    assert hidden is absent is None
    assert OWN not in repr(result) and "Private" not in repr(result) and "other-player" not in repr(result)


@pytest.mark.parametrize(("health", "expected"), [(-1, 0), (-20, 0), (-98, 0), (-99, None), (-100, None), (0, 0), (99, 99)])
def test_elimination_overshoot_is_zero_but_game_end_sentinel_is_not_hp(tmp_path: Path, health: int, expected: int | None) -> None:
    value = payload()
    value["statsBlock"]["players"][1].update(health=health, ffaStanding=2)
    result = read_tft_match(MATCH, QUEUE, OWN, (OWN,), path=write_snapshot(tmp_path, value), now=NOW)
    assert result and result.players[0]
    assert result.players[0].health == expected and result.players[0].standing == 2


@pytest.mark.parametrize("change", ["old-match", "old-queue", "stale", "missing-own", "duplicate-own", "duplicate-roster-own"])
def test_extended_snapshot_requires_fresh_exact_owned_match(tmp_path: Path, change: str) -> None:
    value = payload()
    roster = (OWN, "other-player")
    age = 0
    if change == "old-match":
        value["gameId"] += 1
    elif change == "old-queue":
        value["queueId"] += 1
    elif change == "stale":
        age = 181
    elif change == "missing-own":
        value["statsBlock"]["players"].pop()
    elif change == "duplicate-own":
        value["statsBlock"]["players"].append(dict(value["statsBlock"]["players"][1]))
    else:
        roster = (OWN, OWN)
    assert read_tft_match(MATCH, QUEUE, OWN, roster, path=write_snapshot(tmp_path, value, age=age), now=NOW) is None


def test_duplicate_opponent_is_not_projected(tmp_path: Path) -> None:
    value = payload()
    value["statsBlock"]["players"].append(dict(value["statsBlock"]["players"][0]))
    result = read_tft_match(MATCH, QUEUE, OWN, (OWN, "other-player"), path=write_snapshot(tmp_path, value), now=NOW)
    assert result and result.players[0] and result.players[1] is None


def test_missing_or_malformed_optional_stats_are_never_zero_filled(tmp_path: Path) -> None:
    value = payload()
    value["statsBlock"]["players"][1].update(health=-99, ffaStanding=0, boardPieces=["bad"], augments=[], level=True)
    result = read_tft_match(MATCH, QUEUE, OWN, (OWN,), path=write_snapshot(tmp_path, value), now=NOW)
    assert result and result.players[0] and result.players[0].stats(result.observed_at) == {}


def test_empty_board_is_a_valid_zero(tmp_path: Path) -> None:
    value = payload()
    value["statsBlock"]["players"][1]["boardPieces"] = []
    result = read_tft_match(MATCH, QUEUE, OWN, (OWN,), path=write_snapshot(tmp_path, value), now=NOW)
    assert result and result.players[0] and result.players[0].board_units == 0


@pytest.mark.parametrize("mode", ["valid", "normal-queue", "all-zero", "oversized-pair", "hidden-partner", "duplicate-player"])
def test_double_up_requires_complete_explicit_pairs(tmp_path: Path, mode: str) -> None:
    value = payload()
    value["queueId"] = 1100 if mode == "normal-queue" else 1160
    rows = [{"PUUID": OWN if index == 0 else f"p{index}", "health": 80, "partnerGroupId": index // 2 + 1} for index in range(8)]
    roster: tuple[str | None, ...] = tuple(row["PUUID"] for row in rows)
    if mode == "all-zero":
        for row in rows:
            row["partnerGroupId"] = 0
    elif mode == "oversized-pair":
        rows[2]["partnerGroupId"] = 1
    elif mode == "hidden-partner":
        roster = (OWN, None, *roster[2:])
    elif mode == "duplicate-player":
        rows[7]["PUUID"] = "p6"
    value["statsBlock"]["players"] = rows
    result = read_tft_match(MATCH, value["queueId"], OWN, roster, path=write_snapshot(tmp_path, value), now=NOW)
    assert result
    if mode == "valid":
        assert [player.duo for player in result.players if player] == [0, 0, 1, 1, 2, 2, 3, 3]
    else:
        assert all(player is None or player.duo is None for player in result.players)

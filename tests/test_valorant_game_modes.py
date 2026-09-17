from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from peaks.adapters.riot.valorant import (
    ValorantCoregame,
    ValorantMatchSummary,
    ValorantPregame,
    is_free_for_all,
    parse_coregame,
    parse_match_details,
    parse_pregame,
)
from peaks.adapters.riot.valorant_presence import ValorantPresence
from peaks.application.runtime import CurrentGameService
from peaks.bridge import _match_teams

DM_MODE = "/Game/GameModes/Deathmatch/Deathmatch_GameMode.Deathmatch_GameMode_C"


def current_view(monkeypatch: pytest.MonkeyPatch, match: ValorantCoregame | ValorantPregame):
    client = SimpleNamespace(detect=lambda: match, rank=lambda: None)
    context = MagicMock()
    context.__enter__.return_value = (client, "owned")
    service = CurrentGameService()
    monkeypatch.setattr(service, "_open_valorant_client", lambda discovery: context)
    monkeypatch.setattr(service, "_valorant_agent_names", lambda: {})
    monkeypatch.setattr(service, "_own_valorant_presence", lambda *args: ValorantPresence(7, 5))
    return service._detect_valorant(object())


def test_live_deathmatch_keeps_sixteen_players_in_one_ffa_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = parse_coregame(
        {
            "MatchID": "mode-match",
            "ModeID": DM_MODE,
            "Players": [
                {
                    "Subject": "owned" if index == 0 else f"player-{index}",
                    "TeamID": f"private-team-{index}",
                }
                for index in range(16)
            ],
        }
    )
    assert parsed is not None and parsed.free_for_all
    current = current_view(monkeypatch, parsed)
    assert current["phase"] == "live" and current["modeId"] == DM_MODE
    assert current["freeForAll"] is True and len(current["teams"]) == 1
    assert len(current["teams"][0]["players"]) == 16
    assert current["teams"][0]["score"] == "—"
    assert "private-team" not in repr(current)


def test_live_unknown_mode_preserves_eight_actual_teams_without_guessing_queue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parsed = parse_coregame(
        {
            "MatchID": "mode-match",
            "ModeID": "/Game/GameModes/Future/ActualMode",
            "MatchmakingData": {"QueueID": "server-provided-queue"},
            "Players": [
                {
                    "Subject": "owned" if index == 0 else f"player-{index}",
                    "TeamID": f"private-team-{index // 2}",
                }
                for index in range(16)
            ],
        }
    )
    assert parsed is not None
    current = current_view(monkeypatch, parsed)
    assert current["phase"] == "live" and current["mode"] == "server-provided-queue"
    assert current["queue"] == "server-provided-queue" and current["freeForAll"] is False
    assert [len(team["players"]) for team in current["teams"]] == [2] * 8
    assert all(team["score"] == "—" for team in current["teams"])
    assert "private-team" not in repr(current)


def test_pregame_retains_parent_teams_and_complete_three_vs_three_roster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    teams = [
        {
            "TeamID": team,
            "Players": [
                {"Subject": "owned" if index == 0 and team == "Blue" else f"{team}-{index}"}
                for index in range(3)
            ],
        }
        for team in ("Blue", "Red")
    ]
    parsed = parse_pregame(
        {
            "ID": "mode-match",
            "QueueID": "retake",
            "Mode": "actual-mode",
            "Teams": teams,
            "AllyTeam": teams[0],
        }
    )
    assert parsed is not None and len(parsed.players) == 6
    assert [player.team_id for player in parsed.players] == ["Blue"] * 3 + ["Red"] * 3
    current = current_view(monkeypatch, parsed)
    assert current["phase"] == "pregame" and current["mode"] == "retake"
    assert [len(team["players"]) for team in current["teams"]] == [3, 3]
    assert all(team["score"] == "—" for team in current["teams"])


@pytest.mark.parametrize("metadata_count", [0, 3, 8])
def test_completed_unknown_mode_keeps_eight_teams_when_metadata_is_missing(
    metadata_count: int,
) -> None:
    payload = {
        "matchInfo": {"matchId": "mode-match", "queueID": "server-provided-queue"},
        "players": [
            {
                "subject": "owned" if index == 0 else f"player-{index}",
                "teamId": f"team-{index // 2}",
            }
            for index in range(16)
        ],
        "teams": [{"teamId": f"team-{index}"} for index in range(metadata_count)],
    }
    summary = parse_match_details(
        payload, puuid="owned", fallback=ValorantMatchSummary("mode-match")
    )
    assert not summary.free_for_all
    assert [len(team.players) for team in summary.teams] == [2] * 8
    assert len({player.team_id for team in summary.teams for player in team.players}) == 8
    projected = _match_teams(
        [
            {
                "name": team.name,
                "players": [
                    {"name": f"Player {index}", "self": player.self}
                    for index, player in enumerate(team.players)
                ],
            }
            for team in summary.teams
        ]
    )
    assert [len(team["players"]) for team in projected] == [2] * 8


def test_mode_identification_does_not_confuse_team_deathmatch_or_guess_from_team_counts() -> None:
    assert is_free_for_all("deathmatch")
    assert is_free_for_all(None, DM_MODE)
    assert not is_free_for_all(
        "team-deathmatch", "/Game/GameModes/TeamDeathmatch/TeamDeathmatch_GameMode"
    )
    assert not is_free_for_all("unknown-mode")
    parsed = parse_coregame(
        {"MatchID": "mode-match", "QueueID": "unsafe\nqueue", "ModeID": "unsafe?token=value"}
    )
    assert parsed is not None and parsed.queue_id is None and parsed.mode_id is None


def test_bridge_keeps_sixteen_ffa_participants_and_bounds_total_roster() -> None:
    assert (
        len(
            _match_teams(
                [
                    {
                        "name": "Free for all",
                        "players": [{"name": f"Player {index}"} for index in range(16)],
                    }
                ]
            )[0]["players"]
        )
        == 16
    )
    projected = _match_teams(
        [
            {
                "name": f"Team {team}",
                "players": [{"name": f"Player {index}"} for index in range(20)],
            }
            for team in range(30)
        ]
    )
    assert len(projected) == 20
    assert sum(len(team["players"]) for team in projected) == 20

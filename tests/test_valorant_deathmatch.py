from __future__ import annotations

from peaks.adapters.riot.valorant import ValorantMatchSummary, parse_match_details
from peaks.bridge import _match


def _deathmatch_payload(player_count: int = 12) -> dict[str, object]:
    players = []
    teams = []
    for index in range(player_count):
        subject = "owned-puuid" if index == 0 else f"player-{index}"
        team_id = f"player-team-{index}"
        players.append(
            {
                "subject": subject,
                "teamId": team_id,
                "gameName": f"Player {index + 1}",
                "tagLine": "DM",
                "stats": {
                    "kills": player_count - index,
                    "deaths": index,
                    "assists": 0,
                },
            }
        )
        teams.append(
            {
                "teamId": team_id,
                "won": index == 0,
                "numPoints": player_count - index,
            }
        )
    return {
        "matchInfo": {"matchId": "deathmatch-1", "queueID": "deathmatch"},
        "players": players,
        "teams": teams,
    }


def test_deathmatch_keeps_every_participant_in_one_free_for_all_roster() -> None:
    summary = parse_match_details(
        _deathmatch_payload(),
        puuid="owned-puuid",
        fallback=ValorantMatchSummary("deathmatch-1"),
    )

    assert summary.free_for_all is True
    assert len(summary.teams) == 1
    assert summary.teams[0].name == "Free for all"
    assert len(summary.teams[0].players) == 12
    assert [player.riot_id for player in summary.teams[0].players] == [
        f"Player {index}#DM" for index in range(1, 13)
    ]
    assert sum(player.self for player in summary.teams[0].players) == 1


def test_bridge_preserves_full_deathmatch_roster_and_ffa_marker() -> None:
    players = [
        {
            "name": f"Player {index}",
            "riotId": f"Player {index}#DM",
            "score": f"{20 - index} / {index} / 0",
        }
        for index in range(12)
    ]

    projected = _match(
        {
            "match_id": "deathmatch-1",
            "game": "valorant",
            "queue": "deathmatch",
            "metadata": {
                "freeForAll": True,
                "teams": [{"name": "Free for all", "players": players}],
            },
        }
    )

    assert projected["freeForAll"] is True
    assert len(projected["teams"]) == 1
    assert len(projected["teams"][0]["players"]) == 12

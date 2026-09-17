from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from peaks.adapters.riot.client import RiotClientUnavailable
from peaks.adapters.riot.valorant import (
    ValorantClient,
    ValorantMatchPlayer,
    ValorantMatchSummary,
    ValorantMatchTeam,
)
from peaks.adapters.riot.valorant_enrichment import (
    CompletedMatch,
    RequestBudget,
    ValorantEnrichmentCache,
)
from peaks.bridge import _match_teams


class StatsClient:
    puuid = "owner"

    def __init__(self, payloads: dict[str, Any] | None = None) -> None:
        self.payloads = payloads or {}
        self.calls: list[str] = []

    def _get_json(self, service: str, path: str) -> Any:
        self.calls.append(path)
        if path not in self.payloads:
            raise RiotClientUnavailable("Unavailable")
        return self.payloads[path]


def test_completed_player_progress_tracks_pending_success_and_unavailable_individually() -> None:
    cache = ValorantEnrichmentCache()
    visible = ValorantMatchPlayer(riot_id="Visible#EUW", kills=12)
    hidden = replace(visible, riot_id=None, hidden=True)
    unknown = ValorantMatchPlayer()
    match = CompletedMatch(
        ValorantMatchSummary("report", teams=(ValorantMatchTeam("Blue", players=(visible, hidden, unknown)),)),
        (("visible", visible), ("private", hidden)),
    )
    first = cache._enrich(match)
    assert [player.stats_loading for player in first.teams[0].players] == [True, False, False]
    assert first.teams[0].players[0].kills == 12
    cache._put("rank", "visible", None, 60)
    cache._put("overall", "visible", {"kills": 30, "matchesPlayed": 2}, 60)
    cache._put("overall_pending", "visible", True, 60)
    partial = cache._enrich(match).teams[0].players[0]
    assert partial.stats_loading and partial.overall_stats == {"kills": 30, "matchesPlayed": 2}
    cache._put("overall_pending", "visible", False, 60)
    assert not cache._enrich(match).teams[0].players[0].stats_loading
    cache._put("overall", "visible", None, 60)
    assert not cache._enrich(match).teams[0].players[0].stats_loading


def test_live_players_finish_loading_as_each_bounded_history_request_resolves() -> None:
    cache = ValorantEnrichmentCache()
    client = StatsClient()
    subjects = ("one", "two", "three", "four", "five")
    first = cache.live_profiles(cast(ValorantClient, client), subjects)
    assert [first[subject]["statsLoading"] for subject in subjects] == [False, False, True, True, True]
    second = cache.live_profiles(cast(ValorantClient, client), subjects)
    assert [second[subject]["statsLoading"] for subject in subjects] == [False, False, False, False, True]
    third = cache.live_profiles(cast(ValorantClient, client), subjects)
    assert not any(player["statsLoading"] for player in third.values())
    assert len([path for path in client.calls if path.startswith("/match-history/")]) == 5


def test_failed_match_details_finish_loading_instead_of_leaving_history_pending() -> None:
    client = StatsClient({
        "/match-history/v1/history/owner?startIndex=0&endIndex=5&queue=competitive": {
            "History": [{"MatchID": "inaccessible"}],
        },
    })
    cache = ValorantEnrichmentCache()
    cache._put("rank", "owner", None, 60)
    assert cache.overall(cast(ValorantClient, client), "owner", RequestBudget()) is None
    assert not cache._stats_pending("owner")
    assert cache._get("overall_pending", "owner") == (True, False)


def test_deferred_match_details_keep_loading_until_the_request_can_run() -> None:
    client = StatsClient({
        "/match-history/v1/history/owner?startIndex=0&endIndex=5&queue=competitive": {
            "History": [{"MatchID": "deferred"}],
        },
    })
    cache = ValorantEnrichmentCache()
    cache._put("rank", "owner", None, 60)
    assert cache.overall(cast(ValorantClient, client), "owner", RequestBudget(remaining=1)) is None
    assert cache._stats_pending("owner")
    assert cache._get("overall_pending", "owner") == (True, True)


def test_bridge_only_accepts_boolean_progress_for_visible_players() -> None:
    rows = _match_teams([{"players": [
        {"name": "Visible#EUW", "statsLoading": True},
        {"name": "Complete#EUW", "statsLoading": False},
        {"name": "Hidden", "hidden": True, "statsLoading": True},
        {"name": "Invalid#EUW", "statsLoading": "true"},
    ]}])[0]["players"]
    assert rows[0]["statsLoading"] is True
    assert rows[1]["statsLoading"] is False
    assert "statsLoading" not in rows[2]
    assert "statsLoading" not in rows[3]

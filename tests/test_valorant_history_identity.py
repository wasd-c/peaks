from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from peaks.adapters.riot.client import RiotClientUnavailable
from peaks.adapters.riot.valorant import ValorantClient, ValorantMatchSummary, parse_match_details
from peaks.adapters.riot.valorant_enrichment import (
    CompletedMatch,
    RequestBudget,
    ValorantEnrichmentCache,
)


class HistoryHTTP:
    def __init__(self, pages: dict[int, list[str]] | None = None) -> None:
        self.pages = pages or {0: ["recent"]}
        self.calls: list[str] = []
        self.name_calls: list[list[str]] = []
        self.name_failures = 0
        self.placeholder: str | None = None

    def get_json(self, endpoint: str) -> Any:
        self.calls.append(endpoint)
        if endpoint.startswith("/match-history/v1/history/owner?"):
            offset = int(endpoint.split("startIndex=", 1)[1].split("&", 1)[0])
            return {"History": [{"MatchID": match_id} for match_id in self.pages.get(offset, [])]}
        if endpoint.startswith("/match-details/v1/matches/"):
            match_id = endpoint.rsplit("/", 1)[1]
            return {
                "matchInfo": {"matchId": match_id, "isCompleted": True},
                "players": [{
                    "subject": "owner",
                    "teamId": "Blue",
                    "isIncognito": True,
                    "displayName": self.placeholder,
                }],
                "teams": [{"teamId": "Blue"}],
            }
        raise RiotClientUnavailable("Not available")

    def put_json(self, service: str, endpoint: str, subjects: list[str]) -> Any:
        assert service == "pd" and endpoint == "/name-service/v2/players"
        self.name_calls.append(subjects)
        if len(self.name_calls) <= self.name_failures:
            raise RiotClientUnavailable("Temporary name lookup failure")
        return [{"Subject": subject, "GameName": "Resolved", "TagLine": "EUW"} for subject in subjects]


def make_client(http: HistoryHTTP) -> ValorantClient:
    return ValorantClient(http, "owner")  # type: ignore[arg-type]


@pytest.mark.parametrize("placeholder", ["Hidden player", "Hidden player 3", "Skye", "Player 1", "#EUW", "Name#"])
def test_completed_display_placeholders_do_not_suppress_authenticated_lookup(placeholder: str) -> None:
    http = HistoryHTTP()
    http.placeholder = placeholder
    result = make_client(http).match_history()[0]
    assert http.name_calls == [["owner"]]
    player = result.teams[0].players[0]
    assert player.riot_id == "Resolved#EUW"
    assert player.hidden is False


def test_temporary_completed_name_failure_retries_then_repairs_cached_report() -> None:
    now = [0.0]
    cache = ValorantEnrichmentCache(clock=lambda: now[0])
    http = HistoryHTTP()
    http.name_failures = 1
    client = make_client(http)
    fallback = ValorantMatchSummary("recent")

    def report() -> CompletedMatch:
        result = cache.completed(client, fallback, RequestBudget(), resolve_names=True)
        assert result is not None
        return result

    first = report()
    assert first.summary.teams[0].players[0].riot_id is None
    assert cache.identity_pending(first)
    now[0] = 14
    assert cache.identity_pending(report())
    assert len(http.name_calls) == 1
    now[0] = 15
    resolved = report()
    assert resolved.summary.teams[0].players[0].riot_id == "Resolved#EUW"
    assert not cache.identity_pending(resolved)
    assert len(http.name_calls) == 2
    assert http.calls.count("/match-details/v1/matches/recent") == 1


def test_failed_completed_names_stop_pending_after_three_attempts() -> None:
    now = [0.0]
    cache = ValorantEnrichmentCache(clock=lambda: now[0])
    http = HistoryHTTP()
    http.name_failures = 10
    client = make_client(http)
    for timestamp, pending in [(0, True), (15, True), (30, False), (45, False)]:
        now[0] = timestamp
        result = cache.completed(client, ValorantMatchSummary("recent"), RequestBudget(), resolve_names=True)
        assert result is not None
        assert cache.identity_pending(result) is pending
        assert result.summary.teams[0].players[0].riot_id is None
        assert result.summary.teams[0].players[0].hidden is False
    assert len(http.name_calls) == 3


def test_names_deferred_by_request_budget_remain_pending_until_a_later_refresh() -> None:
    cache = ValorantEnrichmentCache()
    http = HistoryHTTP()
    client = make_client(http)
    fallback = ValorantMatchSummary("recent")
    first = cache.completed(client, fallback, RequestBudget(remaining=1), resolve_names=True)
    assert first is not None and cache.identity_pending(first)
    assert http.name_calls == []
    second = cache.completed(client, fallback, RequestBudget(), resolve_names=True)
    assert second is not None and not cache.identity_pending(second)
    assert second.summary.teams[0].players[0].riot_id == "Resolved#EUW"


@pytest.mark.parametrize("old_name", ["Hidden player 2", "Known#EUW"])
def test_legacy_completed_cache_drops_live_hidden_flag_without_inventing_a_name(old_name: str) -> None:
    http = HistoryHTTP()
    http.name_failures = 10
    client = make_client(http)
    cache = ValorantEnrichmentCache()
    payload = http.get_json("/match-details/v1/matches/recent")
    summary = parse_match_details(payload, puuid="owner", fallback=ValorantMatchSummary("recent"))
    player = replace(summary.teams[0].players[0], hidden=True, riot_id=old_name)
    summary = replace(summary, teams=(replace(summary.teams[0], players=(player,)),))
    cache._put("match", "recent", CompletedMatch(summary, (("owner", player),)), 300)

    result = cache.completed(client, ValorantMatchSummary("recent"), RequestBudget(), resolve_names=True)
    assert result is not None
    repaired = result.summary.teams[0].players[0]
    assert repaired.hidden is False
    assert repaired.riot_id == (old_name if old_name == "Known#EUW" else None)
    assert cache.identity_pending(result) is (old_name != "Known#EUW")
    assert len(http.name_calls) == (0 if old_name == "Known#EUW" else 1)


def test_older_report_is_fetched_only_after_membership_in_own_history() -> None:
    recent = [f"recent-{number}" for number in range(20)]
    http = HistoryHTTP({0: recent, 20: ["older-other", "selected"]})
    client = make_client(http)
    client.priority_match_id = "selected"
    result = client.match_history()
    assert [match.match_id for match in result] == [*recent, "selected"]
    assert http.calls[:2] == [
        "/match-history/v1/history/owner?startIndex=0&endIndex=20",
        "/match-history/v1/history/owner?startIndex=20&endIndex=40",
    ]
    assert "/match-details/v1/matches/selected" in http.calls
    assert "/match-details/v1/matches/older-other" not in http.calls


def test_unknown_priority_stops_after_five_pages_without_fetching_arbitrary_details() -> None:
    http = HistoryHTTP({offset: [f"match-{index}" for index in range(offset, offset + 20)] for offset in range(0, 120, 20)})
    client = make_client(http)
    client.priority_match_id = "not-in-owned-history"
    result = client.match_history()
    assert len(result) == 20
    history_calls = [path for path in http.calls if path.startswith("/match-history/")]
    assert len(history_calls) == 5
    assert history_calls[-1].endswith("startIndex=80&endIndex=100")
    assert all("not-in-owned-history" not in path for path in http.calls)


def test_repeated_history_page_stops_pagination_and_open_report_reuses_authorization() -> None:
    recent = [f"recent-{number}" for number in range(20)]
    http = HistoryHTTP({0: recent, 20: recent, 40: ["selected"]})
    client = make_client(http)
    client.priority_match_id = "selected"
    assert len(client.match_history()) == 20
    assert not any("startIndex=40" in path for path in http.calls)

    http.pages[20] = ["selected"]
    client.enrichment = ValorantEnrichmentCache()
    client.match_history()
    http.calls.clear()
    client.match_history()
    assert "/match-history/v1/history/owner?startIndex=20&endIndex=40" not in http.calls
    assert client.enrichment.owned_history_match("selected") is not None

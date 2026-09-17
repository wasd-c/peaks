from __future__ import annotations

from typing import Any

import pytest

from peaks.adapters.riot.client import RiotClientUnavailable
from peaks.adapters.riot.valorant import ValorantClient, ValorantMatchSummary
from peaks.adapters.riot.valorant_enrichment import RequestBudget, ValorantEnrichmentCache


class ProfileHTTP:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.name_batches: list[tuple[str, ...]] = []
        self.fail: set[str] = set()
        self.history_ids = ["shared-match"]
        self.detail_override: object = None

    def get_json(self, endpoint: str) -> Any:
        self.calls.append(endpoint)
        if any(fragment in endpoint for fragment in self.fail):
            raise RiotClientUnavailable("Unavailable")
        if endpoint == "/content-service/v3/content":
            return {"Seasons": [
                {"ID": "current-act", "Type": "act", "Name": "V26:A5", "IsActive": True},
                {"ID": "peak-act", "Type": "act", "Name": "V26:A3"},
            ]}
        if endpoint.startswith("/mmr/v1/players/"):
            if "/competitiveupdates" in endpoint:
                return {"Matches": []}
            return {"QueueSkills": {"competitive": {"SeasonalInfoBySeasonID": {
                "current-act": {"CompetitiveTier": 23, "RankedRating": 66},
                "peak-act": {"CompetitiveTier": 25},
            }}}}
        if endpoint.startswith("/account-xp/v1/players/"):
            return {"Subject": "owner", "Progress": {"Level": 555}}
        if endpoint.startswith("/match-history/v1/history/"):
            return {"History": [{"MatchID": match_id} for match_id in self.history_ids]}
        if endpoint.startswith("/match-details/v1/matches/"):
            if self.detail_override is not None:
                return self.detail_override
            return self.detail(endpoint.rsplit("/", 1)[1])
        raise RiotClientUnavailable("Not available")

    @staticmethod
    def detail(match_id: str) -> dict[str, Any]:
        return {
            "matchInfo": {"matchId": match_id, "isCompleted": True},
            "players": [
                {"subject": "owner", "teamId": "Blue", "accountLevel": 12,
                 "stats": {"kills": 9, "deaths": 18, "assists": 2}},
                {"subject": "target", "teamId": "Red", "accountLevel": 181,
                 "isIncognito": True, "stats": {"kills": 24, "deaths": 15, "assists": 4}},
            ],
            "teams": [
                {"teamId": "Blue", "roundsWon": 13, "won": True},
                {"teamId": "Red", "roundsWon": 9, "won": False},
            ],
        }

    def put_json(self, service: str, endpoint: str, subjects: list[str]) -> Any:
        assert service == "pd" and endpoint == "/name-service/v2/players"
        self.calls.append(endpoint)
        self.name_batches.append(tuple(subjects))
        if "names" in self.fail:
            raise RiotClientUnavailable("Unavailable")
        return [{"Subject": subject, "GameName": subject.title(), "TagLine": "EUW"} for subject in subjects]


def client_for(http: ProfileHTTP) -> ValorantClient:
    return ValorantClient(http, "owner")  # type: ignore[arg-type]


def test_search_reads_target_rank_level_and_history_without_changing_owner_perspective() -> None:
    http = ProfileHTTP()
    client = client_for(http)
    cache = ValorantEnrichmentCache()
    client.enrichment = cache
    cached_owner = cache.completed(client, ValorantMatchSummary("shared-match"), RequestBudget())
    assert cached_owner is not None and cached_owner.summary.result == "win"
    profile = client.player_profile("target")
    assert profile is not None and profile.rank is not None
    assert (profile.rank.name, profile.rank.rr) == ("Ascendant 3", 66)
    assert (profile.rank.peak_name, profile.rank.peak_season) == ("Immortal 2", "V26:A3")
    assert profile.level == 181
    assert client.puuid == "owner"
    match = profile.matches[0]
    assert (match.result, match.own_score, match.opponent_score) == ("loss", 9, 13)
    searched = next(player for team in match.teams for player in team.players if player.self)
    assert searched.riot_id == "Target#EUW"
    assert (searched.kills, searched.deaths, searched.assists) == (24, 15, 4)
    assert not searched.hidden and not searched.stats_loading and not match.enrichment_pending
    assert not any("account-xp" in call for call in http.calls)
    assert cache.completed(client, ValorantMatchSummary("shared-match"), RequestBudget()) is cached_owner
    assert not cache.owned_history_match("shared-match")


def test_shared_participant_names_are_batched_once_across_searched_matches() -> None:
    http = ProfileHTTP()
    http.history_ids = ["first", "second", "third"]
    profile = client_for(http).player_profile("target")
    assert profile is not None and len(profile.matches) == 3
    assert http.name_batches == [("owner", "target")]
    assert all(player.riot_id for match in profile.matches for team in match.teams for player in team.players)


@pytest.mark.parametrize("failure", ["/mmr/", "/match-history/", "/match-details/", "names"])
def test_independent_lookup_failures_preserve_available_search_data(failure: str) -> None:
    http = ProfileHTTP()
    http.fail.add(failure)
    profile = client_for(http).player_profile("target")
    assert profile is not None
    if failure == "/mmr/":
        assert profile.rank is None and profile.level == 181 and profile.matches[0].result == "loss"
    elif failure == "/match-history/":
        assert profile.rank is not None and profile.matches == () and profile.level is None
    elif failure == "/match-details/":
        assert profile.rank is not None and profile.matches[0].teams == () and profile.level is None
    else:
        assert profile.rank is not None and profile.level == 181
        assert all(player.riot_id is None for team in profile.matches[0].teams for player in team.players)
        assert profile.matches[0].result == "loss"


def test_no_available_valorant_evidence_returns_none() -> None:
    http = ProfileHTTP()
    http.fail.add("/mmr/")
    http.history_ids = []
    assert client_for(http).player_profile("target") is None


def test_own_search_can_read_current_xp_and_prefer_it_to_old_match_level() -> None:
    http = ProfileHTTP()
    profile = client_for(http).player_profile("owner")
    assert profile is not None and profile.level == 555
    assert profile.matches[0].result == "win"
    assert "/account-xp/v1/players/owner" in http.calls


@pytest.mark.parametrize("target", ["", "bad/id", "bad\nidentity", " target", "a" * 129])
def test_invalid_target_never_schedules_requests(target: str) -> None:
    http = ProfileHTTP()
    assert client_for(http).player_profile(target) is None
    assert http.calls == []


def test_history_and_requests_are_bounded_and_duplicate_matches_are_not_refetched() -> None:
    http = ProfileHTTP()
    http.history_ids = ["duplicate", "duplicate", *[f"match-{index}" for index in range(40)]]
    profile = client_for(http).player_profile("target", limit=500)
    assert profile is not None and len(profile.matches) == 9
    assert "/match-history/v1/history/target?startIndex=0&endIndex=10" in http.calls
    assert http.calls.count("/match-details/v1/matches/duplicate") == 1
    assert len(http.calls) <= 24


@pytest.mark.parametrize("info", [
    {"matchId": "wrong-match", "isCompleted": True},
    {"matchId": "shared-match", "isCompleted": False},
])
def test_mismatched_or_live_details_do_not_expose_roster_data(info: dict[str, Any]) -> None:
    http = ProfileHTTP()
    http.detail_override = {**http.detail("shared-match"), "matchInfo": info}
    profile = client_for(http).player_profile("target")
    assert profile is not None and profile.matches[0].teams == ()
    assert profile.level is None and http.name_batches == []


def test_elapsed_request_budget_stops_scheduling_more_history_work() -> None:
    http = ProfileHTTP()
    http.history_ids = [f"match-{index}" for index in range(10)]
    now = [0.0]

    def clock() -> float:
        now[0] += 1
        return now[0]

    client = client_for(http)
    client.enrichment = ValorantEnrichmentCache(clock=clock)
    profile = client.player_profile("target")
    assert profile is not None and profile.rank is not None
    assert len(http.calls) < 10
    assert not any(match.enrichment_pending for match in profile.matches)

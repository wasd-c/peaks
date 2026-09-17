from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from peaks.adapters.riot.client import RiotClientUnavailable
from peaks.adapters.riot.valorant import (
    ValorantClient,
    ValorantMatchPlayer,
    ValorantMatchSummary,
    ValorantRemoteHTTP,
    parse_coregame,
    parse_match_details,
    parse_rank,
)
from peaks.adapters.riot.valorant_enrichment import (
    RequestBudget,
    SeasonCatalog,
    ValorantEnrichmentCache,
    aggregate_recent_stats,
    parse_season_catalog,
    rank_presentation,
)
from peaks.bridge import _match_teams


class PayloadHTTP:
    def __init__(self, payloads: dict[str, Any]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []
        self.name_requests: list[list[str]] = []

    def get_json(self, endpoint: str) -> Any:
        self.calls.append(endpoint)
        if endpoint not in self.payloads:
            raise RiotClientUnavailable("Unavailable")
        return self.payloads[endpoint]

    def put_json(self, service: str, endpoint: str, subjects: list[str]) -> Any:
        assert service == "pd" and endpoint == "/name-service/v2/players"
        self.name_requests.append(subjects)
        return [
            {"Subject": subject, "GameName": "Resolved", "TagLine": "EUW"} for subject in subjects
        ]


def client_for(
    payloads: dict[str, Any],
) -> tuple[ValorantClient, PayloadHTTP, ValorantEnrichmentCache]:
    http = PayloadHTTP(payloads)
    client = ValorantClient(http, "owner")  # type: ignore[arg-type]
    cache = ValorantEnrichmentCache()
    client.enrichment = cache
    return client, http, cache


def test_catalog_uses_dates_and_names_for_exact_episode_and_year_labels() -> None:
    rows = [
        {
            "ID": "modern-act",
            "Name": "ACT VI",
            "Type": "act",
            "StartTime": "2025-10-01T00:00:00Z",
            "EndTime": "2026-01-01T00:00:00Z",
        },
        {
            "ID": "old-act",
            "Name": "ACT III",
            "Type": "act",
            "StartTime": "2022-10-01T00:00:00Z",
            "EndTime": "2023-01-01T00:00:00Z",
        },
        {
            "ID": "modern",
            "Name": "EPISODE V25",
            "Type": "episode",
            "StartTime": "2025-01-01T00:00:00Z",
            "EndTime": "2026-01-01T00:00:00Z",
        },
        {
            "ID": "old",
            "Name": "EPISODE 5",
            "Type": "episode",
            "StartTime": "2022-07-01T00:00:00Z",
            "EndTime": "2023-01-01T00:00:00Z",
        },
        {"ID": "current", "Name": "V26 ACT I", "Type": "act", "IsActive": True},
        {"ID": "unknown", "Name": "ACT I", "Type": "act"},
    ]
    catalog = parse_season_catalog({"Seasons": rows})
    assert catalog.labels == {"modern-act": "V25:A6", "old-act": "E5:A3", "current": "V26:A1"}
    assert catalog.active_id == "current"
    assert parse_season_catalog({"Seasons": list(reversed(rows))}) == catalog


def test_career_peak_normalizes_every_old_tier_before_comparing_wins() -> None:
    payload = {
        "QueueSkills": {
            "competitive": {
                "SeasonalInfoBySeasonID": {
                    "current": {"CompetitiveTier": 26, "WinsByTier": {"26": 8}},
                    "old": {"CompetitiveTier": 21, "WinsByTier": {"24": 1, "999": 30}},
                    "noise": {"CompetitiveTier": 999, "WinsByTier": {"27": 0}},
                }
            }
        }
    }
    rank = parse_rank(payload, "current", season_labels={"old": "E4:A3", "current": "V26:A1"})
    assert rank.name == "Immortal 3"
    assert (rank.peak_tier, rank.peak_name, rank.season_id) == (27, "Radiant", "old")


def test_unresolved_current_season_uses_updates_without_losing_career_peak() -> None:
    client, http, cache = client_for(
        {
            "/mmr/v1/players/visible": {
                "QueueSkills": {
                    "competitive": {
                        "SeasonalInfoBySeasonID": {
                            "old": {"CompetitiveTier": 27},
                            "new": {"CompetitiveTier": 19},
                        }
                    }
                }
            },
            "/mmr/v1/players/visible/competitiveupdates?startIndex=0&endIndex=20&queue=competitive": {
                "Matches": [{"SeasonID": "new", "TierAfterUpdate": 19}]
            },
        }
    )
    rank = cache.profile(client, "visible", SeasonCatalog(), RequestBudget())
    assert rank is not None
    assert (rank.name, rank.peak_name, rank.current_available) == ("Diamond 2", "Radiant", True)
    assert len(http.calls) == 2
    cache.profile(client, "visible", SeasonCatalog(), RequestBudget())
    assert len(http.calls) == 2


def test_recent_rank_fallback_does_not_claim_a_career_peak() -> None:
    client, _, cache = client_for(
        {
            "/mmr/v1/players/visible/competitiveupdates?startIndex=0&endIndex=20&queue=competitive": {
                "Matches": [{"SeasonID": "new", "TierAfterUpdate": 19, "TierBeforeUpdate": 27}]
            },
        }
    )
    rank = cache.profile(client, "visible", SeasonCatalog(active_id="new"), RequestBudget())
    assert rank is not None
    assert rank_presentation(rank) == {"currentRank": "Diamond 2", "currentRankTier": 19}


def test_missing_current_data_remains_absent_instead_of_false_unranked() -> None:
    client, _, cache = client_for(
        {
            "/mmr/v1/players/visible": {
                "QueueSkills": {
                    "competitive": {
                        "SeasonalInfoBySeasonID": {
                            "old": {"CompetitiveTier": 27},
                            "new": {"CompetitiveTier": 19},
                        }
                    }
                }
            },
        }
    )
    result = rank_presentation(cache.profile(client, "visible", SeasonCatalog(), RequestBudget()))
    assert result == {"peakRank": "Radiant", "peakRankTier": 27}


def test_missing_season_metadata_does_not_mislabel_legacy_radiant_as_immortal() -> None:
    client, _, cache = client_for(
        {
            "/mmr/v1/players/visible": {
                "QueueSkills": {
                    "competitive": {
                        "SeasonalInfoBySeasonID": {
                            "current": {"CompetitiveTier": 19},
                            "unknown-old-act": {"WinsByTier": {"24": 3}},
                        }
                    }
                }
            }
        }
    )
    result = rank_presentation(
        cache.profile(client, "visible", SeasonCatalog(active_id="current"), RequestBudget())
    )
    assert result == {"currentRank": "Diamond 2", "currentRankTier": 19}


def detail_payload(
    match_id: str, subject: str = "owner", *, completed: bool = True
) -> dict[str, Any]:
    return {
        "matchInfo": {"matchId": match_id, "isCompleted": completed},
        "players": [
            {
                "subject": subject,
                "teamId": "Blue",
                "isIncognito": True,
                "partyId": "private-party-uuid",
                "accountLevel": 245,
                "stats": {
                    "kills": 12,
                    "deaths": 8,
                    "assists": 4,
                    "score": 3000,
                    "roundsPlayed": 20,
                },
            },
        ],
        "teams": [{"teamId": "Blue", "won": True, "roundsWon": 13}],
    }


def test_report_hydrates_completed_names_even_if_aggregate_cached_it_first() -> None:
    client, http, cache = client_for(
        {"/match-details/v1/matches/match-1": detail_payload("match-1")}
    )
    fallback = ValorantMatchSummary("match-1")
    aggregate = cache.completed(client, fallback, RequestBudget())
    assert aggregate is not None and aggregate.summary.teams[0].players[0].riot_id is None
    report = cache.completed(client, fallback, RequestBudget(), resolve_names=True)
    assert report is not None
    player = report.summary.teams[0].players[0]
    assert player.riot_id == "Resolved#EUW" and player.hidden is False
    assert player.party_id == "party-1" and player.account_level == 245
    assert "private-party-uuid" not in repr(report.summary)
    assert "owner" not in repr(report.summary)
    assert http.calls == ["/match-details/v1/matches/match-1"]
    assert http.name_requests == [["owner"]]
    cache.completed(client, fallback, RequestBudget(), resolve_names=True)
    assert http.name_requests == [["owner"]]


def test_unfinished_details_never_use_completed_identity_resolution() -> None:
    client, http, cache = client_for(
        {"/match-details/v1/matches/live": detail_payload("live", completed=False)}
    )
    fallback = ValorantMatchSummary("live")
    assert cache.completed(client, fallback, RequestBudget(), resolve_names=True) is None
    assert http.name_requests == []
    assert (
        parse_match_details(
            detail_payload("live", completed=False), puuid="owner", fallback=fallback
        )
        == fallback
    )


def test_live_level_obeys_hide_level_and_incognito_is_unchanged() -> None:
    live = parse_coregame(
        {
            "ID": "live",
            "Players": [
                {
                    "Subject": "hidden",
                    "PlayerIdentity": {
                        "Incognito": True,
                        "HideAccountLevel": True,
                        "AccountLevel": 240,
                    },
                },
                {"Subject": "visible", "PlayerIdentity": {"AccountLevel": 120}},
            ],
        }
    )
    assert live is not None
    assert live.players[0].incognito and live.players[0].account_level is None
    assert live.players[1].account_level == 120
    assert all(player.party_id is None for player in live.players)


def test_overall_aggregates_only_observed_recent_samples_without_inventing_missing_stats() -> None:
    sample = ValorantMatchPlayer(
        kills=12,
        deaths=8,
        assists=4,
        rounds_played=20,
        combat_score=3000,
        headshots=8,
        bodyshots=20,
        legshots=2,
    )
    stats = aggregate_recent_stats([(sample, True), (replace(sample, headshots=None), False)])
    assert stats is not None
    assert stats["kills"] == 24 and stats["combatScore"] == 6000 and stats["roundsPlayed"] == 40
    assert stats["matchesPlayed"] == 2 and stats["wins"] == 1
    assert stats["scope"] == "recent" and stats["source"] == "authenticated-client-history"
    assert stats["recentKda"] == [{"kills": 12, "deaths": 8}, {"kills": 12, "deaths": 8}]
    assert "headshots" not in stats and "damage" not in stats


def test_request_budget_stops_new_queries_and_failed_profiles_back_off() -> None:
    now = [0.0]
    budget = RequestBudget(remaining=2, clock=lambda: now[0], seconds=3)
    assert budget.take()
    now[0] = 3
    assert not budget.take()
    client, http, cache = client_for({})
    cache.profile(client, "visible", SeasonCatalog(), RequestBudget(remaining=1))
    assert http.calls == ["/mmr/v1/players/visible"]
    cache.profile(client, "visible", SeasonCatalog(), RequestBudget())
    assert len(http.calls) == 3  # Deferred fallback gets another chance.
    cache.profile(client, "visible", SeasonCatalog(), RequestBudget())
    assert len(http.calls) == 3  # Fully attempted failures back off.


def test_pending_roster_finishes_across_bounded_refreshes_and_negative_lookups_resolve() -> None:
    payload = detail_payload("selected", "one")
    for subject in ("two", "three", "four", "five"):
        payload["players"].append({**payload["players"][0], "subject": subject})
    payloads = {"/match-details/v1/matches/selected": payload}
    client, http, cache = client_for(payloads)
    matches = (ValorantMatchSummary("selected"),)
    # Missing service data is a resolved negative result, rather than an
    # indefinite loading state; only two recent histories are attempted/run.
    first = cache.match_history(client, matches, priority_match_id="selected")[0]
    assert first.enrichment_pending
    second = cache.match_history(client, matches, priority_match_id="selected")[0]
    assert second.enrichment_pending
    third = cache.match_history(client, matches, priority_match_id="selected")[0]
    assert not third.enrichment_pending
    assert len([path for path in http.calls if path.startswith("/match-history/")]) == 5


def test_priority_can_only_reorder_owned_history_and_rank_requests_precede_overall() -> None:
    payloads: dict[str, Any] = {
        "/match-details/v1/matches/newest": detail_payload("newest", "new-player"),
        "/match-details/v1/matches/selected": detail_payload("selected", "selected-player"),
    }
    for subject in ("new-player", "selected-player"):
        payloads[f"/mmr/v1/players/{subject}"] = {
            "QueueSkills": {
                "competitive": {"SeasonalInfoBySeasonID": {"act": {"CompetitiveTier": 20}}}
            }
        }
    client, http, cache = client_for(payloads)
    result = cache.match_history(
        client,
        (ValorantMatchSummary("newest"), ValorantMatchSummary("selected")),
        priority_match_id="selected",
    )
    assert [row.match_id for row in result] == ["newest", "selected"]
    assert http.calls[0] == "/match-details/v1/matches/selected"
    ranks = [index for index, path in enumerate(http.calls) if path.startswith("/mmr/")]
    histories = [
        index for index, path in enumerate(http.calls) if path.startswith("/match-history/")
    ]
    assert max(ranks) < min(histories)
    http.calls.clear()
    cache.match_history(client, (ValorantMatchSummary("newest"),), priority_match_id="unauthorized")
    assert all("unauthorized" not in path for path in http.calls)


def test_bridge_sanitizes_enrichment_and_keeps_overall_separate_from_match_stats() -> None:
    row = {
        "riotId": "Player#EUW",
        "stats": {"kills": 2},
        "currentRank": "Diamond 1",
        "currentRankTier": 18,
        "peakRank": "Radiant",
        "peakRankTier": 27,
        "peakRankSeason": "E4:A3",
        "accountLevel": 20,
        "partyId": "party-1",
        "overallStats": {
            "kills": 60,
            "matchesPlayed": 5,
            "wins": 3,
            "scope": "recent",
            "source": "authenticated-client-history",
            "token": "secret",
        },
    }
    parsed = _match_teams([{"players": [row]}])[0]["players"][0]
    assert parsed["stats"] == {"kills": 2}
    assert parsed["overallStats"]["kills"] == 60
    assert "secret" not in repr(parsed)
    assert parsed["peakRankSeason"] == "E4:A3"
    rejected = _match_teams(
        [
            {
                "players": [
                    {
                        **row,
                        "hidden": True,
                        "partyId": "private-uuid",
                        "accountLevel": True,
                        "peakRankSeason": "raw-uuid",
                    }
                ]
            }
        ]
    )[0]["players"][0]
    assert not {"overallStats", "partyId", "accountLevel", "peakRankSeason"} & rejected.keys()
    assert rejected["riotId"] is None


def test_shared_transport_refuses_to_send_credentials_to_untrusted_hosts() -> None:
    class Session:
        def request(self, *args: Any, **kwargs: Any) -> Any:
            pytest.fail("No network request should be attempted")

    for pd_url in (
        "https://example.com",
        "https://pd.eu.a.pvp.net.evil.example",
        "https://pd.eu.a.pvp.net/path",
    ):
        remote = ValorantRemoteHTTP(
            pd_url=pd_url,
            glz_url="https://glz-eu-1.eu.a.pvp.net",
            headers={"Authorization": "never-send"},
            session=Session(),
        )
        with pytest.raises(RiotClientUnavailable):
            remote.get_json("shared", "/content-service/v3/content")


def test_bridge_recent_kda_requires_exact_sample_count_and_consistent_totals() -> None:
    overall = {
        "kills": 9,
        "deaths": 25,
        "matchesPlayed": 2,
        "scope": "recent",
        "source": "authenticated-client-history",
        "recentKda": [{"kills": 4, "deaths": 12}, {"kills": 5, "deaths": 13}],
    }

    def project(data: dict[str, Any]) -> dict[str, Any]:
        return _match_teams([{"players": [{"overallStats": data}]}])[0]["players"][0][
            "overallStats"
        ]

    assert project(overall)["recentKda"] == overall["recentKda"]
    assert "recentKda" not in project({**overall, "kills": 10})
    assert "recentKda" not in project({**overall, "matchesPlayed": 3})
    assert "recentKda" not in project(
        {**overall, "recentKda": [{"kills": True, "deaths": 12}, {"kills": 5, "deaths": 13}]}
    )


def test_unresolvable_subject_rows_do_not_create_permanent_pending_state() -> None:
    payload = detail_payload("anonymous")
    del payload["players"][0]["subject"]
    client, _, cache = client_for({"/match-details/v1/matches/anonymous": payload})
    result = cache.match_history(client, (ValorantMatchSummary("anonymous"),))[0]
    assert result.teams[0].players
    assert not result.enrichment_pending


def test_failed_history_retry_clears_previous_partial_pending_state() -> None:
    client, _, cache = client_for({})
    cache._put("overall_pending", "owner", True, 300)
    assert cache.overall(client, "owner", RequestBudget()) is None
    assert cache._get("overall_pending", "owner") == (True, False)

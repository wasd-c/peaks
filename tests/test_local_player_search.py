from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.riot.client import RiotClientError, RiotClientUnavailable
from peaks.adapters.riot.league import LeagueClient, parse_summoner_profile
from peaks.application.runtime import RiotSearchService
from peaks.bridge import Bridge


class FakeLocalHTTP:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self.closed = False

    def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, object] | None = None,
    ) -> object:
        self.calls.append((endpoint, params))
        return self.responses[endpoint]

    def close(self) -> None:
        self.closed = True


def test_local_league_lookup_is_region_bound_and_uses_an_exact_riot_id() -> None:
    local = FakeLocalHTTP(
        {
            "/riotclient/region-locale": {"region": "euw1"},
            "/lol-summoner/v1/summoners": {
                "puuid": "resolved-puuid",
                "gameName": "Peak Player",
                "tagLine": "EUW",
                "summonerLevel": 314,
            },
        }
    )
    client = LeagueClient(lcu_http=local)  # type: ignore[arg-type]

    profile = client.lookup_summoner("Peak Player", "EUW", expected_region="EUW")

    assert profile is not None
    assert profile.riot_id == "Peak Player#EUW"
    assert profile.level == 314
    assert local.calls == [
        ("/riotclient/region-locale", None),
        ("/lol-summoner/v1/summoners", {"name": "Peak Player#EUW"}),
    ]


def test_local_league_lookup_reports_a_different_selected_shard() -> None:
    local = FakeLocalHTTP({"/riotclient/region-locale": {"region": "na1"}})
    client = LeagueClient(lcu_http=local)  # type: ignore[arg-type]

    with pytest.raises(RiotClientUnavailable, match="another region"):
        client.lookup_summoner("Peak", "EUW", expected_region="EUW")
    assert local.calls == [("/riotclient/region-locale", None)]


def test_local_league_lookup_keeps_a_real_404_as_not_found() -> None:
    class NotFoundHTTP(FakeLocalHTTP):
        def get_json(
            self,
            endpoint: str,
            *,
            params: dict[str, object] | None = None,
        ) -> object:
            self.calls.append((endpoint, params))
            if endpoint == "/lol-summoner/v1/summoners":
                raise RiotClientError("not found", status_code=404)
            return self.responses[endpoint]

    local = NotFoundHTTP({"/riotclient/region-locale": {"region": "euw1"}})
    client = LeagueClient(lcu_http=local)  # type: ignore[arg-type]

    assert client.lookup_summoner("Missing", "EUW", expected_region="EUW") is None


def test_search_without_a_verified_local_client_returns_actionable_error() -> None:
    service = RiotSearchService(local_client_factory=lambda: LeagueClient(), riot_client_factory=lambda: SimpleNamespace(), valorant_profile_reader=lambda _: None)

    with pytest.raises(RuntimeError, match=r"LOCAL_RIOT_CLIENT_UNAVAILABLE.*EUW"):
        service.search_player("Peak#EUW", region="EUW", game="League of Legends")


def test_summoner_lookup_rejects_an_lcu_fuzzy_name_match() -> None:
    assert (
        parse_summoner_profile(
            {
                "puuid": "wrong-puuid",
                "gameName": "Different Player",
                "tagLine": "EUW",
                "summonerLevel": 20,
            },
            expected_game_name="Peak",
            expected_tag_line="EUW",
        )
        is None
    )


def test_search_without_developer_key_returns_local_identity_and_level() -> None:
    class FakeLocalClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []
            self.closed = False

        def lookup_summoner(
            self,
            game_name: str,
            tag_line: str,
            *,
            expected_region: str,
        ) -> Any:
            self.calls.append((game_name, tag_line, expected_region))
            return SimpleNamespace(
                puuid="local-puuid",
                riot_id="Peak#EUW",
                level=202,
            )

        def close(self) -> None:
            self.closed = True

    local = FakeLocalClient()
    service = RiotSearchService(local_client_factory=lambda: local, valorant_profile_reader=lambda _: None)

    results = service.search_player(
        "Peak#EUW",
        region="EUW",
        game="League of Legends",
    )

    assert local.calls == [("Peak", "EUW", "EUW")]
    assert local.closed is True
    assert results[0]["riotId"] == "Peak#EUW"
    assert results[0]["level"] == 202
    assert results[0]["currentRank"] == "Rank unavailable"
    assert results[0]["ranks"] == []
    assert results[0]["lastUpdated"] == "Just now"


def test_bridge_search_calls_keyless_service_in_non_demo_mode() -> None:
    class FakeSearch:
        def search_player(self, query: str, *, region: str, game: str) -> list[dict[str, Any]]:
            assert (query, region, game) == ("Peak#EUW", "EUW", "VALORANT")
            return [
                {
                    "id": "local-puuid",
                    "riotId": "Peak#EUW",
                    "region": "EUW",
                    "games": ["VALORANT"],
                }
            ]

    bridge = Bridge.__new__(Bridge)
    bridge.demo = False
    bridge._locked = False
    bridge.history = []
    bridge._riot_search_service = FakeSearch()

    results = bridge.search({"query": "Peak#EUW", "region": "EUW", "game": "VALORANT"})

    assert results[0]["game"] == "VALORANT"
    assert bridge.history == ["Peak#EUW"]


def test_bridge_query_only_search_uses_automatic_region_and_all_games() -> None:
    class FakeSearch:
        def search_player(self, query: str, *, region: str, game: str) -> list[dict[str, Any]]:
            assert (query, region, game) == ("Peak#EUW", "", "all")
            return []

    bridge = Bridge.__new__(Bridge)
    bridge.demo = False
    bridge._locked = False
    bridge.history = []
    bridge._riot_search_service = FakeSearch()
    assert bridge.search({"query": "Peak#EUW"}) == []


def test_local_lookup_discovers_region_without_user_input() -> None:
    local = FakeLocalHTTP({
        "/riotclient/region-locale": {"region": "na1"},
        "/lol-summoner/v1/summoners": {"puuid": "target-puuid", "gameName": "Peak", "tagLine": "TAG"},
    })
    result = LeagueClient(lcu_http=local).lookup_summoner("Peak", "TAG")  # type: ignore[arg-type]
    assert result is not None and result.region == "NA"


def test_native_rank_endpoint_uses_resolved_puuid_as_one_path_component() -> None:
    endpoint = "/lol-ranked/v1/ranked-stats/a%2Fb%3Fq%3Dprivate"
    local = FakeLocalHTTP({endpoint: {"queues": []}})
    assert LeagueClient(lcu_http=local).ranked_stats("a/b?q=private") == ()  # type: ignore[arg-type]
    assert local.calls == [(endpoint, None)]

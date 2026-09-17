"""Fixture-backed tests for the documented/public provider boundary.

No test in this module contacts Riot or valorant-api.com.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from peaks.adapters.providers.riot_api import (
    AccountRouting,
    LeagueRank,
    RiotApiClient,
    RiotApiError,
    RiotApiTransportError,
    TftRank,
)
from peaks.adapters.providers.valorant_metadata import (
    UnsupportedValorantApiError,
    ValorantMetadataClient,
    ValorantOfficialProvider,
)


class FakeResponse:
    def __init__(self, payload: Any, *, status_code: int = 200, chunks: list[bytes] | None = None) -> None:
        self.status_code = status_code
        self._body = json.dumps(payload).encode()
        self._chunks = chunks
        self.headers = {"Content-Length": str(len(self._body))}
        self.closed = False

    @property
    def content(self) -> bytes:
        return self._body

    def iter_content(self, *, chunk_size: int) -> list[bytes]:
        del chunk_size
        return self._chunks if self._chunks is not None else [self._body]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self.trust_env = True

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def test_riot_id_resolves_via_account_v1_without_leaking_api_key() -> None:
    session = FakeSession(FakeResponse({"puuid": "puuid-1", "gameName": "Nora", "tagLine": "EUW"}))
    client = RiotApiClient("secret-api-key", session=session)

    account = client.get_account_by_riot_id("Nora Name", "EU#W", routing=AccountRouting.EUROPE)

    assert account.puuid == "puuid-1"
    url, kwargs = session.calls[0]
    assert url == "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/Nora%20Name/EU%23W"
    assert kwargs["headers"]["X-Riot-Token"] == "secret-api-key"
    assert "secret-api-key" not in repr(client)
    assert session.trust_env is False

    client.close()
    assert session.closed is True


def test_league_ranks_use_current_puuid_endpoint() -> None:
    session = FakeSession(
        FakeResponse(
            [
                {
                    "queueType": "RANKED_SOLO_5x5",
                    "tier": "DIAMOND",
                    "rank": "II",
                    "leaguePoints": 72,
                    "wins": 40,
                    "losses": 31,
                    "puuid": "puuid-1",
                }
            ]
        ),
    )
    client = RiotApiClient("user-key", session=session)

    ranks = client.get_league_ranks("puuid-1", routing="euw1")

    assert ranks == (
        LeagueRank(
            queue_type="RANKED_SOLO_5x5",
            tier="DIAMOND",
            rank="II",
            league_points=72,
            wins=40,
            losses=31,
            puuid="puuid-1",
        ),
    )
    assert session.calls[0][0] == (
        "https://euw1.api.riotgames.com/lol/league/v4/entries/by-puuid/puuid-1"
    )


def test_league_and_tft_match_history_are_bounded_and_queryable() -> None:
    session = FakeSession(
        FakeResponse(["EUW1_123", "EUW1_456"]),
        FakeResponse(["TFT9_123"]),
    )
    client = RiotApiClient("user-key", session=session)

    league = client.get_league_match_history(
        "puuid-1",
        routing="europe",
        start=2,
        count=2,
        start_time=100,
        end_time=200,
        queue=420,
        match_type="ranked",
    )
    tft = client.get_tft_match_history("puuid-1", routing="europe", count=1)

    assert league.match_ids == ("EUW1_123", "EUW1_456")
    assert tft.match_ids == ("TFT9_123",)
    assert session.calls[0][1]["params"] == {
        "start": 2,
        "count": 2,
        "startTime": 100,
        "endTime": 200,
        "queue": 420,
        "type": "ranked",
    }
    assert session.calls[0][0].endswith("/lol/match/v5/matches/by-puuid/puuid-1/ids")
    assert session.calls[1][0].endswith("/tft/match/v1/matches/by-puuid/puuid-1/ids")


def test_tft_rank_uses_documented_tft_endpoints() -> None:
    session = FakeSession(
        FakeResponse(
            [
                {
                    "queueType": "RANKED",
                    "tier": "MASTER",
                    "rank": "I",
                    "leaguePoints": 100,
                    "wins": 10,
                    "losses": 4,
                }
            ]
        ),
    )
    ranks = RiotApiClient("user-key", session=session).get_tft_ranks("puuid-1", routing="na1")

    assert isinstance(ranks[0], TftRank)
    assert ranks[0].tier == "MASTER"
    assert session.calls[0][0].endswith("/tft/league/v1/by-puuid/puuid-1")


def test_valorant_matchlist_uses_only_documented_regional_route() -> None:
    session = FakeSession(
        FakeResponse(
            {
                "matches": [
                    {"matchId": "val-1", "gameStartTimeMillis": 1234},
                    {"matchId": "val-2"},
                ]
            }
        )
    )

    history = RiotApiClient("user-key", session=session).get_valorant_match_history(
        "puuid-1", routing="americas"
    )

    assert history.match_ids == ("val-1", "val-2")
    assert history.matches[0].game_start_time_millis == 1234
    assert session.calls[0][0] == (
        "https://americas.api.riotgames.com/val/match/v1/matchlists/by-puuid/puuid-1"
    )


def test_http_errors_are_sanitized_and_retry_after_is_typed() -> None:
    response = FakeResponse({"message": "secret-api-key should not appear"}, status_code=429)
    response.headers["Retry-After"] = "3"
    session = FakeSession(response)

    with pytest.raises(RiotApiError) as raised:
        RiotApiClient("secret-api-key", session=session).get_puuid_by_riot_id("A", "B")

    assert raised.value.status_code == 429
    assert raised.value.retry_after_seconds == 3
    assert "secret-api-key" not in str(raised.value)


def test_response_size_is_limited_before_json_parsing() -> None:
    response = FakeResponse({"ok": True})
    response.headers["Content-Length"] = "999"
    with pytest.raises(RiotApiTransportError):
        RiotApiClient("key", session=FakeSession(response), max_response_bytes=10).get_puuid_by_riot_id(
            "A", "B"
        )


class MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.set_calls: list[tuple[str, float]] = []

    def get(self, key: str) -> object | None:
        return self.values.get(key)

    def set(self, key: str, value: object, ttl_seconds: float) -> None:
        self.values[key] = value
        self.set_calls.append((key, ttl_seconds))


def test_valorant_metadata_is_public_allowlisted_and_cacheable() -> None:
    cache = MemoryCache()
    session = FakeSession(
        FakeResponse(
            {
                "data": [
                    {
                        "uuid": "agent-1",
                        "displayName": "Astra",
                        "isPlayableCharacter": True,
                        "role": {"displayName": "Controller"},
                    }
                ]
            }
        )
    )
    client = ValorantMetadataClient(session=session, cache=cache, cache_ttl_seconds=60)

    agents = client.get_agent_assets(playable_only=True)
    again = client.get_agent_assets(playable_only=True)

    assert agents[0].display_name == "Astra"
    assert agents[0].role_name == "Controller"
    assert again == agents
    assert len(session.calls) == 1
    assert session.calls[0][0] == "https://valorant-api.com/v1/agents"
    assert cache.set_calls == [("valorant-api:/v1/agents", 60.0)]


def test_official_valorant_limitations_are_explicit_and_no_private_fallback() -> None:
    provider = ValorantOfficialProvider()

    assert provider.limitations.official_api_available is True
    assert provider.limitations.supports("match_history") is True
    assert provider.limitations.requires_production_key is True
    assert provider.limitations.requires_rso_opt_in is True
    assert "documents VAL-MATCH-V1" in provider.limitations.reason
    with pytest.raises(UnsupportedValorantApiError) as raised:
        provider.get_match_history("puuid-1")
    assert "production API/RSO" in raised.value.feature

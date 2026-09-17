"""Offline search integration across Riot identity and VALORANT profile sources."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.riot.league import LeagueSummonerProfile, parse_ranked_stats
from peaks.adapters.riot.player_lookup import RiotPlayerIdentity
from peaks.application.runtime import CurrentGameService, RiotSearchService
from peaks.bridge import Bridge

TARGET = "searched-player-puuid"


def profile_snapshot() -> dict[str, Any]:
    return {
        "region": "EU",
        "level": 200,
        "currentRank": "Ascendant 3",
        "peakRank": "Immortal 1",
        "peakRankSeason": "V26:A1",
        "ranks": [{"game": "valorant", "tier": "Ascendant 3", "rating": 45, "peak_tier": "Immortal 1"}],
        "matches": [{
            "match_id": "searched-player-match",
            "game": "valorant",
            "result": "win",
            "queue": "competitive",
            "map_name": "Ascent",
            "played_at": 1_789_000_000,
            "duration_seconds": 1_920,
            "kills": 24,
            "deaths": 15,
            "assists": 4,
            "metadata": {
                "score": "13:9",
                "teams": [{
                    "name": "Allies",
                    "score": 13,
                    "won": True,
                    "players": [{
                        "riotId": "Target#TAG",
                        "agent": "Waylay",
                        "self": True,
                        "hidden": False,
                        "stats": {"kills": 24, "deaths": 15, "assists": 4},
                    }],
                }, {
                    "name": "Enemies",
                    "score": 9,
                    "won": False,
                    "players": [{
                        "riotId": "Opponent#TAG",
                        "agent": "Skye",
                        "self": False,
                        "hidden": False,
                        "stats": {"kills": 15, "deaths": 24, "assists": 2},
                    }],
                }],
            },
        }],
    }


def alias_client() -> SimpleNamespace:
    return SimpleNamespace(
        lookup_player=lambda name, tag: RiotPlayerIdentity(TARGET, name, tag),
        close=lambda: None,
    )


@pytest.mark.parametrize("requested", ["all", "All games", "VALORANT"])
def test_alias_search_loads_the_resolved_players_valorant_profile(requested: str) -> None:
    calls: list[str] = []

    def read_profile(puuid: str) -> dict[str, Any]:
        calls.append(puuid)
        return profile_snapshot()

    service = RiotSearchService(
        local_client_factory=lambda: SimpleNamespace(),
        riot_client_factory=alias_client,
        valorant_profile_reader=read_profile,
    )
    player = Bridge._player(service.search_player("Target#TAG", game=requested)[0])

    assert calls == [TARGET]
    assert player["id"] == TARGET and player["puuid"] == TARGET
    assert player["riotId"] == "Target#TAG"
    assert player["game"] == "VALORANT"
    assert player["region"] == "EU"
    assert player["level"] == 200
    assert player["currentRank"] == "Ascendant 3"
    assert player["peakRank"] == "Immortal 1"
    assert player["peakRankSeason"] == "V26:A1"
    assert player["ranks"][0]["game"] == "VALORANT"
    assert player["ranks"][0]["tier"] == "ascendant"
    assert player["ranks"][0]["division"] == "3"
    assert player["ranks"][0]["rating"] == 45
    match = player["matches"][0]
    assert (match["id"], match["map"], match["game"]) == ("searched-player-match", "Ascent", "VALORANT")
    assert match["result"] == "Win" and match["score"] == "13:9"
    assert len(match["teams"]) == 2
    target = match["teams"][0]["players"][0]
    assert target["self"] is True and target["riotId"] == "Target#TAG"
    assert target["agent"] == "Waylay"
    assert target["stats"] == {"kills": 24, "deaths": 15, "assists": 4}


def test_local_search_merges_valorant_without_losing_league_or_tft() -> None:
    calls: list[str] = []

    def read_profile(puuid: str) -> dict[str, Any]:
        calls.append(puuid)
        return profile_snapshot()

    ranks = parse_ranked_stats({"queues": [
        {"queueType": "RANKED_SOLO_5x5", "tier": "SILVER", "division": "IV", "leaguePoints": 0, "wins": 2, "losses": 3},
        {"queueType": "RANKED_TFT", "tier": "GOLD", "division": "III", "leaguePoints": 68, "wins": 14, "losses": 8},
    ]})
    local = SimpleNamespace(
        lookup_summoner=lambda *_a, **_kw: LeagueSummonerProfile(TARGET, "Target", "TAG", 86),
        ranked_stats=lambda puuid: ranks,
        close=lambda: None,
    )
    service = RiotSearchService(local_client_factory=lambda: local, valorant_profile_reader=read_profile)
    player = Bridge._player(service.search_player("Target#TAG")[0])

    assert calls == [TARGET]
    assert player["games"][0] == "VALORANT"
    assert set(player["games"]) == {"VALORANT", "League of Legends", "Teamfight Tactics"}
    by_game = {rank["game"]: rank for rank in player["ranks"]}
    assert by_game["VALORANT"]["tier"] == "ascendant"
    assert by_game["League of Legends"]["tier"] == "silver"
    assert by_game["League of Legends"]["rating"] == 0
    assert by_game["Teamfight Tactics"]["tier"] == "gold"
    assert by_game["Teamfight Tactics"]["rating"] == 68
    assert player["currentRank"] == "Ascendant 3"
    assert player["peakRank"] == "Immortal 1"
    assert player["matches"][0]["id"] == "searched-player-match"


@pytest.mark.parametrize("response", [None, {}, "error"])
def test_failed_valorant_read_keeps_identity_without_inventing_rank(response: object) -> None:
    def read_profile(puuid: str) -> dict[str, Any] | None:
        assert puuid == TARGET
        if response == "error":
            raise RuntimeError("private-token-must-not-leak")
        return response  # type: ignore[return-value]

    service = RiotSearchService(
        local_client_factory=lambda: SimpleNamespace(),
        riot_client_factory=alias_client,
        valorant_profile_reader=read_profile,
    )
    player = Bridge._player(service.search_player("Target#TAG")[0])

    assert player["riotId"] == "Target#TAG"
    assert player["currentRank"] == "Rank unavailable"
    assert player["ranks"] == [] and player["matches"] == []
    assert "VALORANT" not in player["games"]
    assert "private-token" not in str(player)


def test_empty_identity_lookup_never_reads_valorant_profile() -> None:
    empty_client = SimpleNamespace(lookup_summoner=lambda *_a, **_kw: None)
    empty_alias = SimpleNamespace(lookup_player=lambda *_a: None)
    service = RiotSearchService(
        local_client_factory=lambda: empty_client,
        riot_client_factory=lambda: empty_alias,
        valorant_profile_reader=lambda _: pytest.fail("A profile needs an exact resolved identity"),
    )
    assert service.search_player("Missing#TAG") == []


@pytest.mark.parametrize("requested", ["League", "League of Legends", "TFT", "Teamfight Tactics"])
def test_explicit_other_game_search_does_not_fetch_valorant(requested: str) -> None:
    service = RiotSearchService(
        local_client_factory=lambda: SimpleNamespace(),
        riot_client_factory=alias_client,
        valorant_profile_reader=lambda _: pytest.fail("Explicit other-game search must not fetch VALORANT"),
    )
    assert service.search_player("Target#TAG", game=requested)[0]["riotId"] == "Target#TAG"


def test_default_profile_reader_uses_current_game_service(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def snapshot(_self: CurrentGameService, puuid: str) -> dict[str, Any]:
        calls.append(puuid)
        return profile_snapshot()

    monkeypatch.setattr(CurrentGameService, "valorant_player_snapshot", snapshot)
    service = RiotSearchService(local_client_factory=lambda: SimpleNamespace(), riot_client_factory=alias_client)
    player = Bridge._player(service.search_player("Target#TAG")[0])
    assert calls == [TARGET]
    assert player["game"] == "VALORANT"


def test_bridge_player_preserves_existing_frontend_matches() -> None:
    match = {
        "id": "frontend-match",
        "game": "VALORANT",
        "map": "Abyss",
        "mode": "Competitive",
        "result": "Win",
        "playedAt": "Yesterday",
        "duration": "32m",
        "teams": [],
    }
    player = Bridge._player({"id": TARGET, "riotId": "Target#TAG", "games": ["VALORANT"], "matches": [match]})
    assert player["matches"] == [match]

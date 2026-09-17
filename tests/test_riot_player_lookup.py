from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.persistence import Database
from peaks.adapters.riot.client import RiotClientError, RiotClientUnavailable
from peaks.adapters.riot.player_lookup import (
    RiotPlayerIdentity,
    RiotPlayerLookup,
    parse_alias_lookup,
)
from peaks.application.runtime import RiotSearchService
from peaks.bridge import Bridge
from peaks.domain.models import FollowedAccount


def alias(puuid: str = "target-puuid", name: str = "Peak", tag: str = "TAG") -> dict[str, Any]:
    return {"alias": {"game_name": name, "tag_line": tag}, "puuid": puuid}


def test_lookup_accepts_only_complete_exact_riot_ids() -> None:
    profile = parse_alias_lookup([alias("other-puuid", "Peak", "OTHER"), alias()], "peak", "tag")
    assert profile is not None and profile.puuid == "target-puuid" and profile.riot_id == "Peak#TAG"
    assert "target-puuid" not in repr(profile)
    assert parse_alias_lookup([alias(name="Similar Peak"), alias(tag="OTHER")], "Peak", "TAG") is None
    assert parse_alias_lookup([], "Peak", "TAG") is None


@pytest.mark.parametrize("payload", [None, {}, {"error": "private-response"}, [alias()] * 101, [alias(), alias("conflicting-puuid")]])
def test_lookup_rejects_invalid_or_ambiguous_responses(payload: object) -> None:
    with pytest.raises(RiotClientUnavailable):
        parse_alias_lookup(payload, "Peak", "TAG")


@pytest.mark.parametrize("payload", [[alias("bad\npuuid")], [alias(name="Peak\n")], [{"alias": {"game_name": "Peak", "tag_line": "TAG"}}]])
def test_lookup_drops_malformed_identity_fields(payload: object) -> None:
    assert parse_alias_lookup(payload, "Peak", "TAG") is None


def test_lookup_uses_only_documented_get_with_both_name_and_tag() -> None:
    calls: list[tuple[str, Any]] = []
    class LocalHTTP:
        def get_json(self, endpoint: str, *, params: Any = None) -> Any:
            calls.append((endpoint, params))
            return [alias()]

        def close(self) -> None:
            calls.append(("closed", None))

    client = RiotPlayerLookup(LocalHTTP())  # type: ignore[arg-type]
    assert client.lookup_player("Peak", "TAG") is not None
    client.close()
    assert calls == [("/player-account/aliases/v1/lookup", {"gameName": "Peak", "tagLine": "TAG"}), ("closed", None)]


def test_unsupported_endpoint_is_unavailable_instead_of_not_found() -> None:
    class LocalHTTP:
        def get_json(self, *_: Any, **__: Any) -> Any:
            raise RiotClientError("private-response", status_code=404)

    with pytest.raises(RiotClientUnavailable, match="unavailable"):
        RiotPlayerLookup(LocalHTTP()).lookup_player("Peak", "TAG")  # type: ignore[arg-type]


def test_fallback_discovers_identity_without_league_or_api_key_or_game_guess() -> None:
    closed: list[bool] = []
    client = SimpleNamespace(lookup_player=lambda name, tag: RiotPlayerIdentity("target-puuid", name, tag), close=lambda: closed.append(True))
    service = RiotSearchService(local_client_factory=lambda: SimpleNamespace(), riot_client_factory=lambda: client, valorant_profile_reader=lambda _: None)
    result = Bridge._player(service.search_player("Peak#TAG")[0])
    assert result["riotId"] == "Peak#TAG"
    assert result["region"] == "GLOBAL"
    assert result["games"] == [] and result["ranks"] == []
    assert "game" not in result
    assert result["currentRank"] == "Rank unavailable"
    assert closed == [True]


def test_empty_league_result_can_resolve_globally_in_riot_client() -> None:
    local = SimpleNamespace(lookup_summoner=lambda *_a, **_kw: None)
    riot = SimpleNamespace(lookup_player=lambda *_a: RiotPlayerIdentity("target-puuid", "Peak", "TAG"))
    result = RiotSearchService(local_client_factory=lambda: local, riot_client_factory=lambda: riot, valorant_profile_reader=lambda _: None).search_player("Peak#TAG")
    assert result[0]["puuid"] == "target-puuid"


def test_successful_empty_provider_is_not_changed_to_client_unavailable() -> None:
    local = SimpleNamespace(lookup_summoner=lambda *_a, **_kw: None)
    assert RiotSearchService(local_client_factory=lambda: local, riot_client_factory=lambda: SimpleNamespace(), valorant_profile_reader=lambda _: None).search_player("Peak#TAG") == []


def test_neutral_profile_can_be_watched_and_survives_database_roundtrip(tmp_path: Path) -> None:
    player = Bridge._follow_player({"id": "target-puuid", "riotId": "Peak#TAG", "games": [], "currentRank": "Rank unavailable"})
    assert "game" not in player and player["games"] == []
    followed = Bridge._followed_domain(player)
    assert followed.game is None and followed.rank is None
    assert FollowedAccount.from_dict(followed.to_dict()).game is None
    database = Database(tmp_path / "metadata.db")
    try:
        database.add_followed(followed)
        restored = database.list_followed()[0]
        projected = Bridge._followed_view(restored)
        assert restored.game is None
        assert "game" not in projected and projected["games"] == []
        assert database.is_followed("target-puuid")
        assert database.remove_followed("target-puuid")
    finally:
        database.close()


def test_search_bridge_normalizes_all_real_game_and_rank_labels() -> None:
    result = Bridge._player({"games": ["League", "TFT"], "ranks": [{"game": "TFT", "tier": "Gold III", "rating": 68}]})
    assert result["games"] == ["League of Legends", "Teamfight Tactics"]
    assert result["ranks"] == [{"game": "Teamfight Tactics", "tier": "gold", "division": "III", "rating": 68}]


def test_follow_preserves_both_game_ranks_after_database_reopen(tmp_path: Path) -> None:
    player = Bridge._player({
        "id": "target-puuid", "riotId": "Peak#TAG", "region": "EUW", "games": ["League", "TFT"],
        "currentRank": "Silver IV · 0 LP",
        "ranks": [{"game": "League", "tier": "Silver IV", "rating": 0}, {"game": "TFT", "tier": "Gold III", "rating": 68}],
    })
    followed = Bridge._follow_player(player)
    assert followed["games"] == ["League of Legends", "Teamfight Tactics"]
    assert followed["ranks"] == player["ranks"]
    filename = tmp_path / "watchlist.db"
    database = Database(filename)
    database.add_followed(Bridge._followed_domain(followed))
    database.close()
    reopened = Database(filename)
    try:
        restored = reopened.list_followed()[0]
        assert restored.rank is not None and restored.rank.label == "Silver IV"
        result = Bridge._followed_view(restored)
        assert result["games"] == player["games"]
        assert result["ranks"] == player["ranks"]
        assert result["currentRank"] == "Silver IV · 0 LP"
    finally:
        reopened.close()


def test_follow_ignores_unavailable_rank_placeholders() -> None:
    player = Bridge._follow_player({
        "id": "target-puuid", "riotId": "Peak#TAG", "game": "League of Legends",
        "currentRank": "Rank unavailable", "peakRank": "Tracked after watching",
    })
    followed = Bridge._followed_domain(player)
    assert followed.rank is None and followed.peak_rank is None

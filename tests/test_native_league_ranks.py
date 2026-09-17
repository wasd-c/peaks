"""Synthetic LCU fixtures for independent League and TFT rank hydration."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.riot.discovery import (
    RiotLockfile,
    default_paths,
    discover_verified_league_lockfile,
    validate_league_lockfile_process,
)
from peaks.adapters.riot.league import (
    LeagueClient,
    LeagueSummonerProfile,
    parse_ranked_stats,
)
from peaks.application.runtime import CurrentGameService, RiotSearchService
from peaks.bridge import Bridge
from peaks.domain.models import Game


def queue(queue_type: str = "RANKED_TFT", **changes: Any) -> dict[str, Any]:
    return {"queueType": queue_type, "tier": "GOLD", "division": "III", "leaguePoints": 68, "wins": 14, "losses": 8, **changes}


def test_current_league_owner_is_accepted_with_exact_pid_and_installation(tmp_path: Path) -> None:
    executable = tmp_path / "Riot Games" / "League of Legends" / "LeagueClient.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    (executable.parent / "lockfile").write_text("LeagueClient:91:54323:synthetic-secret:https", encoding="utf-8")
    lock = discover_verified_league_lockfile(
        platform_name="Windows", paths=default_paths(platform_name="Windows", env={}),
        process_identities=((92, "LeagueClientUx.exe", executable.with_name("LeagueClientUx.exe")), (91, "LeagueClient.exe", executable)),
    )
    assert lock is not None and lock.pid == 91
    assert "synthetic-secret" not in repr(lock)
    assert discover_verified_league_lockfile(
        platform_name="Windows", paths=default_paths(platform_name="Windows", env={}),
        process_identities=((92, "LeagueClient.exe", executable),),
    ) is None


@pytest.mark.parametrize("name,folder,basename", [
    ("LeagueClient.exe", "Unrelated", "LeagueClient.exe"),
    ("Unrelated.exe", "League of Legends", "LeagueClient.exe"),
    ("LeagueClient.exe", "League of Legends", "LeagueClientUx.exe"),
])
def test_league_owner_validation_rejects_path_and_process_conflicts(tmp_path: Path, name: str, folder: str, basename: str) -> None:
    executable = tmp_path / "Riot Games" / folder / basename
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    lock = RiotLockfile("LeagueClient", 91, 54323, "synthetic-secret")
    assert validate_league_lockfile_process(lock, process_lookup=lambda _: (name, executable)) is None


def test_parser_keeps_standard_tft_gold_separate_from_league_and_double_up() -> None:
    result = parse_ranked_stats({"queues": [queue("RANKED_TFT_DOUBLE_UP", tier="BRONZE"), queue(), queue("RANKED_SOLO_5x5", tier="SILVER", division="IV", leaguePoints=0)]})
    assert result is not None
    assert [(rank.queue_type, rank.tier, rank.rank, rank.league_points) for rank in result] == [
        ("RANKED_TFT", "GOLD", "III", 68), ("RANKED_SOLO_5x5", "SILVER", "IV", 0),
    ]


def test_parser_requires_an_explicit_queue_before_reporting_unranked() -> None:
    assert parse_ranked_stats({"errorCode": "unavailable"}) is None
    assert parse_ranked_stats({"queues": []}) == ()
    assert parse_ranked_stats({"queues": [queue("RANKED_TFT_DOUBLE_UP")]}) == ()
    result = parse_ranked_stats({"queueMap": {"RANKED_TFT": queue(tier="", division="NA", leaguePoints=0, wins=0, losses=0)}})
    assert result is not None and result[0].tier == "UNRANKED"


@pytest.mark.parametrize("changes", [{"queueType": {}}, {"tier": "not-a-rank"}, {"division": "private text"}, {"leaguePoints": True}, {"wins": -1}, {"losses": "8"}, {"tier": ""}])
def test_parser_omits_malformed_rank_entries(changes: dict[str, Any]) -> None:
    assert parse_ranked_stats({"queues": [queue(**changes)]}) == ()


class LocalClient:
    def __init__(self, *, identity: bool = True, rank_error: bool = False) -> None:
        self.identity = identity
        self.rank_error = rank_error
        self.rank_calls = 0
        self.closed = False

    def lookup_summoner(self, *_: Any, **__: Any) -> LeagueSummonerProfile:
        return LeagueSummonerProfile("owned-puuid", "Peak", "EUW", 86)

    def current_profile(self, puuid: str) -> LeagueSummonerProfile | None:
        return self.lookup_summoner() if self.identity and puuid == "owned-puuid" else None

    def ranked_stats(self, puuid: str, **_: Any) -> Any:
        assert puuid == "owned-puuid"
        self.rank_calls += 1
        if self.rank_error:
            raise RuntimeError("private-token-never-print")
        return parse_ranked_stats({"queues": [queue("RANKED_SOLO_5x5", tier="SILVER", division="IV", leaguePoints=0), queue()]})

    def close(self) -> None:
        self.closed = True


def test_native_search_needs_no_game_or_api_key_and_returns_both_real_ranks() -> None:
    local = LocalClient()
    service = RiotSearchService(local_client_factory=lambda: local, valorant_profile_reader=lambda _: None)
    service._client = SimpleNamespace(get_account_by_riot_id=lambda *_a, **_kw: pytest.fail("Optional API must not replace working native lookup"))
    result = service.search_player("Peak#EUW", region="EUW")[0]
    assert result["games"] == ["League", "TFT"]
    assert [(rank["game"], rank["tier"], rank["rating"]) for rank in result["ranks"]] == [("League", "Silver IV", 0), ("TFT", "Gold III", 68)]
    assert result["level"] == 86
    assert local.closed


def test_failed_rank_read_preserves_identity_without_fabricating_unranked() -> None:
    local = LocalClient(rank_error=True)
    result = RiotSearchService(local_client_factory=lambda: local, valorant_profile_reader=lambda _: None).search_player("Peak#EUW", region="EUW")[0]
    assert result["ranks"] == []
    assert result["currentRank"] == "Rank unavailable"
    assert "private-token" not in str(result)
    assert local.closed


@pytest.mark.parametrize("requested", ["all", "League", "TFT"])
def test_tft_only_rank_never_becomes_league_rank_when_followed(requested: str) -> None:
    class TftOnlyClient(LocalClient):
        def ranked_stats(self, puuid: str, **_: Any) -> Any:
            assert puuid == "owned-puuid"
            return parse_ranked_stats({"queues": [queue()]})

    service = RiotSearchService(local_client_factory=TftOnlyClient, valorant_profile_reader=lambda _: None)
    result = service.search_player("Peak#EUW", game=requested)[0]
    player = Bridge._player(result)
    watched = Bridge._followed_domain(Bridge._follow_player(player))
    assert [(rank.game, rank.label) for rank in watched.ranks] == [(Game.TFT, "Gold III")]
    if requested == "TFT":
        assert result["currentRank"] == "Gold III · 68 LP"
        assert player["game"] == "Teamfight Tactics"
        assert watched.rank is not None and watched.rank.game == Game.TFT
    else:
        assert result["currentRank"] == "Rank unavailable"
        assert player["game"] == "League of Legends"
        assert watched.rank is None


def test_follow_structured_tft_rank_blocks_misattributed_legacy_league_label() -> None:
    player = Bridge._player({
        "id": "owned-puuid", "riotId": "Peak#EUW", "games": ["League", "TFT"],
        "currentRank": "Gold III · 68 LP",
        "ranks": [{"game": "TFT", "tier": "Gold III", "rating": 68}],
    })
    watched = Bridge._followed_domain(Bridge._follow_player(player))
    assert watched.game == Game.LEAGUE_OF_LEGENDS
    assert watched.rank is None
    assert watched.ranks[0].game == Game.TFT


@pytest.mark.parametrize("identity", [True, False])
def test_owned_native_snapshot_requires_exact_identity(monkeypatch: pytest.MonkeyPatch, identity: bool) -> None:
    local = LocalClient(identity=identity)
    monkeypatch.setattr("peaks.application.runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr(LeagueClient, "from_discovery", lambda: local)
    result = CurrentGameService().owned_league_snapshot("owned-puuid")
    assert local.rank_calls == int(identity)
    assert local.closed
    if identity:
        assert result is not None
        assert result["ranks"][1]["tier"] == "Gold III"
        assert result["ranks"][1]["rating"] == 68
    else:
        assert result is None

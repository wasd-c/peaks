from __future__ import annotations

from datetime import UTC, datetime

import pytest

from peaks.domain import (
    Account,
    AccountLayout,
    CurrentMatch,
    FollowedAccount,
    Game,
    MatchRecord,
    MatchResult,
    RankInfo,
    RankTier,
    SearchEntry,
    Settings,
)


def test_game_and_rank_values_are_normalized_without_losing_unknown_tiers() -> None:
    rank = RankInfo(
        game="VALORANT",
        tier="radiant",
        rating=812,
        peak_tier="community_tier",
        division=None,
    )

    assert rank.game is Game.VALORANT
    assert rank.tier is RankTier.RADIANT
    assert rank.tier_label == "Radiant"
    assert rank.peak_tier == "community_tier"
    assert rank.to_dict() == {
        "game": "valorant",
        "tier": "radiant",
        "division": None,
        "rating": 812,
        "wins": None,
        "losses": None,
        "peak_tier": "community_tier",
        "peak_division": None,
        "peak_rating": None,
        "updated_at": None,
        "ranked": True,
    }


def test_account_round_trip_and_rank_lookup() -> None:
    timestamp = datetime(2026, 8, 1, 12, tzinfo=UTC)
    account = Account(
        account_id="puuid-1",
        game_name="Peak Player",
        tag_line="#EUW",
        region="EUW1",
        puuid="puuid-1",
        level=284,
        last_seen_at=timestamp,
        ranks=(
            RankInfo(Game.LEAGUE_OF_LEGENDS, RankTier.EMERALD, division="I"),
            RankInfo(Game.VALORANT, RankTier.DIAMOND, division="2"),
        ),
    )
    restored = Account.from_dict(account.to_dict())

    assert restored == account
    assert account.id == account.account_id == "puuid-1"
    assert account.display_name == "Peak Player#EUW"
    assert account.level == 284
    assert account.rank_for("valorant").label == "Diamond 2"  # type: ignore[union-attr]

    with pytest.raises(ValueError, match="between 0 and 100000"):
        Account("invalid", "Invalid", level=100_001)


def test_search_followed_and_match_dtos_are_serializable() -> None:
    search = SearchEntry("Player", "EUW", "euw1", game="tft")
    followed = FollowedAccount(
        account_id="puuid-2",
        game_name="Player",
        tag_line="EUW",
        region="euw1",
        game=Game.TFT,
        rank=RankInfo(Game.TFT, RankTier.GOLD),
    )
    match = MatchRecord(
        match_id="match-1",
        account_id="puuid-2",
        game=Game.TFT,
        played_at=datetime.now(UTC),
        result=MatchResult.WIN,
        metadata={"placement": 1, "players": ["redacted"]},
    )

    assert SearchEntry.from_dict(search.to_dict()) == search
    assert FollowedAccount.from_dict(followed.to_dict()) == followed
    assert MatchRecord.from_dict(match.to_dict()) == match
    assert match.won is True


def test_match_accepts_provider_unix_timestamp() -> None:
    restored = MatchRecord.from_dict(
        {
            "id": "match-unix",
            "account_id": "owned",
            "game": "league",
            "played_at": 1_787_000_000,
            "result": "win",
        }
    )

    assert restored.played_at.tzinfo is UTC
    assert restored.to_dict()["played_at"].startswith("2026-")


def test_settings_defaults_are_grid_and_lock_preferences_are_preserved() -> None:
    settings = Settings(lock_timeout_seconds=240, layout="list", lock_on_blur=False, reduce_motion=True)
    restored = Settings.from_dict(settings.to_dict())

    assert settings.layout is AccountLayout.LIST
    assert restored == settings
    assert restored.lock_timeout_minutes == 4


def test_no_game_state_is_explicitly_not_clickable() -> None:
    current = CurrentMatch.no_game()

    assert current.detected is False
    assert current.clickable is False
    assert current.to_dict()["game"] is None

    with pytest.raises(ValueError):
        CurrentMatch(detected=False, game=Game.VALORANT)

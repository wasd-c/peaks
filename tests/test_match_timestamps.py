from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from peaks.bridge import Bridge, _match
from peaks.domain.models import Game, MatchRecord

PLAYED = datetime(2026, 9, 18, 12, 30, tzinfo=UTC)
TIMESTAMP = int(PLAYED.timestamp() * 1_000)


@pytest.mark.parametrize(
    "played_at",
    [
        PLAYED,
        PLAYED.replace(tzinfo=None),
        PLAYED.isoformat(),
        "2026-09-18T14:30:00+02:00",
        PLAYED.timestamp(),
        TIMESTAMP,
    ],
)
def test_match_keeps_real_timestamp_in_milliseconds(played_at: Any) -> None:
    view = _match({"id": "match", "game": "valorant", "played_at": played_at})
    assert view["playedAtTimestamp"] == TIMESTAMP


@pytest.mark.parametrize(
    "played_at",
    [
        None,
        "42 minutes ago",
        "not a date",
        True,
        float("nan"),
        float("inf"),
        -1,
    ],
)
def test_unknown_dates_do_not_invent_a_match_timestamp(played_at: Any) -> None:
    assert "playedAtTimestamp" not in _match({"id": "match", "played_at": played_at})


def test_stored_match_and_represented_view_keep_the_same_timestamp() -> None:
    match = MatchRecord("match", "owner", Game.LEAGUE_OF_LEGENDS, PLAYED)
    view = _match(match)
    assert view["playedAtTimestamp"] == TIMESTAMP
    assert _match(view)["playedAtTimestamp"] == TIMESTAMP


def test_refresh_of_older_provider_page_keeps_newer_cross_game_matches_first() -> None:
    account: dict[str, Any] = {
        "matches": [
            {
                "id": "league-newest",
                "game": "League of Legends",
                "playedAtTimestamp": TIMESTAMP,
            }
        ],
    }
    # An entire older VALORANT page used to evict the newer League match.
    snapshot = {
        "matches": [
            {
                "id": f"valorant-{index}",
                "game": "valorant",
                "played_at": PLAYED.timestamp() - (index + 1) * 3_600,
            }
            for index in range(20)
        ]
    }

    Bridge._merge_account_snapshot(account, snapshot)

    assert len(account["matches"]) == 20
    assert account["matches"][0]["id"] == "league-newest"
    assert account["matches"][1]["id"] == "valorant-0"
    assert account["matches"][-1]["id"] == "valorant-18"


def test_unknown_dates_retain_stable_provider_order_without_parsing_display_copy() -> None:
    account: dict[str, Any] = {
        "matches": [{"id": "saved", "playedAt": "just now"}],
    }
    Bridge._merge_account_snapshot(
        account,
        {
            "matches": [
                {"id": "first", "playedAt": "2h ago"},
                {"id": "second", "playedAt": "1h ago"},
            ]
        },
    )
    assert [match["id"] for match in account["matches"]] == ["first", "second", "saved"]

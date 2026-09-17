"""Offline tests for the runtime's official Riot search facade."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from peaks.adapters.providers.riot_api import LeagueRank, RiotAccount, RiotApiError, TftRank
from peaks.application.runtime import RiotSearchService


class FakeClient:
    def __init__(
        self,
        *,
        league_ranks: Any = (),
        tft_ranks: Any = (),
        league_history: Any = (),
        tft_history: Any = (),
        league_details: Any = None,
        tft_details: Any = None,
        account_error: Exception | None = None,
    ) -> None:
        self.account_error = account_error
        self.league_ranks_value = league_ranks
        self.tft_ranks_value = tft_ranks
        self.league_history_value = league_history
        self.tft_history_value = tft_history
        self.league_details = league_details or {}
        self.tft_details = tft_details or {}
        self.calls: list[tuple[str, str, int | None]] = []

    def get_account_by_riot_id(self, game_name: str, tag_line: str, *, routing: str) -> RiotAccount:
        del game_name, tag_line, routing
        if self.account_error is not None:
            raise self.account_error
        return RiotAccount(puuid="puuid-1", game_name="Peak", tag_line="EUW")

    def get_league_ranks(self, puuid: str, *, routing: str) -> tuple[LeagueRank, ...]:
        self.calls.append(("league-ranks", routing, None))
        if isinstance(self.league_ranks_value, Exception):
            raise self.league_ranks_value
        return tuple(self.league_ranks_value)

    def get_tft_ranks(self, puuid: str, *, routing: str) -> tuple[TftRank, ...]:
        self.calls.append(("tft-ranks", routing, None))
        if isinstance(self.tft_ranks_value, Exception):
            raise self.tft_ranks_value
        return tuple(self.tft_ranks_value)

    def get_league_match_history(self, puuid: str, *, routing: str, count: int) -> Any:
        self.calls.append(("league-history", routing, count))
        if isinstance(self.league_history_value, Exception):
            raise self.league_history_value
        return self.league_history_value

    def get_tft_match_history(self, puuid: str, *, routing: str, count: int) -> Any:
        self.calls.append(("tft-history", routing, count))
        if isinstance(self.tft_history_value, Exception):
            raise self.tft_history_value
        return self.tft_history_value

    def get_league_match(self, match_id: str, *, routing: str) -> Any:
        self.calls.append(("league-match", routing, None))
        return SimpleNamespace(info=self.league_details.get(match_id, {}))

    def get_tft_match(self, match_id: str, *, routing: str) -> Any:
        self.calls.append(("tft-match", routing, None))
        return SimpleNamespace(info=self.tft_details.get(match_id, {}))


def _service(client: FakeClient) -> RiotSearchService:
    service = RiotSearchService(local_client_factory=lambda: SimpleNamespace(), riot_client_factory=lambda: SimpleNamespace())
    service._client = client
    return service


def test_clear_api_key_drops_provider_client() -> None:
    service = _service(FakeClient())

    service.clear_api_key()

    with pytest.raises(RuntimeError, match="LOCAL_RIOT_CLIENT_UNAVAILABLE"):
        service.search_player("Peak#EUW", region="EUW", game="all")


def test_search_rejects_unknown_platform_instead_of_guessing_euw() -> None:
    client = FakeClient()

    with pytest.raises(ValueError, match="supported Riot platform region"):
        _service(client).search_player("Peak#EUW", region="AP", game="all")

    assert client.calls == []


def test_all_games_keeps_league_and_tft_useful_when_league_is_unplayed() -> None:
    tft_rank = TftRank("RANKED_TFT", "GOLD", "II", 12, 8, 5)
    client = FakeClient(
        league_ranks=RiotApiError("not found", status_code=404),
        league_history=RiotApiError("not found", status_code=404),
        tft_ranks=(tft_rank,),
    )

    result = _service(client).search_player("Peak#EUW", region="EUW", game="All Games")[0]

    assert result["games"] == ["League", "TFT", "VALORANT"]
    assert result["currentRank"] == "Gold II · 12 LP"
    assert result["lastGame"] == "No recent game"
    assert result["valorantStatus"] == "Requires approved VALORANT RSO"


def test_all_games_omits_unplayed_tft_but_does_not_abort_league() -> None:
    league_rank = LeagueRank("RANKED_SOLO_5x5", "PLATINUM", "IV", 40, 2, 1)
    client = FakeClient(
        league_ranks=(league_rank,),
        league_history=SimpleNamespace(match_ids=()),
        tft_ranks=RiotApiError("not found", status_code=404),
    )

    result = _service(client).search_player("Peak#EUW", region="EUW", game="all")[0]

    assert result["games"] == ["League", "VALORANT"]
    assert result["currentRank"] == "Platinum IV · 40 LP"


def test_account_lookup_error_is_sanitized_before_reaching_ui() -> None:
    client = FakeClient(account_error=RiotApiError("X-Riot-Token=do-not-show", status_code=401))

    with pytest.raises(RuntimeError) as raised:
        _service(client).search_player("Peak#EUW", region="EUW", game="all")

    assert str(raised.value) == "Player lookup failed: Riot API authorization is unavailable"
    assert "do-not-show" not in str(raised.value)


def test_valorant_search_preserves_approved_rso_limitation_without_api_fallback() -> None:
    client = FakeClient()

    result = _service(client).search_player("Peak#EUW", region="EUW", game="valorant")[0]

    assert result["games"] == ["VALORANT"]
    assert result["currentRank"] == "Requires approved VALORANT RSO"
    assert result["valorantStatus"] == "Requires approved VALORANT RSO"
    assert not any("ranks" in call[0] for call in client.calls)


def test_search_result_contains_official_league_history_for_shared_detail_view() -> None:
    league_rank = LeagueRank("RANKED_SOLO_5x5", "DIAMOND", "III", 70, 30, 20)
    match_id = "EUW1_recent"
    client = FakeClient(
        league_ranks=(league_rank,),
        league_history=SimpleNamespace(match_ids=(match_id,)),
        league_details={
            match_id: {
                "gameEndTimestamp": 1_700_000_000_000,
                "queueId": 420,
                "participants": [
                    {"puuid": "puuid-1", "win": True, "kills": 8, "deaths": 2, "assists": 11}
                ],
            }
        },
    )

    result = _service(client).search_player("Peak#EUW", region="EUW", game="League")[0]

    assert result["owned"] is False
    assert [rank["game"] for rank in result["ranks"]] == ["League", "VALORANT"]
    assert result["currentRank"] == "Diamond III · 70 LP"
    assert result["matches"][0]["id"] == match_id
    assert result["matches"][0]["result"] == "win"
    assert result["matches"][0]["mode"] == "420"
    assert result["matches"][0]["playedAt"] != "No recent game"
    assert result["lastGame"] == result["matches"][0]["playedAt"]


def test_account_overview_has_required_ranks_and_bounded_official_match_rows() -> None:
    league_rank = LeagueRank("RANKED_SOLO_5x5", "DIAMOND", "III", 70, 30, 20)
    tft_rank = TftRank("RANKED_TFT", "MASTER", "I", 200, 20, 10)
    league_ids = tuple(f"EUW1_{index}" for index in range(25))
    tft_ids = tuple(f"TFT_{index}" for index in range(4))
    client = FakeClient(
        league_ranks=(league_rank,),
        tft_ranks=(tft_rank,),
        league_history=SimpleNamespace(match_ids=league_ids),
        tft_history=SimpleNamespace(match_ids=tft_ids),
        league_details={match_id: {"gameEndTimestamp": 1_700_000_000_000} for match_id in league_ids},
        tft_details={match_id: {"gameEndTimestamp": 1_700_000_000_000} for match_id in tft_ids},
    )

    overview = _service(client).account_overview("Peak#EUW", "EUW")

    assert overview["riotId"] == "Peak#EUW"
    assert [rank["game"] for rank in overview["ranks"]] == ["League", "TFT", "VALORANT"]
    assert overview["valorantStatus"] == "Requires approved VALORANT RSO"
    assert len(overview["matches"]) == 20
    assert all(row["game"] == "league_of_legends" for row in overview["matches"])
    history_calls = [call for call in client.calls if call[0].endswith("history")]
    assert history_calls == [
        ("league-history", "europe", 20),
        ("tft-history", "europe", 20),
    ]


def test_account_overview_omits_tft_and_tft_history_when_unplayed() -> None:
    client = FakeClient(
        league_history=SimpleNamespace(match_ids=()),
        tft_ranks=RiotApiError("not found", status_code=404),
    )

    overview = _service(client).account_overview("Peak#EUW", "EUW")

    assert [rank["game"] for rank in overview["ranks"]] == ["League", "VALORANT"]
    assert not any(call[0] == "tft-history" for call in client.calls)


def test_account_overview_rejects_unknown_platform_instead_of_guessing_euw() -> None:
    client = FakeClient()

    with pytest.raises(ValueError, match="supported platform region"):
        _service(client).account_overview("Peak#EUW", "GLOBAL")

    assert client.calls == []


def test_rank_service_failure_is_not_reported_or_persisted_as_unranked() -> None:
    client = FakeClient(league_ranks=RiotApiError("unavailable", status_code=503), tft_ranks=RiotApiError("unavailable", status_code=503))
    result = _service(client).search_player("Peak#EUW", region="EUW", game="all")[0]
    assert result["currentRank"] == "Rank unavailable"
    assert not any(rank["game"] in {"League", "TFT"} for rank in result["ranks"])
    overview = _service(client).account_overview("Peak#EUW", "EUW")
    assert not any(rank["game"] in {"League", "TFT"} for rank in overview["ranks"])


def test_double_up_does_not_substitute_for_standard_tft_rank() -> None:
    client = FakeClient(tft_ranks=(TftRank("RANKED_TFT_DOUBLE_UP", "GOLD", "II", 12, 8, 5),))
    result = _service(client).search_player("Peak#EUW", region="EUW", game="all")[0]
    assert not any(rank["game"] == "TFT" for rank in result["ranks"])

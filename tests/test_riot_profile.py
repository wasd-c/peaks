"""Synthetic owned Riot histories: identity binding, compositions and game isolation."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from peaks.adapters.riot.league import LeagueClient, LeagueSummonerProfile
from peaks.adapters.riot.owned_history import history_details
from peaks.adapters.riot.tft_composition import composition_view
from peaks.application.runtime import CurrentGameService, RiotSearchService
from peaks.bridge import Bridge, _match, _match_teams


def tft_info():
    return {"queue_id": 1100, "game_datetime": 1789900000000, "game_length": 1832.5, "participants": [{
        "puuid": "private-owner", "placement": 2, "level": 9, "total_damage_to_players": 143,
        "players_eliminated": 2, "units": [{"character_id": "TFT17_Ahri", "tier": 2, "itemNames": ["TFT_Item_RabadonsDeathcap"]}],
        "traits": [{"name": "TFT17_Mage", "num_units": 4, "tier_current": 2}], "augments": ["TFT6_Augment_Test"],
        "privateToken": "secret-never-present",
    }]}


def test_tft_composition_survives_normalization_without_private_fields():
    raw = RiotSearchService._match_view("TFT", "EUW1_match", puuid="private-owner", info=tft_info(), played_at=1789900000)
    view = _match(raw)
    player = view["teams"][0]["players"][0]
    assert not player["hidden"] and player["self"]
    assert view["durationSeconds"] == 1832
    assert player["stats"]["damage"] == 143
    assert player["stats"]["playersEliminated"] == 2
    assert player["composition"] == {
        "units": [{"id": "TFT17_Ahri", "stars": 2, "items": ["TFT_Item_RabadonsDeathcap"]}],
        "traits": [{"id": "TFT17_Mage", "count": 4, "tier": 2}], "augments": ["TFT6_Augment_Test"],
    }
    assert composition_view(player["composition"]) == player["composition"]
    assert "private-owner" not in repr(view) and "secret-never-present" not in repr(view)


@pytest.mark.parametrize("units", [[{"character_id": "../../credential", "tier": 2}], [{"character_id": "TFT_Ahri", "tier": True}], [{"character_id": "TFT_Ahri", "tier": 999}], [{}] * 33])
def test_malformed_boards_are_unavailable_not_empty(units):
    assert "units" not in composition_view({"units": units})


def test_hidden_players_do_not_expose_compositions():
    teams = _match_teams([{"players": [{"hidden": True, "composition": {"units": [{"id": "TFT_Ahri", "stars": 2}]}}]}])
    assert "composition" not in teams[0]["players"][0]


def test_product_history_requires_explicit_owner_and_supports_legacy_stats():
    legacy = {"games": {"games": [{"gameId": 123, "platformId": "EUW1", "gameCreation": 1789900000000,
        "gameDuration": 1200, "queueId": 420, "participants": [{"participantId": 1, "championId": 103, "stats": {"kills": 12, "deaths": 3, "assists": 5}}],
        "participantIdentities": [{"participantId": 1, "player": {"puuid": "owner"}}]}]}}
    rows = history_details(legacy, puuid="owner", game="League")
    assert rows[0][0] == "EUW1_123"
    assert rows[0][1]["participants"][0]["kills"] == 12
    assert rows[0][1]["participants"][0]["championName"] == "103"
    assert rows[0][2] == 1789900000
    assert history_details(legacy, puuid="other", game="League") == []
    legacy["games"]["games"][0]["participantIdentities"] = []
    assert history_details(legacy, puuid="owner", game="League") == []


def test_native_tft_envelope_preserves_external_match_id_and_numeric_string_date():
    info = tft_info()
    info["game_datetime"] = "1789900000000"
    page = {"games": [{"metadata": {"match_id": "EUW1_tft"}, "json": info}]}
    rows = history_details(page, puuid="private-owner", game="TFT")
    assert len(rows) == 1
    assert rows[0][0] == "EUW1_tft"
    assert rows[0][2] == 1789900000


def test_local_history_does_not_request_another_account():
    paths = []
    client = LeagueClient(lcu_http=SimpleNamespace(get_json=lambda path: paths.append(path)))
    client.current_profile = lambda _: None
    assert client.owned_match_history("other", game="TFT") is None
    assert paths == []
    client.current_profile = lambda _: LeagueSummonerProfile("owner", "Owned", "TEST")
    client.owned_match_history("owner", game="TFT", limit=500)
    assert paths == ["/lol-match-history/v1/products/tft/owner/matches"]
    client.owned_match_history("owner", game="League", limit=500)
    assert paths[-1] == "/lol-match-history/v1/products/lol/owner/matches?begIndex=0&endIndex=19"


def test_owned_snapshot_reads_both_games_even_when_rank_service_fails(monkeypatch):
    calls = []
    local = SimpleNamespace(
        current_profile=lambda _: LeagueSummonerProfile("private-owner", "Owned", "TEST", 123),
        ranked_stats=lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("rank unavailable")),
        owned_match_history=lambda _p, *, game, limit: calls.append((game, limit)) or {"games": [{"json": {"metadata": {"match_id": "EUW1_test"}, "info": tft_info()}}]} if game == "TFT" else calls.append((game, limit)) or {},
        close=lambda: calls.append("close"),
    )
    monkeypatch.setattr("peaks.application.runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr(LeagueClient, "from_discovery", lambda: local)
    snapshot = CurrentGameService().owned_league_snapshot("private-owner")
    assert snapshot and snapshot["level"] == 123
    assert calls == [("League", 20), ("TFT", 20), "close"]
    view = _match(snapshot["matches"][0])
    assert view["teams"][0]["players"][0]["riotId"] == "Owned#TEST"
    assert "composition" in view["teams"][0]["players"][0]


def test_history_budget_is_per_game_and_retains_requested_older_report():
    account = {"matches": []}
    for game in ("valorant", "league_of_legends", "tft"):
        Bridge._merge_account_snapshot(account, {"matches": [{"id": f"{game}-{index}", "game": game, "played_at": 1789900000 + index} for index in range(23)]}, priority_match_id=f"{game}-0")
    assert len(account["matches"]) == 60
    for game in ("VALORANT", "League of Legends", "Teamfight Tactics"):
        rows = [row for row in account["matches"] if row["game"] == game]
        assert len(rows) == 20
        assert any(row["id"].endswith("-0") for row in rows)


def test_game_levels_are_not_substituted_between_profiles():
    account = {"level": 50, "ranks": [], "matches": []}
    Bridge._merge_account_snapshot(account, {"level": 317, "leagueLevel": 317})
    Bridge._merge_account_snapshot(account, {"valorantLevel": 465})
    assert account["leagueLevel"] == account["level"] == 317
    assert account["valorantLevel"] == 465


def test_tft_composition_roundtrips_through_sqlite():
    from peaks.adapters.persistence.database import Database
    from peaks.domain.models import Account, Game, MatchRecord

    with Database() as repository:
        repository.add_account(Account("owned", "Owned", "TEST", "EUW", "private-owner"))
        row = RiotSearchService._match_view("TFT", "EUW1_board", puuid="private-owner", info=tft_info(), played_at=1789900000)
        repository.add_match(MatchRecord.from_dict({**row, "account_id": "owned"}))
        restored = _match(repository.list_matches("owned", game=Game.TFT, limit=20)[0])
        assert restored["durationSeconds"] == 1832
        assert restored["teams"][0]["players"][0]["composition"]["units"][0]["stars"] == 2
        assert "private-owner" not in repr(restored)


def test_double_up_results_and_missing_league_minions_remain_honest():
    info = deepcopy(tft_info())
    info["queue_id"] = 1160
    info["participants"][0]["placement"] = 3
    # A partial Double Up report cannot establish whether #3 is a team or an
    # individual placement, so it must not imply a negative result.
    assert RiotSearchService._match_view("TFT", "duo", puuid="private-owner", info=info)["result"] == "unknown"
    teams = RiotSearchService._public_match_teams("League", [{"puuid": "owner", "kills": 0}], puuid="owner")
    assert "minions" not in teams[0]["players"][0]["stats"]

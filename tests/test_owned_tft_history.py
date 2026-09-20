"""Owner-bound local results fill delayed Riot history without degrading final reports."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from peaks.adapters.riot.league import LeagueClient, LeagueSummonerProfile
from peaks.application.runtime import CurrentGameService
from peaks.bridge import Bridge, _match

OWNER = "synthetic-owner"


def local_report():
    return {
        "id": "EUW1_123", "game": "tft", "queue": "1100", "result": "placement",
        "played_at": 1789882379.0, "duration_seconds": 1533,
        "metadata": {"localEndOfGame": True, "freeForAll": True, "teams": [{"players": [{
            "self": True, "name": "Previous#NAME", "riotId": "Previous#NAME",
            "stats": {"placement": 7},
            "composition": {"units": [{"id": "TFT17_Ahri", "stars": 2}]},
        }]}]},
    }


@pytest.mark.parametrize("history_state", ["failed", "stale", "stub", "missing", "final"])
def test_owned_snapshot_recovers_local_final_even_when_tft_history_lags_or_fails(monkeypatch, history_state):
    local_calls = []

    def read_local(puuid, platform, *, limit):
        local_calls.append((puuid, platform, limit))
        return [local_report()]

    def history(_puuid, *, game, limit):
        assert limit == 20
        if game == "League" or history_state == "missing":
            return {}
        if history_state == "failed":
            raise RuntimeError("synthetic history failure")
        participant = {"puuid": OWNER}
        if history_state != "stub":
            participant["placement"] = 1
        return {"games": [{"json": {
            "metadata": {"match_id": "EUW1_111" if history_state == "stale" else "EUW1_123"},
            "info": {"participants": [participant], "queue_id": 1100, "gameCreation": 1789882375000},
        }}]}

    region_paths = []
    client = SimpleNamespace(
        current_profile=lambda _puuid: LeagueSummonerProfile(OWNER, "Current", "NAME", 100),
        ranked_stats=lambda *_a, **_kw: (),
        owned_match_history=history,
        lcu_http=SimpleNamespace(get_json=lambda path: region_paths.append(path) or {"region": "EUW1"}),
        close=lambda: None,
    )
    monkeypatch.setattr("peaks.application.runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr(LeagueClient, "from_discovery", lambda: client)
    monkeypatch.setattr("peaks.adapters.riot.tft_local_history.read_tft_local_history", read_local)
    snapshot = CurrentGameService().owned_league_snapshot(OWNER)
    assert snapshot is not None
    assert local_calls == [(OWNER, "EUW1", 20)]
    assert region_paths == ["/riotclient/region-locale"]
    final = [match for match in snapshot["matches"] if match["id"] == "EUW1_123"]
    assert len(final) == 1
    player = final[0]["metadata"]["teams"][0]["players"][0]
    assert player["riotId"] == "Current#NAME"
    if history_state == "final":
        assert "localEndOfGame" not in final[0]["metadata"]
        assert player["stats"]["placement"] == 1
    else:
        assert final[0]["metadata"]["localEndOfGame"] is True
        assert player["stats"]["placement"] == 7
        assert player["composition"]["units"][0]["stars"] == 2


def test_owned_snapshot_does_not_read_local_logs_when_current_identity_mismatches(monkeypatch):
    client = SimpleNamespace(
        current_profile=lambda _puuid: LeagueSummonerProfile("someone-else", "Other", "NAME"),
        close=lambda: None,
    )
    monkeypatch.setattr("peaks.application.runtime.platform.system", lambda: "Windows")
    monkeypatch.setattr(LeagueClient, "from_discovery", lambda: client)
    monkeypatch.setattr("peaks.adapters.riot.tft_local_history.read_tft_local_history", lambda *_a, **_kw: pytest.fail("wrong owner's logs"))
    assert CurrentGameService().owned_league_snapshot(OWNER) is None


@pytest.mark.parametrize(("puuid", "platform"), [(OWNER, "GLOBAL"), ("", "EUW"), (" owner ", "EUW")])
def test_direct_local_snapshot_requires_explicit_owned_identity_and_known_platform(monkeypatch, puuid, platform):
    monkeypatch.setattr("peaks.adapters.riot.tft_local_history.read_tft_local_history", lambda *_a, **_kw: pytest.fail("unbound local read"))
    assert CurrentGameService().owned_tft_local_snapshot(puuid, platform=platform) is None


def test_memory_merge_keeps_local_final_until_real_riot_report_then_never_regresses():
    account = {"matches": []}
    local = local_report()
    Bridge._merge_account_snapshot(account, {"matches": [local]})
    expected_local = deepcopy(account["matches"])
    stub = deepcopy(local)
    stub["metadata"].pop("localEndOfGame")
    stub["metadata"]["teams"][0]["players"][0]["stats"] = {"standing": 2}
    stub["metadata"]["teams"][0]["players"][0]["composition"] = {}
    Bridge._merge_account_snapshot(account, {"matches": [stub]})
    assert account["matches"] == expected_local

    riot = deepcopy(local)
    riot["metadata"].pop("localEndOfGame")
    riot["metadata"]["teams"][0]["players"][0]["stats"]["damage"] = 123
    Bridge._merge_account_snapshot(account, {"matches": [riot]})
    assert len(account["matches"]) == 1
    assert "localEndOfGame" not in account["matches"][0]
    assert account["matches"][0]["teams"][0]["players"][0]["stats"]["damage"] == 123
    expected_riot = deepcopy(account["matches"])
    Bridge._merge_account_snapshot(account, {"matches": [local]})
    assert account["matches"] == expected_riot


def test_local_report_provenance_survives_database_projection():
    from peaks.domain.models import MatchRecord

    record = MatchRecord.from_dict({**local_report(), "account_id": "owner-account"})
    assert _match(record)["localEndOfGame"] is True

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from peaks.adapters.riot.match_analytics import parse_round_analytics
from peaks.adapters.riot.season_metadata import parse_public_seasons
from peaks.adapters.riot.valorant import ValorantMatchSummary, parse_match_details
from peaks.adapters.riot.valorant_enrichment import RequestBudget, ValorantEnrichmentCache
from peaks.application.runtime import CurrentGameService
from peaks.bridge import Bridge, _match, _rank


def impact_payload():
    teams = {"own": "Blue", "ally": "Blue", "enemy": "Red", "other": "Red"}
    events = [
        [("enemy", "own", 1_000, []), ("ally", "enemy", 6_000, []), ("ally", "other", 7_000, [])],
        [("own", "enemy", 1_000, ["ally"]), ("other", "ally", 2_000, []), ("own", "other", 3_000, [])],
    ]
    stats = {subject: {"kills": 0, "deaths": 0, "assists": 0, "roundsPlayed": 2} for subject in teams}
    rounds = []
    for index, kills in enumerate(events):
        rows = {subject: {"subject": subject, "kills": [], "damage": []} for subject in teams}
        for killer, victim, at, assistants in kills:
            rows[killer]["kills"].append({
                "killer": killer, "victim": victim, "timeSinceRoundStartMillis": at,
                "assistants": assistants, "finishingDamage": {"damageType": "Weapon", "damageItem": "9c82e19d-4575-0200-1a81-3eacf00cf872"},
            })
            rows[killer]["damage"].append({"receiver": victim, "damage": 100, "headshots": 1, "bodyshots": 0, "legshots": 0})
            stats[killer]["kills"] += 1
            stats[victim]["deaths"] += 1
            for assistant in assistants:
                stats[assistant]["assists"] += 1
        rounds.append({"roundNum": index, "winningTeam": "Blue", "playerStats": list(rows.values())})
    return {
        "matchInfo": {"matchId": "match", "queueID": "competitive", "seasonId": "act-one", "gameLengthMillis": 120_000},
        "players": [{"subject": subject, "teamId": team, "stats": stats[subject]} for subject, team in teams.items()],
        "roundResults": rounds,
    }


def test_kast_trade_window_damage_first_kills_and_pipeline_are_identity_safe():
    payload = impact_payload()
    impact = parse_round_analytics(payload)["own"].impact
    assert impact == {"impact_rounds": 2, "aces": 0, "kast_rounds": 2, "damage_received": 100, "first_kills": 1, "first_deaths": 1, "flawless_rounds": 0}
    detail = parse_match_details(payload, puuid="own", fallback=ValorantMatchSummary("match"))
    snapshot = CurrentGameService()._valorant_snapshot_view(12, None, (detail,), season_labels={"act-one": "V26:A5"})
    view = _match(snapshot["matches"][0])
    own = next(player for team in view["teams"] for player in team["players"] if player["self"])
    assert own["stats"]["kastRounds"] == 2
    assert own["stats"]["damageReceived"] == 100
    assert view["durationSeconds"] == 120
    assert view["season"] == "V26:A5"
    assert "act-one" not in repr(view)
    assert "receiver" not in repr(view)


def test_kast_does_not_count_a_late_trade():
    payload = impact_payload()
    payload["roundResults"][0]["playerStats"][1]["kills"][0]["timeSinceRoundStartMillis"] += 1
    assert parse_round_analytics(payload)["own"].impact["kast_rounds"] == 1


def test_missing_assists_damage_or_kills_never_become_zero_or_survival():
    payload = impact_payload()
    del payload["roundResults"][0]["playerStats"][1]["kills"][0]["assistants"]
    impact = parse_round_analytics(payload)["own"].impact
    assert "kast_rounds" not in impact
    assert impact["first_kills"] == 1
    payload = impact_payload()
    del payload["roundResults"][0]["playerStats"][2]["damage"][0]["receiver"]
    assert "damage_received" not in parse_round_analytics(payload)["own"].impact
    payload = impact_payload()
    payload["roundResults"][0]["playerStats"][2]["kills"] = []
    assert parse_round_analytics(payload)["own"].impact is None


@pytest.mark.parametrize("queue", ["deathmatch", "ggteam", "unknown"])
def test_round_contribution_excludes_respawn_modes(queue):
    payload = impact_payload()
    payload["matchInfo"]["queueID"] = queue
    assert parse_round_analytics(payload)["own"].impact is None


def test_duplicate_events_and_malformed_subjects():
    payload = impact_payload()
    events = payload["roundResults"][0]["playerStats"][1]["kills"]
    events.append(deepcopy(events[0]))
    assert parse_round_analytics(payload)["own"].impact["kast_rounds"] == 2
    events[0]["victim"] = {}
    assert parse_round_analytics(payload)["own"].impact is None


def test_peak_rank_survives_bridge_projection_without_inventing_rr():
    assert _rank({"game": "valorant", "tier": "Ascendant 3", "peak_tier": "Immortal", "peak_division": "1", "peak_season": "E7:A3"}) == {
        "game": "VALORANT", "tier": "ascendant", "division": "3", "rating": None,
        "peakTier": "Immortal", "peakDivision": "1", "peakSeason": "E7:A3",
    }


def test_lockfile_identity_is_separate_from_reusable_session_and_hidden_when_locked(monkeypatch):
    monkeypatch.setenv("PEAKS_DEMO", "1")
    bridge = Bridge()
    bridge.demo = False
    bridge._locked = False
    bridge.accounts = [{"id": "internal", "puuid": "private-subject", "riotId": "Fixture#TEST", "owned": True, "connected": False}]
    service = SimpleNamespace(detect=lambda: None, client_status={"detected": True}, detection_available=True, active_riot_subject=lambda: "private-subject")
    bridge._current_game_service = service
    bridge._poll_activity()
    state = bridge.state()
    assert state["activeAccountId"] == state["accounts"][0]["id"]
    assert state["accounts"][0]["canConnectQr"] is False
    assert "private-subject" not in repr(state)
    bridge._locked = True
    assert bridge.state()["activeAccountId"] is None
    bridge._locked = False
    service.active_riot_subject = lambda: "other-subject"
    bridge._poll_activity()
    assert bridge.state()["activeAccountId"] is None


def test_local_identity_read_uses_only_verified_lockfile_and_closes_transport(monkeypatch):
    from peaks.adapters.riot import client, discovery
    from peaks.application import runtime

    monkeypatch.setattr(runtime.platform, "system", lambda: "Windows")
    monkeypatch.setattr(discovery, "discover_riot_client", lambda: SimpleNamespace(lockfile=None))
    service = CurrentGameService()
    assert service.active_riot_subject() is None
    called = []
    class Local:
        def __init__(self, lockfile):
            assert lockfile == "verified-fixture"
        def get_json(self, path):
            called.append(path)
            return {"subject": "owned-subject", "accessToken": "private-token"}
        def close(self):
            called.append("close")
    monkeypatch.setattr(discovery, "discover_riot_client", lambda: SimpleNamespace(lockfile="verified-fixture"))
    monkeypatch.setattr(client, "RiotClientHTTP", Local)
    assert service.active_riot_subject() == "owned-subject"
    assert called == ["/entitlements/v1/token", "close"]


def test_public_act_fallback_binds_parent_ids_and_never_guesses_unknown_act_labels():
    rows = [
        {"uuid": "year", "displayName": "V26", "startTime": "2026-06-24T00:00:00Z", "endTime": "2027-01-06T00:00:00Z"},
        {"uuid": "act", "displayName": "ACT V", "type": "EAresSeasonType::Act", "parentUuid": "year", "startTime": "2026-08-19T00:00:00Z", "endTime": "2026-10-14T00:00:00Z"},
    ]
    now = datetime(2026, 9, 19, tzinfo=UTC)
    catalog = parse_public_seasons(rows, now=now)
    assert catalog.labels == {"act": "V26:A5"}
    assert catalog.active_id == "act"
    assert parse_public_seasons(rows, now=datetime(2027, 9, 19, tzinfo=UTC)).active_id is None
    rows[1]["parentUuid"] = "missing"
    assert parse_public_seasons(rows, now=now).labels == {}


def test_catalog_fallback_is_bounded_and_cached():
    from peaks.adapters.riot.client import RiotClientUnavailable
    from peaks.adapters.riot.valorant_enrichment import SeasonCatalog

    calls = []
    def unavailable(*args):
        raise RiotClientUnavailable("Unavailable")
    def fallback():
        calls.append("public")
        return SeasonCatalog({"act": "V26:A5"}, "act")
    client = SimpleNamespace(_get_json=unavailable)
    cache = ValorantEnrichmentCache(catalog_fallback=fallback)
    assert not cache.catalog(client, RequestBudget(remaining=0)).labels
    assert calls == []
    assert cache.catalog(client, RequestBudget(remaining=2)).active_id == "act"
    assert cache.catalog(client, RequestBudget(remaining=0)).active_id == "act"
    assert calls == ["public"]


def test_discovered_identity_is_bound_and_deleted_account_is_not_readded(monkeypatch):
    monkeypatch.setenv("PEAKS_DEMO", "1")
    bridge = Bridge()
    bridge.demo = False
    bridge._locked = False
    bridge.accounts = []
    bridge._repository = object()
    calls = []
    identity = SimpleNamespace(puuid="verified-owner")
    result = SimpleNamespace(identity=identity, source="local_client", cookies=None)
    bridge._account_onboarding_factory = lambda: SimpleNamespace(read_local_account=lambda: result)
    bridge._persist_authenticated_account = lambda value: calls.append(value)
    bridge._recognize_local_account("wrong-subject")
    assert calls == []
    bridge._next_local_recognition_at = 0
    bridge._recognize_local_account("verified-owner")
    assert calls == [result]
    calls.clear()
    bridge._next_local_recognition_at = 0
    bridge._dismissed_active_subject = "verified-owner"
    bridge._recognize_local_account("verified-owner")
    assert calls == []

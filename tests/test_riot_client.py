from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import requests

from peaks.adapters.riot.client import RiotClientError, RiotClientHTTP
from peaks.adapters.riot.discovery import (
    default_paths,
    discover_riot_client,
    discover_verified_league_lockfile,
    parse_lockfile,
    read_lockfile,
    validate_league_lockfile_process,
    validate_lockfile_process,
)
from peaks.adapters.riot.league import parse_live_game
from peaks.adapters.riot.valorant import (
    ValorantClient,
    ValorantMatchSummary,
    ValorantRemoteHTTP,
    parse_account_level,
    parse_competitive_updates_rank,
    parse_coregame,
    parse_match_details,
    parse_match_history,
    parse_player_names,
    parse_pregame,
    parse_rank,
)


class FakeResponse:
    def __init__(self, payload: object | None = None, status_code: int = 200) -> None:
        self.status_code = status_code
        self.headers = {"Content-Length": str(len(json.dumps(payload or {"ok": "yes"}).encode()))}
        self.content = json.dumps(payload or {"ok": "yes"}).encode()
        self.closed = False

    def raise_for_status(self) -> None:
        if not 200 <= self.status_code < 300:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> object:
        return json.loads(self.content)

    def iter_content(self, *, chunk_size: int) -> list[bytes]:
        del chunk_size
        return [self.content]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []
        self.trust_env = True
        self.closed = False
        self.response = FakeResponse()

    def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        return self.response

    def close(self) -> None:
        self.closed = True


def test_local_request_uses_loopback_tls_exception_and_auth_without_logging_secret() -> None:
    fake = FakeSession()
    client = RiotClientHTTP(parse_lockfile("riot-client:12:12345:topsecret:https"), session=fake)
    response = client.get_json("/entitlements/v1/token")
    assert response == {"ok": "yes"}
    method, url, kwargs = fake.calls[0]
    assert (method, url) == ("GET", "https://127.0.0.1:12345/entitlements/v1/token")
    assert kwargs["verify"] is False
    assert kwargs["stream"] is True
    assert kwargs["allow_redirects"] is False
    assert fake.trust_env is False
    assert fake.response.closed is True
    assert "topsecret" not in str(kwargs)


@pytest.mark.parametrize("fails", [False, True])
def test_http_diagnostics_never_include_paths_queries_or_provider_errors(
    fails: bool,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSession()
    if fails:

        def fail(*args: object, **kwargs: object) -> None:
            raise requests.ConnectionError("PRIVATE-ERROR token=PRIVATE-TOKEN")

        monkeypatch.setattr(fake, "request", fail)
    logger = logging.getLogger("test.riot_client_privacy")
    client = RiotClientHTTP(
        parse_lockfile("riot-client:12:12345:PRIVATE-PASSWORD:https"), session=fake, logger=logger
    )
    endpoint = "/players/PRIVATE-PUUID/matches/PRIVATE-MATCH?token=PRIVATE-TOKEN"
    with caplog.at_level(logging.DEBUG, logger=logger.name):
        if fails:
            with pytest.raises(RiotClientError):
                client.get_json(endpoint)
        else:
            client.get_json(endpoint)
    assert "PRIVATE" not in caplog.text
    assert "method=GET" in caplog.text
    assert ("riot_local.request.failed" if fails else "status=200") in caplog.text


def test_local_response_is_closed_and_bounded_before_json_parsing() -> None:
    fake = FakeSession()
    client = RiotClientHTTP(
        parse_lockfile("riot-client:12:12345:topsecret:https"),
        session=fake,
        max_response_bytes=4,
    )

    with pytest.raises(RiotClientError, match="size limit"):
        client.get_json("/entitlements/v1/token")

    # Content-Length is rejected before any body buffering, but the response
    # still gets closed by the deterministic response lifecycle.
    assert fake.calls
    assert fake.response.closed is True


def test_local_http_error_exposes_only_status_and_allowlisted_detail() -> None:
    fake = FakeSession()
    fake.response = FakeResponse(
        {
            "errorCode": "RPC_ERROR",
            "message": "Entitlements token is not ready yet",
        },
        status_code=400,
    )
    client = RiotClientHTTP(
        parse_lockfile("riot-client:12:12345:topsecret:https"),
        session=fake,
    )

    with pytest.raises(RiotClientError) as raised:
        client.get_json("/entitlements/v1/token")

    assert raised.value.status_code == 400
    assert raised.value.detail_code == "entitlements_not_ready"
    assert str(raised.value) == "Riot local endpoint returned HTTP 400"
    assert "Entitlements token" not in str(raised.value)
    assert fake.response.closed is True


def test_local_http_context_closes_session() -> None:
    fake = FakeSession()

    with RiotClientHTTP(parse_lockfile("riot-client:12:12345:pw:https"), session=fake):
        assert fake.trust_env is False
    assert fake.closed is True


def test_default_paths_are_empty_on_macos_without_environment() -> None:
    paths = default_paths(platform_name="Darwin", env={})
    assert paths.lockfile == ()
    result = discover_riot_client(platform_name="Darwin", env={})
    assert not result.supported
    assert result.lockfile is None
    assert not result.available


def test_windows_discovery_uses_localappdata_and_never_logs_password(tmp_path: Path) -> None:
    local = tmp_path / "Local App Data"
    lock_path = local / "Riot Games" / "Riot Client" / "Config" / "lockfile"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("riot-client:55:54321:not-for-logs:https\n", encoding="utf-8")
    paths = default_paths(platform_name="Windows", env={"LOCALAPPDATA": str(local)})
    result = discover_riot_client(
        platform_name="Windows",
        env={"LOCALAPPDATA": str(local)},
        paths=paths,
        process_names={"RiotClientServices.exe"},
    )
    assert result.available
    assert result.lockfile is not None
    assert result.lockfile.port == 54321
    assert read_lockfile(lock_path) == result.lockfile
    assert "not-for-logs" not in repr(result)


def test_lockfile_parser_accepts_bounded_spaced_riot_client_name() -> None:
    lockfile = parse_lockfile("Riot Client:55:54321:not-for-logs:https\n")

    assert lockfile.name == "Riot Client"
    assert lockfile.pid == 55
    assert lockfile.port == 54321
    assert "not-for-logs" not in repr(lockfile)

    with pytest.raises(ValueError, match="invalid process name"):
        parse_lockfile(f"{'Riot ' * 30}Client:55:54321:not-for-logs:https")


def test_windows_discovery_rejects_lockfile_without_matching_process(tmp_path: Path) -> None:
    local = tmp_path / "Local App Data"
    lock_path = local / "Riot Games" / "Riot Client" / "Config" / "lockfile"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("riot-client:55:54321:not-for-logs:https\n", encoding="utf-8")

    result = discover_riot_client(
        platform_name="Windows",
        env={"LOCALAPPDATA": str(local)},
        process_names=None,
        process_lookup=lambda _pid: None,
    )

    assert not result.available
    assert "could not be verified" in result.reason


def test_lockfile_process_validation_binds_pid_name_and_resolved_riot_path(tmp_path: Path) -> None:
    executable = tmp_path / "Riot Games" / "Riot Client" / "RiotClientServices.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    lock = parse_lockfile("riot-client:55:54321:not-for-logs:https")

    assert (
        validate_lockfile_process(
            lock,
            process_lookup=lambda pid: (
                ("RiotClientServices.exe", executable) if pid == 55 else None
            ),
        )
        == executable.resolve()
    )
    assert (
        validate_lockfile_process(
            lock,
            process_lookup=lambda _pid: ("Unrelated.exe", executable),
        )
        is None
    )


def test_verified_league_lockfile_binds_lcu_pid_and_riot_installation(tmp_path: Path) -> None:
    local = tmp_path / "Local App Data"
    lock_path = local / "Riot Games" / "League of Legends" / "Config" / "lockfile"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("LeagueClientUx:77:54322:lcu-secret:https\n", encoding="utf-8")
    executable = tmp_path / "Riot Games" / "League of Legends" / "LeagueClientUx.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"fixture")
    paths = default_paths(platform_name="Windows", env={"LOCALAPPDATA": str(local)})

    lockfile = discover_verified_league_lockfile(
        platform_name="Windows",
        paths=paths,
        process_lookup=lambda pid: ("LeagueClientUx.exe", executable) if pid == 77 else None,
    )

    assert lockfile is not None
    assert lockfile.port == 54322
    assert "lcu-secret" not in repr(lockfile)
    assert (
        validate_league_lockfile_process(
            lockfile,
            process_lookup=lambda _pid: ("Unrelated.exe", executable),
        )
        is None
    )


def test_verified_league_lockfile_is_disabled_off_windows(tmp_path: Path) -> None:
    paths = default_paths(platform_name="Darwin", env={})

    assert (
        discover_verified_league_lockfile(
            platform_name="Darwin",
            paths=paths,
            process_lookup=lambda _pid: pytest.fail("must not inspect processes"),
        )
        is None
    )


def test_verified_league_lockfile_finds_custom_install_sibling(tmp_path: Path) -> None:
    executable = tmp_path / "Riot Games" / "League of Legends" / "LeagueClientUx.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"fixture")
    (executable.parent / "lockfile").write_text(
        "LeagueClientUx:91:54323:custom-secret:https\n",
        encoding="utf-8",
    )

    lockfile = discover_verified_league_lockfile(
        platform_name="Windows",
        paths=default_paths(platform_name="Windows", env={}),
        process_identities=((91, "LeagueClientUx.exe", executable),),
    )

    assert lockfile is not None
    assert lockfile.pid == 91
    assert lockfile.port == 54323
    assert "custom-secret" not in repr(lockfile)


def test_valorant_remote_transport_keeps_tls_verification_enabled() -> None:
    fake = FakeSession()
    remote = ValorantRemoteHTTP(
        pd_url="https://pd.eu.a.pvp.net",
        glz_url="https://glz-eu1.eu.a.pvp.net",
        headers={"Authorization": "Bearer access", "X-Riot-Entitlements-JWT": "entitlement"},
        session=fake,
    )
    assert remote.get_json("glz", "/pregame/v1/players/puuid") == {"ok": "yes"}
    _, url, kwargs = fake.calls[0]
    assert url == "https://glz-eu1.eu.a.pvp.net/pregame/v1/players/puuid"
    assert kwargs["verify"] is True
    assert kwargs["stream"] is True
    assert kwargs["allow_redirects"] is False
    assert fake.trust_env is False


def test_valorant_remote_rejects_ipv6_loopback_and_closes_oversized_response() -> None:
    with pytest.raises(ValueError, match="must not be loopback"):
        ValorantRemoteHTTP(
            pd_url="https://[::1]",
            glz_url="https://glz-eu1.eu.a.pvp.net",
            headers={},
        )

    fake = FakeSession()
    remote = ValorantRemoteHTTP(
        pd_url="https://pd.eu.a.pvp.net",
        glz_url="https://glz-eu1.eu.a.pvp.net",
        headers={},
        session=fake,
        max_response_bytes=4,
    )
    with pytest.raises(RiotClientError, match="size limit"):
        remote.get_json("glz", "/pregame/v1/players/puuid")


def test_liveclientdata_parser_handles_actual_nested_league_shape() -> None:
    game = parse_live_game(
        {
            "gameData": {
                "gameMode": "CLASSIC",
                "mapName": "Map11",
                "gameTime": 91.5,
            },
            "allPlayers": [{"summonerName": "Masked", "championName": "Ahri", "team": "ORDER"}],
        }
    )
    assert game is not None and game.game == "league"
    assert game.map_name == "Map11"
    assert game.players[0].name == "Masked"


def test_valorant_pregame_coregame_and_peak_rank_parsers() -> None:
    pregame = parse_pregame(
        {
            "ID": "pre-1",
            "MapID": "/Game/Maps/Ascent/Ascent",
            "AllyTeam": {"Players": [{"Subject": "puuid", "PlayerIdentity": {"Incognito": True}}]},
        }
    )
    coregame = parse_coregame(
        {"MatchID": "core-1", "MapID": "ascent", "Players": [{"Subject": "puuid"}]}
    )
    rank = parse_rank(
        {
            "QueueSkills": {
                "competitive": {
                    "SeasonalInfoBySeasonID": {
                        "current": {"CompetitiveTier": 21, "RankedRating": 48},
                        "previous": {"CompetitiveTier": 24},
                    }
                }
            }
        },
        "current",
    )
    assert pregame is not None and pregame.match_id == "pre-1" and pregame.players[0].incognito
    assert coregame is not None and coregame.match_id == "core-1"
    assert rank.name == "Ascendant 1" and rank.rr == 48 and rank.peak_name == "Immortal 1"


def test_valorant_rank_resolves_active_season_instead_of_mapping_order() -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, endpoint: str) -> object:
            self.calls.append(endpoint)
            if endpoint == "/mmr/v1/players/owned-puuid":
                return {
                    "QueueSkills": {
                        "competitive": {
                            "SeasonalInfoBySeasonID": {
                                "old-season": {"CompetitiveTier": 0, "RankedRating": 0},
                                "current-season": {"CompetitiveTier": 19, "RankedRating": 62},
                            }
                        }
                    }
                }
            return {
                "Matches": [
                    {
                        "SeasonID": "current-season",
                        "TierAfterUpdate": 19,
                        "RankedRatingAfterUpdate": 61,
                    }
                ]
            }

    local = FakeLocal()

    rank = ValorantClient(local, "owned-puuid").rank_optional()  # type: ignore[arg-type]

    assert rank is not None and (rank.name, rank.rr) == ("Diamond 2", 62)
    assert local.calls == [
        "/mmr/v1/players/owned-puuid",
        "/mmr/v1/players/owned-puuid/competitiveupdates?startIndex=0&endIndex=20&queue=competitive",
    ]


def test_valorant_name_parser_returns_only_requested_riot_ids() -> None:
    names = parse_player_names(
        [
            {"Subject": "visible-puuid", "GameName": "Visible", "TagLine": "EUW"},
            {"Subject": "other-puuid", "DisplayName": "Must not escape"},
            {"Subject": "fallback-puuid", "DisplayName": "Fallback#NA"},
        ],
        ["visible-puuid", "fallback-puuid"],
    )

    assert names == {
        "visible-puuid": "Visible#EUW",
        "fallback-puuid": "Fallback#NA",
    }


def test_competitive_updates_rank_uses_newest_valid_row_without_retaining_ids() -> None:
    rank = parse_competitive_updates_rank(
        {
            "Subject": "private-account-subject",
            "Matches": [
                {
                    "MatchID": "private-newest-match",
                    "SeasonID": "current-season",
                    "TierAfterUpdate": 21,
                    "RankedRatingAfterUpdate": 48,
                    "TierBeforeUpdate": 20,
                },
                {
                    "MatchID": "private-older-match",
                    "SeasonID": "previous-season",
                    "TierAfterUpdate": 24,
                    "RankedRatingAfterUpdate": 12,
                    "TierBeforeUpdate": 24,
                },
            ],
        }
    )

    assert rank is not None
    assert (rank.name, rank.rr, rank.peak_name, rank.season_id) == (
        "Ascendant 1",
        48,
        "Immortal 1",
        "previous-season",
    )
    assert "private-account-subject" not in repr(rank)
    assert "private-newest-match" not in repr(rank)


def test_competitive_updates_rank_is_bounded_and_rejects_unknown_tiers() -> None:
    matches = [
        {
            "SeasonID": "current",
            "TierAfterUpdate": 999,
            "RankedRatingAfterUpdate": 50,
        }
        for _ in range(20)
    ]
    matches.append(
        {
            "SeasonID": "current",
            "TierAfterUpdate": 21,
            "RankedRatingAfterUpdate": 50,
        }
    )

    assert parse_competitive_updates_rank({"Matches": matches}, limit=200) is None


def test_valorant_match_history_is_bounded_and_drops_private_payload_fields() -> None:
    history = parse_match_history(
        {
            "Subject": "must-not-return",
            "History": [
                {
                    "MatchID": "match-1",
                    "QueueID": "competitive",
                    "GameStartTime": 1_777_777_777_000,
                    "Players": [{"Subject": "another-player"}],
                },
                {"MatchID": "match-2", "QueueID": "unrated"},
            ],
        },
        limit=1,
    )

    assert len(history) == 1
    assert history[0].match_id == "match-1"
    assert history[0].queue_id == "competitive"
    assert history[0].started_at_ms == 1_777_777_777_000
    assert "Subject" not in repr(history)
    assert "another-player" not in repr(history)


def test_valorant_match_details_keep_only_own_result_map_score_and_timing() -> None:
    summary = parse_match_details(
        {
            "matchInfo": {
                "matchId": "match-1",
                "mapId": "/Game/Maps/Ascent/Ascent",
                "queueID": "competitive",
                "gameStartMillis": 1_777_777_777_000,
                "gameLengthMillis": 2_345_000,
            },
            "players": [
                {"subject": "owned-puuid", "teamId": "Blue"},
                {"subject": "another-player", "teamId": "Red"},
            ],
            "teams": [
                {"teamId": "Blue", "won": True, "roundsWon": 13},
                {"teamId": "Red", "won": False, "roundsWon": 9},
            ],
        },
        puuid="owned-puuid",
        fallback=ValorantMatchSummary("match-1"),
    )

    assert summary.map_id == "/Game/Maps/Ascent/Ascent"
    assert summary.result == "win"
    assert (summary.own_score, summary.opponent_score) == (13, 9)
    assert summary.duration_seconds == 2_345
    assert "owned-puuid" not in repr(summary)
    assert "another-player" not in repr(summary)


def test_completed_match_details_resolve_identities_independently_of_live_incognito() -> None:
    summary = parse_match_details(
        {
            "matchInfo": {"matchId": "match-1"},
            "players": [
                {
                    "subject": "owned-puuid",
                    "teamId": "Blue",
                    "gameName": "Owner",
                    "tagLine": "EUW",
                    "characterId": "sova-id",
                    "competitiveTier": 23,
                    "stats": {
                        "kills": 21,
                        "deaths": 12,
                        "assists": 8,
                        "score": 286,
                        "roundsPlayed": 21,
                        "headshots": 16,
                        "bodyshots": 31,
                        "legshots": 4,
                    },
                    "roundDamage": [{"damage": 210}, {"damage": 190}],
                },
                {
                    "subject": "visible-puuid",
                    "teamId": "Red",
                    "characterId": "omen-id",
                    "stats": {"kills": 14, "deaths": 17, "assists": 5},
                },
                {
                    "subject": "hidden-puuid",
                    "teamId": "Red",
                    "gameName": "MustNotLeak",
                    "tagLine": "HIDE",
                    "isIncognito": True,
                    "stats": {"kills": 9, "deaths": 18, "assists": 2},
                },
            ],
            "teams": [
                {"teamId": "Blue", "won": True, "roundsWon": 13},
                {"teamId": "Red", "won": False, "roundsWon": 8},
            ],
        },
        puuid="owned-puuid",
        fallback=ValorantMatchSummary("match-1"),
        names={"visible-puuid": "Visible#EUW", "hidden-puuid": "Leaked#HIDE"},
    )

    assert [team.name for team in summary.teams] == ["Your team", "Opponents"]
    owner = summary.teams[0].players[0]
    assert owner.riot_id == "Owner#EUW"
    assert owner.competitive_tier == 23
    assert (owner.kills, owner.deaths, owner.assists) == (21, 12, 8)
    assert owner.damage == 400
    assert summary.teams[1].players[0].riot_id == "Visible#EUW"
    hidden = summary.teams[1].players[1]
    assert hidden.hidden is False
    assert hidden.riot_id == "MustNotLeak#HIDE"
    assert "hidden-puuid" not in repr(summary)
    assert "Leaked#HIDE" not in repr(summary)


def test_match_round_analytics_fill_missing_stats_and_preserve_total_combat_score() -> None:
    payload = {
        "matchInfo": {"matchId": "match-1"},
        "players": [
            {
                "subject": "owned-puuid",
                "teamId": "Blue",
                "stats": {"score": 600, "roundsPlayed": 2, "headshots": 1, "kills": 1},
            }
        ],
        "roundResults": [
            {
                "roundNum": 0,
                "playerStats": [
                    {
                        "subject": "owned-puuid",
                        "kills": [
                            {
                                "killer": "owned-puuid",
                                "victim": "opponent",
                                "timeSinceRoundStartMillis": 1000,
                                "finishingDamage": {
                                    "damageType": "Weapon",
                                    "damageItem": "9c82e19d-4575-0200-1a81-3eacf00cf872",
                                },
                            }
                        ],
                        "damage": [{"headshots": 1, "bodyshots": 2, "legshots": 3, "damage": 150}],
                    }
                ],
            },
            {
                "roundNum": 1,
                "playerStats": [{"subject": "owned-puuid", "kills": [], "damage": []}],
            },
        ],
    }
    summary = parse_match_details(
        payload, puuid="owned-puuid", fallback=ValorantMatchSummary("match-1")
    )
    player = summary.teams[0].players[0]
    assert player.combat_score == 600
    assert player.headshots == 1
    assert (player.bodyshots, player.legshots, player.damage) == (2, 3, 150)
    assert player.weapon_usage == (("Vandal", 1),)
    assert player.round_kills == (1, 0)
    assert "owned-puuid" not in repr(summary)

    payload["players"][0]["stats"]["kills"] = 5  # type: ignore[index]
    mismatched = parse_match_details(
        payload, puuid="owned-puuid", fallback=ValorantMatchSummary("match-1")
    )
    assert mismatched.teams[0].players[0].round_kills is None
    assert mismatched.teams[0].players[0].weapon_usage is None
    assert mismatched.teams[0].players[0].bodyshots == 2

    payload["players"][0]["stats"]["headshots"] = 9  # type: ignore[index]
    conflicting = parse_match_details(
        payload, puuid="owned-puuid", fallback=ValorantMatchSummary("match-1")
    )
    assert conflicting.teams[0].players[0].headshots == 9
    assert conflicting.teams[0].players[0].bodyshots is None
    assert conflicting.teams[0].players[0].legshots is None

    payload["players"][0]["stats"]["roundsPlayed"] = 3  # type: ignore[index]
    partial = parse_match_details(
        payload, puuid="owned-puuid", fallback=ValorantMatchSummary("match-1")
    )
    partial_player = partial.teams[0].players[0]
    assert partial_player.headshots == 9
    assert partial_player.bodyshots is None
    assert partial_player.weapon_usage is None
    assert partial_player.round_kills is None


def test_valorant_client_requests_only_its_own_bounded_match_history() -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, endpoint: str) -> object:
            self.calls.append(endpoint)
            if endpoint.startswith("/match-history/"):
                return {"History": [{"MatchID": "match-1", "QueueID": "competitive"}]}
            return {
                "matchInfo": {"matchId": "match-1", "mapId": "/Game/Maps/Ascent/Ascent"},
                "players": [{"subject": "owned-puuid", "teamId": "Blue"}],
                "teams": [{"teamId": "Blue", "won": True, "roundsWon": 13}],
            }

    local = FakeLocal()

    history = ValorantClient(local, "owned-puuid").match_history(limit=200)  # type: ignore[arg-type]

    assert local.calls == [
        "/match-history/v1/history/owned-puuid?startIndex=0&endIndex=20",
        "/match-details/v1/matches/match-1",
    ]
    assert [match.match_id for match in history] == ["match-1"]
    assert history[0].map_id == "/Game/Maps/Ascent/Ascent"
    assert history[0].result == "win"


@pytest.mark.parametrize(
    ("payload", "status_code", "available"),
    [
        ({"errorCode": "RESOURCE_NOT_FOUND"}, 404, True),
        ({"errorCode": "RESOURCE_NOT_FOUND"}, 200, True),
        ({"errorCode": "RESOURCE_NOT_FOUND"}, 503, False),
        ({"errorCode": "UNAUTHORIZED"}, 401, False),
        ({"message": "Not found"}, 404, False),
        ({"unexpected": "payload"}, 200, False),
    ],
)
def test_valorant_idle_requires_explicit_missing_match_responses(
    payload: object,
    status_code: int,
    available: bool,
) -> None:
    fake = FakeSession()
    fake.response = FakeResponse(payload, status_code)
    remote = ValorantRemoteHTTP(
        pd_url="https://pd.eu.a.pvp.net",
        glz_url="https://glz-eu1.eu.a.pvp.net",
        headers={"Authorization": "Bearer access"},
        session=fake,
    )
    client = ValorantClient(remote, "owned-puuid")

    assert client.detect() is None
    assert client.activity_available is available
    assert len(fake.calls) == 2


def test_valorant_partial_idle_with_transient_failure_is_not_match_end() -> None:
    class FakeLocal:
        def get_json(self, endpoint: str) -> object:
            if endpoint.startswith("/core-game/"):
                raise RiotClientError("temporary failure", status_code=503)
            return {"errorCode": "RESOURCE_NOT_FOUND"}

    client = ValorantClient(FakeLocal(), "owned-puuid")  # type: ignore[arg-type]

    assert client.detect() is None
    assert client.activity_available is False


def test_valorant_changed_match_detail_id_is_not_presented_as_live() -> None:
    class FakeLocal:
        def get_json(self, endpoint: str) -> object:
            if endpoint.startswith("/pregame/"):
                return {"errorCode": "RESOURCE_NOT_FOUND"}
            if "/players/" in endpoint:
                return {"MatchID": "requested-match"}
            return {"ID": "different-match", "Players": []}

    client = ValorantClient(FakeLocal(), "owned-puuid")  # type: ignore[arg-type]

    assert client.detect() is None
    assert client.activity_available is False


def test_valorant_client_resolves_bounded_live_names_with_put() -> None:
    fake = FakeSession()
    fake.response = FakeResponse(
        [
            {"Subject": "visible-puuid", "GameName": "Visible", "TagLine": "EUW"},
            {"Subject": "unrequested-puuid", "DisplayName": "Do not return"},
        ]
    )
    remote = ValorantRemoteHTTP(
        pd_url="https://pd.eu.a.pvp.net",
        glz_url="https://glz-eu1.eu.a.pvp.net",
        headers={"Authorization": "Bearer access"},
        session=fake,
    )

    names = ValorantClient(remote, "owned-puuid").player_names(
        ["visible-puuid", "bad subject!", "visible-puuid"]
    )

    assert names == {"visible-puuid": "Visible#EUW"}
    method, url, kwargs = fake.calls[0]
    assert method == "PUT"
    assert url == "https://pd.eu.a.pvp.net/name-service/v2/players"
    assert kwargs["json"] == ["visible-puuid"]
    assert kwargs["verify"] is True


def test_valorant_client_reads_only_bounded_live_roster_ranks() -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, endpoint: str) -> object:
            self.calls.append(endpoint)
            return {"CompetitiveTier": 23, "RankedRating": 72}

    local = FakeLocal()
    ranks = ValorantClient(local, "owned-puuid").live_player_ranks(  # type: ignore[arg-type]
        ["visible-puuid", "bad subject!", "visible-puuid"]
    )

    assert ranks["visible-puuid"].name == "Ascendant 3"
    assert local.calls == ["/mmr/v1/players/visible-puuid"]


def test_valorant_match_history_retries_one_transient_page_failure() -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.history_attempts = 0

        def get_json(self, endpoint: str) -> object:
            if endpoint.startswith("/match-history/"):
                self.history_attempts += 1
                if self.history_attempts == 1:
                    raise RiotClientError("transient")
                return {"History": [{"MatchID": "match-1"}]}
            return {"matchInfo": {"matchId": "match-1"}}

    local = FakeLocal()

    history = ValorantClient(local, "owned-puuid").match_history()  # type: ignore[arg-type]

    assert local.history_attempts == 2
    assert [match.match_id for match in history] == ["match-1"]


def test_valorant_rank_falls_back_to_bounded_competitive_updates(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, endpoint: str) -> object:
            self.calls.append(endpoint)
            if endpoint == "/mmr/v1/players/owned-puuid":
                raise RiotClientError("primary response body must not be logged")
            return {
                "Subject": "owned-puuid",
                "Matches": [
                    {
                        "MatchID": "private-match-id",
                        "SeasonID": "current",
                        "TierAfterUpdate": 19,
                        "RankedRatingAfterUpdate": 62,
                        "TierBeforeUpdate": 19,
                    }
                ],
            }

    local = FakeLocal()
    caplog.set_level(logging.INFO, logger="peaks.adapters.riot.valorant")

    rank = ValorantClient(local, "owned-puuid").rank_optional()  # type: ignore[arg-type]

    assert rank is not None and (rank.name, rank.rr) == ("Diamond 2", 62)
    assert local.calls == [
        "/mmr/v1/players/owned-puuid",
        "/mmr/v1/players/owned-puuid/competitiveupdates?startIndex=0&endIndex=20&queue=competitive",
    ]
    assert "owned-puuid" not in caplog.text
    assert "private-match-id" not in caplog.text
    assert "response body" not in caplog.text


def test_valorant_rank_does_not_request_fallback_when_primary_succeeds() -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, endpoint: str) -> object:
            self.calls.append(endpoint)
            return {"CompetitiveTier": 21, "RankedRating": 48}

    local = FakeLocal()

    rank = ValorantClient(local, "owned-puuid").rank_optional()  # type: ignore[arg-type]

    assert rank is not None and (rank.name, rank.rr) == ("Ascendant 1", 48)
    assert local.calls == ["/mmr/v1/players/owned-puuid"]


def test_valorant_account_level_is_bounded_and_subject_bound() -> None:
    assert (
        parse_account_level(
            {"Subject": "owned-puuid", "Progress": {"Level": 284, "XP": 9876}},
            expected_subject="owned-puuid",
        )
        == 284
    )
    assert (
        parse_account_level(
            {"Subject": "different-puuid", "Progress": {"Level": 284}},
            expected_subject="owned-puuid",
        )
        is None
    )
    assert parse_account_level({"Progress": {"Level": 100_001}}) is None
    assert parse_account_level({"Progress": {"Level": True}}) is None


def test_valorant_client_reads_only_own_account_level_endpoint() -> None:
    class FakeLocal:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def get_json(self, endpoint: str) -> object:
            self.calls.append(endpoint)
            return {"Subject": "owned-puuid", "Progress": {"Level": 284, "XP": 9876}}

    local = FakeLocal()

    level = ValorantClient(local, "owned-puuid").account_level_optional()  # type: ignore[arg-type]

    assert level == 284
    assert local.calls == ["/account-xp/v1/players/owned-puuid"]

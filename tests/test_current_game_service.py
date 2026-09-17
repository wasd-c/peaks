from __future__ import annotations

import io
import logging
import platform
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import peaks.adapters.riot.client as riot_client
import peaks.adapters.riot.discovery as riot_discovery
import peaks.adapters.riot.league as league_adapter
import peaks.adapters.riot.valorant as valorant_adapter
from peaks.adapters.riot.league import GamePlayer, LiveGame
from peaks.adapters.riot.valorant import (
    ValorantCoregame,
    ValorantMatchPlayer,
    ValorantMatchSummary,
    ValorantMatchTeam,
    ValorantPlayer,
    ValorantPregame,
    ValorantRank,
)
from peaks.application.runtime import CurrentGameService


def test_non_windows_detection_is_an_explicit_disabled_no_game_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Windows-only local integration must not probe Riot on macOS/Linux."""

    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    service = CurrentGameService()

    assert service.detect() is None
    assert service.client_status == {
        "detected": False,
        "label": "Riot local integration is available on Windows",
        "path": "",
        "game": "",
    }


def test_valorant_service_info_parser_reads_region_urls_and_client_version(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "ShooterGame.log"
    log_path.write_text(
        "\n".join(
            [
                "[Info] connecting to https://pd.eu.a.pvp.net/account-xp/v1/player",
                "[Info] connecting to https://glz-eu1.eu.a.pvp.net",
                "[Info] CI server version: 12.05.00.1234-shipping",
            ]
        ),
        encoding="utf-8",
    )

    assert CurrentGameService._valorant_service_info(log_path) == (
        "https://pd.eu.a.pvp.net",
        "https://glz-eu1.eu.a.pvp.net",
        "12.05.00.1234-shipping",
    )


def test_valorant_service_info_parser_accepts_account_xp_host_variant(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "ShooterGame.log"
    log_path.write_text(
        "GET https://service.na.a.pvp.net/account-xp/v1/player\n"
        "GET https://glz-na1.na.a.pvp.net\n"
        "CI server version: 11.02.01.9876\n",
        encoding="utf-8",
    )

    assert CurrentGameService._valorant_service_info(log_path) == (
        "https://pd.na.a.pvp.net",
        "https://glz-na1.na.a.pvp.net",
        "11.02.01.9876",
    )


def test_valorant_service_info_keeps_startup_version_after_log_exceeds_tail_window(
    tmp_path: Path,
) -> None:
    """A long active match must not push the one-time version line out of view."""

    log_path = tmp_path / "ShooterGame.log"
    startup = (
        b"CI server version: release-13.04-shipping-20-5340415\n"
        b"https://pd.na.a.pvp.net/account-xp/v1/player\n"
        b"https://glz-na-1.na.a.pvp.net/session/v1/sessions/old\n"
    )
    current = (
        b"https://pd.eu.a.pvp.net/name-service/v2/players\n"
        b"https://glz-eu-1.eu.a.pvp.net/core-game/v1/players/current\n"
    )
    # The production parser intentionally reads at most 1 MiB from the head
    # and 8 MiB from the tail. Put the version outside the latter so this test
    # catches regressions back to a tail-only read.
    with log_path.open("wb") as stream:
        stream.write(startup)
        stream.write(b"x" * (8 * 1024 * 1024 + 1024))
        stream.write(current)

    assert CurrentGameService._valorant_service_info(log_path) == (
        "https://pd.eu.a.pvp.net",
        "https://glz-eu-1.eu.a.pvp.net",
        "release-13.04-shipping-20-5340415",
    )


@pytest.mark.parametrize(
    ("map_id", "expected"),
    [
        (None, "Unknown map"),
        ("", "Unknown map"),
        ("/Game/Maps/Ascent/Ascent", "Ascent"),
        (r"Game\\Maps\\icebox\\icebox", "Icebox"),
        ("fracture", "Fracture"),
        ("/", "Unknown map"),
    ],
)
def test_valorant_map_name_formatting(map_id: str | None, expected: str) -> None:
    assert CurrentGameService._valorant_map_name(map_id) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "—"),
        (-10, "0:00"),
        (0, "0:00"),
        (91.9, "1:31"),
        (3661.9, "61:01"),
    ],
)
def test_elapsed_time_formatting(seconds: float | None, expected: str) -> None:
    assert CurrentGameService._format_elapsed(seconds) == expected


def test_league_team_normalization_hides_private_names_and_preserves_teams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Current-game payloads retain team structure without deanonymizing players."""

    class FakeDiscovery:
        process_running = True
        available = True
        reason = "Riot Client detected"
        executable = None
        lockfile = None

    class FakeLeagueClient:
        @classmethod
        def from_discovery(cls) -> FakeLeagueClient:
            return cls()

        def current_game(self) -> LiveGame:
            return LiveGame(
                game="league",
                game_mode="CLASSIC",
                map_name="Map11",
                game_time=91.9,
                players=(
                    GamePlayer(name=None, champion="Ahri", team="ORDER"),
                    GamePlayer(name="Anonymous", champion="Lux", team="ORDER"),
                    GamePlayer(name="Ally", champion="Garen", team="CHAOS"),
                ),
            )

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(riot_discovery, "discover_riot_client", lambda: FakeDiscovery())
    monkeypatch.setattr(league_adapter, "LeagueClient", FakeLeagueClient)

    current = CurrentGameService().detect()

    assert current is not None
    assert current["streamerMode"] is True
    assert current["elapsed"] == "1:31"
    assert current["privacyNote"] == "Streamer mode respected — hidden identities stay hidden."
    assert [team["name"] for team in current["teams"]] == ["ORDER", "CHAOS"]
    order_players = current["teams"][0]["players"]
    assert [player["name"] for player in order_players] == [
        "Hidden player 1",
        "Hidden player 2",
    ]
    assert order_players[0]["agent"] == "Ahri"
    assert order_players[1]["agent"] == "Lux"
    assert current["teams"][1]["players"][0]["name"] == "Ally"
    assert "Anonymous" not in repr(current)


def test_valorant_service_info_parser_returns_none_for_missing_or_incomplete_log(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.log"
    incomplete = tmp_path / "incomplete.log"
    incomplete.write_text("https://pd.eu.a.pvp.net\n", encoding="utf-8")

    assert CurrentGameService._valorant_service_info(missing) is None
    assert CurrentGameService._valorant_service_info(incomplete) is None


def test_valorant_live_names_respect_incognito_and_cache_exact_ranks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = ValorantCoregame(
        "match-1",
        "/Game/Maps/Ascent/Ascent",
        None,
        (
            ValorantPlayer("owned-puuid", "Blue", "agent-one"),
            ValorantPlayer("visible-puuid", "Red", "agent-two"),
            ValorantPlayer("hidden-puuid", "Red", "agent-three", incognito=True),
        ),
    )

    name_calls: list[tuple[str, ...]] = []
    rank_calls: list[tuple[str, ...]] = []

    class FakeClient:

        def detect(self) -> ValorantCoregame:
            return match

        def rank(self) -> ValorantRank:
            return ValorantRank(23, "Ascendant 3", 72)

        def player_names(self, subjects: tuple[str, ...]) -> dict[str, str]:
            name_calls.append(subjects)
            return {
                "owned-puuid": "Owner#EUW",
                "visible-puuid": "Visible#EUW",
                "hidden-puuid": "MustNeverRender#EUW",
            }

        def live_player_ranks(self, subjects: tuple[str, ...]) -> dict[str, ValorantRank]:
            rank_calls.append(subjects)
            return {
                "visible-puuid": ValorantRank(18, "Diamond 1", 10),
                "hidden-puuid": ValorantRank(0, "Unranked"),
            }

    class FakeContext:
        def __enter__(self) -> tuple[FakeClient, str]:
            return FakeClient(), "owned-puuid"

        def __exit__(self, *args: object) -> None:
            return None

    service = CurrentGameService()
    monkeypatch.setattr(service, "_open_valorant_client", lambda _discovery: FakeContext())
    monkeypatch.setattr(
        service,
        "_valorant_agent_names",
        lambda: {
            "agent-one": "Jett",
            "agent-two": "Omen",
            "agent-three": "Sage",
        },
    )

    current = service._detect_valorant(object())
    repeated = service._detect_valorant(object())

    assert current is not None and repeated is not None
    assert current["id"] == "match-1"
    assert current["phase"] == "live"
    assert service.detection_available is True
    assert service.active_account_puuid == "owned-puuid"
    assert "owned-puuid" not in repr(current)
    blue = current["teams"][0]["players"][0]
    red = current["teams"][1]["players"]
    assert (blue["name"], blue["rank"], blue["rankTier"]) == (
        "Owner#EUW",
        "Ascendant 3",
        23,
    )
    assert (red[0]["name"], red[0]["rank"]) == ("Visible#EUW", "Diamond 1")
    assert red[0]["hidden"] is False
    assert (red[1]["name"], red[1]["rank"]) == ("Hidden player 1", "Unranked")
    assert red[1]["hidden"] is True
    assert name_calls == [("owned-puuid", "visible-puuid")]
    assert rank_calls == [("visible-puuid", "hidden-puuid")]
    assert "MustNeverRender" not in repr(current)


def test_valorant_pregame_is_identified_without_arming_live_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    match = ValorantPregame("pending-match", None, None, ())
    client = SimpleNamespace(detect=lambda: match, rank=lambda: None)
    context = MagicMock()
    context.__enter__.return_value = (client, "owned-puuid")
    service = CurrentGameService()
    monkeypatch.setattr(service, "_open_valorant_client", lambda _discovery: context)
    monkeypatch.setattr(service, "_valorant_agent_names", lambda: {})

    current = service._detect_valorant(object())

    assert current is not None
    assert current["id"] == "pending-match"
    assert current["phase"] == "pregame"
    assert current["mode"] == "Agent select"
    assert service.detection_available is True


@pytest.mark.parametrize("available", [True, False])
def test_valorant_no_match_preserves_detection_confidence(
    monkeypatch: pytest.MonkeyPatch, available: bool,
) -> None:
    client = SimpleNamespace(detect=lambda: None, activity_available=available)
    context = MagicMock()
    context.__enter__.return_value = (client, "owned-puuid")
    service = CurrentGameService()
    monkeypatch.setattr(service, "_open_valorant_client", lambda _discovery: context)

    assert service._detect_valorant(object()) is None
    assert service.detection_available is available


def test_owned_valorant_rank_requires_local_entitlement_subject_and_closes_tokens(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An authenticated local client may only query its own PUUID."""

    log_path = tmp_path / "ShooterGame.log"
    log_path.write_text(
        "https://pd.eu.a.pvp.net/account-xp/v1/player\n"
        "https://glz-eu1.eu.a.pvp.net\n",
        encoding="utf-8",
    )
    lockfile = SimpleNamespace(password="secret", port=1234, base_url="https://127.0.0.1:1234")
    discovery = SimpleNamespace(lockfile=lockfile)
    local_calls: list[str] = []
    remote_instances: list[object] = []

    class FakeLocal:
        def __init__(self, received_lockfile: object) -> None:
            assert received_lockfile is lockfile

        def get_json(self, endpoint: str) -> dict[str, str]:
            local_calls.append(endpoint)
            if endpoint == "/product-session/v1/external-sessions":
                return {
                    "game-session": {  # type: ignore[dict-item]
                        "phase": "Gameplay",
                        "productId": "valorant",
                        "version": "release-13.04-shipping-20-5340415",
                    }
                }
            return {
                "accessToken": "access-token",
                "token": "entitlements-token",
                "subject": "owned-puuid",
            }

        def close(self) -> None:
            local_calls.append("closed")

    class FakeRemote:
        def __init__(self, **kwargs: object) -> None:
            headers = kwargs.get("headers")
            assert isinstance(headers, dict)
            assert headers["X-Riot-ClientVersion"] == "release-13.04-shipping-20-5340415"
            self.kwargs = kwargs
            remote_instances.append(self)

        def close(self) -> None:
            self.kwargs.clear()

    class FakeValorantClient:
        def __init__(self, remote: object, puuid: str) -> None:
            assert remote is remote_instances[0]
            assert puuid == "owned-puuid"

        def rank_optional(self) -> ValorantRank:
            return ValorantRank(21, "Ascendant 1", 48, 24, "Immortal 1", "current")

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(riot_discovery, "discover_riot_client", lambda: discovery)
    monkeypatch.setattr(riot_discovery, "valorant_log_path", lambda: log_path)
    monkeypatch.setattr(riot_client, "RiotClientHTTP", FakeLocal)
    monkeypatch.setattr(valorant_adapter, "ValorantRemoteHTTP", FakeRemote)
    monkeypatch.setattr(valorant_adapter, "ValorantClient", FakeValorantClient)

    result = CurrentGameService().owned_valorant_rank("owned-puuid")

    assert result == ValorantRank(21, "Ascendant 1", 48, 24, "Immortal 1", "current")
    assert local_calls == [
        "/product-session/v1/external-sessions",
        "/entitlements/v1/token",
        "closed",
    ]
    assert len(remote_instances) == 1
    assert remote_instances[0].kwargs == {}


def test_owned_valorant_rank_fails_closed_on_subject_mismatch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lockfile = SimpleNamespace(password="secret", port=1234, base_url="https://127.0.0.1:1234")
    discovery = SimpleNamespace(lockfile=lockfile)
    remote_constructed = False

    class FakeLocal:
        def __init__(self, received_lockfile: object) -> None:
            assert received_lockfile is lockfile

        def get_json(self, endpoint: str) -> dict[str, str]:
            assert endpoint == "/entitlements/v1/token"
            return {
                "accessToken": "access-token",
                "token": "entitlements-token",
                "subject": "another-puuid",
            }

        def close(self) -> None:
            return None

    def forbidden_remote(**kwargs: object) -> object:
        nonlocal remote_constructed
        remote_constructed = True
        raise AssertionError("a mismatched local session must not open the remote service")

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(riot_discovery, "discover_riot_client", lambda: discovery)
    monkeypatch.setattr(riot_discovery, "valorant_log_path", lambda: tmp_path / "missing.log")
    monkeypatch.setattr(riot_client, "RiotClientHTTP", FakeLocal)
    monkeypatch.setattr(valorant_adapter, "ValorantRemoteHTTP", forbidden_remote)

    assert CurrentGameService().owned_valorant_rank("owned-puuid") is None
    assert remote_constructed is False


def test_owned_valorant_rank_is_disabled_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    def forbidden_discovery() -> object:
        raise AssertionError("off-Windows rank lookup must not probe Riot")

    monkeypatch.setattr(riot_discovery, "discover_riot_client", forbidden_discovery)

    assert CurrentGameService().owned_valorant_rank("owned-puuid") is None


def test_owned_valorant_snapshot_returns_only_rank_and_bounded_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = SimpleNamespace(lockfile=object())

    class FakeClient:
        def account_level_optional(self) -> int:
            return 284

        def rank_optional(self) -> ValorantRank:
            return ValorantRank(21, "Ascendant 1", 48, 24, "Immortal 1")

        def match_history(self, *, limit: int) -> tuple[ValorantMatchSummary, ...]:
            assert limit == 20
            return (
                ValorantMatchSummary(
                    "match-1",
                    "competitive",
                    1_777_777_777_000,
                    teams=(
                        ValorantMatchTeam(
                            "Your team",
                            13,
                            True,
                            (
                                ValorantMatchPlayer(
                                    riot_id="Visible#EUW",
                                    character_id="sova-id",
                                    competitive_tier=23,
                                    kills=21,
                                    deaths=12,
                                    assists=8,
                                    combat_score=286,
                                    self=True,
                                    weapon_usage=(("Vandal", 2),),
                                    round_kills=(2, 0),
                                    rounds_played=3,
                                    rounds_analyzed=2,
                                    stats_loading=True,
                                ),
                            ),
                        ),
                    ),
                ),
            )

    class FakeContext:
        def __enter__(self) -> tuple[FakeClient, str]:
            return FakeClient(), "owned-puuid"

        def __exit__(self, *args: object) -> None:
            return None

    service = CurrentGameService()
    log_stream = io.StringIO()
    log_handler = logging.StreamHandler(log_stream)
    runtime_logger = logging.getLogger("peaks.application.runtime")
    previous_level = runtime_logger.level
    runtime_logger.addHandler(log_handler)
    runtime_logger.setLevel(logging.INFO)
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(riot_discovery, "discover_riot_client", lambda: discovery)
    monkeypatch.setattr(service, "_open_valorant_client", lambda _discovery: FakeContext())

    try:
        snapshot = service.owned_valorant_snapshot("owned-puuid")
    finally:
        runtime_logger.removeHandler(log_handler)
        runtime_logger.setLevel(previous_level)
        log_handler.close()

    assert snapshot == {
        "level": 284,
        "ranks": [
            {
                "game": "valorant",
                "tier": "Ascendant 1",
                "rating": 48,
                "peak_tier": "Immortal 1",
            }
        ],
        "matches": [
            {
                "match_id": "match-1",
                "game": "valorant",
                "played_at": "2026-05-03T03:09:37+00:00",
                "result": "unknown",
                "queue": "competitive",
                "map_name": "Unknown map",
                "duration_seconds": None,
                "kills": 21,
                "deaths": 12,
                "assists": 8,
                "metadata": {
                    "score": None,
                    "teams": [
                        {
                            "name": "Your team",
                            "score": 13,
                            "won": True,
                            "players": [
                                {
                                    "name": "Visible#EUW",
                                    "riotId": "Visible#EUW",
                                    "agent": "Agent unavailable",
                                    "rank": "Ascendant 3",
                                    "rankTier": 23,
                                    "score": "21 / 12 / 8",
                                    "stats": {
                                        "kills": 21,
                                        "deaths": 12,
                                        "assists": 8,
                                        "combatScore": 286,
                                        "weaponUsage": [{"weapon": "Vandal", "kills": 2}],
                                        "roundKills": [2, 0],
                                        "roundsPlayed": 3,
                                        "roundsAnalyzed": 2,
                                    },
                                    "self": True,
                                    "hidden": False,
                                    "statsLoading": True,
                                }
                            ],
                        }
                    ],
                    "freeForAll": False,
                },
            }
        ],
    }
    assert "owned-puuid" not in repr(snapshot)
    log_text = log_stream.getvalue()
    assert "current_game.owned_snapshot.start" in log_text
    assert (
        "current_game.owned_snapshot.complete level_available=True rank_count=1 match_count=1"
        in log_text
    )
    assert "owned-puuid" not in log_text


def test_owned_valorant_snapshot_fails_closed_before_private_queries_on_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = SimpleNamespace(lockfile=object())

    class ForbiddenClient:
        def rank_optional(self) -> object:
            raise AssertionError("mismatched account must not be queried")

        def match_history(self, *, limit: int) -> object:
            del limit
            raise AssertionError("mismatched account must not be queried")

    class FakeContext:
        def __enter__(self) -> tuple[ForbiddenClient, str]:
            return ForbiddenClient(), "different-puuid"

        def __exit__(self, *args: object) -> None:
            return None

    service = CurrentGameService()
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(riot_discovery, "discover_riot_client", lambda: discovery)
    monkeypatch.setattr(service, "_open_valorant_client", lambda _discovery: FakeContext())

    assert service.owned_valorant_snapshot("owned-puuid") is None
    assert service.valorant_snapshot_failure == "identity_mismatch"


def test_valorant_product_version_requires_one_active_exact_product_record() -> None:
    assert CurrentGameService._valorant_product_version(
        {
            "client": {
                "phase": "Running",
                "productId": "riot_client",
                "version": "client-version",
            },
            "game": {
                "phase": "Gameplay",
                "productId": "VALORANT",
                "version": "release-13.04-shipping-20-5340415",
            },
        }
    ) == "release-13.04-shipping-20-5340415"

    assert CurrentGameService._valorant_product_version(
        {
            "first": {
                "phase": "Gameplay",
                "productId": "valorant",
                "version": "release-13.04-shipping-20-5340415",
            },
            "second": {
                "phase": "Gameplay",
                "productId": "valorant",
                "version": "release-13.04-shipping-20-5340415",
            },
        }
    ) is None
    for missing_phase in (None, "", "None"):
        payload = {
            "game": {
                "productId": "valorant",
                "version": "release-version",
            }
        }
        if missing_phase is not None:
            payload["game"]["phase"] = missing_phase
        assert CurrentGameService._valorant_product_version(payload) is None
        assert CurrentGameService._has_active_valorant_product_session(payload) is False
    assert CurrentGameService._valorant_product_version(
        {
            "game": {
                "phase": "Gameplay",
                "productId": "valorant",
                "version": "bad version\r\nInjected: header",
            }
        }
    ) is None


def test_inactive_valorant_product_session_skips_entitlements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = SimpleNamespace(lockfile=object())
    calls: list[str] = []

    class FakeLocal:
        def __init__(self, received_lockfile: object) -> None:
            assert received_lockfile is discovery.lockfile

        def get_json(self, endpoint: str) -> object:
            calls.append(endpoint)
            if endpoint != "/product-session/v1/external-sessions":
                raise AssertionError("inactive VALORANT must not request entitlements")
            return {
                "client": {
                    "phase": "",
                    "productId": "riot_client",
                    "version": "client-version",
                }
            }

        def close(self) -> None:
            calls.append("closed")

    monkeypatch.setattr(riot_client, "RiotClientHTTP", FakeLocal)
    service = CurrentGameService()

    with service._open_valorant_client(discovery) as authenticated:
        assert authenticated is None

    assert calls == ["/product-session/v1/external-sessions", "closed"]
    assert service.valorant_snapshot_failure == "valorant_session_inactive"


def test_active_valorant_with_http_400_entitlements_is_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = SimpleNamespace(lockfile=object())
    calls: list[str] = []

    class FakeLocal:
        def __init__(self, received_lockfile: object) -> None:
            assert received_lockfile is discovery.lockfile

        def get_json(self, endpoint: str) -> object:
            calls.append(endpoint)
            if endpoint == "/product-session/v1/external-sessions":
                return {
                    "game": {
                        "phase": "Patching",
                        "productId": "valorant",
                        "version": "release-version",
                    }
                }
            raise riot_client.RiotClientError(
                "Riot local endpoint returned HTTP 400",
                status_code=400,
                detail_code="entitlements_not_ready",
            )

        def close(self) -> None:
            calls.append("closed")

    monkeypatch.setattr(riot_client, "RiotClientHTTP", FakeLocal)
    service = CurrentGameService(retry_sleep=lambda _delay: None)

    with service._open_valorant_client(discovery) as authenticated:
        assert authenticated is None

    assert service.valorant_snapshot_failure == "entitlements_not_ready"
    assert calls == [
        "/product-session/v1/external-sessions",
        "/entitlements/v1/token",
        "/entitlements/v1/token",
        "/entitlements/v1/token",
        "closed",
    ]


def test_owned_league_region_requires_exact_summoner_identity_and_closes_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lockfile = SimpleNamespace(password="secret", port=1234, base_url="https://127.0.0.1:1234")
    endpoints: list[str] = []
    closed = False

    class FakeLocal:
        def __init__(self, received_lockfile: object) -> None:
            assert received_lockfile is lockfile

        def __enter__(self) -> FakeLocal:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

        def get_json(self, endpoint: str) -> dict[str, str]:
            endpoints.append(endpoint)
            return {"puuid": "different-puuid"}

        def close(self) -> None:
            nonlocal closed
            closed = True

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        riot_discovery,
        "discover_verified_league_lockfile",
        lambda: lockfile,
    )
    monkeypatch.setattr(riot_client, "RiotClientHTTP", FakeLocal)

    assert CurrentGameService().owned_league_platform_region("owned-puuid") is None
    assert endpoints == ["/lol-summoner/v1/current-summoner"]
    assert closed is True


def test_owned_league_region_returns_only_allowlisted_authoritative_platform(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    lockfile = SimpleNamespace(password="secret", port=1234, base_url="https://127.0.0.1:1234")
    endpoints: list[str] = []

    class FakeLocal:
        def __init__(self, received_lockfile: object) -> None:
            assert received_lockfile is lockfile

        def __enter__(self) -> FakeLocal:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def get_json(self, endpoint: str) -> dict[str, str]:
            endpoints.append(endpoint)
            if endpoint == "/lol-summoner/v1/current-summoner":
                return {"puuid": "owned-puuid", "displayName": "must-not-be-used"}
            return {"region": "euw1", "locale": "en_GB"}

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        riot_discovery,
        "discover_verified_league_lockfile",
        lambda: lockfile,
    )
    monkeypatch.setattr(riot_client, "RiotClientHTTP", FakeLocal)
    caplog.set_level(logging.INFO, logger="peaks.application.runtime")

    assert CurrentGameService().owned_league_platform_region("owned-puuid") == "EUW"
    assert endpoints == [
        "/lol-summoner/v1/current-summoner",
        "/riotclient/region-locale",
    ]
    assert "owned-puuid" not in caplog.text
    assert "must-not-be-used" not in caplog.text


@pytest.mark.parametrize("value", ["", "global", "EUW<script>", " euw1", 1])
def test_league_platform_region_normalizer_rejects_unknown_values(value: object) -> None:
    assert league_adapter.normalize_platform_region(value) is None

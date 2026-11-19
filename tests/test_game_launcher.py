from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from peaks import bridge as bridge_module
from peaks.adapters.persistence import Database
from peaks.adapters.riot import launcher
from peaks.adapters.riot.client import RiotClientError
from peaks.adapters.riot.discovery import RiotLockfile
from peaks.bridge import Bridge
from peaks.domain.models import Game, Settings

_READY_ENTITLEMENTS = {"subject": "selected-account", "accessToken": "test-access", "token": "test-entitlements"}
_READY_SESSION = {
    "puuid": "selected-account", "loginState": "Authorized", "actionRequired": False,
    "productContext": {"productId": "league_of_legends", "patchlineId": "live"},
}
_READY_CONFIG = {"readiness": "Ready"}
_LEAGUE_EDGE_URL = "https://league.example.invalid"
_LEAGUE_CONTEXT_CALL = call.request("PUT", "/player-session-lifecycle/v1/product-context", json_body={
    "productContext": {"productId": "league_of_legends", "patchlineId": "live"},
})


@pytest.fixture(autouse=True)
def no_live_riot_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher, "discover_riot_client", lambda: SimpleNamespace(lockfile=None, executable=None))
    monkeypatch.setattr(launcher, "RiotClientHTTP", Mock(side_effect=AssertionError("Unexpected live Riot request")))
    monkeypatch.setattr(launcher, "sleep", Mock())
    monkeypatch.setattr(bridge_module, "sleep", Mock())


@pytest.fixture
def bridge(monkeypatch: pytest.MonkeyPatch) -> Bridge:
    monkeypatch.setenv("PEAKS_DEMO", "1")
    monkeypatch.delenv("PEAKS_DEMO_UNLOCKED", raising=False)
    monkeypatch.delenv("PEAKS_ONBOARD_PREVIEW", raising=False)
    service = Bridge()
    service.handle("pin", {"pin": "2580"})
    return service


def test_favorite_preferences_survive_database_reopen(tmp_path: Path, bridge: Bridge) -> None:
    path = tmp_path / "settings.sqlite3"
    repository = Database(path)
    bridge._repository = repository
    try:
        assert repository.get_settings().favorite_game == Game.VALORANT
        assert not repository.get_settings().auto_launch_favorite_game
        bridge.handle("settings", {"favoriteGame": "Teamfight Tactics", "autoLaunchFavoriteGame": True})
    finally:
        repository.close()
    reopened = Database(path)
    try:
        settings = reopened.get_settings()
        assert settings.favorite_game == Game.TFT
        assert settings.auto_launch_favorite_game
        bridge._repository = reopened
        bridge.settings.update(favoriteGame="VALORANT", autoLaunchFavoriteGame=False)
        bridge._load_database()
        assert bridge.settings["favoriteGame"] == "Teamfight Tactics"
        assert bridge.settings["autoLaunchFavoriteGame"] is True
    finally:
        reopened.close()


@pytest.mark.parametrize("payload", [
    {"favoriteGame": "shell.exe"}, {"favoriteGame": []}, {"favoriteGame": None},
    {"autoLaunchFavoriteGame": "true"}, {"autoLaunchFavoriteGame": 1},
    {"favoriteGame": "League of Legends", "autoLaunchFavoriteGame": "false"},
])
def test_invalid_preferences_do_not_change_state(bridge: Bridge, payload: dict[str, object]) -> None:
    before = dict(bridge.settings)
    with pytest.raises(ValueError):
        bridge.handle("settings", payload)
    assert bridge.settings == before


@pytest.mark.parametrize("command", ["connect_riot_client", "connect_riot_qr_image"])
@pytest.mark.parametrize("enabled", [False, True])
def test_launch_only_follows_successful_sign_in(
    bridge: Bridge, monkeypatch: pytest.MonkeyPatch, command: str, enabled: bool,
) -> None:
    events: list[str] = []
    monkeypatch.setattr(bridge, "_connect_riot_client", lambda *_args: events.append("approved"))
    launch = Mock(side_effect=lambda **_kwargs: events.append("launch") or "Launch request sent to Riot Client.")
    monkeypatch.setattr(bridge, "_launch_favorite_game", launch)
    bridge.handle("settings", {"autoLaunchFavoriteGame": enabled})
    result = bridge.handle(command, {"accountId": bridge.accounts[0]["id"]})
    assert events == (["approved", "launch"] if enabled else ["approved"])
    assert result["openedAccountId"] == bridge.accounts[0]["id"]
    if enabled:
        launch.assert_called_once_with(after_qr_account_id=bridge.accounts[0]["id"])


@pytest.mark.parametrize("command", ["connect_riot_client", "connect_riot_qr_image"])
@pytest.mark.parametrize("enabled", [False, True])
def test_automatic_launch_waits_after_qr_approval_and_uses_selected_identity(
    bridge: Bridge, monkeypatch: pytest.MonkeyPatch, command: str, enabled: bool,
) -> None:
    account = bridge.accounts[0]
    account["puuid"] = "selected-account"
    events = []
    monkeypatch.setattr(bridge, "_connect_riot_client", lambda *_args: events.append("approved"))
    monkeypatch.setattr(bridge, "state", lambda: {})
    monkeypatch.setattr(bridge_module, "sleep", lambda seconds: events.append(("wait", seconds)))
    launch = Mock(side_effect=lambda *_args, **_kwargs: events.append("launch"))
    monkeypatch.setattr(launcher, "launch_game", launch)
    bridge.settings.update(autoLaunchFavoriteGame=enabled, favoriteGame="Teamfight Tactics")
    bridge.demo = False
    bridge.handle(command, {"accountId": account["id"]})
    assert events == (["approved", ("wait", 3.0), "launch"] if enabled else ["approved"])
    if enabled:
        launch.assert_called_once_with("Teamfight Tactics", expected_puuid="selected-account")
    else:
        launch.assert_not_called()


def test_no_launch_on_failed_sign_in_or_unrelated_actions(bridge: Bridge, monkeypatch: pytest.MonkeyPatch) -> None:
    launch = Mock()
    monkeypatch.setattr(bridge, "_launch_favorite_game", launch)
    monkeypatch.setattr(bridge, "_connect_riot_client", Mock(side_effect=RuntimeError("QR failed")))
    bridge.handle("settings", {"autoLaunchFavoriteGame": True, "favoriteGame": "League of Legends"})
    bridge.handle("state", {})
    bridge.handle("activity", {})
    bridge.handle("pin", {"pin": "2580"})
    with pytest.raises(RuntimeError, match="QR failed"):
        bridge.handle("connect_riot_client", {"accountId": bridge.accounts[0]["id"]})
    launch.assert_not_called()
    bridge_module.sleep.assert_not_called()


def test_launch_failure_preserves_approved_connection(bridge: Bridge, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge, "_launch_favorite_game", Mock(side_effect=OSError("private path")))
    bridge.handle("settings", {"autoLaunchFavoriteGame": True})
    result = bridge.handle("connect_riot_client", {"accountId": bridge.accounts[0]["id"]})
    assert result["openedAccountId"] == bridge.accounts[0]["id"]
    assert "connected" in result["operationNotice"]
    assert "could not be launched" in result["operationWarning"]
    assert "private path" not in json.dumps(result)


def test_manual_launch_uses_saved_favorite_and_requires_unlock(bridge: Bridge, monkeypatch: pytest.MonkeyPatch) -> None:
    launch = Mock()
    monkeypatch.setattr(launcher, "launch_game", launch)
    bridge.handle("settings", {"favoriteGame": "League of Legends"})
    bridge.demo = False
    result = bridge.handle("launch_favorite_game", {"game": "VALORANT", "executable": "arbitrary.exe"})
    launch.assert_called_once_with("League of Legends")
    bridge_module.sleep.assert_not_called()
    assert result["operationNotice"] == "Launch request sent to Riot Client."
    bridge.handle("lock", {})
    with pytest.raises(PermissionError):
        bridge.handle("launch_favorite_game", {})
    launch.assert_called_once()


def test_preview_never_starts_a_real_game(bridge: Bridge, monkeypatch: pytest.MonkeyPatch) -> None:
    launch = Mock()
    monkeypatch.setattr(launcher, "launch_game", launch)
    assert "preview mode" in bridge.handle("launch_favorite_game", {})["operationNotice"]
    launch.assert_not_called()
    assert Settings.from_dict({}).favorite_game == Game.VALORANT
    assert not Settings.from_dict({"auto_launch_favorite_game": "false"}).auto_launch_favorite_game


@pytest.fixture
def local_riot_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    lock = RiotLockfile("Riot Client", 42, 12345, "local-test-secret")
    monkeypatch.setattr(launcher.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher, "discover_riot_client", lambda: SimpleNamespace(lockfile=lock, executable=None))
    client = Mock()
    session = {**_READY_SESSION}
    client.get_json.side_effect = lambda path: (
        True if path.endswith("/eligibility") else _READY_ENTITLEMENTS
        if path == "/entitlements/v1/token" else session
        if path == "/player-session-lifecycle/v1/session" else _READY_CONFIG
        if path == "/client-config/v1/status/player" else _LEAGUE_EDGE_URL
        if path == "/client-config/v2/config/lol.client_settings.league_edge.url" else {"subject": "selected-account"}
    )
    client.request.return_value = SimpleNamespace(status_code=200)

    def request(method: str, _path: str, **kwargs: object) -> SimpleNamespace:
        if method == "PUT":
            session["productContext"] = kwargs["json_body"]["productContext"]
        return client.request.return_value

    client.request.side_effect = request
    factory = Mock()
    factory.return_value.__enter__ = Mock(return_value=client)
    factory.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(launcher, "RiotClientHTTP", factory)
    monkeypatch.setattr(launcher.subprocess, "Popen", Mock(side_effect=AssertionError("Must launch through the Play API")))
    return client


@pytest.mark.parametrize(("game", "product"), [
    (Game.VALORANT, "valorant"), (Game.LEAGUE_OF_LEGENDS, "league_of_legends"), (Game.TFT, "teamfighttactics"),
])
def test_running_client_launches_the_game_through_play_api(local_riot_client: Mock, game: Game, product: str) -> None:
    launcher.launch_game(game, expected_puuid="selected-account")
    assert local_riot_client.method_calls == [
        call.get_json("/rso-auth/v1/authorization"),
        call.get_json("/entitlements/v1/token"),
        call.request("PUT", "/player-session-lifecycle/v1/product-context", json_body={
            "productContext": {"productId": "league_of_legends" if game == Game.TFT else product, "patchlineId": "live"},
        }),
        call.get_json("/player-session-lifecycle/v1/session"),
        call.get_json("/client-config/v1/status/player"),
        *([call.get_json("/client-config/v2/config/lol.client_settings.league_edge.url")] if game != Game.VALORANT else []),
        call.get_json(f"/product-launcher/v1/products/{product}/patchlines/live/eligibility"),
        call.request("POST", f"/product-launcher/v1/products/{product}/patchlines/live"),
    ]
    assert local_riot_client.timeout == 30.0
    launcher.sleep.assert_not_called()


def test_local_client_can_finish_its_poll_after_the_initial_delay(local_riot_client: Mock) -> None:
    local_riot_client.get_json.side_effect = [
        RiotClientError("Not authenticated", status_code=404), {}, {"subject": "previous-account"},
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, True,
    ]
    launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert launcher.sleep.call_args_list == [call(0.5)] * 3
    assert local_riot_client.request.call_args_list == [
        _LEAGUE_CONTEXT_CALL,
        call("POST", "/product-launcher/v1/products/teamfighttactics/patchlines/live"),
    ]


def test_pending_or_wrong_identity_never_launches_a_game(local_riot_client: Mock) -> None:
    local_riot_client.get_json.side_effect = None
    local_riot_client.get_json.return_value = {"subject": "previous-account"}
    with pytest.raises(RuntimeError, match="has not finished signing in"):
        launcher.launch_game(Game.VALORANT, expected_puuid="selected-account")
    assert local_riot_client.get_json.call_count == 30
    assert launcher.sleep.call_count == 29
    local_riot_client.request.assert_not_called()


def test_signed_in_identity_waits_until_riot_allows_play(local_riot_client: Mock) -> None:
    local_riot_client.get_json.side_effect = [
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, RiotClientError("initializing", status_code=464),
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, False,
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, True,
    ]
    launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert launcher.sleep.call_args_list == [call(0.5)] * 2
    assert local_riot_client.request.call_count == 2


def test_old_or_missing_game_credentials_are_not_enough_to_launch(local_riot_client: Mock) -> None:
    local_riot_client.get_json.side_effect = [
        {"subject": "selected-account"}, {**_READY_ENTITLEMENTS, "subject": "previous-account"},
        {"subject": "selected-account"}, {**_READY_ENTITLEMENTS, "token": ""},
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, True,
    ]
    launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert launcher.sleep.call_count == 2
    assert local_riot_client.request.call_count == 2


def test_waits_for_league_session_after_qr_before_play(local_riot_client: Mock) -> None:
    local_riot_client.get_json.side_effect = [
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, {**_READY_SESSION, "loginState": "PendingProductContext"},
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, {**_READY_SESSION, "loginState": "PendingAffinityData"},
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, True,
    ]
    launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert launcher.sleep.call_args_list == [call(0.5)] * 2
    assert local_riot_client.request.call_args_list == [
        _LEAGUE_CONTEXT_CALL,
        call("POST", "/product-launcher/v1/products/teamfighttactics/patchlines/live"),
    ]


def test_waits_for_player_config_before_league_reads_it_once_at_startup(local_riot_client: Mock) -> None:
    local_riot_client.get_json.side_effect = [
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, {"readiness": "NotReady"},
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, None,
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, _READY_SESSION, _READY_CONFIG, _LEAGUE_EDGE_URL, True,
    ]
    launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert launcher.sleep.call_args_list == [call(0.5)] * 2
    assert local_riot_client.request.call_args_list == [
        _LEAGUE_CONTEXT_CALL,
        call("POST", "/product-launcher/v1/products/teamfighttactics/patchlines/live"),
    ]


@pytest.mark.parametrize("session_change", [
    {"puuid": "previous-account"}, {"actionRequired": True},
    {"loginState": "PendingEulaAcceptance"}, {"productContext": {"productId": "valorant", "patchlineId": "live"}},
])
def test_unready_game_session_never_launches(local_riot_client: Mock, session_change: dict[str, object]) -> None:
    local_riot_client.get_json.side_effect = [
        {"subject": "selected-account"}, _READY_ENTITLEMENTS, {**_READY_SESSION, **session_change},
    ] * 30
    with pytest.raises(RuntimeError, match="has not finished signing in"):
        launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert local_riot_client.request.call_args_list == [_LEAGUE_CONTEXT_CALL]


def test_rejected_product_context_does_not_start_an_empty_client(local_riot_client: Mock) -> None:
    local_riot_client.request.return_value = SimpleNamespace(status_code=400)
    with pytest.raises(RuntimeError, match="could not prepare the game session"):
        launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert local_riot_client.request.call_args_list == [_LEAGUE_CONTEXT_CALL]


def test_slow_play_is_never_retried_and_does_not_use_short_readiness_timeout(local_riot_client: Mock) -> None:
    def play(method: str, *_args: object, **_kwargs: object) -> SimpleNamespace:
        if method == "PUT":
            return SimpleNamespace(status_code=201)
        assert local_riot_client.timeout == 30.0
        raise RiotClientError("timed out")
    local_riot_client.request.side_effect = play
    with pytest.raises(RuntimeError, match="could not start the game"):
        launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert local_riot_client.request.call_count == 2


@pytest.mark.parametrize("status", [400, 401, 409, 500])
def test_rejected_play_is_not_reported_as_a_success(local_riot_client: Mock, status: int) -> None:
    local_riot_client.request.side_effect = [SimpleNamespace(status_code=201), SimpleNamespace(status_code=status)]
    with pytest.raises(RuntimeError, match="could not start the game"):
        launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    assert local_riot_client.request.call_count == 2


def test_auto_launch_does_not_fall_back_to_a_product_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher.platform, "system", lambda: "Windows")
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError, match="not ready after sign-in"):
        launcher.launch_game(Game.TFT, expected_puuid="selected-account")
    spawn.assert_not_called()


@pytest.mark.parametrize(("game", "product"), [
    (Game.VALORANT, "valorant"), (Game.LEAGUE_OF_LEGENDS, "league_of_legends"), (Game.TFT, "teamfighttactics"),
])
def test_launch_uses_riot_shortcut_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, game: Game, product: str,
) -> None:
    executable = tmp_path / "Riot Client" / "RiotClientServices.exe"
    monkeypatch.setattr(launcher.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher, "find_riot_executable", lambda: executable)
    spawn = Mock()
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    launcher.launch_game(game)
    assert spawn.call_args.args[0] == [str(executable), f"--launch-product={product}", "--launch-patchline=live"]
    assert spawn.call_args.kwargs["cwd"] == executable.parent
    assert spawn.call_args.kwargs.get("shell", False) is False
    assert spawn.call_args.kwargs["stdout"] == subprocess.DEVNULL


def test_manifest_discovery_handles_custom_install_and_ignores_other_executables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "Custom Games" / "Riot Client" / "RiotClientServices.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    unrelated = tmp_path / "other.exe"
    unrelated.touch()
    manifest = tmp_path / "Riot Games" / "RiotClientInstalls.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"rc_default": str(unrelated), "rc_live": str(executable)}))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.delenv("ALLUSERSPROFILE", raising=False)
    monkeypatch.setattr(launcher, "discover_riot_client", lambda: SimpleNamespace(executable=None))
    monkeypatch.setattr(launcher, "default_paths", lambda: SimpleNamespace(executables=()))
    assert launcher.find_riot_executable() == executable
    executable.unlink()
    assert launcher.find_riot_executable() is None


def test_launch_failures_are_actionable_and_hide_local_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher.platform, "system", lambda: "Windows")
    monkeypatch.setattr(launcher, "find_riot_executable", lambda: None)
    spawn = Mock(side_effect=OSError("private path"))
    monkeypatch.setattr(launcher.subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError, match="not found"):
        launcher.launch_game(Game.TFT)
    spawn.assert_not_called()
    with pytest.raises(ValueError):
        launcher.launch_game("arbitrary.exe")
    monkeypatch.setattr(launcher, "find_riot_executable", lambda: Path("C:/Riot Client/RiotClientServices.exe"))
    with pytest.raises(RuntimeError, match="could not start") as failure:
        launcher.launch_game(Game.VALORANT)
    assert "private path" not in str(failure.value)
    monkeypatch.setattr(launcher.platform, "system", lambda: "Linux")
    with pytest.raises(RuntimeError, match="Windows only"):
        launcher.launch_game(Game.VALORANT)

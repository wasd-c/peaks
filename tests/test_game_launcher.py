from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from peaks.adapters.persistence import Database
from peaks.adapters.riot import launcher
from peaks.bridge import Bridge
from peaks.domain.models import Game, Settings


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
    launch = Mock(side_effect=lambda: events.append("launch") or "Launch request sent to Riot Client.")
    monkeypatch.setattr(bridge, "_launch_favorite_game", launch)
    bridge.handle("settings", {"autoLaunchFavoriteGame": enabled})
    result = bridge.handle(command, {"accountId": bridge.accounts[0]["id"]})
    assert events == (["approved", "launch"] if enabled else ["approved"])
    assert result["openedAccountId"] == bridge.accounts[0]["id"]


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

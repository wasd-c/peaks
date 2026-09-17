from __future__ import annotations

import json
import runpy
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from peaks.adapters import persistence
from peaks.adapters.persistence import InMemoryPepperProvider, SecretVault
from peaks.adapters.persistence.profile_reset import RESET_MARKER, begin_profile_reset
from peaks.bridge import (
    RESET_APPLICATION_CONFIRMATION,
    Bridge,
    _bridge_response_line,
    _BridgeRequestDispatcher,
    _configure_bridge_stdio,
    _match,
    _vault_has_pin,
)


class CallablePinVault:
    def has_pin(self) -> bool:
        return True


class PropertyPinVault:
    @property
    def has_pin(self) -> bool:
        return True


@pytest.mark.parametrize("vault", [CallablePinVault(), PropertyPinVault()])
def test_vault_has_pin_accepts_callable_and_property_contracts(vault: Any) -> None:
    assert _vault_has_pin(vault) is True


def test_bridge_response_round_trips_unicode_through_a_windows_code_page() -> None:
    response = {"id": 7, "result": {"map": "スプリット", "player": "ズーム#JP"}}

    line = _bridge_response_line(response)

    assert line.encode("cp1252")
    assert "\\u30ba" in line.casefold()
    assert json.loads(line) == response


def test_bridge_configures_all_ipc_streams_as_utf8(monkeypatch: pytest.MonkeyPatch) -> None:
    class RecordingStream:
        def __init__(self) -> None:
            self.configuration: dict[str, str] = {}

        def reconfigure(self, **configuration: str) -> None:
            self.configuration = configuration

    streams = [RecordingStream(), RecordingStream(), RecordingStream()]
    monkeypatch.setattr("peaks.bridge.sys.stdin", streams[0])
    monkeypatch.setattr("peaks.bridge.sys.stdout", streams[1])
    monkeypatch.setattr("peaks.bridge.sys.stderr", streams[2])

    _configure_bridge_stdio()

    assert [stream.configuration for stream in streams] == [
        {"encoding": "utf-8", "errors": "strict"},
        {"encoding": "utf-8", "errors": "strict"},
        {"encoding": "utf-8", "errors": "strict"},
    ]


def test_bridge_keeps_totp_copy_responsive_during_session_import() -> None:
    class BlockingBridge:
        def __init__(self) -> None:
            self.import_started = threading.Event()
            self.release_import = threading.Event()

        def handle(self, command: str, _payload: object) -> dict[str, str]:
            if command == "import_session":
                self.import_started.set()
                assert self.release_import.wait(timeout=1)
                return {"status": "imported"}
            if command == "copy_totp":
                return {"status": "copied"}
            raise AssertionError(f"Unexpected command: {command}")

        def search(self, _payload: object) -> dict[str, str]:
            raise AssertionError("Search should not be called")

    bridge = BlockingBridge()
    responses: list[Mapping[str, Any]] = []
    dispatcher = _BridgeRequestDispatcher(bridge, responses.append)  # type: ignore[arg-type]

    dispatcher.dispatch({"id": 1, "command": "import_session", "payload": {}})
    assert bridge.import_started.wait(timeout=1)
    assert bridge._session_import_in_progress is True  # type: ignore[attr-defined]

    dispatcher.dispatch({"id": 2, "command": "copy_totp", "payload": {}})
    assert responses == [{"id": 2, "result": {"status": "copied"}}]

    bridge.release_import.set()
    dispatcher.wait_for_workers()
    assert {response["id"] for response in responses} == {1, 2}
    assert bridge._session_import_in_progress is False  # type: ignore[attr-defined]


def test_bridge_entrypoint_errors_reach_the_redacted_log(tmp_path: Path) -> None:
    from peaks.diagnostics import configure_diagnostics

    namespace = runpy.run_module("peaks.bridge", run_name="entrypoint_probe")
    path = configure_diagnostics(tmp_path)
    namespace["_execute_bridge_request"](None, [])

    diagnostic = path.read_text(encoding="utf-8")
    assert "bridge.command.failed command=unknown error_type=TypeError" in diagnostic


def test_demo_onboarding_preview_uses_an_ephemeral_passcode_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PEAKS_DEMO", "1")
    monkeypatch.setenv("PEAKS_ONBOARD_PREVIEW", "1")
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)

    bridge = Bridge()

    assert bridge._vault is None
    assert bridge._repository is None
    assert bridge.state()["hasPasscode"] is False
    assert bridge.state()["pinMode"] == "create"

    created = bridge.handle("pin", {"pin": "2468"})
    assert created["locked"] is True
    assert created["pinMode"] == "confirm"

    unlocked = bridge.handle("pin", {"pin": "2468"})
    assert unlocked["locked"] is False
    assert unlocked["hasPasscode"] is True
    assert list(tmp_path.iterdir()) == []


def test_bridge_reopens_existing_vault_in_unlock_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)

    pepper = InMemoryPepperProvider(b"bridge-pepper-0123456789012345")
    vault_path = tmp_path / "vault.json"
    existing_vault = SecretVault(vault_path, pepper_provider=pepper)
    existing_vault.setup_pin("2468")
    original = vault_path.read_bytes()

    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(path, pepper_provider=pepper),
    )

    bridge = Bridge()
    try:
        assert "Peaks service initialization warning" not in capsys.readouterr().err
        assert bridge.state()["pinMode"] == "unlock"
        assert bridge.state()["hasPasscode"] is True
        assert bridge.state()["locked"] is True

        unlocked = bridge.handle("pin", {"pin": "2468"})

        assert unlocked["locked"] is False
        assert vault_path.read_bytes() == original
    finally:
        if bridge._vault is not None:
            bridge._vault.lock()
        if bridge._repository is not None:
            bridge._repository.close()


def test_bridge_new_vault_still_requires_matching_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)

    pepper = InMemoryPepperProvider(b"bridge-pepper-0123456789012345")
    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(path, pepper_provider=pepper),
    )

    bridge = Bridge()
    vault_path = tmp_path / "vault.json"
    try:
        assert bridge.state()["pinMode"] == "create"

        first = bridge.handle("pin", {"pin": "1234"})
        assert first["pinMode"] == "confirm"
        assert vault_path.exists() is False

        with pytest.raises(ValueError, match="Passcodes did not match"):
            bridge.handle("pin", {"pin": "4321"})
        assert bridge.state()["pinMode"] == "create"
        assert vault_path.exists() is False

        bridge.handle("pin", {"pin": "1234"})
        confirmed = bridge.handle("pin", {"pin": "1234"})
        assert confirmed["pinMode"] == "unlock"
        assert confirmed["locked"] is False
        assert vault_path.exists() is True
    finally:
        if bridge._vault is not None:
            bridge._vault.lock()
        if bridge._repository is not None:
            bridge._repository.close()


def test_bridge_forgotten_passcode_reset_reopens_first_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(
            path,
            pepper_provider=InMemoryPepperProvider(
                b"bridge-reset-pepper-012345678901"
            ),
        ),
    )

    unrelated = tmp_path / "keep-me.txt"
    unrelated.write_text("unrelated", encoding="utf-8")
    bridge = Bridge()
    try:
        bridge.handle("pin", {"pin": "1234"})
        bridge.handle("pin", {"pin": "1234"})
        with pytest.raises(PermissionError, match="Lock Peaks"):
            bridge.handle(
                "reset_application",
                {"confirmation": RESET_APPLICATION_CONFIRMATION},
            )

        bridge.handle("lock", {})
        with pytest.raises(PermissionError, match="Confirm the local data reset"):
            bridge.handle("reset_application", {})

        reset = bridge.handle(
            "reset_application",
            {"confirmation": RESET_APPLICATION_CONFIRMATION},
        )

        assert reset["locked"] is True
        assert reset["hasPasscode"] is False
        assert reset["pinMode"] == "create"
        assert reset["accounts"] == []
        assert reset["followed"] == []
        assert reset["searchHistory"] == []
        assert unrelated.read_text(encoding="utf-8") == "unrelated"
        assert (tmp_path / "peaks.sqlite3").is_file()
        assert not (tmp_path / "vault.json").exists()
        assert not (tmp_path / RESET_MARKER).exists()

        bridge.handle("pin", {"pin": "2468"})
        recreated = bridge.handle("pin", {"pin": "2468"})
        assert recreated["locked"] is False
        assert recreated["hasPasscode"] is True
    finally:
        if bridge._vault is not None:
            bridge._vault.lock()
        if bridge._repository is not None:
            bridge._repository.close()


def test_bridge_finishes_a_pending_profile_reset_before_opening_services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(
            path,
            pepper_provider=InMemoryPepperProvider(
                b"bridge-recovery-pepper-012345678"
            ),
        ),
    )
    begin_profile_reset(tmp_path)
    (tmp_path / "vault.json").write_bytes(b"interrupted reset fixture")

    bridge = Bridge()
    try:
        state = bridge.state()
        assert state["hasPasscode"] is False
        assert state["pinMode"] == "create"
        assert not (tmp_path / RESET_MARKER).exists()
        assert not (tmp_path / "vault.json").exists()
        assert (tmp_path / "peaks.sqlite3").is_file()
    finally:
        if bridge._vault is not None:
            bridge._vault.lock()
        if bridge._repository is not None:
            bridge._repository.close()


def test_bridge_security_preferences_are_validated_and_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    pepper = InMemoryPepperProvider(b"bridge-pepper-0123456789012345")
    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(path, pepper_provider=pepper),
    )

    bridge = Bridge()
    try:
        bridge.handle("pin", {"pin": "1234"})
        bridge.handle("pin", {"pin": "1234"})
        state = bridge.handle(
            "settings",
            {"autoLockMinutes": 0, "lockOnBlur": False, "reduceMotion": True, "streamerMode": True},
        )
        assert state["settings"]["autoLockMinutes"] == 0
        assert state["settings"]["streamerMode"] is True
        assert state["settings"]["lockOnBlur"] is False
        assert state["settings"]["reduceMotion"] is True
        with pytest.raises(ValueError, match="automatic lock interval"):
            bridge.handle("settings", {"autoLockMinutes": 2})
        with pytest.raises(ValueError, match="desktop preference"):
            bridge.handle("settings", {"streamerMode": "true"})
    finally:
        if bridge._vault is not None:
            bridge._vault.lock()
        if bridge._repository is not None:
            bridge._repository.close()

    reopened = Bridge()
    try:
        state = reopened.state()
        assert state["settings"]["autoLockMinutes"] == 0
        assert state["settings"]["streamerMode"] is True
        assert state["locked"] is True
        assert state["settings"]["lockOnBlur"] is False
        assert state["settings"]["reduceMotion"] is True
    finally:
        if reopened._vault is not None:
            reopened._vault.lock()
        if reopened._repository is not None:
            reopened._repository.close()


def test_match_projection_exposes_visible_profiles_and_suppresses_hidden_identifiers() -> None:
    projected = _match(
        {
            "match_id": "match-1",
            "game": "valorant",
            "result": "win",
            "metadata": {
                "teams": [
                    {
                        "name": "Your team",
                        "score": 13,
                        "players": [
                            {
                                "name": "Visible alias",
                                "riotId": "Visible#EUW",
                                "subject": "visible-private-subject",
                                "rank": "Ascendant 3",
                                "rankTier": 23,
                                "stats": {"kills": 21, "deaths": 12, "unsafe": 99},
                            },
                            {
                                "name": "Must not leak",
                                "riotId": "Hidden#HIDE",
                                "subject": "hidden-private-subject",
                                "hidden": True,
                                "stats": {"kills": 9},
                            },
                        ],
                    }
                ]
            },
        }
    )

    visible, hidden = projected["teams"][0]["players"]
    assert visible["name"] == "Visible#EUW"
    assert visible["riotId"] == "Visible#EUW"
    assert visible["rankTier"] == 23
    assert visible["stats"] == {"kills": 21, "deaths": 12}
    assert hidden["name"] == "Hidden player 2"
    assert hidden["riotId"] is None
    assert hidden["hidden"] is True
    assert "private-subject" not in repr(projected)
    assert "Must not leak" not in repr(projected)
    assert "Hidden#HIDE" not in repr(projected)


def test_watchlist_player_persists_and_legacy_toggle_unwatches_by_riot_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PEAKS_DEMO", raising=False)
    monkeypatch.setattr("peaks.bridge.user_data_path", lambda *_args, **_kwargs: tmp_path)
    pepper = InMemoryPepperProvider(b"bridge-pepper-0123456789012345")
    monkeypatch.setattr(
        persistence,
        "SecretVault",
        lambda path: SecretVault(path, pepper_provider=pepper),
    )
    player = {
        "id": "riot:valorant:visible#euw",
        "riotId": "Visible#EUW",
        "region": "EUW",
        "game": "VALORANT",
        "currentRank": "Ascendant 3 · 72 RR",
        "peakRank": "Immortal 1 · 18 RR",
    }

    bridge = Bridge()
    try:
        bridge.handle("pin", {"pin": "2468"})
        bridge.handle("pin", {"pin": "2468"})
        watched = bridge.handle("toggle_watchlist", {"player": player})
        assert [item["riotId"] for item in watched["followed"]] == ["Visible#EUW"]
        assert watched["operationNotice"] == "Added to Watchlist"
        assert bridge._repository is not None
        assert [item.display_name for item in bridge._repository.list_followed()] == [
            "Visible#EUW"
        ]
    finally:
        if bridge._vault is not None:
            bridge._vault.lock()
        if bridge._repository is not None:
            bridge._repository.close()

    reopened = Bridge()
    try:
        reopened.handle("pin", {"pin": "2468"})
        assert [item["riotId"] for item in reopened.state()["followed"]] == ["Visible#EUW"]

        unwatched = reopened.handle(
            "toggle_follow",
            {
                "player": {
                    **player,
                    "id": "a-different-provider-id",
                    "riotId": "visible#euw",
                }
            },
        )

        assert unwatched["followed"] == []
        assert unwatched["operationNotice"] == "Removed from Watchlist"
        assert reopened._repository is not None
        assert reopened._repository.list_followed() == []
    finally:
        if reopened._vault is not None:
            reopened._vault.lock()
        if reopened._repository is not None:
            reopened._repository.close()

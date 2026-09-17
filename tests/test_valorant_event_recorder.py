"""The diagnostic capture must preserve evidence without persisting private data."""

from __future__ import annotations

import base64
import collections
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "record_valorant_events.py"
SPEC = importlib.util.spec_from_file_location("record_valorant_events", SCRIPT)
assert SPEC and SPEC.loader
recorder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recorder)


def test_projection_removes_credentials_and_names_but_retains_game_numbers():
    redactor = recorder.Redactor()
    result = redactor.project(
        {
            "gameName": "SecretPlayer",
            "accessToken": "sensitive-token",
            "password": "sensitive-password",
            "kills": 18,
            "deaths": "8",
            "assists": 3,
            "nested": {"cookie": "sensitive-cookie", "score": 123},
        }
    )
    output = json.dumps(result)
    assert "SecretPlayer" not in output
    assert "sensitive" not in output
    assert result["kills"] == 18
    assert result["deaths"] == 8
    assert result["assists"] == 3


def test_subjects_use_ephemeral_aliases_and_self_flag():
    redactor = recorder.Redactor()
    redactor.subject = "private-self-id"
    result = redactor.project({"subject": "private-self-id", "victim": "private-enemy-id"})
    assert result["subject"]["self"] is True
    assert result["victim"]["self"] is False
    assert "private-" not in json.dumps(result)
    assert redactor.alias("one") != recorder.Redactor().alias("one")


def test_presence_only_projects_own_valorant_record():
    redactor = recorder.Redactor()
    redactor.subject = "self-id"

    def row(subject, score):
        return {
            "puuid": subject,
            "product": "valorant",
            "private": base64.b64encode(
                json.dumps(
                    {"partyOwnerMatchScoreAllyTeam": score, "gameName": "PrivateName"}
                ).encode()
            ).decode(),
        }

    result = redactor.presence({"presences": [row("other-id", 19), row("self-id", 9)]})
    assert result["self"]["partyOwnerMatchScoreAllyTeam"] == 9
    assert "PrivateName" not in json.dumps(result)
    assert "19" not in json.dumps(result)


def test_log_signals_never_save_whole_line():
    result = recorder.project_log_line(
        "[2026.09.16-12.34.56:789] LogAudio: Play_VO_Jett_E02_Kill "
        "player=PrivateName token=super-secret kills=3 deaths=1"
    )
    assert result["markers"] == ["Play_VO_Jett_E02_Kill"]
    assert {"field": "kills", "value": 3} in result["numbers"]
    assert "PrivateName" not in json.dumps(result)
    assert "super-secret" not in json.dumps(result)
    assert recorder.project_log_line("LogAuth: token=super-secret") is None


def test_tail_skips_existing_history_but_reads_appends_and_new_session(tmp_path):
    log = tmp_path / "ShooterGame.log"
    log.write_bytes(b"old-history\n")
    tail = recorder.LogTail(log)
    assert tail.read() == []
    with log.open("ab") as output:
        output.write(b"new-event\npartial")
    assert tail.read() == ["new-event"]
    with log.open("ab") as output:
        output.write(b"-line\n")
    assert tail.read() == ["partial-line"]
    log.write_bytes(b"restart\n")
    assert tail.read() == ["restart"]


def test_tail_waits_for_log_creation(tmp_path):
    log = tmp_path / "ShooterGame.log"
    tail = recorder.LogTail(log)
    assert tail.read() == []
    log.write_bytes(b"first-event\n")
    assert tail.read() == ["first-event"]


@pytest.mark.parametrize(
    ("technical", "field", "value"),
    [
        ("SpikePlanted roundNumber=8", "roundnumber", 8),
        ("SpikeDefused roundTime=23.5", "roundtime", 23.5),
        ("SpikeDetonation roundIndex=4", "roundindex", 4),
        ("BuyPhase credits=3900 armor=50", "credits", 3900),
        ("WeaponFire ammo=17", "ammo", 17),
        ("WeaponReload reserveAmmo=50", "reserveammo", 50),
        ("WeaponEquip magazineAmmo=25", "magazineammo", 25),
        ("AbilityCast abilityCharges=2", "abilitycharges", 2),
        ("UltimateReady ultimatePoints=8", "ultimatepoints", 8),
        ("DamageReceived damageTaken=149 headshots=1", "damagetaken", 149),
        ("KillFeed kills=12", "kills", 12),
        ("Performance ping=21.5 fps=240 packetLoss=0.25", "packetloss", 0.25),
    ],
)
def test_log_technical_categories_preserve_numbers_without_raw_values(technical, field, value):
    result = recorder.project_log_line(
        f"LogGame: {technical} player=PrivateName token=super-secret weapon=PrivateWeapon"
    )
    assert result is not None
    assert result["signals"]
    assert {"field": field, "value": value} in result["numbers"]
    assert "Private" not in json.dumps(result)
    assert "super-secret" not in json.dumps(result)


def bare_recorder():
    instance = recorder.Recorder.__new__(recorder.Recorder)
    instance.events = io.StringIO()
    instance.counts = collections.Counter()
    instance.last_payload = {}
    instance.redactor = recorder.Redactor()
    instance.event_names = {"OnGameEvent"}
    return instance


@pytest.mark.parametrize("payload", [{"data": {"kills": 1}}, ["Kill"]])
def test_identical_websocket_events_each_keep_an_occurrence(payload):
    instance = bare_recorder()
    frame = json.dumps([8, "OnGameEvent", payload])
    instance.on_message(frame)
    instance.on_message(frame)
    events = [json.loads(line) for line in instance.events.getvalue().splitlines()]
    assert len(events) == 2
    assert instance.counts["ws:OnGameEvent"] == 2
    assert all(event["at"] for event in events)
    assert events[0]["data"]["frameFingerprint"] == events[1]["data"]["frameFingerprint"]


def test_unknown_changed_fields_get_salted_fingerprints_without_persisting_values():
    instance = bare_recorder()
    for value in ["PrivateAlpha", "PrivateBeta"]:
        instance.on_message(json.dumps([8, "OnGameEvent", {"data": {"unknown": value}}]))
    output = instance.events.getvalue()
    assert "Private" not in output
    events = [json.loads(line) for line in output.splitlines()]
    assert events[0]["data"]["frameFingerprint"] != events[1]["data"]["frameFingerprint"]
    instance.write("self_presence", {"kills": 3}, deduplicate=True)
    instance.write("self_presence", {"kills": 3}, deduplicate=True)
    assert len(instance.events.getvalue().splitlines()) == 3


def test_websocket_oversized_deep_invalid_and_empty_frames_are_bounded(monkeypatch):
    instance = bare_recorder()
    depth = sys.getrecursionlimit() + 100
    instance.on_message("[" * depth + "]" * depth)
    instance.on_message("not-json")
    instance.on_message("\ud800")
    instance.on_message("   ")
    monkeypatch.setattr(recorder, "MAX_MESSAGE_BYTES", 16)
    instance.on_message("é" * 9)
    instance.on_message("x" * 17)
    # CPython versions differ in whether the JSON parser rejects this nesting.
    # Either way it must never become a recorded WAMP gameplay event.
    assert instance.counts["invalid_frame"] >= 2
    assert instance.counts["invalid_frame"] + instance.counts["other_frame"] == 3
    assert instance.counts["empty_acknowledgement"] == 1
    assert instance.counts["oversized_frame"] == 2
    assert instance.events.getvalue() == ""


def test_presence_failure_retains_only_status_and_error_type(monkeypatch):
    instance = bare_recorder()
    instance.redactor.subject = "self"
    instance.lock_identity = (123, 456)
    monkeypatch.setattr(
        recorder,
        "discover_riot_client",
        lambda: SimpleNamespace(lockfile=SimpleNamespace(pid=123, port=456)),
    )

    class PrivateFailure(Exception):
        status_code = 503

    class Client:
        def get_json(self, _path):
            raise PrivateFailure("PrivateName token=super-secret")

    instance.client = Client()
    instance.poll_presence()
    event = json.loads(instance.events.getvalue())
    assert event["data"] == {"errorType": "PrivateFailure", "statusCode": 503}

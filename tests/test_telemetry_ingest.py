"""The public relay must not accept arbitrary private fields or unbounded input."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("peaks_telemetry_ingest", Path(__file__).parents[1] / "deploy" / "telemetry" / "ingest.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def batch(**extras: object) -> dict[str, object]:
    return {"schema": 1, "events": [{"event": "app.started", "version": "0.3.0", "platform": "win32", **extras}]}


def test_minimal_event_has_no_identifiers() -> None:
    assert module.sanitize_batch(batch()) == [{"event": "app.started", "version": "0.3.0", "platform": "win32", "service": "peaks", "schema": 1}]


@pytest.mark.parametrize("field", ["riotId", "puuid", "name", "token", "email", "ip", "deviceId", "message", "stack", "url", "path"])
def test_rejects_additional_fields(field: str) -> None:
    with pytest.raises(ValueError):
        module.sanitize_batch(batch(**{field: "private"}))


@pytest.mark.parametrize("data", [None, {}, {"schema": True, "events": []}, {"schema": 1, "events": []}, {"schema": 1, "events": [{}] * 33}, batch(event="user-provided"), batch(version="private-build"), batch(platform="hostname"), batch(event=["invalid"])])
def test_rejects_invalid_schema(data: object) -> None:
    with pytest.raises(ValueError):
        module.sanitize_batch(data)


@pytest.mark.parametrize("duration", [True, -1, 1.5, 300_100, 1234, "100", float("nan")])
def test_rejects_unbounded_durations(duration: object) -> None:
    with pytest.raises(ValueError):
        module.sanitize_batch(batch(event="command.completed", command="activity", outcome="success", duration_ms=duration))


def test_accepts_known_command_and_rounded_duration() -> None:
    assert module.sanitize_batch(batch(event="command.completed", command="activity", outcome="failure", duration_ms=100))[0]["duration_ms"] == 100


def test_rate_limit_bounds_each_source_and_global_volume() -> None:
    limiter = module.RateLimit()
    assert all(limiter.allow("source", 100) for _ in range(6))
    assert all(not limiter.allow("source", 100) for _ in range(700))
    assert limiter.allow("unrelated", 100)
    assert limiter.allow("source", 160)
    for i in range(599):
        assert limiter.allow(str(i), 160)
    assert not limiter.allow("last", 160)
    assert limiter.allow("last", 220)

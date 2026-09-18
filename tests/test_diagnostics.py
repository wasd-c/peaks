from __future__ import annotations

import ast
import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from peaks.diagnostic_policy import SAFE_EVENTS, sanitize_diagnostic_message
from peaks.diagnostics import DiagnosticFormatter, configure_diagnostics


@pytest.fixture
def diagnostic_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    logger = logging.getLogger("peaks")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    logger.handlers = []
    monkeypatch.setenv("PEAKS_LOG_LEVEL", "DEBUG")
    try:
        yield configure_diagnostics(tmp_path)
    finally:
        for handler in logger.handlers:
            handler.close()
        logger.handlers = handlers
        logger.setLevel(level)
        logger.propagate = propagate


@pytest.mark.parametrize(
    "private",
    [
        "Private Player#EUW",
        "00000000-1111-2222-3333-444444444444",
        "person@example.test",
        r"C:\Users\Private Person\Peaks\vault.json",
        "https://auth.example.test/path?access_token=PRIVATE-TOKEN#id_token=PRIVATE-ID",
        "Bearer PRIVATE-TOKEN",
        "ssid=PRIVATE-COOKIE; password=PRIVATE-PASSWORD",
        '{"accountId":"PRIVATE-ACCOUNT","pin":"1234","code":"123456"}',
        "PRIVATE\n2026-01-01T00:00:00 ERROR peaks forged.entry token=SECRET",
    ],
)
def test_both_log_destinations_withhold_private_content(
    private: str,
    diagnostic_log: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = logging.getLogger("peaks.PRIVATE-LOGGER")
    logger.error("bridge.command.failed command=connect_riot_qr_image payload=%s", private)
    logger.error("bridge.command.failed command=%s error_type=%s", private, private)
    logger.error(private)
    output = diagnostic_log.read_text(encoding="utf-8") + capsys.readouterr().err
    assert private not in output
    assert "PRIVATE" not in output
    assert "person@example.test" not in output
    assert "command=connect_riot_qr_image" in output
    assert "redacted=true" in output
    assert "diagnostics.redacted" in output


def test_exception_tracebacks_and_cached_text_never_reach_logs(
    diagnostic_log: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    try:
        raise ValueError("Private#EU password=PRIVATE-PASSWORD")
    except ValueError:
        logging.getLogger("peaks.bridge").exception(
            "bridge.command.failed command=import_session", stack_info=True
        )
    output = diagnostic_log.read_text(encoding="utf-8") + capsys.readouterr().err
    assert "exception_type=ValueError" in output
    for private in (
        "Private#EU",
        "PRIVATE-PASSWORD",
        "Traceback",
        "test_diagnostics.py",
        "Stack (most recent",
    ):
        assert private not in output
    record = logging.LogRecord(
        "private-name", logging.ERROR, __file__, 1, "bridge.command.failed", (), None
    )
    record.exc_text = "cached PRIVATE-TOKEN"
    record.stack_info = "private source code"
    rendered = DiagnosticFormatter("%(name)s %(message)s").format(record)
    assert rendered == "peaks bridge.command.failed"
    assert record.exc_text == "cached PRIVATE-TOKEN"  # Do not mutate other handlers' records.


def test_malformed_log_arguments_cannot_trigger_logging_to_dump_the_record(
    diagnostic_log: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # pytest 9.1 attaches its own formatter even to non-propagating loggers.
    # Exercise the two production sinks without asking that unrelated formatter
    # to interpolate this deliberately malformed record.
    record = logging.LogRecord(
        "peaks.bridge", logging.ERROR, __file__, 1,
        "bridge.command.failed %s %s", ("PRIVATE-TOKEN",), None,
    )
    handlers = [
        handler for handler in logging.getLogger("peaks").handlers
        if isinstance(handler.formatter, DiagnosticFormatter)
    ]
    assert len(handlers) == 2
    for handler in handlers:
        handler.handle(record)
    output = diagnostic_log.read_text(encoding="utf-8") + capsys.readouterr().err
    assert "diagnostics.redacted" in output
    assert "PRIVATE-TOKEN" not in output
    assert "Logging error" not in output


def test_useful_stage_and_error_metadata_survives() -> None:
    message = "bridge.riot_qr.session.details_failed error_type=RiotClientError status=403"
    assert sanitize_diagnostic_message(message) == message
    message = "riot_session.authorization.complete rotated_cookie_count=4"
    assert sanitize_diagnostic_message(message) == message
    message = "riot_local.request.complete method=GET status=200"
    assert sanitize_diagnostic_message(message) == message
    assert (
        sanitize_diagnostic_message("bridge.session_maintenance.start account_slot=2")
        == "bridge.session_maintenance.start redacted=true"
    )
    assert sanitize_diagnostic_message("bridge.PRIVATE.entry status=403") == "diagnostics.redacted"
    assert (
        sanitize_diagnostic_message("bridge.command.failed error_type=PrivateError")
        == "bridge.command.failed redacted=true"
    )
    assert sanitize_diagnostic_message("x" * 20_000) == "diagnostics.redacted"


def test_current_structured_diagnostic_events_have_explicit_policy() -> None:
    source = Path(__file__).parents[1] / "src" / "peaks"
    for path in source.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if (
                node.func.attr not in {"debug", "info", "warning", "error", "exception"}
                or not node.args
            ):
                continue
            message = node.args[0]
            if isinstance(message, ast.Constant) and isinstance(message.value, str):
                event = message.value.split(" ", 1)[0]
                if re.fullmatch(r"[a-z_]+\.[a-z_.]+", event):
                    assert event in SAFE_EVENTS, (
                        f"Review diagnostic policy for {path.name}: {event}"
                    )

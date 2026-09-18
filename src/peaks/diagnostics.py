"""Redacted local diagnostics for the desktop backend.

The Electron bridge reserves stdout for line-delimited JSON, so diagnostics go
to stderr and a small rotating file beside Peaks' local database.  Callers must
log stage names, booleans, counts, and exception *types* only.  Credentials,
cookie values, tokens, lockfile contents, URLs with fragments, and Riot
identifiers never belong in these logs.
"""

from __future__ import annotations

import logging
import os
import sys
from copy import copy
from logging.handlers import RotatingFileHandler
from pathlib import Path

from peaks.diagnostic_policy import ERROR_TYPES, sanitize_diagnostic_message

DEFAULT_LOG_LEVEL = "INFO"
LOG_FILE_NAME = "peaks.log"
MAX_LOG_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 2
_HANDLER_MARKER = "_peaks_diagnostic_handler"


class DiagnosticFormatter(logging.Formatter):
    """Sanitize before either destination; never append raw traceback/source text."""

    def format(self, record: logging.LogRecord) -> str:
        safe = copy(record)
        try:
            safe.msg = sanitize_diagnostic_message(record.getMessage())
        except Exception:
            safe.msg = "diagnostics.redacted"
        if record.exc_info and record.exc_info[0]:
            name = record.exc_info[0].__name__
            safe.msg += f" exception_type={name if name in ERROR_TYPES else 'Exception'}"
        safe.args = ()
        safe.exc_info = None
        safe.exc_text = None
        safe.stack_info = None
        # Logger names and levels must not become another free-text channel.
        safe.name = "peaks"
        safe.levelname = {10: "DEBUG", 20: "INFO", 30: "WARNING", 40: "ERROR", 50: "CRITICAL"}.get(
            record.levelno, "LOG"
        )
        return super().format(safe)


def _log_level(value: str | None) -> int:
    candidate = str(value or DEFAULT_LOG_LEVEL).strip().upper()
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }.get(candidate, logging.INFO)


def configure_diagnostics(data_directory: Path) -> Path:
    """Configure redacted stderr and rotating-file diagnostics.

    Reconfiguration replaces only handlers installed by this function.  That
    keeps repeated Bridge construction deterministic in tests without
    disturbing an embedding application's logging setup.
    """

    data_directory.mkdir(parents=True, exist_ok=True)
    log_path = data_directory / LOG_FILE_NAME
    level = _log_level(os.getenv("PEAKS_LOG_LEVEL"))
    logger = logging.getLogger("peaks")
    logger.setLevel(level)
    logger.propagate = False

    for handler in tuple(logger.handlers):
        if getattr(handler, _HANDLER_MARKER, False):
            logger.removeHandler(handler)
            handler.close()

    formatter = DiagnosticFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    stream = logging.StreamHandler(sys.stderr)
    stream.setLevel(level)
    stream.setFormatter(formatter)
    setattr(stream, _HANDLER_MARKER, True)

    rotating = RotatingFileHandler(
        log_path,
        maxBytes=MAX_LOG_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    rotating.setLevel(level)
    rotating.setFormatter(formatter)
    setattr(rotating, _HANDLER_MARKER, True)

    logger.addHandler(stream)
    logger.addHandler(rotating)
    logger.info("diagnostics.ready level=%s", logging.getLevelName(level))
    return log_path


__all__ = ["LOG_FILE_NAME", "configure_diagnostics"]

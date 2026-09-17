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
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_LEVEL = "INFO"
LOG_FILE_NAME = "peaks.log"
MAX_LOG_BYTES = 1 * 1024 * 1024
LOG_BACKUP_COUNT = 2
_HANDLER_MARKER = "_peaks_diagnostic_handler"


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

    formatter = logging.Formatter(
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

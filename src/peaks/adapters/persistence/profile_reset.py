"""Crash-recoverable deletion of Peaks' exact local profile files."""

from __future__ import annotations

import os
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

RESET_MARKER = ".reset.pending"


def _atomic_marker(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(b"Peaks local profile reset pending\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def begin_profile_reset(profile_dir: Path) -> Path:
    marker = profile_dir / RESET_MARKER
    _atomic_marker(marker)
    return marker


def clear_profile_files(profile_dir: Path, *, keep_marker: bool = True) -> None:
    """Delete only files currently owned by Peaks; never recurse."""

    exact_names = (
        "peaks.sqlite3",
        "peaks.sqlite3-wal",
        "peaks.sqlite3-shm",
        "peaks.sqlite3-journal",
        "vault.json",
        ".vault-pepper",
        ".vault-pepper.dpapi",
    )
    for name in exact_names:
        with suppress(FileNotFoundError):
            (profile_dir / name).unlink()
    for temporary in profile_dir.glob(".vault.json.*.tmp"):
        with suppress(FileNotFoundError):
            temporary.unlink()
    if not keep_marker:
        with suppress(FileNotFoundError):
            (profile_dir / RESET_MARKER).unlink()


def recover_pending_reset(profile_dir: Path) -> bool:
    marker = profile_dir / RESET_MARKER
    if not marker.is_file():
        return False
    clear_profile_files(profile_dir, keep_marker=False)
    return True

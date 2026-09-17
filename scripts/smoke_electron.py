#!/usr/bin/env python3
"""Bounded demo startup check for the packaged Electron renderer and bridge."""

from __future__ import annotations

import os
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    directory = ROOT / "release" / "electron"
    if sys.platform == "win32":
        executable = directory / "win-unpacked" / "Peaks.exe"
    elif sys.platform == "darwin":
        executable = directory / "mac-arm64" / "Peaks.app" / "Contents" / "MacOS" / "Peaks"
    else:
        raise RuntimeError("Packaged Electron smoke supports Windows and macOS")
    if not executable.is_file():
        raise FileNotFoundError("Packaged Electron executable was not produced")
    screenshot = directory / "smoke" / "demo.png"
    screenshot.parent.mkdir(parents=True, exist_ok=True)
    screenshot.unlink(missing_ok=True)
    env = os.environ.copy()
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env["PEAKS_DEMO"] = "1"
    env["PEAKS_SCREENSHOT"] = str(screenshot)
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
    subprocess.run(
        [str(executable)],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=60,
        startupinfo=startupinfo,
    )
    image = screenshot.read_bytes()
    if image[:8] != b"\x89PNG\r\n\x1a\n" or len(image) < 1024:
        raise RuntimeError("Packaged Electron did not render a valid startup screenshot")
    width, height = struct.unpack(">II", image[16:24])
    if width < 1000 or height < 600:
        raise RuntimeError("Packaged Electron rendered an unexpected startup viewport")
    print(f"Packaged Electron started and rendered a {width} x {height} demo window")


if __name__ == "__main__":
    main()

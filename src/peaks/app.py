"""Launch the Electron/Chromium Peaks desktop shell."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Start Electron while keeping this Python environment for the backend."""
    root = Path(__file__).resolve().parents[2]
    electron = root / "node_modules" / ".bin" / ("electron.cmd" if os.name == "nt" else "electron")
    if not electron.exists():
        located = shutil.which("electron")
        if not located:
            print("Electron dependencies are missing. Run `npm install` first.", file=sys.stderr)
            return 1
        electron = Path(located)
    env = {**os.environ, "PEAKS_PYTHON": sys.executable}
    return subprocess.call([str(electron), str(root), *sys.argv[1:]], cwd=root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())

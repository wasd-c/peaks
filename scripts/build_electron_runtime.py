#!/usr/bin/env python3
"""Build Electron's frozen Python bridge and stage its Patchright Chromium.

The output is intentionally placed under ``build/electron-runtime`` so
Electron Builder can copy only explicit, reproducible resources into the app.
The browser is installed into that staging directory at build time; a packaged
Peaks installation never downloads an executable on first use.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "packaging" / "PeaksBridge.spec"
RUNTIME_ROOT = ROOT / "build" / "electron-runtime"
BACKEND_DIST = RUNTIME_ROOT / "backend"
BROWSER_ROOT = RUNTIME_ROOT / "patchright-browsers"
MANIFEST = RUNTIME_ROOT / "runtime-manifest.json"


def _run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> None:
    print(f"[electron-runtime] {' '.join(command)}")
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=timeout)


def _safe_clean() -> None:
    expected = (ROOT / "build" / "electron-runtime").resolve()
    target = RUNTIME_ROOT.resolve()
    if target != expected or ROOT.resolve() not in target.parents:
        raise RuntimeError(f"refusing to clean unexpected runtime directory: {target}")
    if target.exists():
        print(f"[electron-runtime] removing {target}")
        shutil.rmtree(target)


def _patchright_browser_descriptor() -> dict[str, str]:
    package = metadata.distribution("patchright")
    browser_json = Path(package.locate_file("patchright/driver/package/browsers.json"))
    document: Any = json.loads(browser_json.read_text(encoding="utf-8"))
    browsers = document.get("browsers") if isinstance(document, dict) else None
    if not isinstance(browsers, list):
        raise RuntimeError("Patchright browser manifest is invalid")
    chromium = next(
        (item for item in browsers if isinstance(item, dict) and item.get("name") == "chromium"),
        None,
    )
    ffmpeg = next(
        (item for item in browsers if isinstance(item, dict) and item.get("name") == "ffmpeg"),
        None,
    )
    if not isinstance(chromium, dict):
        raise RuntimeError("Patchright browser manifest has no Chromium entry")
    revision = chromium.get("revision")
    browser_version = chromium.get("browserVersion")
    if not isinstance(revision, str) or not revision:
        raise RuntimeError("Patchright Chromium revision is invalid")
    if not isinstance(browser_version, str) or not browser_version:
        raise RuntimeError("Patchright Chromium version is invalid")
    ffmpeg_revision = ffmpeg.get("revision") if isinstance(ffmpeg, dict) else None
    if not isinstance(ffmpeg_revision, str) or not ffmpeg_revision:
        raise RuntimeError("Patchright FFmpeg revision is invalid")
    return {
        "revision": revision,
        "browserVersion": browser_version,
        "ffmpegRevision": ffmpeg_revision,
    }


def _stage_browser() -> dict[str, str]:
    descriptor = _patchright_browser_descriptor()
    BROWSER_ROOT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_ROOT)
    _run(
        [
            sys.executable,
            "-m",
            "patchright",
            "install",
            "--no-shell",
            "chromium",
        ],
        env=env,
    )

    # Patchright's build-time ownership link contains an absolute developer or
    # CI path and is only used for cache garbage collection. It is neither
    # needed nor appropriate in a distributable application resource.
    links = BROWSER_ROOT / ".links"
    if links.exists():
        shutil.rmtree(links)
    # Winldd validates host dependencies during installation. It is not used by
    # Patchright at runtime, so keep it out of the application resources.
    for build_tool in BROWSER_ROOT.glob("winldd-*"):
        if build_tool.is_dir():
            shutil.rmtree(build_tool)

    chromium_directories = sorted(
        path
        for path in BROWSER_ROOT.glob("chromium-*")
        if path.is_dir() and "headless" not in path.name
    )
    expected_name = f"chromium-{descriptor['revision']}"
    if [path.name for path in chromium_directories] != [expected_name]:
        raise RuntimeError(
            "staged Patchright browser revision does not match the pinned package"
        )
    chromium_root = chromium_directories[0]
    if not (chromium_root / "INSTALLATION_COMPLETE").is_file():
        raise RuntimeError("staged Patchright Chromium is incomplete")
    if sys.platform == "win32":
        executable = chromium_root / "chrome-win64" / "chrome.exe"
        if not executable.is_file():
            raise RuntimeError("staged Patchright Chromium executable is missing")
    chromium_notice = chromium_root / "chrome-win64" / "ABOUT"
    if sys.platform == "win32" and not chromium_notice.is_file():
        raise RuntimeError("staged Patchright Chromium notice is missing")

    ffmpeg_root = BROWSER_ROOT / f"ffmpeg-{descriptor['ffmpegRevision']}"
    ffmpeg_notice = ffmpeg_root / "COPYING.LGPLv2.1"
    if not ffmpeg_notice.is_file():
        raise RuntimeError("staged Patchright FFmpeg LGPL notice is missing")

    descriptor["patchrightVersion"] = metadata.version("patchright")
    descriptor["chromiumNotice"] = "chromium-*/chrome-win64/ABOUT"
    descriptor["ffmpegNotice"] = f"ffmpeg-{descriptor['ffmpegRevision']}/COPYING.LGPLv2.1"
    return descriptor


def _build_backend() -> Path:
    if not SPEC.is_file():
        raise FileNotFoundError(f"Electron bridge spec not found: {SPEC}")
    BACKEND_DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="peaks-electron-bridge-") as temp_dir:
        _run(
            [
                sys.executable,
                "-m",
                "PyInstaller",
                "--clean",
                "--noconfirm",
                "--workpath",
                str(Path(temp_dir) / "work"),
                "--distpath",
                str(BACKEND_DIST),
                str(SPEC),
            ]
        )
    executable = BACKEND_DIST / "PeaksBridge" / (
        "PeaksBridge.exe" if sys.platform == "win32" else "PeaksBridge"
    )
    if not executable.is_file():
        raise FileNotFoundError(f"frozen Electron bridge was not produced: {executable}")
    return executable


def _smoke_backend(executable: Path, *, browser: bool) -> None:
    env = os.environ.copy()
    env["PEAKS_DEMO"] = "1"
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSER_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if browser:
        env["PEAKS_PACKAGING_BROWSER_SMOKE"] = "1"
        _run([str(executable)], env=env, timeout=30)
        return

    requests = (
        json.dumps({"id": 1, "command": "state", "payload": {}}, ensure_ascii=False)
        + "\n"
        + json.dumps(
            {"id": 2, "command": "pin", "payload": {"pin": "2580"}},
            ensure_ascii=False,
        )
        + "\n"
        + json.dumps(
            {
                "id": 3,
                "command": "search",
                "payload": {"query": "ズーム#JP", "region": "JP", "game": "VALORANT"},
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    print(f"[electron-runtime] smoke testing {executable}")
    completed = subprocess.run(
        [str(executable)],
        cwd=ROOT,
        env=env,
        input=requests,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=15,
        check=True,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 3:
        raise RuntimeError("frozen Electron bridge returned invalid smoke output")
    state_response: Any = json.loads(lines[0])
    if not isinstance(state_response, dict) or state_response.get("id") != 1:
        raise RuntimeError("frozen Electron bridge returned an invalid smoke response")
    result = state_response.get("result")
    if not isinstance(result, dict) or result.get("locked") is not True:
        raise RuntimeError("frozen Electron bridge did not return its initial state")
    unlock_response: Any = json.loads(lines[1])
    unlock_result = unlock_response.get("result") if isinstance(unlock_response, dict) else None
    if (
        unlock_response.get("id") != 2
        or not isinstance(unlock_result, dict)
        or unlock_result.get("locked") is not False
    ):
        raise RuntimeError("frozen Electron bridge did not unlock before search")
    search_response: Any = json.loads(lines[2])
    search_result = search_response.get("result") if isinstance(search_response, dict) else None
    if (
        search_response.get("id") != 3
        or not isinstance(search_result, list)
        or not search_result
        or search_result[0].get("riotId") != "ズーム#JP"
    ):
        raise RuntimeError("frozen Electron bridge did not round-trip Unicode IPC")


def build(*, clean: bool, smoke: bool) -> Path:
    if clean:
        _safe_clean()
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    browser = _stage_browser()
    executable = _build_backend()
    manifest = {
        "backend": f"backend/{executable.name}",
        "browser": browser,
        "machine": platform.machine(),
        "platform": sys.platform,
    }
    MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if smoke:
        _smoke_backend(executable, browser=False)
        _smoke_backend(executable, browser=True)
    print(f"[electron-runtime] ready: {RUNTIME_ROOT}")
    return executable


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove only build/electron-runtime before staging",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="exercise the frozen bridge and its exact staged Chromium",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    build(clean=args.clean, smoke=args.smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

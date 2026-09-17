# ruff: noqa: F821
"""PyInstaller onedir spec for the backend embedded in Electron.

This is deliberately separate from Peaks.spec, which still builds the legacy
Qt application. The bridge retains working stdin/stdout pipes and decodes the
trusted Electron window bitmap without shipping Qt.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules,
    copy_metadata,
)

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
ENTRY = ROOT / "packaging" / "electron_bridge_entrypoint.py"
APP_ICON = SRC / "peaks" / "ui" / "assets" / (
    "peaks.ico" if sys.platform == "win32" else "peaks.icns"
)

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []


def _append_unique(values: list[tuple[str, str]], item: tuple[str, str]) -> None:
    if item not in values:
        values.append(item)


def _collect(package: str) -> None:
    if importlib.util.find_spec(package) is None:
        return
    package_datas, package_binaries, package_hidden = collect_all(package)
    for item in package_datas:
        _append_unique(datas, item)
    for item in package_binaries:
        _append_unique(binaries, item)
    hiddenimports.extend(package_hidden)


for package in ("cryptography", "keyring", "patchright", "zxingcpp"):
    _collect(package)

# Patchright uses package data for its Node driver. Metadata also preserves its
# license in the backend onedir artifact.
for package in ("patchright", "keyring"):
    try:
        for item in copy_metadata(package):
            _append_unique(datas, item)
    except Exception as error:
        print(f"[bridge-spec] metadata for {package} was not collected: {error}")

def _is_bridge_module(name: str) -> bool:
    excluded_modules = {"peaks.__main__", "peaks.app", "peaks.application.qr_capture"}
    return name not in excluded_modules and not name.startswith("peaks.ui.") and name != "peaks.ui"


# Bridge services import providers lazily after unlock or user actions.
hiddenimports.extend(collect_submodules("peaks", filter=_is_bridge_module))
if sys.platform == "win32":
    hiddenimports.append("keyring.backends.Windows")
elif sys.platform == "darwin":
    hiddenimports.extend(["keyring.backends.macOS", "keyring.backends.macOS.api"])

for document in ("LICENSE", "SECURITY.md", "THIRD_PARTY_NOTICES.md"):
    source = ROOT / document
    if source.is_file():
        datas.append((str(source), "."))

analysis = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PySide6",
        "matplotlib",
        "peaks.app",
        "peaks.application.qr_capture",
        "peaks.ui",
        "pytest",
        "tkinter",
    ],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="PeaksBridge",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    icon=str(APP_ICON),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    name="PeaksBridge",
)

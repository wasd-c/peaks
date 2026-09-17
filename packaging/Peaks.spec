# ruff: noqa: F821
"""PyInstaller onedir spec for the legacy Qt Peaks application.

Electron packages its stdin/stdout service with ``PeaksBridge.spec``. Keep the
two entry points separate: a windowed PyInstaller executable cannot provide
the reliable pipes required by Electron's line-delimited JSON protocol.

The spec is evaluated on the target OS. It intentionally keeps the Qt runtime
and native helpers in the onedir output and never enables UPX compression. The
build script supplies PEAKS_VERSION_FILE during Windows builds so the EXE
contains normal product/version metadata.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
)

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
ENTRY = ROOT / "packaging" / "entrypoint.py"

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []


def _append_unique(values: list[tuple[str, str]], item: tuple[str, str]) -> None:
    if item not in values:
        values.append(item)


def _append_source_if_missing(source: Path, destination: str) -> None:
    """Add a source data file unless collect_all already found that file."""

    resolved = source.resolve()
    for existing, _ in datas:
        try:
            if Path(existing).resolve() == resolved:
                return
        except OSError:
            continue
    datas.append((str(source), destination))


def _collect(package: str) -> None:
    """Collect an installed package when present in the selected extra set."""

    if importlib.util.find_spec(package) is None:
        return
    try:
        package_datas, package_binaries, package_hidden = collect_all(package)
    except Exception as error:
        print(f"[spec] package {package} was not collected: {error}")
        return
    for item in package_datas:
        _append_unique(datas, item)
    for item in package_binaries:
        _append_unique(binaries, item)
    hiddenimports.extend(package_hidden)


# PySide6's own hooks know how to select platform Qt plugins. We intentionally
# do not call collect_all("PySide6"): it exposes hundreds of optional modules
# and doing so needlessly balloons the analysis graph and artifact. The
# explicit Qt imports below activate hooks for the QML modules Peaks uses.
for package in (
    "peaks",
    "keyring",
    "cryptography",
    # Patchright ships a native Node driver and JavaScript package data. Its
    # upstream PyInstaller hook is currently named for Playwright, so collect
    # the package explicitly instead of relying on import discovery alone.
    # Browser executables are deliberately not part of the Python wheel and
    # are not pulled into this build.
    "patchright",
    "zxingcpp",
):
    _collect(package)

# Preserve Patchright's Apache-2.0 license and package metadata in the onedir
# artifact. collect_all() intentionally targets importable package data and
# does not copy dist-info license files.
try:
    for item in copy_metadata("patchright"):
        _append_unique(datas, item)
except Exception as error:
    print(f"[spec] Patchright metadata collection skipped: {error}")

# Add every Peaks module explicitly. This protects the frozen build when the
# app loads adapters or pages dynamically from a registry.
try:
    hiddenimports.extend(collect_submodules("peaks"))
except Exception as error:
    print(f"[spec] could not enumerate Peaks modules: {error}")

hiddenimports.extend(
    [
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtQml",
        "PySide6.QtQuickControls2",
    ]
)
if sys.platform == "win32":
    hiddenimports.append("keyring.backends.Windows")
elif sys.platform == "darwin":
    hiddenimports.extend(["keyring.backends.macOS", "keyring.backends.macOS.api"])

# Be explicit about user-facing QML and image assets. collect_all("peaks")
# handles package data in normal installations; these paths also support an
# editable checkout where the assets are not represented in wheel metadata.
UI_DATA_SUFFIXES = {
    ".css",
    ".gif",
    ".icns",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".otf",
    ".png",
    ".qrc",
    ".qml",
    ".qss",
    ".svg",
    ".ttf",
    ".webp",
}
UI_ROOT = SRC / "peaks" / "ui"
APP_ICON = UI_ROOT / "assets" / ("peaks.ico" if sys.platform == "win32" else "peaks.icns")
if UI_ROOT.is_dir():
    for source in UI_ROOT.rglob("*"):
        if source.is_file() and source.suffix.lower() in UI_DATA_SUFFIXES:
            destination = (source.relative_to(SRC).parent).as_posix()
            _append_source_if_missing(source, destination)
try:
    for item in collect_data_files("peaks", include_py_files=False):
        _append_unique(datas, item)
except Exception as error:
    print(f"[spec] package asset collection skipped: {error}")

# Keep the application and adapted-source license notices beside the frozen
# executable. They are small, auditable inputs and do not pull any external
# source tree or browser cache into the artifact.
for document in ("LICENSE", "SECURITY.md", "THIRD_PARTY_NOTICES.md"):
    source = ROOT / document
    if source.is_file():
        _append_source_if_missing(source, ".")


version_file = os.environ.get("PEAKS_VERSION_FILE")
version_file_path = Path(version_file) if version_file else None
if version_file_path and not version_file_path.is_file():
    raise FileNotFoundError(f"PEAKS_VERSION_FILE does not exist: {version_file_path}")
project_version = os.environ.get("PEAKS_VERSION", "0.0.0")

analysis = Analysis(
    [str(ENTRY)],
    pathex=[str(SRC), str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "packaging" / "hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "unittest", "matplotlib"],
    noarchive=False,
)

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="Peaks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(APP_ICON),
    version=str(version_file_path) if version_file_path else None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    name="Peaks",
)

if sys.platform == "darwin":
    # PyInstaller's BUNDLE creates a native .app while retaining onedir
    # semantics inside Contents/Frameworks and Contents/Resources.
    app = BUNDLE(
        coll,
        name="Peaks.app",
        icon=str(APP_ICON),
        bundle_identifier="com.peaks.desktop",
        info_plist={
            "CFBundleDisplayName": "Peaks",
            "CFBundleName": "Peaks",
            "CFBundleShortVersionString": project_version,
            "CFBundleVersion": project_version,
        },
    )

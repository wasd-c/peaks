#!/usr/bin/env python3
"""Verify that Windows updater metadata names the exact local installer bytes."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote

import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLED_FILES = ("Peaks.exe", "resources/app.asar", "resources/backend/PeaksBridge.exe")


def _digest(path: Path, algorithm: str) -> bytes:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).digest()


def verify(directory: Path, expected_version: str) -> list[Path]:
    directory = directory.resolve(strict=True)
    metadata_path = directory / "latest.yml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("version") != expected_version:
        raise ValueError("Windows update version does not match package.json")
    entries = metadata.get("files")
    if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
        raise ValueError("Expected exactly one Windows installer in update metadata")
    entry = entries[0]
    url = entry.get("url")
    if not isinstance(url, str):
        raise ValueError("Missing Windows installer filename")
    name = unquote(url)
    if any(part in name for part in ("/", "\\", ":", "\x00")) or not name.endswith(".exe"):
        raise ValueError("Update installer must be a local .exe filename")
    installer = directory / name
    if installer.resolve(strict=True).parent != directory or not installer.is_file():
        raise ValueError("Windows installer escapes the artifact directory")
    if {path.name for path in directory.glob("*.exe")} != {name}:
        raise ValueError("Unexpected Windows installer files in artifact directory")
    size = entry.get("size")
    if isinstance(size, bool) or not isinstance(size, int) or size != installer.stat().st_size:
        raise ValueError("Windows update installer size does not match")
    checksum = base64.b64encode(_digest(installer, "sha512")).decode("ascii")
    if entry.get("sha512") != checksum or metadata.get("sha512") != checksum:
        raise ValueError("Windows update installer checksum does not match")
    if unquote(str(metadata.get("path", ""))) != name:
        raise ValueError("Legacy Windows update path disagrees with files metadata")
    blockmap = directory / f"{name}.blockmap"
    if not blockmap.is_file() or blockmap.stat().st_size == 0:
        raise ValueError("Windows differential update blockmap is missing or empty")
    if blockmap.resolve(strict=True).parent != directory:
        raise ValueError("Windows blockmap escapes the artifact directory")
    return [installer, blockmap, metadata_path]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    files = verify(args.directory, package["version"])
    installed = args.directory / "win-unpacked"
    manifest = {
        "version": package["version"],
        "files": {name: _digest(installed / name, "sha256").hex() for name in INSTALLED_FILES},
    }
    manifest_path = args.directory / "installed-files-sha256.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    files.append(manifest_path)
    checksums = "".join(f"{_digest(path, 'sha256').hex()}  {path.name}\n" for path in files)
    (args.directory / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    print(
        f"Verified Windows update {package['version']}: installer, blockmap, metadata, installed-file hashes"
    )


if __name__ == "__main__":
    main()

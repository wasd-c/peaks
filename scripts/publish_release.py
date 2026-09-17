#!/usr/bin/env python3
"""Publish only a matching tag and five verified Windows release artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from verify_update_artifacts import INSTALLED_FILES, ROOT, verify

REPOSITORY = "wasd-c/peaks"


def _gh(*args: str) -> str:
    try:
        result = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=600, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("GitHub operation timed out") from None
    if result.returncode:
        # Do not print subprocess output: network errors may contain signed URLs.
        raise RuntimeError(f"GitHub operation failed ({args[0]}, exit {result.returncode})")
    return result.stdout


def _api(endpoint: str) -> Any:
    return json.loads(_gh("api", f"repos/{REPOSITORY}/{endpoint}"))


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_inputs(directory: Path, version: str) -> list[Path]:
    files = verify(directory, version)
    manifest_path = directory / "installed-files-sha256.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"version", "files"}
        or manifest["version"] != version
    ):
        raise ValueError("Installed-file manifest version or shape is invalid")
    hashes = manifest["files"]
    if not isinstance(hashes, dict) or set(hashes) != set(INSTALLED_FILES):
        raise ValueError("Installed-file manifest has unexpected paths")
    if not all(
        isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in hashes.values()
    ):
        raise ValueError("Installed-file manifest has invalid hashes")
    files.append(manifest_path)
    checksum_path = directory / "SHA256SUMS.txt"
    expected = {path.name: _sha256(path) for path in files}
    listed = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or name in listed:
            raise ValueError("Invalid or duplicate release checksum entry")
        listed[name] = digest
    if listed != expected:
        raise ValueError("Release checksums do not match the artifact bytes")
    return [*files, checksum_path]


def _upload(tag: str, path: Path) -> None:
    for attempt in range(3):
        try:
            _gh("release", "upload", tag, str(path), "--repo", REPOSITORY, "--clobber")
            return
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(5 * (attempt + 1))


def publish(directory: Path, version: str, expected_commit: str) -> None:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Only stable semantic release versions can be published")
    if not re.fullmatch(r"[a-f0-9]{40}", expected_commit):
        raise ValueError("An exact verified commit SHA is required")
    files = verify_inputs(directory, version)
    tag = f"v{version}"
    if _api(f"commits/{tag}").get("sha") != expected_commit:
        raise ValueError("Release tag does not point to the verified workflow commit")
    releases = _api("releases?per_page=100")
    matches = [release for release in releases if release.get("tag_name") == tag]
    if len(matches) > 1:
        raise ValueError("Multiple releases use the requested tag")
    if matches:
        release = matches[0]
        if release.get("draft") is not True:
            raise ValueError("Refusing to replace an already published release")
    else:
        _gh(
            "release",
            "create",
            tag,
            "--repo",
            REPOSITORY,
            "--verify-tag",
            "--draft",
            "--title",
            f"Peaks {version}",
            "--notes",
            "Windows desktop release with in-app updates.",
        )
        release = _api(f"releases/tags/{tag}")
    for path in files:
        print(f"Uploading {path.name}", flush=True)
        _upload(tag, path)
    release = _api(f"releases/{release['id']}")
    if release.get("draft") is not True:
        raise ValueError("Release visibility changed while uploading")
    assets = release.get("assets", [])
    expected = {path.name: path for path in files}
    if len(assets) != len(expected) or {asset.get("name") for asset in assets} != set(expected):
        raise ValueError("Release does not contain exactly the five expected assets")
    with tempfile.TemporaryDirectory(prefix="peaks-release-verify-") as temporary:
        for asset in assets:
            path = expected[asset["name"]]
            if asset.get("state") != "uploaded" or asset.get("size") != path.stat().st_size:
                raise ValueError("A release asset has not finished uploading")
            expected_digest = _sha256(path)
            digest = asset.get("digest")
            if digest:
                if digest != f"sha256:{expected_digest}":
                    raise ValueError("Uploaded release asset hash does not match")
            else:
                _gh(
                    "release",
                    "download",
                    tag,
                    "--repo",
                    REPOSITORY,
                    "--pattern",
                    path.name,
                    "--dir",
                    temporary,
                )
                if _sha256(Path(temporary) / path.name) != expected_digest:
                    raise ValueError("Downloaded release asset hash does not match")
    # Recheck tag binding after the upload before making the draft public.
    if _api(f"commits/{tag}").get("sha") != expected_commit:
        raise ValueError("Release tag changed during upload")
    _gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--latest")
    print(f"Published {tag}; all five asset sizes and SHA-256 hashes verified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    if (
        os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
    ):
        raise RuntimeError(
            "Release publishing requires an explicit workflow dispatch in wasd-c/peaks"
        )
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    publish(args.directory, package["version"], os.environ.get("PEAKS_RELEASE_COMMIT", ""))


if __name__ == "__main__":
    main()

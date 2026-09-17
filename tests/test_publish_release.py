"""A release must remain a draft until all expected uploads are verified."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml


@pytest.fixture
def release(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[ModuleType, Path, list[tuple[str, ...]], dict[str, Any]]:
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    module = importlib.import_module("publish_release")
    name = "Peaks-Setup-0.3.0-x64.exe"
    installer = tmp_path / name
    installer.write_bytes(b"synthetic installer")
    (tmp_path / f"{name}.blockmap").write_bytes(b"synthetic blockmap")
    digest = base64.b64encode(hashlib.sha512(installer.read_bytes()).digest()).decode("ascii")
    metadata = {
        "version": "0.3.0",
        "path": name,
        "sha512": digest,
        "files": [{"url": name, "sha512": digest, "size": installer.stat().st_size}],
    }
    (tmp_path / "latest.yml").write_text(yaml.safe_dump(metadata), encoding="utf-8")
    (tmp_path / "installed-files-sha256.json").write_text(
        json.dumps({"version": "0.3.0", "files": dict.fromkeys(module.INSTALLED_FILES, "a" * 64)}),
        encoding="utf-8",
    )
    files = list(tmp_path.iterdir())
    (tmp_path / "SHA256SUMS.txt").write_text(
        "".join(f"{module._sha256(path)}  {path.name}\n" for path in files), encoding="utf-8"
    )
    assets = [
        {
            "name": path.name,
            "state": "uploaded",
            "size": path.stat().st_size,
            "digest": f"sha256:{module._sha256(path)}",
        }
        for path in tmp_path.iterdir()
    ]
    state: dict[str, Any] = {
        "sha": "a" * 40,
        "release": {"id": 1, "draft": True, "tag_name": "v0.3.0", "assets": assets},
    }
    calls: list[tuple[str, ...]] = []

    def api(endpoint: str) -> Any:
        if endpoint.startswith("commits/"):
            return {"sha": state["sha"]}
        if endpoint.startswith("releases?"):
            return [state["release"]]
        return state["release"]

    def gh(*args: str) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(module, "_api", api)
    monkeypatch.setattr(module, "_gh", gh)
    return module, tmp_path, calls, state


def test_publishes_only_after_five_verified_uploads(
    release: tuple[ModuleType, Path, list[tuple[str, ...]], dict[str, Any]],
) -> None:
    module, directory, calls, _state = release
    module.publish(directory, "0.3.0", "a" * 40)
    assert len(calls) == 6
    assert all(call[:2] == ("release", "upload") for call in calls[:5])
    assert calls[-1][:2] == ("release", "edit")
    assert "--draft=false" in calls[-1]


@pytest.mark.parametrize("failure", ["tag", "published", "hash", "uploading", "missing"])
def test_never_publishes_incomplete_or_unbound_release(
    release: tuple[ModuleType, Path, list[tuple[str, ...]], dict[str, Any]], failure: str
) -> None:
    module, directory, calls, state = release
    if failure == "tag":
        state["sha"] = "b" * 40
    elif failure == "published":
        state["release"]["draft"] = False
    elif failure == "hash":
        state["release"]["assets"][0]["digest"] = "sha256:" + "b" * 64
    elif failure == "uploading":
        state["release"]["assets"][0]["state"] = "starter"
    else:
        state["release"]["assets"].pop()
    with pytest.raises(ValueError):
        module.publish(directory, "0.3.0", "a" * 40)
    assert all(call[:2] != ("release", "edit") for call in calls)

"""Update metadata must describe the bytes actually attached to a release."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml


@pytest.fixture
def verifier() -> ModuleType:
    source = Path(__file__).resolve().parents[1] / "scripts" / "verify_update_artifacts.py"
    spec = importlib.util.spec_from_file_location("verify_update_artifacts", source)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def update(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    name = "Peaks Setup 0.3.0.exe"
    data = b"synthetic installer bytes"
    (tmp_path / name).write_bytes(data)
    (tmp_path / f"{name}.blockmap").write_bytes(b"synthetic blockmap")
    checksum = base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")
    document = {
        "version": "0.3.0",
        "path": name,
        "sha512": checksum,
        "files": [{"url": name, "sha512": checksum, "size": len(data)}],
    }
    (tmp_path / "latest.yml").write_text(yaml.safe_dump(document), encoding="utf-8")
    return tmp_path, document


def test_valid_update_returns_exact_release_files(
    verifier: ModuleType, update: tuple[Path, dict[str, Any]]
) -> None:
    directory, document = update
    assert [path.name for path in verifier.verify(directory, "0.3.0")] == [
        document["path"],
        document["path"] + ".blockmap",
        "latest.yml",
    ]


@pytest.mark.parametrize(
    "field,value", [("version", "0.2.0"), ("path", "another.exe"), ("sha512", "mismatched")]
)
def test_rejects_inconsistent_metadata(
    verifier: ModuleType, update: tuple[Path, dict[str, Any]], field: str, value: str
) -> None:
    directory, document = update
    document[field] = value
    (directory / "latest.yml").write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError):
        verifier.verify(directory, "0.3.0")


@pytest.mark.parametrize(
    "url",
    ["../outside.exe", "https://example.com/setup.exe", "%2e%2e%2foutside.exe", "C:\\outside.exe"],
)
def test_rejects_external_installer_paths(
    verifier: ModuleType, update: tuple[Path, dict[str, Any]], url: str
) -> None:
    directory, document = update
    document["files"][0]["url"] = url
    (directory / "latest.yml").write_text(yaml.safe_dump(document), encoding="utf-8")
    with pytest.raises(ValueError, match=r"local \.exe"):
        verifier.verify(directory, "0.3.0")


def test_rejects_installer_tampering(
    verifier: ModuleType, update: tuple[Path, dict[str, Any]]
) -> None:
    directory, document = update
    installer = directory / document["path"]
    installer.write_bytes(b"x" * installer.stat().st_size)
    with pytest.raises(ValueError, match="checksum"):
        verifier.verify(directory, "0.3.0")


def test_rejects_missing_blockmap(
    verifier: ModuleType, update: tuple[Path, dict[str, Any]]
) -> None:
    directory, document = update
    (directory / (document["path"] + ".blockmap")).unlink()
    with pytest.raises(ValueError, match="blockmap"):
        verifier.verify(directory, "0.3.0")


def test_rejects_stale_extra_installers(
    verifier: ModuleType, update: tuple[Path, dict[str, Any]]
) -> None:
    directory, _document = update
    (directory / "Peaks Setup 0.2.0.exe").touch()
    with pytest.raises(ValueError, match="Unexpected Windows installer"):
        verifier.verify(directory, "0.3.0")

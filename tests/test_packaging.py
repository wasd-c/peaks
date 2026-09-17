"""Focused checks for the native packaging and release guardrails."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _build_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "peaks_build_script", ROOT / "scripts" / "build.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load scripts/build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _electron_runtime_module() -> ModuleType:
    source = ROOT / "scripts" / "build_electron_runtime.py"
    spec = importlib.util.spec_from_file_location("peaks_electron_runtime", source)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load scripts/build_electron_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_parser_exposes_an_explicit_signing_guard() -> None:
    module = _build_module()
    args = module._parser().parse_args(["--release", "--installer"])

    assert args.release is True
    assert args.installer is True


def test_release_build_fails_before_pyinstaller_without_a_hook(tmp_path: Path) -> None:
    module = _build_module()
    missing_spec = tmp_path / "missing.spec"
    original_spec = module.SPEC
    module.SPEC = missing_spec
    try:
        with pytest.raises(RuntimeError, match="require a signing hook"):
            module.build(
                clean=False,
                smoke=False,
                smoke_timeout=1,
                sign_hook=None,
                release=True,
            )
    finally:
        module.SPEC = original_spec


def test_sign_target_invokes_configured_hook(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _build_module()
    target = tmp_path / "Peaks"
    target.mkdir()
    hook = tmp_path / "sign.sh"
    hook.write_text("#!/bin/sh\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(module, "_run", lambda command: calls.append(command))

    module._sign_target(target, str(hook), required=True)

    assert calls == [[str(hook.resolve()), str(target)]]


def test_installer_script_has_no_wildcard_deletion() -> None:
    installer = (ROOT / "packaging" / "Peaks.iss").read_text(encoding="utf-8")

    assert "[InstallDelete]" not in installer
    assert "[UninstallDelete]" not in installer
    assert "{app}\\*" not in installer


def test_ci_builds_verified_electron_updates_without_publishing() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["defaults"]["run"]["shell"] == "bash"
    steps = workflow["jobs"]["verify-and-package"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)
    assert "npm ci" in commands
    assert "uv sync --dev --locked" in commands
    assert "npm test" in commands and "uv run pytest" in commands
    assert "npm run build:runtime" in commands
    assert "scripts/smoke_electron.py" in commands
    assert "scripts/verify_update_artifacts.py" in commands
    assert "shasum -a 256" in commands
    package_commands = [step["run"] for step in steps if "electron-builder" in step.get("run", "")]
    assert len(package_commands) == 2
    assert all("--publish never" in command for command in package_commands)
    assert any("--win nsis --x64" in command for command in package_commands)
    assert any("--mac dmg zip --arm64" in command for command in package_commands)
    assert "scripts/build.py" not in commands
    uploads = [
        step["with"]["path"]
        for step in steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
    ]
    assert any(
        "latest.yml" in paths and "*.exe.blockmap" in paths and "*.exe" in paths
        for paths in uploads
    )


def test_electron_builder_embeds_only_the_frozen_runtime_browser_and_brand_icon() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    resources = package["build"]["extraResources"]
    assert {item["to"] for item in resources} == {
        "backend",
        "patchright-browsers",
        "runtime-manifest.json",
        "brand/peaks-mark.png",
    }
    assert all(
        item["from"] == "src/renderer/assets/peaks-mark.png"
        if item["to"] == "brand/peaks-mark.png"
        else item["from"].startswith("build/electron-runtime/")
        for item in resources
    )
    assert "src/peaks" not in json.dumps(resources)
    assert "build_electron_runtime.py --clean --smoke" in package["scripts"]["build:runtime"]
    assert package["build"]["directories"]["output"] == "release/electron"
    assert package["build"]["files"][:2] == ["dist/index.html", "dist/assets/**"]
    assert "dist/**" not in package["build"]["files"]
    assert package["build"]["nsis"]["artifactName"] == "Peaks-Setup-${version}-${arch}.${ext}"
    eslint_config = (ROOT / "eslint.config.mjs").read_text(encoding="utf-8")
    assert "'build/**'" in eslint_config
    assert "'release/**'" in eslint_config


def test_electron_browser_staging_is_pinned_and_removes_build_links(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _electron_runtime_module()
    descriptor = module._patchright_browser_descriptor()
    browser_root = tmp_path / "patchright-browsers"
    monkeypatch.setattr(module, "BROWSER_ROOT", browser_root)
    commands: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        command: list[str],
        *,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> None:
        del timeout
        assert env is not None
        commands.append((command, env))
        chromium = browser_root / f"chromium-{descriptor['revision']}"
        (chromium / "chrome-win64").mkdir(parents=True)
        (chromium / "INSTALLATION_COMPLETE").touch()
        (chromium / "chrome-win64" / "chrome.exe").touch()
        (chromium / "chrome-win64" / "ABOUT").touch()
        ffmpeg = browser_root / f"ffmpeg-{descriptor['ffmpegRevision']}"
        ffmpeg.mkdir()
        (ffmpeg / "COPYING.LGPLv2.1").touch()
        winldd = browser_root / "winldd-1007"
        winldd.mkdir()
        links = browser_root / ".links"
        links.mkdir()
        (links / "build-owner").write_text("C:/private/build/path", encoding="utf-8")

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module.sys, "platform", "win32")

    staged = module._stage_browser()

    assert commands[0][0][-2:] == ["--no-shell", "chromium"]
    assert commands[0][1]["PLAYWRIGHT_BROWSERS_PATH"] == str(browser_root)
    assert staged["revision"] == descriptor["revision"]
    assert not (browser_root / ".links").exists()
    assert not (browser_root / "winldd-1007").exists()


def test_electron_runtime_manifest_records_exact_staged_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _electron_runtime_module()
    runtime_root = tmp_path / "electron-runtime"
    executable = runtime_root / "backend" / "PeaksBridge" / "PeaksBridge.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    monkeypatch.setattr(module, "RUNTIME_ROOT", runtime_root)
    monkeypatch.setattr(module, "MANIFEST", runtime_root / "runtime-manifest.json")
    monkeypatch.setattr(
        module,
        "_stage_browser",
        lambda: {
            "revision": "1234",
            "browserVersion": "151.0.0.0",
            "patchrightVersion": "1.62.1",
        },
    )
    monkeypatch.setattr(module, "_build_backend", lambda: executable)

    result = module.build(clean=False, smoke=False)
    manifest = json.loads(module.MANIFEST.read_text(encoding="utf-8"))

    assert result == executable
    assert manifest["backend"] == "backend/PeaksBridge.exe"
    assert manifest["browser"]["revision"] == "1234"

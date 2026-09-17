# Peaks packaging

The Electron package contains two application runtimes: Electron's renderer
and main process, plus a dedicated PyInstaller **onedir** backend. Patchright's
pinned headed Chromium is staged as a separate Electron resource. Keeping the
Python service and browser files explicit makes the clean-machine boundary
auditable and gives Windows endpoint protection stable files to inspect.

## Local build

Use Node.js 22.12 or later, a native Python 3.13 environment, and `uv`:

```powershell
uv sync --dev --locked
npm ci
npm run build
```

The root postinstall runs Electron's official `install-electron` command so
the pinned runtime is present before the configured `electronDist` is packaged.
Electron 43.7.1 is a currently supported, security-patched release. Upgrading to
44 additionally requires migrating Peaks' image and sensitive-text clipboard
flows to Electron's new asynchronous clipboard contract, including shutdown
cleanup; do not change the runtime pin without validating those flows.

`npm run build:runtime` performs the native portion directly: it installs only
the pinned headed Chromium into `build/electron-runtime`, freezes
`packaging/electron_bridge_entrypoint.py` with `PeaksBridge.spec`, removes the
build-owner link that contains an absolute build-machine path, and smoke-tests
both the bridge protocol and browser launch from the frozen executable.

Electron Builder copies only the frozen `PeaksBridge` directory, staged browser
directory, and generated runtime manifest. Packaged Electron resolves those
exact resource paths, ignores `PEAKS_PYTHON`, `PYTHONHOME`, and `PYTHONPATH`,
and never falls back to a machine-wide interpreter. Riot Client discovery,
current-match detection, and automatic login remain Windows-only integrations.
Electron output lives under `release/electron`, separate from Vite's `dist`,
and the package allowlist includes only `dist/index.html` and `dist/assets/**`
so a repeated build cannot recursively ingest an older unpacked application.

## Patchright packaging boundary

`PeaksBridge.spec` collects the pinned Patchright Python package, its native
Node driver and JavaScript support files, plus the zxing-cpp extension used to
decode Electron's bounded Riot-window bitmap without shipping Qt in the bridge.
`build_electron_runtime.py` reads
Patchright's own browser manifest, installs that exact Chromium revision with
`--no-shell`, validates the completed Windows executable, and records the
revision and versions in `runtime-manifest.json`. Electron's embedded Chromium
is not used as a substitute.

Browser binaries remain ignored build artifacts and must not be committed.
The staging script requires and retains Chrome for Testing's upstream `ABOUT`
notice and FFmpeg's `COPYING.LGPLv2.1`; it removes Winldd because that tool is
used only for build-time dependency validation. Release owners must still
review redistribution terms, corresponding-source obligations, and the update
policy.

## Electron Windows installer

After native Windows tests, build the configured NSIS installer with:

```powershell
npm run package:win -- --publish never
```

This command repeats the clean runtime staging and smoke checks before Electron
Builder creates the installer. Test the resulting installer under a non-admin
Windows account with no Python installation and no Patchright browser cache.

Before attaching a build to a GitHub release, run:

```powershell
uv run python scripts/verify_update_artifacts.py release/electron
```

It checks the package version, installer size, SHA-512 hashes and blockmap, then
writes `installed-files-sha256.json` from the three installed application files
and creates `SHA256SUMS.txt`. Keep only the installer for the current version in
that output directory. Upload the `.exe`, its `.exe.blockmap`, `latest.yml`,
`installed-files-sha256.json`, and `SHA256SUMS.txt` together without renaming them.
Peaks reads public releases from
`wasd-c/peaks`; the application contains no GitHub credential.

The CI package steps use `--publish never` and a read-only repository token.
Publishing a release is a separate maintainer action: create `v<version>` at the
exact source commit, then manually dispatch **Peaks CI** with **publish** enabled.
Only that explicitly requested publication job receives write permission. It
waits for both platform checks, retries each upload up to three times, and keeps
the release as a draft until all five assets have matching sizes and SHA-256
hashes. It refuses to replace an already published release or a mismatched tag.
Ordinary pushes, tags, pull requests, and manual runs with publish disabled never
publish. Signing is optional until
a certificate is configured through Electron Builder's `WIN_CSC_LINK` and
`WIN_CSC_KEY_PASSWORD` secrets (Windows), or `CSC_LINK` and `CSC_KEY_PASSWORD`
(macOS). Never commit certificate files or passwords. Unsigned builds remain
unsigned; passing integrity checks does not imply a publisher signature.

## Legacy Qt package

`Peaks.spec`, `scripts/build.py`, and `Peaks.iss` retain the earlier Qt onedir
and Inno Setup pipeline for regression coverage. They are not the backend or
installer used by the Electron package.

### Legacy Windows installer

The legacy command uses Inno Setup 6 (`ISCC.exe`) to turn the onedir
output into `dist/installer/Peaks-Setup-<version>.exe`:

```powershell
uv run python scripts/build.py --clean --smoke --installer
```

The installer requires no elevation and installs to the current user’s
`%LOCALAPPDATA%\Programs\Peaks`, with a Start Menu shortcut enabled by
default. Its stable AppId makes upgrades replace the existing application
files without wildcard deletion. Peaks’ encrypted profile at
`%LOCALAPPDATA%\Peaks\Peaks` is intentionally outside it and is preserved
across upgrades and uninstalls. Inno Setup is
resolved from PATH, `ISCC_EXE`, `INNO_SETUP_COMPILER`, or the standard Program
Files locations; the build never downloads an installer tool.

### Legacy signing

No signing certificate, token, or secret is required by the build. To sign a
local artifact, provide an executable signing hook explicitly:

```powershell
uv run python scripts/build.py --clean --sign-hook packaging/sign.ps1
```

The hook receives one argument: the `dist/Peaks` directory on Windows or the
`dist/Peaks.app` bundle on macOS. When `--installer` is used, it is invoked a
second time with the generated installer executable. A CI job can set
`PEAKS_SIGN_HOOK` instead. The hook is not run by default; configure
certificate access in the protected runner or signing service and keep
credentials out of the repository and build logs. Sign all nested Windows
executables/DLLs as appropriate, then sign the macOS bundle recursively.

## Release checks

`.github/workflows/ci.yml` installs locked JavaScript and Python dependencies,
runs Ruff, mypy, pytest, ESLint, Vitest and TypeScript, then builds the current
Electron application. Both platforms smoke-test the frozen Python bridge,
pinned browser, and packaged Electron renderer. Windows produces the NSIS
installer, blockmap, verified updater metadata, and SHA-256 checksums. macOS
produces a DMG, ZIP, updater metadata, and checksums. These are uploaded as CI
artifacts, never automatically published as a GitHub release.

Riot Client integration still needs a real Windows installation for manual
release testing. Electron release inspection should confirm that the runtime
manifest, frozen bridge, Patchright driver, and exactly one pinned headed
Chromium revision are present, while `.links` and build-machine paths are not.

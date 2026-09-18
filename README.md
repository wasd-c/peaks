# Peaks

Peaks is a Windows-first, cross-platform desktop companion for Riot accounts.
It combines a local encrypted account vault, reusable-session/TOTP helpers, and rank,
match-history, watchlist, and current-game views for League of Legends,
VALORANT, and Teamfight Tactics.

> Peaks is an independent project and is not endorsed by Riot Games. Use it
> only with accounts you own. Never use it to reveal identities hidden by
> streamer mode.

## What works without an API key

Peaks does not require a Riot API key for its local features:

- the first-launch four-digit unlock, configurable inactivity auto-lock or
  locking only when Peaks closes, and explicit manual lock controls;
  changing foreground focus never locks Peaks;
- the encrypted local vault, owned-account rows, search
  history, and player watchlist;
- exact Riot ID search through the signed-in local Riot Client, with no game
  or region selection; the signed-in League client also supplies League solo
  and standard TFT ranks, and updates the matching owned account;
- TOTP generation/copying and identity-bound reusable Riot sessions; and
- Windows local Riot Client discovery and current-game detection for League,
  TFT, and VALORANT when the supported client is running.

On macOS, account/rank/history UI remains available, but Riot Client discovery,
current-game detection, and automatic login are explicitly marked Windows-only.

## Privacy and security settings

Peaks supports **English, French and Korean**. On first use it follows the
device's preferred languages, with English as the fallback. You can change the
language from onboarding, the lock screen or **Settings → Appearance**. A manual
choice is saved locally and takes precedence over device preferences.

After an update, Peaks shows the bundled changelog once you unlock the app:
summary, new features, bug fixes, changes, then removals when applicable. Dismissed
notes stay dismissed for that version; **What's new in Peaks** in Settings opens
them again. New installations go through onboarding without an update notice.

In **Settings**, choose **Only when Peaks closes** under **Automatic lock** to
disable inactivity locking. Every new application session still starts locked,
and **Lock Peaks** remains available at any time.

**Change security code** verifies the current four-digit code, then encrypts the
vault with the new code. It preserves the saved accounts, Riot sessions, and
authenticator secrets. The new code must be entered twice.

**Streamer Mode** replaces player names and Riot IDs with numbered aliases such
as **Player 1** and **Player 2** throughout Peaks, including match reports and
exported match images. Aliases stay consistent while Peaks is unlocked; the
preference survives a restart. This is a display preference: the original
identities remain available internally for Riot actions and account matching.

## Optional Riot Developer API key

An optional key can be entered in Settings for the official League/TFT provider,
including its remote match-history requests. Player search uses the signed-in
local clients first and does not ask for this key. Riot Client alone resolves
an exact identity; League/TFT ranks require the signed-in League client. Missing
rank data is shown as unavailable, and Double Up or Hyper Roll ranks never
replace standard TFT. The key is stored in Peaks' encrypted local vault and
is never embedded in the application binary or source.

The key is not required for the local features above. Riot development keys
are short-lived and expire after 24 hours; they are intended for development,
not for a distributed desktop product. See Riot's [Developer Portal
documentation](https://developer.riotgames.com/docs/portal) before using one.
Do not commit a key, put one in CI logs, or ship one inside a Windows build.

Riot ID lookup establishes an identity without inventing a game profile or
rank. It does not supply arbitrary VALORANT statistics. Authenticated local
VALORANT flows supply the signed-in account and supported match-roster data;
a developer key does not unlock public VALORANT statistics.

Match reports are read-only; active match cards can be rearranged within their
team. Share images use bundled official map/agent art, the match result and
player statistics. Discord activity is controlled by the single
**Partage de l’activité Discord** switch.

Discord activity supports VALORANT, League of Legends, and TFT, including
Double Up. League and TFT follow lobby, matchmaking, ready check, selection,
and live play. League uses champion artwork and real current KDA when available;
TFT uses official arena artwork and its queue. Party counts come from the client.
Live TFT health, current standing and board unit count are shown for visible
players when the current source supplies them. Level and augment count appear
only when available. Cards show when the source last updated, and Double Up
uses verified duo pairings. The standalone
TFT client refreshes `TFTEoGStats.json` during play despite its filename. Peaks
uses its periodic HP updates only while playing, with matching game, queue, and
owned-player identity, and a recent file timestamp. Older or unrelated reports
cannot supply current HP. No additional API key is needed.

**Share app diagnostics** in Settings is optional and starts off. When enabled,
Peaks sends a small, sampled set of app version, platform, operation outcomes and
timing events to the project's diagnostics service. It sends no account or match
data, raw error messages, credentials, or persistent device identifier. Collected
fields, consent and delivery limits are documented in
[Diagnostics and privacy](docs/telemetry.md).

For an explicitly requested diagnostic recording, `scripts/record_tft_events.py`
can follow the standalone TFT client's logs, local session changes, and periodic
TFT stats snapshots. It runs separately from Peaks and records sanitized signals rather
than raw logs, identities, or credentials. A log category is diagnostic evidence,
not proof that a corresponding gameplay action occurred.

## Sign-in and privacy boundaries

**Add account** no longer asks for a Riot ID. On Windows, Peaks first checks
for the exact `VALORANT-Win64-Shipping.exe` process. When VALORANT is active,
it validates that the Riot lockfile belongs to the live Riot Client process,
uses the local loopback API to obtain the signed-in account's entitlements and
identity, and binds the account by its authoritative PUUID. A running game with
an absent, stale, or unverifiable lockfile fails closed instead of trusting a
different local process. Peaks also attempts a separately identity-bound import
of Riot Client's reusable SSO cookies. If Riot's private settings file does not
contain them, the account is still recognized but is shown as disconnected;
lockfile passwords and entitlements tokens are never saved as substitutes.

When VALORANT is not active, Peaks opens Riot's account page in a separate,
headed Patchright Chromium window. The user completes Riot's normal sign-in
and any challenge Riot presents in that window. Peaks captures only the
allowlisted Riot SSO cookies and requests an authorization code protected by
PKCE, including the `offline_access` scope. The resulting short-lived access
token verifies the account identity and stays in memory. When Riot issues a
refresh token, Peaks stores it with the allowlisted cookies in the encrypted
vault, only after that identity has been verified.
This browser fallback does **not** enroll, enable, disable, replace, or otherwise
change MFA, and it does not extract a TOTP secret. MFA enrollment is a separate
action described below and is never part of Add account or Save reusable Riot
session.

**Known issue (0.4.0): enabling MFA directly from Peaks is not yet functional.**
Configure MFA at [your Riot account](https://account.riotgames.com/) for now.

The **Enable MFA** integration, in the account's sign-in **More** menu, is still
in progress. It uses the saved Riot session. Peaks exchanges that
session through Riot's fixed account OAuth flow without opening a browser. It
checks the account's PUUID and canonical Riot ID against both the selected
account and a separately minted SSO identity. This preparation is read-only.
Expired sessions or additional Riot verification stop with an in-app message;
Peaks does not open a browser automatically. The operation requires email MFA
to be enabled and refuses to continue when Riot Mobile authentication is
already enabled or Peaks already has a seed, so it cannot silently rotate an
existing factor.

The **Enable MFA** click authorizes the security change for that account.
After the identity and factor checks, Peaks calls Riot's fixed Riot Mobile
enable endpoint. A valid returned seed is
normalized and written immediately to that account's typed entry in the
encrypted vault before Peaks submits a generated code to Riot's verification
endpoint. Account-site cookies, CSRF values, and the short-lived access token
remain memory-only. If verification fails after Riot has returned the seed,
Peaks keeps the encrypted seed and reports that the factor may already be
enabled; it never rolls back the only recovery secret or falsely reports full
success. Peaks does not register a push device or store browser credentials in
plaintext. These private endpoints may change without notice.

Connect is an owned-account-only, experimental helper for the Windows Riot
Client. Clicking **Connect Riot Client** first asks Electron's trusted main
process for an in-memory capture of visible windows whose title exactly matches
Riot Client, decodes a Riot QR, and treats that selected-identity click as the
approval action. Peaks renews the access token using that identity's encrypted
refresh token, or its saved cookies when no refresh token is available, and
verifies Riot userinfo against the selected account. Riot's QR
is an unclaimed client challenge rather than an account-bearing code, so Peaks
binds that exact one-shot challenge to the already verified PUUID and token
instead of treating challenge metadata as an account identity. A changed
session, stale challenge, malformed code, or non-Riot QR is rejected; captures
and decoded pixels are not written to disk.

The **Save reusable Riot session** action first renews the selected account's
saved authorization. Otherwise it tries Riot Client's exact private
session-settings file, rejecting a different local account before using its
cookies. An expired session requires the same isolated Riot browser sign-in
fallback. All paths require the authoritative identity to match the selected
account before storing cookies and any refresh token in the encrypted vault.
The short-lived access token is never persisted. The implementation
uses Riot's private, undocumented session endpoints and may stop working if Riot
changes them; it should not be treated as a supported public authentication API.
TOTP copying remains a separate clipboard-only action and is not used to bypass
session checks.

Refresh-token renewal uses Riot's token endpoint without browser cookies, so
it can run on demand after Peaks or the computer has been closed. It does not
require the application to stay open. While unlocked, Peaks also checks one
saved account per activity poll, with six hours between successful checks and
a five-minute retry delay for temporary failures. Existing cookie-only sessions
are upgraded when Riot still accepts them. A rejected session is marked as
requiring sign-in, without deleting its recovery material. Riot can revoke or
expire its authorization; no fixed six-month or unlimited lifetime is promised.

The **Connected** label means that renewal credentials or reusable SSO cookies
are saved and have not been marked as rejected; it is not set merely because
a running game returned data. VALORANT rank and match-history
refresh currently requires the authenticated local game client to be active.
Saved SSO cookies alone do not provide the entitlements token, shard URLs, and
client version required by VALORANT's private PD/GLZ services. Previously loaded
rank and match rows remain available from the local database while the game is
closed. While the authenticated game client is active, Peaks retries transient
entitlement/history reads and enriches each bounded history row from Riot's
match-detail endpoint with the human map name, own-team result, score, and
duration. Detail failures retain the safe summary instead of discarding the
entire page.

While the vault is unlocked, the desktop polls local Riot activity every 15
seconds. The sidebar and Current match screen therefore update from the real
`CurrentGameService` instead of demo-only state. Activity failures retain the
last usable renderer state and write only the failed stage and exception type to
the rotating diagnostics log.

Current match follows the connected client through party lobby, matchmaking,
selection, and play without a developer API key. VALORANT uses its authenticated
own-party roster; League and TFT use the verified League client, including ready
checks and League champion selection. Party size, leader, readiness, and roles
are displayed when supplied. Standard TFT renders its eight-player roster;
Double Up renders four duo groups with a blue self card and green partner.
Pairings come from explicit client assignments or a recent, identity-matched
lobby roster carried into the same match. Missing pairings stay unassigned.
Double Up cards use its separate ranked ladder. Visible League/TFT roster
members are enriched with Riot IDs, levels, and queue-specific ranks in bounded
cached reads. Available match reports preserve explicit Double Up pairs too.
Anonymous selection identities stay hidden. League live KDA/CS/vision are shown
when available; TFT gameflow alone supplies no board statistics. Temporary
telemetry failures retain the last session, while confirmed exits clear it.

Riot Client session import is Windows-only; the isolated browser fallback can
still authenticate an owned account when the private Client settings are not
usable. A PUUID and authoritative identity match are required before an owned
account can be connected.

TOTP values are copied to the clipboard only on request and are cleared after the configured short timeout when the
clipboard still contains the same value. Riot IDs, TOTP seeds, API keys,
tokens, and lockfile passwords are never exposed through the renderer command
boundary.

The four-digit passcode is a local convenience barrier, not a replacement for
an OS account, full-disk encryption, or malware protection. Peaks uses a
machine-local keyring pepper plus a per-vault salt and AES-GCM encryption for
secrets, with persistent retry backoff for failed unlocks. Locking wipes the
active vault key and decrypted secret entries. Non-secret account metadata,
preferences, search history, watchlist players, and match summaries are stored
separately in SQLite. The data directory is selected with `platformdirs`:
`%LOCALAPPDATA%\\Peaks\\Peaks` on Windows and the platform's application-data
directory on macOS.

Redacted backend diagnostics rotate at `%LOCALAPPDATA%\Peaks\Peaks\peaks.log`
on Windows. They record command and authentication stage names, status codes,
booleans, counts, and exception types only—not Riot IDs, PUUIDs, file paths,
cookies, tokens, lockfile contents, or browser redirect fragments. Set
`PEAKS_LOG_LEVEL=DEBUG` before launching Peaks for additional adapter detail.

Streamer/incognito identities are masked at the local-client boundary. Hidden
or anonymous League/TFT players receive neutral placeholders. For VALORANT,
Peaks submits only live-roster subjects whose Riot `Incognito` flag is false to
the authenticated Riot name service; incognito subjects are never included in
that request and retain neutral labels. Live ranks are fetched once per roster
and rendered as bundled division-specific emblems. Maps, modes, scores, and
other non-identity match data can still be shown. When no supported game is
detected, the sidebar says **No game detected** and the Current match page is
disabled.

## Development

The desktop backbone uses Electron, Chromium, React, Vite, and TypeScript. A
strict context-isolated preload exposes a narrow command channel to a Python
service, which continues to own persistence, Riot integrations, encrypted
secrets, TOTP, and authentication. Secret material is never added
to the React state tree.

Use a Python environment managed by `uv` alongside the Node workspace:

```bash
uv sync --dev
uv run patchright install chromium
npm install
npm run dev
```

The Patchright command is a one-time download for the headed Riot sign-in
fallback. Its Chromium installation is separate from Electron's embedded
Chromium. Re-run it after a Patchright upgrade when the required browser
revision changes.

`npm run dev` compiles the Electron main process before launching it. During
development, Peaks also uses the Python interpreter in `.venv` automatically
(`.venv\Scripts\python.exe` on Windows). Set `PEAKS_PYTHON` only when you need
to override that interpreter.

For a complete, credential-free UI preview:

```bash
npm run dev:demo
```

The demo passcode is `2580`. Demo records are held in memory and are never
written to the production profile.

UI translations are bundled in `src/renderer/i18n/locales/{en,fr,ko}.json`.
Keep the same keys and interpolation fields in all three catalogs, subscribe
with `useLocale()` in translated components, and translate display labels rather
than Riot identities, queue IDs or values used for game/asset lookups. Language
selection is available before unlocking and does not change vault settings.

Before preparing an authorized release, update `src/renderer/releaseNotes.ts`
and its translations alongside the version. Notes are bundled with that build,
work offline, and display in summary/added/fixed/changed/removed/known-issues order. In a
browser-only development preview, `?firstRun=1` shows onboarding and
`?changelogPreview=1` shows the update modal after unlocking. Development and
demo runs never acknowledge the installed app's pending changelog.

Run the verification suite with:

```bash
uv run ruff check .
uv run mypy src
uv run pytest
npm test
npm run build:web
```

## Native packaging and Windows release

Build on the target operating system. Do not cross-compile a Windows release
from an Apple Silicon Mac. Peaks freezes Electron's Python bridge as a dedicated
PyInstaller onedir service and stages the exact Chromium revision required by
the pinned Patchright package before Electron Builder runs.

On Windows:

```powershell
npm install
npm run build
```

`npm run build` produces `release/electron/win-unpacked`, an unpacked,
clean-machine test package. It downloads
Chromium during the build, freezes the bridge, smoke-tests both the JSON
protocol and the staged browser through the frozen executable, and then runs
Electron Builder. The installed app never falls back to a system Python or a
user browser cache. Its encrypted profile lives outside the installation
directory and is preserved across upgrades and uninstall.

To produce the configured Windows NSIS installer after the same runtime build
and smoke checks, run `npm run package:win`. Signing remains a release-time
responsibility; do not distribute unsigned artifacts as production releases.
Patchright's staged browser remains separate from Electron's embedded Chromium.

### In-app Windows updates

Starting with **0.3.0**, the installed Windows app checks the public
[wasd-c/peaks releases](https://github.com/wasd-c/peaks/releases) after startup
and every six hours. A new stable release adds an **Update** action to the
sidebar. One click downloads the update, shows progress, verifies the installer,
installs it silently, and restarts Peaks. Failed checks or downloads can be
retried from the same control. Updates do not require a GitHub token and never
open a browser download page. Accounts and the encrypted vault remain outside
the installation directory.

Development/browser previews do not check or install releases. Updates never
install automatically just because an available release was discovered or the
app was closed. An older installation without the updater needs to install
0.3.0 once before it can receive subsequent releases in-app.

For each Windows release:

1. Set the same stable version in `package.json` and `pyproject.toml`, refresh
   their lockfiles, and run the verification suite.
2. Run `npm run package:win` on Windows. The build generates the installer,
   its `.blockmap`, and `release/electron/latest.yml` for the GitHub provider.
3. Publish a non-draft, non-prerelease GitHub release tagged `v<version>` with
   the installer, blockmap, `latest.yml`, `SHA256SUMS.txt`, and
   `installed-files-sha256.json`. The release workflow creates both checksum
   manifests from that build. Upload the installer using the **exact asset name in
   `latest.yml` under `files[].url`**, and upload its blockmap using that same
   name plus `.blockmap`. For 0.3.0 this is `Peaks-Setup-0.3.0.exe` and
   `Peaks-Setup-0.3.0.exe.blockmap`; the local installer may instead be named
   `Peaks Setup 0.3.0.exe`. Upload `latest.yml` last, or publish the draft only
   after every artifact is attached.
4. Verify the public feed from an earlier installed version and exercise the
   complete download/install/restart flow. A synthetic preview or a passing
   unit test does not verify installation. Confirm the new executable version,
   installed artifact hashes, preserved vault, and restarted process. For a CI
   build, compare the installed files to that release's
   `installed-files-sha256.json`, rather than an independently built local copy.

The updater uses `electron-updater` with the Windows NSIS target. Release
metadata and the downloaded installer are verified before installation;
prereleases, downgrades, arbitrary download URLs, and renderer-supplied paths
are rejected. See the [electron-builder auto-update documentation](https://www.electron.build/docs/features/auto-update/)
for provider and signing details. Publishing credentials belong only in the
release environment, never in the app or checked-in configuration.

Packaging copies the native Electron distribution installed by `npm install`
from `node_modules/electron/dist`, avoiding an additional archive extraction and
temporary-directory rename on Windows. The Windows icon uses the checked-in
`src/renderer/assets/peaks-mark.ico`, so packaging does not need to convert the
PNG with the icon tool. Keep that ICO in sync when changing the Peaks mark.

On macOS arm64, the same command produces a native DMG. It cannot validate
Windows Riot Client integration.
See [packaging/README.md](packaging/README.md) for signing hooks, artifact
hashes, installer discovery, and release checks. Before distribution, sign the
Windows executable/DLLs and installer with a protected certificate, and sign
the macOS bundle where applicable. No signing secret belongs in this repository
or in build logs.

See [SECURITY.md](SECURITY.md) for the security model and release boundary, and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for source and artwork
attribution.

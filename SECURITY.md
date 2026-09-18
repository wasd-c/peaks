# Peaks security model

This document describes the security boundary of the current desktop build. It
is deliberately conservative: Peaks is a local companion, not a credential
manager with hardware-backed authentication and not a Riot-operated service.

## Local profile and unlock

Peaks stores non-secret metadata (owned-account metadata, ranks, match
summaries, preferences, search history, and watchlist players) in SQLite. Login
material is kept separately in an encrypted vault. The vault uses a random
machine-local keyring pepper, a per-vault salt, scrypt key derivation, and
AES-GCM authenticated encryption. Where the platform keyring is available,
the configured native backend is used (for example, a Windows credential
store/DPAPI-backed backend or macOS Keychain); an explicitly permissioned file
pepper is available only as an opt-in development fallback on non-Windows
hosts. Windows fails closed and never falls back to a plaintext pepper file.

Unlocking reads existing protected keys only. If a legacy profile has both a
keyring value and a different DPAPI fallback, AES-GCM authentication identifies
the value that belongs to that vault. A credential-store outage never creates
a replacement key during unlock. PIN changes reuse the authenticated value;
the active mutable key and pepper buffers are cleared on lock. Existing vault
files retain their format and passcode.

The four-digit PIN gates the UI and derives the vault key together with the
machine-local pepper. It is intentionally a convenience barrier, not a strong
second factor. It does not protect against malware, an administrator, a
compromised OS account, or an attacker who already controls the unlocked
desktop. Failed attempts use persistent retry backoff. Locking clears the
active derived key and decrypted vault entries from the vault object.

Use an OS login, full-disk encryption, and normal endpoint protection for the
device. Do not treat the PIN as a substitute for any of them.

A forgotten PIN cannot be recovered or bypassed. The locked screen offers a
two-step local-profile reset that requires an explicit final confirmation,
deletes only Peaks' allowlisted database, encrypted-vault, machine-pepper, and
atomic-write files, then returns the renderer to onboarding. A durable marker
makes an interrupted reset finish on the next launch; the reset never recurses
through the application-data directory or deletes unrelated files.

## Credential handling

The vault may contain TOTP seeds, a user-entered Riot Developer API key, and
Riot session material used by the owned-account connect flow. These values are
not exposed through QML properties, logs, user-facing provider errors, or
SQLite. TOTP is generated only after unlock and copied only when requested;
clipboard cleanup runs on its timer and on application exit, conditional on
the value remaining unchanged.

Do not put Riot keys, TOTP seeds, QR payloads, lockfile passwords, access
tokens, signing credentials, or test account credentials in source control,
CI variables that are printed, screenshots, bug reports, or packaged
artifacts. A development API key supplied to a local profile is not a release
credential.

## Riot API and RSO boundary

The Developer API key is optional. It is used for official League/TFT account
lookup, rank, and match-history requests and for refreshing owned-account
snapshots. Riot development keys expire after 24 hours and are for development
use; consult the [Riot Developer Portal](https://developer.riotgames.com/docs/portal)
for the current terms and application requirements.

Peaks never bundles a Riot key. A public release must use an approved
architecture, such as a compliant backend with server-side credentials and/or
Riot-approved VALORANT RSO, rather than asking every distributed binary to
share one production key. The current application does not provide that
backend or RSO registration. Public VALORANT rank/search and remote player
current-match data therefore remain unavailable until the required approval is
configured.

## Account onboarding, session connect, and local-game data

Owned-account onboarding is identity-first and never accepts a typed Riot ID as
proof of ownership. On Windows, if the exact VALORANT game executable is
active, Peaks validates that the Riot lockfile PID belongs to the live Riot
Client executable before using its loopback API. It obtains the current
entitlements token and authoritative Riot identity only after that process
binding succeeds. A running game with a missing, stale, malformed, or
unverifiable lockfile fails closed rather than falling through to an untrusted
local listener.

If VALORANT is not active, onboarding may open a separate headed Patchright
Chromium process for the user to complete Riot's normal sign-in. Peaks reads
the completed browser context only to retain an allowlisted SSO cookie set,
then uses the existing importer to mint a short-lived token and fetch the
authoritative identity. The token is not persisted; retained cookies are
encrypted in the vault. This flow does not enroll or change Riot MFA, fetch a
TOTP enrollment secret, submit credentials on the user's behalf, or bypass a
challenge Riot presents. The browser integration is private and undocumented
and can stop working when Riot changes its pages or session behavior.

Riot Mobile TOTP enrollment is deliberately isolated from normal onboarding
and connection. The user selects **Enable MFA** for an owned account to
authorize enrollment. Peaks exchanges its saved SSO session through validated
HTTPS account OAuth redirects with matching state, without opening a browser.
It requires exact PUUID and Riot-ID binding through both the account site and
SSO identity before changing any factor. A missing or expired session or an
additional Riot verification challenge stops the operation without falling
back to a browser. Preparation reads only fixed identity and factor endpoints. Email MFA
must already be enabled, and Peaks fails closed if Riot Mobile is already
enabled or a local seed already exists; it does not rotate either secret.

After those checks, the fixed enable endpoint may change external Riot account
state. Peaks validates and normalizes the returned seed, then commits it to the
typed encrypted-vault entry before attempting verification. This ordering is
intentional: if verification fails after enable, the Riot factor may already
exist, so the encrypted seed is retained and the UI reports partial success
with recovery guidance. A persistence failure after Riot returns a seed is
reported as an external-state warning and verification is not attempted. No
account cookie, CSRF value, access token, generated TOTP, or seed value is
logged or returned to the renderer. The one-click action consumes its internal
one-time preparation immediately. Legacy two-step preparations expire after
five minutes and are discarded on cancel or vault lock.

The explicit session-import action is Windows-only and restricted to an
account selected by the user. It reads only
`%LOCALAPPDATA%\Riot Games\Riot Client\Data\RiotGamesPrivateSettings.yaml`,
keeps only the allowlisted Riot session cookies in the encrypted vault, and
never persists the short-lived access token minted for identity verification.
The selected-identity Connect action may capture up to three exact-title Riot
Client windows through Electron's trusted main process. Renderer input cannot
choose or replace those pixels. The bounded BGRA captures are decoded in memory
as QR symbols only, parsed as allowlisted Riot hosts and fields, and wiped from
the backend's mutable buffers. Approval requires a freshly minted selected-
account token whose Riot userinfo matches the selected PUUID, a fresh one-shot
session-info challenge bound to that PUUID and a non-reversible fingerprint of
the same token, and the same explicit Connect click. Riot QR challenges are
unclaimed before approval; response fields such as `subject` are never treated
as the challenge's account owner. QR payloads, pixels, tokens, fingerprints, and
PUUIDs are not logged. Session import and QR approval rely on private,
undocumented Riot behavior; Riot can change or disable them at any time, so
neither must be treated as a production authentication service.

Local League/TFT/VALORANT detection is isolated behind a Windows adapter and
requires the supported Riot client/game to be running. macOS intentionally
reports this integration as unavailable. Remote HTTPS certificate validation
remains enabled; only the local Riot loopback certificate exception is scoped
to the literal loopback client.

Streamer/incognito protection is a data boundary, not just a UI preference.
Hidden or anonymous League/TFT names are replaced with neutral numbered
placeholders. VALORANT's match-level `Incognito` marker is authoritative: only
non-incognito live subjects are sent to Riot's authenticated name service, and
incognito subjects are never submitted for display-name resolution. Bounded
live-roster rank reads are cached for the current match and exposed only as
rank labels/emblems. Non-identity data such as map, mode, score, and elapsed
time may still be displayed. When no supported game is active, **Current
match** is disabled and displays **No game detected**.

## Release checklist

Before shipping a build:

- build natively on Windows x64 for the Windows release; do not cross-build it
  from Apple Silicon macOS;
- run Ruff, mypy, unit tests, Qt/offscreen tests, packaged startup smoke tests,
  and Windows manual checks against a real Riot installation;
- verify the onedir bundle contains only intended resources and no secrets;
- verify the pinned Patchright package and driver are present, and test the
  headed-browser path with the exact browser revision provisioned for the
  release;
- test the authenticator preparation/cancel path with a dedicated owned test
  account, and test enable/verify only when intentionally changing that test
  account's MFA state;
- inspect the Electron resources for exactly one staged Patchright Chromium,
  its upstream notices, and no `.links` file or absolute build-machine path;
- test a non-admin install, upgrades, spaces/non-ASCII paths, and the
  per-user profile location;
- sign all Windows executables/DLLs and the installer with a protected
  certificate, and sign the macOS bundle when distributing it; and
- publish SHA-256 hashes only after signing and keep signing material outside
  the repository and build logs.

See [packaging/README.md](packaging/README.md) for the native build, installer,
signing hook, and CI details.

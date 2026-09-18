# Peaks diagnostics and privacy

This public document describes the diagnostics contract and privacy protections.
Production deployment procedures and infrastructure configuration belong in
private infrastructure documentation.

The installed app can send optional technical diagnostics. Sharing starts
**off** and can be enabled in Settings → Privacy & security → Share app diagnostics.

The payload contains only a fixed event name, public app version, platform,
allowlisted command name, success/failure, and rounded duration. No account,
player, match, machine, persistent installation identifier, exception text,
cookies, credentials, or local paths are collected. Events are sampled per
category per minute and held in a bounded memory-only queue. Opting out drops
the queue and aborts delivery. Development and demo builds never transmit.

`command.completed` covers the complete trusted operation, including failures
while preparing a QR image, starting the backend, or copying a result. It records
only `command`, `outcome` (`success`/`failure`), and `duration_ms` (rounded to
100 ms and capped at 300,000 ms), alongside `event`, `version` and `platform`.
Consent is captured before preparation starts; opting in later or changing
consent while an operation is running cannot retroactively include it.

| Operations | Command names |
| --- | --- |
| State, activity and data | `state`, `activity`, `refresh`, `search`, `settings` |
| Accounts and Riot sessions | `add_account`, `remove_account`, `import_session`, `connect_riot_client`, `connect_riot_qr_image` |
| Vault and credentials | `pin`, `lock`, `change_pin`, `reset_application`, `api_key` |
| TOTP | `enable_riot_mfa`, `prepare_totp_setup`, `confirm_totp_setup`, `cancel_totp_setup`, `copy_totp` |
| Following and sharing | `toggle_follow`, `toggle_watchlist`, `copy_match_image`, `discord_presence` |
| Updates and release history | `update_check`, `update_install`, `release_history`, `release_history_ack` |

The old names `player`, `match`, `matches`, `account`, `follow`, and `unfollow`
remain accepted for schema-1 compatibility. Reading/changing the diagnostic
preference itself is not tracked. No PIN, TOTP code, API key, session, image,
search text, account identifier or operation result is attached to these events.

Local Python diagnostics use `diagnostic_policy.py` to allow only reviewed event
names and scalar fields (fixed enums, booleans, bounded counters and HTTP status).
Unknown text, fields and values are withheld before writing to `peaks.log` or
stderr. Exceptions retain an allowlisted type, without message, traceback or
source text. Logger names are normalized, and per-account slot numbers are
withheld. Local HTTP logs omit paths as well as query strings, since either can
contain identities or credentials. Electron drains backend stderr without
duplicating arbitrary library output into its console. Local logs are not uploaded.

This remains bounded operational telemetry, not a complete crash-reporting
system: the original sampling, memory-only queue and delivery limits still apply.

The diagnostics service validates the same fixed schema a second time and
limits batch sizes and request rates. It provides no API for reading stored
diagnostics. Source addresses are used in memory for rate limiting and are not
included in forwarded events. This anonymous telemetry does not authenticate
individual installations and must not be used for billing.

The diagnostics client is implemented in `electron/telemetry.ts` and communicates
with the service over HTTPS. Server deployment files are maintained separately;
they are not required to build, test or run the desktop app and are not bundled
in its installer. The app's public tests cover consent, permitted fields and
operation coverage without loading server code.

# Match reviews and sharing

Peaks uses a black Astryx theme, locally bundled game artwork, a fixed navigation rail, and a searchable account roster. The generated Peaks mark is in `src/renderer/assets/peaks-mark.png`; its generation notes are alongside it.

## Automatic review

Peaks observes a live VALORANT match tied to an owned account. After a confirmed transition out of that match, the backend refreshes that account's history and retries on a bounded schedule. The overlay appears only when the exact match has a final record. Startup history, pregame sessions, stale telemetry, and unrelated accounts cannot trigger it. Dismissed matches are remembered locally. League and TFT history can be shared, but they do not currently provide the verified live match IDs required for automatic reviews.

The review includes result, map, score, duration, KDA, combat score, hit locations, recorded weapon kill shares, and player highlights. Its full-report action opens the same detailed match used by history.

## Statistics

- Head, body, and feet percentages use complete hit-location counts.
- Weapon usage means share of recorded weapon kills, not equip time or accuracy. Ability kills do not count as weapon kills.
- Multikill tags require per-round kill events consistent with the recorded totals.
- Sharpshooter means at least 20 recorded hits and at least 30% headshots.
- Quiet game means fewer than 0.5 combined kills and assists per round over at least eight rounds, with complete participation data. It describes recorded contribution and does not infer intent or inactivity.
- ACS requires a known round count; otherwise a total is labelled Combat score. Missing or conflicting evidence remains unavailable. Hidden identities are excluded from public images and contextual tags.

## Share

Share creates a local 1200 × 675 PNG with map artwork, result, player performance, and a small Peaks credit. The user can copy the image, save it, or use a native file-sharing chooser when supported. X and Reddit buttons open a prefilled composer; the image is pasted or attached by the user. Peaks does not automatically publish posts or upload match records.

## Verification

Run renderer/Electron tests with `node node_modules/vitest/vitest.mjs run`, type checking with `node node_modules/typescript/bin/tsc -b`, and Python tests with `.venv/Scripts/python.exe -m pytest`.

The browser preview's `?postMatch=1` route exercises the real tracker with a synthetic live-to-final transition after unlocking with 2580. Reloading creates a fresh fixture ID. Native Electron bypasses this fixture. Preview tests cover the overlay, history report, lobby tags, poster rendering, copy action, and scrolling at the 1080 × 680 minimum window size. A Windows Electron demo startup was also checked. A real VALORANT match-end check remains outstanding.

# Offline TFT archive

`sets/<number>.json` preserves each set's exact Riot character IDs, localized names,
traits, ability descriptions, mana and base stats, spell variables and Riot
calculation trees. `variants` keeps half-sets and special-mode rosters separate;
identical rosters share an alias. `index.json` is the lightweight lookup used by
boards. Full set data loads only when a champion card is opened.

All portraits and spell icons are bundled in `assets/profiles/tft-library`.
The renderer makes no remote asset or catalog requests.

Rebuild from the recorded historical patches and the latest export:

```powershell
uv run --with pillow python scripts/fetch_tft_catalog.py
```

Import another patch without removing old sets:

```powershell
uv run --with pillow python scripts/fetch_tft_catalog.py --patch latest
```

Each set records its CommunityDragon source URLs and SHA-256 hashes. Raw files
are cached under `build/profile-catalogs/<patch>`; remove only the relevant cache
when deliberately refreshing the mutable `latest` snapshot. Imports are catalog
snapshots, not a replay of every historical balance patch.

Lookups use exact API IDs and, when available, the composition's `setNumber` and
`setVariant`. Never strip a set prefix or substitute a same-named champion from
another set. An unknown unit retains its ID and an unavailable-state card.

Spell arrays use Riot's **indexes 1, 2, 3 (and 4)**. Index 0 is not one star.
The card highlights only the recorded rank. Values describe the base ability,
before items, traits and dynamic combat state. Only supported explicit formulas
are evaluated: missing formulas, dynamic values and unresolved localized terms
display `—`, with an explanation, rather than an invented number. Provider
markup is parsed into a small allowlist of text, icons and values, never HTML.

Data and artwork: [CommunityDragon](https://raw.communitydragon.org/latest/cdragon/tft/),
distributed from Riot game assets.

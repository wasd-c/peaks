# Match-poster fonts

These original, unmodified TrueType files are bundled with Peaks. Exporting a
match poster does not request fonts from a CDN or depend on installed fonts.

| File | Family and weight | Intended use |
| --- | --- | --- |
| `BarlowCondensed-ExtraBold.ttf` | Barlow Condensed 800 | Large condensed result, map and agent headlines |
| `IBMPlexMono-Regular.ttf` | IBM Plex Mono 400 | Stat captions and supporting information |
| `IBMPlexMono-SemiBold.ttf` | IBM Plex Mono 600 | Player identity, match header and earned tags |

## Provenance and licensing

Downloaded on 2026-09-16 from the official
[Google Fonts repository](https://github.com/google/fonts), pinned at revision
`02cac32590ff3531408c3d221673d7aa32a98c11`:

- [Barlow Condensed](https://github.com/google/fonts/tree/02cac32590ff3531408c3d221673d7aa32a98c11/ofl/barlowcondensed), by Jeremy Tribby / The Barlow Project Authors. The accompanying license is `BarlowCondensed-OFL.txt`.
- [IBM Plex Mono](https://github.com/google/fonts/tree/02cac32590ff3531408c3d221673d7aa32a98c11/ofl/ibmplexmono), by Mike Abbink and Bold Monday / IBM Corp. The accompanying license is `IBMPlexMono-OFL.txt`.

Both families are distributed under the SIL Open Font License 1.1. Keep their
license files with redistributed font files. The fonts have not been subsetted,
converted or modified. The loader uses private CSS family aliases only.

SHA-256 checksums:

```text
724c9c25952d5f4a2d87185d9767aa006144c5f0d944dc05bf7d5d603551c260  BarlowCondensed-ExtraBold.ttf
6a3412f058c7d8dfd9170c41e85ade48e5156ecb89356110ca57a0a27734af46  IBMPlexMono-Regular.ttf
d3c38e55c78f5b0f28009fddba4834ec503278936a5986032424c9bd2d23aa46  IBMPlexMono-SemiBold.ttf
```

## Canvas usage

Call `await loadPosterFonts()` from `src/renderer/posterFonts.ts` before measuring
or drawing any poster text. It returns `{display, mono}` font-family stacks.

```ts
const fonts = await loadPosterFonts()
context.font = `800 160px ${fonts.display}`
context.font = `600 32px ${fonts.mono}`
context.font = `400 20px ${fonts.mono}`
```

The source-graph imports also include both licenses so Vite emits them with the
font assets. The loader awaits all three `FontFace.load()` calls and registers the loaded
faces in `document.fonts`. Concurrent calls share one load. If font APIs are not
available, or a font fails to load, system-family stacks keep export usable;
failed loads are retried on a later call.

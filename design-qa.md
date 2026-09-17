# Peaks Astryx rebuild — design QA

**Comparison target**

- Source visual truth: `artifacts/design-qa/astryx-components-reference.png`, captured from `https://astryx.atmeta.com/components` in dark mode.
- Rendered implementation: `artifacts/design-qa/peaks-overview-implementation.png`, captured from `http://localhost:5173/` after local passcode unlock.
- Full-view comparison: `artifacts/design-qa/full-comparison.png`.
- Focused navigation comparison: `artifacts/design-qa/sidenav-focused-comparison.png`.
- Additional implementation evidence: `artifacts/design-qa/peaks-passcode-no-keypad.png` and `artifacts/design-qa/peaks-current-match-local-assets.png`.
- CSS viewport: 1280 × 720 for both pages at device pixel ratio 1.
- Captured pixels: source 1265 × 712; implementation 1280 × 720. The source capture was bicubic-normalized to 1280 × 720 for the full comparison. The focused SideNav comparison uses 260 × 720 content regions from each capture.
- State: Astryx components overview in dark mode versus Peaks authenticated Overview in its dark custom Astryx theme. These are not the same product content, so the comparison judges component language, hierarchy, density, typography, navigation, surfaces, and polish rather than pixel-identical copy or information architecture.

**Findings**

- No actionable P0, P1, or P2 differences remain.
- Fonts and typography: Astryx controls on the source page resolve to Figtree at 14px/500. Peaks intentionally resolves to Segoe UI Variable/Segoe UI for a native Windows desktop voice, with a 22px/600 page heading and tokenized supporting text. Hierarchy, wrapping, line height, and optical weight are coherent at the target viewport. This is an intentional theme divergence, not an unresolved fidelity issue.
- Spacing and layout rhythm: the 260px persistent SideNav, selected-item treatment, section grouping, compact rows, page header, metric grid, and dense account lists match Astryx's desktop density and rhythm. No clipping, overlap, or broken wrapping is visible at the 1280 × 720 verification viewport. The Electron window enforces a 1080 × 680 minimum and the account/team grids collapse below 70rem.
- Colors and visual tokens: Peaks intentionally removes Astryx's chromatic accents in favor of an achromatic black/gray theme. Automated inspection found no chromatic hex value in the custom theme, no raw color literal in renderer CSS, and no chromatic semantic component variant in the renderer. Key dark-theme contrast ratios range from 6.90:1 to 18.69:1.
- Image quality and asset fidelity: official map, agent, and rank imagery is sharp, correctly cropped, grayscale-treated, and rendered from local application paths. The verified current-match state loaded one map and six agent images locally; no remote image URL was present. Icons use one consistent Lucide stroke family rather than custom SVG or CSS drawings.
- Copy and content: headings, labels, privacy language, status copy, and account/game metadata read as a coherent standalone local Riot companion. No prompt text or implementation notes leak into the product UI. The browser-only demo passcode hint is excluded from the Electron bridge path.
- States and interactions: keypad-free four-digit entry, automatic fourth-digit submission, wrong-passcode feedback/reset, unlock, navigation, account tabs, player search, watch/unwatch, Add Account and Riot Client dialogs, current match, settings switches, reduced motion, and manual locking were exercised.
- Accessibility: semantic Astryx controls expose names and roles, the passcode textbox has a visible label, four progress indicators have a count label, focus states are visible, reduced motion is supported, and the reviewed foreground/background pairs pass WCAG AA contrast.

**Open Questions**

- None blocking. The Astryx documentation page includes a top navigation because it is a website; Peaks intentionally uses an app-only persistent SideNav because it is a desktop workspace.

**Implementation Checklist**

- [x] Use actual Astryx layout, navigation, control, feedback, and data-display components throughout the active renderer.
- [x] Apply a compiled custom Astryx theme with achromatic tokens.
- [x] Remove the visual keypad and keep keyboard-only four-digit auto-submit.
- [x] Store all used VALORANT API media locally and resolve it through UUID-based local paths.
- [x] Verify primary flows, passcode feedback, reduced motion, local media sources, and browser diagnostics.
- [x] Build the web renderer and Electron process and package the unpacked Windows app.

**Follow-up Polish**

- P3 optional: locally bundle Figtree if exact Astryx documentation typography becomes more important than the current native Windows character.

**Comparison History**

- Pass 1: full-view and focused SideNav comparisons found no actionable P0/P1/P2 visual mismatch. The blacker palette and absence of the documentation site's top navigation were classified as explicit product requirements.
- Diagnostics refinement: switched the app from runtime theme injection to the generated `peaks.js` plus `peaks.css` artifacts. This was a runtime-quality change, not a visual finding.
- Pass 2: recaptured the latest implementation, rebuilt both comparison images, and rechecked them together. No layout, typography, color, image, icon, or copy regression was visible. No new browser error or warning was logged after the final reload.

final result: passed

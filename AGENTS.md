# AGENTS.md

Project-specific guidance for AI coding agents.

## Interface

The renderer is built on **Ant Design 6** (`antd`), dark theme, with Peaks's own palette.

- Screens import components from `src/renderer/ui` (layout, typography, controls, overlays, data, theme), not from `antd` directly. That module wraps Ant Design so spacing, type and accents stay consistent. Reach for `antd` directly only for something `ui/` doesn't cover yet, and prefer adding it to `ui/`.
- Theme: `ui/theme.tsx` holds the Ant Design token config (`antThemeFor`). `theme/tokens.css` holds the Peaks CSS variables (`--color-*`, `--spacing-*`, `--radius-*`, game and TFT palettes) that Peaks's own surfaces use. Keep both in step when changing a colour.
- Game profiles scope their accent with `<Theme theme="valorant" | "league" | "tft" | "riot">`.
- Spacing props are steps of 4px (`gap={3}` = 12px).
- Custom styling: component props first; otherwise CSS with tokens (`var(--color-*)`, `var(--spacing-*)`, `var(--radius-*)`). No raw hex/px in screens.
- Dense data = rows (`Table`, `List`/`ListItem`), never cards around list items. Status = `StatusDot`/`Token`.
- Omit headings, captions and counts that repeat what the screen already shows. Use recognizable game logos and action icons with accessible names and tooltips. Keep visible text for ambiguous actions, data units and exceptional states.
- In game history, lead with the player's score or placement and the recorded rating change. Use the game's exact division emblem where available, with its localized name exposed to assistive technology. Add a visible verdict when the score alone is ambiguous, such as a surrender or a League K/D/A.

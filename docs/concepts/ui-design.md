# One design for all ediarum.platform apps

Every app mounted in ediarum.platform should look like the platform and like
each other. The source of the design is the **platform's design tokens**, the
`--ep-*` custom properties on its `:root` (ediarum-platform `src/styles.css`).
An app reads them when it mounts and builds its UI library's theme from them.
Nothing is copied, so nothing drifts, and a change to the tokens reaches every
app without rebuilding it.

ediarum.index does this as follows. The same steps apply to any Vuetify app.

## The tokens and what they become

| Platform token | Vuetify theme (`frontend/src/theme.ts`) |
|---|---|
| `--ep-color-accent` (ediarum red, darkened for contrast) | `primary`: buttons, links, the active tab |
| `--ep-color-bg` | `background`, `surface`, `surface-bright`; `on-surface-variant` |
| `--ep-color-surface` | `surface-light`: table headers, hover rows, toolbars of lists |
| `--ep-color-text` | `on-background`, `on-surface`; `surface-variant` (tooltips, snackbars) |
| `--ep-color-muted` | `secondary` |
| `--ep-color-border` | the `border-color` variable (opacity 1) |
| `--ep-color-error` / `-success` / `-focus` | `error` / `success` / `info` |
| none | `warning`: `#8a5a00` light, `#e3b341` dark |
| `--ep-font` | the only font family (`--font-body`, `--font-heading`); nothing bundled |
| `--ep-radius` (6px) | `$border-radius-root: 6px` (a SASS value, so a literal) |

Rules:

- **Read, don't copy.** Read the tokens at mount time with
  `getComputedStyle(document.documentElement)`. Keep the platform's own values
  only as per-token fallbacks, for tests or a token that is missing.
- **Hex only.** Vuetify parses theme colours itself. A token in another
  notation falls back.
- **Dark mode follows the platform.** The platform switches its tokens with
  `prefers-color-scheme`. Listen to that media query, rebuild the theme from
  the re-read tokens, and remove the listener on unmount.
- **One font, no font files.** Inherit the platform's `--ep-font`. Only icon
  fonts (`@mdi/font`) are bundled.
- **The theme is scoped.** Theme CSS lives on the app root
  (`theme.scope`, `theme.stylesheetId`), like all CSS of the app. See the
  platform guide, 3.6.

## Component conventions

These are what the tokens don't say:

- **Flat, bordered.** Cards have a border and no elevation; toolbars and app
  bars are flat. Bars use `color="surface"` with a hairline bottom border,
  like the platform's own top bar. No coloured bars.
- **Inputs:** `outlined`, `density="comfortable"`. Buttons keep their text
  case (`text-none`).
- **Titles:** the body font at weight 600, no Material letter-spacing.
- **Tables:** header on `surface-light`, weight 600; hover rows on
  `surface-light`; hairline rows.
- **Dialogs** are `contained` in the app's area, so the scrim stays inside
  the app.
- **Header:** the app's toolbar is the only header and hosts the platform
  controls `<ediarum-home>` (far left) and `<ediarum-user-menu>` (far right);
  they inherit font and colour from the toolbar.

Another Vuetify app adopts this by taking `frontend/src/theme.ts` and the
Vuetify defaults in `frontend/src/vuetify.ts`. For buttons and text the
platform uses `--ep-color-accent`, not the brighter brand red
(`--ep-color-brand`, `#E5312E`).

# Frontend

ediarum.index's UI as an **ediarum.platform app**: the platform loads
`/apps/index/embed.js` and mounts it in its content area (route `/index/…`).
The app's toolbar is the only header: it shows the platform's app menu and
user menu, and the platform hides its own top bar.
Browse, search and edit a project's entries; platform admins also see the
ingest runs and manage API keys. Login, users and projects are the
platform's.

## Stack

Vue 3 (`<script setup>`, TS) · Vite (rolldown) · Vuetify 4 · vue-router ·
axios · Vitest. Package manager: **npm**.

## The platform contract

`src/platform/contract.ts` is a verbatim copy of ediarum-platform's
`src/contract.ts` (the commit is noted at the top); the rules are its
`docs/integrating-an-app.md`. How this app meets them:

| Rule | Where |
|---|---|
| `embed.js` exports `contractVersion` and a synchronous `mount(el, ctx)` | `src/embed.ts`; `npm run check-embed` after a build |
| everything per mount, unmount removes all of it | `src/embed.ts` (app, router + its listener, Vuetify, theme stylesheet, DOM); `src/context.ts` (API client, search state — no module-level state) |
| no login, users, own user menu or auth guard | the platform has them |
| header shows `<ediarum-home>` far left and `<ediarum-user-menu>` far right (guide 3.10) | the toolbar in `App.vue`; `isCustomElement` for `ediarum-*` in `vite.config.mts` |
| router on `ctx.routerBase`, no redirects for unknown paths | `src/routes.ts`, `views/NotFound.vue` (why: see there) |
| API on `ctx.apiBase`; 401 → `onUnauthorized` once; 419 → fresh CSRF cookie, retry once; requests aborted on unmount | `src/api/client.ts` |
| no CSS in or out | `build/scope-to-root.ts` scopes every rule of the bundle to `.index-root`; Vuetify's theme is scoped there too and its overlays render inside the root (`src/vuetify.ts`) |
| fills `el`, scrolls itself | `styles/main.scss` (layout block) |
| build: `base: '/apps/index/'`, entry `embed.ts`, CSS injected by JS | `vite.config.mts` |
| served as plain files, no SPA fallback | `nginx.conf`, `Dockerfile` |

## Layout

Paths are relative to `frontend/`.

| Path | What |
|---|---|
| `src/embed.ts` | the entry module: `mount(el, ctx)` / unmount |
| `src/context.ts` | per-mount context (`useAppContext`, `useHttp`) |
| `src/routes.ts` | `/` projects · `/:project` entries · `/ingest-runs`, `/keys` (admins) |
| `src/App.vue` | the app's toolbar (project, search, admin menu) + routed view |
| `src/views/` | `ProjectsList`, `EntriesList`, `IngestRunsList`, `KeysList`, `NotFound` |
| `src/components/` | `EntryDialog`, `EntryView` (+ `EntryRelations` / `EntryComments`), `common/` (`DataListView`, `FormDialog`, `SchemaField`, `RepeatableField`, `EntryAutocomplete`, `ConfirmDialog`) |
| `src/composables/` | `useEntries`, `useProjects`, `useEntryTypes`, `useRelations`, `useComments`, `useIngestRuns`, `useKeys` |
| `src/api/` | `client.ts` (per-mount axios) + one module per resource, each function taking the client and the project |
| `src/lib/` | pure helpers: value formatting and URL linking (`format.ts`), the person label (`label.ts`), table types (`table.ts`) |
| `src/theme.ts` · `src/vuetify.ts` · `src/styles/` | the theme from the platform's design tokens (see ../docs/UI-DESIGN.md), Vuetify per mount, SASS settings, cascade-layer order |
| `build/` | the PostCSS scoping plugin (+ its spec) |

## Scripts

```bash
npm run dev          # Vite dev server on :5174 for the platform's dev server (hot reload)
npm run build        # type-check + production build -> dist/embed.js + dist/assets/
npm run build:watch  # rebuild dist/ on change (closest to production)
npm run check-embed  # dist/embed.js still exports contractVersion + mount
npm run test         # vitest (happy-dom) — config in vite.config.mts
npm run type-check   # vue-tsc
npm run lint         # eslint  (lint:fix to autofix)
```

There is no standalone page: run it inside the platform, see
[Inside the platform](running.md#inside-the-platform).

## Notes

- **The look is the platform's**: colours, font, radius and dark mode come
  from its `--ep-*` design tokens, read at mount (`src/theme.ts`); the
  component conventions shared by all platform apps are in
  [One design for all ediarum.platform apps](../concepts/ui-design.md). Don't add colours or fonts here.

- **Vuetify's SASS utility classes are disabled** (`$utilities: false` in
  `src/styles/settings.scss`); do fiddly layout with scoped CSS, not `d-flex` /
  `ms-*`. The *theme* utilities (`bg-primary`, behind the `color` prop) are on,
  scoped to the root.
- Storage keys are prefixed `index-` (the platform's storage is shared).
- The backend is the enforcement point for access (403); the UI only hides
  the admin menu from non-admins (`ctx.user.roles`).

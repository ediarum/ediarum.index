# Tests

`make test` (or `scripts/test.sh` where `make` isn't installed) runs both
layers — no browser, no docker.

| Layer | Runner | Location | Run |
|---|---|---|---|
| Backend | **pytest** + FastAPI `TestClient` over in-memory SQLite (`tests/conftest.py`) | `tests/` | `make test-backend` · `uv run --group test pytest` |
| Frontend unit / component | **Vitest** + `@vue/test-utils` (config in `vite.config.mts`, setup in `frontend/tests/setup.ts`) | `frontend/src/**/*.spec.ts`, `frontend/build/*.spec.ts` | `make test-frontend` · `cd frontend && npm run test` |

SQLite doesn't exercise MariaDB-specific behaviour (FK enforcement, JSON,
`utf8mb4`); `scripts/migration-test.sh` runs against a real MariaDB. The app
inside the platform is checked by hand (see [Inside the
platform](running.md#inside-the-platform) and ediarum-platform's
`docs/integrating-an-app.md`, "Testing and checklist").

CI (`.gitlab-ci.yml`) runs `backend-test`, `migration-test` (an upgrade on
MariaDB from the previous release, losing no rows) and `frontend-test` (lint ·
type-check · vitest) in parallel on every commit, then `frontend-build`
(build + `check-embed`); a release tag adds `image-build` (see
[Release](release.md)) and a manual `deploy` stub — ediarum.deploy does the
deploying.

## Before opening a merge request

- `make test` (backend pytest + frontend vitest) must pass.
- `cd frontend && npm run lint && npm run type-check`.
- Touched a project's ingest/export? Re-run
  `uv run ediarum-index roundtrip-report <slug>` and check the
  diff didn't grow in a way you can't explain.
- New endpoint, setting or schema field? Update the
  [Reference](../reference/routes.md) / [Ingest & export](../ingest/index.md)
  pages as part of the same change — they're meant to stay accurate, not
  aspirational.
- Touched the docs or docstrings? `uv run --group docs mkdocs build` must pass
  (strict: no broken links or anchors) — see [Documentation](docs.md).

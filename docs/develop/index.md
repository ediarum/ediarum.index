# Develop

Architecture orientation for a new contributor, running it locally, and
where to hook in when adding something. For the *why* behind a decision see
[Schema design — the reasoning](../concepts/schema.md); for routes, auth, settings and the data
model see the [Reference](../reference/routes.md); for ingest/export details
see [Ingest](../ingest/index.md); for deploying see
[ediarum.index](../index.md).

## The shape of the system

```
frontend/  Vue 3 + Vuetify (platform embed: projects, a project's entries with `?type=`, ingest runs, keys)
    │  HTTP/JSON — src/api/*.ts
    ▼
src/ediarum_index/   FastAPI + SQLModel  ──▶  MariaDB (schema owned by Alembic)
    ▲
    │  TEI XML
ingest.py  /  export.py   (loader and its rough inverse)
```

- **One `entry` table** holds every entry type (person, place, group,
  organisation, work, bible book, glossary) across every project. Type-specific fields live in a
  JSON `data` column; only what every entry needs (`project_name`,
  `entry_type`, `label`, `source_id`, timestamps) is a real column.
- **The field schema is code, not data** — `src/ediarum_index/schemas.py`'s
  `FIELD_SCHEMAS` (base fields per `entry_type`) plus a per-project
  `SchemaOverride` in `src/ediarum_index/projects/<slug>.py` (or a package
  `<slug>/__init__.py`, like the shipped projects). `resolve_schema()` merges
  them; the frontend builds its form from `GET /{project}/schema/{entry_type}`.
- **Cross-entry links are one generic `relation` table**
  (`subject_id, predicate, object_id`) — not a join table per relationship
  kind. See `POST/GET/DELETE /relations/`.
- **Editorial comments and note-internal cross-references round-trip too**
  (`models.Comment`, `models.MentionAnchor`) — an ingested source's
  `oxy_comment_start`/`end` PIs and `persName[@key]`/`placeName[@key]`
  references, or a curator's own remark added in the app, survive an
  export back to TEI XML. See [Ingest](../ingest/index.md)'s
  "Comments and note-links" section.
- **Ingest and export are each other's rough inverse**, not two independent
  paths — a project's `ingest.py` extraction and `export.py` `Emit` config
  should always be read together.

## Backend layout

All in `src/ediarum_index/`:

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app: `lifespan`, middleware, error handler, includes the routers |
| `routes/` | one router per resource (`entries`, `relations`, `comments`, `export`, `files`, `keys`, `projects`, `schema`, `ingest_runs`) |
| `services.py` | every write (entries, relations, anchors, comments, ingest runs) and the export query — shared by routes and ingest; raises `ServiceError` subclasses that map to HTTP statuses |
| `deps.py` | shared FastAPI dependencies: `SessionDep`, `CallerDep` (platform user or API key, via `ediarum_sdk.auth`), `AdminDep`, `ProjectDep` (the `{project}` row, after the access check) |
| `cli.py` | the `ediarum-index` command line |
| `migrate.py` | applies the Alembic migrations programmatically, backup first |
| `models.py` | SQLModel tables, the I/O models, `FieldSchema` / `SchemaOverride` |
| `db.py` | engine and `get_session`; DB URL from env |
| `dates.py` | reduce uncertain date strings (`nach 1824`, `3. Jh.`, `356 v.Chr.`) to the integer `birth_sort` / `death_sort` keys |
| `schemas.py` | schema layer: base `FIELD_SCHEMAS`, `resolve_schema`, `validate_entry` |
| `projects/` | one auto-discovered module per project (`NAME` = the platform slug, `LABEL`, `OVERRIDES`, `REGISTER_DIR`) |
| `bootstrap.py` | `sync_registry` — seeds `entry_type` and mirrors the platform's project registry into `project` on startup |
| `migrations/` | Alembic `env.py` and `versions/` (`alembic.ini` sits at the repo root) |
| `ingest.py` | TEI XML → database loader (in-process, through `services`); `PROFILES` |
| `sources.py` | where a project's XML is on the shared volume (`XML_MOUNT_ROOT/<slug>/<REGISTER_DIR>`), which files its profiles read, their digest |
| `idservice.py` | `source_id`s from ediarum.id for entries created in the app; `ids backfill` |
| `watch.py` | `ediarum-index watch` / `scan`: ingests a project when its files' digest changes; handles `POST /files` notices |
| `export.py` | rebuilds a project's TEI XML from stored entries; `EXPORT` |
| `xmldiff.py` | whitespace/comment-insensitive but PI-*aware* XML diff, used by the round-trip tests |
| `roundtrip_report.py` | ingest → export → diff report, per record (matched by `xml:id`), for every source file of a profile |

The frontend's layout and scripts: [frontend](frontend.md).

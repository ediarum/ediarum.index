# Adding things

| To add… | Do this |
|---|---|
| **A field** on an existing project's entry type | `SchemaOverride(add=[FieldSchema(...)])` in `projects/<slug>.py`. No migration — it's a `data` key. |
| **A field** on *every* project's entry type | `schemas.FIELD_SCHEMAS[entry_type]` (the base list). |
| **A project** | Register it on the platform, then `scripts/add_project.sh <slug> [--register-dir <path>]` and edit `projects/<slug>.py`. No migration, no route/`schemas.py` edit. See [Adding a project](adding-a-project.md). |
| **A TEI ingest source** for a project | A profile in `ingest.PROFILES[slug]` (a flat `fields` XPath map, or a custom `extract_*` callable for a shape that doesn't fit one) + a matching `export.EXPORT[slug]` (an `Emit` per field). Check it round-trips: `uv run ediarum-index roundtrip-report <slug>`. See `docs/INGEST.md`. |
| **An entry type** (beyond person/place/group/organisation/work/bible_book/glossary) | `models.ENTRY_TYPES`. Seeded on startup (`bootstrap.sync_registry`, add-only) — no migration; give it a base schema in `FIELD_SCHEMAS` only if most projects will use it the same way, otherwise leave it project-specific like schleiermacher's `group`. Projects that declare `ENTRY_TYPES` only get it once it's added to their list. |
| **An entry type to one project** (one that exists already) | Add it to `ENTRY_TYPES` in `projects/<slug>.py`, if the module declares that list (without it, every type is offered already). Redeploy; no migration. See [Adding a project](adding-a-project.md#entry_types). |
| **A relation kind** | Nothing to register — `predicate` is a free string on the existing `relation` table. Just start writing/reading that predicate. |
| **A DB column/table** | A migration — follow [Changing the database schema](migrations.md) below. |
| **An HTTP route** | The resource's router in `routes/` (a new resource: a new module, added to `routes.ROUTERS`). A project-scoped route goes on the module's `project_router` (mounted under `/{project}`, which already checks the caller's access and the project); a fixed path on its `router`, with `CallerDep` or `AdminDep` — all from `deps.py`. Put writes in `services.py`, passing the URL's `project` so a row of another project is not found. Mirror an existing route of the same shape rather than inventing a new pattern. |
| **A frontend view/section** | `src/views/` for a route-level page, `src/components/` for a reusable piece (generic ones — not tied to one entry type or project — go in `components/common/`). API calls go in a `src/api/<thing>.ts` wrapper; shared load/create/remove logic in a `src/composables/use<Thing>.ts`. |

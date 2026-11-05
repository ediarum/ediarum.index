# Data model

Every entry type shares **one `entry` table**; type-specific values (surname,
birth_date, lat, …) live in the JSON `data` bag and are described by the
[schema layer](schema-layer.md). `project_name` and `entry_type` are **foreign
keys** into small lookup tables. Why: [Schema design — the reasoning](../concepts/schema.md).

| Table | Columns |
|---|---|
| `entry` | `id`, `project_name → project.name`, `entry_type → entry_type.name`, `label`, `source_id`, `data` (JSON), `birth_sort`, `death_sort`, `created_at`, `updated_at`, `ingested_at`, `ingested_source_hash` |
| `project` | `name` (PK), `label`, `description`, `is_active`, `created_at` |
| `entry_type` | `name` (PK), `label` — the canonical types: `person`, `place`, `group`, `organisation`, `work`, `bible_book`, `glossary` |
| `relation` | `id`, `subject_id → entry.id`, `predicate`, `object_id → entry.id` — generic triple for cross-references |
| `mention_anchor` | `id`, `relation_id → relation.id` (unique), `start_offset`, `end_offset`, `captured_text` — exact character span a `mentions` relation's link occupied in its subject's `note` at ingest time; self-validated lazily at export, see [Comments and note-links](../ingest/links-and-comments.md#comments-and-note-links) |
| `comment` | `id`, `entry_id → entry.id`, `text`, `author`, `created_at`, `source` (`ingested`\|`app`), `start_field`, `end_field`, `thread_meta` — editorial remarks, preserved from the source XML or written by a curator |
| `ingest_run` | `id`, `project` (profile slug), `started_at`, `finished_at`, `status` (`ok`\|`conflicts`\|`failed`), `created`, `updated`, `unchanged`, `problems` (JSON) — one row per ingest run, see [Ingest run history](../ingest/index.md#ingest-run-history) |
| `source_state` | `project → project.name` (PK), `digest`, `ingested_at` — what the last ingest of a project read (`sources.digest`); the watcher re-ingests when the volume's digest differs |
| `file_notice` | `id`, `project → project.name`, `event`, `path`, `previous_path`, `commit`, `sha256`, `received_at` — `POST /files` notices waiting for the watcher |
| `sdk_api_key` | `name` (PK), `key_hash` (SHA-256, unique), `projects` (comma-separated slugs or `*`), `is_admin`, `is_active`, `created_at`, `created_by` — `ediarum_sdk.auth.ApiKey` |

I/O models (not tables): `EntryIn` / `EntryEdit` (the API's bodies) and
`EntryCreate` / `EntryUpdate` (the ingest's, with `ingested_source_hash`),
`EntryPublic`, `EntryRef`, `ProjectPublic`, `EntryTypePublic`,
`RelationCreate` / `RelationPublic` / `RelationWithLabels`,
`MentionAnchorUpsert` / `MentionAnchorPublic`, `CommentIn` (the API's) /
`CommentCreate` (the ingest's, may claim `source`/`author`/`created_at`) /
`CommentPublic`, `IngestRunCreate` / `IngestRunPublic`.

**Project registry.** On every start `bootstrap.sync_registry` seeds
`entry_type` from `models.ENTRY_TYPES` (add-only) and mirrors the platform's
project registry into `project`: every registry project gets an active row with
the registry's label; a row the registry no longer lists is **deactivated,
never deleted** (its entries stay). An unknown slug in a request triggers one
more refresh, so a project added on the platform works without a restart.
Without a registry the discovered `projects/` modules are the list, add-only.

**Uncertain dates.** `birth_date` / `death_date` (and pta's `floruit`) are free
text stored verbatim (`nach 1824`, `um 1810`, `3. Jh.`, `356 v.Chr.`). On every
write `dates.sorts_for` reduces them to an integer (`year*10000 + …`,
BCE-safe) in the indexed `birth_sort` / `death_sort` columns, which back
`?sort_by=birth_date` / `death_date`; undated or unparseable rows sort last.

**Re-ingest reconciliation.** `ingested_at` / `ingested_source_hash` are set
only by an ingest run and let a later re-ingest tell a changed source record
apart from one a curator has edited since: every `PATCH` bumps `updated_at`, so
`updated_at` newer than `ingested_at` means "touched here since the last
ingest". See [Ingest](../ingest/index.md).

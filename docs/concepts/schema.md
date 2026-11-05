# Schema design — the reasoning

Why the data model and the "schema layer" look the way they do.

## One `entry` table + a JSON `data` bag

Persons, places, works… all live in **one table**. Only the fields every entry
needs are real columns (`project_name`, `entry_type`, `label`, `source_id`,
timestamps); everything type-specific (`surname`, `birth_date`, `lat`, …) goes
into the JSON `data` column.

Rationale:

- **Fields change often, tables shouldn't.** An editor wanting one more field on
  `person` for one project must not mean a migration and a schema deploy.
- **Cross-type queries stay trivial** — "all entries in project X", "search
  labels" — no `UNION` across five tables.
- The cost (no per-field DB constraints on `data`) is acceptable: this is an
  authority register, not transactional data, and validation lives in the app.

Links between entries use one generic `relation` triple table
(`subject → predicate → object`) for the same reason — no join table per
relationship kind.

## The field schema is *code*, not database rows

What fields a form has, their labels, types, order and required-ness live in
Python (`schemas.FIELD_SCHEMAS` + the project modules in `projects/`), not in
a `field` table.

Rationale:

- It's **developer-owned configuration**, versioned in git, reviewed in PRs,
  diffable — not data end-users edit.
- No admin UI to build, no bootstrap problem ("what's the schema of the schema
  table?"), no migration to change a label.
- It's tiny and read-only at runtime, so `resolve_schema` is `@lru_cache`d;
  `SCHEMA_VERSION` is the manual cache-buster.

## Base schema + per-project override

`FIELD_SCHEMAS` gives each `entry_type` a **base** field list. A project only
records its **delta** — `SchemaOverride(add / modify / remove / order)` in
the project's module in `projects/` — and `resolve_schema(entry_type, project)`
merges the two.

A field may be `repeatable` (it holds a **list** in `data`) with a `qualifier`
key on each item — `[{"value": "Ἰωάννης", "lang": "grc"}, …]`, `[{"value":
"118557831", "type": "GND"}, …]`. That's how a source with multilingual names or
several typed `<idno>`s round-trips without collapsing.

Rationale:

- Projects share ~90% of their fields; expressing only the difference keeps each
  project file a few lines and makes "what's special about this project"
  obvious.
- `project=None` → base schema, so the generic case needs no project config at
  all.

## Uncertain dates: stored as text, sorted by a derived key

`birth_date` / `death_date` (and pta's `floruit`) are **free text**, stored and
exported exactly as written — `"1809"`, `"nach 1824"`, `"um 1810"`, `"3. Jh."`,
`"356-323 v.Chr."`. Coercing them to an integer year would lose information the
edition deliberately records.

To still order a register by date, every write runs `dates.sorts_for(data)`.
It normalises the German conventions (`nach` / `vor` / `um` / `ca.` anchor on the
year they name; `N. Jh.` → the century span; `YYYY–YYYY` → a range;
`… v. Chr.` → BCE) and reduces the result to one integer,
`year*10000 + month*100 + day` — monotonic across BCE (negative years) and
partial dates (missing month/day = 1) — in the indexed, nullable
`entry.birth_sort` / `entry.death_sort` columns.
`GET /{project}/entries?sort_by=birth_date` (or `death_date`) orders by that column; rows
whose date is missing or unparseable sort last.

The sort columns are pure derived state — never in the API models, recomputed on
every create/`PATCH`, and backfilled by re-ingesting. Parsing is best-effort and
pure-Python (a few regexes, no date library): a value we can't interpret just
yields a `NULL` key, never an error.

## `project` and `entry_type` as lookup tables

`entry.project_name` and `entry.entry_type` are foreign keys into small
`project` / `entry_type` tables.

Rationale:

- **Referential integrity** — you can't insert an entry for a typo'd project or
  a non-existent type.
- **`entry_type` as a table, not an enum**, means adding a type is an `INSERT`,
  not an `ALTER TABLE … MODIFY ENUM` migration.
- `project` carries metadata (label, description, active flag).

Both are filled on startup by `bootstrap.sync_registry`: `entry_type` from
code (`models.ENTRY_TYPES`, add-only), `project` from the platform's project
registry (a project the registry drops is deactivated, never deleted, so its
entries stay).

## The flow

```
frontend  ──GET /leibniz5/schema/person──▶  resolve_schema()
                                                       = FIELD_SCHEMAS["person"]
                                                         merged with
                                                         projects/leibniz5/__init__.py OVERRIDES["person"]
          ◀── [ {name,label,type,required,options,ref_type,
                 repeatable,qualifier,qualifier_options,multiline}, … ] ──
frontend builds the entry form from that list; values are stored back in `data`.
```

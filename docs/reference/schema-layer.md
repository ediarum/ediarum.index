# Schema layer

Field definitions are **code, not database rows** (why: [Schema design — the reasoning](../concepts/schema.md)):

- `schemas.FIELD_SCHEMAS` — the base field list per `entry_type`.
  `FieldSchema`: `name`, `label`, `type` ∈
  `text | number | select | checkbox | date | reference`, `required`,
  `options`, `ref_type`, `multiline` (long free text: a textarea in the form,
  no table column), and for multi-valued fields `repeatable` + `qualifier`
  (e.g. `lang`, `type`) + `qualifier_options`. A repeatable field holds a
  **list** in `entry.data`, each item `{"value": …, <qualifier>: …}`.
- `projects/<slug>` → `OVERRIDES` — a per-project `SchemaOverride`
  (`add` / `modify` / `remove` / `order`, plus `extra_keys`: data keys the
  ingest writes that aren't form fields) keyed by `entry_type`.
  `projects/__init__.py` discovers the modules and builds `PROJECT_NAMES` and
  `PROJECT_OVERRIDES[(project, entry_type)]`. Field-by-field guide:
  [Adding a project](../develop/adding-a-project.md).

`resolve_schema(entry_type, project)` merges base and override; it is
`@lru_cache`d, with `SCHEMA_VERSION` in `projects/__init__.py` as the
cache-buster. `schemas.validate_entry` checks every write against it: unknown
keys (outside the schema and `extra_keys`) and missing required fields are a
422. The frontend builds its forms from `GET /{project}/schema/{entry_type}`.

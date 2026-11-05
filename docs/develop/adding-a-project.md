# Adding a project

A project itself — its slug, label and who may use it — comes from the
ediarum.platform's project registry (mirrored into the `project` table, see
`bootstrap.py`). What ediarum.index keeps per project is one module in
`src/ediarum_index/projects/`: its schema `OVERRIDES` and, optionally, its
`REGISTER_DIR`. Module paths below are relative to that folder. No
migration, no changes to the routes / `schemas.py`.

## Quick way

```bash
scripts/add_project.sh <slug> [--register-dir data/Register]   # the platform slug: [a-z][a-z0-9-]*
```

It copies `_template.py` to `<module>.py` (the slug with `-` spelled `_`, since a
module name can't contain `-`), sets `NAME` (and `REGISTER_DIR`), restarts the
`api` container if it is running, and checks `GET /projects` /
`GET /<slug>/schema/person` (`API_URL`, `API_KEY` for that check).

## Manual way

```bash
cd src/ediarum_index/projects && cp _template.py <module>.py
```

Then edit `<module>.py`:

| Field | Change to | Notes |
|---|---|---|
| `NAME` | `"<slug>"` | the platform's project slug, e.g. `"leibniz5"` |
| `LABEL` | display name | used only without a platform registry (local development); otherwise the platform's name wins |
| `DESCRIPTION` | `str` or `None` | optional |
| `REGISTER_DIR` | e.g. `"data/Register"` | only for a project ingested from its TEI registers, see below |
| `ENTRY_TYPES` | e.g. `["person", "place", "organisation"]` | optional: the entry types the project uses, see below; without it, all of them |
| `OVERRIDES` | `{}` or per-type deltas | **only** where the project differs from the base schema in `schemas.py` |

Restart the backend (`docker compose restart api`) — the module is read on
start. Files starting with `_` are ignored.

## ENTRY_TYPES

The entry types the project uses, from `models.ENTRY_TYPES`: only these get a
tab in the UI (`GET /{project}/entry-types`), and a new entry of another type
is refused (422), whether it comes from the UI, the API or an ingest. Leave it
out to offer every type (the default). A type that already has entries in the
project stays listed regardless, so declaring the list never hides data.
Every `OVERRIDES` key must be in the list; the backend refuses to start
otherwise, and also on an unknown type name.

To start using another type later, add it here (plus an `OVERRIDES` entry
and ingest/export profiles where needed) and redeploy. No migration is needed.

```python
ENTRY_TYPES = ["person", "place", "group", "organisation"]   # avhr
```

## OVERRIDES

`{entry_type: SchemaOverride(...)}`. `person`, `place` and `organisation`
have a base schema in `schemas.py`; a type without one (`group`, `work`,
`bible_book`, `glossary`) can still carry an `OVERRIDES` entry — it's then the
*entire* schema for that type in that project, not a delta.
`schleiermacher/__init__.py` declares no override for `group` at all: its
family entries (see `ingest.ingest_schleiermacher_groups`) carry no data,
only a `label`, so `group` stays schemaless there too. Leave
`OVERRIDES = {}` to use the base schema unchanged.

```python
OVERRIDES = {
    "person": SchemaOverride(
        add=[
            FieldSchema(name="gnd", label="GND ID", type="text"),
            # multi-valued field: value stored as a list of
            # {"value": …, "type": …} objects
            FieldSchema(name="idno", label="Identifiers", type="text",
                        repeatable=True, qualifier="type", qualifier_options=["uri"]),
        ],
        modify={"surname": {"label": "Family name"}},
        remove=["deathplace"],
        order=["forename", "surname", "gnd"],   # unlisted fields keep their order, after these
    ),
}
```

`FieldSchema.type` ∈ `text | number | select | checkbox | date | reference`
(`select` needs `options=[...]`, `reference` needs `ref_type="place"`). Add
`repeatable=True` for a multi-valued field; `qualifier` / `qualifier_options`
name the per-item key (`lang`, `type`, …). `leibniz5`, `mop` and `pta` use a
repeatable `idno` — see `leibniz5/__init__.py` / `pta/__init__.py`.
Set `multiline=True` on long free text (`note`, an Erläuterung): the form
renders it as a full-width textarea and the entry table hides the column.

`SchemaOverride.extra_keys: list[str]` names `data` keys the project's ingest
profile writes that are **not** form fields — not in `resolve_schema()`'s
output, never rendered by `EntryDialog`, but not drift either:
`schemas.validate_entry` (called on every entry write) accepts them
instead of rejecting them as unknown. Use it for data whose shape the
`FieldSchema` type system can't express (a structured, non-uniform repeatable
value) or that must not be independently editable (a value derived from
another field, where editing it alone would silently drop out of the export).
See `mop/__init__.py` (`alt_names`, `old_id`) and `avhr/__init__.py`
(`alt_names`, `gnd`, `viaf`, `wikidata`) for real examples — and
`ingest.py` / `export.py` for how each of those keys is actually
produced and round-tripped.

## If the project's data comes from TEI XML

The schema module is enough for hand-entered projects. To bulk-load from XML you
also add a profile to `PROFILES` in `ingest.py` (its `fields` keys must match
this module's field names) and run `uv run ediarum-index ingest <slug>`.
See [Ingest](../ingest/index.md).

A project with more than one register (e.g. persons *and* places) still has one
module here — one `OVERRIDES` entry per entry type — but one ingest/export
profile per register. The extra profiles get their own key and name the project
explicitly (`"project": "<slug>"`); see `schleiermacher/__init__.py`'s
`"place"` override and `PROFILES["schleiermacher_places"]` in `ingest.py`.

A project whose entries are ingested from its TEI registers declares
`REGISTER_DIR` — where they are inside the project's repository (e.g.
`data/Register`), which ediarum.fileservice checks out at
`XML_MOUNT_ROOT/<slug>/`; the repository and branch are configured in the
platform's project registry. `ingest.PROFILES[slug]["source"]` is a glob
relative to it. See [Where the XML comes from](../ingest/sources.md).

A module is either a flat `<module>.py` or a package `<module>/__init__.py`
(the shipped projects); both load the same.

See `leibniz5/__init__.py` for a real example and
[Schema design — the reasoning](../concepts/schema.md) for the reasoning.

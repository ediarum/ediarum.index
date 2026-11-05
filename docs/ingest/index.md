# Ingest

How a project's TEI registers get loaded into the database (`ingest.py`)
and rebuilt back out of it (`GET /{project}/export/{entry_type}`,
`export.py`) — documented together
because the two are meant to be each other's rough inverse, and
`tests/test_roundtrip.py` / `roundtrip_report.py` check exactly that.

`ingest.py` loads TEI registers into the database. Each register is a
**profile** in the `PROFILES` dict:

- `project` (optional) — the project slug the profile writes into; defaults
  to the profile's own key. Only needed when one project has more than one
  register, i.e. more than one `entry_type` to ingest: `PROFILES` (and
  `export.EXPORT`, which mirrors it) is keyed by *register*, so the extra
  ones get a key of their own and name their project here
  (`schleiermacher_persons` / `schleiermacher_places` → `schleiermacher`).
  Code that needs the project uses `ingest.project_of(key)` /
  `export.export_config(project, entry_type)`, never the key itself.
- `entry_type` — what each record becomes (`person`, `place`, …)
- `source` — a glob for the register's XML files, relative to the project's
  `REGISTER_DIR` in its checkout on the shared volume (see [Where the XML
  comes from](sources.md) below), not the repo root
- `record_xpath` — which element is one record (`//tei:listPerson/tei:person`)
- `fields` — `data` key → a spec that is either an **XPath 1.0** string returning
  one value (lxml; `tei:` bound to the TEI namespace; date strings kept verbatim,
  placeholder-only values like `*`/`†` dropped), or
  a dict `{"each": <element xpath>, "attr": …, "as": …}` for a **repeatable**
  field — every matching element becomes `{"value": <text>, <as>: <attr>}`, so
  multilingual `<forename>`/`<addName>`, typed `<idno>`s, and mop's alternate
  `<persName type="alt">` names (with `@subtype` birthname/pseudonym) are all kept.
- `attrs` (optional) — `{record-attribute: data key}`, for values that live on
  the record element rather than a child. mop uses it to carry `oldID` (the
  entity's pre-migration ediarum id) into `data["old_id"]` so it round-trips.
- `label` — a callable building the entry label; the person profiles use
  `_person_label` (`"Surname, Forename"`, or whichever is present — same rule as
  the frontend's `personLabel`). A profile may instead give a `label_template`
  format string.

A register whose shape a flat field map cannot express declares **`extract`**
instead of `fields` + `label`: a callable taking one record and returning
`{"label", "data"}`. Everything else — walking the files, the safety checks,
dropping empty values, the summary — stays shared. Every profile except
`leibniz5`, `mop` and `pta` uses one (see below). A profile may also
set `recover: True` to parse malformed XML leniently instead of aborting on
the first file that is not well-formed; `schleiermacher_persons` needs this for one
file with an unfilled template id.

Shipped profiles: `leibniz5`; `mop` (Akten der preußischen Monarchie, ~7 300
persons, `oldID` + alternate `<persName type="alt">` names carried through);
`pta` (Patristic Text Archive — `<floruit>` instead of birth/death, multilingual
names, typed `<idno>`s); `avhr`, `avhr_places`, `avhr_organisations`; `mega`;
`schleiermacher_persons`, `schleiermacher_places`,
`schleiermacher_organisations`, `schleiermacher_glossary`,
`schleiermacher_works`, `schleiermacher_bible_books` (see below). A
profile's `data` keys must line up with `resolve_schema(entry_type, slug)` —
i.e. with the project's module in `projects/` — except keys a project explicitly
declares as `SchemaOverride.extra_keys`: data the ingest/export profiles
legitimately read and write but that isn't a form field (mop's `alt_names` /
`old_id`; avhr's `alt_names` / `gnd` / `viaf` / `wikidata`; mega's and
schleiermacher's `alt_names` / `birth_names` / `pseudonyms`). **That alignment is
enforced, not just convention:** every entry write (`services.create_entry` /
`update_entry`, used by the ingest and the API alike) calls
`schemas.validate_entry`, which rejects a `data` key that's neither a
declared field nor a declared `extra_key` — a typo'd or drifted profile field
name fails the ingest run immediately (see the per-record `failed` list) rather
than being written silently. `EntryDialog.vue` separately preserves any
existing undeclared key across an edit (it merges into `props.entry.data`
rather than rebuilding it), so a declared `extra_keys` field also survives
being edited in the UI, just without a rendered input for it.

```bash
uv run ediarum-index ingest mop           # ingest a profile
uv run ediarum-index ingest pta --dry-run   # print first 5 records, write nothing
uv run ediarum-index ingest                 # INDEX_PROJECT env, or 'leibniz5'
uv run ediarum-index ingest avhr --source 'some/other/*.xml'  # override the glob
uv run ediarum-index ingest schleiermacher_places --dry-run  # a profile key, not a project
uv run ediarum-index ingest --all          # every profile, one run
```

`--all` ingests every profile in `PROFILES` in two phases: first every profile's
entries, then every profile's links (mentions, comments, families, place
nesting), so a link into another register resolves on the first run regardless
of order. `--of-project <name>` does the same for one project's profiles (the
watcher uses it). `--source` isn't allowed with either (that override only
makes sense for one profile at a time). A
profile that fails for a reason unrelated to its own data — its source glob
matches nothing because fileservice hasn't checked the project out yet (see
[Where the XML comes from](sources.md) below) — is
reported and skipped rather than aborting the rest of the batch; the run still
exits non-zero if anything was skipped, conflicted, or failed.

The ingest runs **in-process**: it writes straight into the database
(`db.DATABASE_URI`, one session per run) through the same `services`
functions the API's routes use — same validation, no HTTP, no credentials.
Its read helpers (`fetch_existing`, `fetch_relations`, `fetch_comments`, …)
return the same JSON-shaped dicts the API would, so the reconcile passes
compare like with like. `ensure_project()` first checks the target project is
an active row in the `project` table (mirrored from the platform registry).

## Ingest run history

Each profile's run (`_ingest_entries`, one per profile slug) ends by
recording its summary — the same created/updated/unchanged counts and
conflict/skipped/failed details it prints to the terminal — as one
`models.IngestRun` row (`ingest.report_run` → `services.create_ingest_run`),
readable via `GET /ingest-runs` and the UI's "Ingest runs" page (platform
admins only). Most runs are started by the watcher with nobody watching a
terminal, so this is where conflicts and failures surface. A report failing
never fails the run itself (`report_run` catches the error and prints a
warning) — an ingest that wrote its entries but couldn't file its report is
still a successful ingest.

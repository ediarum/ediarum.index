# schleiermacher — Schleiermacher in Berlin

Six registers, each its own profile writing into the project `schleiermacher`; `--of-project schleiermacher` ingests them all.

## Persons (`schleiermacher_persons`)

Profile `schleiermacher_persons`, `project: "schleiermacher"`, `entry_type:
"person"`, source `Personen/*.xml` (relative to the project's `REGISTER_DIR`
clone — see [Where the XML comes from](sources.md)).
`extract_schleiermacher_person()`; schema override in `projects/schleiermacher/__init__.py`.
Adds `used_name` (the call name, `forename/name[@type='used']` — stays part of
the flattened `forename` too) and `name_link` (`persName/nameLink`, empty in
the source so far). `wedding` / `wedding_note` come from `event[@type='wedding']`.
`recover: True` — `Z.xml` has an unfilled template id
(`xml:id="${ediarum_id}"`) that is not well-formed and would otherwise abort
the whole file; what lxml repairs is printed as a warning.

**Family groups.** ~3300 of ~8200 persons are nested inside a source
``listPerson[@type='group']` (a family; `<head>` names it — 8 of 934 groups
have none). The family is *not* a person field: 57 of the 926 headed groups
reuse the same head text for more than one distinct family in a single file —
e.g. three separate "Bülow" families in one file — so a display string can't
identify a family. Instead, each group becomes its own `group` entry — the
head text is only the entry's `label`; there is no `group` form field
(`group` has no base schema and `schleiermacher` declares no override for
it) — and each member gets a `person --member_of--> group` relation (see
[Relations](links-and-comments.md#relations) below).

This runs as a second pass, `PROFILES["schleiermacher_persons"]["post_ingest"] =
ingest_schleiermacher_groups`, invoked by `_ingest_one` once every person in
the run is already in the DB (`id_by_xmlid` maps each person's `xml:id` to
its new entry id — a small, otherwise-unused bit of bookkeeping every other
profile ignores). It re-walks the same source files (`_source_trees`) for
`listPerson[@type='group']`, computes each group's members and a **stable
synthetic id** (`_group_source_id`: a hash of `(filename, head text,
ordinal-among-same-head-in-file)` — *not* of the member set, since
membership legitimately drifts and hashing it would treat every such edit as
a brand-new family), then reconciles two things independently, both via the
existing add/patch/create/delete primitives:

- **the family entries themselves**, via the same `fetch_existing` +
  `hash_data`/`_reconcile` machinery used for persons (hashing `{"label": head}`,
  a family's only mutable content) — create / update / unchanged / conflict,
  exactly as for a person;
- **membership**, via `fetch_relations(…, predicate="member_of")`: a person whose
  desired family matches their current one is left alone; a person who moved
  to a different family gets the old relation deleted and a new one created;
  a person no longer in any group has their relation deleted. A family is
  **never deleted**, even if left with zero members — an empty family is a
  queryable signal (`GET /{project}/relations?object_id=…` returns nothing), not
  something to silently clean up, consistent with `ingest.py` never deleting
  a person either.

A family's id — and therefore its identity across runs — does *not* depend
on its membership, so members can be freely reassigned without ever
recreating the family entry. It *does* change if a group is renamed or
reordered relative to a same-head sibling in the same file: an accepted,
documented limitation, the same class as a person's own `xml:id` changing
being unrecoverable to `source_id`-keyed reconciliation elsewhere. Verified
against the real source data: extracting all 934 groups produces exactly 934
distinct ids — no collisions.

## Places (`schleiermacher_places`)

The project's second register: profile `schleiermacher_places`, `project:
"schleiermacher"`, `entry_type: "place"`, source `Orte.xml` (one file, 2852
places; relative to the same `REGISTER_DIR` `schleiermacher_persons`
uses — see [Where the XML comes from](sources.md)).
`projects/schleiermacher/__init__.py`'s `OVERRIDES["place"]` carries the
schema, `extract_schleiermacher_place()` the extraction:

- `placename` from `placeName[@type='reg']` — exactly one, never empty in all
  2852 records, so it is `required` and doubles as the label.
- `alt_names` from `placeName[@type='alt']` — a *regular repeatable form
  field* (`[{value}]`), unlike the person registers' `alt_names`: there is no
  surname/forename split to protect, so nothing stops it being edited.
- `place_type` from the record's own `@type` (via the profile's `attrs`
  channel), with the register's actual values as select options (`building`,
  `district`, `street`, `park`, `forest`, `mountain`, `sea`, `monument`,
  `others`); set on 451 places, mostly sub-places.
- `geonames` / `idno_other` — the `idno[@type='uri']`, verbatim (at most one
  per place). `ingest._split_idnos` routes it by whether its text contains
  `geonames.org`. `geonames` keeps the **whole** URI rather than the bare
  number: the register spells the same address 76 ways (977× `https://`, 733×
  `http://`, slug suffixes like `/2812482/halle.html`, three malformed).
- `note` — every `<note>` flattened to text and joined with `"; "`: 467 notes
  carry `<placeName key>`/`<persName key>` cross-references (flattened, as
  elsewhere), and two places have an empty `<note/>` *before* the real one,
  which reading only the first note would have lost.
- `lat` / `lon` of the base schema are removed — the register has no
  coordinates.

**Sub-places.** 676 places are nested in another place's `<listPlace>`
(buildings, districts, streets of a city; one case three levels deep). The
`record_xpath` `//tei:listPlace/tei:place` matches them like any other place,
so each is an ordinary `place` entry; the nesting itself becomes a
`place --part_of--> place` relation, built by
`PROFILES["schleiermacher_places"]["post_ingest"] =
ingest_schleiermacher_place_nesting` once every place is in the DB. Only the
immediate parent is recorded — a chain of `part_of` relations describes the
three-level case. This reuses the membership reconciliation of the family
pass (`_reconcile_relations`, shared by both): a sub-place moved under
another parent gets its relation replaced, one promoted to the top level has
it deleted, and no place entry is ever deleted. Unlike families, no synthetic
ids are needed — both ends of the relation are places with their own
`xml:id`.

Both schleiermacher profiles reconcile independently: each fetches only its
own entry type (`fetch_existing(project, entry_type)`) and its own predicate,
so re-ingesting persons never touches places or `part_of`, and vice versa.
`post_ingest` hooks receive both the profile key and the project
(`hook(session, key, project, id_by_xmlid, source)`).

**Not captured:** 10 `placeName` elements in 7 places carry an ediarum
placeholder id as `@type` instead of `reg`/`alt` (e.g.
`type="type_isc_25r_pfc"`, in `S4797270`, `S7190472`, `S3790074`,
`S1293951`, `S6428046`, `S9075021`, `S7562814`). Their content is descriptive
text, not a name ("Stadt an der Emsmündung in Ostfriesland"; in `S6428046` a
single sentence split over three elements), so it is neither an alternative
name nor safely a note — it is dropped on ingest and belongs fixed in the
source.

## Organisations (`schleiermacher_organisations`)

Profile `schleiermacher_organisations`, `project: "schleiermacher"`,
`entry_type: "organisation"`, source `Koerperschaften.xml`; schema in
`projects/schleiermacher/__init__.py`, `EXPORT` config in `export.py`.

A nested `listOrg` with `head` (a parent institution) becomes a `group` entry
plus `member_of` relations (`group_xpath` / `group_member` on the profile). It
runs in the same pass as the person families, `ingest_schleiermacher_groups`;
that pass's `_reconcile_relations` is scoped to the entries of its own run, so
it never removes the other register's `member_of` relations.

`persName[@key]` links in `desc` become `mentions` (`note_tag: "desc"`); export
splices them back into the `description` field (`note_field`).

## Glossary (`schleiermacher_glossary`)

Profile `schleiermacher_glossary`, `project: "schleiermacher"`, `entry_type:
"glossary"`, source `Glossar.xml`; `extract_schleiermacher_glossary()` does the
extraction.

`note` is the flattened `p` paragraphs without `p[@type='source']`, which is
the `source` field. `@resp` is kept verbatim, and the `interp/@id` loses its
`#` (export puts it back).

**Export deviations:**

- The `note` paragraphs come back as one `<p>`, and a note without `p`
  children comes back wrapped in a `<p>`.
- `ref` elements are flattened to text, so the `@target` is lost. `_text` pads a
  `ref` with a space, except before `,.;:)!?`, since the files drop it
  (`Georges<ref>Bd. 2</ref>` → "Georges Bd. 2").
- Comments land at the record's end or in the `note`, as for every register.

## Bible books (`schleiermacher_bible_books`)

Profile `schleiermacher_bible_books`, `project: "schleiermacher"`,
`entry_type: "bible_book"`, source `bibelsystematik.xml` (76 books);
`extract_schleiermacher_bible_book()` does the extraction.

The items have no `xml:id`, so the profile's `source_id` callable returns
`bibelsystematik:<n>` (the `idno` is not unique) and export's `no_xml_id` keeps
that out of the XML. The canon part (`AT`/`AP`/`NT`) comes from the enclosing
`list[@type]`; export rebuilds those lists (`partition`) with their long
`label`, items in `position` order.

**Export deviation:** the empty `gruppea`/`gruppeb`/`gruppec` labels are not
restored.

## Works (`schleiermacher_works`)

Profile `schleiermacher_works`, `project: "schleiermacher"`, `entry_type:
"work"`, source `Werke.xml` (3263 records); `extract_schleiermacher_work()` does
the extraction.

- **Groups.** `listBibl[@type='group']`/`head` (an author's works) becomes a
  `group` entry plus `member_of`, like the person families (`group_xpath` /
  `group_member`).
- **Authors and editors.** `authors` / `editors` are structured lists of
  `{surname, forename | name | orgname, key, role}` (`_contributors`; an empty
  `persName` is `{"unknown": true}`) and `extra_keys`, not form fields; export
  rebuilds them with `Emit(builder=…)`. The `key`s point into the person
  register but are **not relations**.
- **Mentions.** Only `persName`/`placeName[@key]` in `note` are `mentions`
  (`links_only_in_note`).
- **Nested `bibl`.** The one `bibl` inside a `title` (`@sameAs`, no `xml:id`) is
  part of the title text, so `record_xpath` skips nested `bibl`.

## Export deviations

**schleiermacher_persons** — family groups round-trip:
`export.build_document`'s grouping branch (`_emit_grouped`) reconstructs every
`listPerson[@type='group']` from the `group` entries and `member_of` relations
[Family groups](schleiermacher.md#persons-schleiermacher_persons)
builds. Verified against the real data: all 8 214 persons and all 934 groups
present in the export, none missing or duplicated, for every source file.
Persons are exported sorted by label (not document position), and grouping
extends that to families — a family with several members moves as one block
to its label's alphabetical position. Since `roundtrip_report.py` diffs per
person matched by `xml:id` (see [Export](export.md) above), that
reordering produces no diff. A `persName[@key]`/`placeName[@key]`
cross-reference inside `<note>` round-trips as a `mentions` relation, exactly
when a stored `MentionAnchor` still validates and best-effort otherwise (see
[Comments and note-links](links-and-comments.md#comments-and-note-links) above) — what's left
under `--ignore note` is a comment's field-anchor approximation or a link
whose anchor went stale or never resolved. Empty
`<forename/>` is still dropped, same as elsewhere —
`--ignore-empty forename` filters that back out. `alt_names` /
`birth_names` / `pseudonyms` are three separate fields, one per `@subtype`
bucket (`ingest._alt_names`, shared with mega), each a structured list like
mop's/avhr's — `{surname, forename}` where the source splits it, `{value}`
otherwise — so the split round-trips exactly instead of collapsing into a
joined string; not an editable form field (`projects/schleiermacher/__init__.py`,
`projects/mega/__init__.py`), same reason as mop's/avhr's `alt_names`. A person with
more than one alternate-name variant gets them back grouped by bucket, not
interleaved in original document order (same "field order is normalized"
class as pta/avhr's). `sex`'s four attributes
(`value`/`evidence`/`resp`/`cert`) round-trip; `<event type="wedding">`
similarly, with its `@when` and nested `<note>` reconstructed as one element
(ordered right after `sex`, matching the source's typical field order).
`used_name` (the "Rufname"/call name) is spliced back into `forename` as an
inline `<name type="used">` wrapper on a best-effort basis
(`export._splice_inline_wrapped_value`, config'd via the `inline_wraps` key
on the schleiermacher_persons `EXPORT` entry): its own text is already part
of `forename`'s (both captured from the same source element at ingest —
see `extract_schleiermacher_person`), so export searches `forename` for
`used_name`'s value and wraps it if found uniquely. Left plain (no wrapper) when the
value isn't found or occurs more than once — e.g. `forename`/`used_name`
edited independently in the app (both are separately editable form
fields) — with no correctness consequence either way, since the value
itself is never lost from `used_name` regardless of whether the wrapper
gets reconstructed; unlike a `mentions` link, there's no stored-offset
fallback for this, since there's no reference to get wrong, only a
cosmetic wrapper to guess at. `name_link` is wired up but never observed
non-empty in the source, so it's untested in practice. The record's
`@xml:id` is written from `source_id`. `gnd` / `viaf` are *not* re-emitted (same
reasoning as avhr's derived views — `idno_other` alone is the source of truth
for `<idno>`), but unlike avhr they are form fields in
`projects/schleiermacher/__init__.py`: editing `gnd`/`viaf` alone has no
effect on export — edit `idno_other` instead.

**schleiermacher_places** — the nested `<listPlace>` structure round-trips:
`export.build_document`'s nesting branch (`_emit_nested`) puts every place
back under its `part_of` parent, after the parent's own fields, recursively.
Verified against the real `Orte.xml`: all 2852 places present, none missing or
duplicated, every one of the 676 sub-places under the same parent as in the
source (the three-level case included), and all 9 `@type` values restored.
Siblings are sorted by label at every level — the source's own order, so this
costs nothing in practice. `roundtrip_report.py` diffs each place *without* its
nested sub-places (they're diffed under their own id) and reports the
hierarchy separately ("N under a different parent"), so reordering children
doesn't show up as a parent's diff. With `--ignore note`, 8 of 2852 places
differ: the 7 with the placeholder-typed `placeName`s described
[above](schleiermacher.md#places-schleiermacher_places), and
one (`S0000585`) whose `<idno>` follows its `<placeName>` in the source — pure
field-order normalization. Without it, the rest is the usual markup
flattening inside `<note>` and dropped empty `<note/>`s; the flattened note
*text* matches the source for all 2852 places. Every `<idno>` comes back
character-for-character, whatever its spelling. The `@xml:id` comes from
`source_id`, as in the person register.

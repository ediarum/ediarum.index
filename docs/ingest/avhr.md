# avhr — edition humboldt digital

Three registers: persons, places and institutions. `--of-project avhr` ingests all three.

## Persons (`avhr`)

`projects/avhr/__init__.py` carries the
schema override, `extract_ehd_person()` the extraction. It needs a callable
rather than a field map because the label joins its parts conditionally,
alternate names are collected across elements, and `floruit` / `sex` / `note`
carry half their information in attributes.

Two things the source data forces:

- **`surname` is not required.** Part of the register carries an undivided
  `<name>` instead of `surname`+`forename`, which goes into the added `name`
  field.
- `birth_date` / `death_date` are usually a bare year, but a minority are free
  text — approximations, eras, spans and centuries — and are kept verbatim,
  same as every other project's dates.

`label` is `"Surname, Forename"` (or the undivided name) — the order the source
files are alphabetised by. `<note>` is flattened to plain text; the `@key`
cross-references inside it (`persName`, `placeName`, `orgName`) become
`mentions` relations with an exact anchor (see
[Comments and note-links](links-and-comments.md#comments-and-note-links)). Their targets live in the
project's other two registers, so a link only resolves when `avhr_places` and
`avhr_organisations` are ingested too — `--of-project avhr` runs all three, and
the two-phase run resolves the links on the first pass. `gnd` / `viaf` /
`wikidata` are pulled out of `<idno>` URIs into separate fields, with every
other identifier falling back to `idno_other`.

## Places and institutions (`avhr_places`, `avhr_organisations`)

Ingested mainly as the targets of the person notes' `placeName[@key]` (724) and
`orgName[@key]` (483) links, shaped like their schleiermacher counterparts
(`extract_ehd_place()`, `extract_ehd_organisation()`, schema overrides in
`projects/avhr/__init__.py`).

- **Orte** (`Orte/*.xml`, ~8 150 places): `placename`, `alt_names` (with
  `@subtype` as qualifier), `geonames` / `idno_other` split like schleiermacher's
  (`_split_idnos`), `note` + `note_resp`, `place_type` (`@type`), `old_id`,
  `resp`, `role` and `references` (`linkGrp/ptr`, like the persons). A nested
  `place/listPlace/place` is a `place` entry of its own with a `part_of`
  relation (`ingest_schleiermacher_place_nesting` is reused as is). Links in
  `<note>` become `mentions`.
- **Einrichtungen** (`Einrichtungen.xml`, 238 orgs): `orgname`, `alt_names`,
  `idno_uri`, `description` (`desc`, `note_tag: "desc"` for its links),
  `old_id`, `references`. `<location>/<address>` (a GeoNames `idno`,
  `settlement[@key]`, an address `note`, sometimes its own `linkGrp`) is not
  captured.

## Export deviations

**avhr** — a `persName`/`placeName`/`orgName` `[@key]` cross-reference inside
`<note>` round-trips the same way mop's/schleiermacher's does, provided
`avhr_places`/`avhr_organisations` are in the same run (`roundtrip_report.py avhr
avhr_places avhr_organisations`, or no args). Only a key linked *twice* in the
same note loses its earlier occurrence (one relation, one anchor per target);
other inline markup (`<bibl>`, `<ref>`, `<hi>`, `<quote>`, `<rs>`) is still
flattened to text; the
`<note>/<p type="source">` wrapper itself is still flattened to plain text,
same as elsewhere; empty `<note/>` / `<forename/>`
are dropped. `alt_names` is structured like mop's (`{surname, forename}` or
`{value}`, plus `kind` for `@subtype`) rather than a flattened string, so
`persName[@type='alt']` — split, `birthname`/`pseudonym` kind included — round-
trips exactly; like mop, it's not an editable form field (`projects/avhr/__init__.py`),
just captured/restored by the ingest and export profiles. Field order is
normalized like pta's. `gnd` / `viaf` / `wikidata` are display-only derived
views of `idno_other` (regex-extracted, not their own source of truth) and,
for the same reason as `alt_names`, aren't form fields either — editing
`idno_other` (the actual `<idno>` list, restricted to `@type='uri'` on ingest
so export's hardcoded `type="uri"` is always correct) is what reaches the
export; only it is re-emitted, so `<idno>` round-trips without duplication.
`<linkGrp>`/`<ptr>` (`references`, `"<type>[/<subtype>]:<target>"` parsed back
into `@type`/`@subtype`/`@target`) round-trips too, but every `<ptr>` lands under
one rebuilt `<linkGrp>` — the source's grouping into possibly several `<linkGrp>`s
isn't captured (not observed in practice: every avhr person has at most one).
`oldID`, `role`, `resp`, `duplicate`, `sex` (`@value`/`@evidence`), and the
`name`/`surname`+`forename` split on the primary `persName` round-trip.

**avhr_places / avhr_organisations** — names, identifiers, notes with their links,
`references`, sub-place nesting and the record attributes round-trip. Still
deviating: inline markup other than links in `<note>`/`<desc>` (as for the
persons), oxy comment placement, and for the organisations the whole
`<location>` block, which is not captured.

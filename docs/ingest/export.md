# Export (round-trip)

`GET /{project}/export/{entry_type}` rebuilds the register XML from the stored
entries — the rough inverse of ingest. `export.py` holds an `EXPORT`
config per register (keyed like `ingest.PROFILES`, looked up by
`export_config(project, entry_type)`): an `Emit` per `data` field (`persName[@type='reg']/surname`,
`idno` with `type`, …) whose keys mirror the ingest `fields`, plus an element
`order`.

The output **follows the project's shape but deviates**: whitespace and
indentation are the serializer's, markup inside `<note>` other than a
re-spliced `mentions` link is dropped, `<floruit>` date attributes aren't
restored, `pta`'s `<persName type="reg">` comes back bare, and the
`<teiHeader>` is a generated stub. Structure and field content round-trip;
formatting and the envelope do not. Editorial comments and note-internal
links round-trip too — see
[Comments and note-links](links-and-comments.md#comments-and-note-links) above.

`tests/test_roundtrip.py` ingests a fixture, builds the export, and diffs
the two with `xmldiff.xml_diff` — a **unified diff that ignores whitespace
and plain `<!-- -->` comments, but *compares* `oxy_comment_start`/`end`
PIs** (see `xmldiff.py`'s own module docstring), so a non-empty diff is a
real difference. It asserts clean round-trips for per-project fixtures and
shows a human-readable deviation report for a lossy one.

To see the deviations for **every ingested source file**:

```bash
uv run ediarum-index roundtrip-report            # all profiles -> ./roundtrip-diffs/
uv run ediarum-index roundtrip-report pta --out /tmp/rt
uv run ediarum-index roundtrip-report avhr --ignore note --ignore-empty forename
```

`roundtrip_report.py` diffs **per person, matched by `xml:id`** — not the whole
`<listPerson>` as one document. Export reorders persons (alphabetically by
label) and, for schleiermacher, moves whole families to their label's
position; matching by id instead of document order means only a person whose
own content actually differs shows up, and reordering (document- or
family-level) produces zero diff. A person present on only one side (dropped,
or duplicated) is reported separately, by id. `--ignore TAG` (repeatable)
drops every element with that local name from both sides before diffing —
for a known, accepted deviation (mop's flattened `<note>` markup) that would
otherwise drown out everything else; `--ignore-empty TAG` instead drops only
the content-free instances (a bare `<forename/>`, not one with real content).
Neither changes what counts as a clean round-trip elsewhere (tests, the API)
— they only thin this report's output, letting you filter down to the true
residual past the already-known deviations below.

Files that round-trip cleanly produce no `.diff`; `<out>/_summary.txt` lists
every file with how many of its persons actually differ (plus any missing
from, or unexpected in, the export).

Current deviations: **leibniz5** — `<forename/>` and `<nameLink>` are dropped (not
captured); **mop** — empty `<note/>` / `<forename/>` are dropped; a
`persName[@key]`/`placeName[@key]` cross-reference inside `<note>`
round-trips (see [Comments and note-links](links-and-comments.md#comments-and-note-links)
above), but other inline markup (e.g. `<bibl>`) is still flattened to
text; **pta** — `@resp` / `@source` on
`<person>`, `@type="toponymic"` on `<surname>`, `<genName>` (regnal numbers),
`<floruit>` date attributes, and the `<note>/<p>` wrapper are all dropped; the
field *order* within a record is normalized (source is inconsistent, export is
always `idno, forename, surname, epithet, floruit, note`) — record count and
order are unaffected. Uncertain dates (`nach 1824`, `485/484 v. Chr.`), `?` name
placeholders, `oldID`, and every alternate name — with its
`<surname>`/`<forename>` split and `birthname`/`pseudonym` kind — round-trip.

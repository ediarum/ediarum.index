# Relations, comments and note-links

## Relations

`POST` / `GET` / `DELETE /{project}/relations` manage generic `(subject_id,
predicate, object_id)` triples between two entries of the project
(`models.Relation`) — e.g. schleiermacher's `person --member_of--> group`
(family) and `place --part_of--> place` (sub-place) above. `GET` takes optional
`subject_id` / `object_id` / `predicate` filters; each row also carries
`subject_label` / `object_label`, resolved server-side (two aliased joins, not
a per-row lookup), so a caller never has to turn a bare id into a display
name itself. A duplicate triple is a 409 (unique constraint on the full
triple). Nothing here is project-specific — any project with person-to-person
or person-to-group structure (genealogies, institutional membership,
correspondence networks) can use the same mechanism.

A `models.MentionAnchor` records, for one relation, the exact character span
a `mentions` link occupied in its subject's `note` at ingest time (see
[Comments and note-links](#comments-and-note-links) for how it's used). The
ingest upserts it for every resolved link on every run
(`ingest.upsert_mention_anchor` → `services.upsert_mention_anchor`); the API
exposes the same upsert as `PUT /{project}/relations/{id}/anchor`. It is not
restricted to `mentions`, but nothing else uses it.

## Comments and note-links

The source XML carries a large amount of editorial discussion: **4 727**
`oxy_comment_start`/`oxy_comment_end` PI pairs (mostly
mop/mega/schleiermacher) and **503** plain `<!-- -->` comments (mostly avhr).
Separately, `<note>` prose often contains real cross-references to other
entries (`persName[@key="…"]`, `placeName[@key="…"]`, avhr's
`orgName[@key="…"]`). Both are captured as data: `models.Comment` rows, and
`mentions` `Relation`s (the mechanism [above](#relations)).

**Anchoring.** A comment is anchored by `(start_field, end_field)`, not a
single field — investigating the real corpus (not a handful of examples)
found that "one comment → one field" doesn't hold for a large share of real
data: only ~35% of oxy comments cleanly wrap one field's own text; ~20% are
empty position-markers between siblings; ~15% wrap a whole nested
cross-reference element; ~30% (dominant in mop) span multiple sibling fields
or, rarely, two `<person>` records. Equal `start_field`/`end_field` is the
clean single-field case; both `None` is a genuinely unattached, entry-level
remark. avhr's plain comments are mostly **fixed-position convention**
(top-of-record for identity research, end-of-record for source citations),
not true field-proximity — `ingest._walk_record_xml_comments` reflects that:
only a comment that is itself a child of `<note>` gets `"note"` as its
field, everything else is `None`/`None`.

**Parsing.** `ingest._walk_record_comments` walks one `<person>`/`<place>`
record in document order, tracking which field the walk is currently inside
(`ingest._FIELD_BY_TAG`) — needed because a comment can start in one field
and end in another. `persName`/`placeName`/`orgName` `[@key]` cross-references
found while walking are collected as a side effect of the same pass, not
separate code. A nested record list (`listPlace`/`listPerson`/`listOrg`, e.g. a
place's sub-places) is not walked into: its records are walked on their own, and
their comments and links belong to them, not to the record containing them. This requires the record to have been parsed with
`remove_pis=False` (`ingest._source_trees`) — confirmed safe for every other
consumer, since `itertext()` (used everywhere fields are flattened to text)
never reads PI pseudo-text regardless of whether PIs are present in the
tree. Threading metadata (`mid`/`id`/`parentID`, when the source comment is
part of a reply chain) is preserved verbatim in `Comment.thread_meta`, but
the app shows a flat comment list; replying to a specific comment isn't
supported.

The ~15% "wraps a whole nested cross-reference element" case above needs its
own handling: `<persName>`/`<placeName>` aren't themselves in
`_FIELD_BY_TAG` (only their leaf children, `surname`/`forename`/`name`, are),
so a comment's PI boundary sitting immediately *before*/*after* the whole
wrapper — not nested inside it — is invisible to the ordinary
field-propagation walk. `ingest._wrapper_field` catches this specific shape:
when a boundary's field would otherwise come out `None`, it checks whether
the immediately adjacent sibling node is a `persName`/`placeName` and, if
so, falls back to that wrapper's own first mapped-field descendant (e.g.
`surname`) rather than leaving the comment unattached. Without it, such a
comment would fall to the record-level fallback on export — appended
after every other field, reading as if it concerned nothing in particular,
instead of staying anchored near the name it actually annotates. A
`placeName` with no mapped-field descendant (its own text *is* the name, not
a child element) still falls back to `None`/`None` — nothing to anchor to,
not guessed.

**Reconciliation.** Comments are append-only on re-ingest, keyed by
`(entry_id, author, created_at, text)` — `text` is part of the key (not
just `entry_id`/`author`/`created_at`) because plain XML comments have no
real author/timestamp in the source (both constant placeholders), so two
different plain comments on the same entry would otherwise collide.
Note-links reuse `_reconcile_relations_multi` (one subject can reference
*several* objects, unlike `member_of`/`part_of`, which are genuinely 1:1
and use `_reconcile_relations`). Neither a comment nor a link
participates in `Entry.ingested_source_hash`/`_reconcile` — adding one must
never look like an edit to the entry's own fields, and `Entry.updated_at`
is untouched either way (verified by a dedicated test).

A link found inside `<note>` also gets a `models.MentionAnchor` — its exact
character span in the note's own flattened text (`ingest._note_link_offsets`,
`ingest._TextFlattener`) — upserted for *every* resolved link on *every*
ingest run, whether `_reconcile_relations_multi`
reports that link's relation as newly created or already unchanged. This is
deliberately unconditional rather than tracked: an unchanged record's note
is unchanged too, so recomputing the same offsets every run is cheap and
correct, and avoids needing separate "did the anchor change" bookkeeping.
See "Export" below for how this is *used* — self-validated lazily at read
time, never proactively invalidated on a curator's edit.

A link's target can be a **different `entry_type` in the same project** —
schleiermacher's person and place registers are two separate profiles
(`schleiermacher_persons`/`schleiermacher_places`), each ingested as its own
`_ingest_one` run with its own throwaway `id_by_xmlid`, so a person's note
mentioning a place (`placeName[@key="…"]`) is invisible to that run's own
lookup even though the place genuinely exists. Confirmed a large, real
category against the real corpus (~90% of otherwise-unresolved note-links
are exactly this, not a broken source reference). `ingest_comments_and_links`
falls back to `fetch_project_source_ids` — a query across every
`entry_type` in the project — only for keys the local `id_by_xmlid` misses,
so a run with nothing to resolve this way costs no extra query.

**Export.** `GET /{project}/export/{entry_type}` re-emits comments as
`oxy_comment_start`/`oxy_comment_end` PIs (`export._emit_comments`) and
`mentions` relations as `<persName key="…">`/`<placeName key="…">` spliced
into `<note>` (`export._emit_mentions`/`_splice_mention`):

- **Comments are an explicit, documented approximation** — exact character
  offsets aren't stored, only the field anchor. `start_field == end_field`
  brackets that field's own content (`export._wrap_field_content`: the PI
  pair becomes the field's first/last child, matching the dominant
  single-field-wrap shape); anything else (a span, or both `None`) is placed
  right after the `end_field` element if one was found, else right before
  `</note>` if the record has one, else right before `</person>`. Every
  comment re-emits in the oxy PI format regardless of its original style —
  a plain `<!-- -->` comment is *promoted*, not preserved as its own shape,
  since that's the richer format the external editing tool actually
  recognizes as reviewable. A field commonly carries more than one
  independent comment (several editors' remarks accumulated on the same
  `<note>` over time — a real, common corpus shape, confirmed against the
  real data via `roundtrip_report.py`); only the *first* comment for a given
  field brackets its content, since `_wrap_field_content` assumes a pristine
  target — a second call on an already-wrapped element would nest around
  the first comment's own PIs and reverse their order. Later comments for
  the same field are appended as a trailing pair inside it instead.
- **Links are exact when an anchor validates, best-effort search otherwise.**
  `ingest._note_link_offsets` records the exact character span
  (`start_offset`, `end_offset`) a `persName[@key]`/`placeName[@key]` note-link
  occupied in its record's flattened `note` text at ingest time, stored as a
  `models.MentionAnchor` row alongside the `mentions` relation. On export,
  `_emit_mentions` checks each anchor lazily: if `note[start:end]` still
  equals the `captured_text` stored at ingest time, `_splice_anchored_mentions`
  wraps that exact span — no searching, no ambiguity. This handles a case
  the search can't: two people sharing a surname written only once
  ("… Julius Gustav und der Dorothea Charolotte Alberti") — a search gives
  the shared substring to whichever mention comes first, while offsets know
  both positions independently. If
  the curator has edited that part of the note since ingest, the captured
  text no longer matches and the anchor is silently ignored — no
  edit-tracking is needed for this; it's a plain equality check done lazily
  at read time, not something kept in sync on write. Every anchor-validated
  mention is placed in one batched pass (`_splice_anchored_mentions`, applied
  before any fallback) so multiple mentions in one note don't corrupt each
  other's positions the way sequential search-and-splice calls would.

  A mention without a valid anchor (hand-created in the app, or the anchor
  didn't validate) falls back to
  `_splice_mention`'s search: the note's own flat text is searched for the
  target entry's name — natural reading order (`"<forename> <surname>"`,
  never the formatted `"Surname, Forename"` label, since that's not how prose
  is written), then bare surname/place name — wrapping the match in place
  when it's unique, and extending it over any immediately-following letters
  first (`_extend_match_end`) so a grammatically inflected form (German case
  endings — the target's registered surname `"Kant"` matching inside the
  note's own `"Kants"`) wraps the whole word instead of truncating
  mid-word. It falls back further, to appending a trailing `<persName
  key="…">`/`<placeName key="…">`, only when the name isn't found or occurs
  more than once — never guesses which occurrence.
- Comments/links are spliced in *after* `etree.indent()` runs, not during
  `build_record` — `etree.indent()` rewrites an element's `.text` the
  moment it gains a child (to insert pretty-printing whitespace), which
  would otherwise clobber the mixed text/PI/link content these two
  functions build.

`tests/test_export_comments.py` covers the placement rules directly (exact
search-based splice, no-match fallback, ambiguous-match fallback, the
word-boundary extension, the two comment positioning branches, and the
anchor-first branch — valid anchor, stale anchor, the shared-surname
collision resolved); `tests/test_note_link_offsets.py` covers
`_note_link_offsets`/`_TextFlattener` directly, including the two boundary
cases (a merged separator space landing inside a link's captured span on
either its leading or trailing side — see `_TextFlattener.mark`/`.tip`'s
docstrings for why two different accessors are needed, not one).
`tests/test_comments.py`'s
`test_export_round_trips_the_ingested_comment_and_note_link` and
`test_export_resolves_the_shared_surname_collision_via_stored_anchors` run
the full pipeline (real ingest → DB → `/export`) against real-shaped
fixtures, the latter confirming re-ingest idempotency for anchors too.

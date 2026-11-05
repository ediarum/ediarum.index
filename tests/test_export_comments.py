"""Comment + note-link re-emission in export.py — see export.build_record's
_emit_comments/_emit_mentions and the plan's Export section (link placement
via best-effort string match, comment placement via the (start_field,
end_field) anchor). Exercises export.py directly with hand-built entry
dicts, unlike the full-pipeline check in test_comments.py.
"""

from datetime import datetime

from lxml import etree

from ediarum_index import export

NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def _note(doc_xml: str):
    doc = etree.fromstring(doc_xml.encode(), etree.XMLParser(remove_pis=False))
    return doc.find(".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1']/tei:note", NS)


def _herz_and_wilhelm(note_text: str):
    return [
        {
            "id": 1, "source_id": "S1", "label": "Herz, Henriette", "entry_type": "person",
            "data": {"surname": "Herz", "forename": "Henriette", "note": note_text},
        },
        {
            "id": 2, "source_id": "S2", "label": "Wilhelm, Karl", "entry_type": "person",
            "data": {"surname": "Wilhelm", "forename": "Karl", "note": ""},
        },
    ]


def test_link_splices_in_place_on_a_unique_match():
    entries = _herz_and_wilhelm("Schwester von Karl Wilhelm.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document("schleiermacher", "person", entries, mentions=mentions)
    note = _note(xml)

    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert link.text == "Karl Wilhelm"
    assert note.text == "Schwester von "
    assert link.tail == "."


def test_link_falls_back_to_append_when_name_is_not_found():
    entries = _herz_and_wilhelm("No name mentioned here.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document("schleiermacher", "person", entries, mentions=mentions)
    note = _note(xml)

    assert note.text == "No name mentioned here."
    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert link.text == "Wilhelm, Karl"  # fell back to the target's own label
    assert list(note) == [link]  # appended as a trailing child, nothing spliced in place


def test_link_falls_back_to_append_when_the_name_occurs_twice():
    entries = _herz_and_wilhelm("Wilhelm traf Wilhelm im Salon.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document("schleiermacher", "person", entries, mentions=mentions)
    note = _note(xml)

    # never guesses which of the two occurrences is the real reference
    assert note.text == "Wilhelm traf Wilhelm im Salon."
    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert list(note) == [link]


def test_link_extends_to_the_full_inflected_word():
    """A German case ending (genitive -s) on the mentioned name must not
    truncate the splice — the target's registered surname is the bare stem
    ("Kant"), but the note writes it inflected ("Kants"); the whole word
    should be wrapped, not just the stem, leaving a stray "s" outside the
    tag (a real corpus case, not hypothetical)."""
    entries = [
        {
            "id": 1, "source_id": "S1", "label": "Test", "entry_type": "person",
            "data": {"surname": "Test", "forename": "A", "note": "Anhänger Kants, später Fichteaner"},
        },
        {
            "id": 2, "source_id": "S2", "label": "Kant, Immanuel", "entry_type": "person",
            "data": {"surname": "Kant", "forename": "Immanuel", "note": ""},
        },
    ]
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document("schleiermacher", "person", entries, mentions=mentions)
    note = _note(xml)

    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert link.text == "Kants"
    assert note.text == "Anhänger "
    assert link.tail == ", später Fichteaner"


def test_link_extension_stops_at_punctuation_and_does_not_overreach():
    """A match already ending at a real word boundary (punctuation, space)
    must not be extended — only immediately-following *letters* count."""
    entries = _herz_and_wilhelm("Freund von Karl Wilhelm.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document("schleiermacher", "person", entries, mentions=mentions)
    note = _note(xml)

    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert link.text == "Karl Wilhelm"
    assert link.tail == "."


# --- mention_anchors: exact offset-based splicing (models.MentionAnchor) ---


def test_anchor_splices_exactly_with_no_search_at_all():
    """A valid anchor places the link at its stored position directly —
    even a candidate string that would be ambiguous/non-unique for the
    search heuristic (see the shared-surname test below) is never
    consulted when a valid anchor exists."""
    entries = _herz_and_wilhelm("Schwester von Wilhelm, der Wilhelm gut kannte.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]
    text = "Schwester von Wilhelm, der Wilhelm gut kannte."
    start = text.index("Wilhelm")  # the *first* occurrence specifically
    end = start + len("Wilhelm")
    anchors = {(1, 2): {"start": start, "end": end, "text": "Wilhelm"}}

    xml = export.build_document(
        "schleiermacher", "person", entries, mentions=mentions, mention_anchors=anchors
    )
    note = _note(xml)
    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert note.text == "Schwester von "
    assert link.text == "Wilhelm"
    assert link.tail == ", der Wilhelm gut kannte."


def test_stale_anchor_falls_back_to_the_search_heuristic():
    """The note was edited since ingest — the anchor's captured_text no
    longer matches what's actually at [start:end] — so it's ignored and
    the existing search-based placement takes over, unchanged."""
    entries = _herz_and_wilhelm("A completely rewritten note about Karl Wilhelm now.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]
    # an anchor computed against the *old* note text, now nonsensical here
    anchors = {(1, 2): {"start": 0, "end": 7, "text": "Wilhelm"}}

    xml = export.build_document(
        "schleiermacher", "person", entries, mentions=mentions, mention_anchors=anchors
    )
    note = _note(xml)
    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert link.text == "Karl Wilhelm"  # found via search, not the stale offsets


def test_anchor_resolves_the_shared_surname_collision():
    """The real corpus bug this feature exists to fix: two people sharing
    a surname written once ("... Julius Gustav und der Dorothea Charolotte
    Alberti") — the search heuristic can only give the shared substring to
    whichever mention is processed first, losing the other's position
    entirely. Offsets know both positions independently."""
    note_text = "Tochter des Julius Gustav und der Dorothea Charolotte Alberti"
    entries = [
        {
            "id": 1, "source_id": "S1", "label": "Test", "entry_type": "person",
            "data": {"surname": "Test", "forename": "A", "note": note_text},
        },
        {
            "id": 2, "source_id": "S1058", "label": "Alberti, Dorothea Charolotte",
            "entry_type": "person",
            "data": {"surname": "Alberti", "forename": "Dorothea Charolotte", "note": ""},
        },
        {
            "id": 3, "source_id": "S1059", "label": "Alberti, Julius Gustav",
            "entry_type": "person",
            "data": {"surname": "Alberti", "forename": "Julius Gustav", "note": ""},
        },
    ]
    mentions = [
        {"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2},
        {"id": 2, "subject_id": 1, "predicate": "mentions", "object_id": 3},
    ]
    mother = "Dorothea Charolotte Alberti"
    father = "Julius Gustav"
    anchors = {
        (1, 2): {
            "start": note_text.index(mother), "end": note_text.index(mother) + len(mother),
            "text": mother,
        },
        (1, 3): {
            "start": note_text.index(father), "end": note_text.index(father) + len(father),
            "text": father,
        },
    }

    xml = export.build_document(
        "schleiermacher", "person", entries, mentions=mentions, mention_anchors=anchors
    )
    note = _note(xml)
    father_link = note.find("tei:persName[@key='S1059']", NS)
    mother_link = note.find("tei:persName[@key='S1058']", NS)
    assert father_link is not None and father_link.text == "Julius Gustav"
    assert mother_link is not None and mother_link.text == "Dorothea Charolotte Alberti"
    # both spliced in place — neither fell back to appending a synthetic label
    assert list(note) == [father_link, mother_link]


def test_no_anchor_for_a_mention_uses_the_existing_search_heuristic():
    """A mentions relation with no stored anchor at all (hand-created in
    the app, or ingested before this feature existed) behaves exactly as
    it always has."""
    entries = _herz_and_wilhelm("Schwester von Karl Wilhelm.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document("schleiermacher", "person", entries, mentions=mentions)
    note = _note(xml)
    link = note.find("tei:persName[@key='S2']", NS)
    assert link is not None
    assert link.text == "Karl Wilhelm"


def test_multiple_comments_on_the_same_field_stay_sequential_not_nested():
    """Several editors' remarks accumulated on the same field over time is a
    real, common corpus shape (see roundtrip_report.py's real-data findings)
    — only the first can bracket the field's own content (_wrap_field_content
    assumes a pristine target); later ones append as trailing pairs inside
    the same field instead of nesting/reversing around the first."""
    entries = [
        {
            "id": 1, "source_id": "S1", "label": "Test", "entry_type": "person",
            "data": {"surname": "Test", "forename": "A", "note": "AAA BBB CCC"},
        }
    ]
    comments = [
        {
            "entry_id": 1, "text": "first remark", "author": "wagner",
            "created_at": datetime(2019, 1, 1), "source": "ingested",
            "start_field": "note", "end_field": "note", "thread_meta": None,
        },
        {
            "entry_id": 1, "text": "second remark", "author": "holtz",
            "created_at": datetime(2020, 1, 1), "source": "ingested",
            "start_field": "note", "end_field": "note", "thread_meta": None,
        },
    ]

    xml = export.build_document("schleiermacher", "person", entries, comments=comments)
    doc = etree.fromstring(xml.encode(), etree.XMLParser(remove_pis=False))
    note = doc.find(".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1']/tei:note", NS)

    pis = [n for n in note.iter() if n.tag is etree.PI]
    assert [p.target for p in pis] == [
        "oxy_comment_start", "oxy_comment_end", "oxy_comment_start", "oxy_comment_end",
    ]
    # sequential document order, not nested/reversed around each other
    assert 'author="wagner"' in pis[0].text
    assert 'author="holtz"' in pis[2].text
    assert note.text is None  # pushed onto the first start PI's tail
    assert pis[0].tail == "AAA BBB CCC"


def test_comment_wraps_a_clean_single_field_anchor():
    entries = [
        {
            "id": 1, "source_id": "S1", "label": "Herz, Henriette", "entry_type": "person",
            "data": {"surname": "Herz", "forename": "Henriette", "note": ""},
        }
    ]
    comments = [
        {
            "entry_id": 1, "text": "Schreibweise unsicher", "author": "fkoch",
            "created_at": datetime(2024, 1, 24, 16, 29, 10),
            "source": "ingested", "start_field": "surname", "end_field": "surname",
            "thread_meta": None,
        }
    ]

    xml = export.build_document("schleiermacher", "person", entries, comments=comments)
    doc = etree.fromstring(xml.encode(), etree.XMLParser(remove_pis=False))
    surname = doc.find(
        ".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1']"
        "/tei:persName[@type='reg']/tei:surname",
        NS,
    )
    pis = [n for n in surname.iter() if n.tag is etree.PI]
    assert [p.target for p in pis] == ["oxy_comment_start", "oxy_comment_end"]
    assert 'author="fkoch"' in pis[0].text
    assert 'comment="Schreibweise unsicher"' in pis[0].text
    assert 'timestamp="20240124T162910"' in pis[0].text
    assert surname.text is None  # pushed onto the start PI's tail
    assert pis[0].tail == "Herz"


def test_comment_falls_back_to_after_end_field_when_fields_differ():
    entries = [
        {
            "id": 1, "source_id": "S1", "label": "Herz, Henriette", "entry_type": "person",
            "data": {"surname": "Herz", "forename": "Henriette", "note": "etwas Text"},
        }
    ]
    comments = [
        {
            "entry_id": 1, "text": "neu", "author": "fkoch",
            "created_at": datetime(2024, 1, 24, 16, 29, 10),
            "source": "ingested", "start_field": "surname", "end_field": "note",
            "thread_meta": None,
        }
    ]

    xml = export.build_document("schleiermacher", "person", entries, comments=comments)
    doc = etree.fromstring(xml.encode(), etree.XMLParser(remove_pis=False))
    person = doc.find(".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1']", NS)
    note = person.find("tei:note", NS)
    # placed right after the end_field (note) element, not inside it
    following_pis = [n for n in note.itersiblings() if n.tag is etree.PI]
    assert [p.target for p in following_pis] == ["oxy_comment_start", "oxy_comment_end"]


def _ehd_person_and_org(note_text: str):
    return [
        {
            "id": 1, "source_id": "S1", "label": "Baader, Franz", "entry_type": "person",
            "data": {"surname": "Baader", "forename": "Franz", "note": note_text},
        },
    ], [
        {
            "id": 2, "source_id": "H0000529", "label": "Bergakademie Freiberg",
            "entry_type": "organisation", "data": {"orgname": "Bergakademie Freiberg"},
        },
    ]


def test_an_anchored_organisation_mention_comes_back_as_org_name():
    note_text = "studierte an der Bergakademie Freiberg Bergbau"
    entries, targets = _ehd_person_and_org(note_text)
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]
    start = note_text.index("Bergakademie")
    anchors = {(1, 2): {"start": start, "end": start + 21, "text": "Bergakademie Freiberg"}}

    xml = export.build_document(
        "avhr", "person", entries, mentions=mentions, mention_targets=targets,
        mention_anchors=anchors,
    )
    note = _note(xml)
    link = note.find("tei:orgName[@key='H0000529']", NS)
    assert link is not None and link.text == "Bergakademie Freiberg"
    assert note.text == "studierte an der " and link.tail == " Bergbau"
    assert note.find("tei:persName", NS) is None


def test_an_organisation_mention_without_anchor_is_found_by_its_name():
    entries, targets = _ehd_person_and_org("studierte an der Bergakademie Freiberg.")
    mentions = [{"id": 1, "subject_id": 1, "predicate": "mentions", "object_id": 2}]

    xml = export.build_document(
        "avhr", "person", entries, mentions=mentions, mention_targets=targets
    )
    link = _note(xml).find("tei:orgName[@key='H0000529']", NS)
    assert link is not None and link.text == "Bergakademie Freiberg"
    assert link.tail == "."

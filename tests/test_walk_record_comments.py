"""ingest._walk_record_comments / _wrapper_field: the field-tracking walker
that anchors oxy_comment_start/end PIs (and persName[@key]/placeName[@key]
note-links) to roughly the field they were extracted near. No dedicated unit
coverage existed for this before — only indirect coverage via end-to-end
ingest fixtures (tests/test_comments.py) — so these are derived directly
from patterns confirmed in the real corpus (see docs/ingest/links-and-comments.md's
"Comments and note-links" section), not arbitrary made-up cases.
"""

from lxml import etree

from ediarum_index import ingest

_PARSER = etree.XMLParser(remove_pis=False, remove_comments=True)


def _person(xml: str):
    return etree.fromstring(
        f'<person xmlns="http://www.tei-c.org/ns/1.0" xml:id="S1">{xml}</person>'.encode(),
        _PARSER,
    )


def test_clean_single_field_wrap():
    person = _person(
        '<persName type="reg"><surname>'
        '<?oxy_comment_start author="x" comment="c"?>Meier<?oxy_comment_end?>'
        '</surname><forename>A</forename></persName>'
    )
    comments, links = ingest._walk_record_comments(person)
    assert len(comments) == 1
    assert comments[0]["start_field"] == "surname"
    assert comments[0]["end_field"] == "surname"
    assert links == []


def test_empty_position_marker_between_siblings_stays_unattached():
    """An empty pair sitting between two unrelated fields is a real,
    common shape (~20% of the corpus) — never guessed at, both null."""
    person = _person(
        '<sex value="male"/><?oxy_comment_start author="x" comment="c"?><?oxy_comment_end?><birth>1800</birth>'
    )
    comments, _links = ingest._walk_record_comments(person)
    assert len(comments) == 1
    assert comments[0]["start_field"] is None
    assert comments[0]["end_field"] is None


def test_cross_field_span():
    person = _person(
        '<persName type="reg"><surname>'
        '<?oxy_comment_start author="x" comment="neu"?>Preusse</surname>'
        '<forename>A</forename></persName>'
        "<note>Anmerkung<?oxy_comment_end?></note>"
    )
    comments, _links = ingest._walk_record_comments(person)
    assert len(comments) == 1
    assert comments[0]["start_field"] == "surname"
    assert comments[0]["end_field"] == "note"


def test_threaded_reply_preserves_thread_meta():
    person = _person(
        '<note><?oxy_comment_start author="a" comment="orig" id="c1"?>x'
        '<?oxy_comment_end?><?oxy_comment_start author="b" comment="reply" parentID="c1"?>y'
        "<?oxy_comment_end?></note>"
    )
    comments, _links = ingest._walk_record_comments(person)
    assert len(comments) == 2
    assert comments[0]["thread_meta"] == 'id="c1"'
    assert comments[1]["thread_meta"] == 'parentID="c1"'


def test_malformed_orphan_end_is_dropped_silently():
    person = _person("<note>x<?oxy_comment_end?>y</note>")
    comments, _links = ingest._walk_record_comments(person)
    assert comments == []


def test_malformed_unclosed_start_is_dropped_silently():
    person = _person('<note><?oxy_comment_start author="x" comment="c"?>x</note>')
    comments, _links = ingest._walk_record_comments(person)
    assert comments == []


def test_note_link_is_collected_with_its_field():
    person = _person('<note>x <persName key="S2">Someone</persName></note>')
    _comments, links = ingest._walk_record_comments(person)
    assert links == [{"key": "S2", "field": "note"}]


# --- _wrapper_field: comment brackets a whole persName/placeName element ----
#
# ~15% of the real corpus does this (see docs/ingest/links-and-comments.md) — the comment's
# PI boundary is a *sibling* of the wrapper (before/after it), never a
# descendant, so the ordinary field-propagation above never reaches it on
# its own; without _wrapper_field it falls all the way to (None, None) and
# gets exiled to the very end of the record on export.


def test_comment_wraps_whole_persname_falls_back_to_its_inner_field():
    person = _person(
        '<?oxy_comment_start author="sschmidt" comment="ob die Teil der Familie ist?"?>'
        '<persName type="reg"><surname>Ha(h)ne</surname><forename>Ernestine</forename></persName>'
        "<?oxy_comment_end?>"
        '<sex value="female"/>'
    )
    comments, _links = ingest._walk_record_comments(person)
    assert len(comments) == 1
    assert comments[0]["start_field"] == "surname"
    assert comments[0]["end_field"] == "surname"


def test_comment_wraps_whole_placename():
    person = _person(
        '<?oxy_comment_start author="x" comment="c"?>'
        '<placeName type="reg">Berlin</placeName>'
        "<?oxy_comment_end?>"
    )
    comments, _links = ingest._walk_record_comments(person)
    assert len(comments) == 1
    # placeName has no mapped-field descendant (its own text is the name,
    # not a <surname>-like child) — _wrapper_field finds nothing to fall
    # back to, so this stays unattached rather than guessing
    assert comments[0]["start_field"] is None
    assert comments[0]["end_field"] is None


def test_wrapper_fallback_does_not_override_an_already_known_field():
    """A comment genuinely anchored inside <note> must not be hijacked by
    _wrapper_field just because a persName happens to be its next/previous
    sibling within that same note (the note-link case, already handled on
    its own — see test_note_link_is_collected_with_its_field)."""
    person = _person(
        '<note><?oxy_comment_start author="x" comment="c"?>some text'
        '<persName key="S3">Someone</persName><?oxy_comment_end?></note>'
    )
    comments, links = ingest._walk_record_comments(person)
    assert comments[0]["start_field"] == "note"
    assert comments[0]["end_field"] == "note"
    assert links == [{"key": "S3", "field": "note"}]


def test_wrapper_fallback_only_applies_when_the_pi_directly_touches_the_wrapper():
    """An empty marker pair sitting between a closed persName and the next
    field must not accidentally inherit persName's field — getnext()/
    getprevious() land on the *other* PI (not a string tag), not on
    persName, so the (None, None) empty-marker behavior is preserved."""
    person = _person(
        '<persName type="reg"><surname>Meier</surname></persName>'
        '<?oxy_comment_start author="x" comment="c"?><?oxy_comment_end?>'
        "<birth>1800</birth>"
    )
    comments, _links = ingest._walk_record_comments(person)
    assert comments[0]["start_field"] is None
    assert comments[0]["end_field"] is None

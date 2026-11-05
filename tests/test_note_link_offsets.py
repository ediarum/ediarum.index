"""ingest._note_link_offsets / _TextFlattener — exact character offsets for
persName[@key]/placeName[@key] note-links, used to splice a mentions
relation back into <note> without export-time string-searching (see
export._splice_mention's anchor-first branch and docs/ingest/links-and-comments.md's
"Comments and note-links" section).

Each case asserts self-consistency (note[start:end] == the captured text)
plus the actual captured value — self-consistency alone wouldn't catch an
off-by-one that shifts both sides together, as it did during development
(see _TextFlattener.mark()/tip()'s docstrings for the two boundary bugs
found and fixed: a merged separator space landing inside the span on
either the leading or trailing side).
"""

from lxml import etree

from ediarum_index import ingest


def _note(inner: str):
    return etree.fromstring(f'<note xmlns="http://www.tei-c.org/ns/1.0">{inner}</note>'.encode())


def _check(inner: str, expected: dict[str, str]) -> dict[str, dict]:
    note = _note(inner)
    offsets = ingest._note_link_offsets(note)
    full = ingest._text(note)
    by_key = {o["key"]: o for o in offsets}
    for o in offsets:
        assert full[o["start"]:o["end"]] == o["text"]
    assert {k: o["text"] for k, o in by_key.items()} == expected
    return by_key


def test_no_note_returns_empty():
    assert ingest._note_link_offsets(None) == []


def test_note_with_no_links_returns_empty():
    assert ingest._note_link_offsets(_note("plain prose, nothing linked")) == []


def test_single_link_mid_sentence():
    """The exact shape that first surfaced an off-by-one: a link preceded
    by real prose with a separator space right before it — the space must
    land *before* the span, not be swallowed into it."""
    by_key = _check(
        'Kinder der <persName key="S2">Luise von Mühlenfels</persName>',
        {"S2": "Luise von Mühlenfels"},
    )
    assert by_key["S2"]["start"] == len("Kinder der ")


def test_trailing_whitespace_inside_link_does_not_leak_into_following_text():
    """Whitespace *inside* the link element, right before it closes, must
    not merge into a following sibling's text and get counted as part of
    the link's own span."""
    _check('<persName key="S1">Name  </persName>More', {"S1": "Name"})


def test_leading_whitespace_inside_link_is_stripped_like_text():
    """Leading whitespace inside the link (with nothing preceding it in
    the note at all) must not appear in the captured span, matching
    _text()'s own leading-whitespace stripping."""
    _check('<persName key="S1">  Name</persName>', {"S1": "Name"})


def test_multiple_links_each_get_their_own_correct_span():
    _check(
        'Bruder der <persName key="S1">Amalie Hahne</persName>; Schwester des '
        '<persName key="S2">Adolf Schwarz</persName>',
        {"S1": "Amalie Hahne", "S2": "Adolf Schwarz"},
    )


def test_irregular_whitespace_around_the_link():
    _check(
        'Text   before  \n  <persName key="S1">  Name  </persName>  \n after',
        {"S1": "Name"},
    )


def test_placename_as_the_first_child_with_no_preceding_text():
    _check('<placeName key="S3">Berlin</placeName>, wohnhaft', {"S3": "Berlin"})


def test_a_key_mentioned_twice_keeps_only_the_last_occurrence():
    """Matches _reconcile_relations_multi's one-row-per-(subject, object)
    shape — there's only ever one relation to anchor, so only the last
    span is worth keeping (not a documented "correct" choice among two
    equally-valid ones, just a deliberate, consistent one)."""
    note = _note(
        '<persName key="S1">Name</persName> traf später wieder '
        '<persName key="S1">Name</persName>'
    )
    offsets = ingest._note_link_offsets(note)
    assert len(offsets) == 1
    full = ingest._text(note)
    assert full[offsets[0]["start"]:offsets[0]["end"]] == "Name"
    assert offsets[0]["start"] > 0  # the *second* occurrence, not the first


def test_flattener_mark_and_tip_agree_with_text_for_a_real_multi_field_shape():
    """A closer-to-real record shape (name flanked by punctuation, not
    just prose words) — end-to-end sanity beyond the hand-picked cases
    above."""
    _check(
        'Vater der am 10. April 1831 getauften Emilie A. C. Ungerer, siehe '
        '<persName key="S9">Friedrich Schleiermacher</persName>.',
        {"S9": "Friedrich Schleiermacher"},
    )


def test_ref_is_separated_from_its_neighbours_but_not_from_punctuation():
    """The pretty-printed registers drop the space around a <ref>."""
    note = _note('Georges<ref target="x">Bd. 2</ref>, 86; siehe<ref target="y">Anm.</ref>im Text')
    assert ingest._text(note) == "Georges Bd. 2, 86; siehe Anm. im Text"


def test_link_offsets_stay_correct_after_a_ref_and_after_a_pi_tail():
    """Check that a ``<ref>`` or an ``oxy_comment`` PI before a link does not shift its offsets."""
    _check(
        'Siehe<ref target="x">Bd. 2</ref>und <persName key="S1">Kant</persName>',
        {"S1": "Kant"},
    )
    _check(
        'um 1795<?oxy_comment_start comment="x"?><?oxy_comment_end?>gegründet, <persName key="S2">Uhden</persName>',
        {"S2": "Uhden"},
    )


def test_org_name_link_is_recorded_like_a_person_or_place():
    """avhr's notes link institutions with ``orgName[@key]``."""
    _check(
        'Bergbau in <orgName key="H1">Freiberg</orgName>, später in <placeName key="H2">Wien</placeName>',
        {"H1": "Freiberg", "H2": "Wien"},
    )


def test_a_nested_record_keeps_its_own_links_and_comments():
    """A sub-place in a place's own ``listPlace`` is a record of its own — its
    links and comments must not be attributed to the place containing it."""
    place = etree.fromstring(
        b'<place xmlns="http://www.tei-c.org/ns/1.0">'
        b'<placeName type="reg">Altai</placeName>'
        b'<note>Gebirge in <placeName key="H1">Zentralasien</placeName></note>'
        b'<listPlace><place><placeName type="reg">Kolywan</placeName>'
        b'<note><?oxy_comment_start comment="x"?>bei <placeName key="H2">Barnaul</placeName>'
        b'<?oxy_comment_end?><!-- sub-place remark --></note></place></listPlace>'
        b'</place>'
    )
    comments, links = ingest._walk_record_comments(place)
    assert [link["key"] for link in links] == ["H1"]
    assert comments == []
    assert ingest._walk_record_xml_comments(place) == []

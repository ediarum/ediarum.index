"""xmldiff.xml_diff's PI-comparison behavior — oxy_comment_start/end PIs are
now part of the comparison (see xmldiff.py's module docstring and export.py's
comment re-emission), unlike plain <!-- --> comments, which stay stripped.
"""

from ediarum_index.xmldiff import canonicalize, xml_diff

_HEAD = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
    '<person xml:id="S1">'
    '<persName type="reg"><surname>Herz</surname><forename>Henriette</forename></persName>'
)
_TAIL = "</person></listPerson></body></text></TEI>"


def _doc(note_inner: str) -> str:
    return f"{_HEAD}<note>{note_inner}</note>{_TAIL}"


def test_equivalent_comments_diff_empty_despite_attr_order_and_serialization_quirks():
    """Attribute order, a dropped timezone offset (an accepted, permanent
    deviation — see ingest._parse_oxy_timestamp), and export's trailing-space
    empty-PI serialization quirk (<?oxy_comment_end ?> vs source's
    <?oxy_comment_end?>) must never show up as differences on their own."""
    src = _doc(
        '<?oxy_comment_start author="fkoch" timestamp="20240124T162910+0100" '
        'comment="Kinder der Luise"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?>'
    )
    exported = _doc(
        '<?oxy_comment_start timestamp="20240124T162910" comment="Kinder der Luise" '
        'author="fkoch"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end ?>'
    )
    assert xml_diff(src, exported) == ""


def test_different_comment_text_is_caught():
    src = _doc(
        '<?oxy_comment_start author="fkoch" timestamp="20240124T162910+0100" '
        'comment="Kinder der Luise"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?>'
    )
    exported = _doc(
        '<?oxy_comment_start author="fkoch" timestamp="20240124T162910" '
        'comment="Kinder der Emilie"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?>'
    )
    d = xml_diff(src, exported)
    assert d != ""
    assert "Luise" in d and "Emilie" in d


def test_a_dropped_comment_is_caught():
    src = _doc(
        '<?oxy_comment_start author="fkoch" timestamp="20240124T162910+0100" '
        'comment="Kinder der Luise"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?>'
    )
    exported = _doc('Kinder der <persName key="S2">Luise von Mühlenfels</persName>')
    assert xml_diff(src, exported) != ""


def test_plain_xml_comments_stay_ignored():
    """Unlike oxy PIs, a plain <!-- --> comment is never re-emitted as such
    (export.py always promotes it to an oxy PI) — so it must stay excluded
    from the comparison, or every promoted comment would show a spurious diff."""
    src = _doc("<!-- an editorial remark -->some text")
    exported = _doc("some text")
    assert xml_diff(src, exported) == ""


def test_pi_as_a_direct_child_of_person_stays_fully_multi_line():
    """A PI sitting as a direct child of <person> itself — not nested inside
    a prose field like <note> — is the real, common "empty position-marker
    between siblings" shape (~20% of the corpus, see docs/ingest/links-and-comments.md).
    etree.indent() already formats this correctly on its own; _fix_pi_indent
    must not touch it. Two earlier, broader versions of _fix_pi_indent both
    got this wrong (confirmed against a real mop record, see xmldiff.py's
    own docstring) — one collapsed the *entire* record onto a couple of
    lines, the other left just the immediately-following field (<birth>)
    stuck to the PI instead of on its own line."""
    xml = (
        '<person xmlns="http://www.tei-c.org/ns/1.0" oldID="x" xml:id="P1">'
        '<idno type="uri">http://d-nb.info/gnd/1</idno>'
        '<persName type="reg"><surname>Unzelmann</surname><forename>Karl</forename></persName>'
        '<?oxy_comment_start author="wagner" comment="unattached marker"?><?oxy_comment_end?>'
        "<birth>1753</birth><death>1832</death>"
        "<note>some note text</note>"
        "</person>"
    )
    lines = canonicalize(xml).splitlines()
    assert any(ln.strip().startswith("<idno") for ln in lines)
    assert any(ln.strip() == '<persName type="reg">' for ln in lines)
    assert any(ln.strip() == "<birth>1753</birth>" for ln in lines)
    assert any(ln.strip() == "<death>1832</death>" for ln in lines)
    assert any(ln.strip() == "<note>some note text</note>" for ln in lines)


def test_note_wrapping_comment_still_bracketed_correctly():
    """Regression check for the fix above: a comment genuinely wrapping a
    <note>'s own content (a prose field, not a structural container) must
    still bracket that content, not get pushed onto its own indented line
    with the prose split away from it."""
    src = _doc(
        '<?oxy_comment_start author="fkoch" timestamp="20240124T162910+0100" '
        'comment="Kinder der Luise"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?>'
    )
    canon = canonicalize(src)
    assert "Kinder der" in canon.replace("\n", " ")
    assert '<note><?oxy_comment_start' in canon.replace("\n", "").replace("  ", "")

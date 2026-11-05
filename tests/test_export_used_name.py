"""export._splice_inline_wrapped_value — schleiermacher's forename/used_name
("Rufname") re-emission. `<name type="used">` marks *which part* of
`<forename>` is the call name; the value itself is already fully captured
in `used_name` regardless of whether the wrapper is reconstructed, so this
is a best-effort search-and-splice (same philosophy as the original
_splice_mention, before exact offsets existed for links) — never anything
that needs a stored-offset fallback, since a missed guess here has no
correctness consequence, only a cosmetic one. See docs/ingest/schleiermacher.md's
"Comments and note-links" section is unrelated; this lives in the EXPORT
config's own docstring instead.
"""

from lxml import etree

from ediarum_index import export
from ediarum_index import ingest
from tests.test_ingest import _write_schleiermacher_fixture

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def _entry(forename: str, used_name: str, surname: str = "Test") -> dict:
    return {
        "id": 1, "source_id": "S1", "label": "Test", "entry_type": "person",
        "data": {"surname": surname, "forename": forename, "used_name": used_name, "note": ""},
    }


def _forename_xml(xml: str) -> str:
    return xml.replace("\n", "").replace("  ", "")


def test_unique_match_splices_the_call_name_wrapper():
    xml = export.build_document("schleiermacher", "person", [_entry("Karl Friedrich", "Friedrich")])
    assert '<forename>Karl <name type="used">Friedrich</name></forename>' in _forename_xml(xml)


def test_call_name_at_the_start_of_forename():
    xml = export.build_document("schleiermacher", "person", [_entry("Franz August", "Franz")])
    assert '<forename><name type="used">Franz</name> August</forename>' in _forename_xml(xml)


def test_call_name_with_a_parenthetical_nickname_alongside_it():
    xml = export.build_document(
        "schleiermacher", "person", [_entry("Friederike Henriette (Jette)", "Henriette")]
    )
    assert '<name type="used">Henriette</name>' in xml
    assert "(Jette)" in xml


def test_no_used_name_leaves_forename_as_plain_text():
    xml = export.build_document("schleiermacher", "person", [_entry("Karl Wilhelm", "")])
    assert "<forename>Karl Wilhelm</forename>" in _forename_xml(xml)
    assert "name type=" not in xml


def test_used_name_not_found_in_forename_leaves_it_plain():
    """A curator edited one of the two independently-editable fields
    without the other (see projects/schleiermacher/__init__.py) — no wrapper is
    guessed at; the value is still intact in used_name regardless."""
    xml = export.build_document("schleiermacher", "person", [_entry("Karl Wilhelm", "Ferdinand")])
    assert "<forename>Karl Wilhelm</forename>" in _forename_xml(xml)
    assert "name type=" not in xml


def test_ambiguous_match_leaves_forename_plain():
    """The call name occurs twice in forename — never guess which
    occurrence, same "don't guess" rule as _splice_mention's own
    ambiguous-match fallback."""
    xml = export.build_document(
        "schleiermacher", "person", [_entry("Friedrich Friedrich", "Friedrich")]
    )
    assert "<forename>Friedrich Friedrich</forename>" in _forename_xml(xml)
    assert "name type=" not in xml


def test_other_profiles_are_unaffected():
    """inline_wraps is opt-in per export config — a profile with no
    used_name-style field (or no `inline_wraps` entry at all) is
    completely untouched by this mechanism."""
    entry = {
        "id": 1, "source_id": "P1", "label": "Test", "entry_type": "person",
        "data": {"surname": "Test", "forename": "Karl Friedrich", "birth_date": "1800", "death_date": "1850"},
    }
    xml = export.build_document("leibniz5", "person", [entry])
    assert "<forename>Karl Friedrich</forename>" in _forename_xml(xml)
    assert "name type=" not in xml


def test_full_pipeline_ingest_then_export_reconstructs_the_wrapper(client, session, monkeypatch, tmp_path):
    """Real ingest -> DB -> /export, not export.py in isolation — confirms
    extract_schleiermacher_person's own captured used_name value actually
    round-trips through the whole stack, not just a hand-built dict."""
    source = _write_schleiermacher_fixture(
        tmp_path,
        '<person xml:id="S1">'
        '<persName type="reg"><surname>Schmidt</surname>'
        '<forename>Karl<name type="used">Friedrich</name></forename></persName>'
        "</person>",
    )
    assert ingest._ingest_one(session, "schleiermacher_persons", source) is True

    xml = client.get("/schleiermacher/export/person").text
    doc = etree.fromstring(xml.encode(), etree.XMLParser(remove_pis=False))
    s1 = doc.find(".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1']", TEI_NS)
    assert s1 is not None
    forename = s1.find("tei:persName[@type='reg']/tei:forename", TEI_NS)
    assert forename is not None
    used = forename.find("tei:name[@type='used']", TEI_NS)
    assert used is not None
    assert used.text == "Friedrich"
    assert used.tail is None
    assert forename.text == "Karl"

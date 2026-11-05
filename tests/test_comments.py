"""Comment lifecycle: POST / GET / DELETE on /{project}/comments.

Editorial remarks attached to one entry — see models.Comment. No dedicated
project of its own; the project is the commented-on entry's, same shape as
relations (test_relations.py).
"""

from datetime import datetime, timezone

from lxml import etree

from ediarum_index import ingest
from tests.conftest import TEST_EDITOR, user
from tests.test_ingest import _write_places_fixture, _write_schleiermacher_fixture

TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def _mk_entry(client, project, label, entry_type="person"):
    r = client.post(
        f"/{project}/entries",
        json={"entry_type": entry_type, "label": label, "data": {}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_read_defaults_to_app_source(client):
    entry = _mk_entry(client, "leibniz5", "A")
    r = client.post("/leibniz5/comments", json={"entry_id": entry["id"], "text": "looks wrong"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["entry_id"] == entry["id"]
    assert body["text"] == "looks wrong"
    assert body["source"] == "app"
    assert body["author"] == TEST_EDITOR  # the logged-in user's own identity, not claimed
    assert body["start_field"] is None and body["end_field"] is None

    got = client.get("/leibniz5/comments").json()
    assert len(got) == 1 and got[0]["id"] == body["id"]


def test_adding_a_comment_does_not_touch_the_entrys_updated_at(client):
    """A comment is not an edit to the entry's own fields — see
    models.Comment's docstring. Entry.updated_at must stay untouched."""
    entry = _mk_entry(client, "leibniz5", "A")
    before = client.get(f"/leibniz5/entries/{entry['id']}").json()["updated_at"]
    client.post("/leibniz5/comments", json={"entry_id": entry["id"], "text": "a remark"})
    after = client.get(f"/leibniz5/entries/{entry['id']}").json()["updated_at"]
    assert before == after


def test_field_anchor_round_trips(client):
    entry = _mk_entry(client, "leibniz5", "A")
    r = client.post(
        "/leibniz5/comments",
        json={"entry_id": entry["id"], "text": "neu", "start_field": "surname", "end_field": "note"},
    )
    assert r.json()["start_field"] == "surname"
    assert r.json()["end_field"] == "note"


def test_ingest_can_claim_a_different_author_and_timestamp(client, session):
    """Only an ingest write sets `source`, and with it claims its own
    author/created_at (see services.create_comment)."""
    entry = _mk_entry(client, "leibniz5", "A")
    ts = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
    body = ingest.create_comment(
        session, entry["id"], "Quelle: ...",
        source="ingested", author="wagner", created_at=ts, thread_meta='parentID="dnw_4fx_znb"',
    )
    assert body["source"] == "ingested"
    assert body["author"] == "wagner"
    assert body["created_at"].startswith("2020-01-01")


def test_the_api_cannot_claim_an_ingest(client):
    """POST /{project}/comments is always a hand-written comment."""
    entry = _mk_entry(client, "leibniz5", "A")
    r = client.post(
        "/leibniz5/comments",
        json={"entry_id": entry["id"], "text": "x", "source": "ingested", "author": "wagner"},
    )
    assert r.status_code == 201
    assert r.json()["source"] == "app"
    assert r.json()["author"] == TEST_EDITOR


def test_unknown_entry_is_404(client):
    r = client.post("/leibniz5/comments", json={"entry_id": 999999, "text": "x"})
    assert r.status_code == 404


def test_delete(client):
    entry = _mk_entry(client, "leibniz5", "A")
    created = client.post("/leibniz5/comments", json={"entry_id": entry["id"], "text": "x"}).json()
    assert client.delete(f"/leibniz5/comments/{created['id']}").json() == {"ok": True}
    assert client.get("/leibniz5/comments").json() == []
    assert client.delete(f"/leibniz5/comments/{created['id']}").status_code == 404


def test_read_unknown_project_is_404(client):
    assert client.get("/nope/comments").status_code == 404


def test_read_filters_by_entry_id(client):
    a = _mk_entry(client, "leibniz5", "A")
    b = _mk_entry(client, "leibniz5", "B")
    client.post("/leibniz5/comments", json={"entry_id": a["id"], "text": "about A"})
    client.post("/leibniz5/comments", json={"entry_id": b["id"], "text": "about B"})
    got = client.get("/leibniz5/comments", params={"entry_id": a["id"]}).json()
    assert len(got) == 1 and got[0]["text"] == "about A"


def test_user_without_the_project_can_neither_read_nor_write(client, as_caller):
    entry = _mk_entry(client, "leibniz5", "A")
    created = client.post("/leibniz5/comments", json={"entry_id": entry["id"], "text": "x"}).json()
    as_caller(user("mop"))
    assert client.get("/leibniz5/comments").status_code == 403
    assert client.post("/leibniz5/comments", json={"entry_id": entry["id"], "text": "x"}).status_code == 403
    assert client.delete(f"/leibniz5/comments/{created['id']}").status_code == 403


def test_comment_author_is_the_caller(client, as_caller):
    as_caller(user("leibniz5", name="ada@example.org"))
    entry = _mk_entry(client, "leibniz5", "A")
    r = client.post("/leibniz5/comments", json={"entry_id": entry["id"], "text": "x"})
    assert r.json()["author"] == "ada@example.org"


# --- ingest end-to-end: the real oxy_comment_start/end + note-link pipeline ----


def test_ingest_comments_and_note_links_end_to_end(client, session, monkeypatch, tmp_path):
    source = _write_schleiermacher_fixture(
        tmp_path,
        '<person xml:id="S1">'
        '<persName type="reg"><surname>Herz</surname><forename>Henriette</forename></persName>'
        '<note><?oxy_comment_start author="fkoch" timestamp="20240124T162910+0100" '
        'comment="Kinder der Luise"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?></note>'
        "</person>"
        '<person xml:id="S2">'
        '<persName type="reg"><surname>Mühlenfels</surname><forename>Luise von</forename></persName>'
        "</person>",
    )
    clean = ingest._ingest_one(session, "schleiermacher_persons", source)
    assert clean is True

    persons = {
        p["source_id"]: p["id"]
        for p in client.get(
            "/schleiermacher/entries", params={"entry_type": "person"}
        ).json()
    }
    s1_id = persons["S1"]

    comments = client.get(
        "/schleiermacher/comments", params={"entry_id": s1_id}
    ).json()
    assert len(comments) == 1
    assert comments[0]["source"] == "ingested"
    assert comments[0]["author"] == "fkoch"
    assert comments[0]["text"] == "Kinder der Luise"
    assert comments[0]["start_field"] == "note" and comments[0]["end_field"] == "note"

    mentions = client.get(
        "/schleiermacher/relations", params={"predicate": "mentions"}
    ).json()
    assert len(mentions) == 1
    assert mentions[0]["subject_id"] == s1_id
    assert mentions[0]["object_id"] == persons["S2"]

    # re-ingest with no source change: idempotent, no duplicate comment/relation
    clean2 = ingest._ingest_one(session, "schleiermacher_persons", source)
    assert clean2 is True
    assert (
        client.get("/schleiermacher/comments", params={"entry_id": s1_id}).json()
        == comments
    )
    assert (
        client.get(
            "/schleiermacher/relations", params={"predicate": "mentions"}
        ).json()
        == mentions
    )


def test_note_link_resolves_across_slugs_of_the_same_project(client, session, monkeypatch, tmp_path):
    """A person's note mentioning a *place* (placeName[@key]) can't resolve
    through schleiermacher_persons' own id_by_xmlid — the place lives in the
    separate schleiermacher_places profile/run. ingest_comments_and_links
    falls back to fetch_project_source_ids (a live query across the whole
    project) for exactly this — confirmed a large, real category against
    the real corpus (~90% of otherwise-unresolved note-links), not a
    hypothetical edge case."""
    places_source = _write_places_fixture(
        tmp_path, '<place xml:id="S0000065"><placeName type="reg">Berlin</placeName></place>'
    )
    assert ingest._ingest_one(session, "schleiermacher_places", places_source) is True

    persons_source = _write_schleiermacher_fixture(
        tmp_path,
        '<person xml:id="S0002119">'
        '<persName type="reg"><surname>Harrien</surname><forename>Wilhelmine</forename></persName>'
        '<note>Verlagsbuchhändler in <placeName key="S0000065">Berlin</placeName>, Ungersche '
        "Buchhandlung</note>"
        "</person>",
    )
    assert ingest._ingest_one(session, "schleiermacher_persons", persons_source) is True

    person = client.get(
        "/schleiermacher/entries", params={"entry_type": "person"}
    ).json()[0]
    place = client.get(
        "/schleiermacher/entries", params={"entry_type": "place"}
    ).json()[0]

    mentions = client.get(
        "/schleiermacher/relations", params={"predicate": "mentions"}
    ).json()
    assert len(mentions) == 1
    assert mentions[0]["subject_id"] == person["id"]
    assert mentions[0]["object_id"] == place["id"]

    # re-ingesting is still idempotent (fetch_project_source_ids doesn't
    # create a second lookup path that double-creates the relation)
    clean2 = ingest._ingest_one(session, "schleiermacher_persons", persons_source)
    assert clean2 is True
    assert (
        client.get(
            "/schleiermacher/relations", params={"predicate": "mentions"}
        ).json()
        == mentions
    )


def test_batch_resolves_cross_register_links_on_first_run(client, session, monkeypatch, tmp_path):
    """Persons ingested before places in one batch: the person's placeName link
    must still resolve on that first run, not only on a later re-ingest."""
    places_source = _write_places_fixture(
        tmp_path, '<place xml:id="S0000065"><placeName type="reg">Berlin</placeName></place>'
    )
    persons_source = _write_schleiermacher_fixture(
        tmp_path,
        '<person xml:id="S0002119">'
        '<persName type="reg"><surname>Harrien</surname><forename>Wilhelmine</forename></persName>'
        '<note>Verlagsbuchhändler in <placeName key="S0000065">Berlin</placeName></note>'
        "</person>",
    )
    monkeypatch.setitem(ingest.PROFILES["schleiermacher_persons"], "source", persons_source)
    monkeypatch.setitem(ingest.PROFILES["schleiermacher_places"], "source", places_source)

    assert ingest._ingest_profiles(
        session, ["schleiermacher_persons", "schleiermacher_places"], None, batch=True
    ) is True

    mentions = client.get(
        "/schleiermacher/relations", params={"predicate": "mentions"}
    ).json()
    assert len(mentions) == 1


def test_export_round_trips_the_ingested_comment_and_note_link(client, session, monkeypatch, tmp_path):
    """The full pipeline, not just export.py in isolation (see
    tests/test_export_comments.py for that): ingest a real fixture, then
    fetch /export and confirm the oxy PI pair and the persName[@key] link
    both come back — exactly, for this particular fixture (see the
    build_record trace in export.py's docstrings for why this shape is
    expected to match byte-for-byte, not just approximately)."""
    source = _write_schleiermacher_fixture(
        tmp_path,
        '<person xml:id="S1">'
        '<persName type="reg"><surname>Herz</surname><forename>Henriette</forename></persName>'
        '<note><?oxy_comment_start author="fkoch" timestamp="20240124T162910+0100" '
        'comment="Kinder der Luise"?>Kinder der '
        '<persName key="S2">Luise von Mühlenfels</persName><?oxy_comment_end?></note>'
        "</person>"
        '<person xml:id="S2">'
        '<persName type="reg"><surname>Mühlenfels</surname><forename>Luise von</forename></persName>'
        "</person>",
    )
    assert ingest._ingest_one(session, "schleiermacher_persons", source) is True

    xml = client.get("/schleiermacher/export/person").text
    doc = etree.fromstring(xml.encode(), etree.XMLParser(remove_pis=False))
    s1 = doc.find(".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1']", TEI_NS)
    assert s1 is not None
    note = s1.find("tei:note", TEI_NS)
    assert note is not None

    pis = [n for n in note.iter() if n.tag is etree.PI]
    starts = [p for p in pis if p.target == "oxy_comment_start"]
    ends = [p for p in pis if p.target == "oxy_comment_end"]
    assert len(starts) == 1 and len(ends) == 1
    assert 'author="fkoch"' in starts[0].text
    assert 'comment="Kinder der Luise"' in starts[0].text
    assert 'timestamp="20240124T162910"' in starts[0].text

    link = note.find("tei:persName[@key='S2']", TEI_NS)
    assert link is not None
    assert link.text == "Luise von Mühlenfels"

    # the PI pair really wraps the field's content, matching the source shape
    assert list(note) == [starts[0], link, ends[0]]
    assert starts[0].tail == "Kinder der "


def test_export_resolves_the_shared_surname_collision_via_stored_anchors(client, session, monkeypatch, tmp_path):
    """The real corpus bug models.MentionAnchor exists to fix: two people
    sharing a surname, written only once, mentioned in the same note.
    Without stored offsets, export's search heuristic can only give the
    shared substring to whichever mention it processes first, appending
    the other as a synthetic fallback with its position lost entirely.
    Full pipeline (real ingest -> DB -> /export), not export.py in
    isolation (see test_export_comments.py's version of this same case)."""
    source = _write_schleiermacher_fixture(
        tmp_path,
        '<person xml:id="S1060">'
        '<persName type="reg"><surname>Alberti</surname><forename>Dorothea Charolotte</forename></persName>'
        "</person>"
        '<person xml:id="S1059">'
        '<persName type="reg"><surname>Alberti</surname><forename>Julius Gustav</forename></persName>'
        "</person>"
        '<person xml:id="S1061">'
        '<persName type="reg"><surname>Hahne</surname><forename>Amalie</forename></persName>'
        '<note>Tochter des <persName key="S1059">Julius Gustav</persName> und der '
        '<persName key="S1060">Dorothea Charolotte Alberti</persName>, spätere verheiratete Reichardt</note>'
        "</person>",
    )
    assert ingest._ingest_one(session, "schleiermacher_persons", source) is True

    xml = client.get("/schleiermacher/export/person").text
    doc = etree.fromstring(xml.encode(), etree.XMLParser(remove_pis=False))
    child = doc.find(".//tei:person[@{http://www.w3.org/XML/1998/namespace}id='S1061']", TEI_NS)
    note = child.find("tei:note", TEI_NS)
    assert note is not None

    father = note.find("tei:persName[@key='S1059']", TEI_NS)
    mother = note.find("tei:persName[@key='S1060']", TEI_NS)
    assert father is not None and father.text == "Julius Gustav"
    assert mother is not None and mother.text == "Dorothea Charolotte Alberti"
    # both spliced in place, in document order — neither fell back to a
    # synthetic appended label
    assert list(note) == [father, mother]

    # re-ingesting is idempotent: same relations, same anchors, no errors
    clean2 = ingest._ingest_one(session, "schleiermacher_persons", source)
    assert clean2 is True
    xml2 = client.get("/schleiermacher/export/person").text
    assert xml2 == xml

"""ingest.py profiles: XPath extraction + alignment with the backend schema."""

import sys

import pytest
from lxml import etree

from ediarum_index import ingest
from ediarum_index.ingest import _reconcile


def _person(inner: str):
    doc = etree.fromstring(
        f'<listPerson xmlns="http://www.tei-c.org/ns/1.0">{inner}</listPerson>'
    )
    return doc[0]


def test_mop_scalars_and_repeatable_idno():
    rec = _person(
        '<person xml:id="P1" oldID="ediarum_njc_gls_x1b">'
        '<idno type="uri">http://d-nb.info/gnd/116001127</idno>'
        '<persName type="reg"><surname>Abeken</surname><forename>Heinrich</forename></persName>'
        "<birth>1809</birth><death>1872</death>"
        "<note>Legationsrat<?oxy_comment_start author='x'?> hier<?oxy_comment_end?></note>"
        "</person>"
    )
    e = ingest.extract(rec, ingest.PROFILES["mop"], "mop")
    assert e["source_id"] == "P1"
    assert e["label"] == "Abeken, Heinrich"  # "Surname, Forename"
    assert e["data"] == {
        "surname": "Abeken",
        "forename": "Heinrich",
        "birth_date": "1809",  # kept verbatim, no int coercion
        "death_date": "1872",
        # verbatim URI, kept with its @type — reversible for export
        "idno": [{"value": "http://d-nb.info/gnd/116001127", "type": "uri"}],
        "note": "Legationsrat hier",  # processing instruction dropped, text kept
        "old_id": "ediarum_njc_gls_x1b",  # legacy id carried through for round-trip
    }


def test_mop_captures_alternate_names():
    rec = _person(
        '<person xml:id="P1">'
        '<persName type="reg"><surname>Adlerberg</surname><forename>Amalie</forename></persName>'
        '<persName type="alt" subtype="pseudonym"><name>Krüdener, von</name></persName>'
        '<persName type="alt" subtype="birthname"><name>Stargard</name></persName>'
        '<persName type="alt"><surname>Adlerberg</surname><forename>Eduard Ferdinand</forename></persName>'
        "</person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["mop"], "mop")["data"]
    assert data["surname"] == "Adlerberg"  # the reg name is unaffected
    assert data["alt_names"] == [
        {"value": "Krüdener, von", "kind": "pseudonym"},
        {"value": "Stargard", "kind": "birthname"},
        {"surname": "Adlerberg", "forename": "Eduard Ferdinand"},  # split kept, no kind
    ]


def test_multiple_idno_are_all_kept():
    rec = _person(
        '<person xml:id="P2"><persName type="reg"><surname>X</surname></persName>'
        "<idno>345</idno><idno>123</idno></person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["leibniz5"], "leibniz5")["data"]
    assert data["idno"] == [{"value": "345"}, {"value": "123"}]  # no @type -> bare value


def test_label_is_surname_forename():
    def label(inner):
        return ingest.extract(_person(inner), ingest.PROFILES["mop"], "mop")["label"]

    both = '<persName type="reg"><surname>Leibniz</surname><forename>Gottfried Wilhelm</forename></persName>'
    assert label(f'<person xml:id="a">{both}</person>') == "Leibniz, Gottfried Wilhelm"
    assert label('<person xml:id="b"><persName type="reg"><surname>Brinck</surname></persName></person>') == "Brinck"
    assert label('<person xml:id="c"><persName type="reg"><forename>Aristoteles</forename></persName></person>') == "Aristoteles"
    # multilingual surname (pta) -> "German surname, German forename"
    e = ingest.extract(
        _person(
            '<person xml:id="d"><persName type="reg">'
            '<forename xml:lang="deu">Eunomius</forename>'
            '<surname xml:lang="eng">of Cyzicus</surname>'
            '<surname xml:lang="deu">von Kyzikos</surname>'
            "</persName></person>"
        ),
        ingest.PROFILES["pta"],
        "pta",
    )
    assert e["label"] == "von Kyzikos, Eunomius"


def test_mop_placeholder_dates_are_dropped():
    rec = _person(
        '<person xml:id="P9"><persName type="reg"><surname>X</surname></persName>'
        "<birth>*</birth><death>†</death></person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["mop"], "mop")["data"]
    assert "birth_date" not in data and "death_date" not in data


def test_mop_keeps_uncertain_date_strings():
    rec = _person(
        '<person xml:id="P8"><persName type="reg"><surname>X</surname></persName>'
        "<birth>nach 1824</birth><death>um 1890</death></person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["mop"], "mop")["data"]
    assert data["birth_date"] == "nach 1824"  # verbatim, sorting is derived
    assert data["death_date"] == "um 1890"


def test_pta_keeps_every_language_and_typed_id():
    rec = _person(
        '<person xml:id="PTA_P1">'
        '<idno type="GND">118557831</idno><idno type="WIKIDATA">Q43706</idno>'
        '<idno type="TLG">2062</idno>'
        '<persName type="reg">'
        '<forename xml:lang="eng">John</forename>'
        '<forename xml:lang="deu">Johannes</forename>'
        '<forename xml:lang="grc">Ἰωάννης</forename>'
        '<addName type="epithet" xml:lang="deu">Chrysostomos</addName>'
        "</persName>"
        '<floruit from="0381" notAfter="0407">381-407</floruit>'
        "</person>"
    )
    e = ingest.extract(rec, ingest.PROFILES["pta"], "pta")
    assert e["label"] == "Johannes"  # no surname -> forename only (German entry)
    assert e["data"]["forename"] == [
        {"value": "John", "lang": "eng"},
        {"value": "Johannes", "lang": "deu"},
        {"value": "Ἰωάννης", "lang": "grc"},
    ]
    assert e["data"]["epithet"] == [{"value": "Chrysostomos", "lang": "deu"}]
    assert e["data"]["idno"] == [
        {"value": "118557831", "type": "GND"},
        {"value": "Q43706", "type": "WIKIDATA"},
        {"value": "2062", "type": "TLG"},
    ]
    assert e["data"]["floruit"] == "381-407"
    assert "birth_date" not in e["data"]  # pta persons are dated by <floruit>


def test_profile_output_is_accepted_by_the_api(client):
    """Every key a profile emits must be valid for its project's schema."""
    for slug in ("leibniz5", "mop", "pta"):
        rec = _person(
            f'<person xml:id="{slug}_1">'
            '<idno type="uri">urn:x</idno>'
            '<persName type="reg"><surname>Test</surname><forename>T</forename></persName>'
            "<birth>1800</birth></person>"
        )
        payload = ingest.extract(rec, ingest.PROFILES[slug], slug)
        r = client.post(f"/{payload['project_name']}/entries", json=payload)
        assert r.status_code == 201, f"{slug}: {r.text}"
        got = client.get(f"/{payload['project_name']}/entries/{r.json()['id']}").json()
        assert got["data"]["idno"] == [{"value": "urn:x", "type": "uri"}]


# --- avhr: the profile with a custom extractor ---------------------------------


def test_ehd_full_record():
    rec = _person(
        '<person xml:id="H0012467" oldID="d41aae76" role="mythological" resp="#ck">'
        '<idno type="uri">http://d-nb.info/gnd/1047919613</idno>'
        '<idno type="uri">https://viaf.org/viaf/12345</idno>'
        '<idno type="uri">https://www.wikidata.org/wiki/Q5491953</idno>'
        '<persName type="reg"><surname>Abalos</surname><forename>José de</forename></persName>'
        '<persName type="alt"><surname>Avalos</surname><forename>José de</forename></persName>'
        '<persName type="alt" subtype="pseudonym"><name>Avalo</name></persName>'
        '<floruit notBefore="1700" notAfter="1800">18. Jh.</floruit>'
        '<sex value="male" evidence="internal"/>'
        '<note resp="#gk">Beamter für <placeName key="H0000494">Cuba</placeName>; '
        "später Venezuela</note>"
        '<linkGrp><ptr target="16#26" type="letter"/>'
        '<ptr target="19#159" type="page" subtype="comment"/></linkGrp>'
        "</person>"
    )
    e = ingest.extract(rec, ingest.PROFILES["avhr"], "avhr")
    assert e["source_id"] == "H0012467"
    assert e["label"] == "Abalos, José de"  # "Surname, Forename" — the source's order
    assert e["data"]["alt_names"] == [
        {"surname": "Avalos", "forename": "José de"},
        {"value": "Avalo", "kind": "pseudonym"},
    ]
    assert "internal_id" not in e["data"]  # the xml:id is the source_id
    assert e["data"]["old_id"] == "d41aae76"
    assert e["data"]["role"] == "mythological"
    assert e["data"]["resp"] == "#ck"
    assert e["data"]["gnd"] == "1047919613"
    assert e["data"]["viaf"] == "12345"
    assert e["data"]["wikidata"] == "Q5491953"
    assert e["data"]["idno_other"].count("; ") == 2  # lossless catch-all
    assert e["data"]["floruit"] == "18. Jh."
    assert e["data"]["floruit_notbefore"] == "1700"
    assert e["data"]["floruit_notafter"] == "1800"
    assert e["data"]["sex"] == "male"
    assert e["data"]["sex_evidence"] == "internal"
    assert e["data"]["note_resp"] == "#gk"
    # inline markup flattened without an added separator: "für Cuba;", not "für Cuba ;"
    assert e["data"]["note"] == "Beamter für Cuba; später Venezuela"
    assert e["data"]["references"] == "letter:16#26; page/comment:19#159"


def test_ehd_undivided_name_and_absent_fields():
    rec = _person(
        '<person xml:id="H1"><persName type="reg"><name>Abbas-Mirza</name></persName>'
        "</person>"
    )
    e = ingest.extract(rec, ingest.PROFILES["avhr"], "avhr")
    assert e["label"] == "Abbas-Mirza"
    assert e["data"]["name"] == "Abbas-Mirza"
    # empties are dropped rather than stored as ""
    for absent in ("surname", "forename", "floruit", "sex", "note", "references"):
        assert absent not in e["data"], absent


def test_ehd_persname_carrying_bare_text():
    """An lxml element without children is falsy — the childless <persName>
    must still be read, so the extractor tests `is not None`."""
    rec = _person('<person xml:id="H2"><persName type="reg">Anonymus</persName></person>')
    e = ingest.extract(rec, ingest.PROFILES["avhr"], "avhr")
    assert e["data"]["name"] == "Anonymus"
    assert e["label"] == "Anonymus"


def test_ehd_dates_stay_text():
    """birth/death are not coerced to int: a minority are free text."""
    rec = _person(
        '<person xml:id="H3"><persName type="reg"><surname>X</surname></persName>'
        "<birth>ca. 460 v. Chr.</birth><death>1778/1780</death></person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["avhr"], "avhr")["data"]
    assert data["birth_date"] == "ca. 460 v. Chr."
    assert data["death_date"] == "1778/1780"


def test_ehd_label_falls_back_to_xml_id():
    rec = _person('<person xml:id="H4"><note>kein Name</note></person>')
    assert ingest.extract(rec, ingest.PROFILES["avhr"], "avhr")["label"] == "H4"


def test_ehd_output_is_accepted_by_the_api(client):
    rec = _person(
        '<person xml:id="H5"><persName type="reg"><name>Solo</name></persName>'
        '<sex value="unknown"/><birth>ca. 1800</birth></person>'
    )
    payload = ingest.extract(rec, ingest.PROFILES["avhr"], "avhr")
    r = client.post(f"/{payload['project_name']}/entries", json=payload)
    assert r.status_code == 201, r.text


# --- mega / schleiermacher: shared _alt_names helper ----------------------------
# regression coverage for the surname/forename split that _alt_names used to
# collapse into a single joined string (376 real schleiermacher persons + 239
# real mega persons affected) — each item must keep its own shape, like mop's
# and avhr's alt_names, not get flattened to a display string.


def test_schleiermacher_alt_names_keep_surname_forename_split():
    rec = _person(
        '<person xml:id="S1">'
        '<persName type="reg"><surname>Schleiermacher</surname><forename>Friedrich</forename></persName>'
        '<persName type="alt"><surname>Schleyermacher</surname><forename>Fritz</forename></persName>'
        '<persName type="alt" subtype="birthname"><name>Schleyermacher</name></persName>'
        '<persName type="alt" subtype="pseudonym"><surname>X</surname><forename>Y</forename></persName>'
        "</person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["schleiermacher_persons"], "schleiermacher")["data"]
    assert data["alt_names"] == [{"surname": "Schleyermacher", "forename": "Fritz"}]
    assert data["birth_names"] == [{"value": "Schleyermacher"}]
    assert data["pseudonyms"] == [{"surname": "X", "forename": "Y"}]


def test_mega_alt_names_keep_surname_forename_split():
    rec = _person(
        '<person xml:id="M1">'
        '<persName type="reg"><surname>Marx</surname><forename>Karl</forename></persName>'
        '<persName type="alt"><surname>Mordechai</surname><forename>Karl</forename></persName>'
        '<persName type="alt" subtype="pseudonym"><name>Moor</name></persName>'
        "</person>"
    )
    data = ingest.extract(rec, ingest.PROFILES["mega"], "mega")["data"]
    assert data["alt_names"] == [{"surname": "Mordechai", "forename": "Karl"}]
    assert data["pseudonyms"] == [{"value": "Moor"}]
    assert "birth_names" not in data  # empty bucket dropped by extract()


# --- re-ingest reconciliation ---------------------------------------------------


def test_hash_data_is_stable_regardless_of_key_order():
    a = {"surname": "Leibniz", "forename": "G."}
    b = {"forename": "G.", "surname": "Leibniz"}
    assert ingest.hash_data(a) == ingest.hash_data(b)


def test_hash_data_changes_with_content():
    h1 = ingest.hash_data({"surname": "Leibniz"})
    h2 = ingest.hash_data({"surname": "Leibnitz"})
    assert h1 != h2


def test_reconcile_no_existing_entry_is_create():
    assert _reconcile(None, "hash1") == "create"


def test_reconcile_same_hash_is_unchanged():
    old = {"ingested_source_hash": "hash1", "updated_at": None, "ingested_at": None}
    assert _reconcile(old, "hash1") == "unchanged"


def test_reconcile_changed_hash_untouched_since_ingest_is_update():
    old = {
        "ingested_source_hash": "hash1",
        "ingested_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",  # same instant: the ingest write itself
    }
    assert _reconcile(old, "hash2") == "update"


def test_reconcile_changed_hash_edited_after_ingest_is_conflict():
    old = {
        "ingested_source_hash": "hash1",
        "ingested_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-02T00:00:00",  # a curator touched it after that ingest
    }
    assert _reconcile(old, "hash2") == "conflict"


def test_reconcile_changed_hash_never_ingested_before_is_update():
    # matched by source_id but has no prior ingest record (e.g. hand-entered) —
    # safe to claim it
    old = {"ingested_source_hash": None, "ingested_at": None, "updated_at": None}
    assert _reconcile(old, "hash1") == "update"


def test_reconciliation_end_to_end(client, session, monkeypatch):
    """create -> unchanged -> auto-update -> conflict after an app edit, using
    ingest.py's own HTTP helpers against the test API."""

    entry = {
        "project_name": "leibniz5", "entry_type": "person", "label": "Leibniz, G.",
        "source_id": "L1", "data": {"surname": "Leibniz", "forename": "G."},
    }
    entry["ingested_source_hash"] = ingest.hash_data(entry["data"])
    created = ingest.add_entry(session, entry)
    assert created["ingested_at"] is not None

    existing = ingest.fetch_existing(session, "leibniz5", "person")
    assert existing["L1"]["id"] == created["id"]
    assert _reconcile(existing["L1"], entry["ingested_source_hash"]) == "unchanged"

    # source changed, nobody touched the entry in the app -> safe auto-update
    entry["data"]["forename"] = "Gottfried"
    h2 = ingest.hash_data(entry["data"])
    assert _reconcile(existing["L1"], h2) == "update"
    entry["ingested_source_hash"] = h2
    updated = ingest.patch_entry(session, existing["L1"]["id"], entry)
    assert updated["data"]["forename"] == "Gottfried"

    # a curator edits it in the app...
    client.patch(f"/leibniz5/entries/{updated['id']}", json={"label": "Leibniz, Gottfried Wilhelm"})

    # ...then the source changes again -> conflict, must not be silently overwritten
    existing2 = ingest.fetch_existing(session, "leibniz5", "person")
    h3 = ingest.hash_data({"surname": "Leibniz", "forename": "Gottfried Wilhelm"})
    assert _reconcile(existing2["L1"], h3) == "conflict"


# --- --all --------------------------------------------------------------------


def _write_leibniz_fixture(tmp_path, n: int = 8) -> str:
    """``n`` synthetic leibniz5 persons — a small, in-repo stand-in for the
    real (gitignored, local-only) ``testdata/leibniz/...`` corpus, which
    ``_ingest_one`` falls back to for ``source=None`` and CI never has."""
    persons = "".join(
        f'<person xml:id="L{i}"><persName type="reg">'
        f"<surname>Person{i}</surname></persName></person>"
        for i in range(n)
    )
    path = tmp_path / "leibniz-fixture.xml"
    path.write_text(
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>{persons}'
        "</listPerson></body></text></TEI>",
        encoding="utf-8",
    )
    return str(path)


def test_ingest_one_end_to_end(client, session, monkeypatch, tmp_path):
    """`_ingest_one` end to end against a small synthetic leibniz5 fixture."""
    source = _write_leibniz_fixture(tmp_path)
    clean = ingest._ingest_one(session, "leibniz5", source)
    assert clean is True
    r = client.get("/leibniz5/entries")
    assert r.headers["X-Total-Count"] == "8"


def test_ingest_one_second_run_is_all_unchanged(client, session, monkeypatch, capsys, tmp_path):
    source = _write_leibniz_fixture(tmp_path)
    ingest._ingest_one(session, "leibniz5", source)
    capsys.readouterr()  # discard the first run's summary
    clean = ingest._ingest_one(session, "leibniz5", source)
    assert clean is True
    out = capsys.readouterr().out
    assert "0 created" in out and "8 unchanged" in out


def test_all_and_source_together_is_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["ingest.py", "--all", "--source", "foo/*.xml"])
    with pytest.raises(SystemExit) as exc:
        ingest.parse_args()
    assert exc.value.code == 2


# --- schleiermacher family groups -----------------------------------------------


def test_group_source_id_disambiguates_same_head_in_one_file():
    # the real, confirmed case: three distinct "Bülow" families in one file
    ids = {ingest._group_source_id("B.xml", "Bülow", i) for i in range(3)}
    assert len(ids) == 3
    # deterministic: same inputs -> same id
    assert ingest._group_source_id("B.xml", "Bülow", 0) == ingest._group_source_id("B.xml", "Bülow", 0)
    # different file, same head+ordinal -> different id
    assert ingest._group_source_id("B.xml", "Bülow", 0) != ingest._group_source_id("C.xml", "Bülow", 0)


def test_group_source_id_headless_groups_stay_distinct():
    ids = {ingest._group_source_id("Q.xml", "", i) for i in range(2)}
    assert len(ids) == 2
    # a headless group's id never collides with a headed one of the same file/ordinal
    assert ingest._group_source_id("Q.xml", "", 0) != ingest._group_source_id("Q.xml", "Quast", 0)


def _listperson(inner: str):
    return etree.fromstring(
        f'<listPerson xmlns="http://www.tei-c.org/ns/1.0">{inner}</listPerson>'
    )


def test_extract_groups_basic_shape():
    tree = _listperson(
        '<listPerson type="group"><head>Quast</head>'
        '<person xml:id="S1"/><person xml:id="S2"/>'
        "</listPerson>"
        '<listPerson type="group">'  # headless
        '<person xml:id="S3"/>'
        "</listPerson>"
    ).getroottree()
    groups = ingest._extract_groups(tree, "Q.xml")
    assert len(groups) == 2
    headed, headless = groups
    assert headed["label"] == "Quast"
    assert headed["member_xmlids"] == ["S1", "S2"]
    assert headless["label"] == ""
    assert headless["member_xmlids"] == ["S3"]
    assert headed["source_id"] != headless["source_id"]


def test_extract_groups_skips_empty_group():
    tree = _listperson('<listPerson type="group"><head>Empty</head></listPerson>').getroottree()
    assert ingest._extract_groups(tree, "E.xml") == []


def _write_schleiermacher_fixture(tmp_path, xml: str) -> str:
    path = tmp_path / "fixture.xml"
    path.write_text(
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>{xml}'
        "</listPerson></body></text></TEI>",
        encoding="utf-8",
    )
    return str(path)


def test_ingest_schleiermacher_groups_end_to_end(client, session, monkeypatch, tmp_path):
    source = _write_schleiermacher_fixture(
        tmp_path,
        '<listPerson type="group"><head>Testfam</head>'
        '<person xml:id="S1"><persName type="reg"><surname>A</surname></persName></person>'
        '<person xml:id="S2"><persName type="reg"><surname>B</surname></persName></person>'
        "</listPerson>"
        '<person xml:id="S3"><persName type="reg"><surname>C</surname></persName></person>',  # ungrouped
    )
    clean = ingest._ingest_one(session, "schleiermacher_persons", source)
    assert clean is True

    families = client.get(
        "/schleiermacher/entries", params={"entry_type": "group"}
    ).json()
    assert len(families) == 1 and families[0]["label"] == "Testfam"
    fam_id = families[0]["id"]

    relations = client.get(
        "/schleiermacher/relations", params={"predicate": "member_of"}
    ).json()
    assert {r["object_id"] for r in relations} == {fam_id}
    persons = {
        p["source_id"]: p["id"]
        for p in client.get(
            "/schleiermacher/entries", params={"entry_type": "person"}
        ).json()
    }
    assert {r["subject_id"] for r in relations} == {persons["S1"], persons["S2"]}
    assert persons["S3"] not in {r["subject_id"] for r in relations}  # never grouped

    # re-running unchanged: no new families, no new/changed relations
    clean2 = ingest._ingest_one(session, "schleiermacher_persons", source)
    assert clean2 is True
    assert client.get(
        "/schleiermacher/entries", params={"entry_type": "group"}
    ).json() == families
    assert client.get(
        "/schleiermacher/relations", params={"predicate": "member_of"}
    ).json() == relations


def test_ingest_schleiermacher_person_moved_to_different_family(client, session, monkeypatch, tmp_path):
    """A person's group membership changes between runs (source edited): the
    stale relation is replaced, not duplicated, and neither family entry is
    touched — only membership changed, not either family's own identity."""
    fixture_path = tmp_path / "fixture.xml"

    fixture_path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
        '<listPerson type="group"><head>Alpha</head>'
        '<person xml:id="S1"><persName type="reg"><surname>A</surname></persName></person>'
        "</listPerson>"
        "</listPerson></body></text></TEI>",
        encoding="utf-8",
    )
    ingest._ingest_one(session, "schleiermacher_persons", str(fixture_path))
    families_v1 = client.get(
        "/schleiermacher/entries", params={"entry_type": "group"}
    ).json()
    assert len(families_v1) == 1

    # same file (same filename, so Beta's source_id can't collide with Alpha's
    # only by chance) is edited: S1 moves from Alpha to a new group, Beta
    fixture_path.write_text(
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>'
        '<listPerson type="group"><head>Beta</head>'
        '<person xml:id="S1"><persName type="reg"><surname>A</surname></persName></person>'
        "</listPerson>"
        "</listPerson></body></text></TEI>",
        encoding="utf-8",
    )
    clean = ingest._ingest_one(session, "schleiermacher_persons", str(fixture_path))
    assert clean is True

    families_v2 = {
        f["label"]: f for f in client.get(
            "/schleiermacher/entries", params={"entry_type": "group"}
        ).json()
    }
    assert set(families_v2) == {"Alpha", "Beta"}  # Alpha untouched, Beta newly created

    relations = client.get(
        "/schleiermacher/relations", params={"predicate": "member_of"}
    ).json()
    assert len(relations) == 1  # S1's old Alpha membership replaced, not duplicated
    assert relations[0]["object_id"] == families_v2["Beta"]["id"]


# --- schleiermacher places: a second register in the same project -------------


def _place(inner: str):
    doc = etree.fromstring(
        f'<listPlace xmlns="http://www.tei-c.org/ns/1.0">{inner}</listPlace>'
    )
    return doc[0]


def test_schleiermacher_profiles_write_into_the_schleiermacher_project():
    # the profile keys name the registers; the project is schleiermacher's own
    assert ingest.project_of("schleiermacher_places") == "schleiermacher"
    assert ingest.project_of("schleiermacher_persons") == "schleiermacher"
    assert ingest.project_of("mop") == "mop"


def test_schleiermacher_place_full_record():
    rec = _place(
        '<place xml:id="S0172863" type="building">'
        '<idno type="uri">https://www.geonames.org/3092197</idno>'
        '<placeName type="reg">Massow</placeName>'
        '<placeName type="alt">Maszewo </placeName>'
        '<placeName type="alt">Massow in Pommern</placeName>'
        # the real register has two places with an empty <note/> before the real one
        "<note/>"
        '<note>Stadt bei <placeName key="S0000285">Stargard</placeName>, '
        'Wirkungsort von <persName key="S0003672">X</persName></note>'
        # sub-places are records of their own, not part of this one
        '<listPlace><place xml:id="S2"><placeName type="reg">Kirche</placeName></place></listPlace>'
        "</place>"
    )
    e = ingest.extract(rec, ingest.PROFILES["schleiermacher_places"], "schleiermacher")
    assert e["project_name"] == "schleiermacher"
    assert e["entry_type"] == "place"
    assert e["label"] == "Massow"
    assert e["source_id"] == "S0172863"
    assert e["data"] == {
        "placename": "Massow",
        "alt_names": [{"value": "Maszewo"}, {"value": "Massow in Pommern"}],
        "place_type": "building",
        # markup flattened; the empty first <note/> doesn't swallow the real one
        "note": "Stadt bei Stargard, Wirkungsort von X",
        # the whole URI, not a bare number, and no idno_other beside it:
        # _split_idnos routes each <idno> into exactly one of the two
        "geonames": "https://www.geonames.org/3092197",
    }


def test_schleiermacher_place_minimal_record_drops_empty_values():
    rec = _place('<place xml:id="S1"><placeName type="reg">Aachen</placeName></place>')
    data = ingest.extract(rec, ingest.PROFILES["schleiermacher_places"], "schleiermacher")["data"]
    assert data == {"placename": "Aachen"}


def test_schleiermacher_place_non_geonames_idno_kept_verbatim():
    # one real record has "Gneisenau" as its <idno>: it carries no
    # geonames.org, so it stays in idno_other and `geonames` is left unset
    rec = _place(
        '<place xml:id="S1732567"><idno type="uri">Gneisenau</idno>'
        '<placeName type="reg">Gneisenau</placeName></place>'
    )
    data = ingest.extract(rec, ingest.PROFILES["schleiermacher_places"], "schleiermacher")["data"]
    assert data["idno_other"] == "Gneisenau"
    assert "geonames" not in data


def test_schleiermacher_place_output_is_accepted_by_the_api(client):
    rec = _place(
        '<place xml:id="S1" type="district">'
        '<idno type="uri">http://www.geonames.org/2950159</idno>'
        '<placeName type="reg">Berlin</placeName><placeName type="alt">Cölln</placeName>'
        "<note>Residenzstadt</note></place>"
    )
    payload = ingest.extract(rec, ingest.PROFILES["schleiermacher_places"], "schleiermacher")
    r = client.post(f"/{payload['project_name']}/entries", json=payload)
    assert r.status_code == 201, r.text
    got = client.get(f"/{payload['project_name']}/entries/{r.json()['id']}").json()
    assert got["data"]["alt_names"] == [{"value": "Cölln"}]
    # http:// is kept as written — nothing is canonicalised to https://
    assert got["data"]["geonames"] == "http://www.geonames.org/2950159"


def test_extract_place_nesting_records_immediate_parent_only():
    tree = etree.fromstring(
        '<listPlace xmlns="http://www.tei-c.org/ns/1.0">'
        '<place xml:id="P1"><placeName type="reg">Paris</placeName><listPlace>'
        '<place xml:id="P2"><placeName type="reg">Oper</placeName><listPlace>'
        '<place xml:id="P3"><placeName type="reg">Place de Louis XV.</placeName></place>'
        "</listPlace></place>"
        "</listPlace></place>"
        '<place xml:id="P4"><placeName type="reg">Rom</placeName></place>'
        "</listPlace>"
    ).getroottree()
    assert ingest._extract_place_nesting(tree) == {"P2": "P1", "P3": "P2"}


def _write_places_fixture(tmp_path, xml: str) -> str:
    path = tmp_path / "Orte.xml"
    path.write_text(
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPlace>{xml}'
        "</listPlace></body></text></TEI>",
        encoding="utf-8",
    )
    return str(path)


def _part_of(client) -> dict[str, str]:
    """``{child source_id: parent source_id}`` as currently stored."""
    by_id = {
        p["id"]: p["source_id"]
        for p in client.get(
            "/schleiermacher/entries", params={"entry_type": "place"}
        ).json()
    }
    return {
        by_id[r["subject_id"]]: by_id[r["object_id"]]
        for r in client.get(
            "/schleiermacher/relations", params={"predicate": "part_of"}
        ).json()
    }


def test_ingest_schleiermacher_place_nesting_end_to_end(client, session, monkeypatch, tmp_path):
    source = _write_places_fixture(
        tmp_path,
        '<place xml:id="P1"><placeName type="reg">Berlin</placeName><listPlace>'
        '<place xml:id="P2" type="building"><placeName type="reg">Dom</placeName></place>'
        '<place xml:id="P3" type="street"><placeName type="reg">Unter den Linden</placeName></place>'
        "</listPlace></place>"
        '<place xml:id="P4"><placeName type="reg">Halle</placeName></place>',
    )
    assert ingest._ingest_one(session, "schleiermacher_places", source) is True

    places = client.get(
        "/schleiermacher/entries", params={"entry_type": "place"}
    ).json()
    assert {p["source_id"] for p in places} == {"P1", "P2", "P3", "P4"}  # sub-places too
    assert _part_of(client) == {"P2": "P1", "P3": "P1"}
    relations = client.get(
        "/schleiermacher/relations", params={"predicate": "part_of"}
    ).json()

    # re-running unchanged: no new entries, no new/changed relations
    assert ingest._ingest_one(session, "schleiermacher_places", source) is True
    assert client.get(
        "/schleiermacher/entries", params={"entry_type": "place"}
    ).json() == places
    assert client.get(
        "/schleiermacher/relations", params={"predicate": "part_of"}
    ).json() == relations


def test_ingest_schleiermacher_place_moved_and_promoted(client, session, monkeypatch, tmp_path):
    """Between runs, one sub-place moves under a different parent and another
    becomes a top-level place: the stale relations are replaced/removed, not
    duplicated, and no place entry is deleted."""
    source = _write_places_fixture(
        tmp_path,
        '<place xml:id="P1"><placeName type="reg">Berlin</placeName><listPlace>'
        '<place xml:id="P2"><placeName type="reg">Dom</placeName></place>'
        '<place xml:id="P3"><placeName type="reg">Tor</placeName></place>'
        "</listPlace></place>"
        '<place xml:id="P4"><placeName type="reg">Halle</placeName></place>',
    )
    ingest._ingest_one(session, "schleiermacher_places", source)
    assert _part_of(client) == {"P2": "P1", "P3": "P1"}

    _write_places_fixture(
        tmp_path,
        '<place xml:id="P1"><placeName type="reg">Berlin</placeName></place>'
        '<place xml:id="P3"><placeName type="reg">Tor</placeName></place>'
        '<place xml:id="P4"><placeName type="reg">Halle</placeName><listPlace>'
        '<place xml:id="P2"><placeName type="reg">Dom</placeName></place>'
        "</listPlace></place>",
    )
    assert ingest._ingest_one(session, "schleiermacher_places", source) is True
    assert _part_of(client) == {"P2": "P4"}
    places = client.get(
        "/schleiermacher/entries", params={"entry_type": "place"}
    ).json()
    assert len(places) == 4


def test_places_and_persons_of_one_project_reconcile_independently(client, session, monkeypatch, tmp_path):
    """Two profiles, one project: ingesting the place register must neither see
    the person register's entries as its own nor touch its member_of relations."""
    persons = _write_schleiermacher_fixture(
        tmp_path,
        '<listPerson type="group"><head>Testfam</head>'
        '<person xml:id="S1"><persName type="reg"><surname>A</surname></persName></person>'
        "</listPerson>",
    )
    assert ingest._ingest_one(session, "schleiermacher_persons", persons) is True
    places = _write_places_fixture(
        tmp_path,
        '<place xml:id="P1"><placeName type="reg">Berlin</placeName><listPlace>'
        '<place xml:id="P2"><placeName type="reg">Dom</placeName></place>'
        "</listPlace></place>",
    )
    assert ingest._ingest_one(session, "schleiermacher_places", places) is True

    member_of = client.get(
        "/schleiermacher/relations", params={"predicate": "member_of"}
    ).json()
    assert len(member_of) == 1
    assert _part_of(client) == {"P2": "P1"}
    # and back again: re-ingesting persons leaves the place nesting alone
    assert ingest._ingest_one(session, "schleiermacher_persons", persons) is True
    assert _part_of(client) == {"P2": "P1"}


def test_schleiermacher_bible_book():
    """Check a bible book's fields, canon part and synthetic ``source_id``.

    The canon part comes from the ``list[@type]`` above the item, the
    ``source_id`` from the register-wide ``@n`` (the items have no ``xml:id``),
    and the empty ``name2`` label is dropped.
    """
    tree = etree.fromstring(
        f'<TEI xmlns="{ingest.TEI}"><text><body><list>'
        '<list type="NT"><label>Neues Testament</label><list>'
        '<item n="42"><idno>Röm</idno><label unit="name">Römer</label>'
        '<label unit="abk">Röm.</label><label unit="name2"/>'
        '<label unit="gruppea">Briefe</label><label unit="gruppeb">Paulusbriefe</label>'
        "</item></list></list></list></body></text></TEI>"
    )
    profile = ingest.PROFILES["schleiermacher_bible_books"]
    [rec] = tree.xpath(profile["record_xpath"], namespaces=ingest.NS)
    e = ingest.extract(rec, profile, "schleiermacher")
    assert e["entry_type"] == "bible_book"
    assert e["label"] == "Römer"
    assert e["source_id"] == "bibelsystematik:42"
    assert e["data"] == {
        "name": "Römer",
        "sigle": "Röm",
        "abbr": "Röm.",
        "canon_part": "NT",
        "position": 42,
        "group_a": "Briefe",
        "group_b": "Paulusbriefe",
    }


def _first(profile_key, xml):
    """Run ``ingest.extract`` on the single record of a profile in a TEI snippet.

    Args:
        profile_key: Key into ``ingest.PROFILES``, e.g. ``"schleiermacher_bible_books"``.
        xml: TEI fragment placed inside ``TEI/text/body``. Must contain exactly
            one record matching the profile's ``record_xpath``.

    Returns:
        The payload dict from ``ingest.extract``: ``project_name``, ``entry_type``,
        ``label``, ``source_id`` and ``data``.

    Raises:
        ValueError: If the XPath matches zero or several records.
    """
    profile = ingest.PROFILES[profile_key]
    tree = etree.fromstring(f'<TEI xmlns="{ingest.TEI}"><text><body>{xml}</body></text></TEI>')
    [rec] = tree.xpath(profile["record_xpath"], namespaces=ingest.NS)
    return ingest.extract(rec, profile, "schleiermacher")


def test_schleiermacher_organisation():
    """Check an organisation's names and ``desc``.

    The ``persName`` inside the ``desc`` is flattened to plain text.
    """
    e = _first(
        "schleiermacher_organisations",
        '<listOrg><listOrg><head>Akademie</head>'
        '<org xml:id="S1"><orgName type="reg">Akademie, Klasse</orgName>'
        '<orgName type="alt">Klasse</orgName><desc>mit <persName key="S2">Uhden</persName></desc>'
        "</org></listOrg></listOrg>",
    )
    assert e["entry_type"] == "organisation"
    assert e["source_id"] == "S1"
    assert e["data"] == {
        "orgname": "Akademie, Klasse",
        "alt_names": [{"value": "Klasse"}],
        "description": "mit Uhden",
    }


def test_schleiermacher_glossary():
    """Check a glossary item's term, language, ``@resp`` attributes, note and source.

    The ``note`` and its ``p[@type='source']`` are split into two fields.
    """
    e = _first(
        "schleiermacher_glossary",
        '<list><item xml:id="S9"><label type="reg" xml:lang="deu">Katechisation</label>'
        '<label type="alt">Unterricht</label><desc resp="#DS"/>'
        '<note resp="FS"><p>Text <persName key="S3">Wedel</persName>.</p>'
        '<p type="source">Archiv</p></note><interp id="#instrument"/></item></list>',
    )
    assert e["entry_type"] == "glossary"
    assert e["label"] == "Katechisation"
    assert e["data"] == {
        "term": "Katechisation",
        "term_lang": "deu",
        "alt_names": [{"value": "Unterricht"}],
        "desc_resp": "#DS",
        "note": "Text Wedel.",
        "note_resp": "FS",
        "source": "Archiv",
        "category": "instrument",
    }


def test_schleiermacher_work():
    """Check a work's title, structured authors/editors and place key.

    The ``bibl`` nested in the ``title`` is part of the title. An author with
    nothing in it becomes ``{"unknown": True}``, so the element still comes back
    on export.
    """
    e = _first(
        "schleiermacher_works",
        '<listBibl><listBibl type="group"><head>Schiller, Friedrich</head>'
        '<bibl xml:id="S1" type="journal"><author role="translation"><persName key="S2">'
        "<surname>Schiller</surname><forename>Friedrich</forename></persName></author>"
        "<author><persName><surname/><forename/></persName></author>"
        "<editor><persName><name>et al.</name></persName></editor>"
        '<title> Iphigenie <bibl sameAs="S9">in Aulis</bibl></title>'
        '<pubPlace key="S3">Berlin</pubPlace><date>(1815)</date>'
        '<note>bei <placeName key="S3">Berlin</placeName></note></bibl></listBibl></listBibl>',
    )
    assert e["entry_type"] == "work"
    assert e["label"] == "Iphigenie in Aulis"
    assert e["source_id"] == "S1"
    assert e["data"] == {
        "title": "Iphigenie in Aulis",
        "work_type": "journal",
        "authors": [
            {"surname": "Schiller", "forename": "Friedrich", "key": "S2", "role": "translation"},
            {"unknown": True},
        ],
        "editors": [{"name": "et al."}],
        "pub_place": "Berlin",
        "pub_place_key": "S3",
        "date": "(1815)",
        "note": "bei Berlin",
    }


def test_schleiermacher_work_record_xpath_skips_the_bibl_inside_a_title():
    """Check that the works' ``record_xpath`` matches only the outer ``bibl``.

    A ``bibl`` nested in a ``title`` is part of that work, not a record of its own.
    """
    profile = ingest.PROFILES["schleiermacher_works"]
    tree = etree.fromstring(
        f'<TEI xmlns="{ingest.TEI}"><text><body><listBibl><bibl xml:id="S1"><title>A <bibl sameAs="S0">b</bibl></title>'
        "</bibl></listBibl></body></text></TEI>"
    )
    assert len(tree.xpath(profile["record_xpath"], namespaces=ingest.NS)) == 1


def test_a_record_that_breaks_the_schema_fails_alone_not_the_run(client, session, monkeypatch, tmp_path, capsys):
    """A drifted field name fails that record (reported), never the whole run."""
    source = _write_leibniz_fixture(tmp_path)
    original = ingest.extract

    def drifted(record, profile, project):
        entry = original(record, profile, project)
        if entry["source_id"] == "L1":
            entry["data"]["sruname"] = "typo"
        return entry

    monkeypatch.setattr(ingest, "extract", drifted)
    assert ingest._ingest_one(session, "leibniz5", source) is False
    out = capsys.readouterr().out
    assert "1 failed" in out and "sruname" in out
    assert client.get("/leibniz5/entries").headers["X-Total-Count"] == "7"  # the other records went in

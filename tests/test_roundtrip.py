"""Round-trip: ingest a sample -> build the export XML -> diff the two.

The `xml_diff` fixture (see conftest.py) ignores whitespace, comments and PIs, so
a non-empty diff is a real structural / content difference. Fixtures written in
each profile's export order round-trip to an empty diff; the last test shows what
a human-readable deviation report looks like.
"""

from lxml import etree

from ediarum_index import export
from ediarum_index import ingest

XMLID = "{http://www.w3.org/XML/1998/namespace}id"


def _ingest_then_export(slug: str, sample_xml: str) -> tuple[str, str]:
    profile = ingest.PROFILES[slug]
    src = etree.fromstring(
        sample_xml.encode(),
        etree.XMLParser(remove_pis=True, remove_comments=True),
    )
    records = src.xpath(profile["record_xpath"], namespaces=ingest.NS)
    project = ingest.project_of(slug)
    entries = [ingest.extract(r, profile, project) for r in records]
    exported = export.build_document(project, profile["entry_type"], entries)
    return sample_xml, exported


_LEIBNIZ = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <person xml:id="L1000002">
    <idno type="uri">https://d-nb.info/gnd/118958461</idno>
    <persName type="reg"><surname>Eckhart</surname><forename>Johann Georg</forename></persName>
    <birth>1674</birth>
    <death>1730</death>
  </person>
</listPerson></body></text></TEI>
"""

_MOP = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <person oldID="ediarum_njc_gls_x1b" xml:id="P0004638">
    <idno type="uri">http://d-nb.info/gnd/116001127</idno>
    <persName type="reg"><surname>Abeken</surname><forename>Heinrich</forename></persName>
    <birth>1809</birth>
    <death>1872</death>
    <note>evangelischer Theologe und preußischer Legationsrat</note>
  </person>
  <person oldID="ediarum_x_y_z" xml:id="P0011126">
    <persName type="reg"><surname>Adlerberg</surname><forename>Amalie</forename></persName>
    <persName type="alt" subtype="pseudonym"><name>Krüdener, von</name></persName>
    <persName type="alt"><surname>Adlerberg</surname><forename>Eduard Ferdinand Woldemar</forename></persName>
    <persName type="alt"><name>Adlerberg-Krüdener</name></persName>
    <birth>1808</birth>
    <death>1888</death>
  </person>
</listPerson></body></text></TEI>
"""

_PTA = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <person xml:id="PTA_P00001">
    <idno type="GND">118557831</idno>
    <idno type="TLG">2062</idno>
    <persName>
      <forename xml:lang="deu">Johannes</forename>
      <forename xml:lang="grc">Ἰωάννης</forename>
      <addName type="epithet" xml:lang="deu">Chrysostomos</addName>
    </persName>
    <floruit>381-407</floruit>
    <note>Bischof von Konstantinopel</note>
  </person>
</listPerson></body></text></TEI>
"""

_EHD = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <person xml:id="H0006528" oldID="g40d9cd3-f8d1-40b8-a357-7c74fb90a5fa" role="mythological"
          resp="TK" duplicate="H0000001">
    <idno type="uri">http://d-nb.info/gnd/118635794</idno>
    <idno type="uri">https://www.wikidata.org/wiki/Q8577</idno>
    <persName type="reg"><surname>Thales</surname><forename>von Milet</forename></persName>
    <persName type="alt" subtype="pseudonym"><name>Thales Milesius</name></persName>
    <persName type="alt"><surname>Milet</surname><forename>Thales von</forename></persName>
    <birth>ca. 624 v. Chr.</birth>
    <death>ca. 546 v. Chr.</death>
    <floruit notBefore="-0600" notAfter="-0550">6. Jh. v. Chr.</floruit>
    <sex value="male" evidence="selfIdentification"/>
    <note resp="TK">altgriechischer Philosoph</note>
    <linkGrp>
      <ptr target="33#58" type="page"/>
      <ptr subtype="comment" target="04#12" type="letter"/>
    </linkGrp>
  </person>
  <person xml:id="H0006529">
    <persName type="reg"><name>Euklid</name></persName>
  </person>
  <person xml:id="H0006530">
    <persName type="reg"><surname>Lehmann</surname></persName>
    <floruit notBefore="1853" notAfter="1853"/>
  </person>
</listPerson></body></text></TEI>
"""

_SCHLEIERMACHER = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <person xml:id="S0010005" role="mythological">
    <idno type="uri">http://d-nb.info/gnd/118607626</idno>
    <persName type="reg"><surname>Schleiermacher</surname><forename>Friedrich Daniel Ernst</forename></persName>
    <persName type="alt" subtype="birthname"><name>Schleyermacher</name></persName>
    <sex value="male" evidence="assigned" resp="#fko" cert="high"/>
    <birth>21. November 1768 (Breslau)</birth>
    <death>6. Februar 1834</death>
    <event type="wedding" when="1809-05-18"><note>zweite Ehe</note></event>
    <note>evangelischer Theologe und Philosoph</note>
  </person>
  <person xml:id="S0020001">
    <persName type="reg"><name>Anonyma</name></persName>
    <persName type="alt" subtype="pseudonym"><name>X.</name></persName>
  </person>
  <person xml:id="S0030002">
    <persName type="reg"><surname>Herz</surname><forename>Henriette</forename></persName>
    <persName type="alt"><surname>Lemos</surname><forename>Henriette de</forename></persName>
  </person>
</listPerson></body></text></TEI>
"""


def test_leibniz_roundtrips_clean(xml_diff):
    ing, exp = _ingest_then_export("leibniz5", _LEIBNIZ)
    diff = xml_diff(ing, exp, subtree=".//tei:listPerson")
    assert diff == "", "\n" + diff


def test_mop_roundtrips_clean(xml_diff):
    ing, exp = _ingest_then_export("mop", _MOP)
    diff = xml_diff(ing, exp, subtree=".//tei:listPerson")
    assert diff == "", "\n" + diff


def test_pta_multilingual_roundtrips_clean(xml_diff):
    ing, exp = _ingest_then_export("pta", _PTA)
    diff = xml_diff(ing, exp, subtree=".//tei:listPerson")
    assert diff == "", "\n" + diff


def test_ehd_roundtrips_clean(xml_diff):
    ing, exp = _ingest_then_export("avhr", _EHD)
    diff = xml_diff(ing, exp, subtree=".//tei:listPerson")
    assert diff == "", "\n" + diff


def test_schleiermacher_roundtrips_clean(xml_diff):
    # one alt-name variant per person, not three on one — see the "Current
    # deviations" note in docs/ingest/schleiermacher.md: birth_names/pseudonyms/alt_names come back
    # grouped by bucket, not interleaved in source order, on a person that has
    # more than one variant
    ing, exp = _ingest_then_export("schleiermacher_persons", _SCHLEIERMACHER)
    diff = xml_diff(ing, exp, subtree=".//tei:listPerson")
    assert diff == "", "\n" + diff


_SCHLEIERMACHER_GROUPS = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <listPerson type="group">
    <person xml:id="S0200001"><persName type="reg"><surname>Unbekannt</surname></persName></person>
  </listPerson>
  <listPerson type="group">
    <head>Bülow</head>
    <person xml:id="S0100001"><persName type="reg"><surname>Bülow</surname><forename>Anna</forename></persName></person>
    <person xml:id="S0100002"><persName type="reg"><surname>Bülow</surname><forename>Otto</forename></persName></person>
  </listPerson>
  <person xml:id="S0300001"><persName type="reg"><surname>Solo</surname></persName></person>
</listPerson></body></text></TEI>
"""


def test_schleiermacher_groups_roundtrip_clean(xml_diff):
    """A headed group (>=2 members) and a headless group (1 member), plus one
    ungrouped person — export.build_document's grouping branch is the inverse
    of ingest.ingest_schleiermacher_groups, simulated here without a live DB:
    fake sequential entry ids stand in for what create_entry would assign.
    Document order here already matches export's alphabetical-by-label
    ordering (the headless family's empty label sorts first, then "Bülow",
    then "Solo") — same reason the plain _SCHLEIERMACHER fixture above keeps
    one alt-name variant per person: sidestepping an already-documented,
    already-accepted ordering deviation rather than re-demonstrating it here."""
    profile = ingest.PROFILES["schleiermacher_persons"]
    src = etree.fromstring(
        _SCHLEIERMACHER_GROUPS.encode(),
        etree.XMLParser(remove_pis=True, remove_comments=True),
    )
    groups = ingest._extract_groups(src.getroottree(), "TESTGROUPS.xml")

    persons = src.xpath(profile["record_xpath"], namespaces=ingest.NS)
    entries = [ingest.extract(r, profile, "schleiermacher") for r in persons]
    for i, e in enumerate(entries, start=1):
        e["id"] = i
    id_by_xmlid = {e["source_id"]: e["id"] for e in entries}

    families, memberships = [], []
    for i, group in enumerate(groups, start=1000):
        families.append({"id": i, "label": group["label"]})
        for xid in group["member_xmlids"]:
            memberships.append({"subject_id": id_by_xmlid[xid], "object_id": i})

    exported = export.build_document(
        "schleiermacher", "person", entries, families=families, memberships=memberships
    )
    diff = xml_diff(_SCHLEIERMACHER_GROUPS, exported, subtree=".//tei:listPerson")
    assert diff == "", "\n" + diff


# in export order: idno, placeName[reg], placeName[alt]…, note, then the nested
# listPlace; siblings sorted by label at every level (Aachen < Berlin; Dom < Oper
# < Unter den Linden) — the source's own order, as in the real Orte.xml
_SCHLEIERMACHER_PLACES = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPlace>
  <place xml:id="S0000001">
    <idno type="uri">http://www.geonames.org/3247449</idno>
    <placeName type="reg">Aachen</placeName>
  </place>
  <place xml:id="S0000100">
    <idno type="uri">https://www.geonames.org/2950159</idno>
    <placeName type="reg">Berlin</placeName>
    <placeName type="alt">Cölln</placeName>
    <placeName type="alt">Berlin-Cölln</placeName>
    <note>Residenzstadt</note>
    <listPlace>
      <place xml:id="S0000101" type="building">
        <placeName type="reg">Dom</placeName>
      </place>
      <place xml:id="S0000102" type="building">
        <placeName type="reg">Oper</placeName>
        <listPlace>
          <place xml:id="S0000103" type="others">
            <placeName type="reg">Opernplatz</placeName>
          </place>
        </listPlace>
      </place>
      <place xml:id="S0000104" type="street">
        <placeName type="reg">Unter den Linden</placeName>
        <note>Prachtstraße</note>
      </place>
    </listPlace>
  </place>
</listPlace></body></text></TEI>
"""


def _places_ingest_then_export(sample_xml: str) -> str:
    """ingest.extract + the nesting pass, simulated without a live DB — fake
    sequential entry ids stand in for what create_entry would assign, same as
    test_schleiermacher_groups_roundtrip_clean."""
    profile = ingest.PROFILES["schleiermacher_places"]
    src = etree.fromstring(sample_xml.encode(), etree.XMLParser(remove_comments=True))
    records = src.xpath(profile["record_xpath"], namespaces=ingest.NS)
    entries = [ingest.extract(r, profile, "schleiermacher") for r in records]
    for i, e in enumerate(entries, start=1):
        e["id"] = i
    id_by_xmlid = {e["source_id"]: e["id"] for e in entries}
    parents = [
        {"subject_id": id_by_xmlid[child], "object_id": id_by_xmlid[parent]}
        for child, parent in ingest._extract_place_nesting(src.getroottree()).items()
    ]
    return export.build_document("schleiermacher", "place", entries, parents=parents)


def test_schleiermacher_places_roundtrip_clean(xml_diff):
    exported = _places_ingest_then_export(_SCHLEIERMACHER_PLACES)
    diff = xml_diff(_SCHLEIERMACHER_PLACES, exported, subtree=".//tei:listPlace")
    assert diff == "", "\n" + diff


# the register spells the same GeoNames address 76 different ways; `geonames`
# stores each URI whole rather than a bare number precisely so that none of
# them is rewritten on the way back out
_SCHLEIERMACHER_PLACE_URI_FORMS = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPlace>
  <place xml:id="S0000001">
    <idno type="uri">http://www.geonames.org/2743977</idno>
    <placeName type="reg">Aachen</placeName>
  </place>
  <place xml:id="S0000002">
    <idno type="uri">https://www.geonames.org/2812482/halle.html</idno>
    <placeName type="reg">Halle</placeName>
  </place>
  <place xml:id="S0000003">
    <idno type="uri">Gneisenau</idno>
    <placeName type="reg">Gneisenau</placeName>
  </place>
</listPlace></body></text></TEI>
"""


def test_schleiermacher_place_idno_spellings_survive_verbatim(xml_diff):
    """http://, a slug suffix and a non-URI <idno> all come back unchanged."""
    exported = _places_ingest_then_export(_SCHLEIERMACHER_PLACE_URI_FORMS)
    diff = xml_diff(
        _SCHLEIERMACHER_PLACE_URI_FORMS, exported, subtree=".//tei:listPlace"
    )
    assert diff == "", "\n" + diff


def test_schleiermacher_places_without_relations_come_back_flat():
    """No part_of relations (e.g. a hand-entered register) -> the flat path:
    every place at the top level, none dropped."""
    profile = ingest.PROFILES["schleiermacher_places"]
    src = etree.fromstring(_SCHLEIERMACHER_PLACES.encode())
    entries = [
        ingest.extract(r, profile, "schleiermacher")
        for r in src.xpath(profile["record_xpath"], namespaces=ingest.NS)
    ]
    doc = etree.fromstring(export.build_document("schleiermacher", "place", entries).encode())
    top = doc.xpath("/tei:TEI/tei:text/tei:body/tei:listPlace/tei:place", namespaces=ingest.NS)
    assert len(top) == 6


def test_schleiermacher_places_nesting_cycle_drops_nothing():
    """A part_of cycle (only possible through a bad hand edit) must not make
    both ends silently vanish from the export."""
    entries = [
        {"id": 1, "label": "A", "source_id": "A", "data": {"placename": "A"}},
        {"id": 2, "label": "B", "source_id": "B", "data": {"placename": "B"}},
    ]
    cycle = [{"subject_id": 1, "object_id": 2}, {"subject_id": 2, "object_id": 1}]
    doc = etree.fromstring(
        export.build_document("schleiermacher", "place", entries, parents=cycle).encode()
    )
    ids = [p.get(XMLID) for p in doc.xpath("//tei:place", namespaces=ingest.NS)]
    assert sorted(ids) == ["A", "B"]


def test_export_config_is_per_project_and_entry_type():
    # one project, two registers: each entry type resolves to its own config
    assert export.export_config("schleiermacher", "person")["record"] == "person"
    assert export.export_config("schleiermacher", "place")["record"] == "place"
    assert export.export_config("schleiermacher", "group") is None
    # the profile key is not a project
    assert export.export_config("schleiermacher_places", "place") is None


def test_diff_reports_dropped_elements(xml_diff):
    """A source with content ingest doesn't capture -> a readable diff, not a
    silent loss. Empty <forename/> / <nameLink/> and a comment are dropped."""
    lossy = """
    <TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
      <person xml:id="L1">
        <persName type="reg"><surname>Brinck</surname><forename/><nameLink/></persName>
        <!-- unsicher -->
        <birth/><death/>
      </person>
    </listPerson></body></text></TEI>
    """
    ing, exp = _ingest_then_export("leibniz5", lossy)
    diff = xml_diff(ing, exp, subtree=".//tei:listPerson")
    assert diff != ""
    assert "nameLink" in diff  # the dropped element is visible in the report
    assert "<birth/>" in diff


# --- the endpoint --------------------------------------------------------------

def _post(client, **kw):
    body = {"entry_type": "person", "data": {}, **kw}
    r = client.post("/leibniz5/entries", json=body)
    assert r.status_code == 201, r.text


def test_export_endpoint(client):
    _post(client, label="Zed", source_id="Z1", data={"surname": "Zed"})
    _post(
        client,
        label="Abel",
        source_id="A1",
        data={"surname": "Abel", "idno": [{"value": "https://d-nb.info/gnd/1", "type": "uri"}]},
    )

    r = client.get("/leibniz5/export/person")
    assert r.status_code == 200
    assert "xml" in r.headers["content-type"]

    doc = etree.fromstring(r.content)
    persons = doc.xpath("//tei:person", namespaces=ingest.NS)
    assert [p.get(XMLID) for p in persons] == ["A1", "Z1"]  # ordered by label
    assert doc.xpath("//tei:idno/text()", namespaces=ingest.NS) == ["https://d-nb.info/gnd/1"]
    assert doc.xpath("//tei:idno/@type", namespaces=ingest.NS) == ["uri"]


def test_export_endpoint_reconstructs_schleiermacher_group(client):
    """First real coverage of services.export_document's grouping path — every
    earlier grouping test called export.build_document directly. Confirms
    the route's families/memberships queries (parameterized off
    EXPORT["schleiermacher_persons"]["groups"], not hardcoded) actually work end to
    end, and that a project with no `groups` config (leibniz5, exercised by
    test_export_endpoint above) is unaffected."""
    a = client.post(
        "/schleiermacher/entries",
        json={
            "entry_type": "person", "label": "A",
            "source_id": "S1", "data": {"surname": "A"},
        },
    ).json()
    b = client.post(
        "/schleiermacher/entries",
        json={
            "entry_type": "person", "label": "B",
            "source_id": "S2", "data": {"surname": "B"},
        },
    ).json()
    group = client.post(
        "/schleiermacher/entries",
        json={
            "entry_type": "group", "label": "Testfam",
            "source_id": "G1", "data": {},
        },
    ).json()
    for person in (a, b):
        r = client.post(
            "/schleiermacher/relations",
            json={"subject_id": person["id"], "predicate": "member_of", "object_id": group["id"]},
        )
        assert r.status_code == 201, r.text

    r = client.get("/schleiermacher/export/person")
    assert r.status_code == 200
    doc = etree.fromstring(r.content)
    groups = doc.xpath("//tei:listPerson[@type='group']", namespaces=ingest.NS)
    assert len(groups) == 1
    assert groups[0].findtext("tei:head", namespaces=ingest.NS) == "Testfam"
    members = {p.get(XMLID) for p in groups[0].findall("tei:person", namespaces=ingest.NS)}
    assert members == {"S1", "S2"}


def test_export_endpoint_reconstructs_schleiermacher_place_nesting(client):
    """services.export_document's nesting path end to end: the part_of query is
    parameterized off the place config's "nesting", and the same project's
    person export is unaffected by it."""
    def post(label, source_id, **data):
        r = client.post(
        "/schleiermacher/entries",
        json={
                "entry_type": "place", "label": label,
                "source_id": source_id, "data": {"placename": label, **data},
            },
        )
        assert r.status_code == 201, r.text
        return r.json()

    berlin = post("Berlin", "S1")
    dom = post("Dom", "S2", place_type="building")
    post("Aachen", "S3")
    r = client.post(
        "/schleiermacher/relations", json={"subject_id": dom["id"], "predicate": "part_of", "object_id": berlin["id"]}
    )
    assert r.status_code == 201, r.text

    r = client.get("/schleiermacher/export/place")
    assert r.status_code == 200
    doc = etree.fromstring(r.content)
    top = doc.xpath("/tei:TEI/tei:text/tei:body/tei:listPlace/tei:place", namespaces=ingest.NS)
    assert [p.get(XMLID) for p in top] == ["S3", "S1"]  # by label; Dom not at top level
    nested = top[1].xpath("tei:listPlace/tei:place", namespaces=ingest.NS)
    assert [p.get(XMLID) for p in nested] == ["S2"]
    assert nested[0].get("type") == "building"

    # the person register of the same project still exports on its own
    assert client.get("/schleiermacher/export/person").status_code == 200


def test_export_unknown_project_is_404(client):
    assert client.get("/nope/export/person").status_code == 404


def test_export_no_profile_is_404(client):
    # 'place' has no export profile for leibniz5
    assert client.get("/leibniz5/export/place").status_code == 404


def test_export_config_mirrors_ingest_profile():
    for slug, cfg in export.EXPORT.items():
        profile = ingest.PROFILES[slug]
        # same register on both sides: same project, same entry type
        assert cfg.get("project", slug) == ingest.project_of(slug), slug
        assert cfg["entry_type"] == profile["entry_type"], slug
        assert set(cfg["order"]) <= set(cfg["emit"]), slug
        if "fields" not in profile:
            continue  # a custom `extract` profile (e.g. avhr) has no field map to mirror
        assert set(cfg["emit"]) == set(profile["fields"]), slug
        # attribute channel: ingest {attr: key} must reverse export {key: attr}
        ingest_attrs = profile.get("attrs", {})
        export_attrs = cfg.get("attrs", {})
        assert {v: k for k, v in ingest_attrs.items()} == export_attrs, slug


def _simple_ingest_then_export(
    slug: str, sample_xml: str, **export_kw
) -> tuple[etree._Element, list[dict], str]:
    """Ingest a sample register and rebuild it, without a database.

    Entries get the fake ids ``1, 2, ...`` in document order.

    Args:
        slug: Key into ``ingest.PROFILES``.
        sample_xml: A complete TEI document with the register's records.
        **export_kw: Passed on to ``export.build_document``, e.g. ``families``
            and ``memberships`` for a register with groups.

    Returns:
        A tuple ``(src, entries, exported)``: the parsed source tree, the
        extracted entries (with their fake ``id``) and the exported XML string.
    """
    profile = ingest.PROFILES[slug]
    src = etree.fromstring(sample_xml.encode(), etree.XMLParser(remove_comments=True))
    records = src.xpath(profile["record_xpath"], namespaces=ingest.NS)
    project = ingest.project_of(slug)
    entries = [ingest.extract(r, profile, project) for r in records]
    for i, e in enumerate(entries, start=1):
        e["id"] = i
    return src, entries, export.build_document(project, profile["entry_type"], entries, **export_kw)


_SCHLEIERMACHER_GLOSSARY = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><list>
  <item xml:id="S1265447">
    <label type="reg" xml:lang="deu">Katechisation</label>
    <label type="alt">Konfirmationsunterricht</label>
    <desc resp="#DS"/>
    <interp id="#instrument"/>
    <note resp="FS"><p>Mit dem Begriff verweist er auf den Unterricht.</p><p type="source">Archiv der BBAW</p></note>
  </item>
  <item xml:id="S1265448">
    <label type="reg">Agapen</label>
    <desc>Liebesmahl</desc>
  </item>
</list></body></text></TEI>
"""


def test_schleiermacher_glossary_roundtrips_clean(xml_diff):
    """Check that glossary items survive ingest then export without any diff."""
    _, _, exported = _simple_ingest_then_export("schleiermacher_glossary", _SCHLEIERMACHER_GLOSSARY)
    # `list` also names the outer element, so diff the whole body
    diff = xml_diff(_SCHLEIERMACHER_GLOSSARY, exported, subtree=".//tei:body")
    assert diff == "", "\n" + diff


_SCHLEIERMACHER_ORGS = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listOrg>
  <listOrg>
    <head>Akademie</head>
    <org xml:id="S0000002"><orgName type="reg">Akademie, Klasse</orgName><orgName type="alt">Klasse</orgName><desc>Mitglieder</desc></org>
  </listOrg>
  <org xml:id="S0000001">
    <idno type="uri">http://d-nb.info/gnd/1</idno>
    <orgName type="reg">Singverein</orgName>
  </org>
</listOrg></body></text></TEI>
"""


def test_schleiermacher_organisations_roundtrip_clean(xml_diff):
    """Check that organisations, including a parent institution, round-trip without a diff.

    The parent institution (a nested ``listOrg``) is rebuilt from the family and
    membership the DB would hold, simulated here with a fake id.
    """
    profile = ingest.PROFILES["schleiermacher_organisations"]
    src = etree.fromstring(_SCHLEIERMACHER_ORGS.encode())
    groups = ingest._extract_groups(src.getroottree(), "K.xml", profile)
    assert [g["label"] for g in groups] == ["Akademie"]
    _, entries, _ = _simple_ingest_then_export("schleiermacher_organisations", _SCHLEIERMACHER_ORGS)
    id_by_xmlid = {e["source_id"]: e["id"] for e in entries}
    families = [{"id": 1000, "label": "Akademie"}]
    memberships = [
        {"subject_id": id_by_xmlid[x], "object_id": 1000} for x in groups[0]["member_xmlids"]
    ]
    exported = export.build_document(
        "schleiermacher", "organisation", entries, families=families, memberships=memberships
    )
    # the group (label "Akademie") sorts before the ungrouped org ("Singverein")
    diff = xml_diff(_SCHLEIERMACHER_ORGS, exported, subtree=".//tei:body")
    assert diff == "", "\n" + diff


_SCHLEIERMACHER_BIBLE = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><list>
  <list type="AT"><label>Altes Testament</label><list>
    <item n="1"><idno>Gen</idno><label unit="name">Genesis</label><label unit="abk">Gen.</label><label unit="name2">1 Mose</label><label unit="abk2">1 Mose</label><label unit="gruppea">Pentateuch</label></item>
  </list></list>
  <list type="AP"><label>Apokryphen</label><list>
    <item n="40"><idno>Jud</idno><label unit="name">Judit</label><label unit="abk">Jud.</label><label unit="name2">Judith</label><label unit="abk2">Jdt</label><label unit="gruppea">Apokryphen</label></item>
  </list></list>
  <list type="NT"><label>Neues Testament</label><list>
    <item n="50"><idno>Röm</idno><label unit="name">Römer</label><label unit="abk">Röm.</label><label unit="name2">Römerbrief</label><label unit="abk2">Röm</label><label unit="gruppea">Briefe</label><label unit="gruppeb">Paulusbriefe</label></item>
  </list></list>
</list></body></text></TEI>
"""


def test_schleiermacher_bible_books_roundtrip_clean(xml_diff):
    """Check that bible books come back in their ``AT``/``AP``/``NT`` sub-lists, without a diff.

    The synthetic ``source_id`` must not be written out as an ``xml:id``.
    """
    _, _, exported = _simple_ingest_then_export(
        "schleiermacher_bible_books", _SCHLEIERMACHER_BIBLE
    )
    diff = xml_diff(_SCHLEIERMACHER_BIBLE, exported, subtree=".//tei:body")
    assert diff == "", "\n" + diff
    # the synthetic source_id must not leak out as an xml:id
    assert "xml:id" not in exported and "bibelsystematik" not in exported


_SCHLEIERMACHER_WORKS = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listBibl>
  <listBibl type="group">
    <head>Adelung, Johann Christoph</head>
    <bibl xml:id="S0000001">
      <author><persName key="S0000100"><surname>Adelung</surname><forename>Johann Christoph</forename></persName></author>
      <title>Wörterbuch</title>
      <pubPlace key="S0000065">Leipzig</pubPlace>
      <date>(1793)</date>
      <note>zweite Auflage</note>
    </bibl>
  </listBibl>
  <bibl xml:id="S0000003">
    <author role="translation"><persName key="S0000101"><surname>Schiller</surname><forename>Friedrich</forename></persName></author>
    <author><persName><name>Anonym</name></persName></author>
    <editor><persName key="S0000102"><surname>Arnim</surname><forename>Achim von</forename></persName></editor>
    <title>Iphigenie</title>
  </bibl>
  <bibl xml:id="S0000002" type="journal">
    <author><persName><surname/><forename/></persName></author>
    <title>The Times</title>
  </bibl>
</listBibl></body></text></TEI>
"""


def test_schleiermacher_works_roundtrip_clean(xml_diff):
    """Check that works, including an author's group, round-trip without a diff.

    The group (``listBibl[@type='group']``) is rebuilt from the family and
    membership the DB would hold, simulated here with a fake id. The structured
    authors/editors must come back as they were.
    """
    profile = ingest.PROFILES["schleiermacher_works"]
    src = etree.fromstring(_SCHLEIERMACHER_WORKS.encode())
    groups = ingest._extract_groups(src.getroottree(), "Werke.xml", profile)
    assert [g["label"] for g in groups] == ["Adelung, Johann Christoph"]
    _, entries, _ = _simple_ingest_then_export("schleiermacher_works", _SCHLEIERMACHER_WORKS)
    id_by_xmlid = {e["source_id"]: e["id"] for e in entries}
    families = [{"id": 1000, "label": groups[0]["label"]}]
    memberships = [
        {"subject_id": id_by_xmlid[x], "object_id": 1000} for x in groups[0]["member_xmlids"]
    ]
    exported = export.build_document(
        "schleiermacher", "work", entries, families=families, memberships=memberships
    )
    # sorted by label: the group (Adelung…) < Iphigenie < The Times — as in the fixture
    # order of the two ungrouped works below
    diff = xml_diff(_SCHLEIERMACHER_WORKS, exported, subtree=".//tei:body")
    assert diff == "", "\n" + diff


# avhr: the person notes link places and institutions of the project's own
# Orte/Einrichtungen registers — both ingested as their own profiles so the
# links resolve, then spliced back by export like the persName links
_EHD_LINKED_PERSON = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
  <person xml:id="H0003008">
    <persName type="reg"><surname>Baader</surname><forename>Franz</forename></persName>
    <note>1788 Bergbau an der <orgName key="H0000529">Bergakademie Freiberg</orgName>, dann in <placeName key="H0006574">Jena</placeName> und bei <persName key="H0003009">Goethe</persName></note>
  </person>
  <person xml:id="H0003009">
    <persName type="reg"><surname>Goethe</surname><forename>Johann Wolfgang</forename></persName>
  </person>
</listPerson></body></text></TEI>
"""

_EHD_PLACES = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPlace>
  <place oldID="ed_1" xml:id="H0006574">
    <idno type="uri">https://www.geonames.org/2895044</idno>
    <placeName type="reg">Jena</placeName>
    <placeName type="alt" subtype="contemporary">Jhena</placeName>
    <note resp="#CG">Universitätsstadt an der <placeName key="H0000001">Saale</placeName></note>
    <linkGrp>
      <ptr target="16#41" type="letter"/>
    </linkGrp>
    <listPlace>
      <place type="building" xml:id="H0000002">
        <placeName type="reg">Schloss</placeName>
        <note>in <placeName key="H0006574">Jena</placeName></note>
      </place>
    </listPlace>
  </place>
  <place xml:id="H0000001">
    <placeName type="reg">Saale</placeName>
  </place>
</listPlace></body></text></TEI>
"""

_EHD_ORGS = """
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listOrg>
  <org oldID="ed_hpr_1ms_2z" xml:id="H0000529">
    <idno type="uri">http://d-nb.info/gnd/3023911-4</idno>
    <orgName type="reg">Bergakademie Freiberg</orgName>
    <orgName type="alt">Königlich-Sächsische Bergakademie zu Freiberg</orgName>
    <desc>1765 gegründet, in <placeName key="H0006574">Jena</placeName> nicht vertreten</desc>
    <linkGrp>
      <ptr subtype="comment" target="14#143" type="letter"/>
    </linkGrp>
  </org>
</listOrg></body></text></TEI>
"""


def _ehd_ingest_then_export() -> dict[str, str]:
    """All three avhr registers through ingest.extract, the nesting pass and the
    mentions pass, simulated without a live DB the way roundtrip_report.py
    does it: entry ids are shared across the registers, so a link resolves to
    an entry of another register. Returns the exported XML by profile slug."""
    samples = {"avhr": _EHD_LINKED_PERSON, "avhr_places": _EHD_PLACES, "avhr_organisations": _EHD_ORGS}
    parsed, entries_by_slug, id_by_xmlid, entries_by_id = {}, {}, {}, {}
    next_id = 1
    for slug, sample in samples.items():
        profile = ingest.PROFILES[slug]
        src = etree.fromstring(sample.encode())
        records = src.xpath(profile["record_xpath"], namespaces=ingest.NS)
        entries = []
        for r in records:
            entry = ingest.extract(r, profile, "avhr")
            entry["id"] = next_id
            next_id += 1
            entries.append(entry)
            id_by_xmlid[entry["source_id"]] = entry["id"]
            entries_by_id[entry["id"]] = entry
        parsed[slug] = (src, records)
        entries_by_slug[slug] = entries

    out = {}
    for slug, (src, records) in parsed.items():
        profile = ingest.PROFILES[slug]
        mentions, anchors, targets = [], {}, set()
        for record in records:
            subject = id_by_xmlid[record.get(XMLID)]
            _, links = ingest._walk_record_comments(record)
            for link, anchor in ingest._record_links(record, profile, links):
                target = id_by_xmlid[link["key"]]
                mentions.append({"subject_id": subject, "predicate": "mentions", "object_id": target})
                targets.add(target)
                if anchor:
                    anchors[(subject, target)] = anchor
        parents = [
            {"subject_id": id_by_xmlid[child], "object_id": id_by_xmlid[parent]}
            for child, parent in ingest._extract_place_nesting(src.getroottree()).items()
        ]
        out[slug] = export.build_document(
            "avhr", profile["entry_type"], entries_by_slug[slug], parents=parents,
            mentions=mentions, mention_targets=[entries_by_id[t] for t in targets],
            mention_anchors=anchors,
        )
    return out


def test_ehd_place_and_org_links_in_notes_roundtrip_clean(xml_diff):
    exported = _ehd_ingest_then_export()
    for slug, sample, subtree in (
        ("avhr", _EHD_LINKED_PERSON, ".//tei:listPerson"),
        ("avhr_places", _EHD_PLACES, ".//tei:listPlace"),
        ("avhr_organisations", _EHD_ORGS, ".//tei:listOrg"),
    ):
        diff = xml_diff(sample, exported[slug], subtree=subtree)
        assert diff == "", f"{slug}:\n{diff}"

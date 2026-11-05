"""Entry lifecycle: POST / list / filter / GET / PATCH / DELETE on /{project}/entries."""

import pytest


@pytest.fixture
def person(client):
    """Create one leibniz5 person and return its JSON body."""
    r = client.post(
        "/leibniz5/entries",
        json={
            
            "entry_type": "person",
            "label": "Gottfried Wilhelm Leibniz",
            "source_id": "L0001",
            "data": {"surname": "Leibniz", "forename": "Gottfried Wilhelm", "birth_date": "1646"},
        },
    )
    assert r.status_code == 201
    return r.json()


def test_create_and_read(client, person):
    got = client.get(f"/leibniz5/entries/{person['id']}").json()
    assert got["label"] == "Gottfried Wilhelm Leibniz"
    assert got["data"]["birth_date"] == "1646"


def test_list_filters(client, person):
    assert len(client.get("/leibniz5/entries").json()) == 1
    assert len(client.get("/leibniz5/entries", params={"entry_type": "person"}).json()) == 1
    assert client.get("/leibniz5/entries", params={"entry_type": "place"}).json() == []


def _mk(client, label):
    client.post(
        "/leibniz5/entries",
        json={"entry_type": "person", "label": label, "data": {}},
    )


def test_default_order_is_by_label_with_total_count(client):
    for lbl in ("Zed", "Abel", "Mopp"):
        _mk(client, lbl)
    r = client.get("/leibniz5/entries")
    assert r.headers["X-Total-Count"] == "3"
    assert [e["label"] for e in r.json()] == ["Abel", "Mopp", "Zed"]

    desc = client.get("/leibniz5/entries", params={"descending": True})
    assert [e["label"] for e in desc.json()] == ["Zed", "Mopp", "Abel"]


def test_pagination(client):
    for lbl in ("a", "b", "c", "d", "e"):
        _mk(client, lbl)
    page2 = client.get("/leibniz5/entries", params={"limit": 2, "offset": 2})
    assert page2.headers["X-Total-Count"] == "5"
    assert [e["label"] for e in page2.json()] == ["c", "d"]


def test_sort_by_birth_date_uses_derived_key(client):
    # stored verbatim, ordered by the parsed sort key; undated rows come last
    people = {
        "Early": "um 1700",
        "Middle": "nach 1750",
        "Late": "1799",
        "Undated": "?",
    }
    for label, birth in people.items():
        client.post(
        "/leibniz5/entries",
        json={
                
                "entry_type": "person",
                "label": label,
                "data": {"surname": label, "birth_date": birth},
            },
        )
    r = client.get("/leibniz5/entries", params={"sort_by": "birth_date"})
    assert [e["label"] for e in r.json()] == ["Early", "Middle", "Late", "Undated"]

    desc = client.get(
        "/leibniz5/entries", params={"sort_by": "birth_date", "descending": True},
    )
    # NULLs stay last even when descending
    assert [e["label"] for e in desc.json()] == ["Late", "Middle", "Early", "Undated"]


def test_patch_refreshes_the_sort_key(client, person):
    client.patch(f"/leibniz5/entries/{person['id']}", json={"data": {"surname": "Leibniz", "birth_date": "vor 1500"}})
    _mk(client, "later person")  # a person with no date -> sorts after
    r = client.get("/leibniz5/entries", params={"sort_by": "birth_date"})
    assert [e["label"] for e in r.json()][0] == "Gottfried Wilhelm Leibniz"


def test_search_by_label_substring(client):
    for lbl in ("Albert Einstein", "Marie Curie", "Albrecht Dürer"):
        _mk(client, lbl)
    r = client.get("/leibniz5/entries", params={"q": "alb"})  # case-insensitive
    assert sorted(e["label"] for e in r.json()) == ["Albert Einstein", "Albrecht Dürer"]
    assert r.headers["X-Total-Count"] == "2"


def test_search_by_data_field(client):
    body = {"entry_type": "person"}
    client.post("/leibniz5/entries", json={**body, "label": "X", "data": {"surname": "Leibniz"}})
    client.post("/leibniz5/entries", json={**body, "label": "Y", "data": {"surname": "Newton"}})
    client.post(
        "/leibniz5/entries",
        json={
            **body,
            "label": "Z",
            "data": {"surname": "Bernoulli", "idno": [{"value": "gnd/123", "type": "uri"}]},
        },
    )
    assert [e["label"] for e in client.get("/leibniz5/entries", params={"q": "leib", "q_field": "surname"}).json()] == ["X"]
    # repeatable field: matched against the stored JSON text
    assert [e["label"] for e in client.get("/leibniz5/entries", params={"q": "gnd/12", "q_field": "idno"}).json()] == ["Z"]


def test_search_unknown_field_matches_nothing(client):
    _mk(client, "Whoever")
    assert client.get("/leibniz5/entries", params={"q": "who", "q_field": "not a field"}).json() == []


def test_entry_options_returns_id_and_label(client):
    ids = {}
    for lbl in ("Zed", "Abel", "Mopp"):
        r = client.post(
        "/leibniz5/entries",
        json={"entry_type": "person", "label": lbl, "data": {}},
        )
        ids[lbl] = r.json()["id"]

    r = client.get("/leibniz5/entries/options", params={"entry_type": "person"})
    assert r.status_code == 200
    assert r.json() == [
        {"id": ids["Abel"], "label": "Abel"},
        {"id": ids["Mopp"], "label": "Mopp"},
        {"id": ids["Zed"], "label": "Zed"},
    ]
    # nothing of that type
    assert client.get("/leibniz5/entries/options", params={"entry_type": "place"}).json() == []
    # label filter
    q = client.get("/leibniz5/entries/options", params={"entry_type": "person", "q": "ab"})
    assert [o["label"] for o in q.json()] == ["Abel"]


def test_entry_options_pages_with_offset(client):
    for lbl in ("Abel", "Bea", "Cee"):
        client.post(
        "/leibniz5/entries",
        json={"entry_type": "person", "label": lbl, "data": {}},
        )
    page1 = client.get(
        "/leibniz5/entries/options", params={"entry_type": "person", "limit": 2},
    ).json()
    page2 = client.get(
        "/leibniz5/entries/options", params={"entry_type": "person", "limit": 2, "offset": 2},
    ).json()
    assert [o["label"] for o in page1] == ["Abel", "Bea"]
    assert [o["label"] for o in page2] == ["Cee"]


def test_entry_options_unknown_project_is_404(client):
    assert client.get("/nope/entries/options", params={"entry_type": "person"}).status_code == 404


def test_entry_options_ul_format(client):
    r = client.post(
        "/leibniz5/entries",
        json={
            
            "entry_type": "person",
            "label": "Kadach, Johann Gottfried",
            "source_id": "S0002449",
            "data": {"birth_date": "1773", "death_date": "1847"},
        },
    )
    assert r.status_code == 201, r.text
    # no birth/death -> "(-)"
    client.post(
        "/leibniz5/entries",
        json={"entry_type": "person", "label": "Mustermann", "source_id": "S0000001", "data": {}},
    )
    # no source_id (no ID_URL in the tests) -> left out: a numeric id is no xml:id
    client.post("/leibniz5/entries", json={"entry_type": "person", "label": "Nobody", "data": {}})

    resp = client.get(
        "/leibniz5/entries/options", params={"entry_type": "person", "format": "ul"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert resp.text == (
        "<ul>\n"
        '<li xml:id="S0002449">\n'
        "<span>Kadach, Johann Gottfried (1773-1847)</span>\n"
        "</li>\n"
        '<li xml:id="S0000001">\n'
        "<span>Mustermann (-)</span>\n"
        "</li>\n"
        "</ul>"
    )


def test_create_in_unknown_project_is_404(client):
    r = client.post(
        "/ghost/entries",
        json={"entry_type": "person", "label": "X", "data": {}},
    )
    assert r.status_code == 404


def test_create_rejects_unknown_data_field(client):
    # a typo'd / drifted field name, not a real leibniz5 field
    r = client.post(
        "/leibniz5/entries",
        json={"entry_type": "person", "label": "X", "data": {"sruname": "X"}},
    )
    assert r.status_code == 422


def test_create_accepts_a_projects_declared_extra_keys(client):
    # mop's alt_names/old_id aren't form fields but are legitimate ingest data
    r = client.post(
        "/mop/entries",
        json={
            
            "entry_type": "person",
            "label": "X",
            "data": {"surname": "X", "alt_names": "Y", "old_id": "Z"},
        },
    )
    assert r.status_code == 201, r.text


def test_patch_updates_label(client, person):
    updated = client.patch(f"/leibniz5/entries/{person['id']}", json={"label": "Leibniz"}).json()
    assert updated["label"] == "Leibniz"
    assert updated["data"]["surname"] == "Leibniz"  # untouched


def test_patch_rejects_unknown_data_field(client, person):
    r = client.patch(f"/leibniz5/entries/{person['id']}", json={"data": {"sruname": "X"}})
    assert r.status_code == 422
    # rejected write must not have touched the stored entry
    assert client.get(f"/leibniz5/entries/{person['id']}").json()["data"]["surname"] == "Leibniz"


def test_delete(client, person):
    assert client.delete(f"/leibniz5/entries/{person['id']}").json() == {"ok": True}
    assert client.get(f"/leibniz5/entries/{person['id']}").status_code == 404


# --- updated_at / ingested_at (re-ingest reconciliation) -----------------------


def test_patch_sets_updated_at(client, person):
    assert person["updated_at"] is None  # never touched since creation
    updated = client.patch(f"/leibniz5/entries/{person['id']}", json={"label": "Leibniz"}).json()
    assert updated["updated_at"] is not None


def test_the_api_cannot_claim_an_ingest(client, person):
    """``ingested_source_hash`` is the ingest's own (in-process) field; an API
    client sending it is ignored, never recorded."""
    r = client.post(
        "/leibniz5/entries",
        json={"entry_type": "person", "label": "X", "data": {"surname": "X"}, "ingested_source_hash": "abc"},
    )
    assert r.json()["ingested_source_hash"] is None and r.json()["ingested_at"] is None
    r = client.patch(f"/leibniz5/entries/{person['id']}", json={"label": "Y", "ingested_source_hash": "abc"})
    assert r.json()["ingested_source_hash"] is None


def test_create_with_ingest_hash_sets_ingested_at(client, session):  # client: seeds the projects
    from ediarum_index import ingest

    body = ingest.add_entry(session, {
        "project_name": "leibniz5", "entry_type": "person", "label": "X",
        "data": {"surname": "X"}, "ingested_source_hash": "abc123",
    })
    assert body["ingested_source_hash"] == "abc123"
    assert body["ingested_at"] is not None


def test_patch_with_ingest_hash_sets_ingested_at_equal_to_updated_at(session, person):
    # an ingest-driven update must not look like a curator edit that happened
    # after it — see models.Entry.ingested_at
    from ediarum_index import ingest

    updated = ingest.patch_entry(session, person["id"], {
        "label": person["label"], "source_id": person["source_id"],
        "data": {"surname": "Leibniz"}, "ingested_source_hash": "def456",
    })
    assert updated["ingested_source_hash"] == "def456"
    assert updated["ingested_at"] == updated["updated_at"]


def test_patch_without_ingest_hash_leaves_ingested_at_untouched(client, person):
    client.patch(f"/leibniz5/entries/{person['id']}", json={"label": "Leibniz, G. W."})
    got = client.get(f"/leibniz5/entries/{person['id']}").json()
    assert got["ingested_at"] is None  # this entry was never ingested

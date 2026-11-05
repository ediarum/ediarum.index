"""Relation lifecycle: POST / GET / DELETE on /{project}/relations.

Generic (subject, predicate, object) triples linking two entries in the same
project — see models.Relation. No dedicated project of its own; its project
is the one its subject entry belongs to.
"""

import pytest

from tests.conftest import user


def _mk_entry(client, project, label, entry_type="person"):
    r = client.post(
        f"/{project}/entries",
        json={"entry_type": entry_type, "label": label, "data": {}},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def two_leibniz_entries(client):
    a = _mk_entry(client, "leibniz5", "A")
    b = _mk_entry(client, "leibniz5", "B")
    return a, b


def test_create_and_read(client, two_leibniz_entries):
    a, b = two_leibniz_entries
    r = client.post(
        "/leibniz5/relations", json={"subject_id": a["id"], "predicate": "member_of", "object_id": b["id"]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["subject_id"] == a["id"]
    assert body["predicate"] == "member_of"
    assert body["object_id"] == b["id"]

    got = client.get("/leibniz5/relations").json()
    assert len(got) == 1
    # GET returns everything POST did, plus resolved labels (see test_read_resolves_labels)
    for key in ("id", "subject_id", "predicate", "object_id"):
        assert got[0][key] == body[key]


def test_read_resolves_labels(client):
    alice = _mk_entry(client, "leibniz5", "Alice")
    bob = _mk_entry(client, "leibniz5", "Bob")
    client.post(
        "/leibniz5/relations", json={"subject_id": alice["id"], "predicate": "member_of", "object_id": bob["id"]}
    )
    got = client.get("/leibniz5/relations").json()
    assert got[0]["subject_label"] == "Alice"
    assert got[0]["object_label"] == "Bob"

    # direction matters: swap subject/object, labels swap with them, not stay fixed
    client.post(
        "/leibniz5/relations", json={"subject_id": bob["id"], "predicate": "member_of", "object_id": alice["id"]}
    )
    by_subject = {
        r["subject_id"]: (r["subject_label"], r["object_label"])
        for r in client.get("/leibniz5/relations").json()
    }
    assert by_subject[alice["id"]] == ("Alice", "Bob")
    assert by_subject[bob["id"]] == ("Bob", "Alice")


def test_read_filters(client, two_leibniz_entries):
    a, b = two_leibniz_entries
    c = _mk_entry(client, "leibniz5", "C")
    client.post("/leibniz5/relations", json={"subject_id": a["id"], "predicate": "member_of", "object_id": b["id"]})
    client.post("/leibniz5/relations", json={"subject_id": c["id"], "predicate": "sibling_of", "object_id": a["id"]})

    by_subject = client.get("/leibniz5/relations", params={"subject_id": a["id"]}).json()
    assert len(by_subject) == 1 and by_subject[0]["object_id"] == b["id"]

    by_predicate = client.get("/leibniz5/relations", params={"predicate": "sibling_of"}).json()
    assert len(by_predicate) == 1 and by_predicate[0]["subject_id"] == c["id"]

    by_object = client.get("/leibniz5/relations", params={"object_id": a["id"]}).json()
    assert len(by_object) == 1 and by_object[0]["subject_id"] == c["id"]


def test_duplicate_triple_is_rejected(client, two_leibniz_entries):
    a, b = two_leibniz_entries
    body = {"subject_id": a["id"], "predicate": "member_of", "object_id": b["id"]}
    assert client.post("/leibniz5/relations", json=body).status_code == 201
    r = client.post("/leibniz5/relations", json=body)
    assert r.status_code == 409
    # a different predicate between the same two entries is not a duplicate
    other = {**body, "predicate": "sibling_of"}
    assert client.post("/leibniz5/relations", json=other).status_code == 201


def test_unknown_subject_or_object_is_404(client, two_leibniz_entries):
    a, _b = two_leibniz_entries
    assert client.post(
        "/leibniz5/relations", json={"subject_id": a["id"], "predicate": "x", "object_id": 999999}
    ).status_code == 404
    assert client.post(
        "/leibniz5/relations", json={"subject_id": 999999, "predicate": "x", "object_id": a["id"]}
    ).status_code == 404


def test_cross_project_relation_is_rejected(client, two_leibniz_entries):
    a, _b = two_leibniz_entries
    mop_entry = _mk_entry(client, "mop", "M")
    r = client.post(
        "/leibniz5/relations", json={"subject_id": a["id"], "predicate": "x", "object_id": mop_entry["id"]}
    )
    assert r.status_code == 422


def test_delete(client, two_leibniz_entries):
    a, b = two_leibniz_entries
    created = client.post(
        "/leibniz5/relations", json={"subject_id": a["id"], "predicate": "member_of", "object_id": b["id"]}
    ).json()
    assert client.delete(f"/leibniz5/relations/{created['id']}").json() == {"ok": True}
    assert client.get("/leibniz5/relations").json() == []
    assert client.delete(f"/leibniz5/relations/{created['id']}").status_code == 404


def test_read_unknown_project_is_404(client):
    assert client.get("/nope/relations").status_code == 404


def test_user_without_the_project_can_neither_read_nor_write(client, as_caller, two_leibniz_entries):
    a, b = two_leibniz_entries
    created = client.post(
        "/leibniz5/relations", json={"subject_id": a["id"], "predicate": "member_of", "object_id": b["id"]}
    ).json()
    as_caller(user("mop"))
    assert client.get("/leibniz5/relations").status_code == 403
    r = client.post(
        "/leibniz5/relations", json={"subject_id": a["id"], "predicate": "sibling_of", "object_id": b["id"]}
    )
    assert r.status_code == 403
    assert client.delete(f"/leibniz5/relations/{created['id']}").status_code == 403

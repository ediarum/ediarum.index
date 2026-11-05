"""Who may do what: a caller (platform user or API key) may use a project if it
is one of theirs, or they are an admin (``Caller.may_use``); the check runs on
every ``/{project}/…`` route, reads and writes alike. Rows of another project
are not found through this project's URL."""

from tests.conftest import key, user


def _mk(client, project, label="A"):
    r = client.post(f"/{project}/entries", json={"entry_type": "person", "label": label, "data": {}})
    assert r.status_code == 201, r.text
    return r.json()


def test_user_reads_and_writes_their_projects_only(client, as_caller):
    as_caller(user("mop"))
    assert client.get("/mop/entries").status_code == 200
    _mk(client, "mop")
    assert client.get("/pta/entries").status_code == 403
    assert client.post("/pta/entries", json={"entry_type": "person", "label": "x"}).status_code == 403


def test_scoped_key_reads_only_its_projects(client, as_caller):
    as_caller(key("mop"))
    assert client.get("/mop/entries/options", params={"entry_type": "person"}).status_code == 200
    assert client.get("/pta/entries/options", params={"entry_type": "person"}).status_code == 403
    assert client.get("/pta/export/person").status_code == 403


def test_entry_of_another_project_is_not_found_here(client, as_caller):
    entry = _mk(client, "pta")
    as_caller(user("mop"))
    assert client.get(f"/mop/entries/{entry['id']}").status_code == 404
    assert client.patch(f"/mop/entries/{entry['id']}", json={"label": "x"}).status_code == 404
    assert client.delete(f"/mop/entries/{entry['id']}").status_code == 404
    assert client.post("/mop/comments", json={"entry_id": entry["id"], "text": "x"}).status_code == 404


def test_relation_across_projects_is_not_found(client):
    a, b = _mk(client, "mop"), _mk(client, "pta")
    r = client.post("/mop/relations", json={"subject_id": a["id"], "predicate": "x", "object_id": b["id"]})
    assert r.status_code == 422  # subject in mop, object elsewhere
    r = client.post("/pta/relations", json={"subject_id": a["id"], "predicate": "x", "object_id": b["id"]})
    assert r.status_code == 404  # subject not in pta


def test_entry_types_need_a_caller_but_no_project(client, as_caller):
    as_caller(key("mop"))
    assert client.get("/entry-types").status_code == 200


def test_keys_and_ingest_runs_are_for_platform_admins(client, as_caller):
    for caller in (user("mop"), key(admin=True)):
        as_caller(caller)
        assert client.get("/keys").status_code == 403
        assert client.get("/ingest-runs").status_code == 403

"""/keys: platform admins manage API keys; the key is shown once."""

from sqlmodel import select

from ediarum_sdk.auth import ApiKey, hash_key


def test_create_list_revoke(client, session):
    r = client.post("/keys", json={"name": "oxygen-mop", "projects": ["mop"]})
    assert r.status_code == 201
    assert r.headers["cache-control"] == "no-store"
    plaintext = r.json()["key"]
    row = session.exec(select(ApiKey).where(ApiKey.name == "oxygen-mop")).one()
    assert row.key_hash == hash_key(plaintext) and row.created_by == "editor@example.org"

    listed = client.get("/keys").json()
    assert listed == [{"name": "oxygen-mop", "projects": ["mop"], "is_admin": False,
                       "is_active": True, "created_by": "editor@example.org"}]
    assert "key" not in listed[0]
    assert client.get("/keys", params={"project": "pta"}).json() == []

    assert client.post("/keys/oxygen-mop/revoke").status_code == 204
    assert client.get("/keys").json()[0]["is_active"] is False
    assert client.post("/keys/ghost/revoke").status_code == 404


def test_all_projects_key(client):
    assert client.post("/keys", json={"name": "all", "projects": ["*"]}).status_code == 201


def test_duplicate_name_and_unknown_project(client):
    client.post("/keys", json={"name": "k", "projects": ["mop"]})
    assert client.post("/keys", json={"name": "k", "projects": ["mop"]}).status_code == 409
    assert client.post("/keys", json={"name": "k2", "projects": ["nope"]}).status_code == 422
    assert client.post("/keys", json={"name": "bad name", "projects": ["mop"]}).status_code == 422

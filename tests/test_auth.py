"""deps.current_caller for real: platform users via the auth-verify endpoint
(mocked with httpx2.MockTransport) and API keys from the ``sdk_api_key`` table.
Unlike every other test module, nothing here overrides the caller dependency.
"""

import httpx2 as httpx
import pytest
from ediarum_sdk.auth import AuthConfig, create_key
from fastapi.testclient import TestClient
from sqlmodel import Session

from ediarum_index import main
from ediarum_index.main import app, get_session

VERIFY_URL = "https://platform.test/api/auth/verify"


def verify_answering(status: int, headers: dict | None = None, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status, headers=headers or {})
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(name="raw_client")
def raw_client_fixture(engine, monkeypatch):
    """A TestClient with the real auth dependency; the verify endpoint is set
    per test via :func:`use_verify`."""
    monkeypatch.setenv("AUTH_VERIFY_URL", VERIFY_URL)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    original_engine = main.engine
    main.engine = engine
    app.dependency_overrides[get_session] = _get_session_override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        main.engine = original_engine
        app.dependency_overrides.clear()


def use_verify(client: httpx.Client) -> None:
    app.state.verify_client = client
    app.state.auth_config = AuthConfig(verify_url=VERIFY_URL)


PLATFORM_USER = {"x-user": "ada@example.org", "x-user-roles": "", "x-user-projects": "mop,pta"}


def test_platform_user_may_use_their_projects(raw_client):
    use_verify(verify_answering(204, PLATFORM_USER))
    assert raw_client.get("/mop/entries").status_code == 200
    assert raw_client.get("/leibniz5/entries").status_code == 403


def test_projects_lists_only_the_users_projects(raw_client):
    use_verify(verify_answering(204, PLATFORM_USER))
    assert [p["name"] for p in raw_client.get("/projects").json()] == ["mop", "pta"]


def test_platform_admin_may_use_every_project(raw_client):
    use_verify(verify_answering(204, {"x-user": "root@example.org", "x-user-roles": "admin"}))
    assert raw_client.get("/leibniz5/entries").status_code == 200
    assert len(raw_client.get("/projects").json()) >= 6


def test_verify_gets_cookie_xsrf_and_method(raw_client):
    seen = []
    use_verify(verify_answering(204, PLATFORM_USER, seen))
    raw_client.post("/mop/comments", json={"entry_id": 1, "text": "x"},
                    headers={"cookie": "session=abc", "x-xsrf-token": "tok"})
    assert seen[0].headers["cookie"] == "session=abc"
    assert seen[0].headers["x-xsrf-token"] == "tok"
    assert seen[0].headers["x-original-method"] == "POST"


@pytest.mark.parametrize("status,expected", [(401, 401), (419, 419), (500, 503)])
def test_verify_answers_are_mapped(raw_client, status, expected):
    use_verify(verify_answering(status))
    assert raw_client.get("/mop/entries").status_code == expected


def test_verify_204_without_user_is_503(raw_client):
    use_verify(verify_answering(204))
    assert raw_client.get("/mop/entries").status_code == 503


def test_unreachable_verify_is_503(raw_client):
    def boom(request):
        raise httpx.ConnectError("down")
    use_verify(httpx.Client(transport=httpx.MockTransport(boom)))
    assert raw_client.get("/mop/entries").status_code == 503


def test_without_verify_url_only_keys_work(raw_client, engine):
    app.state.auth_config = AuthConfig()
    assert raw_client.get("/mop/entries").status_code == 401
    with Session(engine) as session:
        k = create_key(session, "oxygen", "mop")
    assert raw_client.get("/mop/entries", headers={"Authorization": f"Bearer {k}"}).status_code == 200


def test_key_is_scoped_to_its_projects(raw_client, engine):
    use_verify(verify_answering(401))  # a key never consults the platform
    with Session(engine) as session:
        k = create_key(session, "oxygen", "mop")
    assert raw_client.get("/mop/entries", params={"key": k}).status_code == 200
    assert raw_client.get("/mop/entries", headers={"X-API-Key": k}).status_code == 200
    assert raw_client.get("/pta/entries", params={"key": k}).status_code == 403


def test_options_as_xml_with_a_key_in_the_url(raw_client, engine):
    """ediarum/oXygen can only fetch a URL — the key goes in ``?key=``."""
    with Session(engine) as session:
        k = create_key(session, "oxygen", "*")
    r = raw_client.get("/mop/entries/options", params={"entry_type": "person", "format": "ul", "key": k})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")


def test_unknown_or_revoked_key_is_401(raw_client, engine):
    from ediarum_sdk.auth import ApiKey

    assert raw_client.get("/mop/entries", params={"key": "nope"}).status_code == 401
    with Session(engine) as session:
        k = create_key(session, "old", "*")
        row = session.get(ApiKey, "old")
        row.is_active = False
        session.add(row)
        session.commit()
    assert raw_client.get("/mop/entries", params={"key": k}).status_code == 401


def test_dev_user_is_an_admin(raw_client):
    app.state.auth_config = AuthConfig(dev_user="dev@example.org")
    assert raw_client.get("/leibniz5/entries").status_code == 200

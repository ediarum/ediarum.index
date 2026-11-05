"""source_ids from ediarum.id for entries created in the app (``idservice``)."""

import httpx2 as httpx
import pytest
from sqlmodel import select

from ediarum_index.idservice import IdService, IdServiceUnavailable, backfill
from ediarum_index.main import app
from ediarum_index.models import Entry


class FakeIds:
    "Stands in for ``IdService``: hands out L0000001, L0000002, … and records the calls."

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[tuple[str, str | None]] = []

    def new_id(self, project: str, note: str | None = None) -> str:
        if self.fail:
            raise IdServiceUnavailable("ediarum.id: unreachable")
        self.calls.append((project, note))
        return f"L{len(self.calls):07d}"


@pytest.fixture
def ids(client):
    fake = FakeIds()
    app.state.ids = fake
    yield fake
    app.state.ids = None


def create(client, **body):
    return client.post("/leibniz5/entries", json={"entry_type": "person", "label": "Nobody", "data": {}, **body})


def test_new_entry_gets_an_id(client, ids):
    r = create(client)
    assert r.status_code == 201
    assert r.json()["source_id"] == "L0000001"
    assert ids.calls == [("leibniz5", "ediarum.index person: Nobody")]


def test_an_empty_source_id_counts_as_none(client, ids):
    assert create(client, source_id="").json()["source_id"] == "L0000001"


def test_a_given_source_id_is_kept(client, ids):
    assert create(client, source_id="X1").json()["source_id"] == "X1"
    assert ids.calls == []


def test_no_entry_without_an_id(client, session):
    app.state.ids = FakeIds(fail=True)
    try:
        r = create(client)
    finally:
        app.state.ids = None
    assert r.status_code == 503
    assert session.exec(select(Entry)).all() == []


def test_new_id_reserves_and_confirms():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/leibniz5/ids":
            return httpx.Response(201, json={"ids": ["L0012345"]})
        return httpx.Response(200, json={"confirmed": ["L0012345"]})

    service = IdService(httpx.Client(transport=httpx.MockTransport(handler)), "http://id/", key="k")
    assert service.new_id("leibniz5", note="n") == "L0012345"
    reserve, confirm = requests
    assert (reserve.url.path, reserve.url.params["note"], reserve.headers["X-API-Key"]) == ("/leibniz5/ids", "n", "k")
    assert (confirm.url.path, confirm.content) == ("/leibniz5/ids/confirm", b'{"ids":["L0012345"]}')


@pytest.mark.parametrize("response", [httpx.Response(403), httpx.Response(200, text="not json")])
def test_new_id_failures_are_unavailable(response):
    service = IdService(httpx.Client(transport=httpx.MockTransport(lambda r: response)), "http://id")
    with pytest.raises(IdServiceUnavailable):
        service.new_id("leibniz5")


def test_backfill(client, session):
    create(client, label="A")
    create(client, label="B", source_id="KEEP")
    assert [(e.label, new) for e, new in backfill(session, None, dry_run=True)] == [("A", None)]
    assert backfill(session, FakeIds(), project="mop") == []
    fake = FakeIds()
    assert [(e.label, new) for e, new in backfill(session, fake, project="leibniz5")] == [("A", "L0000001")]
    assert {e.label: e.source_id for e in session.exec(select(Entry))} == {"A": "L0000001", "B": "KEEP"}

"""The shared-volume pipeline: sources.py (which files, their digest),
POST /files notices and the watcher that ingests a changed project."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select

from ediarum_index import sources
from ediarum_index.bootstrap import sync_registry
from ediarum_index.models import Entry, FileNotice, SourceState
from ediarum_index.watch import Watcher, on_volume

REGISTER = "leibniz5/data/Register"  # leibniz5's REGISTER_DIR, inside its checkout


def _persons(*names: str) -> str:
    people = "".join(
        f'<person xml:id="L{i}"><persName type="reg"><surname>{n}</surname></persName></person>'
        for i, n in enumerate(names)
    )
    return f'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>{people}</listPerson></body></text></TEI>'


@pytest.fixture
def volume(tmp_path, monkeypatch):
    "A shared XML volume with one leibniz5 register file."
    monkeypatch.setenv("XML_MOUNT_ROOT", str(tmp_path))
    persons = tmp_path / REGISTER / "Personen"
    persons.mkdir(parents=True)
    (persons / "A.xml").write_text(_persons("Arnauld", "Bayle"), encoding="utf-8")
    (tmp_path / "leibniz5/data/Briefe.xml").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "leibniz5/data/Briefe.xml").write_text("<x/>")  # not a register file
    return tmp_path


@pytest.fixture
def watcher(engine, session, volume):
    sync_registry(session)
    return Watcher(engine, only=["leibniz5"], settle=0, wait_max=60)


def _labels(engine):
    with Session(engine) as s:
        return sorted(s.exec(select(Entry.label).where(Entry.project_name == "leibniz5")).all())


# --- sources ---------------------------------------------------------------------

def test_project_files_are_what_the_profiles_read(volume):
    assert [p.name for p in sources.project_files("leibniz5")] == ["A.xml"]
    assert sources.is_source_path("leibniz5", "data/Register/Personen/B.xml")
    assert not sources.is_source_path("leibniz5", "data/Briefe.xml")
    assert not sources.is_source_path("leibniz5", "Personen/A.xml")  # outside REGISTER_DIR


def test_digest_follows_content_and_file_set(volume):
    before = sources.digest("leibniz5")
    (volume / "leibniz5/data/Briefe.xml").write_text("<y/>")  # irrelevant file
    assert sources.digest("leibniz5") == before
    (volume / REGISTER / "Personen/B.xml").write_text(_persons("Clarke"), encoding="utf-8")
    assert sources.digest("leibniz5") != before


def test_missing_mount_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("XML_MOUNT_ROOT", raising=False)
    with pytest.raises(SystemExit, match="XML_MOUNT_ROOT"):
        sources.register_dir("leibniz5")


# --- the watcher ------------------------------------------------------------------

def test_first_check_ingests_then_nothing_until_the_files_change(watcher, engine, volume):
    assert watcher.check("leibniz5") is True
    assert _labels(engine) == ["Arnauld", "Bayle"]
    with Session(engine) as s:
        first = s.get(SourceState, "leibniz5").ingested_at

    assert watcher.check("leibniz5") is True  # unchanged: no ingest
    with Session(engine) as s:
        assert s.get(SourceState, "leibniz5").ingested_at == first

    (volume / REGISTER / "Personen/A.xml").write_text(_persons("Arnauld", "Bayle", "Clarke"), encoding="utf-8")
    watcher.check("leibniz5")
    assert _labels(engine) == ["Arnauld", "Bayle", "Clarke"]


def test_a_project_not_on_the_volume_yet_is_skipped_not_recorded(watcher, engine, volume):
    import shutil

    shutil.rmtree(volume / "leibniz5")
    assert watcher.check("leibniz5") is True
    with Session(engine) as s:
        assert s.get(SourceState, "leibniz5") is None  # ingested once the files arrive


def test_a_failed_ingest_is_retried(watcher, engine, monkeypatch):
    from ediarum_index import ingest

    def boom(session, project):
        raise RuntimeError("db gone")

    monkeypatch.setattr(ingest, "ingest_project", boom)
    assert watcher.check("leibniz5") is False
    with Session(engine) as s:
        assert s.get(SourceState, "leibniz5") is None  # so the next check tries again


class FakeFileservice:
    def __init__(self):
        self.state = ("c1", "c1")
        self.calls = 0

    def fingerprint(self, project):
        self.calls += 1
        return self.state


def test_fileservice_status_saves_the_digest(watcher, volume, monkeypatch):
    watcher.fileservice = FakeFileservice()
    watcher.check("leibniz5")
    digests = []
    monkeypatch.setattr(sources, "digest", lambda project, cache=None: digests.append(project) or "x")
    watcher.check("leibniz5")
    assert digests == []  # fileservice reports no change: no digest
    watcher.fileservice.state = ("c2", "c1")
    watcher.check("leibniz5")
    assert digests == ["leibniz5"]


def test_app_led_projects_are_not_watched(watcher):
    class Info:
        index_source_of_truth = "app"

    class Registry:
        def all(self, force=False):
            return {"leibniz5": Info()}

    watcher.registry = Registry()
    assert watcher.projects() == []



class _Led:
    "A registry entry: only ``index_source_of_truth`` matters to the watcher."
    def __init__(self, led):
        self.index_source_of_truth = led


class _Registry:
    """Every project app-led except those in ``xml``; ``all()`` returns a mapping
    that contains every name, as the platform registry would."""
    def __init__(self, xml=()):
        self.xml = set(xml)

    def all(self, force=False):
        registry = self

        class _All(dict):
            def __contains__(self, name):
                return True

            def __getitem__(self, name):
                return _Led("xml" if name in registry.xml else "app")

        return _All()


def test_with_only_app_led_projects_the_watcher_idles(engine, session, volume):
    sync_registry(session)
    watcher = Watcher(engine, registry=_Registry(), settle=0, wait_max=60, interval=0)
    watcher.start()  # no SystemExit: idle
    watcher.step()
    assert watcher.projects() == []
    assert _labels(engine) == []


def test_a_project_that_becomes_xml_led_is_picked_up(engine, session, volume):
    sync_registry(session)
    registry = _Registry()
    watcher = Watcher(engine, registry=registry, settle=0, wait_max=60, interval=0)
    watcher.start()
    registry.xml.add("leibniz5")
    watcher.step()
    assert watcher.projects() == ["leibniz5"]
    assert _labels(engine) == ["Arnauld", "Bayle"]


def test_a_named_project_that_is_not_watched_is_an_error(engine, session, volume):
    sync_registry(session)
    watcher = Watcher(engine, registry=_Registry(), only=["leibniz5"])
    with pytest.raises(SystemExit, match="leibniz5"):
        watcher.start()


# --- POST /files and the notices ----------------------------------------------------

def _post(client, event="modified", path="data/Register/Personen/A.xml", content=b"<x/>", **extra):
    data = {"event": event, "project": "leibniz5", "commit": "abc123", "path": path, **extra}
    files = {"file": ("A.xml", content)} if content is not None else None
    return client.post("/files", data=data, files=files)


def test_post_files_queues_a_notice_for_a_register_file(client, session):
    r = _post(client)
    assert r.status_code == 202 and r.json()["queued"] is True
    notice = session.exec(select(FileNotice)).one()
    assert notice.event == "modified" and notice.sha256 is not None


def test_post_files_ignores_other_files(client, session):
    r = _post(client, path="data/Briefe.xml")
    assert r.status_code == 202 and r.json()["queued"] is False
    assert session.exec(select(FileNotice)).all() == []


@pytest.mark.parametrize("kwargs,status", [
    ({"event": "touched"}, 422),
    ({"content": None}, 422),  # modified without content
    ({"path": "../etc/passwd"}, 400),
    ({"event": "moved"}, 422),  # without previous_path
])
def test_post_files_rejects_bad_notices(client, kwargs, status):
    assert _post(client, **kwargs).status_code == status


def test_post_files_needs_the_project(client, as_caller):
    from tests.conftest import key

    as_caller(key("mop"))
    assert _post(client).status_code == 403


def test_post_files_for_a_project_without_registers_is_acknowledged(client, session):
    """A platform project this app keeps no registers for (no REGISTER_DIR):
    webdav reports every save there too — not an error, just nothing to do."""
    from ediarum_index import projects

    module = projects.PROJECT_MODULES["leibniz5"]
    saved = module.REGISTER_DIR
    del module.REGISTER_DIR
    try:
        r = _post(client)
        assert r.status_code == 202 and r.json()["queued"] is False
    finally:
        module.REGISTER_DIR = saved
    assert session.exec(select(FileNotice)).all() == []


def test_post_files_for_an_app_led_project_is_acknowledged(client, session):
    """Registers kept here: webdav's notice is answered, nothing is queued
    (a 409 would land in webdav's failed queue)."""
    from ediarum_index.main import app

    class Info:
        index_source_of_truth = "app"

    class Registry:
        def get(self, slug):
            return Info()

    app.state.projects = Registry()
    try:
        r = _post(client)
        assert r.status_code == 202 and r.json()["queued"] is False
    finally:
        app.state.projects = None
    assert session.exec(select(FileNotice)).all() == []


def _notice(**kw):
    return FileNotice(**{"project": "leibniz5", "event": "modified", "commit": "c",
                         "path": "data/Register/Personen/A.xml", **kw})


def test_on_volume_compares_the_reported_content(volume):
    content = (volume / REGISTER / "Personen/A.xml").read_bytes()
    import hashlib
    assert on_volume(_notice(sha256=hashlib.sha256(content).hexdigest()))
    assert not on_volume(_notice(sha256="0" * 64))  # fileservice hasn't written it yet
    assert on_volume(_notice(event="deleted", path="data/Register/Personen/gone.xml"))
    assert not on_volume(_notice(event="moved", previous_path="data/Register/Personen/A.xml",
                                 path="data/Register/Personen/B.xml"))


def test_a_notice_triggers_the_ingest_once_the_volume_shows_it(watcher, engine, volume):
    watcher.check("leibniz5")
    target = volume / REGISTER / "Personen/A.xml"
    new = _persons("Arnauld", "Bayle", "Clarke").encode()
    import hashlib
    with Session(engine) as s:
        s.add(_notice(sha256=hashlib.sha256(new).hexdigest()))
        s.commit()

    watcher.handle_notices()  # fileservice hasn't written the file yet: wait
    with Session(engine) as s:
        assert len(s.exec(select(FileNotice)).all()) == 1

    target.write_bytes(new)
    watcher.handle_notices()
    assert _labels(engine) == ["Arnauld", "Bayle", "Clarke"]
    with Session(engine) as s:
        assert s.exec(select(FileNotice)).all() == []


def test_a_notice_is_handled_after_wait_max_even_if_the_volume_never_matches(watcher, engine):
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    with Session(engine) as s:
        s.add(_notice(sha256="0" * 64, received_at=old))
        s.commit()
    watcher.handle_notices()
    with Session(engine) as s:
        assert s.exec(select(FileNotice)).all() == []
        assert s.get(SourceState, "leibniz5") is not None

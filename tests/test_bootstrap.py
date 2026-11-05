"""bootstrap: entry types from code; projects from the platform registry, or
from the project modules without one."""

from dataclasses import dataclass

from sqlmodel import select

from ediarum_index import bootstrap
from ediarum_index.models import EntryTypeRow, Project


@dataclass
class Info:  # the slice of ediarum_sdk.projects.ProjectInfo bootstrap reads
    slug: str
    label: str


class FakeRegistry:
    def __init__(self, *infos, fail=False):
        self.projects = {i.slug: i for i in infos}
        self.fail = fail

    def all(self, *, force=False):
        if self.fail:
            raise RuntimeError("platform down")
        return self.projects


def _projects(session):
    return {p.name: (p.label, p.is_active) for p in session.exec(select(Project)).all()}


def test_without_registry_the_modules_are_the_projects(session):
    bootstrap.sync_registry(session)
    assert set(_projects(session)) == {"avhr", "leibniz5", "mega", "mop", "pta", "schleiermacher"}
    assert session.exec(select(EntryTypeRow)).all()


def test_registry_projects_are_added_and_relabelled(session):
    session.add(Project(name="mop", label="old label"))
    session.commit()
    bootstrap.sync_registry(session, FakeRegistry(Info("mop", "MoP"), Info("new-one", "New")))
    assert _projects(session) == {"mop": ("MoP", True), "new-one": ("New", True)}


def test_a_project_missing_from_the_registry_is_deactivated_not_deleted(session):
    bootstrap.sync_registry(session, FakeRegistry(Info("mop", "MoP"), Info("pta", "PTA")))
    bootstrap.sync_registry(session, FakeRegistry(Info("mop", "MoP")))
    assert _projects(session)["pta"] == ("PTA", False)
    bootstrap.sync_registry(session, FakeRegistry(Info("mop", "MoP"), Info("pta", "PTA")))
    assert _projects(session)["pta"] == ("PTA", True)


def test_refresh_survives_an_unreachable_registry(session):
    assert bootstrap.refresh_projects(session, FakeRegistry(fail=True)) is False
    assert bootstrap.refresh_projects(session, None) is False


def test_unknown_slug_refreshes_from_the_registry(client):
    """A project added on the platform works without a restart."""
    from ediarum_index.main import app

    assert client.get("/fresh/entries").status_code == 404
    app.state.projects = FakeRegistry(Info("fresh", "Fresh"))
    try:
        assert client.get("/fresh/entries").status_code == 200
    finally:
        app.state.projects = None

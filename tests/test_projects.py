"""GET /projects and the project lookup every /{project}/… route goes through."""

from tests.conftest import key, user


def test_seeded_projects_match_code(client):
    from ediarum_index.projects import iter_projects

    want = {name: label for name, label, _ in iter_projects()}
    got = {p["name"]: p["label"] for p in client.get("/projects").json()}
    assert got == want
    assert "leibniz5" in want


def test_projects_are_narrowed_to_the_callers(client, as_caller):
    as_caller(user("mop", "pta"))
    assert [p["name"] for p in client.get("/projects").json()] == ["mop", "pta"]
    as_caller(key("avhr"))
    assert [p["name"] for p in client.get("/projects").json()] == ["avhr"]
    as_caller(key())  # "*"
    assert len(client.get("/projects").json()) == 6


def test_unknown_project_is_404_for_an_admin(client):
    assert client.get("/ghost/entries").status_code == 404


def test_unknown_project_is_403_for_a_user_without_it(client, as_caller):
    """Not 404: a non-admin can't learn which slugs exist."""
    as_caller(user("mop"))
    assert client.get("/ghost/entries").status_code == 403


def test_inactive_project_is_404_and_hidden(client, session):
    from ediarum_index.models import Project

    row = session.get(Project, "pta")
    row.is_active = False
    session.add(row)
    session.commit()
    assert client.get("/pta/entries").status_code == 404
    assert "pta" not in [p["name"] for p in client.get("/projects").json()]
    assert "pta" in [p["name"] for p in client.get("/projects", params={"include_inactive": True}).json()]


def test_projects_cannot_be_created_or_edited_here(client):
    """The platform owns projects."""
    assert client.post("/projects", json={"name": "x", "label": "X"}).status_code == 405
    assert client.patch("/projects/mop", json={"label": "x"}).status_code in (404, 405)


def test_projects_say_where_the_registers_are_kept_and_who_assigns_ids(client):
    from ediarum_index.main import app

    class Info:
        def __init__(self, led):
            self.index_source_of_truth = led

    class Registry:
        def all(self, force=False):
            return {"avhr": Info("app"), "mop": Info("xml")}

    def by_name():
        return {p["name"]: p for p in client.get("/projects").json()}

    # no registry, no ediarum.id: every project xml-led, no ids assigned
    assert {p["index_source_of_truth"] for p in by_name().values()} == {"xml"}
    assert not any(p["assigns_ids"] for p in by_name().values())

    app.state.projects, app.state.ids = Registry(), object()
    try:
        got = by_name()
        assert got["avhr"]["index_source_of_truth"] == "app"
        assert got["mop"]["index_source_of_truth"] == "xml"
        assert got["pta"]["index_source_of_truth"] == "xml"  # not in the registry: the default
        assert got["avhr"]["registers_from_xml"] is False  # app-led
        assert got["mop"]["registers_from_xml"] is True
        assert all(p["assigns_ids"] for p in got.values())
    finally:
        app.state.projects, app.state.ids = None, None


def test_projects_still_list_when_the_registry_is_down(client):
    from ediarum_index.main import app

    class Down:
        def all(self, force=False):
            raise ConnectionError("down")

    app.state.projects = Down()
    try:
        r = client.get("/projects")
    finally:
        app.state.projects = None
    assert r.status_code == 200
    assert {p["index_source_of_truth"] for p in r.json()} == {None}
    assert {p["registers_from_xml"] for p in r.json()} == {None}


def test_a_project_without_register_files_is_not_xml_registered(client, monkeypatch):
    from ediarum_index import sources

    monkeypatch.setattr(sources, "has_sources", lambda name: name != "pta")
    got = {p["name"]: p for p in client.get("/projects").json()}
    assert got["pta"]["index_source_of_truth"] == "xml"
    assert got["pta"]["registers_from_xml"] is False
    assert got["mop"]["registers_from_xml"] is True

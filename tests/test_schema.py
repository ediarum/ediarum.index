"""Schema layer: /entry-types and /{project}/schema/{type}."""

import pytest

from ediarum_index.schemas import SchemaViolation, resolve_schema, validate_entry


def test_entry_types_in_canonical_order(client):
    names = [t["name"] for t in client.get("/entry-types").json()]
    assert names == ["person", "place", "group", "organisation", "work", "bible_book", "glossary"]


def test_person_base_schema():
    fields = [f.name for f in resolve_schema("person", None)]
    assert fields == [
        "surname",
        "forename",
        "birth_date",
        "birthplace",
        "death_date",
        "deathplace",
    ]


def test_known_type_without_fields_is_empty_not_404(client):
    r = client.get("/mop/schema/work")
    assert r.status_code == 200
    assert r.json() == []


def test_unknown_type_is_404(client):
    assert client.get("/mop/schema/bogus").status_code == 404


def test_project_override_is_merged(client):
    fields = {f["name"]: f for f in client.get("/leibniz5/schema/person").json()}
    # leibniz5 adds a repeatable, typed `idno` field and reorders
    assert "idno" in fields
    assert fields["idno"]["repeatable"] is True
    assert fields["idno"]["qualifier"] == "type"
    names = list(fields)
    assert names.index("forename") < names.index("surname")


def test_pta_names_are_repeatable_multilingual(client):
    fields = {f["name"]: f for f in client.get("/pta/schema/person").json()}
    assert fields["forename"]["repeatable"] is True
    assert fields["forename"]["qualifier"] == "lang"
    assert "grc" in fields["forename"]["qualifier_options"]
    assert fields["surname"]["required"] is False
    assert "birth_date" not in fields


def test_schema_for_unknown_project_is_404(client):
    assert client.get("/nope/schema/person").status_code == 404


def test_schleiermacher_group_schema_has_no_fields(client):
    # `group` has no base schema and schleiermacher declares no override for
    # it either — the family name only ever becomes the entry's label (see
    # ingest._extract_groups), never a form field.
    assert client.get("/schleiermacher/schema/group").json() == []
    assert client.get("/leibniz5/schema/group").json() == []


# --- validate_entry ------------------------------------------------------------
# Wired into services.create_entry / update_entry: a data key that isn't in
# resolve_schema() and isn't declared as a project's extra_keys is a real
# schema/ingest mismatch (a typo'd or drifted field name), not legitimate data.


def test_validate_entry_rejects_unknown_field():
    with pytest.raises(SchemaViolation, match="sruname"):
        validate_entry("person", "leibniz5", {"sruname": "Leibniz"})  # typo


def test_validate_entry_allows_declared_extra_keys():
    # mop's alt_names/old_id aren't form fields (see projects/mop/__init__.py) but are
    # legitimate data the ingest profile writes — must not be rejected as drift.
    validate_entry("person", "mop", {"surname": "X", "alt_names": "Y", "old_id": "Z"})


def test_validate_entry_extra_keys_are_project_scoped():
    # mop's extra_keys must not leak into another project's validation
    with pytest.raises(SchemaViolation):
        validate_entry("person", "leibniz5", {"surname": "X", "alt_names": "Y"})


def test_validate_entry_schleiermacher_group():
    # no fields at all — the family name lives only in the entry's label
    validate_entry("group", "schleiermacher", {})
    with pytest.raises(SchemaViolation):
        validate_entry("group", "schleiermacher", {"head": "Bülow"})


def test_schleiermacher_place_schema(client):
    fields = {
        f["name"]: f
        for f in client.get("/schleiermacher/schema/place").json()
    }
    assert list(fields) == [
        "placename", "alt_names", "place_type", "geonames",
        "idno_other", "note",
    ]
    assert fields["placename"]["required"] is True
    assert fields["alt_names"]["repeatable"] is True
    # the register's own @type values, not the base schema's city/region/…
    assert "street" in fields["place_type"]["options"]
    assert "city" not in fields["place_type"]["options"]
    # other projects keep the unchanged base place schema
    base = [f["name"] for f in client.get("/leibniz5/schema/place").json()]
    assert base == ["placename", "place_type", "lat", "lon"]


def test_validate_entry_schleiermacher_place():
    # geonames is a form field of its own and holds the full URI, not a number
    validate_entry(
        "place",
        "schleiermacher",
        {"placename": "Aachen", "geonames": "https://www.geonames.org/3247449"},
    )
    with pytest.raises(SchemaViolation):
        validate_entry("place", "schleiermacher", {"placename": "Aachen", "lat": 50.7})  # removed
    with pytest.raises(SchemaViolation):
        validate_entry("place", "schleiermacher", {"note": "Fluss"})  # placename is required


# --- the entry types a project uses ------------------------------------------------

ALL_TYPES = ["person", "place", "group", "organisation", "work", "bible_book", "glossary"]


def _types(client, project):
    return [t["name"] for t in client.get(f"/{project}/entry-types").json()]


def test_a_project_lists_only_its_declared_entry_types(client):
    assert _types(client, "avhr") == ["person", "place", "group", "organisation"]


def test_a_project_without_a_declaration_lists_every_type(client):
    assert _types(client, "schleiermacher") == ALL_TYPES
    assert _types(client, "mop") == ALL_TYPES


def test_a_type_with_entries_stays_listed(session, client):
    from ediarum_index.models import Entry

    # e.g. made before the project declared ENTRY_TYPES
    session.add(Entry(project_name="avhr", entry_type="glossary", label="Lemma", data={}))
    session.commit()
    assert _types(client, "avhr") == ["person", "place", "group", "organisation", "glossary"]


def test_an_entry_of_an_undeclared_type_is_refused(client):
    r = client.post("/avhr/entries", json={"entry_type": "bible_book", "label": "Gen", "data": {}})
    assert r.status_code == 422
    assert "bible_book" in r.json()["detail"]
    r = client.post("/avhr/entries", json={"entry_type": "group", "label": "Familie", "data": {}})
    assert r.status_code in (200, 201)


def test_entry_types_are_checked_when_the_projects_load():
    from types import SimpleNamespace

    from ediarum_index.projects import _declared_entry_types

    assert _declared_entry_types(SimpleNamespace(NAME="x")) is None
    with pytest.raises(ValueError, match="bogus"):
        _declared_entry_types(SimpleNamespace(NAME="x", ENTRY_TYPES=["person", "bogus"]))
    with pytest.raises(ValueError, match="place"):
        _declared_entry_types(SimpleNamespace(NAME="x", ENTRY_TYPES=["person"], OVERRIDES={"place": None}))

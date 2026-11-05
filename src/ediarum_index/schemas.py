"""The schema layer: what fields an entry form has, per entry_type and project.

Two code-defined sources, merged at request time:

* ``FIELD_SCHEMAS`` here — the base field list for each ``entry_type``.
* ``PROJECT_OVERRIDES`` from the ``projects`` package — per ``(project,
  entry_type)`` deltas (``add`` / ``modify`` / ``remove`` / ``order``).

Nothing here is persisted. ``resolve_schema`` is what
``GET /{project}/schema/{entry_type}`` returns; the frontend builds the entry
dialog from it.
"""

from functools import lru_cache

from .projects import PROJECT_ENTRY_TYPES, PROJECT_OVERRIDES, SCHEMA_VERSION

from .models import (
    ENTRY_TYPES,
    FieldSchema,
    SchemaOverride,
)

_ENTRY_TYPE_NAMES = {name for name, _ in ENTRY_TYPES}
# canonical tab / display order for entry types
ENTRY_TYPE_ORDER = {name: i for i, (name, _) in enumerate(ENTRY_TYPES)}


def entry_types_for(project: str) -> tuple[str, ...]:
    """The entry types ``project`` uses, in canonical order: its module's
    ``ENTRY_TYPES``, or every type when it declares none (or has no module)."""
    declared = PROJECT_ENTRY_TYPES.get(project)
    if declared is None:
        return tuple(name for name, _ in ENTRY_TYPES)
    return tuple(sorted(declared, key=ENTRY_TYPE_ORDER.__getitem__))

FIELD_SCHEMAS: dict[str, list[FieldSchema]] = {
    "person": [
        FieldSchema(name="surname", label="Surname", type="text"),
        FieldSchema(name="forename", label="Forename", type="text"),
        # free text on purpose: "1809", "nach 1824", "um 1810", "3. Jh." are all
        # valid. Ordering uses the derived Entry.birth_sort / death_sort columns
        # (see dates.py); ?sort_by=birth_date / death_date.
        FieldSchema(name="birth_date", label="Birth date", type="text"),
        FieldSchema(name="birthplace", label="Birthplace", type="reference", ref_type="place"),
        FieldSchema(name="death_date", label="Death date", type="text"),
        FieldSchema(name="deathplace", label="Deathplace", type="reference", ref_type="place"),
    ],
    "place": [
        FieldSchema(name="placename", label="Placename", type="text"),
        FieldSchema(name="place_type", label="Type", type="select", options=["city", "region", "country", "building"]),
        FieldSchema(name="lat", label="Latitude", type="number"),
        FieldSchema(name="lon", label="Longitude", type="number"),
    ],
    "organisation": [
        FieldSchema(name="orgname", label="Organisation", type="text"),
        FieldSchema(name="org_type", label="Type", type="text"),
        FieldSchema(name="place", label="Place", type="reference", ref_type="place"),
    ]
}

def _merge(base: list[FieldSchema], ov: SchemaOverride) -> list[FieldSchema]:
    """Apply ``ov`` (remove, then modify, then add, then reorder) to ``base``.

    Raises ``ValueError`` if the override modifies a missing field or re-adds an
    existing one. Fields not named in ``ov.order`` keep their relative position
    after the ordered ones.
    """
    fields = {f.name: f for f in base}

    for name in ov.remove:
        fields.pop(name, None)

    for name, patch in ov.modify.items():
        if name not in fields:
            raise ValueError(f"override modifies unknown field {name!r}")
        fields[name] = fields[name].model_copy(update=patch)

    for f in ov.add:
        if f.name in fields:
            raise ValueError(f"override re-adds existing field {f.name!r}")
        fields[f.name] = f

    ordered = list(fields.values())
    if ov.order:
        rank = {n: i for i, n in enumerate(ov.order)}
        ordered.sort(key = lambda f: rank.get(f.name, len(rank)))
    return ordered

@lru_cache(maxsize=256)
def resolve_schema(
    entry_type: str, project: str | None, _v: int = SCHEMA_VERSION
) -> tuple[FieldSchema, ...]:
    """Return the merged field list for ``entry_type`` (+ project override).

    A known ``entry_type`` (one of ``models.ENTRY_TYPES``) with no configured
    fields yet — e.g. ``group``, ``work`` — returns an empty tuple rather than
    erroring. ``KeyError`` is raised only for an entry type that does not exist.
    ``project=None`` (or a project with no module in ``projects/``) returns
    the base schema unchanged; whether the project exists is checked by the route
    against the DB. Cached; ``_v`` ties the cache to ``SCHEMA_VERSION``.
    """
    if entry_type not in _ENTRY_TYPE_NAMES:
        raise KeyError(entry_type)
    base = FIELD_SCHEMAS.get(entry_type, [])
    ov = PROJECT_OVERRIDES.get((project, entry_type)) if project else None
    return tuple(_merge(base, ov)) if ov else tuple(base)

class SchemaViolation(ValueError):
    "``data`` doesn't fit the schema (``services`` answers it with a 422)."


def validate_entry(entry_type: str, project: str, data: dict) -> None:
    """Reject ``data`` if it has an unknown or a missing-required field.

    Called from ``services.create_entry`` / ``update_entry``, so a typo'd or drifted
    ``ingest.py`` field name (or a hand-edited payload) is rejected instead of
    written silently. "Unknown" excludes each project's declared
    ``extra_keys`` — data the ingest/export profiles legitimately read and
    write but that isn't a form field (see ``SchemaOverride.extra_keys``), e.g.
    mop's ``alt_names``/``old_id`` or avhr's ``gnd``/``viaf``/``wikidata``.
    ``KeyError`` propagates from ``resolve_schema`` for an unknown
    ``entry_type`` — callers should turn that into a 422.
    """
    schema = resolve_schema(entry_type, project)
    known = {f.name for f in schema}
    ov = PROJECT_OVERRIDES.get((project, entry_type))
    extra = set(ov.extra_keys) if ov else set()
    if unknown := set(data) - known - extra:
        raise SchemaViolation(f"Unknown fields: {sorted(unknown)}")
    for f in schema:
        if f.required and data.get(f.name) in (None, "", []):
            raise SchemaViolation(f"Missing required field: {f.name}")

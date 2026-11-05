"""Project definition, auto-discovered by ``projects/__init__.py`` on backend start.

The project itself comes from the ediarum.platform's project registry; this
module holds what ediarum.index keeps per project, so adding one needs **no
database migration** and **no edits to the routes / schemas.py**.

Contract:
  * ``NAME``         - the platform's project slug ([a-z][a-z0-9-]*); this file
                       is named after it, with "-" spelled "_".
  * ``LABEL``        - display name, used only without a platform registry.
  * ``DESCRIPTION``  - optional, stored when the project row is created.
  * ``REGISTER_DIR`` - optional, for a project ingested from its TEI registers.
  * ``ENTRY_TYPES``  - optional, the entry types the project uses (its tabs), from
                       ``models.ENTRY_TYPES``. Without it the project offers all
                       of them. New entries of other types are refused (422).
  * ``OVERRIDES``    - maps an ``entry_type`` to a ``SchemaOverride``. Only
                       list the types that deviate from ``schemas.FIELD_SCHEMAS``;
                       an empty dict means "use the base schema unchanged".

Files whose name starts with ``_`` (like this one) are ignored by the loader.
"""

from ..models import FieldSchema, SchemaOverride  # noqa: F401  (FieldSchema used once you add fields)

NAME = "_template"
LABEL = "_template"          # display name; used only without a platform registry
DESCRIPTION = None           # optional str, seeded into project.description

# Only for a project whose entries are ingested from its TEI registers: where
# they are inside the project's repository, which ediarum.fileservice checks
# out at XML_MOUNT_ROOT/<slug>/ (its git URL and branch are configured in the
# platform's project registry, not here). The ingest profiles' "source" globs
# are relative to it — see ../sources.py and docs/ingest/sources.md.
# Leave commented out for a project edited only in the app.
# REGISTER_DIR = "data/Register"

# The entry types this project uses: only these get a tab, and new entries of
# other types are refused. Leave commented out to offer every type. A type that
# already has entries in the project stays listed regardless.
# ENTRY_TYPES = ["person", "place", "organisation"]

OVERRIDES: dict[str, SchemaOverride] = {
    # "person": SchemaOverride(
    #     add=[
    #         FieldSchema(name="gnd", label="GND ID", type="text"),
    #     ],
    #     modify={"surname": {"label": "Family name"}},
    #     remove=["deathplace"],
    #     order=["forename", "surname", "gnd"],
    # ),
}

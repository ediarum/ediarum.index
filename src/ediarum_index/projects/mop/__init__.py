from ...models import FieldSchema, SchemaOverride

NAME = "mop"
LABEL = "Akten der preußischen Monarchie – Personenregister"
DESCRIPTION = None

# where the registers are inside the project's repository (checked out by
# ediarum.fileservice at XML_MOUNT_ROOT/<slug>/); the ingest profiles' "source"
# globs are relative to it — see sources.py
REGISTER_DIR = "data/Register"

# keys must match the "mop" profile in ingest.py
OVERRIDES: dict[str, SchemaOverride] = {
    "person": SchemaOverride(
        add=[
            FieldSchema(
                name="idno",
                label="Identifiers",
                type="text",
                repeatable=True,
                qualifier="type",
                qualifier_options=["uri"],
            ),
            FieldSchema(name="note", label="Note", type="text", multiline=True),
        ],
        order=["forename", "surname", "birth_date", "death_date", "idno", "note"],
        # `alt_names` and `old_id` are captured by the ingest/export profiles and
        # shown read-only in the entry view; neither is a form field (`alt_names`
        # holds structured name records, not a scalar; `old_id` is legacy
        # provenance) — see backend/ingest.py. Declared here so
        # schemas.validate_entry doesn't reject them as drift.
        extra_keys=["alt_names", "old_id"],
    ),
}

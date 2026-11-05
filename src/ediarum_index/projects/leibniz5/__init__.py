from ...models import FieldSchema, SchemaOverride

NAME = "leibniz5"
LABEL = "Leibniz-Edition, Reihe V"
DESCRIPTION = None

# where the registers are inside the project's repository (checked out by
# ediarum.fileservice at XML_MOUNT_ROOT/<slug>/); the ingest profiles' "source"
# globs are relative to it — see sources.py
REGISTER_DIR = "data/Register"

# entry_type -> SchemaOverride; only where leibniz5 deviates from schemas.FIELD_SCHEMAS
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
        ],
        order=["forename", "surname", "birth_date", "death_date", "idno"],
    ),
}

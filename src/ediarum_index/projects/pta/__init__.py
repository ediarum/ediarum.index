from ...models import FieldSchema, SchemaOverride

NAME = "pta"
LABEL = "Patristic Text Archive – Personenregister"
DESCRIPTION = None

# where the registers are inside the project's repository (checked out by
# ediarum.fileservice at XML_MOUNT_ROOT/<slug>/); the ingest profiles' "source"
# globs are relative to it — see sources.py
REGISTER_DIR = "data/Register"

_LANGS = ["deu", "eng", "lat", "grc"]

# Patristic persons: no birth/death (dated by <floruit>), often no surname,
# multilingual names (repeatable, qualifier "lang"), typed external ids
# (repeatable, qualifier "type"). Keys match the "pta" profile in ingest.py.
OVERRIDES: dict[str, SchemaOverride] = {
    "person": SchemaOverride(
        modify={
            "surname": {"required": False, "repeatable": True, "qualifier": "lang",
                        "qualifier_options": _LANGS},
            "forename": {"repeatable": True, "qualifier": "lang", "qualifier_options": _LANGS},
        },
        remove=["birth_date", "death_date", "birthplace", "deathplace"],
        add=[
            FieldSchema(name="epithet", label="Epithet", type="text",
                        repeatable=True, qualifier="lang", qualifier_options=_LANGS),
            FieldSchema(name="floruit", label="Floruit", type="text"),
            FieldSchema(name="idno", label="Identifiers", type="text",
                        repeatable=True, qualifier="type",
                        qualifier_options=["GND", "TLG", "WIKIDATA", "PTATG"]),
            FieldSchema(name="note", label="Note", type="text", multiline=True),
        ],
        order=["forename", "surname", "epithet", "floruit", "idno", "note"],
    ),
}

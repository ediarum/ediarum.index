"""Marx-Engels-Gesamtausgabe — Personenregister
Entfernte Felder:
* Geburts- und Sterbeort: ``birthplace`` und ``deathplace`` der Basis kommen in diesem Register nicht vor.

Anpassungen gegenüber dem Basisschema:
* Personennamen: ``persName[@type='reg']`` enthält entweder ``surname``+``forename`` oder
  einen ungeteilten Namen in ``name``, daher ist die Angabe eines Nachnamens hier nicht verpflichtend.
* Vorname: Anpassen des Labels.
* Geburts- und Sterbejahr: ``birth``/``death`` sind meist eine Jahreszahl, da in einigen Fällen aber weitere
  Informationen in Textform ("ca. 1822", "241 v. Chr.", "1814 oder 1815") enthalten sind, wird ein Textfeld verwendet.

Hinzugefügte Felder:
* Ungegliederter Name: ``name`` nimmt den nicht in Vor- und Nachname zerlegbaren Namen aus
  ``persName[@type='reg']`` auf.
* Wirkungszeitraum: ``floruit`` als Textfeld, da die Angabe in Textform vorliegen kann.
* Wirkungszeitraum nicht vor / nicht nach: ``floruit_notbefore`` und ``floruit_notafter`` bilden die
  Attribute ``@notBefore``/``@notAfter`` ab; meist volle ISO-Daten, vereinzelt reine Jahreszahlen oder
  negative Angaben, daher Textfelder.
* Geschlecht: ``sex`` als Auswahlfeld mit den im Register verwendeten Werten ``female``, ``male``,
  ``unknown`` und ``intersex``.
* Beleg zum Geschlecht: ``sex_evidence`` hält fest, woraus die Angabe zum Geschlecht erschlossen wurde;
  im Register durchgängig ``assigned``.
* Rolle: ``role`` als Auswahlfeld, das nicht-historische Personen als ``mythological`` oder
  ``fictional`` kennzeichnet.
* Interne ID: Nutzung der ``@xml:id`` des Eintrags zu einer Person.
* MEGA-Registernummer: ``mega_id`` aus ``idno[@type='mega']``; nicht eindeutig, vereinzelt doppelt
  vergeben oder mehrfach an einer Person angegeben (dann mit ``"; "`` verbunden).
* GND-ID, VIAF-ID: ``gnd`` und ``viaf`` werden in separate Felder geschrieben.
* Normdaten-URIs: ``idno_other`` enthält alle ``idno[@type='uri']``, damit auch die seltenen BNF-, ISNI-
  und IdRef-Links sowie vereinzelten Freitext, die kein eigenes Feld besitzen.
* Frühere ID: ``old_id`` dokumentiert die vor der Migration vergebene Kennung (``pdrPo.…`` bzw. ``ed_…``).
* Anmerkung: ``note`` für biografische Angaben zur Person.
* Belegstellen: ``references`` verzeichnet die Stellen in den Bänden, die einen Bezug zur betrachteten Person haben.

Keine Formularfelder (``extra_keys``):
* ``alt_names`` / ``birth_names`` / ``pseudonyms`` sammeln abweichende Namensformen
  (``persName[@type='alt']``, nach ``@subtype`` sortiert — ohne Angabe oder unbekannt landet in
  ``alt_names``) als Liste von ``{surname, forename}`` bzw. ``{value}`` (``ingest._alt_names``, geteilt
  mit Schleiermacher). Kein Textfeld: die Form ist nicht darstellbar, und über das Formular bearbeitet
  ginge bei einem geteilten Namen der Vor-/Nachname-Split verloren, siehe ``docs/ingest/mega.md``.
"""

from ...models import FieldSchema, SchemaOverride

NAME = "mega"
LABEL = "Marx-Engels-Gesamtausgabe"
DESCRIPTION = "Personenregister der Marx-Engels-Gesamtausgabe (MEGA)"

# where the registers are inside the project's repository (checked out by
# ediarum.fileservice at XML_MOUNT_ROOT/<slug>/); the ingest profiles' "source"
# globs are relative to it — see sources.py
REGISTER_DIR = "data/Register"

OVERRIDES: dict[str, SchemaOverride] = {
    "person": SchemaOverride(
        remove=["birthplace", "deathplace"],
        modify={
            "surname": {"label": "Nachname", "required": False},
            "forename": {"label": "Vorname"},
            "birth_date": {"label": "Geburtsdatum"},
            "death_date": {"label": "Sterbedatum"},
        },
        add=[
            FieldSchema(name="name", label="Ungegliederter Name", type="text"),
            FieldSchema(name="internal_id", label="Interne ID", type="text"),
            FieldSchema(name="mega_id", label="MEGA-Registernummer", type="text"),
            FieldSchema(name="floruit", label="Wirkungszeitraum", type="text"),
            FieldSchema(name="floruit_notbefore", label="Wirkungszeitraum nicht vor", type="text"),
            FieldSchema(name="floruit_notafter", label="Wirkungszeitraum nicht nach", type="text"),
            FieldSchema(
                name="sex",
                label="Geschlecht",
                type="select",
                options=["female", "male", "unknown", "intersex"],
            ),
            FieldSchema(name="sex_evidence", label="Beleg zum Geschlecht", type="text"),
            FieldSchema(
                name="role",
                label="Rolle",
                type="select",
                options=["mythological", "fictional"],
            ),
            FieldSchema(name="gnd", label="GND-ID", type="text"),
            FieldSchema(name="viaf", label="VIAF-ID", type="text"),
            FieldSchema(name="idno_other", label="Normdaten-URIs", type="text"),
            FieldSchema(name="old_id", label="Frühere ID", type="text"),
            FieldSchema(name="note", label="Anmerkung", type="text", multiline=True),
            FieldSchema(name="references", label="Belegstellen", type="text"),
        ],
        # alt_names/birth_names/pseudonyms aren't form fields — see the
        # "Keine Formularfelder" note above and docs/ingest/mega.md — but ingest
        # legitimately writes them, so validate_entry mustn't reject them
        extra_keys=["alt_names", "birth_names", "pseudonyms"],
        order=[
            "name",
            "surname",
            "forename",
            "birth_date",
            "death_date",
            "floruit",
            "floruit_notbefore",
            "floruit_notafter",
            "sex",
            "sex_evidence",
            "role",
            "internal_id",
            "mega_id",
            "gnd",
            "viaf",
            "idno_other",
            "old_id",
            "note",
            "references",
        ],
    ),
}

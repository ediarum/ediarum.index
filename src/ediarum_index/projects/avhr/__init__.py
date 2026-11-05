"""edition humboldt digital — Personen-, Orts- und Einrichtungsregister

== Personen ==
Entfernte Felder:
* Geburts- und Sterbeort: ``birthplace`` und ``deathplace`` der Basis kommen in diesem Register nicht vor.

Anpassungen gegenüber dem Basisschema:
* Personennamen: ``persName[@type='reg']`` enthält entweder ``surname``+``forename`` oder
  ein ungeteilten Namen oder ein Mononym in ``name``, daher ist die Angabe eines Nachnamens hier nicht verpflichtend.
* Vorname: Anpassen des Labels.
* Geburts- und Sterbejahr:``birth``/``death`` sind meist eine Jahreszahl, da in einigen Fällen aber weitere
  Informationen in Textform ("ca. 460", "63 v. Chr.", "1778/1780") enthalten sind, wird ein Textfeld verwendet.

Hinzugefügte Felder:
* Ungegliederter Name: ``name`` nimmt den nicht in Vor- und Nachname zerlegbaren Namen bzw. das
  Mononym aus ``persName[@type='reg']`` auf.
* Wirkungszeitraum: ``floruit`` als Textfeld, da die Angabe in Textform vorliegen können.
* Wirkungszeitraum nicht vor / nicht nach: ``floruit_notbefore`` und ``floruit_notafter`` bilden die
  Attribute ``@notBefore``/``@notAfter`` für unscharfe Zeitgrenzen ab.
* Geschlecht: ``sex`` als Auswahlfeld mit den in ``persName``/``person`` verwendeten Werten
  ``female``, ``male`` und ``unknown``.
* Beleg zum Geschlecht: ``sex_evidence`` hält fest, woraus die Angabe zum Geschlecht erschlossen wurde.
* Rolle: ``role`` als Auswahlfeld, das nicht-historische Personen als ``mythological`` oder
  ``fictional`` kennzeichnet.
* Keine eigene interne ID: die ``@xml:id`` des Eintrags ist seine Projekt-ID (``source_id``).
* GND-ID, VIAF-ID, Wikidata-ID: ``gnd``, ``viaf`` und ``wikidata`` sind aus ``idno_other``
  abgeleitete Anzeigefelder (keine Formularfelder, ``extra_keys``), ``idno_other`` bleibt die
  Quelle für den Export.
* Normdaten-URIs: ``idno_other`` für weitere Identifier, die selten vorkommen und kein eigenes Feld besitzen.
* Frühere ID: ``old_id`` dokumentiert die vor der Migration vergebene Kennung.
* Dublette zu: ``duplicate_of`` verweist auf den Eintrag, mit dem der Datensatz zusammenfällt.
* Anmerkung: ``note`` für biografische Angaben zur Person.
* Zuständigkeit für die Anmerkung: ``note_resp``-Angabe zur Anmerkung.
* Verantwortung Eintrag: ``resp`` nennt die für den Registereintrag im Gesamten verantwortliche Person.
* Belegstellen: ``references`` verzeichnet die Stellen in den Quellen, die einen Bezug zur betrachteten Person haben.
* Verweise in der Anmerkung: ``persName``/``placeName``/``orgName[@key]`` in ``note`` werden zu
  ``mentions``-Relationen auf den Personen-, Orts- bzw. Einrichtungseintrag (mit der genauen Textposition)
  und beim Export wieder in die Anmerkung eingesetzt.

== Orte ==
Basisschema ``place`` mit Anpassungen (``Orte/*.xml``):
* Entfernte Felder: ``lat`` und ``lon``; Koordinaten stehen nur über die GeoNames-URI zur Verfügung.
* Art des Ortes: ``place_type`` übernimmt die im Register belegten ``@type``-Werte.
* Hinzugefügt: ``alt_names`` (``placeName[@type='alt']``, wiederholbar, mit ``@subtype``), ``geonames``
  (jede ``idno[@type='uri']`` mit ``geonames.org``), ``idno_other`` (die übrigen ``idno``), ``note`` (als
  Text; Verweise darin werden zu ``mentions``-Relationen) mit ``note_resp``, ``old_id``,
  ``resp``, ``role`` und ``references`` (``linkGrp/ptr``, wie bei den Personen).
* Untergeordnete Orte (``place/listPlace/place``) bleiben eigene ``place``-Einträge mit einer
  ``part_of``-Relation auf den übergeordneten Ort.

== Einrichtungen ==
Basisschema ``organisation`` mit Anpassungen (``Einrichtungen.xml``):
* Entfernte Felder: ``org_type`` und ``place``.
* Hinzugefügt: ``alt_names`` (``orgName[@type='alt']``, wiederholbar), ``idno_uri`` (``idno[@type='uri']``),
  ``description`` (``desc``, als Text; Verweise darin werden zu ``mentions``-Relationen),
  ``old_id`` und ``references``.
* Nicht übernommen: ``location/address`` (GeoNames-``idno``, ``settlement[@key]``, Adress-``note``).
"""

from ...models import FieldSchema, SchemaOverride

NAME = "avhr"
LABEL = "edition humboldt digital"
DESCRIPTION = "Personen-, Orts- und Einrichtungsregister der edition humboldt digital"

# where the registers are inside the project's repository (checked out by
# ediarum.fileservice at XML_MOUNT_ROOT/<slug>/); the ingest profiles' "source"
# globs are relative to it — see sources.py
REGISTER_DIR = "data/Register"

# the entry types this edition uses (its tabs); no works, Bible books or glossary
ENTRY_TYPES = ["person", "place", "group", "organisation"]

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
            FieldSchema(name="floruit", label="Wirkungszeitraum", type="text"),
            FieldSchema(name="floruit_notbefore", label="Wirkungszeitraum nicht vor", type="text"),
            FieldSchema(name="floruit_notafter", label="Wirkungszeitraum nicht nach", type="text"),
            FieldSchema(
                name="sex",
                label="Geschlecht",
                type="select",
                options=["female", "male", "unknown"],
            ),
            FieldSchema(name="sex_evidence", label="Beleg zum Geschlecht", type="text"),
            FieldSchema(
                name="role",
                label="Rolle",
                type="select",
                options=["mythological", "fictional"],
            ),
            FieldSchema(name="idno_other", label="Normdaten-URIs", type="text"),
            FieldSchema(name="old_id", label="Frühere ID", type="text"),
            FieldSchema(name="duplicate_of", label="Dublette zu", type="text"),
            FieldSchema(name="note", label="Anmerkung", type="text", multiline=True),
            FieldSchema(name="note_resp", label="Verantwortung Anmerkung", type="text"),
            FieldSchema(name="resp", label="Verantwortung Eintrag", type="text"),
            FieldSchema(name="references", label="Belegstellen", type="text"),
        ],
        # `alt_names` is captured by the ingest/export profiles and shown read-only
        # in the entry view; it is not a form field (it holds structured name
        # records, not a scalar) — see backend/ingest.py, same as mop's.
        #
        # `gnd` / `viaf` / `wikidata` aren't form fields either: they're display
        # views ingest derives from `idno_other` by regex, not their own source of
        # truth, so an edit to them alone wouldn't reach the export — see
        # export.EXPORT["avhr"]. Edit `idno_other` (the actual `<idno>` list) instead.
        #
        # All four declared below so schemas.validate_entry doesn't reject them
        # as drift.
        extra_keys=["alt_names", "gnd", "viaf", "wikidata"],
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
            "idno_other",
            "old_id",
            "duplicate_of",
            "note",
            "note_resp",
            "resp",
            "references",
        ],
    ),
    # Ortsregister (Orte/*.xml) — see the "Orte" section of the module docstring.
    "place": SchemaOverride(
        remove=["lat", "lon"],
        modify={
            "placename": {"label": "Ortsname"},
            "place_type": {
                "label": "Art des Ortes",
                # exactly the @type values the register uses
                "options": [
                    "building",
                    "district",
                    "street",
                    "park",
                    "mine",
                    "mountain",
                    "sea",
                    "monument",
                    "mythological",
                    "others",
                ],
            },
        },
        add=[
            FieldSchema(
                name="alt_names",
                label="Alternativbezeichnung",
                type="text",
                repeatable=True,
                qualifier="subtype",
                qualifier_options=["contemporary"],
            ),
            FieldSchema(name="geonames", label="GeoNames-URI", type="text"),
            FieldSchema(name="idno_other", label="Normdaten-URIs", type="text"),
            FieldSchema(name="note", label="Anmerkung", type="text", multiline=True),
            FieldSchema(name="note_resp", label="Verantwortung Anmerkung", type="text"),
            FieldSchema(name="old_id", label="Frühere ID", type="text"),
            FieldSchema(name="resp", label="Verantwortung Eintrag", type="text"),
            FieldSchema(
                name="role",
                label="Rolle",
                type="select",
                options=["mythological", "fictional"],
            ),
            FieldSchema(name="references", label="Belegstellen", type="text"),
        ],
        order=[
            "placename",
            "alt_names",
            "place_type",
            "geonames",
            "idno_other",
            "note",
            "note_resp",
            "old_id",
            "resp",
            "role",
            "references",
        ],
    ),
    # Einrichtungen (Einrichtungen.xml) — see the "Einrichtungen" section of the module docstring.
    "organisation": SchemaOverride(
        remove=["org_type", "place"],
        modify={"orgname": {"label": "Name"}},
        add=[
            FieldSchema(
                name="alt_names",
                label="Alternativbezeichnung",
                type="text",
                repeatable=True,
            ),
            FieldSchema(name="idno_uri", label="Normdaten-URI", type="text"),
            FieldSchema(name="description", label="Beschreibung", type="text"),
            FieldSchema(name="old_id", label="Frühere ID", type="text"),
            FieldSchema(name="references", label="Belegstellen", type="text"),
        ],
        order=[
            "orgname",
            "alt_names",
            "idno_uri",
            "description",
            "old_id",
            "references",
        ],
    ),
}

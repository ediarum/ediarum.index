"""Schleiermacher in Berlin — Personen-, Orts- und Körperschaftsregister, Glossar, Werke, Bibelbücher

== Personen ==
Entfernte Felder:
* Geburts- und Sterbeort: ``birthplace`` und ``deathplace`` der Basis kommen in diesem Register nicht als
  eigene Angaben vor; Orte stehen, wo vorhanden, im Freitext von ``birth``/``death``.

Anpassungen gegenüber dem Basisschema:
* Personennamen: ``persName[@type='reg']`` enthält fast immer ``surname``+``forename``, vereinzelt einen
  ungeteilten Namen in ``name``, daher ist die Angabe eines Nachnamens hier nicht verpflichtend.
* Vorname: Anpassen des Labels; ``forename`` enthält auch Namenspartikel (z. B. ``Gustav Andreas von``).
* Geburt und Tod: ``birth``/``death`` sind Freitext mit heterogener Schreibung und teils
  angefügtem Ort ("30. November 1765 (Roxheim)", "6.8.1813", "1814 od 1815"), daher wird ein Textfeld
  mit den Labels "Geburt" und "Tod" verwendet.

Hinzugefügte Felder:
* Ungegliederter Name: ``name`` nimmt den nicht in Vor- und Nachname zerlegbaren Namen aus
  ``persName[@type='reg']`` auf.
* Rufname: ``used_name`` hebt den gebräuchlichen Vornamen (``forename/name[@type='used']``) hervor;
  er bleibt zugleich Teil des Vornamens, falls er dort bereits genannt wurde.
* Namenszusatz: ``name_link`` nimmt ``persName[@type='reg']/nameLink`` auf; im Register kommt das Element
  bisher nur leer vor.
* Geschlecht: ``sex`` als Auswahlfeld mit den im Register verwendeten Werten ``female`` und ``male``.
* Beleg zum Geschlecht: ``sex_evidence`` hält fest, woraus die Angabe zum Geschlecht erschlossen wurde
  (``assigned``, ``selfIdentification``).
* Verantwortung Geschlecht: ``sex_resp`` nennt, wer die Angabe gemacht hat (``#gendertagger``, ``#fko``).
* Sicherheit Geschlecht: ``sex_cert`` als Auswahlfeld mit ``high`` und ``low``.
* Rolle: ``role`` als Auswahlfeld, das nicht-historische Personen als ``mythological`` kennzeichnet.
* Heirat: ``wedding`` aus ``event[@type='wedding']/@when``; Freitextfeld.
* Anmerkung zur Heirat: ``wedding_note`` aus ``event/note``.
* GND-ID, VIAF-ID: ``gnd`` und ``viaf`` werden in separate Felder geschrieben.
* Normdaten-URIs: ``idno_other`` enthält die ``idno[@type='uri']`` unverändert.
* Anmerkung: ``note`` für biografische Angaben zur Person.

Keine Formularfelder (``extra_keys``):
* ``alt_names`` / ``birth_names`` / ``pseudonyms`` sammeln abweichende Namensformen
  (``persName[@type='alt']``, nach ``@subtype`` sortiert — ohne Angabe oder unbekannt landet in
  ``alt_names``) als Liste von ``{surname, forename}`` bzw. ``{value}`` (``ingest._alt_names``).
  Kein Textfeld, da in der aktuellen Listenform nicht darstellbar (siehe ``docs/ingest/schleiermacher.md``).

``group`` — Familien/Gruppen:
* Eine ``listPerson[@type='group']`` wird als eigener ``group``-Eintrag angelegt (nicht als Textfeld
  am Personeneintrag, siehe ``ingest.ingest_schleiermacher_groups``); der Familienname aus ``head``
  wird nur zum Label des Eintrags, es gibt kein eigenes Formularfeld dafür. Mitgliedschaft läuft
  über ``member_of``-Relationen (``person`` → ``group``) (siehe ``docs/ingest/schleiermacher.md``).

== Orte ==
Entfernte Felder:
* Koordinaten: ``lat`` und ``lon`` der Basis kommen im Register nicht vor; die Verortung läuft
  ausschließlich über die GeoNames-URI in ``idno[@type='uri']``.

Anpassungen gegenüber dem Basisschema:
* Ortsname: ``placeName[@type='reg']`` ist in allen Einträgen vorhanden, daher ``required``;
  das Label wird auf "Ortsname" gesetzt.
* Art des Ortes: ``place_type`` übernimmt die im Register tatsächlich belegten ``@type``-Werte
  (``building``, ``district``, ``street``, ``park``, ``forest``, ``mountain``, ``sea``,
  ``monument``, ``others``) statt der Basisoptionen.

Hinzugefügte Felder:
* Alternativbezeichnungen: ``alt_names`` nimmt die ``placeName[@type='alt']`` auf.
* GeoNames-URI: ``geonames`` nimmt jede ``idno[@type='uri']`` vollständig auf, die ``geonames.org`` enthält.
  Eine Vereinheitliung wird nicht durchgeführt.
* Normdaten-URIs: ``idno_other`` enthält jede übrige ``idno[@type='uri']``.
* Anmerkung: ``note`` für die Kurzcharakterisierung des Ortes ("Fluss", "Ort am Harz").

Untergeordnete Orte:
* Ein verschachteltes ``place/listPlace/place`` (Gebäude, Stadtteil, Straße innerhalb eines Ortes)
  wird **nicht** als Feld abgelegt, sondern bleibt ein eigener ``place``-Eintrag und bekommt eine
  ``part_of``-Relation auf den übergeordneten Ort ``place`` → ``place`` (siehe 
  ``ingest.ingest_schleiermacher_place_nesting`` und ``docs/ingest/schleiermacher.md``).

== Körperschaften ==
Basisschema ``organisation`` mit Anpassungen:
* Entfernte Felder: ``org_type`` und ``place`` kommen im Register nicht vor.
* Name: ``orgName[@type='reg']`` ist in jedem Eintrag genau einmal vorhanden, daher ``orgname`` Pflichtfeld.
* Hinzugefügt: ``alt_names`` (``orgName[@type='alt']``, wiederholbar), ``idno_uri`` (``idno[@type='uri']``
  und ``description`` (``desc``, als Text; ``persName[@key]`` darin  werden zu ``mentions``-Relationen).
* Übergeordnete Institution: ein verschachteltes ``listOrg`` mit ``head`` wird wie eine Familie im
  Personenregister ein eigener ``group``-Eintrag (Label = ``head``) mit ``member_of``-Relationen
  ``organisation`` → ``group``; es gibt kein Formularfeld dafür.

== Glossar ==
Eigener Eintragstyp ``glossary`` ohne Basisschema.
* ``term`` = ``label[@type='reg']`` (Pflicht, zugleich Label); ``term_lang`` = dessen ``@xml:lang``
  (``deu``, bei 4 Einträgen); ``alt_names`` = ``label[@type='alt']``.
* ``desc`` / ``desc_resp``: kürzere Beschreibung und ``@resp`` (verbatim, z. B. ``#FK``).
* ``note`` / ``note_resp``: Erläuterung (die ``p``-Absätze als Text, ohne den Quellenabsatz) und ``@resp``
  (verbatim; ``FS`` kommt ohne ``#`` vor). ``persName[@key]`` darin werden zu ``mentions``-Relationen.
* ``source``: ``note/p[@type='source']``.
* ``category``: ``interp/@id`` ohne ``#`` (``instrument``, ``christliche_sitte``).

== Werke ==
Eintragstyp ``work`` ohne Basisschema.
* ``title`` = ``bibl/title``, zugleich Label.
* ``work_type`` = ``bibl/@type``.
* ``pub_place`` = ``pubPlace`` (Freitext) und ``pub_place_key`` = dessen ``@key``, die ``xml:id`` des
  Ortes im Ortsregister; ``date`` = ``date`` verbatim, z. B. "(1815)" oder "(1798-1848)";
  ``note`` = ``note`` als Text (``persName``/``placeName[@key]`` darin werden zu ``mentions``-Relationen).
* Verfasser/Herausgeber: ``authors`` / ``editors`` sind keine Formularfelder (``extra_keys``), sondern
  Listen von ``{surname, forename | name | orgname, key, role}`` (``ingest._contributors``): der Name
  steht mal in ``surname``+``forename``, mal in einem ``name`` ("Anonym", "et al."), ``key`` verweist auf
  das Personenregister, bei ``role`` kommt nur ``translation`` als Wert vor. Ein leeres
  ``persName`` ("Verfasser unbekannt") bleibt als ``{"unknown": true}`` erhalten. Die Verweise sind
  keine Relationen, sondern liegen in diesen Listen.
* Autorengruppen: ``listBibl[@type='group']`` mit ``head`` wird wie eine Familie im Personenregister
  ein ``group``-Eintrag (Label = ``head``) mit ``member_of``-Relationen ``work`` → ``group``.
* Ein ``bibl`` *innerhalb* eines ``title`` (``@sameAs``, ohne ``xml:id``) ist Teil des Titeltexts und
  kein eigener Eintrag.
* Nicht übernommen: die auskommentierte ``idno[@type='uri']``.

== Bibelbücher (bibelsystematik.xml) ==
Eigener Eintragstyp ``bible_book``. Kein Basisschema, ``OVERRIDES["bible_book"]`` ist daher das gesamte Schema.

* Name: ``label[@unit='name']`` ist Label des Eintrags und Feld ``name``.
* Kanonteil: ``canon_part`` (Auswahl ``AT``/``AP``/``NT``) aus ``list/@type``; die Langbezeichnung
  ("Altes Testament") steht nur im ``label`` der Liste und wird nicht gespeichert.
* Position: ``position`` aus ``item/@n``.
* Sigle: ``sigle`` aus ``idno``. Nicht eindeutig (``Jud`` kommt zweimal vor), daher ist die
  ``source_id`` die Position im Register ``bibelsystematik:<n>`` und nicht die Sigle.
* Abkürzung/Zweitname/Zweitabkürzung: ``abbr``, ``name2``, ``abbr2``.
* Gruppierung: ``group_a``/``group_b``/``group_c`` aus ``label[@unit='gruppea|gruppeb|gruppec']``;
  leere Elemente entfallen.
"""

from ...models import FieldSchema, SchemaOverride

NAME = "schleiermacher"
LABEL = "Schleiermacher"
DESCRIPTION = "Register der Schleiermacher-Edition"

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
            "birth_date": {"label": "Geburt"},
            "death_date": {"label": "Tod"},
        },
        add=[
            FieldSchema(name="name", label="Ungegliederter Name", type="text"),
            FieldSchema(name="used_name", label="Rufname", type="text"),
            FieldSchema(name="name_link", label="Namenszusatz", type="text"),
            FieldSchema(
                name="sex",
                label="Geschlecht",
                type="select",
                options=["female", "male"],
            ),
            FieldSchema(name="sex_evidence", label="Beleg zum Geschlecht", type="text"),
            FieldSchema(name="sex_resp", label="Verantwortung Geschlecht", type="text"),
            FieldSchema(
                name="sex_cert",
                label="Sicherheit Geschlecht",
                type="select",
                options=["high", "low"],
            ),
            FieldSchema(
                name="role",
                label="Rolle",
                type="select",
                options=["mythological"],
            ),
            FieldSchema(name="wedding", label="Heirat", type="text"),
            FieldSchema(name="wedding_note", label="Anmerkung zur Heirat", type="text", multiline=True),
            FieldSchema(name="gnd", label="GND-ID", type="text"),
            FieldSchema(name="viaf", label="VIAF-ID", type="text"),
            FieldSchema(name="idno_other", label="Normdaten-URIs", type="text"),
            FieldSchema(name="note", label="Anmerkung", type="text", multiline=True),
        ],
        # alt_names/birth_names/pseudonyms aren't form fields — see the
        # "Keine Formularfelder" note above and docs/ingest/schleiermacher.md — but ingest
        # legitimately writes them, so validate_entry mustn't reject them
        extra_keys=["alt_names", "birth_names", "pseudonyms"],
        order=[
            "name",
            "surname",
            "forename",
            "used_name",
            "name_link",
            "birth_date",
            "death_date",
            "sex",
            "sex_evidence",
            "sex_resp",
            "sex_cert",
            "role",
            "wedding",
            "wedding_note",
            "gnd",
            "viaf",
            "idno_other",
            "note",
        ],
    ),
    # Ortsregister (Orte.xml) — see the "Orte" section of the module docstring.
    # A sub-place (a nested place/listPlace/place) is a `place` entry of its
    # own plus a part_of relation, not a field — see
    # ingest.ingest_schleiermacher_place_nesting and docs/ingest/schleiermacher.md.
    "place": SchemaOverride(
        remove=["lat", "lon"],
        modify={
            "placename": {"label": "Ortsname", "required": True},
            "place_type": {
                "label": "Art des Ortes",
                # exactly the @type values the register uses, not the base
                # schema's city/region/country/building
                "options": [
                    "building",
                    "district",
                    "street",
                    "park",
                    "forest",
                    "mountain",
                    "sea",
                    "monument",
                    "others",
                ],
            },
        },
        add=[
            # plain strings, not a surname/forename split like the person
            # register's alternate names — so this stays an editable form field
            FieldSchema(
                name="alt_names",
                label="Alternativbezeichnung",
                type="text",
                repeatable=True,
            ),
            # a GeoNames URI is its own editable field, not a view of
            # idno_other: ingest._split_idnos routes each <idno> into exactly
            # one of the two and export re-emits both, so this is where a
            # GeoNames reference is corrected
            FieldSchema(name="geonames", label="GeoNames-URI", type="text"),
            FieldSchema(name="idno_other", label="Normdaten-URIs", type="text"),
            FieldSchema(name="note", label="Anmerkung", type="text", multiline=True),
        ],
        order=[
            "placename",
            "alt_names",
            "place_type",
            "geonames",
            "idno_other",
            "note",
        ],
    ),
    # Körperschaften
    # The parent institution (nested listOrg/head) is a `group` entry plus member_of relations, not a field.
    "organisation": SchemaOverride(
        remove=["org_type", "place"],
        modify={"orgname": {"label": "Name", "required": True}},
        add=[
            FieldSchema(
                name="alt_names",
                label="Alternativbezeichnung",
                type="text",
                repeatable=True,
            ),
            FieldSchema(name="idno_uri", label="Normdaten-URI", type="text"),
            FieldSchema(name="description", label="Beschreibung", type="text"),
        ],
        order=["orgname", "alt_names", "idno_uri", "description"],
    ),
    # Glossar
    "glossary": SchemaOverride(
        add=[
            FieldSchema(name="term", label="Begriff", type="text", required=True),
            FieldSchema(name="term_lang", label="Sprache des Begriffs", type="text"),
            FieldSchema(
                name="alt_names",
                label="Alternativbezeichnung",
                type="text",
                repeatable=True,
            ),
            FieldSchema(
                name="category",
                label="Sachgruppe",
                type="select",
                options=["instrument", "christliche_sitte"],
            ),
            FieldSchema(name="desc", label="Kurze Beschreibung", type="text"),
            FieldSchema(name="desc_resp", label="Verantwortung Beschreibung", type="text"),
            FieldSchema(name="note", label="Erläuterung", type="text", multiline=True),
            FieldSchema(name="note_resp", label="Verantwortung Erläuterung", type="text"),
            FieldSchema(name="source", label="Quellenangabe", type="text"),
        ],
        order=[
            "term",
            "term_lang",
            "alt_names",
            "category",
            "desc",
            "desc_resp",
            "note",
            "note_resp",
            "source",
        ],
    ),
    # Werke
    # Authors/Editors are structured (ingest._contributors), hence extra_keys, not form fields.
    "work": SchemaOverride(
        add=[
            FieldSchema(name="title", label="Titel", type="text"),
            FieldSchema(name="work_type", label="Art des Werks", type="select", options=["journal"]),
            FieldSchema(name="pub_place", label="Erscheinungsort", type="text"),
            FieldSchema(name="pub_place_key", label="Ortsregister-ID des Erscheinungsorts", type="text"),
            FieldSchema(name="date", label="Erscheinungsdatum", type="text"),
            FieldSchema(name="note", label="Anmerkung", type="text", multiline=True),
        ],
        extra_keys=["authors", "editors"],
        order=["title", "work_type", "pub_place", "pub_place_key", "date", "note"],
    ),
    # Bibelsystematik
    # See the "Bibelbücher" section of the module docstring.
    "bible_book": SchemaOverride(
        add=[
            FieldSchema(name="name", label="Name", type="text", required=True),
            FieldSchema(name="sigle", label="Kurzsigle", type="text"),
            FieldSchema(name="abbr", label="Abkürzung", type="text"),
            FieldSchema(name="name2", label="Zweitname", type="text"),
            FieldSchema(name="abbr2", label="Abkürzung 2", type="text"),
            FieldSchema(
                name="canon_part",
                label="Kanonteil",
                type="select",
                options=["AT", "AP", "NT"],
            ),
            FieldSchema(name="position", label="Position im Kanon", type="number"),
            FieldSchema(name="group_a", label="Gruppe (Ebene 1)", type="text"),
            FieldSchema(name="group_b", label="Gruppe (Ebene 2)", type="text"),
            FieldSchema(name="group_c", label="Gruppe (Ebene 3)", type="text"),
        ],
        order=[
            "canon_part",
            "position",
            "sigle",
            "name",
            "abbr",
            "name2",
            "abbr2",
            "group_a",
            "group_b",
            "group_c",
        ],
    ),
}

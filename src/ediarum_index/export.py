"""Build TEI register XML from stored entries — the rough inverse of ingest.py.

The output follows each project's original shape but is **not** byte-identical:

* whitespace / indentation are the serializer's,
* markup inside ``<note>`` other than a re-spliced ``mentions`` link is gone
  (the field itself round-trips as flattened text — see ingest.py),
* identifiers and dates are emitted verbatim as stored (URIs stay URIs, an
  uncertain ``<birth>nach 1824</birth>`` comes back unchanged),
* the ``<teiHeader>`` is a minimal generated stub.

Structure and field content round-trip; formatting and the envelope do not. Use
``tests/test_roundtrip.py`` (which diffs ingest vs. export, whitespace-insensitive)
to see exactly where a given register deviates.

Comments (``models.Comment``) and note-internal links (``mentions``
relations) round-trip too — see ``_emit_comments``/``_emit_mentions`` below
and docs/ingest/links-and-comments.md for exactly what deviates. A comment's position is an
approximation (its ``(start_field, end_field)`` anchor, not the exact
original character offset — see ``_wrap_field_content``). A link's position
is exact when a valid ``models.MentionAnchor`` exists (the stored character
span still matches the note's current text — see
``_splice_anchored_mentions``); otherwise it falls back to a best-effort
string search against the target's own name (``_splice_mention``,
``_mention_candidates``), and only to appending a synthetic reference when
even that search is missing or ambiguous.

A profile can also declare ``inline_wraps`` in its ``EXPORT`` config — a
field-into-field best-effort splice unrelated to comments/links (e.g.
schleiermacher's ``forename``/``used_name``, "Rufname" — see
``_splice_inline_wrapped_value``).
"""

import re
from datetime import datetime

from lxml import etree

TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"

_STEP_RE = re.compile(r"^([\w]+)((?:\[@[\w:]+='[^']*'\])*)$")
_PRED_RE = re.compile(r"\[@([\w:]+)='([^']*)'\]")


class Emit:
    """How one ``data`` field maps back to element(s), relative to the record.

    ``path`` is a ``/``-separated chain of TEI tag names, each optionally carrying
    ``[@attr='value']`` predicates that are written as attributes when the element
    is created. The last step is the leaf that receives the value; parent steps
    are created once and reused.

    ``qualifier`` writes a value's extra key as an attribute *on the leaf*.
    ``wrapper_qualifier`` instead builds a **fresh single-step wrapper per value**
    (its static predicates plus this attribute, taken from the value's
    ``qual_key``) — for ``<persName type="alt" subtype="…">…</persName>``. In
    wrapper mode a value with ``surname`` / ``forename`` keys emits those child
    elements; otherwise its ``value`` goes in the leaf tag from ``path``.

    ``split`` turns a single ``"; "``-joined string value into one element per
    part — for a field a custom extractor flattened to a scalar instead of a
    list (e.g. avhr's ``idno_other``). ``value_attr`` writes the value as an
    attribute instead of the leaf's text, for elements that carry it that way
    (``<sex value="…"/>``). ``attrs_from`` sets extra attributes on the leaf
    from *other*, sibling ``data`` fields, not this one's own value — e.g.
    ``floruit``'s ``@notBefore``/``@notAfter`` live in
    ``floruit_notbefore``/``floruit_notafter``. ``attr_map`` parses one item
    (post-``split``) into a ``{attr: value}`` dict written on the leaf,
    text-free — for a leaf that is itself a packed string, e.g. avhr's
    ``references`` (``"page:33#58"`` -> ``<ptr type="page" target="33#58"/>``).

    ``prefix`` is put in front of a scalar value on the way out (the glossary
    stores ``interp/@id="#instrument"`` as ``instrument``). ``parent_attrs_from``
    is ``attrs_from`` for the leaf's *parent* step — the glossary's
    ``<note resp="…"><p>…</p></note>`` keeps ``@resp`` on ``note``, while the
    text goes in the ``p``; a value of ``None`` then writes only those
    attributes and no leaf.
``builder`` is for a field whose element shape none of the above can
    express: a callable ``builder(record, value)`` that appends the elements
    itself (the works' structured ``authors``/``editors``).
    """

    __slots__ = (
        "path", "repeatable", "qualifier", "wrapper_qualifier", "qual_key",
        "split", "value_attr", "attrs_from", "attr_map", "prefix", "parent_attrs_from",
        "builder",
    )

    def __init__(
        self,
        path: str,
        *,
        repeatable: bool = False,
        qualifier: str | None = None,
        wrapper_qualifier: str | None = None,
        qual_key: str | None = None,
        split: str | None = None,
        value_attr: str | None = None,
        attrs_from: dict[str, str] | None = None,
        attr_map=None,
        prefix: str = "",
        parent_attrs_from: dict[str, str] | None = None,
        builder=None,
    ):
        self.path = path
        self.repeatable = repeatable
        self.qualifier = qualifier
        self.wrapper_qualifier = wrapper_qualifier
        self.qual_key = qual_key  # which value-object key holds the wrapper qualifier
        self.split = split  # delimiter that turns a joined string value into a list
        self.value_attr = value_attr  # attribute name to hold the value instead of text
        self.attrs_from = attrs_from  # {attr name: sibling data key}, set on the leaf
        self.attr_map = attr_map  # str -> {attr: value}, applied per item instead of text
        self.prefix = prefix  # put in front of a scalar value (text or value_attr)
        self.parent_attrs_from = parent_attrs_from  # {attr name: data key}, set on the leaf's parent
        self.builder = builder  # (record, value) -> None, builds the elements itself


_REFERENCE_RE = re.compile(r"^([^/:]+)(?:/([^:]+))?:(.*)$")


def _parse_reference(part: str) -> dict[str, str]:
    """Reverse ``ingest._references``'s ``"<type>/<subtype>:<target>"`` format.

    A missing ``@type`` was written as ``"?"`` by the ingest side — skip it
    rather than writing it back out as a literal attribute value.
    """
    if not (m := _REFERENCE_RE.match(part)):
        return {"target": part}
    kind, subtype, target = m.groups()
    out = {"target": target}
    if kind and kind != "?":
        out["type"] = kind
    if subtype:
        out["subtype"] = subtype
    return out


def _contributors_builder(tag: str):
    """``Emit.builder`` for ``ingest._contributors``' output: one ``<author>`` /
    ``<editor>`` per item, with ``@role``, and a ``persName`` (``@key``,
    ``surname`` + ``forename`` — both, even when one is empty, as in the source —
    or a lone ``name``) or an ``orgName``. ``{"unknown": True}`` is the empty
    persName.

    Args:
        tag: ``"author"`` or ``"editor"``: the element to write.

    Returns:
        A callable ``build(record, items)`` to pass as ``Emit(builder=...)``.
    """

    def build(record, items) -> None:
        """Append one element per contributor to ``record``.

        Args:
            record: The record element the contributors are appended to.
            items: The stored list from ``ingest._contributors``, or ``None``.
        """
        for item in items or []:
            el = etree.SubElement(record, f"{{{TEI}}}{tag}")
            if item.get("role"):
                el.set("role", item["role"])
            if item.get("orgname"):
                name_el = etree.SubElement(el, f"{{{TEI}}}orgName")
                name_el.text = item["orgname"]
            else:
                name_el = etree.SubElement(el, f"{{{TEI}}}persName")
                if item.get("name"):
                    etree.SubElement(name_el, f"{{{TEI}}}name").text = item["name"]
                else:
                    for part in ("surname", "forename"):
                        etree.SubElement(name_el, f"{{{TEI}}}{part}").text = item.get(part) or None
            if item.get("key"):
                name_el.set("key", item["key"])

    return build


# leibniz5 & mop share this; each profile's `emit` keys must mirror
# `ingest.PROFILES[slug]["fields"]`, and `order` controls element sequence.
_PERSON_EMIT = {
    "surname": Emit("persName[@type='reg']/surname"),
    "forename": Emit("persName[@type='reg']/forename"),
    "birth_date": Emit("birth"),
    "death_date": Emit("death"),
    "idno": Emit("idno", repeatable=True, qualifier="type"),
}

# a mentions link's tag by its target's entry_type, for every avhr register
_EHD_MENTION_TAGS = {"place": "placeName", "organisation": "orgName"}

EXPORT: dict[str, dict] = {
    "leibniz5": {
        "entry_type": "person",
        "doctype": "register",
        "list": "listPerson",
        "record": "person",
        "emit": _PERSON_EMIT,
        "order": ["idno", "surname", "forename", "birth_date", "death_date"],
    },
    "mop": {
        "entry_type": "person",
        "doctype": "avh_register",
        "list": "listPerson",
        "record": "person",
        "emit": {
            **_PERSON_EMIT,
            "alt_names": Emit(
                "persName[@type='alt']/name",
                repeatable=True,
                wrapper_qualifier="subtype",
                qual_key="kind",
            ),
            "note": Emit("note"),
        },
        "order": ["idno", "surname", "forename", "alt_names", "birth_date", "death_date", "note"],
        "attrs": {"old_id": "oldID"},
    },
    "pta": {
        "entry_type": "person",
        "doctype": "register",
        "list": "listPerson",
        "record": "person",
        "emit": {
            "forename": Emit("persName/forename", repeatable=True, qualifier="xml:lang"),
            "surname": Emit("persName/surname", repeatable=True, qualifier="xml:lang"),
            "epithet": Emit(
                "persName/addName[@type='epithet']", repeatable=True, qualifier="xml:lang"
            ),
            "floruit": Emit("floruit"),
            "idno": Emit("idno", repeatable=True, qualifier="type"),
            "note": Emit("note"),
        },
        "order": ["idno", "forename", "surname", "epithet", "floruit", "note"],
    },
    "avhr": {
        "entry_type": "person",
        "doctype": "register",
        "list": "listPerson",
        "record": "person",
        # avhr links its institutions with orgName (see _MENTION_TAGS)
        "mention_tags": _EHD_MENTION_TAGS,
        "emit": {
            "surname": Emit("persName[@type='reg']/surname"),
            "forename": Emit("persName[@type='reg']/forename"),
            "name": Emit("persName[@type='reg']/name"),
            # structured like mop's alt_names ({surname, forename} or {value},
            # plus "kind" for @subtype) — see ingest.extract_ehd_person
            "alt_names": Emit(
                "persName[@type='alt']/name",
                repeatable=True,
                wrapper_qualifier="subtype",
                qual_key="kind",
            ),
            "birth_date": Emit("birth"),
            "death_date": Emit("death"),
            "floruit": Emit("floruit", attrs_from={"notBefore": "floruit_notbefore", "notAfter": "floruit_notafter"}),
            "sex": Emit("sex", value_attr="value", attrs_from={"evidence": "sex_evidence"}),
            # idno_other is ingest's lossless catch-all of every <idno>, so it
            # alone rebuilds the source elements; gnd/viaf/wikidata are derived
            # subsets of it and would duplicate entries if also emitted
            "idno_other": Emit("idno[@type='uri']", repeatable=True, split="; "),
            "note": Emit("note", attrs_from={"resp": "note_resp"}),
            # "page:33#58" / "letter/comment:16#26" -> <ptr type="page" target="33#58"/>
            # — the grouping into possibly-several source <linkGrp>s is lost,
            # every ptr comes back under one
            "references": Emit("linkGrp/ptr", repeatable=True, split="; ", attr_map=_parse_reference),
        },
        "order": [
            "idno_other", "surname", "forename", "name", "alt_names",
            "birth_date", "death_date", "floruit", "sex", "note", "references",
        ],
        "attrs": {
            "old_id": "oldID",
            "duplicate_of": "duplicate",
            "role": "role",
            "resp": "resp",
        },
    },
    # avhr's place and organisation registers — mainly the targets of the
    # placeName/orgName links in the person notes; shaped like schleiermacher's
    "avhr_places": {
        "project": "avhr",
        "entry_type": "place",
        "doctype": "register",
        "list": "listPlace",
        "record": "place",
        "nesting": {"predicate": "part_of", "list": "listPlace"},
        # avhr links its institutions with orgName (see _MENTION_TAGS)
        "mention_tags": _EHD_MENTION_TAGS,
        "emit": {
            # ingest._split_idnos routes each <idno> into exactly one of these
            "geonames": Emit("idno[@type='uri']", repeatable=True, split="; "),
            "idno_other": Emit("idno[@type='uri']", repeatable=True, split="; "),
            "placename": Emit("placeName[@type='reg']"),
            "alt_names": Emit("placeName[@type='alt']", repeatable=True, qualifier="subtype"),
            "note": Emit("note", attrs_from={"resp": "note_resp"}),
            "references": Emit("linkGrp/ptr", repeatable=True, split="; ", attr_map=_parse_reference),
        },
        # the source's own order: idno, placeName[reg], placeName[alt]…, note,
        # linkGrp — the nested <listPlace> is appended after these by _emit_nested
        "order": ["geonames", "idno_other", "placename", "alt_names", "note", "references"],
        "attrs": {"old_id": "oldID", "place_type": "type", "resp": "resp", "role": "role"},
    },
    "avhr_organisations": {
        "project": "avhr",
        "entry_type": "organisation",
        "doctype": "register",
        "list": "listOrg",
        "record": "org",
        # the links sit in <desc>
        "note_field": "description",
        # avhr links its institutions with orgName (see _MENTION_TAGS)
        "mention_tags": _EHD_MENTION_TAGS,
        "emit": {
            "idno_uri": Emit("idno[@type='uri']"),
            "orgname": Emit("orgName[@type='reg']"),
            "alt_names": Emit("orgName[@type='alt']", repeatable=True),
            "description": Emit("desc"),
            "references": Emit("linkGrp/ptr", repeatable=True, split="; ", attr_map=_parse_reference),
        },
        # <location> follows linkGrp in the source but is not captured yet
        "order": ["idno_uri", "orgname", "alt_names", "description", "references"],
        "attrs": {"old_id": "oldID"},
    },
    # profile key, not project slug — see `project` below and export_config()
    "schleiermacher_places": {
        "project": "schleiermacher",
        "entry_type": "place",
        "doctype": "register",
        "list": "listPlace",
        "record": "place",
        # sub-place reconstruction — see _emit_nested and
        # ingest.ingest_schleiermacher_place_nesting (the inverse)
        "nesting": {"predicate": "part_of", "list": "listPlace"},
        "emit": {
            # ingest._split_idnos routes each <idno type="uri"> into exactly one
            # of these two — geonames.org ones to `geonames`, the rest to
            # `idno_other` — so both rebuild source elements and neither can
            # duplicate the other. Both keep the full URI text, which is what
            # makes the round-trip exact across the register's 76 spellings.
            "geonames": Emit("idno[@type='uri']", repeatable=True, split="; "),
            "idno_other": Emit("idno[@type='uri']", repeatable=True, split="; "),
            "placename": Emit("placeName[@type='reg']"),
            # plain strings, one <placeName type="alt"> each — no surname/forename
            # split to preserve, so an ordinary repeatable field does the job and
            # no wrapper_qualifier is needed
            "alt_names": Emit("placeName[@type='alt']", repeatable=True),
            "note": Emit("note"),
        },
        # the source's own order in all 2852 records: idno, placeName[reg],
        # placeName[alt]…, note — the nested <listPlace> is appended after
        # these by _emit_nested
        "order": ["geonames", "idno_other", "placename", "alt_names", "note"],
        # the record's `@xml:id` is written by build_record from
        # entry["source_id"]; there is no separate id field to emit.
        "attrs": {"place_type": "type"},
    },
    "schleiermacher_organisations": {
        "project": "schleiermacher",
        "entry_type": "organisation",
        "doctype": "register",
        "list": "listOrg",
        "record": "org",
        # a parent institution is a `group` entry (ingest.ingest_schleiermacher_groups):
        # a nested listOrg/head, without the person register's @type="group"
        "groups": {
            "entry_type": "group", "predicate": "member_of",
            "list": "listOrg", "type_attr": False,
        },
        # the `desc` is where persName[@key] links and comments sit
        "note_field": "description",
        "emit": {
            "idno_uri": Emit("idno[@type='uri']"),
            "orgname": Emit("orgName[@type='reg']"),
            "alt_names": Emit("orgName[@type='alt']", repeatable=True),
            "description": Emit("desc"),
        },
        "order": ["idno_uri", "orgname", "alt_names", "description"],
    },
    "schleiermacher_works": {
        "project": "schleiermacher",
        "entry_type": "work",
        "doctype": "register",
        "list": "listBibl",
        "record": "bibl",
        # an author's works sit in listBibl[@type='group'] / head, like the
        # person families (ingest.ingest_schleiermacher_groups)
        "groups": {"entry_type": "group", "predicate": "member_of", "list": "listBibl"},
        "emit": {
            "authors": Emit("author", builder=_contributors_builder("author")),
            "editors": Emit("editor", builder=_contributors_builder("editor")),
            "title": Emit("title"),
            "pub_place": Emit("pubPlace", attrs_from={"key": "pub_place_key"}),
            "date": Emit("date"),
            "note": Emit("note"),
        },
        "order": ["authors", "editors", "title", "pub_place", "date", "note"],
        "attrs": {"work_type": "type"},
    },
    "schleiermacher_glossary": {
        "project": "schleiermacher",
        "entry_type": "glossary",
        "doctype": "register",
        "list": "list",
        "record": "item",
        "emit": {
            "term": Emit("label[@type='reg']", attrs_from={"xml:lang": "term_lang"}),
            "alt_names": Emit("label[@type='alt']", repeatable=True),
            "desc": Emit("desc", attrs_from={"resp": "desc_resp"}),
            # the paragraphs come back as one <p> (ingest joins them, like any
            # note); @resp stays on <note>, the source paragraph goes after it
            "note": Emit("note/p", parent_attrs_from={"resp": "note_resp"}),
            "source": Emit("note/p[@type='source']"),
            "category": Emit("interp", value_attr="id", prefix="#"),
        },
        "order": ["term", "alt_names", "desc", "category", "note", "source"],
    },
    "schleiermacher_bible_books": {
        "project": "schleiermacher",
        "entry_type": "bible_book",
        "doctype": "register",
        "list": "list",
        "record": "item",
        # body/list/list[@type]/(label, list/item) — see _emit_partitioned
        "partition": {
            "field": "canon_part",
            "wrapper": "list",
            "attr": "type",
            "inner": "list",
            "sort": "position",
            "labels": {"AT": "Altes Testament", "AP": "Apokryphen", "NT": "Neues Testament"},
        },
        # the items carry no xml:id; the source_id is synthetic
        "no_xml_id": True,
        "attrs": {"position": "n"},
        # ingest drops the empty gruppea/b/c labels, so they are not re-emitted
        "emit": {
            "sigle": Emit("idno"),
            "name": Emit("label[@unit='name']"),
            "abbr": Emit("label[@unit='abk']"),
            "name2": Emit("label[@unit='name2']"),
            "abbr2": Emit("label[@unit='abk2']"),
            "group_a": Emit("label[@unit='gruppea']"),
            "group_b": Emit("label[@unit='gruppeb']"),
            "group_c": Emit("label[@unit='gruppec']"),
        },
        "order": [
            "sigle", "name", "abbr", "name2", "abbr2", "group_a", "group_b", "group_c",
        ],
    },
    "schleiermacher_persons": {
        "project": "schleiermacher",
        "entry_type": "person",
        "doctype": "register",
        "list": "listPerson",
        "record": "person",
        # family/group reconstruction — see _emit_grouped and
        # ingest.ingest_schleiermacher_groups (the inverse)
        "groups": {"entry_type": "group", "predicate": "member_of"},
        "emit": {
            "surname": Emit("persName[@type='reg']/surname"),
            "forename": Emit("persName[@type='reg']/forename"),
            "name": Emit("persName[@type='reg']/name"),
            # always empty in the source so far (see ingest.extract_schleiermacher_person)
            "name_link": Emit("persName[@type='reg']/nameLink"),
            # three separate fields, one bucket each by subtype — unlike mop/avhr's
            # single alt_names, there's no per-item qualifier to carry, so
            # wrapper_qualifier only serves to give each name its own fresh
            # <persName type="alt"> wrapper; the [@subtype=...] predicate is baked
            # into birth_names'/pseudonyms' own path instead of being per-item.
            # Each item is {surname, forename} or {value} (ingest._alt_names) —
            # same shape mop's alt_names uses, so the surname/forename split
            # round-trips instead of collapsing into one joined <name>.
            "alt_names": Emit("persName[@type='alt']/name", repeatable=True, wrapper_qualifier="subtype"),
            "birth_names": Emit(
                "persName[@type='alt'][@subtype='birthname']/name",
                repeatable=True, wrapper_qualifier="subtype",
            ),
            "pseudonyms": Emit(
                "persName[@type='alt'][@subtype='pseudonym']/name",
                repeatable=True, wrapper_qualifier="subtype",
            ),
            "birth_date": Emit("birth"),
            "death_date": Emit("death"),
            "sex": Emit(
                "sex", value_attr="value",
                attrs_from={"evidence": "sex_evidence", "resp": "sex_resp", "cert": "sex_cert"},
            ),
            # `wedding` must stay ordered before `wedding_note` (see `order` below):
            # its own emission creates the <event type="wedding"> element via a
            # fresh SubElement; wedding_note's chain lookup then finds *that*
            # element (by tag+predicate) and nests <note> inside it, rather than
            # each creating a separate <event>
            "wedding": Emit("event[@type='wedding']", value_attr="when"),
            "wedding_note": Emit("event[@type='wedding']/note"),
            # idno_other is ingest's lossless catch-all of every <idno>, so it
            # alone rebuilds the source elements; gnd/viaf are derived subsets of
            # it (see ingest._idnos) and would duplicate entries if also emitted —
            # unlike avhr, projects/schleiermacher/__init__.py lists them as
            # regular editable fields, so an edit to gnd/viaf alone doesn't reach
            # the export; edit idno_other instead
            "idno_other": Emit("idno[@type='uri']", repeatable=True, split="; "),
            "note": Emit("note"),
        },
        "order": [
            "idno_other", "surname", "forename", "name", "name_link",
            "alt_names", "birth_names", "pseudonyms",
            # sex precedes birth/death in the source itself (6580 of 6586
            # records with both) — matching it keeps the round-trip report
            # from drowning in pure reordering noise
            "sex", "birth_date", "death_date", "wedding", "wedding_note", "note",
        ],
        # the record's `@xml:id` is written by build_record from
        # entry["source_id"]; there is no separate id field to emit.
        # `used_name` is spliced back into `forename` as an inline
        # <name type="used"> wrapper on a best-effort basis (see
        # _splice_inline_wrapped_value) rather than as its own `Emit` — its
        # own text is already part of `forename`'s (see
        # extract_schleiermacher_person), so re-emitting it as a separate
        # field would duplicate it. `group` (which `listPerson[@type='group']`
        # a person is nested under) is structural, not a per-person field,
        # and isn't reconstructed either.
        "inline_wraps": [
            {"field": "forename", "wrapped_field": "used_name", "tag": "name", "attrs": {"type": "used"}},
        ],
        "attrs": {"role": "role"},
    },
}


def export_config(project: str, entry_type: str) -> dict | None:
    """The ``EXPORT`` config for one ``(project, entry_type)``, or ``None``.

    ``EXPORT`` is keyed by *profile*, mirroring ``ingest.PROFILES``, and a
    project with more than one register has one profile per entry type — so a
    config may name a ``project`` that differs from its key (schleiermacher's
    places). Callers that only know the project and the entry type (the
    ``/export`` route, ``build_document``) go through here instead of indexing
    ``EXPORT`` directly.
    """
    for key, cfg in EXPORT.items():
        if cfg.get("project", key) == project and cfg["entry_type"] == entry_type:
            return cfg
    return None


def _attr(name: str) -> str:
    return f"{{{XML}}}{name[4:]}" if name.startswith("xml:") else name


def _parse_step(step: str) -> tuple[str, dict[str, str]]:
    m = _STEP_RE.match(step)
    if not m:
        raise ValueError(f"bad emit step: {step!r}")
    return m.group(1), dict(_PRED_RE.findall(m.group(2)))


def _child(parent, step: str):
    """``parent``'s child matching ``step`` (tag + predicate attrs), created once."""
    tag, preds = _parse_step(step)
    qname = f"{{{TEI}}}{tag}"
    for ch in parent:
        if ch.tag == qname and all(ch.get(_attr(k)) == v for k, v in preds.items()):
            return ch
    el = etree.SubElement(parent, qname)
    for k, v in preds.items():
        el.set(_attr(k), v)
    return el


def _qual(item) -> str | None:
    """The value object's one non-``value`` key's value (the qualifier).

    Only a ``{value, <qualifier>}`` shaped item has one (idno's ``type``,
    pta's ``xml:lang``, ...) — requiring ``"value"`` keeps this from
    misreading a ``{surname, forename}`` split-name item (no qualifier at
    all) as if its ``surname`` were the qualifier.
    """
    if isinstance(item, dict) and "value" in item:
        return next((v for k, v in item.items() if k != "value"), None)
    return None


def _text_of(item):
    return str(item["value"]) if isinstance(item, dict) else (None if item is None else str(item))


def _emit(record, spec: Emit, value, data: dict | None = None) -> None:
    if spec.builder:
        spec.builder(record, value)
        return
    *chain, leaf = spec.path.split("/")
    if spec.split and isinstance(value, str):
        items = [part.strip() for part in value.split(spec.split) if part.strip()]
    else:
        items = value if isinstance(value, list) else [value]

    if spec.wrapper_qualifier:
        # a fresh single-step wrapper per value, carrying the value's qualifier
        wrap_tag, wrap_preds = _parse_step(chain[0])
        leaf_tag, _ = _parse_step(leaf)
        for raw in items:
            item = raw if isinstance(raw, dict) else {"value": _text_of(raw)}
            wrap = etree.SubElement(record, f"{{{TEI}}}{wrap_tag}")
            for k, v in wrap_preds.items():
                wrap.set(_attr(k), v)
            qv = item.get(spec.qual_key) if spec.qual_key else _qual(item)
            if qv:
                wrap.set(_attr(spec.wrapper_qualifier), qv)
            if item.get("surname") or item.get("forename"):
                for sub in ("surname", "forename"):
                    if item.get(sub):
                        etree.SubElement(wrap, f"{{{TEI}}}{sub}").text = str(item[sub])
            elif item.get("value"):
                etree.SubElement(wrap, f"{{{TEI}}}{leaf_tag}").text = str(item["value"])
        return

    parent = record
    for step in chain:
        parent = _child(parent, step)
    if spec.parent_attrs_from and data:
        for attr, key in spec.parent_attrs_from.items():
            if v := data.get(key):
                parent.set(_attr(attr), str(v))
        if value is None:  # only the parent's attributes were stored
            return
    tag, preds = _parse_step(leaf)
    qname = f"{{{TEI}}}{tag}"
    for item in items:
        el = etree.SubElement(parent, qname)
        for k, v in preds.items():
            el.set(_attr(k), v)
        if spec.attr_map:
            for k, v in spec.attr_map(item).items():
                if v:
                    el.set(_attr(k), str(v))
        elif isinstance(item, dict):
            el.text = str(item.get("value", "")) or None
            qv = _qual(item)
            if spec.qualifier and qv:
                el.set(_attr(spec.qualifier), qv)
        elif item is not None:
            if spec.value_attr:
                el.set(_attr(spec.value_attr), spec.prefix + str(item))
            else:
                el.text = spec.prefix + str(item)
        if spec.attrs_from and data:
            for attr, key in spec.attrs_from.items():
                if v := data.get(key):
                    el.set(_attr(attr), str(v))


def _find_field_element(rec, cfg: dict, field_name: str | None):
    """The element ``build_record`` created for ``field_name``, if the field
    has a simple (non-``wrapper_qualifier``) path and a value was actually
    emitted for it — a read-only counterpart to ``_child`` (never creates).
    Used to anchor re-exported comments/note-links onto roughly the field
    they were extracted near; ``None`` when there's nothing to anchor to, so
    callers fall back to a record- or note-level default position.
    """
    if not field_name:
        return None
    spec = cfg.get("emit", {}).get(field_name)
    if spec is None or spec.wrapper_qualifier:
        return None
    *chain, leaf = spec.path.split("/")
    parent = rec
    for step in chain:
        tag, preds = _parse_step(step)
        qname = f"{{{TEI}}}{tag}"
        parent = next(
            (ch for ch in parent if ch.tag == qname and all(ch.get(_attr(k)) == v for k, v in preds.items())),
            None,
        )
        if parent is None:
            return None
    tag, preds = _parse_step(leaf)
    qname = f"{{{TEI}}}{tag}"
    return next(
        (ch for ch in parent if ch.tag == qname and all(ch.get(_attr(k)) == v for k, v in preds.items())),
        None,
    )


# --- comments: re-emitted as oxy_comment_start/end PIs -------------------------
#
# Every comment re-emits in the richer oxy PI format regardless of its
# original style (see ingest._walk_record_xml_comments — a plain <!-- -->
# comment is promoted, not preserved as-is): one re-emission shape, not two,
# and the one the external editing tool actually recognizes as reviewable.

_NO_TIMESTAMP_NAIVE = datetime(1970, 1, 1)  # ingest._NO_TIMESTAMP, tz-stripped


def _esc(text: str) -> str:
    """Keep a value safe inside a ``key="value"`` PI attribute — PI content
    isn't attribute-value-normalized XML, so this is a best-effort escape,
    not a guarantee (see ingest._walk_record_comments's own parsing regex,
    which assumes no embedded ``"``)."""
    return text.replace('"', "'").replace("?>", "? >")


def _oxy_comment_attrs(comment: dict) -> str:
    parts = []
    if author := comment.get("author"):
        parts.append(f'author="{_esc(author)}"')
    created_at = comment.get("created_at")
    # the source's wall-clock time (see ingest._parse_oxy_timestamp); stored
    # tagged UTC, so the zone is dropped again here
    if created_at and created_at.replace(tzinfo=None) != _NO_TIMESTAMP_NAIVE:
        parts.append(f'timestamp="{created_at.strftime("%Y%m%dT%H%M%S")}"')
    parts.append(f'comment="{_esc(comment.get("text") or "")}"')
    if thread_meta := comment.get("thread_meta"):
        parts.append(thread_meta)  # already "key=\"value\"" pairs, verbatim
    return " ".join(parts)


def _wrap_field_content(target, start_pi, end_pi) -> None:
    """Bracket ``target``'s own content with the PI pair — ``start_pi``
    becomes its first child (pushing its existing text to ``start_pi``'s
    tail), ``end_pi`` its last. Matches the dominant real-corpus shape for a
    clean single-field comment (``<surname><?oxy_comment_start
    …?>Meier<?oxy_comment_end?></surname>``, or the same inside ``<note>``)."""
    start_pi.tail = target.text
    target.text = None
    target.insert(0, start_pi)
    target.append(end_pi)


def _emit_comments(rec, cfg: dict, comments: list[dict]) -> None:
    """Re-emit ``comments`` (this record's own, already filtered by caller)
    as ``oxy_comment_start``/``oxy_comment_end`` PI pairs.

    Positioning is an explicit, documented approximation (exact interleaving
    isn't tracked — see module docstring): ``start_field == end_field``
    wraps that field's own content; anything else (a span, or both null) is
    placed right after the ``end_field`` element if one was found, else
    right before ``</note>`` if the record has one, else right before
    ``</person>``/``</place>``.

    A field commonly carries *more than one* independent comment (several
    editors' remarks accumulated on the same ``<note>`` over time — a real,
    common corpus shape, confirmed via ``roundtrip_report.py`` against the
    real data). ``_wrap_field_content`` assumes a pristine target, so a
    second call on the same element would nest around the first comment's
    own PIs and reverse their order (confirmed directly: two same-field
    comments came back as ``start2, start1, TEXT, end1, end2`` instead of
    the source's sequential shape) — ``wrapped`` tracks which elements have
    already been bracketed so only the first comment for a given field gets
    that treatment; later ones for the same field are appended as a
    trailing pair inside it instead (still anchored to the right field,
    just not bracketing any one span of it).
    """
    note_el = _find_field_element(rec, cfg, "note")
    wrapped: set[int] = set()  # id() of elements _wrap_field_content already used
    for comment in comments:
        start_field = comment.get("start_field")
        end_field = comment.get("end_field")
        start_pi = etree.PI("oxy_comment_start", _oxy_comment_attrs(comment))
        end_pi = etree.PI("oxy_comment_end")

        if start_field and start_field == end_field:
            target = _find_field_element(rec, cfg, start_field)
            if target is not None:
                if id(target) not in wrapped:
                    _wrap_field_content(target, start_pi, end_pi)
                    wrapped.add(id(target))
                else:
                    target.append(start_pi)
                    target.append(end_pi)
                continue

        anchor_el = _find_field_element(rec, cfg, end_field) if end_field else None
        if anchor_el is not None:
            anchor_el.addnext(end_pi)
            anchor_el.addnext(start_pi)
        elif note_el is not None:
            note_el.append(start_pi)
            note_el.append(end_pi)
        else:
            rec.append(start_pi)
            rec.append(end_pi)


# --- note-links: re-spliced as persName/placeName/orgName[@key] -----------


# entry_type -> link tag; anything else is a persName. A profile can override
# this with its own "mention_tags": schleiermacher links its organisations with
# persName (no orgName[@key] in the whole register), avhr with orgName.
_MENTION_TAGS = {"place": "placeName"}


def _mention_tag(target: dict, tags: dict[str, str] | None = None) -> str:
    return (tags or _MENTION_TAGS).get(target.get("entry_type"), "persName")


def _mention_candidates(target: dict) -> list[str]:
    """Candidate strings to search for in ``note`` text, in the order the
    source prose is actually written: natural ``forename surname`` (never
    the formatted "Surname, Forename" ``label``), then bare ``surname``,
    then a place's or organisation's own name."""
    data = target.get("data") or {}
    surname = str(data.get("surname") or "").strip()
    forename = str(data.get("forename") or "").strip()
    placename = str(data.get("placename") or "").strip()
    orgname = str(data.get("orgname") or "").strip()
    candidates = []
    if forename and surname:
        candidates.append(f"{forename} {surname}")
    if surname:
        candidates.append(surname)
    if placename:
        candidates.append(placename)
    if orgname:
        candidates.append(orgname)
    return [c for c in candidates if c]


def _text_runs(note_el):
    """``[(owner, attr)]`` for each contiguous text run inside ``note_el``,
    in document order — its own leading text, then each child's tail."""
    return [(note_el, "text"), *((child, "tail") for child in note_el)]


def _extend_match_end(text: str, end: int) -> int:
    """Extend a confirmed match's end index over any immediately-following
    letters, with no intervening space/punctuation — so a match landing on
    a name's bare stem inside a grammatically inflected word form (German
    case endings: e.g. the target's registered surname "Kant" matching
    inside the note's own "Kants") captures the *whole* word instead of
    truncating mid-word (confirmed a real corpus case, not hypothetical).
    Only extends trailing characters — a name is always written out in
    full at its *start* in the source prose, so nothing needs to extend
    backward; only trailing inflection does."""
    while end < len(text) and text[end].isalpha():
        end += 1
    return end


def _splice_mention(note_el, target: dict, tags: dict[str, str] | None = None) -> None:
    """Place one ``mentions`` link inside ``note_el``: search its flat text
    for a candidate name and wrap the match in place if it's unique, else
    fall back to appending a trailing ``persName``/``placeName`` — never
    guess which occurrence when a name isn't found or occurs more than once.
    """
    tag = _mention_tag(target, tags)
    qname = f"{{{TEI}}}{tag}"
    key = target.get("source_id") or ""
    for needle in _mention_candidates(target):
        runs = _text_runs(note_el)
        # uniqueness is checked against the bare candidate — extending to a
        # word boundary only changes *how much* of a confirmed, unique
        # match gets wrapped, never *whether* one exists
        if sum((getattr(owner, attr) or "").count(needle) for owner, attr in runs) != 1:
            continue
        for owner, attr in runs:
            text = getattr(owner, attr) or ""
            idx = text.find(needle)
            if idx == -1:
                continue
            end = _extend_match_end(text, idx + len(needle))
            before, after = text[:idx], text[end:]
            link = etree.Element(qname)
            link.set("key", key)
            link.text = text[idx:end]
            link.tail = after or None
            if attr == "text":
                owner.text = before or None
                owner.insert(0, link)
            else:
                owner.tail = before or None
                owner.addnext(link)
            return
    link = etree.SubElement(note_el, qname)
    link.set("key", key)
    link.text = target.get("label") or ""


def _splice_anchored_mentions(
    note_el, original_text: str, spans: list[tuple[int, int, int, dict]],
    tags: dict[str, str] | None = None,
) -> set[int]:
    """Rebuild ``note_el``'s content in one pass from a set of
    ``(object_id, start, end, target)`` spans, each already validated
    against ``original_text`` (see ``_emit_mentions``) — every span
    becomes a ``persName``/``placeName`` wrapping exactly
    ``original_text[start:end]``, everything else stays plain text.
    Returns the set of ``object_id``s actually placed — excludes any span
    that overlapped an earlier, kept one (should not occur for
    well-formed source XML, since two sibling elements can't overlap, but
    guarded rather than assumed impossible); the caller falls those back
    to the search heuristic instead of silently dropping them.

    Called *before* any fallback/search-based splicing, on a ``note_el``
    that's still a single, unsplit text string (``build_record``'s own
    output — ``_emit_mentions`` runs before ``_emit_comments``, and
    nothing else touches ``note_el`` first) — so ``original_text`` is
    simply ``note_el.text`` at the point this is called, and the whole
    structure can be laid out in one deterministic left-to-right pass
    instead of one splice at a time mutating an already-fragmented tree
    (which is what the search-based ``_splice_mention`` does, and why it
    can only safely place *one* mention per call — offsets don't have
    that problem, since they're all measured against the same original
    string, known up front).
    """
    ordered = sorted(spans, key=lambda s: s[1])
    kept: list[tuple[int, int, int, dict]] = []
    prev_end = 0
    for object_id, start, end, target in ordered:
        if start < prev_end:
            continue  # overlaps a previous span — leave it to the search fallback
        kept.append((object_id, start, end, target))
        prev_end = end

    cursor = 0
    tail_owner = note_el  # note_el.text first, then each inserted link's .tail
    for _object_id, start, end, target in kept:
        before = original_text[cursor:start]
        if tail_owner is note_el:
            note_el.text = before or None
        else:
            tail_owner.tail = before or None
        link = etree.Element(f"{{{TEI}}}{_mention_tag(target, tags)}")
        link.set("key", target.get("source_id") or "")
        link.text = original_text[start:end]
        note_el.append(link)
        tail_owner = link
        cursor = end
    tail_text = original_text[cursor:]
    if tail_owner is note_el:
        note_el.text = tail_text or None
    else:
        tail_owner.tail = tail_text or None

    return {object_id for object_id, _, _, _ in kept}


def _emit_mentions(
    rec, cfg: dict, object_ids: list[int], entries_by_id: dict, anchors: dict | None = None
) -> None:
    if not object_ids:
        return
    note_el = _find_field_element(rec, cfg, cfg.get("note_field", "note"))
    if note_el is None:  # this profile has no note field to splice into
        return
    anchors = anchors or {}
    tags = cfg.get("mention_tags")

    # anchor-validated placements first, batched against note_el's original
    # (still-unsplit) text; whatever's left falls through to the existing
    # search heuristic, applied to note_el's resulting structure exactly as
    # it already handles one with existing children
    original_text = note_el.text or ""
    validated: list[tuple[int, int, int, dict]] = []
    for object_id in object_ids:
        anchor = anchors.get(object_id)
        target = entries_by_id.get(object_id)
        if not anchor or not target:
            continue
        start, end = anchor["start"], anchor["end"]
        if original_text[start:end] == anchor["text"]:
            validated.append((object_id, start, end, target))

    placed: set[int] = (
        _splice_anchored_mentions(note_el, original_text, validated, tags) if validated else set()
    )

    for object_id in object_ids:
        if object_id in placed:
            continue
        if target := entries_by_id.get(object_id):
            _splice_mention(note_el, target, tags)


# --- inline field wraps: e.g. schleiermacher's forename/used_name ("Rufname") -


def _splice_inline_wrapped_value(rec, cfg: dict, wrap: dict, data: dict) -> None:
    """Search ``wrap["field"]``'s own flattened text for
    ``data[wrap["wrapped_field"]]``'s value and, if found uniquely, wrap it
    in an inline ``<wrap["tag"] wrap["attrs"]...>`` element — e.g.
    schleiermacher's forename/used_name ("Rufname"): the call name is
    already fully present as `forename`'s own text (both captured from the
    same source element at ingest — see
    ``ingest.extract_schleiermacher_person``'s own comment, "the call name
    stays part of the flattened forename as well"), only the
    ``<name type="used">`` wrapper marking *which part* of it is the call
    name is lost on export.

    Best-effort, like ``_splice_mention``'s search: if the value isn't
    found, or occurs more than once (e.g. a curator edited one of the two
    fields without the other — both are independently editable, see
    ``projects/schleiermacher/__init__.py``), the field is simply left as plain
    unwrapped text. Nothing is lost either way — the value itself is
    already fully captured in ``wrapped_field`` regardless of whether the
    wrapper gets reconstructed, unlike a `mentions` link (where the whole
    point is recovering a *reference*) — so unlike links, this never needs
    a stored-offset fallback: a wrong or missing guess here has no
    correctness consequence, only a cosmetic one.
    """
    value = str(data.get(wrap["wrapped_field"]) or "").strip()
    if not value:
        return
    target = _find_field_element(rec, cfg, wrap["field"])
    if target is None or not target.text or target.text.count(value) != 1:
        return
    idx = target.text.find(value)
    before, after = target.text[:idx], target.text[idx + len(value):]
    wrapper = etree.Element(f"{{{TEI}}}{wrap['tag']}")
    for k, v in wrap.get("attrs", {}).items():
        wrapper.set(_attr(k), v)
    wrapper.text = value
    wrapper.tail = after or None
    target.text = before or None
    target.insert(0, wrapper)


def build_record(entry: dict, cfg: dict):
    """Build one ``<person>``/``<place>`` element from field data alone —
    comments/note-links are spliced in separately, by ``build_document``,
    *after* ``etree.indent()`` runs (see its docstring: indent() rewrites an
    element's ``.text`` the moment it gains a child, which would otherwise
    clobber the mixed text/PI/link content ``_emit_comments``/
    ``_emit_mentions`` build)."""
    rec = etree.Element(f"{{{TEI}}}{cfg['record']}")
    # `no_xml_id`: a register whose records have none in the source (the
    # bible books) stores a synthetic source_id that must not be written back
    if entry.get("source_id") and not cfg.get("no_xml_id"):
        rec.set(_attr("xml:id"), entry["source_id"])

    data = entry.get("data") or {}

    # data keys written back as record-element attributes (mop's legacy oldID)
    for key, attr in cfg.get("attrs", {}).items():
        if data.get(key):
            rec.set(_attr(attr), str(data[key]))

    seen: set[str] = set()
    for name in [*cfg["order"], *cfg["emit"]]:
        if name in seen or name not in cfg["emit"]:
            continue
        spec = cfg["emit"][name]
        # a field can be absent (its own value empty, e.g. a text-less
        # <floruit notBefore="…"/>) while an attrs_from sibling still has one —
        # extract() already stripped the empty "" from `data`, so check those too
        if name not in data and not any(
            attrs and any(k in data for k in attrs.values())
            for attrs in (spec.attrs_from, spec.parent_attrs_from)
        ):
            continue
        seen.add(name)
        _emit(rec, spec, data.get(name), data)
    return rec


_ENVELOPE = (
    '<TEI xmlns="{tei}" xmlns:telota="http://www.telota.de" telota:doctype="{doctype}">'
    "<teiHeader><fileDesc>"
    "<titleStmt><title>{title}</title></titleStmt>"
    "<publicationStmt><p>Generated from the ediarum.index database.</p></publicationStmt>"
    "<sourceDesc><p>Exported from project {project!r}.</p></sourceDesc>"
    "</fileDesc></teiHeader>"
    "<text><body><{list}/></body></text></TEI>"
)


def _emit_grouped(list_el, entries, cfg, families, memberships, records: list) -> None:
    """Rebuild ``<listPerson type="group">`` wrappers from ``families`` (each a
    `group` entry dict) and ``memberships`` (each a ``{subject_id, object_id}``
    ``member_of`` relation dict) — the inverse of
    ``ingest.ingest_schleiermacher_groups``. Only engaged when ``cfg["groups"]``
    is set and both are non-empty; every other profile's caller passes neither
    and takes the flat path below unchanged. Each built ``(entry, rec)`` pair
    is appended to ``records`` (mutated in place) — see ``build_document``,
    which splices comments/note-links into them afterward.

    Ordering: the source's original document position isn't tracked (families
    and persons are fetched, not walked file-by-file), so a family and every
    otherwise-ungrouped person are emitted as one flat sequence sorted by
    label — the same "order is normalized" deviation already accepted for
    other profiles, not a new kind of lossiness. A family with zero *present*
    members (all its members are outside the exported slice, or it's
    genuinely empty) is skipped, same as it would be if never referenced.
    """
    family_by_id = {f["id"]: f for f in families}
    # first membership wins for a person in more than one family (not
    # expected in practice — ingest.py enforces one member_of per person)
    family_of: dict[int, int] = {}
    for m in memberships:
        family_of.setdefault(m["subject_id"], m["object_id"])

    grouped: dict[int, list[dict]] = {}
    items: list[tuple[str, dict | None, list[dict]]] = []
    for entry in entries:
        fid = family_of.get(entry.get("id"))
        if fid is not None and fid in family_by_id:
            grouped.setdefault(fid, []).append(entry)
        else:
            items.append((entry["label"], None, [entry]))
    for fid, members in grouped.items():
        family = family_by_id[fid]
        items.append((family["label"], family, members))

    for _label, family, members in sorted(items, key=lambda item: item[0]):
        if family is None:
            rec = build_record(members[0], cfg)
            list_el.append(rec)
            records.append((members[0], rec))
            continue
        grp = etree.SubElement(list_el, f"{{{TEI}}}{cfg['groups'].get('list', 'listPerson')}")
        if cfg["groups"].get("type_attr", True):
            grp.set("type", "group")
        if family["label"]:
            etree.SubElement(grp, f"{{{TEI}}}head").text = family["label"]
        for member in members:
            rec = build_record(member, cfg)
            grp.append(rec)
            records.append((member, rec))


def _emit_nested(list_el, entries, cfg, parents, records: list) -> None:
    """Rebuild the source's nested ``<listPlace>`` structure from ``parents``
    (each a ``{subject_id, object_id}`` ``part_of`` relation dict, subject =
    the *contained* entry) — the inverse of
    ``ingest.ingest_schleiermacher_place_nesting``. Only engaged when
    ``cfg["nesting"]`` is set and ``parents`` is non-empty.

    Unlike ``_emit_grouped``'s families, both ends here are records of the
    same kind, so a parent is emitted as an ordinary record and its children
    go into a nested list *inside* it, after its own fields — the order the
    source uses. Nesting can be several levels deep (the register has one
    three-level case), hence the recursion.

    Ordering is by label at every level, the same "document order is
    normalized" deviation the flat path already has. An entry whose parent
    isn't in this slice is emitted at the top level rather than dropped; so is
    anything the walk never reaches, which is what a cycle in the relations
    would otherwise cost (silently losing both ends).
    """
    by_id = {e["id"]: e for e in entries if e.get("id") is not None}
    parent_of: dict[int, int] = {}
    for rel in parents:
        parent_of.setdefault(rel["subject_id"], rel["object_id"])

    children: dict[int, list[dict]] = {}
    roots: list[dict] = []
    for entry in entries:
        parent_id = parent_of.get(entry.get("id"))
        if parent_id is not None and parent_id in by_id:
            children.setdefault(parent_id, []).append(entry)
        else:
            roots.append(entry)

    emitted: set[int] = set()

    def emit(parent_el, entry) -> None:
        emitted.add(entry.get("id"))
        rec = build_record(entry, cfg)
        parent_el.append(rec)
        records.append((entry, rec))
        if kids := children.get(entry.get("id")):
            sub = etree.SubElement(rec, f"{{{TEI}}}{cfg['nesting']['list']}")
            for kid in sorted(kids, key=lambda e: e["label"]):
                if kid.get("id") not in emitted:  # cycle guard
                    emit(sub, kid)

    for entry in sorted(roots, key=lambda e: e["label"]):
        emit(list_el, entry)
    for entry in entries:  # unreachable (only possible via a relation cycle)
        if entry.get("id") not in emitted:
            emit(list_el, entry)


def _emit_partitioned(list_el, entries, cfg, records: list) -> None:
    """Rebuild a register whose records sit in typed sub-lists — the bible
    books: ``list/list[@type=AT|AP|NT]/(label, list/item)``. The part comes
    from ``data[partition["field"]]``; each part's wrapper gets its long
    ``label`` and an inner list, and the records are in ``sort`` order (the
    source's own register-wide position), not by label. A record with no (or
    an unknown) part is appended to the outer list unwrapped rather than
    dropped; an unknown part gets a wrapper of its own, without a label.

    Args:
        list_el: The outer list element the wrappers are appended to.
        entries: The entries to write.
        cfg: The register's ``EXPORT`` config; its ``partition`` entry names
            the field, wrapper, attribute, inner list, sort key and labels.
        records: Collects an ``(entry, element)`` pair for each written
            record, so the caller can add comments and mentions afterwards.
    """
    part = cfg["partition"]
    by_part: dict[object, list[dict]] = {}
    for entry in entries:
        by_part.setdefault((entry.get("data") or {}).get(part["field"]), []).append(entry)

    def sort_key(e):
        """Sort by ``position``, entries without one last, then by label.

        Args:
            e: An entry dict.
        """
        pos = (e.get("data") or {}).get(part["sort"])
        return (pos is None, pos or 0, e["label"])

    known = list(part["labels"])
    extra = sorted(k for k in by_part if k is not None and k not in known)
    for key in [*known, *extra]:
        members = by_part.get(key)
        if not members:
            continue
        wrap = etree.SubElement(list_el, f"{{{TEI}}}{part['wrapper']}")
        wrap.set(part["attr"], key)
        if label := part["labels"].get(key):
            etree.SubElement(wrap, f"{{{TEI}}}label").text = label
        inner = etree.SubElement(wrap, f"{{{TEI}}}{part['inner']}")
        for entry in sorted(members, key=sort_key):
            rec = build_record(entry, cfg)
            inner.append(rec)
            records.append((entry, rec))
    for entry in sorted(by_part.get(None, []), key=sort_key):
        rec = build_record(entry, cfg)
        list_el.append(rec)
        records.append((entry, rec))


def build_document(
    project: str, entry_type: str, entries, families=(), memberships=(), parents=(),
    comments=(), mentions=(), mention_targets=(), mention_anchors=None,
) -> str:
    """``entries``/``families`` and friends are plain dicts (``.model_dump()``
    of the corresponding table rows — see ``services.export_document``, the only
    real caller). ``comments`` is every ``Comment`` row on an entry in
    ``entries``; ``mentions`` is every outgoing ``mentions`` `Relation` from
    one; ``mention_targets`` is the referenced entries not already in
    ``entries`` (a note can reference an entry of a *different*
    ``entry_type`` — e.g. a person's note mentioning a place — so the
    caller resolves those separately; within-type targets are already
    covered by ``entries`` itself). ``mention_anchors`` is an optional
    ``{(subject_id, object_id): {"start", "end", "text"}}`` map (see
    ``models.MentionAnchor``) — a pair missing from it, or absent
    entirely, just falls back to ``_splice_mention``'s search heuristic.
    """
    cfg = export_config(project, entry_type)
    if cfg is None:
        raise KeyError((project, entry_type))

    comments_by_entry: dict[int, list[dict]] = {}
    for c in comments:
        comments_by_entry.setdefault(c["entry_id"], []).append(c)

    mentions_by_subject: dict[int, list[int]] = {}
    for m in mentions:
        mentions_by_subject.setdefault(m["subject_id"], []).append(m["object_id"])

    mention_anchors = mention_anchors or {}

    entries_by_id = {
        e["id"]: e for e in (*entries, *mention_targets) if e.get("id") is not None
    }

    tei = etree.fromstring(
        _ENVELOPE.format(
            tei=TEI, doctype=cfg["doctype"], title=f"{project} {entry_type} register",
            project=project, list=cfg["list"],
        ).encode()
    )
    list_el = tei.find(f".//{{{TEI}}}{cfg['list']}")
    # (entry, rec) pairs in emitted order — comments/mentions are spliced in
    # only after etree.indent() below, see build_record's docstring
    records: list[tuple[dict, object]] = []
    if cfg.get("groups") and families and memberships:
        _emit_grouped(list_el, entries, cfg, families, memberships, records)
    elif cfg.get("nesting") and parents:
        _emit_nested(list_el, entries, cfg, parents, records)
    elif cfg.get("partition"):
        _emit_partitioned(list_el, entries, cfg, records)
    else:
        for entry in entries:
            rec = build_record(entry, cfg)
            list_el.append(rec)
            records.append((entry, rec))

    etree.indent(tei, space="  ")

    for entry, rec in records:
        entry_id = entry.get("id")
        object_ids = mentions_by_subject.get(entry_id, [])
        anchors = {
            oid: mention_anchors[(entry_id, oid)]
            for oid in object_ids
            if (entry_id, oid) in mention_anchors
        }
        _emit_mentions(rec, cfg, object_ids, entries_by_id, anchors)
        _emit_comments(rec, cfg, comments_by_entry.get(entry_id, []))
        for wrap in cfg.get("inline_wraps", []):
            _splice_inline_wrapped_value(rec, cfg, wrap, entry.get("data") or {})

    return etree.tostring(tei, encoding="unicode")

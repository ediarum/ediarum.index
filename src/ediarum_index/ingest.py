"""Load TEI registers into the database.

Each register is a *profile* in ``PROFILES``: where the files live, which
element is a record, and a spec per target field. Parsing is ``lxml`` — XPath
**1.0** with the TEI namespace bound to ``tei:``.

A profile key is usually the project slug, but it need not be: a project with
more than one register (schleiermacher's persons *and* places) has one profile
per entry type, and the extra ones name their project explicitly. Use
``project_of``, not the profile key, for anything that reaches the database.

A field spec is either

* a string  — an XPath returning one value (``normalize-space(...)`` etc.); a
  post-processor in ``COERCERS`` may clean it (date strings kept verbatim,
  placeholder-only values like ``*`` / ``†`` dropped); **or**
* a dict ``{"each": <element xpath>, "attr": <attr>, "as": <key>}`` — *repeatable*:
  every matching element becomes ``{"value": <text>, <key>: <attr value>}``.
  This is how multilingual names and typed ``<idno>``s are kept intact.

A register whose shape a flat field map cannot express declares **`extract`**
instead of `fields` + `label`/`label_template`: a callable taking one record
and returning ``{"label": str, "data": dict}``. Every profile except
``leibniz5``, ``mop`` and ``pta`` uses one — the label joins its parts
conditionally, alternate names are collected across elements, and floruit /
sex / note carry half their information in attributes or inline markup. A profile may also set
``recover: True`` to parse malformed XML leniently (lxml's recover mode)
instead of aborting on the first file that is not well-formed; what the
parser had to repair is printed as a warning.

    uv run ediarum-index ingest mop
    uv run ediarum-index ingest pta --dry-run  # print records, write nothing
    uv run ediarum-index ingest --all
    uv run ediarum-index ingest --of-project schleiermacher

The ingest writes straight into the database (``db.DATABASE_URI``), through
the same ``services`` functions the API's routes use — so the same
validation applies, but no HTTP and no credentials are involved.

Field keys and their repeatable/qualifier shape must match
``resolve_schema(entry_type, project)`` — i.e. the project's module in ``projects/``.

A re-run reconciles rather than blindly re-inserting (see ``_reconcile``):
each record is matched to an existing entry by ``source_id``, and a content
hash of its extracted ``data`` (stored server-side as ``ingested_source_hash``
alongside ``ingested_at``, see ``models.Entry``) tells an unchanged source
record apart from a changed one. A changed record is only auto-updated if
nobody has edited it in the app since the last ingest (``updated_at`` not
newer than ``ingested_at``); otherwise both sides moved and it's reported as a
conflict rather than silently overwritten.
"""

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
import sys
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

from lxml import etree
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from . import services, sources
from .db import engine
from .models import (
    Comment,
    CommentCreate,
    CommentPublic,
    Entry,
    EntryCreate,
    EntryPublic,
    EntryUpdate,
    IngestRunCreate,
    MentionAnchorUpsert,
    Project,
    Relation,
    RelationCreate,
)
from .services import ServiceError


TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"tei": TEI}
XML_ID = f"{{{XML}}}id"
XML_LANG = f"{{{XML}}}lang"

GND_RE = re.compile(r"gnd/([\w-]+)")
VIAF_RE = re.compile(r"viaf\.org/viaf/(\d+)")
WIKIDATA_RE = re.compile(r"wikidata\.org/(?:entity|wiki)/(Q\d+)")
# the schleiermacher place register routes its geonames URIs by this marker
# instead (see _split_idnos) — no regex, because nothing is extracted from them
GEONAMES_MARKER = "geonames.org"


def _date_text(v):
    """Keep the date string as written; drop values with no digit ('*', '†', '?', '').

    Uncertain dates ('nach 1824', 'um 1810', '3. Jh.') are preserved verbatim —
    ordering is handled by the derived birth_sort / death_sort columns, see
    ``dates.sorts_for``.
    """
    if not v:
        return None
    s = " ".join(str(v).split())
    return s if any(c.isdigit() for c in s) else None


COERCERS = {"birth_date": _date_text, "death_date": _date_text}


def _primary(v) -> str:
    """One display string from a scalar or a repeatable value (prefers ``deu``)."""
    if isinstance(v, list):
        if not v:
            return ""
        pick = next((x for x in v if x.get("lang") == "deu"), v[0])
        return str(pick.get("value", ""))
    return "" if v is None else str(v)


def _person_label(data: dict) -> str:
    """"Surname, Forename" when both are set, else whichever one is — matches the
    frontend ``personLabel`` so ingested and hand-edited labels agree."""
    s = _primary(data.get("surname")).strip()
    f = _primary(data.get("forename")).strip()
    return f"{s}, {f}" if s and f else (s or f)


# --- text helpers -------------------------------------------------------------

def _norm(text: str | None) -> str:
    """Collapse the pretty-printed XML whitespace into single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


_WS_RUN_RE = re.compile(r"(\s+)")


class _TextFlattener:
    """Builds ``_norm``'s output incrementally, one text piece at a
    time, exposing the current length as a stable position marker mid-walk.

    Used so a character offset captured *during* a document-order walk
    (e.g. where a ``persName[@key]`` note-link sits — see
    ``_note_link_offsets``) always lines up with ``_text``'s own
    output for the same element, by construction — one shared
    implementation, not two independently-written ones (a plain flatten
    pass and a position-tracking pass) that would have to be kept in sync
    by hand and could silently drift apart. ``_text`` itself is
    expressed in terms of this class below, for exactly that reason.

    Mirrors ``_norm``'s ``re.sub(r"\\s+", " ", text).strip()`` exactly,
    including collapsing a run of whitespace that spans *across* separate
    ``.append()`` calls (i.e. across an element boundary) to one space, and
    never emitting leading whitespace — confirmed to match ``_norm`` on a
    single joined string, not just on isolated pieces, since ``_norm``
    itself operates on the whole joined string at once and this class has
    to reproduce that exactly for offsets to be trustworthy.
    """

    __slots__ = ("_parts", "_pending_space", "_length")

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._pending_space = False
        self._length = 0

    def append(self, text: str) -> None:
        if not text:
            return
        for token in _WS_RUN_RE.split(text):
            if not token:
                continue
            if token.isspace():
                self._pending_space = True
                continue
            if self._pending_space and self._parts:
                self._parts.append(" ")
                self._length += 1
            self._parts.append(token)
            self._length += len(token)
            self._pending_space = False

    def mark(self) -> int:
        """The position, in the final normalised string, where content
        appended *right now* would start landing.

        Accounts for a whitespace run already seen but not yet flushed —
        it only materialises into a real character once more real content
        arrives (see ``append``), which is exactly the situation right
        before walking into a child element's own leading text. Confirmed
        by construction: a mark taken here, immediately followed by
        appending that child's content, always lines up with where its
        first real character actually ends up — unlike plain
        ``len(self.result())``, which would be off by one whenever a
        pending separator space is still waiting to be flushed.
        """
        return self._length + (1 if self._pending_space and self._parts else 0)

    def tip(self) -> int:
        """The position right after the last real character actually
        flushed so far — i.e. ``len(self.result())`` right now, *not*
        counting any not-yet-materialised pending whitespace.

        Deliberately does not use ``mark``'s look-ahead: a trailing
        whitespace run inside a just-walked child might go on to merge
        with unrelated content that follows it (a sibling's own text),
        the moment more content is appended — that merged separator
        character belongs to the gap between them, not to the child
        whose span just ended. Leaving it pending (not counted here)
        correctly excludes it either way — whether it stays pending
        forever (nothing else follows — `_norm`'s own ``.strip()`` would
        drop it too) or gets flushed later as a separator for whatever
        comes next.
        """
        return self._length

    def result(self) -> str:
        return "".join(self._parts)


_REF_TAG = f"{{{TEI}}}ref"
# a `ref` followed directly by one of these gets no separating space
_NO_SPACE_BEFORE = ",.;:)!?"


def _flatten_into(el, flattener: "_TextFlattener", spans: list | None = None) -> None:
    """Feed ``el``'s text content to ``flattener`` in document order — the one
    walk behind both ``_text`` and ``_note_link_offsets``, so the two
    can never disagree about what the flattened text is.

    The parts are joined without a separator, because the source carries its
    own whitespace between inline elements ("Cuba;" must not become
    "Cuba ;") — with one exception: the pretty-printed register files drop
    the space around a ``<ref>`` ("Georges<ref>Bd. 2</ref>"), so a ``ref``
    is padded with a space on both sides, except before closing punctuation
    (``_NO_SPACE_BEFORE``). Surplus spaces collapse in the flattener.

    A PI/comment contributes no text of its own, but its tail does (as in
    ``itertext()``). With ``spans``, the ``(key, start, end)`` of every
    ``persName``/``placeName``/``orgName`` ``[@key]`` is recorded.

    Args:
        el: The element whose text content is flattened.
        flattener: The ``_TextFlattener`` the text is appended to.
        spans: If given, ``(key, start, end)`` is appended for each link element,
            with ``start``/``end`` as offsets into the flattened text.
    """
    if el.text:
        flattener.append(el.text)
    for child in el:
        tag = child.tag
        if isinstance(tag, str):
            is_ref = tag == _REF_TAG
            if is_ref:
                flattener.append(" ")
            if spans is not None and tag in _LINK_TAGS and child.get("key"):
                start = flattener.mark()
                _flatten_into(child, flattener, spans)
                spans.append((child.get("key"), start, flattener.tip()))
            else:
                _flatten_into(child, flattener, spans)
            if is_ref and (child.tail or " ")[0] not in _NO_SPACE_BEFORE:
                flattener.append(" ")
        if child.tail:
            flattener.append(child.tail)


def _text(el) -> str:
    """Flatten an element to normalised plain text (see ``_flatten_into``
    for how the parts are joined). ``""`` when ``el`` is ``None``, so callers can
    pass the result of ``find()`` straight in.

    Expressed via ``_TextFlattener`` (not a separate
    ``_norm("".join(...))`` call) so this and ``_note_link_offsets``
    are guaranteed to agree on what the flattened text actually is.
    """
    if el is None:
        return ""
    flattener = _TextFlattener()
    _flatten_into(el, flattener)
    return flattener.result()


# --- register profiles --------------------------------------------------------

_PERSON_FIELDS = {
    "surname": "tei:persName[@type='reg']/tei:surname/text()",
    "forename": "normalize-space(tei:persName[@type='reg']/tei:forename)",
    "birth_date": "tei:birth/text()",
    "death_date": "tei:death/text()",
    "idno": {"each": "tei:idno", "attr": "type", "as": "type"},
}


# --- helpers shared by the custom extractors ----------------------------------
#
# The avhr, mega and schleiermacher registers do not fit a flat XPath field map:
# the label joins its parts conditionally, alternate names are collected across
# elements, and floruit / sex / note carry half their information in
# attributes. Hence a callable per register, built from the helpers below.

def _persname_parts(pn) -> tuple[str, str, str]:
    """Split one ``<persName>`` into its three possible name carriers.

    The avhr register uses either ``surname``+``forename`` or an undivided
    ``name``, never both. Returns ``(surname, forename, name)``; whichever
    variant the element does not use comes back as ``""``. A ``<persName>``
    holding bare text with no child elements is reported as
    ``("", "", <that text>)``.
    """
    surname = _text(pn.find("tei:surname", NS))
    forename = _text(pn.find("tei:forename", NS))
    name = _text(pn.find("tei:name", NS))
    if not (surname or forename or name):
        name = _text(pn)  # persName carrying bare text
    return surname, forename, name


def _display_name(surname: str, forename: str, name: str) -> str:
    """Join the parts of a name for display.

    ``"Surname, Forename"`` when both are present — the order the source files
    are alphabetised by — otherwise the first non-empty of surname, forename,
    name. ``""`` if all three are empty.
    """
    if surname and forename:
        return f"{surname}, {forename}"
    return surname or forename or name


AUTHORITY_RES = {
    "gnd": GND_RE,
    "viaf": VIAF_RE,
    "wikidata": WIKIDATA_RE,
}


def _idnos(
    record,
    path: str = "tei:idno",
    authorities: tuple[str, ...] = ("gnd", "viaf", "wikidata"),
) -> dict[str, str]:
    """Pull the authority-file ids out of a record's ``<idno>`` children.

    Used for ``<person>``; the schleiermacher ``<place>`` register routes its
    ``<idno>``s instead, see ``_split_idnos``. Direct children only (``path``
    is relative to the record), because ``<note>`` can carry its own markup and
    only the record's own children are register fields. ``idno_other`` is
    every matched ``<idno>`` joined with ``"; "`` as a lossless catch-all;
    each of ``authorities`` is the bare id extracted from the first matching
    URI, or ``""``.
    """
    uris = [_text(x) for x in record.findall(path, NS)]
    uris = [u for u in uris if u]
    out = {"idno_other": "; ".join(uris)}
    for key in authorities:
        rx = AUTHORITY_RES[key]
        out[key] = next((m.group(1) for u in uris if (m := rx.search(u))), "")
    return out


def _split_idnos(record, path: str, marker: str, key: str) -> dict[str, str]:
    """Route each ``<idno>`` into ``key`` or ``idno_other`` — verbatim, nothing stripped.

    Unlike ``_idnos``, which derives a bare id *in addition to* the lossless
    ``idno_other``, this splits the URIs into two disjoint buckets: those
    carrying ``marker`` go to ``key``, every other one to ``idno_other``. Both
    keep the full URI text, so export re-emits them unchanged — the schleiermacher
    place register writes 76 different spellings of the same GeoNames URI
    (``http://`` and ``https://``, slug suffixes like ``/2812482/halle.html``),
    and reconstructing one canonical form from a bare number would rewrite 809
    of its 1786 URIs. Matching is case-insensitive; several hits join with
    ``"; "`` like ``idno_other`` does.
    """
    uris = [u for x in record.findall(path, NS) if (u := _text(x))]
    hit = [u for u in uris if marker in u.lower()]
    rest = [u for u in uris if marker not in u.lower()]
    return {key: "; ".join(hit), "idno_other": "; ".join(rest)}


def _references(person) -> str:
    """Flatten the ``<linkGrp>`` pointers into one string.

    Every ``<ptr>`` as ``"<type>/<subtype>:<target>"`` (the ``/<subtype>`` part
    only where the attribute is present), joined with ``"; "`` — e.g.
    ``"letter/comment:14#9; page:26#323-325"``. ``""`` for a person without a
    ``<linkGrp>``. A missing ``@type`` becomes ``"?"``.
    """
    parts = []
    for grp in person.findall("tei:linkGrp", NS):
        for ptr in grp.findall("tei:ptr", NS):
            kind = ptr.get("type") or "?"
            if subtype := ptr.get("subtype"):
                kind = f"{kind}/{subtype}"
            parts.append(f"{kind}:{ptr.get('target') or ''}")
    return "; ".join(parts)


_ALT_SUBTYPES = {"birthname": "birth_names", "pseudonym": "pseudonyms"}


def _alt_names(person) -> dict[str, list[dict]]:
    """Sort a person's ``persName[@type='alt']`` into fields by ``@subtype``.

    MEGA and Schleiermacher mark birth names and pseudonyms with ``@subtype``
    (the Schleiermacher guideline keeps them apart from other variants), so
    they get fields of their own; a variant without — or with an unknown —
    subtype lands in ``alt_names``. Each item keeps its own shape —
    ``{surname, forename}`` where the source splits it, ``{value: <name>}``
    otherwise — same as mop's ``alt_names``, so a source's surname/forename
    split survives the export (376 of mega+schleiermacher's alt names have
    one). Empty buckets return ``[]``,
    dropped like any other empty value by ``extract``.
    """
    out: dict[str, list[dict]] = {"alt_names": [], "birth_names": [], "pseudonyms": []}
    for pn in person.findall("tei:persName[@type='alt']", NS):
        surname, forename, name = _persname_parts(pn)
        item: dict[str, str] = {}
        if surname:
            item["surname"] = surname
        if forename:
            item["forename"] = forename
        if not item and name:
            item["value"] = name
        if item:
            out[_ALT_SUBTYPES.get(pn.get("subtype"), "alt_names")].append(item)
    return out


# --- editorial comments + note-links -------------------------------------------
#
# oxy_comment_start/end PIs and <note>'s persName/placeName/orgName[@key]
# cross-references are the same parsing problem: both need to know which
# *field* a position in the document falls in, and a comment can start in
# one field (e.g. <surname>) and end in another (e.g. <note>) — confirmed a
# real, common pattern in the corpus, not a hypothetical edge case (see
# docs/ingest/links-and-comments.md). So both are collected in one document-order walk of
# the whole <person> record, not by parsing <note> in isolation.

# tag -> approximate data-field name, best-effort only (not authoritative —
# a project's own extractor is the real source of truth for field names;
# this is just enough to anchor a comment/link to "roughly which field",
# see Comment.start_field/end_field and docs/ingest/links-and-comments.md)
_FIELD_BY_TAG = {
    "surname": "surname",
    "forename": "forename",
    "name": "name",
    "birth": "birth_date",
    "death": "death_date",
    "note": "note",
    "sex": "sex",
}

_THREAD_ATTRS = ("mid", "id", "parentID")
# stable stand-in for plain <!-- --> comments, which carry no real timestamp
# in the source — see _walk_record_xml_comments
_NO_TIMESTAMP = datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()


def _parse_oxy_timestamp(raw: str) -> str:
    """oXygen's own compact timestamp (``20240124T162910+0100``) as an ISO
    8601 string this stack's reconciliation can compare reliably.

    Python's ``datetime.fromisoformat`` (3.11+) already accepts the compact
    form. The source's own wall-clock time is kept and its offset dropped —
    what ``export`` writes back is that same wall-clock time, so a round trip
    leaves the PI unchanged. The value is tagged UTC only because SQLModel's
    datetime columns store timezone-aware values (and read them back as UTC):
    the numbers go in and come out unchanged. ``_reconcile_comments``
    compares parsed datetimes, not these strings. Falls back to
    ``_NO_TIMESTAMP`` for a missing or unparseable value rather than
    failing the whole record over one malformed comment attribute.
    """
    if not raw:
        return _NO_TIMESTAMP
    try:
        return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return _NO_TIMESTAMP


def _thread_meta(attrs: dict[str, str]) -> str | None:
    """Raw mid/id/parentID attributes from an oxy_comment_start PI, verbatim,
    joined for storage — only set when at least one is actually present (most
    comments carry none of these; they mark a source reply-thread, see
    Comment.thread_meta)."""
    parts = [f'{k}="{attrs[k]}"' for k in _THREAD_ATTRS if attrs.get(k)]
    return " ".join(parts) or None


def _wrapper_field(el) -> str | None:
    """The field a ``persName``/``placeName`` *wrapper* conceptually
    represents, for a comment that brackets the whole element rather than
    one of its own leaf children — the wrapper's own tag isn't itself in
    ``_FIELD_BY_TAG`` (only ``surname``/``forename``/``name`` are), so the
    ordinary field-propagation in ``_walk_record_comments`` never
    reaches a PI that's merely a *sibling* of the wrapper (before or after
    it), not a descendant. Confirmed a real corpus shape (~15% of oxy
    comments wrap a whole nested cross-reference element like this, not a
    hypothetical) — without this, such a comment lands unattached
    (``None``, ``None``) and is exiled to the very end of the record on
    export, instead of staying anchored near the name it actually concerns.
    Looks one level down for the wrapper's first mapped-field descendant.
    """
    if etree.QName(el).localname not in ("persName", "placeName"):
        return None
    for descendant in el.iter():
        if descendant is el or not isinstance(descendant.tag, str):
            continue
        if field := _FIELD_BY_TAG.get(etree.QName(descendant).localname):
            return field
    return None


_LINK_TAGS = (f"{{{TEI}}}persName", f"{{{TEI}}}placeName", f"{{{TEI}}}orgName")
# a nested list of records (a place's sub-places in its own listPlace) holds
# records in their own right — their comments and links belong to them, not
# to the record that contains them
_NESTED_LIST_TAGS = (f"{{{TEI}}}listPlace", f"{{{TEI}}}listPerson", f"{{{TEI}}}listOrg")


def _in_nested_list(node, record) -> bool:
    """Whether ``node`` sits inside a nested record list of ``record``."""
    for ancestor in node.iterancestors():
        if ancestor is record:
            return False
        if ancestor.tag in _NESTED_LIST_TAGS:
            return True
    return False


def _walk_record_comments(person) -> tuple[list[dict], list[dict]]:
    """Walk one ``<person>`` record in document order, pairing
    ``oxy_comment_start``/``oxy_comment_end`` PIs and collecting
    ``persName``/``placeName``/``orgName`` ``[@key]`` cross-references found along the
    way. Requires the record to have been parsed with ``remove_pis=False``
    (PIs appear as regular children in iteration order otherwise they're
    gone before this ever runs).

    Returns ``(comments, links)``:

    - each comment: ``{"text", "author", "created_at", "start_field",
      "end_field", "thread_meta"}`` — ``start_field``/``end_field`` are
      ``None`` when the boundary falls between fields rather than inside one
      (an empty position-marker pair, or a span with no clear start/end
      element — confirmed a real, common shape, not a fallback for a bug).
      A boundary immediately touching a whole ``persName``/``placeName``
      wrapper (rather than one of its own children) falls back to that
      wrapper's own field — see ``_wrapper_field``.
    - each link: ``{"key", "field"}`` — ``key`` is the referenced record's
      own ``xml:id``, resolved to an entry id by the caller once every
      record in the run is already in the DB (same two-pass shape as
      ``ingest_schleiermacher_groups``, for the same reason: the
      referenced person may be defined later in the same run, or in a
      different file).

    An ``oxy_comment_end`` with nothing open, or a start left unclosed at
    the end of the record, is silently dropped rather than guessed at —
    malformed source PI pairing, not something to paper over.
    """
    comments: list[dict] = []
    links: list[dict] = []
    open_stack: list[dict] = []  # unclosed starts, most-recently-opened last

    def field_of(el) -> str | None:
        return _FIELD_BY_TAG.get(etree.QName(el).localname)

    def walk(el, current_field: str | None) -> None:
        current_field = field_of(el) or current_field
        for child in el:
            tag = child.tag
            if isinstance(tag, str):
                if tag in _NESTED_LIST_TAGS:
                    continue
                if tag in _LINK_TAGS and child.get("key"):
                    links.append({"key": child.get("key"), "field": current_field})
                walk(child, current_field)
            elif tag is etree.PI:
                if child.target == "oxy_comment_start":
                    attrs = dict(re.findall(r'(\w+)="([^"]*)"', child.text or ""))
                    start_field = current_field
                    if start_field is None:
                        nxt = child.getnext()
                        if nxt is not None and isinstance(nxt.tag, str):
                            start_field = _wrapper_field(nxt)
                    open_stack.append(
                        {
                            "text": attrs.get("comment", ""),
                            "author": attrs.get("author", ""),
                            "created_at": _parse_oxy_timestamp(attrs.get("timestamp", "")),
                            "start_field": start_field,
                            "thread_meta": _thread_meta(attrs),
                        }
                    )
                elif child.target == "oxy_comment_end" and open_stack:
                    started = open_stack.pop()
                    end_field = current_field
                    if end_field is None:
                        prv = child.getprevious()
                        if prv is not None and isinstance(prv.tag, str):
                            end_field = _wrapper_field(prv)
                    started["end_field"] = end_field
                    comments.append(started)

    walk(person, None)
    return comments, links


def _walk_record_xml_comments(person) -> list[dict]:
    """Collect plain ``<!-- -->`` comments on one ``<person>`` record —
    avhr's dominant comment style, distinct from oxy PIs: no author/timestamp
    attributes, and mostly **fixed-position convention rather than true
    field-proximity** (confirmed against the real corpus, see
    docs/ingest/links-and-comments.md) — ~45% sit right after ``<person>``'s opening tag
    (identity/research notes, regardless of which field they concern), ~15%
    right before ``</person>`` (source citations for the whole record); only
    a comment that is itself a child of ``<note>`` is anchored to it. A
    comment that wraps actual markup (an XML fragment, not prose — ~2% of
    the real corpus) is skipped: that's a deactivated record/field, a
    different and unrelated thing from an editorial remark.
    """
    out: list[dict] = []
    for node in person.iter():
        if node.tag is not etree.Comment:
            continue
        if _in_nested_list(node, person):
            continue
        text = _norm(node.text or "")
        if not text or re.search(r"<[a-zA-Z]", text):
            continue
        parent = node.getparent()
        field = "note" if parent is not None and etree.QName(parent).localname == "note" else None
        out.append(
            {
                "text": text,
                "author": "",
                # no timestamp exists in the source for this comment style;
                # a *fixed* sentinel, not the ingest run's own time — the
                # reconciliation natural key needs this stable across runs,
                # or the same comment would look "new" and get re-created
                # every single re-ingest (see _reconcile_comments)
                "created_at": _NO_TIMESTAMP,
                "start_field": field,
                "end_field": field,
                "thread_meta": None,
            }
        )
    return out


def _note_link_offsets(note_el) -> list[dict]:
    """Walk ``note_el`` in the same document order ``_text`` (via
    ``itertext()``) flattens it, recording the exact character-offset span
    each ``persName``/``placeName``/``orgName`` ``[@key]`` child's own text occupies
    in the resulting normalised string.

    Used to store an exact position for a ``mentions`` link at ingest
    time, so export can splice it back in without guessing — see
    ``export._emit_mentions``, which self-validates a stored span against
    the *current* note text at export time (does ``note[start:end]`` still
    equal what was captured here?), splices the valid ones with
    ``export._splice_anchored_mentions`` and falls back to the search
    heuristic (``export._splice_mention``) when a span no longer matches
    (the note was edited in the app since ingest). A stale anchor is
    simply ignored, never trusted.

    Built on ``_TextFlattener`` — the same class ``_text`` itself
    uses — rather than a second, separately-written flattening pass,
    so an offset captured here is guaranteed to land on the same string
    ``_text`` produces for the same note; two independent
    implementations of "collapse this XML's whitespace" would risk
    silently drifting apart as either one is changed later.

    Returns ``[{"key", "start", "end", "text"}, ...]`` in document order;
    ``[]`` if ``note_el`` is ``None``. A key appearing more than once
    keeps only its *last* occurrence's span, matching
    ``_reconcile_relations_multi``'s one-row-per-``(subject, object)``
    shape — there is only ever one relation to anchor either way.
    """
    if note_el is None:
        return []
    flattener = _TextFlattener()
    spans: list[tuple[str, int, int]] = []
    _flatten_into(note_el, flattener, spans)
    full_text = flattener.result()
    by_key: dict[str, tuple[int, int]] = {}
    for key, start, end in spans:
        by_key[key] = (start, end)
    return [
        {"key": key, "start": start, "end": end, "text": full_text[start:end]}
        for key, (start, end) in by_key.items()
    ]


# --- avhr — edition humboldt digital -------------------------------------------

def extract_ehd_person(person) -> dict:
    """Map one avhr-register ``<person>`` onto its label and ``data`` bag.

    Changes to the base schema are listed in ``projects/avhr/__init__.py``; absent values
    are ``""`` and get stripped by ``extract``.
    """
    reg = person.find("tei:persName[@type='reg']", NS)
    # `is not None`: an lxml element without children is falsy, and a persName
    # carrying bare text has none — `if reg` would drop exactly those.
    surname, forename, name = _persname_parts(reg) if reg is not None else ("", "", "")

    data: dict[str, object] = {
        "surname": surname,
        "forename": forename,
        "name": name,
        # structured, like mop's alt_names: {surname, forename} where the source
        # splits it, else {value: <bare name>}; @subtype (birthname/pseudonym)
        # carried through as "kind" — not shown as a form field (see projects/avhr/__init__.py)
        "alt_names": _multi(
            person,
            {
                "each": "tei:persName[@type='alt']",
                "attr": "subtype",
                "as": "kind",
                "parts": {"surname": "tei:surname", "forename": "tei:forename"},
            },
        ),
        "old_id": person.get("oldID") or "",
        "duplicate_of": person.get("duplicate") or "",
        "role": person.get("role") or "",
        "resp": person.get("resp") or "",
        "references": _references(person),
    }
    # restricted to @type='uri' (like mega/schleiermacher): export always
    # rebuilds idno_other as <idno type="uri">, so idno_other must never
    # contain a differently-typed idno in the first place
    data.update(_idnos(person, "tei:idno[@type='uri']"))

    # kept as text, not coerced to int: a minority are "ca. 460", "63 v. Chr.",
    # "1778/1780" — see the schema override in projects/avhr/__init__.py
    for tag, key in (("birth", "birth_date"), ("death", "death_date")):
        data[key] = _text(person.find(f"tei:{tag}", NS))

    if (floruit := person.find("tei:floruit", NS)) is not None:
        data["floruit"] = _text(floruit)
        data["floruit_notbefore"] = floruit.get("notBefore") or ""
        data["floruit_notafter"] = floruit.get("notAfter") or ""

    if (sex := person.find("tei:sex", NS)) is not None:
        data["sex"] = sex.get("value") or ""
        data["sex_evidence"] = sex.get("evidence") or ""

    if (note := person.find("tei:note", NS)) is not None:
        # flattened to plain text; the @key cross-references inside it (persName,
        # placeName, orgName) would belong in the `relation` table, not here.
        data["note"] = _text(note)
        data["note_resp"] = note.get("resp") or ""

    return {"label": _display_name(surname, forename, name), "data": data}


def extract_ehd_place(place) -> dict:
    """Map one avhr-``Orte/*.xml`` ``<place>`` onto its label and ``data`` bag.

    Shaped like ``extract_schleiermacher_place``. The register is ingested
    mainly so the ``placeName[@key]`` links in the person notes resolve to a
    target (see ``ingest_comments_and_links``); the place notes carry
    such links themselves. ``@type`` comes in through the profile's
    ``attrs``, and a nested ``listPlace`` becomes ``part_of`` relations
    (``ingest_schleiermacher_place_nesting``), not a field.

    Args:
        place: One ``<place>`` element of the register.

    Returns:
        ``{"label": ..., "data": ...}``: the entry's label (the regular name) and
        its ``data`` bag. Empty values are dropped later, by ``extract``.
    """
    name = _text(place.find("tei:placeName[@type='reg']", NS))
    note = place.find("tei:note", NS)
    data: dict[str, object] = {
        "placename": name,
        # @subtype ("contemporary", the only value) kept as the qualifier
        "alt_names": _multi(
            place, {"each": "tei:placeName[@type='alt']", "attr": "subtype", "as": "subtype"}
        ),
        "note": _text(note),
        "note_resp": (note.get("resp") or "") if note is not None else "",
        "old_id": place.get("oldID") or "",
        "resp": place.get("resp") or "",
        "role": place.get("role") or "",
        "references": _references(place),
    }
    # every <idno> in the register is @type='uri'; geonames.org ones to `geonames`
    data.update(_split_idnos(place, "tei:idno[@type='uri']", GEONAMES_MARKER, "geonames"))
    return {"label": name, "data": data}


def extract_ehd_organisation(org) -> dict:
    """Map one avhr-``Einrichtungen.xml`` ``<org>`` onto its label and ``data`` bag.

    Shaped like ``extract_schleiermacher_organisation``: ``desc`` is
    flattened to plain text, its ``orgName``/``placeName``/``persName``
    ``[@key]`` links become ``mentions`` relations. ``<location>`` (the
    institution's address: a GeoNames ``idno``, ``settlement[@key]`` and an
    address ``note``) is not captured.

    Args:
        org: One ``<org>`` element of the register.

    Returns:
        ``{"label": ..., "data": ...}``: the entry's label (the regular name) and
        its ``data`` bag. Empty values are dropped later, by ``extract``.
    """
    name = _text(org.find("tei:orgName[@type='reg']", NS))
    data: dict[str, object] = {
        "orgname": name,
        "alt_names": _multi(org, {"each": "tei:orgName[@type='alt']"}),
        # at most one per org, always @type='uri'
        "idno_uri": _text(org.find("tei:idno[@type='uri']", NS)),
        "description": _text(org.find("tei:desc", NS)),
        "old_id": org.get("oldID") or "",
        "references": _references(org),
    }
    return {"label": name, "data": data}


# --- mega — Marx-Engels-Gesamtausgabe -----------------------------------------

def extract_mega_person(person) -> dict:
    """Map one MEGA-register ``<person>`` onto its label and ``data`` bag.

    Changes to the base schema are listed in ``projects/mega/__init__.py``; absent values
    are ``""`` and get stripped by ``extract``.
    """
    reg = person.find("tei:persName[@type='reg']", NS)
    surname, forename, name = _persname_parts(reg) if reg is not None else ("", "", "")

    # the register number is not unique across persons, and a few persons list
    # two (once the same one twice): keep each distinct value once
    mega_ids = dict.fromkeys(_text(x) for x in person.findall("tei:idno[@type='mega']", NS))

    data: dict[str, object] = {
        "surname": surname,
        "forename": forename,
        "name": name,
        **_alt_names(person),
        "internal_id": person.get(XML_ID) or "",
        "old_id": person.get("oldID") or "",
        "mega_id": "; ".join(m for m in mega_ids if m),
        "role": person.get("role") or "",
        "references": _references(person),
    }
    # only the uri idnos: idno[@type='mega'] is the register number above
    data.update(_idnos(person, "tei:idno[@type='uri']", ("gnd", "viaf")))

    # kept as text, not coerced to int: a minority are "ca. 1822", "241 v. Chr.",
    # "1814 oder 1815" — see the schema override in projects/mega/__init__.py
    for tag, key in (("birth", "birth_date"), ("death", "death_date")):
        data[key] = _text(person.find(f"tei:{tag}", NS))

    if (floruit := person.find("tei:floruit", NS)) is not None:
        data["floruit"] = _text(floruit)
        data["floruit_notbefore"] = floruit.get("notBefore") or ""
        data["floruit_notafter"] = floruit.get("notAfter") or ""

    if (sex := person.find("tei:sex", NS)) is not None:
        data["sex"] = sex.get("value") or ""
        data["sex_evidence"] = sex.get("evidence") or ""

    if (note := person.find("tei:note", NS)) is not None:
        data["note"] = _text(note)

    return {"label": _display_name(surname, forename, name), "data": data}


# --- schleiermacher — Schleiermacher in Berlin --------------------------------

def extract_schleiermacher_person(person) -> dict:
    """Map one Schleiermacher-register ``<person>`` onto its label and ``data`` bag.

    Changes to the base schema are listed in ``projects/schleiermacher/__init__.py``;
    absent values are ``""`` and get stripped by ``extract``.
    """
    reg = person.find("tei:persName[@type='reg']", NS)
    surname, forename, name = _persname_parts(reg) if reg is not None else ("", "", "")
    # the call name stays part of the flattened forename as well
    used = reg.find("tei:forename/tei:name[@type='used']", NS) if reg is not None else None
    # so far only empty in the register, i.e. nothing is stored yet
    name_link = reg.find("tei:nameLink", NS) if reg is not None else None

    data: dict[str, object] = {
        "surname": surname,
        "forename": forename,
        "name": name,
        "used_name": _text(used),
        "name_link": _text(name_link),
        **_alt_names(person),
        "role": person.get("role") or "",
    }
    data.update(_idnos(person, "tei:idno[@type='uri']", ("gnd", "viaf")))

    # a family (a nested listPerson[@type='group']) is not a person field: it's
    # its own `group` entry and a member_of relation, built by
    # ingest_schleiermacher_groups() after every person in the file is in the
    # DB — see PROFILES["schleiermacher_persons"]["post_ingest"] and docs/ingest/

    # free text, often with the place appended: "30. November 1765 (Roxheim)"
    for tag, key in (("birth", "birth_date"), ("death", "death_date")):
        data[key] = _text(person.find(f"tei:{tag}", NS))

    if (sex := person.find("tei:sex", NS)) is not None:
        data["sex"] = sex.get("value") or ""
        data["sex_evidence"] = sex.get("evidence") or ""
        data["sex_resp"] = sex.get("resp") or ""
        data["sex_cert"] = sex.get("cert") or ""

    # at most one wedding per person in the register; joined should there be more
    weddings = person.findall("tei:event[@type='wedding']", NS)
    data["wedding"] = "; ".join(filter(None, (w.get("when") for w in weddings)))
    data["wedding_note"] = "; ".join(
        filter(None, (_text(w.find("tei:note", NS)) for w in weddings))
    )

    if (note := person.find("tei:note", NS)) is not None:
        # flattened to plain text, as for avhr: the persName/placeName @key
        # cross-references would belong in the `relation` table
        data["note"] = _text(note)

    return {"label": _display_name(surname, forename, name), "data": data}


def extract_schleiermacher_place(place) -> dict:
    """Map one Schleiermacher-``Orte.xml`` ``<place>`` onto its label and ``data`` bag.

    Changes to the base place schema are listed in ``projects/schleiermacher/__init__.py``;
    absent values are ``""`` / ``None`` and get stripped by ``extract``.

    A flat ``fields`` map would almost do here, but two things need code: a
    ``<note>`` has to be flattened across its inline markup (467 of 1840 notes
    carry ``<placeName>`` / ``<persName>`` cross-references), and the
    ``<idno>`` URIs are routed verbatim into ``geonames`` / ``idno_other``
    (``_split_idnos``).

    ``@type`` (the kind of place) is carried by the profile's ``attrs``
    channel, and a nested ``listPlace`` is not read here at all — sub-places
    are records in their own right (``record_xpath`` matches them too) and get
    a ``part_of`` relation from ``ingest_schleiermacher_place_nesting``
    once every place in the run is in the DB.
    """
    # exactly one per place in the whole register, never empty
    name = _text(place.find("tei:placeName[@type='reg']", NS))

    data: dict[str, object] = {
        "placename": name,
        # plain strings — unlike the person register's alternate names there is
        # no surname/forename split to keep, so this is an ordinary repeatable
        # field rather than an extra_keys structure
        "alt_names": _multi(place, {"each": "tei:placeName[@type='alt']"}),
          # every <note> flattened and joined: two places carry an empty <note/>
        # *before* the one with the actual text, so reading only the first
        # (as the person extractor does) would drop their content
        "note": "; ".join(
            filter(None, (_text(n) for n in place.findall("tei:note", NS)))
        ),
    }
    # at most one <idno> per place, always @type='uri' — restricted to that
    # type for the same reason as the person profiles: export rebuilds both
    # fields as <idno type="uri">, so nothing else may end up in them. A
    # geonames.org URI is the `geonames` field itself, not a derived view of
    # idno_other — both are re-emitted verbatim, see _split_idnos
    data.update(_split_idnos(place, "tei:idno[@type='uri']", GEONAMES_MARKER, "geonames"))

    return {"label": name, "data": data}


def extract_schleiermacher_organisation(org) -> dict:
    """Map one ``Koerperschaften.xml`` ``<org>`` onto its label and ``data`` bag.

    ``desc`` is flattened to plain text; its ``persName[@key]`` links become
    ``mentions`` relations in the shared comments/links pass. A parent
    institution (a nested ``listOrg`` with ``head``) is not read here — see
    ``ingest_schleiermacher_groups``.

    Args:
        org: One ``<org>`` element of the register.

    Returns:
        ``{"label": ..., "data": ...}``: the entry's label (the regular name) and
        its ``data`` bag. Empty values are dropped later, by ``extract``.
    """
    name = _text(org.find("tei:orgName[@type='reg']", NS))
    data: dict[str, object] = {
        "orgname": name,
        "alt_names": _multi(org, {"each": "tei:orgName[@type='alt']"}),
        # one idno in the whole register, always @type='uri' (a GND link)
        "idno_uri": _text(org.find("tei:idno[@type='uri']", NS)),
        "description": _text(org.find("tei:desc", NS)),
    }
    return {"label": name, "data": data}


def extract_schleiermacher_glossary(item) -> dict:
    """Map one ``Glossar.xml`` ``<item>`` onto its label and ``data`` bag.

    ``note`` is the flattened ``p`` paragraphs *without* the trailing
    ``p[@type='source']``, which is its own field. ``desc`` / ``note`` keep their
    ``@resp`` verbatim (``#FK`` and ``FS`` are both attested, not normalised);
    the category is ``interp/@id`` without its ``#``.

    Args:
        item: One ``<item>`` element of the glossary.

    Returns:
        ``{"label": ..., "data": ...}``: the entry's label (the regular term) and
        its ``data`` bag. Empty values are dropped later, by ``extract``.
    """
    label_el = item.find("tei:label[@type='reg']", NS)
    name = _text(label_el)
    desc = item.find("tei:desc", NS)
    note = item.find("tei:note", NS)
    paragraphs = [] if note is None else note.findall("tei:p", NS)
    body = [p for p in paragraphs if p.get("type") != "source"]
    if note is None:
        note_text = ""
    elif paragraphs:
        note_text = " ".join(filter(None, (_text(p) for p in body)))
    else:
        note_text = _text(note)
    interp = item.find("tei:interp", NS)
    data: dict[str, object] = {
        "term": name,
        "term_lang": label_el.get(XML_LANG) if label_el is not None else None,
        "alt_names": _multi(item, {"each": "tei:label[@type='alt']"}),
        "desc": _text(desc),
        "desc_resp": desc.get("resp") if desc is not None else None,
        "note": note_text,
        "note_resp": note.get("resp") if note is not None else None,
        "source": "; ".join(
            filter(None, (_text(p) for p in paragraphs if p.get("type") == "source"))
        ),
        "category": (interp.get("id") or "").lstrip("#") if interp is not None else None,
    }
    return {"label": name, "data": data}


def _contributors(bibl, tag: str) -> list[dict] | None:
    """The ``author`` / ``editor`` elements of one ``<bibl>`` as a list of
    ``{surname, forename | name | orgname, key, role}`` (empty parts omitted).

    A contributor with nothing in it — the register's way of saying "author
    unknown" is ``<author><persName><surname/><forename/></persName></author>`` —
    becomes ``{"unknown": True}``, so the element still comes back on export.
    ``key`` is the ``xml:id`` of the person (or, once, the organisation) in its
    own register.

    Args:
        bibl: One ``<bibl>`` element of the works register.
        tag: ``"author"`` or ``"editor"``: which contributors to read.

    Returns:
        One dict per matching element, in document order, or ``None`` when
        there is none.
    """
    out = []
    for el in bibl.findall(f"tei:{tag}", NS):
        item: dict[str, object] = {}
        if (pn := el.find("tei:persName", NS)) is not None:
            for part in ("surname", "forename", "name"):
                if value := _text(pn.find(f"tei:{part}", NS)):
                    item[part] = value
            if pn.get("key"):
                item["key"] = pn.get("key")
        elif (on := el.find("tei:orgName", NS)) is not None:
            if value := _text(on):
                item["orgname"] = value
            if on.get("key"):
                item["key"] = on.get("key")
        if el.get("role"):
            item["role"] = el.get("role")
        out.append(item or {"unknown": True})
    return out or None


def extract_schleiermacher_work(bibl) -> dict:
    """Map one ``Werke.xml`` ``<bibl>`` onto its label and ``data`` bag.

    ``authors`` / ``editors`` are structured lists (``_contributors``), not
    form fields — see ``extra_keys`` in the work schema. ``pubPlace/@key`` is the
    ``pub_place_key`` field; ``persName``/``placeName`` ``[@key]`` links inside
    ``note`` become ``mentions`` relations in the shared comments/links pass (the
    contributors' own ``persName[@key]`` deliberately do not,
    ``links_only_in_note``). The ``title`` is flattened, so the one ``bibl`` that
    sits *inside* a title (``@sameAs``, no ``xml:id``) is part of that text and
    not a record of its own (the profile's ``record_xpath`` excludes it). The
    kind of work (``@type``) is carried by the profile's ``attrs``.

    Args:
        bibl: One top-level ``<bibl>`` element of the works register.

    Returns:
        ``{"label": ..., "data": ...}``: the entry's label (the flattened title)
        and its ``data`` bag. Empty values are dropped later, by ``extract``.
    """
    title = _text(bibl.find("tei:title", NS))
    place = bibl.find("tei:pubPlace", NS)
    data: dict[str, object] = {
        "title": title,
        "authors": _contributors(bibl, "author"),
        "editors": _contributors(bibl, "editor"),
        "pub_place": _text(place),
        "pub_place_key": place.get("key") if place is not None else None,
        "date": _text(bibl.find("tei:date", NS)),
        "note": _text(bibl.find("tei:note", NS)),
    }
    return {"label": title, "data": data}


def extract_schleiermacher_bible_book(item) -> dict:
    """Map one ``bibelsystematik.xml`` ``<item>`` onto its label and ``data`` bag.

    The canon part is not on the item but on the ``list[@type]`` two levels up
    (``list[@type]/list/item``). The file has no ``xml:id`` per book and its
    ``<idno>`` (Kurzsigle) is not unique (``Jud`` twice), so the ``source_id``
    is derived from the register-wide ``@n`` — see the profile's ``source_id``.
    Empty ``label`` elements (``gruppea``/``gruppeb`` are often present but blank)
    are stripped by ``extract``.

    Args:
        item: One ``<item>`` element of the bible books register.

    Returns:
        ``{"label": ..., "data": ...}``: the entry's label (the book's name) and
        its ``data`` bag.
    """

    def label(unit: str) -> str:
        """Text of the item's ``label`` with this ``@unit`` (``""`` if absent).

        Args:
            unit: The ``@unit`` value, e.g. ``"abk"`` for the abbreviation.
        """
        return _text(item.find(f"tei:label[@unit='{unit}']", NS))

    name = label("name")
    n = item.get("n")
    canon = item.getparent().getparent()
    data: dict[str, object] = {
        "name": name,
        "sigle": _text(item.find("tei:idno", NS)),
        "abbr": label("abk"),
        "name2": label("name2"),
        "abbr2": label("abk2"),
        "canon_part": canon.get("type"),
        "position": int(n) if n and n.isdigit() else None,
        "group_a": label("gruppea"),
        "group_b": label("gruppeb"),
        "group_c": label("gruppec"),
    }
    return {"label": name, "data": data}


PROFILES: dict[str, dict] = {
    "leibniz5": {
        "source": "Personen/*.xml",
        "entry_type": "person",
        "record_xpath": "//tei:listPerson/tei:person",
        "label": _person_label,
        "fields": _PERSON_FIELDS,
    },
    "mop": {
        "source": "Personen/*.xml",
        "entry_type": "person",
        "record_xpath": "//tei:listPerson/tei:person",
        "label": _person_label,
        "fields": {
            **_PERSON_FIELDS,
            # every non-reg persName is <persName type="alt" [subtype="birthname|pseudonym"]>;
            # keep surname/forename split where the source has it, else a plain <name>
            "alt_names": {
                "each": "tei:persName[@type='alt']",
                "attr": "subtype",
                "as": "kind",
                "parts": {"surname": "tei:surname", "forename": "tei:forename"},
            },
            "note": "normalize-space(tei:note)",
        },
        "attrs": {"oldID": "old_id"},  # legacy ediarum id, kept for reference resolution
    },
    "pta": {
        "source": "pta_persons.xml",  # assumed filename directly under Register/ — first real sync confirms/corrects
        "entry_type": "person",
        "record_xpath": "//tei:listPerson/tei:person",
        "label": _person_label,
        "fields": {
            "forename": {"each": "tei:persName/tei:forename", "attr": XML_LANG, "as": "lang"},
            "surname": {"each": "tei:persName/tei:surname", "attr": XML_LANG, "as": "lang"},
            "epithet": {
                "each": "tei:persName/tei:addName[@type='epithet']",
                "attr": XML_LANG,
                "as": "lang",
            },
            "floruit": "normalize-space(tei:floruit)",
            "idno": {"each": "tei:idno", "attr": "type", "as": "type"},
            "note": "normalize-space(tei:note)",
        },
    },
    "avhr": {
        "source": "Personen/*.xml",
        "entry_type": "person",
        "record_xpath": "//tei:listPerson/tei:person",
        "extract": extract_ehd_person,
    },
    # the targets of the placeName/orgName links in the person notes
    "avhr_places": {
        "project": "avhr",
        "source": "Orte/*.xml",
        "entry_type": "place",
        # also matches the sub-places one level down, in a place's own listPlace
        "record_xpath": "//tei:listPlace/tei:place",
        "extract": extract_ehd_place,
        "attrs": {"type": "place_type"},
    },
    "avhr_organisations": {
        "project": "avhr",
        "source": "Einrichtungen.xml",
        "entry_type": "organisation",
        "record_xpath": "//tei:listOrg/tei:org",
        "extract": extract_ehd_organisation,
        # the links sit in <desc>, not <note>
        "note_tag": "desc",
    },
    "mega": {
        "source": "Personen/*.xml",
        "entry_type": "person",
        "record_xpath": "//tei:listPerson/tei:person",
        "extract": extract_mega_person,
    },
    # schleiermacher has two registers, so each gets a profile key of its own
    # and names its project explicitly (see `project` / project_of())
    "schleiermacher_persons": {
        "project": "schleiermacher",
        "source": "Personen/*.xml",
        "entry_type": "person",
        # also matches the persons one level down, in a family listPerson
        "record_xpath": "//tei:listPerson/tei:person",
        # Z.xml has an unfilled template id, xml:id="${ediarum_id}", which is
        # not well-formed and would otherwise abort the whole file
        "recover": True,
        "extract": extract_schleiermacher_person,
    },
    "schleiermacher_places": {
        "project": "schleiermacher",
        "source": "Orte.xml",
        "entry_type": "place",
        # also matches the sub-places one level down, in a place's own listPlace
        "record_xpath": "//tei:listPlace/tei:place",
        "extract": extract_schleiermacher_place,
        # the kind of place lives on the record element, not in a child
        "attrs": {"type": "place_type"},
    },
    "schleiermacher_organisations": {
        "project": "schleiermacher",
        "source": "Koerperschaften.xml",
        "entry_type": "organisation",
        # also the orgs inside a nested listOrg (grouped under a parent institution)
        "record_xpath": "//tei:listOrg//tei:org",
        "extract": extract_schleiermacher_organisation,
        # a nested listOrg/head is a group entry, like a person family
        "group_xpath": "//tei:listOrg/tei:listOrg",
        "group_member": "tei:org",
        # persName[@key] links sit in <desc>, not <note>
        "note_tag": "desc",
    },
    "schleiermacher_glossary": {
        "project": "schleiermacher",
        "source": "Glossar.xml",
        "entry_type": "glossary",
        "record_xpath": "//tei:body/tei:list/tei:item",
        "extract": extract_schleiermacher_glossary,
    },
    "schleiermacher_works": {
        "project": "schleiermacher",
        "source": "Werke.xml",
        "entry_type": "work",
        # not the bibl nested in a title — see extract_schleiermacher_work
        "record_xpath": "//tei:listBibl//tei:bibl[not(ancestor::tei:bibl)]",
        "extract": extract_schleiermacher_work,
        "attrs": {"type": "work_type"},
        # listBibl[@type='group'] / head = an author's works: a `group` entry
        "group_xpath": "//tei:listBibl[@type='group']",
        "group_member": "tei:bibl",
        # only the persName/placeName in <note> are mentions; the authors' keys are not
        "links_only_in_note": True,
    },
    "schleiermacher_bible_books": {
        "project": "schleiermacher",
        "source": "bibelsystematik.xml",
        "entry_type": "bible_book",
        # the books sit at body/list/list[@type]/list/item
        "record_xpath": "//tei:list[@type]/tei:list/tei:item",
        "extract": extract_schleiermacher_bible_book,
        # no xml:id on the items and the idno is not unique — @n is the
        # register-wide position, 1–76
        "source_id": lambda item: f"bibelsystematik:{item.get('n')}" if item.get("n") else None,
    },
}


def project_of(slug: str) -> str:
    """The project a profile writes into — its own key unless it says otherwise.

    A profile key is a *register*, not a project: a project with more than one
    register (schleiermacher's persons and places) needs one profile per entry
    type, so those extra profiles carry an explicit ``project``. Everything
    that reaches the database (``ensure_project``, ``fetch_existing``,
    ``extract``'s ``project_name``) must use this, not the profile key.
    """
    return PROFILES[slug].get("project", slug)


class _Blank(dict):
    def __missing__(self, key):  # noqa: D105
        return ""


def _value(record, expr: str):
    """One scalar XPath value; node/text lists are joined with '; '. '' -> None."""
    r = record.xpath(expr, namespaces=NS, smart_strings=False)
    if isinstance(r, list):
        parts = [str(x).strip() for x in r if str(x).strip()]
        return "; ".join(parts) or None
    return str(r).strip() or None


def _multi(record, spec: dict):
    """A list of value objects, one per element matched by ``spec['each']``.

    With ``spec['parts']`` ({key: relative xpath}) each object gets those named
    sub-values (e.g. ``surname`` / ``forename``); otherwise it gets a single
    ``value`` (the element's text). ``spec['attr']`` -> ``spec['as']`` adds the
    element attribute as a qualifier. Empty objects are skipped; [] -> None.
    """
    parts = spec.get("parts")
    out = []
    for el in record.xpath(spec["each"], namespaces=NS):
        item: dict = {}
        if parts:
            for key, sub in parts.items():
                text = " ".join(el.xpath(f"string({sub})", namespaces=NS).split())
                if text:
                    item[key] = text
        if not item:
            text = " ".join("".join(el.itertext()).split())
            if text:
                item["value"] = text
        if not item:
            continue
        q = el.get(spec["attr"]) if spec.get("attr") else None
        if q:
            item[spec["as"]] = q
        out.append(item)
    return out or None


def _fields(record, profile: dict) -> dict:
    """The declarative path: one XPath per target field, plus coercion."""
    data: dict = {}
    for name, spec in profile["fields"].items():
        if isinstance(spec, dict):
            v = _multi(record, spec)
        else:
            v = _value(record, spec)
            if name in COERCERS:
                v = COERCERS[name](v)
        if v not in (None, "", [], {}):
            data[name] = v
    return data


def _source_id(record, profile: dict) -> str | None:
    """The record's identifier in its source: ``@xml:id``, or the profile's own
    ``source_id`` callable for a register whose records carry none.

    Args:
        record: One record element of the register.
        profile: The register's entry in ``PROFILES``.

    Returns:
        The identifier, or ``None`` when the record has none.
    """
    if make_id := profile.get("source_id"):
        return make_id(record)
    return record.get(XML_ID)


def extract(record, profile: dict, project: str) -> dict:
    """Turn one record into the entry payload ``services.create_entry`` /
    ``update_entry`` take.

    Dispatches to the profile's ``extract`` callable where it has one, else to
    the declarative ``fields`` mapping, then wraps the result in the entry
    envelope (``project_name``, ``entry_type``, ``label``, ``source_id``,
    ``data``). Empty values are dropped from ``data`` so the stored JSON
    stays free of ``""`` / ``None`` noise.
    """
    if custom := profile.get("extract"):
        got = custom(record)
        data = {k: v for k, v in got["data"].items() if v not in (None, "", [])}
        label = got["label"]
    else:
        data = _fields(record, profile)
        make_label = profile.get("label")
        if callable(make_label):
            label = make_label(data)
        else:  # "label_template" — a format string over the primary display values
            display = {k: _primary(v) for k, v in data.items()}
            label = profile["label_template"].format_map(_Blank(display))
        label = " ".join(label.split())

    # record-element attributes carried into `data` (e.g. mop's legacy oldID)
    for attr, key in profile.get("attrs", {}).items():
        v = record.get(attr)
        if v:
            data[key] = v

    ext_id = _source_id(record, profile)
    return {
        "project_name": project,
        "entry_type": profile["entry_type"],
        "label": label or ext_id or "(unnamed)",
        "source_id": ext_id,
        "data": data,
    }


# --- API --------------------------------------------------------------------

def _json(model) -> dict:
    """``model`` as the API would have serialized it — the dict shape the
    reconcile passes below compare against (datetimes as ISO strings)."""
    return model.model_dump(mode="json")


def report_run(session: Session, run: dict) -> None:
    """Record one ingest run's summary (see ``models.IngestRun``) — never
    allowed to fail the run itself: a run that ingested cleanly but couldn't
    file its own report is still a clean run.
    """
    try:
        services.create_ingest_run(session, IngestRunCreate.model_validate(run))
    except Exception as e:  # noqa: BLE001 — reporting is best-effort
        session.rollback()
        print(f"  (could not record this run: {e})")


def add_entry(session: Session, entry: dict) -> dict:
    created = services.create_entry(session, EntryCreate.model_validate(entry))
    return _json(EntryPublic.model_validate(created))


def patch_entry(session: Session, entry_id: int, entry: dict) -> dict:
    payload = EntryUpdate(
        label=entry["label"],
        source_id=entry["source_id"],
        data=entry["data"],
        ingested_source_hash=entry["ingested_source_hash"],
    )
    return _json(EntryPublic.model_validate(services.update_entry(session, entry_id, payload)))


def fetch_existing(session: Session, project: str, entry_type: str) -> dict[str, dict]:
    """Every existing entry for ``(project, entry_type)``, keyed by ``source_id``.

    Fetched once per run so each record's reconciliation decision
    (``_reconcile``) needs no further queries. Entries with no
    ``source_id`` (hand-entered, never ingested) can't be matched to a source
    record and are excluded.
    """
    rows = session.exec(
        select(Entry)
        .where(Entry.project_name == project, Entry.entry_type == entry_type, Entry.source_id.is_not(None))
        .execution_options(populate_existing=True)  # never a row as this session last saw it
    ).all()
    return {row.source_id: _json(EntryPublic.model_validate(row)) for row in rows if row.source_id}


def fetch_project_source_ids(session: Session, project: str) -> dict[str, int]:
    """Every entry's own id by ``source_id``, across the **whole project**
    (every ``entry_type``) — unlike ``fetch_existing``, which is scoped
    to one. Used by ``ingest_comments_and_links`` to resolve a note-link
    that points to an entry of a *different* entry_type in the same project
    (a schleiermacher person's note mentioning a place, or vice versa) — a
    real, common pattern confirmed against the real corpus (~90% of
    otherwise-unresolved note-links turned out to be exactly this), not a
    hypothetical. This slug's own ``id_by_xmlid`` can't see across profiles
    (schleiermacher_persons/schleiermacher_places each run as their own
    ``_ingest_one`` call, with their own throwaway ``id_by_xmlid``), so
    without this, such a link would look identical to a genuinely broken
    source reference and silently never resolve.
    """
    rows = session.exec(
        select(Entry.source_id, Entry.id).where(Entry.project_name == project, Entry.source_id.is_not(None))
    ).all()
    return {source_id: entry_id for source_id, entry_id in rows if source_id}


def create_relation(session: Session, subject_id: int, predicate: str, object_id: int) -> dict:
    payload = RelationCreate(subject_id=subject_id, predicate=predicate, object_id=object_id)
    return _json(services.create_relation(session, payload))


def delete_relation(session: Session, relation_id: int) -> None:
    services.delete_relation(session, relation_id)


def upsert_mention_anchor(session: Session, relation_id: int, start: int, end: int, text: str) -> dict:
    """Create-or-replace the exact-position anchor for one ``mentions``
    relation — see ``models.MentionAnchor``."""
    payload = MentionAnchorUpsert(start_offset=start, end_offset=end, captured_text=text)
    return _json(services.upsert_mention_anchor(session, relation_id, payload))


def fetch_relations(session: Session, project: str, *, predicate: str | None = None) -> list[dict]:
    """Every relation whose subject is in ``project`` (optionally only
    ``predicate``'s), as ``{"id", "subject_id", "predicate", "object_id"}``."""
    subject = aliased(Entry)
    query = (
        select(Relation)
        .join(subject, subject.id == Relation.subject_id)
        .where(subject.project_name == project)
    )
    if predicate is not None:
        query = query.where(Relation.predicate == predicate)
    query = query.order_by(Relation.id).execution_options(populate_existing=True)
    return [_json(r) for r in session.exec(query).all()]


def hash_data(data: dict) -> str:
    """Stable content hash of an extracted record's ``data`` bag.

    Keys sorted, so re-extracting the same XML twice always yields the same
    hash regardless of dict insertion order — this is what lets a re-run tell
    an unchanged source record apart from a changed one (see ``_reconcile``)
    without diffing the actual field values.
    """
    blob = json.dumps(data, sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def _reconcile(old: dict | None, new_hash: str) -> str:
    """What a re-ingest should do with one record: ``"create"``, ``"update"``,
    ``"unchanged"`` or ``"conflict"``.

    * no existing entry with this record's ``source_id`` -> ``"create"``.
    * an existing entry whose ``ingested_source_hash`` already matches
      ``new_hash`` -> ``"unchanged"`` — the source didn't change, skip.
    * hash differs, and nobody has edited the entry in the app since the last
      ingest (``updated_at`` not newer than ``ingested_at``, or neither is
      set) -> ``"update"``, safe to overwrite with the freshly extracted data.
    * hash differs *and* it was edited in the app since -> ``"conflict"``:
      both the source and the DB moved since the last ingest: don't silently
      pick one, let a human reconcile it.
    """
    if old is None:
        return "create"
    if old.get("ingested_source_hash") == new_hash:
        return "unchanged"
    updated_at = old.get("updated_at")
    ingested_at = old.get("ingested_at")
    if not updated_at or not ingested_at:
        return "update"
    if datetime.fromisoformat(updated_at) <= datetime.fromisoformat(ingested_at):
        return "update"
    return "conflict"


def ensure_project(session: Session, project: str) -> None:
    """Fail early (with guidance) rather than on every entry."""
    row = session.get(Project, project)
    if row is None or not row.is_active:
        raise SystemExit(
            f"project {project!r} is not an active project in the database — "
            f"it isn't in the platform's project registry (or, without one, has "
            f"no module in src/ediarum_index/projects/); the API adds it on its "
            f"next start."
        )


# --- runner -----------------------------------------------------------------

def resolve_source_pattern(profile: dict, project: str, source: str | None = None) -> str:
    """The absolute glob pattern a profile's XML source resolves to.

    A project's XML is on the shared volume ediarum.fileservice keeps
    (``sources.register_dir``: ``XML_MOUNT_ROOT/<project>/<REGISTER_DIR>``).
    ``profile["source"]`` — or the ``source`` override some callers pass
    (``--source`` / an ingest with a hand-picked file; an absolute path stays
    as it is) — is a path/glob *relative to* that directory.

    The single place this resolution happens — ``_source_trees`` and
    ``roundtrip_report._source_files`` both call this rather than each
    building the path independently, which is exactly the kind of duplicated
    logic that drifts.
    """
    pattern = source or profile["source"]
    if os.path.isabs(pattern):
        return pattern
    return str(sources.register_dir(project) / pattern)


def _source_trees(profile: dict, project: str, source: str | None = None):
    """Every source file for a profile, parsed once — ``(filename, tree)`` pairs.

    ``_records`` walks each tree's records; schleiermacher's group pass
    (``ingest_schleiermacher_groups``) needs the whole tree instead, to
    XPath ``listPerson[@type='group']`` separately from ``tei:person`` — hence
    this is factored out rather than folded into ``_records``.

    ``remove_pis=False``: PIs (``oxy_comment_start``/``end``) stay in the
    tree — needed by ``_walk_record_comments``. Safe for every other
    consumer: ``lxml``'s ``itertext()`` (what ``_text`` flattens fields
    with) never yields a PI's own pseudo-text regardless, only real element
    text nodes — confirmed, not assumed — so this changes nothing about how
    any existing field gets extracted.
    """
    pattern = resolve_source_pattern(profile, project, source)
    files = sorted(
        p for p in glob(pattern, recursive=True) if ".ipynb_checkpoints" not in p
    )
    if not files:
        raise SystemExit(f"no XML at {pattern}")
    recover = profile.get("recover", False)
    parser = etree.XMLParser(
        remove_pis=False, resolve_entities=False, huge_tree=True, recover=recover
    )
    for path in files:
        tree = etree.parse(path, parser)
        if recover:  # repaired input must not pass silently
            for err in parser.error_log:
                print(f"warning: {Path(path).name}:{err.line}: {err.message}", file=sys.stderr)
        yield Path(path).name, tree


def _records(profile: dict, project: str, source: str | None = None):
    for fname, tree in _source_trees(profile, project, source):
        for record in tree.xpath(profile["record_xpath"], namespaces=NS):
            yield fname, record


# --- structure the source expresses by nesting, rebuilt as relations ----------

def _reconcile_relations(
    session: Session,
    project: str,
    predicate: str,
    desired: dict[int, int],
    scope: set[int] | None = None,
) -> tuple[int, int, int, list[tuple[int, str]]]:
    """Make ``predicate``'s relations in ``project`` match ``desired``.

    ``desired`` maps a subject entry id to the *single* object entry id it
    should point at (a person to their family, a sub-place to its parent
    place) — both structures the source expresses by nesting and this stack
    stores as ``(subject, predicate, object)`` triples.

    A subject already pointing at the right object is left alone; one pointing
    somewhere else has the old relation deleted and a new one created; one no
    longer in ``desired`` has its relation deleted. The *object* entry itself
    is never deleted here — an empty family (or a parent place that lost its
    sub-places) is a queryable signal, not something to clean up silently,
    consistent with ingest.py never deleting an entry either.

    Returns ``(created, deleted, unchanged, failed)``; ``failed`` is
    ``[(subject id, detail)]``, so one bad write is reported instead of
    aborting the rest of the pass.

    ``scope`` limits which subjects may be *removed*: when several registers of
    one project use the same predicate (schleiermacher's persons and
    organisations both ``member_of`` a ``group``), a pass must not delete the
    other register's relations just because they are not in its ``desired``.
    ``None`` = every subject of the predicate.
    """
    current: dict[int, tuple[int, int]] = {  # subject id -> (relation id, object id)
        r["subject_id"]: (r["id"], r["object_id"])
        for r in fetch_relations(session, project, predicate=predicate)
    }

    created, deleted, unchanged = 0, 0, 0
    failed: list[tuple[int, str]] = []
    for subject_id, object_id in desired.items():
        old_rel = current.get(subject_id)
        if old_rel is not None and old_rel[1] == object_id:
            unchanged += 1
            continue
        try:
            if old_rel is not None:  # now points somewhere else
                delete_relation(session, old_rel[0])
                deleted += 1
            create_relation(session, subject_id, predicate, object_id)
            created += 1
        except (ServiceError, ValueError) as e:
            session.rollback()
            failed.append((subject_id, str(e)))

    for subject_id, (relation_id, _object_id) in current.items():
        if subject_id not in desired and (scope is None or subject_id in scope):
            try:
                delete_relation(session, relation_id)
                deleted += 1
            except (ServiceError, ValueError) as e:
                session.rollback()
                failed.append((subject_id, str(e)))

    return created, deleted, unchanged, failed


def _reconcile_relations_multi(
    session: Session, project: str, predicate: str, desired: dict[int, set[int]]
) -> tuple[int, int, int, list[tuple[int, str]], dict[tuple[int, int], int]]:
    """Like ``_reconcile_relations``, but for a predicate where one
    subject legitimately points at *several* objects at once — ``mentions``
    (a note can reference more than one other entry), unlike ``member_of``'s
    or ``part_of``'s one-subject-one-object shape, which is exactly why that
    function assumes a single object per subject and can't be reused as-is
    here.

    ``desired`` maps a subject entry id to the *set* of object ids it should
    point at. A subject entirely absent from ``desired`` is left completely
    alone — its note simply wasn't walked in this run, not a signal its
    existing links should be removed.

    Also returns a ``{(subject_id, object_id): relation_id}`` map covering
    every pair in ``desired`` that ended up with a real relation row —
    both freshly created ones and already-``unchanged`` ones. Used by
    ``ingest_comments_and_links`` to upsert a ``MentionAnchor`` for
    every resolved link regardless of whether the relation itself was new
    this run (an unchanged record's note is unchanged too, so refreshing
    unconditionally is cheap and avoids separate "did the anchor change"
    tracking — see ``models.MentionAnchor``).
    """
    current: dict[int, dict[int, int]] = defaultdict(dict)  # subject -> {object: relation_id}
    for r in fetch_relations(session, project, predicate=predicate):
        current[r["subject_id"]][r["object_id"]] = r["id"]

    created, deleted, unchanged = 0, 0, 0
    failed: list[tuple[int, str]] = []
    relation_ids: dict[tuple[int, int], int] = {}
    for subject_id, objects in desired.items():
        existing = current.get(subject_id, {})
        for object_id in objects:
            if object_id in existing:
                unchanged += 1
                relation_ids[(subject_id, object_id)] = existing[object_id]
                continue
            try:
                rel = create_relation(session, subject_id, predicate, object_id)
                created += 1
                relation_ids[(subject_id, object_id)] = rel["id"]
            except (ServiceError, ValueError) as e:
                session.rollback()
                failed.append((subject_id, str(e)))
        for object_id, relation_id in existing.items():
            if object_id not in objects:
                try:
                    delete_relation(session, relation_id)
                    deleted += 1
                except (ServiceError, ValueError) as e:
                    session.rollback()
                    failed.append((subject_id, str(e)))

    return created, deleted, unchanged, failed, relation_ids


def create_comment(session: Session, entry_id: int, text: str, **kw) -> dict:
    """``kw`` may carry ``start_field``/``end_field``/``source``/``author``/
    ``created_at``/``thread_meta`` — an ingest write sets ``source``, which
    keeps its own author/timestamp (see ``services.create_comment``)."""
    payload = CommentCreate.model_validate({"entry_id": entry_id, "text": text, **kw})
    return _json(CommentPublic.model_validate(services.create_comment(session, payload, author="ingest")))


def delete_comment(session: Session, comment_id: int) -> None:
    services.delete_comment(session, comment_id)


def fetch_comments(session: Session, project: str) -> list[dict]:
    """Every comment on an entry of ``project``."""
    rows = session.exec(
        select(Comment)
        .join(Entry, Entry.id == Comment.entry_id)
        .where(Entry.project_name == project)
        .execution_options(populate_existing=True)
    ).all()
    return [_json(CommentPublic.model_validate(c)) for c in rows]


def _when(value: str) -> datetime:
    """An ISO timestamp as a comparable datetime: the database answers
    ``…Z``, the source walk ``…+00:00`` — the same instant, unequal strings."""
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _reconcile_comments(
    session: Session, project: str, desired: list[dict]
) -> tuple[int, int, list[str]]:
    """Add ingested comments not already present, identified by
    ``(entry_id, author, created_at, text)`` — see ``models.Comment``'s
    docstring for why this, not `_reconcile`, governs comments: append-only,
    an existing comment is never updated or deleted by a re-ingest, even if
    the source comment's own text changed without its timestamp changing
    (an accepted limitation, not solved here). ``text`` has to be part of
    the key, not just a nice-to-have: plain ``<!-- -->`` comments carry no
    real author/timestamp at all (both a fixed stand-in, see
    ``_walk_record_xml_comments``/``_NO_TIMESTAMP``), so without ``text`` in
    the key, a *second* plain comment on the same entry would look
    identical to the first and silently fail to be created.

    Each item of ``desired`` is one comment dict from
    ``_walk_record_comments``/``_walk_record_xml_comments``, plus
    its resolved ``entry_id``. Returns ``(created, unchanged, failed)`` —
    ``failed`` is a list of detail strings, one bad write reported rather
    than aborting the rest.
    """
    existing = {
        (c["entry_id"], c["author"], _when(c["created_at"]), c["text"])
        for c in fetch_comments(session, project)
    }
    created, unchanged = 0, 0
    failed: list[str] = []
    for c in desired:
        key = (c["entry_id"], c["author"], _when(c["created_at"]), c["text"])
        if key in existing:
            unchanged += 1
            continue
        try:
            create_comment(
                session,
                c["entry_id"],
                c["text"],
                source=c["source"],
                author=c["author"],
                created_at=c["created_at"],
                start_field=c.get("start_field"),
                end_field=c.get("end_field"),
                thread_meta=c.get("thread_meta"),
            )
            created += 1
        except (ServiceError, ValueError) as e:
            session.rollback()
            failed.append(str(e))
    return created, unchanged, failed


# --- schleiermacher — family groups ------------------------------------------
#
# A family (a source listPerson[@type='group']) is not a person field: it's
# its own `group` entry plus a `member_of` relation per member, built here
# after every person in the file(s) is already in the DB. See docs/ingest/schleiermacher.md.

_GROUP_ID_PREFIX = "schleiermacher-group:"
_HEADLESS_MARKER = "\x00noheading"


def _group_source_id(fname: str, head_text: str, ordinal: int) -> str:
    """Stable synthetic id for one family group — there is no natural one in
    the source.

    Keyed by ``(filename, head text, ordinal-among-same-head-in-file)``, not
    by the group's *member set*: membership legitimately drifts over time (a
    curator reassigns a person — see ``ingest_schleiermacher_groups``), so
    hashing membership would treat every such edit as a brand-new family.
    ``ordinal`` only needs to disambiguate the confirmed real case of one head
    text naming more than one distinct family in the same file (three separate
    "Bülow" families in one file) — 0-indexed among groups sharing that exact
    ``(fname, head_text)`` pair, not the group's absolute position in the file
    (which shifts if unrelated groups move). Headless groups (no ``<head>``)
    use ``_HEADLESS_MARKER`` in place of head text, with their own ordinal
    counter, so they stay distinct from each other too.

    The id *does* change if a group is renamed or reordered relative to a
    same-head sibling in the same file — an accepted, documented limitation,
    consistent with how a person's own ``xml:id`` changing is already
    unrecoverable to ``source_id``-keyed reconciliation elsewhere.
    """
    key = head_text if head_text else _HEADLESS_MARKER
    blob = f"{fname}\x00{key}\x00{ordinal}"
    return _GROUP_ID_PREFIX + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _extract_groups(tree, fname: str, profile: dict | None = None) -> list[dict]:
    """Every family group in one parsed source file: ``{source_id, label,
    member_xmlids}``. A group with no members is skipped (nothing to attach
    the family to yet). The head text becomes only the entry's ``label`` —
    there is no ``group`` form field for it (see the "group — Familien/Gruppen"
    section of ``projects.schleiermacher``'s module docstring).

    A profile may name its own ``group_xpath`` / ``group_member`` (the
    organisation register nests ``listOrg/listOrg`` with ``org`` members);
    the default is the person register's ``listPerson[@type='group']``.

    Args:
        tree: The parsed source file.
        fname: The file's name, used to build the groups' ``source_id``.
        profile: The register's entry in ``PROFILES``; ``None`` means the
            person register's defaults.

    Returns:
        One dict per group, as described above.
    """
    profile = profile or {}
    group_xpath = profile.get("group_xpath", "//tei:listPerson[@type='group']")
    member_tag = profile.get("group_member", "tei:person")
    seen: dict[str, int] = {}
    groups = []
    for grp in tree.xpath(group_xpath, namespaces=NS):
        head_el = grp.find("tei:head", NS)
        head_text = _text(head_el) if head_el is not None else ""
        ordinal = seen.get(head_text, 0)
        seen[head_text] = ordinal + 1
        member_ids = [xid for p in grp.findall(member_tag, NS) if (xid := p.get(XML_ID))]
        if not member_ids:
            continue
        groups.append({
            "source_id": _group_source_id(fname, head_text, ordinal),
            "label": head_text,
            "member_xmlids": member_ids,
        })
    return groups


def ingest_schleiermacher_groups(
    session: Session,
    slug: str,
    project: str,
    id_by_xmlid: dict[str, int],
    source: str | None,
) -> bool:
    """Post-ingest pass for schleiermacher only (``PROFILES["schleiermacher_persons"]["post_ingest"]``),
    run by ``_ingest_one`` after every person in the file(s) is already in
    the DB. Reconstructs the source's family groups as their own ``group``
    entries plus ``member_of`` relations. A family's *identity* (its
    ``source_id``, see ``_group_source_id``) never depends on its
    membership, so a re-run can freely add/move/remove members without ever
    touching the family entry itself — only relations change. Re-walks the
    same files a second time (via ``_source_trees``) rather than sharing
    trees with the person pass — simpler, and these files are small enough
    that the extra parse is cheap.
    """
    profile = PROFILES[slug]
    groups: list[dict] = []
    for fname, tree in _source_trees(profile, project, source):
        groups.extend(_extract_groups(tree, fname, profile))

    # --- families themselves: same reconcile machinery as persons ----------
    fam_created, fam_updated, fam_unchanged = 0, 0, 0
    fam_conflicts: list[str] = []
    fam_failed: list[tuple[str, str]] = []
    existing_families = fetch_existing(session, project, "group")
    family_id: dict[str, int] = {}  # group source_id -> entry id
    for group in groups:
        entry = {
            "project_name": project,
            "entry_type": "group",
            "label": group["label"],
            "source_id": group["source_id"],
            "data": {},
        }
        # a family's only mutable content is its label (the head text) — hash
        # that, not `data`, which is redundant with it
        entry["ingested_source_hash"] = hash_data({"label": group["label"]})
        old = existing_families.get(group["source_id"])
        action = _reconcile(old, entry["ingested_source_hash"])
        try:
            if action == "create":
                family_id[group["source_id"]] = add_entry(session, entry)["id"]
                fam_created += 1
            elif action == "update":
                family_id[group["source_id"]] = patch_entry(session, old["id"], entry)["id"]
                fam_updated += 1
            elif action == "unchanged":
                family_id[group["source_id"]] = old["id"]
                fam_unchanged += 1
            else:  # conflict — a curator renamed this family entry since the last ingest
                family_id[group["source_id"]] = old["id"]
                fam_conflicts.append(group["source_id"])
        except (ServiceError, ValueError) as e:
            session.rollback()
            fam_failed.append((group["source_id"], str(e)))

    # --- membership: person --member_of--> family ---------------------------
    desired: dict[int, int] = {}  # person entry id -> family entry id
    for group in groups:
        fid = family_id.get(group["source_id"])
        if fid is None:
            continue  # this family's own write failed; don't touch its members
        for xid in group["member_xmlids"]:
            if (pid := id_by_xmlid.get(xid)) is not None:
                desired[pid] = fid

    rel_created, rel_deleted, rel_unchanged, rel_failed = _reconcile_relations(
        session, project, "member_of", desired, scope=set(id_by_xmlid.values())
    )

    print(
        f"{slug} (families): {fam_created} created, {fam_updated} updated, "
        f"{fam_unchanged} unchanged, {len(fam_conflicts)} conflicts, {len(fam_failed)} failed"
    )
    print(
        f"{slug} (memberships): {rel_created} created, {rel_deleted} deleted, "
        f"{rel_unchanged} unchanged, {len(rel_failed)} failed"
    )
    for source_id, detail in fam_failed[:20]:
        print(f"  family {source_id}: {detail}")
    for person_id, detail in rel_failed[:20]:
        print(f"  relation for person {person_id}: {detail}")
    return not (fam_conflicts or fam_failed or rel_failed)


# --- schleiermacher — nested places -------------------------------------------
#
# A sub-place (a source place/listPlace/place: a building, district or street
# inside a larger place) is not a field on the parent: `record_xpath` already
# matches it, so it is a `place` entry in its own right, and the nesting comes
# back as a `part_of` relation built here once every place is in the DB.

def _extract_place_nesting(tree) -> dict[str, str]:
    """``{child xml:id: parent xml:id}`` for every nested place in one file.

    Only the immediate parent is recorded — the register nests at most three
    levels deep (one place in the current data), and a chain of ``part_of``
    relations describes that as well as a materialised ancestor list would,
    without having to invalidate anything when a place moves.
    """
    nesting: dict[str, str] = {}
    for parent in tree.xpath("//tei:place[tei:listPlace]", namespaces=NS):
        parent_id = parent.get(XML_ID)
        if not parent_id:
            continue
        for child in parent.xpath("tei:listPlace/tei:place", namespaces=NS):
            if child_id := child.get(XML_ID):
                nesting[child_id] = parent_id
    return nesting


def ingest_schleiermacher_place_nesting(
    session: Session,
    slug: str,
    project: str,
    id_by_xmlid: dict[str, int],
    source: str | None,
) -> bool:
    """Post-ingest pass for the place register
    (``PROFILES["schleiermacher_places"]["post_ingest"]``), run by
    ``_ingest_one`` once every place in the file is already in the DB.

    Simpler than the family pass: there is no entry to create here — both ends
    of the relation are ordinary ``place`` entries the main pass has already
    written — so this only has to turn the source's nesting into ``part_of``
    relations (``_reconcile_relations``). A place moved under a different
    parent, or promoted to the top level, is reconciled like any membership
    change; no entry is ever deleted.
    """
    profile = PROFILES[slug]
    nesting: dict[str, str] = {}
    for _fname, tree in _source_trees(profile, project, source):
        nesting.update(_extract_place_nesting(tree))

    desired: dict[int, int] = {}  # child entry id -> parent entry id
    unresolved = 0
    for child_xmlid, parent_xmlid in nesting.items():
        child_id = id_by_xmlid.get(child_xmlid)
        parent_id = id_by_xmlid.get(parent_xmlid)
        if child_id is None or parent_id is None:
            # one end never made it into the DB (its own write failed, or it was
            # skipped as a duplicate xml:id) — don't guess at a half relation
            unresolved += 1
            continue
        desired[child_id] = parent_id

    created, deleted, unchanged, failed = _reconcile_relations(
        session, project, "part_of", desired
    )
    print(
        f"{slug} (nesting): {created} created, {deleted} deleted, "
        f"{unchanged} unchanged, {unresolved} unresolved, {len(failed)} failed"
    )
    for child_id, detail in failed[:20]:
        print(f"  relation for place {child_id}: {detail}")
    return not failed


# --- editorial comments + note-links: the ingest side ------------------------

def _record_links(record, profile: dict, links: list[dict]) -> list[tuple[dict, dict | None]]:
    """The ``mentions`` links of one record, each with its exact position in the
    note (or ``None``): ``links`` is ``_walk_record_comments``'s second
    result. Shared by ``ingest_comments_and_links`` and ``roundtrip_report.py``
    so the two can't drift apart.

    A profile whose links sit in another element than ``<note>`` names it
    (``note_tag``: the organisation register's ``<desc>``); export splices into
    the same field (``EXPORT[...]["note_field"]``). ``links_only_in_note`` drops
    every link outside ``<note>`` (the works' authors' ``persName[@key]`` are not
    mentions).

    Args:
        record: One record element of the register.
        profile: The register's entry in ``PROFILES``; read for ``note_tag`` and
            ``links_only_in_note``.
        links: The links found in ``record``, each ``{"key", "field"}``.

    Returns:
        One ``(link, anchor)`` pair per kept link. ``anchor`` is
        ``{"start", "end", "text"}`` or ``None`` when the link has no known
        position in the note.
    """
    note_tag = profile.get("note_tag", "note")
    offsets_by_key = {
        o["key"]: o for o in _note_link_offsets(record.find(f"tei:{note_tag}", NS))
    }
    if profile.get("links_only_in_note"):
        links = [link for link in links if link["field"] == "note"]
    out = []
    for link in links:
        in_note = link["field"] == "note" or note_tag != "note"
        out.append((link, offsets_by_key.get(link["key"]) if in_note else None))
    return out


def ingest_comments_and_links(
    session: Session,
    slug: str,
    project: str,
    id_by_xmlid: dict[str, int],
    source: str | None,
) -> bool:
    """Post-ingest pass wiring ``_walk_record_comments`` /
    ``_walk_record_xml_comments`` into a real run — re-walks the same
    files a second time (via ``_source_trees``), same reasoning as
    ``ingest_schleiermacher_groups``: simpler than threading comments
    through ``extract``'s ``{"label", "data"}`` contract, and cheap
    enough given these files' size.

    A comment or link on a record whose own write failed this run (absent
    from ``id_by_xmlid``) is silently skipped — nothing to attach it to. A
    link whose target isn't in ``id_by_xmlid`` falls back to a project-wide
    lookup (``fetch_project_source_ids``, only fetched if actually
    needed) — the target may be a different entry_type in the same project,
    invisible to this slug's own ``id_by_xmlid`` (see that function's
    docstring). Only once *that* also misses is a link treated as a
    genuinely unresolved cross-reference and silently skipped, not flagged
    as a failure — the source pointing at something outside this project, or
    something this run never wrote, isn't this pass's problem to flag.

    A link found inside ``<note>`` also gets its exact character span
    within that note's own flattened text (``_note_link_offsets``),
    stored as a ``MentionAnchor`` alongside its relation — see
    ``export._emit_mentions``, which uses this to splice the link back in
    exactly instead of re-deriving placement by searching for the target's
    name at export time. A link found in some other field (rare —
    ``export._emit_mentions`` only ever splices into ``<note>``) simply gets
    no anchor.
    """
    profile = PROFILES[slug]
    comments: list[dict] = []
    link_targets: dict[int, set[int]] = defaultdict(set)  # subject entry id -> {object entry id}
    unresolved_links: list[tuple[int, str, dict | None]] = []  # (subject id, key, anchor)
    anchors: dict[tuple[int, int], dict] = {}  # (subject_id, object_id) -> {start, end, text}

    for _fname, tree in _source_trees(profile, project, source):
        for record in tree.getroot().xpath(profile["record_xpath"], namespaces=NS):
            xid = record.get(XML_ID)
            entry_id = id_by_xmlid.get(xid) if xid else None
            if entry_id is None:
                continue
            pi_comments, links = _walk_record_comments(record)
            for c in pi_comments:
                comments.append({**c, "entry_id": entry_id, "source": "ingested"})
            for c in _walk_record_xml_comments(record):
                comments.append({**c, "entry_id": entry_id, "source": "ingested"})

            for link, anchor in _record_links(record, profile, links):
                if (target_id := id_by_xmlid.get(link["key"])) is not None:
                    link_targets[entry_id].add(target_id)
                    if anchor:
                        anchors[(entry_id, target_id)] = anchor
                else:
                    unresolved_links.append((entry_id, link["key"], anchor))

    if unresolved_links:
        project_ids = fetch_project_source_ids(session, project)
        for entry_id, key, anchor in unresolved_links:
            if (target_id := project_ids.get(key)) is not None:
                link_targets[entry_id].add(target_id)
                if anchor:
                    anchors[(entry_id, target_id)] = anchor

    com_created, com_unchanged, com_failed = _reconcile_comments(session, project, comments)
    rel_created, rel_deleted, rel_unchanged, rel_failed, relation_ids = _reconcile_relations_multi(
        session, project, "mentions", link_targets
    )

    # refreshed every run for every resolved link, regardless of whether
    # the relation itself was created or already unchanged — see
    # models.MentionAnchor's docstring for why this is safe to do
    # unconditionally rather than tracking "did the anchor change"
    anchor_failed: list[str] = []
    anchors_written = 0
    for pair, anchor in anchors.items():
        relation_id = relation_ids.get(pair)
        if relation_id is None:
            continue
        try:
            upsert_mention_anchor(session, relation_id, anchor["start"], anchor["end"], anchor["text"])
            anchors_written += 1
        except (ServiceError, ValueError) as e:
            session.rollback()
            anchor_failed.append(str(e))

    print(f"{slug} (comments): {com_created} created, {com_unchanged} unchanged, {len(com_failed)} failed")
    print(
        f"{slug} (mentions): {rel_created} created, {rel_deleted} deleted, "
        f"{rel_unchanged} unchanged, {len(rel_failed)} failed"
    )
    print(f"{slug} (mention anchors): {anchors_written} written, {len(anchor_failed)} failed")
    for detail in com_failed[:20]:
        print(f"  comment: {detail}")
    for subject_id, detail in rel_failed[:20]:
        print(f"  mentions for entry {subject_id}: {detail}")
    for detail in anchor_failed[:20]:
        print(f"  mention anchor: {detail}")
    return not (com_failed or rel_failed or anchor_failed)


# wired here rather than in the PROFILES literal above: the post_ingest hooks
# are defined after PROFILES (they need fetch_existing / add_entry / etc., all
# defined further down), so these assignments have to come after both exist.
# A profile's "post_ingest" is a *list*, run in order — schleiermacher_persons
# needs both its own family-group pass and the shared comments/links pass.
PROFILES["schleiermacher_persons"]["post_ingest"] = [
    ingest_schleiermacher_groups,
    ingest_comments_and_links,
]
PROFILES["schleiermacher_places"]["post_ingest"] = [ingest_schleiermacher_place_nesting]
PROFILES["schleiermacher_organisations"]["post_ingest"] = [
    ingest_schleiermacher_groups,
    ingest_comments_and_links,
]
PROFILES["schleiermacher_glossary"]["post_ingest"] = [ingest_comments_and_links]
PROFILES["schleiermacher_works"]["post_ingest"] = [
    ingest_schleiermacher_groups,
    ingest_comments_and_links,
]
PROFILES["avhr_places"]["post_ingest"] = [
    ingest_schleiermacher_place_nesting,
    ingest_comments_and_links,
]
for _slug in ("avhr", "avhr_organisations", "mega", "mop"):
    PROFILES[_slug]["post_ingest"] = [ingest_comments_and_links]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Load a TEI register into the database.")
    p.add_argument(
        "project", nargs="?", default=os.getenv("INDEX_PROJECT", "leibniz5"),
        choices=sorted(PROFILES), help="profile to ingest (default: $INDEX_PROJECT)",
    )
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="print the first records instead of posting them")
    p.add_argument("--source", help="override the profile's source glob (single profile only)")
    p.add_argument(
        "--all", action="store_true",
        help="ingest every profile in PROFILES (ignores the project argument)",
    )
    p.add_argument(
        "--of-project", choices=sorted({project_of(slug) for slug in PROFILES}),
        help="ingest every profile of one project (ignores the profile argument)",
    )
    args = p.parse_args()
    if args.all and args.of_project:
        p.error("--all and --of-project are mutually exclusive")
    if (args.all or args.of_project) and args.source:
        p.error("--source only makes sense with a single profile")
    return args


def _ingest_entries(
    session: Session, slug: str, source: str | None
) -> tuple[dict[str, int], bool]:
    """Phase 1 of an ingest: create or update this profile's entries.

    Returns each record's resulting entry id by xml:id, and whether the run was
    clean (no conflicts or failures).
    """
    profile = PROFILES[slug]
    project = project_of(slug)
    started_at = datetime.now(timezone.utc)
    created, updated, unchanged = 0, 0, 0
    skipped, conflicts, failed = [], [], []
    seen: set[str] = set()
    # every record's resulting entry id, by its xml:id — read by the profile's
    # post-ingest hooks in phase 2
    id_by_xmlid: dict[str, int] = {}

    existing = fetch_existing(session, project, profile["entry_type"])
    for fname, record in _records(profile, project, source):
        ext_id = _source_id(record, profile)
        # avhr's H0012742 is in both A.xml and R.xml; source_id stays unique
        if ext_id and ext_id in seen:
            skipped.append((fname, ext_id, "duplicate xml:id"))
            continue
        entry = extract(record, profile, project)
        entry["ingested_source_hash"] = hash_data(entry["data"])
        old = existing.get(ext_id) if ext_id else None
        action = _reconcile(old, entry["ingested_source_hash"])
        try:
            if action == "create":
                entry_id = add_entry(session, entry)["id"]
                created += 1
            elif action == "update":
                entry_id = patch_entry(session, old["id"], entry)["id"]
                updated += 1
            elif action == "unchanged":
                entry_id = old["id"]
                unchanged += 1
            else:  # "conflict" — edited in the app since the last ingest, and the source also changed
                entry_id = old["id"]
                conflicts.append((fname, ext_id, "edited in the app since the last ingest; not overwritten"))
            if ext_id:
                seen.add(ext_id)
                id_by_xmlid[ext_id] = entry_id
        except (ServiceError, ValueError) as e:
            session.rollback()
            detail = str(e)
            failed.append((fname, ext_id, detail))

    print(
        f"{slug}: {created} created, {updated} updated, {unchanged} unchanged, "
        f"{len(conflicts)} conflicts, {len(skipped)} skipped, {len(failed)} failed"
    )
    problems = conflicts + skipped + failed
    for fname, xid, detail in problems[:50]:
        print(f"  {fname} [{xid}]: {detail}")
    if len(problems) > 50:
        print(f"  … and {len(problems) - 50} more")
    clean = not (conflicts or failed)

    report_run(session, {
        "project": slug,
        "started_at": started_at.isoformat(),
        "status": "failed" if failed else "conflicts" if conflicts else "ok",
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "problems": (
            [{"fname": f, "ext_id": x, "detail": d, "kind": "conflict"} for f, x, d in conflicts]
            + [{"fname": f, "ext_id": x, "detail": d, "kind": "skipped"} for f, x, d in skipped]
            + [{"fname": f, "ext_id": x, "detail": d, "kind": "failed"} for f, x, d in failed]
        ),
    })

    return id_by_xmlid, clean


def _run_post_ingest(
    session: Session, slug: str, id_by_xmlid: dict[str, int], source: str | None
) -> bool:
    """Phase 2: the profile's post-ingest hooks (family and place-nesting relations,
    comments, note links). Runs only once every profile of the batch has finished
    phase 1, so a link into another register resolves on the first run."""
    project = project_of(slug)
    clean = True
    for hook in PROFILES[slug].get("post_ingest", []):
        clean = hook(session, slug, project, id_by_xmlid, source) and clean
    return clean


def _ingest_profiles(
    session: Session, slugs: list[str], source: str | None, *, batch: bool
) -> bool:
    """Ingest ``slugs`` in two phases: every profile's entries first, then every
    profile's links. ``batch`` skips a profile whose source or project is
    unavailable and carries on; otherwise that failure is fatal."""
    clean = True
    id_maps: dict[str, dict[str, int]] = {}
    for slug in slugs:
        try:
            ensure_project(session, project_of(slug))
            id_maps[slug], ok = _ingest_entries(session, slug, source)
            clean = clean and ok
        except SystemExit as e:
            if not batch:
                raise
            print(f"{slug}: skipped — {e}")
            clean = False
    for slug, id_by_xmlid in id_maps.items():
        clean = _run_post_ingest(session, slug, id_by_xmlid, source) and clean
    return clean


def _ingest_one(session: Session, slug: str, source: str | None) -> bool:
    return _ingest_profiles(session, [slug], source, batch=False)


def profiles_of(project: str) -> list[str]:
    "The profile slugs writing into ``project``, in a stable order."
    return [slug for slug in sorted(PROFILES) if project_of(slug) == project]


def ingest_project(session: Session, project: str) -> bool:
    """Every profile of ``project``, in the two phases of ``_ingest_profiles``
    — what the watcher runs; ``True`` if the run was clean."""
    return _ingest_profiles(session, profiles_of(project), None, batch=True)


def main() -> None:
    args = parse_args()
    if args.all:
        slugs = sorted(PROFILES)
    elif args.of_project:
        slugs = profiles_of(args.of_project)
    else:
        slugs = [args.project]
    batch = args.all or args.of_project is not None

    if args.dry_run:
        for slug in slugs:
            if batch:
                print(f"=== {slug} ===")
            profile = PROFILES[slug]
            project = project_of(slug)
            try:
                for i, (_fname, record) in enumerate(_records(profile, project, args.source)):
                    payload = extract(record, profile, project)
                    print(json.dumps(payload, ensure_ascii=False, indent=2))
                    if i >= 4:
                        break
            except SystemExit as e:
                if not batch:  # single profile: a missing source is fatal, as before
                    raise
                print(f"  skipped — {e}")
        return

    with Session(engine) as session:
        all_clean = _ingest_profiles(session, slugs, args.source, batch=batch)

    if not all_clean:
        sys.exit(1)


if __name__ == "__main__":
    main()

"""Whitespace / comment-insensitive, but PI-*aware* XML unified diff.

Used by the round-trip check (``tests/test_roundtrip.py`` via a fixture, and the
``roundtrip_report.py`` script). ``xml_diff`` returns ``""`` when two documents
are equivalent once formatting and plain ``<!-- -->`` comments are removed.

Plain XML comments are still dropped (never re-emitted as such — see
``export.py``: every comment round-trips as an ``oxy_comment_start``/``end``
PI regardless of its original source style, so comparing a source's
``<!-- -->`` against an export's PI would always show a spurious diff for an
otherwise-correct round trip). ``oxy_comment_start``/``end`` PIs, however,
*are* part of the comparison — see ``_normalize``'s PI branch — so a
regression in comment content or in ``export._emit_comments``'s placement
shows up here like any other content difference.
"""

import difflib
import re

from lxml import etree

_TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}

# a trailing UTC offset ("+0100", "Z") on an oxy comment's timestamp — see
# ingest._parse_oxy_timestamp: the DB's plain DateTime column drops tzinfo on
# write, so this is unrecoverable on export by design, not a regression.
# Stripped before comparing so every single real-corpus comment (virtually
# all of which carry an offset) doesn't drown out genuine differences.
_TZ_OFFSET_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


def _normalize(el) -> None:
    """Collapse whitespace in text and put attributes in a stable (sorted) order —
    neither is significant, so neither should show up as a difference."""
    if el.tag is etree.PI:
        # an oxy comment PI's pseudo-attributes (author/timestamp/comment —
        # see ingest._walk_record_comments) aren't real XML attributes, but
        # their order isn't semantically significant either — sort them for
        # the same reason real attributes are sorted below. el.attrib is a
        # read-only *view* lxml parses from .text on the fly (mutating it
        # doesn't write back), so the sorted form has to be assigned to
        # .text directly instead of going through .attrib like an Element.
        if el.target == "oxy_comment_start":
            items = sorted(el.attrib.items())
            items = [
                (k, _TZ_OFFSET_RE.sub("", v) if k == "timestamp" else v) for k, v in items
            ]
            el.text = " ".join(f'{k}="{v}"' for k, v in items)
        elif el.target == "oxy_comment_end":
            el.text = ""  # always empty in practice; treat None/"" alike
        el.tail = " ".join(el.tail.split()) if el.tail and el.tail.strip() else None
        return
    el.text = " ".join(el.text.split()) if el.text and el.text.strip() else None
    el.tail = " ".join(el.tail.split()) if el.tail and el.tail.strip() else None
    if len(el.attrib) > 1:
        ordered = sorted(el.attrib.items())
        el.attrib.clear()
        el.attrib.update(ordered)
    for child in el:
        _normalize(child)


# Tags whose content is "one field's own prose text" (see
# ingest._FIELD_BY_TAG) — a PI directly inside one of these sits mixed into
# running text, which is exactly what _fix_pi_indent below has to protect
# from etree.indent()'s block-level formatting. A PI as a direct child of a
# *structural* container instead (<person>, <place>, <persName>, ...) is
# just another block-level sibling among heterogeneous fields —
# etree.indent() already gives it its own line correctly on its own
# (confirmed directly: a `<person><idno/><persName/>
# <?oxy_comment_start/end?><birth/><death/><note/></person>`-shaped record
# canonicalizes perfectly with *no* fix at all), so touching it there would
# only undo indent()'s already-correct formatting.
_PROSE_FIELD_TAGS = {"note", "surname", "forename", "name", "birth", "death", "sex"}


def _fix_pi_indent(root) -> None:
    """Undo ``etree.indent()``'s pretty-print whitespace, but *only* on the
    text/tail nodes that actually touch a PI sitting inside a prose field
    (``_PROSE_FIELD_TAGS``) — ``indent()`` isn't mixed-content-aware (its
    own docs say so): it treats every element with children as
    block-structured and happily writes a real ``"\\n  "`` into an
    element's ``.text``/a child's ``.tail`` the moment that element gains
    *any* child, including an inline PI that used to sit directly in
    running prose (e.g. a comment wrapping a whole field's content — see
    ``export._wrap_field_content`` — or, just as much, a source record
    parsed as-is, since a source ``<note>`` beginning with a comment already
    has this exact shape before ``canonicalize`` touches it).

    The PI's parent decides: inside a prose field the adjacent whitespace is
    indent()'s and is removed; a PI that is a direct child of the record
    (``<person>`` — an "empty position-marker between siblings", a common
    shape) sits among block-structured fields, where indent()'s spacing is
    wanted and stays.
    """
    for el in root.iter():
        if el.tag is not etree.PI:
            continue
        parent = el.getparent()
        if parent is None or etree.QName(parent).localname not in _PROSE_FIELD_TAGS:
            continue
        if el.tail and not el.tail.strip():
            el.tail = None
        prev = el.getprevious()
        if prev is not None:
            if prev.tail and not prev.tail.strip():
                prev.tail = None
        elif parent.text and not parent.text.strip():
            parent.text = None


def canonicalize(xml: str | bytes, subtree: str | None = None, *, recover: bool = False) -> str:
    """Pretty-printed, whitespace-normalised form of an XML string/bytes.

    ``subtree`` is an optional XPath (``tei:`` bound); its first match is compared
    instead of the whole document. ``recover`` parses leniently instead of
    raising on the first well-formedness issue — needed for a profile whose
    ``ingest.py`` entry sets ``recover: True`` (schleiermacher's ``Z.xml``):
    the source tree was already parsed leniently and re-serialized, so it can
    carry the same not-quite-well-formed content (e.g. an unfilled
    ``xml:id="${ediarum_id}"`` template) that a strict re-parse here would
    otherwise choke on. Off by default — most callers' input is well-formed,
    and a genuinely malformed diff input should fail loudly.
    """
    parser = etree.XMLParser(
        remove_blank_text=True, remove_comments=True, remove_pis=False, recover=recover
    )
    root = etree.fromstring(xml.encode() if isinstance(xml, str) else xml, parser)

    if subtree:
        hit = root.xpath(subtree, namespaces=_TEI_NS)
        if hit:
            # re-parse standalone (same recover setting) so inherited
            # namespace decls can be dropped
            root = etree.fromstring(etree.tostring(hit[0]), parser)

    etree.cleanup_namespaces(root)
    _normalize(root)
    etree.indent(root, space="  ")
    _fix_pi_indent(root)  # see its docstring: indent() alone corrupts PI-adjacent text
    return etree.tostring(root, encoding="unicode")


def xml_diff(a, b, *, subtree: str | None = None, from_name="a", to_name="b", recover: bool = False) -> str:
    ca, cb = canonicalize(a, subtree, recover=recover), canonicalize(b, subtree, recover=recover)
    if ca == cb:
        return ""
    return "\n".join(
        difflib.unified_diff(
            ca.splitlines(), cb.splitlines(),
            fromfile=from_name, tofile=to_name, lineterm="",
        )
    )

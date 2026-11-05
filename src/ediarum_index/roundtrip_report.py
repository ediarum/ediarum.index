"""Round-trip every ingested source file and write per-file diffs to a folder.

    uv run ediarum-index roundtrip-report                    # all profiles -> ./roundtrip-diffs
    uv run ediarum-index roundtrip-report pta --out /tmp/rt  # one profile, custom folder
    uv run ediarum-index roundtrip-report avhr --ignore note --ignore-empty forename

For each source XML: extract its records with ingest.py, rebuild them with
export.py, then diff **per person, matched by ``xml:id``** — not the whole
``<listPerson>`` subtree as one document — ignoring whitespace and plain
``<!-- -->`` comments, but *comparing* ``oxy_comment_start``/``end`` PIs
(``xmldiff.xml_diff``, the same the tests use) within each pair. Export
reorders persons (alphabetically by label) and, for schleiermacher, moves
whole families to their label's position; diffing whole-document would count
every person after the first reordering as "changed" even when its own
content round-trips perfectly. Matching by id instead means only a person
whose *own* content actually differs shows up — document- and family-level
reordering produce zero diff. A person present on only one side (dropped, or
somehow duplicated) is reported separately, by id, since there's nothing on
the other side to diff it against. The same holds for a register whose records
nest (schleiermacher's sub-places): each record is diffed without its nested
sub-records, and whether each sits under the same parent is reported on its
own ("N under a different parent").

Files that round-trip cleanly produce no ``.diff``; ``<out>/_summary.txt``
lists every file with how many of its persons actually differ.

``--ignore TAG`` (repeatable) removes every element with that local name from
*both* sides before diffing — for a known, accepted deviation (like avhr's
flattened ``<note>`` markup) that would otherwise drown out everything else in
the report. ``--ignore-empty TAG`` (repeatable) instead removes only the
*content-free* instances (no text, no children) — for a field ingest already
drops when empty (an ``<idno/>`` with real content still shows up as a
difference; a bare ``<forename/>`` doesn't). Neither changes what counts as a
clean round-trip elsewhere (tests, the API); they only thin this report's
output. Each flag takes exactly one tag — repeat it for more (``--ignore note
--ignore bibl``), rather than a space-separated list, so it can't swallow the
profile slugs that follow it on the command line.
"""

import argparse
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from glob import glob
from pathlib import Path

from lxml import etree

from . import export
from . import ingest
from .xmldiff import xml_diff

_TEI = "http://www.tei-c.org/ns/1.0"
# birth/death carrying only a placeholder symbol hold no date -> ingest drops
# them, so don't count them as a difference in the report.
_YEAR_TAGS = {f"{{{_TEI}}}birth", f"{{{_TEI}}}death"}


def _drop_placeholder_dates(tree) -> None:
    for el in tree.iter(*_YEAR_TAGS):
        if not any(c.isdigit() for c in (el.text or "")):
            el.getparent().remove(el)


def _strip(xml: str, tags: set[str], *, only_empty: bool, recover: bool = False) -> str:
    """Remove elements whose local name is in ``tags``.

    Every instance by default; with ``only_empty``, only the content-free ones
    (no text, no children) — see ``--ignore`` / ``--ignore-empty`` above.
    ``recover``: see ``xmldiff.canonicalize`` — needed here too, or
    ``--ignore``/``--ignore-empty`` on a profile like schleiermacher (whose
    ``Z.xml`` has an unfilled ``xml:id`` template) aborts the whole run.
    """
    if not tags:
        return xml
    root = etree.fromstring(xml.encode(), etree.XMLParser(recover=recover))
    for tag in tags:
        for el in list(root.iter(f"{{{_TEI}}}{tag}")):
            if only_empty and ((el.text and el.text.strip()) or len(el) > 0):
                continue
            el.getparent().remove(el)
    return etree.tostring(root, encoding="unicode")


def _index_persons(root, xpath: str) -> dict[str, "etree._Element"]:
    """Every record matched by ``xpath``, keyed by its ``xml:id``.

    A record with no ``xml:id`` (shouldn't happen in a real register) can't be
    matched across source/export and is silently excluded, same as the ids
    ``ingest.extract`` itself relies on for ``source_id``.

    Each record comes back as a *copy without its nested sub-records*
    (schleiermacher's sub-places sit inside their parent ``<place>``): those
    are records of their own, diffed under their own id, and leaving them in
    would make a parent differ whenever its children merely come back in a
    different order. Whether each one lands under the right parent is checked
    separately (see ``nesting`` in ``_run``). A no-op for every register
    whose records don't nest.
    """
    nested_xpath = "." + xpath if xpath.startswith("//") else xpath
    out = {}
    for el in root.xpath(xpath, namespaces=ingest.NS):
        if not (xid := el.get(ingest.XML_ID)):
            continue
        own = deepcopy(el)
        for sub in own.xpath(nested_xpath, namespaces=ingest.NS):
            sub.getparent().remove(sub)
        out[xid] = own
    return out


def _source_files(profile: dict, project: str) -> list[Path]:
    return sorted(
        Path(p)
        for p in glob(ingest.resolve_source_pattern(profile, project), recursive=True)
        if ".ipynb_checkpoints" not in p
    )


def _run(slugs: list[str], out: Path, ignore: set[str], ignore_empty: set[str]) -> None:
    summary: list[str] = []
    files_with_diffs = 0

    # Phase 1: parse and extract every file in *every* requested slug once,
    # before any diffing — builds id_by_xmlid/entries_by_id shared across
    # every slug in this invocation (scoped per project, not fully global,
    # so two different projects' xml:ids can't accidentally collide). Needed
    # so a note-link can resolve to an entry defined by a *different* slug
    # of the same project — e.g. a schleiermacher person's note mentioning a
    # place, which lives in the separate schleiermacher_places profile, not
    # schleiermacher_persons' own files (confirmed a large, real category
    # against the real corpus: ~90% of otherwise-unresolved note-links were
    # exactly this). Mirrors ingest.fetch_project_source_ids's production
    # fix for the same gap. Doing this as its own pass, before any per-slug
    # diffing, matters: PROFILES lists schleiermacher_persons before
    # schleiermacher_places, so resolving mentions *while* processing each
    # slug in turn would still miss a forward reference to a slug not yet
    # reached — this only works because every slug's entries are known
    # before diffing starts for any of them. It only resolves within *this*
    # invocation's own slugs, unlike the DB-backed production fix — running
    # with no args (every slug) covers the common case; filtering to a
    # single slug reintroduces the same blind spot deliberately.
    next_id = 1
    id_by_xmlid_by_project: dict[str, dict[str, int]] = defaultdict(dict)
    entries_by_id: dict[int, dict] = {}
    file_data_by_slug: dict[str, list[tuple[Path, "etree._ElementTree", list[dict]]]] = {}

    for slug in slugs:
        profile = ingest.PROFILES[slug]
        project = ingest.project_of(slug)
        # honor the profile's `recover` flag like ingest.py does — schleiermacher's
        # Z.xml has an unfilled template id that isn't well-formed and would
        # otherwise abort this whole run, not just that one file
        recover = profile.get("recover", False)
        # remove_pis=False: PIs must survive so the "source" side of the diff
        # below actually carries oxy_comment_start/end content — see
        # ingest._source_trees's own docstring for why this is safe (itertext()
        # never reads PI pseudo-text, so nothing else in this script is affected)
        parser = etree.XMLParser(
            remove_pis=False, remove_comments=True, huge_tree=True, recover=recover
        )
        id_by_xmlid = id_by_xmlid_by_project[project]

        file_data: list[tuple[Path, "etree._ElementTree", list[dict]]] = []
        for path in _source_files(profile, project):
            tree = etree.parse(str(path), parser)
            if recover:  # repaired input must not pass silently
                for err in parser.error_log:
                    print(f"warning: {path.name}:{err.line}: {err.message}", file=sys.stderr)
            records = tree.xpath(profile["record_xpath"], namespaces=ingest.NS)
            if not records:
                file_data.append((path, tree, []))
                continue
            _drop_placeholder_dates(tree)

            entries = []
            for rec in records:
                try:
                    entry = ingest.extract(rec, profile, project)
                except Exception:  # noqa: BLE001 — report, don't abort the file
                    continue
                entry["id"] = next_id  # fake — there's no live DB here
                next_id += 1
                entries.append(entry)
                entries_by_id[entry["id"]] = entry
                if entry.get("source_id"):
                    id_by_xmlid[entry["source_id"]] = entry["id"]
            file_data.append((path, tree, entries))
        file_data_by_slug[slug] = file_data

    # Phase 2: diff each slug's own files, now that every slug's entries are
    # known (id_by_xmlid_by_project is fully populated).
    for slug in slugs:
        profile = ingest.PROFILES[slug]
        project = ingest.project_of(slug)
        entry_type = profile["entry_type"]
        cfg = export.export_config(project, entry_type) or {}
        (out / slug).mkdir(parents=True, exist_ok=True)
        recover = profile.get("recover", False)
        id_by_xmlid = id_by_xmlid_by_project[project]

        for path, tree, entries in file_data_by_slug[slug]:
            records = tree.xpath(profile["record_xpath"], namespaces=ingest.NS)
            if not records:
                continue
            errs = len(records) - len(entries)

            # families/memberships, for a profile whose export reconstructs
            # grouped structure (schleiermacher) — simulated the same way as
            # entry ids, since there's no live DB in this script; groups don't
            # span files, so this is entirely per-file, matching the ingest loop
            families, memberships = [], []
            if cfg.get("groups"):
                for gi, group in enumerate(
                    ingest._extract_groups(tree, path.name, profile), start=1_000_000
                ):
                    families.append({"id": gi, "label": group["label"]})
                    for xid in group["member_xmlids"]:
                        if xid in id_by_xmlid:
                            memberships.append({"subject_id": id_by_xmlid[xid], "object_id": gi})

            # part_of relations, for a profile whose records nest (schleiermacher's
            # sub-places) — simulated from the same file, like the families above
            parents = []
            if cfg.get("nesting"):
                for child, parent in ingest._extract_place_nesting(tree).items():
                    if child in id_by_xmlid and parent in id_by_xmlid:
                        parents.append(
                            {"subject_id": id_by_xmlid[child], "object_id": id_by_xmlid[parent]}
                        )

            # comments + note-links (models.Comment / "mentions" relations),
            # simulated the same way as families/parents above — mirrors
            # ingest.ingest_comments_and_links, minus the DB round trip.
            # Unlike families/parents, a link's target can be (and often is)
            # defined in a *different* source file — id_by_xmlid/entries_by_id
            # are the profile-wide caches built in the first pass above, so
            # that resolves correctly here too; a target outside this file's
            # own `entries` is added to `mention_target_entries` so
            # build_document can splice it without also emitting it as one of
            # this file's own top-level records. Plain <!-- --> comments
            # aren't simulated: this script's parser (like xmldiff.py's own)
            # still drops them, since export always promotes a plain comment
            # to an oxy PI rather than preserving its original shape, so
            # comparing a stripped source against a promoted export would be
            # a spurious diff either way — see xmldiff.py's module docstring.
            comments: list[dict] = []
            mentions_by_subject: dict[int, set[int]] = defaultdict(set)
            file_entry_ids = {e["id"] for e in entries}
            mention_target_ids: set[int] = set()
            # (subject_id, object_id) -> {"start", "end", "text"} — simulates
            # models.MentionAnchor without a DB, mirroring
            # ingest.ingest_comments_and_links's own anchor computation
            mention_anchors: dict[tuple[int, int], dict] = {}
            for record in records:
                xid = record.get(ingest.XML_ID)
                entry_id = id_by_xmlid.get(xid) if xid else None
                if entry_id is None:
                    continue
                pi_comments, links = ingest._walk_record_comments(record)
                for c in pi_comments:
                    # _walk_record_comments's created_at is the raw ISO
                    # *string* _parse_oxy_timestamp produces (real ingest
                    # gets this turned into a datetime for free by
                    # CommentCreate's pydantic validation on the way into
                    # the DB — there's no DB here, so do it explicitly)
                    comments.append({
                        **c, "entry_id": entry_id, "source": "ingested",
                        "created_at": datetime.fromisoformat(c["created_at"]),
                    })
                for link, anchor in ingest._record_links(record, profile, links):
                    if (target_id := id_by_xmlid.get(link["key"])) is not None:
                        mentions_by_subject[entry_id].add(target_id)
                        if target_id not in file_entry_ids:
                            mention_target_ids.add(target_id)
                        if anchor:
                            mention_anchors[(entry_id, target_id)] = anchor
            mentions = [
                {"subject_id": sid, "predicate": "mentions", "object_id": oid}
                for sid, targets in mentions_by_subject.items()
                for oid in targets
            ]
            mention_target_entries = [entries_by_id[tid] for tid in mention_target_ids]

            try:
                exported = export.build_document(
                    project, entry_type, entries,
                    families=families, memberships=memberships, parents=parents,
                    comments=comments, mentions=mentions, mention_targets=mention_target_entries,
                    mention_anchors=mention_anchors,
                )
            except KeyError:
                summary.append(f"{slug}/{path.name}: no export profile for {entry_type!r}")
                continue

            src_xml = _strip(etree.tostring(tree, encoding="unicode"), ignore, only_empty=False, recover=recover)
            src_xml = _strip(src_xml, ignore_empty, only_empty=True, recover=recover)
            exp_xml = _strip(exported, ignore, only_empty=False, recover=recover)
            exp_xml = _strip(exp_xml, ignore_empty, only_empty=True, recover=recover)

            strip_parser = etree.XMLParser(recover=recover)
            src_root = etree.fromstring(src_xml.encode(), strip_parser)
            exp_root = etree.fromstring(exp_xml.encode(), strip_parser)
            src_people = _index_persons(src_root, profile["record_xpath"])
            exp_people = _index_persons(exp_root, profile["record_xpath"])

            # the hierarchy itself, which the per-record diffs above no longer
            # see: a record whose parent differs between source and export
            misnested = []
            if cfg.get("nesting"):
                src_parent = ingest._extract_place_nesting(src_root)
                exp_parent = ingest._extract_place_nesting(exp_root)
                misnested = sorted(
                    xid for xid in set(src_parent) | set(exp_parent)
                    if src_parent.get(xid) != exp_parent.get(xid)
                )
            only_src = sorted(set(src_people) - set(exp_people))
            only_exp = sorted(set(exp_people) - set(src_people))
            person_diffs = [
                (xid, d)
                for xid in sorted(set(src_people) & set(exp_people))
                if (
                    d := xml_diff(
                        etree.tostring(src_people[xid], encoding="unicode"),
                        etree.tostring(exp_people[xid], encoding="unicode"),
                        from_name=f"{path.name}#{xid} (source)",
                        to_name=f"{path.name}#{xid} (export)",
                        recover=recover,
                    )
                )
            ]
            changed = sum(
                1
                for _, d in person_diffs
                for ln in d.splitlines()
                if ln[:1] in "+-" and not ln.startswith(("+++", "---"))
            )

            bits = []
            if person_diffs:
                bits.append(
                    f"{len(person_diffs)}/{len(records)} {entry_type}s differ ({changed} changed lines)"
                )
            if misnested:
                bits.append(f"{len(misnested)} under a different parent")
            if only_src:
                bits.append(f"{len(only_src)} missing from export")
            if only_exp:
                bits.append(f"{len(only_exp)} unexpected in export")
            note = f"{errs} extract error(s)" if errs else ""
            summary.append(
                f"{slug}/{path.name}: {'; '.join(bits) if bits else 'clean'}"
                f"  ({len(records)} records){f'  [{note}]' if note else ''}"
            )
            if bits:
                files_with_diffs += 1
                parts = [d for _, d in person_diffs]
                if misnested:
                    parts.append("under a different parent: " + ", ".join(misnested))
                if only_src:
                    parts.append("missing from export: " + ", ".join(only_src))
                if only_exp:
                    parts.append("unexpected in export: " + ", ".join(only_exp))
                (out / slug / f"{path.name}.diff").write_text(
                    "\n\n".join(parts) + "\n", encoding="utf-8"
                )

    (out / "_summary.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))
    print(f"\n-> {out}/  ({files_with_diffs} file(s) with differences)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("slugs", nargs="*", help="profiles to check (default: all)")
    ap.add_argument("--out", type=Path, default=Path("roundtrip-diffs"), help="output folder")
    ap.add_argument(
        "--ignore", action="append", default=[], metavar="TAG",
        help="element local name to drop from both sides before diffing; repeatable (e.g. --ignore note)",
    )
    ap.add_argument(
        "--ignore-empty", action="append", default=[], metavar="TAG",
        help="element local name to drop only when content-free; repeatable (e.g. --ignore-empty forename)",
    )
    args = ap.parse_args()

    slugs = args.slugs or list(ingest.PROFILES)
    unknown = [s for s in slugs if s not in ingest.PROFILES]
    if unknown:
        sys.exit(f"unknown profile(s): {', '.join(unknown)}. known: {', '.join(ingest.PROFILES)}")

    _run(slugs, args.out, set(args.ignore), set(args.ignore_empty))


if __name__ == "__main__":
    main()

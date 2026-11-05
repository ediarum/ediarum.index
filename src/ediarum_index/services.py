"""Write operations on entries, relations, anchors, comments and ingest runs —
the one place they happen, whether a route or the ingest calls them.

Each function takes a ``Session`` and commits its own change. Failures raise a
``ServiceError`` subclass carrying the HTTP status the API answers with
(``main`` registers the handler). Writes on an existing row take an optional
``project``: the routes pass the URL's, and a row of another project is then
reported as not found — the caller's access was checked for the URL's project
only.
"""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from . import export
from .dates import sorts_for
from .models import (
    Comment,
    CommentCreate,
    Entry,
    EntryCreate,
    EntryUpdate,
    IngestRun,
    IngestRunCreate,
    MentionAnchor,
    MentionAnchorUpsert,
    Project,
    Relation,
    RelationCreate,
)
from .schemas import SchemaViolation, entry_types_for, validate_entry

class ServiceError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class NotFound(ServiceError):
    status_code = 404


class Invalid(ServiceError):
    status_code = 422


class Conflict(ServiceError):
    status_code = 409


# --- entries -------------------------------------------------------------------

def _in_project(row_project: str | None, project: str | None) -> bool:
    return project is None or row_project == project


def _validate(entry_type: str, project: str, data: dict) -> None:
    try:
        validate_entry(entry_type, project, data)
    except KeyError:
        raise Invalid(f"unknown entry type {entry_type!r}")
    except SchemaViolation as exc:
        raise Invalid(str(exc))


def create_entry(session: Session, payload: EntryCreate) -> Entry:
    if session.get(Project, payload.project_name) is None:
        raise Invalid(f"unknown project {payload.project_name!r}")
    _validate(payload.entry_type, payload.project_name, payload.data)
    # only on create: an entry of an undeclared type that exists already
    # (made before the project declared ENTRY_TYPES) stays editable
    if payload.entry_type not in entry_types_for(payload.project_name):
        raise Invalid(f"project {payload.project_name!r} doesn't use entry type {payload.entry_type!r}")
    entry = Entry.model_validate(payload)
    entry.sqlmodel_update(sorts_for(entry.data))  # birth_sort / death_sort
    if payload.ingested_source_hash:
        entry.ingested_at = datetime.now(timezone.utc)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def update_entry(session: Session, entry_id: int, payload: EntryUpdate, project: str | None = None) -> Entry:
    entry = session.get(Entry, entry_id)
    if not entry or not _in_project(entry.project_name, project):
        raise NotFound("Entry not found.")
    data = payload.model_dump(exclude_unset=True)
    entry.sqlmodel_update(data)
    now = datetime.now(timezone.utc)
    entry.updated_at = now
    if data.get("ingested_source_hash"):
        # same `now` as updated_at above: an ingest-driven write must not look
        # like a curator edit that happened after it (see Entry.ingested_at)
        entry.ingested_at = now
    if "data" in data:  # date fields may have changed -> refresh sort keys
        _validate(entry.entry_type, entry.project_name, entry.data)
        entry.sqlmodel_update(sorts_for(entry.data))
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def delete_entry(session: Session, entry_id: int, project: str | None = None) -> None:
    entry = session.get(Entry, entry_id)
    if not entry or not _in_project(entry.project_name, project):
        raise NotFound("Entry not found.")
    session.delete(entry)
    session.commit()


# --- relations -----------------------------------------------------------------
# `Relation` has no `project_name` of its own: its project is its subject's
# (both ends must share one project, enforced in create_relation).

def relation_project(session: Session, relation: Relation) -> str:
    subject = session.get(Entry, relation.subject_id)
    return subject.project_name if subject else ""


def create_relation(session: Session, payload: RelationCreate, project: str | None = None) -> Relation:
    subject = session.get(Entry, payload.subject_id)
    obj = session.get(Entry, payload.object_id)
    if subject is None or obj is None or not _in_project(subject.project_name, project):
        raise NotFound("subject_id or object_id does not exist")
    if subject.project_name != obj.project_name:
        raise Invalid("subject_id and object_id must belong to the same project")
    relation = Relation.model_validate(payload)
    session.add(relation)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise Conflict(
            f"relation ({payload.subject_id}, {payload.predicate!r}, {payload.object_id}) already exists"
        )
    session.refresh(relation)
    return relation


def delete_relation(session: Session, relation_id: int, project: str | None = None) -> None:
    relation = session.get(Relation, relation_id)
    if not relation or not _in_project(relation_project(session, relation), project):
        raise NotFound("Relation not found.")
    session.delete(relation)
    session.commit()


def upsert_mention_anchor(
    session: Session, relation_id: int, payload: MentionAnchorUpsert, project: str | None = None
) -> MentionAnchor:
    """Create-or-replace the exact-position anchor for one ``mentions``
    relation's note-link (see ``models.MentionAnchor``)."""
    relation = session.get(Relation, relation_id)
    if not relation or not _in_project(relation_project(session, relation), project):
        raise NotFound("Relation not found.")
    anchor = session.exec(select(MentionAnchor).where(MentionAnchor.relation_id == relation_id)).first()
    if anchor is None:
        anchor = MentionAnchor(relation_id=relation_id, **payload.model_dump())
    else:
        anchor.sqlmodel_update(payload.model_dump())
    session.add(anchor)
    session.commit()
    session.refresh(anchor)
    return anchor


# --- comments ------------------------------------------------------------------

def create_comment(session: Session, payload: CommentCreate, author: str, project: str | None = None) -> Comment:
    """``author`` is used only for a hand-written comment: ``source``'s
    presence is what marks an ingest write (same convention as
    ``EntryCreate.ingested_source_hash``), which keeps its claimed author and
    time."""
    entry = session.get(Entry, payload.entry_id)
    if entry is None or not _in_project(entry.project_name, project):
        raise NotFound("entry_id does not exist")
    data = payload.model_dump()
    if not data.get("source"):
        data["source"] = "app"
        data["author"] = author
        data["created_at"] = datetime.now(timezone.utc)
    comment = Comment.model_validate(data)
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


def delete_comment(session: Session, comment_id: int, project: str | None = None) -> None:
    comment = session.get(Comment, comment_id)
    entry = session.get(Entry, comment.entry_id) if comment else None
    if not comment or not _in_project(entry.project_name if entry else None, project):
        raise NotFound("Comment not found.")
    session.delete(comment)
    session.commit()


# --- ingest runs ---------------------------------------------------------------

def create_ingest_run(session: Session, payload: IngestRunCreate) -> IngestRun:
    run = IngestRun.model_validate(payload.model_dump())
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


# --- export --------------------------------------------------------------------

def export_document(session: Session, project: str, entry_type: str) -> str:
    """The project's register XML for ``entry_type``, rebuilt from the stored
    entries (see ``export.build_document``)."""
    if session.get(Project, project) is None:
        raise NotFound(f"unknown project {project!r}")
    rows = session.exec(
        select(Entry)
        .where(Entry.project_name == project, Entry.entry_type == entry_type)
        .order_by(Entry.label, Entry.id)
    ).all()
    # families + memberships, for a register whose export config reconstructs
    # grouped structure (schleiermacher's family groups) — parameterized off
    # the config's "groups", not hardcoded, so this is skipped entirely (not
    # just empty) for a register with no such config
    cfg = export.export_config(project, entry_type) or {}
    groups_cfg = cfg.get("groups", {})
    families, memberships = [], []
    if group_type := groups_cfg.get("entry_type"):
        families = session.exec(
            select(Entry).where(Entry.project_name == project, Entry.entry_type == group_type)
        ).all()
        family_ids = {f.id for f in families}
        if family_ids:
            memberships = session.exec(
                select(Relation).where(
                    Relation.predicate == groups_cfg["predicate"], Relation.object_id.in_(family_ids)
                )
            ).all()
    # child -> parent relations, for a register whose records nest inside each
    # other (schleiermacher's sub-places) — same parameterization, off the
    # config's "nesting"
    parents = []
    if (predicate := cfg.get("nesting", {}).get("predicate")) and rows:
        parents = session.exec(
            select(Relation).where(
                Relation.predicate == predicate, Relation.subject_id.in_([r.id for r in rows])
            )
        ).all()
    # comments + note-links (models.Comment / "mentions" Relations) — see
    # export.build_record's comment/link re-emission. A link's target may be
    # a different entry_type (a person's note mentioning a place), so those
    # targets are resolved separately from `rows`, mirroring `families` above.
    comments, mentions, mention_targets = [], [], []
    if rows:
        row_ids = [r.id for r in rows]
        comments = session.exec(select(Comment).where(Comment.entry_id.in_(row_ids))).all()
        mentions = session.exec(
            select(Relation).where(Relation.predicate == "mentions", Relation.subject_id.in_(row_ids))
        ).all()
        target_ids = {m.object_id for m in mentions} - set(row_ids)
        if target_ids:
            mention_targets = session.exec(select(Entry).where(Entry.id.in_(target_ids))).all()
    # exact splice positions for mentions relations (models.MentionAnchor)
    # — see export._splice_mention's anchor-first branch. Keyed by
    # (subject_id, object_id), the shape _emit_mentions actually needs;
    # absent for a relation with no stored anchor (hand-created in the app,
    # or ingested before this existed), which just falls back to the
    # existing search-based placement, same as always.
    mention_anchors: dict[tuple[int, int], dict] = {}
    if mentions:
        anchor_rows = session.exec(
            select(MentionAnchor).where(MentionAnchor.relation_id.in_([m.id for m in mentions]))
        ).all()
        rel_by_id = {m.id: m for m in mentions}
        for a in anchor_rows:
            rel = rel_by_id[a.relation_id]
            mention_anchors[(rel.subject_id, rel.object_id)] = {
                "start": a.start_offset, "end": a.end_offset, "text": a.captured_text,
            }
    try:
        return export.build_document(
            project, entry_type, [r.model_dump() for r in rows],
            families=[f.model_dump() for f in families],
            memberships=[m.model_dump() for m in memberships],
            parents=[p.model_dump() for p in parents],
            comments=[c.model_dump() for c in comments],
            mentions=[m.model_dump() for m in mentions],
            mention_targets=[t.model_dump() for t in mention_targets],
            mention_anchors=mention_anchors,
        )
    except KeyError:
        raise NotFound(f"no export profile for {project!r}/{entry_type!r}")

"""Relations: generic (subject, predicate, object) triples linking two entries
in the same project — e.g. schleiermacher's person --member_of--> family — and
the exact-position anchors of ``mentions`` note-links."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.orm import aliased
from sqlmodel import select

from .. import services
from ..deps import SessionDep
from ..models import (
    Entry,
    MentionAnchorPublic,
    MentionAnchorUpsert,
    Relation,
    RelationCreate,
    RelationPublic,
    RelationWithLabels,
)

project_router = APIRouter(prefix="/relations", tags=["relations"])


@project_router.post("", response_model=RelationPublic, status_code=201)
def create_relation(project: str, payload: RelationCreate, session: SessionDep):
    """Both entries must belong to the URL's project."""
    return services.create_relation(session, payload, project)


@project_router.get("", response_model=list[RelationWithLabels])
def read_relations(
    project: str,
    session: SessionDep,
    subject_id: int | None = None,
    object_id: int | None = None,
    predicate: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    """Relations whose subject belongs to ``project``.

    Each row's ``subject_label``/``object_label`` are resolved here, in the
    same query (two aliased joins, not per-row lookups) — so a caller never
    has to turn a bare id into a display name itself, unlike the ``reference``
    field type elsewhere, which doesn't.
    """
    Subj, Obj = aliased(Entry), aliased(Entry)
    query = (
        select(Relation, Subj.label, Obj.label)
        .join(Subj, Subj.id == Relation.subject_id)
        .join(Obj, Obj.id == Relation.object_id)
        .where(Subj.project_name == project)
    )
    if subject_id is not None:
        query = query.where(Relation.subject_id == subject_id)
    if object_id is not None:
        query = query.where(Relation.object_id == object_id)
    if predicate is not None:
        query = query.where(Relation.predicate == predicate)
    rows = session.exec(query.order_by(Relation.id).offset(offset).limit(limit)).all()
    return [
        RelationWithLabels(**relation.model_dump(), subject_label=subj_label, object_label=obj_label)
        for relation, subj_label, obj_label in rows
    ]


@project_router.delete("/{relation_id}")
def delete_relation(project: str, relation_id: int, session: SessionDep):
    services.delete_relation(session, relation_id, project)
    return {"ok": True}


@project_router.put("/{relation_id}/anchor", response_model=MentionAnchorPublic)
def upsert_mention_anchor(project: str, relation_id: int, payload: MentionAnchorUpsert, session: SessionDep):
    """Create-or-replace the exact-position anchor for one ``mentions``
    relation's note-link (see ``models.MentionAnchor``). Ingest writes these
    itself (``services.upsert_mention_anchor``); not restricted to the
    ``mentions`` predicate.
    """
    return services.upsert_mention_anchor(session, relation_id, payload, project)

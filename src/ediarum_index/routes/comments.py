"""Comments: editorial remarks attached to one entry — preserved from the
source XML's own oxy_comment_start/end PIs and <!-- --> comments, or written by
a curator in the app. See models.Comment: deliberately not a Relation, and
never touches Entry.updated_at/ingested_source_hash — adding a comment must
never look like an edit to the entry's own fields."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlmodel import select

from .. import services
from ..deps import CallerDep, SessionDep
from ..models import Comment, CommentCreate, CommentIn, CommentPublic, Entry

project_router = APIRouter(prefix="/comments", tags=["comments"])


@project_router.post("", response_model=CommentPublic, status_code=201)
def create_comment(project: str, payload: CommentIn, caller: CallerDep, session: SessionDep):
    """A hand-written comment: the caller (user email or key name) is its
    author, now its time."""
    return services.create_comment(session, CommentCreate(**payload.model_dump()), caller.name, project)


@project_router.get("", response_model=list[CommentPublic])
def read_comments(
    project: str,
    session: SessionDep,
    entry_id: int | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    """Comments on entries belonging to ``project`` (a `Comment` has no
    project of its own, only `entry_id`)."""
    query = (
        select(Comment)
        .join(Entry, Entry.id == Comment.entry_id)
        .where(Entry.project_name == project)
    )
    if entry_id is not None:
        query = query.where(Comment.entry_id == entry_id)
    return session.exec(query.order_by(Comment.created_at).offset(offset).limit(limit)).all()


@project_router.delete("/{comment_id}")
def delete_comment(project: str, comment_id: int, session: SessionDep):
    services.delete_comment(session, comment_id, project)
    return {"ok": True}

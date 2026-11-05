"""Ingest runs: one row per ingest run against one profile slug — its summary
(created/updated/unchanged/conflicts/skipped/failed), persisted so a run the
watcher starts surfaces its problems in the app. Written by the ingest itself
(``services.create_ingest_run``). See models.IngestRun."""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlmodel import select

from ..deps import AdminDep, SessionDep
from ..models import IngestRun, IngestRunPublic

router = APIRouter(prefix="/ingest-runs", tags=["ingest"])


@router.get("", response_model=list[IngestRunPublic])
def read_ingest_runs(
    admin: AdminDep,
    session: SessionDep,
    project: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
):
    """Recent ingest runs, newest first, optionally of one profile slug —
    platform admins only (operational information)."""
    query = select(IngestRun)
    if project is not None:
        query = query.where(IngestRun.project == project)
    query = query.order_by(IngestRun.finished_at.desc()).offset(offset).limit(limit)
    return session.exec(query).all()

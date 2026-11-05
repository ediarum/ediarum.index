"""The projects the caller may use, for the project picker."""

import logging

from fastapi import APIRouter, Request
from sqlmodel import select

from .. import sources
from ..deps import CallerDep, SessionDep
from ..models import Project, ProjectPublic

router = APIRouter(prefix="/projects", tags=["projects"])
log = logging.getLogger(__name__)


def _sources_of_truth(request: Request) -> dict | None:
    """``{slug: "xml" | "app"}`` from the platform registry; ``{}`` without one
    (every project is then ``xml``-led), None if it can't be reached."""
    registry = getattr(request.app.state, "projects", None)
    if registry is None:
        return {}
    try:
        return {slug: info.index_source_of_truth for slug, info in registry.all().items()}
    except Exception as exc:  # noqa: BLE001 — the picker must not fail with the registry
        log.warning("platform project registry unavailable: %r", exc)
        return None


@router.get("", response_model=list[ProjectPublic])
def list_projects(session: SessionDep, caller: CallerDep, request: Request, include_inactive: bool = False):
    """The projects ``caller`` may use (all of them for an admin or an
    unscoped key), by name; inactive ones — no longer in the platform's
    registry — only with ``include_inactive``.

    ``index_source_of_truth`` is the registry's flag; ``registers_from_xml``
    whether this app actually ingests the project's registers from TEI files
    (``xml``-led and a ``REGISTER_DIR``) — the UI then notes that edits here
    don't reach the files. Both None while the registry is unreachable.
    ``assigns_ids``: an entry created without a ``source_id`` gets one from
    ediarum.id."""
    query = select(Project).order_by(Project.name)
    if not include_inactive:
        query = query.where(Project.is_active == True)  # noqa: E712
    led = _sources_of_truth(request)
    assigns_ids = getattr(request.app.state, "ids", None) is not None
    out = []
    for p in session.exec(query).all():
        if not caller.may_use(p.name):
            continue
        source = None if led is None else led.get(p.name, "xml")
        out.append(ProjectPublic(
            **p.model_dump(include={"name", "label", "description", "is_active"}),
            index_source_of_truth=source,
            registers_from_xml=None if source is None else source == "xml" and sources.has_sources(p.name),
            assigns_ids=assigns_ids,
        ))
    return out

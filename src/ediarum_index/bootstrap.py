"""Seeding of the ``entry_type`` and ``project`` lookup tables.

- ``entry_type``: from code (``models.ENTRY_TYPES``), add-only.
- ``project``: mirrors the ediarum.platform project registry (``ediarum_sdk.
  projects.ProjectsClient``, configured by ``PLATFORM_PROJECTS_URL``): every
  registry project gets an active row with the registry's label; a row the
  registry no longer lists is deactivated, never deleted (its entries stay).
  Without a registry (local development, tests) the project modules in
  ``projects/`` are the list instead, add-only.

Requires the tables to already exist, i.e. the migrations (``ediarum-index
migrate``) must have run first (``ediarum-index serve`` does this before
starting the app).
"""

import logging

from ediarum_sdk.projects import ProjectsClient
from sqlmodel import Session, select

from .models import ENTRY_TYPES, EntryTypeRow, Project
from .projects import PROJECT_MODULES, iter_projects

log = logging.getLogger("uvicorn.error")


def sync_registry(session: Session, registry: ProjectsClient | None = None) -> None:
    """Insert missing ``entry_type`` rows, and bring ``project`` in line with
    ``registry`` (or the project modules, without one)."""
    known_types = set(session.exec(select(EntryTypeRow.name)).all())
    for name, label in ENTRY_TYPES:
        if name not in known_types:
            session.add(EntryTypeRow(name=name, label=label))
    session.commit()

    if registry is None:
        known_projects = set(session.exec(select(Project.name)).all())
        for name, label, description in iter_projects():
            if name not in known_projects:
                session.add(Project(name=name, label=label, description=description))
        session.commit()
    else:
        sync_projects(session, registry.all())


def sync_projects(session: Session, registry: dict) -> None:
    """Mirror ``registry`` (``{slug: ProjectInfo}``) into the ``project`` table."""
    rows = {p.name: p for p in session.exec(select(Project)).all()}
    for slug, info in registry.items():
        row = rows.get(slug)
        if row is None:
            module = PROJECT_MODULES.get(slug)
            session.add(Project(name=slug, label=info.label,
                                description=getattr(module, "DESCRIPTION", None)))
            log.info("project %s added from the platform registry", slug)
        elif row.label != info.label or not row.is_active:
            row.label, row.is_active = info.label, True
            session.add(row)
    for name, row in rows.items():
        if name not in registry and row.is_active:
            row.is_active = False
            session.add(row)
            log.warning("project %s is no longer in the platform registry; deactivated", name)
    session.commit()


def refresh_projects(session: Session, registry: ProjectsClient | None) -> bool:
    """Re-sync ``project`` from ``registry`` (cached by the client); ``False``
    without a registry or when it is unreachable."""
    if registry is None:
        return False
    try:
        sync_projects(session, registry.all())
    except Exception as exc:  # an unreachable registry must not fail the request
        log.warning("platform project registry unavailable: %r", exc)
        return False
    return True

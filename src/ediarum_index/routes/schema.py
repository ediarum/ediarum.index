"""Entry types and the per-project form schema."""

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from ..deps import CallerDep, SessionDep
from ..models import Entry, EntryTypePublic, EntryTypeRow, FieldSchema
from ..schemas import ENTRY_TYPE_ORDER, entry_types_for, resolve_schema

router = APIRouter(tags=["schema"])
project_router = APIRouter(tags=["schema"])


def _in_canonical_order(rows):
    return sorted(rows, key=lambda r: ENTRY_TYPE_ORDER.get(r.name, 99))


@router.get("/entry-types", response_model=list[EntryTypePublic])
def list_entry_types(session: SessionDep, caller: CallerDep):
    """Registered entry types in canonical order (every project's)."""
    return _in_canonical_order(session.exec(select(EntryTypeRow)).all())


@project_router.get("/entry-types", response_model=list[EntryTypePublic])
def list_project_entry_types(project: str, session: SessionDep):
    """The entry types ``project`` uses, in canonical order — drives the
    frontend tabs: its module's ``ENTRY_TYPES`` (every type without one), plus
    any type it already has entries of, so no entry is hidden."""
    in_use = session.exec(select(Entry.entry_type).where(Entry.project_name == project).distinct()).all()
    names = set(entry_types_for(project)) | set(in_use)
    rows = session.exec(select(EntryTypeRow).where(EntryTypeRow.name.in_(names))).all()
    return _in_canonical_order(rows)


@project_router.get("/schema/{entry_type}", response_model=list[FieldSchema])
def get_schema(project: str, entry_type: str):
    try:
        return list(resolve_schema(entry_type, project))
    except KeyError:
        raise HTTPException(404, f"Unknown entry type {entry_type!r}")

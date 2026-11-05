"""Entries: paged search, picker options, and create/read/update/delete."""

from html import escape as _xml_escape
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import false
from sqlmodel import func, select

from .. import services
from ..deps import SessionDep
from ..models import Entry, EntryCreate, EntryEdit, EntryIn, EntryPublic, EntryRef, EntryUpdate

project_router = APIRouter(tags=["entries"])

_ENTRY_SORT_COLS = {
    "label": Entry.label,
    "entry_type": Entry.entry_type,
    "source_id": Entry.source_id,
    # integer keys derived from the free-text date fields (see dates.sorts_for);
    # rows with an unparseable / missing date sort last either way.
    "birth_date": Entry.birth_sort,
    "death_date": Entry.death_sort,
}


@project_router.get("/entries", response_model=list[EntryPublic])
def read_entries(
    project: str,
    response: Response,
    session: SessionDep,
    entry_type: str | None = None,
    q: str | None = None,
    q_field: str = "label",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    sort_by: str = "label",
    descending: bool = False,
):
    """One page of entries, ordered by ``sort_by`` (default the generated label).

    ``sort_by`` accepts ``label``, ``entry_type``, ``source_id`` and the
    date keys ``birth_date`` / ``death_date`` (ordered
    by the derived integer sort columns; undated rows come last).

    ``q`` filters by a case-insensitive substring match on ``q_field``: the
    ``label`` (default) or ``source_id`` column, or any key inside the JSON
    ``data`` bag (matched against the stored value's text, so it also hits
    repeatable fields). An unknown ``q_field`` matches nothing.

    The full match count is in the ``X-Total-Count`` response header.
    """
    query = select(Entry).where(Entry.project_name == project)
    if entry_type is not None:
        query = query.where(Entry.entry_type == entry_type)
    if q:
        term = f"%{q}%"
        if q_field in ("label", "source_id"):
            query = query.where(getattr(Entry, q_field).ilike(term))
        elif q_field.isidentifier():
            query = query.where(Entry.data[q_field].as_string().ilike(term))
        else:
            query = query.where(false())

    response.headers["X-Total-Count"] = str(
        session.exec(select(func.count()).select_from(query.subquery())).one()
    )

    col = _ENTRY_SORT_COLS.get(sort_by, Entry.label)
    ordering = col.desc() if descending else col.asc()
    return session.exec(
        # NULLs (missing / unparseable) always last, regardless of direction
        query.order_by(col.is_(None), ordering, Entry.id).offset(offset).limit(limit)
    ).all()


def _entries_ul(rows) -> str:
    """``rows`` (id, source_id, label, data) as
    ``<ul><li xml:id="…"><span>Label (birth-death)</span></li>…</ul>``.

    For an external reference picker (the ediarum/oXygen authoring
    environment) that expects a source ``xml:id`` to key on, not this app's
    own numeric id. An entry without a ``source_id`` is left out: its numeric
    id is not a valid ``xml:id``. Birth/
    death come from ``data["birth_date"]``/``["death_date"]``, the field name
    every project with dated persons uses; always appended as ``" (b-d)"``,
    even blank-blank, to match the reference format's fixed shape — a project
    or entry type without those fields (pta's floruit, any ``group`` entry)
    just always gets the empty ``" (-)"`` suffix.
    """
    items = []
    for _entry_id, source_id, label, data in rows:
        xml_id = _xml_escape(source_id, quote=True)
        birth = (data or {}).get("birth_date", "")
        death = (data or {}).get("death_date", "")
        text = _xml_escape(f"{label} ({birth}-{death})")
        items.append(f'<li xml:id="{xml_id}">\n<span>{text}</span>\n</li>')
    return "<ul>\n" + "\n".join(items) + "\n</ul>" if items else "<ul></ul>"


@project_router.get("/entries/options", response_model=list[EntryRef])
def list_entry_options(
    project: str,
    session: SessionDep,
    entry_type: str,
    q: str | None = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100000)] = 10000,
    format: Literal["json", "ul"] = "json",
):
    """``(id, label)`` for the entries of ``(project, entry_type)``, ordered by
    label — for populating a reference field / autocomplete. ``id`` is the
    MariaDB primary key. Optional ``q`` is a case-insensitive substring match on
    the label.

    Page with ``offset`` for a project with more entries than ``limit``
    rather than raising the cap: an uncapped query here is the one way a huge project could
    turn an options lookup into an accidental full-table scan.

    ``format=ul`` returns ``<ul><li xml:id="…"><span>Label (birth-death)</span>
    </li>…</ul>`` as ``application/xml`` instead — see ``_entries_ul``.
    """
    cols = (
        (Entry.id, Entry.source_id, Entry.label, Entry.data)
        if format == "ul"
        else (Entry.id, Entry.label)
    )
    query = select(*cols).where(Entry.project_name == project, Entry.entry_type == entry_type)
    if format == "ul":  # see _entries_ul: only entries with a source_id
        query = query.where(Entry.source_id.is_not(None), Entry.source_id != "")
    if q:
        query = query.where(Entry.label.ilike(f"%{q}%"))
    rows = session.exec(query.order_by(Entry.label, Entry.id).offset(offset).limit(limit)).all()
    if format == "ul":
        return Response(_entries_ul(rows), media_type="application/xml")
    return [EntryRef(id=row_id, label=label) for row_id, label in rows]


@project_router.post("/entries", response_model=EntryPublic, status_code=201)
def create_entry(project: str, entry: EntryIn, session: SessionDep, request: Request):
    """Create an entry. Without a ``source_id`` it gets one from ediarum.id
    (``idservice``); 503 if ediarum.id can't be reached — no entry without an id."""
    ids = getattr(request.app.state, "ids", None)
    if not entry.source_id and ids is not None:
        entry.source_id = ids.new_id(project, note=f"ediarum.index {entry.entry_type}: {entry.label}")
    return services.create_entry(session, EntryCreate(project_name=project, **entry.model_dump()))


@project_router.get("/entries/{entry_id}", response_model=EntryPublic)
def read_entry(project: str, entry_id: int, session: SessionDep) -> Entry:
    entry = session.get(Entry, entry_id)
    if not entry or entry.project_name != project:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry


@project_router.patch("/entries/{entry_id}", response_model=EntryPublic)
def update_entry(project: str, entry_id: int, entry: EntryEdit, session: SessionDep):
    payload = EntryUpdate(**entry.model_dump(exclude_unset=True))
    return services.update_entry(session, entry_id, payload, project)


@project_router.delete("/entries/{entry_id}")
def delete_entry(project: str, entry_id: int, session: SessionDep):
    services.delete_entry(session, entry_id, project)
    return {"ok": True}

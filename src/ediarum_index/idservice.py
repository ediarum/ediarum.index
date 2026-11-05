"""New ``source_id``s from ediarum.id, for entries created in the app.

An entry created by ``POST /{project}/entries`` without a ``source_id`` gets
one from ediarum.id: reserved there, then confirmed at once, so ediarum.id
counts it as used whether or not it ever shows up in a file. Confirming
before the entry is stored means a failed write leaves at worst an unused id.

``ID_URL`` (ediarum.id's API, e.g. ``http://ediarum-id-api:8000``) and
``ID_KEY`` (an ediarum.id key valid for the projects, e.g.
``ediarum-id keys add index --admin``). Without ``ID_URL`` entries created in
the app get no ``source_id`` and are left out of the oXygen picker.

``ediarum-index ids backfill`` gives the entries that have none one each.
"""

import os

import httpx2 as httpx
from sqlmodel import Session, or_, select

from .models import Entry
from .services import ServiceError

ID_URL_ENV = "ID_URL"
ID_KEY_ENV = "ID_KEY"
TIMEOUT = 5.0


class IdServiceUnavailable(ServiceError):
    "ediarum.id unreachable or refusing: no entry is created without an id (503)."
    status_code = 503


class IdService:
    "Client for ediarum.id's ``POST /{project}/ids`` and ``POST /{project}/ids/confirm``."

    def __init__(self, client: httpx.Client, url: str, key: str | None = None):
        self.client = client
        self.url = url.rstrip("/")
        self.headers = {"X-API-Key": key} if key else {}

    @classmethod
    def from_env(cls) -> "IdService | None":
        "From ``ID_URL`` / ``ID_KEY``; None without ``ID_URL``."
        url = os.getenv(ID_URL_ENV)
        if not url:
            return None
        return cls(httpx.Client(timeout=TIMEOUT), url, os.getenv(ID_KEY_ENV))

    def _post(self, path: str, **kwargs) -> dict:
        try:
            res = self.client.post(f"{self.url}{path}", headers=self.headers, **kwargs)
            res.raise_for_status()
            return res.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise IdServiceUnavailable(f"ediarum.id: {exc}") from None

    def new_id(self, project: str, note: str | None = None) -> str:
        "Reserve one id for ``project`` and confirm it as used."
        params = {"note": note[:1024]} if note else {}
        xml_id = self._post(f"/{project}/ids", params=params)["ids"][0]
        self._post(f"/{project}/ids/confirm", json={"ids": [xml_id]})
        return xml_id


def backfill(session: Session, ids: IdService | None, project: str | None = None,
             dry_run: bool = False) -> list[tuple[Entry, str | None]]:
    """Give every entry without a ``source_id`` one from ediarum.id, optionally of one
    project; ``(entry, new id)`` per entry, the id None with ``dry_run``. Each entry is
    committed on its own, so an interrupted run keeps what it did. ``updated_at`` stays:
    an identifier, not a curator edit."""
    query = select(Entry).where(or_(Entry.source_id.is_(None), Entry.source_id == ""))
    if project:
        query = query.where(Entry.project_name == project)
    done = []
    for entry in session.exec(query.order_by(Entry.project_name, Entry.id)).all():
        if dry_run:
            done.append((entry, None))
            continue
        entry.source_id = ids.new_id(entry.project_name, note=f"ediarum.index {entry.entry_type}: {entry.label}")
        session.add(entry)
        session.commit()
        done.append((entry, entry.source_id))
    return done

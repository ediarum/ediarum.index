"""API keys (``ediarum_sdk.auth.ApiKey``) for clients without a platform
session — ediarum/oXygen, scripts. Platform admins only; the key itself is
shown once, in the create response."""

import logging

from ediarum_sdk.auth import ApiKey, create_key
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import select

from ..deps import AdminDep, SessionDep
from ..models import Project

log = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/keys", tags=["keys"])

NO_STORE = {"Cache-Control": "no-store"}


class KeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    projects: list[str] = Field(min_length=1)  # slugs, or ["*"] for every project


class KeyOut(BaseModel):
    name: str
    projects: list[str]
    is_admin: bool
    is_active: bool
    created_by: str | None

    @classmethod
    def from_row(cls, row: ApiKey) -> "KeyOut":
        return cls(name=row.name, projects=row.projects.split(","), is_admin=row.is_admin,
                   is_active=row.is_active, created_by=row.created_by)


class NewKey(BaseModel):
    name: str
    key: str


@router.get("", response_model=list[KeyOut])
def list_keys(admin: AdminDep, session: SessionDep, project: str | None = None):
    "API clients, optionally only those that may use ``project``. Keys themselves are never shown."
    rows = session.exec(select(ApiKey).order_by(ApiKey.name)).all()
    return [KeyOut.from_row(r) for r in rows if project is None or r.is_admin or r.may_use(project)]


@router.post("", response_model=NewKey, status_code=201)
def create_api_key(body: KeyIn, admin: AdminDep, session: SessionDep, response: Response):
    "Create a client for the given projects; the key is in this response only."
    response.headers.update(NO_STORE)
    if session.get(ApiKey, body.name) is not None:
        raise HTTPException(409, f"a key named {body.name} already exists")
    projects = list(dict.fromkeys(body.projects))
    if projects != ["*"]:
        known = set(session.exec(select(Project.name).where(Project.is_active == True)))  # noqa: E712
        if unknown := [p for p in projects if p not in known]:
            raise HTTPException(422, f"unknown or inactive project: {', '.join(unknown)}")
    key = create_key(session, body.name, ",".join(projects), created_by=admin.name)
    log.info("API key %s for %s created by %s", body.name, ",".join(projects), admin.name)
    return NewKey(name=body.name, key=key)


@router.post("/{name}/revoke", status_code=204)
def revoke_key(name: str, admin: AdminDep, session: SessionDep) -> None:
    "Deactivate a key for good (revoking twice is fine)."
    row = session.get(ApiKey, name)
    if row is None:
        raise HTTPException(404, f"unknown key {name}")
    if row.is_active:
        row.is_active = False
        session.add(row)
        session.commit()
        log.info("API key %s revoked by %s", name, admin.name)

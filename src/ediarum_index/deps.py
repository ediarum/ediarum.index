"""FastAPI dependencies shared by the routers: the DB session, the caller and
the project.

Two kinds of callers, both resolved by ``ediarum_sdk.auth`` into a ``Caller``:

- **platform users** — requests from the ediarum.platform carry its session
  cookie; the auth provider's verify endpoint (``AUTH_VERIFY_URL``) says who
  the user is, their roles and their projects (ediarum-platform:
  docs/auth-contract.md). A user may use a project if it is one of theirs or
  they have the role ``admin``.
- **API keys** — for clients without a browser session (ediarum/oXygen,
  scripts): ``Authorization: Bearer``, ``X-API-Key`` or a ``key`` query
  parameter, checked against the SDK's ``sdk_api_key`` table. A key is scoped
  to some projects or ``*``.

A request with a key is always checked as a key. Without ``AUTH_VERIFY_URL``
(or ``AUTH_DEV_USER``, local development only) only keys are accepted.
"""

from typing import Annotated

from ediarum_sdk.auth import Caller, extract_key, key_caller, platform_user, require_project_access
from fastapi import Depends, HTTPException, Query, Request, status
from sqlmodel import Session

from .bootstrap import refresh_projects
from .db import get_session
from .models import Project

SessionDep = Annotated[Session, Depends(get_session)]


def current_caller(
    request: Request,
    session: SessionDep,
    key: Annotated[str | None, Query(include_in_schema=False)] = None,
) -> Caller:
    """The caller (key or platform user); 403 if the route's ``{project}`` is
    not one they may use."""
    presented = extract_key(request, key)
    caller = key_caller(session, presented) if presented else platform_user(request)
    require_project_access(caller, request.path_params.get("project"))
    return caller


CallerDep = Annotated[Caller, Depends(current_caller)]


def admin_user(caller: CallerDep) -> Caller:
    "Platform users with the role ``admin`` only — never a key, so a key can't make keys."
    if caller.kind != "user" or not caller.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "platform admins only")
    return caller


AdminDep = Annotated[Caller, Depends(admin_user)]


def current_project(project: str, caller: CallerDep, request: Request, session: SessionDep) -> Project:
    """The route's ``{project}`` row, after the caller's access check; 404 if
    it is unknown or inactive. An unknown slug triggers one refresh from the
    platform registry first, so a project added there works without a restart."""
    row = session.get(Project, project)
    if row is None and refresh_projects(session, getattr(request.app.state, "projects", None)):
        row = session.get(Project, project)
    if row is None or not row.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown project {project!r}")
    return row


ProjectDep = Annotated[Project, Depends(current_project)]

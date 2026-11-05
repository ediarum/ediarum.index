"""FastAPI app: read/write ediarum.index entries and serve the per-project form schema.

The routes live in ``routes/`` (one router per resource), their writes in
``services``, the shared dependencies (caller, project) in ``deps``.

Served behind the ediarum.platform's proxy at ``/api/index/`` (prefix
stripped; ``ediarum-index serve --root-path`` / ``$ROOT_PATH``), same-origin
with the platform — so no CORS and no session of its own: every request is a
platform user (checked against ``AUTH_VERIFY_URL``) or an API key, see ``deps``.

Startup (``lifespan``):

- ``app.state.auth_config`` / ``verify_client`` — what ``ediarum_sdk.auth``
  needs to check platform users;
- ``app.state.projects`` — the platform's project registry
  (``PLATFORM_PROJECTS_URL``), or ``None`` without one;
- ``app.state.ids`` — ediarum.id, for the ``source_id`` of entries created in
  the app (``ID_URL``), or ``None`` without it;
- ``bootstrap.sync_registry`` — seeds ``entry_type`` and mirrors the
  projects. The tables must already exist: ``ediarum-index serve`` migrates
  the database before the app starts. Schema is never created here.
"""

import logging
import os
from contextlib import asynccontextmanager

import httpx2 as httpx
from ediarum_sdk.auth import VERIFY_TIMEOUT, AuthConfig
from ediarum_sdk.projects import PROJECTS_URL_ENV, ProjectsClient
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session

from .bootstrap import sync_registry
from .db import engine, get_session  # noqa: F401 — get_session: the dependency tests override
from .idservice import IdService
from .routes import ROUTERS
from .services import ServiceError

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.auth_config = AuthConfig.from_env()
    if not (app.state.auth_config.verify_url or app.state.auth_config.dev_user):
        log.warning("neither AUTH_VERIFY_URL nor AUTH_DEV_USER is set: only API keys are accepted")
    with httpx.Client(timeout=VERIFY_TIMEOUT) as verify_client, httpx.Client() as registry_client:
        app.state.verify_client = verify_client
        app.state.projects = ProjectsClient(registry_client) if os.getenv(PROJECTS_URL_ENV) else None
        app.state.ids = IdService.from_env()
        if app.state.ids is None:
            log.warning("ID_URL not set: entries created in the app get no source_id")
        with Session(engine) as session:
            try:
                sync_registry(session, app.state.projects)
            except httpx.HTTPError as exc:
                # the project rows from the last sync stay; the next unknown
                # slug retries (deps.current_project)
                log.warning("platform project registry unavailable at startup: %r", exc)
        try:
            yield
        finally:
            if app.state.ids is not None:
                app.state.ids.client.close()


app = FastAPI(title="ediarum.index", lifespan=lifespan)


@app.exception_handler(ServiceError)
def service_error(request: Request, exc: ServiceError):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


for router in ROUTERS:
    app.include_router(router)

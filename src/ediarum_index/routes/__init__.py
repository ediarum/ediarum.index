"""The API's routers, one module per resource; ``main`` includes ``ROUTERS``.

Fixed paths (``/projects``, ``/entry-types``, ``/keys``, ``/ingest-runs``, ``/files``)
come first; everything else lives under ``/{project}/…``, behind
``deps.current_project`` (the caller's access check, then the project lookup).
"""

from fastapi import APIRouter, Depends

from ..deps import current_project
from . import comments, entries, export, files, ingest_runs, keys, projects, relations, schema

# path segments a project slug must not be — they are fixed routes
RESERVED_SLUGS = {"projects", "entry-types", "keys", "ingest-runs", "files", "docs", "redoc", "openapi.json"}

project_routes = APIRouter(prefix="/{project}", dependencies=[Depends(current_project)])
for module in (schema, entries, export, relations, comments):
    project_routes.include_router(module.project_router)

ROUTERS = [
    projects.router,
    schema.router,
    keys.router,
    ingest_runs.router,
    files.router,
    project_routes,
]

"""``POST /files``: ediarum.webdav reports a saved file — the multipart notice
ediarum.fileservice takes too. (The deployed webdav posts to one services URL
with one key; whether a notice reaches this app as well depends on the
deployment — the watcher's periodic check covers it either way.) Nothing is
ingested here: the notice is recorded (``FileNotice``) and
``ediarum-index watch`` ingests the project once the change is on the shared
volume (fileservice writes it there)."""

import hashlib
from pathlib import PurePosixPath
from typing import Annotated

from ediarum_sdk.auth import require_project_access
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from .. import sources
from ..deps import CallerDep, SessionDep
from ..models import FILE_EVENTS, FileNotice, FileNoticeOut, Project

router = APIRouter(tags=["files"])


def posted_path(path: str, field: str) -> str:
    "``path`` as sent, normalized; 400 if it isn't a relative path inside the project."
    p = PurePosixPath(path)
    if not path or p.is_absolute() or ".." in p.parts or "\\" in path:
        raise HTTPException(400, f"{field} must be a relative path inside the project: {path!r}")
    return str(p)


def source_of_truth(request: Request, project: str) -> str:
    registry = getattr(request.app.state, "projects", None)
    if registry is None:
        return "xml"
    try:
        info = registry.get(project)
    except Exception:
        raise HTTPException(503, "platform project registry unavailable")
    return info.index_source_of_truth if info else "xml"


@router.post("/files", response_model=FileNoticeOut, status_code=202)
def file_changed(
    request: Request,
    session: SessionDep,
    caller: CallerDep,
    event: Annotated[str, Form()],
    project: Annotated[str, Form()],
    commit: Annotated[str, Form()],
    path: Annotated[str, Form()],
    previous_path: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    """One file change in a project's data, as ediarum.webdav saved it:
    ``created`` / ``modified`` (with ``file``), ``moved`` (``previous_path`` →
    ``path``, ``file`` optional) or ``deleted``. ``queued`` is false for a
    file none of the project's registers are read from — including every file
    of a project this app has no registers for (no ``REGISTER_DIR``) and of
    an ``app``-led project, whose registers are kept here."""
    if event not in FILE_EVENTS:
        raise HTTPException(422, f"unknown event {event!r}")
    require_project_access(caller, project)
    row = session.get(Project, project)
    if row is None or not row.is_active:
        raise HTTPException(404, f"unknown project {project!r}")
    path = posted_path(path, "path")
    if event == "moved":
        if not previous_path:
            raise HTTPException(422, "'moved' requires previous_path")
        previous_path = posted_path(previous_path, "previous_path")
    elif event in ("created", "modified") and file is None:
        raise HTTPException(422, f"{event!r} requires file content")
    result = FileNoticeOut(project=project, event=event, path=path, commit=commit, queued=False)
    if source_of_truth(request, project) != "xml":  # registers kept here: nothing to ingest
        return result
    if not (sources.is_source_path(project, path)
            or (previous_path and sources.is_source_path(project, previous_path))):
        return result
    sha256 = hashlib.sha256(file.file.read()).hexdigest() if file is not None and event != "deleted" else None
    session.add(FileNotice(project=project, event=event, path=path, commit=commit, sha256=sha256,
                           previous_path=previous_path if event == "moved" else None))
    session.commit()
    return result.model_copy(update={"queued": True})

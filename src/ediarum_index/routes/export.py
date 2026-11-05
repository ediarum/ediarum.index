"""TEI export of a project's register, rebuilt from the stored entries."""

from fastapi import APIRouter, Response

from .. import services
from ..deps import SessionDep

project_router = APIRouter(tags=["export"])


@project_router.get("/export/{entry_type}")
def export_entries(project: str, entry_type: str, session: SessionDep):
    """Rebuild the project's register XML from the stored entries.

    Structure and field content match the source; whitespace, comments and the
    ``<teiHeader>`` do not (see ``export.py``). 404 if there is no export
    profile for ``(project, entry_type)``.
    """
    xml = services.export_document(session, project, entry_type)
    return Response(content=xml, media_type="application/xml")

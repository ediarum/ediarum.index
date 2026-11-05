"""Where a project's TEI registers are, and whether they changed.

The XML lives on the shared volume ediarum.fileservice keeps in step with git
and ediarum.webdav (mounted read-only, ``XML_MOUNT_ROOT``): one checkout per
project at ``XML_MOUNT_ROOT/<slug>/``, files at their repository paths. This
app never clones, pulls or writes there.

Inside that checkout a project module's ``REGISTER_DIR`` (e.g.
``data/Register``) is where its registers are; the ingest profiles' ``source``
globs are relative to it. Only *which files* the profiles read matters here:
``project_files`` lists them, ``digest`` fingerprints their content.
"""

import hashlib
import os
from fnmatch import fnmatch
from glob import glob
from pathlib import Path, PurePosixPath

from . import projects

MOUNT_ROOT_ENV = "XML_MOUNT_ROOT"


class SourceError(SystemExit):
    "A project's XML can't be located (raised as SystemExit, like the ingest's other setup errors)."


def mount_root() -> Path:
    root = os.getenv(MOUNT_ROOT_ENV)
    if not root:
        raise SourceError(f"set {MOUNT_ROOT_ENV} to the shared XML volume (one folder per project slug)")
    return Path(root)


def register_dir(project: str) -> Path:
    """``XML_MOUNT_ROOT/<project>/<REGISTER_DIR>`` — what the profiles' ``source``
    globs are relative to."""
    module = projects.PROJECT_MODULES.get(project)
    rel = getattr(module, "REGISTER_DIR", None)
    if rel is None:
        raise SourceError(f"project {project!r} has no REGISTER_DIR in its module (src/ediarum_index/projects/)")
    return mount_root() / project / rel


def has_sources(project: str) -> bool:
    "Whether ``project`` is ingested from XML at all (its module declares ``REGISTER_DIR``)."
    return getattr(projects.PROJECT_MODULES.get(project), "REGISTER_DIR", None) is not None


def profile_globs(project: str) -> list[str]:
    "The ``source`` globs of every ingest profile writing into ``project``."
    from .ingest import PROFILES, project_of  # ingest imports this module

    return [p["source"] for slug, p in PROFILES.items() if project_of(slug) == project]


def project_files(project: str) -> list[Path]:
    "Every file ``project``'s profiles read, sorted."
    base = register_dir(project)
    files = {Path(p) for pattern in profile_globs(project)
             for p in glob(str(base / pattern), recursive=True) if ".ipynb_checkpoints" not in p}
    return sorted(f for f in files if f.is_file())


def is_source_path(project: str, path: str) -> bool:
    """Whether ``path`` (relative to the project's checkout, as webdav and
    fileservice name it) is one of the files ``project``'s profiles read."""
    module = projects.PROJECT_MODULES.get(project)
    rel = getattr(module, "REGISTER_DIR", None)
    if rel is None:
        return False
    try:
        inside = PurePosixPath(path).relative_to(PurePosixPath(rel))
    except ValueError:
        return False
    return any(fnmatch(str(inside), pattern) for pattern in profile_globs(project))


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class HashCache:
    """Content hashes by path, re-read only when size or mtime changed — a
    long-running watcher reads each file once, then just ``stat``s it."""

    def __init__(self):
        self._known: dict[Path, tuple[int, int, str]] = {}

    def sha256(self, path: Path) -> str:
        st = path.stat()  # before reading: a write during the read shows up next time
        known = self._known.get(path)
        if known and known[:2] == (st.st_size, st.st_mtime_ns):
            return known[2]
        sha = file_sha256(path)
        self._known[path] = (st.st_size, st.st_mtime_ns, sha)
        return sha


def digest(project: str, cache: HashCache | None = None) -> str:
    """One fingerprint of the content of every file ``project``'s profiles
    read (and of which files those are): changes iff an ingest could see
    something different."""
    cache = cache or HashCache()
    base = register_dir(project)
    h = hashlib.sha256()
    for path in project_files(project):
        try:
            sha = cache.sha256(path)
        except FileNotFoundError:  # deleted between listing and reading
            continue
        h.update(f"{path.relative_to(base).as_posix()}\0{sha}\n".encode())
    return h.hexdigest()

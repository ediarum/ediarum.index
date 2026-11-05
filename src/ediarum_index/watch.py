"""Keep the entries in step with the shared XML volume: ``ediarum-index watch``.

A standalone, long-lived process, separate from the API server; it is the only
thing that runs the ingest automatically. One project at a time, so two
ingests of a project never overlap.

- **Digest, not events.** A project is ingested when the digest of the files
  its profiles read (``sources.digest``) differs from the one its last ingest
  read (``models.SourceState``). Content hashes are only re-read for files
  whose size or mtime changed. No inotify: events can be lost, a digest can't
  miss anything.
- **First start.** A project with no ``SourceState`` yet is ingested in full —
  on an empty database that is the initial ingest.
- **Periodic checks.** Every ``interval`` seconds each project is checked. If
  ``FILESERVICE_URL`` is set, its ``/projects/<slug>/status`` says whether
  fileservice changed anything since the last check (claimed or verified
  commit); if not, the digest is skipped — but never for longer than
  ``full_every`` seconds. Without fileservice, or if it can't be reached,
  every check computes the digest: the volume is the truth, the status only
  saves work.
- **``POST /files`` notices.** ediarum.webdav reports a saved file at once
  (``models.FileNotice``). A project with notices is checked as soon as the
  volume shows every reported change (fileservice writes it there — the two
  are separate jobs, in no fixed order) and nothing new arrived for
  ``settle`` seconds; after ``wait_max`` seconds it is checked anyway.
- **Nothing to watch yet.** Without an XML-led project (every project
  ``app``-led, or none registered) the watcher idles and re-reads the registry
  every ``interval``; a project that becomes XML-led is picked up then. Only
  ``--project`` names that don't qualify are an error (exit).
- A failed ingest is logged and retried at the next periodic check; watching
  continues.
  Conflicts and failed records are in the ingest run history, not here.
"""

import os
import time
from datetime import datetime, timezone

import httpx2 as httpx
from ediarum_sdk.projects import PROJECTS_URL_ENV, ProjectsClient
from sqlmodel import Session, delete, select

from . import ingest, sources
from .bootstrap import refresh_projects, sync_registry
from .models import FileNotice, Project, SourceState

DEFAULT_INTERVAL = 300  # seconds between checks of a project; fileservice's default grace period
DEFAULT_FULL_EVERY = 86400  # compute the digest at least this often, whatever fileservice says
DEFAULT_SETTLE = 10  # seconds without a new notice before a noticed project is checked
DEFAULT_WAIT_MAX = 300  # check a noticed project after this long even if the volume doesn't match
FILESERVICE_URL_ENV = "FILESERVICE_URL"
FILESERVICE_KEY_ENV = "FILESERVICE_KEY"
STATUS_TIMEOUT = 5.0


def log(message: str) -> None:
    print(time.strftime("%Y-%m-%d %H:%M:%S"), message, flush=True)


class FileserviceStatus:
    "What ediarum.fileservice last did to a project's files: its claimed and verified commit."

    def __init__(self, client: httpx.Client, url: str, key: str | None = None):
        self.client = client
        self.url = url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}

    @classmethod
    def from_env(cls) -> "FileserviceStatus | None":
        url = os.getenv(FILESERVICE_URL_ENV)
        if not url:
            return None
        return cls(httpx.Client(timeout=STATUS_TIMEOUT), url, os.getenv(FILESERVICE_KEY_ENV))

    def fingerprint(self, project: str) -> tuple:
        "Changes whenever fileservice wrote or reset the project's files. Raises if unreachable."
        res = self.client.get(f"{self.url}/projects/{project}/status", headers=self.headers)
        res.raise_for_status()
        body = res.json()
        return body.get("claimed_commit"), body.get("verified_commit")


def on_volume(notice: FileNotice) -> bool:
    "Whether the shared volume already shows the change ``notice`` reports."
    root = sources.mount_root() / notice.project
    target = root / notice.path
    if notice.event == "deleted":
        return not target.exists()
    if notice.event == "moved" and notice.previous_path and (root / notice.previous_path).exists():
        return False
    if not target.is_file():
        return False
    return notice.sha256 is None or sources.file_sha256(target) == notice.sha256


class Watcher:
    def __init__(self, engine, registry: ProjectsClient | None = None,
                 fileservice: FileserviceStatus | None = None, only: list[str] | None = None,
                 interval: float = DEFAULT_INTERVAL, full_every: float = DEFAULT_FULL_EVERY,
                 settle: float = DEFAULT_SETTLE, wait_max: float = DEFAULT_WAIT_MAX):
        self.engine = engine
        self.registry = registry
        self.fileservice = fileservice
        self.only = set(only) if only else None
        self.interval = interval
        self.full_every = full_every
        self.settle = settle
        self.wait_max = wait_max
        self.cache = sources.HashCache()
        self._checked: dict[str, float] = {}  # project -> last check (monotonic)
        self._digested: dict[str, float] = {}  # project -> last digest
        self._fingerprints: dict[str, tuple] = {}  # project -> fileservice state at the last digest
        self._empty: set[str] = set()  # projects without register files on the volume (logged once)
        self._refreshed = float("-inf")  # last registry refresh (monotonic)
        self._watched: list[str] = []  # the projects of the last step, for the "now watching" log

    def projects(self) -> list[str]:
        """The active projects ingested from XML: a ``REGISTER_DIR`` in their
        module, and ``xml``-led in the platform registry (if there is one)."""
        with Session(self.engine) as session:
            active = session.exec(select(Project.name).where(Project.is_active == True)).all()  # noqa: E712
        registry = None
        if self.registry is not None:
            try:
                registry = self.registry.all()
            except Exception as exc:  # the cached list, or nothing yet
                log(f"platform project registry unavailable ({exc!r})")
        names = []
        for name in sorted(active):
            if not sources.has_sources(name) or (self.only and name not in self.only):
                continue
            if registry is not None and name in registry and registry[name].index_source_of_truth != "xml":
                continue
            names.append(name)
        return names

    def check(self, project: str, force: bool = False) -> bool:
        """Ingest ``project`` if its sources changed since its last ingest (or
        ``force``); ``True`` unless the ingest failed. The digest is skipped when
        fileservice reports no change since the last one (see module docstring)."""
        now = time.monotonic()
        self._checked[project] = now
        fingerprint = None
        if self.fileservice and not force:
            try:
                fingerprint = self.fileservice.fingerprint(project)
            except (httpx.HTTPError, ValueError) as exc:
                log(f"{project}: fileservice status unavailable ({type(exc).__name__}: {exc}) — checking")
        recent = now - self._digested.get(project, float("-inf")) < self.full_every
        if not force and recent and fingerprint is not None and fingerprint == self._fingerprints.get(project):
            return True
        try:
            if not sources.project_files(project):
                # fileservice hasn't checked it out (yet): nothing to ingest, nothing to record
                if project not in self._empty:
                    log(f"{project}: no register files at {sources.register_dir(project)} — skipped")
                    self._empty.add(project)
                return True
            self._empty.discard(project)
            current = sources.digest(project, self.cache)
        except SystemExit as exc:  # no mount / no REGISTER_DIR
            log(f"{project}: {exc}")
            return False
        self._digested[project] = now
        if fingerprint is not None:
            self._fingerprints[project] = fingerprint
        with Session(self.engine) as session:
            state = session.get(SourceState, project)
            if state is not None and state.digest == current and not force:
                return True
            log(f"{project}: {'first ingest' if state is None else 'sources changed'} — ingesting")
            started = time.monotonic()
            try:
                clean = ingest.ingest_project(session, project)
            except Exception as exc:  # keep watching whatever happens
                session.rollback()
                log(f"{project}: ingest FAILED, retried at the next check: {type(exc).__name__}: {exc}")
                return False
            state = session.get(SourceState, project) or SourceState(project=project, digest=current)
            state.digest, state.ingested_at = current, datetime.now(timezone.utc)
            session.add(state)
            session.commit()
        log(f"{project}: ingested in {time.monotonic() - started:.0f}s"
            + ("" if clean else " — with conflicts or failed records, see /ingest-runs"))
        return True

    def handle_notices(self) -> None:
        "Check every project whose ``POST /files`` notices are on the volume (or waited long enough)."
        with Session(self.engine) as session:
            notices = session.exec(select(FileNotice).order_by(FileNotice.id)).all()
        by_project: dict[str, list[FileNotice]] = {}
        for n in notices:
            by_project.setdefault(n.project, []).append(n)
        now = datetime.now(timezone.utc)
        for project, items in by_project.items():
            newest = max(n.received_at for n in items)
            oldest = min(n.received_at for n in items)
            if (now - newest).total_seconds() < self.settle:
                continue
            waited = (now - oldest).total_seconds() >= self.wait_max
            if not waited and not all(on_volume(n) for n in items):
                continue
            if project in self.projects():
                log(f"{project}: {len(items)} reported change(s)" + (" (not all on the volume yet)" if waited else ""))
                # a failed ingest leaves the old SourceState, so the next periodic
                # check retries it — the notices are done either way
                self.check(project)
            with Session(self.engine) as session:
                session.exec(delete(FileNotice).where(FileNotice.id.in_([n.id for n in items])))
                session.commit()

    def step(self) -> None:
        "Handle notices; re-read the registry every ``interval``; check every project that is due."
        self.handle_notices()
        now = time.monotonic()
        if now - self._refreshed >= self.interval:
            # also while idle: a new or newly XML-led project must show up
            self._refreshed = now
            with Session(self.engine) as session:
                refresh_projects(session, self.registry)
        projects = self.projects()
        if projects != self._watched:
            log(f"watching {', '.join(projects)}" if projects else "no XML-led project to watch — idle")
            self._watched = projects
        for project in projects:
            if now - self._checked.get(project, float("-inf")) >= self.interval:
                self.check(project)

    def start(self) -> None:
        with Session(self.engine) as session:
            try:
                sync_registry(session, self.registry)
            except Exception as exc:
                log(f"platform project registry unavailable at start ({exc!r}); using the known projects")
        self._refreshed = time.monotonic()
        projects = self.projects()
        self._watched = projects
        if not projects:
            if self.only:  # named on the command line: a configuration error
                raise SystemExit(f"nothing to watch — {', '.join(sorted(self.only))}: not an active, "
                                 "XML-led project with a REGISTER_DIR")
            log(f"no XML-led project with a REGISTER_DIR yet — idle, re-checking every {self.interval:g}s")
            return
        log(f"catching up on {len(projects)} project(s) ...")
        for project in projects:
            self.check(project)

    def run_forever(self) -> None:
        self.start()
        if self._watched:
            log(f"watching {len(self._watched)} project(s), checked every {self.interval:g}s"
                + (" (fileservice status)" if self.fileservice else ""))
        try:
            while True:
                self.step()
                time.sleep(1)
        except KeyboardInterrupt:
            log("stopping ...")


def registry_from_env() -> ProjectsClient | None:
    return ProjectsClient(httpx.Client()) if os.getenv(PROJECTS_URL_ENV) else None

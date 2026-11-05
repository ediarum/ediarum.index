"""Shared fixtures: an in-memory SQLite DB, a TestClient wired to it, and the
caller the requests are made as.

Route/unit tests run against SQLite (StaticPool, so every connection shares the
one in-memory database). MySQL-specific behaviour (FK enforcement, JSON column,
utf8mb4) is *not* exercised here.

Auth: the ``client`` fixture replaces ``deps.current_caller`` with one that
returns ``callers.current`` (default: a platform admin) — but still applies
the project access check, so ``as_caller(...)`` exercises it. The real
platform-verify / API-key resolution is tested in ``test_auth.py``.
"""

import os

# real-deployment config that may leak in via the local .env must not change
# what the tests see: no platform, no verify endpoint
for var in ("AUTH_VERIFY_URL", "AUTH_DEV_USER", "PLATFORM_PROJECTS_URL", "PLATFORM_SERVICE_TOKEN",
            "DATABASE_URL", "XML_MOUNT_ROOT", "FILESERVICE_URL", "FILESERVICE_KEY"):
    os.environ.pop(var, None)

import pytest
from ediarum_sdk.auth import Caller, require_project_access
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from ediarum_index import deps, main
from ediarum_index.main import app, get_session
from ediarum_index.xmldiff import xml_diff as _xml_diff

TEST_EDITOR = "editor@example.org"
ADMIN = Caller(TEST_EDITOR, "user", True, ())


def user(*projects: str, name: str = "user@example.org") -> Caller:
    "A non-admin platform user with ``projects``."
    return Caller(name, "user", False, projects)


def key(*projects: str, name: str = "a-key", admin: bool = False) -> Caller:
    "An API-key caller; no ``projects`` = every project (``*``)."
    return Caller(name, "key", admin, projects or None)


class Callers:
    current: Caller = ADMIN


@pytest.fixture(name="xml_diff")
def xml_diff_fixture():
    """`xml_diff(a, b, subtree=None) -> str`: a unified diff of two XML docs that
    ignores whitespace, comments and processing instructions. '' == equivalent."""
    return _xml_diff


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        SQLModel.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(name="session")
def session_fixture(engine):
    """A bare DB session — tables exist; seeded once ``client`` has started."""
    with Session(engine) as session:
        yield session


@pytest.fixture(name="as_caller")
def as_caller_fixture():
    """``as_caller(caller)`` — make the following requests as ``caller``
    (see :func:`user` / :func:`key`); reset to the admin after the test."""
    def set_caller(caller: Caller) -> None:
        Callers.current = caller
    yield set_caller
    Callers.current = ADMIN


@pytest.fixture(name="client")
def client_fixture(engine):
    """A TestClient bound to the SQLite engine, calling as a platform admin
    (``TEST_EDITOR``).

    Entering the client context runs ``main.lifespan`` -> ``sync_registry``
    (no platform registry configured), so the ``project`` / ``entry_type``
    tables are seeded from the project modules before the first request.
    """

    def _get_session_override():
        with Session(engine) as session:
            yield session

    def _caller_override(request: Request) -> Caller:
        require_project_access(Callers.current, request.path_params.get("project"))
        return Callers.current

    original_engine = main.engine
    main.engine = engine
    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[deps.current_caller] = _caller_override
    try:
        with TestClient(app) as client:
            yield client
    finally:
        main.engine = original_engine
        app.dependency_overrides.clear()
        Callers.current = ADMIN

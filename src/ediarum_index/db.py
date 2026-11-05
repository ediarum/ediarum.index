"""Database engine and session factory.

The connection URL is ``DATABASE_URL`` (e.g.
``mysql+pymysql://user:pw@database:3306/index?charset=utf8mb4``). Without it,
the URL is assembled from the ``MYSQL_*`` keys of ``.env`` plus ``DB_HOST``
(default ``database``, the docker compose service name; set e.g.
``127.0.0.1`` to reach a dockerised DB from the host — the port must then be
published).

Migrations (``migrate.py``, ``migrations/env.py``) reuse ``DATABASE_URI``; the
app uses ``engine`` and ``get_session``.
"""

import os
from urllib.parse import quote_plus

from sqlmodel import Session, create_engine


def _url_from_parts() -> str:
    user = os.getenv("MYSQL_USER", "")
    password = quote_plus(os.getenv("MYSQL_PASSWORD", ""))
    name = os.getenv("MYSQL_DATABASE", "")
    host = os.getenv("DB_HOST", "database")
    return f"mysql+pymysql://{user}:{password}@{host}:3306/{name}?charset=utf8mb4"


DATABASE_URI = os.getenv("DATABASE_URL") or _url_from_parts()


def make_engine(url: str = DATABASE_URI):
    return create_engine(url, pool_pre_ping=url.startswith("mysql"))


engine = make_engine()


def get_session():
    """Yield a session bound to ``engine`` — a FastAPI dependency."""
    with Session(engine) as session:
        yield session

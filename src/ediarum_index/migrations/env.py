"""Alembic environment.

Two ways in:
- programmatically (``migrate.upgrade``, ``ediarum-index migrate``): a
  connection is passed in ``config.attributes["connection"]``;
- the ``alembic`` CLI with the repo's ``alembic.ini`` (writing new revisions):
  connects to ``db.DATABASE_URI``.
"""

from alembic import context
from sqlmodel import SQLModel

from ediarum_index import db, models  # noqa: F401 — models registers the tables on SQLModel.metadata

config = context.config
target_metadata = SQLModel.metadata


def configure(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)


def run_migrations_offline() -> None:
    context.configure(
        url=db.DATABASE_URI,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        configure(connection)
        with context.begin_transaction():
            context.run_migrations()
        return
    with db.make_engine(db.DATABASE_URI).connect() as connection:
        configure(connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

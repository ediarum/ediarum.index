"""Database schema migrations (Alembic), run programmatically.

``upgrade(engine)`` brings the database to the newest schema without losing data:

- **empty database** → all migrations run, creating the tables;
- **already migrated** → only pending migrations run; nothing happens at head;
- **tables but no migration history** → refused, never guessed at;
- **pending migrations on a database that holds tables** → a backup is
  written first (``backup``), and nothing is migrated if that fails.

MariaDB is backed up with ``mariadb-dump`` (gzipped SQL, one consistent
transaction) into ``BACKUP_DIR``; a SQLite file is copied next to itself.
Restoring is a plain ``gunzip -c <file> | mariadb <database>`` — see
docs/develop/migrations.md.

The migration scripts live in ``migrations/`` inside the package, so they ship
with the installed package (and the Docker image). ``alembic.ini`` at the repo
root points there too, for ``uv run alembic revision --autogenerate``.
"""

import gzip
import os
import shutil
import sqlite3
import subprocess
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
VERSION_TABLE = "alembic_version"
BACKUP_DIR_ENV = "BACKUP_DIR"


class SchemaError(RuntimeError):
    pass


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_sqlite(engine, label: str) -> Path | None:
    "Consistent copy of a SQLite file (sqlite3 backup API); None for an in-memory database."
    database = engine.url.database
    if database in (None, "", ":memory:"):
        return None
    path = Path(database)
    if not path.exists():
        return None
    target = path.with_name(f"{path.name}.{_stamp()}.before-{label}.bak")
    with closing(sqlite3.connect(path)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    return target


# DATABASE_URL query options (PyMySQL's TLS settings) → the dump client's
TLS_OPTIONS = {"ssl_ca": "--ssl-ca", "ssl_cert": "--ssl-cert", "ssl_key": "--ssl-key"}


def dump_command(url, dump: str = "mariadb-dump") -> list[str]:
    """The ``mariadb-dump`` call for the database at ``url`` (a SQLAlchemy URL).

    - One consistent snapshot (``--single-transaction``) of tables and
      triggers. No ``--routines``: the app has no stored routines, and hosted
      accounts often lack the privilege to dump them.
    - TLS as the app connects: the URL's ``ssl_ca`` / ``ssl_cert`` /
      ``ssl_key`` (what PyMySQL reads) become the client's options, with the
      server certificate verified — a hosted server that requires TLS would
      refuse the dump otherwise. ``ssl_verify_cert=false`` in the URL turns
      the verification off for both.
    - The password goes in the environment (``MYSQL_PWD``), not the command line.
    """
    cmd = [dump, "--single-transaction", "--triggers", "--default-character-set=utf8mb4",
           "-h", url.host or "localhost", "-P", str(url.port or 3306), "-u", url.username or ""]
    query = dict(url.query)
    tls = [f"{flag}={query[key]}" for key, flag in TLS_OPTIONS.items() if query.get(key)]
    if tls:
        cmd += ["--ssl", *tls]
        verify = str(query.get("ssl_verify_cert", "true")).lower() not in ("false", "0", "no")
        cmd.append("--ssl-verify-server-cert" if verify else "--skip-ssl-verify-server-cert")
    return [*cmd, url.database]


def backup_mariadb(engine, label: str, directory: Path) -> Path:
    "``mariadb-dump`` of the whole database (``dump_command``), gzipped, into ``directory``."
    dump = shutil.which("mariadb-dump") or shutil.which("mysqldump")
    if dump is None:
        raise SchemaError("mariadb-dump (or mysqldump) not found — install the MariaDB client to back up")
    url = engine.url
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{url.database}-{_stamp()}-before-{label}.sql.gz"
    cmd = dump_command(url, dump)
    env = {**os.environ, "MYSQL_PWD": url.password or ""}
    try:
        with tempfile.TemporaryFile() as errors, gzip.open(target, "wb") as out:
            with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors, env=env) as proc:
                shutil.copyfileobj(proc.stdout, out, 1 << 20)  # streamed: no whole dump in memory
            written = out.tell()
            errors.seek(0)
            message = errors.read().decode(errors="replace").strip()
        if proc.returncode != 0 or not written:
            raise SchemaError(f"backup failed: {message or 'empty dump'}")
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target


def backup(engine, label: str = "manual") -> Path | None:
    """Back up the database behind ``engine``; the file written, or None for a
    database there is nothing to back up from (in-memory SQLite). Raises
    ``SchemaError`` if it can't."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        return backup_sqlite(engine, label)
    if dialect in ("mysql", "mariadb"):
        directory = os.getenv(BACKUP_DIR_ENV)
        if not directory:
            raise SchemaError(f"set {BACKUP_DIR_ENV} for the backup before migrating "
                              "(or migrate without one: --no-backup)")
        return backup_mariadb(engine, label, Path(directory))
    raise SchemaError(f"no backup for a {dialect} database — back it up by hand, then use --no-backup")


def upgrade(engine, log=print, make_backup: bool = True) -> None:
    "Bring the database behind ``engine`` to the newest schema (see module docstring)."
    head = head_revision()
    with engine.connect() as conn:
        tables = set(inspect(conn).get_table_names())
        current = current_revision(conn)
    if tables - {VERSION_TABLE} and current is None:
        raise SchemaError("The database has tables but no migration history, so its schema is unknown. "
                          "Back it up and migrate it by hand, or start from an empty database.")
    if current == head:
        return
    if tables - {VERSION_TABLE} and make_backup:
        if path := backup(engine, head):
            log(f"backup before migrating {current} -> {head}: {path}")
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    log(f"database migrated {current or 'empty'} -> {head}")

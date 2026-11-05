"""migrate.upgrade: the baseline on an empty database, the refusals, and the
backup before pending migrations."""

import pytest
from sqlalchemy import create_engine, inspect, text

from ediarum_index import migrate


@pytest.fixture
def sqlite_file(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'index.db'}")
    yield engine
    engine.dispose()


def test_empty_database_gets_the_whole_schema_without_a_backup(sqlite_file, tmp_path):
    messages = []
    migrate.upgrade(sqlite_file, log=messages.append)
    with sqlite_file.connect() as conn:
        assert migrate.current_revision(conn) == migrate.head_revision()
        assert {"entry", "project", "sdk_api_key", "source_state", "file_notice"} <= set(inspect(conn).get_table_names())
    assert messages == [f"database migrated empty -> {migrate.head_revision()}"]
    assert not list(tmp_path.glob("*.bak"))


def test_at_head_nothing_happens(sqlite_file):
    migrate.upgrade(sqlite_file)
    messages = []
    migrate.upgrade(sqlite_file, log=messages.append)
    assert messages == []


def test_tables_without_history_are_refused(sqlite_file):
    with sqlite_file.begin() as conn:
        conn.execute(text("CREATE TABLE entry (id INTEGER PRIMARY KEY)"))
    with pytest.raises(migrate.SchemaError, match="no migration history"):
        migrate.upgrade(sqlite_file)


def test_pending_migrations_on_data_are_backed_up_first(sqlite_file, tmp_path, monkeypatch):
    migrate.upgrade(sqlite_file)
    head = migrate.head_revision()
    # pretend the code moved on: the database is one revision behind
    monkeypatch.setattr(migrate, "head_revision", lambda: "9999")
    monkeypatch.setattr(migrate.command, "upgrade", lambda cfg, rev: None)
    messages = []
    migrate.upgrade(sqlite_file, log=messages.append)
    backups = list(tmp_path.glob("index.db.*.before-9999.bak"))
    assert len(backups) == 1
    assert messages[0].startswith(f"backup before migrating {head} -> 9999")


def test_no_backup_no_migration(sqlite_file, monkeypatch):
    migrate.upgrade(sqlite_file)
    monkeypatch.setattr(migrate, "head_revision", lambda: "9999")
    ran = []
    monkeypatch.setattr(migrate.command, "upgrade", lambda cfg, rev: ran.append(rev))

    def failing(engine, label):
        raise migrate.SchemaError("disk full")

    monkeypatch.setattr(migrate, "backup", failing)
    with pytest.raises(migrate.SchemaError, match="disk full"):
        migrate.upgrade(sqlite_file)
    assert ran == []
    migrate.upgrade(sqlite_file, make_backup=False)  # an explicit choice
    assert ran == ["head"]


def test_mariadb_backup_needs_a_backup_dir(monkeypatch):
    monkeypatch.delenv("BACKUP_DIR", raising=False)
    engine = create_engine("mysql+pymysql://u:p@db.invalid/index")
    with pytest.raises(migrate.SchemaError, match="BACKUP_DIR"):
        migrate.backup(engine)


def test_mariadb_backup_failure_leaves_no_file(monkeypatch, tmp_path):
    """A dump that fails (here: the client can't connect) must not leave a
    file that looks like a backup."""
    import shutil

    if not (shutil.which("mariadb-dump") or shutil.which("mysqldump")):
        pytest.skip("no MariaDB client installed")
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    engine = create_engine("mysql+pymysql://u:p@127.0.0.1:1/index")
    with pytest.raises(migrate.SchemaError, match="backup failed"):
        migrate.backup(engine)
    assert list(tmp_path.iterdir()) == []


def test_dump_command_plain():
    from sqlalchemy.engine import make_url

    cmd = migrate.dump_command(make_url("mysql+pymysql://index:pw@db.example.org:3307/ediarum_index?charset=utf8mb4"))
    assert cmd[:4] == ["mariadb-dump", "--single-transaction", "--triggers", "--default-character-set=utf8mb4"]
    assert "--routines" not in cmd  # hosted accounts often may not dump routines
    assert cmd[cmd.index("-h") + 1] == "db.example.org" and cmd[cmd.index("-P") + 1] == "3307"
    assert cmd[-1] == "ediarum_index"
    assert "pw" not in " ".join(cmd)  # the password goes in MYSQL_PWD
    assert not any(c.startswith("--ssl") for c in cmd)


def test_dump_command_uses_the_urls_tls():
    """A hosted server that requires TLS: the dump connects as the app does."""
    from sqlalchemy.engine import make_url

    url = make_url("mysql+pymysql://index:pw@db.example.org/ix?ssl_ca=/certs/ca.pem&ssl_cert=/c.pem&ssl_key=/k.pem")
    cmd = migrate.dump_command(url)
    assert {"--ssl", "--ssl-ca=/certs/ca.pem", "--ssl-cert=/c.pem", "--ssl-key=/k.pem",
            "--ssl-verify-server-cert"} <= set(cmd)
    insecure = migrate.dump_command(make_url("mysql+pymysql://i:p@h/ix?ssl_ca=/ca.pem&ssl_verify_cert=false"))
    assert "--skip-ssl-verify-server-cert" in insecure


def test_0002_drops_avhrs_internal_id(sqlite_file):
    from alembic import command

    cfg = migrate.alembic_config()
    with sqlite_file.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "0001")
        conn.execute(text("INSERT INTO entry_type (name, label) VALUES ('person', 'Person')"))
        conn.execute(text("INSERT INTO project (name, label, is_active, created_at) VALUES ('avhr', 'avhr', 1, '2026-01-01'), ('mega', 'mega', 1, '2026-01-01')"))
        for project in ("avhr", "mega"):
            conn.execute(
                text("INSERT INTO entry (project_name, entry_type, label, source_id, data, created_at, updated_at) "
                     "VALUES (:p, 'person', 'X', 'H1', :d, '2026-01-01', '2026-01-01')"),
                {"p": project, "d": '{"internal_id": "H1", "surname": "X"}'},
            )
        command.upgrade(cfg, "0002")
        rows = dict(conn.execute(text("SELECT project_name, data FROM entry")).all())
    assert rows["avhr"] == '{"surname":"X"}'
    assert "internal_id" in rows["mega"]  # MEGA's own field stays

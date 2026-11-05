"""Command line: ``ediarum-index serve | migrate | keys … | ids … | watch | scan | ingest | roundtrip-report``.

``ingest`` and ``roundtrip-report`` hand their arguments to the module of the
same job, which has its own parser (``ediarum-index ingest -h``).
"""

import argparse
import importlib
import os
import sys

# subcommand -> module whose main() parses the remaining arguments itself
DELEGATED = {
    "ingest": ("ingest", "load TEI registers into the database"),
    "roundtrip-report": ("roundtrip_report", "diff source XML against its rebuilt export"),
}


def _migrate(make_backup: bool = True, log=print) -> None:
    from . import migrate
    from .db import engine

    try:
        migrate.upgrade(engine, log=log, make_backup=make_backup)
    except migrate.SchemaError as exc:
        sys.exit(str(exc))


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else None
    if command in DELEGATED:
        module = importlib.import_module(f"{__package__}.{DELEGATED[command][0]}")
        sys.argv = [f"ediarum-index {command}", *sys.argv[2:]]
        module.main()
        return

    parser = argparse.ArgumentParser(prog="ediarum-index")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="migrate the database, then run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--root-path", default=os.getenv("ROOT_PATH", ""),
                       help="path prefix a reverse proxy strips, e.g. /api/index (default: $ROOT_PATH)")
    serve.add_argument("--no-migrate", action="store_true", help="don't apply pending migrations first")
    serve.add_argument("--no-backup", action="store_true", help="migrate without the backup first")

    migrate_cmd = commands.add_parser("migrate", help="database schema migrations")
    migrate_cmd.add_argument("--check", action="store_true",
                             help="only show the database's revision and the newest one; exit 1 if behind")
    migrate_cmd.add_argument("--backup", action="store_true", help="only write a backup ($BACKUP_DIR)")
    migrate_cmd.add_argument("--no-backup", action="store_true",
                             help="apply pending migrations without the backup first")

    keys = commands.add_parser("keys", help="API keys for clients without a platform session").add_subparsers(
        dest="action", required=True)
    add = keys.add_parser("add", help="create a client and print its key (shown only this once)")
    add.add_argument("name")
    add.add_argument("--projects", default="*", help="comma-separated project slugs (default: all)")
    add.add_argument("--admin", action="store_true")
    keys.add_parser("list", help="list clients")
    revoke = keys.add_parser("revoke", help="deactivate a client for good")
    revoke.add_argument("name")

    ids = commands.add_parser("ids", help="source_ids from ediarum.id ($ID_URL, $ID_KEY)").add_subparsers(
        dest="action", required=True)
    backfill = ids.add_parser("backfill", help="give every entry without a source_id one from ediarum.id")
    backfill.add_argument("--project", help="only this project")
    backfill.add_argument("--dry-run", action="store_true", help="only list the entries")

    from .watch import DEFAULT_FULL_EVERY, DEFAULT_INTERVAL

    watch = commands.add_parser("watch", help="ingest a project whenever its XML on the shared volume changes")
    watch.add_argument("--project", action="append", help="watch only this project (repeatable)")
    watch.add_argument("--interval", type=float, default=float(os.getenv("RECONCILE_INTERVAL", DEFAULT_INTERVAL)),
                       help="seconds between checks of a project (default: $RECONCILE_INTERVAL or 300)")
    watch.add_argument("--full-every", type=float, default=DEFAULT_FULL_EVERY,
                       help="check the files at least this often, even if fileservice reports no change")
    scan = commands.add_parser("scan", help="check every project's XML once, as the watcher does, then exit")
    scan.add_argument("--project", action="append", help="only this project (repeatable)")
    scan.add_argument("--force", action="store_true", help="ingest even if the sources didn't change")

    for name, (_module, help_text) in DELEGATED.items():
        commands.add_parser(name, help=f"{help_text} (see: ediarum-index {name} -h)")

    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn

        if not args.no_migrate:
            _migrate(make_backup=not args.no_backup)
        uvicorn.run("ediarum_index.main:app", host=args.host, port=args.port, reload=args.reload,
                    root_path=args.root_path)
        return

    if args.command == "migrate":
        from . import migrate
        from .db import engine

        if args.check:
            with engine.connect() as conn:
                current = migrate.current_revision(conn)
            head = migrate.head_revision()
            print(f"database: {current or 'none'}   newest: {head}")
            if current != head:
                sys.exit(1)
            return
        if args.backup:
            try:
                print(migrate.backup(engine))
            except migrate.SchemaError as exc:
                sys.exit(str(exc))
            return
        _migrate(make_backup=not args.no_backup)
        print(f"database at {migrate.head_revision()}")
        return

    if args.command == "ids":  # backfill
        from sqlmodel import Session

        from .db import engine
        from .idservice import IdService, IdServiceUnavailable, backfill

        service = IdService.from_env()
        if service is None and not args.dry_run:
            sys.exit("set ID_URL (and ID_KEY): ediarum.id's API")
        with Session(engine) as session:
            try:
                done = backfill(session, service, args.project, args.dry_run)
            except IdServiceUnavailable as exc:
                sys.exit(exc.detail)
            for entry, new in done:
                print(f"{entry.project_name}\t{entry.id}\t{new or '-'}\t{entry.label}")
        print(f"{len(done)} entries {'without a source_id' if args.dry_run else 'got a source_id'}",
              file=sys.stderr)
        return

    if args.command in ("watch", "scan"):
        from sqlmodel import Session

        from .bootstrap import sync_registry
        from .db import engine
        from .watch import FileserviceStatus, Watcher, registry_from_env

        if args.command == "watch":
            Watcher(engine, registry_from_env(), FileserviceStatus.from_env(), args.project,
                    args.interval, args.full_every).run_forever()
            return
        watcher = Watcher(engine, registry_from_env(), only=args.project)
        with Session(engine) as session:
            sync_registry(session, watcher.registry)
        if not all([watcher.check(p, force=args.force) for p in watcher.projects()]):
            sys.exit(1)
        return

    if args.command == "keys":
        from ediarum_sdk.auth import ApiKey, create_key
        from sqlmodel import Session, select

        from .db import engine

        with Session(engine) as session:
            if args.action == "add":
                if session.get(ApiKey, args.name) is not None:
                    sys.exit(f"a key named {args.name} already exists")
                print(create_key(session, args.name, args.projects, is_admin=args.admin, created_by="cli"))
            elif args.action == "list":
                for row in session.exec(select(ApiKey).order_by(ApiKey.name)).all():
                    flags = " ".join(f for f, on in (("admin", row.is_admin), ("revoked", not row.is_active)) if on)
                    print(f"{row.name:<32}{row.projects:<40}{flags}")
            else:
                row = session.get(ApiKey, args.name)
                if row is None:
                    sys.exit(f"unknown key {args.name}")
                row.is_active = False
                session.add(row)
                session.commit()

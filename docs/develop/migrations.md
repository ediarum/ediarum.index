# Changing the database schema

The database holds data that exists nowhere else (curators' edits,
comments, API keys). An upgrade must never lose it. The history starts
at one baseline, `0001` (`src/ediarum_index/migrations/versions/`).

1. Edit `src/ediarum_index/models.py`, then, against a MariaDB at the current
   head: `uv run alembic revision --autogenerate -m "…"`. **Review the file**:
   autogenerate can't tell a rename from a drop + add, and never writes data
   moves.
2. **Additive or expand/contract only.**
   - Adding a table, a nullable column, a column with a server default, or an
     index is fine.
   - A rename, a type change or a split is three steps: add the new shape and
     copy the data in the migration (hand-written `op.execute` / batch
     updates); switch the code; drop the old shape **one release later** —
     never in the release that stops using it.
   - Never drop a table or column that still holds data the new code doesn't
     carry over.
3. `uv run ediarum-index migrate`, then `uv run alembic check` (no drift).
4. `scripts/migration-test.sh` (CI's `migration-test`): the previous
   release migrates an empty MariaDB and ingests the fixtures in
   `tests/data/xml`; your code upgrades it and must lose no rows.

How an upgrade runs in production: `ediarum-index serve` (the backend
container) applies pending migrations before the API starts. If any are
pending on a database that holds tables, it first writes a `mariadb-dump`
backup (gzipped, one consistent transaction) to `BACKUP_DIR` (`/backups`, the
`db_backups` volume in compose) — and migrates nothing if that fails.
`ediarum-index migrate --check` shows what is pending (exit 1 if anything is)
— run it before a deploy. `ediarum-index migrate --backup` writes a backup on
demand.

**Restore** a backup (stop the api and watcher first):

```bash
docker compose stop api watcher
docker compose exec database sh -c \
    'mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE \`$MYSQL_DATABASE\`; CREATE DATABASE \`$MYSQL_DATABASE\`"'
docker compose run --rm --entrypoint sh api -c \
    'gunzip -c /backups/<file>.sql.gz | mariadb -h database -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"'
```

That is the local setup (`docker-compose.dev.yml`'s `database` container).
Against the **hosted** database, empty the database the provider's way, then
load the dump from the api container, connecting as the app does:

```bash
docker compose run --rm --entrypoint sh api -c \
    'gunzip -c /backups/<file>.sql.gz | mariadb -h <host> -P <port> -u <user> -p --ssl-ca=/certs/ca.pem <database>'
```

…then deploy the release that matches the backup's revision (its file name
says which: `…-before-<new revision>.sql.gz` was taken at the revision before).

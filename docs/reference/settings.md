# Settings

From the environment; `.env` (git-ignored, see `.env.example`) feeds both
compose files.

| Setting | Used by | Meaning |
|---|---|---|
| `DATABASE_URL` | api, watcher, CLI | `mysql+pymysql://user:pw@host:3306/db?charset=utf8mb4`, TLS via `&ssl_ca=/certs/ca.pem` (plus `ssl_cert` / `ssl_key`). Required in `docker-compose.yml` |
| `MYSQL_USER` · `MYSQL_PASSWORD` · `MYSQL_DATABASE` · `DB_HOST` | api, watcher, CLI | instead of `DATABASE_URL`: the URL is assembled in `db.py` (`DB_HOST` default `database`); also create the dev MariaDB container |
| `BACKUP_DIR` | api, CLI | where the `mariadb-dump` before pending migrations goes (compose: `/backups`, volume `db_backups`) |
| `AUTH_VERIFY_URL` | api | the platform's auth verify endpoint, as reachable from the container. Required in `docker-compose.yml` |
| `AUTH_DEV_USER` | api | local development only: every request is this admin user |
| `PLATFORM_PROJECTS_URL` · `PLATFORM_SERVICE_TOKEN` | api, watcher | the platform's project registry, mirrored into `project`. Unset: the modules in `src/ediarum_index/projects/` are the list |
| `ROOT_PATH` | api | the prefix the proxy strips (`/api/index`), for `/docs` |
| `XML_MOUNT_ROOT` | watcher, ingest | the shared XML volume, one checkout per project slug (compose: `/data/xml`) |
| `ID_URL` · `ID_KEY` | api, CLI | ediarum.id's API and a key valid for the projects (`ediarum-id keys add index --admin`): the `source_id` of entries created in the app. Unset: they get none |
| `FILESERVICE_URL` · `FILESERVICE_KEY` | watcher | optional: fileservice's per-project status lets the watcher skip unchanged projects |
| `RECONCILE_INTERVAL` | watcher | seconds between the watcher's checks (default 300) |
| `INDEX_PROJECT` | ingest | `ediarum-index ingest`'s default profile |

Compose only: `PLATFORM_NETWORK` (the platform's Docker network),
`XML_VOLUME` (fileservice's volume), `DB_CERTS_DIR` (mounted at `/certs`,
default `./certs`), `INDEX_VERSION` / `INDEX_IMAGE` (the images; default
`latest`). Dev overlay only: `MARIADB_VERSION`, `DEV_DB_PORT` (3306),
`DEV_API_PORT` (8004), `DEV_XML_DIR` (`./xml`).

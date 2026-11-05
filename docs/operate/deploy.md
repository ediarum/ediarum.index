# Deploy

1. **Prerequisites** on the platform's host: Docker Compose, the platform's
   Docker network, its auth `verify` endpoint, and ediarum.fileservice running
   with its XML volume (`/data/xml/<slug>`).
2. **Database** (hosted MariaDB, external to compose):
   - an **empty database** with `utf8mb4` — the app creates the tables, never
     the database;
   - **one account** with `SELECT, INSERT, UPDATE, DELETE` (operation),
     `CREATE, ALTER, DROP, INDEX, REFERENCES` (migrations) and
     `SHOW VIEW, TRIGGER` (the backup's `mariadb-dump`);
   - **network access** from the deploy host;
   - **TLS** if the server requires it: `?ssl_ca=/certs/ca.pem` (plus
     `ssl_cert` / `ssl_key`) in `DATABASE_URL`, the files in `DB_CERTS_DIR`.
     The app and `mariadb-dump` both verify the server's certificate.
3. **Configure:** `cp .env.example .env`; set `DATABASE_URL`,
   `AUTH_VERIFY_URL`, `PLATFORM_NETWORK`, `XML_VOLUME` (required),
   `PLATFORM_PROJECTS_URL` / `PLATFORM_SERVICE_TOKEN`,
   `FILESERVICE_URL` / `FILESERVICE_KEY`, `ID_URL` / `ID_KEY` (an ediarum.id
   admin key: `ediarum-id keys add index --admin`) (recommended),
   `INDEX_VERSION`. All
   settings: [Settings](../reference/settings.md).
4. **Wire up the platform:** reverse proxy and portal `apps.json`:
   ```nginx
   location /api/index/  { proxy_pass http://ediarum-index-api:8000/; }
   location /apps/index/ { proxy_pass http://ediarum-index-frontend/; }
   ```
   ```json
   { "id": "index", "label": "Index", "entry": "/apps/index/embed.js", "apiBase": "/api/index", "roles": [] }
   ```
5. **Start:** `docker compose pull && docker compose up -d`. The `api`
   migrates the database on start; the `watcher` waits for it, then ingests
   every `xml`-led project (first start) — `docker compose logs -f watcher`.
   With no `xml`-led project (all `app`-led, or none registered yet) it idles
   and picks a project up once the registry lists one.
6. **Connect webdav:** create a key for webdav
   (`docker compose exec api ediarum-index keys add webdav --projects <slug>,…`,
   printed once) and add `http://ediarum-index-api:8000/files` with it to
   webdav's file-change targets.
7. **Check:** `docker compose ps` shows `api` healthy; the portal's "Index"
   shows the projects' entries; a save in oXygen appears as a `POST /files`
   in the api log and is ingested shortly after.

**Update:** `docker compose exec api ediarum-index migrate --check` shows
what the new version would migrate (exit 1 if anything is pending); then set
`INDEX_VERSION`, `docker compose pull && docker compose up -d`. Pending
migrations run on start, after a `mariadb-dump` into `BACKUP_DIR` (`/backups`,
volume `db_backups`) — a safety net for the upgrade, not a replacement for the
provider's backups. Restore: [Changing the database schema](../develop/migrations.md).

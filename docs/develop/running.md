# Running it

## With docker (MariaDB, api, watcher)

`.env` (git-ignored, see `.env.example`) supplies the values. The
`docker-compose.dev.yml` overlay adds a MariaDB container (from the `MYSQL_*`
keys), runs the api on the host's network at `localhost:8004` against the
platform's mock login, the watcher on `./xml`, and the bundle at
`localhost:8081`:

```bash
docker compose -p ediarum-index-dev -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# DEV_DB_PORT / DEV_API_PORT / DEV_XML_DIR move the database port, api port, XML folder
```

The data lives in that compose project's `mariadb_data` volume: `down` keeps
it, `down -v` wipes it (the next `up` migrates again and the watcher ingests
every project). Without `AUTH_VERIFY_URL` / `AUTH_DEV_USER` only API keys are
accepted; without `PLATFORM_PROJECTS_URL` the project modules are the project
list.

Backend only, against a reachable MariaDB (`DATABASE_URL` exported, or the
`MYSQL_*` keys with `DB_HOST`):

```bash
AUTH_DEV_USER=you@example.org uv run ediarum-index serve --reload   # migrates first
```

## Inside the platform

The UI only runs inside ediarum.platform. Locally the platform's dev server
hosts it with a mock login (ediarum-platform `docs/integrating-an-app.md`,
"Local development"), with both repositories side by side:

```bash
# 1. the backend, checking requests against the platform's mock auth
AUTH_VERIFY_URL=http://localhost:5173/api/auth/verify uv run ediarum-index serve --port 8004

# 2. the frontend bundle (or `npm run dev` for hot reload: then
#    EDIARUM_DEV_BUNDLES=index=http://localhost:5174 below)
cd frontend && npm run build:watch

# 3. the platform, pointed at both
cd ../ediarum-platform && \
  EDIARUM_DEV_BACKENDS=index=http://localhost:8004 \
  EDIARUM_DEV_BUNDLES=index=../ediarum.index/frontend/dist \
  EDIARUM_APPS_JSON=../ediarum.index/dev/platform-apps.json \
  npm run dev -- --strictPort
```

Open `http://localhost:5173/index/` and log in as `ada@example.org` (member
of `schleiermacher`) or `admin@example.org`, password `password`.

# Command line

`ediarum-index` (installed with the package; in the repo
`uv run ediarum-index …`, in a container
`docker compose exec api ediarum-index …`):

| Command | Does |
|---|---|
| `serve [--host --port --reload --root-path --no-migrate]` | apply pending migrations, then run the API (uvicorn) |
| `migrate [--check] [--backup] [--no-backup]` | apply pending migrations (after a backup into `BACKUP_DIR` if the database holds data); `--check` only compares the revision with the newest (exit 1 if behind); `--backup` only writes a backup |
| `keys add <name> [--projects a,b] [--admin]` · `keys list` · `keys revoke <name>` | API keys for clients without a platform session; `add` prints the key once |
| `ids backfill [--project P] [--dry-run]` | give every entry without a `source_id` one from ediarum.id (`ID_URL`, `ID_KEY`); prints project, entry id, new id, label per entry |
| `ingest …` | TEI XML → database loader (`ediarum-index ingest -h`, [Ingest](../ingest/index.md)) |
| `roundtrip-report …` | ingest → export → diff report (`ediarum-index roundtrip-report -h`) |
| `watch [--project P] [--interval S]` | the watcher service: ingest a project whenever its XML on the shared volume changes (and, on first start, every project) |
| `scan [--project P] [--force]` | one pass of the watcher's check, then exit |

# Operating

```bash
docker compose ps                                    # api healthy, watcher running
docker compose logs -f api watcher                   # requests, ingests, warnings
docker compose exec api ediarum-index migrate --backup   # manual backup into /backups
docker compose exec api ediarum-index scan --project <slug> --force   # re-ingest now
docker compose down                                  # stop; the database is external
```

`docker compose down -v` deletes the `db_backups` volume (the pre-migration
backups).

## API keys

Portal users need nothing extra. ediarum/oXygen, scripts and ediarum.webdav
authenticate with a key (`Authorization: Bearer`, `X-API-Key` or `?key=`),
limited to its projects:

- platform admins: `POST /keys` (shown once), `POST /keys/{name}/revoke`;
- on the server: `docker compose exec api ediarum-index keys add|list|revoke`
  (also admin keys for all projects: `--admin`).

## oXygen reference picker

```
https://platform.ediarum.de/api/index/<slug>/entries/options?entry_type=person&format=ul&key=<key>
```

returns `<ul><li xml:id="…"><span>Label (birth-death)</span></li>…</ul>`.

# Python API

Generated from the docstrings of the `ediarum_index` package — the code's own
account of what each module and function does. Private helpers (`_name`) are
included: much of the ingest and export logic lives there.

| Page | Modules | |
|---|---|---|
| [Web app](app.md) | `main`, `deps`, `routes`, `routes.projects`, `routes.schema`, `routes.entries`, `routes.relations`, `routes.comments`, `routes.export`, `routes.files`, `routes.keys`, `routes.ingest_runs` | The FastAPI app, its shared dependencies and the routers (one module per resource). |
| [Services](services.md) | `services` | Every write, shared by the routes and the ingest. |
| [Models](models.md) | `models` | Tables, I/O models and the schema types. |
| [Schema layer](schemas.md) | `schemas`, `projects` | Base field lists, per-project overrides, validation. |
| [Ingest](ingest.md) | `ingest` | TEI XML → database. |
| [Export](export.md) | `export` | Database → TEI XML. |
| [Round-trip check](roundtrip.md) | `xmldiff`, `roundtrip_report` | The diff behind the round-trip tests and report. |
| [Watcher and sources](watch.md) | `watch`, `sources` | Where a project's XML is, and ingesting it when it changes. |
| [ediarum.id](idservice.md) | `idservice` | `source_id`s for entries created in the app. |
| [Database](database.md) | `db`, `migrate`, `bootstrap` | Engine, migrations and the lookup-table bootstrap. |
| [Dates](dates.md) | `dates` | Sort keys for uncertain dates. |
| [Command line](cli.md) | `cli` | The `ediarum-index` entry point. |

# Contributing

The contributor documentation is in [`docs/develop/`](docs/develop/index.md):

- [The shape of the system and the backend layout](docs/develop/index.md)
- [Running it locally](docs/develop/running.md) — with docker, or inside the platform's dev server
- [Tests](docs/develop/tests.md) — and what to check before opening a merge request
- [Adding things](docs/develop/adding-things.md) — a field, project, register, route, view
- [Changing the database schema](docs/develop/migrations.md)
- [Release](docs/develop/release.md)

Before a merge request: `make test`, `cd frontend && npm run lint && npm run type-check`,
and `uv run --group docs mkdocs build` if you touched the docs or docstrings.

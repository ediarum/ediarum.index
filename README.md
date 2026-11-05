<a href="https://www.ediarum.org"><img src="docs/assets/ediarum-logo.png" alt="ediarum" width="236"></a>

# ediarum.index

[![Documentation](https://github.com/ediarum/ediarum.index/actions/workflows/docs.yml/badge.svg)](https://ediarum.github.io/ediarum.index/)

Version: 0.2.0

© 2026 by Berlin-Brandenburg Academy of Sciences and Humanities

Part of ediarum (https://www.ediarum.org, ediarum@bbaw.de)

Developed by TELOTA (https://www.bbaw.de/telota, telota@bbaw.de), a DH
working group of the Berlin-Brandenburg Academy of Sciences and Humanities.

Developers of ediarum.index:

* Marcus Lampert
* Felix Schenke
* Malte Vogl

The authority registers of the BBAW editions, running as an app of
**ediarum.platform**: **entries** (persons, places, groups, organisations,
works, bible books, glossary entries) per project, stored in MariaDB, browsed
and edited in a Vue UI, ingested from and exported back to the projects' TEI
XML registers.

**Where the data lives depends on the project.** The platform registry marks
each project `xml`- or `app`-led. For an `xml`-led project the TEI files stay
the ground truth: every save in ediarum.webdav is posted here, and a watcher
ingests the changed registers from the platform's shared XML volume
(read-only). For an `app`-led project the entries are kept here. Either way
`GET /{project}/export/{entry_type}` rebuilds the register XML.

## Documentation

The full documentation is in [`docs/`](docs/index.md), published as a site at
https://ediarum.github.io/ediarum.index/ (from each release). Build it locally with
`uv run --group docs mkdocs serve`.

| | |
|---|---|
| [Deploy](docs/operate/deploy.md) · [Operating](docs/operate/operating.md) · [Projects](docs/operate/projects.md) | running it on the platform |
| [Develop](docs/develop/index.md) · [Running locally](docs/develop/running.md) · [Tests](docs/develop/tests.md) · [Migrations](docs/develop/migrations.md) · [Release](docs/develop/release.md) | working on the code |
| [Schema design](docs/concepts/schema.md) · [UI design](docs/concepts/ui-design.md) | why it works this way |
| [Ingest & export](docs/ingest/index.md) | how a register gets in and out, per project |
| [Reference](docs/reference/routes.md) | routes, auth, CLI, settings, data model |
| [Python API](docs/api/index.md) | generated from the docstrings (site only) |

## Quick start

```bash
cp .env.example .env                      # DATABASE_URL, AUTH_VERIFY_URL, PLATFORM_NETWORK, XML_VOLUME, …
docker compose pull && docker compose up -d
```

Local development with a MariaDB container and the platform's mock login:
[docs/develop/running.md](docs/develop/running.md).

## License

ediarum.index is free software: you can redistribute it and/or modify it
under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or (at your
option) any later version. See [LICENSE](LICENSE).

Not covered by this license:

- **Logos** (`docs/assets/bbaw-logo-*.png`, `docs/assets/ediarum-logo.png`)
  are marks of the Berlin-Brandenburg Academy of Sciences and Humanities, all
  rights reserved. Forks must not use them to suggest endorsement.
- **Fonts** (`docs/assets/fonts/noto-sans-*.woff2`): Noto Sans, SIL Open
  Font License 1.1, see [docs/assets/fonts/OFL.txt](docs/assets/fonts/OFL.txt).

Third-party dependencies keep their own licenses (MIT, BSD, Apache-2.0,
MPL-2.0, …), all compatible with the AGPL-3.0.

## Cite this software

If you use this software, please cite it using the metadata in the file
[CITATION.cff](CITATION.cff) (for more information about CFF see
https://citation-file-format.github.io/).

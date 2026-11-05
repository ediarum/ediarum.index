# Documentation

The site is [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/)
over the Markdown in `docs/`, configured in `mkdocs.yml`. The public site,
https://ediarum.github.io/ediarum.index/, is built by
`.github/workflows/docs.yml` on the GitHub mirror, so it shows the latest
release. The `pages` CI job publishes the current `main` to GitLab Pages as
an internal preview.

```bash
uv run --group docs mkdocs serve    # http://127.0.0.1:8000, rebuilds on save
uv run --group docs mkdocs build    # strict: fails on a broken link or anchor
```

- **One source.** Every page lives in `docs/`; `README.md`, `CONTRIBUTING.md`
  and the READMEs in `frontend/` and `src/ediarum_index/projects/` only point
  here. The pages are plain Markdown, so they read on GitLab too.
- **Navigation** is the `nav` in `mkdocs.yml`: a new page needs an entry there.
- **Links** between pages are relative (`../reference/settings.md#…`), so they
  work on the site and on GitLab. Link to code by its path in backticks, not a
  file link — files outside `docs/` aren't part of the site.
- **Look** follows [ediarum.org](https://www.ediarum.org): the colours and
  self-hosted Noto Sans are in `docs/stylesheets/ediarum.css`, and the footer
  (Über ediarum, Herausgeber, BBAW logo, Impressum & Datenschutz) is
  `docs/overrides/partials/copyright.html`. Logos and fonts are in `docs/assets/`.
- **Diagrams** are Mermaid (` ```mermaid `), which GitLab renders too.
- **Python API** pages (`docs/api/`) are generated from the docstrings by
  [mkdocstrings](https://mkdocstrings.github.io/): each page is a list of
  `::: ediarum_index.<module>` directives. Docstrings use the Google style for
  `Args:` / `Returns:`; types come from the signature.

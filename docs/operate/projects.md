# Projects

A project exists in the platform registry; this app mirrors it into its
`project` table on every start (and on the first request for an unknown slug).
A project removed from the registry is deactivated, its entries stay.

Code is needed only for what the platform doesn't know: schema overrides and,
for an `xml`-led project, where its registers are and how to read them.

```bash
scripts/add_project.sh <slug> [--register-dir data/Register]   # adds projects/<slug>.py
```

Then the fields: [Adding a project](../develop/adding-a-project.md);
an ingest profile: [Ingest](../ingest/index.md). No migration needed.

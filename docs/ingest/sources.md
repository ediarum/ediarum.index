# Where the XML comes from

ediarum.index never clones, pulls or writes XML. **ediarum.fileservice** keeps
one checkout per project on a shared volume, in step with git and
ediarum.webdav (it is the only writer); ediarum.index mounts that volume
read-only at `XML_MOUNT_ROOT` — `XML_MOUNT_ROOT/<slug>/` is the project's
checkout, files at their repository paths. Which repository and branch is
configured in the **platform's project registry** (`repo_url`, `branch`,
`index_source_of_truth: "xml"`), not here.

What ediarum.index keeps per project is where the registers are inside that
repository: `REGISTER_DIR` in the project's module in `projects/`.
`ingest.PROFILES[slug]["source"]` is a glob *relative to*
`XML_MOUNT_ROOT/<slug>/<REGISTER_DIR>` (`sources.register_dir`, resolved by
`ingest.resolve_source_pattern`). A registry `sparse_path` restricting a
checkout must include `REGISTER_DIR`.

The projects with registers here are those whose module in `projects/`
declares a `REGISTER_DIR` (currently `avhr`, `leibniz5`, `mega`, `mop`, `pta`
and `schleiermacher`, all with `data/Register`); their repository and branch
are looked up in the platform registry.

Every other registry project (bismarck, cagb, goa, goedel, jp, maps, omad,
test, …) is a project here too — entries can be edited in the app — but
nothing is ingested for it until its module declares a `REGISTER_DIR` and
`ingest.PROFILES` has a profile for it; `POST /files` notices for it are
acknowledged and ignored.

**`ediarum-index watch`** (`watch.py`) is what runs the ingest automatically —
a standalone, long-lived process, separate from the API server, one project
at a time:

- A project is ingested when the **digest** of the files its profiles read
  (`sources.digest`: their paths and content hashes) differs from the one its
  last ingest read (`models.SourceState`). A project with no state yet is
  ingested in full on the watcher's first start — on an empty database, that
  is the **initial ingest**.
- Every `--interval` seconds (default 300, `$RECONCILE_INTERVAL`) each
  project is checked; with `FILESERVICE_URL`/`FILESERVICE_KEY`, fileservice's
  `GET /projects/<slug>/status` skips the digest when it changed nothing
  (but at least daily, `--full-every`, default 86400 s). Only files whose size or mtime
  changed are re-hashed.
- **`POST /files`**: ediarum.webdav reports a saved file to ediarum.index too
  (the same multipart notice fileservice and ediarum.id get, with a
  per-project API key). It is recorded (`models.FileNotice`); the watcher
  checks that project as soon as the volume shows the reported content — the
  two notices are separate jobs in no fixed order — and nothing new arrived
  for 10 s, or after 5 minutes regardless. A file none of the project's
  profiles read is acknowledged (`queued: false`) and ignored.
- A failed ingest is logged and retried at the next check.
- Only `xml`-led projects are watched. The registry is re-read every
  interval, so a project that is added, or switched to `xml`, is picked up
  then; with none to watch the watcher idles instead of exiting. Only
  `--project` names that aren't watched are an error.

```bash
XML_MOUNT_ROOT=/data/xml uv run ediarum-index watch      # the service
XML_MOUNT_ROOT=/data/xml uv run ediarum-index scan       # one pass, then exit
uv run ediarum-index scan --project mop --force          # re-ingest regardless
```

Locally, `XML_MOUNT_ROOT=./xml` with a clone of each project's repository
at `./xml/<slug>/` (git-ignored) stands in for the volume.

Two things to know before running it:

- **A re-run reconciles, it doesn't blindly re-insert.** Before writing
  anything, it fetches every existing entry for the project and matches each
  source record to one by `source_id`. Per record (`_reconcile` in
  `ingest.py`): no match → create; a content hash of the extracted `data`
  matches what the *last* ingest wrote (`Entry.ingested_source_hash`) →
  unchanged, skip; hash differs and nobody has edited the entry in the app
  since that ingest (`updated_at` not newer than `ingested_at`) → update in
  place; hash differs *and* it was edited in the app since → **conflict** —
  both sides moved, so it's left untouched and listed in the run's output for
  a human to reconcile, rather than silently overwritten either way. A run
  with conflicts or failures exits non-zero.
- An `xml:id` seen twice *within one run* is skipped rather than posted again,
  so `source_id` stays unique where a register repeats an entry across its
  files.

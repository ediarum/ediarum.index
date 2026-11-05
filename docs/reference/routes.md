# HTTP routes

On the platform every path is below `/api/index` (the proxy strips it, the app
knows it as `ROOT_PATH`); API docs at `/api/index/docs`.

Every route needs a caller (see [Auth](auth.md)). 🔐 = platform admins only.
Everything under `/{project}/…` also needs access to that project (403) and an
active project (404).

| Method & path | Purpose |
|---|---|
| `GET /projects?include_inactive=` | the projects the caller may use (`ProjectPublic[]`): besides name and label, `index_source_of_truth` (the registry's `xml`/`app`), `registers_from_xml` (`xml`-led *and* read from XML here — the UI then notes that edits don't reach the files) — both `null` while the registry is unreachable — and `assigns_ids` (a new entry without a `source_id` gets one from ediarum.id) |
| `GET /entry-types` | the registered entry types (`EntryTypePublic[]`) in canonical order, every project's |
| `GET /{project}/entry-types` | the entry types the project uses (`EntryTypePublic[]`), in canonical order: its module's `ENTRY_TYPES` (every type without one), plus any type it already has entries of. Drives the frontend tabs; `POST /{project}/entries` refuses other types (422) |
| `GET /keys?project=` 🔐 | API clients (never the keys themselves), optionally those that may use `project` |
| `POST /keys` 🔐 | `{name, projects}` (`["*"]` = every project) → `{name, key}`, the key shown only here; duplicate → 409, unknown project → 422 |
| `POST /keys/{name}/revoke` 🔐 | deactivate a key for good |
| `GET /ingest-runs?project=&offset=&limit=` 🔐 | recent ingest runs, newest first, optionally of one profile slug — see [Ingest run history](../ingest/index.md#ingest-run-history) |
| `POST /files` | ediarum.webdav's notice of a saved file (multipart `event`, `project`, `commit`, `path`, `previous_path`, `file`) → 202 `{…, queued}`; the watcher ingests the project once the change is on the volume — see [Where the XML comes from](../ingest/sources.md). Needs access to `project` (typically its webdav API key); `queued: false` for a file — or a whole project — this app reads no registers from, and for an `app`-led project |
| `GET /{project}/schema/{entry_type}` | resolved field schema; unknown type → 404 |
| `GET /{project}/entries?entry_type=&q=&q_field=&offset=&limit=&sort_by=&descending=` | one page of entries; `q` is a case-insensitive substring match on `q_field` (`label` (default), `source_id`, or a `data`-bag key — unknown field → no rows); ordered by `sort_by` (`label` (default), `entry_type`, `source_id`, `birth_date`, `death_date`); full count in the `X-Total-Count` header |
| `GET /{project}/entries/options?entry_type=&q=&offset=&limit=&format=` | `[{id, label}]` for an entry type, ordered by label — for reference pickers; `format=ul` returns `<ul><li xml:id="…"><span>Label (birth-death)</span></li>…</ul>` as `application/xml` instead (the oXygen/ediarum reference picker, typically with `?key=`); only entries with a `source_id` |
| `POST /{project}/entries` | create (`EntryIn`) → 201; without a `source_id` it gets one from ediarum.id (`ID_URL`), 503 if that is unreachable |
| `GET /{project}/entries/{id}` | read one |
| `PATCH /{project}/entries/{id}` | partial update (`EntryEdit`: `label`, `source_id`, `data`) |
| `DELETE /{project}/entries/{id}` | delete |
| `GET /{project}/export/{entry_type}` | rebuild the register XML from the stored entries (`application/xml`) — see [Export (round-trip)](../ingest/export.md) |
| `POST /{project}/relations` | create a `(subject_id, predicate, object_id)` triple linking two entries of the project; unknown id → 404, cross-project → 422, duplicate triple → 409 |
| `GET /{project}/relations?subject_id=&object_id=&predicate=&offset=&limit=` | relations whose subject belongs to the project, with `subject_label`/`object_label` resolved |
| `DELETE /{project}/relations/{id}` | delete |
| `PUT /{project}/relations/{id}/anchor` | create-or-replace a `MentionAnchor` (exact character span) for one relation's note-link — see [Comments and note-links](../ingest/links-and-comments.md#comments-and-note-links) |
| `POST /{project}/comments` | a hand-written remark on an entry (`CommentIn`): `source="app"`, the caller as author, now; unknown `entry_id` → 404 |
| `GET /{project}/comments?entry_id=&offset=&limit=` | comments on the project's entries |
| `DELETE /{project}/comments/{id}` | delete |

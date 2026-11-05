# Auth

ediarum.index has no login, users or session of its own. **Every request** is
one of two callers, resolved by `ediarum_sdk.auth` into a `Caller`
(`deps.current_caller`):

- **Platform user** — the request carries the platform's session cookie. The
  app forwards `Cookie`, `X-XSRF-TOKEN` and the method to the platform's
  verify endpoint (`AUTH_VERIFY_URL`, ediarum-platform
  `docs/auth-contract.md`), which answers `204` with `X-User` (email),
  `X-User-Roles` and `X-User-Projects`. `401`/`419` are passed on; anything
  else, a timeout or a `204` without `X-User` is a `503`.
- **API key** — for clients without a browser session (ediarum/oXygen,
  scripts): `Authorization: Bearer <key>`, `X-API-Key: <key>` or, for a client
  that can only fetch a URL, `?key=<key>`. Checked against the SDK's
  `sdk_api_key` table (SHA-256 hashes only). A request with a key is always
  checked as a key — the platform is not consulted.

**Access rule** (the same in every platform app): a caller may use a project
if it is one of their projects or they are an admin (role `admin`, or an admin
key). It is checked on every `/{project}/…` route, reads and writes alike —
`403` otherwise; an unknown or inactive project is then `404`. A row of
another project addressed through this project's URL is `404`.

**Admin-only** (platform users with role `admin`, never a key — a key can't
make keys): `/keys` and `GET /ingest-runs`.

- Keys are created by a platform admin (`POST /keys`, shown once) or on the
  server (`ediarum-index keys add <name> --projects mop,pta` — the bootstrap
  path), and revoked for good with `POST /keys/{name}/revoke` /
  `ediarum-index keys revoke`.
- `AUTH_VERIFY_URL` (production) and `AUTH_DEV_USER=<email>` (local
  development: every request is that admin user) are mutually exclusive.
  Neither set: only keys work.
- The ingest needs no credentials: it writes straight into the database
  through `services`.

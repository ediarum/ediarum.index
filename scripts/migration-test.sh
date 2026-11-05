#!/usr/bin/env bash
#
# Upgrade a database that holds data to this code's newest schema, as a
# release would — and fail if any table lost rows, or models and migrations
# disagree.
#
#   DATABASE_URL=mysql+pymysql://… scripts/migration-test.sh
#
# With a previous release (the newest vX.Y.Z tag before HEAD): its own code
# migrates the empty database and ingests the fixture volume
# (tests/data/xml); this code then migrates it — with the backup a real
# upgrade writes — and ingests again. Without one (before the first release):
# the same, starting from this code's own schema.
#
# Needs: an empty database at DATABASE_URL, git history with tags, uv, the
# MariaDB client (mariadb-dump) for the backup.
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL to an empty database}"
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
export XML_MOUNT_ROOT="$root/tests/data/xml"
export BACKUP_DIR="$(mktemp -d)"
unset AUTH_VERIFY_URL AUTH_DEV_USER PLATFORM_PROJECTS_URL FILESERVICE_URL

counts() {  # {table: rows} of the database, as JSON
  uv run --project "$root" python - <<'PY'
import json, os
from sqlalchemy import create_engine, inspect, text
engine = create_engine(os.environ["DATABASE_URL"])
with engine.connect() as conn:
    print(json.dumps({t: conn.execute(text(f"SELECT COUNT(*) FROM `{t}`")).scalar()
                      for t in inspect(conn).get_table_names() if t != "alembic_version"}))
PY
}

prev="$(git describe --tags --abbrev=0 --match 'v[0-9]*.[0-9]*.[0-9]*' HEAD^ 2>/dev/null || true)"
if [[ -n "$prev" ]]; then
  echo "== $prev: migrate an empty database, ingest the fixtures"
  old="$(mktemp -d)"
  git worktree add --quiet --detach "$old" "$prev"
  trap 'git worktree remove --force "$old"' EXIT
  uv run --project "$old" ediarum-index migrate
  uv run --project "$old" ediarum-index scan
else
  echo "== no previous release: this code's schema, then the fixtures"
  uv run ediarum-index migrate
  uv run ediarum-index scan
fi
before="$(counts)"
echo "before: $before"

echo "== this code: migrate (with backup if anything is pending), check, ingest again"
uv run ediarum-index migrate
uv run ediarum-index migrate --check
uv run alembic check
uv run ediarum-index scan --force
after="$(counts)"
echo "after:  $after"

BEFORE="$before" AFTER="$after" python3 - <<'PY'
import json, os, sys
before, after = json.loads(os.environ["BEFORE"]), json.loads(os.environ["AFTER"])
lost = {t: (n, after.get(t)) for t, n in before.items() if after.get(t, -1) < n}
if not before.get("entry"):
    sys.exit("the fixture ingest wrote no entries — nothing was really migrated")
if lost:
    sys.exit(f"rows lost by the upgrade (table: before, after): {lost}")
print("ok: no table lost rows")
PY

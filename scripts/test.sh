#!/usr/bin/env bash
# Run the test suites. Same targets as the Makefile, for machines without `make`.
#
#   scripts/test.sh            backend + frontend unit tests
#   scripts/test.sh backend    pytest only
#   scripts/test.sh frontend   vitest only
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-unit}"

run_backend()  { ( cd "$root" && uv run --group test pytest ); }
run_frontend() { ( cd "$root/frontend" && npm run test ); }

case "$target" in
  backend)  run_backend ;;
  frontend) run_frontend ;;
  unit|all) run_backend && run_frontend ;;
  *) echo "usage: $0 [backend|frontend|unit]" >&2; exit 2 ;;
esac

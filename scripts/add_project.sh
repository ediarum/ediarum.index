#!/usr/bin/env bash
#
# Add the module ediarum.index keeps for a project.
#
# The project itself (slug, name, who may use it, its git repository and
# branch) is configured in the ediarum.platform's project registry. This adds
# the module ediarum.index keeps per project — schema OVERRIDES and, for a
# project ingested from its TEI registers, REGISTER_DIR — in
# src/ediarum_index/projects/. No edits to the routes / schemas.py, and no
# Alembic migration. <project_slug> is the platform slug ([a-z][a-z0-9-]*);
# the module is named after it with "-" spelled "_".
#
# Usage:
#   scripts/add_project.sh <project_slug>
#   scripts/add_project.sh <project_slug> --register-dir <path>
#
# --register-dir is where the registers are inside the project's repository
# (e.g. data/Register), which ediarum.fileservice checks out at
# XML_MOUNT_ROOT/<slug>/. Then add the project's profiles to ingest.PROFILES.
#
# Env:
#   API_URL   backend base URL for the smoke test (default http://localhost:8000)
#   API_KEY   an API key for the smoke test (not needed with AUTH_DEV_USER)
#
set -euo pipefail

name=""
register_dir=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --register-dir) register_dir="${2:-}"; shift 2 ;;
    --*) echo "error: unknown flag '$1'" >&2; exit 2 ;;
    *) name="$1"; shift ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
proj_dir="$repo_root/src/ediarum_index/projects"
tmpl="$proj_dir/_template.py"
api="${API_URL:-http://localhost:8000}"
key_param="${API_KEY:+?key=${API_KEY}}"

# --- validate ---------------------------------------------------------------
if [[ -z "$name" ]]; then
  echo "usage: $(basename "$0") <project_slug> [--register-dir <path>]" >&2
  exit 2
fi
if [[ ! "$name" =~ ^[a-z][a-z0-9-]*$ ]]; then
  echo "error: '$name' must be a platform project slug: [a-z][a-z0-9-]*" >&2
  exit 2
fi
module="${name//-/_}"   # a Python module name can't contain "-"
if [[ -e "$proj_dir/${module}.py" || -d "$proj_dir/${module}" ]]; then
  echo "error: project already exists: src/ediarum_index/projects/${module}.py or ${module}/" >&2
  exit 1
fi

# --- create the module ----------------------------------------------------
target="$proj_dir/${module}.py"
cp "$tmpl" "$target"
sed -i "s/^NAME = .*/NAME = \"${name}\"/" "$target"
if [[ -n "$register_dir" ]]; then
  sed -i "s|^# REGISTER_DIR = .*|REGISTER_DIR = \"${register_dir}\"|" "$target"
fi
echo "created src/ediarum_index/projects/${module}.py  (edit OVERRIDES if the project needs custom fields)"
[[ -n "$register_dir" ]] && echo "next: add the project's profiles to ingest.PROFILES (their sources relative to ${register_dir})"

# --- reload the backend so the loader picks it up ------------------------
cd "$repo_root"
if ! command -v docker >/dev/null 2>&1 || [[ -z "$(docker compose ps -q api 2>/dev/null || true)" ]]; then
  echo "api container not present - run 'docker compose up' to load the project"
  exit 0
fi

echo "restarting backend ..."
docker compose restart api >/dev/null

for _ in $(seq 1 30); do
  if curl -fsS "$api/projects${key_param}" 2>/dev/null | grep -q "\"${name}\""; then
    echo "ok: $api/projects now lists ${name}"
    echo "person schema for ${name}:"
    curl -fsS "$api/${name}/schema/person${key_param}"; echo
    exit 0
  fi
  sleep 1
done

echo "warning: ${name} not reported by $api/projects within 30s; check 'docker compose logs api'" >&2
exit 1

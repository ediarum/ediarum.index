#!/bin/sh
# Smoke test for a built image: runs INSIDE the container, fed on stdin, so it
# works the same locally and in CI (where the job's checkout isn't visible to
# the container):
#
#   docker build -t ediarum-index:test .
#   docker run --rm -i ediarum-index:test sh < scripts/smoke-test.sh
#
# Checks that the installed package (incl. the migrations shipped in it) can
# migrate an empty database, ingest a project from an XML volume, serve the
# API to an API key, and accept a webdav file notice.
set -eu

work=$(mktemp -d)
export DATABASE_URL="sqlite:///$work/index.db"
export XML_MOUNT_ROOT="$work/xml"
unset AUTH_VERIFY_URL AUTH_DEV_USER PLATFORM_PROJECTS_URL FILESERVICE_URL

mkdir -p "$work/xml/leibniz5/data/Register/Personen"
cat > "$work/xml/leibniz5/data/Register/Personen/A.xml" <<'XML'
<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><listPerson>
<person xml:id="L0001"><persName type="reg"><surname>Arnauld</surname><forename>Antoine</forename></persName><birth>1612</birth></person>
</listPerson></body></text></TEI>
XML

echo "== migrations"
ediarum-index migrate
ediarum-index migrate --check

echo "== scan (the watcher's check, once)"
ediarum-index scan --project leibniz5

echo "== api"
key=$(ediarum-index keys add smoke --projects leibniz5)
ediarum-index serve --port 8000 > "$work/api.log" 2>&1 &
api=$!
python - "$key" <<'PY'
import json, sys, time, urllib.error, urllib.request

base, key = "http://127.0.0.1:8000", sys.argv[1]
auth = {"Authorization": f"Bearer {key}"}
for _ in range(50):
    try:
        urllib.request.urlopen(f"{base}/openapi.json")
        break
    except OSError:
        time.sleep(0.2)
else:
    sys.exit("api did not start")

def get(path, headers=auth):
    return urllib.request.urlopen(urllib.request.Request(f"{base}{path}", headers=headers))

projects = [p["name"] for p in json.load(get("/projects"))]
assert projects == ["leibniz5"], projects
ul = get(f"/leibniz5/entries/options?entry_type=person&format=ul&key={key}", {}).read().decode()
assert 'xml:id="L0001"' in ul and "Arnauld" in ul, ul
print("projects:", projects, "| options:", ul.count("<li"), "entry")

for path, status in (("/mop/entries", 403), ("/leibniz5/entries", None)):
    try:
        get(path, {} if status is None else auth)
        raise SystemExit(f"{path}: expected an error")
    except urllib.error.HTTPError as e:
        assert e.code == (status or 401), (path, e.code)

boundary = "smoke"
parts = [("event", "modified"), ("project", "leibniz5"), ("commit", "abc"),
         ("path", "data/Register/Personen/A.xml")]
body = "".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in parts)
body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="A.xml"\r\n'
         f'Content-Type: application/xml\r\n\r\n<TEI/>\r\n--{boundary}--\r\n')
req = urllib.request.Request(f"{base}/files", body.encode(), method="POST",
                             headers={**auth, "Content-Type": f"multipart/form-data; boundary={boundary}"})
notice = json.load(urllib.request.urlopen(req))
assert notice["queued"] is True, notice
print("files: notice queued; access checks: 403 / 401 as expected")
PY
kill "$api"

echo "smoke test passed"

"""IngestRun: written by the ingest itself, listed for platform admins."""

from ediarum_index import ingest


def test_report_run_then_list_and_filter(client, session):
    for slug, status in (("mop", "ok"), ("pta", "failed")):
        ingest.report_run(session, {
            "project": slug, "started_at": "2026-01-01T00:00:00+00:00", "status": status,
            "created": 1, "updated": 0, "unchanged": 0,
            "problems": [{"fname": "a.xml", "ext_id": "x", "detail": "d", "kind": "failed"}],
        })
    runs = client.get("/ingest-runs").json()
    assert {r["project"] for r in runs} == {"mop", "pta"}
    only = client.get("/ingest-runs", params={"project": "pta"}).json()
    assert [r["status"] for r in only] == ["failed"]
    assert only[0]["problems"][0]["kind"] == "failed"


def test_a_report_that_cannot_be_written_never_fails_the_run(session, capsys):
    ingest.report_run(session, {"project": "mop"})  # missing required fields
    assert "could not record this run" in capsys.readouterr().out

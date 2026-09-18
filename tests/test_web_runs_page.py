"""The Runs page: history with outcome, the PDF link, reprint; PDFs are served only from the app's own folders."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lakota_grades.web import app as webapp, db, jobs
from lakota_grades.web.stores import runs
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed
from tests.test_web_jobs import FakeActions


def _rows(home):
    conn = seed(home)
    pdf = home / "sheets" / "2026-09-15" / "sheet.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 fake")
    ids = [
        runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "2p Al=3 Sam=2", str(pdf)),
        runs.record(conn, "refresh", "2026-09-15T13:50:00-04:00", "2026-09-15T13:51:00-04:00", "web", "OK", "refresh 1: 10 new items"),
        runs.record(conn, "open-work", "2026-09-14T14:00:00-04:00", "2026-09-14T14:01:00-04:00", "schedule", "FAIL", "printer offline; PDF kept at /gone.pdf", "/gone.pdf"),
        runs.record(conn, "open-work", "2026-09-13T14:00:00-04:00", "2026-09-13T14:00:01-04:00", "cli", "SKIP", "outside print window"),
    ]
    conn.close()
    return ids, pdf


def test_runs_page_lists_history_newest_first_with_badges_and_links(tmp_path):
    ids, pdf = _rows(tmp_path)
    body = app_for(tmp_path).get("/runs").text
    assert body.index("2p Al=3 Sam=2") < body.index("refresh 1") < body.index("printer offline") < body.index("outside print window")
    assert 'class="badge OK"' in body and 'class="badge FAIL"' in body and 'class="badge SKIP"' in body
    assert f'href="/runs/{ids[0]}/pdf"' in body
    assert f'href="/runs/{ids[2]}/pdf"' not in body            # the file is gone: no link
    assert "Mon 9/14" in body and "schedule" in body and "cli" in body


def test_reprint_button_only_for_printable_ok_runs_when_a_worker_exists(tmp_path):
    ids, pdf = _rows(tmp_path)
    body = app_for(tmp_path).get("/runs").text
    assert 'hx-post="/jobs/print"' not in body                 # no worker: no button
    body = app_for(tmp_path, worker=True).get("/runs").text
    assert body.count('hx-post="/jobs/print"') == 1 and 'value="2026-09-15"' in body


def test_reprint_submits_the_report_key_of_its_own_row(tmp_path):
    """Reprint posted only a date, so reprinting a saved report's run printed the open-work
    sheet instead of the report. The row's own key goes with the date now."""
    import json
    import re

    from lakota_grades import config
    from lakota_grades.web.stores import reports as reportstore

    ids, pdf = _rows(tmp_path)
    conn = db.open_db(tmp_path)
    rid = reportstore.create(conn, "Mine", json.dumps({"title": "Mine", "source": "items",
                                                       "columns": ["kid", "name"]}),
                             now="2026-09-16T08:00:00-04:00")
    runs.record(conn, f"view:{rid}", "2026-09-16T16:00:00-04:00", "2026-09-16T16:01:00-04:00",
                "schedule", "OK", "1p 3 rows", str(pdf))
    conn.close()

    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    fake = FakeActions()
    w = jobs.Worker(application.state.lakota, actions=fake)
    application.state.lakota.jobs = w
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    form = re.search(r'<form hx-post="/jobs/print".*?</form>', c.get("/runs").text, re.S).group(0)
    fields = dict(re.findall(r'name="(\w+)" value="([^"]*)"', form))   # the newest run: the view report
    assert fields == {"date": "2026-09-16", "report": f"view:{rid}"}

    assert c.post("/jobs/print", data=fields).status_code == 200
    assert w.current.params == {"date": "2026-09-16", "report": f"view:{rid}"}
    w.run_pending()
    assert ("print", "2026-09-16", f"view:{rid}") in fake.calls


def test_pdf_is_served_from_home_and_refused_elsewhere(tmp_path):
    ids, pdf = _rows(tmp_path)
    c = app_for(tmp_path)
    r = c.get(f"/runs/{ids[0]}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert c.get(f"/runs/{ids[2]}/pdf").status_code == 404     # missing file
    assert c.get(f"/runs/{ids[1]}/pdf").status_code == 404     # no pdf on a refresh
    assert c.get("/runs/999/pdf").status_code == 404
    outside = tmp_path.parent / "elsewhere.pdf"
    outside.write_bytes(b"%PDF-1.4 no")
    conn = db.open_db(tmp_path)
    rid = runs.record(conn, "open-work", "2026-09-12T14:00:00-04:00", "2026-09-12T14:01:00-04:00", "cli", "OK", "x", str(outside))
    conn.close()
    assert c.get(f"/runs/{rid}/pdf").status_code == 404          # outside home and the archive


def test_a_directory_named_like_a_pdf_is_a_404_not_a_500(tmp_path):
    """FileResponse on a directory raises inside the response; safe_pdf refuses it first."""
    seed(tmp_path).close()
    folder = tmp_path / "sheets" / "sheet.pdf"
    folder.mkdir(parents=True)
    conn = db.open_db(tmp_path)
    rid = runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:01:00-04:00", "cli", "OK", "x", str(folder))
    conn.close()
    c = app_for(tmp_path)
    assert c.get(f"/runs/{rid}/pdf").status_code == 404
    assert f'href="/runs/{rid}/pdf"' not in c.get("/runs").text       # and no link to it either


def test_pdf_under_the_archive_folder_is_allowed(tmp_path):
    from lakota_grades import config
    archive = tmp_path / "Drive" / "Sheets"
    archive.mkdir(parents=True)
    f = archive / "2026-09-15 Open Work.pdf"
    f.write_bytes(b"%PDF-1.4 archived")
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    rid = runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:01:00-04:00", "cli", "OK", "x", str(f))
    conn.close()
    s = config.Settings(home=tmp_path)
    s.sheets_archive = str(archive)
    assert TestClient(webapp.create_app(s, worker=False), headers=LOCAL_HOST_HEADERS).get(f"/runs/{rid}/pdf").status_code == 200


def test_job_pdf_after_a_preview(tmp_path):
    from lakota_grades import config
    seed(tmp_path).close()
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    fake = FakeActions()
    w = jobs.Worker(application.state.lakota, actions=fake)
    application.state.lakota.jobs = w
    pdf = tmp_path / "sheets" / "2026-09-15" / "sheet.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 preview")
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    c.post("/jobs/preview")
    w.run_pending()
    body = c.get(f"/jobs/{w.last.id}").text
    assert f'href="/jobs/{w.last.id}/pdf"' in body
    assert c.get(f"/jobs/{w.last.id}/pdf").status_code == 200
    assert c.get("/jobs/999/pdf").status_code == 404
    # The link is gated on the same check the route makes, so a PDF deleted since the job ran
    # (an archive clean-up, a tidied Downloads folder) is not offered as a dead link.
    pdf.unlink()
    assert f'href="/jobs/{w.last.id}/pdf"' not in c.get(f"/jobs/{w.last.id}").text
    assert c.get(f"/jobs/{w.last.id}/pdf").status_code == 404

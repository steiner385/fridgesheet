"""Diagnostics: the last doctor report, and the button that runs a new one."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lakota_grades import config
from lakota_grades.web import app as webapp, jobs
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed
from tests.test_web_jobs import FakeActions


def test_page_shows_no_report_yet_then_the_report(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/diagnostics").text
    assert "not been run yet" in body and 'hx-post="/jobs/doctor"' not in body
    (tmp_path / "doctor.txt").write_text("OK    python: 3.12\nFAIL  printers: none\n1 check(s) failed\n")
    body = c.get("/diagnostics").text
    assert "FAIL  printers" in body and "1 check(s) failed" in body


def test_run_diagnostics_button_starts_the_job_and_the_page_shows_it(tmp_path):
    seed(tmp_path).close()
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    w = jobs.Worker(application.state.lakota, actions=FakeActions())
    application.state.lakota.jobs = w
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    assert 'hx-post="/jobs/doctor"' in c.get("/diagnostics").text
    r = c.post("/jobs/doctor")
    assert r.status_code == 200 and "Running diagnostics" in r.text
    w.run_pending()
    assert "OK    python" in c.get(f"/jobs/{w.last.id}").text

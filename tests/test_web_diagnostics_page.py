"""Diagnostics: the last doctor report, and the button that runs a new one."""
from __future__ import annotations

from fastapi.testclient import TestClient

from fridgesheet import config
from fridgesheet.host import selfupdate
from fridgesheet.web import app as webapp, jobs, updates
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
    w = jobs.Worker(application.state.fridgesheet, actions=FakeActions())
    application.state.fridgesheet.jobs = w
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    assert 'hx-post="/jobs/doctor"' in c.get("/diagnostics").text
    r = c.post("/jobs/doctor")
    assert r.status_code == 200 and "Running diagnostics" in r.text
    w.run_pending()
    assert "OK    python" in c.get(f"/jobs/{w.last.id}").text


def test_a_failed_update_is_reported_with_its_log(tmp_path):
    # The breadcrumb must exist before the app is built: `resolve_pending` runs once, at
    # startup (see `webapp.create_app`), not on every /diagnostics GET -- a GET must not
    # archive the breadcrumb (issue #resolve_pending mutates state), and a second visitor
    # (or a refresh) must see the same verdict the first one saw.
    seed(tmp_path).close()
    selfupdate.write_pending(tmp_path, selfupdate.Pending(
        from_version="0.4.1", to_version="9.9.9", started_at="2026-09-22T15:00:00-04:00",
        installer=r"C:\u\Setup.exe", log=r"C:\u\install.log"))
    body = app_for(tmp_path).get("/diagnostics").text
    assert "9.9.9" in body and "install.log" in body


def test_a_successful_update_archives_the_breadcrumb_and_shows_no_card(tmp_path):
    """The `to_version` this process is actually running -- not a made-up "9.9.9" -- so
    `resolve_pending` (run once at startup) takes the "ok" branch: it archives
    update-pending.json to update-last.json, and the "did not finish" card must not appear.
    A test that only ever wrote a failing breadcrumb (the old version of this test) would
    still pass with the card's `{% if %}` deleted outright -- this earns its place by
    covering the branch that never renders a card at all."""
    seed(tmp_path).close()
    running = updates.current_version()
    selfupdate.write_pending(tmp_path, selfupdate.Pending(
        from_version="0.1.0", to_version=running, started_at="2026-09-22T15:00:00-04:00",
        installer=r"C:\u\Setup.exe", log=r"C:\u\install.log"))
    body = app_for(tmp_path).get("/diagnostics").text
    assert "did not finish" not in body
    assert not (tmp_path / selfupdate.PENDING_NAME).exists()   # archived, not left to fire again
    assert (tmp_path / selfupdate.LAST_NAME).exists()


def test_a_clean_start_says_nothing_about_updates(tmp_path):
    seed(tmp_path).close()
    assert "did not finish" not in app_for(tmp_path).get("/diagnostics").text


def test_a_malformed_breadcrumb_does_not_stop_the_app_from_starting(tmp_path):
    """`read_pending` already treats bad JSON as absent -- this proves that guarantee still
    holds now that the resolve happens at app *startup* (`webapp.create_app`) rather than on
    a page render: a corrupt update-pending.json must never be the reason the whole app
    fails to boot."""
    seed(tmp_path).close()
    (tmp_path / selfupdate.PENDING_NAME).write_text("{not json", encoding="utf-8")
    body = app_for(tmp_path).get("/diagnostics").text
    assert "did not finish" not in body

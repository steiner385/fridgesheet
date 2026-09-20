"""The jobs worker: one at a time, progress lines, the runner's lock, SSE frames, and the routes."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from fridgesheet import config, runner
from fridgesheet.web import actions, db, jobs
from fridgesheet.web import app as webapp
from fridgesheet.web.stores import runs
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, TZ, app_for, seed, snapshot


def _settings(home):
    return config.Settings(home=home)


def test_refresh_collects_ingests_and_records_a_run(tmp_path):
    lines = []
    r = actions.refresh(home=tmp_path, log=lines.append, settings=_settings(tmp_path), collect=lambda s: snapshot(), now=NOW)
    assert r.ok and r.refresh_id == 1 and "refresh" in r.message.lower()
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 10
    (row,) = runs.recent(conn)
    assert (row["report_key"], row["trigger"], row["outcome"]) == ("refresh", "web", "OK")
    conn.close()
    assert any("ingested" in ln for ln in lines)


def test_refresh_fails_softly_when_the_runner_lock_is_held(tmp_path):
    lock = runner.Lock(tmp_path / runner.LOCK_NAME)
    assert lock.acquire()
    try:
        r = actions.refresh(home=tmp_path, log=lambda s: None, settings=_settings(tmp_path), collect=lambda s: snapshot())
    finally:
        lock.release()
    assert not r.ok and "already running" in r.message
    conn = db.open_db(tmp_path)
    rows = runs.recent(conn)
    assert len(rows) == 1 and rows[0]["outcome"] == "FAIL" and "already running" in rows[0]["message"]
    conn.close()


def test_refresh_reports_a_collector_error_as_fail_with_a_run_row(tmp_path):
    def boom(s):
        raise RuntimeError("portal timeout")
    r = actions.refresh(home=tmp_path, log=lambda s: None, settings=_settings(tmp_path), collect=boom)
    assert not r.ok and "portal timeout" in r.message
    conn = db.open_db(tmp_path)
    assert runs.recent(conn)[0]["outcome"] == "FAIL"
    conn.close()


class FakeActions:
    """Stand-ins for the five actions; each logs a line and returns what the real one returns."""
    def __init__(self):
        self.calls = []

    def refresh(self, *, home, log, settings):
        self.calls.append("refresh"); log("refreshing"); return actions.RefreshResult(True, "refresh OK", 1)

    def preview(self, *, home, log, settings, report_key="open-work", refresh=False):
        self.calls.append(("preview", report_key, refresh)); log("building"); return home / "sheets" / "2026-09-15" / "sheet.pdf"

    def print_now(self, *, home, log, settings, date=None, report_key="open-work", refresh=False):
        self.calls.append(("print", date, report_key, refresh)); log("printing"); return 0

    def run_doctor(self, *, home, log, settings):
        self.calls.append("doctor"); log("OK    python: 3.12"); return True

    def test_login(self, *, home, log, settings):
        self.calls.append("login"); log("Canvas: OK"); return actions.LoginResult(True, {"Canvas": None}, "Login OK for Canvas.")


def _worker(tmp_path, fake=None):
    s = _settings(tmp_path)
    application = webapp.create_app(s, worker=False)
    w = jobs.Worker(application.state.fridgesheet, actions=fake or FakeActions())
    application.state.fridgesheet.jobs = w
    return application, w


def test_worker_runs_one_job_at_a_time_and_keeps_its_lines(tmp_path):
    application, w = _worker(tmp_path)
    job = w.submit("refresh")
    assert job is not None and job.kind == "refresh" and w.current is job and not job.done
    assert w.submit("doctor") is None                     # busy: refused, not queued
    w.run_pending()
    assert job.done and job.outcome == "OK" and job.lines == ["refreshing", "refresh OK"] and w.current is None and w.last is job
    second = w.submit("doctor")
    w.run_pending()
    assert second.id == job.id + 1 and second.outcome == "OK" and "python" in second.lines[0]


def test_worker_print_passes_the_date_and_maps_rc_to_outcome(tmp_path):
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    job = w.submit("print", date="2026-09-14")
    w.run_pending()
    assert ("print", "2026-09-14", "open-work", False) in fake.calls and job.outcome == "OK"
    fake.print_now = lambda **kw: 1
    job = w.submit("print"); w.run_pending()
    assert job.outcome == "FAIL"


def test_worker_turns_an_exception_into_fail_and_frees_the_slot(tmp_path):
    fake = FakeActions()
    def boom(**kw):
        raise RuntimeError("kaboom")
    fake.preview = boom
    application, w = _worker(tmp_path, fake)
    job = w.submit("preview"); w.run_pending()
    assert job.outcome == "FAIL" and "kaboom" in job.message and w.current is None
    assert w.submit("doctor") is not None


def test_a_job_inside_its_deadline_still_holds_the_slot(tmp_path):
    application, w = _worker(tmp_path)
    state = application.state.fridgesheet
    state.clock = lambda: NOW
    w.submit("refresh")                                   # never run: nothing calls run_pending
    state.clock = lambda: NOW + timedelta(seconds=jobs.JOB_TIMEOUT_SECONDS - 1)
    assert w.submit("doctor") is None                     # still busy, still 409


def test_a_job_past_its_deadline_is_displaced_by_the_next_submit(tmp_path):
    """A hung Playwright job must not wedge every button in the app forever."""
    application, w = _worker(tmp_path)
    state = application.state.fridgesheet
    state.clock = lambda: NOW
    stuck = w.submit("refresh")
    later = NOW + timedelta(seconds=jobs.JOB_TIMEOUT_SECONDS + 1)
    state.clock = lambda: later
    fresh = w.submit("doctor")
    assert fresh is not None and w.current is fresh and stuck.id != fresh.id
    assert stuck.done and stuck.outcome == "FAIL" and stuck.message == jobs.TIMED_OUT
    assert stuck.lines[-1] == jobs.TIMED_OUT and stuck.finished_at == later and w.last is stuck
    w.run_pending()                                       # the displaced job is skipped, not re-run
    assert not fresh.done and stuck.message == jobs.TIMED_OUT
    w.run_pending()
    assert fresh.done and fresh.outcome == "OK" and w.current is None and w.last is fresh


def test_a_displaced_job_finishing_late_leaves_the_running_one_alone(tmp_path):
    """The abandoned thread is never killed; when it finally returns it must not free the slot."""
    import threading, time
    fake = FakeActions()
    gate = threading.Event()
    def blocked(*, home, log, settings):
        log("refreshing"); gate.wait(5); return actions.RefreshResult(True, "refresh OK", 1)
    fake.refresh = blocked
    application, w = _worker(tmp_path, fake)
    state = application.state.fridgesheet
    state.clock = lambda: NOW
    stuck = w.submit("refresh")
    hung = threading.Thread(target=w.run_pending, daemon=True)
    hung.start()
    for _ in range(100):                                  # wait until it is really inside the action
        if stuck.lines:
            break
        time.sleep(0.01)
    state.clock = lambda: NOW + timedelta(seconds=jobs.JOB_TIMEOUT_SECONDS + 1)
    fresh = w.submit("doctor")
    gate.set()
    hung.join(timeout=5)
    assert w.current is fresh and w.last is stuck                    # the slot stayed with the new job
    assert stuck.outcome == "FAIL" and stuck.message == jobs.TIMED_OUT
    assert stuck.lines == ["refreshing", jobs.TIMED_OUT]             # the outcome it already has


def test_unknown_kind_is_rejected(tmp_path):
    application, w = _worker(tmp_path)
    with pytest.raises(ValueError):
        w.submit("dance")


def test_events_replay_the_lines_then_end_with_done(tmp_path):
    application, w = _worker(tmp_path)
    job = w.submit("login"); w.run_pending()
    frames = list(w.events(job.id))
    assert frames == ["data: Canvas: OK\n\n", "data: Login OK for Canvas.\n\n", "event: done\ndata: OK\n\n"]
    assert list(w.events(999)) == ["event: done\ndata: unknown\n\n"]


def test_events_stream_while_a_job_runs(tmp_path):
    """A job on the worker thread: the generator yields lines as they arrive and ends when the job ends."""
    import threading, time
    fake = FakeActions()
    gate = threading.Event()
    def slow(*, home, log, settings):
        log("step 1"); gate.wait(5); log("step 2"); return True
    fake.run_doctor = slow
    application, w = _worker(tmp_path, fake)
    w.start()
    job = w.submit("doctor")
    it = w.events(job.id)
    assert next(it) == "data: step 1\n\n"
    gate.set()
    assert next(it) == "data: step 2\n\n"
    assert next(it).startswith("event: done")
    for _ in range(50):
        if w.current is None: break
        time.sleep(0.05)
    assert w.current is None


def test_routes_start_a_job_answer_busy_and_stream_events(tmp_path):
    from fastapi.testclient import TestClient
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    r = c.post("/jobs/refresh")
    assert r.status_code == 200 and "Refreshing" in r.text and f'data-sse="/jobs/{w.current.id}/events"' in r.text
    assert c.post("/jobs/doctor").status_code == 409
    assert c.get("/").text.count("Refreshing") >= 1              # the header badge
    w.run_pending()
    r = c.get(f"/jobs/{w.last.id}")
    assert r.status_code == 200 and "OK" in r.text and "refreshing" in r.text and "data-sse" not in r.text
    with c.stream("GET", f"/jobs/{w.last.id}/events") as s:
        body = "".join(s.iter_text())
    assert "data: refreshing" in body and "event: done" in body
    assert c.post("/jobs/dance").status_code == 404
    assert c.get("/jobs/999").status_code == 404


def test_dashboard_offers_refresh_only_when_a_worker_exists(tmp_path):
    seed(tmp_path).close()
    assert 'hx-post="/jobs/refresh"' not in app_for(tmp_path).get("/").text
    application, w = _worker(tmp_path)
    from fastapi.testclient import TestClient
    assert 'hx-post="/jobs/refresh"' in TestClient(application, headers=LOCAL_HOST_HEADERS).get("/").text


def test_a_job_carries_the_report_key(tmp_path):
    from fastapi.testclient import TestClient
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    assert c.post("/jobs/print", data={"report": "open-work"}).status_code == 200
    w.run_pending()
    assert ("print", "open-work") in [(k[0], k[2]) for k in fake.calls if isinstance(k, tuple) and k[0] == "print"]
    assert c.post("/jobs/print", data={"report": "view:999"}).status_code == 400


def test_refresh_first_checkbox_reaches_the_action_only_when_checked(tmp_path):
    """The Dashboard's "Refresh data first" checkbox (and the Reports page's "Refresh first")
    is an ordinary unchecked-by-default HTML checkbox: unchecked, the browser omits the field
    entirely, and `preview`/`print_now` must default to the fast, no-live-pull path."""
    from fastapi.testclient import TestClient
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    assert c.post("/jobs/preview").status_code == 200
    w.run_pending()
    assert ("preview", "open-work", False) in fake.calls
    assert c.post("/jobs/print", data={"refresh_first": "on"}).status_code == 200
    w.run_pending()
    assert ("print", None, "open-work", True) in fake.calls

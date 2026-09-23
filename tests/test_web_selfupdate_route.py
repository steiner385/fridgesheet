"""The "update" job: in `jobs.KINDS` so the worker can run it, out of `jobs.OPEN_KINDS` so the
generic `POST /jobs/{kind}` route (no PIN) can never start it -- only `POST /settings/update` can.
"""
from __future__ import annotations

from datetime import timedelta

from fridgesheet import host
from fridgesheet.web import jobs, updatepin
from tests.web_fixtures import NOW, app_for, seed


def test_the_generic_job_route_will_not_start_an_update(tmp_path):
    """The PIN is worthless if POST /jobs/update works without it. `update` is in KINDS so
    the worker can run it, and out of OPEN_KINDS so the open route cannot start it."""
    assert "update" in jobs.KINDS
    assert "update" not in jobs.OPEN_KINDS
    seed(tmp_path)
    r = app_for(tmp_path).post("/jobs/update")
    assert r.status_code == 404


def test_no_pin_configured_means_the_route_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path)
    r = app_for(tmp_path).post("/settings/update", data={"pin": "2468"})
    assert r.status_code == 403
    assert "PIN" in r.text


def test_a_wrong_pin_is_refused_and_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = app_for(tmp_path)
    for _ in range(5):
        assert c.post("/settings/update", data={"pin": "0000"}).status_code == 403
    r = c.post("/settings/update", data={"pin": "2468"})          # correct, but locked now
    assert r.status_code == 429 and "15 minutes" in r.text


def test_the_route_refuses_when_the_parent_turned_update_checks_off(tmp_path):
    """Review Focus 5. `check_updates = false` is the parent switching off this app's one
    outbound call; a button must not quietly put it back. No platform patch needed: this
    guard fires before the platform check, on any host."""
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"), check_updates=False)
    r = app_for(tmp_path).post("/settings/update", data={"pin": "2468"})
    assert r.status_code == 409


def test_the_route_refuses_on_a_non_windows_host(tmp_path, monkeypatch):
    """Fix round: today nothing checked the platform until `selfupdate.spawn_installer`'s
    dispatcher raised -- the LAST step, after a 286 MB download and a written breadcrumb.
    The PIN-gated route must refuse before any of that, alongside its other 409."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    r = app_for(tmp_path).post("/settings/update", data={"pin": "2468"})
    assert r.status_code == 409
    assert "Windows" in r.text


def _with_idle_worker(tmp_path):
    """A client whose jobs worker never drains its queue. `self_update` still runs for real
    (against `tests/conftest.py`'s always-offline `updates.DEFAULT_FETCH`) the moment a
    background thread would pick a job up -- exactly the seam `test_web_jobs.py`,
    `test_web_runs_page.py` and `test_web_diagnostics_page.py` all avoid by attaching a
    `Worker` without calling `start()`. Without that seam, whether "the update still holds
    the slot" held would depend on whether the assertion below outran a real thread -- a race,
    not a test.
    """
    c = app_for(tmp_path)
    c.app.state.fridgesheet.jobs = jobs.Worker(c.app.state.fridgesheet)
    return c


def test_an_update_job_will_not_be_displaced_by_another_job(tmp_path, monkeypatch):
    """Review Focus 1: `Worker.submit` abandons the running job to take the slot, but the
    abandoned thread keeps going -- so a Refresh started mid-update would still get an
    installer fired at it. An update in flight holds the slot."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = _with_idle_worker(tmp_path)
    c.post("/settings/update", data={"pin": "2468"})
    r = c.post("/jobs/refresh")
    assert r.status_code == 409


def test_an_update_past_its_own_deadline_is_still_not_displaced(tmp_path, monkeypatch):
    """Fix round 1, Important A. `test_an_update_job_will_not_be_displaced_by_another_job`
    above holds the clock at `NOW`, where the ordinary busy-slot check in `Worker.submit`
    (`now < self.current.deadline`) already returns `None` before the update-specific guard
    is ever reached -- it proves "the slot is busy", not "an update refuses displacement".
    This advances the clock past `jobs.JOB_TIMEOUT_SECONDS` first (the same pattern
    `tests/test_web_jobs.py::test_a_job_past_its_deadline_is_displaced_by_the_next_submit`
    uses), so the far more general "abandon a stuck job and take the slot" path is genuinely
    live, and only the update-specific guard stands between it and displacing the job.
    """
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = _with_idle_worker(tmp_path)
    state = c.app.state.fridgesheet
    state.clock = lambda: NOW
    r = c.post("/settings/update", data={"pin": "2468"})
    assert r.status_code == 200
    w = state.jobs
    update_job = w.current
    assert update_job is not None and update_job.kind == "update" and not update_job.done

    state.clock = lambda: NOW + timedelta(seconds=jobs.JOB_TIMEOUT_SECONDS + 1)
    second = w.submit("refresh")
    assert second is None                              # still refused, past the deadline too
    assert w.current is update_job and not update_job.done   # never abandoned, never displaced


def test_a_second_update_cannot_start_while_one_is_running(tmp_path, monkeypatch):
    """Review Focus 2: two 286 MB downloads and two installers racing each other."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path, update_pin_hash=updatepin.hash_pin("2468"))
    c = _with_idle_worker(tmp_path)
    assert c.post("/settings/update", data={"pin": "2468"}).status_code == 200
    assert c.post("/settings/update", data={"pin": "2468"}).status_code == 409

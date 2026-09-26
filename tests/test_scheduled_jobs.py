"""What a scheduled run does: the Refresh button's path, and the OS task's old command line."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fridgesheet import config, runner
from fridgesheet.web import actions, jobs
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed

TZ = ZoneInfo("America/New_York")


def test_scheduled_run_keeps_every_guard(tmp_path):
    seen = {}

    def fake_run(key, opts, settings, echo=None):
        seen["key"], seen["opts"] = key, opts
        return 0

    rc = actions.scheduled_run(home=tmp_path, log=lambda _l: None, settings=config.Settings(home=tmp_path),
                               report_key="view:3", run=fake_run)
    assert rc == 0 and seen["key"] == "view:3"
    o = seen["opts"]
    assert (o.no_refresh, o.trigger, o.force, o.reprint, o.force_print, o.dry_run) == (True, "schedule", False, False, False, False)


class _Actions:
    def __init__(self):
        self.calls = []

    def refresh(self, **kw):
        self.calls.append(("refresh", kw["trigger"]))
        return SimpleNamespace(ok=True, message="refresh 1: ok")

    def scheduled_run(self, **kw):
        self.calls.append(("report", kw["report_key"]))
        kw["log"]("OK printed")
        return 0


def _worker(tmp_path, acts):
    state = SimpleNamespace(settings=config.Settings(home=tmp_path), home=tmp_path,
                            now=lambda: datetime(2026, 9, 25, 14, tzinfo=TZ))
    return jobs.Worker(state, actions=acts)


def test_scheduled_refresh_records_as_schedule(tmp_path):
    acts = _Actions()
    w = _worker(tmp_path, acts)
    job = w.submit("scheduled-refresh")
    w.run_pending()
    assert acts.calls == [("refresh", "schedule")] and job.outcome == "OK"


def test_scheduled_report_runs_the_named_report(tmp_path):
    acts = _Actions()
    w = _worker(tmp_path, acts)
    job = w.submit("scheduled-report", report="open-work")
    w.run_pending()
    assert acts.calls == [("report", "open-work")] and job.outcome == "OK"


def test_neither_kind_can_be_started_from_the_open_route(tmp_path):
    assert {"scheduled-refresh", "scheduled-report"} <= set(jobs.GATED)
    assert not {"scheduled-refresh", "scheduled-report"} & set(jobs.OPEN_KINDS)
    seed(tmp_path).close()
    c = app_for(tmp_path)                                  # the kind check comes before the worker lookup
    for kind in ("scheduled-refresh", "scheduled-report"):
        assert c.post(f"/jobs/{kind}", headers=LOCAL_HOST_HEADERS).status_code == 404

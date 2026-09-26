# tests/test_clock.py
"""The server's own clock, driven one tick at a time: no thread, no sleep."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fridgesheet import config, host
from fridgesheet.web import clock as clockmod, db
from fridgesheet.web.stores import fires

TZ = ZoneInfo("America/New_York")


def at(d, h, mi=0):
    return datetime(2026, 9, d, h, mi, tzinfo=TZ)


def _write(home, doc):
    config.save_config_doc(home / "config.toml", doc)


class FakeWorker:
    def __init__(self, busy=False):
        self.busy, self.submitted = busy, []

    def submit(self, kind, **params):
        if self.busy:
            return None
        self.submitted.append((kind, params))
        return object()


def _clock(home, worker):
    db.open_db(home).close()
    state = SimpleNamespace(home=home)
    return clockmod.Clock(state, submit=worker.submit)


ON_2PM = {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]}}}


def _fired(home):
    conn = db.open_db(home)
    try:
        return fires.all(conn)
    finally:
        conn.close()


def test_first_sight_does_not_fire(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    assert c.tick(at(25, 16)) is None and w.submitted == []
    assert _fired(tmp_path) == {"open-work": at(25, 14)}


def test_a_due_slot_is_submitted_and_recorded(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))                                  # first sight: records Thursday's 14:00
    assert c.tick(at(25, 14)) == "open-work"
    assert w.submitted == [("scheduled-report", {"report": "open-work"})]
    assert _fired(tmp_path)["open-work"] == at(25, 14)


def test_busy_worker_defers_to_next_tick(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    w.busy = True
    assert c.tick(at(25, 14)) is None and _fired(tmp_path)["open-work"] == at(24, 14)
    w.busy = False
    assert c.tick(at(25, 14, 1)) == "open-work"


def test_a_restart_does_not_fire_the_same_slot_again(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    c.tick(at(25, 14))
    again = _clock(tmp_path, w)
    assert again.tick(at(25, 14, 5)) is None and len(w.submitted) == 1


def test_one_job_per_tick_refresh_first(tmp_path):
    _write(tmp_path, {**ON_2PM, "refresh": {"enabled": True, "every_hours": 1, "start": "13:00", "end": "14:00"}})
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    assert c.tick(at(25, 14)) == host.DATA_REFRESH_KEY
    assert c.tick(at(25, 14, 1)) == "open-work"
    assert [k for k, _ in w.submitted] == ["scheduled-refresh", "scheduled-report"]


def test_a_key_that_no_longer_resolves_is_ignored(tmp_path):
    _write(tmp_path, {"reports": {"view:42": {"enabled": True, "time": "14:00", "days": ["Fri"]}}})
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    assert c.tick(at(25, 14)) is None and w.submitted == [] and "view:42" not in _fired(tmp_path)


def test_a_broken_schedule_does_not_block_the_others(tmp_path):
    _write(tmp_path, {**ON_2PM, "refresh": {"enabled": True, "every_hours": 1, "start": "06:00", "end": "21:00"}})
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    assert host.DATA_REFRESH_KEY in c.problems             # 16 a day is over the cap of 12
    assert c.tick(at(25, 14)) == "open-work"


def test_a_raising_tick_is_logged_and_the_next_still_runs(tmp_path, caplog):
    (tmp_path / "config.toml").write_text("this is [not toml", encoding="utf-8")
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.safe_tick(at(25, 9))                                 # never raises
    assert "clock tick failed" in caplog.text and c.last_tick is None
    _write(tmp_path, ON_2PM)
    c.safe_tick(at(25, 10))
    assert c.last_tick == at(25, 10)


def test_the_heartbeat_goes_stale(tmp_path):
    _write(tmp_path, ON_2PM)
    c = _clock(tmp_path, FakeWorker())
    assert c.stale(at(25, 9))                              # never ticked
    c.tick(at(25, 9))
    assert not c.stale(at(25, 9, 2)) and c.stale(at(25, 9, 4))


def test_the_header_says_when_schedules_are_paused(tmp_path):
    from tests.web_fixtures import app_for, seed
    seed(tmp_path).close()
    c = app_for(tmp_path)
    stopped = _clock(tmp_path, FakeWorker())                # never ticked: stale
    c.app.state.fridgesheet.extra["clock"] = stopped
    assert clockmod.PAUSED in c.get("/").text


def test_remove_leftovers_keeps_failures_for_the_page(tmp_path):
    from fridgesheet.host.scheduling import Leftovers
    state = SimpleNamespace(extra={})
    got = Leftovers(removed=["Fridge Sheet - open-work"], failed=[("Fridge Sheet - data-refresh", "denied", "cmd")])
    clockmod.remove_leftovers(state, remove=lambda: got)
    assert state.extra["leftovers"] == [("Fridge Sheet - data-refresh", "denied", "cmd")]


def test_remove_leftovers_never_raises(tmp_path):
    state = SimpleNamespace(extra={})
    clockmod.remove_leftovers(state, remove=lambda: (_ for _ in ()).throw(OSError("no schtasks")))
    assert "leftovers" not in state.extra


def test_turning_a_schedule_back_on_does_not_fire_a_passed_slot(tmp_path):
    # Spec section 4: ticking a 2 PM report on at 3 PM must not print immediately -- even when
    # the report fired before it was switched off and its old row would say "fired Monday".
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(21, 9))                                      # Mon 21 Sep: first sight
    assert c.tick(at(21, 14)) == "open-work"
    _write(tmp_path, {"reports": {"open-work": {"enabled": False, "time": "14:00"}}})
    c.tick(at(22, 9))                                      # Tue: off, so its row goes
    assert "open-work" not in _fired(tmp_path)
    _write(tmp_path, ON_2PM)
    assert c.tick(at(25, 15)) is None and len(w.submitted) == 1   # Fri 15:00: on again
    assert _fired(tmp_path) == {"open-work": at(25, 14)}
    assert c.tick(at(28, 14)) == "open-work"               # next Mon 14:00 fires
    assert len(w.submitted) == 2


def test_a_reissued_view_id_does_not_inherit_an_old_fire(tmp_path):
    import json
    from fridgesheet.web.stores import reports as reports_store
    w = FakeWorker()
    c = _clock(tmp_path, w)
    conn = db.open_db(tmp_path)
    try:
        fires.record(conn, "view:1", at(21, 14))           # left by a report since deleted
    finally:
        conn.close()
    _write(tmp_path, {})
    c.tick(at(22, 9))                                      # a tick while view:1 is absent
    assert "view:1" not in _fired(tmp_path)
    name, definition = reports_store.TEMPLATES[0]
    conn = db.open_db(tmp_path)
    try:
        rid = reports_store.create(conn, name, json.dumps(definition), now="2026-09-25T08:00:00-04:00")
    finally:
        conn.close()
    assert rid == 1
    _write(tmp_path, {"reports": {"view:1": {"enabled": True, "time": "14:00", "days": ["Fri"]}}})
    assert c.tick(at(25, 15)) is None and w.submitted == []
    assert _fired(tmp_path)["view:1"] == at(25, 14)


def test_the_header_names_a_failing_tick(tmp_path):
    from tests.web_fixtures import app_for, seed
    seed(tmp_path).close()
    c = app_for(tmp_path)
    broken = _clock(tmp_path, FakeWorker())
    (tmp_path / "config.toml").write_text("this is [not toml", encoding="utf-8")
    broken.safe_tick(at(25, 9))
    assert broken.last_error
    c.app.state.fridgesheet.extra["clock"] = broken
    page = c.get("/").text
    assert clockmod.PAUSED not in page and "Schedules are paused: " in page

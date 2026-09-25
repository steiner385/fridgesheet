"""What the Schedules page does: config.toml in, config.toml out. Nothing here runs systemctl --
there is no OS scheduler left to call."""
from __future__ import annotations

import tomllib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fridgesheet import config
from fridgesheet.web import db, schedules, views
from fridgesheet.web.stores import reports as store, runs

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 25, 9, 0, tzinfo=TZ)          # a Friday


def _home(tmp_path: Path) -> Path:
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    return tmp_path


def test_rows_covers_every_report_with_its_next_and_last_run(tmp_path):
    home = _home(tmp_path)
    (home / "config.toml").write_text('[reports.open-work]\nenabled = true\ntime = "14:00"\ndays = ["Mon", "Fri"]\n')
    conn = db.open_db(home)
    runs.record(conn, "open-work", "2026-09-22T14:00:07-04:00", "2026-09-22T14:02:00-04:00", "schedule", "FAIL", "no printer")
    conn.close()
    got = {r.key: r for r in schedules.rows(home, now=NOW)}
    assert set(got) == {"open-work", "view:1"}
    assert got["open-work"].enabled and got["open-work"].days == ["Mon", "Fri"]
    assert got["open-work"].next_run == datetime(2026, 9, 25, 14, 0, tzinfo=TZ)
    assert got["open-work"].last_run == "Tue 9/22 2:00 PM, FAIL"
    assert got["view:1"].title == "Weekly summary"
    assert got["view:1"].time == "16:00"          # the view report's own default_time
    assert got["view:1"].enabled is False and got["view:1"].prints is True
    assert got["view:1"].next_run is None and got["view:1"].last_run == ""


def test_a_schedule_the_plan_cannot_run_carries_the_plans_problem(tmp_path, monkeypatch):
    """The row reads its problem from the same `clock.configured` the clock ticks on, so the
    page says why a schedule is not firing in the clock's own words."""
    from fridgesheet.web import clock
    home = _home(tmp_path)
    monkeypatch.setattr(clock, "configured", lambda h, settings=None: ([], {"open-work": "cannot run"}))
    row = {r.key: r for r in schedules.rows(home, now=NOW)}["open-work"]
    assert row.problem == "cannot run" and row.next_run is None


def test_last_scheduled_reads_only_scheduled_runs(tmp_path):
    conn = db.open_db(tmp_path)
    assert schedules.last_scheduled(conn, "open-work") == ""
    runs.record(conn, "open-work", "2026-09-24T14:00:05-04:00", "2026-09-24T14:01:00-04:00", "schedule", "OK", "printed")
    runs.record(conn, "open-work", "2026-09-24T16:00:00-04:00", "2026-09-24T16:01:00-04:00", "web", "FAIL", "x")
    runs.record(conn, "view:1", "2026-09-24T17:00:00-04:00", "2026-09-24T17:01:00-04:00", "schedule", "FAIL", "x")
    assert schedules.last_scheduled(conn, "open-work") == "Thu 9/24 2:00 PM, OK"
    conn.close()


def test_save_writes_the_config_and_nothing_else(tmp_path):
    home = _home(tmp_path)
    out = schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="Brother",
                         prints=False, home=home, log=lambda s: None)
    assert out.ok and not out.errors
    assert out.messages == ["Saved Weekly summary.", "Scheduled: Fri at 16:30, PDF only."]
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"] == {"enabled": True, "time": "16:30", "days": ["Fri"],
                                        "printer": "Brother", "print": False}


def test_turning_a_schedule_off_keeps_the_settings(tmp_path):
    home = _home(tmp_path)
    schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None)
    out = schedules.save("view:1", enabled=False, time="16:30", days=["Fri"], printer="Brother", prints=True,
                         home=home, log=lambda s: None)
    assert out.ok and "Weekly summary is not scheduled." in out.messages
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"]["enabled"] is False
    assert doc["reports"]["view:1"]["time"] == "16:30"     # kept, so turning it back on remembers


def test_a_bad_time_or_no_days_is_an_error_and_changes_nothing(tmp_path):
    home = _home(tmp_path)
    for kw, match in ((dict(time="2pm", days=["Fri"]), "HH:MM"), (dict(time="16:00", days=[]), "no days")):
        out = schedules.save("view:1", enabled=True, printer="", prints=True, home=home,
                             log=lambda s: None, **kw)
        assert not out.ok and any(match in e for e in out.errors)
    assert not (home / "config.toml").exists()


def test_an_unknown_report_is_refused(tmp_path):
    out = schedules.save("view:99", enabled=True, time="16:00", days=["Fri"], printer="", prints=True,
                         home=_home(tmp_path), log=lambda s: None)
    assert not out.ok and any("view:99" in e for e in out.errors)


def _scheduled(home, key="view:1"):
    schedules.save(key, enabled=True, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None)


def test_forget_drops_the_saved_settings(tmp_path):
    """The off switch keeps `[reports.<key>]` so turning it back on remembers; forgetting the
    report cannot, or the next report to take id 1 inherits this one's schedule."""
    home = _home(tmp_path)
    _scheduled(home)
    out = schedules.forget("view:1", home=home, log=lambda s: None)
    assert out.ok and out.messages == ["Its schedule was removed too."]
    doc = tomllib.loads((home / "config.toml").read_text())
    assert "view:1" not in doc.get("reports", {})


def test_forget_is_quiet_about_a_report_that_was_never_scheduled(tmp_path):
    """No `[reports.view:1]` table: nothing to remove, no message, and no file written."""
    home = _home(tmp_path)
    out = schedules.forget("view:1", home=home, log=lambda s: None)
    assert out.ok and out.messages == [] and not (home / schedules.CONFIG_NAME).exists()


# --- the app's own data refresh --------------------------------------------------------

def test_saving_the_refresh_writes_every_time(tmp_path):
    out = schedules.save_refresh(enabled=True, every_hours=3, start="06:00", end="12:00",
                                 days=["Mon", "Tue"], home=tmp_path, log=lambda _m: None)
    assert out.ok, out.errors
    assert out.messages[-1] == "Refreshing at 06:00, 09:00, 12:00 on Mon, Tue."
    doc = config.load_config_doc(tmp_path / schedules.CONFIG_NAME)
    assert doc["refresh"]["enabled"] is True and doc["refresh"]["every_hours"] == 3
    assert (doc["refresh"]["start"], doc["refresh"]["end"]) == ("06:00", "12:00")
    assert doc["refresh"]["days"] == ["Mon", "Tue"]


def test_disabling_the_refresh_keeps_the_settings(tmp_path):
    out = schedules.save_refresh(enabled=False, every_hours=4, start="07:00", end="19:00",
                                 days=["Mon"], home=tmp_path, log=lambda _m: None)
    assert out.ok and out.messages[-1] == "The data is not refreshed on a schedule."
    doc = config.load_config_doc(tmp_path / schedules.CONFIG_NAME)
    assert doc["refresh"]["every_hours"] == 4 and doc["refresh"]["enabled"] is False


def test_a_refusal_from_the_expansion_is_an_error_not_a_traceback(tmp_path):
    out = schedules.save_refresh(enabled=True, every_hours=1, start="00:00", end="23:00",
                                 days=["Mon"], home=tmp_path, log=lambda _m: None)
    assert not out.ok and any("12" in e for e in out.errors)
    assert not (tmp_path / schedules.CONFIG_NAME).exists()


def test_saving_the_refresh_leaves_a_report_schedule_alone(tmp_path):
    home = _home(tmp_path)
    _scheduled(home)
    schedules.save_refresh(enabled=True, every_hours=6, start="06:00", end="18:00",
                           days=["Mon"], home=home, log=lambda _m: None)
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"] == {"enabled": True, "time": "16:30", "days": ["Fri"],
                                        "printer": "Brother", "print": True}


def test_the_refresh_row_carries_next_and_last(tmp_path):
    schedules.save_refresh(enabled=True, every_hours=3, start="06:00", end="12:00",
                           days=["Fri"], home=tmp_path, log=lambda _m: None)
    conn = db.open_db(tmp_path)
    runs.record(conn, "refresh", "2026-09-25T06:00:02-04:00", "2026-09-25T06:04:00-04:00", "schedule", "OK", "ok")
    conn.close()
    row = schedules.refresh_row(tmp_path, now=NOW)
    assert row.next_run == datetime(2026, 9, 25, 12, 0, tzinfo=TZ)
    assert row.last_run == "Fri 9/25 6:00 AM, OK"


def test_a_report_may_not_claim_the_reserved_refresh_key(tmp_path):
    """config.toml is hand-editable, so a `[reports.data-refresh]` must be refused rather than
    written over the app's own refresh schedule."""
    out = schedules.save(key="Data-Refresh", enabled=True, time="14:00", days=["Mon"],
                         printer="", prints=True, home=tmp_path, log=lambda _m: None)
    assert not out.ok and any("reserved" in e.lower() for e in out.errors)
    assert not (tmp_path / schedules.CONFIG_NAME).exists()


def test_a_qr_that_cannot_be_drawn_leaves_the_settings_page_up(monkeypatch):
    """#8: the Settings page's QR is a convenience; `_lan_qr` swallows a drawing failure, and
    nothing pinned that it does."""
    from fridgesheet import qr
    from fridgesheet.web.routes import settings as settings_route
    monkeypatch.setattr(qr, "svg", lambda url: (_ for _ in ()).throw(RuntimeError("segno broke")))
    assert settings_route._lan_qr("http://192.168.1.50:8433/") is None
    assert settings_route._lan_qr(None) is None

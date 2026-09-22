"""What the Schedules page does, with the scheduler injected. Nothing here runs systemctl."""
from __future__ import annotations

import tomllib
from pathlib import Path

from fridgesheet import host
from fridgesheet.web import db, schedules, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import FakeScheduling


def _home(tmp_path: Path) -> Path:
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    (tmp_path / "login-ok.txt").write_text("ok")
    return tmp_path


def test_rows_covers_every_report_with_what_the_scheduler_says(tmp_path):
    home = _home(tmp_path)
    (home / "config.toml").write_text('[reports.open-work]\nenabled = true\ntime = "14:00"\ndays = ["Mon", "Fri"]\n')
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd", True, "Fri 14:00", None)})
    got = {r.key: r for r in schedules.rows(home, scheduling=sched)}
    assert set(got) == {"open-work", "view:1"}
    assert got["open-work"].enabled and got["open-work"].days == ["Mon", "Fri"]
    assert got["open-work"].info.next_run == "Fri 14:00"
    assert got["view:1"].title == "Weekly summary"
    assert got["view:1"].time == "16:00"          # the view report's own default_time
    assert got["view:1"].enabled is False and got["view:1"].prints is True


def test_a_host_with_no_scheduler_still_renders_every_row(tmp_path):
    class NoScheduling(FakeScheduling):
        def describe(self, key):
            raise host.NotSupported("this host does not schedule anything")

    got = schedules.rows(_home(tmp_path), scheduling=NoScheduling())
    assert [r.unsupported for r in got] == ["this host does not schedule anything"] * 2
    assert all(r.info is None for r in got)


def test_save_writes_the_config_and_installs(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling()
    out = schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="Brother",
                         prints=False, home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and not out.errors
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"] == {"enabled": True, "time": "16:30", "days": ["Fri"],
                                        "printer": "Brother", "print": False}
    assert sched.installed[0]["key"] == "view:1"
    assert sched.installed[0]["title"] == "Weekly summary"     # the unit's Description, not its name
    assert sched.installed[0]["days"] == ["Fri"]


def test_turning_a_schedule_off_removes_the_unit_and_keeps_the_settings(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling()
    schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None, scheduling=sched)
    schedules.save("view:1", enabled=False, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None, scheduling=sched)
    assert sched.removed == ["view:1"]
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"]["enabled"] is False
    assert doc["reports"]["view:1"]["time"] == "16:30"     # kept, so turning it back on remembers


def test_a_bad_time_or_no_days_is_an_error_and_changes_nothing(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling()
    for kw, match in ((dict(time="2pm", days=["Fri"]), "HH:MM"), (dict(time="16:00", days=[]), "no days")):
        out = schedules.save("view:1", enabled=True, printer="", prints=True, home=home,
                             log=lambda s: None, scheduling=sched, **kw)
        assert not out.ok and any(match in e for e in out.errors)
    assert not sched.installed and not (home / "config.toml").exists()


def test_an_unknown_report_is_refused(tmp_path):
    out = schedules.save("view:99", enabled=True, time="16:00", days=["Fri"], printer="", prints=True,
                         home=_home(tmp_path), log=lambda s: None, scheduling=FakeScheduling())
    assert not out.ok and any("view:99" in e for e in out.errors)


def test_a_scheduler_that_refuses_keeps_the_saved_settings(tmp_path):
    """The config is written before the scheduler is touched, so a systemctl that will not talk
    to the bus costs the install, never the parent's typing."""
    home = _home(tmp_path)
    sched = FakeScheduling(fail="Failed to connect to bus: No medium found")
    out = schedules.save("view:1", enabled=True, time="16:00", days=["Fri"], printer="", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert not out.ok
    assert any("No medium found" in e for e in out.errors)
    assert tomllib.loads((home / "config.toml").read_text())["reports"]["view:1"]["time"] == "16:00"


def test_removing_a_schedule_the_host_cannot_manage_keeps_the_saved_settings(tmp_path):
    """NotSupported on the remove() side of the off switch: same guarantee as the SchedulingError
    case below, the other exception type."""
    home = _home(tmp_path)
    sched = FakeScheduling(not_supported="this host does not schedule anything")
    out = schedules.save("view:1", enabled=False, time="16:30", days=["Fri"], printer="Brother", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert out.ok
    assert any("this host does not schedule anything" in m for m in out.messages)
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"]["enabled"] is False
    assert doc["reports"]["view:1"]["time"] == "16:30"


def test_a_scheduler_that_refuses_to_remove_keeps_the_saved_settings(tmp_path):
    """SchedulingError on the remove() side of the off switch: the mirror of
    test_a_scheduler_that_refuses_keeps_the_saved_settings, which only covers install()."""
    home = _home(tmp_path)
    sched = FakeScheduling(fail="Failed to connect to bus: No medium found")
    out = schedules.save("view:1", enabled=False, time="16:30", days=["Fri"], printer="Brother", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert not out.ok
    assert any("No medium found" in e for e in out.errors)
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"]["enabled"] is False
    assert doc["reports"]["view:1"]["time"] == "16:30"


def test_installing_on_a_host_that_cannot_schedule_keeps_the_saved_settings(tmp_path):
    """NotSupported on the install() side: the settings are still saved even though this host
    (e.g. Linux, where scheduling stays with a hand-installed systemd timer) never gets a unit."""
    home = _home(tmp_path)
    sched = FakeScheduling(not_supported="this host does not schedule anything")
    out = schedules.save("view:1", enabled=True, time="16:00", days=["Fri"], printer="", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert out.ok
    assert any("this host does not schedule anything" in m for m in out.messages)
    assert tomllib.loads((home / "config.toml").read_text())["reports"]["view:1"]["time"] == "16:00"


def test_a_schedule_waits_for_a_passing_test_login(tmp_path):
    """Same gate the Settings page has always had: a schedule that runs before the credentials
    work just fails every afternoon in the background."""
    home = _home(tmp_path)
    (home / "login-ok.txt").unlink()
    sched = FakeScheduling()
    out = schedules.save("open-work", enabled=True, time="14:00", days=["Mon"], printer="", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and not sched.installed
    assert any("Test login" in m for m in out.messages)


def test_save_refuses_a_schedule_this_app_did_not_write(tmp_path):
    """The disabled checkbox on an unmanageable row is a hint, not a guard. A POST with
    `enabled` simply absent used to take the off branch, swallow "does not exist" from
    systemctl and answer "Open Work Sheet is not scheduled" -- while the hand-written
    fridgesheet-print-sheet.timer kept printing at 2 PM, as the same page's own state line said."""
    home = _home(tmp_path)
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd (hand-written)", True, "Wed 14:00", None, False)})
    for enabled in (True, False):
        out = schedules.save("open-work", enabled=enabled, time="14:00", days=["Mon"], printer="", prints=True,
                             home=home, log=lambda s: None, scheduling=sched)
        assert not out.ok
        assert any("did not write" in e and "Wed 14:00" in e for e in out.errors)
        # #36: the message must name the unit actually in the way, not a hardcoded
        # "fridgesheet-print-sheet.timer" that happens to be right only for "open-work".
        assert any("fridgesheet-print-sheet.timer" in e for e in out.errors)
    assert not sched.installed and not sched.removed
    assert not (home / schedules.CONFIG_NAME).exists()        # nor is the file told a different story


def test_save_refuses_a_schedule_this_app_did_not_write_naming_a_non_open_work_key(tmp_path):
    """The same refusal for a saved report (key `view:1`, not `open-work`) must name *its own*
    unit -- `fridgesheet-view-1.timer` -- not the print-sheet timer the old hardcoded message always
    named regardless of which report was blocked (#36)."""
    home = _home(tmp_path)
    sched = FakeScheduling({"view:1": host.ScheduleInfo("systemd (hand-written)", True, "Fri 16:30", None, False)})
    out = schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert not out.ok
    assert any("fridgesheet-view-1.timer" in e for e in out.errors)
    assert not any("fridgesheet-print-sheet.timer" in e for e in out.errors)


def _scheduled(home, sched, key="view:1"):
    schedules.save(key, enabled=True, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None, scheduling=sched)


def test_forget_removes_the_unit_and_drops_the_saved_settings(tmp_path):
    """The off switch keeps `[reports.<key>]` so turning it back on remembers; forgetting the
    report cannot, or the next report to take id 1 inherits this one's schedule."""
    home = _home(tmp_path)
    sched = FakeScheduling()
    _scheduled(home, sched)
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and sched.removed == ["view:1"]
    doc = tomllib.loads((home / "config.toml").read_text())
    assert "view:1" not in doc.get("reports", {})


def test_forget_reports_a_removal_that_failed_and_keeps_the_settings(tmp_path):
    home = _home(tmp_path)
    _scheduled(home, FakeScheduling())
    sched = FakeScheduling(fail="Failed to connect to bus: No medium found")
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert not out.ok and any("No medium found" in e for e in out.errors)
    assert tomllib.loads((home / "config.toml").read_text())["reports"]["view:1"]["enabled"] is True


def test_forget_on_a_host_that_schedules_nothing_still_drops_the_settings(tmp_path):
    home = _home(tmp_path)
    _scheduled(home, FakeScheduling())
    sched = FakeScheduling(not_supported="this host does not schedule anything")
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert out.ok
    assert "view:1" not in tomllib.loads((home / "config.toml").read_text()).get("reports", {})


def test_forget_is_quiet_about_a_report_that_was_never_scheduled(tmp_path):
    """No `[reports.view:1]` table and `describe` already says `installed=False`
    (`FakeScheduling`'s default): there is nothing for the host or the file to remove, so
    `remove()` is never called at all -- not called-and-happens-to-succeed."""
    home = _home(tmp_path)
    sched = FakeScheduling()
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and sched.removed == [] and not (home / schedules.CONFIG_NAME).exists()


def test_forget_skips_the_remove_call_for_a_report_the_scheduler_cannot_confirm_either(tmp_path):
    """#36: a server started outside a user D-Bus session cannot delete a brand-new report's
    schedule -- `remove()` would call systemctl, which cannot reach the bus, and the page
    would blame a schedule that never existed. `describe` still answers `installed=False`
    even with the bus unreachable (`_is_enabled` treats any non-zero `is-enabled` as "no"), so
    with no `[reports.<key>]` table either, `forget` must skip the `remove()` call entirely
    rather than let it fail."""
    home = _home(tmp_path)
    sched = FakeScheduling(fail="Failed to connect to bus: No medium found")
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and not out.errors and sched.removed == []


def test_forget_treats_not_supported_from_describe_as_confirmed_nothing_installed(tmp_path):
    """`_installed_or_unknown`'s `NotSupported` branch, exercised directly: a host that cannot
    schedule anything at all answers exactly like a report that was never scheduled -- skip
    `remove()`, same as the sibling test above.

    This pins the branch's polarity (`NotSupported` -> "confirmed nothing there", not "who
    knows") against an injected `describe` that raises. It is not coverage of live behaviour:
    nothing under `fridgesheet/host/` raises `NotSupported` for scheduling -- both platforms
    have a real implementation -- so what runs here is `FakeScheduling(describe_error=...)`'s
    contract. The handler stays because it is cheap insurance for a third platform, and this
    test says which way it must fall when one appears."""
    home = _home(tmp_path)
    sched = FakeScheduling(describe_error=host.NotSupported("this host does not schedule anything"))
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and not out.errors and sched.removed == []


def test_forget_still_tries_remove_when_describe_fails_for_an_unexplained_reason(tmp_path):
    """`_installed_or_unknown`'s other branch: an *unexplained* `describe()` failure (not
    `NotSupported`) must read as "maybe installed", not "confirmed nothing there" -- the
    opposite polarity from the test above. Getting this backwards would silently skip
    `remove()` for a report that really might still be scheduled, on nothing more than a
    `describe()` call that happened to raise. `sched.removed` proves `remove()` still ran."""
    home = _home(tmp_path)
    sched = FakeScheduling(describe_error=RuntimeError("systemctl exploded"))
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and sched.removed == ["view:1"]


def test_forget_refuses_a_schedule_this_app_did_not_write(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling({"view:1": host.ScheduleInfo("systemd (hand-written)", True, "Fri 16:30", None, False)})
    out = schedules.forget("view:1", home=home, log=lambda s: None, scheduling=sched)
    assert not out.ok and sched.removed == []
    assert any("did not write" in e for e in out.errors)


# --- the app's own data refresh --------------------------------------------------------

def test_saving_the_refresh_installs_one_task_with_every_time(tmp_path):
    from fridgesheet.web import schedules
    (tmp_path / schedules.LOGIN_STAMP).write_text("ok")
    fake = FakeScheduling()
    out = schedules.save_refresh(enabled=True, every_hours=3, start="06:00", end="12:00",
                                 days=["Mon", "Tue"], home=tmp_path, log=lambda _m: None,
                                 scheduling=fake)
    assert out.ok, out.errors
    assert len(fake.installed) == 1
    assert fake.installed[0]["key"] == "data-refresh"
    assert fake.installed[0]["times"] == ["06:00", "09:00", "12:00"]


def test_disabling_the_refresh_removes_the_task_and_keeps_the_settings(tmp_path):
    from fridgesheet import config
    from fridgesheet.web import schedules
    fake = FakeScheduling()
    schedules.save_refresh(enabled=False, every_hours=4, start="07:00", end="19:00",
                           days=["Mon"], home=tmp_path, log=lambda _m: None, scheduling=fake)
    assert fake.removed == ["data-refresh"]
    doc = config.load_config_doc(tmp_path / schedules.CONFIG_NAME)
    assert doc["refresh"]["every_hours"] == 4 and doc["refresh"]["enabled"] is False


def test_a_refusal_from_the_expansion_is_an_error_not_a_traceback(tmp_path):
    from fridgesheet.web import schedules
    fake = FakeScheduling()
    out = schedules.save_refresh(enabled=True, every_hours=1, start="00:00", end="23:00",
                                 days=["Mon"], home=tmp_path, log=lambda _m: None, scheduling=fake)
    assert not out.ok and any("12" in e for e in out.errors)
    assert fake.installed == []


def test_saving_the_refresh_leaves_a_report_schedule_alone(tmp_path):
    from fridgesheet.web import schedules
    (tmp_path / schedules.LOGIN_STAMP).write_text("ok")
    fake = FakeScheduling()
    schedules.save_refresh(enabled=True, every_hours=6, start="06:00", end="18:00",
                           days=["Mon"], home=tmp_path, log=lambda _m: None, scheduling=fake)
    assert [i["key"] for i in fake.installed] == ["data-refresh"]
    assert fake.removed == []


def test_a_report_may_not_claim_the_reserved_refresh_key(tmp_path):
    """config.toml is hand-editable and `schedule remove --all` feeds keys straight off
    disk, so a `[reports.data-refresh]` must be refused rather than installed over the
    app's own task."""
    from fridgesheet.web import schedules
    fake = FakeScheduling()
    out = schedules.save(key="Data-Refresh", enabled=True, time="14:00", days=["Mon"],
                         printer="", prints=True, home=tmp_path, log=lambda _m: None,
                         scheduling=fake)
    assert not out.ok and any("reserved" in e.lower() for e in out.errors)
    assert fake.installed == []

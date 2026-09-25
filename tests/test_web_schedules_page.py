"""The Schedules page. The scheduler is a fake on `state.extra`, as the Settings page's is."""
from __future__ import annotations

import tomllib

from fastapi.testclient import TestClient

from fridgesheet import config, host
from fridgesheet.web import app as webapp, db, views
from fridgesheet.web.routes import schedules as routes_schedules
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import LOCAL_HOST_HEADERS, FakeScheduling, app_for, seed


def test_days_is_hosts_day_names_not_a_fourth_spelling():
    """`_DAY_TAGS`'s keys (Windows), `host.DAY_NAMES` and this module's `DAYS` used to be three
    spellings of the same seven abbreviations (#31-#36 roll-up). Identity, not just equality,
    so a future edit to `DAY_NAMES` cannot leave a separately-hardcoded `DAYS` silently out of
    step -- equal-by-value would not have caught that."""
    assert routes_schedules.DAYS is host.DAY_NAMES


def _client(tmp_path, sched=None):
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    (tmp_path / "login-ok.txt").write_text("ok")
    s = config.Settings(home=tmp_path)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.extra["scheduling"] = sched or FakeScheduling()
    application.state.fridgesheet.extra["printers"] = ["Brother", "Canon"]
    return TestClient(application, headers=LOCAL_HOST_HEADERS), application


def test_the_page_lists_every_report_with_its_state(tmp_path):
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd", True, "Wed 14:00", None)})
    c, _ = _client(tmp_path, sched)
    body = c.get("/schedules").text
    assert "Open Work Sheet" in body and "Weekly summary" in body
    assert "Wed 14:00" in body
    assert 'value="open-work"' in body and 'value="view:1"' in body
    assert '<option value="Brother"' in body                  # the printer list is offered
    assert 'name="days" value="Mon"' in body


def test_saving_a_schedule_installs_it_and_says_so(tmp_path):
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Mon", "Fri"], "printer": "Brother", "prints": "on"})
    assert r.status_code == 200
    assert "Scheduled: Mon, Fri at 16:30" in r.text
    assert sched.installed[0]["key"] == "view:1"
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["view:1"]["days"] == ["Mon", "Fri"]


def test_a_pdf_only_schedule_says_so_on_the_page(tmp_path):
    c, _ = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Fri"], "printer": "", "prints": ""})
    assert "PDF only" in r.text


def test_a_bad_time_comes_back_as_an_error_not_a_crash(tmp_path):
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "half four",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "HH:MM" in r.text
    assert not sched.installed


def test_a_hand_written_timer_is_shown_but_not_offered_for_removal(tmp_path):
    """The app reports Tony's own fridgesheet-print-sheet.timer and gives no button that would
    delete a unit it did not write."""
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd (hand-written)", True, "Wed 14:00", None, False)})
    c, _ = _client(tmp_path, sched)
    body = c.get("/schedules").text
    assert "hand-written" in body
    assert "written outside this app" in body                 # the explanation, in the row

    # ...and a POST that skips the disabled controls entirely is refused on the server, rather
    # than answering "not scheduled" while the timer keeps printing at 2 PM.
    r = c.post("/schedules", data={"key": "open-work", "time": "14:00", "days": ["Mon"],
                                   "printer": "", "prints": "on"})
    assert r.status_code == 200 and "did not write" in r.text
    assert sched.removed == [] and sched.installed == []
    assert not (tmp_path / "config.toml").exists()


def test_an_unknown_key_is_a_bad_request_not_a_500(tmp_path):
    c, _ = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:404", "enabled": "on", "time": "16:00",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "view:404" in r.text


def test_the_nav_links_to_it(tmp_path):
    c, _ = _client(tmp_path)
    assert 'href="/schedules"' in c.get("/").text


def test_a_stored_printer_no_longer_offered_still_renders_selected_and_round_trips(tmp_path):
    """A printer removed from CUPS (or a `printer_names` that could not be read) must not make
    the select fall back to the shared printer and silently blank a saved schedule's printer."""
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)      # extra["printers"] is ["Brother", "Canon"]
    c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                               "days": ["Fri"], "printer": "OldPrinter", "prints": "on"})
    body = c.get("/schedules").text
    assert 'value="OldPrinter" selected' in body
    assert "not currently listed" in body
    # Saving exactly what the rendered form would submit (the selected option) must not change
    # the stored printer.
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Fri"], "printer": "OldPrinter", "prints": "on"})
    assert r.status_code == 200
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["view:1"]["printer"] == "OldPrinter"


class _NoScheduler(FakeScheduling):
    """A host with no scheduling adapter at all: every `describe()` refuses."""
    def describe(self, key):
        raise host.NotSupported("scheduling is not available on this host")


def test_a_host_with_no_scheduler_says_so_on_every_row(tmp_path):
    c, _ = _client(tmp_path, _NoScheduler())
    body = c.get("/schedules").text
    assert "scheduling is not available on this host" in body


def test_the_page_shows_the_refresh_editor_with_its_expanded_times(tmp_path):
    body = app_for(tmp_path).get("/schedules").text
    assert "Refresh the data" in body
    assert 'name="every_hours"' in body and 'name="start"' in body and 'name="end"' in body
    assert 'hx-post="/schedules/refresh"' in body


def test_a_junk_every_hours_does_not_500(tmp_path):
    """`int(form.get("every_hours") or 3)` used to raise `ValueError` straight out of the
    route for anything that is not an integer -- a 500, where every neighbouring field
    (start/end/days) degrades instead of failing outright. A junk value falls back to the
    same default (3) the field itself defaults to."""
    c, _ = _client(tmp_path)
    r = c.post("/schedules/refresh", data={"every_hours": "not-a-number", "start": "06:00",
                                           "end": "21:00", "days": ["Mon"]})
    assert r.status_code == 200
    assert "Traceback" not in r.text
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["refresh"]["every_hours"] == 3


def test_the_header_still_says_when_the_data_was_refreshed(tmp_path):
    """#141: the page passed the refresh *schedule* as `refresh`, the name `_header.html` reads
    the last refresh from -- so this was the one page whose header said "Refreshed" and no time."""
    c, _ = _client(tmp_path)
    body = c.get("/schedules").text
    assert "Refreshed Tue 9/15 1:50 PM" in body
    assert "Refresh on a schedule" in body                    # the schedule editor still renders


# --- #120: a scheduled report prints from the last refresh, so scheduling one keeps the refresh on ----

def _refresh_installs(sched):
    return [i for i in sched.installed if i["key"] == host.DATA_REFRESH_KEY]


def test_saving_an_enabled_report_turns_on_the_data_refresh_with_defaults(tmp_path):
    """A scheduled report runs `--no-refresh` and refuses a snapshot older than a day, so a
    household that schedules a report without the refresh gets one sheet and then a daily
    FAIL (#120). Saving an enabled report with the refresh off turns the refresh on, with
    the defaults, and says so."""
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Mon", "Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200
    assert "Scheduled: Mon, Fri at 16:30" in r.text
    assert "Turned on the data refresh too" in r.text
    assert "every 3 hours" in r.text
    installs = _refresh_installs(sched)
    assert len(installs) == 1
    assert installs[0]["times"] == ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]
    assert installs[0]["days"] == list(host.DAY_NAMES)
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["refresh"]["enabled"] is True
    assert doc["reports"]["view:1"]["enabled"] is True
    assert "data refresh is off" not in c.get("/schedules").text        # nothing left to warn about


def test_saving_a_report_leaves_an_already_on_refresh_alone(tmp_path):
    """The parent's own refresh settings (every 2 hours, weekdays) are never overwritten with
    the defaults, and the refresh task is not reinstalled on every report save."""
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    c.post("/schedules/refresh", data={"enabled": "on", "every_hours": "2", "start": "07:00",
                                       "end": "19:00", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]})
    assert len(_refresh_installs(sched)) == 1
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert "Turned on the data refresh" not in r.text
    assert len(_refresh_installs(sched)) == 1                            # still the one from the parent's save
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["refresh"]["every_hours"] == 2 and doc["refresh"]["days"] == ["Mon", "Tue", "Wed", "Thu", "Fri"]


def test_turning_a_report_off_never_touches_the_refresh(tmp_path):
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "time": "16:30", "days": ["Fri"],
                                   "printer": "", "prints": "on"})
    assert r.status_code == 200 and "not scheduled" in r.text
    assert _refresh_installs(sched) == []
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert "refresh" not in doc


def test_a_refresh_that_will_not_install_is_an_error_beside_the_saved_report(tmp_path):
    """The report's own schedule is in; the refresh could not be. Both facts on the page."""
    class _RefreshFails(FakeScheduling):
        def install(self, key, times, days, exe, args, workdir, **kw):
            if key == host.DATA_REFRESH_KEY:
                raise host.SchedulingError("no bus")
            super().install(key, times, days, exe, args, workdir, **kw)

    sched = _RefreshFails()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200
    assert "Scheduled: Fri at 16:30" in r.text
    assert "no bus" in r.text and "data refresh" in r.text
    assert sched.installed[0]["key"] == "view:1"


def test_the_page_warns_when_a_report_is_scheduled_and_the_refresh_is_off(tmp_path):
    c, _ = _client(tmp_path)
    assert "data refresh is off" not in c.get("/schedules").text          # nothing scheduled: no warning
    (tmp_path / "config.toml").write_text('[reports."view:1"]\nenabled = true\ntime = "16:30"\ndays = ["Fri"]\n')
    body = c.get("/schedules").text
    assert "data refresh is off" in body
    assert "Weekly summary" in body.split("data refresh is off")[0]       # names the report(s) affected
    (tmp_path / "config.toml").write_text('[refresh]\nenabled = true\n[reports."view:1"]\nenabled = true\ntime = "16:30"\ndays = ["Fri"]\n')
    assert "data refresh is off" not in c.get("/schedules").text


def test_the_page_no_longer_claims_a_scheduled_report_refreshes(tmp_path):
    """schedules.html said "it refreshes, builds, and prints"; it never refreshed (#120)."""
    body = app_for(tmp_path).get("/schedules").text
    assert "it refreshes, builds, and prints" not in body
    assert "does not refresh first" in body


# --- #121: a report's time on a refresh time is a note, never an error -----------------------

_REFRESH_EVERY_2H = {"enabled": "on", "every_hours": "2", "start": "06:00", "end": "21:00", "days": ["Mon", "Fri"]}


def test_saving_a_report_at_a_refresh_time_says_the_report_will_wait(tmp_path):
    c, _ = _client(tmp_path, FakeScheduling())
    c.post("/schedules/refresh", data=_REFRESH_EVERY_2H)                  # 06:00, 08:00, ..., 14:00, ..., 20:00
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "14:00",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "Scheduled: Fri at 14:00" in r.text
    assert "This report and the data refresh both run at 14:00; the report will wait for the refresh." in r.text
    # Between refreshes, or on a day the refresh does not run, there is nothing to say.
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "14:05",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert "both run at" not in r.text
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "14:00",
                                   "days": ["Sat"], "printer": "", "prints": "on"})
    assert "both run at" not in r.text


def test_saving_a_refresh_that_lands_on_a_scheduled_reports_time_says_so(tmp_path):
    c, _ = _client(tmp_path, FakeScheduling())
    c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "14:00",
                               "days": ["Fri"], "printer": "", "prints": "on"})
    r = c.post("/schedules/refresh", data=_REFRESH_EVERY_2H)
    assert r.status_code == 200
    assert "Weekly summary and the data refresh both run at 14:00; the report will wait for the refresh." in r.text
    r = c.post("/schedules/refresh", data={**_REFRESH_EVERY_2H, "every_hours": "3"})   # 06, 09, 12, 15, 18, 21
    assert "both run at" not in r.text

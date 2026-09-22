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

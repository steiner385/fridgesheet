"""The Schedules page. Saving writes config.toml and nothing else; the server's own clock runs it."""
from __future__ import annotations

import tomllib
from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet import host
from fridgesheet.web import db, views
from fridgesheet.web.routes import schedules as routes_schedules
from fridgesheet.web.stores import reports as store, runs
from tests.web_fixtures import NOW, app_for, seed

TZ = ZoneInfo("America/New_York")


def test_days_is_hosts_day_names_not_a_fourth_spelling():
    """`_DAY_TAGS`'s keys (Windows), `host.DAY_NAMES` and this module's `DAYS` used to be three
    spellings of the same seven abbreviations (#31-#36 roll-up). Identity, not just equality,
    so a future edit to `DAY_NAMES` cannot leave a separately-hardcoded `DAYS` silently out of
    step -- equal-by-value would not have caught that."""
    assert routes_schedules.DAYS is host.DAY_NAMES


def _client(tmp_path, now=None):
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    c = app_for(tmp_path, now=now or datetime(2026, 9, 25, 9, 0, tzinfo=TZ))
    c.app.state.fridgesheet.extra["printers"] = ["Brother", "Canon"]
    return c


def test_saving_writes_config_and_names_the_next_run(tmp_path):
    c = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Mon", "Fri"], "printer": "Brother", "prints": "on"})
    assert r.status_code == 200 and "Scheduled: Mon, Fri at 16:30" in r.text
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["view:1"] == {"enabled": True, "time": "16:30", "days": ["Mon", "Fri"],
                                        "printer": "Brother", "print": True}
    assert "next: Fri 9/25 4:30 PM" in r.text


def test_saving_needs_no_test_login(tmp_path):
    c = _client(tmp_path)                                  # no login-ok.txt written
    r = c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    assert "Test login" not in r.text and "Scheduled: Fri at 14:00" in r.text


def test_a_schedule_that_never_ran_says_so(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    assert "has not run on a schedule yet" in c.get("/schedules").text


def test_the_last_scheduled_run_is_shown(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Thu", "Fri"]})
    conn = db.open_db(tmp_path)
    runs.record(conn, "open-work", "2026-09-24T14:00:05-04:00", "2026-09-24T14:01:30-04:00", "schedule", "OK", "printed")
    runs.record(conn, "open-work", "2026-09-24T15:00:00-04:00", "2026-09-24T15:01:00-04:00", "web", "OK", "printed")
    conn.close()
    assert "last: Thu 9/24 2:00 PM, OK" in c.get("/schedules").text


def test_the_refresh_row_shows_next_and_last(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules/refresh", data={"enabled": "on", "every_hours": "2", "start": "05:00", "end": "21:00",
                                       "days": list(host.DAY_NAMES)})
    body = c.get("/schedules").text
    assert "next: Fri 9/25 11:00 AM" in body and "has not run on a schedule yet" in body


def test_turning_off_needs_no_day_and_touches_nothing_else(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    r = c.post("/schedules", data={"key": "open-work", "time": "14:00"})
    assert "Open Work Sheet is not scheduled." in r.text
    assert tomllib.loads((tmp_path / "config.toml").read_text())["reports"]["open-work"]["enabled"] is False


def test_linux_without_the_service_says_how_to_keep_schedules_running(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seed(tmp_path).close()
    c = app_for(tmp_path, service_installed=False)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    assert "fridgesheet service install" in c.get("/schedules").text


def test_no_service_hint_when_nothing_is_scheduled(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seed(tmp_path).close()
    assert "fridgesheet service install" not in app_for(tmp_path, service_installed=False).get("/schedules").text


def test_the_page_lists_every_report_with_its_state(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    body = c.get("/schedules").text
    assert "Open Work Sheet" in body and "Weekly summary" in body
    assert "next: Fri 9/25 2:00 PM" in body                   # open-work, from the plan
    assert "not scheduled" in body                            # view:1, never saved
    assert 'value="open-work"' in body and 'value="view:1"' in body
    assert '<option value="Brother"' in body                  # the printer list is offered
    assert 'name="days" value="Mon"' in body


def test_a_pdf_only_schedule_says_so_on_the_page(tmp_path):
    c = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Fri"], "printer": "", "prints": ""})
    assert "PDF only" in r.text


def test_a_bad_time_comes_back_as_an_error_not_a_crash(tmp_path):
    c = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "half four",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "HH:MM" in r.text
    assert not (tmp_path / "config.toml").exists()


def test_an_unknown_key_is_a_bad_request_not_a_500(tmp_path):
    c = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:404", "enabled": "on", "time": "16:00",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "view:404" in r.text


def test_the_nav_links_to_it(tmp_path):
    c = _client(tmp_path)
    assert 'href="/schedules"' in c.get("/").text


def test_a_stored_printer_no_longer_offered_still_renders_selected_and_round_trips(tmp_path):
    """A printer removed from CUPS (or a `printer_names` that could not be read) must not make
    the select fall back to the shared printer and silently blank a saved schedule's printer."""
    c = _client(tmp_path)      # extra["printers"] is ["Brother", "Canon"]
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
    c = _client(tmp_path)
    r = c.post("/schedules/refresh", data={"every_hours": "not-a-number", "start": "06:00",
                                           "end": "21:00", "days": ["Mon"]})
    assert r.status_code == 200
    assert "Traceback" not in r.text
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["refresh"]["every_hours"] == 3


def test_the_header_still_says_when_the_data_was_refreshed(tmp_path):
    """#141: the page passed the refresh *schedule* as `refresh`, the name `_header.html` reads
    the last refresh from -- so this was the one page whose header said "Refreshed" and no time."""
    c = _client(tmp_path, now=NOW)
    body = c.get("/schedules").text
    assert "Refreshed Tue 9/15 1:50 PM" in body
    assert "Refresh on a schedule" in body                    # the schedule editor still renders


def test_a_leftover_that_could_not_be_removed_is_named_with_its_command(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.app.state.fridgesheet.extra["leftovers"] = [
        ("Fridge Sheet - data-refresh", "Access is denied.", 'schtasks /Delete /TN "Fridge Sheet - data-refresh" /F')]
    body = c.get("/schedules").text
    assert "Fridge Sheet - data-refresh" in body and "schtasks /Delete" in body


def test_a_leftover_listing_that_failed_says_so_in_plain_words(tmp_path):
    """A failed listing has no task name and no command: it gets its own line, never
    "Remove it with: " followed by nothing."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.app.state.fridgesheet.extra["leftovers"] = [
        ("the list of scheduled tasks", "schtasks /Query failed: Access is denied.", "")]
    body = c.get("/schedules").text
    assert "could not check for old scheduled tasks from an earlier version" in body
    assert "Access is denied." in body
    assert "Remove it with" not in body and "the list of scheduled tasks" not in body

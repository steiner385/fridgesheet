"""Schedules as the household's timetable (the Student Planner; the surface brief in
.impeccable/surfaces/, 2026-10-01): the refresh and each report as ruled sections parted by the
printed rule, the time at Display size at the head's right, one pencil line for the days, the
next run and the last with the Runs word, the fields label over control, one Save each."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fridgesheet import host
from fridgesheet.web import db, schedules, views
from fridgesheet.web.stores import reports as store, runs
from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")
TZ = ZoneInfo("America/New_York")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _client(tmp_path):
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    runs.record(conn, "open-work", "2026-09-24T14:00:05-04:00", "2026-09-24T14:01:30-04:00", "schedule", "OK", "printed")
    conn.close()
    c = app_for(tmp_path, now=datetime(2026, 9, 25, 9, 0, tzinfo=TZ))
    c.app.state.fridgesheet.extra["printers"] = ["Brother"]
    return c


def test_the_words_of_the_timetable():
    assert schedules.clock_words("14:00") == "2:00 PM" and schedules.clock_words("05:00") == "5:00 AM"
    assert schedules.clock_words("00:30") == "12:30 AM" and schedules.clock_words("half four") == "half four"
    assert schedules.days_words(list(host.DAY_NAMES)) == "every day"
    assert schedules.days_words(["Mon", "Tue", "Wed", "Thu", "Fri"]) == "Mon–Fri"
    assert schedules.days_words(["Sat", "Sun"]) == "weekends"
    assert schedules.days_words(["Fri", "Mon", "Wed"]) == "Mon, Wed, Fri"       # the week's order, not the form's
    assert schedules.days_words(["Tue", "Wed", "Thu"]) == "Tue–Thu" and schedules.days_words([]) == "no days"


def test_each_schedule_is_a_ruled_section_with_its_time_at_the_heads_right(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules/refresh", data={"enabled": "on", "every_hours": "2", "start": "05:00", "end": "21:00", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]})
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Thu", "Fri"], "prints": "on"})
    body = c.get("/schedules").text
    forms = re.findall(r'<form[^>]*class="sec schedule">', body)
    assert len(forms) == 3 and "<h4" not in body and 'class="card' not in body.split('class="page-head"')[1]
    assert re.search(r'<div class="sec-head"><h3>Refresh the data</h3>\s*<span class="when"><span class="big">every 2 hours</span> <span class="muted">5:00 AM–9:00 PM</span></span>', body)
    assert re.search(r'<p class="sched-line muted">Mon–Fri · next: Fri 9/25 11:00 AM · has not run on a schedule yet</p>', body)
    assert re.search(r'<div class="sec-head"><h3 title="open-work">Open Work Sheet</h3>\s*<span class="when"><span class="big">2:00 PM</span></span>', body)
    assert re.search(r'<p class="sched-line muted">Thu, Fri · next: Fri 9/25 2:00 PM · last: Thu 9/24 2:00 PM, <span class="word outcome ok">OK</span></p>', body)
    # An unscheduled report says so in pencil where the numeral would be, and its line is just its days.
    assert re.search(r'<h3 title="view:1">Weekly summary</h3>\s*<span class="when"><span class="muted">not scheduled</span></span>', body)
    assert body.count('<p class="form-save"><button class="primary">Save</button></p>') == 3
    assert re.findall(r"<legend>([^<]*)</legend>", body) == ["Days", "Days", "Days"]
    assert body.count('<div class="settings-grid">') == 3


def test_a_failed_last_run_wears_the_runs_word_and_a_problem_is_red_pen(tmp_path):
    c = _client(tmp_path)
    conn = db.open_db(tmp_path)
    runs.record(conn, "open-work", "2026-09-25T07:00:00-04:00", "2026-09-25T07:00:30-04:00", "schedule", "FAIL", "printer offline")
    conn.close()
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"], "prints": "on"})
    body = c.get("/schedules").text
    assert 'last: Fri 9/25 7:00 AM, <span class="word outcome fail">FAIL</span>' in body
    assert "font-weight: 700" in _rule(".run .outcome, .report .outcome, .check .outcome, .sched-line .outcome")
    assert "background: var(--hl-red)" in _rule(".run .outcome.fail, .report .outcome.fail, .check .outcome.fail, .sched-line .outcome.fail")


def test_a_last_run_without_its_word_is_not_a_template_error():
    assert schedules._last_words("Thu 9/24 2:00 PM, OK") == ("Thu 9/24 2:00 PM", "OK")
    assert schedules._last_words("Thu 9/24 2:00 PM") == ("Thu 9/24 2:00 PM", "") and schedules._last_words("") == ("", "")


def test_the_timetable_is_drawn_in_the_planners_rules():
    assert "margin-left: auto" in _rule(".schedule .sec-head .when")
    assert "border-top: 1.5px solid var(--box)" in _rule(".timetable > form.sec + form.sec")        # the printed rule between schedules
    assert "max-width: var(--measure)" in _rule(".schedule")
    assert "font-size: 28px" in _rule(".big")                                                       # Display size, as the grade strip
    assert ".schedule h4" not in CSS and ".schedule > .tick" not in CSS and ".schedule .sched-line .outcome" not in CSS
    assert "68ch" in _rule(".schedule > .field-help")

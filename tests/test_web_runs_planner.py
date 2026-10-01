"""Runs as the sheet's own log (the Student Planner; the surface brief in .impeccable/surfaces/,
2026-10-01): the runs grouped by the household's day, newest first, each day a day row with its
tally over ruled lines, one per run; the outcome a word on its highlighter at the line's right;
the PDF and Reprint as the line's foot links."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web.stores import runs
from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _rows(home):
    conn = seed(home)
    pdf = home / "sheets" / "2026-09-30" / "sheet.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 fake")
    ids = [
        runs.record(conn, "open-work", "2026-09-30T07:52:40-04:00", "2026-09-30T07:52:41-04:00", "web", "FAIL", "no snapshot on disk and refresh failed"),
        runs.record(conn, "open-work", "2026-09-30T07:00:00-04:00", "2026-09-30T07:02:00-04:00", "schedule", "OK", "Printed 1 page: Alex=3 Sam=2", str(pdf)),
        runs.record(conn, "refresh", "2026-09-29T06:00:00-04:00", "2026-09-29T06:00:30-04:00", "schedule", "FAIL", "HAC: timed out waiting for the gradebook"),
        runs.record(conn, "open-work", "2026-09-28T07:00:00-04:00", "2026-09-28T07:00:01-04:00", "cli", "SKIP", "outside print window"),
    ]
    conn.close()
    return ids


def test_each_day_is_a_row_with_its_tally_over_its_runs(tmp_path):
    ids = _rows(tmp_path)
    body = app_for(tmp_path, worker=True).get("/runs").text
    days = re.findall(r'<h3 class="day">([^<]*)<span class="tally">· ([^<]*)</span></h3>', body)
    assert days == [("Wed 9/30 ", "2 runs · 1 failed"), ("Tue 9/29 ", "1 run · 1 failed"), ("Mon 9/28 ", "1 run · 1 skipped")]
    assert "<table" not in body and 'class="badge' not in body.split('<div class="planner-main run-log">')[1]
    first = re.search(r'<div class="run">(.*?)</div>', body, re.S).group(1)
    assert re.search(r'<span class="at">7:52 AM</span>\s*<span class="what">Open Work Sheet</span>\s*<span class="by">In the app</span>\s*'
                     r'<span class="detail">no snapshot on disk and refresh failed</span>\s*<span class="word outcome fail">FAIL</span>', first)
    assert '<span class="foot">' not in first                     # nothing to open or reprint on a failed run
    printed = re.search(r'<div class="run">\s*<span class="at">7:00 AM</span>.*?</div>', body, re.S).group(0)
    assert f'<span class="foot">\n    <a href="/runs/{ids[1]}/pdf">open the PDF</a>' in printed
    assert re.search(r'<form hx-post="/jobs/reprint"[^>]*hx-confirm="Print Open Work Sheet from 9/30 again, as it was, on [^"]*">\s*'
                     rf'<input type="hidden" name="run_id" value="{ids[1]}"><button>Reprint</button></form>', printed)
    assert '<span class="what">Refresh</span>' in body            # the runner's key, said as a word
    assert body.index('<h3 class="day">') < body.index('<div class="run">')


def test_the_tally_counts_the_day_then_what_went_wrong():
    assert runs.tally({"OK": 1}) == ["1 run"]
    assert runs.tally({"OK": 1, "FAIL": 1}) == ["2 runs", "1 failed"]
    assert runs.tally({"FAIL": 1, "SKIP": 2, "OK": 3}) == ["6 runs", "1 failed", "2 skipped"]


def test_a_run_is_filed_under_the_households_day(tmp_path):
    """A run that started at 11:30 PM Eastern is written with its offset; a reader in the same
    zone finds it under that day, not under the UTC day after."""
    from fridgesheet.web.routes.runs import days_of
    from zoneinfo import ZoneInfo
    conn = seed(tmp_path)
    runs.record(conn, "open-work", "2026-09-30T23:30:00-04:00", "2026-09-30T23:31:00-04:00", "web", "OK", "2p")
    runs.record(conn, "open-work", "2026-09-30T23:45:00-04:00", "2026-09-30T23:46:00-04:00", "web", "OK", "2p")
    groups = days_of(runs.recent(conn), ZoneInfo("America/New_York"))
    conn.close()
    assert [(str(g["date"]), g["tally"]) for g in groups] == [("2026-09-30", ["2 runs"])]


def test_no_runs_is_one_pencil_line(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/runs").text
    assert '<p class="muted no-runs">No runs yet.</p>' in body and '<h3 class="day">' not in body


def test_the_log_is_drawn_in_the_planners_rules_and_the_outcome_wears_its_colour():
    assert "max-width: 1100px" in _rule(".change-log, .run-log")
    day = _rule(".change-log > h3.day, .run-log > h3.day")
    assert "text-transform: uppercase" in day and "color: var(--muted)" in day
    line = _rule(".change, .run")
    assert "border-bottom: 1px solid var(--rule)" in line and "background" not in line
    outcome = _rule(".run .outcome")
    assert "margin-left: auto" in outcome and "color: var(--muted)" in outcome         # SKIP: pencil
    assert _rule(".run .outcome.ok").strip() == "color: var(--ok);"                   # no green highlighter
    fail = _rule(".run .outcome.fail")
    assert "color: var(--warn)" in fail and "background: var(--hl-red)" in fail
    assert "flex-basis: 100%" in _rule(".run .foot")
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"\.run \.foot a\s*\{[^}]*min-height: 44px", coarse)
    assert "small.row-actions" not in CSS and ".runs" not in CSS

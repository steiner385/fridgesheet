"""Reports as the household's report shelf (the Student Planner; the surface brief in
.impeccable/surfaces/, 2026-10-01): Built in and Yours as day rows over ruled lines, one per
report, each remembering its last run from the sheet's log with Preview and Print at its right;
the builder as ruled sections ending in Save with Preview beside it; the report itself one paper
page with its title along the top edge."""
from __future__ import annotations

import json
import re
from pathlib import Path

from fridgesheet.web import db
from fridgesheet.web.stores import reports as store, runs
from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _shelf(home):
    """Two saved reports and a log: the sheet printed, Mine was previewed, Other never ran."""
    conn = seed(home)
    mine = store.create(conn, "Mine", json.dumps({"title": "Mine", "source": "items", "columns": ["kid", "name"]}), now="2026-09-29T08:00:00-04:00")
    other = store.create(conn, "Other", json.dumps({"title": "Other", "source": "items", "columns": ["kid"]}), now="2026-09-28T08:00:00-04:00")
    runs.record(conn, "open-work", "2026-09-30T07:00:00-04:00", "2026-09-30T07:02:00-04:00", "schedule", "OK", "Printed 1 page: Alex=3 Sam=2")
    runs.record(conn, "open-work", "2026-09-29T07:00:00-04:00", "2026-09-29T07:02:00-04:00", "schedule", "FAIL", "printer offline")
    runs.record(conn, f"view:{mine}", "2026-09-30T08:10:00-04:00", "2026-09-30T08:11:00-04:00", "web", "OK", "dry-run built mine.pdf 1p")
    conn.close()
    return mine, other


def test_the_shelf_is_two_day_rows_over_lines_that_remember_their_last_run(tmp_path):
    mine, other = _shelf(tmp_path)
    body = app_for(tmp_path, worker=True).get("/reports").text
    shelf = body.split('<div class="planner-main report-shelf">')[1].split('id="job"')[0]
    assert re.findall(r'<h3 class="day">([^<]*)</h3>', shelf) == ["Built in", "Yours"]
    assert "<table" not in body and 'class="badge' not in shelf and "row-more" not in body
    # The newest run wins, said in the log's words: the sheet printed this morning after failing yesterday.
    assert re.search(r'<span class="name" title="open-work">Open Work Sheet</span>\s*<span class="last">Printed Wed 9/30 7:00 AM · <span class="word outcome ok">OK</span></span>\s*<span class="acts">', shelf)
    # A preview is not called a print; a report the log has never seen says so in pencil.
    assert re.search(rf'<a href="/reports/{mine}/view" title="view:{mine}">Mine</a></span>\s*<span class="updated">updated Tue 9/29 8:00 AM</span>\s*<span class="last">Previewed Wed 9/30 8:10 AM · <span class="word outcome ok">OK</span></span>', shelf)
    assert re.search(rf'title="view:{other}">Other</a></span>\s*<span class="updated">[^<]*</span>\s*<span class="last">Not run yet</span>', shelf)
    line = re.search(r'<div class="report">\s*<span class="name"><a href="/reports/%d/view".*?</details>\s*</div>' % mine, shelf, re.S).group(0)
    assert line.count("<button>Preview</button>") == 1 and line.count("<button>Print</button>") == 1
    assert re.search(rf'<details class="fold more"><summary>More</summary><span class="more-actions">\s*<a href="/reports/{mine}">Edit</a> · <a href="/reports/{mine}/export.csv">CSV</a> · <a href="/reports/{mine}/export.json">JSON</a>\s*<form hx-post="/reports/{mine}/delete"', line)
    assert body.index('<h3 class="day">Built in</h3>') < body.index('<div class="report">')


def test_a_failed_last_run_says_only_the_time_and_the_word(tmp_path):
    conn = seed(tmp_path)
    runs.record(conn, "open-work", "2026-09-30T07:52:00-04:00", "2026-09-30T07:53:00-04:00", "web", "FAIL", "no snapshot on disk")
    conn.close()
    body = app_for(tmp_path).get("/reports").text
    assert '<span class="last">Wed 9/30 7:52 AM · <span class="word outcome fail">FAIL</span></span>' in body
    assert "Failed Wed" not in body


def test_the_shelf_without_a_worker_has_no_buttons_and_no_tick(tmp_path):
    _shelf(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert '<span class="acts">' not in body and 'id="refresh-first"' not in body
    assert '<span class="last">' in body                     # the log's memory does not need a worker


def test_the_builder_is_three_ruled_sections_closing_on_save_and_preview(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reports/new").text
    form = re.search(r'<form[^>]*id="builder"[^>]*>(.*?)</form>', body, re.S).group(0)
    assert form.startswith('<form method="post" action="/reports/new" class="builder-form" id="builder">')
    assert re.findall(r'<div class="sec-head"><h3>([^<]*)</h3></div>', form) == ["What goes in", "Order and filters", "Chart and page"]
    assert re.findall(r"<legend>(\w+)", form) == ["Kids", "Columns", "Sort", "Filters", "Chart"]
    assert re.search(r'<p class="form-save actions"><button class="primary">Save</button>\s*<button type="button" hx-post="/reports/preview" hx-include="#builder" hx-target="#preview">Preview</button></p>\s*</form>\s*<div id="preview"></div>', body)
    assert 'class="card' not in body.split('class="page-head"')[1]


def test_the_report_is_one_paper_page_with_its_title_along_the_top_edge(tmp_path):
    conn = seed(tmp_path)
    rid = store.create(conn, "Mine", json.dumps({"title": "Mine", "source": "items", "columns": ["kid", "name"], "window": "30d", "group_by": "kid"}), now="2026-09-29T08:00:00-04:00")
    conn.close()
    c = app_for(tmp_path)
    body = c.get(f"/reports/{rid}/view").text
    assert re.search(r'<article class="report-sheet">\s*<p class="muted printed-at"><span class="screen-only">As of</span><span class="print-only">Printed</span> [A-Z][a-z]{2} \d+/\d+ [^<]*</p>\s*<section class="sec report-page">', body)
    assert re.search(r'<h3 class="report-title">Mine <span class="tally">· \d+ rows? · Rows from: the last 30 days</span></h3>', body)
    assert re.findall(r'<h4 class="day">([^<]*)</h4>', body)                       # one day row per kid group
    assert 'class="card' not in body
    # The builder's live preview is the same paper page.
    partial = c.post("/reports/preview", data={"title": "T", "source": "items", "columns": ["kid", "name"]}).text
    assert partial.lstrip().startswith('<section class="sec report-page">') and '<h3 class="report-title">T <span class="tally">· ' in partial
    empty = c.post("/reports/preview", data={"title": "T", "source": "items", "columns": ["kid"], "window": "custom", "date_from": "2020-01-01", "date_to": "2020-01-02"}).text
    assert '<p class="muted no-rows">No rows matched this report.</p>' in empty


def test_the_shelf_and_the_page_are_drawn_in_the_planners_rules():
    assert "max-width: 1100px" in _rule(".change-log, .run-log, .report-shelf, .checkup")
    line = _rule(".report")
    assert "border-bottom: 1px solid var(--rule)" in line and "background" not in line
    assert "font-weight: 650" in _rule(".report .name")
    assert "margin-left: auto" in _rule(".report .acts")
    assert "flex-basis: 100%" in _rule(".report > details.fold.more")
    page = _rule(".report-page")
    assert "background: var(--paper)" in page and "border: 1.5px solid var(--box)" in page
    title = _rule(".report-page > h3.report-title")
    assert "border-bottom: 1.5px solid var(--box)" in title and "text-transform: uppercase" in title
    assert "border: 0" in _rule(".report-page .chart-holder")                    # a figure on the page, not a box in a box
    strip = re.search(r"@media \(max-width: 1023px\)\s*\{(.*?)\n\}", CSS, re.S).group(1)
    assert re.search(r"\.report-page table\.items thead tr, \.report-page table\.items tbody tr[^{]*\{[^}]*display: table-row", strip)   # a report's table stays a table on a phone
    assert "display: inline" in re.search(r"@media print\s*\{(.*?)\n\}", CSS, re.S).group(1).split(".print-page .print-only")[1].split("}")[0]
    assert ".row-more" not in CSS and "h3.report-title { font-size: calc" not in CSS

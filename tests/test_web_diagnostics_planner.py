"""Diagnostics as the app's checkup (the Student Planner; the surface brief in .impeccable/surfaces/,
2026-10-01): one day row dated when the checks ran with its tally, over one planner line per
check -- a drawn tick or cross, the name, the detail in pencil, OK or FAIL on its highlighter at
the right -- and the report as a file under a pencil fold."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web.routes.diagnostics import parse_report
from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")
REPORT = "OK    python: 3.12\nOK    home: writable\nFAIL  printers: none found\nsomething the parser does not know\n1 check(s) failed\n"


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def test_the_report_is_read_as_lines_and_nothing_it_says_is_lost():
    lines, n, failed = parse_report(REPORT)
    assert lines == [{"ok": True, "name": "python", "detail": "3.12"}, {"ok": True, "name": "home", "detail": "writable"},
                     {"ok": False, "name": "printers", "detail": "none found"}, {"raw": "something the parser does not know"}]
    assert (n, failed) == (3, 1)
    assert parse_report("OK    python: 3.12\nAll checks passed\n") == ([{"ok": True, "name": "python", "detail": "3.12"}], 1, 0)


def test_the_checkup_is_a_day_row_over_one_line_per_check(tmp_path):
    seed(tmp_path).close()
    (tmp_path / "doctor.txt").write_text(REPORT, encoding="utf-8")
    body = app_for(tmp_path).get("/diagnostics").text
    checkup = body.split('<div class="planner-main checkup">')[1]
    assert re.search(r'<h3 class="day">Checked [A-Z][a-z]{2} \d+/\d+ \d+:\d\d [AP]M <span class="tally">· 3 checks · 1 failed</span></h3>', checkup)
    assert re.search(r'<div class="check passed">\s*<span class="glyph" aria-hidden="true"><svg[^>]*><path d="M2 6\.5l2\.5 2\.5L10 3\.5"[^>]*/></svg></span>\s*<span class="name">python</span>\s*<span class="detail">3\.12</span>\s*<span class="word outcome ok">OK</span>', checkup)
    assert re.search(r'<div class="check failed">\s*<span class="glyph" aria-hidden="true"><svg[^>]*><path d="M3 3l6 6M9 3l-6 6"[^>]*/></svg></span>\s*<span class="name">printers</span>\s*<span class="detail">none found</span>\s*<span class="word outcome fail">FAIL</span>', checkup)
    assert '<p class="muted raw-line">something the parser does not know</p>' in checkup
    assert '<details class="fold as-file"><summary>The report as a file</summary><pre class="report-text">' in checkup
    assert "FAIL  printers: none found" in checkup and 'pre class="log"' not in checkup
    assert checkup.index('<h3 class="day">') < checkup.index('<div class="check')


def test_a_clean_report_says_all_passed(tmp_path):
    seed(tmp_path).close()
    (tmp_path / "doctor.txt").write_text("OK    python: 3.12\nOK    home: writable\nAll checks passed\n", encoding="utf-8")
    body = app_for(tmp_path).get("/diagnostics").text
    assert '<span class="tally">· 2 checks · all passed</span>' in body and 'class="check failed"' not in body


def test_a_report_that_cannot_be_read_is_one_pencil_line_not_a_clean_verdict(tmp_path):
    """POSIX only: chmod 0 does not make a file unreadable on Windows, and root reads anything."""
    import os
    import sys
    import pytest
    if sys.platform == "win32" or getattr(os, "geteuid", lambda: 1)() == 0:
        pytest.skip("needs a file this process cannot read")
    seed(tmp_path).close()
    (tmp_path / "doctor.txt").write_text(REPORT, encoding="utf-8")
    os.chmod(tmp_path / "doctor.txt", 0)                    # a file that is there but cannot be read
    try:
        body = app_for(tmp_path).get("/diagnostics").text
    finally:
        os.chmod(tmp_path / "doctor.txt", 0o644)
    assert "all passed" not in body and '<h3 class="day">' not in body
    assert re.search(r'<p class="muted raw-line">The last doctor report could not be read: ', body)


def test_a_report_with_only_a_summary_line_has_a_day_row_and_no_tally(tmp_path):
    seed(tmp_path).close()
    (tmp_path / "doctor.txt").write_text("All checks passed\n", encoding="utf-8")
    body = app_for(tmp_path).get("/diagnostics").text
    assert re.search(r'<h3 class="day">Checked [^<]*</h3>', body) and '<span class="tally">' not in body.split('class="planner-main checkup"')[1]


def test_before_the_first_run_one_pencil_line(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/diagnostics").text
    assert '<p class="muted not-run">Diagnostics have not been run yet.</p>' in body and '<h3 class="day">' not in body


def test_the_checkup_is_drawn_in_the_planners_rules():
    assert "max-width: 1100px" in _rule(".change-log, .run-log, .report-shelf, .checkup")
    line = _rule(".check")
    assert "border-bottom: 1px solid var(--rule)" in line and "background" not in line
    assert "color: var(--ok)" in _rule(".check .glyph") and "color: var(--warn)" in _rule(".check.failed .glyph")
    text = _rule(".checkup .report-text")
    assert "background: var(--paper)" in text and "#111" not in text                 # a file on paper, not a console
    assert "background: var(--hl-red)" in _rule(".run .outcome.fail, .report .outcome.fail, .check .outcome.fail, .sched-line .outcome.fail")
    assert "margin-left: auto" in _rule(".run .outcome, .check .outcome")                    # the word at the line's right

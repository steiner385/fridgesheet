"""Today as the family's planner week (the Student Planner; surface brief for dashboard.html,
seed 484d9aac): the sheet strip as the page's date header, five small day boxes with tonight on
the highlighter, then one day box per kid holding tonight's lines with their answers."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _page(tmp_path):
    seed(tmp_path).close()
    return app_for(tmp_path).get("/").text


def test_the_page_is_sheet_strip_then_week_then_the_kids(tmp_path):
    body = _page(tmp_path)
    assert body.index('class="sec sheet-strip"') < body.index('class="week-strip"') < body.index('class="mf-spread today-spread"')
    assert "No sheet built today yet." in body.split('class="week-strip"')[0]


def test_the_week_is_five_day_boxes_with_tonight_first_and_highlighted(tmp_path):
    body = _page(tmp_path)
    week = re.search(r'<ol class="week-strip"[^>]*>(.*?)</ol>', body, re.S).group(1)
    days = re.findall(r'<li class="mf-section day-cell([^"]*)"><h4>(.*?)</h4>', week)
    assert len(days) == 5
    assert days[0][0] == " today" and days[0][1].startswith('<span class="day-word">Tonight</span>')
    assert days[1][1].startswith('<span class="day-word">Tomorrow</span>')
    assert "background: var(--hl-due)" in _rule(".week-strip > li.today > h4 > .day-word")   # the stroke hugs the word


def test_the_week_counts_each_kids_work_by_the_day_it_is_due(tmp_path):
    body = _page(tmp_path)
    week = re.search(r'<ol class="week-strip"[^>]*>(.*?)</ol>', body, re.S).group(1)
    tonight = re.search(r'day-cell today"><h4>.*?</h4>\s*<p>(.*?)</p>', week, re.S).group(1)
    assert "Alex 1" in tonight and "Sam 2" in tonight          # Vocabulary tonight; Sam's two overdue rows count under tonight
    tomorrow = re.search(r'day-cell"><h4><span class="day-word">Tomorrow</span>.*?</h4>\s*<p>(.*?)</p>', week, re.S).group(1)
    assert "Alex 1" in tomorrow and "Sam" not in tomorrow      # Worksheet 3


def test_a_kids_box_holds_tonights_lines_with_their_answers(tmp_path):
    conn = seed(tmp_path)
    vid = conn.execute("SELECT id FROM items WHERE name = 'Vocabulary'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get("/").text
    start = body.index('<div class="mf-section day-box" data-section="Alex">')
    box = body[start:body.index("</div><!-- /kid -->", start)]
    assert '<h3><a href="/kids/Alex/check-in">Alex</a> <span class="day">· by tomorrow</span></h3>' in box   # the box names what it holds
    assert box.index('class="tally"') < box.index('id="td-%d"' % vid) < box.index('class="family-plan"')
    line = box[box.index('id="td-%d"' % vid):]
    assert '<span class="when word due">DUE TODAY</span>' in line
    assert 'hx-post="/items/%d/answer"' % vid in line and 'name="slot" value="qt-%d"' % vid in line
    assert 'value="too_late"' not in line and 'value="ignore"' not in line         # the dismissals stay on the Plan's detail


def test_the_print_two_step_is_unchanged_in_the_sheet_strip(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path, worker=True).get("/").text
    strip = re.search(r'<section class="sec sheet-strip".*?</section>', body, re.S).group(0)
    assert '<details class="print-confirm"><summary>Print now</summary>' in strip
    assert re.search(r'<button class="primary" hx-post="/jobs/print"', strip) and body.count('class="primary"') == 1


def test_the_kid_box_and_the_week_cells_share_the_day_box_rule():
    assert "grid-column: auto" in _rule(".today-spread > .day-box")
    label = _rule(".day-box > h3")
    assert "text-transform: uppercase" in label and "border-bottom: 1.5px solid var(--box)" in label
    phone = re.search(r"@media \(max-width: 1023px\)\s*\{\s*/\* Five cells fit a phone(.*?)\n\}", CSS, re.S).group(1)
    assert "font-size: var(--type-tiny)" in phone and "overflow-x" not in phone     # five cells, no scrolling
    assert "max-width: 1100px" in _rule(".week-strip, .today-spread")
    assert "color: var(--muted)" in _rule(".day-box > .family-plan")
    assert "min-height: 44px" in re.search(r"\.day-box > \.links a\s*\{([^}]*)\}", CSS).group(1)

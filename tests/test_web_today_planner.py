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
    assert "Alex 1" in tonight and "Sam 2 late" in tonight     # Vocabulary tonight; Sam's two overdue rows are named late, not due (re-critique 2026-09-30)
    assert "Sam 2<" not in tonight and "Sam 2 ·" not in tonight
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
    assert 'value="too_late"' in line and "more-answers" not in line            # one tap to say it won't be done (2026-10-03)
    assert 'value="ignore"' not in line                                          # "Let it go" stays on the Plan's detail


def test_the_print_two_step_is_unchanged_in_the_sheet_strip(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path, worker=True).get("/").text
    strip = re.search(r'<section class="sec sheet-strip".*?</section>', body, re.S).group(0)
    assert '<details class="print-confirm"><summary>Print now</summary>' in strip
    assert re.search(r'<button class="primary" hx-post="/jobs/print"', strip) and body.count('class="primary"') == 1


def test_the_sheets_controls_stand_open_on_a_wide_screen_and_fold_on_a_phone(tmp_path):
    """Re-critique 2026-09-30: on a phone four boxed controls stood between the title and the
    first line. The markup ships the fold open (no script needed on a wide screen, where the
    summary is not drawn); app.js closes it under the strip breakpoint, and the planner is
    ordered first there."""
    seed(tmp_path).close()
    body = app_for(tmp_path, worker=True).get("/").text
    assert '<details class="print-controls" data-phone-fold open><summary>Print or preview</summary>' in body
    assert body.index('<div class="today-pages">') < body.index('class="sec sheet-strip"') < body.index('class="planner-main week-block"') < body.index('class="planner-main kids-block"')
    assert "display: contents" in _rule(".today-pages") and "display: none" in _rule(".print-controls > summary")
    phone = re.search(r"@media \(max-width: 1023px\)\s*\{\s*/\* Five cells fit a phone(.*?)\n\}", CSS, re.S).group(1)
    assert re.search(r"\.today-pages > \.week-block\s*\{[^}]*order: -1", phone)           # week, then the folded strip, then the kids
    assert re.search(r"\.print-controls > summary\s*\{[^}]*min-height: 44px", phone)
    js = (WEB / "static" / "app.js").read_text(encoding="utf-8")
    assert 'details[data-phone-fold][open]' in js and 'max-width: 1023px' in js
    assert re.search(r'querySelector\("summary"\); if \(s\) s\.focus\(\);', js)      # Cancel returns focus to the summary


def test_the_household_page_speaks_in_the_parents_voice(tmp_path):
    """Maintainer, 2026-09-30: Today's ask lines and answers are the parent's phrasing whatever
    the child's tier; only the sheet's word keeps the child's words."""
    from tests.web_fixtures import client_with_grades
    seed(tmp_path).close()
    c = client_with_grades(tmp_path, Sam=5)
    body = c.get("/").text
    sam = body[body.index('data-section="Sam"'):body.index("</div><!-- /kid -->", body.index('data-section="Sam"'))]
    assert "It&#39;s handed in" in sam and "I handed it in" not in sam
    assert "When will you work on it?" in sam and "When will you do it?" not in sam
    assert "Teacher hasn&#39;t got it" in sam                                        # the sheet's word, in Sam's words
    assert "I handed it in" in c.get("/kids/Sam/plan").text                          # the child's own page still speaks as the child


def test_the_kid_box_and_the_week_cells_share_the_day_box_rule():
    assert "grid-column: auto" in _rule(".today-spread > .day-box")
    label = _rule(".day-box > h3")
    assert "text-transform: uppercase" in label and "border-bottom: 1.5px solid var(--box)" in label
    phone = re.search(r"@media \(max-width: 1023px\)\s*\{\s*/\* Five cells fit a phone(.*?)\n\}", CSS, re.S).group(1)
    assert "font-size: var(--type-tiny)" in phone and "overflow-x" not in phone     # five cells, no scrolling
    assert "max-width: var(--page-max)" in _rule(".week-strip, .today-spread")   # cards fill the column
    assert "color: var(--muted)" in _rule(".day-box > .family-plan")
    assert "min-height: 44px" in re.search(r"\.day-box > \.links a\s*\{([^}]*)\}", CSS).group(1)

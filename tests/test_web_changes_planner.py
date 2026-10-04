"""Changes as the planner's log (the Student Planner; the surface brief in .impeccable/surfaces/,
2026-10-01): the Window, Kid and Kind words in the sort line's grammar; the window's days newest
first, each a day row with its tally over ruled lines, one per thing that moved; a name opens its
record in a slot under its line."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web.stores import changes
from tests.web_fixtures import app_for, history

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
JS = (WEB / "static" / "app.js").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def test_the_choices_are_words_and_the_chosen_one_is_marked(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=7d&kid=Alex&kind=now_missing").text
    line = re.search(r'<p class="sort change-words" role="group" aria-label="Show">(.*?)</p>', body, re.S).group(1)
    assert re.search(r'<a href="/changes\?kid=Alex&kind=now_missing&window=7d" aria-current="true">Last week</a>', line)
    assert re.search(r'<span class="muted">Kid</span> <a href="/changes\?window=7d&kind=now_missing">all</a> · <a href="/changes\?window=7d&kid=Alex&kind=now_missing" aria-current="true">Alex</a>', line)
    assert re.search(r'<span class="muted">Kind</span> <a href="/changes\?window=7d&kid=Alex">all</a>', line) and 'aria-current="true">Now missing</a>' in line
    assert line.count('aria-current="true"') == 3 and 'class="badge' not in body and 'class="filters"' not in body


def test_each_day_is_a_row_with_its_tally_over_its_lines(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=30d").text
    log = re.search(r'<div class="planner-main change-log">(.*?)</div>\s*(?:<p class="muted pager">|\n*\s*</div>)', body, re.S)
    assert log
    days = re.findall(r'<h3 class="day">([A-Z][a-z]{2} \d+/\d+) <span class="tally">· (\d+) changes? · ([^<]*)</span></h3>', body)
    assert days, "a day row with its tally"
    for _, total, rest in days:
        assert re.match(r"\d+ [a-z ]+( · \d+ [a-z ]+)*$", rest), rest
    assert "<table" not in body and 'class="badge' not in body
    assert re.search(r'<div class="change">\s*<span class="at">\d{1,2}:\d{2} [AP]M</span>\s*<span class="what">[^<]+</span>\s*<span class="subject"><a href="#change-\d+-\d+" hx-get="/items/\d+\?tone=line" hx-target="#change-\d+-\d+" aria-expanded="false" aria-controls="change-\d+-\d+">', body)
    assert re.search(r'<span class="meta"><a href="/kids/Alex">Alex</a> · Honors English 9', body)
    assert re.search(r'<div class="detail-slot" id="change-\d+-\d+" hidden></div>', body)
    assert body.index('<h3 class="day">') < body.index('<div class="change">')


def test_the_tally_words_follow_the_kinds_in_order():
    assert changes.tally({"grade_posted": 2, "now_missing": 1}) == ["3 changes", "2 grades posted", "1 now missing"]
    assert changes.tally({"flag_set": 1}) == ["1 change", "1 answer"]
    assert changes.tally({"course_grade": 3, "new_item": 1}) == ["4 changes", "1 new", "3 class averages"]


def test_an_empty_window_is_one_pencil_line(tmp_path):
    from tests.web_fixtures import seed
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=1d&kind=course_grade").text
    assert '<p class="muted nothing-changed">Nothing has changed in this window.</p>' in body
    assert '<h3 class="day">' not in body


def test_a_record_opens_in_a_slot_under_its_line():
    assert 'closest("tr.detail, .detail-slot")' in JS and 'row.matches("tr")' in JS
    assert "display: none" in _rule(".change-log > .detail-slot[hidden]")
    assert "display: none" in _rule(".detail-slot .item::before, .detail-slot .item::after")
    assert "display: inline-block" in _rule("tr.detail .close-detail, .detail-slot .close-detail")


def test_a_record_under_a_line_keeps_the_sheets_word_and_can_close(tmp_path):
    from fridgesheet.web import db
    history(tmp_path).close()
    conn = db.open_db(tmp_path)
    qid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    conn.close()
    record = app_for(tmp_path).get(f"/items/{qid}?tone=line").text
    assert re.search(r'<span class="when word red">', record)                                  # the sheet's word at the head
    assert record.count("data-close-detail") == 2 and "hx-get=\"/items/" not in record.split("data-close-detail", 1)[1].split(">", 1)[0]


def test_the_log_is_drawn_in_the_planners_rules():
    # Runs shares the log's rules (the sheet's own log, 2026-10-01), so each selector names both.
    assert "max-width: var(--page-max)" in _rule(".change-log, .run-log, .report-shelf, .checkup")
    day = _rule(".change-log > h3.day, .run-log > h3.day, .report-shelf > h3.day, .checkup > h3.day")
    assert "text-transform: uppercase" in day and "letter-spacing: .04em" in day and "color: var(--muted)" in day
    line = _rule(".change, .run")
    assert "border-bottom: 1px solid var(--rule)" in line and "background" not in line
    assert "font-weight: 650" in _rule(".change .what, .run .what") and "color: var(--muted)" in _rule(".change .at, .run .at")
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"\.change \.subject a, \.pager a\s*\{[^}]*padding-block: 11px", coarse)              # 44px under a finger, one underline
    assert "max-width: var(--page-max)" in _rule(".change-words") and "background: var(--paper)" in _rule(".change-log > .detail-slot")
    assert re.search(r"\.change \.meta a\s*\{[^}]*min-height: 24px", coarse)

"""The weekly pages (the Student Planner; surface brief for kid.html, seed d4a7b45f), now
Assignments' Done view and any old link's filtered list (spec 2026-10-06): every assignment on
the week it was due, newest week first, settled weeks folded to one line; the sort as a run-in
line. The To do view above them is tested in test_web_assignments_to_do.py."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, items_block, needs_row, seed, week_line

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_the_pages_run_newest_week_first_under_the_sort_line(tmp_path):
    seed(tmp_path).close()
    body = items_block(app_for(tmp_path).get("/kids/Alex?show=all").text)
    assert body.index('class="planner-main pages"') < body.index('class="sort"') < body.index('class="weeks"')   # the ruling runs behind both
    weeks = re.findall(r'<(section|details) class="mf-section week[^"]*" data-week="([0-9-]+|none)"', body)
    assert [w for _, w in weeks] == ["2026-09-14", "2026-09-07", "2026-08-17"]      # Mondays, newest first
    assert all(tag == "section" for tag, _ in weeks)                                 # every week has an open line at the fixture's now


def test_this_week_is_named_and_highlighted_and_earlier_weeks_are_dated(tmp_path):
    seed(tmp_path).close()
    body = items_block(app_for(tmp_path).get("/kids/Alex?show=all").text)
    assert '<h4 id="week-2026-09-14"><span class="week-word">This week</span> <span class="sep">· </span><span class="date">Mon 9/14</span></h4>' in body
    assert '<span class="week-word">Last week</span> <span class="sep">· </span><span class="date">Mon 9/7</span>' in body
    assert '<span class="week-word">Week of</span> <span class="date">Mon 8/17</span>' in body        # no separator before a bare date
    assert "background: var(--hl-due)" in _rule(".week.current > h4 > .week-word")                 # the stroke hugs the word


def test_a_week_sorted_by_due_date_reads_as_day_rows(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = items_block(c.get("/kids/Alex?show=all").text)
    this_week = body[body.index('data-week="2026-09-14"'):body.index("</section>", body.index('data-week="2026-09-14"'))]
    assert re.findall(r'<h5 class="day">([^<]+)</h5>', this_week) == ["Mon 9/14", "Tue 9/15", "Wed 9/16", "Sun 9/20"]   # every row, Essay draft too
    assert "· by 11:59pm" in this_week and "due Tue 9/15" not in this_week           # the day is the row; the line keeps its hour
    by_name = items_block(c.get("/kids/Alex?show=all&sort=name").text)
    assert '<h5 class="day">' not in by_name and "due Tue 9/15 11:59pm" in by_name    # any other sort: the date on the line


def test_a_line_keeps_the_rows_id_and_only_an_asked_line_answers(tmp_path):
    """Re-critique 2026-09-30: every open line carried the plan prompt and three answers, so a
    single question stood over 24 buttons. On the pages only a line the app asks about offers its
    answers; the rest plan from "Plan a step" in the foot."""
    vid, pid = _id(tmp_path, "Vocabulary"), _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    line = week_line(body, vid)
    assert line.startswith('<div class="item due" id="row-%d"' % vid)
    assert '<span class="when word due">DUE TODAY</span>' in line
    assert 'class="answers"' not in line and "ask-line" not in line and 'id="q-%d"' % vid not in line
    assert ">Plan a step</a>" in line
    asked = week_line(body, pid)
    assert '<p class="ask-line">Was it handed in?</p>' in asked
    assert 'hx-post="/items/%d/answer"' % pid in asked and 'hx-target="#qw-%d"' % pid in asked
    assert items_block(body).count('class="answers"') == 1                             # the one question


def test_a_question_is_asked_under_to_do_and_counted(tmp_path):
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex").text
    assert '<h3 id="ct-head">Check with the teacher</h3><span class="count">1</span>' in body
    asked = needs_row(body, pid)
    assert '<p class="ask-line">Was it handed in?</p>' in asked and 'value="done"' in asked
    assert 'id="q-%d"' % pid not in body                                                # no second card for the same question


def test_a_week_with_nothing_shown_folds_and_this_week_is_always_printed(tmp_path):
    """Open work's "Past the late-work window" set is Homework 4 alone (the week of 8/17): the
    week of 9/7 has nothing in the set, so it folds with its tally, its lines behind the fold
    rather than dropped; this week is printed even though nothing on it is shown. The
    planner's silhouette on the page the child opens: the open page over folded pages."""
    seed(tmp_path).close()
    body = items_block(app_for(tmp_path).get("/kids/Alex?show=past_window").text)
    assert re.search(r'<details class="mf-section week folded" data-week="2026-09-07">\s*<summary><h4[^>]*>.*?<span class="tally">· [^<]*outside Canvas[^<]*</span></h4></summary>', body, re.S)
    folded = body[body.index('data-week="2026-09-07"'):body.index('data-week="2026-08-17"')]
    assert "Quiz 1" in folded and "Participation" in folded                            # behind the fold, not dropped
    assert '<section class="mf-section week" data-week="2026-08-17"' in body and "Homework 4" in body
    assert re.search(r'<section class="mf-section week current" data-week="2026-09-14"[^>]*>\s*<h4[^>]*>.*?</h4>\s*<p class="muted empty-week">Nothing due this week</p>', body, re.S)
    assert body.index('data-week="2026-09-14"') < body.index('data-week="2026-09-07"') < body.index('data-week="2026-08-17"')
    # An outcome or class filter narrows the planner itself: no fold for a week it excludes.
    assert 'data-week="2026-08-17"' not in items_block(app_for(tmp_path).get("/kids/Alex?outcome=done_offline").text)


def test_the_verdict_sections_follow_the_pages(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?view=done").text
    assert body.index('class="legend sources-hint') < body.index("Settled by the records")
    assert "Check with the teacher" not in body


def test_a_detail_opened_from_a_line_closes_back_to_the_line(tmp_path):
    vid = _id(tmp_path, "Vocabulary")
    c = app_for(tmp_path)
    detail = c.get(f"/items/{vid}?card=row-{vid}").text
    # The record keeps the line's colour and the sheet's word at its head (re-critique 2026-09-30).
    assert f'<div class="item due" id="row-{vid}"' in detail and '<span class="when word due">DUE TODAY</span>' in detail
    assert detail.count(f'hx-get="/items/{vid}/question?slot=row-{vid}"') == 2                  # Close at the head and at the foot
    assert re.search(r'<span class="meta"><a href="/kids/Alex/courses/\d+">Honors English 9</a>', detail)
    line = c.get(f"/items/{vid}/question?slot=row-{vid}").text
    assert f'<div class="item due" id="row-{vid}"' in line and '<span class="when word due">DUE TODAY</span>' in line
    assert 'class="answers"' not in line                                                        # not asked: no answers on the line


def test_a_child_with_one_class_gets_no_class_picker(tmp_path):
    """One class is no choice (re-critique 2026-09-30: controls before the first line on a
    nine-year-old's phone); a child with two classes gets the picker."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert 'name="course"' not in c.get("/kids/Sam").text
    assert 'name="course"' in c.get("/kids/Alex").text


def test_the_pages_share_the_planners_rules():
    assert "max-width: var(--page-max)" in _rule(".weeks")
    assert "text-transform: uppercase" in _rule("details.week > summary > h4")
    assert "font-weight: 650" in _rule(".sort a[aria-current]")
    coarse = re.search(r"@media \(pointer: coarse\)\s*\{\s*\.sort a[^{]*\{([^}]*)\}", CSS).group(1)
    assert "min-height: 44px" in coarse

"""Assignments as the weekly pages (the Student Planner; surface brief for kid.html, seed d4a7b45f):
every assignment on the week it was due, this week's page first, earlier weeks beneath, settled
weeks folded to one line; a question asked on its own line; the sort as a run-in line."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, items_block, seed, week_line

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
    body = items_block(c.get("/kids/Alex").text)
    this_week = body[body.index('data-week="2026-09-14"'):body.index("</section>", body.index('data-week="2026-09-14"'))]
    assert re.findall(r'<h5 class="day">([^<]+)</h5>', this_week) == ["Tue 9/15", "Wed 9/16", "Sun 9/20"]
    assert "· by 11:59pm" in this_week and "due Tue 9/15" not in this_week           # the day is the row; the line keeps its hour
    by_name = items_block(c.get("/kids/Alex?sort=name").text)
    assert '<h5 class="day">' not in by_name and "due Tue 9/15 11:59pm" in by_name    # any other sort: the date on the line


def test_a_line_keeps_the_rows_id_and_answers_in_its_own_slot(tmp_path):
    vid = _id(tmp_path, "Vocabulary")
    line = week_line(app_for(tmp_path).get("/kids/Alex").text, vid)
    assert line.startswith('<div class="item due" id="row-%d"' % vid)
    assert '<span class="when word due">DUE TODAY</span>' in line
    assert 'hx-post="/items/%d/answer"' % vid in line and 'name="slot" value="qw-%d"' % vid in line
    assert 'hx-target="#qw-%d"' % vid in line and 'id="q-%d"' % vid not in line


def test_a_question_is_asked_on_its_line_and_counted_in_the_lead(tmp_path):
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex").text
    assert '<p id="q-lead" class="lead">1 question about your work</p>' in body
    line = week_line(body, pid)
    assert '<p class="ask-line">Was it handed in?</p>' in line and 'value="done"' in line
    assert 'id="q-%d"' % pid not in body                                                # no second card for the same question


def test_a_week_with_nothing_shown_folds_and_this_week_is_always_printed(tmp_path):
    """Open work's "Past the late-work window" set is Homework 4 alone (the week of 8/17): the
    week of 9/7 has nothing in the set, so it folds with its tally, its lines behind the fold
    rather than dropped; this week is printed even though nothing on it is shown. The
    planner's silhouette on the page the child opens: the open page over folded pages."""
    seed(tmp_path).close()
    body = items_block(app_for(tmp_path).get("/kids/Alex?show=past_window").text)
    assert re.search(r'<details class="mf-section week folded" data-week="2026-09-07">\s*<summary><h4[^>]*>.*?<span class="tally">· [^<]*on paper[^<]*</span></h4></summary>', body, re.S)
    folded = body[body.index('data-week="2026-09-07"'):body.index('data-week="2026-08-17"')]
    assert "Quiz 1" in folded and "Participation" in folded                            # behind the fold, not dropped
    assert '<section class="mf-section week" data-week="2026-08-17"' in body and "Homework 4" in body
    assert re.search(r'<section class="mf-section week current" data-week="2026-09-14"[^>]*>\s*<h4[^>]*>.*?</h4>\s*<p class="muted empty-week">Nothing due this week</p>', body, re.S)
    assert body.index('data-week="2026-09-14"') < body.index('data-week="2026-09-07"') < body.index('data-week="2026-08-17"')
    # An outcome or class filter narrows the planner itself: no fold for a week it excludes.
    assert 'data-week="2026-08-17"' not in items_block(app_for(tmp_path).get("/kids/Alex?outcome=done_offline").text)


def test_the_verdict_sections_follow_the_pages(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert body.index('class="legend sources-hint') < body.index("Settled by the records") < body.index("Waiting, nothing to do yet")
    assert "1 question about your work" not in body[body.index("Settled by the records"):]


def test_a_detail_opened_from_a_line_closes_back_to_the_line(tmp_path):
    vid = _id(tmp_path, "Vocabulary")
    c = app_for(tmp_path)
    detail = c.get(f"/items/{vid}?card=row-{vid}").text
    assert f'<div class="item" id="row-{vid}"' in detail and f'hx-get="/items/{vid}/question?slot=row-{vid}"' in detail
    line = c.get(f"/items/{vid}/question?slot=row-{vid}").text
    assert f'<div class="item due" id="row-{vid}"' in line and '<span class="when word due">DUE TODAY</span>' in line
    assert f'name="slot" value="qw-{vid}"' in line


def test_the_pages_share_the_planners_rules():
    assert "max-width: 1100px" in _rule(".weeks")
    assert "text-transform: uppercase" in _rule("details.week > summary > h4")
    assert "font-weight: 650" in _rule(".sort a[aria-current]")
    coarse = re.search(r"@media \(pointer: coarse\)\s*\{\s*\.sort a\s*\{([^}]*)\}", CSS).group(1)
    assert "min-height: 44px" in coarse

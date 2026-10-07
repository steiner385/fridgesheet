"""The kid page's verdicts (spec 6.1) on Assignments (spec 2026-10-06): a question asked in Check
with the teacher, the waiting work folded under To do, the records' decisions under Done."""
from __future__ import annotations

import re

from tests.web_fixtures import app_for, items_block, needs_row, seed


def _page(tmp_path, q=""):
    seed(tmp_path).close()
    return app_for(tmp_path).get(f"/kids/Alex{q}").text


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_alex_has_one_question_one_decided_and_two_waiting(tmp_path):
    pid = _id(tmp_path, "Participation")
    body = _page(tmp_path)
    ct = body[body.index('id="check-teacher"'):body.index('id="waiting"')]
    assert '<p class="ask-line">' in needs_row(ct, pid)                      # asked under To do
    waiting = body[body.index('<details id="waiting"'):]
    assert "Essay draft" in waiting and "Lab notebook" in waiting and "Ask now" in waiting
    done = _page(tmp_path, "?view=done")
    decided = done[done.index("Settled by the records"):]
    assert "Quiz 1" in decided and "Not right?" in decided


def test_the_class_picker_narrows_the_questions_too(tmp_path):
    """One partition over the class in force: a class with no questions shows none."""
    assert 'id="check-teacher"' in _page(tmp_path)
    assert 'id="check-teacher"' not in _page(tmp_path, "?course=999")


def test_the_work_list_has_three_columns_and_no_sources_or_actionable(tmp_path):
    body = _page(tmp_path, "?show=all")
    table = items_block(body)
    assert "Where it stands" in table and "Sources" not in table and "actionable" not in table


def test_red_marks_only_school_recorded_not_done(tmp_path):
    table = items_block(_page(tmp_path, "?show=all"))
    rows = {m.group(2): m.group(1) for m in re.finditer(r'<div class="(item[^"]*)" id="row-\d+"[^>]*>\s*<div class="item-head"><span class="name"><a[^>]*>([^<]+)</a>', table)}
    assert "red" in rows["Homework 4"]            # Canvas marked it missing
    assert "red" not in rows["Lab notebook"]      # the app is waiting, not the school saying no
    assert "red" not in rows["Quiz 1"]            # decided done


def test_an_old_link_keeps_its_filters_through_a_class_change(tmp_path):
    body = _page(tmp_path, "?source=canvas&kind=paper&flagged=any")
    for name, value in (("source", "canvas"), ("kind", "paper"), ("flagged", "any")):
        assert f'<input type="hidden" name="{name}" value="{value}">' in body


def test_the_course_page_asks_a_question_on_its_own_line(tmp_path):
    """Finding 10 said the course page had no question cards, so its tag pointed at the kid
    page's line. The class's record (2026-09-30) prints the same weekly pages as Assignments, so
    the question is asked on the line itself here too, never on a bare row (#85)."""
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    pid = conn.execute("SELECT id FROM items WHERE name = 'Participation'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    line = body[body.index(f'id="row-{pid}"'):]
    line = line[:line.index('class="item-foot"')]
    assert 'class="ask-line"' in line and 'class="answers"' in line
    assert f'href="/kids/Alex#row-{pid}"' not in body


# --- kids' UX audit F8: one true sentence about what has been done ---------------------------------

def test_the_page_says_what_has_been_done_so_far(tmp_path):
    """Every child surface listed only what was wrong; the on-time counts lived inside a collapsed
    details on the parent's Today page. Alex's settled work at the fixture's now: Quiz 1 done on
    paper, Essay draft on time, Lab notebook and Participation unknown, Homework 4 not done."""
    body = _page(tmp_path)
    assert "Done so far: 2 of 5 due · 1 on time." in body
    assert body.index("Done so far") < body.index('id="to-do"')            # above the list


def test_nothing_done_yet_says_nothing(tmp_path):
    """A line that exists to state what went right does not appear to state that nothing has,
    which the dashboard's record already does in numbers."""
    seed(tmp_path).close()
    assert "Done so far" not in app_for(tmp_path).get("/kids/Sam").text     # two not-done rows, nothing done

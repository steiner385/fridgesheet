"""Assignments as a to-do list (spec 2026-10-06): every open item once, in deadline order, the
gradebook questions under it, waiting and missed work folded, finished work in a Done view."""
from __future__ import annotations

import re
from datetime import timedelta
from uuid import uuid4

from fridgesheet.web.stores import plans, students
from tests.web_fixtures import NOW, app_for, seed, snapshot, week_line


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_a_missed_row_says_the_window_in_the_past_tense(tmp_path):
    """Protist Lab on Doug's page read "the late-work window has closed. Late work is usually
    accepted until Mon 10/5." -- a date already gone, in the present tense."""
    safety = _id(tmp_path, "Safety quiz")
    body = app_for(tmp_path, now=NOW + timedelta(days=30)).get("/kids/Sam?show=all").text
    line = week_line(body, safety)
    assert "is usually accepted until" not in line
    assert "Late work was accepted until" in line



def _ids(tmp_path, *names):
    conn = seed(tmp_path)
    try:
        return [conn.execute("SELECT id FROM items WHERE name = ?", (n,)).fetchone()["id"] for n in names]
    finally:
        conn.close()


def _section(body: str, sid: str) -> str:
    """One group under the list: from its id to the next group or the end of #items (a row's
    own Record fold closes a `<details>` inside it, so a closing tag is no boundary)."""
    start = body.index(f'id="{sid}"')
    end = re.compile(r'<(?:section|details) id="|class="legend sources-hint').search(body, start + 1)
    return body[start:end.start() if end else len(body)]


def _todo(body: str) -> str:
    start = body.index('id="to-do"')
    return body[start:body.index("</section>", start)]


def _boxes(html: str) -> list[int]:
    return [int(i) for i in re.findall(r'<div class="(?:item|line)[^"]*" id="(?:nn|row|q)-(\d+)"', html)]


def test_to_do_is_the_default_and_the_old_triage_and_filters_are_gone(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert 'id="needs-now"' not in body and "More filters" not in body and 'name="show"' not in body
    assert body.index('id="to-do"') < body.index('id="check-teacher"')
    assert 'aria-current="page">' + "To do</a>" in body
    assert 'href="/kids/Alex?view=done"' in body


def test_alex_bands_in_deadline_order_answers_on_the_urgent_ones(tmp_path):
    vocab, worksheet, reading = _ids(tmp_path, "Vocabulary", "Worksheet 3", "Reading log")
    todo = _todo(app_for(tmp_path).get("/kids/Alex").text)
    assert re.findall(r'data-band="(\w+)"', todo) == ["tonight", "tomorrow", "this_week"]
    assert _boxes(todo) == [vocab, worksheet, reading]
    for i in (vocab, worksheet):
        assert f'id="nn-{i}"' in todo and f'name="slot" value="qn-{i}"' in todo
    assert f'id="row-{reading}"' in todo and f'value="qn-{reading}"' not in todo


def test_overdue_closest_to_losing_credit_first_and_a_step_keeps_its_row(tmp_path):
    conn = seed(tmp_path)
    safety, cell = (conn.execute("SELECT id FROM items WHERE name = ?", (n,)).fetchone()["id"] for n in ("Safety quiz", "Cell diagram"))
    sam = conn.execute("SELECT student_id FROM items WHERE id = ?", (safety,)).fetchone()["student_id"]
    plans.save(conn, sam, dict(title="Safety quiz", planned_for="2026-09-16", family_account="", next_step="Work on it",
               owner="Sam", minutes=None, state="planned", position=10, evidence="{}", recorded_by=""),
               now=NOW.isoformat(), request_key=str(uuid4()), item_id=safety)
    conn.close()
    todo = _todo(app_for(tmp_path).get("/kids/Sam").text)
    assert re.findall(r'data-band="(\w+)"', todo) == ["overdue"]
    assert _boxes(todo) == [safety, cell]
    assert "Our step: Work on it" in todo


def test_questions_sit_under_the_list_and_answer_in_place(tmp_path):
    participation, = _ids(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex").text
    ct = _section(body, "check-teacher")
    assert _boxes(ct) == [participation]
    assert f'name="slot" value="qn-{participation}"' in ct


def test_waiting_and_missed_fold_under_the_list(tmp_path):
    lab, essay, hw4 = _ids(tmp_path, "Lab notebook", "Essay draft", "Homework 4")
    body = app_for(tmp_path).get("/kids/Alex").text
    assert re.search(r'<details id="waiting" class="sec quiet">', body)
    assert sorted(_boxes(_section(body, "waiting"))) == sorted([lab, essay])
    assert _boxes(_section(body, "missed")) == [hw4]


def test_every_item_on_the_page_once(tmp_path):
    seed(tmp_path).close()
    for kid in ("Alex", "Sam"):
        ids = _boxes(app_for(tmp_path).get(f"/kids/{kid}").text)
        assert len(ids) == len(set(ids)), kid


def test_nothing_to_do_is_one_quiet_line(tmp_path):
    snap = snapshot()
    snap["students"]["Sam"]["canvas"]["courses"][0]["assignments"] = []
    seed(tmp_path, snap).close()
    todo = _todo(app_for(tmp_path).get("/kids/Sam").text)
    assert _boxes(todo) == [] and "Nothing left to do." in todo


def test_the_done_view_is_the_weekly_pages_of_finished_work(tmp_path):
    quiz, vocab = _ids(tmp_path, "Quiz 1", "Vocabulary")
    body = app_for(tmp_path).get("/kids/Alex?view=done").text
    assert 'id="to-do"' not in body and 'data-week="' in body
    assert f'id="row-{quiz}"' in body and f'id="row-{vocab}"' not in body
    assert 'aria-current="page">Done</a>' in body
    assert "view=done" in re.search(r'id="sort-due" href="([^"]+)"', body).group(1)


def test_show_all_link_lands_on_the_row(tmp_path):
    """Other pages link a name to `/kids/X?show=all#row-<id>`: still a Done view with every row."""
    cell, = _ids(tmp_path, "Cell diagram")
    body = app_for(tmp_path).get("/kids/Sam?show=all").text
    assert 'id="to-do"' not in body and f'id="row-{cell}"' in body
    assert 'href="/kids/Sam"' in body                      # back to To do


def test_an_old_outcome_filter_opens_done_with_it_in_force(tmp_path):
    cell, safety = _ids(tmp_path, "Cell diagram", "Safety quiz")
    body = app_for(tmp_path).get("/kids/Sam?outcome=not_done").text
    assert 'id="to-do"' not in body and f'id="row-{cell}"' in body and f'id="row-{safety}"' in body


def test_the_class_picker_narrows_every_group(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    alg = next(cid for cid, label in students.course_options(conn, alex["id"]) if "Algebra" in label)
    hw4 = conn.execute("SELECT id FROM items WHERE name = 'Homework 4'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex?course={alg}").text
    assert _boxes(_todo(body)) == [] and 'id="check-teacher"' not in body
    assert _boxes(_section(body, "missed")) == [hw4]
    assert f'<option value="{alg}" selected>' in body


def test_a_class_change_swaps_only_the_lists(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/kids/Alex", headers={"HX-Request": "true"})
    assert 'id="to-do"' in r.text and "<html" not in r.text

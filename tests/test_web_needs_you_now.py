"""Needs you now (2026-10-04): the top of Assignments is the triage, most urgent first, each row
with the Plan's one-tap answers; the weekly pages under it stay the school's record. A parent at
a desk and a child on a phone both open this page, and both had to scroll past the filters and
last Monday's lines to reach the MISSING ones."""
from __future__ import annotations

import re
from uuid import uuid4

from fridgesheet.web.stores import plans
from tests.web_fixtures import NOW, app_for, seed, snapshot, week_line


def _ids(tmp_path, *names):
    conn = seed(tmp_path)
    try:
        return [conn.execute("SELECT id FROM items WHERE name = ?", (n,)).fetchone()["id"] for n in names]
    finally:
        conn.close()


def _section(body: str) -> str:
    start = body.index('id="needs-now"')
    return body[start:body.index("</section>", start)]


def _rows(section: str) -> list[int]:
    return [int(i) for i in re.findall(r'<div class="item[^"]*" id="nn-(\d+)"', section)]


def test_the_section_comes_before_the_list_and_its_filters(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert body.index('id="needs-now"') < body.index('class="filters controls"') < body.index('id="items"')
    assert '<h3 id="nn-heading">Needs you now</h3>' in _section(body)


def test_tonight_then_tomorrow_then_the_questions(tmp_path):
    vocab, worksheet, participation = _ids(tmp_path, "Vocabulary", "Worksheet 3", "Participation")
    section = _section(app_for(tmp_path).get("/kids/Alex").text)
    assert _rows(section) == [vocab, worksheet, participation]
    # Every row answers in place, in its own slot, so an answer swaps the answers, not the row.
    for i in (vocab, worksheet, participation):
        assert f'hx-post="/items/{i}/answer"' in section and f'name="slot" value="qn-{i}"' in section
    assert ">Do it today</button>" in section and ">Too late to submit</button>" in section


def test_overdue_work_comes_closest_to_losing_credit_first(tmp_path):
    cell, safety = _ids(tmp_path, "Cell diagram", "Safety quiz")
    section = _section(app_for(tmp_path).get("/kids/Sam").text)
    assert _rows(section) == [safety, cell]               # credit ends 9/25, then 9/27
    assert ">ZERO</span>" in section and ">MISSING</span>" in section


def test_a_step_still_ahead_covers_its_row_and_one_that_slipped_does_not(tmp_path):
    conn = seed(tmp_path)
    cell = conn.execute("SELECT id FROM items WHERE name = 'Cell diagram'").fetchone()["id"]
    safety = conn.execute("SELECT id FROM items WHERE name = 'Safety quiz'").fetchone()["id"]
    sam = conn.execute("SELECT student_id FROM items WHERE id = ?", (cell,)).fetchone()["student_id"]
    base = dict(family_account="", next_step="Work on it", owner="Sam", minutes=None, state="planned",
                position=10, evidence="{}", recorded_by="")
    plans.save(conn, sam, {**base, "title": "Cell diagram", "planned_for": "2026-09-14"}, now=NOW.isoformat(),
               request_key=str(uuid4()), item_id=cell)            # yesterday: the step slipped
    plans.save(conn, sam, {**base, "title": "Safety quiz", "planned_for": "2026-09-16"}, now=NOW.isoformat(),
               request_key=str(uuid4()), item_id=safety)          # tomorrow: in hand
    conn.close()
    section = _section(app_for(tmp_path).get("/kids/Sam").text)
    assert _rows(section) == [cell]
    assert "Our step: Work on it" in section and ">Too late to submit</button>" in section


def test_a_line_up_top_offers_no_second_set_of_answers_below(tmp_path):
    participation, = _ids(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex").text
    line = week_line(body, participation)
    assert 'class="answers"' not in line and "ask-line" not in line
    assert body.count('class="answers"') == len(_rows(_section(body)))


def test_nothing_to_triage_is_one_quiet_line(tmp_path):
    snap = snapshot()
    snap["students"]["Sam"]["canvas"]["courses"][0]["assignments"] = []
    seed(tmp_path, snap).close()
    section = _section(app_for(tmp_path).get("/kids/Sam").text)
    assert _rows(section) == [] and "Nothing needs you now." in section


def test_an_answer_from_the_section_swaps_its_answers_and_undo_puts_them_back(tmp_path):
    participation, = _ids(tmp_path, "Participation")
    c = app_for(tmp_path)
    done = c.post(f"/items/{participation}/answer", data={"answer": "done", "slot": f"qn-{participation}"})
    assert done.status_code == 200
    assert f'<div class="line ok done-line" id="qn-{participation}"' in done.text
    back = c.post(f"/items/{participation}/undo", data={"prev": "", "prev_set_at": "", "slot": f"qn-{participation}"})
    assert back.status_code == 200
    assert back.text.lstrip().startswith(f'<div id="qn-{participation}"')     # the answers alone, not a card inside the row
    assert 'class="answers"' in back.text

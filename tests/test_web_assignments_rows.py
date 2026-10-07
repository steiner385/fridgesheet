"""The rows on Assignments that answer in place (2026-10-04, kept by spec 2026-10-06): overdue,
tonight's and tomorrow's work and Check with the teacher, each an `nn-<id>` row with the Plan's
one-tap answers in `qn-<id>`. An answer swaps the answers, Undo puts them back, the name opens
the record in place and Close puts the row back. Where each row is listed is tested in
test_web_assignments_to_do.py."""
from __future__ import annotations

from tests.web_fixtures import _h, app_for, needs_row, seed, snapshot


def _ids(tmp_path, *names):
    conn = seed(tmp_path)
    try:
        return [conn.execute("SELECT id FROM items WHERE name = ?", (n,)).fetchone()["id"] for n in names]
    finally:
        conn.close()






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


def _hac_lower(tmp_path) -> int:
    """Quiz 1 graded higher in Canvas than in HAC: a question whose first answer is "HAC is
    right", which is the `ignore` action (verdicts.py)."""
    snap = snapshot()
    for a in snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Quiz 1":
            a.update(missing=False, state="graded", score=30.0, grade="30")
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"] = [_h("Quiz 1", "09/12/2026", 20.0, points=30.0)]
    conn = seed(tmp_path, snap)
    try:
        return conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    finally:
        conn.close()


def test_a_question_keeps_every_answer_it_asks_with(tmp_path):
    """Only a red row drops "Let it go" (as on Must finish); a question's own `ignore` answer
    ("HAC is right") is the question's answer, not a way to wave a row off."""
    quiz = _hac_lower(tmp_path)
    row = needs_row(app_for(tmp_path).get("/kids/Alex").text, quiz)
    assert 'value="ignore"' in row


def test_undo_on_a_red_row_puts_back_its_prompt_and_answers(tmp_path):
    vocab, = _ids(tmp_path, "Vocabulary")
    c = app_for(tmp_path)
    c.post(f"/items/{vocab}/answer", data={"answer": "too_late", "slot": f"qn-{vocab}"})
    back = c.post(f"/items/{vocab}/undo", data={"prev": "", "prev_set_at": "", "slot": f"qn-{vocab}"}).text
    assert back.lstrip().startswith(f'<div id="qn-{vocab}"')
    assert '<p class="ask-line plan">When will you work on it?</p>' in back and ">Do it today</button>" in back


def test_the_name_opens_the_record_and_close_puts_the_row_back(tmp_path):
    vocab, = _ids(tmp_path, "Vocabulary")
    c = app_for(tmp_path)
    row = needs_row(c.get("/kids/Alex").text, vocab)
    assert f'hx-get="/items/{vocab}?card=nn-{vocab}"' in row and f'hx-target="#nn-{vocab}"' in row
    detail = c.get(f"/items/{vocab}?card=nn-{vocab}").text
    assert f'hx-get="/items/{vocab}/question?slot=nn-{vocab}"' in detail          # Close knows where it came from
    back = c.get(f"/items/{vocab}/question?slot=nn-{vocab}").text
    assert back.lstrip().startswith(f'<div class="item due" id="nn-{vocab}"') and f'name="slot" value="qn-{vocab}"' in back

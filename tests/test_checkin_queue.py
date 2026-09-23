"""Which review group an item lands in at the check-in, decided without rendering a page."""
from __future__ import annotations

from types import SimpleNamespace

from fridgesheet.web import outcomes
from fridgesheet.web import verdicts as V
from fridgesheet.web.routes import checkin


def view(**kw):
    base = dict(id=1, outcome=outcomes.NOT_DONE, canvas=None, hac=None, grade_zero=False,
                open_in={"canvas"}, upcoming=False, due=None, handled=False, verdict=V.Verdict(V.STATUS, "not_done"))
    base.update(kw)
    return SimpleNamespace(**base)


def test_handled_work_stays_out_of_review():
    assert checkin.queue_for(view(handled=True, verdict=V.Verdict(V.STATUS, "answered")), covered=set()) is None


def test_a_stale_answer_needs_clarification_even_when_handled():
    v = view(handled=True, open_in=set(), verdict=V.Verdict(V.QUESTION, "stale_answer"))
    assert checkin.queue_for(v, covered=set()) == "Questions"


def test_any_question_needs_clarification():
    assert checkin.queue_for(view(verdict=V.Verdict(V.QUESTION, "hac_lower")), covered=set()) == "Questions"


def test_waiting_on_the_teacher_is_the_waiting_group():
    v = view(open_in=set(), verdict=V.Verdict(V.WAITING, "teacher_grading"))
    assert checkin.queue_for(v, covered=set()) == "Waiting on the school"


def test_work_with_an_agreed_step_stays_out_of_review():
    assert checkin.queue_for(view(verdict=V.Verdict(V.QUESTION, "hac_lower")), covered={1}) is None


def test_open_work_is_work_to_consider():
    assert checkin.queue_for(view(), covered=set()) == "To do"

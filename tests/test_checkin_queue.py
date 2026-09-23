"""Which review group an item lands in at the check-in, decided without rendering a page."""
from __future__ import annotations

from types import SimpleNamespace

from fridgesheet.web import outcomes
from fridgesheet.web.routes import checkin


def view(**kw):
    base = dict(id=1, outcome=outcomes.NOT_DONE, canvas=None, hac=None, grade_zero=False, case_kinds=[],
                open_in={"canvas"}, upcoming=False, due=None, handled=False)
    base.update(kw)
    return SimpleNamespace(**base)


def test_handled_work_stays_out_of_review():
    assert checkin.queue_for(view(handled=True), covered=set()) is None


def test_a_handled_flag_the_school_now_contradicts_needs_clarification():
    """Issue #36: "flagged done, Canvas now says MISSING" is the disagreement a check-in exists for."""
    v = view(handled=True, case_kinds=["stale_flag"], open_in=set())
    assert checkin.queue_for(v, covered=set()) == "Needs clarification"


def test_work_with_an_agreed_step_stays_out_of_review():
    assert checkin.queue_for(view(case_kinds=["stale_flag"]), covered={1}) is None


def test_open_work_is_work_to_consider():
    assert checkin.queue_for(view(), covered=set()) == "Work to consider"

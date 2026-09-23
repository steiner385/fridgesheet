"""One verdict per item (spec section 4.1). Plain dicts stand in for observation rows."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet import late_rules
from fridgesheet.web import verdicts as V

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)
RULES = late_rules.LateRules(late_rules.Rule(late_days=7, credit="50%"), [], [])
TIMES = {1: "2026-09-01T06:00:00-04:00", 2: "2026-09-08T06:00:00-04:00", 3: "2026-09-15T06:00:00-04:00"}


def item(kind="online", due="2026-09-12T23:59:00-04:00", points=30.0, peer=2):
    return {"kind": kind, "due": due, "points": points, "kid": "Alex", "course_name": "Honors English 9 S1",
            "peer_course_id": peer}


def canvas(rid=3, **kw):
    base = dict(refresh_id=rid, state="unsubmitted", score=None, grade=None, submitted_at=None, late=0,
                missing=0, excused=0, published=1)
    base.update(kw)
    return base


def hac(rid=3, score=None):
    return dict(refresh_id=rid, state="graded" if score is not None else "ungraded", score=score, grade=None,
                submitted_at=None, late=None, missing=None, excused=None, published=None)


def run(it, obs, flag=None, flag_set_at="", now=NOW):
    return V.verdict(it, obs, flag=flag, flag_set_at=flag_set_at, now=now, rules=RULES, refresh_times=TIMES)


def test_hac_grade_over_automatic_missing_is_decided():
    v = run(item(), {"canvas": canvas(missing=1), "hac": hac(score=28.0)})
    assert (v.state, v.kind) == (V.DECIDED, "graded_in_hac")
    assert v.facts == {"hac": "28 of 30"}
    assert [a.flag for a in v.answers] == ["done", "ask_teacher"]      # what "Not right?" offers


def test_missing_recorded_after_the_hac_grade_is_a_question():
    v = run(item(), {"canvas": canvas(rid=3, missing=1), "hac": hac(rid=2, score=28.0)})
    assert (v.state, v.kind) == (V.QUESTION, "missing_after_grade")


def test_submitted_online_but_hac_zero_is_a_question_with_the_timestamp():
    v = run(item(), {"canvas": canvas(state="submitted", submitted_at="2026-09-14T20:02:00-04:00"), "hac": hac(score=0.0)})
    assert (v.state, v.kind) == (V.QUESTION, "submitted_hac_zero")
    assert v.facts == {"when": "Mon 9/14, 8:02 PM"}


def test_excused_in_canvas_but_hac_zero_is_a_question():
    v = run(item(), {"canvas": canvas(excused=1), "hac": hac(score=0.0)})
    assert (v.state, v.kind) == (V.QUESTION, "excused_hac_zero")


def test_hac_lower_than_canvas_is_a_question():
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=20.0), "hac": hac(score=15.0)})
    assert (v.state, v.kind) == (V.QUESTION, "hac_lower")
    assert v.facts == {"canvas": "20 of 25", "hac": "15 of 25"}


def test_hac_higher_than_canvas_is_not_a_question():
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=15.0), "hac": hac(score=20.0)})
    assert v.state == V.STATUS


def test_a_gap_within_half_a_point_is_the_same_score():
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=20.0), "hac": hac(score=19.6)})
    assert v.state == V.STATUS


def test_hac_applying_the_late_penalty_is_explained():
    # 50% credit rule: Canvas has the raw 20, HAC entered 10.
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=20.0, late=1), "hac": hac(score=10.0)})
    assert (v.state, v.kind) == (V.DECIDED, "scores_explained")
    assert v.facts == {"why": "late"}


def test_hac_as_a_percentage_is_explained():
    # Canvas 180/200 is 90%; HAC typed 90. Points above 100 make HAC's number look lower.
    v = run(item(points=200.0), {"canvas": canvas(state="graded", score=180.0), "hac": hac(score=90.0)})
    assert (v.state, v.kind) == (V.DECIDED, "scores_explained")
    assert v.facts == {"why": "scale"}


def test_no_points_skips_score_comparison():
    """Review Focus 2: no division, and an extra-credit 0-point item is not a zero."""
    v = run(item(points=0.0), {"canvas": canvas(state="graded", score=2.0), "hac": hac(score=0.0)})
    assert v.state == V.STATUS
    v = run(item(points=None), {"canvas": canvas(state="graded", score=2.0), "hac": hac(score=1.0)})
    assert v.state == V.STATUS


def test_a_handled_flag_is_an_answered_status():
    v = run(item(), {"canvas": canvas(missing=1)}, flag="done", flag_set_at="2026-09-15T08:00:00-04:00")
    assert (v.state, v.kind) == (V.STATUS, "answered")


def test_ask_teacher_is_an_asked_status_with_its_date():
    v = run(item(), {"canvas": canvas(missing=1)}, flag="ask_teacher", flag_set_at="2026-09-15T08:00:00-04:00")
    assert (v.state, v.kind) == (V.STATUS, "asked")
    assert v.facts == {"when": "9/15"}


def test_a_done_flag_contradicted_later_is_a_stale_answer():
    v = run(item(), {"canvas": canvas(rid=3, missing=1)}, flag="done", flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "stale_answer")
    assert v.facts == {"flag": "done", "when": "9/10", "change": "Canvas now says missing"}
    assert [a.flag for a in v.answers] == ["confirm", "clear", "ask_teacher"]


def test_stale_check_accepts_a_naive_flag_timestamp():
    """Review Focus 4: older flag rows carry no offset."""
    v = run(item(), {"canvas": canvas(rid=3, missing=1)}, flag="done", flag_set_at="2026-09-10T08:00:00")
    assert v.kind == "stale_answer"


def test_canvas_graded_hac_blank_is_waiting_until_seven_days():
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=18.0), "hac": hac(rid=3)})
    assert (v.state, v.kind) == (V.WAITING, "hac_lag")
    assert v.asks_on.isoformat() == "2026-09-22"


def test_canvas_graded_hac_blank_after_seven_days_is_a_question():
    v = run(item(), {"canvas": canvas(rid=2, state="graded", score=18.0), "hac": hac(rid=2)})
    assert (v.state, v.kind) == (V.QUESTION, "hac_still_blank")
    assert v.facts == {"canvas": "18 of 30", "when": "9/8"}


def test_a_class_with_no_hac_twin_never_waits_for_hac():
    """Review Focus 3."""
    v = run(item(peer=None), {"canvas": canvas(rid=1, state="graded", score=18.0)})
    assert v.state == V.STATUS


def test_a_canvas_zero_with_hac_blank_is_not_done_not_a_hac_question():
    v = run(item(), {"canvas": canvas(rid=1, state="graded", score=0.0), "hac": hac(rid=1)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")


def test_submitted_and_ungraded_is_waiting_on_the_teacher():
    v = run(item(), {"canvas": canvas(state="submitted", submitted_at="2026-09-14T20:00:00-04:00")})
    assert (v.state, v.kind) == (V.WAITING, "teacher_grading")


def test_paper_with_no_grade_waits_seven_calendar_days():
    v = run(item(kind="paper", due="2026-09-10T23:59:00-04:00"), {"canvas": canvas()})
    assert (v.state, v.kind) == (V.WAITING, "awaiting_grade")
    assert v.asks_on.isoformat() == "2026-09-17"


def test_paper_with_no_grade_after_seven_days_is_a_question():
    v = run(item(kind="paper", due="2026-09-08T23:59:00-04:00"), {"canvas": canvas()})
    assert (v.state, v.kind) == (V.QUESTION, "still_ungraded")
    assert v.facts == {"kind": "paper", "due": "Tue 9/8"}


def test_hac_only_with_no_grade_follows_the_same_grace():
    v = run(item(kind="", due="2026-09-08T23:59:00-04:00", peer=None), {"hac": hac()})
    assert v.kind == "still_ungraded"


def test_an_undated_item_is_a_status_never_a_question():
    """Review Focus 1."""
    v = run(item(kind="paper", due=None), {"canvas": canvas()})
    assert v.state == V.STATUS


def test_open_work_past_its_credit_window_is_a_status():
    v = run(item(due="2026-08-20T23:59:00-04:00"), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "past_credit")


def test_open_work_inside_its_window_is_a_not_done_status():
    v = run(item(due="2026-09-12T23:59:00-04:00"), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")

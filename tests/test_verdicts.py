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


def _sample_facts(kind):
    return {"hac": "28 of 30", "canvas": "20 of 25", "when": "9/14", "why": "late", "flag": "done",
            "change": "Canvas now says missing", "kind": "paper", "due": "Thu 9/10", "school": "Canvas marks it missing"}


def test_every_question_kind_has_facts_ask_and_answer_words():
    for kind, answers in V.ANSWERS.items():
        assert V.say("facts." + kind, "", _sample_facts(kind)) != "facts." + kind, kind
        for a in answers:
            assert V.say(a.key, "") != a.key, a.key
    for kind in ("missing_after_grade", "hac_lower", "submitted_hac_zero", "excused_hac_zero",
                 "hac_still_blank", "still_ungraded", "stale_answer"):
        assert V.say("ask." + kind, "") != "ask." + kind, kind


def test_facts_are_filled_in_and_escaped_by_the_template_not_here():
    assert V.say("facts.graded_in_hac", "", {"hac": "28 of 30"}) == "HAC has 28 of 30. Canvas still shows its automatic \"missing\"."


# --- final-review fixes ------------------------------------------------------------------

def test_a_graded_ask_teacher_is_asked_then_graded_with_its_own_answers():
    """Review 2: a teacher grading work the family asked about is not "still done?"."""
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=28.0)}, flag="ask_teacher",
            flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "asked_then_graded")
    assert [a.flag for a in v.answers] == ["done", "confirm"]
    assert V.say("ask." + v.kind, "") != "ask." + v.kind


def test_waiting_rules_never_contradict_an_excused_or_unpublished_outcome():
    """Review 5 (S19, S20)."""
    sub = "2026-09-12T20:00:00-04:00"
    assert run(item(), {"canvas": canvas(excused=1, state="submitted", submitted_at=sub)}).kind == "excused"
    assert run(item(), {"canvas": canvas(published=0, state="submitted", submitted_at=sub)}).kind == "unpublished"


def test_a_teacher_missing_mark_is_not_done_even_with_a_score_or_a_submission():
    """Review 5 (S18, S22): Canvas's missing flag with a Canvas score and no HAC grade, or with a
    submission, is not something to wait on."""
    v = run(item(), {"canvas": canvas(rid=3, missing=1, state="graded", score=5.0), "hac": hac(rid=3)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")
    v = run(item(), {"canvas": canvas(missing=1, state="submitted", submitted_at="2026-09-12T20:00:00-04:00")})
    assert (v.state, v.kind) == (V.STATUS, "not_done")


def test_a_zero_both_gradebooks_agree_on_is_not_a_question():
    """Review 6: Canvas graded the submission 0 and HAC has 0; nothing to tell the teacher."""
    v = run(item(), {"canvas": canvas(state="graded", score=0.0, submitted_at="2026-09-12T20:00:00-04:00"), "hac": hac(score=0.0)})
    assert v.state == V.STATUS


# --- deferred review findings --------------------------------------------------------------

def test_follow_up_is_its_own_status_not_asked_the_teacher():
    """Finding 12: "follow up" is the family's own reminder; nobody asked the teacher."""
    v = run(item(), {"canvas": canvas(missing=1)}, flag="follow_up", flag_set_at="2026-09-15T08:00:00-04:00")
    assert (v.state, v.kind) == (V.STATUS, "following_up")
    assert "teacher" not in V.say("where.following_up", "", v.facts).lower()


def test_a_graded_follow_up_does_not_say_you_asked_the_teacher():
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=28.0)}, flag="follow_up",
            flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "followed_up_then_graded")
    assert [a.flag for a in v.answers] == ["done", "confirm"]
    assert "asked the teacher" not in V.say("facts." + v.kind, "", v.facts).lower()


def test_under_the_hac_preference_a_later_missing_is_decided_not_asked():
    """Finding 7: a class set to trust HAC already counts it done; asking which is right
    contradicts the family's own setting."""
    obs = {"canvas": canvas(rid=3, missing=1), "hac": hac(rid=2, score=28.0)}
    v = V.verdict(item(), obs, flag=None, flag_set_at="", now=NOW, rules=RULES, refresh_times=TIMES, prefer="hac")
    assert (v.state, v.kind) == (V.DECIDED, "graded_in_hac")
    assert run(item(), obs).kind == "missing_after_grade"          # the default preference still asks


# --- second persona pass: answers, the asked trail, missing work (#71, #73, #74) ----------------

from types import SimpleNamespace as _NS


def _view(verdict, flag=None, grade="", status=""):
    return _NS(verdict=verdict, flag=flag, grade=grade, status=status, grade_source="")


def test_an_answered_item_says_what_was_recorded_and_when():
    """#71: "Answered" told a grandparent nothing."""
    v = run(item(), {"canvas": canvas(missing=1)}, flag="ignore", flag_set_at="2026-09-15T08:00:00-04:00")
    assert v.facts == {"when": "9/15"}
    assert V.standing(_view(v, flag="ignore"), "") == "Let go on 9/15"
    v = run(item(), {"canvas": canvas(missing=1)}, flag="done", flag_set_at="2026-09-15T08:00:00-04:00")
    assert V.standing(_view(v, flag="done"), "") == "Marked done on 9/15"


def test_asked_says_when_in_where_it_stands():
    v = run(item(), {"canvas": canvas(missing=1)}, flag="ask_teacher", flag_set_at="2026-09-15T08:00:00-04:00")
    assert V.standing(_view(v, flag="ask_teacher"), "") == "Asked the teacher on 9/15"


def _run_prev(obs, prev, flag, set_at):
    return V.verdict(item(), obs, flag=flag, flag_set_at=set_at, now=NOW, rules=RULES, refresh_times=TIMES, prev_obs=prev)


def test_canvas_clearing_missing_after_an_ask_closes_the_loop():
    """#73: the teacher cleared Canvas's missing flag without entering a Canvas score."""
    v = _run_prev({"canvas": canvas(rid=3, missing=0)}, {"canvas": canvas(rid=1, missing=1)},
                  "ask_teacher", "2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "asked_then_graded")
    assert v.facts["change"] == "Canvas no longer marks it missing"


def test_an_unchanged_score_after_an_ask_is_not_news():
    v = _run_prev({"canvas": canvas(rid=1, missing=1), "hac": hac(rid=3, score=28.0)},
                  {"hac": hac(rid=1, score=28.0)}, "ask_teacher", "2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.STATUS, "asked")


def test_a_changed_score_after_an_ask_says_before_and_after():
    v = _run_prev({"canvas": canvas(rid=1, missing=1), "hac": hac(rid=3, score=28.0)},
                  {"hac": hac(rid=1, score=20.0)}, "ask_teacher", "2026-09-10T08:00:00-04:00")
    assert v.kind == "asked_then_graded" and v.facts["change"] == "HAC changed the grade: 20 → 28 of 30"


def test_missing_work_offers_handed_in_and_plan_without_asking():
    """#74: a red row with no question still needs a one-tap "it's handed in"."""
    v = run(item(), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")
    assert [a.flag for a in v.answers] == ["done", None]
    assert V.say("facts.not_done", "", v.facts) == "Canvas marks it missing."


def test_past_credit_work_offers_let_it_go():
    v = run(item(due="2026-08-20T23:59:00-04:00"), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "past_credit")
    assert [a.flag for a in v.answers] == ["ignore", "done"]

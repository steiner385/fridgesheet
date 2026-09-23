"""The learned pace: what the history says a class usually takes (spec section 4)."""
from __future__ import annotations

from fridgesheet.web import pace as P


def test_fewer_than_three_samples_is_no_estimate():
    assert P.estimate([]) is None
    assert P.estimate([4, 5]) is None


def test_the_estimate_is_the_80th_percentile_by_nearest_rank():
    assert P.estimate([1, 2, 3, 4, 10]) == 4          # rank ceil(0.8 * 5) = 4 -> 4th smallest
    assert P.estimate([3, 3, 3]) == 3                  # rank ceil(2.4) = 3
    assert P.estimate([2, 9, 1, 4]) == 9               # sorted 1,2,4,9; rank ceil(3.2) = 4 -> 4th smallest


def test_floor_and_cap():
    assert P.estimate([0, 0, 0]) == 1
    assert P.estimate([30, 40, 50]) == 21


def test_zeros_are_not_samples():
    """Review Focus 1: the store never feeds zeros in, and a table of nothing is the default."""
    pace = P.Pace(grade={(5, "offline"): []}, hac={}, classes={5: 5}, teachers={})
    assert pace.grade_days({"course_id": 5, "kind": "paper", "teacher": "Hoch"}) == P.Estimate(7, 0, "default")


def test_kind_group():
    assert P.kind_group("online") == "online"
    for kind in ("paper", "in class", ""):
        assert P.kind_group(kind) == "offline", kind


def _item(course_id=5, kind="paper", teacher="Michael Hoch"):
    return {"course_id": course_id, "kind": kind, "teacher": teacher}


def test_the_course_and_kind_group_come_first():
    pace = P.Pace(grade={(5, "offline"): [9, 10, 12], (5, "online"): [1, 1, 1]}, hac={}, classes={5: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(kind="paper")) == P.Estimate(12, 3, "course_kind")
    assert pace.grade_days(_item(kind="online")) == P.Estimate(1, 3, "course_kind")


def test_then_the_whole_course_pooled_across_kinds_for_online_work():
    pace = P.Pace(grade={(5, "offline"): [9], (5, "online"): [1, 2]}, hac={}, classes={5: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(kind="online")) == P.Estimate(9, 3, "course")


def test_paper_work_never_borrows_the_online_pace():
    """Review: auto-graded quizzes must not teach the app that paper is graded the same day.
    Offline work skips the pooled tier and goes to the same teacher's offline work, else the default."""
    pace = P.Pace(grade={(5, "online"): [1, 1, 1, 1], (5, "offline"): [9]}, hac={}, classes={5: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(kind="paper")) == P.Estimate(7, 0, "default")
    pace = P.Pace(grade={(5, "online"): [1, 1, 1, 1], (8, "offline"): [6, 7, 8]}, hac={},
                  classes={5: 5, 8: 8}, teachers={5: "michael hoch", 8: "michael hoch"})
    assert pace.grade_days(_item(kind="paper")) == P.Estimate(8, 3, "teacher")


def test_then_the_same_teacher_across_the_household_same_kind():
    pace = P.Pace(grade={(5, "offline"): [2], (8, "offline"): [6, 7], (9, "offline"): [40, 40, 40]}, hac={},
                  classes={5: 5, 8: 8, 9: 9}, teachers={5: "michael hoch", 8: "michael hoch", 9: "dana lee"})
    assert pace.grade_days(_item(course_id=5, kind="paper", teacher=" Michael HOCH ")) == P.Estimate(7, 3, "teacher")


def test_a_different_teacher_is_never_pooled():
    pace = P.Pace(grade={(9, "offline"): [40, 40, 40]}, hac={}, classes={5: 5, 9: 9}, teachers={5: "michael hoch", 9: "dana lee"})
    assert pace.grade_days(_item(course_id=5)) == P.Estimate(7, 0, "default")


def test_an_unknown_course_and_a_blank_teacher_are_the_default():
    pace = P.Pace(grade={(5, "offline"): [9, 10, 12]}, hac={}, classes={5: 5}, teachers={5: ""})
    assert pace.grade_days(_item(course_id=77, teacher="")) == P.Estimate(7, 0, "default")
    assert pace.grade_days(_item(course_id=5, teacher="")).scope == "course_kind"     # its own history still counts


def test_a_hac_twin_shares_its_canvas_course_history():
    pace = P.Pace(grade={(5, "offline"): [9, 10, 12]}, hac={}, classes={5: 5, 6: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(course_id=6, kind="")) == P.Estimate(12, 3, "course_kind")


def test_hac_days_reads_the_hac_table():
    pace = P.Pace(grade={}, hac={(5, "online"): [2, 3, 5]}, classes={5: 5}, teachers={})
    assert pace.hac_days(_item(kind="online")) == P.Estimate(5, 3, "course_kind")
    assert pace.hac_days(_item(kind="paper")) == P.Estimate(5, 3, "course")


def test_the_default_pace_object_always_answers_seven():
    assert P.DEFAULT.grade_days(_item()) == P.Estimate(7, 0, "default")
    assert P.DEFAULT.hac_days(_item()) == P.Estimate(7, 0, "default")

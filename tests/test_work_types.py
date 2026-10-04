"""The assignment-type classifier (spec 2026-10-04 assignment types §4): four families, a
six-rung ladder, keyword rows tried in order."""
from __future__ import annotations

import pytest

from fridgesheet import work_types as wt
from fridgesheet.work_types import Facts, Rule


# Names and gradebook labels from the household's snapshot (spec §1).
@pytest.mark.parametrize("facts, family", [
    (Facts("WS #2-4 A", canvas_group="Assignments", hac_category="Assignments"), "practice"),
    (Facts("Concept 2:  Cell Transport Video Notes Part 1", canvas_group="Assignments"), "practice"),
    (Facts("Unit 3 Test", canvas_group="Assignments"), "assessment"),
    (Facts("Chapter 4", canvas_group="Quizzes & Tests"), "assessment"),
    (Facts("Ch 2", hac_category="Pre-Tests"), "assessment"),
    (Facts("Week 3", canvas_group="Assessments"), "assessment"),
    (Facts("Density", hac_category="Labs"), "lab_project"),
    (Facts("Density", canvas_group="LABS"), "lab_project"),
    (Facts("Scales", hac_category="Playing/Written Work"), "participation"),
    (Facts("Fall concert", hac_category="Concert Attendance"), "participation"),
    (Facts("p. 41", canvas_group="HMWK"), "practice"),
    (Facts("p. 41", hac_category="Homework Completion"), "practice"),
    (Facts("Bell work", hac_category="Daily"), "practice"),
    (Facts("Socratic Seminar", hac_category="Assignments"), "participation"),
    (Facts("Lab Quiz"), "assessment"),                          # assessment row is tried first
    (Facts("Label the map"), "practice"),                       # "lab" needs a word boundary
    (Facts("Example problems"), "practice"),                    # "exam" needs a word boundary
    (Facts("Lab3 write-up"), "lab_project"),                    # a digit is a boundary
])
def test_real_names_get_the_family_a_parent_would_give(facts, family):
    assert wt.family_of(facts).family == family


def test_each_rung_of_the_ladder_answers_in_order():
    f = Facts("Unit 3 Test", canvas_group="Labs", hac_category="Homework", online_quiz=True)
    rule = Rule(1, "name_prefix", "unit", "participation", "2026-10-04T10:00:00")
    assert wt.family_of(f, [rule], "practice").rung == 1
    assert wt.family_of(f, [rule], "practice").family == "practice"
    assert (wt.family_of(f, [rule]).rung, wt.family_of(f, [rule]).family) == (2, "participation")
    assert (wt.family_of(f).rung, wt.family_of(f).family) == (3, "assessment")
    no_quiz = Facts("Unit 3 Test", canvas_group="Labs", hac_category="Homework")
    assert (wt.family_of(no_quiz).rung, wt.family_of(no_quiz).family) == (4, "practice")   # HAC before Canvas
    only_name = Facts("Unit 3 Test", canvas_group="Assignments")
    assert (wt.family_of(only_name).rung, wt.family_of(only_name).family) == (5, "assessment")
    nothing = Facts("Evidence Tracker", canvas_group="Assignments", hac_category="Total Points")
    t = wt.family_of(nothing)
    assert (t.rung, t.family, t.why) == (6, "practice", "type.why.default")


def test_hac_wins_at_rung_four_but_a_generic_hac_name_defers_to_canvas():
    assert wt.family_of(Facts("x", canvas_group="Quiz", hac_category="Labs")).family == "lab_project"
    assert wt.family_of(Facts("x", canvas_group="Quiz", hac_category="Assignments")).family == "assessment"
    t = wt.family_of(Facts("x", canvas_group="Quiz", hac_category="Assignments"))
    assert (t.why, t.values) == ("type.why.canvas", {"name": "Quiz"})


def test_a_non_generic_gradebook_name_with_no_keyword_falls_through_to_the_item_name():
    t = wt.family_of(Facts("Chapter 2 Test", canvas_group="Smartbook"))
    assert (t.rung, t.family) == (5, "assessment")


def test_rules_group_beats_prefix_longest_prefix_then_newest():
    f = Facts("WS #2-4 A", canvas_group="Classwork")
    group = Rule(1, "group", "classwork", "participation", "2026-10-01T00:00:00")
    short = Rule(2, "name_prefix", "ws", "assessment", "2026-10-03T00:00:00")
    long_ = Rule(3, "name_prefix", "ws #", "lab_project", "2026-10-02T00:00:00")
    assert wt.family_of(f, [short, long_, group]).family == "participation"
    assert wt.family_of(f, [short, long_]).family == "lab_project"
    older = Rule(4, "name_prefix", "ws #", "assessment", "2026-09-01T00:00:00")
    assert wt.family_of(f, [older, long_]).family == "lab_project"


def test_a_group_rule_matches_either_gradebook_name_case_folded():
    rule = Rule(1, "group", "assignments", "practice", "t")
    assert wt.family_of(Facts("Unit Test", hac_category=" ASSIGNMENTS "), [rule]).rung == 2
    assert wt.family_of(Facts("Unit Test", canvas_group="Assignments"), [rule]).rung == 2
    assert wt.family_of(Facts("Unit Test", canvas_group="Homework"), [rule]).rung == 4   # no match: the group's own name answers


def test_generic_names():
    assert wt.is_generic("Imported Assignments") and wt.is_generic("  total points ")
    assert wt.is_generic(None) and wt.is_generic("")
    assert not wt.is_generic("Homework")


@pytest.mark.parametrize("name, prefix", [
    ("WS #2-4 A", "WS #"), ("Unit #0 - Canvas Review", "Unit #"), ("Chapter 1.3 Reading Guide", "Chapter"),
    ("7", None), ("A1 warmup", None), ("Most Dangerous Game Evidence Tracker", "Most Dangerous Game Evidence Tracker"),
])
def test_prefix_suggestion_is_the_text_before_the_first_digit(name, prefix):
    assert wt.prefix_suggestion(name) == prefix


def test_coverage_counts_every_rung():
    typed = [wt.family_of(Facts("Unit Test")), wt.family_of(Facts("x")), wt.family_of(Facts("y"))]
    assert wt.coverage(typed) == {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2}


def test_rank_orders_tests_first():
    assert sorted(wt.FAMILIES, key=wt.RANK.__getitem__) == ["assessment", "lab_project", "practice", "participation"]

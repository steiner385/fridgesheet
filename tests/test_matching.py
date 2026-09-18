"""Course and assignment pairing across Canvas and HAC lives in its own module so the
printed sheet can use it without importing the MCP server."""
from __future__ import annotations

from fridgesheet.matching import match_course, same_item, short_course


def test_short_course_strips_term_year_and_teacher_tails():
    assert short_course("Adv Social Studies 7-2027-Collett") == "Adv Social Studies 7"
    assert short_course("Honors Algebra II S1-2027-Hoch") == "Honors Algebra II"
    assert short_course("Math Plus 5th Gr-2027-Pene") == "Math Plus 5th Gr"
    assert short_course("Algebra II - 3") == "Algebra II"


def test_same_item_tolerates_wording_but_not_numbers():
    assert same_item("MakeMusic Cloud Assignment #1", "MakeMusic Assignment #1")
    assert not same_item("Quiz 1", "Quiz 2")


def test_match_course_pairs_differently_abbreviated_names():
    table = {"ELA Plus 5th Gr": "ela", "Adv Math 7 - 2": "math7", "Adv Math 8 - 2": "math8"}
    assert match_course("ENGLISH LANGUAGE ARTS", table) == "ela"
    assert match_course("Adv Math 7-2027-Nagy", table) == "math7"
    assert match_course("", table) is None

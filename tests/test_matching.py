"""Course and assignment pairing across Canvas and HAC lives in its own module so the
printed sheet can use it without importing the MCP server."""
from __future__ import annotations

from fridgesheet.matching import course_matches, kid_matches, match_course, same_item, short_course


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


def test_kid_matches_the_name_or_a_short_form_of_it_never_a_longer_one():
    assert kid_matches("", "anyone")
    assert kid_matches("alex", "Alex") and kid_matches("Alex", "Alexander")
    assert not kid_matches("Alexander", "Alex")          # was a two-way prefix (#134)
    assert not kid_matches("Max", "Maxine", household=["Max", "Maxine"])
    assert kid_matches("Max", "Max", household=["Max", "Maxine"])
    assert kid_matches("Max", "Maxine", household=["Maxine", "Sam"])   # no Max in the house: a short form


def test_course_matches_whole_words_for_every_rule():
    assert not course_matches("Algebra I", "Algebra II")
    assert course_matches("English 9", "Honors English 9 S1-2027-Hoch")
    assert course_matches("", "anything")


def test_course_aliases_are_read_when_used_not_when_imported(monkeypatch):
    """#148: `FRIDGESHEET_COURSE_ALIASES` was parsed at import, before `.env` was loaded."""
    import json
    from fridgesheet import matching
    assert matching.course_base("ENGLISH LANGUAGE ARTS") != matching.course_base("ELA Plus 5th Gr")
    monkeypatch.setenv("FRIDGESHEET_COURSE_ALIASES", json.dumps({"ENGLISH LANGUAGE ARTS": "ELA Plus 5th Gr"}))
    assert matching.course_base("ENGLISH LANGUAGE ARTS") == matching.course_base("ELA Plus 5th Gr")
    monkeypatch.setenv("FRIDGESHEET_COURSE_ALIASES", "not json")          # ignored, never fatal
    assert matching.course_base("ENGLISH LANGUAGE ARTS") == "english language arts"
    monkeypatch.delenv("FRIDGESHEET_COURSE_ALIASES")
    assert matching.course_aliases() == {}

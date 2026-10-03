"""The account of a class average (spec 2026-10-03 §4), on the household's own numbers.

Every HAC class whose subtotal rows the scraper saw rebuilt to HAC's marking-period average as
straight total points; the module checks that on each class rather than assuming it."""
from __future__ import annotations

import logging

from fridgesheet import grading


def _sub(category, earned, possible, percent=""):
    return {"category": category, "earned": earned, "possible": possible, "percent": percent}


def _row(category, score, points, excused=False):
    return {"category": category, "score": score, "points": points, "excused": excused}


# Honors Algebra II, 2026-10-03: two subtotals, 25 points of blank work already counted as zero.
ALGEBRA_SUBS = [_sub("Assessments", 290.66, 400.0, "72.665%"), _sub("Assignments", 78.25, 120.5, "64.937%")]
ALGEBRA_ROWS = [_row("Assessments", 290.66, 400.0), _row("Assignments", 78.25, 95.5),
                _row("Assignments", None, 15.0), _row("Assignments", None, 10.0), _row("Assignments", None, 5.0)]


def test_straight_points_rebuild_matches_hac_within_a_hundredth():
    a = grading.account_hac(70.88, ALGEBRA_SUBS, ALGEBRA_ROWS)
    assert a.basis == "subtotals" and a.match == "exact"
    assert (a.earned, a.possible) == (368.91, 520.5)
    assert round(a.rebuilt, 2) == 70.88                # 368.91 / 520.5 = 70.876: HAC's own number
    assert [l.category for l in a.lines] == ["Assessments", "Assignments"]
    assert round(a.lines[0].share, 3) == round(400 / 520.5, 3)


def test_blank_work_counted_as_zero_is_capped_by_the_blank_rows_that_could_explain_it():
    a = grading.account_hac(70.88, ALGEBRA_SUBS, ALGEBRA_ROWS)
    assert a.zero_points == 25.0                      # 120.5 - 95.5 = 25, and 30 points of blanks exist
    fewer_blanks = [r for r in ALGEBRA_ROWS if r["points"] != 10.0]       # only 20 points of blank rows
    assert grading.account_hac(70.88, ALGEBRA_SUBS, fewer_blanks).zero_points == 20.0
    no_rows = grading.account_hac(70.88, ALGEBRA_SUBS, [])
    assert no_rows.zero_points == 0.0                 # rows the scraper never saw are not blank work


def test_a_category_with_rows_but_no_subtotal_row_is_summed_from_the_rows_and_listed_last():
    # Honors Biology: HAC's category table leaves Final Exam out; its rows make the rebuild exact.
    subs = [_sub("Assignments", 9.5, 12.0), _sub("Daily", 88.5, 100.0), _sub("Homework", 22.7, 25.0),
            _sub("Labs", 50.0, 80.0), _sub("Quiz", 95.83, 120.0)]
    rows = [_row("Daily", 88.5, 100.0), _row("Final Exam", 12.0, 12.0), _row("Labs", None, 20.0)]
    a = grading.account_hac(79.81, subs, rows)
    assert a.match == "exact" and round(a.rebuilt, 2) == 79.81
    assert a.lines[-1].category == "Final Exam" and a.lines[-1].from_rows and a.lines[-1].rows == 1
    assert all(not l.from_rows for l in a.lines[:-1])


def test_without_subtotal_rows_the_account_is_built_from_the_rows_and_says_when_it_is_off():
    # Math Plus 5th: HAC shows no category table and the rows do not rebuild its number.
    rows = [_row("Assignments", 38.0, 40.0), _row("Quiz", 11.0, 17.0), _row("Daily", 25.0, 25.0)]
    a = grading.account_hac(86.57, [], rows)
    assert a.basis == "rows" and a.match == "off"
    assert round(a.rebuilt, 2) == 90.24 and a.zero_points == 0.0
    assert all(l.from_rows for l in a.lines) and sum(l.rows for l in a.lines) == 3


def test_excused_rows_are_counted_and_never_summed():
    rows = [_row("Assignments", 28.0, 30.0), _row("Assignments", None, 10.0, excused=True)]
    a = grading.account_hac(93.33, [_sub("Assignments", 28.0, 30.0)], rows)
    assert a.excused == 1 and a.zero_points == 0.0 and a.match == "exact"


def test_nothing_at_all_is_basis_none_and_unknown():
    a = grading.account_hac(None, [], [])
    assert (a.basis, a.match, a.rebuilt, a.lines) == ("none", "unknown", None, ())


def test_no_reported_average_is_unknown_not_off():
    a = grading.account_hac(None, [_sub("Assignments", 28.0, 30.0)], [_row("Assignments", 28.0, 30.0)])
    assert a.match == "unknown" and round(a.rebuilt, 2) == 93.33


def test_a_category_with_nothing_possible_has_no_percent():
    a = grading.account_hac(88.0, [_sub("Assignments", 44.0, 50.0), _sub("Project", 0.0, 0.0)], [])
    assert a.lines[1].percent is None and a.lines[1].share == 0.0 and a.match == "exact"


def test_extra_credit_reads_above_a_hundred_and_earns_the_top_letter():
    a = grading.account_hac(101.67, [_sub("Quiz", 61.0, 60.0)], [_row("Quiz", 61.0, 60.0)])
    assert round(a.lines[0].percent, 2) == 101.67 and a.match == "exact"
    assert grading.TEN_POINT.letter(101.67) == "A"


def test_canvas_account_is_by_group_over_graded_rows_and_carries_final_hidden_and_missing():
    rows = [{"group": "Homework", "score": 68.8, "points": 100.0, "excused": False, "missing": False, "state": "graded"},
            {"group": "Homework", "score": None, "points": 10.0, "excused": False, "missing": True, "state": "unsubmitted"},
            {"group": "Labs", "score": None, "points": 20.0, "excused": False, "missing": True, "state": "unsubmitted"},
            {"group": "Labs", "score": None, "points": 5.0, "excused": True, "missing": False, "state": "unsubmitted"}]
    a = grading.account_canvas(68.8, 51.1, False, rows)
    assert a.source == "canvas" and a.basis == "rows" and a.match == "exact"
    assert [(l.category, l.earned, l.possible, l.rows) for l in a.lines] == [("Homework", 68.8, 100.0, 1)]
    assert (a.final, a.hidden, a.missing, a.excused) == (51.1, False, 2, 1)
    hidden = grading.account_canvas(None, None, True, rows)
    assert hidden.hidden and hidden.match == "unknown"


def test_the_ten_point_scale_at_every_floor_and_on_none():
    s = grading.TEN_POINT
    assert [s.letter(v) for v in (100, 90, 89.99, 80, 79.5, 70, 69, 60, 59.99, 0)] == ["A", "A", "B", "B", "C", "C", "D", "D", "F", "F"]
    assert s.letter(None) == ""


def test_a_scale_from_config_sorts_by_floor_and_allows_plus_and_minus():
    s = grading.scale_from_doc({"grading": {"scale": {"A": 93, "A-": 90, "B+": 87, "B": 83}, "below": "C"}})
    assert s.cuts == (("A", 93.0), ("A-", 90.0), ("B+", 87.0), ("B", 83.0)) and s.below == "C"
    assert [s.letter(v) for v in (95, 91, 88, 83, 50)] == ["A", "A-", "B+", "B", "C"]


def test_a_malformed_grading_section_warns_and_keeps_the_default(caplog):
    with caplog.at_level(logging.WARNING, logger="fridgesheet.grading"):
        assert grading.scale_from_doc({"grading": {"scale": "A B C"}}) == grading.TEN_POINT
        assert grading.scale_from_doc({"grading": {"scale": {"A": "ninety"}}}) == grading.TEN_POINT
    assert "[grading]" in caplog.text
    assert grading.scale_from_doc({}) == grading.TEN_POINT


def test_number_formatting_for_phrases():
    assert grading.fmt_points(25.0) == "25" and grading.fmt_points(368.91) == "368.91" and grading.fmt_points(520.5) == "520.5"
    assert grading.fmt_avg(70.874) == "70.87" and grading.fmt_avg(100.0) == "100.00" and grading.fmt_avg(None) == ""

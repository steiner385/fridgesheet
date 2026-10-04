"""What moves the grade (spec 2026-10-04 §3-§4), on the household's own numbers."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fridgesheet import grading, guidance

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 4, 9, 0, tzinfo=TZ)


def _sub(category, earned, possible):
    return {"category": category, "earned": earned, "possible": possible, "percent": ""}


def _hrow(category, score, points, excused=False):
    return {"category": category, "score": score, "points": points, "excused": excused}


def _row(name, points, *, category="Assignments", due_days=-5, overdue=True, upcoming=False, hac_blank=False,
         hac_scored=False, hac_zero=False, credit="?", late_days=14, item_id=None):
    due = NOW + timedelta(days=due_days)
    return {"item_id": item_id, "name": name, "category": category, "points": points, "due": due,
            "late_until": due + timedelta(days=late_days), "credit_text": credit, "overdue": overdue,
            "upcoming": upcoming, "hac_blank": hac_blank, "hac_scored": hac_scored, "hac_zero": hac_zero}


# Concert Band: Daily 175/175, Playing 92/130; 25 blank points in Playing already counted as zero.
BAND = grading.account_hac(87.54, [_sub("Daily", 175.0, 175.0), _sub("Playing/Written Work", 92.0, 130.0)],
                           [_hrow("Daily", 175.0, 175.0), _hrow("Playing/Written Work", 92.0, 105.0),
                            _hrow("Playing/Written Work", None, 25.0)])


def test_zeros_alone_can_reach_the_next_letter():
    g = guidance.guide(BAND, [_row("Scale test", 25.0, category="Playing/Written Work", hac_blank=True)], grading.TEN_POINT)
    assert g.sound and g.letter == "B"
    (lever,) = g.levers
    assert lever.kind == "zero" and round(lever.worth, 2) == round(100 * 25 / 305, 2)      # earned grows, possible fixed
    assert g.reach.letter == "A" and g.reach.needed <= 0 and g.reach.reachable
    assert g.zero_points == 25.0


def test_missing_and_upcoming_levers_add_to_both_sides_of_the_fraction():
    # Honors Biology: 278.53 / 349 = 79.81; a 20-point lab not yet counted.
    bio = grading.account_hac(79.81, [_sub("Labs", 50.0, 80.0), _sub("Quiz", 95.83, 120.0), _sub("Daily", 132.7, 149.0)], [])
    g = guidance.guide(bio, [_row("Lab 5", 20.0, category="Labs", due_days=3, overdue=False, upcoming=True)], grading.TEN_POINT)
    (lever,) = g.levers
    assert lever.kind == "upcoming" and lever.credit == 1.0
    assert round(lever.worth, 2) == round(100 * (278.53 + 20) / 369 - bio.rebuilt, 2)
    assert g.reach.letter == "B" and round(g.reach.needed, 1) == 3.4 and g.reach.posted == 20.0 and g.reach.reachable


def test_reach_beyond_posted_work_is_reported_not_hidden():
    # Honors Algebra II: a B needs ~237 perfect points; 80 are posted.
    alg = grading.account_hac(70.88, [_sub("Assessments", 290.66, 400.0), _sub("Assignments", 78.25, 120.5)],
                              [_hrow("Assessments", 290.66, 400.0), _hrow("Assignments", 78.25, 95.5), _hrow("Assignments", None, 25.0)])
    rows = [_row("Blank quiz", 25.0, hac_blank=True), _row("Unit test", 80.0, category="Assessments", due_days=4, overdue=False, upcoming=True)]
    g = guidance.guide(alg, rows, grading.TEN_POINT)
    assert g.reach.letter == "B" and not g.reach.reachable and g.reach.needed > g.reach.posted == 80.0
    # The 25 blank points at a fixed denominator (+4.8) outrank a perfect 80-point test that
    # also widens the denominator (+3.9): the best move is the blank work.
    assert g.best.kind == "zero" and g.best.name == "Blank quiz"
    assert round(g.levers[0].worth, 1) == 4.8 and round(g.levers[1].worth, 1) == 3.9


def test_late_credit_halves_a_levers_worth_and_an_unknown_credit_is_flagged():
    g = guidance.guide(BAND, [_row("Scale test", 25.0, category="Playing/Written Work", hac_blank=True, credit="50%"),
                              _row("Rhythm sheet", 10.0, category="Playing/Written Work", credit="?")], grading.TEN_POINT)
    half, unknown = g.levers[0], g.levers[1]
    assert half.credit == 0.5 and half.credit_known and round(half.worth, 2) == round(100 * 12.5 / 305, 2)
    assert unknown.credit == 1.0 and not unknown.credit_known


def test_zero_allocation_is_oldest_due_first_within_the_category():
    rows = [_row("Newer", 15.0, category="Playing/Written Work", hac_blank=True, due_days=-2),
            _row("Older", 15.0, category="Playing/Written Work", hac_blank=True, due_days=-9),
            _row("Oldest", 5.0, category="Playing/Written Work", hac_blank=True, due_days=-12)]
    g = guidance.guide(BAND, rows, grading.TEN_POINT)
    kinds = {l.name: l.kind for l in g.levers}
    assert kinds == {"Oldest": "zero", "Older": "zero", "Newer": "missing"}            # 5 + 15 fill the 25; the newest is not counted yet


def test_a_future_blank_row_is_upcoming_not_a_zero():
    g = guidance.guide(BAND, [_row("Next scale", 25.0, category="Playing/Written Work", hac_blank=True, due_days=2, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.levers[0].kind == "upcoming" and g.zero_points == 0.0


def test_a_scored_row_and_a_pointless_row_are_never_levers():
    g = guidance.guide(BAND, [_row("Graded", 10.0, hac_scored=True), _row("Attendance", 0.0)], grading.TEN_POINT)
    assert g.levers == ()


def test_an_unsound_account_gives_points_but_no_worth_reach_or_slack():
    off = grading.account_hac(86.57, [], [_hrow("Quiz", 11.0, 17.0)])
    g = guidance.guide(off, [_row("Quiz 2", 17.0, category="Quiz", due_days=2, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert not g.sound and g.levers[0].worth is None and g.reach is None and g.slack is None


def test_at_the_top_letter_there_is_no_reach_only_slack():
    health = grading.account_hac(100.0, [_sub("Total Points", 585.0, 585.0)], [])
    g = guidance.guide(health, [_row("Unit quiz", 115.0, category="Total Points", due_days=5, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.reach is None and g.slack.letter == "A"
    assert round(g.slack.can_miss, 1) == round(585 + 115 - 0.9 * 700, 1) and g.slack.posted == 115.0


def test_below_the_next_letter_the_slack_and_the_reach_both_hold():
    # Total points cannot give a negative slack: sitting at a letter means E/P is at its floor.
    low = grading.account_hac(79.9, [_sub("A", 39.95, 50.0)], [])
    g = guidance.guide(low, [_row("Next", 10.0, category="A", due_days=1, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.slack.letter == "C" and g.slack.can_miss > 0
    assert g.reach.letter == "B" and g.reach.reachable                                    # 80 is within the next 10


def test_ranking_is_worth_then_deadline_and_a_lever_without_a_deadline_ranks_last_among_ties():
    rows = [_row("B", 10.0, due_days=-3), _row("A", 10.0, due_days=-6)]
    undated = _row("U", 10.0, due_days=-4)
    undated["due"] = None
    undated["late_until"] = None
    g = guidance.guide(BAND, rows + [undated], grading.TEN_POINT)
    assert [l.name for l in g.levers] == ["A", "B", "U"]


def test_fmt_worth():
    assert guidance.fmt_worth(2.0) == "2.0" and guidance.fmt_worth(4.84) == "4.8" and guidance.fmt_worth(0.04) == "0.0"


def test_with_article():
    assert guidance.with_article("A") == "an A" and guidance.with_article("B") == "a B" and guidance.with_article("F") == "an F"
    assert guidance.with_article("A-") == "an A-" and guidance.with_article("") == ""


# --- final review fixes (2026-10-04) ------------------------------------------------------------------

def test_blank_rows_outside_open_work_use_the_zero_budget_first():
    # 80/90 scored, an old blank 10 HAC already zeroed (possible 100), a new blank 10 not counted yet.
    acc = grading.account_hac(80.0, [_sub("A", 80.0, 100.0)], [_hrow("A", 80.0, 90.0), _hrow("A", None, 10.0), _hrow("A", None, 10.0)])
    assert acc.lines[0].zero_points == 10.0
    old = _row("Old sheet", 10.0, category="A", hac_blank=True, due_days=-30)
    old["counted_only"] = True                                   # past its window or answered: not a lever, but HAC zeroed it
    g = guidance.guide(acc, [old, _row("New sheet", 10.0, category="A", hac_blank=True, due_days=-2)], grading.TEN_POINT)
    assert [(l.name, l.kind) for l in g.levers] == [("New sheet", "missing")]
    assert g.zero_points == 0.0 and g.reach.needed > 0          # no "turn it in and it's a B" from a row HAC never counted


def test_worth_is_never_negative_and_missing_work_says_what_a_zero_would_cost():
    acc = grading.account_hac(92.0, [_sub("A", 92.0, 100.0)], [])
    g = guidance.guide(acc, [_row("Essay", 10.0, category="A", credit="50%")], grading.TEN_POINT)
    (lever,) = g.levers
    assert lever.kind == "missing" and lever.worth == 0.0                     # at half credit it cannot raise a 92
    assert round(lever.cost, 1) == round(92 - 100 * 92 / 110, 1)              # but left blank, the zero costs 8.4


def test_an_explicit_zero_is_a_zero_lever_without_touching_the_budget():
    rows = [_row("Zeroed quiz", 10.0, category="Playing/Written Work", hac_zero=True),
            _row("Scale test", 25.0, category="Playing/Written Work", hac_blank=True)]
    g = guidance.guide(BAND, rows, grading.TEN_POINT)
    kinds = {l.name: l.kind for l in g.levers}
    assert kinds == {"Zeroed quiz": "zero", "Scale test": "zero"}            # the blank still finds its 25-point budget
    zq = next(l for l in g.levers if l.name == "Zeroed quiz")
    assert round(zq.worth, 2) == round(100 * 10 / 305, 2)


def test_a_cut_at_one_hundred_is_never_a_reach():
    scale = grading.GradeScale((("A+", 100.0), ("A", 90.0), ("B", 80.0)), "C")
    acc = grading.account_hac(95.0, [_sub("A", 95.0, 100.0)], [])
    g = guidance.guide(acc, [_row("Next", 10.0, category="A", due_days=2, overdue=False, upcoming=True)], scale)
    assert g.reach is None and g.slack.letter == "A"


# --- weighted classes ---------------------------------------------------------------------------------

def _wsub(category, earned, possible, weight=1.0):
    return {"category": category, "earned": earned, "possible": possible, "percent": "", "weight": weight}


MATH = grading.account_hac(86.57, [_wsub("Assignments", 38.0, 40.0), _wsub("Daily", 25.0, 25.0), _wsub("Quiz", 11.0, 17.0)], [])


def test_in_a_weighted_class_ten_points_of_quiz_move_it_more_than_ten_of_assignments():
    rows = [_row("Quiz 2", 10.0, category="Quiz", due_days=3, overdue=False, upcoming=True),
            _row("Worksheet", 10.0, category="Assignments", due_days=2, overdue=False, upcoming=True)]
    g = guidance.guide(MATH, rows, grading.TEN_POINT)
    assert g.sound and [l.name for l in g.levers] == ["Quiz 2", "Worksheet"]
    quiz, ws = g.levers
    assert round(quiz.worth, 2) == round((95 + 100 + 100 * 21 / 27) / 3 - MATH.rebuilt, 2)    # +4.36
    assert round(ws.worth, 2) == round((96 + 100 + 100 * 11 / 17) / 3 - MATH.rebuilt, 2)      # +0.33


def test_a_weighted_reach_is_the_ceiling_of_the_posted_work_not_a_point_count():
    rows = [_row("Quiz 2", 10.0, category="Quiz", due_days=3, overdue=False, upcoming=True)]
    g = guidance.guide(MATH, rows, grading.TEN_POINT)
    assert g.reach.letter == "A" and g.reach.needed is None and g.reach.posted == 10.0
    assert round(g.reach.ceiling, 2) == round((95 + 100 + 100 * 21 / 27) / 3, 2) and g.reach.reachable      # 90.93
    assert g.slack is None


def test_a_weighted_missing_lever_says_what_its_zero_would_cost_in_its_category():
    g = guidance.guide(MATH, [_row("Late quiz", 10.0, category="Quiz")], grading.TEN_POINT)
    (l,) = g.levers
    assert round(l.cost, 2) == round(MATH.rebuilt - (95 + 100 + 100 * 11 / 27) / 3, 2)


def test_a_lever_in_a_category_the_weighted_table_does_not_list_has_no_worth():
    g = guidance.guide(MATH, [_row("Project", 20.0, category="Project", due_days=3, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.levers[0].worth is None

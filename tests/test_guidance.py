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
         hac_scored=False, credit="?", late_days=14, item_id=None):
    due = NOW + timedelta(days=due_days)
    return {"item_id": item_id, "name": name, "category": category, "points": points, "due": due,
            "late_until": due + timedelta(days=late_days), "credit_text": credit, "overdue": overdue,
            "upcoming": upcoming, "hac_blank": hac_blank, "hac_scored": hac_scored}


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


def test_negative_slack_says_how_much_of_the_next_points_the_letter_needs():
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

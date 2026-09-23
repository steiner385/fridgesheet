"""The Grade and Status cells follow the assignments preference; the Handed-in cell never does."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web import reconcile
from fridgesheet.web.stores import items

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 21, 16, 0, tzinfo=TZ)
PAST = "2026-09-10T23:59:00-04:00"


def canvas(**kw):
    base = dict(state="unsubmitted", score=None, grade=None, submitted_at=None, late=0, missing=0, excused=0, published=1)
    base.update(kw)
    return base


def hac(score=None):
    return dict(state="graded" if score is not None else "ungraded", score=score, grade=None, submitted_at=None,
                late=None, missing=None, excused=None, published=None)


def item(points=50, kind="online"):
    return {"kind": kind, "due": PAST, "points": points}


def test_grade_cell_shows_the_preferred_score():
    obs = {"canvas": canvas(state="graded", score=12.5, grade="12.5"), "hac": hac(48.0)}
    assert items.grade_text(item(), obs) == ("12.5/50", False)
    assert items.grade_text(item(), obs, prefer="hac") == ("48/50", False)


def test_grade_cell_hac_preference_over_canvas_missing():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert items.grade_text(item(), obs) == ("Missing", False)
    assert items.grade_text(item(), obs, prefer="hac") == ("48/50", False)


def test_grade_cell_hac_zero_is_flagged_as_a_zero():
    assert items.grade_text(item(), {"canvas": canvas(state="graded", score=40), "hac": hac(0.0)}, prefer="hac") == ("0/50", True)


def test_grade_cell_falls_back_when_the_preferred_source_is_silent():
    obs = {"canvas": canvas(state="graded", score=41), "hac": hac(None)}
    assert items.grade_text(item(), obs, prefer="hac") == ("41/50", False)


def test_status_cell_follows_the_preference():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert items.status_text(item(), obs, NOW) == "Missing"
    assert items.status_text(item(), obs, NOW, prefer="hac") == "48/50"
    assert items.status_text(item(), {"canvas": canvas(excused=1), "hac": hac(48.0)}, NOW, prefer="hac") == "Excused"


def test_handed_in_is_canvas_only_whatever_the_preference():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert items.handed_in_text(item(), obs) == ("No", None)            # signature unchanged: no prefer


def test_open_sources_settles_when_hac_is_preferred_and_graded():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert reconcile.open_sources(item(), obs, NOW) == {"canvas"}
    assert reconcile.open_sources(item(), obs, NOW, prefer="hac") == set()


def test_late_hand_in_graded_in_hac_is_settled_under_hac_preference():
    """Review finding: open_sources judged "late, still ungraded" by Canvas's score alone, so the
    app kept the item open while its own Grade cell and the printed sheet said it was graded."""
    obs = {"canvas": canvas(submitted_at=PAST, late=1), "hac": hac(9.0)}
    assert reconcile.open_sources(item(points=10), obs, NOW) == {"canvas"}          # default: Canvas has no grade yet
    assert reconcile.open_sources(item(points=10), obs, NOW, prefer="hac") == set()


def test_status_never_says_missing_for_in_class_work_hac_graded():
    """Issue #32: "Missing" for in-class work was the app's guess, printed as Canvas's word.
    HAC holds the grade for work with nothing to submit online, so its score is the status."""
    obs = {"canvas": canvas(), "hac": hac(18.0)}
    assert items.status_text(item(points=25, kind="in class"), obs, NOW) == "18/25"
    assert items.status_text(item(points=25, kind="paper"), obs, NOW) == "18/25"


def test_status_for_ungraded_in_class_work_asks_rather_than_accuses():
    obs = {"canvas": canvas(), "hac": hac(None)}
    assert items.status_text(item(kind="in class"), obs, NOW) == "In class, check"
    assert items.status_text(item(kind="paper"), obs, NOW) == "Paper, check"


def test_status_still_says_missing_for_past_due_online_work():
    assert items.status_text(item(kind="online"), {"canvas": canvas(), "hac": hac(None)}, NOW) == "Missing"

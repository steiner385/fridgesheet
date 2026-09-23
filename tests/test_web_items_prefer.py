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

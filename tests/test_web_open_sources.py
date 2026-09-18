"""`reconcile.open_sources` reads the outcome definition; it no longer has a rule of its own."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web import reconcile

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=TZ)
PAST = "2026-09-10T23:59:00-04:00"


def canvas(**kw):
    base = dict(state="unsubmitted", score=None, grade=None, submitted_at=None, late=0, missing=0, excused=0, published=1)
    base.update(kw)
    return base


def hac(score=None):
    return dict(state="graded" if score is not None else "ungraded", score=score, grade=None, submitted_at=None,
                late=None, missing=None, excused=None, published=None)


def item(kind="online", due=PAST, points=10):
    return {"kind": kind, "due": due, "points": points}


def test_paper_work_graded_in_hac_is_settled():
    """The live case: Concert Contract Due, unsubmitted in Canvas, 10/10 in HAC, open 27 days."""
    assert reconcile.open_sources(item("paper"), {"canvas": canvas(), "hac": hac(10)}, NOW) == set()


def test_not_done_and_unknown_are_open_and_name_the_unsettled_sources():
    assert reconcile.open_sources(item("online"), {"canvas": canvas(missing=1)}, NOW) == {"canvas"}
    assert reconcile.open_sources(item("paper"), {"canvas": canvas()}, NOW) == {"canvas"}                # unknown
    assert reconcile.open_sources(item("paper"), {"canvas": canvas(), "hac": hac()}, NOW) == {"canvas", "hac"}
    assert reconcile.open_sources(item("paper"), {"hac": hac()}, NOW) == {"hac"}                        # HAC-only, ungraded
    assert reconcile.open_sources(item("paper"), {"hac": hac(0)}, NOW) == {"hac"}                       # HAC's zero: not done


def test_handed_in_and_graded_are_settled_and_late_stays_open_until_graded():
    assert reconcile.open_sources(item(), {"canvas": canvas(submitted_at=PAST)}, NOW) == set()
    assert reconcile.open_sources(item(), {"canvas": canvas(state="graded", score=8)}, NOW) == set()
    assert reconcile.open_sources(item(), {"canvas": canvas(submitted_at=PAST, late=1)}, NOW) == {"canvas"}
    assert reconcile.open_sources(item(), {"canvas": canvas(submitted_at=PAST, late=1, state="graded", score=8)}, NOW) == set()
    assert reconcile.open_sources(item("paper"), {"hac": hac(9)}, NOW) == set()                        # done on paper


def test_a_teachers_flag_or_zero_is_open_whatever_hac_says():
    """A disagreement between the sources is Reconcile's to show, not this function's to settle."""
    assert reconcile.open_sources(item(), {"canvas": canvas(missing=1), "hac": hac(28)}, NOW) == {"canvas"}
    assert reconcile.open_sources(item(), {"canvas": canvas(state="graded", score=0), "hac": hac(28)}, NOW) == {"canvas"}

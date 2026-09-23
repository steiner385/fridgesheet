"""The Status column split into the three facts it was hiding: due, handed in, graded.

"Missing", "Zero", "3/5", "Paper, check", "Due Sun" and "HAC, no grade" all lived in one
cell. They answer three different questions, and a parent scanning a table needs each
answered in its own place. `ItemView.status` -- the sheet's one word -- stays for the sort
and the detail card; these are the columns.
"""
from __future__ import annotations

import re

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web.stores import items

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=TZ)


def _canvas(**kw):
    base = dict(state="unsubmitted", score=None, grade=None, submitted_at=None, late=0, missing=0, excused=0, published=1)
    base.update(kw)
    return base


def _hac(score=None, grade=None):
    return dict(state="graded" if score is not None else "ungraded", score=score, grade=grade, submitted_at=None,
                late=0, missing=0, excused=0, published=None)


ONLINE = {"kind": "online", "points": 50}
PAPER = {"kind": "paper", "points": 10}


# --- due, as a distance ----------------------------------------------------------------------

def test_due_relative_speaks_in_days_a_parent_uses():
    d = lambda day: datetime(2026, 9, day, 23, 59, tzinfo=TZ)
    assert items.due_relative(d(17), NOW) == "today"
    assert items.due_relative(d(18), NOW) == "tomorrow"
    assert items.due_relative(d(20), NOW) == "Sun"        # within the week: the weekday
    assert items.due_relative(d(24), NOW) == ""           # a week out: the date alone is enough
    assert items.due_relative(d(16), NOW) == "yesterday"
    assert items.due_relative(d(10), NOW) == "7 days ago"
    assert items.due_relative(None, NOW) == ""


# --- handed in --------------------------------------------------------------------------------

def test_handed_in_reads_the_submission_not_the_grade():
    assert items.handed_in_text(ONLINE, {"canvas": _canvas()}) == ("No", None)
    yes, at = items.handed_in_text(ONLINE, {"canvas": _canvas(submitted_at="2026-09-15T20:11:00-04:00", state="submitted")})
    assert yes == "Yes" and at.day == 15
    late, _ = items.handed_in_text(ONLINE, {"canvas": _canvas(submitted_at="2026-09-16T08:00:00-04:00", late=1)})
    assert late == "Late"
    assert items.handed_in_text(ONLINE, {"canvas": _canvas(excused=1)}) == ("Excused", None)


def test_paper_and_in_class_work_is_not_a_no():
    """Canvas lists paper work as unsubmitted forever. That is not the kid skipping it."""
    assert items.handed_in_text(PAPER, {"canvas": _canvas()}) == ("On paper", None)
    assert items.handed_in_text({"kind": "in class", "points": 5}, {"canvas": _canvas()}) == ("On paper", None)


def test_hac_alone_cannot_say_whether_it_was_handed_in():
    assert items.handed_in_text(ONLINE, {"hac": _hac(28.0)}) == ("Unknown", None)


def test_an_item_no_source_describes_is_unknown_not_blank():
    """A blank cell reads as an answer. It is not one."""
    assert items.handed_in_text(ONLINE, {}) == ("Unknown", None)


def test_nothing_to_hand_in_and_nobody_can_say_are_different_cells():
    """The bug this split fixes: one dash stood for both, so the column could not be read.
    "On paper" is not applicable; "Unknown" is not answered. Neither is "No"."""
    nothing_to_submit, _ = items.handed_in_text(PAPER, {"canvas": _canvas()})
    cannot_say, _ = items.handed_in_text(ONLINE, {"hac": _hac(28.0)})
    assert nothing_to_submit != cannot_say
    assert "No" not in (nothing_to_submit, cannot_say)


# --- grade ------------------------------------------------------------------------------------

def test_grade_is_the_score_and_a_zero_is_flagged_as_one():
    assert items.grade_text(ONLINE, {"canvas": _canvas(state="graded", score=12.5033)}) == ("12.5/50", False)
    assert items.grade_text(ONLINE, {"canvas": _canvas(state="graded", score=0)}) == ("0/50", True)


def test_grade_carries_the_teachers_marks_and_waits_honestly():
    assert items.grade_text(ONLINE, {"canvas": _canvas(missing=1)}) == ("Missing", False)
    assert items.grade_text(ONLINE, {"canvas": _canvas(submitted_at="2026-09-15T20:11:00-04:00")}) == ("Not yet", False)
    assert items.grade_text(ONLINE, {"canvas": _canvas(excused=1)}) == ("Excused", False)
    assert items.grade_text(ONLINE, {"canvas": _canvas(published=0)}) == ("Unpublished", False)
    assert items.grade_text(ONLINE, {"canvas": _canvas()}) == ("", False)        # nothing said yet


def test_grade_falls_back_to_hac_only_when_canvas_has_nothing():
    assert items.grade_text(ONLINE, {"hac": _hac(28.0)}) == ("28/50", False)
    assert items.grade_text(ONLINE, {"hac": _hac()}) == ("Not yet", False)
    # Canvas unsubmitted, HAC already scored it (paper work graded in HAC): HAC's number shows.
    assert items.grade_text(PAPER, {"canvas": _canvas(), "hac": _hac(9.0)}) == ("9/10", False)
    # Canvas has a score too: Canvas wins, and any disagreement is Reconcile's to raise.
    assert items.grade_text(ONLINE, {"canvas": _canvas(state="graded", score=40), "hac": _hac(28.0)}) == ("40/50", False)


# --- the page ---------------------------------------------------------------------------------

def test_the_kid_table_has_the_three_columns_and_the_old_composite_words_are_gone(tmp_path):
    """Three columns: Due, Assignment, Where it stands (docs/superpowers/specs/
    2026-09-23-questions-not-cases-design.md, 6.1). Where it stands is one phrase from the
    item's verdict; for work not yet due it is simply when it is due."""
    from web_fixtures import app_for, seed
    seed(tmp_path).close()
    c = app_for(tmp_path)
    html = c.get("/kids/Alex", headers={"host": "127.0.0.1"}).text
    table = html[html.index('id="items"'):]
    # A sortable heading carries an arrow inside its link when it is the column doing the
    # sorting (#11 item 9), so the label is not always the whole of the element's text.
    for header in ("Due", "Assignment", "Where it stands"):
        assert re.search(rf">{header}(?:<| <span class=\"arrow\">)", table), header
    for gone in (">Status<", ">Handed in<", ">Grade<", ">Sources<"):
        assert gone not in table, gone
    # The composite words the old Status column used for settled or waiting work are the
    # verdict's words now.
    for composite in ("Submitted, ungraded", "Late, ungraded", "HAC, no grade", "Paper, check"):
        assert composite not in table, composite
    assert "Due today" in table and 'class="rel">today</small>' in table

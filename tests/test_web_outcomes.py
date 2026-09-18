"""`outcomes.classify`: one word per assignment, defined once, used by every count.

The scenarios here are the rows of docs/outcomes.md. The numbers in the last test are the
real ones that prompted this: a Canvas dashboard reporting 4 missing when 11 were not done.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web import outcomes as oc

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 17, 16, 0, tzinfo=TZ)
PAST = "2026-09-10T23:59:00-04:00"
FUTURE = "2026-09-24T23:59:00-04:00"


def canvas(**kw):
    base = dict(state="unsubmitted", score=None, grade=None, submitted_at=None, late=0, missing=0, excused=0, published=1)
    base.update(kw)
    return base


def hac(score=None):
    return dict(state="graded" if score is not None else "ungraded", score=score, grade=None, submitted_at=None,
                late=None, missing=None, excused=None, published=None)


def item(kind="online", due=PAST, points=10):
    return {"kind": kind, "due": due, "points": points}


# --- the marks and the zero settle it first ---------------------------------------------------

def test_a_missing_flag_is_not_done():
    assert oc.classify(item(), {"canvas": canvas(missing=1)}, NOW) == oc.NOT_DONE


def test_a_zero_is_not_done_whether_or_not_something_was_handed_in():
    assert oc.classify(item(), {"canvas": canvas(state="graded", score=0)}, NOW) == oc.NOT_DONE
    assert oc.classify(item(), {"canvas": canvas(state="graded", score=0, submitted_at=PAST)}, NOW) == oc.NOT_DONE
    assert oc.classify(item(), {"hac": hac(0)}, NOW) == oc.NOT_DONE                      # HAC's zero counts too
    assert oc.classify(item(points=0), {"canvas": canvas(state="graded", score=0)}, NOW) != oc.NOT_DONE  # 0 of 0 is nothing


def test_excused_and_unpublished_are_counted_nowhere():
    assert oc.classify(item(), {"canvas": canvas(excused=1, missing=1)}, NOW) == oc.EXCUSED
    assert oc.classify(item(), {"canvas": canvas(published=0)}, NOW) == oc.UNPUBLISHED
    assert oc.EXCUSED not in oc.PAST_DUE and oc.UNPUBLISHED not in oc.PAST_DUE


# --- a submission settles timing ------------------------------------------------------------

def test_a_submission_is_on_time_or_late_by_canvas_s_own_word():
    assert oc.classify(item(), {"canvas": canvas(submitted_at="2026-09-09T20:00:00-04:00")}, NOW) == oc.ON_TIME
    assert oc.classify(item(), {"canvas": canvas(submitted_at="2026-09-12T20:00:00-04:00", late=1)}, NOW) == oc.LATE
    # graded afterwards changes nothing about when it was handed in
    assert oc.classify(item(), {"canvas": canvas(submitted_at=PAST, late=1, state="graded", score=8)}, NOW) == oc.LATE


# --- a grade with no submission means done by hand ---------------------------------------------

def test_graded_without_a_submission_is_done_on_paper_whatever_the_kind():
    assert oc.classify(item("paper"), {"canvas": canvas(state="graded", score=9)}, NOW) == oc.DONE_OFFLINE
    assert oc.classify(item("online"), {"canvas": canvas(state="graded", score=9)}, NOW) == oc.DONE_OFFLINE
    assert oc.classify(item("paper"), {"canvas": canvas(), "hac": hac(9)}, NOW) == oc.DONE_OFFLINE   # HAC has the grade
    assert oc.classify(item("paper"), {"hac": hac(9)}, NOW) == oc.DONE_OFFLINE                      # HAC alone


# --- nothing handed in, nothing graded: it depends on the kind and the date ----------------------

def test_past_due_online_with_nothing_is_not_done_even_without_the_flag():
    """The unflagged case: the Biology teacher does not run the auto-missing policy."""
    assert oc.classify(item("online"), {"canvas": canvas()}, NOW) == oc.NOT_DONE


def test_past_due_paper_with_nothing_is_unknown_not_not_done():
    assert oc.classify(item("paper"), {"canvas": canvas()}, NOW) == oc.UNKNOWN
    assert oc.classify(item("in class"), {"canvas": canvas()}, NOW) == oc.UNKNOWN
    assert oc.classify(item("paper"), {"hac": hac()}, NOW) == oc.UNKNOWN


def test_not_due_yet():
    assert oc.classify(item("online", due=FUTURE), {"canvas": canvas()}, NOW) == oc.NOT_DUE
    assert oc.classify(item("paper", due=None), {"canvas": canvas()}, NOW) == oc.NOT_DUE
    assert oc.classify(item("paper", due=FUTURE), {"hac": hac()}, NOW) == oc.NOT_DUE


def test_nothing_known():
    assert oc.classify(item(), {}, NOW) == oc.NO_DATA


# --- the tally --------------------------------------------------------------------------------

def test_the_tally_counts_only_settled_outcomes_and_rates_only_timed_ones():
    t = oc.tally([oc.ON_TIME] * 55 + [oc.LATE] * 9 + [oc.NOT_DONE] * 11 + [oc.DONE_OFFLINE] * 11 + [oc.UNKNOWN] * 8
                 + [oc.NOT_DUE] * 13 + [oc.EXCUSED] * 2 + [oc.NO_DATA])
    assert (t.on_time, t.late, t.not_done, t.done_offline, t.unknown) == (55, 9, 11, 11, 8)
    assert t.total == 94                                    # the 94 past-due, not-excused assignments
    assert round(t.on_time_rate, 3) == round(55 / 75, 3)    # on time over on time + late + not done
    assert oc.tally([]).on_time_rate is None


# --- the pages ------------------------------------------------------------------------------

def test_the_kid_card_shows_the_record_and_the_kid_page_filters_by_outcome(tmp_path):
    from web_fixtures import app_for, seed
    seed(tmp_path).close()
    c = app_for(tmp_path)
    dash = c.get("/", headers={"host": "127.0.0.1"}).text
    assert 'class="record"' in dash and "not done</a>" in dash and "due so far" in dash
    page = c.get("/kids/Alex?outcome=not_done", headers={"host": "127.0.0.1"}).text
    assert 'name="outcome"' in page and '<option value="not_done" selected>not done</option>' in page
    assert "Quiz 1" in page                                  # missing in Canvas: not done
    assert "Essay draft" not in page                         # submitted: not this outcome
    # an outcome filter shows all matching rows, including those past the credit window
    everything = c.get("/kids/Alex?outcome=on_time", headers={"host": "127.0.0.1"}).text
    assert "Essay draft" in everything


def test_sorting_a_column_keeps_the_outcome_filter(tmp_path):
    from web_fixtures import app_for, seed
    seed(tmp_path).close()
    page = app_for(tmp_path).get("/kids/Alex?outcome=not_done", headers={"host": "127.0.0.1"}).text
    assert "outcome=not_done&amp;sort=name" in page or "outcome=not_done&sort=name" in page

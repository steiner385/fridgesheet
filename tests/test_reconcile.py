"""The rules that turn two gradebooks and a parent's flags into 'what is actionable', and
the verdict each item then gets (web/verdicts.py). Seeded rows, no ingest, so each case is explicit."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from fridgesheet import late_rules
from fridgesheet.web import db, reconcile
from fridgesheet.web.stores import flags as flagstore

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)
RULES = late_rules.LateRules(late_rules.Rule(late_days=7, credit="50%"), [], [])


def _seed(conn):
    with conn:
        conn.executemany("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (?, ?, '{}', 1)", [(1, "2026-09-10T06:00:00"), (2, "2026-09-15T06:00:00")])
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        # peer_course_id is set by UPDATE after both rows exist -- inserting it inline forward-references
        # a row that doesn't exist yet, which sqlite3's immediate FK enforcement rejects (see ingest.py).
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Honors Biology S1', 'Honors Biology')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (2, 1, 'hac', 'Honors Biology - 3', 'Honors Biology')")
        conn.execute("UPDATE courses SET peer_course_id = 2 WHERE id = 1")
        conn.execute("UPDATE courses SET peer_course_id = 1 WHERE id = 2")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (3, 1, 'canvas', 'Latin I S1', 'Latin I')")


def _item(conn, id, key, name, due_days, course_id=1, kind="online", last_seen=2):
    due = (NOW + timedelta(days=due_days)).isoformat()
    with conn:
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, kind, due, first_seen, last_seen) VALUES (?, 1, ?, ?, ?, ?, ?, 1, ?)",
                     (id, course_id, key, name, kind, due, last_seen))


def _obs(conn, item_id, source, refresh_id=2, **v):
    cols = {"state": None, "score": None, "grade": None, "submitted_at": None, "late": None, "missing": None,
            "excused": None, "published": None}
    cols.update(v)
    with conn:
        conn.execute("INSERT INTO item_observations(refresh_id, item_id, source, state, score, grade, submitted_at, late, missing, excused, published) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (refresh_id, item_id, source, *cols.values()))


@pytest.fixture
def conn(tmp_path):
    c = db.open_db(tmp_path)
    _seed(c)
    return c


def _verdicts(conn) -> dict[str, tuple[str, str]]:
    """item key -> (verdict state, verdict kind), for the live items of student 1
    (web/verdicts.py; these scenarios were once reconcile "cases")."""
    from fridgesheet.web.stores import items
    student = conn.execute("SELECT * FROM students WHERE id = 1").fetchone()
    return {v.key: (v.verdict.state, v.verdict.kind) for v in items.list_items(conn, student, now=NOW, rules=RULES, show="all")}


def test_missing_in_canvas_is_actionable_until_flagged_or_out_of_credit(conn):
    _item(conn, 1, "canvas:1", "WS 1", -2)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:1"]
    flagstore.set_flag(conn, 1, "done", now=NOW.isoformat())
    assert reconcile.actionable_items(conn, 1, rules=RULES, now=NOW) == []
    flagstore.clear(conn, 1, now=NOW.isoformat())
    _item(conn, 2, "canvas:2", "Old WS", -20)                       # past the 7-day credit window
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:1"]
    assert _verdicts(conn)["canvas:2"] == ("status", "past_credit")


def test_an_item_the_sources_no_longer_report_gets_no_verdict(conn):
    """`items` keeps every row it has ever seen; a case must be about something a source
    still reports. Only items last seen in this student's most recent refresh count."""
    _item(conn, 1, "canvas:1", "Gone from the gradebook", -3, last_seen=1)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted", missing=1)
    _item(conn, 2, "canvas:2", "Still listed", -3)                  # last_seen = 2, the latest
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:2"]
    assert set(_verdicts(conn)) == {"canvas:2"}


def test_an_item_due_before_the_school_year_gets_no_verdict(conn):
    """Due dates before August 1st are last year's course-copy artifacts, which is the floor
    the sheet uses too (open_items.school_year_start)."""
    _item(conn, 1, "canvas:1", "Last year's worksheet", -60)        # 2026-07-17, before Aug 1
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    assert reconcile.actionable_items(conn, 1, rules=RULES, now=NOW) == []
    assert _verdicts(conn) == {}


def test_an_undated_item_survives_the_year_floor(conn):
    """HAC lists real work with no due date; it must not be mistaken for last year's."""
    with conn:
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, kind, due, first_seen, last_seen) VALUES (1, 1, 2, 'hac:Honors Biology:reading log', 'Reading log', '', NULL, 1, 2)")
    _obs(conn, 1, "hac", state="ungraded")
    assert [r["key"] for r in reconcile.live_items(conn, 1, NOW)] == ["hac:Honors Biology:reading log"]


def test_an_unpublished_canvas_item_is_not_open(conn):
    """A teacher who unpublishes an assignment has taken it off the kid's plate; the sheet
    already drops it (open_items._status) and the reconcile rules must agree."""
    _item(conn, 1, "canvas:1", "Draft nobody can see", -2)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1, published=0)
    _item(conn, 2, "canvas:2", "WS 2", -2)
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1, published=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:2"]
    assert _verdicts(conn)["canvas:1"] == ("status", "unpublished")


def test_sources_disagree_both_directions(conn):
    _item(conn, 1, "canvas:1", "Quiz 1", -3)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    _obs(conn, 1, "hac", state="graded", score=28.0)
    _item(conn, 2, "canvas:2", "Lab 2", -3)
    _obs(conn, 2, "canvas", state="graded", score=9.0)
    _obs(conn, 2, "hac", state="ungraded")
    v = _verdicts(conn)
    assert v["canvas:1"] == ("decided", "graded_in_hac")      # HAC's grade beats the automatic missing
    assert v["canvas:2"] == ("waiting", "hac_lag")            # graded in Canvas today; HAC will catch up


def test_only_one_source_knows(conn):
    _item(conn, 1, "hac:Honors Biology:reading log", "reading log", -3, course_id=2, kind="")
    _obs(conn, 1, "hac", state="ungraded")
    _item(conn, 2, "canvas:2", "Vocab 3", -3)                           # course 1 has a HAC peer, but no HAC row for this
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    _item(conn, 3, "canvas:3", "Latin WS", -3, course_id=3)              # Latin has no HAC peer: not a case
    _obs(conn, 3, "canvas", state="unsubmitted", missing=1)
    v = _verdicts(conn)
    assert v["hac:Honors Biology:reading log"] == ("waiting", "awaiting_grade")   # HAC-only, no grade, 3 days on
    assert v["canvas:2"] == ("status", "not_done")            # missing in Canvas; HAC's silence is not a question
    assert v["canvas:3"] == ("status", "not_done")


def test_submitted_and_paper_work_wait_for_a_grade(conn):
    _item(conn, 1, "canvas:1", "Essay", -3)
    _obs(conn, 1, "canvas", state="submitted", submitted_at="2026-09-12T20:00:00-04:00")
    _item(conn, 2, "canvas:2", "Worksheet (paper)", -3, kind="paper")
    _obs(conn, 2, "canvas", state="unsubmitted")
    _item(conn, 3, "canvas:3", "Future paper", 3, kind="paper")
    _obs(conn, 3, "canvas", state="unsubmitted")
    v = _verdicts(conn)
    assert v["canvas:1"] == ("waiting", "teacher_grading") and v["canvas:2"] == ("waiting", "awaiting_grade")
    assert v["canvas:3"] == ("status", "not_due_yet")


def test_stale_flags(conn):
    _item(conn, 1, "canvas:1", "WS 1", -3)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted", missing=1)
    flagstore.set_flag(conn, 1, "done", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "canvas", refresh_id=2, state="graded", score=0.0)      # a zero posted after the flag
    _item(conn, 2, "canvas:2", "Lab", -3)
    _obs(conn, 2, "canvas", refresh_id=1, state="submitted")
    flagstore.set_flag(conn, 2, "follow_up", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 2, "canvas", refresh_id=2, state="graded", score=8.0)      # graded after the flag
    _item(conn, 3, "canvas:3", "Fine", -3)
    _obs(conn, 3, "canvas", refresh_id=1, state="unsubmitted", missing=1)
    flagstore.set_flag(conn, 3, "done", now=NOW.isoformat())                # flag newer than any observation: not stale
    v = _verdicts(conn)
    assert v["canvas:1"] == ("question", "stale_answer")                # done, then a zero
    assert v["canvas:2"] == ("question", "followed_up_then_graded")     # follow up, then graded
    assert v["canvas:3"] == ("status", "answered")


def test_a_stale_answer_comes_before_any_other_verdict(conn):
    _item(conn, 1, "canvas:1", "WS 1", -3)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted")
    flagstore.set_flag(conn, 1, "done", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "canvas", refresh_id=2, state="unsubmitted", missing=1)     # missing shows up after the flag
    _obs(conn, 1, "hac", refresh_id=2, state="graded", score=15.0)           # and HAC disagrees with a real score
    assert _verdicts(conn)["canvas:1"] == ("question", "stale_answer")     # the family's answer is what changed


@pytest.mark.parametrize("kind", ["paper", "in class"])
def test_paper_work_hac_graded_is_done_not_a_question(conn, kind):
    """Issue #33: work with nothing to submit online, past due, no Canvas grade -- but HAC
    graded it. "No grade: ask" beside an 18/25 is the app contradicting its own evidence."""
    _item(conn, 1, "canvas:1", "MakeMusic #3", -3, kind=kind)
    _obs(conn, 1, "canvas", state="unsubmitted")
    _obs(conn, 1, "hac", state="graded", score=18.0)
    assert _verdicts(conn)["canvas:1"] == ("status", "done_offline")


def test_paper_work_hac_lists_ungraded_waits_for_a_grade(conn):
    _item(conn, 1, "canvas:1", "MakeMusic #3", -3, kind="in class")
    _obs(conn, 1, "canvas", state="unsubmitted")
    _obs(conn, 1, "hac", state="ungraded", score=None)
    assert _verdicts(conn)["canvas:1"] == ("waiting", "awaiting_grade")


def test_in_class_work_hac_graded_is_not_actionable(conn):
    _item(conn, 1, "canvas:1", "MakeMusic #3", -3, kind="in class")
    _obs(conn, 1, "canvas", state="unsubmitted")
    _obs(conn, 1, "hac", state="graded", score=18.0)
    assert reconcile.actionable_items(conn, 1, rules=RULES, now=NOW) == []


def test_a_hac_grade_posted_after_ask_teacher_makes_the_flag_stale(conn):
    """Issue #36: for in-class and paper work the teacher fixes HAC, not Canvas. Canvas has
    nothing newer than the flag here; HAC does."""
    _item(conn, 1, "canvas:1", "MakeMusic #3", -3, kind="in class")
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted")
    _obs(conn, 1, "hac", refresh_id=1, state="ungraded")
    flagstore.set_flag(conn, 1, "ask_teacher", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "hac", refresh_id=2, state="graded", score=18.0)
    assert _verdicts(conn)["canvas:1"] == ("question", "asked_then_graded")


def test_a_hac_zero_posted_after_done_makes_the_flag_stale(conn):
    _item(conn, 1, "canvas:1", "Worksheet", -3, kind="paper")
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted")
    _obs(conn, 1, "hac", refresh_id=1, state="ungraded")
    flagstore.set_flag(conn, 1, "done", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "hac", refresh_id=2, state="graded", score=0.0)
    assert _verdicts(conn)["canvas:1"] == ("question", "stale_answer")


def test_a_hac_observation_older_than_the_flag_does_not_make_it_stale(conn):
    _item(conn, 1, "canvas:1", "Worksheet", -3, kind="paper")
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted")
    _obs(conn, 1, "hac", refresh_id=1, state="graded", score=18.0)
    flagstore.set_flag(conn, 1, "ask_teacher", now="2026-09-12T08:00:00-04:00")
    assert _verdicts(conn)["canvas:1"] == ("status", "asked")


def test_stale_flag_reasons_name_the_flag_in_words(conn):
    _item(conn, 1, "canvas:1", "Lab", -3)
    _obs(conn, 1, "canvas", refresh_id=1, state="submitted")
    flagstore.set_flag(conn, 1, "ask_teacher", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "canvas", refresh_id=2, state="graded", score=8.0)
    from fridgesheet.web.stores import items
    student = conn.execute("SELECT * FROM students WHERE id = 1").fetchone()
    (v,) = [v for v in items.list_items(conn, student, now=NOW, rules=RULES, show="all") if v.key == "canvas:1"]
    assert v.verdict.facts["flag"] == "ask the teacher"


def test_a_handled_item_whose_flag_went_stale_is_a_question_again(conn):
    """A `done` flag the school now contradicts is exactly the open question the Questions page
    is for; handled work is otherwise answered."""
    _item(conn, 1, "canvas:1", "WS 1", -3)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted")
    flagstore.set_flag(conn, 1, "done", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "canvas", refresh_id=2, state="unsubmitted", missing=1)
    _item(conn, 2, "canvas:2", "WS 2", -3)
    _obs(conn, 2, "canvas", refresh_id=2, state="unsubmitted", missing=1)
    flagstore.set_flag(conn, 2, "done", now=NOW.isoformat())            # handled, not stale
    v = _verdicts(conn)
    assert v["canvas:1"] == ("question", "stale_answer") and v["canvas:2"] == ("status", "answered")

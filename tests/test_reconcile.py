"""The rules that turn two gradebooks and a parent's flags into 'what is actionable' and
'what needs a human to decide'. Seeded rows, no ingest, so each case is explicit."""
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


def _kinds(conn):
    return sorted((c.kind, c.key) for c in reconcile.cases(conn, 1, rules=RULES, now=NOW))


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
    assert ("past_credit", "canvas:2") in _kinds(conn)


def test_an_item_the_sources_no_longer_report_raises_no_case(conn):
    """`items` keeps every row it has ever seen; a case must be about something a source
    still reports. Only items last seen in this student's most recent refresh count."""
    _item(conn, 1, "canvas:1", "Gone from the gradebook", -3, last_seen=1)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted", missing=1)
    _item(conn, 2, "canvas:2", "Still listed", -3)                  # last_seen = 2, the latest
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:2"]
    assert [key for _, key in _kinds(conn)] == ["canvas:2"]


def test_an_item_due_before_the_school_year_raises_no_case(conn):
    """Due dates before August 1st are last year's course-copy artifacts, which is the floor
    the sheet uses too (open_items.school_year_start)."""
    _item(conn, 1, "canvas:1", "Last year's worksheet", -60)        # 2026-07-17, before Aug 1
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    assert reconcile.actionable_items(conn, 1, rules=RULES, now=NOW) == []
    assert _kinds(conn) == []


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
    assert not any(key == "canvas:1" for _, key in _kinds(conn))


def test_sources_disagree_both_directions(conn):
    _item(conn, 1, "canvas:1", "Quiz 1", -3)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    _obs(conn, 1, "hac", state="graded", score=28.0)
    _item(conn, 2, "canvas:2", "Lab 2", -3)
    _obs(conn, 2, "canvas", state="graded", score=9.0)
    _obs(conn, 2, "hac", state="ungraded")
    kinds = _kinds(conn)
    assert ("disagree", "canvas:1") in kinds and ("disagree", "canvas:2") in kinds
    reasons = {c.key: c.reason for c in reconcile.cases(conn, 1, rules=RULES, now=NOW)}
    assert "Canvas says MISSING" in reasons["canvas:1"] and "HAC" in reasons["canvas:1"]


def test_only_one_source_knows(conn):
    _item(conn, 1, "hac:Honors Biology:reading log", "reading log", -3, course_id=2, kind="")
    _obs(conn, 1, "hac", state="ungraded")
    _item(conn, 2, "canvas:2", "Vocab 3", -3)                           # course 1 has a HAC peer, but no HAC row for this
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    _item(conn, 3, "canvas:3", "Latin WS", -3, course_id=3)              # Latin has no HAC peer: not a case
    _obs(conn, 3, "canvas", state="unsubmitted", missing=1)
    kinds = _kinds(conn)
    assert ("one_source", "hac:Honors Biology:reading log") in kinds and ("one_source", "canvas:2") in kinds
    assert ("one_source", "canvas:3") not in kinds


def test_submitted_ungraded_and_paper_no_grade(conn):
    _item(conn, 1, "canvas:1", "Essay", -3)
    _obs(conn, 1, "canvas", state="submitted", submitted_at="2026-09-12T20:00:00-04:00")
    _item(conn, 2, "canvas:2", "Worksheet (paper)", -3, kind="paper")
    _obs(conn, 2, "canvas", state="unsubmitted")
    _item(conn, 3, "canvas:3", "Future paper", 3, kind="paper")
    _obs(conn, 3, "canvas", state="unsubmitted")
    kinds = _kinds(conn)
    assert ("submitted_ungraded", "canvas:1") in kinds and ("paper_no_grade", "canvas:2") in kinds
    assert not any(k == "canvas:3" for _, k in kinds)


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
    kinds = _kinds(conn)
    assert ("stale_flag", "canvas:1") in kinds and ("stale_flag", "canvas:2") in kinds
    assert ("stale_flag", "canvas:3") not in kinds


def test_one_item_can_carry_both_a_stale_flag_and_a_disagreement(conn):
    _item(conn, 1, "canvas:1", "WS 1", -3)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted")
    flagstore.set_flag(conn, 1, "done", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "canvas", refresh_id=2, state="unsubmitted", missing=1)     # missing shows up after the flag
    _obs(conn, 1, "hac", refresh_id=2, state="graded", score=15.0)           # and HAC disagrees with a real score
    kinds = {c.kind for c in reconcile.cases(conn, 1, rules=RULES, now=NOW) if c.key == "canvas:1"}
    assert kinds == {"stale_flag", "disagree"}


def test_cases_are_sorted_and_carry_context(conn):
    _item(conn, 1, "canvas:1", "B item", -1)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    _obs(conn, 1, "hac", state="graded", score=5.0)
    _item(conn, 2, "canvas:2", "A item", -5)
    _obs(conn, 2, "canvas", state="submitted", submitted_at="x")
    cs = reconcile.cases(conn, 1, rules=RULES, now=NOW)
    assert [c.key for c in cs] == ["canvas:2", "canvas:1"]
    assert cs[1].course == "Honors Biology" and cs[1].name == "B item" and cs[1].due is not None

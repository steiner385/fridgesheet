"""The Changes feed: what the change log says happened between two moments."""
from __future__ import annotations

from datetime import datetime, timedelta

from lakota_grades.web import db, ingest
from lakota_grades.web.stores import changes, flags, students
from tests.web_fixtures import NOW, REFRESH_TIMES, TZ, history, seed, snapshot


def _at(i: int) -> datetime:
    return datetime.fromisoformat(REFRESH_TIMES[i])


def _kinds(events):
    return sorted({e.kind for e in events})


def _find(events, kind, name=None):
    return [e for e in events if e.kind == kind and (name is None or e.item_name == name)]


def test_empty_database_has_no_events(tmp_path):
    conn = db.open_db(tmp_path)
    assert changes.since(conn, since=NOW - timedelta(days=30)) == []
    conn.close()


def test_the_whole_history_reports_every_kind(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    assert _kinds(events) == ["cleared", "course_grade", "grade_posted", "new_item", "now_missing"]
    # Day 1 is the database's first refresh, so its nine items are not "new" -- there was no
    # before. Vocabulary, which joins on day 2, is the one genuine arrival.
    assert [e.item_name for e in _find(events, "new_item")] == ["Vocabulary"]
    conn.close()


def test_the_first_refresh_reports_state_but_not_newness(tmp_path):
    """A one-refresh install -- the state every install starts in. There is no "before", so
    nothing is `new_item`; but the observations themselves carry a state, and Trends counts
    those, so the feed must too or the two pages contradict each other."""
    conn = seed(tmp_path)
    events = changes.since(conn, since=NOW - timedelta(days=30))
    assert _find(events, "new_item") == []
    (quiz,) = _find(events, "grade_posted", "Quiz 1")          # HAC lists it already scored
    assert quiz.source == "hac" and quiz.detail == "28/30"
    (cell,) = _find(events, "now_missing", "Cell diagram")     # first seen already MISSING
    assert cell.source == "canvas" and "missing" in cell.detail.lower()
    (essay,) = _find(events, "cleared", "Essay draft")         # first seen already handed in
    assert "submitted" in essay.detail.lower()
    conn.close()


def test_grade_changed_carries_both_scores(tmp_path):
    """`grade_changed` is the only producer of the "x → y" detail, and needs a score that
    actually moves between two refreshes -- which the standard history never does."""
    conn = db.open_db(tmp_path)
    first = snapshot()
    for a in first["students"]["Sam"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Safety quiz":
            a["state"], a["score"], a["grade"] = "graded", 5.0, "5"
    first["fetched_at"] = REFRESH_TIMES[0]
    ingest.record(conn, first, tz=TZ, now=_at(0))
    later = snapshot()                                          # Safety quiz regraded to 0
    later["fetched_at"] = REFRESH_TIMES[2]
    ingest.record(conn, later, tz=TZ, now=_at(2))
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    (changed,) = _find(events, "grade_changed", "Safety quiz")
    assert changed.detail == "5/10 → 0/10" and changed.at == _at(2) and changed.source == "canvas"
    conn.close()


def test_the_last_day_reports_only_that_day(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(2) - timedelta(minutes=1))
    names = {(e.kind, e.item_name) for e in events}
    assert ("new_item", "Vocabulary") not in names                 # that was yesterday
    assert ("now_missing", "Quiz 1") in names                      # Canvas turned on missing today
    assert ("grade_posted", "Safety quiz") in names                # 0 is a grade
    assert ("cleared", "Essay draft") in names                     # submitted: no longer open
    conn.close()


def test_grade_posted_and_changed_carry_readable_detail(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    (posted,) = _find(events, "grade_posted", "Quiz 1")
    assert posted.source == "hac" and posted.detail == "28/30" and posted.course_short == "Honors English 9"
    assert posted.student_key == "Alex" and posted.at == _at(1)
    (avg,) = [e for e in _find(events, "course_grade") if e.course_short == "Honors English 9" and e.at == _at(1)]
    assert avg.detail == "HAC average 85 → 88" and avg.item_id is None
    conn.close()


def test_new_item_names_its_course_and_time(tmp_path):
    conn = history(tmp_path)
    (vocab,) = _find(changes.since(conn, since=_at(0)), "new_item", "Vocabulary")
    assert vocab.at == _at(1) and vocab.course_short == "Honors English 9" and vocab.student_key == "Alex"
    conn.close()


def test_now_missing_and_cleared_are_opposites(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    (hw,) = _find(events, "now_missing", "Homework 4")
    assert hw.at == _at(1) and hw.source == "canvas" and "missing" in hw.detail.lower()
    (essay,) = _find(events, "cleared", "Essay draft")
    assert essay.at == _at(2) and "submitted" in essay.detail.lower()
    conn.close()


def test_flags_appear_and_disappear(tmp_path):
    conn = history(tmp_path)
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    flags.set_flag(conn, quiz, "follow_up", now="2026-09-15T15:00:00-04:00", text="emailed Mr Hoch")
    events = changes.since(conn, since=_at(2))
    (f,) = _find(events, "flag_set", "Quiz 1")
    assert f.flag == "follow_up" and "emailed Mr Hoch" in f.detail and f.at == datetime.fromisoformat("2026-09-15T15:00:00-04:00")
    flags.clear(conn, quiz, now="2026-09-15T16:00:00-04:00")
    events = changes.since(conn, since=_at(2))
    assert _find(events, "flag_cleared", "Quiz 1")
    conn.close()


def test_filters_by_student_and_kind(tmp_path):
    conn = history(tmp_path)
    sam = students.by_key(conn, "Sam")["id"]
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1), student_id=sam)
    assert {e.student_key for e in events} == {"Sam"}
    only_new = changes.since(conn, since=_at(0) - timedelta(minutes=1), kinds=("new_item",))
    assert _kinds(only_new) == ["new_item"]
    assert changes.since(conn, since=_at(0) - timedelta(minutes=1), kinds=("nonsense",)) == []
    conn.close()


def test_until_bounds_the_window(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1), until=_at(1))
    assert all(e.at <= _at(1) for e in events) and events
    conn.close()


def test_events_are_newest_first(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    assert [e.at for e in events] == sorted((e.at for e in events), reverse=True)
    conn.close()


def test_same_instant_events_tie_break_forwards(tmp_path):
    """Newest first, but *within* one timestamp the plan's order is ascending student key then
    item name then kind -- not the reverse-alphabetical order one `reverse=True` sort gives."""
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    by_instant: dict = {}
    for e in events:
        by_instant.setdefault(e.at, []).append(e)
    ties = [group for group in by_instant.values() if len(group) > 1]
    assert ties, "the fixture should share at least one timestamp between events"
    for group in ties:
        keys = [(e.student_key, e.item_name or "", e.kind) for e in group]
        assert keys == sorted(keys)
    conn.close()


def test_the_cap_keeps_the_newest_and_counts_the_rest(tmp_path):
    conn = history(tmp_path)
    whole = changes.since(conn, since=_at(0) - timedelta(minutes=1), limit=None)
    assert whole.total == len(whole) and whole.dropped == 0
    capped = changes.since(conn, since=_at(0) - timedelta(minutes=1), limit=3)
    assert len(capped) == 3 and capped.total == len(whole)
    assert capped.dropped == len(whole) - 3
    assert list(capped) == list(whole)[:3]                      # the newest three, in order
    conn.close()


def test_window_start_reads_the_keys(tmp_path):
    assert changes.window_start("1d", NOW) == NOW - timedelta(days=1)
    assert changes.window_start("7d", NOW) == NOW - timedelta(days=7)
    assert changes.window_start("nonsense", NOW) == NOW - timedelta(days=1)     # the default window

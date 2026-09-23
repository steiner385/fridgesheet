"""Samples from the observation history (spec 4.1, 4.2). Built directly on the schema so each
case is one item with a hand-written history."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import pace as store


def _refresh(conn, at):
    return conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES (?, '{}', 1)", (at,)).lastrowid


def _course(conn, sid, source, name, teacher="Michael Hoch", peer=None):
    return conn.execute("INSERT INTO courses(student_id, source, name, short_name, teacher, peer_course_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (sid, source, name, name[:4], teacher, peer)).lastrowid


def _item(conn, sid, cid, name, *, kind="paper", due="2026-09-10T23:59:00-04:00", first_seen):
    return conn.execute("INSERT INTO items(student_id, course_id, key, name, kind, points, due, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, 10, ?, ?, ?)",
                        (sid, cid, f"canvas:{name}", name, kind, due, first_seen, first_seen)).lastrowid


def _obs(conn, rid, iid, source, score=None, submitted_at=None):
    conn.execute("INSERT INTO item_observations(refresh_id, item_id, source, state, score, submitted_at, late, missing, excused, published) "
                 "VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 1)", (rid, iid, source, "graded" if score is not None else "unsubmitted", score, submitted_at))


def _home(tmp_path):
    conn = db.open_db(tmp_path)
    sid = conn.execute("INSERT INTO students(key, name) VALUES ('Alex', 'Alex')").lastrowid
    r1, r2, r3 = (_refresh(conn, at) for at in ("2026-09-08T06:00:00-04:00", "2026-09-15T06:00:00-04:00", "2026-09-22T06:00:00-04:00"))
    cid = _course(conn, sid, "canvas", "Honors English 9")
    return conn, sid, cid, (r1, r2, r3)


def test_grade_lag_is_days_from_due_to_the_first_scored_refresh(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Reading guide", first_seen=r1)            # due 9/10
    _obs(conn, r1, iid, "canvas")                                           # ungraded when first seen
    _obs(conn, r3, iid, "canvas", score=8.0)                                # graded, seen 9/22
    pace = store.load(conn)
    assert pace.grade[(cid, "offline")] == [12]


def test_online_work_anchors_on_its_submission(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Quiz", kind="online", first_seen=r1)
    _obs(conn, r1, iid, "canvas")
    _obs(conn, r2, iid, "canvas", score=8.0, submitted_at="2026-09-13T20:00:00-04:00")    # seen 9/15
    assert store.load(conn).grade[(cid, "online")] == [2]


def test_an_item_first_seen_already_graded_is_not_a_sample(tmp_path):
    """Review Focus 2."""
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Old quiz", first_seen=r2)
    _obs(conn, r2, iid, "canvas", score=8.0)
    assert (cid, "offline") not in store.load(conn).grade


def test_zeros_and_ungraded_items_are_not_samples(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    zero = _item(conn, sid, cid, "Missing one", first_seen=r1)
    _obs(conn, r1, zero, "canvas")
    _obs(conn, r2, zero, "canvas", score=0.0)
    open_ = _item(conn, sid, cid, "Still open", first_seen=r1)
    _obs(conn, r1, open_, "canvas")
    assert store.load(conn).grade == {}


def test_an_item_with_no_due_date_and_no_submission_is_not_a_sample(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Undated", due=None, first_seen=r1)
    _obs(conn, r1, iid, "canvas")
    _obs(conn, r2, iid, "canvas", score=8.0)
    assert store.load(conn).grade == {}


def test_a_grade_seen_before_the_due_date_is_a_zero_day_lag(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Early", due="2026-09-30T23:59:00-04:00", first_seen=r1)
    _obs(conn, r1, iid, "canvas")
    _obs(conn, r2, iid, "canvas", score=8.0)
    assert store.load(conn).grade[(cid, "offline")] == [0]


def test_hac_lag_is_days_between_the_two_first_scored_refreshes(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    hac = _course(conn, sid, "hac", "Honors English 9 S1", peer=cid)
    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hac, cid))
    iid = _item(conn, sid, cid, "Essay", first_seen=r1)
    _obs(conn, r1, iid, "canvas"); _obs(conn, r1, iid, "hac")
    _obs(conn, r2, iid, "canvas", score=8.0)
    _obs(conn, r3, iid, "hac", score=8.0)
    pace = store.load(conn)
    assert pace.hac[(cid, "offline")] == [7]
    assert pace.classes == {cid: cid, hac: cid}                 # the twin shares the Canvas course's history


def test_teachers_are_keyed_by_class_and_normalised(tmp_path):
    conn, sid, cid, _ = _home(tmp_path)
    assert store.load(conn).teachers == {cid: "michael hoch"}


def test_a_hac_only_item_borrows_its_twins_teacher(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    hac = _course(conn, sid, "hac", "Honors English 9 S1", teacher=None, peer=cid)
    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hac, cid))
    assert store.load(conn).teachers[cid] == "michael hoch"


# --- review: one grade sample per item, censored and anchored across both sources ------------------

def _twin(conn, sid, cid):
    hac = _course(conn, sid, "hac", "Honors English 9 S1", peer=cid)
    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hac, cid))
    return hac


def test_one_grade_sample_per_item_however_many_sources_graded_it(tmp_path):
    """The count on the card says "N earlier assignments": an item graded in Canvas and then
    in HAC is one assignment, and its grade lag is when the app first saw any grade."""
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    _twin(conn, sid, cid)
    iid = _item(conn, sid, cid, "Essay", first_seen=r1)                    # due 9/10
    _obs(conn, r1, iid, "canvas"); _obs(conn, r1, iid, "hac")
    _obs(conn, r2, iid, "canvas", score=8.0)                                # seen 9/15
    _obs(conn, r3, iid, "hac", score=8.0)                                   # seen 9/22
    assert store.load(conn).grade[(cid, "offline")] == [5]


def test_a_grade_met_already_in_canvas_is_not_a_sample_when_hac_catches_up_later(tmp_path):
    """Review Focus 2 across sources: Canvas had graded it before the app existed; HAC showing
    the grade a week later is HAC lag, not the teacher's pace."""
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    _twin(conn, sid, cid)
    iid = _item(conn, sid, cid, "Old essay", due="2026-09-01T23:59:00-04:00", first_seen=r1)
    _obs(conn, r1, iid, "canvas", score=8.0); _obs(conn, r1, iid, "hac")
    _obs(conn, r3, iid, "hac", score=8.0)
    pace = store.load(conn)
    assert pace.grade == {} and pace.hac == {}


def test_a_hac_first_grade_anchors_on_the_canvas_submission_when_there_is_one(tmp_path):
    """A late hand-in graded first in HAC: the lag runs from the hand-in, not the due date."""
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    _twin(conn, sid, cid)
    iid = _item(conn, sid, cid, "Late quiz", kind="online", first_seen=r1)      # due 9/10
    _obs(conn, r1, iid, "canvas"); _obs(conn, r1, iid, "hac")
    _obs(conn, r2, iid, "canvas", submitted_at="2026-09-20T20:00:00-04:00")     # handed in late, ungraded
    _obs(conn, r3, iid, "hac", score=8.0)                                       # seen 9/22
    assert store.load(conn).grade[(cid, "online")] == [2]

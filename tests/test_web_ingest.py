# tests/test_web_ingest.py
"""Snapshot -> database. Two snapshots a day apart: the second changes one score, adds one
assignment, and repeats everything else; only the changes become observations.

Also covers the HAC item-key collision rule from the Task 1 spike: real HAC data can list the
same normalised assignment name twice in one course with different due dates -- genuinely
different assignments -- so `record` must disambiguate every colliding row with its due date
(never only the second, so the key doesn't depend on row order), while two colliding rows that
also share a due date are the same row scraped twice and collapse to one.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.matching import hac_item_key
from fridgesheet.web import db, ingest

TZ = ZoneInfo("America/New_York")
T1 = datetime(2026, 9, 14, 6, 0, tzinfo=TZ)
T2 = datetime(2026, 9, 15, 6, 0, tzinfo=TZ)


def _assignment(i, name, due="2026-09-12T23:59:00-04:00", **over):
    a = {"id": i, "name": name, "due_at": due, "unlock_at": None, "created_at": "2026-09-01T08:00:00-04:00",
         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "group_weight": None,
         "published": True, "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": True,
         "excused": False, "submitted_at": None, "seconds_late": 0}
    a.update(over)
    return a


def snapshot(fetched: datetime) -> dict:
    return {
        "fetched_at": fetched.isoformat(), "fetched_at_epoch": fetched.timestamp(),
        "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {
            "Alex": {
                "name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
                "canvas": {"courses": [{
                    "id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                    "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                    "staff": [{"name": "Michael Hoch", "email": "hoch@example.org", "roles": ["TeacherEnrollment"]}],
                    "assignments": [_assignment(77, "Quiz 1"), _assignment(78, "Essay draft")],
                }]},
                "hac": {"week_view": [], "classes": [{
                    "code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 75.67, "last_updated": "9/11/2026",
                    "assignments": [
                        {"due": "09/12/2026", "assigned": "09/10/2026", "name": "Quiz #1", "category": "Assessments",
                         "score": 28.0, "score_raw": "28.00", "points": 30.0, "percent": "93.33%"},
                        {"due": "09/11/2026", "assigned": "09/09/2026", "name": "Reading log", "category": "Assignments",
                         "score": None, "score_raw": "", "points": 5.0, "percent": ""},
                    ],
                    "categories": [],
                }]},
            },
            "Sam": {"name": "Sam Example", "canvas_id": 124, "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}},
        },
    }


def test_first_ingest_creates_everything_and_links_hac_to_canvas(tmp_path):
    conn = db.open_db(tmp_path)
    r = ingest.record(conn, snapshot(T1), tz=TZ, now=T1)
    assert (r.students, r.courses) == (2, 2)                       # one Canvas + one HAC course for Alex
    assert r.items == 3                                             # Quiz 1 (linked), Essay draft, Reading log (HAC-only)
    keys = {row["key"] for row in conn.execute("SELECT key FROM items")}
    assert keys == {"canvas:77", "canvas:78", "hac:Honors English 9:reading log"}
    latest = db.latest_observations(conn, conn.execute("SELECT id FROM students WHERE key='Alex'").fetchone()[0])
    quiz = conn.execute("SELECT id FROM items WHERE key='canvas:77'").fetchone()[0]
    assert set(latest[quiz]) == {"canvas", "hac"}                   # "Quiz #1" in HAC attached to Canvas' "Quiz 1"
    assert latest[quiz]["hac"]["score"] == 28.0 and latest[quiz]["canvas"]["missing"] == 1
    hac_course = conn.execute("SELECT * FROM courses WHERE source='hac'").fetchone()
    canvas_course = conn.execute("SELECT * FROM courses WHERE source='canvas'").fetchone()
    assert hac_course["peer_course_id"] == canvas_course["id"] and canvas_course["peer_course_id"] == hac_course["id"]
    assert canvas_course["teacher"] == "Michael Hoch" and canvas_course["short_name"] == "Honors English 9"
    assert canvas_course["teacher_email"] == "hoch@example.org"
    grades = conn.execute("SELECT * FROM grade_observations ORDER BY course_id").fetchall()
    assert [(g["current"], g["average"]) for g in grades] == [(91.2, None), (None, 75.67)]
    reading = conn.execute("SELECT * FROM items WHERE key LIKE 'hac:%'").fetchone()
    assert reading["due"] == "2026-09-11T23:59:00-04:00" and reading["kind"] == ""
    assert conn.execute("SELECT ok, sources FROM refreshes").fetchone()[0] == 1


def test_second_ingest_writes_only_changes(tmp_path):
    conn = db.open_db(tmp_path)
    ingest.record(conn, snapshot(T1), tz=TZ, now=T1)
    before = conn.execute("SELECT count(*) FROM item_observations").fetchone()[0]
    r = ingest.record(conn, snapshot(T2), tz=TZ, now=T2)          # identical content, new fetch time
    assert r.observations == 0 and r.grades == 0
    assert r.items == 0                                           # `items` counts what was created, not what was seen
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM item_observations").fetchone()[0] == before
    assert conn.execute("SELECT last_seen FROM items WHERE key='canvas:77'").fetchone()[0] == 2

    changed = snapshot(T2)
    quiz = changed["students"]["Alex"]["canvas"]["courses"][0]["assignments"][0]
    quiz.update(score=9.0, grade="9", state="graded", missing=False)
    changed["students"]["Alex"]["canvas"]["courses"][0]["assignments"].append(_assignment(79, "Vocabulary 3", due="2026-09-20T23:59:00-04:00", missing=False))
    changed["students"]["Alex"]["hac"]["classes"][0]["marking_period_avg"] = 78.1
    r = ingest.record(conn, changed, tz=TZ, now=T2)
    assert r.observations == 2 and r.grades == 1                    # quiz's canvas view changed; the new item's first observation
    assert r.items == 1                                             # only Vocabulary 3 is new
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 4
    latest = db.latest_observations(conn, 1)
    quiz_id = conn.execute("SELECT id FROM items WHERE key='canvas:77'").fetchone()[0]
    assert latest[quiz_id]["canvas"]["state"] == "graded" and latest[quiz_id]["canvas"]["score"] == 9.0
    assert conn.execute("SELECT count(*) FROM item_observations WHERE item_id=? AND source='canvas'", (quiz_id,)).fetchone()[0] == 2


def test_failed_source_is_recorded_and_carried_students_are_untouched(tmp_path):
    conn = db.open_db(tmp_path)
    snap = snapshot(T1)
    snap["sources"]["hac"] = "login_required: OneLogin did not redirect"
    snap["stale"] = {"hac": {"fetched_at": "2026-09-13T06:00:00-04:00", "fetched_at_epoch": 0, "reason": "login_required"}}
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    row = conn.execute("SELECT ok, sources FROM refreshes").fetchone()
    assert row[0] == 0 and json.loads(row[1])["hac"].startswith("login_required")
    assert r.items == 3                                             # carried-forward HAC data still ingests


def test_keys_are_stable_across_name_punctuation(tmp_path):
    assert hac_item_key("Honors English 9 S1", 'Quiz #1: "The Seventh Man"') == "hac:Honors English 9:quiz 1 the seventh man"
    assert hac_item_key("Honors English 9 - 3", "quiz  1:  the seventh man") == "hac:Honors English 9:quiz 1 the seventh man"
    assert ingest.item_key_canvas(77) == "canvas:77"


def _snap_hac_only(assignments: list[dict]) -> dict:
    """One student, one HAC-only course (no Canvas courses, so nothing can twin), one class
    with the given raw HAC assignment rows."""
    return {
        "fetched_at": T1.isoformat(), "fetched_at_epoch": T1.timestamp(),
        "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {
            "Alex": {
                "name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
                "canvas": {"courses": []},
                "hac": {"week_view": [], "classes": [{
                    "code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 75.67, "last_updated": "9/11/2026",
                    "assignments": assignments,
                    "categories": [],
                }]},
            },
        },
    }


def _employability(due: str, assigned: str) -> dict:
    return {"due": due, "assigned": assigned, "name": "Employability", "category": "Participation",
            "score": 10.0, "score_raw": "10.00", "points": 10.0, "percent": "100%"}


def test_hac_only_collision_gets_dated_keys(tmp_path):
    """Two HAC-only rows, same normalised name, different due dates: genuinely different
    assignments (per the Task 1 spike), so both keys gain the due-date suffix -- not just the
    second row, so the key never depends on row order."""
    conn = db.open_db(tmp_path)
    snap = _snap_hac_only([_employability("09/04/2026", "08/31/2026"), _employability("08/21/2026", "08/13/2026")])
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    keys = {row["key"] for row in conn.execute("SELECT key FROM items")}
    assert keys == {"hac:Honors English 9:employability:2026-09-04", "hac:Honors English 9:employability:2026-08-21"}
    assert r.items == 2

    # Reversing row order must not change which row gets which key.
    conn2 = db.open_db(tmp_path / "reversed")
    snap2 = _snap_hac_only([_employability("08/21/2026", "08/13/2026"), _employability("09/04/2026", "08/31/2026")])
    ingest.record(conn2, snap2, tz=TZ, now=T1)
    keys2 = {row["key"] for row in conn2.execute("SELECT key FROM items")}
    assert keys2 == keys


def test_hac_only_non_colliding_keeps_base_key(tmp_path):
    """No name collision among the HAC-only rows: each keeps the plain base key."""
    conn = db.open_db(tmp_path)
    snap = _snap_hac_only([
        _employability("09/04/2026", "08/31/2026"),
        {"due": "09/11/2026", "assigned": "09/09/2026", "name": "Reading log", "category": "Assignments",
         "score": None, "score_raw": "", "points": 5.0, "percent": ""},
    ])
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    keys = {row["key"] for row in conn.execute("SELECT key FROM items")}
    assert keys == {"hac:Honors English 9:employability", "hac:Honors English 9:reading log"}
    assert r.items == 2


def test_hac_only_collision_same_due_date_is_deduped(tmp_path):
    """Two colliding rows that also share a due date are the same row scraped twice, not two
    assignments: keep the first, skip the rest, and don't count it anywhere."""
    conn = db.open_db(tmp_path)
    snap = _snap_hac_only([_employability("09/04/2026", "08/31/2026"), _employability("09/04/2026", "08/31/2026")])
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    keys = {row["key"] for row in conn.execute("SELECT key FROM items")}
    assert keys == {"hac:Honors English 9:employability:2026-09-04"}
    assert r.items == 1


def test_hac_only_collision_without_due_dates_gets_ordinal_keys(tmp_path):
    """A missing due date can't prove two same-named rows are the same row scraped twice, so
    -- unlike the same-due-date case -- undated colliding rows never merge: each keeps its own
    ordinal-suffixed key."""
    conn = db.open_db(tmp_path)
    snap = _snap_hac_only([
        {"due": "", "assigned": "", "name": "Employability", "category": "Participation",
         "score": 10.0, "score_raw": "10.00", "points": 10.0, "percent": "100%"},
        {"due": "", "assigned": "", "name": "Employability", "category": "Participation",
         "score": 8.0, "score_raw": "8.00", "points": 10.0, "percent": "80.00%"},
    ])
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    keys = {row["key"] for row in conn.execute("SELECT key FROM items")}
    assert keys == {"hac:Honors English 9:employability:unknown", "hac:Honors English 9:employability:unknown-2"}
    assert r.items == 2


def _hac_class(name: str, code: str, rows: list[dict]) -> dict:
    return {"code": code, "name": name, "marking_period_avg": 90.0, "last_updated": "9/11/2026",
            "assignments": rows, "categories": []}


def _reading_log(due: str = "09/11/2026") -> dict:
    return {"due": due, "assigned": "09/09/2026", "name": "Reading log", "category": "Assignments",
            "score": None, "score_raw": "", "points": 5.0, "percent": ""}


def _snap_students(students: dict) -> dict:
    return {"fetched_at": T1.isoformat(), "fetched_at_epoch": T1.timestamp(),
            "sources": {"canvas": "ok", "hac": "ok"}, "stale": {}, "students": students}


def test_two_kids_in_like_named_classes_keep_separate_items(tmp_path):
    """Two kids in Honors English 9 -- the same section, so even the Canvas assignment id is
    shared -- produce the same item keys. They are different items: if the key alone decided,
    the second kid's observation would collide on (refresh_id, item_id, source) and roll the
    whole snapshot back, and later refreshes would file one kid's score under the other's item.
    """
    conn = db.open_db(tmp_path)
    kid = lambda cid: {                                                                   # noqa: E731
        "name": "Rivera", "canvas_id": cid,
        "canvas": {"courses": [{"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                                "grade": {}, "staff": [], "assignments": [_assignment(77, "Quiz 1")]}]},
        "hac": {"week_view": [], "classes": [_hac_class("Honors English 9 S1", "13001 - 5", [_reading_log()])]},
    }
    r = ingest.record(conn, _snap_students({"Alex": kid(123), "Sam": kid(124)}), tz=TZ, now=T1)
    assert r.items == 4                                                     # two kids x (Quiz 1 + Reading log)
    rows = conn.execute("""SELECT s.key AS kid, i.key AS item FROM items i JOIN students s ON s.id = i.student_id
                           ORDER BY s.key, i.key""").fetchall()
    assert [(x["kid"], x["item"]) for x in rows] == [
        ("Alex", "canvas:77"), ("Alex", "hac:Honors English 9:reading log"),
        ("Sam", "canvas:77"), ("Sam", "hac:Honors English 9:reading log")]
    assert conn.execute("SELECT count(*) FROM item_observations").fetchone()[0] == 4     # every observation landed


def test_one_kid_in_two_sections_of_one_course_keeps_separate_items(tmp_path):
    """Two HAC classes whose short names agree ("Honors English 9 - 1" and "- 3") list the same
    assignment name: one key, two courses, two items -- and no collision error."""
    conn = db.open_db(tmp_path)
    snap = _snap_students({"Alex": {
        "name": "Alex Example", "canvas_id": 123, "canvas": {"courses": []},
        "hac": {"week_view": [], "classes": [_hac_class("Honors English 9 - 1", "13001 - 1", [_reading_log()]),
                                            _hac_class("Honors English 9 - 3", "13001 - 3", [_reading_log()])]},
    }})
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    assert r.items == 2
    rows = conn.execute("""SELECT c.name AS course, i.key AS item FROM items i JOIN courses c ON c.id = i.course_id
                           ORDER BY c.name""").fetchall()
    assert [(x["course"], x["item"]) for x in rows] == [
        ("Honors English 9 - 1", "hac:Honors English 9:reading log"),
        ("Honors English 9 - 3", "hac:Honors English 9:reading log")]
    ingest.record(conn, snap, tz=TZ, now=T2)                                # a second refresh adds neither
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 2


def test_a_renamed_course_takes_its_items_with_it(tmp_path):
    """The school edits a Canvas course name mid-year, which makes a new `courses` row. The
    assignment keeps its id, so it follows the course rather than starting a second history."""
    conn = db.open_db(tmp_path)
    snap = snapshot(T1)
    ingest.record(conn, snap, tz=TZ, now=T1)
    renamed = snapshot(T2)
    renamed["students"]["Alex"]["canvas"]["courses"][0]["name"] = "Honors English 9 S2-2027-Hoch"
    ingest.record(conn, renamed, tz=TZ, now=T2)
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 3     # the same three, not six
    row = conn.execute("""SELECT c.name AS course, i.first_seen, i.last_seen FROM items i JOIN courses c ON c.id = i.course_id
                          WHERE i.key = 'canvas:77'""").fetchall()
    assert len(row) == 1 and row[0]["course"] == "Honors English 9 S2-2027-Hoch"
    assert (row[0]["first_seen"], row[0]["last_seen"]) == (1, 2)            # one history, not two


def test_published_is_observed_and_defaults_to_published(tmp_path):
    conn = db.open_db(tmp_path)
    snap = snapshot(T1)
    assignments = snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"]
    assignments[1]["published"] = False
    del assignments[0]["published"]                                         # an older snapshot says nothing
    ingest.record(conn, snap, tz=TZ, now=T1)
    got = {r["key"]: r["published"] for r in conn.execute(
        """SELECT i.key, o.published FROM item_observations o JOIN items i ON i.id = o.item_id WHERE o.source = 'canvas'""")}
    assert got == {"canvas:77": 1, "canvas:78": 0}
    hac = conn.execute("""SELECT o.published FROM item_observations o JOIN items i ON i.id = o.item_id
                          WHERE i.key LIKE 'hac:%'""").fetchone()[0]
    assert hac is None                                                      # HAC has no such notion
    # publishing it again is a change of its own, so it becomes a new observation
    snap2 = snapshot(T2)
    r = ingest.record(conn, snap2, tz=TZ, now=T2)
    assert r.observations == 1
    assert conn.execute("""SELECT o.published FROM item_observations o JOIN items i ON i.id = o.item_id
                           WHERE i.key = 'canvas:78' ORDER BY o.id DESC""").fetchone()[0] == 1


def test_two_hac_rows_matching_one_canvas_twin_attach_only_the_first(tmp_path):
    """A Canvas item gets at most one HAC observation per refresh: when two HAC rows both name
    the same work as one Canvas assignment (a collision open_items already resolves with
    `next(...)`), the first attaches and the second is dropped -- not turned into a HAC-only
    item, and not a second write to the same (refresh_id, item_id, 'hac') observation, which
    would violate item_observations' UNIQUE constraint and roll back the whole snapshot."""
    conn = db.open_db(tmp_path)
    snap = {
        "fetched_at": T1.isoformat(), "fetched_at_epoch": T1.timestamp(),
        "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {
            "Alex": {
                "name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
                "canvas": {"courses": [{
                    "id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                    "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                    "staff": [],
                    "assignments": [_assignment(77, "Quiz 1")],
                }]},
                "hac": {"week_view": [], "classes": [{
                    "code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 75.67, "last_updated": "9/11/2026",
                    "assignments": [
                        {"due": "09/12/2026", "assigned": "09/10/2026", "name": "Quiz #1", "category": "Assessments",
                         "score": 28.0, "score_raw": "28.00", "points": 30.0, "percent": "93.33%"},
                        {"due": "09/12/2026", "assigned": "09/10/2026", "name": "Quiz #1", "category": "Assessments",
                         "score": 15.0, "score_raw": "15.00", "points": 30.0, "percent": "50.00%"},
                    ],
                    "categories": [],
                }]},
            },
        },
    }
    r = ingest.record(conn, snap, tz=TZ, now=T1)                    # must not raise sqlite3.IntegrityError
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1   # canvas:77 only, no HAC-only item
    assert r.items == 1
    quiz_id = conn.execute("SELECT id FROM items WHERE key='canvas:77'").fetchone()[0]
    scores = [row["score"] for row in conn.execute(
        "SELECT score FROM item_observations WHERE item_id=? AND source='hac'", (quiz_id,))]
    assert scores == [28.0]                                          # the first row's values only


def test_the_teacher_of_record_supplies_both_the_name_and_the_address(tmp_path):
    """A TA listed first must not lend the teacher their mailto: (the parent emails it)."""
    conn = db.open_db(tmp_path)
    snap = snapshot(T1)
    snap["students"]["Alex"]["canvas"]["courses"][0]["staff"] = [
        {"name": "Avery Aide", "email": "ta@x", "roles": ["TaEnrollment"]},
        {"name": "Michael Hoch", "email": "t@x", "roles": ["TeacherEnrollment"]},
    ]
    ingest.record(conn, snap, tz=TZ, now=T1)
    course = conn.execute("SELECT * FROM courses WHERE source='canvas'").fetchone()
    assert (course["teacher"], course["teacher_email"]) == ("Michael Hoch", "t@x")


def _snap_with(canvas_assignments, hac_rows):
    return {
        "fetched_at": T1.isoformat(), "fetched_at_epoch": T1.timestamp(),
        "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {"Alex": {
            "name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
            "canvas": {"courses": [{"id": 7, "name": "Concert Band S1-2027-Desmond", "course_code": "BAND",
                                    "grade": {"current_score": None, "final_score": None, "current_grade": None, "hidden": False},
                                    "staff": [], "assignments": canvas_assignments}]},
            "hac": {"week_view": [], "classes": [{"code": "21001 - 1", "name": "Concert Band - 1", "marking_period_avg": 100.0,
                                                  "last_updated": "9/11/2026", "assignments": hac_rows, "categories": []}]},
        }},
    }


def _hac_row(name, due="08/21/2026", points=10.0, score=10.0):
    return {"due": due, "assigned": "08/14/2026", "name": name, "category": "Classwork",
            "score": score, "score_raw": f"{score:.2f}", "points": points, "percent": "100.00%"}


def test_a_hac_row_the_title_matcher_misses_still_pairs_on_due_date_and_points(tmp_path):
    """Seen on a real gradebook: Canvas "Concert Contract Due", HAC "Concert Contract" -- the
    same ten-point sheet, due the same day, graded 10/10 in HAC and unsubmitted in Canvas.
    `same_item` did not pair them (two words vs three), so the record counted the work twice:
    once as done on paper (HAC) and once as unknown (Canvas)."""
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(501, "Concert Contract Due", due="2026-08-21T23:59:00-04:00",
                                   submission_types=["on_paper"], missing=False)],
                      [_hac_row("Concert Contract")])
    ingest.record(conn, snap, tz=TZ, now=T1)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE key LIKE 'hac:%'").fetchone()[0] == 0   # no second item
    obs = conn.execute("""SELECT o.source, o.score FROM item_observations o JOIN items i ON i.id = o.item_id
                          WHERE i.key = 'canvas:501' ORDER BY o.source""").fetchall()
    assert [(r["source"], r["score"]) for r in obs] == [("canvas", None), ("hac", 10.0)]


def test_the_fallback_pairs_only_when_exactly_one_canvas_item_fits(tmp_path):
    """Two same-day ten-point items with unrelated titles must not be guessed between."""
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(501, "Scale sheet", due="2026-08-21T23:59:00-04:00", submission_types=["on_paper"], missing=False),
                       _assignment(502, "Rhythm sheet", due="2026-08-21T23:59:00-04:00", submission_types=["on_paper"], missing=False)],
                      [_hac_row("Concert Contract")])
    ingest.record(conn, snap, tz=TZ, now=T1)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE key LIKE 'hac:%'").fetchone()[0] == 1   # stays HAC-only


def test_two_canvas_assignments_with_the_same_title_stay_two_items(tmp_path):
    """#11 item 21: a real gradebook listed "Cool-down: Find the Volume of a Figure" twice for
    one kid, same course, same 4 points, same due date, as Canvas assignments 2571430 and
    2571431. The audit wondered whether that was a dedupe miss. It is not: they are two
    assignments the teacher created, and `items.key` is `canvas:<id>` -- the source's own
    identity -- precisely so the app never decides two of a teacher's assignments are one.

    Collapsing them would under-count the work and let a kid hand in one of the two and look
    finished. This pins that they stay apart.
    """
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(2571430, "Cool-down: Find the Volume of a Figure",
                                   due="2026-09-10T23:59:00-04:00", points_possible=4.0),
                       _assignment(2571431, "Cool-down: Find the Volume of a Figure",
                                   due="2026-09-10T23:59:00-04:00", points_possible=4.0)], [])
    ingest.record(conn, snap, tz=TZ, now=T1)
    rows = conn.execute("SELECT key FROM items WHERE name LIKE 'Cool-down%' ORDER BY key").fetchall()
    assert [r["key"] for r in rows] == ["canvas:2571430", "canvas:2571431"]


def test_a_hac_row_will_not_guess_between_two_identical_canvas_assignments(tmp_path):
    """The other half of the same fact. When the teacher has entered the work twice in Canvas,
    a HAC row that matches both on date and points matches neither: `_twin_by_date_and_points`
    pairs only when exactly one candidate fits, so an ambiguous grade is never attached to an
    arbitrary one of the two."""
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(2571430, "Cool-down: Find the Volume of a Figure",
                                   due="2026-08-21T23:59:00-04:00", submission_types=["on_paper"],
                                   missing=False, points_possible=10.0),
                       _assignment(2571431, "Cool-down: Find the Volume of a Figure",
                                   due="2026-08-21T23:59:00-04:00", submission_types=["on_paper"],
                                   missing=False, points_possible=10.0)],
                      [_hac_row("Volume cool down")])
    ingest.record(conn, snap, tz=TZ, now=T1)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE key LIKE 'hac:%'").fetchone()[0] == 1


def test_the_fallback_never_crosses_a_number(tmp_path):
    """Same day, same points, but "Week 1" is not "Week 2" however the rest of the title reads."""
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(501, "Week 2 participation", due="2026-08-21T23:59:00-04:00", submission_types=["none"], missing=False)],
                      [_hac_row("Week 1")])
    ingest.record(conn, snap, tz=TZ, now=T1)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE key LIKE 'hac:%'").fetchone()[0] == 1


def test_a_chapter_prefix_on_one_side_does_not_block_the_pair(tmp_path):
    """"Ch. 1 - Community Health" in HAC, "Community Health" in Canvas: same day, same points,
    and the only number is on one side. Seen live; the first cut of the fallback refused it."""
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(501, "Community Health", due="2026-08-21T23:59:00-04:00",
                                   submission_types=["on_paper"], missing=False, points_possible=20.0)],
                      [_hac_row("Ch. 1 - Community Health", points=20.0, score=20.0)])
    ingest.record(conn, snap, tz=TZ, now=T1)
    assert conn.execute("SELECT COUNT(*) FROM items WHERE key LIKE 'hac:%'").fetchone()[0] == 0


def test_lock_dates_live_on_the_item_and_lock_state_on_the_observation(tmp_path):
    conn = db.open_db(tmp_path)
    snap = _snap_with([_assignment(601, "Locked quiz", unlock_at="2026-09-01T00:00:00-04:00", lock_at="2026-09-05T23:59:59-04:00",
                                   locked=True, lock_reason="closed")], [])
    ingest.record(conn, snap, tz=TZ, now=T1)
    item = conn.execute("SELECT * FROM items WHERE key='canvas:601'").fetchone()
    assert (item["unlock_at"], item["lock_at"]) == ("2026-09-01T00:00:00-04:00", "2026-09-05T23:59:59-04:00")
    obs = conn.execute("SELECT * FROM item_observations WHERE item_id=?", (item["id"],)).fetchone()
    assert (obs["locked"], obs["lock_reason"]) == (1, "closed")


def test_closing_an_assignment_is_a_new_observation(tmp_path):
    conn = db.open_db(tmp_path)
    open_ = _snap_with([_assignment(602, "Quiz", locked=False, lock_reason=None)], [])
    ingest.record(conn, open_, tz=TZ, now=T1)
    closed = _snap_with([_assignment(602, "Quiz", locked=True, lock_reason="closed")], [])
    closed["fetched_at"], closed["fetched_at_epoch"] = T2.isoformat(), T2.timestamp()
    r = ingest.record(conn, closed, tz=TZ, now=T2)
    assert r.observations == 1
    rows = conn.execute("SELECT locked, lock_reason FROM item_observations ORDER BY id").fetchall()
    assert [tuple(x) for x in rows] == [(0, None), (1, "closed")]


def test_a_snapshot_from_before_lock_fields_existed_and_a_hac_row_both_say_nothing(tmp_path):
    conn = db.open_db(tmp_path)
    ingest.record(conn, snapshot(T1), tz=TZ, now=T1)
    quiz = conn.execute("SELECT id FROM items WHERE key='canvas:77'").fetchone()[0]
    for src in ("canvas", "hac"):
        obs = conn.execute("SELECT locked, lock_reason FROM item_observations WHERE item_id=? AND source=?", (quiz, src)).fetchone()
        assert tuple(obs) == (None, None), src
    assert conn.execute("SELECT lock_at FROM items WHERE id=?", (quiz,)).fetchone()[0] is None

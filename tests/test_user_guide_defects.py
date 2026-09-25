"""Six rules the user guide turned up wrong, pinned where they were found.

#131  A Canvas observation is rewritten whenever any field changes, the availability window
      locking included, and that read as "Canvas marked it missing after HAC's grade".
#132  "Unit 3 Test Retake" paired with "Unit 3 Test" -- the first title over the bar, not
      the best -- and the retake's own HAC grade was then dropped on the floor.
#135  HAC's "EXC" (excused) was read as no grade at all: unknown on screen, silently gone
      from the sheet.
#136  A lone HAC-only row was keyed by title alone, and a second row with that title re-keyed
      it, orphaning its flag, notes and history.
#138  "of N due so far" counted work handed in early, before it was due.
#139  Work due at 00:00 said "Due tomorrow" the evening it had to be finished.

The setups are the scratch demonstrations that confirmed each defect; the assertions are
turned round to say what a parent expects (docs/outcomes.md).
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fridgesheet import dates, late_rules, open_items, sheet
from fridgesheet.web import db, ingest, outcomes, reconcile, verdicts
from fridgesheet.web.stores import flags, items as items_store, notes, trends

TZ = ZoneInfo("America/New_York")
RULES = late_rules.LateRules(late_rules.Rule(), [], [])
T = {1: "2026-09-13T08:00:00-04:00", 2: "2026-09-14T08:00:00-04:00", 3: "2026-09-16T08:00:00-04:00",
     4: "2026-09-17T08:00:00-04:00", 5: "2026-09-18T08:00:00-04:00"}


def _a(id, name, due, **kw):
    base = {"id": id, "name": name, "due_at": f"2026-{due}T23:59:00-04:00", "unlock_at": None, "lock_at": None,
            "created_at": "2026-08-20T08:00:00-04:00", "points_possible": 10.0, "submission_types": ["online_upload"],
            "group": "Homework", "published": True, "score": None, "grade": None, "state": "unsubmitted",
            "late": False, "missing": False, "excused": False, "submitted_at": None, "locked": False}
    base.update(kw)
    return base


def _h(name, due, score, points=10.0, raw=None):
    return {"due": due, "assigned": "09/01/2026", "name": name, "category": "Assignments", "score": score,
            "score_raw": raw if raw is not None else ("" if score is None else f"{score:.2f}"), "points": points,
            "percent": "" if score is None else "90%"}


def snap(canvas_assign, hac_rows, when=T[2]):
    return {"fetched_at": when, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
            "students": {"Alex": {"name": "Alex Example", "canvas": {"courses": [
                {"id": 5, "name": "Honors English 9 S1-2027-Hoch", "grade": {}, "staff": [], "assignments": canvas_assign}]},
                "hac": {"classes": [{"code": "1", "name": "Honors English 9 S1", "marking_period_avg": 90.0,
                                     "last_updated": None, "assignments": hac_rows}]}}}}


def _student(conn):
    return conn.execute("SELECT * FROM students").fetchone()


def views(conn, now):
    return {v.name: v for v in items_store._views(conn, _student(conn), now=now, rules=RULES)}


def _at(month, day, hour=9, minute=0):
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


# --- #131: only a *new missing mark* is Canvas contradicting HAC's grade ----------------------

def _canvas(rid, **kw):
    base = dict(refresh_id=rid, state="unsubmitted", score=None, grade=None, submitted_at=None, late=0,
                missing=0, excused=0, published=1, missing_since=None, scored_since=None)
    base.update(kw)
    return base


def _hac(rid, score=None):
    return dict(refresh_id=rid, state="graded" if score is not None else "ungraded", score=score, grade=None,
                submitted_at=None, late=None, missing=None, excused=None, published=None,
                missing_since=None, scored_since=rid if score is not None else None)


def _item(kind="online", due="2026-09-12T23:59:00-04:00", points=10.0, peer=2):
    return {"kind": kind, "due": due, "points": points, "kid": "Alex", "course_name": "Honors English 9 S1",
            "peer_course_id": peer}


def test_classify_compares_when_the_missing_mark_was_set_not_when_canvas_last_changed():
    """Missing since refresh 1, HAC's grade in refresh 2, and some other Canvas field changed in
    refresh 3: the mark is older than the grade, so the grade decides."""
    obs = {"canvas": _canvas(3, missing=1, missing_since=1), "hac": _hac(2, 9.0)}
    assert outcomes.classify(_item(), obs, _at(9, 16)) == outcomes.DONE_OFFLINE
    v = verdicts.verdict(_item(), obs, flag=None, flag_set_at="", now=_at(9, 16), rules=RULES, refresh_times=T)
    assert (v.state, v.kind) == (verdicts.DECIDED, "graded_in_hac")


def test_a_missing_mark_set_after_the_hac_grade_still_asks():
    obs = {"canvas": _canvas(3, missing=1, missing_since=3), "hac": _hac(2, 9.0)}
    assert outcomes.classify(_item(), obs, _at(9, 16)) == outcomes.NOT_DONE
    v = verdicts.verdict(_item(), obs, flag=None, flag_set_at="", now=_at(9, 16), rules=RULES, refresh_times=T)
    assert (v.state, v.kind) == (verdicts.QUESTION, "missing_after_grade")


def test_a_lock_flip_does_not_reopen_a_hac_graded_item(tmp_path):
    """The guide's repro: Canvas auto-marked Quiz 1 missing on 9/13, HAC posted 9/10 on 9/14
    (done on paper), and on 9/16 the availability window closed with the mark unchanged."""
    conn = db.open_db(tmp_path)
    a = _a(77, "Quiz 1", "09-12", missing=True)
    ingest.record(conn, snap([a], [_h("Quiz 1", "09/12/2026", None)], T[1]), tz=TZ)
    ingest.record(conn, snap([a], [_h("Quiz 1", "09/12/2026", 9.0)], T[2]), tz=TZ)
    v = views(conn, _at(9, 15))["Quiz 1"]
    assert v.outcome == outcomes.DONE_OFFLINE and v.verdict.kind == "graded_in_hac"
    locked = dict(a, locked=True, lock_reason="closed")       # missing unchanged, only the lock flipped
    ingest.record(conn, snap([locked], [_h("Quiz 1", "09/12/2026", 9.0)], T[3]), tz=TZ)
    v = views(conn, _at(9, 16))["Quiz 1"]
    assert v.outcome == outcomes.DONE_OFFLINE
    assert (v.verdict.state, v.verdict.kind) == (verdicts.DECIDED, "graded_in_hac")
    assert items_store.dashboard_counts(conn, _student(conn), now=_at(9, 16), rules=RULES).record.not_done == 0


def test_a_missing_mark_that_arrives_after_the_hac_grade_still_asks_end_to_end(tmp_path):
    conn = db.open_db(tmp_path)
    a = _a(77, "Quiz 1", "09-12")
    ingest.record(conn, snap([a], [_h("Quiz 1", "09/12/2026", None)], T[1]), tz=TZ)
    ingest.record(conn, snap([a], [_h("Quiz 1", "09/12/2026", 9.0)], T[2]), tz=TZ)
    ingest.record(conn, snap([dict(a, missing=True)], [_h("Quiz 1", "09/12/2026", 9.0)], T[3]), tz=TZ)
    v = views(conn, _at(9, 16))["Quiz 1"]
    assert v.outcome == outcomes.NOT_DONE and v.verdict.kind == "missing_after_grade"


def test_ingest_records_the_refresh_in_which_a_mark_or_a_score_first_appeared(tmp_path):
    """`missing_since` and `scored_since` follow the current run of the mark and of the score:
    carried across a rewrite for some other field, cleared when the mark lifts, restarted when
    it returns, restarted when the score changes."""
    conn = db.open_db(tmp_path)
    a = _a(77, "Quiz 1", "09-12", missing=True)
    ingest.record(conn, snap([a], [], T[1]), tz=TZ)
    ingest.record(conn, snap([dict(a, locked=True, lock_reason="closed")], [], T[2]), tz=TZ)
    ingest.record(conn, snap([dict(a, missing=False, state="graded", score=8.0)], [], T[3]), tz=TZ)
    ingest.record(conn, snap([dict(a, missing=False, state="graded", score=8.0, locked=True, lock_reason="closed")], [], T[4]), tz=TZ)
    ingest.record(conn, snap([dict(a, missing=True, state="graded", score=0.0)], [], T[5]), tz=TZ)
    rows = conn.execute("SELECT refresh_id, missing_since, scored_since FROM item_observations WHERE source='canvas' ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [(1, 1, None), (2, 1, None), (3, None, 3), (4, None, 3), (5, 5, 5)]


def test_the_hac_grace_period_runs_from_when_canvas_graded_it():
    """Canvas graded it in refresh 2 (9/8) and changed something else in refresh 3 (9/15): HAC
    has had a week, so this is a question today, not a fresh wait."""
    obs = {"canvas": _canvas(3, state="graded", score=8.0, scored_since=2), "hac": _hac(3)}
    v = verdicts.verdict(_item(), obs, flag=None, flag_set_at="", now=_at(9, 15, 14), rules=RULES,
                         refresh_times={2: "2026-09-08T06:00:00-04:00", 3: "2026-09-15T06:00:00-04:00"})
    assert (v.state, v.kind) == (verdicts.QUESTION, "hac_still_blank")
    assert v.facts["when"] == "9/8"


def test_a_lock_flip_does_not_restart_the_hac_grace_period_end_to_end(tmp_path):
    conn = db.open_db(tmp_path)
    a = _a(78, "Essay", "09-12", state="graded", score=8.0)
    ingest.record(conn, snap([a], [_h("Essay", "09/12/2026", None)], T[2]), tz=TZ)
    before = views(conn, _at(9, 15))["Essay"].verdict
    assert before.kind == "hac_lag" and before.asks_on == date(2026, 9, 21)
    ingest.record(conn, snap([dict(a, locked=True, lock_reason="closed")], [_h("Essay", "09/12/2026", None)], T[3]), tz=TZ)
    after = views(conn, _at(9, 16))["Essay"].verdict
    assert after.kind == "hac_lag" and after.asks_on == date(2026, 9, 21)


def test_migrating_an_older_database_backfills_when_marks_first_appeared(tmp_path):
    """A file written before the two columns existed gets them filled from its own history,
    so the day after an upgrade reads the same as the day before."""
    conn = db.connect(tmp_path / "old.db")
    conn.executescript("BEGIN;\n" + db._SCHEMA_V1 + db._SCHEMA_V2 + db._SCHEMA_V3 + db._SCHEMA_V4
                       + "\nINSERT INTO schema_version(version) VALUES (4);\nCOMMIT;")
    with conn:
        conn.executemany("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (?, 't', '{}', 1)", [(i,) for i in range(1, 5)])
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Bio', 'Bio')")
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (1, 1, 1, 'canvas:1', 'WS', 1, 4)")
        conn.executemany("INSERT INTO item_observations(refresh_id, item_id, source, missing, score, locked) VALUES (?, 1, 'canvas', ?, ?, ?)",
                         [(1, 1, None, 0), (2, 1, None, 1), (3, 0, 8.0, 0), (4, 0, 8.0, 1)])
    assert db.migrate(conn) == db.SCHEMA_VERSION
    rows = conn.execute("SELECT refresh_id, missing_since, scored_since FROM item_observations ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [(1, 1, None), (2, 1, None), (3, None, 3), (4, None, 3)]


# --- #135: HAC "EXC" is excused, everywhere ---------------------------------------------------

def test_hac_excused_is_carried_through_ingest():
    assert ingest._hac_values(_h("Field trip form", "09/01/2026", None, raw="EXC"))["excused"] == 1
    assert ingest._hac_values(_h("Field trip form", "09/01/2026", None, raw="EX"))["excused"] == 1
    # Not 0: an older observation stored None, and a changed value would rewrite every HAC
    # row on the first refresh after the upgrade (`_observe` compares the fields).
    assert ingest._hac_values(_h("Lab", "09/01/2026", None))["excused"] is None
    assert ingest._hac_values(_h("Lab", "09/01/2026", 9.0))["excused"] is None


def test_hac_excused_is_excused_on_screen(tmp_path):
    """The guide's repro: a HAC-only "Field trip form" marked EXC. Excused, counted nowhere,
    never asked about."""
    conn = db.open_db(tmp_path)
    ingest.record(conn, snap([], [_h("Field trip form", "09/01/2026", None, raw="EXC")]), tz=TZ)
    v = views(conn, _at(9, 15))["Field trip form"]
    assert v.outcome == outcomes.EXCUSED and not v.actionable and not v.open_in
    assert (v.verdict.state, v.verdict.kind) == (verdicts.STATUS, "excused")
    assert (v.status, v.grade, v.handed_in) == ("Excused", "Excused", "Excused")
    assert items_store.dashboard_counts(conn, _student(conn), now=_at(9, 15), rules=RULES).record.total == 0


def test_hac_excused_beats_canvas_missing():
    obs = {"canvas": _canvas(2, missing=1, missing_since=2), "hac": dict(_hac(2), excused=1)}
    assert outcomes.classify(_item(), obs, _at(9, 15)) == outcomes.EXCUSED
    v = verdicts.verdict(_item(), obs, flag=None, flag_set_at="", now=_at(9, 15), rules=RULES, refresh_times=T)
    assert (v.state, v.kind) == (verdicts.STATUS, "excused")


def test_hac_excused_does_not_print():
    entry = snap([_a(4, "Field trip form", "09-10", missing=True)],
                 [_h("Field trip form", "09/10/2026", None, raw="EXC"), _h("Permission slip", "09/01/2026", None, raw="EXC")])["students"]["Alex"]
    work = open_items.open_items(entry, "Alex", _at(9, 15, 14))
    assert [i.name for i in work.items] == [] and work.dropped == []


# --- #138: "due so far" is work that is due ----------------------------------------------------

def test_handed_in_early_is_on_time_but_not_on_the_record_yet():
    item = {"kind": "online", "due": "2026-09-30T23:59:00-04:00", "points": 10}
    c = _canvas(1, state="submitted", submitted_at="2026-09-14T10:00:00-04:00")
    assert outcomes.classify(item, {"canvas": c}, _at(9, 15)) == outcomes.ON_TIME       # early is still on time
    assert not outcomes.on_record(outcomes.ON_TIME, datetime.fromisoformat(item["due"]), _at(9, 15))
    assert outcomes.on_record(outcomes.ON_TIME, datetime.fromisoformat(item["due"]), _at(10, 1))


def test_undated_work_is_on_the_record_once_something_has_happened_to_it():
    """No due date can never pass, so a grade, a hand-in or a mark is what puts it on the
    record; nothing at all (not due yet) never is."""
    now = _at(9, 15)
    assert outcomes.on_record(outcomes.DONE_OFFLINE, None, now)
    assert outcomes.on_record(outcomes.NOT_DONE, None, now)
    assert not outcomes.on_record(outcomes.NOT_DUE, None, now)
    assert not outcomes.on_record(outcomes.EXCUSED, None, now) and not outcomes.on_record(outcomes.EXCUSED, _at(9, 1), now)


def test_the_record_line_counts_only_work_that_is_due(tmp_path):
    """Quiz 1 was due 9/12 and handed in; the essay is due Friday and was handed in on Monday.
    On Tuesday the record is 1 on time of 1 due so far, and the Trends bucket for this week
    does not hold the essay yet. The essay still filters as on time: the outcome is right,
    the tally was not."""
    conn = db.open_db(tmp_path)
    ca = [_a(1, "Quiz 1", "09-12", state="submitted", submitted_at="2026-09-12T10:00:00-04:00"),
          _a(2, "Essay", "09-18", state="submitted", submitted_at="2026-09-14T10:00:00-04:00")]
    ingest.record(conn, snap(ca, []), tz=TZ)
    now = _at(9, 15, 14)
    record = items_store.dashboard_counts(conn, _student(conn), now=now, rules=RULES).record
    assert (record.on_time, record.total) == (1, 1)
    assert views(conn, now)["Essay"].outcome == outcomes.ON_TIME
    week = trends.weekly_outcomes(conn, weeks=1, now=now)[-1]
    assert (week.week_start, week.on_time) == (date(2026, 9, 14), 0)
    later = items_store.dashboard_counts(conn, _student(conn), now=_at(9, 19), rules=RULES).record
    assert (later.on_time, later.total) == (2, 2)


# --- #139: due at midnight means due tonight ----------------------------------------------------

def test_a_deadline_in_the_first_hour_belongs_to_the_evening_before():
    assert dates.deadline_date(_at(9, 16, 0, 0)) == date(2026, 9, 15)
    assert dates.deadline_date(_at(9, 16, 0, 59)) == date(2026, 9, 15)
    assert dates.deadline_date(_at(9, 16, 1, 0)) == date(2026, 9, 16)
    assert dates.deadline_date(_at(9, 16, 23, 59)) == date(2026, 9, 16)


def test_midnight_due_says_tonight_on_screen():
    """The guide's repro: due 9/16 00:00, read at 8pm on 9/15."""
    item = {"kind": "online", "due": "2026-09-16T00:00:00-04:00", "points": 10}
    obs = {"canvas": _canvas(1)}
    due = datetime.fromisoformat(item["due"])
    assert items_store.status_text(item, obs, _at(9, 15, 20)) == "Due tonight"
    assert items_store.due_relative(due, _at(9, 15, 20)) == "tonight"
    assert items_store.status_text(item, obs, _at(9, 14, 20)) == "Due tomorrow"
    assert items_store.due_relative(due, _at(9, 14, 20)) == "tomorrow"
    assert items_store.status_text(item, obs, _at(9, 12, 20)) == "Due Tue"
    # An ordinary end-of-day deadline reads as it always did.
    plain = {"kind": "online", "due": "2026-09-16T23:59:00-04:00", "points": 10}
    assert items_store.status_text(plain, obs, _at(9, 15, 20)) == "Due tomorrow"
    assert items_store.status_text(plain, obs, _at(9, 16, 20)) == "Due today"


def test_midnight_due_says_tonight_on_the_sheet():
    a = _a(1, "Quiz 1", "09-16", due_at="2026-09-16T00:00:00-04:00")
    entry = snap([a], [])["students"]["Alex"]
    assert [i.status for i in open_items.open_items(entry, "Alex", _at(9, 15, 20)).items] == ["DUE TONIGHT"]
    assert [i.status for i in open_items.open_items(entry, "Alex", _at(9, 14, 20)).items] == ["DUE TOMORROW"]
    assert [i.status for i in open_items.open_items(entry, "Alex", _at(9, 12, 20)).items] == ["DUE TUE"]
    assert sheet.STATUS_COLOR["DUE TONIGHT"] == sheet.BLUE
    assert sheet.status_word("DUE TONIGHT", "early") == "Due tonight"
    assert sheet.status_word("DUE TONIGHT", "older") == "DUE TONIGHT"


def test_the_dashboard_counts_a_midnight_deadline_as_due_today(tmp_path):
    conn = db.open_db(tmp_path)
    ingest.record(conn, snap([_a(1, "Quiz 1", "09-16", due_at="2026-09-16T00:00:00-04:00")], []), tz=TZ)
    counts = items_store.dashboard_counts(conn, _student(conn), now=_at(9, 15, 20), rules=RULES)
    assert (counts.due_today, counts.due_tomorrow) == (1, 0)


# --- #132: each title gets its own twin; a HAC row that finds none stays a HAC-only item ---------

def _graded(id, name, due, score):
    return _a(id, name, due, state="graded", score=score, submitted_at=f"2026-{due}T10:00:00-04:00")


def test_a_retake_keeps_its_own_hac_grade_on_screen(tmp_path):
    """The guide's repro: Canvas "Unit 3 Test" (6) and "Unit 3 Test Retake" (9); HAC has both.
    The retake's HAC 9/10 used to vanish -- its twin was already taken, and the row was
    neither attached nor kept."""
    conn = db.open_db(tmp_path)
    ca = [_graded(1, "Unit 3 Test", "09-10", 6.0), _graded(2, "Unit 3 Test Retake", "09-14", 9.0)]
    hr = [_h("Unit 3 Test", "09/10/2026", 6.0), _h("Unit 3 Test Retake", "09/14/2026", 9.0)]
    ingest.record(conn, snap(ca, hr), tz=TZ)
    v = views(conn, _at(9, 15))
    assert sorted(v) == ["Unit 3 Test", "Unit 3 Test Retake"]
    assert (v["Unit 3 Test"].hac["score"], v["Unit 3 Test Retake"].hac["score"]) == (6.0, 9.0)
    assert v["Unit 3 Test Retake"].verdict.kind != "hac_lag"


def test_the_order_hac_lists_near_twins_in_does_not_matter_on_screen(tmp_path):
    conn = db.open_db(tmp_path)
    ca = [_graded(1, "Essay", "09-10", 6.0), _graded(2, "Essay Corrections", "09-14", 9.0),
          _graded(3, "Lab Report 2", "09-10", 7.0), _graded(4, "Lab Report 2 Revision", "09-14", 10.0)]
    hr = [_h("Lab Report 2 Revision", "09/14/2026", 10.0), _h("Essay Corrections", "09/14/2026", 9.0),
          _h("Lab Report 2", "09/10/2026", 7.0), _h("Essay", "09/10/2026", 6.0)]
    ingest.record(conn, snap(ca, hr), tz=TZ)
    v = views(conn, _at(9, 15))
    assert {n: r.hac["score"] for n, r in v.items()} == {"Essay": 6.0, "Essay Corrections": 9.0,
                                                          "Lab Report 2": 7.0, "Lab Report 2 Revision": 10.0}


def test_a_hac_row_whose_twin_is_taken_stays_a_hac_only_item(tmp_path):
    """Canvas has only "Unit 3 Test"; HAC has that and the retake. The retake's grade is real
    work the kid did: it is its own HAC-only row, never discarded."""
    conn = db.open_db(tmp_path)
    hr = [_h("Unit 3 Test", "09/10/2026", 6.0), _h("Unit 3 Test Retake", "09/14/2026", 9.0)]
    ingest.record(conn, snap([_graded(1, "Unit 3 Test", "09-10", 6.0)], hr), tz=TZ)
    v = views(conn, _at(9, 15))
    assert v["Unit 3 Test"].sources == ("canvas", "hac") and v["Unit 3 Test"].hac["score"] == 6.0
    assert v["Unit 3 Test Retake"].sources == ("hac",) and v["Unit 3 Test Retake"].outcome == outcomes.DONE_OFFLINE
    assert conn.execute("SELECT key FROM items WHERE name = 'Unit 3 Test Retake'").fetchone()["key"] \
        == "hac:Honors English 9:unit 3 test retake:2026-09-14"


def test_a_retake_graded_in_hac_does_not_print_missing():
    """The guide's sheet repro: Canvas "Unit 3 Test Retake" took HAC's "Unit 3 Test" (a 0) and
    printed MISSING for a retake graded 9. Same rule as the screen: each its own."""
    ca = [_a(1, "Unit 3 Test", "09-10", missing=True), _a(2, "Unit 3 Test Retake", "09-14", missing=True, submission_types=["on_paper"])]
    hr = [_h("Unit 3 Test Retake", "09/14/2026", 9.0), _h("Unit 3 Test", "09/10/2026", 0.0)]
    entry = snap(ca, hr)["students"]["Alex"]
    rows = {i.name: i.status for i in open_items.open_items(entry, "Alex", _at(9, 15)).items}
    assert rows == {"Unit 3 Test": "MISSING"}


def test_near_twins_print_by_their_own_hac_rows_whatever_the_order():
    ca = [_a(1, "Essay Corrections", "09-14", missing=True, submission_types=["on_paper"]), _a(2, "Essay", "09-10", missing=True),
          _a(3, "Lab Report 2 Revision", "09-14", missing=True, submission_types=["on_paper"]), _a(4, "Lab Report 2", "09-10", missing=True)]
    hr = [_h("Lab Report 2", "09/10/2026", 0.0), _h("Essay", "09/10/2026", 0.0),
          _h("Lab Report 2 Revision", "09/14/2026", 10.0), _h("Essay Corrections", "09/14/2026", 9.0)]
    entry = snap(ca, hr)["students"]["Alex"]
    rows = {i.name: i.status for i in open_items.open_items(entry, "Alex", _at(9, 15)).items}
    assert rows == {"Essay": "MISSING", "Lab Report 2": "MISSING"}


def test_a_leftover_hac_row_prints_as_its_own_hac_only_row():
    """Canvas has only "Unit 3 Test" (handed in); HAC has that, graded, and the retake, blank
    and past due. The retake used to be swallowed by the near match and never printed."""
    ca = [_graded(1, "Unit 3 Test", "09-10", 6.0)]
    hr = [_h("Unit 3 Test", "09/10/2026", 6.0), _h("Unit 3 Test Retake", "09/12/2026", None)]
    entry = snap(ca, hr)["students"]["Alex"]
    work = open_items.open_items(entry, "Alex", _at(9, 15))
    assert [(i.name, i.status, i.key) for i in work.items] == \
        [("Unit 3 Test Retake", "HAC — NO GRADE", "hac:Honors English 9:unit 3 test retake:2026-09-12")]


# --- #136: a HAC-only item's key is stable, so its flag and notes stay with it -----------------

def test_a_second_same_named_hac_row_does_not_orphan_the_first(tmp_path):
    """The guide's repro: week 1 "Participation" answered *It's done*; week 2 a second
    "Participation" appears. The first keeps its item, its flag and its note; the second is a
    fresh, unflagged row."""
    conn = db.open_db(tmp_path)
    ingest.record(conn, snap([], [_h("Participation", "09/05/2026", None)], T[1]), tz=TZ)
    iid = conn.execute("SELECT id FROM items WHERE name = 'Participation'").fetchone()["id"]
    flags.set_flag(conn, iid, "done", now=T[1])
    notes.add(conn, "item", iid, "asked the teacher", now=T[1])
    ingest.record(conn, snap([], [_h("Participation", "09/05/2026", None), _h("Participation", "09/12/2026", None)], T[2]), tz=TZ)
    live = {r["id"]: r for r in reconcile.live_items(conn, 1, _at(9, 15))}
    assert len(live) == 2 and live[iid]["flag"] == "done"
    assert [r["flag"] for i, r in live.items() if i != iid] == [None]
    assert [n["body"] for n in notes.for_target(conn, "item", iid)] == ["asked the teacher"]
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 2


def test_every_hac_only_key_carries_its_due_date():
    lone = _h("Participation", "09/05/2026", None)
    assert open_items.hac_only_keys([lone], "Honors English 9 S1", TZ) == [(lone, "hac:Honors English 9:participation:2026-09-05")]
    undated = _h("Participation", "", None)
    assert open_items.hac_only_keys([undated], "Honors English 9 S1", TZ) == [(undated, "hac:Honors English 9:participation:unknown")]


def _v5_database(path):
    """A file as the v5 build left it: schema v5, no rows."""
    conn = db.connect(path)
    conn.executescript("BEGIN;\n" + db._SCHEMA_V1 + db._SCHEMA_V2 + db._SCHEMA_V3 + db._SCHEMA_V4
                       + "\nINSERT INTO schema_version(version) VALUES (4);\nCOMMIT;")
    with conn:
        conn.execute("BEGIN")
        db._migrate_v5(conn)
        conn.execute("UPDATE schema_version SET version = 5")
    return conn


def test_migrating_a_v5_database_dates_every_hac_only_key_and_folds_an_orphans_twin(tmp_path):
    """A v5 file after the guide's repro: item 1 is the bare "Participation" (flagged, with a
    note, last seen in refresh 1); item 2 is the dated row the re-key created for the same
    work (a newer flag, a note, a plan step, the later observations); item 3 the second
    Participation; item 4 a lone undated row; item 5 a Canvas item. After: every HAC-only key
    carries its date, item 2 is folded into item 1 -- flags, notes, plan step, observations --
    and nothing else is touched."""
    conn = _v5_database(tmp_path / "old.db")
    with conn:
        conn.executemany("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (?, ?, '{}', 1)", [(i, T[i]) for i in (1, 2, 3)])
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex Example')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'hac', 'Honors English 9 S1', 'Honors English 9')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (2, 1, 'canvas', 'Honors English 9 S1-2027-Hoch', 'Honors English 9')")
        conn.executemany("INSERT INTO items(id, student_id, course_id, key, name, due, first_seen, last_seen) VALUES (?, 1, ?, ?, ?, ?, ?, ?)", [
            (1, 1, "hac:Honors English 9:participation", "Participation", "2026-09-05T23:59:00-04:00", 1, 1),
            (2, 1, "hac:Honors English 9:participation:2026-09-05", "Participation", "2026-09-05T23:59:00-04:00", 2, 3),
            (3, 1, "hac:Honors English 9:participation:2026-09-12", "Participation", "2026-09-12T23:59:00-04:00", 2, 3),
            (4, 1, "hac:Honors English 9:reading log", "Reading log", None, 1, 3),
            (5, 2, "canvas:77", "Quiz 1", "2026-09-12T23:59:00-04:00", 1, 3)])
        conn.executemany("INSERT INTO item_observations(refresh_id, item_id, source, state, score) VALUES (?, ?, 'hac', ?, ?)", [
            (1, 1, "ungraded", None), (2, 2, "ungraded", None), (3, 2, "graded", 5.0), (2, 3, "ungraded", None), (1, 4, "ungraded", None)])
        conn.executemany("INSERT INTO flags(item_id, flag, set_at) VALUES (?, ?, ?)", [(1, "done", T[1]), (2, "follow_up", T[2])])
        conn.executemany("INSERT INTO notes(target_type, target_id, body, created_at, updated_at) VALUES ('item', ?, ?, ?, ?)",
                         [(1, "asked the teacher", T[1], T[1]), (2, "she said Friday", T[2], T[2])])
        conn.execute("INSERT INTO plan_steps(student_id, item_id, title, next_step, owner, planned_for, state, request_key, created_at, updated_at) "
                     "VALUES (1, 2, 'Participation', 'hand it in', 'Alex', '2026-09-16', 'planned', 'r1', ?, ?)", (T[2], T[2]))
    assert db.migrate(conn) == db.SCHEMA_VERSION
    keys = {r["id"]: r["key"] for r in conn.execute("SELECT id, key FROM items")}
    assert keys == {1: "hac:Honors English 9:participation:2026-09-05", 3: "hac:Honors English 9:participation:2026-09-12",
                    4: "hac:Honors English 9:reading log:unknown", 5: "canvas:77"}
    one = conn.execute("SELECT * FROM items WHERE id = 1").fetchone()
    assert (one["first_seen"], one["last_seen"]) == (1, 3)
    assert [tuple(r) for r in conn.execute("SELECT refresh_id, score FROM item_observations WHERE item_id = 1 ORDER BY refresh_id")] \
        == [(1, None), (2, None), (3, 5.0)]
    # One active flag per item: the newer answer stands, the older one is closed off when it was.
    assert [tuple(r) for r in conn.execute("SELECT flag, set_at, cleared_at FROM flags WHERE item_id = 1 ORDER BY set_at")] \
        == [("done", T[1], T[2]), ("follow_up", T[2], None)]
    assert [n["body"] for n in notes.for_target(conn, "item", 1)] == ["she said Friday", "asked the teacher"]   # newest first
    assert [r["item_id"] for r in conn.execute("SELECT item_id FROM plan_steps")] == [1]
    assert conn.execute("SELECT COUNT(*) FROM items WHERE id = 2").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM item_observations WHERE item_id = 2").fetchone()[0] == 0


def test_migrating_the_same_file_twice_changes_nothing_more(tmp_path):
    conn = _v5_database(tmp_path / "old.db")
    with conn:
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex Example')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'hac', 'Honors English 9 S1', 'Honors English 9')")
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, due, first_seen, last_seen) "
                     "VALUES (1, 1, 1, 'hac:Honors English 9:participation', 'Participation', '2026-09-05T23:59:00-04:00', 1, 1)")
    db.migrate(conn)
    before = [tuple(r) for r in conn.execute("SELECT * FROM items")]
    assert db.migrate(conn) == db.SCHEMA_VERSION
    assert [tuple(r) for r in conn.execute("SELECT * FROM items")] == before
    assert before[0][3] == "hac:Honors English 9:participation:2026-09-05"


def test_an_upgraded_file_reads_the_next_refresh_as_the_same_items(tmp_path):
    """The whole point: a flag set under the v5 key is still on the row the next refresh
    upserts, so the day after the upgrade reads like the day before."""
    conn = _v5_database(db.db_path(tmp_path))
    with conn:      # a v5 build's ingest: the bare key
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, ?, '{}', 1)", (T[1],))
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex Example')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'hac', 'Honors English 9 S1', 'Honors English 9')")
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, due, first_seen, last_seen) "
                     "VALUES (1, 1, 1, 'hac:Honors English 9:participation', 'Participation', '2026-09-05T23:59:00-04:00', 1, 1)")
        conn.execute("INSERT INTO item_observations(refresh_id, item_id, source, state) VALUES (1, 1, 'hac', 'ungraded')")
        conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (1, 'done', ?)", (T[1],))
    db.migrate(conn)
    ingest.record(conn, snap([], [_h("Participation", "09/05/2026", None), _h("Participation", "09/12/2026", None)], T[2]), tz=TZ)
    live = {r["id"]: r["flag"] for r in reconcile.live_items(conn, 1, _at(9, 15))}
    assert live[1] == "done" and len(live) == 2

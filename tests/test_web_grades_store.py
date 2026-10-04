"""Accounts and report-card lines read from the database (spec 2026-10-03 §6)."""
from __future__ import annotations

from zoneinfo import ZoneInfo

from fridgesheet import grading, sources
from fridgesheet.web.stores import grades, students
from tests.web_fixtures import seed

TZ = ZoneInfo("America/New_York")


def _course(conn, short, source):
    return conn.execute("SELECT * FROM courses WHERE short_name = ? AND source = ?", (short, source)).fetchone()


def test_latest_subtotals_are_the_newest_set_in_hacs_order(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    subs = grades.latest_subtotals(conn, eng["id"])
    assert [(s["category"], s["earned"], s["possible"]) for s in subs] == [("Assignments", 28.0, 30.0), ("Daily", 16.0, 20.0)]
    assert grades.subtotal_history(conn, eng["id"]) == [subs]


def test_hac_rows_come_from_the_twin_course_too(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    rows = sorted(grades.hac_rows(conn, eng), key=lambda r: r["name"])
    assert [(r["name"], r["category"], r["score"], r["points"]) for r in rows] == [
        ("Participation", "Assignments", None, 10.0), ("Quiz 1", "Assignments", 28.0, 30.0)]


def test_the_hac_account_rebuilds_the_fixtures_average(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    s = students.by_key(conn, "Alex")
    a = grades.account_for(conn, eng, students.latest_grades(conn, s["id"]).get(eng["id"]))
    assert a.source == "hac" and a.basis == "subtotals" and a.match == "exact"
    assert (a.reported, a.earned, a.possible) == (88.0, 44.0, 50.0)
    assert [l.rows for l in a.lines] == [1, 0]


def test_the_canvas_account_carries_final_and_missing(tmp_path):
    conn = seed(tmp_path)
    sci = _course(conn, "Science 7", "canvas")
    s = students.by_key(conn, "Sam")
    a = grades.account_for(conn, sci, students.latest_grades(conn, s["id"]).get(sci["id"]))
    assert a.source == "canvas" and (a.reported, a.final, a.missing) == (85.0, 60.0, 1)


def test_report_card_is_one_line_per_class_official_first_with_the_scales_letter(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    lines = grades.report_card(conn, s, sources.DEFAULT, grading.TEN_POINT, TZ)
    by = {l.short_name: l for l in lines}
    assert sorted(by) == ["Algebra I", "Honors English 9"]
    eng = by["Honors English 9"]
    assert (eng.official, eng.official_source, eng.letter) == (88.0, "hac", "B")
    assert eng.course_id == _course(conn, "Honors English 9", "canvas")["id"]        # a paired class links the Canvas page
    assert eng.as_of == "9/11" and eng.account.source == "hac" and eng.other.source == "canvas"
    assert eng.how == ("rc.adds_up", {"earned": "44", "possible": "50"})
    alg = by["Algebra I"]
    assert (alg.official, alg.official_source, alg.letter) == (79.5, "hac", "C")
    assert alg.how == ("rc.no_breakdown", {"reported": "79.50"})                      # no subtotals, no HAC rows


def test_report_card_follows_the_familys_source_choice(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    prefs = sources.DEFAULT.with_default("canvas", "canvas")
    eng = next(l for l in grades.report_card(conn, s, prefs, grading.TEN_POINT, TZ) if l.short_name == "Honors English 9")
    assert (eng.official, eng.official_source, eng.letter) == (91.2, "canvas", "A")
    assert eng.account.source == "canvas"


def test_a_class_without_an_average_is_still_a_line(tmp_path):
    conn = seed(tmp_path)
    with conn:
        conn.execute("UPDATE grade_observations SET average = NULL WHERE course_id = ?", (_course(conn, "Algebra I", "hac")["id"],))
        conn.execute("UPDATE grade_observations SET current = NULL WHERE course_id = ?", (_course(conn, "Algebra I", "canvas")["id"],))
    s = students.by_key(conn, "Alex")
    alg = next(l for l in grades.report_card(conn, s, sources.DEFAULT, grading.TEN_POINT, TZ) if l.short_name == "Algebra I")
    assert (alg.official, alg.letter, alg.how) == (None, "", ("rc.no_grade", {}))


def test_a_hidden_canvas_only_course_is_a_line_that_says_so(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Sam")
    with conn:
        rid = conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('2026-09-15T14:00:00-04:00', '{}', 1)").lastrowid
        cid = conn.execute("INSERT INTO courses(student_id, source, name, short_name) VALUES (?, 'canvas', 'Technology 7-2027-Dunn', 'Technology 7')", (s["id"],)).lastrowid
        conn.execute("INSERT INTO grade_observations(refresh_id, course_id, average, letter, current, final, last_updated) VALUES (?, ?, NULL, NULL, NULL, NULL, NULL)", (rid, cid))
    tech = next(l for l in grades.report_card(conn, s, sources.DEFAULT, grading.TEN_POINT, TZ) if l.short_name == "Technology 7")
    assert tech.official is None and tech.how == ("rc.canvas_hidden", {})


def test_how_for_picks_the_sentence_in_the_specs_order():
    sub = [{"category": "A", "earned": 50.0, "possible": 100.0, "percent": ""}]
    assert grades.how_for(None) == ("rc.no_grade", {})
    assert grades.how_for(grading.account_hac(None, sub, [])) == ("rc.no_grade", {})
    canvas = grading.account_canvas(84.42, 68.94, False, [{"group": "A", "score": 84.42, "points": 100.0, "excused": False, "missing": True, "state": "unsubmitted"}])
    assert grades.how_for(canvas) == ("rc.canvas_partial", {"current": "84.42", "final": "68.94", "missing": "1"})
    whole = grading.account_canvas(91.2, 91.2, False, [])
    assert grades.how_for(whole) == ("rc.canvas_current", {"current": "91.20"})         # Canvas's how is what it counts, never HAC's words
    zeros = grading.account_hac(50.0, sub, [{"category": "A", "score": 50.0, "points": 75.0, "excused": False}, {"category": "A", "score": None, "points": 25.0, "excused": False}])
    assert grades.how_for(zeros) == ("rc.adds_up_zeros", {"earned": "50", "possible": "100", "zero_points": "25"})
    off_rows = grading.account_hac(86.57, [], [{"category": "A", "score": 74.0, "points": 82.0, "excused": False}])
    assert grades.how_for(off_rows) == ("rc.rows_dont_add_up", {"rebuilt": "90.24", "reported": "86.57", "rows": "1"})
    off = grading.account_hac(79.0, sub, [])
    assert grades.how_for(off) == ("rc.dont_add_up", {"rebuilt": "50.00", "reported": "79.00"})


def test_canvas_with_a_lower_final_but_nothing_marked_missing_says_unsubmitted_not_zero_missing():
    a = grading.account_canvas(84.42, 68.94, False, [{"group": "A", "score": 84.42, "points": 100.0, "excused": False, "missing": False, "state": "graded"}])
    assert grades.how_for(a) == ("rc.canvas_partial_unsubmitted", {"current": "84.42", "final": "68.94"})


def test_the_account_reads_stored_weights_and_says_so(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    with conn:
        conn.execute("UPDATE category_observations SET weight = CASE category WHEN 'Assignments' THEN 3 ELSE 2 END WHERE course_id = ?", (eng["id"],))
    s = students.by_key(conn, "Alex")
    a = grades.account_for(conn, eng, students.latest_grades(conn, s["id"]).get(eng["id"]))
    assert a.basis == "weighted" and a.match == "exact" and round(a.rebuilt, 2) == 88.0     # (93.33*3 + 80*2)/5
    assert grades.how_for(a) == ("rc.adds_up_weighted", {"n": "2"})


def test_as_of_reads_the_same_shape_for_either_gradebook(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    eng = next(l for l in grades.report_card(conn, s, sources.DEFAULT.with_default("canvas", "canvas"), grading.TEN_POINT, TZ) if l.short_name == "Honors English 9")
    assert eng.official_source == "canvas" and eng.as_of == "9/15"                  # like HAC's "9/11": no weekday


def test_a_stale_hac_score_without_a_hac_label_does_not_feed_the_account(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    s = students.by_key(conn, "Alex")
    with conn:
        rid = conn.execute("SELECT MAX(id) FROM refreshes").fetchone()[0]
        iid = conn.execute("INSERT INTO items(student_id, course_id, key, name, points, first_seen, last_seen) VALUES (?, ?, 'hac:old', 'Old quiz', 10, 1, 1)",
                           (s["id"], eng["id"])).lastrowid
        conn.execute("INSERT INTO item_observations(refresh_id, item_id, source, state, score) VALUES (?, ?, 'hac', 'graded', 10)", (rid, iid))
    a = grades.account_for(conn, eng, students.latest_grades(conn, s["id"]).get(eng["id"]))
    assert a.match == "exact" and [l.category for l in a.lines] == ["Assignments", "Daily"]

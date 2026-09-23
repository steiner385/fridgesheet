"""The item list every page reads: sources, openness, actionability, status words, filters, counts."""
from __future__ import annotations

from datetime import timedelta

from fridgesheet import late_rules
from fridgesheet.web import reconcile
from fridgesheet.web.stores import flags, items, notes, students
from tests.web_fixtures import NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _doug(conn):
    return students.by_key(conn, "Alex")


def _by_name(views):
    return {v.name: v for v in views}


def test_all_items_carry_sources_status_and_flags(tmp_path):
    conn = seed(tmp_path)
    v = _by_name(items.list_items(conn, _doug(conn), now=NOW, rules=RULES, show="all"))
    assert set(v) == {"Quiz 1", "Essay draft", "Reading log", "Worksheet 3", "Vocabulary", "Lab notebook", "Participation", "Homework 4"}
    # Canvas's automatic MISSING loses to HAC's 28/30 recorded in the same refresh (docs/outcomes.md).
    assert v["Quiz 1"].sources == ("canvas", "hac") and v["Quiz 1"].open_in == set() and not v["Quiz 1"].actionable
    assert v["Quiz 1"].outcome == "done_offline"
    assert v["Quiz 1"].status == "Missing" and v["Quiz 1"].hac["score"] == 28.0 and v["Quiz 1"].verdict.kind == "graded_in_hac"
    assert v["Essay draft"].status == "Submitted, ungraded" and not v["Essay draft"].open_in and v["Essay draft"].verdict.kind == "teacher_grading"
    assert v["Vocabulary"].status == "Due today" and v["Worksheet 3"].status == "Due tomorrow" and v["Reading log"].status == "Due Sun"
    assert v["Lab notebook"].kind == "paper" and v["Lab notebook"].status == "Paper, check" and v["Lab notebook"].verdict.kind == "awaiting_grade"
    assert v["Participation"].sources == ("hac",) and v["Participation"].status == "HAC, no grade" and v["Participation"].verdict.kind == "still_ungraded"
    assert v["Homework 4"].open_in == {"canvas"} and not v["Homework 4"].actionable and v["Homework 4"].verdict.kind == "past_credit"
    assert v["Quiz 1"].course_short == "Honors English 9" and v["Quiz 1"].due.date().isoformat() == "2026-09-12"


def test_show_open_actionable_and_all(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    names = lambda **kw: sorted(v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, **kw))
    assert names(show="open") == ["Homework 4", "Lab notebook", "Participation", "Reading log", "Vocabulary", "Worksheet 3"]
    assert names(show="actionable") == ["Lab notebook", "Participation"]
    assert len(names(show="all")) == 8
    flags.set_flag(conn, v_id(conn, "Lab notebook"), "done", now="2026-09-15T14:30:00-04:00")
    assert "Lab notebook" not in names(show="open") and "Lab notebook" not in names(show="actionable")
    assert "Lab notebook" in names(show="all") and _by_name(items.list_items(conn, d, now=NOW, rules=RULES, show="all"))["Lab notebook"].flag == "done"


def v_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_source_course_kind_and_flag_filters(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    names = lambda **kw: sorted(v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", **kw))
    assert names(source="hac") == ["Participation", "Quiz 1"]
    assert names(source="canvas") == ["Essay draft", "Homework 4", "Lab notebook", "Quiz 1", "Reading log", "Vocabulary", "Worksheet 3"]
    assert names(source="both") == ["Quiz 1"]
    alg = [c for c in students.courses(conn, d["id"]) if c["source"] == "canvas" and c["short_name"] == "Algebra I"][0]
    assert names(course_id=alg["id"]) == ["Homework 4"]
    assert names(kind="paper") == ["Lab notebook"]
    flags.set_flag(conn, v_id(conn, "Essay draft"), "ask_teacher", now="2026-09-15T14:30:00-04:00", text="emailed 9/15")
    flags.set_flag(conn, v_id(conn, "Homework 4"), "ignore", now="2026-09-15T14:31:00-04:00")
    assert names(flagged="any") == ["Essay draft", "Homework 4"]
    assert names(flagged="marked") == ["Essay draft"] and names(flagged="handled") == ["Homework 4"]
    assert "Essay draft" not in names(flagged="none")
    assert _by_name(items.list_items(conn, d, now=NOW, rules=RULES, show="all"))["Essay draft"].flag_text == "emailed 9/15"


def test_sorts(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    by_due = [v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", sort="due")]
    assert by_due[:2] == ["Homework 4", "Participation"] and by_due[-1] == "Reading log"
    by_course = [v.course_short for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", sort="course")]
    assert by_course == sorted(by_course)
    by_name = [v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", sort="name")]
    assert by_name == sorted(by_name, key=str.lower)


def test_note_counts_and_one(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    qid = v_id(conn, "Quiz 1")
    notes.add(conn, "item", qid, "Teacher says the HAC score is right", now="2026-09-15T14:30:00-04:00")
    one = items.one(conn, d, qid, now=NOW, rules=RULES)
    assert one is not None and one.notes == 1 and one.name == "Quiz 1"
    assert items.one(conn, d, 99999, now=NOW, rules=RULES) is None
    sam = students.by_key(conn, "Sam")
    assert items.one(conn, sam, qid, now=NOW, rules=RULES) is None       # another kid's item is not this kid's


def test_dashboard_counts(tmp_path):
    conn = seed(tmp_path)
    c = items.dashboard_counts(conn, _doug(conn), now=NOW, rules=RULES)
    assert (c.fixable, c.due_today, c.due_tomorrow, c.new_since_yesterday) == (2, 1, 1, 8)       # Quiz 1 is done on paper (HAC 28/30)
    k = items.dashboard_counts(conn, students.by_key(conn, "Sam"), now=NOW, rules=RULES)
    assert (k.fixable, k.due_today, k.due_tomorrow, k.new_since_yesterday) == (2, 0, 0, 2)
    later = items.dashboard_counts(conn, _doug(conn), now=NOW + timedelta(days=3), rules=RULES)
    assert later.new_since_yesterday == 0


def test_live_items_is_public_and_upcoming_is_bounded(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    rows = {r["name"]: r for r in reconcile.live_items(conn, d["id"], NOW)}
    obs = reconcile.db.latest_observations(conn, d["id"])
    assert reconcile.upcoming(rows["Reading log"], obs[rows["Reading log"]["id"]], NOW)
    assert not reconcile.upcoming(rows["Reading log"], obs[rows["Reading log"]["id"]], NOW, days_ahead=3)
    assert not reconcile.upcoming(rows["Quiz 1"], obs[rows["Quiz 1"]["id"]], NOW)       # past due is open, not upcoming


def test_each_seeded_item_carries_the_expected_verdict(tmp_path):
    """The household in tests/web_fixtures.py, at its frozen clock (Tue 9/15 2 PM)."""
    conn = seed(tmp_path)
    views = {v.name: v.verdict for v in items.list_items(conn, _doug(conn), now=NOW, rules=RULES, show="all")}
    assert (views["Quiz 1"].state, views["Quiz 1"].kind) == ("decided", "graded_in_hac")
    assert (views["Participation"].state, views["Participation"].kind) == ("question", "still_ungraded")
    assert (views["Lab notebook"].state, views["Lab notebook"].kind) == ("waiting", "awaiting_grade")
    assert (views["Essay draft"].state, views["Essay draft"].kind) == ("waiting", "teacher_grading")
    assert (views["Homework 4"].state, views["Homework 4"].kind) == ("status", "past_credit")


def test_views_carry_as_of_times_and_the_teacher_email(tmp_path):
    conn = seed(tmp_path)
    quiz = next(v for v in items.list_items(conn, _doug(conn), now=NOW, rules=RULES, show="all") if v.name == "Quiz 1")
    started = conn.execute("SELECT started_at FROM refreshes ORDER BY id DESC LIMIT 1").fetchone()["started_at"]
    assert quiz.canvas_as_of == started and quiz.hac_as_of == started
    assert quiz.teacher_email == "hoch@example.org"


def test_near_twins_lists_a_missed_pairing_and_not_unrelated_work(tmp_path):
    from tests.web_fixtures import snapshot
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    eng["assignments"].append(dict(eng["assignments"][-1], id=83, name="Participation grade",
                                   due_at="2026-09-09T23:59:00-04:00", submission_types=["none"]))
    conn = seed(tmp_path, snap)
    views = items.list_items(conn, _doug(conn), now=NOW, rules=RULES, show="all")
    pairs = {(c.name, h.name) for c, h in items.near_twins(conn, views)}
    assert ("Participation grade", "Participation") in pairs
    assert not any(c == "Lab notebook" for c, _ in pairs)

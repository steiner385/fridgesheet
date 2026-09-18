"""The item list every page reads: sources, openness, actionability, status words, filters, counts."""
from __future__ import annotations

from datetime import timedelta

from lakota_grades import late_rules
from lakota_grades.web import reconcile
from lakota_grades.web.stores import flags, items, notes, students
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
    assert v["Quiz 1"].sources == ("canvas", "hac") and v["Quiz 1"].open_in == {"canvas"} and v["Quiz 1"].actionable
    assert v["Quiz 1"].status == "Missing" and v["Quiz 1"].hac["score"] == 28.0 and v["Quiz 1"].case_kinds == ["disagree"]
    assert v["Essay draft"].status == "Submitted, ungraded" and not v["Essay draft"].open_in and v["Essay draft"].case_kinds == ["submitted_ungraded"]
    assert v["Vocabulary"].status == "Due today" and v["Worksheet 3"].status == "Due tomorrow" and v["Reading log"].status == "Due Sun"
    assert v["Lab notebook"].kind == "paper" and v["Lab notebook"].status == "Paper, check" and "paper_no_grade" in v["Lab notebook"].case_kinds
    assert v["Participation"].sources == ("hac",) and v["Participation"].status == "HAC, no grade" and v["Participation"].case_kinds == ["one_source"]
    assert v["Homework 4"].open_in == {"canvas"} and not v["Homework 4"].actionable and "past_credit" in v["Homework 4"].case_kinds
    assert v["Homework 4"].case_kinds == ["one_source", "past_credit"]     # Algebra's HAC twin has no row for it (rule 2) and credit closed (rule 5)
    assert v["Quiz 1"].course_short == "Honors English 9" and v["Quiz 1"].due.date().isoformat() == "2026-09-12"


def test_show_open_actionable_and_all(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    names = lambda **kw: sorted(v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, **kw))
    assert names(show="open") == ["Homework 4", "Lab notebook", "Participation", "Quiz 1", "Reading log", "Vocabulary", "Worksheet 3"]
    assert names(show="actionable") == ["Lab notebook", "Participation", "Quiz 1"]
    assert len(names(show="all")) == 8
    flags.set_flag(conn, v_id(conn, "Quiz 1"), "done", now="2026-09-15T14:30:00-04:00")
    assert "Quiz 1" not in names(show="open") and "Quiz 1" not in names(show="actionable")
    assert "Quiz 1" in names(show="all") and _by_name(items.list_items(conn, d, now=NOW, rules=RULES, show="all"))["Quiz 1"].flag == "done"


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
    assert (c.actionable, c.due_today, c.due_tomorrow, c.new_since_yesterday) == (3, 1, 1, 8)
    k = items.dashboard_counts(conn, students.by_key(conn, "Sam"), now=NOW, rules=RULES)
    assert (k.actionable, k.due_today, k.due_tomorrow, k.new_since_yesterday) == (2, 0, 0, 2)
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

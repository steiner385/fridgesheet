"""Assignment types in the database (spec 2026-10-04 assignment types §5): schema 14, the
online-quiz bit at ingest, corrections and rules carried and read."""
from __future__ import annotations

from fridgesheet import late_rules
from fridgesheet.web import db
from fridgesheet.web.stores import items, students, work_types as type_store
from web_fixtures import NOW, seed, snapshot


def _items(conn):
    return {r["name"]: r for r in conn.execute("SELECT * FROM items")}


def test_schema_14_adds_the_two_tables_and_the_column(tmp_path):
    conn = db.open_db(tmp_path)
    assert db.SCHEMA_VERSION == 14 and db.migrate(conn) == 14
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert "online_quiz" in cols
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"item_types", "type_rules"} <= tables


def test_the_v14_migration_runs_again_on_a_file_rolled_back_to_13(tmp_path):
    conn = db.open_db(tmp_path)
    conn.execute("UPDATE schema_version SET version = 13")
    assert db.migrate(conn) == 14                       # column and tables already there: no error


def test_ingest_records_canvas_online_quizzes(tmp_path):
    snap = snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"][0]["submission_types"] = ["online_quiz"]
    conn = seed(tmp_path, snap)
    rows = _items(conn)
    assert rows["Quiz 1"]["online_quiz"] == 1
    assert rows["Essay draft"]["online_quiz"] == 0


def test_folding_items_carries_the_correction_and_online_quiz(tmp_path):
    conn = seed(tmp_path)
    a, b = [r["id"] for r in conn.execute("SELECT id FROM items ORDER BY id LIMIT 2")]
    with conn:
        conn.execute("UPDATE items SET online_quiz = 1 WHERE id = ?", (a,))
        conn.execute("INSERT INTO item_types(item_id, family, set_at) VALUES (?, 'lab_project', 't')", (a,))
        db._fold_item(conn, a, into=b)
    assert conn.execute("SELECT family FROM item_types WHERE item_id = ?", (b,)).fetchone()["family"] == "lab_project"
    assert conn.execute("SELECT COUNT(*) FROM item_types WHERE item_id = ?", (a,)).fetchone()[0] == 0
    assert conn.execute("SELECT online_quiz FROM items WHERE id = ?", (b,)).fetchone()[0] == 1


def test_folding_keeps_the_survivors_own_correction(tmp_path):
    conn = seed(tmp_path)
    a, b = [r["id"] for r in conn.execute("SELECT id FROM items ORDER BY id LIMIT 2")]
    with conn:
        conn.execute("INSERT INTO item_types(item_id, family, set_at) VALUES (?, 'lab_project', 't1')", (a,))
        conn.execute("INSERT INTO item_types(item_id, family, set_at) VALUES (?, 'assessment', 't2')", (b,))
        db._fold_item(conn, a, into=b)
    assert [r["family"] for r in conn.execute("SELECT family FROM item_types")] == ["assessment"]


# --- the store, and every view carrying its family (assignment types §6.1) --------------------
RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _views(conn, key="Alex"):
    s = students.by_key(conn, key)
    return {v.name: v for v in items.list_items(conn, s, now=NOW, rules=RULES, show="all")}


def _course(conn, name_like):
    return conn.execute("SELECT * FROM courses WHERE name LIKE ?", (f"%{name_like}%",)).fetchall()


def test_every_view_carries_a_family_and_the_rung_that_gave_it(tmp_path):
    snap = snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"][0]["submission_types"] = ["online_quiz"]
    conn = seed(tmp_path, snap)
    v = _views(conn)
    assert (v["Quiz 1"].family, v["Quiz 1"].family_rung) == ("assessment", 3)
    assert v["Quiz 1"].is_assessment
    assert (v["Essay draft"].family, v["Essay draft"].family_rung) == ("practice", 4)   # group "Homework"
    assert (v["Lab notebook"].family, v["Lab notebook"].family_rung) == ("practice", 4)  # group beats name
    assert v["Participation"].family == "participation"                               # HAC-only, by name


def test_a_correction_wins_and_clearing_it_restores_the_guess(tmp_path):
    conn = seed(tmp_path)
    iid = _views(conn)["Lab notebook"].id
    type_store.set_correction(conn, iid, "lab_project", "2026-10-04T10:00:00")
    assert (_views(conn)["Lab notebook"].family, _views(conn)["Lab notebook"].family_rung) == ("lab_project", 1)
    type_store.clear_correction(conn, iid)
    assert _views(conn)["Lab notebook"].family == "practice"


def test_a_rule_made_on_either_course_of_a_pair_applies_to_both(tmp_path):
    conn = seed(tmp_path)
    hac_course = [c for c in _course(conn, "English") if c["source"] == "hac"][0]
    type_store.add_rule(conn, hac_course["id"], "group", "Homework", "lab_project", "2026-10-04T10:00:00")
    v = _views(conn)
    assert (v["Essay draft"].family, v["Essay draft"].family_rung) == ("lab_project", 2)   # a Canvas item
    assert v["Homework 4"].family == "practice"                                          # Algebra: another class


def test_rule_reach_counts_the_items_a_rule_would_cover(tmp_path):
    conn = seed(tmp_path)
    sid = students.by_key(conn, "Alex")["id"]
    canvas_eng = [c for c in _course(conn, "English") if c["source"] == "canvas"][0]
    assert type_store.rule_reach(conn, sid, canvas_eng["id"], "group", "homework") == 6
    assert type_store.rule_reach(conn, sid, canvas_eng["id"], "name_prefix", "quiz") == 1


def test_add_rule_folds_the_value_and_replaces_its_own_family(tmp_path):
    conn = seed(tmp_path)
    cid = _course(conn, "English")[0]["id"]
    type_store.add_rule(conn, cid, "name_prefix", "  WS # ", "practice", "t1")
    type_store.add_rule(conn, cid, "name_prefix", "ws #", "assessment", "t2")
    rows = conn.execute("SELECT value, family FROM type_rules").fetchall()
    assert [(r["value"], r["family"]) for r in rows] == [("ws #", "assessment")]


def test_list_items_filters_by_family(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    shown = items.list_items(conn, s, now=NOW, rules=RULES, show="all", family="participation")
    assert [v.name for v in shown] == ["Participation"]
    every = items.list_items(conn, s, now=NOW, rules=RULES, show="all", family="nonsense")
    assert len(every) == len(_views(conn))

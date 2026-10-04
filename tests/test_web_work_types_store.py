"""Assignment types in the database (spec 2026-10-04 assignment types §5): schema 14, the
online-quiz bit at ingest, corrections and rules carried and read."""
from __future__ import annotations

from fridgesheet.web import db
from web_fixtures import seed, snapshot


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

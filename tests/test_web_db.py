"""The SQLite file: creation, pragmas, migration idempotence, and the schema's rules."""
from __future__ import annotations

import sqlite3

import pytest

from fridgesheet.web import db


def test_open_db_creates_file_and_schema(tmp_path):
    conn = db.open_db(tmp_path / "home")
    assert (tmp_path / "home" / "fridgesheet.db").is_file()
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == db.SCHEMA_VERSION
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"refreshes", "students", "courses", "items", "item_observations", "grade_observations",
            "notes", "flags", "reports", "schedules", "runs", "schema_version"} <= names


def test_migrate_is_idempotent(tmp_path):
    conn = db.open_db(tmp_path)
    assert db.migrate(conn) == db.SCHEMA_VERSION
    assert conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 1


def test_a_second_writer_waits_instead_of_failing_at_once(tmp_path):
    """Two processes share the file (the CLI runner and, in Plan B, the web worker), so a
    connection that finds the write lock held waits ten seconds rather than raising."""
    conn = db.open_db(tmp_path)
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS == 10000


def test_a_file_from_a_newer_build_is_refused_by_name(tmp_path):
    """Migrations only run forwards: an older build must not write into a newer schema."""
    conn = db.open_db(tmp_path)
    conn.execute("UPDATE schema_version SET version = ?", (db.SCHEMA_VERSION + 7,))
    with pytest.raises(RuntimeError) as e:
        db.migrate(conn)
    assert str(db.SCHEMA_VERSION + 7) in str(e.value) and str(db.SCHEMA_VERSION) in str(e.value)


def test_item_identity_is_student_and_course_as_well_as_key(tmp_path):
    """One key can belong to several items: two kids in like-named classes share
    `hac:<short course>:<name>`, and siblings in one section share `canvas:<id>`. Only the
    same key in the same course for the same kid is the same item."""
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        conn.executemany("INSERT INTO students(id, key, name) VALUES (?, ?, ?)", [(1, "Alex", "Alex S"), (2, "Sam", "Sam S")])
        conn.executemany("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (?, ?, 'hac', ?, 'Honors English 9')",
                         [(1, 1, "Honors English 9 - 1"), (2, 1, "Honors English 9 - 3"), (3, 2, "Honors English 9 - 1")])
        conn.executemany("INSERT INTO items(student_id, course_id, key, name, first_seen, last_seen) VALUES (?, ?, 'hac:Honors English 9:reading log', 'Reading log', 1, 1)",
                         [(1, 1), (1, 2), (2, 3)])       # two sections for one kid, and another kid
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 3
    with pytest.raises(sqlite3.IntegrityError):          # the same key twice in one course is one item
        with conn:
            conn.execute("INSERT INTO items(student_id, course_id, key, name, first_seen, last_seen) VALUES (1, 1, 'hac:Honors English 9:reading log', 'Reading log', 1, 1)")


def test_one_active_flag_per_item(tmp_path):
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Bio', 'Bio')")
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (1, 1, 1, 'canvas:1', 'WS', 1, 1)")
        conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (1, 'done', 't1')")
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (1, 'ignore', 't2')")
    with conn:
        conn.execute("UPDATE flags SET cleared_at = 't3' WHERE item_id = 1")
        conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (1, 'ignore', 't4')")   # allowed once cleared
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (1, 'bogus', 't5')")


def test_latest_observations_picks_the_newest_per_source(tmp_path):
    conn = db.open_db(tmp_path)
    with conn:
        conn.executemany("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (?, ?, '{}', 1)", [(1, "2026-09-10"), (2, "2026-09-11")])
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Bio', 'Bio')")
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (1, 1, 1, 'canvas:1', 'WS', 1, 2)")
        conn.executemany("INSERT INTO item_observations(refresh_id, item_id, source, state, score) VALUES (?, 1, ?, ?, ?)",
                         [(1, "canvas", "unsubmitted", None), (2, "canvas", "graded", 9.0), (1, "hac", "ungraded", None)])
    latest = db.latest_observations(conn, 1)
    assert latest[1]["canvas"]["state"] == "graded" and latest[1]["canvas"]["score"] == 9.0
    assert latest[1]["hac"]["state"] == "ungraded"
    assert db.latest_observations(conn, 999) == {}

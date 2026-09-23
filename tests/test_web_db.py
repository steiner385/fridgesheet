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


def test_flags_check_constraint_accepts_too_late(tmp_path):
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Bio', 'Bio')")
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (1, 1, 1, 'canvas:1', 'WS', 1, 1)")
        conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (1, 'too_late', 't1')")
    assert conn.execute("SELECT flag FROM flags WHERE item_id = 1").fetchone()[0] == "too_late"


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


# --- schema 1 -> 2: the check-in tables arrive; nothing already recorded moves ---------------

def _populated_v1(path):
    """A file exactly as a 0.4.x build left it: schema 1, one refresh of the standard household,
    a note, a flag and a printed run."""
    from fridgesheet.web.stores import flags, notes
    from tests.web_fixtures import NOW, TZ, snapshot
    from fridgesheet.web import ingest
    conn = db.connect(path)
    conn.executescript("BEGIN;\n" + db._SCHEMA_V1 + "\nINSERT INTO schema_version(version) VALUES (1);\nCOMMIT;")
    ingest.record(conn, snapshot(), tz=TZ, now=NOW)
    qid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()[0]
    notes.add(conn, "item", qid, "teacher said she would regrade", now=NOW.isoformat())
    flags.set_flag(conn, qid, "follow_up", now=NOW.isoformat(), text="ask Monday")
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message) VALUES (?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "2p Al=3 Sam=2"))
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("refreshes", "students", "courses", "items", "item_observations", "grade_observations", "notes", "flags", "runs")}
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 1
    conn.close()
    return qid, counts


def test_a_populated_schema_1_file_migrates_to_2_with_everything_still_in_it(tmp_path):
    qid, before = _populated_v1(db.db_path(tmp_path))
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == db.SCHEMA_VERSION
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"plan_steps", "checkins"} <= names
    after = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in before}
    assert after == before
    assert conn.execute("SELECT body FROM notes").fetchone()[0] == "teacher said she would regrade"
    flag = conn.execute("SELECT flag, text, cleared_at FROM flags WHERE item_id = ?", (qid,)).fetchone()
    assert (flag["flag"], flag["text"], flag["cleared_at"]) == ("follow_up", "ask Monday", None)
    assert conn.execute("SELECT message FROM runs").fetchone()[0] == "2p Al=3 Sam=2"
    assert conn.execute("SELECT COUNT(*) FROM plan_steps").fetchone()[0] == 0
    # Running the migration again is a no-op, and the version row stays single.
    assert db.migrate(conn) == db.SCHEMA_VERSION
    assert [tuple(r) for r in conn.execute("SELECT version FROM schema_version")] == [(db.SCHEMA_VERSION,)]
    conn.close()
    # And a fresh connection -- the next request, the next process -- sees the migrated file
    # as it is, with nothing migrated twice and nothing lost (#2).
    again = db.open_db(tmp_path)
    assert again.execute("SELECT version FROM schema_version").fetchone()[0] == db.SCHEMA_VERSION
    assert again.execute("SELECT COUNT(*) FROM items").fetchone()[0] == before["items"]
    assert again.execute("SELECT body FROM notes").fetchone()[0] == "teacher said she would regrade"
    again.close()


def test_a_file_under_the_old_name_is_renamed_and_then_migrated_in_one_open(tmp_path):
    from fridgesheet.migrate import OLD_DB_NAME
    qid, before = _populated_v1(tmp_path / OLD_DB_NAME)
    conn = db.open_db(tmp_path)
    assert (tmp_path / "fridgesheet.db").is_file() and not (tmp_path / OLD_DB_NAME).exists()
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == db.SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == before["items"]
    assert conn.execute("SELECT flag FROM flags WHERE item_id = ? AND cleared_at IS NULL", (qid,)).fetchone()[0] == "follow_up"
    conn.close()


# --- schema 2 -> 3: "too late to submit" joins the flags a family can pick ------------------

def _populated_v2(path):
    """A file exactly as a 0.5.x build left it: schema 2, one refresh of the standard
    household, and an active flag that must survive the CHECK constraint's table rebuild."""
    from fridgesheet.web.stores import flags
    from tests.web_fixtures import NOW, TZ, snapshot
    from fridgesheet.web import ingest
    conn = db.connect(path)
    conn.executescript("BEGIN;\n" + db._SCHEMA_V1 + "\nINSERT INTO schema_version(version) VALUES (1);\nCOMMIT;")
    conn.executescript("BEGIN;\n" + db._SCHEMA_V2 + "\nUPDATE schema_version SET version = 2;\nCOMMIT;")
    ingest.record(conn, snapshot(), tz=TZ, now=NOW)
    qid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()[0]
    flags.set_flag(conn, qid, "excused", now=NOW.isoformat(), text="teacher excused it")
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 2
    conn.close()
    return qid


def test_a_populated_schema_2_file_migrates_to_3_and_too_late_becomes_a_legal_flag(tmp_path):
    qid = _populated_v2(db.db_path(tmp_path))
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == 3
    flag = conn.execute("SELECT flag, text, cleared_at FROM flags WHERE item_id = ?", (qid,)).fetchone()
    assert (flag["flag"], flag["text"], flag["cleared_at"]) == ("excused", "teacher excused it", None)
    with conn:
        conn.execute("UPDATE flags SET cleared_at = 't2' WHERE item_id = ?", (qid,))
        conn.execute("INSERT INTO flags(item_id, flag, set_at) VALUES (?, 'too_late', 't3')", (qid,))
    assert conn.execute("SELECT flag FROM flags WHERE item_id = ? AND cleared_at IS NULL", (qid,)).fetchone()[0] == "too_late"
    assert db.migrate(conn) == 3
    assert [tuple(r) for r in conn.execute("SELECT version FROM schema_version")] == [(3,)]
    conn.close()


def test_the_check_in_tables_enforce_their_rules(tmp_path):
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
    ok = ("INSERT INTO plan_steps(student_id, title, next_step, owner, planned_for, minutes, state, request_key, created_at, updated_at) "
          "VALUES (1, 'T', 'N', 'Alex', '2026-09-16', ?, ?, ?, 't', 't')")
    with conn:
        conn.execute(ok, (30, "planned", "k1"))
        conn.execute(ok, (None, "waiting", "k2"))                             # no estimate is allowed
    for minutes, state, key in ((0, "planned", "k3"), (1441, "planned", "k4"), (30, "someday", "k5"), (30, "planned", "k1")):
        with pytest.raises(sqlite3.IntegrityError):
            with conn:
                conn.execute(ok, (minutes, state, key))
    with pytest.raises(sqlite3.IntegrityError):                                # a step belongs to a real student
        with conn:
            conn.execute(ok.replace("VALUES (1,", "VALUES (9,"), (30, "planned", "k6"))
    with conn:
        conn.execute("INSERT INTO checkins(student_id, finished_at, next_check, available_minutes, plan, request_key) VALUES (1, 't', '2026-09-17', 40, '[]', 'c1')")
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("INSERT INTO checkins(student_id, finished_at, next_check, available_minutes, plan, request_key) VALUES (1, 't', '2026-09-17', 0, '[]', 'c2')")

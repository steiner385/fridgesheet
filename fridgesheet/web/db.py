"""The app's database: one SQLite file beside the JSON snapshot.

The snapshot stays the MCP server's input; this file is the app's memory: every refresh
as a change log, the parent's notes and flags, saved reports and run history. Schedules
are *not* here: `config.toml`'s `[reports.<key>]` holds them (see the `schedules` table
below, which nothing reads or writes). Schema changes are forward-only migrations, one
function per version.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_NAME = "fridgesheet.db"
SCHEMA_VERSION = 2
BUSY_TIMEOUT_MS = 10_000          # how long a writer waits for another process's write lock

_SCHEMA_V1 = """
CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE refreshes (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    sources TEXT NOT NULL,           -- JSON: {"canvas": "ok", "hac": "login_required: ..."}
    ok INTEGER NOT NULL
);
CREATE TABLE students (
    id INTEGER PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,        -- the snapshot's student key ("Alexander")
    name TEXT NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE courses (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    source TEXT NOT NULL CHECK (source IN ('canvas', 'hac')),
    external_id TEXT,                -- Canvas course id / HAC course code
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    teacher TEXT,
    teacher_email TEXT,
    peer_course_id INTEGER REFERENCES courses(id),   -- the other source's course for the same class
    hidden INTEGER NOT NULL DEFAULT 0,
    UNIQUE (student_id, source, name)
);
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    key TEXT NOT NULL,               -- canvas:<id> | hac:<short course>:<norm name>
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',   -- online | paper | in class | ''
    points REAL,
    due TEXT,
    assigned TEXT,
    is_assessment INTEGER NOT NULL DEFAULT 0,
    first_seen INTEGER NOT NULL REFERENCES refreshes(id),
    last_seen INTEGER NOT NULL REFERENCES refreshes(id),
    -- The key alone is not unique: two kids in like-named classes, or one kid in two
    -- sections of one course, share hac:<short course>:<norm name>, and siblings in one
    -- section share canvas:<id>. An item is identified by student and course as well.
    UNIQUE (student_id, course_id, key)
);
CREATE INDEX items_student ON items(student_id);
CREATE TABLE item_observations (
    id INTEGER PRIMARY KEY,
    refresh_id INTEGER NOT NULL REFERENCES refreshes(id),
    item_id INTEGER NOT NULL REFERENCES items(id),
    source TEXT NOT NULL CHECK (source IN ('canvas', 'hac')),
    state TEXT,                      -- canvas: unsubmitted|submitted|graded|pending_review ; hac: graded|ungraded
    score REAL,
    grade TEXT,
    submitted_at TEXT,
    late INTEGER,
    missing INTEGER,
    excused INTEGER,
    published INTEGER,               -- canvas: 0 when the teacher unpublished it; NULL for hac
    UNIQUE (refresh_id, item_id, source)
);
CREATE INDEX item_observations_item ON item_observations(item_id, source, refresh_id);
CREATE TABLE grade_observations (
    id INTEGER PRIMARY KEY,
    refresh_id INTEGER NOT NULL REFERENCES refreshes(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    average REAL,                    -- HAC marking-period average
    letter TEXT,
    current REAL,                    -- Canvas current_score
    final REAL,                      -- Canvas final_score
    last_updated TEXT,
    UNIQUE (refresh_id, course_id)
);
CREATE TABLE notes (
    id INTEGER PRIMARY KEY,
    target_type TEXT NOT NULL CHECK (target_type IN ('item', 'course', 'student')),
    target_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX notes_target ON notes(target_type, target_id);
CREATE TABLE flags (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    flag TEXT NOT NULL CHECK (flag IN ('done', 'excused', 'ignore', 'follow_up', 'ask_teacher')),
    text TEXT NOT NULL DEFAULT '',
    set_at TEXT NOT NULL,
    cleared_at TEXT
);
CREATE UNIQUE INDEX flags_one_active ON flags(item_id) WHERE cleared_at IS NULL;
CREATE TABLE reports (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    definition TEXT NOT NULL,        -- JSON, spec section 7
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
-- UNUSED. Nothing in this tree reads or writes this table: a report's schedule lives in
-- config.toml's [reports.<key>] (web/schedules.py), which is the authoritative copy -- the
-- scheduler's own units are generated from it, and a second declared home for the same six
-- fields is how two halves of one setting drift apart. Kept because dropping a table is a
-- schema migration, and this branch deliberately does not change the schema.
CREATE TABLE schedules (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL,        -- "open-work" or "view:<id>"
    days TEXT NOT NULL,              -- JSON list, e.g. ["Mon","Tue"]
    time TEXT NOT NULL,              -- HH:MM
    printer TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'print' CHECK (mode IN ('print', 'pdf')),
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE runs (
    id INTEGER PRIMARY KEY,
    report_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    trigger TEXT NOT NULL,           -- cli | schedule | web
    outcome TEXT NOT NULL,           -- OK | SKIP | FAIL
    message TEXT NOT NULL DEFAULT '',
    pdf_path TEXT,
    job_ref TEXT
);
CREATE INDEX runs_started ON runs(started_at);
"""


_SCHEMA_V2 = """
CREATE TABLE plan_steps (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    item_id INTEGER REFERENCES items(id),
    title TEXT NOT NULL,
    family_account TEXT NOT NULL DEFAULT '',
    next_step TEXT NOT NULL,
    owner TEXT NOT NULL,
    planned_for TEXT NOT NULL,
    minutes INTEGER CHECK (minutes IS NULL OR minutes BETWEEN 1 AND 1440),
    state TEXT NOT NULL CHECK (state IN ('planned', 'waiting', 'blocked', 'done')),
    position INTEGER NOT NULL DEFAULT 10,
    evidence TEXT NOT NULL DEFAULT '{}',
    request_key TEXT NOT NULL UNIQUE,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX plan_steps_student ON plan_steps(student_id, planned_for, position);
CREATE TABLE checkins (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    finished_at TEXT NOT NULL,
    next_check TEXT NOT NULL,
    available_minutes INTEGER NOT NULL CHECK (available_minutes BETWEEN 1 AND 1440),
    summary TEXT NOT NULL DEFAULT '',
    plan TEXT NOT NULL,
    request_key TEXT NOT NULL UNIQUE
);
CREATE INDEX checkins_student ON checkins(student_id, id);
"""


def db_path(home: Path) -> Path:
    return home / DB_NAME


def now_iso(tz) -> str:
    return datetime.now(tz).replace(microsecond=0).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    """One connection, autocommit, WAL, foreign keys on, and patient about other writers.

    The CLI runner and the web worker are separate processes over one file: WAL lets a
    reader work while a writer holds the lock, but two writers still serialise, so a
    busy connection waits up to ten seconds instead of failing the whole run at once.
    """
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn


def _version(conn: sqlite3.Connection) -> int:
    has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
    if not has:
        return 0
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Bring the file to SCHEMA_VERSION. Each migration runs in one transaction.

    A file written by a newer build is never touched: migrations are forward-only, so an
    older build cannot know what the newer one added and would silently write rows the
    newer schema rejects. The runner turns this into a WARN (and prints anyway), doctor
    into a FAIL, which is what a parent running two versions needs to see.
    """
    v = _version(conn)
    if v > SCHEMA_VERSION:
        raise RuntimeError(
            f"{DB_NAME} is at schema version {v}, but this build understands version {SCHEMA_VERSION}; "
            "upgrade fridgesheet (migrations only run forwards)")
    if v < 1:
        # executescript commits any pending transaction first, so the script carries its own
        # BEGIN/COMMIT to make the whole migration atomic.
        conn.executescript("BEGIN;\n" + _SCHEMA_V1 + "\nINSERT INTO schema_version(version) VALUES (1);\nCOMMIT;")
        v = 1
    if v < 2:
        conn.executescript("BEGIN;\n" + _SCHEMA_V2 + "\nUPDATE schema_version SET version = 2;\nCOMMIT;")
        v = 2
    return v


def open_db(home: Path) -> sqlite3.Connection:
    from ..migrate import migrate_db as _rename_old_file
    home.mkdir(parents=True, exist_ok=True)
    _rename_old_file(home, DB_NAME)          # lakota.db from before the rename, once
    conn = connect(db_path(home))
    migrate(conn)
    return conn


def latest_observations(conn: sqlite3.Connection, student_id: int) -> dict[int, dict[str, sqlite3.Row]]:
    """item id -> source -> the most recent observation row for that source."""
    rows = conn.execute(
        """SELECT o.* FROM item_observations o
           JOIN items i ON i.id = o.item_id
           WHERE i.student_id = ?
           ORDER BY o.item_id, o.source, o.refresh_id DESC, o.id DESC""",
        (student_id,),
    ).fetchall()
    out: dict[int, dict[str, sqlite3.Row]] = {}
    for r in rows:
        out.setdefault(r["item_id"], {}).setdefault(r["source"], r)   # first seen per (item, source) is the newest
    return out

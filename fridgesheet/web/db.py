"""The app's database: one SQLite file beside the JSON snapshot.

The snapshot stays the MCP server's input; this file is the app's memory: every refresh
as a change log, the parent's notes and flags, saved reports and run history. Schedules
are *not* here: `config.toml`'s `[reports.<key>]` and `[refresh]` hold them; `schedule_fires`
only remembers the last slot each one fired (see the `schedules` table below, which nothing
reads or writes). Schema changes are forward-only migrations, one function per version.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ..matching import hac_item_key, hac_only_key

DB_NAME = "fridgesheet.db"
SCHEMA_VERSION = 8
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
    created_by TEXT NOT NULL DEFAULT '',   -- who typed it in (free text: there is no login)
    recorded_by TEXT NOT NULL DEFAULT '',  -- who last saved it
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
    recorded_by TEXT NOT NULL DEFAULT '',
    request_key TEXT NOT NULL UNIQUE
);
CREATE INDEX checkins_student ON checkins(student_id, id);
"""


_SCHEMA_V3 = """
-- SQLite cannot ALTER a CHECK constraint, so the flag family (#104's "too late to submit")
-- means rebuilding the table: a new one with the wider constraint, the old rows copied over,
-- the old one dropped, the new one renamed into its place.
CREATE TABLE flags_v3 (
    id INTEGER PRIMARY KEY,
    item_id INTEGER NOT NULL REFERENCES items(id),
    flag TEXT NOT NULL CHECK (flag IN ('done', 'excused', 'ignore', 'follow_up', 'ask_teacher', 'too_late')),
    text TEXT NOT NULL DEFAULT '',
    set_at TEXT NOT NULL,
    cleared_at TEXT
);
INSERT INTO flags_v3 SELECT * FROM flags;
DROP TABLE flags;
ALTER TABLE flags_v3 RENAME TO flags;
CREATE UNIQUE INDEX flags_one_active ON flags(item_id) WHERE cleared_at IS NULL;
"""


_SCHEMA_V4 = """
-- Canvas's availability window and its "Locked" state. The dates are assignment attributes
-- like `due`; whether the kid can open it right now changes as those dates pass, so that
-- lives with the other per-refresh observations. lock_reason is one of closed | not_yet |
-- module | no_permission | other (see canvas._lock_reason); NULL when not locked or unknown.
ALTER TABLE items ADD COLUMN unlock_at TEXT;
ALTER TABLE items ADD COLUMN lock_at TEXT;
ALTER TABLE item_observations ADD COLUMN locked INTEGER;
ALTER TABLE item_observations ADD COLUMN lock_reason TEXT;
"""


_SCHEMA_V8 = """
-- The last slot each schedule fired, per schedule key (a report key, or "data-refresh").
-- An ISO datetime with its UTC offset. What stops a restart firing a slot twice, and what
-- lets a slot missed while the server was down be caught up once (web/clock.py).
CREATE TABLE schedule_fires (
    key TEXT PRIMARY KEY,
    slot TEXT NOT NULL
);
"""


def _migrate_v5(conn: sqlite3.Connection) -> None:
    """When the observation's missing mark, and its score, first appeared: the refresh that
    began the current run of each, carried forward across rewrites for other fields. An
    observation is rewritten whenever any field changes -- the availability window closing,
    say -- and its own refresh_id then read as "Canvas marked it missing after HAC's grade"
    (#131). NULL when not missing / no score. One transaction with the backfill, so the version
    only moves once every existing row carries them."""
    conn.execute("ALTER TABLE item_observations ADD COLUMN missing_since INTEGER REFERENCES refreshes(id)")
    conn.execute("ALTER TABLE item_observations ADD COLUMN scored_since INTEGER REFERENCES refreshes(id)")
    _backfill_since(conn)


_SCHEMA_V6 = """
-- Canvas classes this refresh could not pull, when one class fails on its own (#140): JSON
-- {"carried": [{kid, course_id, name, reason, fetched_at}], "missing": [{kid, course_id, reason}]}
-- as `collector.course_faults` lists them, NULL when every class answered. A carried class is
-- served from an older pull and its refresh still counts as good (`ok`); a missing one had
-- nothing older to serve. The header reads it to say so beside "Canvas OK".
ALTER TABLE refreshes ADD COLUMN carried TEXT;
"""


def since_fields(last: sqlite3.Row | None, refresh_id: int, missing, score) -> tuple[int | None, int | None]:
    """`missing_since` and `scored_since` for a new observation, given the one before it: the
    run continues when the mark is still set (the score still the same), else it starts here.
    Shared by ingest and the v5 backfill so an upgraded file reads as if it had always kept them."""
    missing_since = scored_since = None
    if missing:
        carried = last is not None and last["missing"]
        missing_since = (last["missing_since"] or last["refresh_id"]) if carried else refresh_id
    if score is not None:
        carried = last is not None and last["score"] == score
        scored_since = (last["scored_since"] or last["refresh_id"]) if carried else refresh_id
    return missing_since, scored_since


def _backfill_since(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT id, item_id, source, refresh_id, missing, score FROM item_observations "
                        "ORDER BY item_id, source, refresh_id, id").fetchall()
    last: dict[tuple[int, str], dict] = {}
    for r in rows:
        key = (r["item_id"], r["source"])
        missing_since, scored_since = since_fields(last.get(key), r["refresh_id"], r["missing"], r["score"])
        conn.execute("UPDATE item_observations SET missing_since = ?, scored_since = ? WHERE id = ?", (missing_since, scored_since, r["id"]))
        last[key] = {"refresh_id": r["refresh_id"], "missing": r["missing"], "score": r["score"],
                     "missing_since": missing_since, "scored_since": scored_since}


def _migrate_v7(conn: sqlite3.Connection) -> None:
    """Every HAC-only item's key carries its due date (`matching.hac_only_key`, #136).

    Up to v6 a lone HAC-only row was keyed `hac:<short course>:<norm name>` and only rows that
    shared a title got `:<YYYY-MM-DD>`, so the day a second "Participation" appeared the first
    was re-keyed: a new item, and the flag, notes and history left behind on the old one. Each
    bare key is rewritten with the item's own due date (`:unknown` without one; a key already
    dated, or not one this code made, is left alone). Where the re-key already happened, the
    dated twin the newer refreshes wrote is folded back onto the bare item that holds the
    parent's answers, so the next refresh upserts the row it was set on. One transaction with
    the version bump."""
    rows = conn.execute(
        """SELECT i.id, i.student_id, i.course_id, i.key, i.name, i.due, c.name AS course
           FROM items i JOIN courses c ON c.id = i.course_id WHERE i.key LIKE 'hac:%' ORDER BY i.id""").fetchall()
    for r in rows:
        if r["key"] != hac_item_key(r["course"], r["name"]):
            continue
        try:
            due = datetime.fromisoformat(r["due"]).date() if r["due"] else None
        except ValueError:
            due = None
        key = hac_only_key(r["course"], r["name"], due)
        twin = conn.execute("SELECT id FROM items WHERE student_id = ? AND course_id = ? AND key = ?",
                            (r["student_id"], r["course_id"], key)).fetchone()
        if twin is not None:
            _fold_item(conn, twin["id"], into=r["id"])
        conn.execute("UPDATE items SET key = ? WHERE id = ?", (key, r["id"]))


def _fold_item(conn: sqlite3.Connection, src: int, into: int) -> None:
    """Move everything that hangs off item `src` onto `into`, then delete `src`: the dated
    twin the pre-v7 re-key made for one HAC row, folded back onto the item the parent answered."""
    # The twin began in the refresh the bare row stopped being seen, so the two never share
    # an observation; one that would is dropped rather than doubled (unique per refresh, source).
    conn.execute(
        """UPDATE item_observations SET item_id = ? WHERE item_id = ? AND NOT EXISTS (
               SELECT 1 FROM item_observations o WHERE o.item_id = ?
               AND o.refresh_id = item_observations.refresh_id AND o.source = item_observations.source)""",
        (into, src, into))
    conn.execute("DELETE FROM item_observations WHERE item_id = ?", (src,))
    # One active flag per item: the twin's is the parent's later answer, so the older one is
    # closed off at the moment the newer was set.
    newer = conn.execute("SELECT set_at FROM flags WHERE item_id = ? AND cleared_at IS NULL", (src,)).fetchone()
    if newer is not None:
        conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (newer["set_at"], into))
    conn.execute("UPDATE flags SET item_id = ? WHERE item_id = ?", (into, src))
    conn.execute("UPDATE notes SET target_id = ? WHERE target_type = 'item' AND target_id = ?", (into, src))
    conn.execute("UPDATE plan_steps SET item_id = ? WHERE item_id = ?", (into, src))
    # The twin is the later sighting of the row: its attributes, and the span of both.
    t = conn.execute("SELECT * FROM items WHERE id = ?", (src,)).fetchone()
    conn.execute(
        """UPDATE items SET name = ?, kind = ?, points = ?, due = ?, assigned = COALESCE(?, assigned), is_assessment = ?,
           unlock_at = ?, lock_at = ?, first_seen = MIN(first_seen, ?), last_seen = MAX(last_seen, ?) WHERE id = ?""",
        (t["name"], t["kind"], t["points"], t["due"], t["assigned"], t["is_assessment"], t["unlock_at"], t["lock_at"],
         t["first_seen"], t["last_seen"], into))
    conn.execute("DELETE FROM items WHERE id = ?", (src,))


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


def household(home: Path) -> list[str]:
    """Every student's key, for the late rules' kid matching (`matching.kid_matches`): read-only,
    and empty when there is no database yet or it cannot be read -- rules still resolve then, a
    short name just cannot be told apart from a sibling's whole one."""
    path = db_path(home)
    if not path.is_file():
        return []
    try:
        conn = connect(path)
        try:
            return [r["key"] for r in conn.execute("SELECT key FROM students")]
        finally:
            conn.close()
    except sqlite3.Error:
        return []


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
    if v < 3:
        conn.executescript("BEGIN;\n" + _SCHEMA_V3 + "\nUPDATE schema_version SET version = 3;\nCOMMIT;")
        v = 3
    if v < 4:
        conn.executescript("BEGIN;\n" + _SCHEMA_V4 + "\nUPDATE schema_version SET version = 4;\nCOMMIT;")
        v = 4
    if v < 5:
        with conn:
            conn.execute("BEGIN")
            _migrate_v5(conn)
            conn.execute("UPDATE schema_version SET version = 5")
        v = 5
    if v < 6:
        conn.executescript("BEGIN;\n" + _SCHEMA_V6 + "\nUPDATE schema_version SET version = 6;\nCOMMIT;")
        v = 6
    if v < 7:
        with conn:
            conn.execute("BEGIN")
            _migrate_v7(conn)
            conn.execute("UPDATE schema_version SET version = 7")
        v = 7
    if v < 8:
        conn.executescript("BEGIN;\n" + _SCHEMA_V8 + "\nUPDATE schema_version SET version = 8;\nCOMMIT;")
        v = 8
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


def previous_observations(conn: sqlite3.Connection, student_id: int) -> dict[int, dict[str, sqlite3.Row]]:
    """item id -> source -> the observation before the latest one. Ingest writes a row only
    when something changed, so this is what the source said before its latest change."""
    rows = conn.execute(
        """SELECT o.* FROM item_observations o
           JOIN items i ON i.id = o.item_id
           WHERE i.student_id = ?
           ORDER BY o.item_id, o.source, o.refresh_id DESC, o.id DESC""",
        (student_id,),
    ).fetchall()
    seen: dict[tuple[int, str], int] = {}
    out: dict[int, dict[str, sqlite3.Row]] = {}
    for r in rows:
        k = (r["item_id"], r["source"])
        seen[k] = seen.get(k, 0) + 1
        if seen[k] == 2:
            out.setdefault(r["item_id"], {})[r["source"]] = r
    return out

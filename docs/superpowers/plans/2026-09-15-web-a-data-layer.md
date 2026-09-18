# Web App Plan A: Data Layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app a database that remembers every refresh as a change log, holds the parent's notes and flags, and lets flags change what the printed sheet says, with the reconciliation rules that define "actionable" written as tested pure functions. No UI in this plan.

**Architecture:** A single SQLite file `<home>/lakota.db` (standard library `sqlite3`, WAL, forward-only migrations) beside the existing JSON snapshot, which stays for the MCP server. `web/ingest.py` turns a snapshot into rows and writes an observation only when a source's view of an item changed. `web/stores/` holds the notes and flags stores; `web/reconcile.py` holds the rules. `open_items` learns about flags; the CLI runner ingests after each refresh, loads flags before building, and records every run.

**Tech Stack:** Python 3.12, `sqlite3` (stdlib), the existing `matching`, `open_items`, `late_rules`, `runner`, `reports` and `doctor` modules. No new third-party dependencies in this plan.

**Spec:** `docs/superpowers/specs/2026-09-15-lakota-web-app-design.md`, sections 4 (data), 6 (reconciliation), 9 (the CLI writes `runs`), 13 (Plan A), 15 (risk 1). GitHub milestone "Web app A: Data layer", issues #5 to #11; each task names its issue and closes it in the commit message.

## Global Constraints

- Database file: `<home>/lakota.db`; `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`; a `schema_version` table; migrations are forward-only functions in `web/db.py`, one per version.
- Times are stored as ISO-8601 strings. Canvas times keep their timezone offset as given by the snapshot; HAC dates (`mm/dd/yyyy`) become `YYYY-MM-DDT23:59:00` plus the settings time zone offset, matching `open_items._parse_hac_date`.
- Item keys are stable across refreshes: Canvas `canvas:<assignment id>`; HAC-only `hac:<short course>:<normalised name>` where the course goes through `matching.short_course` and the name through `matching.norm_name`. A HAC row that `matching.same_item` links to a Canvas assignment in the matched course attaches to that Canvas item as a second source rather than becoming its own item.
- `item_observations` and `grade_observations` are written only when the observed values differ from the previous observation for that item/course and source. A refresh that changes nothing adds a `refreshes` row and nothing else.
- Flags: exactly one active flag per item (`cleared_at IS NULL`); values `done`, `excused`, `ignore`, `follow_up`, `ask_teacher`. `done`/`excused`/`ignore` remove the item from the open list into a `handled` count on the sheet; `follow_up`/`ask_teacher` print a marker in the status column.
- The CLI runner must keep working when the database cannot be opened or written: ingest and run recording failures are `WARN` log lines, never a failed run.
- No credential is ever stored in the database. No CLI commands for notes or flags in this plan.
- Existing behaviour survives: the full suite (`env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`, 194 passed, 1 skipped at the start of this plan) stays green on Linux and in CI on both runners.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Closes #<issue>` on its own line.

## Snapshot shape (what ingest reads)

```
snapshot = {
  "fetched_at": "2026-09-15T06:02:11-04:00", "fetched_at_epoch": 1789...,
  "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
  "students": {
    "Alex": {                                  # key: first name as the collector chose it
      "name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
      "canvas": {"courses": [
        {"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "...",
         "grade": {"current_score": 91.2, "final_score": null, "current_grade": "A-", "hidden": false},
         "staff": [{"name": "Michael Hoch", "email": null, "roles": ["TeacherEnrollment"]}],
         "assignments": [
           {"id": 77, "name": "Quiz 1", "due_at": "2026-09-12T23:59:00-04:00", "unlock_at": null, "created_at": "...",
            "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "group_weight": null,
            "published": true, "score": null, "grade": null, "state": "unsubmitted", "late": false, "missing": true,
            "excused": false, "submitted_at": null, "seconds_late": 0}]}]},
      "hac": {"week_view": [...], "classes": [
        {"code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 75.67, "last_updated": "9/11/2026",
         "assignments": [{"due": "09/11/2026", "assigned": "09/11/2026", "name": "Quiz 1", "category": "Assignments",
                          "score": 28.0, "score_raw": "28.00", "points": 30.0, "percent": "93.33%"}],
         "categories": [...]}]}}}}
```

## File map

| Path | Responsibility |
|---|---|
| `scripts/hac_key_spike.py` (new) | Task 1 throwaway: key stability over the real snapshot and the real `sheets/*/rows.json` |
| `lakota_grades/web/__init__.py` (new) | package docstring |
| `lakota_grades/web/db.py` (new) | `db_path`, `connect`, `migrate`, `open_db`, `latest_observations`, `SCHEMA_VERSION` |
| `lakota_grades/web/ingest.py` (new) | `record(conn, snapshot, *, tz, now) -> IngestResult`, key helpers |
| `lakota_grades/web/stores/__init__.py`, `notes.py`, `flags.py` (new) | notes and flags stores |
| `lakota_grades/web/reconcile.py` (new) | `is_actionable`, `cases` |
| `lakota_grades/open_items.py` (modify) | `flags` argument; `OpenWork.handled`; markers |
| `lakota_grades/reports/base.py`, `reports/open_work.py` (modify) | `BuildContext.flags`; pass to `open_items` |
| `lakota_grades/sheet.py` (modify) | "Handled" trailer line |
| `lakota_grades/runner.py` (modify) | ingest after refresh, load flags, record runs; `RunOptions.trigger` |
| `lakota_grades/doctor.py` (modify) | `database` probe |
| `tests/test_web_db.py`, `test_web_ingest.py`, `test_web_stores.py`, `test_reconcile.py` (new); `tests/test_open_items.py`, `test_print_sheet.py`, `test_runner.py`, `test_doctor.py` (modify) | |

---

### Task 1: Spike, stable HAC keys over real data (issue #5)

The spec's first risk. HAC rows have no ids; the key must survive a teacher editing punctuation and must not collide across courses. Real data lives only on Tony's machine (`~/.lakota-grades`), so this script runs there, by hand, and its findings are recorded in this plan. The script is kept under `scripts/` because it is the tool for re-checking after any change to `matching`.

**Files:**
- Create: `scripts/hac_key_spike.py`
- Modify: this plan (Step 4 records the outcome)

**Interfaces:**
- Produces: the decision on `item_key_hac` (Task 3 uses `f"hac:{short_course(course)}:{norm_name(name)}"` unless this spike says otherwise) and a count of HAC rows that link to Canvas items versus stay HAC-only.

- [ ] **Step 1: Write the script**

```python
# scripts/hac_key_spike.py
"""Throwaway check for spec risk 15.1: are HAC item keys stable, and do HAC rows link
to their Canvas twins? Reads the real ~/.lakota-grades (or LAKOTA_GRADES_HOME) and
prints a report. Nothing is written.

Run:  env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python scripts/hac_key_spike.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lakota_grades.matching import match_course, norm_name, same_item, short_course  # noqa: E402

home = Path(os.environ.get("LAKOTA_GRADES_HOME") or Path.home() / ".lakota-grades")
snap = json.loads((home / "cache" / "snapshot.json").read_text())


def hac_key(course: str, name: str) -> str:
    return f"hac:{short_course(course)}:{norm_name(name)}"


linked = hac_only = 0
collisions: Counter[str] = Counter()
for kid, entry in snap["students"].items():
    canvas = {c["name"]: c for c in (entry.get("canvas") or {}).get("courses") or []}
    for h in (entry.get("hac") or {}).get("classes") or []:
        peer = match_course(h["name"], canvas)
        peer_names = [a["name"] for a in (peer or {}).get("assignments", [])]
        for row in h.get("assignments", []):
            if any(same_item(row["name"], n) for n in peer_names):
                linked += 1
            else:
                hac_only += 1
                collisions[f"{kid}|{hac_key(h['name'], row['name'])}"] += 1
dupes = {k: n for k, n in collisions.items() if n > 1}
print(f"HAC rows: {linked} linked to a Canvas assignment, {hac_only} HAC-only, {len(dupes)} duplicate HAC-only keys")
for k in list(dupes)[:10]:
    print("  duplicate:", k)

# Stability: do the HAC keys the sheet used on earlier days still resolve to the same rows today?
today_keys = {f"{kid}|{hac_key(h['name'], r['name'])}" for kid, e in snap["students"].items()
              for h in (e.get("hac") or {}).get("classes") or [] for r in h.get("assignments", [])}
for day in sorted((home / "sheets").glob("*/rows.json")):
    rows = json.loads(day.read_text())
    hac_rows = [(kid, r) for kid, items in rows.items() for r in items if r["key"].startswith("hac:")]
    seen = sum(1 for kid, r in hac_rows if f"{kid}|hac:{r['course']}:{norm_name(r['name'])}" in today_keys)
    print(f"{day.parent.name}: {len(hac_rows)} HAC rows on that sheet, {seen} still present under the same key today")
```

- [ ] **Step 2: Run it on the real data**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python scripts/hac_key_spike.py`
Expected: a "HAC rows:" line with zero duplicate keys, and one line per `sheets/<date>` showing how many earlier HAC rows are still present. A duplicate key means two different rows normalise to the same name in one course; if any appear, print both raw names and decide whether to add the due date to the key (record the decision in Step 4).

- [ ] **Step 3: Commit the script**

```bash
git add scripts/hac_key_spike.py
git commit -m "Spike: HAC item key stability over real snapshot and sheet history

Closes #5

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 4: Record the outcome here**

Run against the real `~/.lakota-grades` (three kids, real courses; nothing written) on 2026-09-15:

```
HAC rows: 99 linked to a Canvas assignment, 76 HAC-only, 1 duplicate HAC-only keys
  duplicate: <kid>|hac:<course>:<name>  (two rows, different due dates)
2026-09-11: 0 HAC rows on that sheet, 0 still present under the same key today
2026-09-12: 1 HAC rows on that sheet, 1 still present under the same key today
2026-09-14: 3 HAC rows on that sheet, 3 still present under the same key today
```

The one duplicate is a single student's single-course participation grade, which HAC lists twice under the same name, due dates two weeks apart, both graded — so the two rows are genuinely different assignments that happen to share a name, not the same row counted twice. Decision: keep the key as `hac:<short course>:<norm name>` for the 74 HAC-only rows that don't collide (99 linked, 76 HAC-only total, 2 of which share the one colliding key), and for rows that collide within one student's course append the due date, `hac:<short course>:<norm name>:<YYYY-MM-DD>`, which Task 3's `item_key_hac` should apply whenever a collision is detected. All HAC-only keys seen on the three earlier printed sheets still resolve to the same rows today, so the base key form is otherwise stable across refreshes.

---

### Task 2: `web/db.py`: the database and migration 1 (issue #6)

**Files:**
- Create: `lakota_grades/web/__init__.py`, `lakota_grades/web/db.py`
- Test: `tests/test_web_db.py`

**Interfaces:**
- Produces:
  - `db.SCHEMA_VERSION = 1`, `db.DB_NAME = "lakota.db"`, `db.db_path(home: Path) -> Path`
  - `db.connect(path: Path) -> sqlite3.Connection` (row factory `sqlite3.Row`, WAL, foreign keys on, `isolation_level=None` so callers manage transactions with explicit `BEGIN`/`COMMIT` via `with conn:`)
  - `db.migrate(conn) -> int` (returns the version now in place; idempotent)
  - `db.open_db(home: Path) -> sqlite3.Connection` (`connect` + `migrate`, creating the folder)
  - `db.latest_observations(conn, student_id: int) -> dict[int, dict[str, sqlite3.Row]]` (item id → source → the most recent `item_observations` row)
  - `db.now_iso(tz) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_db.py
"""The SQLite file: creation, pragmas, migration idempotence, and the schema's rules."""
from __future__ import annotations

import sqlite3

import pytest

from lakota_grades.web import db


def test_open_db_creates_file_and_schema(tmp_path):
    conn = db.open_db(tmp_path / "home")
    assert (tmp_path / "home" / "lakota.db").is_file()
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_web_db.py -q`
Expected: FAIL at import (`No module named 'lakota_grades.web'`).

- [ ] **Step 3: Write the package and `db.py`**

```python
# lakota_grades/web/__init__.py
"""The local web app (spec 2026-09-15). Plan A ships the data layer only: `db`, `ingest`,
`stores`, `reconcile`. The server, routes and templates arrive in Plan B."""
```

```python
# lakota_grades/web/db.py
"""The app's database: one SQLite file beside the JSON snapshot.

The snapshot stays the MCP server's input; this file is the app's memory: every refresh
as a change log, the parent's notes and flags, saved reports, schedules and run history.
Schema changes are forward-only migrations, one function per version.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_NAME = "lakota.db"
SCHEMA_VERSION = 1

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
    key TEXT NOT NULL UNIQUE,        -- the snapshot's student key ("Alex")
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
    peer_course_id INTEGER REFERENCES courses(id),   -- the other source's course for the same class
    hidden INTEGER NOT NULL DEFAULT 0,
    UNIQUE (student_id, source, name)
);
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    key TEXT NOT NULL UNIQUE,        -- canvas:<id> | hac:<short course>:<norm name>
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',   -- online | paper | in class | ''
    points REAL,
    due TEXT,
    assigned TEXT,
    is_assessment INTEGER NOT NULL DEFAULT 0,
    first_seen INTEGER NOT NULL REFERENCES refreshes(id),
    last_seen INTEGER NOT NULL REFERENCES refreshes(id)
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


def db_path(home: Path) -> Path:
    return home / DB_NAME


def now_iso(tz) -> str:
    return datetime.now(tz).replace(microsecond=0).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _version(conn: sqlite3.Connection) -> int:
    has = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'").fetchone()
    if not has:
        return 0
    row = conn.execute("SELECT version FROM schema_version").fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Bring the file to SCHEMA_VERSION. Each migration runs in one transaction."""
    v = _version(conn)
    if v < 1:
        # executescript commits any pending transaction first, so the script carries its own
        # BEGIN/COMMIT to make the whole migration atomic.
        conn.executescript("BEGIN;\n" + _SCHEMA_V1 + "\nINSERT INTO schema_version(version) VALUES (1);\nCOMMIT;")
        v = 1
    return v


def open_db(home: Path) -> sqlite3.Connection:
    home.mkdir(parents=True, exist_ok=True)
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
```

Note on transactions: `isolation_level=None` puts the connection in autocommit; `with conn:` still commits or rolls back on exit when a transaction is open, so multi-statement writers (`ingest.record`, `flags.set_flag`) do `conn.execute("BEGIN")` inside `with conn:`. Single statements run autocommitted.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_web_db.py -q`
Expected: 4 passed. If `test_one_active_flag_per_item`'s `with conn:` blocks do not roll back on the `IntegrityError` under autocommit, change the two `with conn:` blocks that expect an error to plain statements (the error is raised either way; the point is the partial index).

- [ ] **Step 5: Commit**

```bash
git add lakota_grades/web tests/test_web_db.py
git commit -m "web.db: the SQLite file, migration 1, latest_observations

Closes #6

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: `web/ingest.py`: snapshot to rows, observations only on change (issue #7)

**Files:**
- Create: `lakota_grades/web/ingest.py`
- Test: `tests/test_web_ingest.py`

**Interfaces:**
- Consumes: `db.open_db`, `db.now_iso`; `matching.short_course`, `norm_name`, `same_item`, `match_course`; `open_items._kind`, `open_items._parse_hac_date`.
- Produces:
  - `ingest.item_key_canvas(assignment_id) -> str` (`canvas:<id>`), `ingest.item_key_hac(course_name, name) -> str` (`hac:<short course>:<norm name>`)
  - `ingest.IngestResult(refresh_id: int, students: int, courses: int, items: int, observations: int, grades: int)`
  - `ingest.record(conn, snapshot: dict, *, tz, now: datetime | None = None) -> IngestResult` — one transaction; a snapshot that changes nothing writes only the `refreshes` row.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_ingest.py
"""Snapshot -> database. Two snapshots a day apart: the second changes one score, adds one
assignment, and repeats everything else; only the changes become observations."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from lakota_grades.web import db, ingest

TZ = ZoneInfo("America/New_York")
T1 = datetime(2026, 9, 14, 6, 0, tzinfo=TZ)
T2 = datetime(2026, 9, 15, 6, 0, tzinfo=TZ)


def _assignment(i, name, due="2026-09-12T23:59:00-04:00", **over):
    a = {"id": i, "name": name, "due_at": due, "unlock_at": None, "created_at": "2026-09-01T08:00:00-04:00",
         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "group_weight": None,
         "published": True, "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": True,
         "excused": False, "submitted_at": None, "seconds_late": 0}
    a.update(over)
    return a


def snapshot(fetched: datetime) -> dict:
    return {
        "fetched_at": fetched.isoformat(), "fetched_at_epoch": fetched.timestamp(),
        "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {
            "Alex": {
                "name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
                "canvas": {"courses": [{
                    "id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                    "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                    "staff": [{"name": "Michael Hoch", "email": None, "roles": ["TeacherEnrollment"]}],
                    "assignments": [_assignment(77, "Quiz 1"), _assignment(78, "Essay draft")],
                }]},
                "hac": {"week_view": [], "classes": [{
                    "code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 75.67, "last_updated": "9/11/2026",
                    "assignments": [
                        {"due": "09/12/2026", "assigned": "09/10/2026", "name": "Quiz #1", "category": "Assessments",
                         "score": 28.0, "score_raw": "28.00", "points": 30.0, "percent": "93.33%"},
                        {"due": "09/11/2026", "assigned": "09/09/2026", "name": "Reading log", "category": "Assignments",
                         "score": None, "score_raw": "", "points": 5.0, "percent": ""},
                    ],
                    "categories": [],
                }]},
            },
            "Sam": {"name": "Sam Example", "canvas_id": 124, "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}},
        },
    }


def test_first_ingest_creates_everything_and_links_hac_to_canvas(tmp_path):
    conn = db.open_db(tmp_path)
    r = ingest.record(conn, snapshot(T1), tz=TZ, now=T1)
    assert (r.students, r.courses) == (2, 2)                       # one Canvas + one HAC course for Alex
    assert r.items == 3                                             # Quiz 1 (linked), Essay draft, Reading log (HAC-only)
    keys = {row["key"] for row in conn.execute("SELECT key FROM items")}
    assert keys == {"canvas:77", "canvas:78", "hac:Honors English 9:reading log"}
    latest = db.latest_observations(conn, conn.execute("SELECT id FROM students WHERE key='Alex'").fetchone()[0])
    quiz = conn.execute("SELECT id FROM items WHERE key='canvas:77'").fetchone()[0]
    assert set(latest[quiz]) == {"canvas", "hac"}                   # "Quiz #1" in HAC attached to Canvas' "Quiz 1"
    assert latest[quiz]["hac"]["score"] == 28.0 and latest[quiz]["canvas"]["missing"] == 1
    hac_course = conn.execute("SELECT * FROM courses WHERE source='hac'").fetchone()
    canvas_course = conn.execute("SELECT * FROM courses WHERE source='canvas'").fetchone()
    assert hac_course["peer_course_id"] == canvas_course["id"] and canvas_course["peer_course_id"] == hac_course["id"]
    assert canvas_course["teacher"] == "Michael Hoch" and canvas_course["short_name"] == "Honors English 9"
    grades = conn.execute("SELECT * FROM grade_observations ORDER BY course_id").fetchall()
    assert [(g["current"], g["average"]) for g in grades] == [(91.2, None), (None, 75.67)]
    reading = conn.execute("SELECT * FROM items WHERE key LIKE 'hac:%'").fetchone()
    assert reading["due"] == "2026-09-11T23:59:00-04:00" and reading["kind"] == ""
    assert conn.execute("SELECT ok, sources FROM refreshes").fetchone()[0] == 1


def test_second_ingest_writes_only_changes(tmp_path):
    conn = db.open_db(tmp_path)
    ingest.record(conn, snapshot(T1), tz=TZ, now=T1)
    before = conn.execute("SELECT count(*) FROM item_observations").fetchone()[0]
    r = ingest.record(conn, snapshot(T2), tz=TZ, now=T2)          # identical content, new fetch time
    assert r.observations == 0 and r.grades == 0
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM item_observations").fetchone()[0] == before
    assert conn.execute("SELECT last_seen FROM items WHERE key='canvas:77'").fetchone()[0] == 2

    changed = snapshot(T2)
    quiz = changed["students"]["Alex"]["canvas"]["courses"][0]["assignments"][0]
    quiz.update(score=9.0, grade="9", state="graded", missing=False)
    changed["students"]["Alex"]["canvas"]["courses"][0]["assignments"].append(_assignment(79, "Vocabulary 3", due="2026-09-20T23:59:00-04:00", missing=False))
    changed["students"]["Alex"]["hac"]["classes"][0]["marking_period_avg"] = 78.1
    r = ingest.record(conn, changed, tz=TZ, now=T2)
    assert r.observations == 2 and r.grades == 1                    # quiz's canvas view changed; the new item's first observation
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 4
    latest = db.latest_observations(conn, 1)
    quiz_id = conn.execute("SELECT id FROM items WHERE key='canvas:77'").fetchone()[0]
    assert latest[quiz_id]["canvas"]["state"] == "graded" and latest[quiz_id]["canvas"]["score"] == 9.0
    assert conn.execute("SELECT count(*) FROM item_observations WHERE item_id=? AND source='canvas'", (quiz_id,)).fetchone()[0] == 2


def test_failed_source_is_recorded_and_carried_students_are_untouched(tmp_path):
    conn = db.open_db(tmp_path)
    snap = snapshot(T1)
    snap["sources"]["hac"] = "login_required: OneLogin did not redirect"
    snap["stale"] = {"hac": {"fetched_at": "2026-09-13T06:00:00-04:00", "fetched_at_epoch": 0, "reason": "login_required"}}
    r = ingest.record(conn, snap, tz=TZ, now=T1)
    row = conn.execute("SELECT ok, sources FROM refreshes").fetchone()
    assert row[0] == 0 and json.loads(row[1])["hac"].startswith("login_required")
    assert r.items == 3                                             # carried-forward HAC data still ingests


def test_keys_are_stable_across_name_punctuation(tmp_path):
    assert ingest.item_key_hac("Honors English 9 S1", 'Quiz #1: "The Seventh Man"') == "hac:Honors English 9:quiz 1 the seventh man"
    assert ingest.item_key_hac("Honors English 9 - 3", "quiz  1:  the seventh man") == "hac:Honors English 9:quiz 1 the seventh man"
    assert ingest.item_key_canvas(77) == "canvas:77"
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_web_ingest.py -q`
Expected: FAIL at import (`cannot import name 'ingest'`).

- [ ] **Step 3: Write `ingest.py`**

```python
# lakota_grades/web/ingest.py
"""Snapshot -> database rows. Called after every refresh (CLI runner, later the web worker).

One transaction per snapshot. Students, courses and items are upserted by stable keys;
an observation is appended only when the source's view of an item (or a course's grade)
differs from the last one recorded, so the observation tables are change logs.
A HAC row that names the same work as a Canvas assignment in the matched course becomes
that assignment's second source rather than its own item.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..matching import match_course, norm_name, same_item, short_course
from ..open_items import _kind, _parse_hac_date
from . import db

_ASSESSMENT_WORDS = ("quiz", "test", "assess", "exam")


@dataclass(frozen=True)
class IngestResult:
    refresh_id: int
    students: int
    courses: int
    items: int
    observations: int
    grades: int


def item_key_canvas(assignment_id) -> str:
    return f"canvas:{assignment_id}"


def item_key_hac(course_name: str, name: str) -> str:
    return f"hac:{short_course(course_name)}:{norm_name(name)}"


def _upsert_student(conn, key: str, name: str) -> int:
    conn.execute("INSERT INTO students(key, name) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET name = excluded.name", (key, name))
    return conn.execute("SELECT id FROM students WHERE key = ?", (key,)).fetchone()[0]


def _upsert_course(conn, student_id: int, source: str, external_id, name: str, teacher: str | None) -> int:
    conn.execute(
        """INSERT INTO courses(student_id, source, external_id, name, short_name, teacher) VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(student_id, source, name) DO UPDATE SET external_id = excluded.external_id,
               teacher = COALESCE(excluded.teacher, courses.teacher)""",
        (student_id, source, str(external_id) if external_id is not None else None, name, short_course(name), teacher),
    )
    return conn.execute("SELECT id FROM courses WHERE student_id = ? AND source = ? AND name = ?", (student_id, source, name)).fetchone()[0]


def _upsert_item(conn, student_id: int, course_id: int, key: str, name: str, kind: str, points, due: str | None,
                 assigned: str | None, is_assessment: bool, refresh_id: int) -> tuple[int, bool]:
    row = conn.execute("SELECT id FROM items WHERE key = ?", (key,)).fetchone()
    if row:
        conn.execute("UPDATE items SET name = ?, kind = ?, points = ?, due = ?, assigned = COALESCE(?, assigned), is_assessment = ?, last_seen = ? WHERE id = ?",
                     (name, kind, points, due, assigned, int(is_assessment), refresh_id, row[0]))
        return row[0], False
    cur = conn.execute(
        "INSERT INTO items(student_id, course_id, key, name, kind, points, due, assigned, is_assessment, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (student_id, course_id, key, name, kind, points, due, assigned, int(is_assessment), refresh_id, refresh_id))
    return cur.lastrowid, True


_OBS_FIELDS = ("state", "score", "grade", "submitted_at", "late", "missing", "excused")


def _observe(conn, refresh_id: int, item_id: int, source: str, values: dict) -> bool:
    """Append an observation if it differs from the last one for (item, source). Returns True when written."""
    last = conn.execute("SELECT * FROM item_observations WHERE item_id = ? AND source = ? ORDER BY refresh_id DESC, id DESC LIMIT 1",
                        (item_id, source)).fetchone()
    if last is not None and all(last[f] == values.get(f) for f in _OBS_FIELDS):
        return False
    conn.execute(
        "INSERT INTO item_observations(refresh_id, item_id, source, state, score, grade, submitted_at, late, missing, excused) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (refresh_id, item_id, source, *(values.get(f) for f in _OBS_FIELDS)))
    return True


def _observe_grade(conn, refresh_id: int, course_id: int, average, letter, current, final, last_updated) -> bool:
    last = conn.execute("SELECT * FROM grade_observations WHERE course_id = ? ORDER BY refresh_id DESC, id DESC LIMIT 1", (course_id,)).fetchone()
    new = (average, letter, current, final, last_updated)
    if last is not None and (last["average"], last["letter"], last["current"], last["final"], last["last_updated"]) == new:
        return False
    conn.execute("INSERT INTO grade_observations(refresh_id, course_id, average, letter, current, final, last_updated) VALUES (?,?,?,?,?,?,?)",
                 (refresh_id, course_id, *new))
    return True


def _flag(v) -> int | None:
    return None if v is None else int(bool(v))


def _canvas_values(a: dict) -> dict:
    return {"state": a.get("state"), "score": a.get("score"), "grade": a.get("grade"), "submitted_at": a.get("submitted_at"),
            "late": _flag(a.get("late")), "missing": _flag(a.get("missing")), "excused": _flag(a.get("excused"))}


def _hac_values(row: dict) -> dict:
    graded = row.get("score") is not None
    return {"state": "graded" if graded else "ungraded", "score": row.get("score"), "grade": (row.get("percent") or None) if graded else None,
            "submitted_at": None, "late": None, "missing": None, "excused": None}


def record(conn: sqlite3.Connection, snapshot: dict, *, tz, now: datetime | None = None) -> IngestResult:
    now = now or datetime.now(tz)
    sources = snapshot.get("sources") or {}
    n_students = n_courses = n_items = n_obs = n_grades = 0
    with conn:
        conn.execute("BEGIN")
        cur = conn.execute("INSERT INTO refreshes(started_at, finished_at, sources, ok) VALUES (?, ?, ?, ?)",
                           (snapshot.get("fetched_at") or now.isoformat(), now.isoformat(), json.dumps(sources),
                            int(all(v == "ok" for v in sources.values()))))
        refresh_id = cur.lastrowid
        for key, entry in (snapshot.get("students") or {}).items():
            student_id = _upsert_student(conn, key, entry.get("name") or key)
            n_students += 1
            canvas_courses = (entry.get("canvas") or {}).get("courses") or []
            hac_classes = (entry.get("hac") or {}).get("classes") or []

            # Canvas courses, grades and assignments
            canvas_course_ids: dict[str, int] = {}
            canvas_items_by_course: dict[int, list[tuple[int, str]]] = {}
            for c in canvas_courses:
                staff = c.get("staff") or []
                teacher = next((s.get("name") for s in staff if "TeacherEnrollment" in (s.get("roles") or [])), None) or (staff[0].get("name") if staff else None)
                cid = _upsert_course(conn, student_id, "canvas", c.get("id"), c["name"], teacher)
                canvas_course_ids[c["name"]] = cid
                n_courses += 1
                g = c.get("grade") or {}
                n_grades += _observe_grade(conn, refresh_id, cid, None, g.get("current_grade"), g.get("current_score"), g.get("final_score"), None)
                for a in c.get("assignments") or []:
                    if a.get("id") is None:
                        continue
                    assigned = a.get("unlock_at") or a.get("created_at")
                    item_id, _ = _upsert_item(conn, student_id, cid, item_key_canvas(a["id"]), a.get("name") or "", _kind(a.get("submission_types")),
                                              a.get("points_possible"), a.get("due_at"), assigned,
                                              bool(a.get("group") and any(w in a["group"].lower() for w in _ASSESSMENT_WORDS)), refresh_id)
                    n_items += 1
                    n_obs += _observe(conn, refresh_id, item_id, "canvas", _canvas_values(a))
                    canvas_items_by_course.setdefault(cid, []).append((item_id, a.get("name") or ""))

            # HAC classes: pair with a Canvas course, attach rows to Canvas twins, else HAC-only items
            for h in hac_classes:
                hid = _upsert_course(conn, student_id, "hac", h.get("code"), h["name"], None)
                n_courses += 1
                peer_cid = match_course(h["name"], canvas_course_ids) if canvas_course_ids else None
                if peer_cid is not None:
                    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (peer_cid, hid))
                    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hid, peer_cid))
                n_grades += _observe_grade(conn, refresh_id, hid, h.get("marking_period_avg"), None, None, None, h.get("last_updated"))
                twins = canvas_items_by_course.get(peer_cid, []) if peer_cid is not None else []
                for row in h.get("assignments") or []:
                    name = row.get("name") or ""
                    twin = next((iid for iid, n in twins if same_item(name, n)), None)
                    if twin is not None:
                        n_obs += _observe(conn, refresh_id, twin, "hac", _hac_values(row))
                        continue
                    due = _parse_hac_date(row.get("due"), tz)
                    assigned = _parse_hac_date(row.get("assigned"), tz)
                    item_id, _ = _upsert_item(conn, student_id, hid, item_key_hac(h["name"], name), name, "", row.get("points"),
                                              due.replace(hour=23, minute=59).isoformat() if due else None,
                                              assigned.isoformat() if assigned else None,
                                              any(w in (row.get("category") or "").lower() for w in ("quiz", "assess")), refresh_id)
                    n_items += 1
                    n_obs += _observe(conn, refresh_id, item_id, "hac", _hac_values(row))
    return IngestResult(refresh_id, n_students, n_courses, n_items, n_obs, n_grades)
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_web_ingest.py tests/test_web_db.py -q`
Expected: 8 passed. If `test_first_ingest...` fails on `assert (r.students, r.courses) == (2, 2)` because Sam has no courses, the count is students seen (2) and courses upserted (2): check the loop counts, not the fixture.

- [ ] **Step 5: Commit**

```bash
git add lakota_grades/web/ingest.py tests/test_web_ingest.py
git commit -m "web.ingest: snapshot to rows; observations only on change; HAC rows attach to their Canvas twins

Closes #7

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Notes and flags stores (issue #8)

**Files:**
- Create: `lakota_grades/web/stores/__init__.py`, `lakota_grades/web/stores/notes.py`, `lakota_grades/web/stores/flags.py`
- Test: `tests/test_web_stores.py`

**Interfaces:**
- Produces:
  - `stores.notes.add(conn, target_type: str, target_id: int, body: str, *, now: str) -> int`, `edit(conn, note_id, body, *, now) -> None`, `delete(conn, note_id) -> None`, `for_target(conn, target_type, target_id) -> list[sqlite3.Row]` (newest first), `for_student(conn, student_id) -> list[sqlite3.Row]` (every note on the student, its courses and its items, newest first, each row carrying `target_type`, `target_id`, `target_name`).
  - `stores.flags.FLAGS = ("done", "excused", "ignore", "follow_up", "ask_teacher")`, `HANDLED = ("done", "excused", "ignore")`
  - `stores.flags.set_flag(conn, item_id: int, flag: str, *, now: str, text: str = "") -> int` (clears any active flag first), `clear(conn, item_id, *, now) -> bool`, `active(conn, item_id) -> sqlite3.Row | None`, `active_by_key(conn, student_id: int | None = None) -> dict[str, str]` (item key → flag, for the runner), `history(conn, item_id) -> list[sqlite3.Row]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_stores.py
"""Notes and flags: the parent's own knowledge next to the data."""
from __future__ import annotations

import pytest

from lakota_grades.web import db
from lakota_grades.web.stores import flags, notes


@pytest.fixture
def conn(tmp_path):
    c = db.open_db(tmp_path)
    with c:
        c.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        c.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        c.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Honors Biology S1', 'Honors Biology')")
        c.executemany("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (?, 1, 1, ?, ?, 1, 1)",
                      [(1, "canvas:1", "WS 1"), (2, "canvas:2", "WS 2")])
    return c


def test_notes_round_trip_and_student_view(conn):
    n1 = notes.add(conn, "item", 1, "emailed Mr. Nance", now="2026-09-14T10:00:00")
    n2 = notes.add(conn, "course", 1, "late work 50% for a week", now="2026-09-14T11:00:00")
    n3 = notes.add(conn, "student", 1, "check planner Fridays", now="2026-09-14T12:00:00")
    assert [r["body"] for r in notes.for_target(conn, "item", 1)] == ["emailed Mr. Nance"]
    notes.edit(conn, n1, "emailed Mr. Nance; he replied", now="2026-09-14T13:00:00")
    row = notes.for_target(conn, "item", 1)[0]
    assert row["body"].endswith("replied") and row["updated_at"] == "2026-09-14T13:00:00" and row["created_at"] == "2026-09-14T10:00:00"
    all_rows = notes.for_student(conn, 1)
    assert [(r["target_type"], r["target_name"]) for r in all_rows] == [("student", "Alex S"), ("course", "Honors Biology"), ("item", "WS 1")]
    notes.delete(conn, n2)
    assert len(notes.for_student(conn, 1)) == 2 and n3


def test_flags_one_active_replace_clear_and_history(conn):
    assert flags.active(conn, 1) is None
    flags.set_flag(conn, 1, "follow_up", now="2026-09-14T10:00:00", text="ask about retake")
    assert flags.active(conn, 1)["flag"] == "follow_up"
    flags.set_flag(conn, 1, "done", now="2026-09-15T10:00:00")          # replaces: old one gets cleared_at
    assert flags.active(conn, 1)["flag"] == "done"
    hist = flags.history(conn, 1)
    assert [(h["flag"], h["cleared_at"] is None) for h in hist] == [("done", True), ("follow_up", False)]
    assert flags.clear(conn, 1, now="2026-09-16T10:00:00") is True
    assert flags.active(conn, 1) is None and flags.clear(conn, 1, now="x") is False
    with pytest.raises(ValueError):
        flags.set_flag(conn, 1, "bogus", now="t")


def test_active_by_key_for_the_runner(conn):
    flags.set_flag(conn, 1, "done", now="t")
    flags.set_flag(conn, 2, "ask_teacher", now="t")
    assert flags.active_by_key(conn) == {"canvas:1": "done", "canvas:2": "ask_teacher"}
    assert flags.active_by_key(conn, student_id=1) == {"canvas:1": "done", "canvas:2": "ask_teacher"}
    assert flags.active_by_key(conn, student_id=99) == {}
    assert flags.HANDLED == ("done", "excused", "ignore")
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_web_stores.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Write the stores**

```python
# lakota_grades/web/stores/__init__.py
"""One module per table family. Every function takes the connection first and commits
its own transaction with `with conn:` so callers never hold one open across a request."""
```

```python
# lakota_grades/web/stores/notes.py
from __future__ import annotations

import sqlite3

TARGETS = ("item", "course", "student")


def add(conn: sqlite3.Connection, target_type: str, target_id: int, body: str, *, now: str) -> int:
    if target_type not in TARGETS:
        raise ValueError(f"unknown note target {target_type!r}")
    with conn:
        cur = conn.execute("INSERT INTO notes(target_type, target_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                           (target_type, target_id, body, now, now))
        return cur.lastrowid


def edit(conn: sqlite3.Connection, note_id: int, body: str, *, now: str) -> None:
    with conn:
        conn.execute("UPDATE notes SET body = ?, updated_at = ? WHERE id = ?", (body, now, note_id))


def delete(conn: sqlite3.Connection, note_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


def for_target(conn: sqlite3.Connection, target_type: str, target_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM notes WHERE target_type = ? AND target_id = ? ORDER BY created_at DESC, id DESC",
                        (target_type, target_id)).fetchall()


def for_student(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    """Every note that belongs to a student: on the student, on their courses, on their items."""
    return conn.execute(
        """SELECT n.*, CASE n.target_type
                 WHEN 'student' THEN s.name WHEN 'course' THEN c.short_name ELSE i.name END AS target_name
           FROM notes n
           LEFT JOIN students s ON n.target_type = 'student' AND s.id = n.target_id
           LEFT JOIN courses c ON n.target_type = 'course' AND c.id = n.target_id
           LEFT JOIN items i ON n.target_type = 'item' AND i.id = n.target_id
           WHERE COALESCE(s.id, c.student_id, i.student_id) = ?
           ORDER BY n.created_at DESC, n.id DESC""",
        (student_id,)).fetchall()
```

```python
# lakota_grades/web/stores/flags.py
"""The parent's verdict on an item, which the sources cannot know. One active flag per
item (a partial unique index enforces it); setting a new one clears the old."""
from __future__ import annotations

import sqlite3

FLAGS = ("done", "excused", "ignore", "follow_up", "ask_teacher")
HANDLED = ("done", "excused", "ignore")          # these remove the item from the open list
MARKED = ("follow_up", "ask_teacher")            # these print a marker in the status column


def active(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM flags WHERE item_id = ? AND cleared_at IS NULL", (item_id,)).fetchone()


def set_flag(conn: sqlite3.Connection, item_id: int, flag: str, *, now: str, text: str = "") -> int:
    if flag not in FLAGS:
        raise ValueError(f"unknown flag {flag!r}; one of {', '.join(FLAGS)}")
    with conn:
        conn.execute("BEGIN")
        conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        cur = conn.execute("INSERT INTO flags(item_id, flag, text, set_at) VALUES (?, ?, ?, ?)", (item_id, flag, text, now))
        return cur.lastrowid


def clear(conn: sqlite3.Connection, item_id: int, *, now: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        return cur.rowcount > 0


def history(conn: sqlite3.Connection, item_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM flags WHERE item_id = ? ORDER BY set_at DESC, id DESC", (item_id,)).fetchall()


def active_by_key(conn: sqlite3.Connection, student_id: int | None = None) -> dict[str, str]:
    """item key -> active flag; what the runner hands to open_items."""
    sql = "SELECT i.key, f.flag FROM flags f JOIN items i ON i.id = f.item_id WHERE f.cleared_at IS NULL"
    args: tuple = ()
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args = (student_id,)
    return {r["key"]: r["flag"] for r in conn.execute(sql, args)}
```

- [ ] **Step 4: Run the tests, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_web_stores.py -q` — 3 passed; then the full suite.

```bash
git add lakota_grades/web/stores tests/test_web_stores.py
git commit -m "web.stores: notes on items, courses and students; one active flag per item

Closes #8

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 5: Flags reach the printed sheet (issue #9)

**Files:**
- Modify: `lakota_grades/open_items.py` (`Item.flag`, `OpenWork.handled`, `open_items(..., flags=)`, the two constants)
- Modify: `lakota_grades/web/stores/flags.py` (import the constants from `open_items` instead of defining them)
- Modify: `lakota_grades/reports/base.py` (`BuildContext.flags`), `lakota_grades/reports/open_work.py` (pass it)
- Modify: `lakota_grades/sheet.py` (`_status_cell` marker, `_tail_lines` "Handled" line)
- Modify: `lakota_grades/runner.py` (load flags before building)
- Test: `tests/test_open_items.py` (append), `tests/test_runner.py` (append)

**Interfaces:**
- Consumes: `web.db.open_db`, `web.stores.flags.active_by_key` (Task 4).
- Produces:
  - `open_items.HANDLED_FLAGS = ("done", "excused", "ignore")`, `open_items.MARKED_FLAGS = ("follow_up", "ask_teacher")`
  - `open_items.Item.flag: str = ""`; `open_items.OpenWork.handled: list[Item]` (items removed by a handled flag; not in `items` or `dropped`)
  - `open_items.open_items(entry, kid, now, days_ahead=14, overdue_days=14, rules=None, include_hac=True, flags: dict[str, str] | None = None) -> OpenWork`
  - `reports.base.BuildContext.flags: dict[str, str]` (default empty)
  - `runner._load_flags(home: Path, log) -> dict[str, str]` (empty dict and a `WARN` line on any database error)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_open_items.py` (it already imports `open_items`, `late_rules`, has `TZ`/`NOW`-style fixtures; reuse its existing `entry`/snapshot helpers where present, else build a minimal entry as below):

```python
def _entry_with_two_missing():
    a = lambda i, name: {"id": i, "name": name, "due_at": (NOW - timedelta(days=2)).isoformat(), "unlock_at": None, "created_at": None,  # noqa: E731
                         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "published": True,
                         "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": True, "excused": False}
    return {"name": "Alex Example", "canvas": {"courses": [{"id": 5, "name": "Honors Biology S1-2027-Nance", "assignments": [a(1, "WS 1"), a(2, "WS 2")]}]}, "hac": {"classes": []}}


def test_handled_flags_remove_items_and_marked_flags_annotate():
    work = open_items.open_items(_entry_with_two_missing(), "Al", NOW, flags={"canvas:1": "done", "canvas:2": "ask_teacher"})
    assert [i.key for i in work.items] == ["canvas:2"] and work.items[0].flag == "ask_teacher"
    assert [i.key for i in work.handled] == ["canvas:1"] and work.handled[0].flag == "done"
    assert work.dropped == []
    assert "flag" in work.items[0].to_dict()
    assert open_items.HANDLED_FLAGS == ("done", "excused", "ignore") and open_items.MARKED_FLAGS == ("follow_up", "ask_teacher")


def test_no_flags_means_no_change():
    work = open_items.open_items(_entry_with_two_missing(), "Al", NOW)
    assert len(work.items) == 2 and work.handled == [] and all(i.flag == "" for i in work.items)
```

(`NOW` and `timedelta` are already available in that module; if `NOW` is named differently there, use the module's constant.)

Append to `tests/test_runner.py`:

```python
def test_runner_loads_flags_from_the_database(env):
    """A flag set in the browser reaches the scheduled sheet: the flagged item is not in rows.json."""
    from lakota_grades.web import db, ingest
    from lakota_grades.web.stores import flags as flagstore
    s, calls, refresh, print_pdf, toast = env
    conn = db.open_db(s.home)
    ingest.record(conn, _snapshot(), tz=TZ, now=FRI_2PM)
    item_id = conn.execute("SELECT id FROM items WHERE key = 'canvas:1'").fetchone()[0]
    flagstore.set_flag(conn, item_id, "done", now=FRI_2PM.isoformat())
    conn.close()
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    rows = json.loads((s.home / "sheets" / "2026-09-11" / "rows.json").read_text())
    assert rows["Alex"] == []
    log = (s.home / runner.LOG_NAME).read_text()
    assert "Al=0" in log


def test_runner_survives_a_broken_database(env):
    s, calls, refresh, print_pdf, toast = env
    (s.home / "lakota.db").mkdir()                                  # a directory where the file should be
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert "WARN" in (s.home / runner.LOG_NAME).read_text()
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_open_items.py tests/test_runner.py -q -k "flag or broken_database"`
Expected: FAIL (`TypeError: open_items() got an unexpected keyword argument 'flags'`, `AttributeError` on `HANDLED_FLAGS`, and the runner test's `rows["Alex"] == []` failing).

- [ ] **Step 3: Implement**

`lakota_grades/open_items.py`:
- Add after `OVERDUE_STATUSES`: `HANDLED_FLAGS = ("done", "excused", "ignore")` and `MARKED_FLAGS = ("follow_up", "ask_teacher")`.
- `Item` gains `flag: str = ""` (after `submission_types`).
- `OpenWork` gains `handled: list[Item] = field(default_factory=list)` (after `dropped`).
- `open_items(...)` gains `flags: dict[str, str] | None = None`; at the top `flags = flags or {}` and `handled: list[Item] = []`. In **both** branches, right after the `Item(...)` is constructed and before the overdue/late-rules logic, add:

```python
            it.flag = flags.get(it.key, "")
            if it.flag in HANDLED_FLAGS:
                handled.append(it)
                continue
```

  (In the Canvas branch this goes before `canvas_names_by_course.setdefault(...)` so a handled Canvas item still suppresses its HAC twin: move the `setdefault` line above the flag check.) The return becomes `OpenWork(kid=kid, as_of=now, items=items, dropped=dropped, handled=handled)`; sort `handled` like `dropped`.

`lakota_grades/web/stores/flags.py`: replace the three constant lines with
```python
from ...open_items import HANDLED_FLAGS as HANDLED, MARKED_FLAGS as MARKED

FLAGS = HANDLED + MARKED
```

`lakota_grades/reports/base.py`: `BuildContext` gains `flags: dict[str, str] = field(default_factory=dict)` as the last field (import `field`). `reports/open_work.py`: pass `flags=ctx.flags` to `open_items.open_items(...)`.

`lakota_grades/sheet.py`: in `_status_cell`, after the `text = _esc(it.status)` line add
```python
    if it.flag in ("follow_up", "ask_teacher"):
        text += f'<br/><font name="Helvetica-Bold" size="7" color="#6C3FA0">{"FOLLOW UP" if it.flag == "follow_up" else "ASK TEACHER"}</font>'
```
and in `_tail_lines`, before the `dropped` block:
```python
    if ks.work.handled:
        n = len(ks.work.handled)
        out.append(Paragraph(f"Handled: {n} item{'s' if n != 1 else ''} marked done, excused or ignored in the app", NOTE))
```

`lakota_grades/runner.py`: add
```python
def _load_flags(home: Path, log) -> dict[str, str]:
    """Active flags from the app's database, or nothing (with a WARN) if it cannot be read."""
    try:
        from .web import db as webdb
        from .web.stores import flags as flagstore
        conn = webdb.open_db(home)
        try:
            return flagstore.active_by_key(conn)
        finally:
            conn.close()
    except Exception as e:  # the sheet must print even if the database is broken
        log("WARN", f"could not read flags from the database: {type(e).__name__}: {str(e)[:120]}")
        return {}
```
and in `run()`, in the build section, `ctx = BuildContext(..., data_as_of=as_of, flags=_load_flags(home, log))`.

- [ ] **Step 4: Run the suite, commit**

Run the full suite; expected: all previous tests pass (the sheet's existing text assertions are unaffected) plus the 4 new ones.

```bash
git add lakota_grades/open_items.py lakota_grades/web/stores/flags.py lakota_grades/reports lakota_grades/sheet.py lakota_grades/runner.py tests/test_open_items.py tests/test_runner.py
git commit -m "Flags reach the printed sheet: handled flags drop the item, marked flags annotate it; the runner loads flags from the database

Closes #9

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The CLI runner ingests after refresh and records runs; doctor `database` probe (issue #10)

**Files:**
- Modify: `lakota_grades/runner.py` (`RunOptions.trigger`, `_ingest`, `_record_run`, calls), `lakota_grades/doctor.py` (probe), `lakota_grades/cli.py` (`cmd_run` passes `trigger="cli"`; nothing else)
- Test: `tests/test_runner.py` (append), `tests/test_doctor.py` (modify the names list, append a test)

**Interfaces:**
- Consumes: `web.db.open_db`, `web.ingest.record`.
- Produces:
  - `runner.RunOptions.trigger: str = "cli"` (`cli` | `schedule` | `web`)
  - `runner._ingest(home, snap, tz, log) -> None` (WARN on failure), `runner._record_run(home, report_key, started: datetime, finished: datetime, trigger, outcome, message, pdf_path, job_ref, log) -> None` (WARN on failure)
  - Every exit of `runner.run` except the unknown-report exit writes a `runs` row: `OK`, `SKIP` or `FAIL`, with the log message, and the PDF path / job reference when known; `dry-run` writes `OK` with the PDF path.
  - `doctor` probe `("database", ...)` inserted right after `("home", ...)`: opens the database, reports `"<path> schema <v>: <n> refreshes, <m> items, <k> active flags"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_runner.py`:

```python
def test_run_ingests_after_refresh_and_records_the_run(env):
    from lakota_grades.web import db
    s, calls, refresh, print_pdf, toast = env
    assert _run(s, runner.RunOptions(printer="Office"), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    conn = db.open_db(s.home)
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM items").fetchone()[0] == 1          # the fixture's one assignment
    run = conn.execute("SELECT * FROM runs").fetchone()
    assert (run["report_key"], run["trigger"], run["outcome"], run["job_ref"]) == ("open-work", "cli", "OK", "job-1")
    assert run["pdf_path"].endswith("sheet.pdf") and run["finished_at"] and "printed" in run["message"]


def test_no_refresh_and_skips_still_record_but_do_not_ingest(env):
    from lakota_grades.web import db
    s, calls, refresh, print_pdf, toast = env
    _run(s, runner.RunOptions(dry_run=True, no_refresh=True, trigger="web"), refresh=refresh, print_pdf=print_pdf, toast=toast)
    _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=9), refresh=refresh, print_pdf=print_pdf, toast=toast)   # window skip
    conn = db.open_db(s.home)
    assert conn.execute("SELECT count(*) FROM refreshes").fetchone()[0] == 0
    rows = conn.execute("SELECT trigger, outcome FROM runs ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [("web", "OK"), ("cli", "SKIP")]


def test_run_recording_failure_is_a_warning(env):
    s, calls, refresh, print_pdf, toast = env
    (s.home / "lakota.db").mkdir()
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert (s.home / runner.LOG_NAME).read_text().count("WARN") >= 1
```

In `tests/test_doctor.py`, change the expected names list in `test_real_probes_run_on_this_machine` to
`["python", "home", "database", "timezone", "pdf", "chromium", "credential store", "printers", "print engine", "scheduler"]`, add `by["database"].ok` to the unconditional assertions, and append:

```python
def test_database_probe_reports_counts(tmp_path):
    from lakota_grades.web import db
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('t', '{}', 1)")
    conn.close()
    out = {c.name: c for c in doctor.checks(Settings(home=tmp_path), tmp_path, probes=[p for p in doctor.PROBES if p[0] == "database"])}
    assert out["database"].ok and "schema 1" in out["database"].detail and "1 refreshes" in out["database"].detail
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_runner.py tests/test_doctor.py -q`
Expected: the new runner tests fail (`no such table: runs` is not it: `open_db` creates it; the failures are `count == 0`, missing rows, and `trigger` being an unexpected keyword); the doctor names test fails on the list.

- [ ] **Step 3: Implement**

`lakota_grades/runner.py`:
- `RunOptions` gains `trigger: str = "cli"` (last field).
- Add:
```python
def _ingest(home: Path, snap: dict, tz, log) -> None:
    try:
        from .web import db as webdb, ingest
        conn = webdb.open_db(home)
        try:
            r = ingest.record(conn, snap, tz=tz)
        finally:
            conn.close()
        log("INFO", f"ingested refresh {r.refresh_id}: {r.items} items, {r.observations} changes, {r.grades} grade changes")
    except Exception as e:  # the database is a passenger; the sheet must not depend on it
        log("WARN", f"could not ingest the snapshot into the database: {type(e).__name__}: {str(e)[:120]}")


def _record_run(home: Path, report_key: str, started: datetime, finished: datetime, trigger: str, outcome: str,
                message: str, pdf_path, job_ref, log) -> None:
    try:
        from .web import db as webdb
        conn = webdb.open_db(home)
        try:
            with conn:
                conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path, job_ref) VALUES (?,?,?,?,?,?,?,?)",
                             (report_key, started.isoformat(), finished.isoformat(), trigger, outcome, message[:500],
                              str(pdf_path) if pdf_path else None, job_ref))
        finally:
            conn.close()
    except Exception as e:
        log("WARN", f"could not record the run in the database: {type(e).__name__}: {str(e)[:120]}")
```
- In `run()`: capture `started = datetime.now(tz)` right after `now` is set (real clock; `now` may be injected). Change `finish` to record: after `log(level, msg)`, call `_record_run(home, report_key, started, datetime.now(tz), opts.trigger, level, msg, pdf_path, job_ref, log)` where `finish` gains keyword parameters `pdf_path=None, job_ref=None` (the OK call passes `built.pdf` and `job`; the `PrintError` FAIL passes `built.pdf`). The dry-run branch (`log("OK", f"dry-run built ...")`; `return 0`) becomes `return finish("OK", f"dry-run built {built.pdf} {summary}", 0, toast_msg=None, pdf_path=built.pdf)` **but** `finish` must not toast on dry runs: it already checks `opts.dry_run`, so this is safe. The "already running" SKIP also goes through `_record_run` (call it directly there with `level="SKIP"`).
- After a successful `snap = refresh(settings)` (inside the `try`, after the `bad` computation), call `_ingest(home, snap, tz, log)`.
- `_Log` gains nothing; `INFO` is just another level word.

`lakota_grades/cli.py` `cmd_run`: `runner.RunOptions(..., trigger="cli")` (explicit, for the reader).

`lakota_grades/doctor.py`: add
```python
def _database(s: Settings, home: Path) -> str:
    from .web import db as webdb
    conn = webdb.open_db(home)
    try:
        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        n = conn.execute("SELECT count(*) FROM refreshes").fetchone()[0]
        m = conn.execute("SELECT count(*) FROM items").fetchone()[0]
        k = conn.execute("SELECT count(*) FROM flags WHERE cleared_at IS NULL").fetchone()[0]
    finally:
        conn.close()
    return f"{webdb.db_path(home)} schema {v}: {n} refreshes, {m} items, {k} active flags"
```
and insert `("database", _database)` into `PROBES` right after `("home", _home)`.

- [ ] **Step 4: Run the suite, commit**

Run the full suite; expected: green. `tests/test_print_sheet.py` still passes because its fixture home now also gets a `lakota.db` (harmless) and its `printed.txt`/log assertions are unchanged.

```bash
git add lakota_grades/runner.py lakota_grades/cli.py lakota_grades/doctor.py tests/test_runner.py tests/test_doctor.py
git commit -m "runner: ingest after refresh and record every run; doctor database probe

Closes #10

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: `web/reconcile.py`: "actionable" and the six reconciliation cases (issue #11)

**Files:**
- Create: `lakota_grades/web/reconcile.py`
- Test: `tests/test_reconcile.py`

**Interfaces:**
- Consumes: `db.latest_observations`, `stores.flags`, `late_rules.LateRules`, `open_items.HANDLED_FLAGS/MARKED_FLAGS`.
- Produces:
  - `reconcile.Case(kind: str, item_id: int, key: str, course: str, name: str, due: datetime | None, reason: str)` with `kind` in `("disagree", "one_source", "submitted_ungraded", "paper_no_grade", "past_credit", "stale_flag")`
  - `reconcile.open_sources(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime) -> set[str]` (which sources consider the item open)
  - `reconcile.is_actionable(item, obs, flag: str | None, rules, kid: str, now) -> bool`
  - `reconcile.cases(conn, student_id: int, *, rules, now) -> list[Case]` (sorted by due, then course, then name)
  - `reconcile.actionable_items(conn, student_id, *, rules, now) -> list[sqlite3.Row]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_reconcile.py
"""The rules that turn two gradebooks and a parent's flags into 'what is actionable' and
'what needs a human to decide'. Seeded rows, no ingest, so each case is explicit."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from lakota_grades import late_rules
from lakota_grades.web import db, reconcile
from lakota_grades.web.stores import flags as flagstore

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)
RULES = late_rules.LateRules(late_rules.Rule(late_days=7, credit="50%"), [], [])


def _seed(conn):
    with conn:
        conn.executemany("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (?, ?, '{}', 1)", [(1, "2026-09-10T06:00:00"), (2, "2026-09-15T06:00:00")])
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name, peer_course_id) VALUES (1, 1, 'canvas', 'Honors Biology S1', 'Honors Biology', 2)")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name, peer_course_id) VALUES (2, 1, 'hac', 'Honors Biology - 3', 'Honors Biology', 1)")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (3, 1, 'canvas', 'Latin I S1', 'Latin I')")


def _item(conn, id, key, name, due_days, course_id=1, kind="online"):
    due = (NOW + timedelta(days=due_days)).isoformat()
    with conn:
        conn.execute("INSERT INTO items(id, student_id, course_id, key, name, kind, due, first_seen, last_seen) VALUES (?, 1, ?, ?, ?, ?, ?, 1, 2)",
                     (id, course_id, key, name, kind, due))


def _obs(conn, item_id, source, refresh_id=2, **v):
    cols = {"state": None, "score": None, "grade": None, "submitted_at": None, "late": None, "missing": None, "excused": None}
    cols.update(v)
    with conn:
        conn.execute("INSERT INTO item_observations(refresh_id, item_id, source, state, score, grade, submitted_at, late, missing, excused) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (refresh_id, item_id, source, *cols.values()))


@pytest.fixture
def conn(tmp_path):
    c = db.open_db(tmp_path)
    _seed(c)
    return c


def _kinds(conn):
    return sorted((c.kind, c.key) for c in reconcile.cases(conn, 1, rules=RULES, now=NOW))


def test_missing_in_canvas_is_actionable_until_flagged_or_out_of_credit(conn):
    _item(conn, 1, "canvas:1", "WS 1", -2)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:1"]
    flagstore.set_flag(conn, 1, "done", now=NOW.isoformat())
    assert reconcile.actionable_items(conn, 1, rules=RULES, now=NOW) == []
    flagstore.clear(conn, 1, now=NOW.isoformat())
    _item(conn, 2, "canvas:2", "Old WS", -20)                       # past the 7-day credit window
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    assert [r["key"] for r in reconcile.actionable_items(conn, 1, rules=RULES, now=NOW)] == ["canvas:1"]
    assert ("past_credit", "canvas:2") in _kinds(conn)


def test_sources_disagree_both_directions(conn):
    _item(conn, 1, "canvas:1", "Quiz 1", -3)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    _obs(conn, 1, "hac", state="graded", score=28.0)
    _item(conn, 2, "canvas:2", "Lab 2", -3)
    _obs(conn, 2, "canvas", state="graded", score=9.0)
    _obs(conn, 2, "hac", state="ungraded")
    kinds = _kinds(conn)
    assert ("disagree", "canvas:1") in kinds and ("disagree", "canvas:2") in kinds
    reasons = {c.key: c.reason for c in reconcile.cases(conn, 1, rules=RULES, now=NOW)}
    assert "Canvas says MISSING" in reasons["canvas:1"] and "HAC" in reasons["canvas:1"]


def test_only_one_source_knows(conn):
    _item(conn, 1, "hac:Honors Biology:reading log", "reading log", -3, course_id=2, kind="")
    _obs(conn, 1, "hac", state="ungraded")
    _item(conn, 2, "canvas:2", "Vocab 3", -3)                           # course 1 has a HAC peer, but no HAC row for this
    _obs(conn, 2, "canvas", state="unsubmitted", missing=1)
    _item(conn, 3, "canvas:3", "Latin WS", -3, course_id=3)              # Latin has no HAC peer: not a case
    _obs(conn, 3, "canvas", state="unsubmitted", missing=1)
    kinds = _kinds(conn)
    assert ("one_source", "hac:Honors Biology:reading log") in kinds and ("one_source", "canvas:2") in kinds
    assert ("one_source", "canvas:3") not in kinds


def test_submitted_ungraded_and_paper_no_grade(conn):
    _item(conn, 1, "canvas:1", "Essay", -3)
    _obs(conn, 1, "canvas", state="submitted", submitted_at="2026-09-12T20:00:00-04:00")
    _item(conn, 2, "canvas:2", "Worksheet (paper)", -3, kind="paper")
    _obs(conn, 2, "canvas", state="unsubmitted")
    _item(conn, 3, "canvas:3", "Future paper", 3, kind="paper")
    _obs(conn, 3, "canvas", state="unsubmitted")
    kinds = _kinds(conn)
    assert ("submitted_ungraded", "canvas:1") in kinds and ("paper_no_grade", "canvas:2") in kinds
    assert not any(k == "canvas:3" for _, k in kinds)


def test_stale_flags(conn):
    _item(conn, 1, "canvas:1", "WS 1", -3)
    _obs(conn, 1, "canvas", refresh_id=1, state="unsubmitted", missing=1)
    flagstore.set_flag(conn, 1, "done", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 1, "canvas", refresh_id=2, state="graded", score=0.0)      # a zero posted after the flag
    _item(conn, 2, "canvas:2", "Lab", -3)
    _obs(conn, 2, "canvas", refresh_id=1, state="submitted")
    flagstore.set_flag(conn, 2, "follow_up", now="2026-09-12T08:00:00-04:00")
    _obs(conn, 2, "canvas", refresh_id=2, state="graded", score=8.0)      # graded after the flag
    _item(conn, 3, "canvas:3", "Fine", -3)
    _obs(conn, 3, "canvas", refresh_id=1, state="unsubmitted", missing=1)
    flagstore.set_flag(conn, 3, "done", now=NOW.isoformat())                # flag newer than any observation: not stale
    kinds = _kinds(conn)
    assert ("stale_flag", "canvas:1") in kinds and ("stale_flag", "canvas:2") in kinds
    assert ("stale_flag", "canvas:3") not in kinds


def test_cases_are_sorted_and_carry_context(conn):
    _item(conn, 1, "canvas:1", "B item", -1)
    _obs(conn, 1, "canvas", state="unsubmitted", missing=1)
    _obs(conn, 1, "hac", state="graded", score=5.0)
    _item(conn, 2, "canvas:2", "A item", -5)
    _obs(conn, 2, "canvas", state="submitted", submitted_at="x")
    cs = reconcile.cases(conn, 1, rules=RULES, now=NOW)
    assert [c.key for c in cs] == ["canvas:2", "canvas:1"]
    assert cs[1].course == "Honors Biology" and cs[1].name == "B item" and cs[1].due is not None
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_reconcile.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Write `reconcile.py`**

```python
# lakota_grades/web/reconcile.py
"""What is actionable, and what the sources cannot settle by themselves.

Pure functions over database rows. An item is actionable when (1) at least one source
still considers it open, (2) the late-work rules say it still earns credit, and (3) no
handled flag (done / excused / ignore) is set. The six case kinds are the situations the
Reconcile page shows a parent, each with a one-line reason and the flag menu.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..open_items import HANDLED_FLAGS, MARKED_FLAGS
from . import db

KINDS = ("disagree", "one_source", "submitted_ungraded", "paper_no_grade", "past_credit", "stale_flag")


@dataclass(frozen=True)
class Case:
    kind: str
    item_id: int
    key: str
    course: str
    name: str
    due: datetime | None
    reason: str


def _due(item: sqlite3.Row) -> datetime | None:
    return datetime.fromisoformat(item["due"]) if item["due"] else None


def _score_text(o: sqlite3.Row | None) -> str:
    if o is None or o["score"] is None:
        return "no grade"
    return f"{o['score']:g}"


def open_sources(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime) -> set[str]:
    """Which sources consider the item open (the kid can still act on it)."""
    out: set[str] = set()
    due = _due(item)
    c = obs.get("canvas")
    if c is not None and not c["excused"]:
        past = due is not None and due < now
        unsubmitted = c["state"] in ("unsubmitted", None) and c["score"] is None
        if c["missing"] or (c["state"] == "graded" and c["score"] == 0) or (c["late"] and c["score"] is None) or (past and unsubmitted):
            out.add("canvas")
    h = obs.get("hac")
    if h is not None and h["score"] is None and due is not None and due < now - timedelta(days=1):
        out.add("hac")
    return out


def is_actionable(item: sqlite3.Row, obs: dict[str, sqlite3.Row], flag: str | None, rules, kid: str, now: datetime) -> bool:
    if flag in HANDLED_FLAGS or not open_sources(item, obs, now):
        return False
    due = _due(item)
    return due is None or now <= rules.deadline(kid, item["course_name"], due)


def _rows(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT i.*, c.name AS course_name, c.short_name AS course_short, c.source AS course_source, c.peer_course_id,
                  s.key AS kid, f.flag AS flag, f.set_at AS flag_set_at
           FROM items i JOIN courses c ON c.id = i.course_id JOIN students s ON s.id = i.student_id
           LEFT JOIN flags f ON f.item_id = i.id AND f.cleared_at IS NULL
           WHERE i.student_id = ?""", (student_id,)).fetchall()


def actionable_items(conn: sqlite3.Connection, student_id: int, *, rules, now: datetime) -> list[sqlite3.Row]:
    latest = db.latest_observations(conn, student_id)
    out = [r for r in _rows(conn, student_id) if is_actionable(r, latest.get(r["id"], {}), r["flag"], rules, r["kid"], now)]
    return sorted(out, key=lambda r: (r["due"] or "", r["course_short"], r["name"]))


def _refresh_time(conn: sqlite3.Connection, refresh_id: int) -> str:
    row = conn.execute("SELECT started_at FROM refreshes WHERE id = ?", (refresh_id,)).fetchone()
    return row[0] if row else ""


def cases(conn: sqlite3.Connection, student_id: int, *, rules, now: datetime) -> list[Case]:
    latest = db.latest_observations(conn, student_id)
    found: list[Case] = []
    for r in _rows(conn, student_id):
        obs = latest.get(r["id"], {})
        c, h = obs.get("canvas"), obs.get("hac")
        due = _due(r)
        past = due is not None and due < now
        opened = open_sources(r, obs, now)
        flag = r["flag"]

        def add(kind: str, reason: str) -> None:
            found.append(Case(kind, r["id"], r["key"], r["course_short"], r["name"], due, reason))

        # 1. the sources disagree
        if c is not None and h is not None:
            if (c["missing"] or (c["state"] == "graded" and c["score"] == 0)) and h["score"] not in (None, 0):
                add("disagree", f"Canvas says {'MISSING' if c['missing'] else 'ZERO'}, HAC shows {_score_text(h)}")
            elif h["score"] is None and c["state"] == "graded" and c["score"] not in (None, 0):
                add("disagree", f"HAC has no grade, Canvas shows {_score_text(c)}")
        # 2. only one source knows
        if r["key"].startswith("hac:") and "hac" in opened:
            add("one_source", "Only HAC lists this; probably paper work")
        elif c is not None and h is None and past and r["peer_course_id"] is not None and "canvas" in opened:
            add("one_source", "Not in HAC's gradebook yet")
        # 3. submitted, not graded
        if c is not None and c["submitted_at"] and c["score"] is None and past:
            add("submitted_ungraded", "Turned in, not graded yet")
        # 4. paper or in-class, past due, no grade
        if c is not None and r["kind"] in ("paper", "in class") and past and c["state"] in ("unsubmitted", None) and c["score"] is None:
            add("paper_no_grade", f"{r['kind'].capitalize()} work with no grade: ask")
        # 5. past the credit window
        if opened and flag not in HANDLED_FLAGS and due is not None:
            deadline = rules.deadline(r["kid"], r["course_name"], due)
            if now > deadline:
                add("past_credit", f"No longer earns credit (window closed {deadline:%a %m/%d}); flag ignore to hide")
        # 6. a flag the sources have overtaken
        if flag and c is not None and r["flag_set_at"] and _refresh_time(conn, c["refresh_id"]) > r["flag_set_at"]:
            if flag in HANDLED_FLAGS and (c["missing"] or (c["state"] == "graded" and c["score"] == 0)):
                add("stale_flag", f"Flagged {flag} but Canvas now says {'MISSING' if c['missing'] else 'ZERO'}")
            elif flag in MARKED_FLAGS and c["score"] is not None:
                add("stale_flag", f"Flagged {flag} but it is graded now ({_score_text(c)})")
    return sorted(found, key=lambda x: (x.due or datetime.max.replace(tzinfo=now.tzinfo), x.course, x.name))
```

- [ ] **Step 4: Run the tests, the suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_reconcile.py -q` — 6 passed; then the full suite.

```bash
git add lakota_grades/web/reconcile.py tests/test_reconcile.py
git commit -m "web.reconcile: the actionable rule and the six reconciliation cases

Closes #11

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Done when

- `lakota.db` appears in `~/.lakota-grades` after the next scheduled run on Tony's box, with one `refreshes` row and one `runs` row per run; the sheet prints exactly as before when no flags are set.
- A flag set directly in the database (Plan B brings the UI) removes an item from the next sheet, and the sheet says how many items were handled.
- `lakota-grades doctor` shows a `database` line.
- Issues #5 to #11 are closed by the commits; CI is green on both runners.
- Task 1's Step 4 records the key-stability findings for Plan B's Reconcile page.

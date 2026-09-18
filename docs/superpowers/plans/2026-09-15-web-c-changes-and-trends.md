# Web App Plan C: Changes and Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the change log Plan A has been filling into the two pages that answer "what happened while I wasn't looking" and "is this getting better or worse": a Changes feed since a chosen moment, and Trends with grade lines per class and weekly missing, late and on-time counts.

**Architecture:** Two new read-only stores over the existing tables. `web/stores/changes.py` walks `item_observations`, `grade_observations`, `items.first_seen` and `flags` between two refreshes and returns one ordered list of typed events; `web/stores/trends.py` reduces the same tables into series a chart can take. Both are pure reads with no new schema. The pages are ordinary server-rendered Jinja; the charts are the uPlot that Plan B part 1 already vendored, fed from a small JSON endpoint so the template stays free of data.

**Tech Stack:** Python 3.12, `sqlite3` (stdlib), FastAPI/Jinja2/htmx as in Plan B, vendored uPlot 1.6.31 (`/static/uplot.min.js`, global `uPlot`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-lakota-web-app-design.md`, sections 4 (the change log is why the data is shaped this way), 5 (Changes and Trends), 12 (testing), 13.C. GitHub milestone "Web app C: Time", issues **#20** (Changes feed — Tasks 1 and 2), **#21** (trend queries — Task 3) and **#22** (Trends page with charts — Task 4). Issue #33 also carries the `plan-c` label but is Plan B part 2's residual list, not a task here. Residuals from earlier plans live in issues #31, #32 and #33.

## Global Constraints

- **Read-only.** This plan adds no table, no column and no migration, and writes nothing. `SCHEMA_VERSION` stays 1. Every query is a `SELECT`.
- All SQL lives in `web/db.py` or `web/stores/*.py`. Routes never contain SQL; templates never compute beyond display formatting.
- Jinja2 autoescape stays on and nothing is marked `|safe`. htmx requests get the template's `partial` block, plain requests the full page — `app.render` already does this.
- Times are ISO strings in the database and are rendered through the existing filters (`wd_md_time`, `md`, `time12`). Parse with `datetime.fromisoformat`; compare with `reconcile.comparable(a, b)` when either side may differ in offset, never as strings.
- A page must render with an empty database, with one refresh, and with a kid who has no courses. "Nothing yet" is a sentence the parent reads, never a traceback.
- The charts take their data from a JSON endpoint under `/trends/…`; the page template contains no embedded series. uPlot is loaded only on the Trends page and the course page, never from `base.html`.
- No credential is read by these routes, and nothing is sent anywhere. Both pages work from the LAN exactly as the Kid page does.
- The full suite (`env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`, **337 passed** at the start of this plan) stays green and pristine on Linux and in CI on both runners.
- Commit after every task with the trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`, and the issue line each task's commit block gives verbatim (`Part of #20`, `Closes #20`, `Closes #21`, `Closes #22`).

## What Plans A and B left (read before any task)

| Module | You use |
|---|---|
| `web/db.py` | `open_db(home)`, `now_iso(tz)`, `latest_observations(conn, student_id) -> {item_id: {source: Row}}`; schema v1 (below) |
| `web/reconcile.py` | `live_items(conn, student_id, now)`, `due_of(row)`, `comparable(a, b) -> (a, b)`, `open_sources`, `is_actionable`, `cases`, `KINDS` |
| `web/stores/students.py` | `visible(conn)`, `by_key`, `by_id`, `courses(conn, student_id)`, `course(conn, course_id)`, `latest_grades`, `grade_history(conn, course_id)`, `owner_of_item` |
| `web/stores/items.py` | `ItemView` (fields `id, key, name, course_id, course_short, course_name, kind, points, due, sources, open_in, actionable, upcoming, flag, flag_text, status, canvas, hac, notes, case_kinds`; properties `overdue`, `handled`), `status_text(item, obs, now)`, `list_items`, `one`, `dashboard_counts`, `with_cases` |
| `web/stores/refreshes.py` | `latest(conn)` |
| `web/app.py` | `create_app(settings, *, home=None, worker=False)`, `AppState` (`home`, `settings`, `tz`, `clock`, `now()`, `rules()`, `extra`), `get_state`, `get_db`, `Db`, `State`, `render(request, conn, name, /, status_code=200, **ctx)`, `render_partial(request, conn, name, /, **ctx)`, `is_htmx`, `page_context` (supplies `students`, `refresh`, `sources`, `last_run`, `now`, `job`, `jobs`, `warnings`), `student_or_404(conn, key)` |
| `web/templates/base.html` | the rail — add Changes and Trends under a new `Time` group |
| `web/static/` | `uplot.min.js` (global `uPlot`), `uplot.min.css`, `app.js`, `app.css` |
| `open_items.py` | `school_year_start(now)`, `HANDLED_FLAGS`, `MARKED_FLAGS` |
| `dates.py` | `md`, `wd_md`, `time12`, `wd_md_time` |
| `tests/web_fixtures.py` | `TZ`, `NOW` (2026-09-15 14:00 EDT), `snapshot()`, `seed(home, snap=None, now=NOW)`, `app_for(home, now=NOW, worker=False)` — read its docstring for the ten items it creates |

Schema columns this plan reads (all from Plan A's v1, unchanged):

```
refreshes(id, started_at, finished_at, sources, ok)
students(id, key, name, hidden)
courses(id, student_id, source, external_id, name, short_name, teacher, teacher_email, peer_course_id, hidden)
items(id, student_id, course_id, key, name, kind, points, due, assigned, is_assessment, first_seen, last_seen)
item_observations(id, refresh_id, item_id, source, state, score, grade, submitted_at, late, missing, excused, published)
grade_observations(id, refresh_id, course_id, average, letter, current, final, last_updated)
flags(id, item_id, flag, text, set_at, cleared_at)
notes(id, target_type, target_id, body, created_at, updated_at)
```

`item_observations` and `grade_observations` are a **change log**: Plan A's ingest writes a row only when a source's view of that item or course differs from the previous observation. So two consecutive observation rows for one item and source are, by construction, a change — that is what makes both pages cheap.

## File map

| Path | Responsibility |
|---|---|
| `lakota_grades/web/stores/changes.py` (new) | `Event`, `since(conn, *, since, until=None, student_id=None, kinds=None)` — the feed |
| `lakota_grades/web/stores/trends.py` (new) | `GradeSeries`, `WeekCounts`, `grade_series`, `weekly_counts`, `open_days` — the numbers behind the charts |
| `lakota_grades/web/routes/changes.py` (new) | `GET /changes` |
| `lakota_grades/web/routes/trends.py` (new) | `GET /trends`, `GET /trends/grades.json`, `GET /trends/weekly.json` |
| `lakota_grades/web/templates/changes.html`, `_change_rows.html` (new) | the feed and its htmx-swappable body |
| `lakota_grades/web/templates/trends.html`, `_chart.html` (new) | the page and one reusable chart block |
| `lakota_grades/web/templates/base.html`, `course.html` (modify) | the rail's Time group; the course page's grade chart |
| `lakota_grades/web/static/app.js`, `app.css` (modify) | the uPlot bootstrap and the chart styles |
| `lakota_grades/web/app.py` (modify) | include the two routers |
| `tests/web_fixtures.py` (modify) | `history(home)` — a multi-refresh fixture both pages need |
| `tests/test_web_changes_store.py`, `test_web_trends_store.py`, `test_web_changes_page.py`, `test_web_trends_page.py` (new) | |

---

### Task 1: A multi-refresh fixture, and `web/stores/changes.py` (issue #20, part 1 of 2)

Everything in this plan needs history, and the existing fixture has exactly one refresh. This task builds the fixture both pages use, then the feed store over it.

**Files:**
- Modify: `tests/web_fixtures.py`
- Create: `lakota_grades/web/stores/changes.py`, `tests/test_web_changes_store.py`

**Interfaces:**
- Consumes: `db.open_db`, `ingest.record`, `students`, `reconcile.comparable`.
- Produces:
  - `tests/web_fixtures.history(home, now=NOW) -> sqlite3.Connection` — ingests three snapshots (see Step 1) and returns the open connection; `REFRESH_TIMES = ("2026-09-13T06:00:00-04:00", "2026-09-14T06:00:00-04:00", "2026-09-15T13:50:00-04:00")`
  - `changes.KINDS = ("new_item", "grade_posted", "grade_changed", "now_missing", "cleared", "flag_set", "flag_cleared", "course_grade")`
  - `changes.Event(kind, at, student_key, student_id, item_id, item_name, course_short, source, detail, flag)` — a frozen dataclass; `item_id`/`item_name`/`course_short`/`source`/`flag` are `None` where they do not apply
  - `changes.since(conn, *, since: datetime, until: datetime | None = None, student_id: int | None = None, kinds: tuple[str, ...] | None = None) -> list[Event]` — newest first, then by student key and item name
  - `changes.WINDOWS = (("1d", "Since yesterday", 1), ("3d", "Last 3 days", 3), ("7d", "Last week", 7), ("30d", "Last month", 30))` and `changes.window_start(key, now) -> datetime`

- [ ] **Step 1: The history fixture**

Append to `tests/web_fixtures.py` (keep `snapshot()` untouched — every existing test depends on it):

```python
REFRESH_TIMES = ("2026-09-13T06:00:00-04:00", "2026-09-14T06:00:00-04:00", "2026-09-15T13:50:00-04:00")


def _history_snapshots() -> list[dict]:
    """Three days of one household, so the change log has something to say.

    Day 1 (9/13): Quiz 1 is ungraded everywhere; Homework 4 is not missing yet; no Vocabulary.
    Day 2 (9/14): HAC posts Quiz 1 at 28/30 and the English average rises; Homework 4 goes
                  MISSING in Canvas; Vocabulary appears for the first time.
    Day 3 (9/15): Canvas marks Quiz 1 MISSING (it disagrees with HAC -- the reconcile case),
                  Essay draft is submitted, Safety quiz is graded 0, English average slips.
    """
    day1 = snapshot()
    eng = day1["students"]["Alex"]["canvas"]["courses"][0]
    eng["grade"]["current_score"] = 93.0
    eng["assignments"] = [a for a in eng["assignments"] if a["name"] != "Vocabulary"]
    for a in eng["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"] = False
        if a["name"] == "Essay draft":
            a["state"], a["submitted_at"] = "unsubmitted", None
    day1["students"]["Alex"]["canvas"]["courses"][1]["assignments"][0]["missing"] = False
    hac_eng = day1["students"]["Alex"]["hac"]["classes"][0]
    hac_eng["marking_period_avg"] = 85.0
    hac_eng["assignments"] = [_h("Quiz 1", "09/12/2026", None, points=30.0), _h("Participation", "09/08/2026", None)]
    sci = day1["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci["assignments"]:
        if a["name"] == "Safety quiz":
            a["state"], a["score"], a["grade"] = "unsubmitted", None, None
    day1["fetched_at"] = REFRESH_TIMES[0]

    day2 = snapshot()
    eng2 = day2["students"]["Alex"]["canvas"]["courses"][0]
    eng2["grade"]["current_score"] = 93.0
    for a in eng2["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"] = False
        if a["name"] == "Essay draft":
            a["state"], a["submitted_at"] = "unsubmitted", None
    sci2 = day2["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci2["assignments"]:
        if a["name"] == "Safety quiz":
            a["state"], a["score"], a["grade"] = "unsubmitted", None, None
    day2["fetched_at"] = REFRESH_TIMES[1]

    day3 = snapshot()                                  # the fixture every other test already knows
    day3["fetched_at"] = REFRESH_TIMES[2]
    return [day1, day2, day3]


def history(home: Path, now: datetime = NOW) -> sqlite3.Connection:
    """Three refreshes of the standard household, oldest first. Returns the open connection."""
    conn = db.open_db(home)
    for snap in _history_snapshots():
        ingest.record(conn, snap, tz=TZ, now=datetime.fromisoformat(snap["fetched_at"]))
    return conn
```

- [ ] **Step 2: Write the failing store test**

`tests/test_web_changes_store.py`:

```python
"""The Changes feed: what the change log says happened between two moments."""
from __future__ import annotations

from datetime import datetime, timedelta

from lakota_grades.web import db
from lakota_grades.web.stores import changes, flags, students
from tests.web_fixtures import NOW, REFRESH_TIMES, TZ, history


def _at(i: int) -> datetime:
    return datetime.fromisoformat(REFRESH_TIMES[i])


def _kinds(events):
    return sorted({e.kind for e in events})


def _find(events, kind, name=None):
    return [e for e in events if e.kind == kind and (name is None or e.item_name == name)]


def test_empty_database_has_no_events(tmp_path):
    conn = db.open_db(tmp_path)
    assert changes.since(conn, since=NOW - timedelta(days=30)) == []
    conn.close()


def test_the_whole_history_reports_every_kind(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    assert _kinds(events) == ["cleared", "course_grade", "grade_posted", "new_item", "now_missing"]
    # Day 1 has nine items (the ten of the standard fixture, less Vocabulary); Vocabulary joins on day 2.
    assert len(_find(events, "new_item")) == 10
    conn.close()


def test_the_last_day_reports_only_that_day(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(2) - timedelta(minutes=1))
    names = {(e.kind, e.item_name) for e in events}
    assert ("new_item", "Vocabulary") not in names                 # that was yesterday
    assert ("now_missing", "Quiz 1") in names                      # Canvas turned on missing today
    assert ("grade_posted", "Safety quiz") in names                # 0 is a grade
    assert ("cleared", "Essay draft") in names                     # submitted: no longer open
    conn.close()


def test_grade_posted_and_changed_carry_readable_detail(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    (posted,) = _find(events, "grade_posted", "Quiz 1")
    assert posted.source == "hac" and posted.detail == "28/30" and posted.course_short == "Honors English 9"
    assert posted.student_key == "Alex" and posted.at == _at(1)
    (avg,) = [e for e in _find(events, "course_grade") if e.course_short == "Honors English 9" and e.at == _at(1)]
    assert avg.detail == "HAC average 85 → 88" and avg.item_id is None
    conn.close()


def test_new_item_names_its_course_and_time(tmp_path):
    conn = history(tmp_path)
    (vocab,) = _find(changes.since(conn, since=_at(0)), "new_item", "Vocabulary")
    assert vocab.at == _at(1) and vocab.course_short == "Honors English 9" and vocab.student_key == "Alex"
    conn.close()


def test_now_missing_and_cleared_are_opposites(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    (hw,) = _find(events, "now_missing", "Homework 4")
    assert hw.at == _at(1) and hw.source == "canvas" and "missing" in hw.detail.lower()
    (essay,) = _find(events, "cleared", "Essay draft")
    assert essay.at == _at(2) and "submitted" in essay.detail.lower()
    conn.close()


def test_flags_appear_and_disappear(tmp_path):
    conn = history(tmp_path)
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    flags.set_flag(conn, quiz, "follow_up", now="2026-09-15T15:00:00-04:00", text="emailed Mr Hoch")
    events = changes.since(conn, since=_at(2))
    (f,) = _find(events, "flag_set", "Quiz 1")
    assert f.flag == "follow_up" and "emailed Mr Hoch" in f.detail and f.at == datetime.fromisoformat("2026-09-15T15:00:00-04:00")
    flags.clear(conn, quiz, now="2026-09-15T16:00:00-04:00")
    events = changes.since(conn, since=_at(2))
    assert _find(events, "flag_cleared", "Quiz 1")
    conn.close()


def test_filters_by_student_and_kind(tmp_path):
    conn = history(tmp_path)
    sam = students.by_key(conn, "Sam")["id"]
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1), student_id=sam)
    assert {e.student_key for e in events} == {"Sam"}
    only_new = changes.since(conn, since=_at(0) - timedelta(minutes=1), kinds=("new_item",))
    assert _kinds(only_new) == ["new_item"]
    assert changes.since(conn, since=_at(0) - timedelta(minutes=1), kinds=("nonsense",)) == []
    conn.close()


def test_until_bounds_the_window(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1), until=_at(1))
    assert all(e.at <= _at(1) for e in events) and events
    conn.close()


def test_events_are_newest_first(tmp_path):
    conn = history(tmp_path)
    events = changes.since(conn, since=_at(0) - timedelta(minutes=1))
    assert [e.at for e in events] == sorted((e.at for e in events), reverse=True)
    conn.close()


def test_window_start_reads_the_keys(tmp_path):
    assert changes.window_start("1d", NOW) == NOW - timedelta(days=1)
    assert changes.window_start("7d", NOW) == NOW - timedelta(days=7)
    assert changes.window_start("nonsense", NOW) == NOW - timedelta(days=1)     # the default window
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_changes_store.py`
Expected: FAIL (`ImportError: cannot import name 'changes'`).

- [ ] **Step 3: Implement `web/stores/changes.py`**

```python
"""The Changes feed: what the sources and the parent did since a chosen moment.

`item_observations` and `grade_observations` are a change log -- Plan A's ingest writes a row
only when a source's view differs from the one before -- so two consecutive rows for one item
and source *are* a change, and the feed is a walk over consecutive pairs rather than a diff of
two whole snapshots. `items.first_seen` supplies the "new" events and the `flags` table
supplies the parent's own, which are the ones no gradebook can tell them about.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

KINDS = ("new_item", "grade_posted", "grade_changed", "now_missing", "cleared", "flag_set", "flag_cleared", "course_grade")

#: The feed's window buttons: (key, label, days).
WINDOWS = (("1d", "Since yesterday", 1), ("3d", "Last 3 days", 3), ("7d", "Last week", 7), ("30d", "Last month", 30))
DEFAULT_WINDOW = "1d"

LABELS = {
    "new_item": "New", "grade_posted": "Grade posted", "grade_changed": "Grade changed",
    "now_missing": "Now missing", "cleared": "Cleared", "flag_set": "You flagged",
    "flag_cleared": "You cleared a flag", "course_grade": "Class average",
}


@dataclass(frozen=True)
class Event:
    kind: str
    at: datetime
    student_key: str
    student_id: int
    item_id: int | None = None
    item_name: str | None = None
    course_short: str | None = None
    source: str | None = None
    detail: str = ""
    flag: str | None = None

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, self.kind)


def window_start(key: str, now: datetime) -> datetime:
    days = next((d for k, _, d in WINDOWS if k == key), None)
    if days is None:
        days = next(d for k, _, d in WINDOWS if k == DEFAULT_WINDOW)
    return now - timedelta(days=days)


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _num(v) -> str:
    """9.0 -> '9', 88.5 -> '88.5'; a grade a parent reads, not a float repr."""
    return "" if v is None else f"{v:g}"


def _score_text(score, grade, points) -> str:
    if score is None:
        return str(grade) if grade else "no score"
    return f"{_num(score)}/{_num(points)}" if points else _num(score)


def _item_rows(conn: sqlite3.Connection, student_id: int | None) -> list[sqlite3.Row]:
    """Every item observation in refresh order, with what the row needs to describe itself."""
    sql = """SELECT o.*, r.started_at AS at, i.name AS item_name, i.points AS points, i.student_id AS student_id,
                    s.key AS student_key, c.short_name AS course_short
             FROM item_observations o
             JOIN refreshes r ON r.id = o.refresh_id
             JOIN items i ON i.id = o.item_id
             JOIN students s ON s.id = i.student_id
             JOIN courses c ON c.id = i.course_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY o.item_id, o.source, o.refresh_id"
    return conn.execute(sql, args).fetchall()


def _observation_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    """A grade appearing or changing, an item turning missing, an item ceasing to be open."""
    out: list[Event] = []
    prev: dict[tuple[int, str], sqlite3.Row] = {}
    for row in _item_rows(conn, student_id):
        key = (row["item_id"], row["source"])
        before = prev.get(key)
        prev[key] = row
        if before is None:
            continue                       # the first sighting of an item is a `new_item`, below
        at = _dt(row["at"])
        common = dict(at=at, student_key=row["student_key"], student_id=row["student_id"],
                      item_id=row["item_id"], item_name=row["item_name"],
                      course_short=row["course_short"], source=row["source"])
        had, has = before["score"] is not None, row["score"] is not None
        if not had and has:
            out.append(Event("grade_posted", detail=_score_text(row["score"], row["grade"], row["points"]), **common))
        elif had and has and before["score"] != row["score"]:
            out.append(Event("grade_changed",
                             detail=f"{_score_text(before['score'], before['grade'], row['points'])}"
                                    f" → {_score_text(row['score'], row['grade'], row['points'])}", **common))
        if not before["missing"] and row["missing"]:
            out.append(Event("now_missing", detail="marked missing", **common))
        elif before["missing"] and not row["missing"]:
            out.append(Event("cleared", detail="no longer missing", **common))
        if not before["submitted_at"] and row["submitted_at"]:
            out.append(Event("cleared", detail="submitted", **common))
        if not before["excused"] and row["excused"]:
            out.append(Event("cleared", detail="excused", **common))
    return out


def _new_item_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    sql = """SELECT i.id, i.name, r.started_at AS at, s.key AS student_key, i.student_id AS student_id,
                    c.short_name AS course_short
             FROM items i JOIN refreshes r ON r.id = i.first_seen
             JOIN students s ON s.id = i.student_id JOIN courses c ON c.id = i.course_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    return [Event("new_item", _dt(r["at"]), r["student_key"], r["student_id"], item_id=r["id"],
                  item_name=r["name"], course_short=r["course_short"], detail="first seen")
            for r in conn.execute(sql, args)]


def _course_grade_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    """A class average moving. One event per course per refresh that changed something."""
    sql = """SELECT g.*, r.started_at AS at, c.short_name AS course_short, c.source AS course_source,
                    c.student_id AS student_id, s.key AS student_key
             FROM grade_observations g JOIN refreshes r ON r.id = g.refresh_id
             JOIN courses c ON c.id = g.course_id JOIN students s ON s.id = c.student_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND c.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY g.course_id, g.refresh_id"
    out: list[Event] = []
    prev: dict[int, sqlite3.Row] = {}
    for row in conn.execute(sql, args):
        before = prev.get(row["course_id"])
        prev[row["course_id"]] = row
        if before is None:
            continue
        for field, word in (("average", "HAC average"), ("current", "Canvas current")):
            a, b = before[field], row[field]
            if a is not None and b is not None and a != b:
                out.append(Event("course_grade", _dt(row["at"]), row["student_key"], row["student_id"],
                                 course_short=row["course_short"], source=row["course_source"],
                                 detail=f"{word} {_num(a)} → {_num(b)}"))
    return out


def _flag_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    sql = """SELECT f.*, i.name AS item_name, i.student_id AS student_id, s.key AS student_key,
                    c.short_name AS course_short
             FROM flags f JOIN items i ON i.id = f.item_id
             JOIN students s ON s.id = i.student_id JOIN courses c ON c.id = i.course_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    out: list[Event] = []
    for r in conn.execute(sql, args):
        common = dict(student_key=r["student_key"], student_id=r["student_id"], item_id=r["item_id"],
                      item_name=r["item_name"], course_short=r["course_short"], flag=r["flag"])
        word = r["flag"].replace("_", " ")
        out.append(Event("flag_set", _dt(r["set_at"]), detail=f"{word}: {r['text']}" if r["text"] else word, **common))
        if r["cleared_at"]:
            out.append(Event("flag_cleared", _dt(r["cleared_at"]), detail=f"was {word}", **common))
    return out


def since(conn: sqlite3.Connection, *, since: datetime, until: datetime | None = None,
          student_id: int | None = None, kinds: tuple[str, ...] | None = None) -> list[Event]:
    """Everything that happened in (`since`, `until`], newest first.

    `kinds` filters to those event kinds; an unknown kind simply matches nothing, so a
    hand-typed query string cannot 500 the page.
    """
    from .. import reconcile
    events = (_observation_events(conn, student_id) + _new_item_events(conn, student_id)
              + _course_grade_events(conn, student_id) + _flag_events(conn, student_id))
    if kinds is not None:
        events = [e for e in events if e.kind in kinds]
    kept = []
    for e in events:
        if e.at is None:
            continue
        a, b = reconcile.comparable(e.at, since)
        if a <= b:
            continue
        if until is not None:
            a2, b2 = reconcile.comparable(e.at, until)
            if a2 > b2:
                continue
        kept.append(e)
    kept.sort(key=lambda e: (e.at, e.student_key, e.item_name or "", e.kind), reverse=True)
    return kept
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_changes_store.py`
Expected: PASS. If `test_the_whole_history_reports_every_kind` disagrees on the count, print the events and count what the fixture really produces before touching anything: day 1 creates nine items (Alex six Canvas English assignments, the HAC-only Participation, one Algebra; Sam two) because Vocabulary is removed, and day 2 adds Vocabulary, so ten `new_item` events. Fix the fixture, not the assertion.

- [ ] **Step 4: Full suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`
Expected: 337 + the new tests, pristine.

```bash
git add lakota_grades/web/stores/changes.py tests/test_web_changes_store.py tests/web_fixtures.py
git commit -m "web.stores.changes: the change log as a feed of events

Part of #20

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The Changes page (issue #20, part 2 of 2 — this commit closes it)

**Files:**
- Create: `lakota_grades/web/routes/changes.py`, `templates/changes.html`, `templates/_change_rows.html`, `tests/test_web_changes_page.py`
- Modify: `lakota_grades/web/app.py` (include the router), `templates/base.html` (the Time group in the rail)

**Interfaces:**
- Consumes: Task 1's `changes.since/WINDOWS/window_start/KINDS/Event.label`, `app.render`, `students.visible`, `students.by_key`.
- Produces: `GET /changes?window=&kid=&kind=` (htmx → the `partial` block, which is the table only).

- [ ] **Step 1: Write the failing page test**

`tests/test_web_changes_page.py`:

```python
"""The Changes page: what happened while I wasn't looking."""
from __future__ import annotations

from tests.web_fixtures import app_for, history, seed


def test_empty_database_says_nothing_yet(tmp_path):
    c = app_for(tmp_path)
    r = c.get("/changes")
    assert r.status_code == 200 and "Nothing has changed" in r.text
    assert "Since yesterday" in r.text                     # the window buttons render anyway


def test_the_default_window_is_since_yesterday(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes").text
    assert "Quiz 1" in body and "Now missing" in body      # today's Canvas change
    assert "Vocabulary" not in body                        # yesterday's new item is outside 1 day


def test_a_longer_window_reaches_further_back(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=7d").text
    assert "Vocabulary" in body and "New" in body
    assert "Grade posted" in body and "28/30" in body
    assert "Class average" in body and "→" in body


def test_filters_by_kid_and_kind(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/changes?window=7d&kid=Sam").text
    assert "Safety quiz" in body and "Quiz 1" not in body
    body = c.get("/changes?window=7d&kind=new_item").text
    assert "Vocabulary" in body and "Now missing" not in body
    assert c.get("/changes?window=7d&kind=nonsense").status_code == 200      # unknown kind: no crash
    assert c.get("/changes?window=7d&kid=Nobody").status_code == 404


def test_htmx_gets_the_table_only(tmp_path):
    history(tmp_path).close()
    r = app_for(tmp_path).get("/changes?window=7d", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "Quiz 1" in r.text


def test_rows_link_to_the_kid_and_the_item(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=7d").text
    assert 'href="/kids/Alex"' in body
    assert 'hx-get="/items/' in body                       # the row expands the same detail the Kid page uses


def test_a_flag_shows_as_the_parents_own_change(tmp_path):
    conn = history(tmp_path)
    from lakota_grades.web.stores import flags
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    flags.set_flag(conn, quiz, "ask_teacher", now="2026-09-15T15:00:00-04:00", text="emailed")
    conn.close()
    body = app_for(tmp_path).get("/changes").text
    assert "You flagged" in body and "ask teacher" in body and "emailed" in body


def test_one_refresh_only_still_renders(tmp_path):
    seed(tmp_path).close()                                  # the single-refresh fixture
    body = app_for(tmp_path).get("/changes?window=7d").text
    assert "New" in body and "Quiz 1" in body               # first_seen events exist with one refresh
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_changes_page.py`
Expected: FAIL (404).

- [ ] **Step 2: The route**

`lakota_grades/web/routes/changes.py`:

```python
"""The Changes feed: everything that moved since a chosen moment."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render, student_or_404
from ..stores import changes

router = APIRouter()


@router.get("/changes")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    q = request.query_params
    window = q.get("window") or changes.DEFAULT_WINDOW
    kid = q.get("kid") or None
    kind = q.get("kind") or None
    student = student_or_404(conn, kid) if kid else None
    now = state.now()
    events = changes.since(conn, since=changes.window_start(window, now),
                           student_id=student["id"] if student else None,
                           kinds=(kind,) if kind else None)
    return render(request, conn, "changes.html", current="changes", events=events, window=window,
                  kid=kid, kind=kind, WINDOWS=changes.WINDOWS, KINDS=changes.KINDS, LABELS=changes.LABELS)
```

Include it in `create_app` beside the others (`from .routes import changes as change_routes`, then add `change_routes.router` to the loop).

- [ ] **Step 3: The templates**

`templates/changes.html`:

```html
{% extends "base.html" %}
{% block title %}Changes · Lakota Sheet{% endblock %}
{% block content %}
<h2>Changes</h2>
<p class="muted">What the gradebooks and you have done since a chosen moment. Newest first.</p>
{% set base = "/changes?" ~ (("kid=" ~ kid ~ "&") if kid else "") ~ (("kind=" ~ kind ~ "&") if kind else "") %}
<div class="filters">
  <span>Window:</span>
  {% for key, label, days in WINDOWS %}
  <a class="badge {{ 'current' if window == key }}" href="{{ base }}window={{ key }}"
     hx-get="{{ base }}window={{ key }}" hx-target="#changes" hx-push-url="true">{{ label }}</a>
  {% endfor %}
  <span>Kid:</span>
  <a class="badge {{ 'current' if not kid }}" href="/changes?window={{ window }}{{ ('&kind=' ~ kind) if kind else '' }}">all</a>
  {% for s in students %}
  <a class="badge {{ 'current' if kid == s.key }}" href="/changes?window={{ window }}&kid={{ s.key }}{{ ('&kind=' ~ kind) if kind else '' }}">{{ s.key | nickname }}</a>
  {% endfor %}
  <span>Kind:</span>
  <a class="badge {{ 'current' if not kind }}" href="/changes?window={{ window }}{{ ('&kid=' ~ kid) if kid else '' }}">all</a>
  {% for k in KINDS %}
  <a class="badge {{ 'current' if kind == k }}" href="/changes?window={{ window }}{{ ('&kid=' ~ kid) if kid else '' }}&kind={{ k }}">{{ LABELS[k] }}</a>
  {% endfor %}
</div>
<div id="changes">
{% block partial %}
{% include "_change_rows.html" %}
{% endblock %}
</div>
{% endblock %}
```

`templates/_change_rows.html`:

```html
<table class="items">
  <thead><tr><th>When</th><th>Kid</th><th>What</th><th>Item</th><th>Class</th><th>Detail</th></tr></thead>
  <tbody>
  {% for e in events %}
  <tr>
    <td>{{ e.at | wd_md_time }}</td>
    <td><a href="/kids/{{ e.student_key }}">{{ e.student_key | nickname }}</a></td>
    <td><span class="badge">{{ e.label }}</span></td>
    <td>{% if e.item_id %}<a href="#change-{{ loop.index }}" hx-get="/items/{{ e.item_id }}" hx-target="#change-{{ loop.index }}">{{ e.item_name }}</a>{% endif %}</td>
    <td class="muted">{{ e.course_short or '' }}{% if e.source %} · {{ e.source }}{% endif %}</td>
    <td>{{ e.detail }}</td>
  </tr>
  <tr class="detail"><td colspan="6" id="change-{{ loop.index }}"></td></tr>
  {% else %}
  <tr><td colspan="6" class="muted">Nothing has changed in this window.</td></tr>
  {% endfor %}
  </tbody>
</table>
```

`base.html`: insert before the `App` group:

```html
      <div class="group">Time</div>
      <a href="/changes" class="{{ 'current' if current == 'changes' }}">Changes</a>
      <a href="/trends" class="{{ 'current' if current == 'trends' }}">Trends</a>
```

(The Trends link 404s until Task 4; that is one task's gap in a branch that is never merged mid-plan. If you would rather not ship a dead link inside the branch, add only the Changes link here and the Trends link in Task 4 — either is fine, say which you did.)

- [ ] **Step 4: Run, full suite, commit**

```bash
git add lakota_grades/web tests/test_web_changes_page.py
git commit -m "web: the Changes page, one feed of everything that moved

Closes #20

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `web/stores/trends.py` (issue #21)

**Files:**
- Create: `lakota_grades/web/stores/trends.py`, `tests/test_web_trends_store.py`

**Interfaces:**
- Consumes: `tests/web_fixtures.history`, `students`, `reconcile.comparable`, `open_items.school_year_start`.
- Produces:
  - `trends.GradeSeries(course_id, course_short, source, label, points)` where `points` is `list[tuple[datetime, float]]`
  - `trends.WeekCounts(week_start: date, missing: int, late: int, on_time: int, posted: int)`
  - `trends.grade_series(conn, *, student_id=None, since=None) -> list[GradeSeries]`
  - `trends.weekly_counts(conn, *, student_id=None, weeks=8, now) -> list[WeekCounts]` (oldest first, one entry per week even when empty)
  - `trends.open_days(conn, *, student_id=None, now) -> list[tuple[str, float]]` — (item name, days between first seen and the observation that cleared it), longest first, at most 10
  - `trends.on_time_rate(weeks: list[WeekCounts]) -> float | None`

- [ ] **Step 1: Write the failing store test**

`tests/test_web_trends_store.py`:

```python
"""Trends: grade lines per class, and the weekly counts under them."""
from __future__ import annotations

from datetime import date, datetime

from lakota_grades.web import db
from lakota_grades.web.stores import students, trends
from tests.web_fixtures import NOW, REFRESH_TIMES, history


def test_empty_database_has_no_series(tmp_path):
    conn = db.open_db(tmp_path)
    assert trends.grade_series(conn) == []
    weeks = trends.weekly_counts(conn, weeks=4, now=NOW)
    assert len(weeks) == 4 and all(w.missing == 0 and w.posted == 0 for w in weeks)
    assert trends.on_time_rate(weeks) is None
    conn.close()


def test_grade_series_per_course_and_source(tmp_path):
    conn = history(tmp_path)
    series = {(s.course_short, s.source): s for s in trends.grade_series(conn)}
    hac = series[("Honors English 9", "hac")]
    assert [v for _, v in hac.points] == [85.0, 88.0]                 # day 1 then day 2 onward
    assert [t.isoformat() for t, _ in hac.points] == [REFRESH_TIMES[0], REFRESH_TIMES[1]]
    canvas = series[("Honors English 9", "canvas")]
    assert [v for _, v in canvas.points] == [93.0, 91.2]
    assert canvas.label == "Honors English 9 (Canvas current)"
    assert hac.label == "Honors English 9 (HAC average)"
    conn.close()


def test_grade_series_filters_by_student_and_since(tmp_path):
    conn = history(tmp_path)
    sam = students.by_key(conn, "Sam")["id"]
    assert {s.course_short for s in trends.grade_series(conn, student_id=sam)} == {"Science 7"}
    late = trends.grade_series(conn, since=datetime.fromisoformat(REFRESH_TIMES[1]))
    assert all(all(t >= datetime.fromisoformat(REFRESH_TIMES[1]) for t, _ in s.points) for s in late)
    conn.close()


def test_weekly_counts_bucket_by_week(tmp_path):
    conn = history(tmp_path)
    weeks = trends.weekly_counts(conn, weeks=3, now=NOW)
    assert len(weeks) == 3 and [w.week_start for w in weeks] == sorted(w.week_start for w in weeks)
    assert weeks[-1].week_start == date(2026, 9, 14)                  # the Monday of NOW's week
    this_week = weeks[-1]
    assert this_week.missing >= 1 and this_week.posted >= 1
    assert all(w.missing >= 0 and w.late >= 0 and w.on_time >= 0 for w in weeks)
    conn.close()


def test_weekly_counts_filter_by_student(tmp_path):
    conn = history(tmp_path)
    sam = students.by_key(conn, "Sam")["id"]
    mine = trends.weekly_counts(conn, student_id=sam, weeks=3, now=NOW)
    everyone = trends.weekly_counts(conn, weeks=3, now=NOW)
    assert sum(w.missing for w in mine) <= sum(w.missing for w in everyone)
    conn.close()


def test_on_time_rate_is_a_fraction_or_none(tmp_path):
    conn = history(tmp_path)
    weeks = trends.weekly_counts(conn, weeks=8, now=NOW)
    rate = trends.on_time_rate(weeks)
    assert rate is None or 0.0 <= rate <= 1.0
    conn.close()


def test_open_days_reports_the_longest_first(tmp_path):
    conn = history(tmp_path)
    rows = trends.open_days(conn, now=NOW)
    assert len(rows) <= 10
    assert [d for _, d in rows] == sorted((d for _, d in rows), reverse=True)
    assert all(d >= 0 for _, d in rows)
    conn.close()
```

Run it. Expected: FAIL (`ImportError`).

- [ ] **Step 2: Implement `web/stores/trends.py`**

```python
"""The numbers behind the Trends page.

Three questions a parent actually asks: is this class's grade going up or down, are the
missing and late counts getting better week by week, and what has been sitting open the
longest. All three are reductions of the same change log the Changes feed walks, so nothing
here writes or caches -- at three kids and a school year it is a few thousand rows.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ...open_items import school_year_start

MAX_OPEN_DAYS_ROWS = 10


@dataclass
class GradeSeries:
    course_id: int
    course_short: str
    source: str                       # canvas | hac
    label: str
    points: list[tuple[datetime, float]] = field(default_factory=list)


@dataclass(frozen=True)
class WeekCounts:
    week_start: date
    missing: int = 0
    late: int = 0
    on_time: int = 0
    posted: int = 0


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def grade_series(conn: sqlite3.Connection, *, student_id: int | None = None,
                 since: datetime | None = None) -> list[GradeSeries]:
    """One line per course per source: HAC's marking-period average and Canvas' current score.

    `grade_observations` only holds rows where something changed, so each point is a real
    move; a flat stretch is simply the absence of points between two of them.
    """
    sql = """SELECT g.*, r.started_at AS at, c.short_name AS course_short, c.source AS course_source
             FROM grade_observations g JOIN refreshes r ON r.id = g.refresh_id
             JOIN courses c ON c.id = g.course_id JOIN students s ON s.id = c.student_id
             WHERE s.hidden = 0 AND c.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND c.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY g.course_id, g.refresh_id"
    out: dict[tuple[int, str], GradeSeries] = {}
    for r in conn.execute(sql, args):
        at = _dt(r["at"])
        if at is None or (since is not None and at < since):
            continue
        for field_name, source, word in (("average", "hac", "HAC average"), ("current", "canvas", "Canvas current")):
            value = r[field_name]
            if value is None:
                continue
            key = (r["course_id"], source)
            s = out.get(key)
            if s is None:
                s = out[key] = GradeSeries(r["course_id"], r["course_short"], source,
                                           f"{r['course_short']} ({word})")
            s.points.append((at, float(value)))
    return [s for s in out.values() if s.points]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_counts(conn: sqlite3.Connection, *, student_id: int | None = None, weeks: int = 8,
                  now: datetime) -> list[WeekCounts]:
    """Per week: how many items turned missing, how many were handed in late, how many were
    handed in on time, and how many grades were posted. Oldest first, one row per week even
    when nothing happened, so a chart has an even x axis."""
    starts = [_monday(now.date()) - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    buckets = {s: {"missing": 0, "late": 0, "on_time": 0, "posted": 0} for s in starts}
    floor = starts[0]
    sql = """SELECT o.*, r.started_at AS at, i.student_id AS student_id
             FROM item_observations o JOIN refreshes r ON r.id = o.refresh_id
             JOIN items i ON i.id = o.item_id JOIN students s ON s.id = i.student_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY o.item_id, o.source, o.refresh_id"
    prev: dict[tuple[int, str], sqlite3.Row] = {}
    for row in conn.execute(sql, args):
        key = (row["item_id"], row["source"])
        before = prev.get(key)
        prev[key] = row
        at = _dt(row["at"])
        if at is None:
            continue
        week = _monday(at.date())
        if week < floor or week not in buckets:
            continue
        b = buckets[week]
        if before is None:
            if row["missing"]:
                b["missing"] += 1
            if row["score"] is not None:
                b["posted"] += 1
            continue
        if not before["missing"] and row["missing"]:
            b["missing"] += 1
        if before["score"] is None and row["score"] is not None:
            b["posted"] += 1
        if not before["submitted_at"] and row["submitted_at"]:
            b["late" if row["late"] else "on_time"] += 1
    return [WeekCounts(s, **buckets[s]) for s in starts]


def on_time_rate(weeks: list[WeekCounts]) -> float | None:
    """On-time hand-ins as a fraction of all hand-ins, or None when nothing was handed in."""
    handed = sum(w.on_time + w.late for w in weeks)
    return (sum(w.on_time for w in weeks) / handed) if handed else None


def open_days(conn: sqlite3.Connection, *, student_id: int | None = None,
              now: datetime) -> list[tuple[str, float]]:
    """How long each still-open item has been open, longest first: the days between its first
    sighting and now, for items no source has cleared. Ten rows at most -- this is a chart,
    not an inventory."""
    sql = """SELECT i.name AS name, r.started_at AS first_at, i.id AS id
             FROM items i JOIN refreshes r ON r.id = i.first_seen
             JOIN students s ON s.id = i.student_id
             WHERE s.hidden = 0 AND i.due IS NOT NULL"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    floor = school_year_start(now)
    out: list[tuple[str, float]] = []
    from .. import db as _db, reconcile
    latest_by_student: dict[int, dict] = {}
    for r in conn.execute(sql, args):
        first = _dt(r["first_at"])
        if first is None:
            continue
        a, b = reconcile.comparable(first, floor)
        if a < b:
            continue
        item = conn.execute("SELECT * FROM items WHERE id = ?", (r["id"],)).fetchone()
        student = item["student_id"]
        if student not in latest_by_student:
            latest_by_student[student] = _db.latest_observations(conn, student)
        obs = latest_by_student[student].get(item["id"], {})
        if not reconcile.open_sources(item, obs, now):
            continue
        a2, b2 = reconcile.comparable(now, first)
        out.append((r["name"], round((a2 - b2).total_seconds() / 86400, 1)))
    out.sort(key=lambda p: p[1], reverse=True)
    return out[:MAX_OPEN_DAYS_ROWS]
```

`open_days`'s per-item `SELECT` is the one N+1 in this plan, bounded by a kid's live item count (tens). If it reads badly to you, hoist it into the first query and say so in your report; do not change the signature.

Run the store tests. Expected: PASS. `test_weekly_counts_bucket_by_week` asserting `date(2026, 9, 14)` depends on 2026-09-15 being a Tuesday — check with `python -c "import datetime;print(datetime.date(2026,9,15).weekday())"` (1 = Tuesday) before adjusting anything.

- [ ] **Step 3: Full suite, commit**

```bash
git add lakota_grades/web/stores/trends.py tests/test_web_trends_store.py
git commit -m "web.stores.trends: grade lines, weekly counts and what has sat open longest

Closes #21

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The Trends page and the charts (issue #22)

**Files:**
- Create: `lakota_grades/web/routes/trends.py`, `templates/trends.html`, `templates/_chart.html`, `tests/test_web_trends_page.py`
- Modify: `lakota_grades/web/app.py` (router), `templates/base.html` (the Trends rail link, if Task 2 left it out), `templates/course.html` (the course grade chart), `static/app.js`, `static/app.css`

**Interfaces:**
- Consumes: Task 3's stores, `app.render`, `students`.
- Produces: `GET /trends?kid=&weeks=`; `GET /trends/grades.json?kid=&weeks=`; `GET /trends/weekly.json?kid=&weeks=`. Both JSON endpoints answer `{"series": [{"label": str, "points": [[epoch_seconds, value], …]}]}` for grades and `{"weeks": ["2026-09-14", …], "missing": [...], "late": [...], "on_time": [...], "posted": [...]}` for weekly.

- [ ] **Step 1: Write the failing page test**

`tests/test_web_trends_page.py`:

```python
"""The Trends page and the JSON its charts read."""
from __future__ import annotations

from tests.web_fixtures import app_for, history, seed


def test_empty_database_says_nothing_yet(tmp_path):
    r = app_for(tmp_path).get("/trends")
    assert r.status_code == 200 and "Not enough history yet" in r.text


def test_page_renders_chart_holders_and_the_summary(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    assert 'data-chart="/trends/grades.json' in body and 'data-chart="/trends/weekly.json' in body
    assert "uplot.min.js" in body and "uplot.min.css" in body
    assert "On-time" in body and "%" in body
    assert "Open the longest" in body and "Quiz 1" in body


def test_grades_json_has_one_series_per_course_and_source(tmp_path):
    history(tmp_path).close()
    data = app_for(tmp_path).get("/trends/grades.json").json()
    labels = {s["label"] for s in data["series"]}
    assert "Honors English 9 (HAC average)" in labels and "Honors English 9 (Canvas current)" in labels
    hac = next(s for s in data["series"] if s["label"].endswith("(HAC average)") and s["label"].startswith("Honors"))
    assert [v for _, v in hac["points"]] == [85.0, 88.0]
    assert all(isinstance(t, (int, float)) for t, _ in hac["points"])       # epoch seconds for uPlot


def test_weekly_json_is_parallel_arrays(tmp_path):
    history(tmp_path).close()
    data = app_for(tmp_path).get("/trends/weekly.json?weeks=4").json()
    assert len(data["weeks"]) == 4
    for key in ("missing", "late", "on_time", "posted"):
        assert len(data[key]) == 4
    assert data["weeks"] == sorted(data["weeks"])


def test_kid_filter_applies_to_page_and_json(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/trends?kid=Sam").text
    assert "Science 7" in body and "Honors English 9" not in body
    data = c.get("/trends/grades.json?kid=Sam").json()
    assert all("Science 7" in s["label"] for s in data["series"])
    assert c.get("/trends?kid=Nobody").status_code == 404
    assert c.get("/trends/grades.json?kid=Nobody").status_code == 404


def test_weeks_parameter_is_bounded(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    assert len(c.get("/trends/weekly.json?weeks=200").json()["weeks"]) == 52     # clamped
    assert len(c.get("/trends/weekly.json?weeks=0").json()["weeks"]) == 1
    assert c.get("/trends/weekly.json?weeks=nonsense").status_code == 200        # falls back to the default


def test_course_page_gains_a_grade_chart(tmp_path):
    conn = history(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    assert 'data-chart="/trends/grades.json?course=' in body and "uplot.min.js" in body


def test_one_refresh_only_still_renders(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/trends")
    assert r.status_code == 200 and "Trends" in r.text
```

Run it. Expected: FAIL (404).

- [ ] **Step 2: The route**

`lakota_grades/web/routes/trends.py`:

```python
"""Trends: grade lines per class, weekly missing/late/on-time counts, and what has sat open
longest. The page renders holders; the two JSON endpoints feed uPlot."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..app import Db, State, render, student_or_404
from ..stores import trends

router = APIRouter()

DEFAULT_WEEKS = 8
MAX_WEEKS = 52


def _weeks(request: Request) -> int:
    raw = request.query_params.get("weeks")
    try:
        n = int(raw) if raw else DEFAULT_WEEKS
    except ValueError:
        n = DEFAULT_WEEKS
    return max(1, min(n, MAX_WEEKS))


def _student(conn, request: Request):
    kid = request.query_params.get("kid") or None
    return student_or_404(conn, kid) if kid else None


@router.get("/trends")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    sid = student["id"] if student else None
    weeks = _weeks(request)
    now = state.now()
    week_rows = trends.weekly_counts(conn, student_id=sid, weeks=weeks, now=now)
    return render(request, conn, "trends.html", current="trends",
                  kid=student["key"] if student else None, weeks=weeks,
                  series=trends.grade_series(conn, student_id=sid),
                  week_rows=week_rows, rate=trends.on_time_rate(week_rows),
                  longest=trends.open_days(conn, student_id=sid, now=now))


@router.get("/trends/grades.json")
def grades_json(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    series = trends.grade_series(conn, student_id=student["id"] if student else None)
    course = request.query_params.get("course")
    if course and course.isdigit():
        series = [s for s in series if s.course_id == int(course)]
    return JSONResponse({"series": [
        {"label": s.label, "points": [[t.timestamp(), v] for t, v in s.points]} for s in series]})


@router.get("/trends/weekly.json")
def weekly_json(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    rows = trends.weekly_counts(conn, student_id=student["id"] if student else None,
                                weeks=_weeks(request), now=state.now())
    return JSONResponse({
        "weeks": [w.week_start.isoformat() for w in rows],
        "missing": [w.missing for w in rows], "late": [w.late for w in rows],
        "on_time": [w.on_time for w in rows], "posted": [w.posted for w in rows],
    })
```

Include the router in `create_app`.

- [ ] **Step 3: The templates**

`templates/_chart.html` — one holder, used three times:

```html
<div class="chart" data-chart="{{ url }}" data-kind="{{ kind }}" data-title="{{ title }}" style="height:{{ height|default(220) }}px">
  <p class="muted">Loading the chart…</p>
</div>
```

`templates/trends.html`:

```html
{% extends "base.html" %}
{% block title %}Trends · Lakota Sheet{% endblock %}
{% block content %}
<link rel="stylesheet" href="/static/uplot.min.css">
<script src="/static/uplot.min.js" defer></script>
<h2>Trends</h2>
<div class="filters">
  <span>Kid:</span>
  <a class="badge {{ 'current' if not kid }}" href="/trends?weeks={{ weeks }}">all</a>
  {% for s in students %}<a class="badge {{ 'current' if kid == s.key }}" href="/trends?kid={{ s.key }}&weeks={{ weeks }}">{{ s.key | nickname }}</a>{% endfor %}
  <span>Weeks:</span>
  {% for n in (4, 8, 16) %}<a class="badge {{ 'current' if weeks == n }}" href="/trends?{{ ('kid=' ~ kid ~ '&') if kid else '' }}weeks={{ n }}">{{ n }}</a>{% endfor %}
</div>
{% if not series and not longest %}
<p class="muted">Not enough history yet. Trends fill in as refreshes accumulate — come back after a few days of runs.</p>
{% endif %}
<div class="cards">
  <div class="card"><h2>On-time hand-ins</h2>
    {% if rate is not none %}<p class="big">{{ (rate * 100) | round | int }}%</p><p class="muted">of everything handed in during these {{ weeks }} weeks</p>
    {% else %}<p class="muted">Nothing handed in yet in this window.</p>{% endif %}
  </div>
  <div class="card"><h2>Open the longest</h2>
    {% for name, days in longest %}<p>{{ name }} <span class="muted">{{ days }} days</span></p>{% else %}<p class="muted">Nothing is open.</p>{% endfor %}
  </div>
</div>
<h3>Grades</h3>
{% with url = "/trends/grades.json" ~ (("?kid=" ~ kid) if kid else ""), kind = "lines", title = "Grade per class", height = 260 %}
{% include "_chart.html" %}
{% endwith %}
<h3>Missing, late and on time, by week</h3>
{% with url = "/trends/weekly.json?weeks=" ~ weeks ~ (("&kid=" ~ kid) if kid else ""), kind = "weekly", title = "Per week" %}
{% include "_chart.html" %}
{% endwith %}
<table class="items">
  <thead><tr><th>Week of</th><th>Missing</th><th>Late</th><th>On time</th><th>Grades posted</th></tr></thead>
  <tbody>
  {% for w in week_rows %}<tr><td>{{ w.week_start | md }}</td><td>{{ w.missing }}</td><td>{{ w.late }}</td><td>{{ w.on_time }}</td><td>{{ w.posted }}</td></tr>{% endfor %}
  </tbody>
</table>
{% endblock %}
```

`templates/course.html`: after the "Grade history" table, add

```html
<link rel="stylesheet" href="/static/uplot.min.css">
<script src="/static/uplot.min.js" defer></script>
{% with url = "/trends/grades.json?course=" ~ course.id, kind = "lines", title = "This class" %}
{% include "_chart.html" %}
{% endwith %}
```

- [ ] **Step 4: The chart bootstrap**

Append to `static/app.js`:

```js
// Charts: a <div class="chart" data-chart=URL data-kind=lines|weekly> fetches its own JSON and
// draws one uPlot into itself. No data is embedded in the page, so a chart is just a URL.
function drawChart(el) {
  if (el.dataset.drawn) return;
  el.dataset.drawn = "1";
  fetch(el.dataset.chart, { headers: { Accept: "application/json" } })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var opts, series;
      if (el.dataset.kind === "weekly") {
        var xs = data.weeks.map(function (w) { return Date.parse(w) / 1000; });
        series = [xs, data.missing, data.late, data.on_time];
        opts = { title: el.dataset.title, width: el.clientWidth, height: el.clientHeight,
                 series: [{}, { label: "Missing", stroke: "#b3261e" }, { label: "Late", stroke: "#b8860b" },
                          { label: "On time", stroke: "#2e7d32" }] };
      } else {
        if (!data.series.length) { el.innerHTML = '<p class="muted">No grades recorded yet.</p>'; return; }
        var times = {};
        data.series.forEach(function (s) { s.points.forEach(function (p) { times[p[0]] = 1; }); });
        var xs2 = Object.keys(times).map(Number).sort(function (a, b) { return a - b; });
        series = [xs2].concat(data.series.map(function (s) {
          var by = {}; s.points.forEach(function (p) { by[p[0]] = p[1]; });
          var last = null;
          return xs2.map(function (t) { if (by[t] !== undefined) last = by[t]; return last; });
        }));
        var colors = ["#1f5fa8", "#b3261e", "#2e7d32", "#6b3fa0", "#b8860b", "#00707f"];
        opts = { title: el.dataset.title, width: el.clientWidth, height: el.clientHeight,
                 series: [{}].concat(data.series.map(function (s, i) {
                   return { label: s.label, stroke: colors[i % colors.length] };
                 })) };
      }
      el.innerHTML = "";
      new uPlot(opts, series, el);
    })
    .catch(function () { el.innerHTML = '<p class="warn">The chart could not load.</p>'; });
}
function attachCharts(root) {
  if (typeof uPlot === "undefined") { setTimeout(function () { attachCharts(root); }, 50); return; }
  (root.querySelectorAll ? root.querySelectorAll(".chart[data-chart]") : []).forEach(drawChart);
}
document.addEventListener("DOMContentLoaded", function () { attachCharts(document); });
document.addEventListener("htmx:afterSwap", function (e) { attachCharts(e.detail.target); });
```

Append to `static/app.css`:

```css
.chart { background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; padding: 8px; margin: 8px 0; }
.chart .muted { padding: 8px; }
.u-legend { font-size: 12px; }
```

The `setTimeout` retry exists because `uplot.min.js` is loaded with `defer` from the page body while `app.js` is deferred from `base.html`'s head; rather than depend on the order, the bootstrap waits for the global. Say in your report if you found a cleaner ordering.

- [ ] **Step 5: Run, full suite, commit**

Run the page tests, then the full suite.

```bash
git add lakota_grades/web tests/test_web_trends_page.py
git commit -m "web: the Trends page, three charts and the weekly table

Closes #22

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- `/changes` lists everything that moved in the chosen window — new items, grades posted and changed, items turning missing or clearing, class averages moving, and the parent's own flags — filterable by kid and kind, with rows that expand into the same item detail the Kid page uses.
- `/trends` shows a grade line per class and source, a weekly missing/late/on-time chart with the table under it, the on-time percentage, and what has sat open longest; the course page carries its own one-class chart.
- Both pages render with an empty database, with one refresh, and for a kid with no courses, and say so in a sentence rather than failing.
- No schema change, no write, no new dependency; the full suite is green and pristine locally and in CI on both runners.
- Not in this plan: view reports, the builder, export and schedules (Plan D); the friend's page, the QR code and doc polish (Plan E); the residuals in issues #31, #32 and #33.

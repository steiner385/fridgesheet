# Web App Plan D (part 1 of 2): View Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the parent define a report in the browser — which kids, which rows, which columns, how sorted and grouped — save it, preview it, print it as a PDF through the same runner the open-work sheet uses, and export it as CSV or JSON.

**Architecture:** A view definition is JSON in the existing `reports` table. `web/views.py` turns one definition into typed columns and rows by querying the same stores the pages already use, so a view can never disagree with the Kid or Trends page about the same fact. `reports/view.py` wraps that in the `Report` protocol so `view:<id>` flows through `runner.run` exactly like `open-work`, which means printing, archiving, run recording and toasts come free. `sheet.py` grows a generic table renderer beside the open-work layout, which is left untouched.

**Tech Stack:** Python 3.12, `sqlite3` and `csv` (stdlib), the existing reportlab, FastAPI/Jinja2/htmx. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-15-lakota-web-app-design.md`, sections 5 (the Reports bullet), 7 (Reports — the binding description of a view definition), 12, 13.D. GitHub milestone "Web app D: Reports", issues **#23** (Task 1), **#24** (Task 2), **#25** (Tasks 3 and 4). Part 2 of Plan D covers issues #26 and #27 (the Linux systemd writer and the Schedules page) and is written after this plan lands. Earlier residuals live in issues #31, #32, #33 and #34.

## Global Constraints

- A view definition is JSON with exactly these keys: `title` (str), `scope` (list of student keys; empty means every visible kid), `source` (`"items"` | `"grades"` | `"changes"`), `columns` (list of column ids), `filters` (list of `{field, op, value}`), `group_by` (a column id or `null`), `sort` (list of `{column, dir}` where dir is `asc`/`desc`), `chart` (`null` for this plan), `orientation` (`"portrait"` | `"landscape"`), `per_kid_sections` (bool). An unknown key is ignored on read and dropped on write; a missing key takes its default. **Validation is total**: `views.validate(definition) -> list[str]` returns every problem as a sentence, and nothing is saved or built while that list is non-empty.
- Report keys: code reports keep their keys (`open-work`); a view report's key is `view:<row id>`. `reports.resolve(key, home)` is the one place a key becomes a `Report`; `reports.get(key)` keeps working unchanged for code reports and the registry stays the place a new code report is added.
- A view report's rows come from the same stores the pages use (`stores/items.py`, `stores/trends.py`, `stores/changes.py`). No new SQL outside `web/db.py` and `web/stores/`, and `web/views.py` holds no SQL of its own.
- The open-work sheet's layout is untouched. `sheet.py` gains a generic renderer used only by view reports; every existing test of the printed sheet must still pass byte-for-byte in behaviour.
- A view report goes through `runner.run` unchanged, so it archives, records a `runs` row, toasts and respects `run.lock` exactly as the sheet does. `RunOptions.trigger` and the existing guards are not special-cased.
- Export is a download, not a page: CSV via `csv.writer` into a `StringIO`, JSON via `json.dumps`, both served with a `Content-Disposition` filename built from the report's title and the date.
- The builder posts ordinary form fields; there is no JSON editor in the browser and no client-side validation. Jinja autoescape stays on, nothing is `|safe`, routes contain no SQL, templates do not compute.
- The four seed templates (Open work, Weekly summary, Grade trend, Quarter recap) are inserted only when the `reports` table is empty, and only by an explicit action — never as a side effect of opening a page.
- No credential is read by any of this. Nothing leaves the machine.
- The full suite (`env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`, **389 passed** at the start of this plan) stays green and pristine on Linux and in CI on both runners.
- Commit after every task with the trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` and the issue line each task's commit block gives verbatim.

## What Plans A to C left (read before any task)

| Module | You use |
|---|---|
| `web/db.py` | `open_db(home)`, `now_iso(tz)`; the `reports` table (`id, name, definition, created_at, updated_at`) is empty and unused so far |
| `web/stores/items.py` | `ItemView` (fields `id, key, name, course_id, course_short, course_name, kind, points, due, sources, open_in, actionable, upcoming, flag, flag_text, status, canvas, hac, notes, case_kinds`; properties `overdue`, `handled`), `SHOW`, `SORTS`, `FLAGGED`, `list_items(conn, student, *, now, rules, show, source, course_id, kind, flagged, sort)`, `one`, `with_cases`, `dashboard_counts` |
| `web/stores/trends.py` | `GradeSeries(course_id, course_short, source, label, points)`, `WeekCounts(week_start, missing, late, on_time, posted)`, `grade_series(conn, *, student_id=None, since=None)`, `weekly_counts(conn, *, student_id=None, weeks=8, now)`, `on_time_rate`, `open_days` |
| `web/stores/changes.py` | `Event` (fields `kind, at, student_key, student_id, item_id, item_name, course_short, source, detail, flag`; property `label`), `KINDS`, `LABELS`, `WINDOWS`, `DEFAULT_WINDOW`, `window_start(key, now)`, `since(conn, *, since, until=None, student_id=None, kinds=None, limit=...) -> Feed` (a list subclass carrying `total` and `dropped`) |
| `web/stores/students.py` | `visible(conn)`, `by_key`, `by_id`, `courses`, `course`, `latest_grades`, `grade_history`, `owner_of_item` |
| `web/app.py` | `create_app(settings, *, home=None, worker=False)`, `AppState` (`home`, `settings`, `tz`, `clock`, `now()`, `rules()`, `extra`, `reload()`), `get_state`, `get_db`, `Db`, `State`, `render(request, conn, name, /, status_code=200, **ctx)`, `render_partial`, `is_htmx`, `page_context`, `student_or_404`, `safe_pdf`, `loopback` |
| `web/jobs.py` | `Worker` (`submit(kind, **params)`, `KINDS = ("refresh", "preview", "print", "doctor", "login")`), `Job`; `AppState.jobs` |
| `web/actions.py` | `preview(*, home, log, settings, run=None, opener=None, today=None)`, `print_now(*, home, log, settings, run=None, date=None)` — both call `runner.run("open-work", …)` today and gain a report key in Task 4 |
| `reports/` | `REPORTS` (`{"open-work": OpenWorkReport()}`), `get(key)`, `Report` protocol (`key`, `title`, `output_dir`, `default_time`, `archive_name(day)`, `build(snap, ctx) -> Built`), `BuildContext` (`settings, home, day, now, out_dir, kid, nicknames, prev_rows, prev_label, stale_note, options, data_as_of, flags`), `Built(pdf, rows, summary)`, `ReportError` |
| `sheet.py` | `build_pdf(sheets, out_path, *, data_as_of, days_ahead, overdue_days, stale_note=None, printed_at=None) -> int`, `pdf_text(path)`, the `ParagraphStyle`s (`H1`, `SM`, `CELL`, `CELLB`, `TINY`, `NOTE`), `MARGIN`, the colour constants, `_esc` |
| `runner.py` | `run(report_key, opts, settings, *, now=None, refresh=…, print_pdf=…, toast=…, echo=…) -> int`, `RunOptions(dry_run, force, reprint, date, kid, no_refresh, printer, options, notify, trigger)`, `Lock`, `LOG_NAME` |
| `config.py` | `Settings`, `load_settings`, `WEEKDAYS` |
| `tests/web_fixtures.py` | `TZ`, `NOW` (2026-09-15 14:00 EDT), `REFRESH_TIMES`, `snapshot()`, `seed(home)`, `history(home)`, `app_for(home, now=NOW, worker=False)` |

## File map

| Path | Responsibility |
|---|---|
| `lakota_grades/web/views.py` (new) | `COLUMNS`, `SOURCES`, `OPS`, `Definition`, `validate`, `defaults`, `build(conn, definition, *, now, rules, nicknames) -> Rendered` |
| `lakota_grades/web/stores/reports.py` (new) | `all`, `by_id`, `create`, `update`, `delete`, `seed_templates` over the `reports` table |
| `lakota_grades/sheet.py` (modify) | `build_table_pdf(rendered, out_path, *, title, printed_at, orientation, per_kid_sections) -> int` beside the untouched open-work code |
| `lakota_grades/reports/view.py` (new) | `ViewReport` — the `Report` protocol over a stored definition |
| `lakota_grades/reports/__init__.py` (modify) | `resolve(key, home)`; `REPORTS` and `get` unchanged |
| `lakota_grades/runner.py` (modify) | resolve through `reports.resolve(report_key, home)` |
| `lakota_grades/web/routes/reports.py` (new) | the list, the builder, preview, save, delete, print, export |
| `lakota_grades/web/templates/reports.html`, `report_builder.html`, `_report_preview.html` (new); `base.html` (modify) | |
| `lakota_grades/web/actions.py`, `jobs.py` (modify) | a report key reaches `preview`/`print_now` and the job params |
| `tests/test_web_views.py`, `test_web_reports_store.py`, `test_report_view.py`, `test_sheet_table.py`, `test_web_reports_page.py` (new); `tests/test_reports.py`, `test_runner.py`, `test_web_jobs.py` (modify) | |

---

### Task 1: `web/views.py` and the reports store (issue #23)

**Files:**
- Create: `lakota_grades/web/views.py`, `lakota_grades/web/stores/reports.py`, `tests/test_web_views.py`, `tests/test_web_reports_store.py`

**Interfaces:**
- Consumes: `stores/items.py`, `stores/trends.py`, `stores/changes.py`, `stores/students.py`, `db.now_iso`.
- Produces:
  - `views.SOURCES = ("items", "grades", "changes")`
  - `views.OPS = ("is", "is not", "contains", "≥", "≤")`
  - `views.COLUMNS: dict[str, dict[str, Column]]` — source → column id → `Column(id, label, kind)` where `kind` is `"text" | "number" | "date" | "bool"`. Exactly these:
    - `items`: `kid`, `course`, `name`, `status`, `due`, `points`, `kind`, `sources`, `flag`, `open`, `actionable`, `notes`, `cases`
    - `grades`: `kid`, `course`, `source`, `label`, `value`, `at`
    - `changes`: `at`, `kid`, `what`, `item`, `course`, `source`, `detail`
  - `views.Definition` — a frozen dataclass with the Global Constraints' fields and their defaults; `views.defaults(source="items") -> Definition`; `Definition.to_json()` / `views.from_json(text) -> Definition` (an unknown key is dropped, a missing one defaulted, a malformed payload raises `views.ViewError`)
  - `views.validate(d: Definition) -> list[str]` — every problem as a sentence
  - `views.Rendered(title, columns, groups)` where `groups` is `list[Group]` and `Group(label, rows)` with `rows` a `list[dict]` keyed by column id, values already formatted for display as `str`
  - `views.build(conn, d: Definition, *, now, rules, nicknames) -> Rendered`
  - `stores.reports.all(conn)`, `by_id(conn, report_id)`, `create(conn, name, definition_json, *, now) -> int`, `update(conn, report_id, name, definition_json, *, now) -> bool`, `delete(conn, report_id) -> bool`, `seed_templates(conn, *, now) -> int` (inserts the four templates only when the table is empty; returns how many it wrote)

- [ ] **Step 1: Write the failing store test**

`tests/test_web_reports_store.py`:

```python
"""Saved view reports: the rows behind the Reports list."""
from __future__ import annotations

import json

from lakota_grades.web import db
from lakota_grades.web.stores import reports


def test_empty_table(tmp_path):
    conn = db.open_db(tmp_path)
    assert reports.all(conn) == [] and reports.by_id(conn, 1) is None
    conn.close()


def test_create_read_update_delete(tmp_path):
    conn = db.open_db(tmp_path)
    rid = reports.create(conn, "Weekly summary", '{"source": "items"}', now="2026-09-16T08:00:00-04:00")
    row = reports.by_id(conn, rid)
    assert row["name"] == "Weekly summary" and json.loads(row["definition"])["source"] == "items"
    assert row["created_at"] == row["updated_at"] == "2026-09-16T08:00:00-04:00"
    assert reports.update(conn, rid, "Renamed", '{"source": "grades"}', now="2026-09-16T09:00:00-04:00") is True
    row = reports.by_id(conn, rid)
    assert row["name"] == "Renamed" and row["created_at"] < row["updated_at"]
    assert reports.update(conn, 999, "x", "{}", now="2026-09-16T09:00:00-04:00") is False
    assert reports.delete(conn, rid) is True and reports.by_id(conn, rid) is None
    assert reports.delete(conn, rid) is False
    conn.close()


def test_all_is_by_name(tmp_path):
    conn = db.open_db(tmp_path)
    for name in ("Zebra", "Apple", "Mango"):
        reports.create(conn, name, "{}", now="2026-09-16T08:00:00-04:00")
    assert [r["name"] for r in reports.all(conn)] == ["Apple", "Mango", "Zebra"]
    conn.close()


def test_seed_templates_only_fills_an_empty_table(tmp_path):
    conn = db.open_db(tmp_path)
    assert reports.seed_templates(conn, now="2026-09-16T08:00:00-04:00") == 4
    names = [r["name"] for r in reports.all(conn)]
    assert names == ["Grade trend", "Open work", "Quarter recap", "Weekly summary"]
    assert reports.seed_templates(conn, now="2026-09-16T08:00:00-04:00") == 0
    assert len(reports.all(conn)) == 4
    conn.close()


def test_seeded_definitions_are_valid(tmp_path):
    from lakota_grades.web import views
    conn = db.open_db(tmp_path)
    reports.seed_templates(conn, now="2026-09-16T08:00:00-04:00")
    for r in reports.all(conn):
        d = views.from_json(r["definition"])
        assert views.validate(d) == [], f"{r['name']}: {views.validate(d)}"
    conn.close()
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_reports_store.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 2: Write the failing views test**

`tests/test_web_views.py`:

```python
"""A view definition: what it accepts, what it refuses, and the rows it renders."""
from __future__ import annotations

import json

import pytest

from lakota_grades import late_rules
from lakota_grades.web import views
from lakota_grades.web.stores import students
from tests.web_fixtures import NOW, history, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _build(conn, d):
    return views.build(conn, d, now=NOW, rules=RULES, nicknames={"Alex": "Al"})


def test_defaults_are_valid_and_round_trip():
    d = views.defaults()
    assert d.source == "items" and d.columns and views.validate(d) == []
    again = views.from_json(d.to_json())
    assert again == d


def test_from_json_drops_unknown_keys_and_fills_missing():
    d = views.from_json('{"source": "grades", "nonsense": 1}')
    assert d.source == "grades" and d.orientation == "portrait" and not d.scope
    with pytest.raises(views.ViewError):
        views.from_json("not json")
    with pytest.raises(views.ViewError):
        views.from_json('["a list"]')


def test_validate_names_every_problem():
    d = views.defaults()
    bad = views.from_json(json.dumps({**json.loads(d.to_json()),
                                      "source": "nope", "columns": ["kid", "bogus"],
                                      "filters": [{"field": "kid", "op": "~", "value": "x"}],
                                      "group_by": "bogus", "sort": [{"column": "bogus", "dir": "sideways"}],
                                      "orientation": "diagonal", "title": ""}))
    problems = views.validate(bad)
    assert len(problems) >= 6
    assert any("source" in p for p in problems) and any("bogus" in p for p in problems)
    assert any("~" in p for p in problems) and any("sideways" in p for p in problems)
    assert any("orientation" in p.lower() for p in problems) and any("title" in p.lower() for p in problems)
    assert all(p.endswith(".") for p in problems)


def test_validate_rejects_an_empty_column_list():
    d = views.from_json('{"source": "items", "columns": []}')
    assert any("at least one column" in p for p in views.validate(d))


def test_items_source_renders_rows_a_parent_reads(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"title": "Open work", "source": "items",
                                    "columns": ["kid", "course", "name", "status", "due"],
                                    "filters": [{"field": "open", "op": "is", "value": "yes"}],
                                    "sort": [{"column": "due", "dir": "asc"}]}))
    r = _build(conn, d)
    assert [c.id for c in r.columns] == ["kid", "course", "name", "status", "due"]
    assert len(r.groups) == 1 and r.groups[0].label == ""
    names = [row["name"] for row in r.groups[0].rows]
    assert "Quiz 1" in names and "Essay draft" not in names            # submitted: not open
    row = next(x for x in r.groups[0].rows if x["name"] == "Quiz 1")
    assert row["kid"] == "Al" and row["course"] == "Honors English 9" and row["status"] == "Missing"
    assert row["due"] == "9/12" and all(isinstance(v, str) for v in row.values())
    conn.close()


def test_scope_limits_the_kids(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"], "scope": ["Sam"]}))
    assert {row["kid"] for row in _build(conn, d).groups[0].rows} == {"Sam"}
    conn.close()


def test_group_by_splits_and_labels(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "course", "name"], "group_by": "kid"}))
    r = _build(conn, d)
    assert [g.label for g in r.groups] == ["Al", "Sam"]
    assert all(g.rows for g in r.groups)
    conn.close()


def test_filters_by_every_operator(tmp_path):
    conn = seed(tmp_path)
    def rows(f):
        d = views.from_json(json.dumps({"source": "items", "columns": ["name", "points", "course"], "filters": [f]}))
        return [x["name"] for x in _build(conn, d).groups[0].rows]
    assert "Quiz 1" in rows({"field": "course", "op": "contains", "value": "English"})
    assert "Cell diagram" not in rows({"field": "course", "op": "contains", "value": "English"})
    assert rows({"field": "name", "op": "is", "value": "Quiz 1"}) == ["Quiz 1"]
    assert "Quiz 1" not in rows({"field": "name", "op": "is not", "value": "Quiz 1"})
    assert "Quiz 1" in rows({"field": "points", "op": "≥", "value": "30"})
    assert "Quiz 1" not in rows({"field": "points", "op": "≤", "value": "10"})
    conn.close()


def test_sort_is_applied_in_order(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"],
                                    "sort": [{"column": "kid", "dir": "desc"}, {"column": "name", "dir": "asc"}]}))
    rows = _build(conn, d).groups[0].rows
    assert rows[0]["kid"] == "Sam"
    sam = [r["name"] for r in rows if r["kid"] == "Sam"]
    assert sam == sorted(sam)
    conn.close()


def test_grades_source(tmp_path):
    conn = history(tmp_path)
    d = views.from_json(json.dumps({"source": "grades", "columns": ["kid", "course", "source", "value", "at"]}))
    rows = _build(conn, d).groups[0].rows
    assert any(r["course"] == "Honors English 9" and r["source"] == "hac" and r["value"] == "88" for r in rows)
    assert all(r["at"] for r in rows)
    conn.close()


def test_changes_source(tmp_path):
    conn = history(tmp_path)
    d = views.from_json(json.dumps({"source": "changes", "columns": ["at", "kid", "what", "item", "detail"]}))
    rows = _build(conn, d).groups[0].rows
    assert any(r["what"] == "Grade posted" and r["item"] == "Quiz 1" for r in rows)
    conn.close()


def test_an_empty_result_still_renders_columns(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json(json.dumps({"source": "items", "columns": ["kid", "name"],
                                    "filters": [{"field": "name", "op": "is", "value": "nothing at all"}]}))
    r = _build(conn, d)
    assert [c.id for c in r.columns] == ["kid", "name"] and r.groups == []
    conn.close()


def test_build_refuses_an_invalid_definition(tmp_path):
    conn = seed(tmp_path)
    d = views.from_json('{"source": "items", "columns": []}')
    with pytest.raises(views.ViewError):
        _build(conn, d)
    conn.close()
```

Run it. Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement `web/stores/reports.py`**

```python
"""Saved view reports. The definition is opaque JSON here; `web/views.py` owns its meaning."""
from __future__ import annotations

import json
import sqlite3

#: Seeded on request into an empty table (spec section 7). Each is a valid `views.Definition`.
TEMPLATES: tuple[tuple[str, dict], ...] = (
    ("Open work", {"title": "Open work", "source": "items",
                   "columns": ["kid", "course", "name", "status", "due", "points"],
                   "filters": [{"field": "open", "op": "is", "value": "yes"}],
                   "group_by": "kid", "sort": [{"column": "due", "dir": "asc"}], "per_kid_sections": True}),
    ("Weekly summary", {"title": "Weekly summary", "source": "changes",
                        "columns": ["at", "kid", "what", "item", "course", "detail"],
                        "sort": [{"column": "at", "dir": "desc"}]}),
    ("Grade trend", {"title": "Grade trend", "source": "grades",
                     "columns": ["kid", "course", "source", "value", "at"],
                     "group_by": "kid", "sort": [{"column": "at", "dir": "asc"}]}),
    ("Quarter recap", {"title": "Quarter recap", "source": "items",
                       "columns": ["kid", "course", "name", "status", "points", "flag"],
                       "group_by": "course", "sort": [{"column": "course", "dir": "asc"}, {"column": "name", "dir": "asc"}],
                       "orientation": "landscape"}),
)


def all(conn: sqlite3.Connection) -> list[sqlite3.Row]:   # noqa: A001  the store's vocabulary
    return conn.execute("SELECT * FROM reports ORDER BY name").fetchall()


def by_id(conn: sqlite3.Connection, report_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


def create(conn: sqlite3.Connection, name: str, definition_json: str, *, now: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO reports(name, definition, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, definition_json, now, now))
        return cur.lastrowid


def update(conn: sqlite3.Connection, report_id: int, name: str, definition_json: str, *, now: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE reports SET name = ?, definition = ?, updated_at = ? WHERE id = ?",
                           (name, definition_json, now, report_id))
        return cur.rowcount > 0


def delete(conn: sqlite3.Connection, report_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        return cur.rowcount > 0


def seed_templates(conn: sqlite3.Connection, *, now: str) -> int:
    """Write the starter reports, but only into an empty table -- never over the parent's own."""
    if conn.execute("SELECT 1 FROM reports LIMIT 1").fetchone():
        return 0
    for name, definition in TEMPLATES:
        create(conn, name, json.dumps(definition), now=now)
    return len(TEMPLATES)
```

Run the store test. Expected: PASS except `test_seeded_definitions_are_valid`, which needs Step 4.

- [ ] **Step 4: Implement `web/views.py`**

```python
"""A view report: a JSON definition, the rows it selects, and the checks that keep it honest.

The rows come from the same stores the pages read, so a report can never disagree with the Kid,
Trends or Changes page about the same fact -- that is the whole reason this module has no SQL.
Every value is formatted to a string here, once, so the HTML table, the PDF and the CSV all show
the same text.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from .. import dates
from .stores import changes as changes_store, items as items_store, students as students_store, trends as trends_store

SOURCES = ("items", "grades", "changes")
OPS = ("is", "is not", "contains", "≥", "≤")
ORIENTATIONS = ("portrait", "landscape")
DIRS = ("asc", "desc")
MAX_ROWS = 2000


class ViewError(RuntimeError):
    """The definition cannot be read or cannot be built."""


@dataclass(frozen=True)
class Column:
    id: str
    label: str
    kind: str                       # text | number | date | bool


def _cols(*specs: tuple[str, str, str]) -> dict[str, Column]:
    return {c[0]: Column(*c) for c in specs}


COLUMNS: dict[str, dict[str, Column]] = {
    "items": _cols(
        ("kid", "Kid", "text"), ("course", "Class", "text"), ("name", "Item", "text"),
        ("status", "Status", "text"), ("due", "Due", "date"), ("points", "Points", "number"),
        ("kind", "Kind", "text"), ("sources", "Seen in", "text"), ("flag", "Flag", "text"),
        ("open", "Open", "bool"), ("actionable", "Actionable", "bool"),
        ("notes", "Notes", "number"), ("cases", "Reconcile", "text"),
    ),
    "grades": _cols(
        ("kid", "Kid", "text"), ("course", "Class", "text"), ("source", "Source", "text"),
        ("label", "Series", "text"), ("value", "Value", "number"), ("at", "Seen", "date"),
    ),
    "changes": _cols(
        ("at", "When", "date"), ("kid", "Kid", "text"), ("what", "What", "text"),
        ("item", "Item", "text"), ("course", "Class", "text"), ("source", "Source", "text"),
        ("detail", "Detail", "text"),
    ),
}

DEFAULT_COLUMNS = {"items": ["kid", "course", "name", "status", "due"],
                   "grades": ["kid", "course", "source", "value", "at"],
                   "changes": ["at", "kid", "what", "item", "detail"]}


@dataclass(frozen=True)
class Definition:
    title: str = "Untitled report"
    source: str = "items"
    scope: tuple[str, ...] = ()
    columns: tuple[str, ...] = ()
    filters: tuple[dict, ...] = ()
    group_by: str | None = None
    sort: tuple[dict, ...] = ()
    chart: None = None
    orientation: str = "portrait"
    per_kid_sections: bool = False

    def to_json(self) -> str:
        return json.dumps({
            "title": self.title, "source": self.source, "scope": list(self.scope),
            "columns": list(self.columns), "filters": [dict(f) for f in self.filters],
            "group_by": self.group_by, "sort": [dict(s) for s in self.sort], "chart": None,
            "orientation": self.orientation, "per_kid_sections": self.per_kid_sections,
        }, indent=1)


def defaults(source: str = "items") -> Definition:
    src = source if source in SOURCES else "items"
    return Definition(source=src, columns=tuple(DEFAULT_COLUMNS[src]))


def from_json(text: str) -> Definition:
    """Read a stored definition. Unknown keys are dropped, missing ones defaulted; anything that
    is not a JSON object, or whose fields are the wrong shape, is a `ViewError`."""
    try:
        raw = json.loads(text or "{}")
    except ValueError as e:
        raise ViewError(f"the definition is not JSON: {e}") from None
    if not isinstance(raw, dict):
        raise ViewError("the definition must be a JSON object")
    src = raw.get("source") if isinstance(raw.get("source"), str) else "items"
    d = defaults(src)
    def seq(key, default):
        v = raw.get(key)
        return tuple(v) if isinstance(v, list) else default
    try:
        return replace(
            d,
            title=str(raw.get("title", d.title)),
            source=src,
            scope=tuple(str(x) for x in seq("scope", ())),
            columns=tuple(str(x) for x in seq("columns", d.columns)),
            filters=tuple(dict(f) for f in seq("filters", ()) if isinstance(f, dict)),
            group_by=raw["group_by"] if isinstance(raw.get("group_by"), str) else None,
            sort=tuple(dict(s) for s in seq("sort", ()) if isinstance(s, dict)),
            orientation=str(raw.get("orientation", d.orientation)),
            per_kid_sections=bool(raw.get("per_kid_sections", False)),
        )
    except (TypeError, ValueError) as e:
        raise ViewError(f"the definition has a field of the wrong shape: {e}") from None


def validate(d: Definition) -> list[str]:
    """Every problem with the definition, one sentence each. Empty means it can be built."""
    problems: list[str] = []
    if not d.title.strip():
        problems.append("The title cannot be empty.")
    if d.source not in SOURCES:
        problems.append(f"Unknown source {d.source!r}; choose one of {', '.join(SOURCES)}.")
        return problems                      # every other check depends on the source
    known = COLUMNS[d.source]
    if not d.columns:
        problems.append("Choose at least one column.")
    for c in d.columns:
        if c not in known:
            problems.append(f"{c!r} is not a column of the {d.source} source.")
    for f in d.filters:
        if f.get("field") not in known:
            problems.append(f"The filter field {f.get('field')!r} is not a column of the {d.source} source.")
        if f.get("op") not in OPS:
            problems.append(f"{f.get('op')!r} is not a filter operator; use one of {', '.join(OPS)}.")
        if str(f.get("value", "")).strip() == "":
            problems.append("A filter needs a value.")
    if d.group_by is not None and d.group_by not in known:
        problems.append(f"Cannot group by {d.group_by!r}; it is not a column of the {d.source} source.")
    for s in d.sort:
        if s.get("column") not in known:
            problems.append(f"Cannot sort by {s.get('column')!r}; it is not a column of the {d.source} source.")
        if s.get("dir") not in DIRS:
            problems.append(f"{s.get('dir')!r} is not a sort direction; use asc or desc.")
    if d.orientation not in ORIENTATIONS:
        problems.append(f"Unknown orientation {d.orientation!r}; use portrait or landscape.")
    return problems


@dataclass
class Group:
    label: str
    rows: list[dict] = field(default_factory=list)


@dataclass
class Rendered:
    title: str
    columns: list[Column]
    groups: list[Group] = field(default_factory=list)
    truncated: int = 0               # rows dropped by MAX_ROWS


def _num(v) -> str:
    return "" if v is None else (f"{v:g}" if isinstance(v, (int, float)) else str(v))


def _date(v) -> str:
    if v is None:
        return ""
    d = datetime.fromisoformat(v) if isinstance(v, str) else v
    return dates.md(d) if isinstance(d, datetime) else str(d)


def _yes(v) -> str:
    return "yes" if v else "no"


def _item_rows(conn, d, *, now, rules, nicknames) -> list[dict]:
    out = []
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for v in items_store.list_items(conn, s, now=now, rules=rules, show="all"):
            out.append({
                "kid": nicknames.get(s["key"], s["key"]), "course": v.course_short, "name": v.name,
                "status": v.status, "due": _date(v.due), "points": _num(v.points), "kind": v.kind,
                "sources": " + ".join(v.sources), "flag": (v.flag or "").replace("_", " "),
                "open": _yes(v.overdue or v.upcoming), "actionable": _yes(v.actionable),
                "notes": _num(v.notes), "cases": ", ".join(k.replace("_", " ") for k in v.case_kinds),
            })
    return out


def _grade_rows(conn, d, *, now, nicknames) -> list[dict]:
    out = []
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for series in trends_store.grade_series(conn, student_id=s["id"]):
            for at, value in series.points:
                out.append({"kid": nicknames.get(s["key"], s["key"]), "course": series.course_short,
                            "source": series.source, "label": series.label,
                            "value": _num(value), "at": _date(at)})
    return out


def _change_rows(conn, d, *, now, nicknames) -> list[dict]:
    keys = {s["key"] for s in students_store.visible(conn)}
    feed = changes_store.since(conn, since=now - timedelta(days=365), limit=MAX_ROWS)
    out = []
    for e in feed:
        if e.student_key not in keys or (d.scope and e.student_key not in d.scope):
            continue
        out.append({"at": _date(e.at), "kid": nicknames.get(e.student_key, e.student_key),
                    "what": e.label, "item": e.item_name or "", "course": e.course_short or "",
                    "source": e.source or "", "detail": e.detail})
    return out


def _keep(row: dict, f: dict) -> bool:
    got, want, op = row.get(f["field"], ""), str(f["value"]).strip(), f["op"]
    if op in ("≥", "≤"):
        try:
            a, b = float(got or 0), float(want)
        except ValueError:
            return False
        return a >= b if op == "≥" else a <= b
    a, b = got.lower(), want.lower()
    if op == "is":
        return a == b
    if op == "is not":
        return a != b
    return b in a


def _sort_key(row: dict, columns: list[str]):
    return tuple(row.get(c, "").lower() for c in columns)


def build(conn: sqlite3.Connection, d: Definition, *, now: datetime, rules, nicknames: dict) -> Rendered:
    """Definition to rows. Raises `ViewError` when the definition does not validate."""
    problems = validate(d)
    if problems:
        raise ViewError(" ".join(problems))
    if d.source == "items":
        rows = _item_rows(conn, d, now=now, rules=rules, nicknames=nicknames)
    elif d.source == "grades":
        rows = _grade_rows(conn, d, now=now, nicknames=nicknames)
    else:
        rows = _change_rows(conn, d, now=now, nicknames=nicknames)
    for f in d.filters:
        rows = [r for r in rows if _keep(r, f)]
    for s in reversed(d.sort):                     # stable sorts, least significant first
        rows.sort(key=lambda r, c=s["column"]: r.get(c, "").lower(), reverse=s["dir"] == "desc")
    truncated = max(0, len(rows) - MAX_ROWS)
    rows = rows[:MAX_ROWS]
    columns = [COLUMNS[d.source][c] for c in d.columns]
    slim = [{c.id: r.get(c.id, "") for c in columns} | ({d.group_by: r.get(d.group_by, "")} if d.group_by else {})
            for r in rows]
    groups: list[Group] = []
    if d.group_by:
        seen: dict[str, Group] = {}
        for r in slim:
            label = r.get(d.group_by, "")
            g = seen.get(label)
            if g is None:
                g = seen[label] = Group(label)
                groups.append(g)
            g.rows.append({c.id: r[c.id] for c in columns})
        groups.sort(key=lambda g: g.label)
    elif slim:
        groups = [Group("", [{c.id: r[c.id] for c in columns} for r in slim])]
    return Rendered(d.title, columns, groups, truncated)
```

Note on `_change_rows`: a year back is what "everything the change log holds" means for a household database, and the `limit` keeps a runaway from reaching the PDF. A year in days rather than `now.replace(year=…)`, which raises on 29 February.

Run both test files. Expected: PASS. If `test_group_by_splits_and_labels` orders groups differently, note that `groups.sort(key=label)` puts "Al" before "Sam" — check the nickname is applied before grouping.

- [ ] **Step 5: Full suite, commit**

```bash
git add lakota_grades/web/views.py lakota_grades/web/stores/reports.py tests/test_web_views.py tests/test_web_reports_store.py
git commit -m "web.views: a report definition, its checks, and the rows it selects

Closes #23

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: A generic table PDF, and `reports/view.py` (issue #24)

**Files:**
- Modify: `lakota_grades/sheet.py` (add; never change the open-work path), `lakota_grades/reports/__init__.py`, `lakota_grades/runner.py`
- Create: `lakota_grades/reports/view.py`, `tests/test_sheet_table.py`, `tests/test_report_view.py`
- Modify: `tests/test_reports.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: Task 1's `views.Rendered/Group/Column/from_json/build`, `stores.reports.by_id`, `sheet`'s styles and `pdf_text`, `reports.Report`/`BuildContext`/`Built`/`ReportError`.
- Produces:
  - `sheet.build_table_pdf(rendered, out_path, *, title, printed_at, orientation="portrait", per_kid_sections=False, note=None) -> int` — returns the page count
  - `reports.view.ViewReport(report_id, name, definition)` satisfying the `Report` protocol, with `key = f"view:{report_id}"`, `title = name`, `output_dir = f"reports/view-{report_id}"`, `default_time = "16:00"`, `archive_name(day)` → `f"{day.isoformat()} {name}.pdf"`
  - `reports.resolve(key: str, home: Path | None = None) -> Report` — a code report from `REPORTS`, or a `view:<id>` loaded from `<home>/lakota.db`; raises `ReportError` for an unknown key, a missing home, or a deleted row
  - `runner.run` resolves through `reports.resolve(report_key, settings.home)`

- [ ] **Step 1: Write the failing table-PDF test**

`tests/test_sheet_table.py`:

```python
"""The generic table PDF a view report prints. The open-work layout is not touched by any of this."""
from __future__ import annotations

from lakota_grades import sheet
from lakota_grades.web.views import Column, Group, Rendered
from tests.conftest import needs_pdftotext
from tests.web_fixtures import NOW

COLS = [Column("kid", "Kid", "text"), Column("name", "Item", "text"), Column("due", "Due", "date")]


def _rendered(groups):
    return Rendered("Weekly summary", COLS, groups)


@needs_pdftotext
def test_a_flat_table_prints_its_title_headers_and_rows(tmp_path):
    r = _rendered([Group("", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"},
                              {"kid": "Sam", "name": "Cell diagram", "due": "9/13"}])])
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(r, out, title="Weekly summary", printed_at=NOW)
    assert pages >= 1 and out.is_file()
    text = sheet.pdf_text(out)
    assert "Weekly summary" in text and "Kid" in text and "Item" in text and "Due" in text
    assert "Quiz 1" in text and "Cell diagram" in text and "9/12" in text
    assert "printed" in text.lower()


@needs_pdftotext
def test_groups_print_their_labels(tmp_path):
    r = _rendered([Group("Al", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"}]),
                   Group("Sam", [{"kid": "Sam", "name": "Cell diagram", "due": "9/13"}])])
    out = tmp_path / "r.pdf"
    sheet.build_table_pdf(r, out, title="By kid", printed_at=NOW)
    text = sheet.pdf_text(out)
    assert "Al" in text and "Sam" in text and "By kid" in text


@needs_pdftotext
def test_an_empty_report_still_prints_a_page_that_says_so(tmp_path):
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(_rendered([]), out, title="Nothing", printed_at=NOW)
    assert pages == 1
    assert "No rows" in sheet.pdf_text(out)


@needs_pdftotext
def test_orientation_and_per_kid_sections_are_accepted(tmp_path):
    r = _rendered([Group("Al", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"}])])
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(r, out, title="Wide", printed_at=NOW, orientation="landscape", per_kid_sections=True)
    assert pages >= 1 and "Quiz 1" in sheet.pdf_text(out)


@needs_pdftotext
def test_a_long_table_paginates_and_repeats_the_header(tmp_path):
    rows = [{"kid": "Al", "name": f"Item {i}", "due": "9/12"} for i in range(120)]
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(_rendered([Group("", rows)]), out, title="Long", printed_at=NOW)
    assert pages >= 2
    text = sheet.pdf_text(out)
    assert text.count("Kid") >= 2 and "Item 119" in text


def test_a_truncation_note_is_printed(tmp_path):
    r = Rendered("Big", COLS, [Group("", [{"kid": "Al", "name": "Quiz 1", "due": "9/12"}])], truncated=17)
    out = tmp_path / "r.pdf"
    sheet.build_table_pdf(r, out, title="Big", printed_at=NOW, note="17 more rows are not shown")
    assert out.is_file()
```

- [ ] **Step 2: Implement `sheet.build_table_pdf`**

Append to `sheet.py`, below the open-work code (import `landscape` from `reportlab.lib.pagesizes`):

```python
TABLE_HEAD = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5)
GROUP_HEAD = ParagraphStyle("gh", fontName="Helvetica-Bold", fontSize=11, leading=13, spaceBefore=6)


def build_table_pdf(rendered, out_path: Path, *, title: str, printed_at: datetime,
                    orientation: str = "portrait", per_kid_sections: bool = False, note: str | None = None) -> int:
    """A view report: a title, then one table per group, each with a repeating header row.

    Deliberately plain beside the open-work sheet's bespoke layout -- a report the parent
    designed should look like what they designed, not like the sheet.
    """
    page = landscape(letter) if orientation == "landscape" else letter
    width = page[0] - 2 * MARGIN
    cols = rendered.columns
    col_width = width / max(1, len(cols))
    story: list = [Paragraph(_esc(title), H1), Paragraph(long_date(printed_at), SM), Spacer(1, 8)]
    if not rendered.groups:
        story.append(Paragraph("No rows matched this report.", CELL))
    for g in rendered.groups:
        if g.label:
            story.append(Paragraph(_esc(g.label), GROUP_HEAD))
        data = [[Paragraph(_esc(c.label), TABLE_HEAD) for c in cols]]
        for row in g.rows:
            data.append([Paragraph(_esc(str(row.get(c.id, ""))), CELL) for c in cols])
        t = Table(data, colWidths=[col_width] * len(cols), repeatRows=1)
        t.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
            ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#D9D9D9")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(PageBreak() if per_kid_sections and g is not rendered.groups[-1] else Spacer(1, 10))
    if note:
        story.append(Spacer(1, 6))
        story.append(Paragraph(_esc(note), NOTE))
    pages = {"n": 0}

    def footer(canvas, doc):
        pages["n"] = max(pages["n"], doc.page)
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(page[0] - MARGIN, 0.4 * inch,
                               f"lakota-grades · {_esc(title)} · printed {md(printed_at)} {time12(printed_at)} · page {doc.page}")
        canvas.restoreState()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out_path), pagesize=page, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=0.55 * inch, bottomMargin=0.65 * inch,
                            title=f"{title} {printed_at:%Y-%m-%d}", author="lakota-grades")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return pages["n"]
```

Add `PageBreak` to the platypus import and `landscape` to the pagesizes import. Nothing above this function changes.

- [ ] **Step 3: Write the failing view-report test**

`tests/test_report_view.py`:

```python
"""A stored definition as a Report: it resolves by key and builds a PDF through the runner's protocol."""
from __future__ import annotations

import json
from datetime import date

import pytest

from lakota_grades import config, reports, runner
from lakota_grades.reports import ReportError
from lakota_grades.web import db
from lakota_grades.web.stores import reports as reportstore
from tests.conftest import needs_pdftotext
from tests.web_fixtures import NOW, seed


def _save(home, name="Weekly summary", **over):
    conn = db.open_db(home)
    d = {"title": name, "source": "items", "columns": ["kid", "course", "name", "status"], **over}
    rid = reportstore.create(conn, name, json.dumps(d), now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def test_resolve_finds_code_and_view_reports(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    assert reports.resolve("open-work", tmp_path).key == "open-work"
    r = reports.resolve(f"view:{rid}", tmp_path)
    assert r.key == f"view:{rid}" and r.title == "Weekly summary"
    assert r.output_dir == f"reports/view-{rid}" and r.archive_name(date(2026, 9, 16)).endswith("Weekly summary.pdf")
    with pytest.raises(ReportError):
        reports.resolve("view:999", tmp_path)
    with pytest.raises(ReportError):
        reports.resolve("nonsense", tmp_path)
    with pytest.raises(ReportError):
        reports.resolve(f"view:{rid}", None)


def test_get_still_serves_code_reports_only():
    assert reports.get("open-work").key == "open-work"
    with pytest.raises(ReportError):
        reports.get("view:1")


def _ctx(home, out):
    return reports.BuildContext(settings=config.Settings(home=home), home=home, day=NOW.date(), now=NOW,
                                out_dir=out, kid=None, nicknames={"Alex": "Al"}, prev_rows=None,
                                prev_label=None, stale_note=None, options={}, data_as_of=NOW)


@needs_pdftotext
def test_build_writes_a_pdf_and_rows(tmp_path):
    from lakota_grades import sheet
    seed(tmp_path).close()
    rid = _save(tmp_path)
    r = reports.resolve(f"view:{rid}", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    built = r.build({}, _ctx(tmp_path, out))
    assert built.pdf.is_file() and built.pdf.parent == out
    text = sheet.pdf_text(built.pdf)
    assert "Quiz 1" in text and "Al" in text
    assert built.rows["columns"] == ["kid", "course", "name", "status"]
    assert any(row["name"] == "Quiz 1" for row in built.rows["rows"])
    n = len(built.rows["rows"])
    assert built.summary.endswith(f"{n} rows") and built.summary[0].isdigit()


def test_build_refuses_a_broken_definition(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=[])
    r = reports.resolve(f"view:{rid}", tmp_path)
    with pytest.raises(ReportError):
        r.build({}, _ctx(tmp_path, tmp_path))


def test_the_runner_runs_a_view_report(tmp_path):
    """The runner loads a snapshot before building whatever the report is, so one has to be on
    disk even though a view report reads the database instead."""
    from tests.web_fixtures import snapshot
    seed(tmp_path).close()
    (tmp_path / "cache").mkdir(exist_ok=True)
    (tmp_path / "cache" / "snapshot.json").write_text(json.dumps(snapshot()))
    rid = _save(tmp_path)
    s = config.Settings(home=tmp_path)
    rc = runner.run(f"view:{rid}", runner.RunOptions(dry_run=True, force=True, no_refresh=True, notify=False),
                    s, now=NOW)
    assert rc == 0
    conn = db.open_db(tmp_path)
    row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    assert row["report_key"] == f"view:{rid}" and row["outcome"] == "OK"
    assert (tmp_path / f"reports/view-{rid}" / NOW.date().isoformat() / "report.pdf").is_file()
```

- [ ] **Step 4: Implement `reports/view.py` and `resolve`**

`lakota_grades/reports/view.py`:

```python
"""A saved view report, wearing the same Report protocol as the open-work sheet.

Everything around a report -- the guards, the refresh, the archive copy, the `runs` row, the
toast, the lock -- lives in the runner, so a view report gets all of it by being a `Report`
and nothing more.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .. import sheet
from ..web import db, views
from .base import Built, BuildContext, ReportError


@dataclass
class ViewReport:
    report_id: int
    name: str
    definition: str                  # the stored JSON

    @property
    def key(self) -> str:
        return f"view:{self.report_id}"

    @property
    def title(self) -> str:
        return self.name

    @property
    def output_dir(self) -> str:
        return f"reports/view-{self.report_id}"

    default_time = "16:00"

    def archive_name(self, day: date) -> str:
        return f"{day.isoformat()} {self.name}.pdf"

    def build(self, snap: dict, ctx: BuildContext) -> Built:
        """The snapshot is unused: a view reads the database, which the runner has just ingested."""
        conn = db.open_db(ctx.home)
        try:
            d = views.from_json(self.definition)
            rendered = views.build(conn, d, now=ctx.now, rules=_rules(ctx), nicknames=ctx.nicknames)
        except views.ViewError as e:
            raise ReportError(f"{self.name}: {e}") from None
        finally:
            conn.close()
        pdf = ctx.out_dir / "report.pdf"
        note = f"{rendered.truncated} more rows are not shown" if rendered.truncated else None
        pages = sheet.build_table_pdf(rendered, pdf, title=d.title or self.name, printed_at=ctx.now,
                                      orientation=d.orientation, per_kid_sections=d.per_kid_sections, note=note)
        n = sum(len(g.rows) for g in rendered.groups)
        rows = {"columns": [c.id for c in rendered.columns],
                "rows": [r for g in rendered.groups for r in g.rows]}
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {n} rows")


def _rules(ctx: BuildContext):
    from .. import late_rules
    return late_rules.load(ctx.home / "late-rules.toml")
```

In `reports/__init__.py`:

```python
from pathlib import Path


def resolve(key: str, home: Path | None = None) -> Report:
    """A report key to a report: a code report from the registry, or `view:<id>` from the database.

    The runner calls this; `get` stays the registry's own lookup so a code report never depends
    on a database being present.
    """
    if not key.startswith("view:"):
        return get(key)
    if home is None:
        raise ReportError(f"{key} needs a home directory to load from")
    try:
        report_id = int(key.split(":", 1)[1])
    except ValueError:
        raise ReportError(f"malformed report key {key!r}") from None
    from ..web import db
    from ..web.stores import reports as store
    from .view import ViewReport
    conn = db.open_db(home)
    try:
        row = store.by_id(conn, report_id)
    finally:
        conn.close()
    if row is None:
        raise ReportError(f"no saved report {report_id}")
    return ViewReport(report_id, row["name"], row["definition"])
```

Add `resolve` to `__all__`. In `runner.py`, change `report = reports.get(report_key)` to `report = reports.resolve(report_key, settings.home)`. Check `tests/test_runner.py` and `tests/test_reports.py` for anything that asserts on `reports.get` being the runner's lookup, and update it.

- [ ] **Step 5: Run, full suite, commit**

```bash
git add lakota_grades tests
git commit -m "A view report prints: the generic table engine, ViewReport, and resolve by key

Closes #24

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The Reports page — list, builder, preview, save (issue #25, part 1 of 2)

**Files:**
- Create: `lakota_grades/web/routes/reports.py`, `templates/reports.html`, `report_builder.html`, `_report_preview.html`, `tests/test_web_reports_page.py`
- Modify: `lakota_grades/web/app.py` (router), `templates/base.html` (rail)

**Interfaces:**
- Consumes: Task 1's `views` and `stores.reports`, `app.render`/`render_partial`, `students.visible`.
- Produces: `GET /reports`; `POST /reports/seed`; `GET /reports/new`; `GET /reports/{id}`; `POST /reports/{id}` (save); `POST /reports/{id}/delete`; `POST /reports/preview` (the builder's live preview, returns `_report_preview.html`); `routes.reports.definition_from_form(form) -> views.Definition`.

- [ ] **Step 1: Write the failing page test**

`tests/test_web_reports_page.py`:

```python
"""The Reports page: the list, the builder, the live preview and saving."""
from __future__ import annotations

import json

from lakota_grades.web import db
from lakota_grades.web.stores import reports as store
from tests.web_fixtures import app_for, seed


def _save(home, name="Mine", **over):
    conn = db.open_db(home)
    d = {"title": name, "source": "items", "columns": ["kid", "name"], **over}
    rid = store.create(conn, name, json.dumps(d), now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def test_empty_list_offers_the_templates(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/reports").text
    assert "No saved reports yet" in body and 'hx-post="/reports/seed"' in body
    assert "Open Work Sheet" in body                       # the code report is always listed
    r = c.post("/reports/seed")
    assert r.status_code == 200 and "Weekly summary" in r.text and "Grade trend" in r.text
    assert "No saved reports yet" not in c.get("/reports").text
    assert "already has reports" in c.post("/reports/seed").text


def test_list_shows_code_and_view_reports_with_links(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    body = app_for(tmp_path).get("/reports").text
    assert f'href="/reports/{rid}"' in body and "Mine" in body
    assert "open-work" in body and f"view:{rid}" in body


def test_builder_renders_every_control(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reports/new").text
    for name in ("title", "source", "scope", "columns", "group_by", "orientation", "per_kid_sections"):
        assert f'name="{name}"' in body, name
    assert 'value="items"' in body and 'value="grades"' in body and 'value="changes"' in body
    assert "Alex" in body and "Sam" in body            # scope options
    assert 'hx-post="/reports/preview"' in body


def test_preview_returns_a_table(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/preview", data={"title": "T", "source": "items", "columns": ["kid", "name"],
                                         "sort_column": ["name"], "sort_dir": ["asc"]})
    assert r.status_code == 200 and "<html" not in r.text
    assert "Quiz 1" in r.text and "Kid" in r.text and "Item" in r.text


def test_preview_shows_every_problem_instead_of_rows(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).post("/reports/preview", data={"title": "", "source": "items"})
    assert r.status_code == 200
    assert "title cannot be empty" in r.text and "at least one column" in r.text
    assert "<table" not in r.text


def test_save_round_trips_and_edits(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/new", data={"name": "Mine", "title": "Mine", "source": "items",
                                     "columns": ["kid", "name"], "orientation": "portrait"})
    assert r.status_code == 200 and "Saved" in r.text
    conn = db.open_db(tmp_path)
    (row,) = store.all(conn)
    conn.close()
    d = json.loads(row["definition"])
    assert d["columns"] == ["kid", "name"] and d["source"] == "items" and "nonsense" not in d
    r = c.post(f"/reports/{row['id']}", data={"name": "Renamed", "title": "Mine", "source": "items",
                                              "columns": ["kid", "name", "status"], "orientation": "landscape"})
    assert "Saved" in r.text
    conn = db.open_db(tmp_path)
    row = store.by_id(conn, row["id"])
    conn.close()
    assert row["name"] == "Renamed" and json.loads(row["definition"])["orientation"] == "landscape"


def test_save_refuses_an_invalid_definition_and_writes_nothing(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/reports/new", data={"name": "Bad", "title": "Bad", "source": "items", "columns": []})
    assert r.status_code == 200 and "at least one column" in r.text
    conn = db.open_db(tmp_path)
    assert store.all(conn) == []
    conn.close()


def test_delete_removes_it(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path)
    c = app_for(tmp_path)
    r = c.post(f"/reports/{rid}/delete")
    assert r.status_code == 200 and "Mine" not in r.text
    assert c.post(f"/reports/{rid}/delete").status_code == 404
    assert c.get(f"/reports/{rid}").status_code == 404
```

- [ ] **Step 2: The route**

`lakota_grades/web/routes/reports.py`:

```python
"""Reports: the list of code and saved reports, the builder, and its live preview."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ... import reports as registry
from .. import db, views
from ..app import Db, State, render, render_partial
from ..stores import reports as store, students

router = APIRouter()


def definition_from_form(form) -> views.Definition:
    """The builder's flat form fields as a definition. Unknown values fail `validate`, not here."""
    sort = [{"column": c, "dir": d} for c, d in
            zip(form.getlist("sort_column"), form.getlist("sort_dir")) if c]
    filters = [{"field": f, "op": o, "value": v} for f, o, v in
               zip(form.getlist("filter_field"), form.getlist("filter_op"), form.getlist("filter_value")) if f]
    group_by = form.get("group_by") or None
    return views.from_json(views.Definition(
        title=form.get("title", ""), source=form.get("source", "items"),
        scope=tuple(form.getlist("scope")), columns=tuple(form.getlist("columns")),
        filters=tuple(filters), group_by=group_by, sort=tuple(sort),
        orientation=form.get("orientation", "portrait"),
        per_kid_sections=bool(form.get("per_kid_sections")),
    ).to_json())


def _page(request, conn, state, *, messages=(), errors=()):
    return render(request, conn, "reports.html", current="reports",
                  saved=store.all(conn), code=list(registry.REPORTS.values()),
                  messages=list(messages), errors=list(errors))


@router.get("/reports")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _page(request, conn, state)


@router.post("/reports/seed")
def seed(request: Request, conn: sqlite3.Connection = Db, state=State):
    n = store.seed_templates(conn, now=db.now_iso(state.tz))
    msg = f"Added {n} starter reports." if n else "This app already has reports; the starters were not added."
    return _page(request, conn, state, messages=[msg])


def _builder(request, conn, state, *, report=None, d=None, problems=(), messages=()):
    return render(request, conn, "report_builder.html", current="reports", report=report,
                  d=d or views.defaults(), COLUMNS=views.COLUMNS, SOURCES=views.SOURCES, OPS=views.OPS,
                  ORIENTATIONS=views.ORIENTATIONS, problems=list(problems), messages=list(messages),
                  kids=students.visible(conn))


@router.get("/reports/new")
def new(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _builder(request, conn, state)


async def _save(request, conn, state, report_id: int | None):
    form = await request.form()
    d = definition_from_form(form)
    problems = views.validate(d)
    name = (form.get("name") or d.title).strip() or "Untitled report"
    if problems:
        return _builder(request, conn, state, report=store.by_id(conn, report_id) if report_id else None,
                        d=d, problems=problems)
    now = db.now_iso(state.tz)
    if report_id is None:
        report_id = store.create(conn, name, d.to_json(), now=now)
    elif not store.update(conn, report_id, name, d.to_json(), now=now):
        raise HTTPException(404, "no such report")
    return _builder(request, conn, state, report=store.by_id(conn, report_id), d=d, messages=["Saved."])


@router.post("/reports/new")
async def create(request: Request, conn: sqlite3.Connection = Db, state=State):
    return await _save(request, conn, state, None)


@router.post("/reports/preview")
async def preview(request: Request, conn: sqlite3.Connection = Db, state=State):
    form = await request.form()
    d = definition_from_form(form)
    problems = views.validate(d)
    rendered = None
    if not problems:
        try:
            rendered = views.build(conn, d, now=state.now(), rules=state.rules(), nicknames=state.settings.nicknames)
        except views.ViewError as e:
            problems = [str(e)]
    return render_partial(request, conn, "_report_preview.html", rendered=rendered, problems=problems)


@router.get("/reports/{report_id}")
def edit(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    row = store.by_id(conn, report_id)
    if row is None:
        raise HTTPException(404, "no such report")
    return _builder(request, conn, state, report=row, d=views.from_json(row["definition"]))


@router.post("/reports/{report_id}")
async def save(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    if store.by_id(conn, report_id) is None:
        raise HTTPException(404, "no such report")
    return await _save(request, conn, state, report_id)


@router.post("/reports/{report_id}/delete")
def remove(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    if not store.delete(conn, report_id):
        raise HTTPException(404, "no such report")
    return _page(request, conn, state, messages=["Deleted."])
```

**Registration order matters and this file's order is deliberate.** FastAPI matches routes in the order they are added, and `{report_id}` is an `int` path parameter: a request for `/reports/new` or `/reports/preview` that reaches an `int` route first fails conversion and becomes a 404 page. So every literal path — `/reports/seed`, `/reports/new` (both methods), `/reports/preview` — is registered **before** any `/reports/{report_id}` route. Keep that order, and let `test_save_round_trips_and_edits` and `test_preview_returns_a_table` be the proof: both would 404 if the order were wrong.

- [ ] **Step 3: The templates**

`templates/reports.html`:

```html
{% extends "base.html" %}
{% block title %}Reports · Lakota Sheet{% endblock %}
{% block content %}
<h2>Reports</h2>
{% for m in messages %}<p class="ok">{{ m }}</p>{% endfor %}
{% for e in errors %}<p class="warn">{{ e }}</p>{% endfor %}
<p><a class="badge" href="/reports/new">New report</a>
   {% if not saved %}<button hx-post="/reports/seed" hx-target="body">Add the starter reports</button>{% endif %}</p>
<h3>Built in</h3>
<table class="items"><tr><th>Report</th><th>Key</th><th></th></tr>
{% for r in code %}<tr><td>{{ r.title }}</td><td class="muted">{{ r.key }}</td>
  <td>{# Task 4 adds the Print form here. #}</td></tr>{% endfor %}
</table>
<h3>Yours</h3>
{% if saved %}
<table class="items"><tr><th>Report</th><th>Key</th><th>Updated</th><th></th></tr>
{% for r in saved %}
<tr>
  <td><a href="/reports/{{ r.id }}">{{ r.name }}</a></td>
  <td class="muted">view:{{ r.id }}</td>
  <td class="muted">{{ r.updated_at | wd_md_time }}</td>
  <td>
    {# Task 4 adds the CSV and JSON links and the Print form here. #}
    <form style="display:inline" hx-post="/reports/{{ r.id }}/delete" hx-target="body" hx-confirm="Delete {{ r.name }}?"><button>Delete</button></form>
  </td>
</tr>
{% endfor %}
</table>
{% else %}<p class="muted">No saved reports yet.</p>{% endif %}
<div id="job">{% if job %}{% with busy=false %}{% include "_job.html" %}{% endwith %}{% endif %}</div>
{% endblock %}
```

The two `{# … #}` comments mark where Task 4 adds the export links and the Print forms; nothing in Task 3 asserts on them, and no dead link ships in between.

`templates/report_builder.html`:

```html
{% extends "base.html" %}
{% block title %}{{ report.name if report else "New report" }} · Lakota Sheet{% endblock %}
{% block content %}
<h2>{{ report.name if report else "New report" }}</h2>
{% for m in messages %}<p class="ok">{{ m }}</p>{% endfor %}
{% for p in problems %}<p class="warn">{{ p }}</p>{% endfor %}
{% set action = ("/reports/" ~ report.id) if report else "/reports/new" %}
<form method="post" action="{{ action }}" class="card" id="builder">
  <p><label>Name <input name="name" value="{{ report.name if report else d.title }}"></label>
     <label>Title on the page <input name="title" value="{{ d.title }}"></label></p>
  <p><label>Rows come from
     <select name="source">{% for s in SOURCES %}<option value="{{ s }}" {{ 'selected' if d.source == s }}>{{ s }}</option>{% endfor %}</select></label></p>
  <p>Kids: {% for k in kids %}<label><input type="checkbox" name="scope" value="{{ k.key }}" {{ 'checked' if k.key in d.scope }}> {{ k.key | nickname }}</label> {% endfor %}
     <span class="muted">none ticked means every kid</span></p>
  <p>Columns:<br>
    {% for cid, col in COLUMNS[d.source].items() %}
    <label><input type="checkbox" name="columns" value="{{ cid }}" {{ 'checked' if cid in d.columns }}> {{ col.label }}</label>
    {% endfor %}</p>
  <p><label>Group by <select name="group_by"><option value="">nothing</option>
    {% for cid, col in COLUMNS[d.source].items() %}<option value="{{ cid }}" {{ 'selected' if d.group_by == cid }}>{{ col.label }}</option>{% endfor %}</select></label></p>
  <p>Sort:
    {% for i in range(2) %}
    <select name="sort_column"><option value="">—</option>
      {% for cid, col in COLUMNS[d.source].items() %}<option value="{{ cid }}" {{ 'selected' if d.sort|length > i and d.sort[i].column == cid }}>{{ col.label }}</option>{% endfor %}</select>
    <select name="sort_dir"><option value="asc">ascending</option><option value="desc" {{ 'selected' if d.sort|length > i and d.sort[i].dir == 'desc' }}>descending</option></select>
    {% endfor %}</p>
  <p>Filters:
    {% for i in range(3) %}<br>
    <select name="filter_field"><option value="">—</option>
      {% for cid, col in COLUMNS[d.source].items() %}<option value="{{ cid }}" {{ 'selected' if d.filters|length > i and d.filters[i].field == cid }}>{{ col.label }}</option>{% endfor %}</select>
    <select name="filter_op">{% for o in OPS %}<option value="{{ o }}" {{ 'selected' if d.filters|length > i and d.filters[i].op == o }}>{{ o }}</option>{% endfor %}</select>
    <input name="filter_value" value="{{ d.filters[i].value if d.filters|length > i else '' }}">
    {% endfor %}</p>
  <p><label>Page <select name="orientation">{% for o in ORIENTATIONS %}<option value="{{ o }}" {{ 'selected' if d.orientation == o }}>{{ o }}</option>{% endfor %}</select></label>
     <label><input type="checkbox" name="per_kid_sections" {{ 'checked' if d.per_kid_sections }}> start each group on its own page</label></p>
  <p><button>Save</button>
     <button type="button" hx-post="/reports/preview" hx-include="#builder" hx-target="#preview">Preview</button>
     <a class="badge" href="/reports">Back to reports</a></p>
</form>
<div id="preview"></div>
{% endblock %}
```

`templates/_report_preview.html`:

```html
<div class="card">
  {% for p in problems %}<p class="warn">{{ p }}</p>{% endfor %}
  {% if rendered %}
  <h2>{{ rendered.title }}</h2>
  {% for g in rendered.groups %}
    {% if g.label %}<h3>{{ g.label }}</h3>{% endif %}
    <table class="items">
      <thead><tr>{% for c in rendered.columns %}<th>{{ c.label }}</th>{% endfor %}</tr></thead>
      <tbody>{% for row in g.rows %}<tr>{% for c in rendered.columns %}<td>{{ row[c.id] }}</td>{% endfor %}</tr>{% endfor %}</tbody>
    </table>
  {% else %}
    <p class="muted">No rows matched this report.</p>
  {% endfor %}
  {% if rendered.truncated %}<p class="muted">{{ rendered.truncated }} more rows are not shown.</p>{% endif %}
  {% endif %}
</div>
```

`base.html`: add `<a href="/reports" class="{{ 'current' if current == 'reports' }}">Reports</a>` under the `Work` group, after Reconcile. Include the router in `create_app`.

- [ ] **Step 4: Run, full suite, commit**

```bash
git add lakota_grades/web tests/test_web_reports_page.py
git commit -m "web: the Reports page, the builder and its live preview

Part of #25

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Print and export (issue #25, part 2 of 2 — this commit closes it)

**Files:**
- Modify: `lakota_grades/web/routes/reports.py`, `templates/reports.html`, `lakota_grades/web/actions.py`, `lakota_grades/web/jobs.py`, `lakota_grades/web/routes/jobs.py`, `tests/test_web_reports_page.py`, `tests/test_web_jobs.py`, `tests/test_web_actions.py`

**Interfaces:**
- Consumes: Task 2's `reports.resolve`, Task 3's route module, `jobs.Worker.submit`.
- Produces:
  - `GET /reports/{id}/export.csv` and `GET /reports/{id}/export.json` — a download whose filename is `<title> <YYYY-MM-DD>.csv|json`
  - `actions.preview(..., report_key="open-work")` and `actions.print_now(..., report_key="open-work")` — the key reaches `runner.run`
  - `jobs.Worker.submit("preview"|"print", report=<key>)` passes it through; `POST /jobs/{kind}` accepts a `report` form field, defaulting to `open-work`, and rejects a key that does not resolve with a 400

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_reports_page.py`:

```python
def test_export_csv_and_json(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, title="Mine", columns=["kid", "name"])
    c = app_for(tmp_path)
    r = c.get(f"/reports/{rid}/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "Mine" in r.headers["content-disposition"] and ".csv" in r.headers["content-disposition"]
    lines = r.text.strip().splitlines()
    assert lines[0] == "Kid,Item" and any("Quiz 1" in ln for ln in lines[1:])
    r = c.get(f"/reports/{rid}/export.json")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    data = r.json()
    assert data["title"] == "Mine" and data["columns"] == ["kid", "name"]
    assert any(row["name"] == "Quiz 1" for row in data["rows"])
    assert c.get("/reports/999/export.csv").status_code == 404


def test_export_of_a_broken_definition_is_a_400(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=[])
    assert app_for(tmp_path).get(f"/reports/{rid}/export.csv").status_code == 400


def test_a_group_column_is_exported_once(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, columns=["kid", "name"], group_by="kid")
    r = app_for(tmp_path).get(f"/reports/{rid}/export.csv")
    assert r.text.strip().splitlines()[0] == "Kid,Item"
```

Append to `tests/test_web_jobs.py`:

```python
def test_a_job_carries_the_report_key(tmp_path):
    from fastapi.testclient import TestClient
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    c = TestClient(application)
    assert c.post("/jobs/print", data={"report": "open-work"}).status_code == 200
    w.run_pending()
    assert ("print", "open-work") in [(k[0], k[2]) for k in fake.calls if isinstance(k, tuple) and k[0] == "print"]
    assert c.post("/jobs/print", data={"report": "view:999"}).status_code == 400
```

Extend `FakeActions.print_now`/`preview` in that file to record the `report_key` they receive, and update the existing assertions to match the new tuple shape.

- [ ] **Step 2: Implement export**

Append to `routes/reports.py`:

```python
import csv
import io
from datetime import date as _date

from fastapi.responses import JSONResponse, Response


def _rendered_or_400(conn, state, report_id: int):
    row = store.by_id(conn, report_id)
    if row is None:
        raise HTTPException(404, "no such report")
    try:
        d = views.from_json(row["definition"])
        return row, d, views.build(conn, d, now=state.now(), rules=state.rules(), nicknames=state.settings.nicknames)
    except views.ViewError as e:
        raise HTTPException(400, str(e)) from None


def _filename(title: str, day: _date, ext: str) -> str:
    safe = "".join(ch for ch in title if ch.isalnum() or ch in " -_").strip() or "report"
    return f"{safe} {day.isoformat()}.{ext}"


@router.get("/reports/{report_id}/export.csv")
def export_csv(report_id: int, conn: sqlite3.Connection = Db, state=State):
    row, d, rendered = _rendered_or_400(conn, state, report_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([c.label for c in rendered.columns])
    for g in rendered.groups:
        for r in g.rows:
            w.writerow([r.get(c.id, "") for c in rendered.columns])
    name = _filename(d.title or row["name"], state.now().date(), "csv")
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/reports/{report_id}/export.json")
def export_json(report_id: int, conn: sqlite3.Connection = Db, state=State):
    row, d, rendered = _rendered_or_400(conn, state, report_id)
    name = _filename(d.title or row["name"], state.now().date(), "json")
    return JSONResponse({"title": rendered.title, "columns": [c.id for c in rendered.columns],
                         "labels": [c.label for c in rendered.columns],
                         "rows": [r for g in rendered.groups for r in g.rows],
                         "truncated": rendered.truncated},
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})
```

Both have two path segments after `/reports`, so they cannot be shadowed by the single-segment `/reports/{report_id}`; `test_export_csv_and_json` is the proof, not this sentence.

In `templates/reports.html`, replace the two `{# Task 4 adds … #}` comments with the real markup: for a saved report, `<a class="badge" href="/reports/{{ r.id }}/export.csv">CSV</a>`, the same for JSON, and a print form posting `report=view:{{ r.id }}`; for a code report, a print form posting `report={{ r.key }}`. Both print forms are wrapped in `{% if jobs %}`, target `#job` and swap `outerHTML`, exactly as the Dashboard's buttons do.

- [ ] **Step 3: The report key reaches a job**

In `web/actions.py`, give `preview` and `print_now` a `report_key: str = "open-work"` parameter and pass it as `runner.run(report_key, …)` instead of the hardcoded `REPORT_KEY`. Note that `preview` builds its PDF path from `reports.get(REPORT_KEY).output_dir` today — resolve the same key it ran, through `reports.resolve(report_key, home)`, or the preview of a view report looks for the sheet's PDF and reports that none was built. In `web/jobs.py`, pass `job.params.get("report", "open-work")` into both as `report_key=`. In `routes/jobs.py`, accept `report: str = Form("open-work")`, validate it with `registry.resolve(report, state.home)` inside a `try` that turns `ReportError` into `HTTPException(400, …)`, and put it into the params for the `preview` and `print` kinds only.

- [ ] **Step 4: Run, full suite, commit**

```bash
git add lakota_grades tests
git commit -m "web: print a saved report through the runner, and export it as CSV or JSON

Closes #25

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Done when

- `/reports` lists the built-in sheet and the parent's own reports, offers the four starters into an empty table, and links each saved report to a builder that previews live as it is edited.
- A saved report prints through the same runner the sheet uses: it archives, records a `runs` row, toasts, and respects the lock; its PDF appears under `reports/view-<id>/<date>/report.pdf`.
- CSV and JSON download with a sensible filename, and a report whose definition no longer validates is a clear 400 rather than a traceback.
- `lakota-grades run view:<id>` works from the command line, which is what makes part 2's schedules possible.
- No schema change; the open-work sheet's layout and every existing test of it are untouched; the full suite is green and pristine locally and in CI on both runners.
- Not in this plan: the Linux systemd writer and the Schedules page (Plan D part 2, issues #26 and #27); charts inside a view report (`chart` stays `null`); the friend's page and doc polish (Plan E); the residuals in issues #31 to #34.

# Report charts and custom date filtering: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A parent building a view report can add a line/bar/stacked-bar chart plotted against
a real date axis, and can narrow any report (table or chart) to an arbitrary custom start/end
date range, on top of the existing preset windows.

**Architecture:** `views.py`'s `Definition`/`build()` gain a `ChartSpec` and a bucketed
`ChartData`, built from the exact same filtered rows the table renders. One
`views.chart_config()` turns that into a Chart.js config consumed by two hosts: the live web
preview (config inlined next to a `<canvas>`) and a new `chart_render.py`, which loads the
identical config in a headless Chromium page (the app's existing bundled Playwright, already
used for Canvas/HAC sessions) and screenshots it to a PNG that `sheet.build_table_pdf` embeds.
A chart render failure degrades the report to a table plus a note; it never fails the run.
Date filtering adds a `"custom"` window alongside the presets, with `date_from`/`date_to`
bounding every source the same way the existing presets already do.

**Tech Stack:** Python 3.11+, FastAPI/Jinja2/htmx (no build step), reportlab (PDF),
Playwright (already a hard dependency, `pyproject.toml`: `playwright>=1.45`), Chart.js
(new, vendored as a single UMD file — no package manager, matching how `uplot.min.js` is
already vendored).

**Spec:** `docs/superpowers/specs/2026-09-24-report-charts-and-date-filtering-design.md`

## Global Constraints

- Python `>=3.11` (`pyproject.toml`); no new runtime dependency — Playwright is already
  required (`playwright>=1.45`), Chart.js ships as a vendored static file, not a package.
- No JS build step, no framework: every new client-side behavior is plain JS in `app.js` or a
  vendored single-file library in `fridgesheet/web/static/`, matching the existing pattern.
- `MAX_CHART_POINTS = 60` — a chart keeps only its most recent 60 buckets.
- `ViewReport.build()` (`fridgesheet/reports/view.py`) must never raise because a chart failed
  to render; it always falls back to a chart-less PDF plus a note.
- Exactly one function, `views.chart_config()`, builds the Chart.js config; both the live
  preview route and `chart_render.render_chart_png` call it — neither reimplements it.
- Every new `validate()` problem is one plain sentence, matching every existing rule in that
  function (see `fridgesheet/web/views.py`).
- Parts are independently shippable but touch the same functions in `views.py` — land Part 1
  (Tasks 1–4) and let it settle before starting Part 2 (Tasks 5–13), not as two concurrent PRs.

## Review Focus

- A saved report whose `chart.x`/`y`/`series` pointed at a column that belonged to the old
  source, after the source is changed in the builder — must be dropped/repaired the same way
  `edit()` already repairs an unreadable definition, not a 500 (Task 13).
- A report with zero rows in its window must build a chart-less report cleanly — `_chart_data`
  returns `(None, "")`, not an exception (Task 7).
- A headless chart render failure during a scheduled run must still produce a `Built` PDF with
  a note, never a failed/crashed run (Task 12).
- A custom range with `date_from` blank, `date_to` blank, or `date_from > date_to` must be a
  `validate()` problem, not a crash inside `window_start`/`window_end` (Task 1, Task 2).
- A bucket with genuinely zero matching rows on a bar/stacked-bar chart must show `0` (an even
  x-axis); a bucket with no rows on a line chart of a number column must be absent, not `0` —
  the two "nothing there" meanings must not get swapped (Task 7).

---

# Part 1 — Custom date range

## Task 1: `Definition` gains a custom date range

**Files:**
- Modify: `fridgesheet/web/views.py:13` (import), `:27` (`WINDOWS`), `:73-99` (`Definition`,
  `to_json`), `:102-131` (`from_json`), `:144-184` (`validate`), `:206-211` (`window_start`)
- Test: `tests/test_report_window.py`

**Interfaces:**
- Produces: `Definition.date_from: str`, `Definition.date_to: str`; `WINDOWS` gains
  `("custom", "Custom range", None)`; `window_start` handles `"custom"`; a new
  `_parse_plain_date(s: str) -> date | None` other tasks reuse.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report_window.py, appended
def test_a_custom_range_needs_both_dates_in_order():
    ok = views.Definition(title="x", columns=("name",), window="custom",
                          date_from="2026-09-01", date_to="2026-09-15")
    assert views.validate(ok) == []
    missing = views.Definition(title="x", columns=("name",), window="custom", date_from="2026-09-01")
    assert any("start and an end date" in p for p in views.validate(missing))
    backwards = views.Definition(title="x", columns=("name",), window="custom",
                                 date_from="2026-09-15", date_to="2026-09-01")
    assert any("on or before" in p for p in views.validate(backwards))
    garbage = views.Definition(title="x", columns=("name",), window="custom",
                               date_from="not-a-date", date_to="2026-09-15")
    assert any("start and an end date" in p for p in views.validate(garbage))


def test_a_custom_range_round_trips_through_json():
    d = views.from_json(json.dumps({"source": "items", "window": "custom",
                                    "date_from": "2026-09-01", "date_to": "2026-09-15"}))
    assert d.window == "custom" and d.date_from == "2026-09-01" and d.date_to == "2026-09-15"
    back = json.loads(d.to_json())
    assert back["date_from"] == "2026-09-01" and back["date_to"] == "2026-09-15"


def test_window_start_reads_the_custom_range():
    d = views.Definition(window="custom", date_from="2026-09-01", date_to="2026-09-15")
    start = views.window_start(d, NOW)
    assert start is not None and (start.month, start.day) == (9, 1)
```

`NOW` and `json` are already imported at the top of `tests/test_report_window.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_window.py -k custom -v`
Expected: FAIL — `date_from`/`date_to` are not attributes of `Definition` yet.

- [ ] **Step 3: Add the fields, `validate()` rule and `window_start` case**

In `fridgesheet/web/views.py`:

```python
# line 13, replace:
from datetime import UTC, datetime, timedelta
# with:
from datetime import UTC, date as _date, datetime, timedelta
```

```python
# line 27-28, replace WINDOWS with:
WINDOWS = (("all", "Any time", None), ("7d", "The last 7 days", 7), ("30d", "The last 30 days", 30),
           ("90d", "The last 90 days", 90), ("school_year", "This school year", None),
           ("custom", "Custom range", None))
```

```python
# Definition dataclass (line 73-85), add two fields after `window`:
    window: str = "all"
    date_from: str = ""              # ISO "YYYY-MM-DD", used only when window == "custom"
    date_to: str = ""
```

```python
# to_json (line 87-94), add to the dict:
            "window": self.window, "date_from": self.date_from, "date_to": self.date_to,
```

```python
# from_json's replace(...) call (line 117-129), add two lines:
            window=str(raw.get("window", d.window)),
            date_from=str(raw.get("date_from", "")),
            date_to=str(raw.get("date_to", "")),
```

```python
# new module-level helper, placed just above validate():
def _parse_plain_date(s: str) -> _date | None:
    """`date_from`/`date_to` as a plain date, or `None` when blank or unreadable -- callers
    treat `None` as "this custom range cannot be resolved", never as `datetime.min`."""
    try:
        return _date.fromisoformat(s) if s else None
    except ValueError:
        return None
```

```python
# validate() (line 144-148), replace the window check:
    if d.window not in WINDOW_KEYS:
        problems.append(f"Unknown window {d.window!r}; choose one of {', '.join(WINDOW_KEYS)}.")
    elif d.window == "custom":
        fd, td = _parse_plain_date(d.date_from), _parse_plain_date(d.date_to)
        if fd is None or td is None:
            problems.append("A custom range needs both a start and an end date.")
        elif fd > td:
            problems.append("The custom range's start date must be on or before its end date.")
```

```python
# window_start (line 206-211), add the custom case before school_year:
def window_start(d: Definition, now: datetime) -> datetime | None:
    """Where this report's rows begin, or None for "any time" (#94)."""
    if d.window == "custom":
        fd = _parse_plain_date(d.date_from)
        return datetime.combine(fd, datetime.min.time(), tzinfo=now.tzinfo) if fd else None
    if d.window == "school_year":
        return school_year_start(now)
    days = next((n for k, _, n in WINDOWS if k == d.window), None)
    return now - timedelta(days=days) if days else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_window.py -v`
Expected: PASS, including the pre-existing window tests (no regression).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/views.py tests/test_report_window.py
git commit -m "Add a custom start/end date range alongside the preset report windows"
```

## Task 2: Every source respects the custom range's end date

**Files:**
- Modify: `fridgesheet/web/views.py:214-220` (`_on_or_after`, new `_on_or_before`), `:291-351`
  (`_item_rows`, `_grade_rows`, `_change_rows`), `:413` (window label)
- Test: `tests/test_report_window.py`

**Interfaces:**
- Consumes: `_parse_plain_date`, `window_start` (Task 1).
- Produces: `window_end(d, now) -> datetime | None`, `_on_or_before(v, end) -> bool`, both used
  by Task 7's chart pipeline too (a chart is built from the same windowed rows).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report_window.py, appended
def test_a_custom_range_bounds_items_by_due_date(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    names = _names(c, _save(tmp_path, window="custom", date_from="2026-09-10", date_to="2026-09-14"))
    assert "Homework 4" not in names           # due 8/20, before the range
    assert "Reading log" not in names          # due 9/20, after the range
    assert "Lab notebook" in names             # due 9/10, the range's first day


def test_a_custom_range_bounds_changes_by_when_they_happened(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="changes", columns=["at", "kid", "what"],
               window="custom", date_from="2026-01-01", date_to="2026-09-01")
    body = c.get(f"/reports/{rid}/view").text
    assert "No rows matched this report." in body   # every seeded change happens after 9/1


def test_the_preview_names_a_custom_range(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, window="custom", date_from="2026-09-01", date_to="2026-09-15")
    body = c.get(f"/reports/{rid}/view").text
    assert "Custom range" in body and "9/1" in body and "9/15" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_window.py -k custom -v`
Expected: FAIL — the new tests bound by date_to but nothing enforces an upper bound yet.

- [ ] **Step 3: Add `window_end`, `_on_or_before`, and wire every source**

```python
# fridgesheet/web/views.py, just after _on_or_after (line 214-220):
def window_end(d: Definition, now: datetime) -> datetime | None:
    """Where this report's rows stop, or None for "through now" -- every window but "custom"
    already means that; a preset window has no far side. Inclusive of the whole end day."""
    if d.window != "custom":
        return None
    td = _parse_plain_date(d.date_to)
    return datetime.combine(td, datetime.min.time(), tzinfo=now.tzinfo) + timedelta(days=1) if td else None


def _on_or_before(v: datetime | None, end: datetime | None) -> bool:
    if end is None:
        return True
    if v is None:
        return False
    a, b = reconcile.comparable(v, end)
    return a < b
```

```python
# _item_rows (line 291-308): add `end` and the second check
def _item_rows(conn, d, *, now, rules, nicknames, prefs=None, window=None) -> list[tuple[dict, dict]]:
    out = []
    start, end = window_start(d, now), window_end(d, now)
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for v in items_store.list_items(conn, s, now=now, rules=rules, show="all", prefs=prefs, **(window or {})):
            if not _on_or_after(v.due, start) or not _on_or_before(v.due, end):
                continue
            row = {
                "kid": nicknames.get(s["key"], s["key"]), "course": v.course_short, "name": v.name,
                "status": v.status, "due": _date(v.due, now), "points": _num(v.points), "kind": v.kind,
                "sources": " + ".join(v.sources), "flag": (v.flag or "").replace("_", " "),
                "open": _yes(v.overdue or v.upcoming), "actionable": _yes(v.actionable),
                "notes": _num(v.notes), "cases": verdicts.standing(v, "") if v.verdict.state in ("question", "decided", "waiting") else "",
            }
            out.append((row, _keys("items", row, {"due": v.due, "points": v.points, "notes": v.notes})))
    return out
```

(the `row = {...}` literal above is unchanged from the current file — only the `if not
_on_or_after(...)` line and the `start, end = ...` line are new.)

```python
# _grade_rows (line 311-322): filter each point by `end` too
def _grade_rows(conn, d, *, now, nicknames, prefs=None) -> list[tuple[dict, dict]]:
    out = []
    end = window_end(d, now)
    for s in students_store.visible(conn):
        if d.scope and s["key"] not in d.scope:
            continue
        for series in trends_store.grade_series(conn, student_id=s["id"], since=window_start(d, now), prefs=prefs):
            for at, value in series.points:
                if not _on_or_before(at, end):
                    continue
                row = {"kid": nicknames.get(s["key"], s["key"]), "course": series.course_short,
                       "source": series.source, "official": "yes" if series.official else "", "label": series.label,
                       "value": _num(value), "at": _date(at, now)}
                out.append((row, _keys("grades", row, {"at": at, "value": value})))
    return out
```

```python
# _change_rows (line 325-351): `end` computed once, checked in the loop
def _change_rows(conn, d, *, now, nicknames, prefs=None) -> tuple[list[tuple[dict, dict]], int]:
    visible = students_store.visible(conn)
    keys = {s["key"] for s in visible}
    start = window_start(d, now) or now - timedelta(days=365)
    end = window_end(d, now)
    if d.scope:
        feeds = [changes_store.since(conn, since=start, limit=MAX_ROWS, prefs=prefs, student_id=s["id"])
                 for s in visible if s["key"] in d.scope]
        events = [e for f in feeds for e in f]
        dropped = sum(f.dropped for f in feeds)
    else:
        feed = changes_store.since(conn, since=start, limit=MAX_ROWS, prefs=prefs)
        events, dropped = list(feed), feed.dropped
    out = []
    for e in events:
        if e.student_key not in keys or (d.scope and e.student_key not in d.scope) or not _on_or_before(e.at, end):
            continue
        row = {"at": _date(e.at, now, with_time=True), "kid": nicknames.get(e.student_key, e.student_key),
               "what": e.label, "item": e.item_name or "", "course": e.course_short or "",
               "source": e.source or "", "detail": e.detail}
        out.append((row, _keys("changes", row, {"at": e.at})))
    return out, dropped
```

```python
# build()'s window label (line 413), replace:
    label = next((l for k, l, _ in WINDOWS if k == d.window), "") if d.window != "all" else ""
# with:
    if d.window == "custom":
        fd, td = _parse_plain_date(d.date_from), _parse_plain_date(d.date_to)
        label = f"Custom range ({dates.md(fd)}–{dates.md(td)})" if fd and td else "Custom range"
    elif d.window != "all":
        label = next((l for k, l, _ in WINDOWS if k == d.window), "")
    else:
        label = ""
```

`dates.md` needs importing at the top of `views.py`: add `from .. import dates` next to the
existing `from .. import reconcile, verdicts` import.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_window.py -v`
Expected: PASS, all of them, including the Task 1 tests.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/views.py tests/test_report_window.py
git commit -m "Bound items, grades and changes by a custom range's end date"
```

## Task 3: Builder UI for the custom range

**Files:**
- Modify: `fridgesheet/web/templates/report_builder.html:15-17`,
  `fridgesheet/web/routes/reports.py:24-38` (`definition_from_form`), `:98-116` (`rebuild`)
- Test: `tests/test_web_reports_page.py`

**Interfaces:**
- Consumes: `Definition.date_from`/`.date_to` (Task 1).
- Produces: form fields `date_from`, `date_to`, read by `definition_from_form`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_reports_page.py, appended
def test_the_builder_saves_a_custom_range(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    r = c.post("/reports/new", data={"title": "Recap", "source": "items", "columns": ["kid", "name"],
                                     "window": "custom", "date_from": "2026-09-01", "date_to": "2026-09-15"})
    assert r.status_code == 200 and "Saved." in r.text
    body = c.get("/reports/1").text
    assert 'name="date_from" value="2026-09-01"' in body and 'name="date_to" value="2026-09-15"' in body


def test_the_builder_shows_the_custom_range_problem(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    r = c.post("/reports/new", data={"title": "Recap", "source": "items", "columns": ["kid", "name"],
                                     "window": "custom", "date_from": "2026-09-15", "date_to": "2026-09-01"})
    assert "on or before" in r.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_reports_page.py -k custom_range -v`
Expected: FAIL — the form has no `date_from`/`date_to` fields, so nothing round-trips them.

- [ ] **Step 3: Add the fields**

```python
# fridgesheet/web/routes/reports.py, definition_from_form (line 31-38):
    return views.from_json(views.Definition(
        title=form.get("title", ""), source=form.get("source", "items"),
        scope=tuple(form.getlist("scope")), columns=tuple(form.getlist("columns")),
        filters=tuple(filters), group_by=group_by, sort=tuple(sort),
        orientation=form.get("orientation", "portrait"),
        per_kid_sections=bool(form.get("per_kid_sections")),
        window=form.get("window", "all"),
        date_from=form.get("date_from", ""), date_to=form.get("date_to", ""),
    ).to_json())
```

```python
# rebuild() (line 106-112), carry the two fields through unchanged -- they don't depend on
# the source, unlike columns/filters/sort/group_by:
    d = views.Definition(
        title=d.title, source=d.source, scope=d.scope,
        columns=tuple(c for c in d.columns if c in known) or tuple(views.DEFAULT_COLUMNS.get(d.source, ())),
        filters=tuple(f for f in d.filters if f.get("field") in known),
        group_by=d.group_by if d.group_by in known else None,
        sort=tuple(s for s in d.sort if s.get("column") in known),
        orientation=d.orientation, per_kid_sections=d.per_kid_sections, window=d.window,
        date_from=d.date_from, date_to=d.date_to)
```

```html
<!-- fridgesheet/web/templates/report_builder.html, replace line 15-17: -->
  <p><label>Rows from
     <select name="window" onchange="document.getElementById('customRange').hidden = this.value !== 'custom'">{% for key, label, _ in WINDOWS %}<option value="{{ key }}" {{ 'selected' if d.window == key }}>{{ label }}</option>{% endfor %}</select></label>
     <span class="muted">by due date for assignments, by when it happened for grades and changes</span>
     <span id="customRange" {{ 'hidden' if d.window != 'custom' }}>
       <label>from <input type="date" name="date_from" value="{{ d.date_from }}"></label>
       <label>to <input type="date" name="date_to" value="{{ d.date_to }}"></label>
     </span></p>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_reports_page.py -k custom_range -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates/report_builder.html fridgesheet/web/routes/reports.py tests/test_web_reports_page.py
git commit -m "Add a custom date-range control to the report builder"
```

## Task 4: Whole-branch check for Part 1

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/ -v 2>&1 | tee /tmp/fridgesheet-part1-tests.log`
Expected: every test passes, including `test_report_window.py`, `test_web_reports_page.py`,
`test_web_views.py`, `test_report_view.py`, `test_reports.py`.

- [ ] **Step 2: Confirm no other caller constructs `Definition` or `Rendered` positionally in
  a way the two new fields would break**

Run: `grep -rn "views.Definition(" fridgesheet tests | grep -v "title=\|source=\|window="`
Expected: no output — every construction site already uses keyword arguments, so appending
`date_from`/`date_to` at the end of the dataclass is a non-breaking change.

This is a natural point to open a PR for Part 1 alone, per the spec's delivery-sequencing note
— Part 2 edits the same functions and should not be developed as a second, concurrently open
branch against them.

---

# Part 2 — Report charts

## Task 5: `ChartSpec` on `Definition`, with validation and JSON round-trip

**Files:**
- Modify: `fridgesheet/web/views.py:20-31` (constants), `:73-99` (`Definition`, `to_json`),
  `:102-131` (`from_json`), `:144-184` (`validate`)
- Test: `tests/test_web_views.py`

**Interfaces:**
- Produces: `ChartSpec(type, x, y=None, series=None, bucket="week")`, `CHART_TYPES`,
  `BUCKETS`, `MAX_CHART_POINTS`, `Definition.chart: ChartSpec | None`. Task 7 consumes all of
  these; Task 13's builder UI consumes `CHART_TYPES`/`BUCKETS`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_views.py, appended
def test_a_chart_needs_a_real_date_column_of_its_source():
    ok = views.Definition(title="x", source="grades", columns=("value",),
                          chart=views.ChartSpec(type="line", x="at", y="value"))
    assert views.validate(ok) == []
    bad_x = views.Definition(title="x", source="grades", columns=("value",),
                             chart=views.ChartSpec(type="line", x="value", y="value"))
    assert any("date" in p for p in views.validate(bad_x))


def test_a_stacked_bar_chart_needs_a_series_column():
    d = views.Definition(title="x", source="items", columns=("name",),
                        chart=views.ChartSpec(type="stacked_bar", x="due"))
    assert any("series" in p for p in views.validate(d))
    fixed = views.Definition(title="x", source="items", columns=("name",),
                            chart=views.ChartSpec(type="stacked_bar", x="due", series="status"))
    assert views.validate(fixed) == []


def test_a_chart_round_trips_through_json():
    d = views.from_json(json.dumps({"source": "items", "chart": {
        "type": "bar", "x": "due", "y": None, "series": "status", "bucket": "day"}}))
    assert d.chart == views.ChartSpec(type="bar", x="due", series="status", bucket="day")
    back = json.loads(d.to_json())["chart"]
    assert back == {"type": "bar", "x": "due", "y": None, "series": "status", "bucket": "day"}
    assert views.from_json(json.dumps({"source": "items"})).chart is None       # stored before this feature
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_views.py -k chart -v`
Expected: FAIL — `ChartSpec` does not exist yet.

- [ ] **Step 3: Add `ChartSpec` and wire it through**

```python
# fridgesheet/web/views.py, after WINDOW_KEYS (line 29):
CHART_TYPES = ("line", "bar", "stacked_bar")
BUCKETS = ("day", "week", "month")
MAX_CHART_POINTS = 60          # a chart is illustrative, not exhaustive
```

```python
# a new dataclass, placed after Column (line 39-42):
@dataclass(frozen=True)
class ChartSpec:
    type: str
    x: str                      # a date column of the source
    y: str | None = None        # a number column, or None = count of rows
    series: str | None = None   # splits the chart into lines/segments; required for stacked_bar
    bucket: str = "week"
```

```python
# Definition (line 73-85), replace the stub field:
    chart: ChartSpec | None = None
```

```python
# to_json (line 87-94), replace the chart line:
            "chart": ({"type": self.chart.type, "x": self.chart.x, "y": self.chart.y,
                      "series": self.chart.series, "bucket": self.chart.bucket} if self.chart else None),
```

```python
# from_json, a helper placed just above it:
def _chart_from(raw: dict) -> ChartSpec | None:
    """Whatever shape `chart` has in the stored JSON, built as-is -- `validate()` is where a
    malformed chart is named precisely, the same discipline `filters`/`sort` already follow."""
    c = raw.get("chart")
    if not isinstance(c, dict) or not c.get("type"):
        return None
    return ChartSpec(type=str(c.get("type", "")), x=str(c.get("x", "")),
                     y=(str(c["y"]) if c.get("y") else None),
                     series=(str(c["series"]) if c.get("series") else None),
                     bucket=str(c.get("bucket") or "week"))
```

```python
# from_json's replace(...) call, add:
            chart=_chart_from(raw),
```

```python
# validate(), just before the final `return problems` (line 184):
    if d.chart is not None:
        ch = d.chart
        if ch.type not in CHART_TYPES:
            problems.append(f"Unknown chart type {ch.type!r}; choose one of {', '.join(CHART_TYPES)}.")
        if ch.bucket not in BUCKETS:
            problems.append(f"Unknown chart bucket {ch.bucket!r}; choose one of {', '.join(BUCKETS)}.")
        if ch.x not in known or known[ch.x].kind != "date":
            problems.append("The chart's date field must be one of the source's date columns.")
        if ch.y is not None and (ch.y not in known or known[ch.y].kind != "number"):
            problems.append("The chart's value field must be one of the source's number columns.")
        if ch.type == "stacked_bar" and ch.series is None:
            problems.append("A stacked/grouped bar chart needs a series column.")
        if ch.series is not None and ch.series not in known:
            problems.append(f"{ch.series!r} is not a column of the {d.source} source.")
    return problems
```

(`known` is already bound earlier in `validate()`, right after the source check.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_views.py -v`
Expected: PASS, all of them.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/views.py tests/test_web_views.py
git commit -m "Add ChartSpec to view report definitions, with validation and JSON round-trip"
```

## Task 6: Shared week/month bucket boundaries

**Files:**
- Modify: `fridgesheet/dates.py`, `fridgesheet/web/stores/trends.py:14, 102-103, 115, 167`
- Test: `tests/test_dates.py` (create if it does not already exist — check first)

**Interfaces:**
- Produces: `dates.week_start(d: date) -> date`, `dates.month_start(d: date) -> date`, reused
  by Task 7's `_chart_data` and by `trends.py` (replacing its private `_monday`).

- [ ] **Step 1: Check for an existing dates test file**

Run: `ls tests/test_dates.py 2>&1 || echo "no existing file"`

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_dates.py (new, or appended if it already exists)
from datetime import date
from fridgesheet import dates


def test_week_start_is_the_monday_of_that_week():
    assert dates.week_start(date(2026, 9, 16)) == date(2026, 9, 14)     # a Wednesday
    assert dates.week_start(date(2026, 9, 14)) == date(2026, 9, 14)     # already a Monday


def test_month_start_is_the_first_of_that_month():
    assert dates.month_start(date(2026, 9, 16)) == date(2026, 9, 1)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_dates.py -v`
Expected: FAIL — `dates.week_start`/`dates.month_start` do not exist yet.

- [ ] **Step 4: Add the two helpers and dedup `trends.py`**

```python
# fridgesheet/dates.py -- add timedelta to the existing import line:
from datetime import date, datetime, timedelta
```

```python
# fridgesheet/dates.py, new functions:
def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)
```

```python
# fridgesheet/web/stores/trends.py:14, add the import:
from ... import dates as _dates
```

```python
# fridgesheet/web/stores/trends.py:102-103, delete _monday entirely, then replace its two
# call sites (lines ~115 and ~167, both `_monday(now.date())`) with:
    starts = [_dates.week_start(now.date()) - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_dates.py tests/test_web_trends_store.py tests/test_web_trends_page.py -v`
Expected: PASS — the Trends page's own tests confirm the dedup changed no behavior.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/dates.py fridgesheet/web/stores/trends.py tests/test_dates.py
git commit -m "Share week/month bucket boundaries between Trends and the new chart pipeline"
```

## Task 7: Bucketed chart data, built from the report's own rows

**Files:**
- Modify: `fridgesheet/web/views.py` (new dataclasses, `_chart_data`, `Rendered`, `build()`)
- Test: `tests/test_report_chart.py` (new)

**Interfaces:**
- Consumes: `ChartSpec`, `CHART_TYPES`, `BUCKETS`, `MAX_CHART_POINTS` (Task 5);
  `dates.week_start`/`month_start` (Task 6); the `(row, keys)` pairs `build()` already computes.
- Produces: `ChartData(type, x_label, y_label, series: list[ChartSeries])`,
  `ChartSeries(label, points: list[tuple[str, float]])`, `Rendered.chart`,
  `Rendered.chart_note`. Task 8's `chart_config()` and Task 12's PDF wiring consume `Rendered.chart`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report_chart.py (new)
"""Bucketing and aggregation for a report's chart -- built from the same filtered, windowed,
scoped rows the table shows, never a separate query."""
from __future__ import annotations

import json

from fridgesheet import late_rules
from fridgesheet.web import db, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])          # tests/test_web_views.py's own idiom


def _save(home, **d):
    conn = db.open_db(home)
    rid = store.create(conn, "Mine", json.dumps({"title": "Mine", "source": "items", "columns": ["name", "due"], **d}),
                       now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def _rendered(home, rid):
    conn = db.open_db(home)
    row = store.by_id(conn, rid)
    d = views.from_json(row["definition"])
    rendered = views.build(conn, d, now=NOW, rules=RULES, nicknames={"Alex": "Al"})
    conn.close()
    return row, d, rendered


def test_a_stacked_bar_chart_counts_rows_per_bucket_per_series(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="items",
               chart={"type": "stacked_bar", "x": "due", "y": None, "series": "status", "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert rendered.chart is not None
    assert rendered.chart.type == "stacked_bar"
    total_points = sum(len(s.points) for s in rendered.chart.series)
    assert total_points > 0
    assert all(isinstance(v, float) for s in rendered.chart.series for _, v in s.points)


def test_a_line_chart_averages_a_number_column_and_skips_blank_buckets(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="grades", columns=["course", "value", "at"],
               chart={"type": "line", "x": "at", "y": "value", "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert rendered.chart is not None and rendered.chart.type == "line"
    # every point is a real observed average, never a manufactured zero for a silent week
    assert all(v != 0.0 for s in rendered.chart.series for _, v in s.points) or not rendered.chart.series


def test_a_report_with_no_rows_has_no_chart(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="items", scope=["nobody"],
               chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert rendered.chart is None and rendered.chart_note == ""


def test_a_chart_field_need_not_be_a_displayed_column(tmp_path):
    """The chart's x/y/series columns are independent of which columns the table shows."""
    seed(tmp_path).close()
    rid = _save(tmp_path, source="items", columns=["name"],           # "due" and "status" not shown
               chart={"type": "stacked_bar", "x": "due", "y": None, "series": "status", "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert views.validate(d) == [] and rendered.chart is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_chart.py -v`
Expected: FAIL — `rendered.chart` does not exist on `Rendered` yet, and `_save`'s `chart` dict
is silently dropped by `from_json` until Task 5/7 land (Task 5 already landed; this task wires
the data through).

- [ ] **Step 3: Add `ChartData`/`ChartSeries`, `_chart_data`, and wire `build()`**

```python
# fridgesheet/web/views.py, new dataclasses, placed after Rendered (line 193-199):
@dataclass
class ChartSeries:
    label: str
    points: list[tuple[str, float]] = field(default_factory=list)   # (bucket label, value)


@dataclass
class ChartData:
    type: str
    x_label: str
    y_label: str
    series: list[ChartSeries] = field(default_factory=list)
```

```python
# Rendered gains two fields (line 193-199):
@dataclass
class Rendered:
    title: str
    columns: list[Column]
    groups: list[Group] = field(default_factory=list)
    truncated: int = 0
    window: str = ""
    chart: ChartData | None = None
    chart_note: str = ""
```

```python
# a new helper, placed just above _chart_data:
def _bucket_start(dt: datetime, bucket: str):
    d = dt.date()
    if bucket == "day":
        return d
    if bucket == "month":
        return dates.month_start(d)
    return dates.week_start(d)


def _chart_data(source: str, spec: ChartSpec, kept: list[tuple[dict, dict]]) -> tuple[ChartData | None, str]:
    """The chart half of `build()`'s output, from the exact rows the table already kept -- a
    chart can never show a point the table doesn't. `spec.x`/`spec.y`/`spec.series` need not be
    among the report's displayed columns; `row` always carries every column of the source.

    A row with no `x` value cannot be plotted and is dropped from the chart only. A row whose
    `y` column is blank is excluded from its bucket's average, not treated as a zero -- a
    missing grade observation must not pull a trend line down. `bar`/`stacked_bar` buckets are
    zero-filled so the x-axis is even (`weekly_counts`' convention); `line` buckets are left
    absent when nothing landed in them (`grade_series`' convention) -- a flat stretch is the
    absence of points, not a plotted dip to zero.
    """
    known = COLUMNS[source]
    dropped = 0
    buckets: dict = {}
    for row, keys in kept:
        x_iso = keys.get(spec.x, "")
        if not x_iso:
            dropped += 1
            continue
        if spec.y and row.get(spec.y, "") == "":
            continue
        y = float(row[spec.y]) if spec.y else 1.0
        label = row.get(spec.series, "") if spec.series else (known[spec.y].label if spec.y else "Count")
        bstart = _bucket_start(datetime.fromisoformat(x_iso), spec.bucket)
        buckets.setdefault(bstart, {}).setdefault(label, []).append(y)
    if not buckets:
        return None, ""
    starts = sorted(buckets)
    overflow = max(0, len(starts) - MAX_CHART_POINTS)
    starts = starts[-MAX_CHART_POINTS:]
    labels_seen: list[str] = []
    for s in starts:
        for label in buckets[s]:
            if label not in labels_seen:
                labels_seen.append(label)
    zero_fill = spec.type in ("bar", "stacked_bar")
    series_out = []
    for label in labels_seen:
        points = []
        for s in starts:
            values = buckets[s].get(label)
            if values is None:
                if zero_fill:
                    points.append((dates.md(s), 0.0))
                continue
            value = (sum(values) / len(values)) if spec.y else float(len(values))
            points.append((dates.md(s), value))
        series_out.append(ChartSeries(label=label, points=points))
    notes = []
    if dropped:
        notes.append(f"{dropped} row(s) with no date are not charted")
    if overflow:
        notes.append(f"Chart shows the most recent {MAX_CHART_POINTS} of {MAX_CHART_POINTS + overflow}; "
                     "choose a coarser bucket or a shorter range to see the rest")
    y_label = known[spec.y].label if spec.y else "Count"
    return ChartData(type=spec.type, x_label=known[spec.x].label, y_label=y_label, series=series_out), "; ".join(notes)
```

```python
# build()'s return (end of the function), replace:
    return Rendered(d.title, columns, groups, truncated, label)
# with:
    chart, chart_note = _chart_data(d.source, d.chart, kept) if d.chart else (None, "")
    return Rendered(d.title, columns, groups, truncated, label, chart=chart, chart_note=chart_note)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_chart.py tests/test_web_views.py tests/test_report_window.py -v`
Expected: PASS, all of them.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/views.py tests/test_report_chart.py
git commit -m "Build bucketed chart data from a report's own filtered rows"
```

## Task 8: `chart_config()` — one Chart.js config for both hosts

**Files:**
- Modify: `fridgesheet/web/views.py`
- Test: `tests/test_report_chart.py`

**Interfaces:**
- Consumes: `ChartData`/`ChartSeries` (Task 7).
- Produces: `chart_config(data: ChartData) -> dict`, consumed by Task 9 (web preview route)
  and Task 10 (`chart_render.py`) — neither may build its own version of this dict.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_chart.py, appended
def test_chart_config_is_one_shape_for_every_chart_type():
    data = views.ChartData(type="stacked_bar", x_label="Due", y_label="Count", series=[
        views.ChartSeries(label="MISSING", points=[("9/8", 2.0), ("9/15", 0.0)]),
        views.ChartSeries(label="LATE", points=[("9/8", 0.0), ("9/15", 1.0)]),
    ])
    cfg = views.chart_config(data)
    assert cfg["type"] == "bar"
    assert cfg["data"]["labels"] == ["9/8", "9/15"]
    assert [ds["label"] for ds in cfg["data"]["datasets"]] == ["MISSING", "LATE"]
    assert cfg["data"]["datasets"][0]["data"] == [2.0, 0.0]
    assert cfg["options"]["scales"]["x"]["stacked"] is True

    line = views.chart_config(views.ChartData(type="line", x_label="Seen", y_label="Value",
                                              series=[views.ChartSeries(label="Value", points=[("9/8", 91.2)])]))
    assert line["type"] == "line" and line["options"]["scales"]["x"]["stacked"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_chart.py -k chart_config -v`
Expected: FAIL — `views.chart_config` does not exist yet.

- [ ] **Step 3: Add `chart_config()`**

```python
# fridgesheet/web/views.py, after _chart_data:
_CHART_JS_TYPE = {"line": "line", "bar": "bar", "stacked_bar": "bar"}
_SERIES_COLORS = ("#1f5fa8", "#b3261e", "#2e7d32", "#6b3fa0", "#b8860b", "#00707f")


def chart_config(data: ChartData) -> dict:
    """A Chart.js `type`/`data`/`options` object, built once -- the live web preview and the
    headless PDF capture (`chart_render.py`) both draw from this, so neither can disagree with
    the other about what a chart looks like."""
    labels: list[str] = []
    for s in data.series:
        for label, _ in s.points:
            if label not in labels:
                labels.append(label)
    datasets = []
    for i, s in enumerate(data.series):
        by_label = dict(s.points)
        color = _SERIES_COLORS[i % len(_SERIES_COLORS)]
        datasets.append({"label": s.label, "data": [by_label.get(l) for l in labels],
                         "borderColor": color, "backgroundColor": color, "fill": False})
    stacked = data.type == "stacked_bar"
    return {
        "type": _CHART_JS_TYPE[data.type],
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "animation": False,
            "scales": {
                "x": {"stacked": stacked, "title": {"display": True, "text": data.x_label}},
                "y": {"stacked": stacked, "title": {"display": True, "text": data.y_label}},
            },
        },
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_chart.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/views.py tests/test_report_chart.py
git commit -m "Add chart_config(), the one Chart.js config shape shared by preview and PDF"
```

## Task 9: Live web preview draws the chart

**Files:**
- Create: `fridgesheet/web/static/chart.umd.min.js` (vendored)
- Modify: `fridgesheet/web/routes/reports.py` (import `json`, `_chart_json`, `preview()`, `view()`)
- Modify: `fridgesheet/web/templates/_report_preview.html`, `report_builder.html`,
  `report_view.html`, `fridgesheet/web/static/app.js`
- Test: `tests/test_web_reports_page.py`

**Interfaces:**
- Consumes: `views.chart_config` (Task 8).
- Produces: `[data-report-chart]`/`[data-chart-config]` markup and `attachReportCharts` in
  `app.js`, which Task 10 does **not** reuse (the headless capture builds its own standalone
  HTML) but which establishes the exact config JSON shape Task 10 must also emit.

- [ ] **Step 1: Vendor Chart.js**

Download the current Chart.js UMD build (`chart.umd.min.js` from the official `chart.js`
distribution) to `fridgesheet/web/static/chart.umd.min.js`, matching how `uplot.min.js` is
already vendored in the same directory (single file, no source map required, MIT-licensed).
Confirm licensing is compatible with this project's MIT license before committing it.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_web_reports_page.py, appended
def test_a_saved_chart_report_shows_a_canvas_and_its_config(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="items", columns=["kid", "name", "due"],
               chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    body = c.get(f"/reports/{rid}/view").text
    assert "data-report-chart" in body and "data-chart-config" in body
    assert '"type": "bar"' in body or '"type":"bar"' in body


def test_a_table_only_report_shows_no_chart_markup(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="items", columns=["kid", "name"])
    body = c.get(f"/reports/{rid}/view").text
    assert "data-report-chart" not in body
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_reports_page.py -k report_chart -v`
Expected: FAIL — nothing emits `data-report-chart` yet.

- [ ] **Step 4: Wire the route and templates**

```python
# fridgesheet/web/routes/reports.py, add near the top imports:
import json
```

```python
# a small helper, placed above preview():
def _chart_json(rendered) -> str | None:
    return json.dumps(views.chart_config(rendered.chart)) if rendered and rendered.chart else None
```

```python
# preview() (line 118-129), add chart_json to the render_partial call:
    return render_partial(request, conn, "_report_preview.html", rendered=rendered, problems=problems,
                          chart_json=_chart_json(rendered))
```

```python
# view() (line 132-137), add chart_json:
    row, d, rendered = _rendered_or_400(conn, state, report_id)
    return render(request, conn, "report_view.html", report=row, rendered=rendered, now=state.now(),
                  chart_json=_chart_json(rendered))
```

```html
<!-- fridgesheet/web/templates/_report_preview.html, insert after the row-count <p> (line 7),
     before the groups loop: -->
  {% if rendered.chart %}
  <div class="chart-holder">
    <canvas data-report-chart width="700" height="260"></canvas>
    <script type="application/json" data-chart-config>{{ chart_json | safe }}</script>
  </div>
  {% if rendered.chart_note %}<p class="muted">{{ rendered.chart_note }}</p>{% endif %}
  {% endif %}
```

```html
<!-- fridgesheet/web/templates/report_builder.html, right after {% block content %}: -->
<script src="/static/chart.umd.min.js" defer></script>
```

```html
<!-- fridgesheet/web/templates/report_view.html, add before the app.js script tag (line 9): -->
<script src="/static/chart.umd.min.js" defer></script>
```

```js
// fridgesheet/web/static/app.js, added after the existing attachCharts block:

// Report charts: `views.chart_config()`'s output, inlined as JSON next to a `<canvas>`.
// Unlike Trends' uPlot charts, a report's chart has no URL of its own -- a builder preview is
// an unsaved definition with no report id to fetch by -- so the config travels with the page
// rather than being fetched. Both `report_builder.html` and `report_view.html` load
// chart.umd.min.js on their own initial page load, before any htmx swap can bring in a
// chart-bearing partial, so there is no "library not loaded yet" race to poll for here (unlike
// attachCharts' wait loop, which exists for the first draw on page load itself).
function attachReportCharts(root) {
  var els = root.querySelectorAll ? root.querySelectorAll("[data-report-chart]") : [];
  Array.prototype.forEach.call(els, function (canvas) {
    if (canvas.dataset.drawn) return;
    var script = canvas.parentNode.querySelector("[data-chart-config]");
    if (!script) return;
    canvas.dataset.drawn = "1";
    try {
      new Chart(canvas.getContext("2d"), JSON.parse(script.textContent));
    } catch (e) {
      canvas.parentNode.innerHTML = '<p class="warn">The chart could not load.</p>';
    }
  });
}
document.addEventListener("DOMContentLoaded", function () { attachReportCharts(document); });
document.addEventListener("htmx:afterSwap", function (e) { attachReportCharts(e.detail.target); });
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_reports_page.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/static/chart.umd.min.js fridgesheet/web/routes/reports.py \
        fridgesheet/web/templates/_report_preview.html fridgesheet/web/templates/report_builder.html \
        fridgesheet/web/templates/report_view.html fridgesheet/web/static/app.js tests/test_web_reports_page.py
git commit -m "Draw a report's chart in the live preview and standalone view"
```

## Task 10: Headless chart capture for the PDF

**Files:**
- Create: `fridgesheet/chart_render.py`
- Test: `tests/test_chart_render.py` (new)

**Interfaces:**
- Consumes: `views.chart_config()`'s output shape (Task 8); the vendored
  `fridgesheet/web/static/chart.umd.min.js` (Task 9).
- Produces: `render_chart_png(config: dict, *, width_px=1400, height_px=500) -> bytes`,
  consumed by Task 12.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chart_render.py (new)
"""Headless-rendered chart images for the PDF path. Gated on the same bundled Chromium
`doctor.py` already health-checks -- if that probe fails on this machine, there is nothing this
test can prove here that the doctor test suite hasn't already reported."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from fridgesheet import chart_render, doctor
from fridgesheet.config import Settings


def _chromium_available(tmp_path) -> bool:
    checks = doctor.checks(Settings(home=tmp_path), tmp_path)
    return next(c for c in checks if c.name == "chromium").ok


def test_render_chart_png_returns_a_png_at_the_requested_size(tmp_path):
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    config = {"type": "bar", "data": {"labels": ["9/8", "9/15"],
                                     "datasets": [{"label": "Count", "data": [1, 2]}]},
             "options": {}}
    png = chart_render.render_chart_png(config, width_px=400, height_px=200)
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.width == 800 and img.height == 400        # device_scale_factor=2
```

`PIL` is already used in this test suite without a `pyproject.toml` entry of its own
(`tests/test_packaging.py:300`, pulled in transitively) — importing it here follows existing
precedent rather than adding a new dependency.

- [ ] **Step 2: Run the test to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_chart_render.py -v`
Expected: FAIL — `fridgesheet.chart_render` does not exist yet.

- [ ] **Step 3: Write `chart_render.py`**

```python
"""Headless-rendered chart images for the PDF path (`sheet.build_table_pdf`'s `chart_png`).

`views.chart_config()` is the one Chart.js config the live web preview and this module both
draw from; this module's only job is getting that same drawing onto paper, via the app's
existing bundled Chromium (`session.py` uses the same Playwright install for Canvas/HAC
sessions; `doctor.py` already health-checks it). A fresh, non-persistent browser context is
used here -- unlike `session.browser()`, a chart capture has no cookies or login profile to
keep between runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

_STATIC = Path(__file__).parent / "web" / "static"
_CHART_JS = (_STATIC / "chart.umd.min.js").read_text(encoding="utf-8")

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0}}</style>
<script>{chart_js}</script></head>
<body><canvas id="c" width="{width}" height="{height}"></canvas>
<script>
var cfg = {config};
cfg.options = cfg.options || {{}};
cfg.options.animation = {{onComplete: function () {{ window.__chartReady = true; }}}};
cfg.options.responsive = false;
new Chart(document.getElementById("c").getContext("2d"), cfg);
</script></body></html>"""


def render_chart_png(config: dict, *, width_px: int = 1400, height_px: int = 500) -> bytes:
    """A Chart.js `config` (from `views.chart_config`), drawn headlessly and returned as a PNG
    at 2x scale for print sharpness. Raises on anything that stops it -- a missing/broken
    Chromium, a page that never signals ready -- so the caller decides how to degrade
    (`reports/view.py` falls back to a chart-less PDF rather than failing the run)."""
    html = _HTML.format(chart_js=_CHART_JS, width=width_px, height=height_px, config=json.dumps(config))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width_px, "height": height_px}, device_scale_factor=2)
            page.set_content(html)
            page.wait_for_function("window.__chartReady === true", timeout=10000)
            return page.locator("canvas").screenshot()
        finally:
            browser.close()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_chart_render.py -v`
Expected: PASS (or a clean, explicit skip on a machine with no Chromium installed).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/chart_render.py tests/test_chart_render.py
git commit -m "Add headless Chart.js rendering to a PNG, for embedding a chart in a PDF"
```

## Task 11: `build_table_pdf` embeds the chart image

**Files:**
- Modify: `fridgesheet/sheet.py:24` (import), `:254-282` (`build_table_pdf`)
- Test: `tests/test_report_view.py`

**Interfaces:**
- Consumes: PNG bytes shaped like `chart_render.render_chart_png`'s return value.
- Produces: `build_table_pdf(..., chart_png: bytes | None = None)`, consumed by Task 12.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_view.py, add near the top:
from fridgesheet import sheet
from fridgesheet.web import views
```

```python
# tests/test_report_view.py, appended
def test_build_table_pdf_embeds_a_chart_image_when_given_one(tmp_path):
    png_bytes = _tiny_png()          # a minimal real PNG -- reportlab's Image flowable opens it with PIL
    rendered = views.Rendered("Recap", [views.Column("name", "Name", "text")],
                              [views.Group("", [{"name": "Quiz 1"}])])
    out = tmp_path / "r.pdf"
    pages = sheet.build_table_pdf(rendered, out, title="Recap", printed_at=NOW, chart_png=png_bytes)
    assert pages >= 1 and out.exists()


def _tiny_png() -> bytes:
    """A 1x1 white PNG, small enough to inline here rather than shipping a fixture file."""
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
```

`NOW` is already imported at the top of `tests/test_report_view.py` (`from tests.web_fixtures
import NOW, seed`).

- [ ] **Step 2: Run the test to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_view.py -k embeds_a_chart -v`
Expected: FAIL — `build_table_pdf` has no `chart_png` parameter yet.

- [ ] **Step 3: Add the parameter and the flowable**

```python
# fridgesheet/sheet.py:24, add Image to the existing import:
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
```

```python
# fridgesheet/sheet.py, add `import io` near the top with the other stdlib imports.
```

```python
# build_table_pdf's signature (line 254-255):
def build_table_pdf(rendered, out_path: Path, *, title: str, printed_at: datetime,
                    orientation: str = "portrait", per_kid_sections: bool = False, note: str | None = None,
                    chart_png: bytes | None = None) -> int:
```

```python
# build_table_pdf's story construction (line 265), insert the image right after the header:
    story: list = [Paragraph(_esc(title), H1), Paragraph(long_date(printed_at), SM), Spacer(1, 8)]
    if chart_png:
        story += [Image(io.BytesIO(chart_png), width=width, height=width * 500 / 1400), Spacer(1, 10)]
    if not rendered.groups:
```

(`width` is already computed just above, from the page and margins; `500/1400` matches
`chart_render`'s default `height_px`/`width_px` so the embedded image keeps its aspect ratio —
if either module's defaults ever change, change both together.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_view.py -v`
Expected: PASS, all of them (no regression on reports built without a chart).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/sheet.py tests/test_report_view.py
git commit -m "Embed a chart image in a view report's PDF when the report has one"
```

## Task 12: `ViewReport.build()` renders the chart, and degrades cleanly on failure

**Files:**
- Modify: `fridgesheet/reports/view.py`
- Test: `tests/test_report_view.py`

**Interfaces:**
- Consumes: `chart_render.render_chart_png` (Task 10), `views.chart_config` (Task 8),
  `sheet.build_table_pdf`'s `chart_png` parameter (Task 11).
- Produces: the guarantee named in Global Constraints — a chart render failure never raises
  out of `build()`.

**Files (test):** `tests/test_report_view.py` — it already has `_save`, `_ctx` and the
`reports.resolve(f"view:{rid}", tmp_path).build({}, ctx)` idiom every `ViewReport` test uses.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report_view.py, add near the top:
from unittest.mock import patch
```

```python
# tests/test_report_view.py, appended (uses this file's own _save/_ctx, defined at lines
# 17 and 130):
@needs_pdftotext
def test_a_chart_bearing_report_embeds_the_chart(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    r = reports.resolve(f"view:{rid}", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    built = r.build({}, _ctx(tmp_path, out))
    assert built.pdf.is_file()


@needs_pdftotext
def test_a_broken_chart_renderer_still_produces_a_built_report(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    r = reports.resolve(f"view:{rid}", tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    with patch("fridgesheet.reports.view.chart_render.render_chart_png", side_effect=RuntimeError("no chromium")):
        built = r.build({}, _ctx(tmp_path, out))
    assert built.pdf.is_file()
    from fridgesheet import sheet
    assert "Chart unavailable" in sheet.pdf_text(built.pdf)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_view.py -k chart -v`
Expected: FAIL — `ViewReport.build` does not import or call `chart_render` yet.

- [ ] **Step 3: Wire it up**

```python
# fridgesheet/reports/view.py, imports:
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from .. import chart_render, sheet
from ..naming import safe_name
from ..web import db, views
from .base import Built, BuildContext, ReportError

log = logging.getLogger("fridgesheet.reports.view")
```

```python
# ViewReport.build(), replace the body from `pdf = ctx.out_dir / "report.pdf"` onward:
        pdf = ctx.out_dir / "report.pdf"
        notes = ([f"Rows from {rendered.window.lower()}"] if rendered.window else []) + \
                ([f"{rendered.truncated} more rows are not shown"] if rendered.truncated else [])
        if rendered.chart_note:
            notes.append(rendered.chart_note)
        chart_png = None
        if rendered.chart is not None:
            try:
                chart_png = chart_render.render_chart_png(views.chart_config(rendered.chart))
            except Exception as e:
                # Broad on purpose: a chart is an enhancement to this report, not a requirement
                # of it -- whatever stops the headless render (a missing Chromium, a timeout, a
                # malformed config) must degrade to a chart-less PDF, never fail the run.
                log.warning("%s: chart render failed (%s)", self.name, e)
                notes.append("Chart unavailable this run — see the log")
        note = "; ".join(notes) or None
        pages = sheet.build_table_pdf(rendered, pdf, title=d.title or self.name, printed_at=ctx.now,
                                      orientation=d.orientation, per_kid_sections=d.per_kid_sections, note=note,
                                      chart_png=chart_png)
        n = sum(len(g.rows) for g in rendered.groups)
        rows = {"columns": [c.id for c in rendered.columns],
                "rows": [r for g in rendered.groups for r in g.rows]}
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {n} rows")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_report_view.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/reports/view.py tests/test_report_view.py
git commit -m "Render a report's chart into its PDF, degrading to a note if rendering fails"
```

## Task 13: Chart controls in the builder

**Files:**
- Modify: `fridgesheet/web/templates/report_builder.html`,
  `fridgesheet/web/routes/reports.py:24-38` (`definition_from_form`), `:98-116` (`rebuild`),
  `:140-153` (`edit`)
- Test: `tests/test_web_reports_page.py`

**Interfaces:**
- Consumes: `ChartSpec`, `CHART_TYPES`, `BUCKETS`, `views.COLUMNS` (Task 5).
- Produces: form fields `chart_type`, `chart_x`, `chart_y`, `chart_series`, `chart_bucket`,
  read by `definition_from_form`; a `rebuild()`/`edit()` path that clears an invalid chart the
  same way `rebuild()` already clears an invalid `group_by`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_reports_page.py, appended
def test_the_builder_saves_a_chart(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    r = c.post("/reports/new", data={
        "title": "Recap", "source": "items", "columns": ["kid", "name", "due"],
        "chart_type": "stacked_bar", "chart_x": "due", "chart_series": "status", "chart_bucket": "week"})
    assert r.status_code == 200 and "Saved." in r.text
    body = c.get("/reports/1").text
    # The template's `{{ 'selected' if ... }}` with no `else` renders nothing when false, so a
    # true condition is the only way this exact substring appears (report_builder.html, Step 3).
    assert '<option value="stacked_bar" selected>' in body
    assert '<option value="due" selected>' in body
    assert '<option value="status" selected>' in body
    assert '<option value="week" selected>' in body
    assert '<span id="chartFields" >' in body            # visible: a chart is set


def test_changing_source_clears_a_chart_that_no_longer_fits(tmp_path):
    """"due" and "status" belong to items, not grades -- the redrawn builder must not carry a
    now-invalid chart forward silently."""
    seed(tmp_path).close()
    c = _client(tmp_path)
    r = c.post("/reports/builder", data={
        "title": "Recap", "source": "grades", "columns": ["value"],
        "chart_type": "stacked_bar", "chart_x": "due", "chart_series": "status", "chart_bucket": "week"})
    assert r.status_code == 200
    assert '<span id="chartFields" hidden>' in r.text     # hidden: the chart was dropped
    assert '<option value="stacked_bar" selected>' not in r.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_reports_page.py -k "saves_a_chart or clears_a_chart" -v`
Expected: FAIL — no chart fields exist in the form yet.

- [ ] **Step 3: Add the controls and wiring**

```python
# fridgesheet/web/routes/reports.py, definition_from_form (Task 3 already added date_from/date_to
# to this call; extend it further):
def definition_from_form(form) -> views.Definition:
    sort = [{"column": c, "dir": d} for c, d in
            zip(form.getlist("sort_column"), form.getlist("sort_dir")) if c]
    filters = [{"field": f, "op": o, "value": v} for f, o, v in
               zip(form.getlist("filter_field"), form.getlist("filter_op"), form.getlist("filter_value")) if f]
    group_by = form.get("group_by") or None
    chart_type = form.get("chart_type") or None
    chart = views.ChartSpec(type=chart_type, x=form.get("chart_x", ""),
                            y=form.get("chart_y") or None, series=form.get("chart_series") or None,
                            bucket=form.get("chart_bucket") or "week") if chart_type else None
    return views.from_json(views.Definition(
        title=form.get("title", ""), source=form.get("source", "items"),
        scope=tuple(form.getlist("scope")), columns=tuple(form.getlist("columns")),
        filters=tuple(filters), group_by=group_by, sort=tuple(sort), chart=chart,
        orientation=form.get("orientation", "portrait"),
        per_kid_sections=bool(form.get("per_kid_sections")),
        window=form.get("window", "all"),
        date_from=form.get("date_from", ""), date_to=form.get("date_to", ""),
    ).to_json())
```

```python
# rebuild() -- extend the reconstruction to drop a chart whose fields don't fit the new source,
# the same instinct already applied to columns/filters/group_by/sort:
    def _fits(ch):
        if ch is None or ch.x not in known:
            return None
        if ch.y is not None and ch.y not in known:
            ch = replace(ch, y=None)
        if ch.series is not None and ch.series not in known:
            ch = replace(ch, series=None)
        if ch.type == "stacked_bar" and ch.series is None:
            return None                  # can no longer satisfy validate()'s own rule
        return ch
    d = views.Definition(
        title=d.title, source=d.source, scope=d.scope,
        columns=tuple(c for c in d.columns if c in known) or tuple(views.DEFAULT_COLUMNS.get(d.source, ())),
        filters=tuple(f for f in d.filters if f.get("field") in known),
        group_by=d.group_by if d.group_by in known else None,
        sort=tuple(s for s in d.sort if s.get("column") in known),
        chart=_fits(d.chart),
        orientation=d.orientation, per_kid_sections=d.per_kid_sections, window=d.window,
        date_from=d.date_from, date_to=d.date_to)
```

`replace` needs importing at the top of `routes/reports.py`: `from dataclasses import replace`.

```html
<!-- fridgesheet/web/templates/report_builder.html, added after the Filters block (line 38): -->
  <p>Chart:
    <select name="chart_type" onchange="document.getElementById('chartFields').hidden = !this.value; document.getElementById('chartSeries').hidden = this.value !== 'stacked_bar'">
      <option value="">none</option>
      {% for t in CHART_TYPES %}<option value="{{ t }}" {{ 'selected' if d.chart and d.chart.type == t }}>{{ t.replace('_', ' ') }}</option>{% endfor %}
    </select>
    <span id="chartFields" {{ 'hidden' if not d.chart }}>
      <label>Date <select name="chart_x">{% for cid, col in cols.items() if col.kind == 'date' %}<option value="{{ cid }}" {{ 'selected' if d.chart and d.chart.x == cid }}>{{ col.label }}</option>{% endfor %}</select></label>
      <label>Value <select name="chart_y"><option value="">Count of rows</option>{% for cid, col in cols.items() if col.kind == 'number' %}<option value="{{ cid }}" {{ 'selected' if d.chart and d.chart.y == cid }}>{{ col.label }}</option>{% endfor %}</select></label>
      <span id="chartSeries" {{ 'hidden' if not d.chart or d.chart.type != 'stacked_bar' }}>
        <label>Series <select name="chart_series"><option value="">—</option>{% for cid, col in cols.items() %}<option value="{{ cid }}" {{ 'selected' if d.chart and d.chart.series == cid }}>{{ col.label }}</option>{% endfor %}</select></label>
      </span>
      <label>Bucket <select name="chart_bucket">{% for b in BUCKETS %}<option value="{{ b }}" {{ 'selected' if d.chart and d.chart.bucket == b }}>{{ b }}</option>{% endfor %}</select></label>
    </span></p>
```

```python
# _builder() (routes/reports.py:60-69), pass the two new constants to the template:
    return render(request, conn, "report_builder.html", current="reports", report=report,
                  d=d, cols=cols, SOURCES=views.SOURCES, OPS=views.OPS,
                  ORIENTATIONS=views.ORIENTATIONS, WINDOWS=views.WINDOWS,
                  CHART_TYPES=views.CHART_TYPES, BUCKETS=views.BUCKETS,
                  problems=list(problems), messages=list(messages), kids=students.visible(conn))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/test_web_reports_page.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates/report_builder.html fridgesheet/web/routes/reports.py tests/test_web_reports_page.py
git commit -m "Add chart controls to the report builder, dropped when a source change breaks them"
```

## Task 14: Whole-branch check for Part 2

**Files:** none (verification only)

- [ ] **Step 1: Run the full suite**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest tests/ -v 2>&1 | tee /tmp/fridgesheet-part2-tests.log`
Expected: every test passes; `test_chart_render.py`'s browser test either passes or skips
cleanly with "no Playwright browser here".

- [ ] **Step 2: Manual check — build a chart report end to end**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m fridgesheet.web` from
outside the worktree (per this project's own convention for browser checks against main, or
inside the worktree if checking this branch's own code) and, in a browser:
1. Create a view report with `source=items`, a `stacked_bar` chart (`x=due`, `series=status`,
   `bucket=week`).
2. Confirm the live preview draws a stacked bar chart with a legend per status.
3. Open the standalone `/reports/{id}/view` page and confirm the same chart renders there.
4. Run the report from the CLI (`fridgesheet run view:<id>` or the Reports page's own
   print/run action) and open the produced PDF — confirm the chart image appears above the
   table, matching the browser's chart in shape and colors.

This is the step that proves the spec's central claim — the live preview and the printed PDF
cannot disagree about what a chart looks like, because both come from the same
`chart_config()`.

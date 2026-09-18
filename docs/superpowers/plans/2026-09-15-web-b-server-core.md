# Web App Plan B (part 1 of 2): Server Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a browser in front of Plan A's database: a FastAPI server the parent opens on this machine, with the Dashboard, the Kid page (notes and flags), and the Reconcile page, reading the same `lakota.db` the CLI runner fills.

**Architecture:** One process, `lakota-grades web`, runs a FastAPI app on uvicorn and serves Jinja2 pages; htmx swaps partials for notes, flags and filters; no front-end build. Page data comes from small store modules under `web/stores/` (all SQL lives there or in `db.py`), the reconciliation rules from `web/reconcile.py`. A per-request SQLite connection (WAL, `busy_timeout`) keeps the server and a concurrent CLI run out of each other's way. Part 2 of Plan B (a separate plan file) adds the jobs worker, Settings and Diagnostics, the always-on service and the Windows entry point; nothing here depends on it.

**Tech Stack:** Python 3.12, `fastapi`, `uvicorn`, `jinja2`, `python-multipart` (new runtime deps), `httpx` (dev, for `TestClient`), vendored `htmx` 2.0.4 and `uPlot` 1.6.31 (uPlot is used by Plan C; vendored now so `static/` is complete). Standard-library `sqlite3`, `urllib`, `webbrowser`.

**Spec:** `docs/superpowers/specs/2026-09-15-lakota-web-app-design.md`, sections 3 (architecture), 5 (pages: Dashboard, Kid, Reconcile), 6 (reconciliation), 8 (access), 13.B, 15 (risks 2 and 4). GitHub milestone "Web app B: Server", issues #12 to #15; each task names its issue and closes it in the commit message. Issue #31 lists Plan A residuals; the ones this plan touches are named in the task that touches them.

## Global Constraints

- The server binds to `127.0.0.1:8433` by default; `[web] allow_lan = true` in `config.toml` rebinds to `0.0.0.0`; `[web] port` overrides the port; env `LAKOTA_WEB_PORT` / `LAKOTA_WEB_HOST` override both (env wins, as everywhere in `config.py`). No login, no HTTPS, no telemetry; the server talks to nothing but the browser and (via the runner, part 2) OneLogin, Canvas and HAC.
- One instance per home: the server takes an exclusive lock file `<home>/web.lock` (pid inside). `lakota-grades web` when the port already answers `/health` with `{"app": "lakota-grades"}` opens the browser at the running instance and exits 0 instead of starting a second server.
- All SQL lives in `web/db.py` or `web/stores/*.py`. Routes never contain SQL; templates never compute.
- Every page carries the header: last refresh time and per-source health from the latest `refreshes` row, and the latest `runs` outcome. With an empty database the header says "No refresh yet".
- Templates are Jinja2 with autoescape on; htmx requests (`HX-Request: true`) get a partial, plain requests get the full page. All in-page updates are `hx-post` to form endpoints returning partials; no JSON API in this plan.
- Times in pages are rendered in the settings time zone with the existing `dates.py` helpers where one fits (`time12`, `wd_md_time`, `md`); ISO strings from the database are parsed with `datetime.fromisoformat`.
- No credential is ever read by these routes. Nothing in this plan writes `config.toml` (part 2 does).
- Item identity in URLs is the database `items.id`, never the item key (keys are only unique within a student and course; Plan A).
- The full suite (`env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`, 238 passed at the start of this plan) stays green on Linux and in CI on both runners. The live venv needs `pip install -e ".[dev]"` once for the new dependencies; say so in the report of the task that adds them.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Closes #<issue>` on its own line.

## What Plan A left (read before any task)

| Module | You use |
|---|---|
| `web/db.py` | `open_db(home) -> Connection` (creates, migrates, WAL, `busy_timeout`, Row factory), `now_iso(tz)`, `latest_observations(conn, student_id) -> {item_id: {source: Row}}`, schema v1 (`refreshes`, `students`, `courses`, `items`, `item_observations`, `grade_observations`, `notes`, `flags`, `reports`, `schedules`, `runs`) |
| `web/ingest.py` | `record(conn, snapshot, *, tz, now=None) -> IngestResult(refresh_id, students, courses, items, observations, grades)`; tests seed a database by calling it on a snapshot dict |
| `web/stores/notes.py` | `add(conn, target_type, target_id, body, *, now) -> id`, `edit(conn, note_id, body, *, now)`, `delete(conn, note_id)`, `for_target(conn, target_type, target_id) -> [Row]`, `for_student(conn, student_id) -> [Row]` |
| `web/stores/flags.py` | `FLAGS`, `HANDLED`, `MARKED`, `active(conn, item_id) -> Row|None`, `set_flag(conn, item_id, flag, *, now, text="") -> id`, `clear(conn, item_id, *, now) -> bool`, `history(conn, item_id)`, `active_by_student(conn)` |
| `web/reconcile.py` | `KINDS`, `Case(kind, item_id, key, course, name, due, reason)`, `open_sources(item, obs, now) -> set`, `is_actionable(item, obs, flag, rules, kid, now) -> bool`, `_rows(conn, student_id, now)` (Task 3 renames it `live_items`), `actionable_items(conn, student_id, *, rules, now)`, `cases(conn, student_id, *, rules, now) -> [Case]` |
| `open_items.py` | `HANDLED_FLAGS`, `MARKED_FLAGS`, `school_year_start(now)`, `parse_hac_date`, `kind_of` |
| `late_rules.py` | `load(path) -> LateRules`; the rules file is `<home>/late-rules.toml`; `LateRules.deadline(kid, course, due)` |
| `config.py` | `Settings` (fields `home`, `timezone`, `nicknames`, `printer`, ...), `load_settings()`, `settings_from_doc(doc, s)`, `load_config_doc(path)` |
| `dates.py` | `time12(dt)`, `wd_md_time(dt)`, `md(dt)` |
| `runner.py` | `LOG_NAME`, `LOCK_NAME`; `run(...)` is not called in this plan |

Snapshot shape (what `ingest.record` reads; the test fixture in Task 3 builds one):

```
{"fetched_at": "2026-09-15T06:02:11-04:00", "fetched_at_epoch": 1789..., "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
 "students": {"Alex": {"name": "Alex Example", "canvas_id": 123, "hac_name": "Alex Example",
   "canvas": {"courses": [{"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "...",
       "grade": {"current_score": 91.2, "final_score": null, "current_grade": "A-", "hidden": false},
       "staff": [{"name": "Michael Hoch", "email": null, "roles": ["TeacherEnrollment"]}],
       "assignments": [{"id": 77, "name": "Quiz 1", "due_at": "2026-09-12T23:59:00-04:00", "unlock_at": null, "created_at": "...",
           "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "group_weight": null,
           "published": true, "score": null, "grade": null, "state": "unsubmitted", "late": false, "missing": true,
           "excused": false, "submitted_at": null, "seconds_late": 0}]}]},
   "hac": {"week_view": [], "classes": [{"code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 75.67, "last_updated": "9/11/2026",
       "assignments": [{"due": "09/11/2026", "assigned": "09/11/2026", "name": "Quiz 1", "category": "Assignments",
                        "score": 28.0, "score_raw": "28.00", "points": 30.0, "percent": "93.33%"}], "categories": []}]}}}}
```

## File map

| Path | Responsibility |
|---|---|
| `packaging/windows/spike_web.py`, `packaging/windows/SpikeWeb.spec`, `.github/workflows/spike-web-pyinstaller.yml` (Task 1, all deleted at the end of Task 1) | prove FastAPI + uvicorn + Jinja2 templates freeze and serve under PyInstaller on the Windows runner; record the hidden imports |
| `pyproject.toml` (modify) | new runtime deps; `httpx` in `dev` |
| `lakota_grades/config.py` (modify) | `[web]` section: `web_host`, `web_port`, `web_allow_lan`; env overrides |
| `lakota_grades/web/app.py` (new) | `create_app(settings, *, home=None) -> FastAPI`; `AppState`; the per-request connection dependency; `page_context` |
| `lakota_grades/web/server.py` (new) | `run(settings, *, host, port, open_browser)`; `port_answers`; `WebLock` |
| `lakota_grades/web/stores/refreshes.py`, `runs.py`, `students.py` (new) | header data; run history; students, courses, latest grades |
| `lakota_grades/web/stores/items.py` (new, Task 3) | the item list behind the Kid page and the Dashboard counts |
| `lakota_grades/web/reconcile.py` (modify, Task 3) | `_rows` becomes public `live_items`; `status_text` |
| `lakota_grades/web/routes/__init__.py`, `dashboard.py`, `kid.py`, `notes.py`, `flags.py`, `reconcile.py` (new) | routers, one per page family |
| `lakota_grades/web/templates/*.html` (new) | `base.html`, `_header.html`, `dashboard.html`, `kid.html`, `course.html`, `reconcile.html`, `404.html`, partials `_item_rows.html`, `_item_detail.html`, `_notes.html`, `_flag_menu.html`, `_case_group.html` |
| `lakota_grades/web/static/` (new) | `app.css`, `app.js`, `htmx.min.js`, `uplot.min.js`, `uplot.min.css`, `VENDOR.md` |
| `lakota_grades/cli.py` (modify) | `web` command |
| `tests/web_fixtures.py` (new, Task 3) | `snapshot(...)` builder and `seeded_app(tmp_path)` helper shared by page tests |
| `tests/test_web_app.py`, `test_web_server.py`, `test_web_stores_pages.py`, `test_web_pages.py`, `test_web_reconcile_page.py` (new); `tests/test_config.py`, `test_packaging.py` (modify) | |

---

### Task 1: Spike, FastAPI + uvicorn + Jinja2 under PyInstaller on Windows (issue #12)

Spec section 15 risk 2. A throwaway bundle on the Windows runner proves the three libraries freeze, that templates ship as data, and which hidden imports uvicorn needs. Everything this task adds is deleted at its end; the outcome is recorded in this plan file (below) and read by part 2's packaging task.

**Files:**
- Create: `packaging/windows/spike_web.py`, `packaging/windows/SpikeWeb.spec`, `.github/workflows/spike-web-pyinstaller.yml`
- Modify: `tests/test_packaging.py` (`test_spike_files_are_gone` gains the three names)
- Then delete all three files in the same task.

**Interfaces:**
- Produces: the "Task 1 outcome" block at the end of this task (hidden imports list, data paths), consumed by part 2's PyInstaller spec change.

- [ ] **Step 1: Write the spike app**

`packaging/windows/spike_web.py`:

```python
"""Throwaway: does a frozen FastAPI + uvicorn + Jinja2 app serve a bundled template?
`spike_web.exe --port N` serves GET / rendering templates/spike.html and exits on SIGTERM."""
from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
app = FastAPI()
templates = Jinja2Templates(directory=str(BASE / "templates"))


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "spike.html", {"who": "frozen"})


if __name__ == "__main__":
    port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
```

`packaging/windows/templates/spike.html` (create the folder):

```html
<!doctype html><title>spike</title><p>spike ok: {{ who }}</p>
```

`packaging/windows/SpikeWeb.spec`:

```python
# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

HERE = os.path.abspath(SPECPATH)
a = Analysis(
    [os.path.join(HERE, "spike_web.py")],
    pathex=[HERE],
    datas=[(os.path.join(HERE, "templates"), "templates")],
    hiddenimports=collect_submodules("uvicorn") + ["fastapi", "jinja2", "multipart", "anyio._backends._asyncio"],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="spike_web", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="spike_web")
```

- [ ] **Step 2: Write the temporary workflow**

`.github/workflows/spike-web-pyinstaller.yml` (a `push` trigger on this branch; `workflow_dispatch` only works on the default branch, as Plan 3 found):

```yaml
name: spike-web-pyinstaller
on:
  push:
    branches: ["ccswitch/**"]
jobs:
  spike:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install pyinstaller fastapi uvicorn jinja2 python-multipart
      - run: pyinstaller --noconfirm --clean packaging/windows/SpikeWeb.spec
      - name: Serve and fetch
        shell: pwsh
        run: |
          $p = Start-Process -FilePath dist\spike_web\spike_web.exe -ArgumentList "--port","8765" -PassThru
          $ok = $false
          foreach ($i in 1..30) {
            Start-Sleep -Milliseconds 500
            try { $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/; if ($r.Content -match "spike ok: frozen") { $ok = $true; break } } catch {}
          }
          Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
          if (-not $ok) { throw "the frozen server never answered with the rendered template" }
          Write-Host "spike OK"
```

- [ ] **Step 3: Push the branch and read the run**

Run: `git add packaging/windows/spike_web.py packaging/windows/SpikeWeb.spec packaging/windows/templates/spike.html .github/workflows/spike-web-pyinstaller.yml && git commit -m "Spike: FastAPI + uvicorn + Jinja2 under PyInstaller on Windows" && git push`
Then: `gh run list --workflow spike-web-pyinstaller --limit 1` and `gh run watch <id> --exit-status`; on failure `gh run view <id> --log-failed`.
If the fetch fails with an import error in the exe's output, add the missing module to `hiddenimports`, commit, push, repeat. Typical additions: `uvicorn.logging`, `uvicorn.loops.auto`, `uvicorn.protocols.http.auto`, `uvicorn.protocols.websockets.auto`, `uvicorn.lifespan.on` (all covered by `collect_submodules("uvicorn")`), `email.mime.multipart` (used by `python-multipart` on some versions).
Expected: "spike OK" in the run log.

- [ ] **Step 4: Record the outcome and remove the spike**

Append under "Task 1 outcome" below: the final `hiddenimports` list that worked, the `datas` entry that carried the templates, the PyInstaller version the runner used (`pip show pyinstaller` in the log), and the run URL. Then delete the three files and the `templates/` folder, add their names to `test_spike_files_are_gone` in `tests/test_packaging.py`:

```python
def test_spike_files_are_gone():
    assert not (WIN / "spike_entry.py").exists()
    assert not (ROOT / ".github" / "workflows" / "spike-pyinstaller.yml").exists()
    assert not (WIN / "spike_web.py").exists() and not (WIN / "SpikeWeb.spec").exists()
    assert not (ROOT / ".github" / "workflows" / "spike-web-pyinstaller.yml").exists()
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_packaging.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A packaging/windows .github/workflows tests/test_packaging.py docs/superpowers/plans/2026-09-15-web-b-server-core.md
git commit -m "Spike done: FastAPI, uvicorn and Jinja2 freeze under PyInstaller; record and remove

Closes #12

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

#### Task 1 outcome

FastAPI + uvicorn + Jinja2 freeze and serve under PyInstaller on the Windows runner. The spike
passed on the first run, no `hiddenimports` iteration was needed.

- `hiddenimports` that worked (unchanged from the brief): `collect_submodules("uvicorn")` plus
  `["fastapi", "jinja2", "multipart", "anyio._backends._asyncio"]`.
- `datas` entry that carried the templates: `[(os.path.join(HERE, "templates"), "templates")]`
  (one folder, `packaging/windows/templates/`, containing `spike.html`), read at runtime via
  `Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "templates"`.
- PyInstaller version on the runner: 6.22.3 (Python 3.12.10, `windows-latest`).
- Run: https://github.com/steiner385/fridgesheet/actions/runs/34976441451 (success,
  2026-09-15 09:40 America/New_York) — log shows `spike OK` after the frozen `spike_web.exe`
  answered `GET /` with the rendered template.
- Iterations: 1 (no hidden-import additions needed).

---

### Task 2: `web/app.py`, `server.py`, the base layout, vendored assets, `lakota-grades web` (issue #13)

**Files:**
- Modify: `pyproject.toml` (dependencies), `lakota_grades/config.py` (`[web]`), `lakota_grades/cli.py` (`web` command), `tests/test_config.py`
- Create: `lakota_grades/web/app.py`, `lakota_grades/web/server.py`, `lakota_grades/web/stores/refreshes.py`, `lakota_grades/web/stores/runs.py`, `lakota_grades/web/stores/students.py`, `lakota_grades/web/routes/__init__.py`, `lakota_grades/web/routes/dashboard.py`, `lakota_grades/web/templates/base.html`, `_header.html`, `dashboard.html`, `404.html`, `lakota_grades/web/static/app.css`, `app.js`, `htmx.min.js`, `uplot.min.js`, `uplot.min.css`, `VENDOR.md`
- Test: `tests/test_web_app.py`, `tests/test_web_server.py`

**Interfaces:**
- Consumes: `db.open_db`, `ingest.record` (tests), `config.Settings`.
- Produces (later tasks rely on these exact names):
  - `app.create_app(settings: Settings, *, home: Path | None = None) -> FastAPI`
  - `app.AppState(home, settings, tz, started_at)` at `request.app.state.lakota`; `AppState.rules() -> LateRules` (re-reads `<home>/late-rules.toml` each call)
  - dependency `app.get_db(request) -> Iterator[sqlite3.Connection]` (one connection per request, closed after)
  - `app.ENV: jinja2.Environment` (the shared loader) and `app.render(request, conn, name, status_code=200, **ctx) -> HTMLResponse`, which merges `page_context(request, conn)` (keys `refresh`, `sources`, `last_run`, `students`, `now`, `settings`, `version`; filters `wd_md_time`, `md`, `time12`, `nickname`) with `ctx` and, for an htmx request, renders only the template's `partial` block when it has one; `app.render_partial(request, conn, name, **ctx)` for standalone partials; `app.is_htmx(request)`
  - `stores.refreshes.latest(conn) -> Row | None`
  - `stores.runs.latest(conn) -> Row | None`, `stores.runs.recent(conn, limit=50) -> [Row]`, `stores.runs.printed_on(conn, day: date) -> [Row]`
  - `stores.students.visible(conn) -> [Row]` (students with `hidden = 0`, by key), `stores.students.by_key(conn, key) -> Row | None`, `stores.students.courses(conn, student_id) -> [Row]` (courses with `peer_course_id`, ordered by short_name, source), `stores.students.latest_grades(conn, student_id) -> {course_id: Row}` (latest `grade_observations` per course)
  - `server.run(settings, *, host=None, port=None, open_browser=True, serve=None, opener=None, answers=None, wait_and_open=None) -> int`, `server.port_answers(host, port, timeout=1.0) -> bool`, `server.WebLock(path)` (`acquire() -> bool`, `release()`), `server._wait_and_open(url, opener, *, answers=port_answers, tries=100, interval=0.2)`, `server.LOCK_NAME = "web.lock"`
  - config: `Settings.web_host: str = "127.0.0.1"`, `Settings.web_port: int = 8433`, `Settings.web_allow_lan: bool = False`, `Settings.bind_host -> str` (`0.0.0.0` when `web_allow_lan` else `web_host`)

- [ ] **Step 1: Dependencies**

In `pyproject.toml` `dependencies`, add (keep the list sorted as it is):

```toml
    "fastapi>=0.115",
    "jinja2>=3.1",
    "python-multipart>=0.0.9",
    "uvicorn>=0.30",
```

and in `[project.optional-dependencies]`: `dev = ["pytest>=8", "httpx>=0.27"]`.
In `[tool.setuptools.package-data]`: `lakota_grades = ["host/*.xml", "web/templates/*.html", "web/static/*"]`.

Run: `~/lakota-grades-mcp/.venv/bin/pip install -e ".[dev]"` (the live venv; say so in the report).

- [ ] **Step 2: `[web]` settings, test first**

Append to `tests/test_config.py`:

```python
def test_web_section_and_env_override(tmp_path, monkeypatch):
    s = config.Settings(home=tmp_path)
    config.settings_from_doc({"web": {"port": 9000, "allow_lan": True, "host": "10.0.0.5"}}, s)
    assert (s.web_port, s.web_allow_lan, s.web_host) == (9000, True, "10.0.0.5")
    assert s.bind_host == "0.0.0.0"
    s2 = config.Settings(home=tmp_path)
    assert (s2.web_port, s2.web_allow_lan, s2.bind_host) == (8433, False, "127.0.0.1")
    config.settings_from_doc({"web": {"port": "not a number"}}, s2)
    assert s2.web_port == 8433                     # a bad value keeps the default
    monkeypatch.setenv("LAKOTA_WEB_PORT", "8500")
    monkeypatch.setenv("LAKOTA_WEB_HOST", "0.0.0.0")
    monkeypatch.setenv("LAKOTA_GRADES_HOME", str(tmp_path))
    s3 = config.load_settings()
    assert (s3.web_port, s3.bind_host) == (8500, "0.0.0.0")
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_config.py -k web_section`
Expected: FAIL (`AttributeError: web_port`).

- [ ] **Step 3: Implement `[web]`**

In `config.Settings` add after `reports`:

```python
    web_host: str = "127.0.0.1"        # [web] host; bind address when allow_lan is off
    web_port: int = 8433
    web_allow_lan: bool = False        # [web] allow_lan; True binds 0.0.0.0 (spec section 8)
```

and a property:

```python
    @property
    def bind_host(self) -> str:
        return "0.0.0.0" if self.web_allow_lan else self.web_host
```

In `settings_from_doc`, after the `kids` block:

```python
    raw_web = doc.get("web")
    web = raw_web if isinstance(raw_web, dict) else {}
    s.web_host = str(web.get("host", s.web_host))
    s.web_allow_lan = bool(web.get("allow_lan", s.web_allow_lan))
    try:
        s.web_port = int(web.get("port", s.web_port))
    except (TypeError, ValueError):
        pass
```

In `load_settings`, after the `printer` line:

```python
    s.web_host = os.environ.get("LAKOTA_WEB_HOST", s.web_host)
    if os.environ.get("LAKOTA_WEB_HOST") == "0.0.0.0":
        s.web_allow_lan = True
    try:
        s.web_port = int(os.environ.get("LAKOTA_WEB_PORT", s.web_port))
    except ValueError:
        pass
```

Run the test again. Expected: PASS.

- [ ] **Step 4: Header and student stores, test first**

`tests/test_web_app.py` (start of the file; more tests join it in step 8):

```python
"""The app skeleton: every page carries the header, the header reads the database, static files serve."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from lakota_grades import config
from lakota_grades.web import app as webapp, db, ingest
from lakota_grades.web.stores import refreshes, runs, students

TZ = ZoneInfo("America/New_York")


def _snapshot(ok=True):
    return {
        "fetched_at": "2026-09-15T06:02:11-04:00", "fetched_at_epoch": 1789000000,
        "sources": {"canvas": "ok", "hac": "ok" if ok else "login_required: portal timeout"}, "stale": {},
        "students": {"Alex": {"name": "Alex Example", "canvas_id": 1, "hac_name": "Alex Example",
            "canvas": {"courses": [{"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                "staff": [{"name": "Michael Hoch", "email": None, "roles": ["TeacherEnrollment"]}], "assignments": []}]},
            "hac": {"week_view": [], "classes": [{"code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 88.0,
                "last_updated": "9/11/2026", "assignments": [], "categories": []}]}}}}


@pytest.fixture
def home(tmp_path):
    return tmp_path


@pytest.fixture
def settings(home):
    return config.Settings(home=home)


@pytest.fixture
def client(settings):
    return TestClient(webapp.create_app(settings))


def test_stores_read_an_empty_database(home):
    conn = db.open_db(home)
    assert refreshes.latest(conn) is None and runs.latest(conn) is None and students.visible(conn) == []
    conn.close()


def test_stores_read_the_seeded_database(home):
    conn = db.open_db(home)
    ingest.record(conn, _snapshot(ok=False), tz=TZ, now=datetime(2026, 9, 15, 6, 5, tzinfo=TZ))
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path) VALUES (?,?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "printed", "/x/sheet.pdf"))
    r = refreshes.latest(conn)
    assert r["started_at"].startswith("2026-09-15T06:05") and json.loads(r["sources"])["hac"].startswith("login_required")
    assert runs.latest(conn)["outcome"] == "OK"
    assert [x["outcome"] for x in runs.printed_on(conn, datetime(2026, 9, 15).date())] == ["OK"]
    al = students.by_key(conn, "Alex")
    assert al["name"] == "Alex Example" and [s["key"] for s in students.visible(conn)] == ["Alex"]
    cs = students.courses(conn, al["id"])
    assert [(c["source"], c["short_name"]) for c in cs] == [("canvas", "Honors English 9"), ("hac", "Honors English 9")]
    assert cs[0]["peer_course_id"] == cs[1]["id"] and cs[0]["teacher"] == "Michael Hoch"
    grades = students.latest_grades(conn, al["id"])
    assert grades[cs[0]["id"]]["current"] == 91.2 and grades[cs[1]["id"]]["average"] == 88.0
    conn.close()
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_app.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 5: Implement the three stores**

`lakota_grades/web/stores/refreshes.py`:

```python
"""What the header says about the last refresh."""
from __future__ import annotations

import sqlite3


def latest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM refreshes ORDER BY id DESC LIMIT 1").fetchone()
```

`lakota_grades/web/stores/runs.py`:

```python
"""Run history: the CLI runner and (part 2) the jobs worker write it; the header badge,
the Dashboard and the Runs page read it."""
from __future__ import annotations

import sqlite3
from datetime import date


def latest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)).fetchall()


def printed_on(conn: sqlite3.Connection, day: date) -> list[sqlite3.Row]:
    """OK runs that produced a PDF on `day` (local date prefix of started_at)."""
    return conn.execute(
        "SELECT * FROM runs WHERE outcome = 'OK' AND pdf_path IS NOT NULL AND substr(started_at, 1, 10) = ? ORDER BY id",
        (day.isoformat(),)).fetchall()
```

`lakota_grades/web/stores/students.py`:

```python
"""Students, their courses and the latest grade per course."""
from __future__ import annotations

import sqlite3


def visible(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM students WHERE hidden = 0 ORDER BY key").fetchall()


def by_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM students WHERE key = ?", (key,)).fetchone()


def by_id(conn: sqlite3.Connection, student_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


def courses(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM courses WHERE student_id = ? AND hidden = 0 ORDER BY short_name, source", (student_id,)).fetchall()


def course(conn: sqlite3.Connection, course_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()


def latest_grades(conn: sqlite3.Connection, student_id: int) -> dict[int, sqlite3.Row]:
    """course_id -> the newest grade_observations row for that course."""
    out: dict[int, sqlite3.Row] = {}
    for r in conn.execute(
            """SELECT g.* FROM grade_observations g JOIN courses c ON c.id = g.course_id
               WHERE c.student_id = ? ORDER BY g.refresh_id DESC, g.id DESC""", (student_id,)):
        out.setdefault(r["course_id"], r)
    return out


def grade_history(conn: sqlite3.Connection, course_id: int) -> list[sqlite3.Row]:
    """Every grade observation for one course, oldest first, with the refresh time."""
    return conn.execute(
        """SELECT g.*, r.started_at FROM grade_observations g JOIN refreshes r ON r.id = g.refresh_id
           WHERE g.course_id = ? ORDER BY g.refresh_id""", (course_id,)).fetchall()
```

Run the two store tests. Expected: PASS.

- [ ] **Step 6: The app skeleton, test first**

Append to `tests/test_web_app.py`:

```python
def test_health_names_the_app(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["app"] == "lakota-grades" and "version" in r.json()


def test_dashboard_renders_with_an_empty_database(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "No refresh yet" in r.text and "Lakota Sheet" in r.text
    assert 'href="/static/app.css"' in r.text and 'src="/static/htmx.min.js"' in r.text


def test_header_shows_refresh_time_source_health_and_last_run(settings, home):
    conn = db.open_db(home)
    ingest.record(conn, _snapshot(ok=False), tz=TZ, now=datetime(2026, 9, 15, 6, 5, tzinfo=TZ))
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message) VALUES (?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "FAIL", "printer offline"))
    conn.close()
    r = TestClient(webapp.create_app(settings)).get("/")
    assert "Tue 9/15 6:05 AM" in r.text            # dates.wd_md_time of the refresh (2026-09-15 is a Tuesday)
    assert "Canvas OK" in r.text and "HAC login_required" in r.text
    assert "FAIL" in r.text and "printer offline" in r.text
    assert 'href="/kids/Alex"' in r.text        # the rail lists every student


def test_static_files_are_served(client):
    assert client.get("/static/htmx.min.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_unknown_page_is_a_404_page(client):
    r = client.get("/nope")
    assert r.status_code == 404 and "Not found" in r.text


def test_htmx_request_gets_only_the_partial(settings):
    r = TestClient(webapp.create_app(settings)).get("/", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "No refresh yet" in r.text
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_app.py`
Expected: FAIL (`AttributeError: create_app`).

- [ ] **Step 7: Vendor the static assets**

Download exactly these, record the SHA-256 of each file in `lakota_grades/web/static/VENDOR.md` with its URL and licence, and commit the files:

- `https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js` → `htmx.min.js` (BSD-2-Clause)
- `https://unpkg.com/uplot@1.6.31/dist/uPlot.iife.min.js` → `uplot.min.js` (MIT)
- `https://unpkg.com/uplot@1.6.31/dist/uPlot.min.css` → `uplot.min.css` (MIT)

Run: `curl -sSL -o lakota_grades/web/static/htmx.min.js https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js` (and the other two), then `sha256sum lakota_grades/web/static/*.js lakota_grades/web/static/*.css`.

`VENDOR.md`:

```markdown
# Vendored front-end files

No build step: these files are committed as downloaded. To upgrade, change the version in the URL, re-download, and update the hash.

| File | Source | Version | Licence | SHA-256 |
|---|---|---|---|---|
| htmx.min.js | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js | 2.0.4 | BSD-2-Clause | `<fill in>` |
| uplot.min.js | https://unpkg.com/uplot@1.6.31/dist/uPlot.iife.min.js | 1.6.31 | MIT | `<fill in>` |
| uplot.min.css | https://unpkg.com/uplot@1.6.31/dist/uPlot.min.css | 1.6.31 | MIT | `<fill in>` |
```

Add to `tests/test_web_app.py`:

```python
def test_vendored_assets_match_their_recorded_hashes():
    import hashlib, re
    from pathlib import Path
    static = Path(webapp.__file__).parent / "static"
    table = (static / "VENDOR.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (\S+\.(?:js|css)) \|.*`([0-9a-f]{64})` \|$", table, re.M)
    assert len(rows) == 3
    for name, sha in rows:
        assert hashlib.sha256((static / name).read_bytes()).hexdigest() == sha, name
```

`app.css` (the whole visual system for this plan; Plan C adds chart styles):

```css
/* Lakota Sheet: one layout, a left rail on wide screens, one column on a phone. */
:root { --ink: #1c1c1c; --muted: #6b6b6b; --rule: #d9d9d9; --paper: #fff; --wash: #f4f4f2; --accent: #1f5fa8; --warn: #b3261e; --ok: #2e7d32; }
* { box-sizing: border-box; }
body { margin: 0; font: 15px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); background: var(--wash); }
a { color: var(--accent); }
.shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.rail { background: var(--paper); border-right: 1px solid var(--rule); padding: 16px; }
.rail h1 { font-size: 18px; margin: 0 0 12px; }
.rail nav a { display: block; padding: 6px 8px; border-radius: 6px; text-decoration: none; color: var(--ink); }
.rail nav a.current, .rail nav a:hover { background: var(--wash); }
.rail nav .group { margin: 12px 0 4px; font-size: 12px; text-transform: uppercase; color: var(--muted); }
main { padding: 16px 24px 48px; max-width: 1100px; }
header.status { display: flex; flex-wrap: wrap; gap: 16px; align-items: baseline; padding-bottom: 8px; border-bottom: 1px solid var(--rule); margin-bottom: 16px; color: var(--muted); font-size: 13px; }
header.status .ok { color: var(--ok); } header.status .bad { color: var(--warn); }
.badge { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; background: var(--wash); border: 1px solid var(--rule); }
.badge.OK { border-color: var(--ok); color: var(--ok); } .badge.FAIL { border-color: var(--warn); color: var(--warn); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 16px; }
.card { background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; padding: 12px 16px; }
.card h2 { margin: 0 0 8px; font-size: 16px; }
.big { font-size: 28px; font-weight: 600; }
table.items { width: 100%; border-collapse: collapse; background: var(--paper); }
table.items th, table.items td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }
table.items th a { text-decoration: none; }
tr.overdue td.due { color: var(--warn); }
tr.detail td { background: var(--wash); }
.muted { color: var(--muted); } .warn { color: var(--warn); }
.filters { display: flex; flex-wrap: wrap; gap: 8px 16px; margin: 8px 0 12px; align-items: center; }
.filters label { font-size: 13px; color: var(--muted); }
.flagmenu button, .actions button { margin: 2px 4px 2px 0; }
.note { border-left: 3px solid var(--rule); padding: 4px 8px; margin: 6px 0; background: var(--paper); }
.note .meta { font-size: 12px; color: var(--muted); }
textarea { width: 100%; min-height: 60px; font: inherit; }
.case { border-left: 3px solid var(--accent); }
.case.disagree { border-color: var(--warn); }
@media (max-width: 800px) { .shell { grid-template-columns: 1fr; } .rail { border-right: 0; border-bottom: 1px solid var(--rule); } main { padding: 12px; } }
```

`app.js`:

```js
// Small helpers; everything interactive is htmx. Keep the expanded row open after a swap.
document.addEventListener("htmx:afterSwap", function (e) {
  var el = e.detail.target;
  if (el && el.matches && el.matches("[data-focus]")) { var f = el.querySelector("textarea, input"); if (f) f.focus(); }
});
```

- [ ] **Step 8: Templates**

`lakota_grades/web/templates/base.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}Lakota Sheet{% endblock %}</title>
<link rel="stylesheet" href="/static/app.css">
<script src="/static/htmx.min.js" defer></script>
<script src="/static/app.js" defer></script>
</head>
<body>
<div class="shell">
  <aside class="rail">
    <h1><a href="/" style="text-decoration:none;color:inherit">Lakota Sheet</a></h1>
    <nav>
      <a href="/" class="{{ 'current' if current == 'dashboard' }}">Dashboard</a>
      <div class="group">Kids</div>
      {% for s in students %}<a href="/kids/{{ s.key }}" class="{{ 'current' if current == 'kid:' ~ s.key }}">{{ s.key | nickname }}</a>{% endfor %}
      <div class="group">Work</div>
      <a href="/reconcile" class="{{ 'current' if current == 'reconcile' }}">Reconcile</a>
      {% block rail_extra %}{% endblock %}
    </nav>
  </aside>
  <main>
    {% include "_header.html" %}
    {% block content %}{% endblock %}
  </main>
</div>
</body>
</html>
```

`_header.html`:

```html
<header class="status">
  {% if refresh %}
    <span>Refreshed {{ refresh.started_at | wd_md_time }}</span>
    {% for name, state in sources %}<span class="{{ 'ok' if state == 'ok' else 'bad' }}">{{ name }} {{ 'OK' if state == 'ok' else state }}</span>{% endfor %}
  {% else %}
    <span>No refresh yet</span>
  {% endif %}
  {% if last_run %}
    <span>Last run <span class="badge {{ last_run.outcome }}">{{ last_run.outcome }}</span> {{ last_run.started_at | wd_md_time }} <span class="muted">{{ last_run.message | truncate(80) }}</span></span>
  {% endif %}
  <span class="muted">{{ now | wd_md_time }}</span>
</header>
```

`dashboard.html` (Task 4 replaces the content block; this version is the skeleton's proof of life):

```html
{% extends "base.html" %}
{% block title %}Dashboard · Lakota Sheet{% endblock %}
{% block content %}
{% block partial %}
<div class="cards">
  {% for s in students %}
  <div class="card"><h2>{{ s.key | nickname }}</h2><p class="muted">Kid page: <a href="/kids/{{ s.key }}">open</a></p></div>
  {% else %}
  <div class="card"><h2>Nothing here yet</h2><p class="muted">{% if refresh %}The last refresh found no students.{% else %}No refresh yet. Run <code>lakota-grades refresh</code> (or, once part 2 lands, press Refresh now) and this page fills in.{% endif %}</p></div>
  {% endfor %}
</div>
{% endblock %}
{% endblock %}
```

`404.html`:

```html
{% extends "base.html" %}
{% block title %}Not found · Lakota Sheet{% endblock %}
{% block content %}<h2>Not found</h2><p class="muted">{{ path }} is not a page here.</p>{% endblock %}
```

- [ ] **Step 9: Implement `app.py`**

```python
"""The FastAPI application: state, the per-request database connection, page rendering.

`create_app(settings)` is the only constructor; the server (`server.py`), the tests
(`TestClient`) and part 2's jobs worker all go through it. Routes live in `routes/`, SQL in
`stores/`; this module owns what every page shares -- the header data and the rail.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import jinja2

from .. import dates, late_rules
from ..config import Settings
from . import db
from .stores import refreshes, runs, students

HERE = Path(__file__).parent
APP_NAME = "lakota-grades"


def version() -> str:
    try:
        return metadata.version("lakota-grades-mcp")
    except metadata.PackageNotFoundError:
        return "dev"


@dataclass
class AppState:
    home: Path
    settings: Settings
    tz: ZoneInfo
    started_at: datetime
    extra: dict = field(default_factory=dict)     # part 2 hangs the jobs worker here

    def rules(self) -> late_rules.LateRules:
        """Re-read each call: the parent edits late-rules.toml (part 2's Settings page)."""
        return late_rules.load(self.home / "late-rules.toml")

    def now(self) -> datetime:
        return datetime.now(self.tz)


def _parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _filters(state: AppState) -> dict:
    def wd_md_time(v):
        d = _parse(v) if isinstance(v, str) else v
        return dates.wd_md_time(d.astimezone(state.tz)) if d else ""

    def md(v):
        d = _parse(v) if isinstance(v, str) else v
        return dates.md(d.astimezone(state.tz)) if d else ""

    def time12(v):
        d = _parse(v) if isinstance(v, str) else v
        return dates.time12(d.astimezone(state.tz)) if d else ""

    def nickname(key: str) -> str:
        return state.settings.nicknames.get(key, key)

    return {"wd_md_time": wd_md_time, "md": md, "time12": time12, "nickname": nickname}


#: The shared loader. Rendering goes through a per-request overlay (see `_env`) so each app's
#: filters (nicknames, time zone) stay its own even when tests build many apps in one process.
ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(HERE / "templates")), autoescape=True)


def _env(request: Request) -> jinja2.Environment:
    env = ENV.overlay()
    env.filters.update(get_state(request).extra["filters"])
    return env


def get_state(request: Request) -> AppState:
    return request.app.state.lakota


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.open_db(get_state(request).home)
    try:
        yield conn
    finally:
        conn.close()


def page_context(request: Request, conn: sqlite3.Connection) -> dict:
    state = get_state(request)
    r = refreshes.latest(conn)
    sources = sorted(json.loads(r["sources"]).items()) if r else []
    return {
        "request": request, "settings": state.settings, "now": state.now(), "refresh": r,
        "sources": [(k.upper() if k == "hac" else k.capitalize(), v) for k, v in sources],
        "last_run": runs.latest(conn), "students": students.visible(conn), "version": version(),
    }


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def render(request: Request, conn: sqlite3.Connection, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
    """Render a page; for an htmx request render only the template's `partial` block."""
    context = {**page_context(request, conn), **ctx}
    tmpl = _env(request).get_template(name)
    if is_htmx(request):
        block = tmpl.blocks.get("partial")
        if block is not None:
            return HTMLResponse("".join(block(tmpl.new_context(context))), status_code=status_code)
    return HTMLResponse(tmpl.render(context), status_code=status_code)


def render_partial(request: Request, conn: sqlite3.Connection, name: str, **ctx) -> HTMLResponse:
    """A standalone partial template (no page around it), for htmx swaps."""
    context = {**page_context(request, conn), **ctx}
    return HTMLResponse(_env(request).get_template(name).render(context))


def create_app(settings: Settings, *, home: Path | None = None) -> FastAPI:
    home = home or settings.home
    tz = ZoneInfo(settings.timezone)
    app = FastAPI(title="Lakota Sheet", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.lakota = AppState(home=home, settings=settings, tz=tz, started_at=datetime.now(tz))
    app.state.lakota.extra["filters"] = _filters(app.state.lakota)
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    @app.get("/health")
    def health() -> JSONResponse:
        return JSONResponse({"app": APP_NAME, "version": version(), "home": str(home), "started_at": app.state.lakota.started_at.isoformat()})

    @app.exception_handler(404)
    async def not_found(request: Request, exc):   # noqa: ARG001
        conn = db.open_db(home)
        try:
            return render(request, conn, "404.html", status_code=404, path=request.url.path)
        finally:
            conn.close()

    from .routes import dashboard
    app.include_router(dashboard.router)
    return app


Db = Depends(get_db)
State = Depends(get_state)
```

`lakota_grades/web/routes/__init__.py`:

```python
"""One router per page family. Each module exposes `router`; `app.create_app` includes them."""
```

`lakota_grades/web/routes/dashboard.py` (Task 4 grows it):

```python
"""The Dashboard: one card per kid."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, render

router = APIRouter()


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db):
    return render(request, conn, "dashboard.html", current="dashboard")
```

Why no `fastapi.templating.Jinja2Templates`: its one shared environment would make the last-created app's filters win across the whole test process; the overlay per request above keeps each app's nicknames and time zone its own, and `autoescape=True` is stated rather than inherited.

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_app.py`
Expected: PASS (all).

- [ ] **Step 10: `server.py`, test first**

`tests/test_web_server.py`:

```python
"""Starting the server: one instance per home, open the browser at the running one, the lock file."""
from __future__ import annotations

import os
import socket

from lakota_grades import config
from lakota_grades.web import server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_port_answers_is_false_on_a_closed_port():
    assert server.port_answers("127.0.0.1", _free_port(), timeout=0.2) is False


def test_lock_is_exclusive_and_a_dead_pid_is_stale(tmp_path):
    lock = server.WebLock(tmp_path / "web.lock")
    assert lock.acquire() is True
    assert server.WebLock(tmp_path / "web.lock").acquire() is False       # same pid, still running: taken
    lock.release()
    (tmp_path / "web.lock").write_text("999999999")                       # a pid that cannot exist
    assert server.WebLock(tmp_path / "web.lock").acquire() is True
    assert (tmp_path / "web.lock").read_text() == str(os.getpid())


def test_run_opens_the_browser_at_a_running_instance_instead_of_serving(tmp_path):
    s = config.Settings(home=tmp_path)
    opened, served = [], []
    rc = server.run(s, open_browser=True, serve=lambda *a, **k: served.append(a), opener=opened.append, answers=lambda h, p: True)
    assert rc == 0 and served == [] and opened == ["http://127.0.0.1:8433/"]


def test_run_serves_and_hands_the_browser_to_the_waiter(tmp_path):
    s = config.Settings(home=tmp_path)
    s.web_port = 8500
    opened, served, waited = [], [], []

    def wait_and_open(url, opener, **kw):
        waited.append(url)
        opener(url)

    rc = server.run(s, serve=lambda app, host, port: served.append((host, port)), opener=opened.append,
                    answers=lambda h, p: False, wait_and_open=wait_and_open)
    assert rc == 0 and served == [("127.0.0.1", 8500)] and waited == opened == ["http://127.0.0.1:8500/"]
    assert not (tmp_path / "web.lock").exists()                           # released on exit
    assert (tmp_path / "lakota.db").exists()                              # created and migrated before serving


def test_wait_and_open_opens_once_the_port_answers():
    calls = iter([False, False, True, True])
    opened = []
    server._wait_and_open("http://127.0.0.1:8500/", opened.append, answers=lambda h, p: next(calls), interval=0)
    assert opened == ["http://127.0.0.1:8500/"]
    opened.clear()
    server._wait_and_open("http://127.0.0.1:8500/", opened.append, answers=lambda h, p: False, tries=3, interval=0)
    assert opened == []                                                   # gives up quietly


def test_run_refuses_when_another_instance_holds_the_lock_and_the_port_is_silent(tmp_path, capsys):
    s = config.Settings(home=tmp_path)
    lock = server.WebLock(tmp_path / "web.lock")
    lock.acquire()
    try:
        rc = server.run(s, serve=lambda *a, **k: None, opener=lambda u: None, answers=lambda h, p: False)
    finally:
        lock.release()
    assert rc == 1 and "web.lock" in capsys.readouterr().err


def test_no_browser_flag(tmp_path):
    s = config.Settings(home=tmp_path)
    opened = []
    rc = server.run(s, open_browser=False, serve=lambda *a, **k: None, opener=opened.append, answers=lambda h, p: False)
    assert rc == 0 and opened == []


def test_lan_binding_uses_the_machine_address_in_the_browser_url(tmp_path):
    s = config.Settings(home=tmp_path)
    s.web_allow_lan = True
    opened = []
    server.run(s, serve=lambda *a, **k: None, opener=opened.append, answers=lambda h, p: True)
    assert opened == ["http://127.0.0.1:8433/"]      # the browser on this machine still uses loopback
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_server.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 11: Implement `server.py`**

```python
"""`lakota-grades web`: run the server in the foreground, or hand off to the one already running.

One instance per home (spec section 15, risk 4): an exclusive pid lock beside the database.
If the port already answers /health as this app, the second start opens the browser there
and exits 0 -- that is what the desktop shortcut and `LakotaSheet.exe` with no arguments do.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from ..config import Settings
from . import db
from .app import APP_NAME, create_app

LOCK_NAME = "web.lock"


def port_answers(host: str, port: int, timeout: float = 1.0) -> bool:
    """True when something on host:port is this app (GET /health says so)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_NAME
    except Exception:
        return False


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


class WebLock:
    """<home>/web.lock holding our pid. A lock whose pid is gone is stale and taken over."""

    def __init__(self, path: Path):
        self.path, self.held = path, False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                pid = int(self.path.read_text().strip() or "0")
            except ValueError:
                pid = 0
            if _pid_alive(pid):
                return False
            self.path.unlink(missing_ok=True)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                return False
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        self.held = True
        return True

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False


def _wait_and_open(url: str, opener, *, answers=port_answers, tries: int = 100, interval: float = 0.2) -> None:
    """Open the browser once the server answers (called on a helper thread while uvicorn runs)."""
    host, port = url.split("//")[1].split("/")[0].split(":")
    for _ in range(tries):
        if answers(host, int(port)):
            opener(url)
            return
        time.sleep(interval)


def _serve(app, host: str, port: int) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


def run(settings: Settings, *, host: str | None = None, port: int | None = None, open_browser: bool = True,
        serve=None, opener=None, answers=None, wait_and_open=None) -> int:
    host = host or settings.bind_host
    port = port or settings.web_port
    serve = serve or _serve
    opener = opener or webbrowser.open
    answers = answers or port_answers
    wait_and_open = wait_and_open or _wait_and_open
    local = f"http://127.0.0.1:{port}/"
    if answers("127.0.0.1", port):
        if open_browser:
            opener(local)
        print(f"Lakota Sheet is already running at {local}", file=sys.stderr)
        return 0
    lock = WebLock(settings.home / LOCK_NAME)
    if not lock.acquire():
        print(f"another server holds {settings.home / LOCK_NAME} but {local} does not answer; "
              f"stop it or delete the lock file", file=sys.stderr)
        return 1
    try:
        db.open_db(settings.home).close()             # create and migrate before the first request
        app = create_app(settings)
        if open_browser:
            threading.Thread(target=wait_and_open, args=(local, opener), kwargs={"answers": answers}, daemon=True).start()
        serve(app, host, port)
        return 0
    finally:
        lock.release()
```

Run the server tests. Expected: PASS. (The `_wait_and_open` test passes `answers` explicitly and `interval=0`, so no real sleeping.)

- [ ] **Step 12: The `web` CLI command**

In `cli.py`, before `cmd_doctor`:

```python
def cmd_web(args) -> int:
    from .web import server
    return server.run(load_settings(), host=args.host, port=args.port, open_browser=not args.no_browser)
```

and in `main`, after the `app` parser:

```python
    w = sub.add_parser("web", help="run the browser app (foreground); opens the browser unless --no-browser")
    w.add_argument("--host", default=None, help="bind address (default: config.toml [web], 127.0.0.1)")
    w.add_argument("--port", type=int, default=None, help="port (default: config.toml [web], 8433)")
    w.add_argument("--no-browser", action="store_true")
    w.set_defaults(fn=cmd_web)
```

Update the module docstring's command list to include `web`.

- [ ] **Step 13: Full suite, then commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`
Expected: all pass (238 + the new tests), no warnings. If Starlette's `TestClient` or `StaticFiles` warns on the installed version, fix the cause; the output must be pristine.

```bash
git add pyproject.toml lakota_grades/config.py lakota_grades/cli.py lakota_grades/web tests/test_config.py tests/test_web_app.py tests/test_web_server.py
git commit -m "web: the FastAPI app, the server with a pid lock, the base layout and lakota-grades web

Closes #13

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The item store behind the pages, and the shared page fixture (issue #14, part 1)

Pages need one list of a kid's live items with everything a row shows: which sources know it, whether it is open and actionable, its flag, a status phrase, note count and reconciliation case kinds. That list is computed once here, over Plan A's rules, and the routes only filter and sort it.

**Files:**
- Create: `lakota_grades/web/stores/items.py`, `tests/web_fixtures.py`, `tests/test_web_stores_pages.py`
- Modify: `lakota_grades/web/reconcile.py` (`_rows` → `live_items`, public; add `upcoming`)

**Interfaces:**
- Consumes: `reconcile.open_sources`, `is_actionable`, `cases`, `db.latest_observations`, `stores.students`.
- Produces:
  - `reconcile.live_items(conn, student_id, now) -> [Row]` (the old `_rows`, same rows: joined `course_name`, `course_short`, `course_source`, `peer_course_id`, `kid`, `flag`, `flag_set_at`)
  - `reconcile.upcoming(item, obs, now, days_ahead=14) -> bool`
  - `stores.items.ItemView` dataclass; `stores.items.SHOW = ("open", "actionable", "all")`; `SORTS = ("due", "course", "name", "status")`; `FLAGGED = ("any", "marked", "handled", "none")`
  - `stores.items.list_items(conn, student, *, now, rules, show="open", source=None, course_id=None, kind=None, flagged=None, sort="due") -> [ItemView]`
  - `stores.items.one(conn, student, item_id, *, now, rules) -> ItemView | None`
  - `stores.items.status_text(item, obs, now) -> str`
  - `stores.items.Counts(actionable, due_today, due_tomorrow, new_since_yesterday)`; `stores.items.dashboard_counts(conn, student, *, now, rules) -> Counts`
  - `tests/web_fixtures.py`: `TZ`, `NOW` (2026-09-15 14:00 EDT), `snapshot() -> dict`, `seed(home, snap=None, now=NOW) -> sqlite3.Connection` (open, ingest, return the open connection), `app_for(home) -> TestClient`

- [ ] **Step 1: The fixture**

`tests/web_fixtures.py`:

```python
"""One snapshot for every page test: two kids, and every row situation the pages must show.

Alex, Honors English 9 (Canvas course 5 <-> HAC "Honors English 9 S1"):
  77 Quiz 1        due 9/12  Canvas MISSING, HAC 28/30           -> open (canvas), disagree
  78 Essay draft   due 9/14  submitted, ungraded                 -> submitted_ungraded, not open
  79 Reading log   due 9/20  unsubmitted, in the future          -> upcoming, not open
  80 Worksheet 3   due 9/16  unsubmitted (tomorrow)              -> upcoming, due tomorrow
  81 Vocabulary    due 9/15  unsubmitted (today)                 -> upcoming, due today
  82 Lab notebook  due 9/10  on paper, unsubmitted, no grade     -> open (canvas), paper_no_grade
  HAC-only "Participation" due 9/08, blank score                 -> open (hac), one_source
Alex, Algebra I (Canvas course 6 <-> HAC "Algebra I - 2"):
  90 Homework 4    due 8/20  MISSING                             -> open, past_credit (14-day default window)
Sam, Science 7 (Canvas course 7 <-> HAC "Science 7 - 1"):
  100 Cell diagram due 9/13  MISSING                             -> open, actionable
  101 Safety quiz  due 9/11  graded 0                            -> open (ZERO), actionable
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from lakota_grades import config
from lakota_grades.web import app as webapp, db, ingest

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)


def _a(id, name, due, **kw):
    base = {"id": id, "name": name, "due_at": f"2026-{due}T23:59:00-04:00", "unlock_at": None, "created_at": "2026-08-20T08:00:00-04:00",
            "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "group_weight": None,
            "published": True, "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": False,
            "excused": False, "submitted_at": None, "seconds_late": 0}
    base.update(kw)
    return base


def _h(name, due, score, points=10.0, assigned="09/01/2026"):
    return {"due": due, "assigned": assigned, "name": name, "category": "Assignments", "score": score,
            "score_raw": "" if score is None else f"{score:.2f}", "points": points, "percent": "" if score is None else "93.33%"}


def snapshot() -> dict:
    return {
        "fetched_at": "2026-09-15T13:50:00-04:00", "fetched_at_epoch": 1789000000, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {
            "Alex": {"name": "Alex Example", "canvas_id": 1, "hac_name": "Alex Example",
                "canvas": {"courses": [
                    {"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                     "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                     "staff": [{"name": "Michael Hoch", "email": "hoch@example.org", "roles": ["TeacherEnrollment"]}],
                     "assignments": [
                         _a(77, "Quiz 1", "09-12", missing=True, points_possible=30.0),
                         _a(78, "Essay draft", "09-14", state="submitted", submitted_at="2026-09-14T20:00:00-04:00"),
                         _a(79, "Reading log", "09-20"),
                         _a(80, "Worksheet 3", "09-16"),
                         _a(81, "Vocabulary", "09-15"),
                         _a(82, "Lab notebook", "09-10", submission_types=["on_paper"]),
                     ]},
                    {"id": 6, "name": "Algebra I S1-2027-Lee", "course_code": "ALG1",
                     "grade": {"current_score": 78.0, "final_score": None, "current_grade": "C+", "hidden": False},
                     "staff": [{"name": "Dana Lee", "email": None, "roles": ["TeacherEnrollment"]}],
                     "assignments": [_a(90, "Homework 4", "08-20", missing=True)]},
                ]},
                "hac": {"week_view": [], "classes": [
                    {"code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 88.0, "last_updated": "9/11/2026",
                     "assignments": [_h("Quiz 1", "09/12/2026", 28.0, points=30.0), _h("Participation", "09/08/2026", None)], "categories": []},
                    {"code": "20010 - 2", "name": "Algebra I - 2", "marking_period_avg": 79.5, "last_updated": "9/12/2026",
                     "assignments": [], "categories": []},
                ]}},
            "Sam": {"name": "Sam Example", "canvas_id": 2, "hac_name": "Sam Example",
                "canvas": {"courses": [
                    {"id": 7, "name": "Science 7 S1-2027-Kim", "course_code": "SCI7",
                     "grade": {"current_score": 85.0, "final_score": None, "current_grade": "B", "hidden": False},
                     "staff": [{"name": "Pat Kim", "email": None, "roles": ["TeacherEnrollment"]}],
                     "assignments": [_a(100, "Cell diagram", "09-13", missing=True),
                                     _a(101, "Safety quiz", "09-11", state="graded", score=0.0, grade="0")]},
                ]},
                "hac": {"week_view": [], "classes": [
                    {"code": "30001 - 1", "name": "Science 7 - 1", "marking_period_avg": 84.0, "last_updated": "9/12/2026",
                     "assignments": [], "categories": []},
                ]}},
        },
    }


def seed(home: Path, snap: dict | None = None, now: datetime = NOW) -> sqlite3.Connection:
    conn = db.open_db(home)
    ingest.record(conn, snap or snapshot(), tz=TZ, now=now)
    return conn


def app_for(home: Path, now: datetime = NOW) -> TestClient:
    """A client whose app clock is frozen at `now` (pages compare due dates against it)."""
    s = config.Settings(home=home)
    application = webapp.create_app(s)
    application.state.lakota.now = lambda: now
    return TestClient(application)
```

- [ ] **Step 2: Store tests**

`tests/test_web_stores_pages.py`:

```python
"""The item list every page reads: sources, openness, actionability, status words, filters, counts."""
from __future__ import annotations

from datetime import timedelta

from lakota_grades import late_rules
from lakota_grades.web import reconcile
from lakota_grades.web.stores import flags, items, notes, students
from tests.web_fixtures import NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _doug(conn):
    return students.by_key(conn, "Alex")


def _by_name(views):
    return {v.name: v for v in views}


def test_all_items_carry_sources_status_and_flags(tmp_path):
    conn = seed(tmp_path)
    v = _by_name(items.list_items(conn, _doug(conn), now=NOW, rules=RULES, show="all"))
    assert set(v) == {"Quiz 1", "Essay draft", "Reading log", "Worksheet 3", "Vocabulary", "Lab notebook", "Participation", "Homework 4"}
    assert v["Quiz 1"].sources == ("canvas", "hac") and v["Quiz 1"].open_in == {"canvas"} and v["Quiz 1"].actionable
    assert v["Quiz 1"].status == "Missing" and v["Quiz 1"].hac["score"] == 28.0 and v["Quiz 1"].case_kinds == ["disagree"]
    assert v["Essay draft"].status == "Submitted, ungraded" and not v["Essay draft"].open_in and v["Essay draft"].case_kinds == ["submitted_ungraded"]
    assert v["Vocabulary"].status == "Due today" and v["Worksheet 3"].status == "Due tomorrow" and v["Reading log"].status == "Due Sun"
    assert v["Lab notebook"].kind == "paper" and v["Lab notebook"].status == "Paper, check" and "paper_no_grade" in v["Lab notebook"].case_kinds
    assert v["Participation"].sources == ("hac",) and v["Participation"].status == "HAC, no grade" and v["Participation"].case_kinds == ["one_source"]
    assert v["Homework 4"].open_in == {"canvas"} and not v["Homework 4"].actionable and "past_credit" in v["Homework 4"].case_kinds
    assert v["Homework 4"].case_kinds == ["one_source", "past_credit"]     # Algebra's HAC twin has no row for it (rule 2) and credit closed (rule 5)
    assert v["Quiz 1"].course_short == "Honors English 9" and v["Quiz 1"].due.date().isoformat() == "2026-09-12"


def test_show_open_actionable_and_all(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    names = lambda **kw: sorted(v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, **kw))
    assert names(show="open") == ["Homework 4", "Lab notebook", "Participation", "Quiz 1", "Reading log", "Vocabulary", "Worksheet 3"]
    assert names(show="actionable") == ["Lab notebook", "Participation", "Quiz 1"]
    assert len(names(show="all")) == 8
    flags.set_flag(conn, v_id(conn, "Quiz 1"), "done", now="2026-09-15T14:30:00-04:00")
    assert "Quiz 1" not in names(show="open") and "Quiz 1" not in names(show="actionable")
    assert "Quiz 1" in names(show="all") and _by_name(items.list_items(conn, d, now=NOW, rules=RULES, show="all"))["Quiz 1"].flag == "done"


def v_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_source_course_kind_and_flag_filters(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    names = lambda **kw: sorted(v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", **kw))
    assert names(source="hac") == ["Participation", "Quiz 1"]
    assert names(source="canvas") == ["Essay draft", "Homework 4", "Lab notebook", "Quiz 1", "Reading log", "Vocabulary", "Worksheet 3"]
    assert names(source="both") == ["Quiz 1"]
    alg = [c for c in students.courses(conn, d["id"]) if c["source"] == "canvas" and c["short_name"] == "Algebra I"][0]
    assert names(course_id=alg["id"]) == ["Homework 4"]
    assert names(kind="paper") == ["Lab notebook"]
    flags.set_flag(conn, v_id(conn, "Essay draft"), "ask_teacher", now="2026-09-15T14:30:00-04:00", text="emailed 9/15")
    flags.set_flag(conn, v_id(conn, "Homework 4"), "ignore", now="2026-09-15T14:31:00-04:00")
    assert names(flagged="any") == ["Essay draft", "Homework 4"]
    assert names(flagged="marked") == ["Essay draft"] and names(flagged="handled") == ["Homework 4"]
    assert "Essay draft" not in names(flagged="none")
    assert _by_name(items.list_items(conn, d, now=NOW, rules=RULES, show="all"))["Essay draft"].flag_text == "emailed 9/15"


def test_sorts(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    by_due = [v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", sort="due")]
    assert by_due[:2] == ["Homework 4", "Participation"] and by_due[-1] == "Reading log"
    by_course = [v.course_short for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", sort="course")]
    assert by_course == sorted(by_course)
    by_name = [v.name for v in items.list_items(conn, d, now=NOW, rules=RULES, show="all", sort="name")]
    assert by_name == sorted(by_name, key=str.lower)


def test_note_counts_and_one(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    qid = v_id(conn, "Quiz 1")
    notes.add(conn, "item", qid, "Teacher says the HAC score is right", now="2026-09-15T14:30:00-04:00")
    one = items.one(conn, d, qid, now=NOW, rules=RULES)
    assert one is not None and one.notes == 1 and one.name == "Quiz 1"
    assert items.one(conn, d, 99999, now=NOW, rules=RULES) is None
    sam = students.by_key(conn, "Sam")
    assert items.one(conn, sam, qid, now=NOW, rules=RULES) is None       # another kid's item is not this kid's


def test_dashboard_counts(tmp_path):
    conn = seed(tmp_path)
    c = items.dashboard_counts(conn, _doug(conn), now=NOW, rules=RULES)
    assert (c.actionable, c.due_today, c.due_tomorrow, c.new_since_yesterday) == (3, 1, 1, 8)
    k = items.dashboard_counts(conn, students.by_key(conn, "Sam"), now=NOW, rules=RULES)
    assert (k.actionable, k.due_today, k.due_tomorrow, k.new_since_yesterday) == (2, 0, 0, 2)
    later = items.dashboard_counts(conn, _doug(conn), now=NOW + timedelta(days=3), rules=RULES)
    assert later.new_since_yesterday == 0


def test_live_items_is_public_and_upcoming_is_bounded(tmp_path):
    conn = seed(tmp_path)
    d = _doug(conn)
    rows = {r["name"]: r for r in reconcile.live_items(conn, d["id"], NOW)}
    obs = reconcile.db.latest_observations(conn, d["id"])
    assert reconcile.upcoming(rows["Reading log"], obs[rows["Reading log"]["id"]], NOW)
    assert not reconcile.upcoming(rows["Reading log"], obs[rows["Reading log"]["id"]], NOW, days_ahead=3)
    assert not reconcile.upcoming(rows["Quiz 1"], obs[rows["Quiz 1"]["id"]], NOW)       # past due is open, not upcoming
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_stores_pages.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: `reconcile.live_items` and `upcoming`**

In `reconcile.py`: rename `_rows` to `live_items` (update its two callers, `actionable_items` and `cases`), add the public aliases `due_of = _due` and `comparable = _comparable` right after those two functions (the item store reads them; a leading underscore across a module boundary is a smell), and add after `open_sources`:

```python
def upcoming(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime, days_ahead: int = 14) -> bool:
    """Not open yet, but due within `days_ahead` days and still unsubmitted in Canvas: the
    sheet's DUE TODAY / DUE TOMORROW / DUE <weekday> rows."""
    due = _due(item)
    c = obs.get("canvas")
    if c is None or due is None or c["excused"] or c["published"] == 0:
        return False
    a, b = _comparable(due, now)
    if a <= b or a > b + timedelta(days=days_ahead):
        return False
    return c["state"] in ("unsubmitted", None) and c["score"] is None
```

- [ ] **Step 4: Implement `stores/items.py`**

```python
"""The item list behind the Kid page, the Dashboard counts and the Reconcile page.

One pass over a kid's live items (Plan A's `reconcile.live_items`) decorates each row with
what the browser shows: the sources that know it, whether it is open and actionable, its
active flag, a status phrase, the note count and the reconciliation case kinds. Routes
filter and sort these views; they never touch SQL.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...open_items import HANDLED_FLAGS, MARKED_FLAGS
from .. import db, reconcile

SHOW = ("open", "actionable", "all")
SORTS = ("due", "course", "name", "status")
FLAGGED = ("any", "marked", "handled", "none")
DAYS_AHEAD = 14


@dataclass
class ItemView:
    id: int
    key: str
    name: str
    course_id: int
    course_short: str
    course_name: str
    kind: str
    points: float | None
    due: datetime | None
    sources: tuple[str, ...]
    open_in: set[str]
    actionable: bool
    upcoming: bool
    flag: str | None
    flag_text: str
    status: str
    canvas: sqlite3.Row | None
    hac: sqlite3.Row | None
    notes: int = 0
    case_kinds: list[str] = field(default_factory=list)

    @property
    def overdue(self) -> bool:
        return bool(self.open_in)

    @property
    def handled(self) -> bool:
        return self.flag in HANDLED_FLAGS


def _score(o: sqlite3.Row, points) -> str:
    if o["score"] is None:
        return o["grade"] or ""
    return f"{o['score']:g}/{points:g}" if points else f"{o['score']:g}"


def status_text(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime) -> str:
    """The status column, in words a parent reads (the sheet's status words, unshouted)."""
    c, h = obs.get("canvas"), obs.get("hac")
    due = reconcile.due_of(item)
    past = due is not None and reconcile.comparable(due, now)[0] < reconcile.comparable(due, now)[1]
    if c is not None:
        if c["excused"]:
            return "Excused"
        if c["published"] == 0:
            return "Unpublished"
        if c["missing"]:
            return "Missing"
        if c["state"] == "graded" and c["score"] == 0:
            return "Zero"
        if c["late"] and c["score"] is None:
            return "Late, ungraded"
        if c["submitted_at"] and c["score"] is None:
            return "Submitted, ungraded"
        if c["score"] is not None:
            return _score(c, item["points"])
        if past:
            return "Paper, check" if item["kind"] == "paper" else "Missing"
        if due is not None:
            days = (due.date() - now.date()).days
            return "Due today" if days == 0 else "Due tomorrow" if days == 1 else "Due " + due.strftime("%a")
        return "No due date"
    if h is not None:
        if h["score"] is None:
            return "HAC, no grade" if past else "Not graded yet"
        return _score(h, item["points"])
    return ""


def _views(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules) -> list[ItemView]:
    latest = db.latest_observations(conn, student["id"])
    kinds: dict[int, list[str]] = {}
    for case in reconcile.cases(conn, student["id"], rules=rules, now=now):
        kinds.setdefault(case.item_id, []).append(case.kind)
    note_counts = {r["target_id"]: r["n"] for r in conn.execute(
        "SELECT target_id, COUNT(*) AS n FROM notes WHERE target_type = 'item' GROUP BY target_id")}
    flag_text = {r["item_id"]: r["text"] for r in conn.execute("SELECT item_id, text FROM flags WHERE cleared_at IS NULL")}
    out: list[ItemView] = []
    for r in reconcile.live_items(conn, student["id"], now):
        obs = latest.get(r["id"], {})
        out.append(ItemView(
            id=r["id"], key=r["key"], name=r["name"], course_id=r["course_id"], course_short=r["course_short"],
            course_name=r["course_name"], kind=r["kind"], points=r["points"], due=reconcile.due_of(r),
            sources=tuple(s for s in ("canvas", "hac") if s in obs),
            open_in=reconcile.open_sources(r, obs, now),
            actionable=reconcile.is_actionable(r, obs, r["flag"], rules, r["kid"], now),
            upcoming=reconcile.upcoming(r, obs, now, DAYS_AHEAD),
            flag=r["flag"], flag_text=flag_text.get(r["id"], ""), status=status_text(r, obs, now),
            canvas=obs.get("canvas"), hac=obs.get("hac"),
            notes=note_counts.get(r["id"], 0), case_kinds=kinds.get(r["id"], []),
        ))
    return out


def _keep(v: ItemView, show: str, source, course_id, kind, flagged) -> bool:
    if show == "open" and not ((v.open_in or v.upcoming) and not v.handled):
        return False
    if show == "actionable" and not v.actionable:
        return False
    if source == "both" and v.sources != ("canvas", "hac"):
        return False
    if source in ("canvas", "hac") and source not in v.sources:
        return False
    if course_id is not None and v.course_id != course_id:
        return False
    if kind and v.kind != kind:
        return False
    if flagged == "any" and not v.flag:
        return False
    if flagged == "marked" and v.flag not in MARKED_FLAGS:
        return False
    if flagged == "handled" and v.flag not in HANDLED_FLAGS:
        return False
    if flagged == "none" and v.flag:
        return False
    return True


_FAR = datetime.max.replace(tzinfo=None)


def _sort_key(sort: str):
    def due_key(v: ItemView):
        return (v.due.replace(tzinfo=None) if v.due else _FAR, v.course_short, v.name.lower())
    if sort == "course":
        return lambda v: (v.course_short, due_key(v))
    if sort == "name":
        return lambda v: (v.name.lower(), due_key(v))
    if sort == "status":
        return lambda v: (not v.actionable, not v.overdue, v.status, due_key(v))
    return due_key


def list_items(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules, show: str = "open",
               source: str | None = None, course_id: int | None = None, kind: str | None = None,
               flagged: str | None = None, sort: str = "due") -> list[ItemView]:
    if show not in SHOW:
        show = "open"
    views = [v for v in _views(conn, student, now=now, rules=rules) if _keep(v, show, source, course_id, kind, flagged)]
    return sorted(views, key=_sort_key(sort if sort in SORTS else "due"))


def one(conn: sqlite3.Connection, student: sqlite3.Row, item_id: int, *, now: datetime, rules) -> ItemView | None:
    return next((v for v in _views(conn, student, now=now, rules=rules) if v.id == item_id), None)


@dataclass(frozen=True)
class Counts:
    actionable: int
    due_today: int
    due_tomorrow: int
    new_since_yesterday: int


def dashboard_counts(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules) -> Counts:
    views = _views(conn, student, now=now, rules=rules)
    today = now.date()
    due_today = sum(1 for v in views if v.upcoming and v.due and v.due.date() == today)
    due_tomorrow = sum(1 for v in views if v.upcoming and v.due and v.due.date() == today + timedelta(days=1))
    since = (now - timedelta(days=1)).isoformat()
    new = conn.execute(
        """SELECT COUNT(*) AS n FROM items i JOIN refreshes r ON r.id = i.first_seen
           WHERE i.student_id = ? AND r.started_at >= ?""", (student["id"], since)).fetchone()["n"]
    return Counts(sum(1 for v in views if v.actionable), due_today, due_tomorrow, new)
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_stores_pages.py tests/test_reconcile.py`
Expected: PASS. If `test_dashboard_counts` disagrees on `new_since_yesterday`, check the fixture's ingest `now` (2026-09-15 14:00) against `since` (2026-09-14 14:00): every item's `first_seen` refresh started at 14:00 on the 15th, so all 8 (Alex) and 2 (Sam) count; three days later none do. If `Due Sun` differs, 2026-09-20 is a Sunday; check `%a`.

- [ ] **Step 5: Full suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`
Expected: all pass.

```bash
git add lakota_grades/web/reconcile.py lakota_grades/web/stores/items.py tests/web_fixtures.py tests/test_web_stores_pages.py
git commit -m "web.stores.items: one decorated item list for the pages; reconcile.live_items and upcoming

Part of #14

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Dashboard and Kid pages with notes and the flag menu (issue #14, part 2)

**Files:**
- Create: `lakota_grades/web/routes/kid.py`, `notes.py`, `flags.py`; templates `kid.html`, `course.html`, `_item_rows.html`, `_item_detail.html`, `_notes.html`, `_flag_menu.html`; `tests/test_web_pages.py`
- Modify: `lakota_grades/web/routes/dashboard.py`, `templates/dashboard.html`, `lakota_grades/web/app.py` (include the routers)

**Interfaces:**
- Consumes: Task 2's `render`, `render_partial`, `Db`, `State`, `get_state`; Task 3's `stores.items`; `stores.notes`, `stores.flags`, `stores.students`, `stores.runs`.
- Produces (URLs the Reconcile page and part 2 reuse):
  - `GET /` Dashboard; `GET /kids/{key}?show=&source=&course=&kind=&flagged=&sort=` (htmx → `partial` block: the table only); `GET /items/{id}` → `_item_detail.html`; `GET /kids/{key}/courses/{course_id}` → `course.html`
  - `POST /items/{id}/flag` form `flag` (one of `FLAGS` or `clear`), `text` → `_item_detail.html`
  - `POST /notes` form `target_type`, `target_id`, `body` → `_notes.html` for that target; `POST /notes/{id}/edit` form `body`; `POST /notes/{id}/delete` → `_notes.html`
  - `app.student_or_404(conn, key) -> Row` raising `HTTPException(404)`

- [ ] **Step 1: Page tests**

`tests/test_web_pages.py`:

```python
"""Dashboard and Kid pages: what a parent sees, and the notes and flags round trip."""
from __future__ import annotations

from lakota_grades.web import db
from lakota_grades.web.stores import flags, notes
from tests.web_fixtures import NOW, app_for, seed


def _item_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_dashboard_cards_per_kid(tmp_path):
    conn = seed(tmp_path)
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path) VALUES (?,?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:05-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "2p Al=3 Sam=2", "/x/sheet.pdf"))
    conn.close()
    r = app_for(tmp_path).get("/")
    assert r.status_code == 200
    body = r.text
    assert body.index("Alex") < body.index("Sam")
    assert "3 actionable" in body and "1 due today" in body and "1 due tomorrow" in body and "8 new since yesterday" in body
    assert "2 actionable" in body                                   # Sam
    assert "Printed today" in body and "2p Al=3 Sam=2" in body
    assert 'href="/kids/Alex?show=actionable"' in body


def test_dashboard_with_nothing_printed_says_so(tmp_path):
    seed(tmp_path).close()
    assert "Nothing printed today" in app_for(tmp_path).get("/").text


def test_kid_page_lists_open_items_by_default_with_filters_and_sort_links(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/kids/Alex")
    assert r.status_code == 200
    body = r.text
    for name in ("Quiz 1", "Lab notebook", "Participation", "Vocabulary", "Worksheet 3", "Reading log", "Homework 4"):
        assert name in body, name
    assert "Essay draft" not in body                                 # submitted: not open
    assert "Missing" in body and "Due today" in body and "HAC, no grade" in body
    assert 'name="show"' in body and 'value="actionable"' in body and 'name="course"' in body
    assert "Honors English 9" in body and "Algebra I" in body        # course filter options
    assert "&amp;sort=name" in body or "&sort=name" in body           # the column header sort links


def test_kid_page_filters_apply_and_htmx_gets_the_table_only(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.get("/kids/Alex?show=actionable")
    assert "Quiz 1" in r.text and "Reading log" not in r.text
    r = c.get("/kids/Alex?show=all&source=hac", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "Participation" in r.text and "Essay draft" not in r.text
    r = c.get("/kids/Alex?show=all&flagged=marked")
    assert "Quiz 1" not in r.text


def test_unknown_kid_is_404(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).get("/kids/Nobody").status_code == 404


def test_item_detail_shows_both_sources_cases_notes_and_the_flag_menu(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    notes.add(conn, "item", qid, "Asked Mr Hoch about the missing mark", now="2026-09-15T14:30:00-04:00")
    conn.close()
    r = app_for(tmp_path).get(f"/items/{qid}")
    assert r.status_code == 200 and "<html" not in r.text
    body = r.text
    assert "Canvas" in body and "Missing" in body and "HAC" in body and "28/30" in body
    assert "Canvas says MISSING, HAC shows 28" in body              # the reconcile reason (reconcile._score_text prints the bare score)
    assert "Asked Mr Hoch" in body
    for f in ("done", "excused", "ignore", "follow_up", "ask_teacher"):
        assert f'value="{f}"' in body, f
    assert f'hx-post="/items/{qid}/flag"' in body and f'hx-post="/notes"' in body


def test_flag_round_trip_updates_the_detail_and_the_list(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    r = c.post(f"/items/{qid}/flag", data={"flag": "done", "text": "HAC is right"})
    assert r.status_code == 200 and "Marked done" in r.text and "HAC is right" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, qid)["flag"] == "done"
    conn.close()
    assert "Quiz 1" not in c.get("/kids/Alex").text               # handled items leave the open list
    assert "Quiz 1" in c.get("/kids/Alex?show=all").text
    r = c.post(f"/items/{qid}/flag", data={"flag": "clear"})
    assert "No flag" in r.text
    assert "Quiz 1" in c.get("/kids/Alex").text
    assert c.post(f"/items/{qid}/flag", data={"flag": "bogus"}).status_code == 400


def test_notes_round_trip(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    r = c.post("/notes", data={"target_type": "item", "target_id": qid, "body": "first note"})
    assert r.status_code == 200 and "first note" in r.text
    conn = db.open_db(tmp_path)
    (n,) = notes.for_target(conn, "item", qid)
    conn.close()
    r = c.post(f"/notes/{n['id']}/edit", data={"body": "edited note"})
    assert "edited note" in r.text and "first note" not in r.text
    r = c.post(f"/notes/{n['id']}/delete")
    assert "edited note" not in r.text and "No notes yet" in r.text
    assert c.post("/notes", data={"target_type": "item", "target_id": qid, "body": "   "}).status_code == 400
    assert c.post("/notes", data={"target_type": "planet", "target_id": 1, "body": "x"}).status_code == 400


def test_course_page_shows_grades_teacher_and_course_notes(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    notes.add(conn, "course", cid, "Syllabus says 7-day late window", now="2026-09-15T14:30:00-04:00")
    conn.close()
    r = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}")
    assert r.status_code == 200
    body = r.text
    assert "Honors English 9" in body and "Michael Hoch" in body and "hoch@example.org" in body
    assert "91.2" in body and "A-" in body and "88" in body          # Canvas current, letter, HAC average via the peer course
    assert "Syllabus says" in body and 'name="target_type" value="course"' in body
    assert "Quiz 1" in body                                          # the course's items


def test_course_of_another_kid_is_404(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE short_name = 'Science 7' AND source = 'canvas'").fetchone()["id"]
    conn.close()
    assert app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").status_code == 404
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_pages.py`
Expected: FAIL (404s and missing text).

- [ ] **Step 2: `app.py` additions**

Add to `app.py`:

```python
from fastapi import HTTPException


def student_or_404(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    s = students.by_key(conn, key)
    if s is None or s["hidden"]:
        raise HTTPException(404, f"no student {key!r}")
    return s
```

and in `create_app`, replace the single router include with:

```python
    from .routes import dashboard, flags as flag_routes, kid, notes as note_routes
    for r in (dashboard.router, kid.router, note_routes.router, flag_routes.router):
        app.include_router(r)
```

Make the 404 handler cover `HTTPException(404)` raised by routes too: register it with `@app.exception_handler(HTTPException)` and, inside, fall through to FastAPI's default for any status other than 404 (`from fastapi.exception_handlers import http_exception_handler` and `return await http_exception_handler(request, exc)`).

- [ ] **Step 3: Routes**

`routes/dashboard.py` (replace):

```python
"""The Dashboard: one card per kid with today's numbers, and what printed today."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ..stores import items, runs, students

router = APIRouter()


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    cards = [(s, items.dashboard_counts(conn, s, now=now, rules=rules)) for s in students.visible(conn)]
    return render(request, conn, "dashboard.html", current="dashboard", cards=cards,
                  printed=runs.printed_on(conn, now.date()), jobs=state.extra.get("jobs"))
```

`routes/kid.py`:

```python
"""The Kid page: the item list with filters, the expanded row, and the course page."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request

from ..app import Db, State, render, render_partial, student_or_404
from ..stores import items, notes, students

router = APIRouter()


def _filters(request: Request) -> dict:
    q = request.query_params
    course = q.get("course")
    return {
        "show": q.get("show", "open"), "source": q.get("source") or None,
        "course_id": int(course) if course and course.isdigit() else None,
        "kind": q.get("kind") or None, "flagged": q.get("flagged") or None, "sort": q.get("sort", "due"),
    }


@router.get("/kids/{key}")
def kid(key: str, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    f = _filters(request)
    rows = items.list_items(conn, s, now=state.now(), rules=state.rules(), **f)
    return render(request, conn, "kid.html", current=f"kid:{key}", student=s, rows=rows, f=f,
                  courses=students.courses(conn, s["id"]), SHOW=items.SHOW, FLAGGED=items.FLAGGED, SORTS=items.SORTS)


@router.get("/items/{item_id}")
def item_detail(item_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = students.owner_of_item(conn, item_id)
    v = items.one(conn, s, item_id, now=state.now(), rules=state.rules()) if s is not None else None
    if v is None:
        raise HTTPException(404, "no such item")
    return render_partial(request, conn, "_item_detail.html", student=s, item=v, message=None,
                          notes=notes.for_target(conn, "item", item_id),
                          cases=[c for c in _cases(conn, s, state) if c.item_id == item_id])


def _cases(conn, s, state):
    from .. import reconcile
    return reconcile.cases(conn, s["id"], rules=state.rules(), now=state.now())


@router.get("/kids/{key}/courses/{course_id}")
def course(key: str, course_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    c = students.course(conn, course_id)
    if c is None or c["student_id"] != s["id"]:
        raise HTTPException(404, "no such course")
    peer = students.course(conn, c["peer_course_id"]) if c["peer_course_id"] else None
    grades = students.latest_grades(conn, s["id"])
    rows = items.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", course_id=course_id)
    if peer is not None:
        rows += items.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", course_id=peer["id"])
    return render(request, conn, "course.html", current=f"kid:{key}", student=s, course=c, peer=peer,
                  grade=grades.get(course_id), peer_grade=grades.get(peer["id"]) if peer else None,
                  history=students.grade_history(conn, course_id), rows=rows,
                  notes=notes.for_target(conn, "course", course_id))
```

`routes/flags.py`:

```python
"""Set or clear the one active flag on an item; answer with the refreshed detail partial."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, render_partial
from ..stores import flags, items, notes, students
from .. import db, reconcile

router = APIRouter()

LABELS = {"done": "Marked done", "excused": "Marked excused", "ignore": "Ignored", "follow_up": "Marked follow up",
          "ask_teacher": "Marked ask teacher", "clear": "No flag"}


@router.post("/items/{item_id}/flag")
def set_item_flag(item_id: int, request: Request, flag: str = Form(...), text: str = Form(""),
                  conn: sqlite3.Connection = Db, state=State):
    s = students.owner_of_item(conn, item_id)
    if s is None:
        raise HTTPException(404, "no such item")
    if flag not in flags.FLAGS and flag != "clear":
        raise HTTPException(400, f"unknown flag {flag!r}")
    now = db.now_iso(state.tz)
    if flag == "clear":
        flags.clear(conn, item_id, now=now)
    else:
        flags.set_flag(conn, item_id, flag, now=now, text=text.strip())
    v = items.one(conn, s, item_id, now=state.now(), rules=state.rules())
    cases = [c for c in reconcile.cases(conn, s["id"], rules=state.rules(), now=state.now()) if c.item_id == item_id]
    return render_partial(request, conn, "_item_detail.html", student=s, item=v, message=LABELS[flag],
                          notes=notes.for_target(conn, "item", item_id), cases=cases)
```

`routes/notes.py`:

```python
"""Notes on an item, a course or a student; every action answers with the target's note list."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, render_partial
from ..stores import notes
from .. import db

router = APIRouter()


def _partial(request, conn, target_type, target_id):
    return render_partial(request, conn, "_notes.html", target_type=target_type, target_id=target_id,
                          notes=notes.for_target(conn, target_type, target_id))


@router.post("/notes")
def add_note(request: Request, target_type: str = Form(...), target_id: int = Form(...), body: str = Form(""),
             conn: sqlite3.Connection = Db, state=State):
    if target_type not in notes.TARGETS:
        raise HTTPException(400, f"unknown target {target_type!r}")
    if not body.strip():
        raise HTTPException(400, "an empty note")
    notes.add(conn, target_type, target_id, body.strip(), now=db.now_iso(state.tz))
    return _partial(request, conn, target_type, target_id)


@router.post("/notes/{note_id}/edit")
def edit_note(note_id: int, request: Request, body: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    n = notes.get(conn, note_id)
    if n is None:
        raise HTTPException(404, "no such note")
    body = body or request.headers.get("HX-Prompt", "")     # htmx's hx-prompt sends the answer as a header
    if not body.strip():
        raise HTTPException(400, "an empty note")
    notes.edit(conn, note_id, body.strip(), now=db.now_iso(state.tz))
    return _partial(request, conn, n["target_type"], n["target_id"])


@router.post("/notes/{note_id}/delete")
def delete_note(note_id: int, request: Request, conn: sqlite3.Connection = Db):
    n = notes.get(conn, note_id)
    if n is None:
        raise HTTPException(404, "no such note")
    notes.delete(conn, note_id)
    return _partial(request, conn, n["target_type"], n["target_id"])
```

Add to `stores/notes.py`:

```python
def get(conn: sqlite3.Connection, note_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
```

and to `stores/students.py`:

```python
def owner_of_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT s.* FROM students s JOIN items i ON i.student_id = s.id WHERE i.id = ?", (item_id,)).fetchone()
```

- [ ] **Step 4: Templates**

`dashboard.html` (replace the content block):

```html
{% extends "base.html" %}
{% block title %}Dashboard · Lakota Sheet{% endblock %}
{% block content %}
{% block partial %}
<div class="cards">
  {% for s, c in cards %}
  <div class="card">
    <h2><a href="/kids/{{ s.key }}">{{ s.key | nickname }}</a></h2>
    <p><a href="/kids/{{ s.key }}?show=actionable" class="big">{{ c.actionable }} actionable</a></p>
    <p class="muted">{{ c.due_today }} due today · {{ c.due_tomorrow }} due tomorrow · {{ c.new_since_yesterday }} new since yesterday</p>
  </div>
  {% else %}
  <div class="card"><h2>Nothing here yet</h2><p class="muted">{% if refresh %}The last refresh found no students.{% else %}No refresh yet. Run <code>lakota-grades refresh</code> and this page fills in.{% endif %}</p></div>
  {% endfor %}
  <div class="card">
    <h2>Printed today</h2>
    {% for r in printed %}<p>{{ r.started_at | time12 }} <span class="badge OK">OK</span> {{ r.message }}</p>{% else %}<p class="muted">Nothing printed today.</p>{% endfor %}
    {% if jobs %}<p><button hx-post="/jobs/refresh" hx-target="#job">Refresh now</button></p><div id="job"></div>{% endif %}
  </div>
</div>
{% endblock %}
{% endblock %}
```

`kid.html`:

```html
{% extends "base.html" %}
{% block title %}{{ student.key | nickname }} · Lakota Sheet{% endblock %}
{% block content %}
<h2>{{ student.key | nickname }}</h2>
<form class="filters" hx-get="/kids/{{ student.key }}" hx-target="#items" hx-push-url="true" hx-trigger="change">
  <label>Show
    <select name="show">{% for v in SHOW %}<option value="{{ v }}" {{ 'selected' if f.show == v }}>{{ v }}</option>{% endfor %}</select></label>
  <label>Source
    <select name="source"><option value="">any</option>{% for v in ("canvas", "hac", "both") %}<option value="{{ v }}" {{ 'selected' if f.source == v }}>{{ v }}</option>{% endfor %}</select></label>
  <label>Course
    <select name="course"><option value="">any</option>{% for c in courses %}<option value="{{ c.id }}" {{ 'selected' if f.course_id == c.id }}>{{ c.short_name }} ({{ c.source }})</option>{% endfor %}</select></label>
  <label>Kind
    <select name="kind"><option value="">any</option>{% for v in ("online", "paper", "in class") %}<option value="{{ v }}" {{ 'selected' if f.kind == v }}>{{ v }}</option>{% endfor %}</select></label>
  <label>Flagged
    <select name="flagged"><option value="">any</option>{% for v in FLAGGED %}<option value="{{ v }}" {{ 'selected' if f.flagged == v }}>{{ v }}</option>{% endfor %}</select></label>
  <input type="hidden" name="sort" value="{{ f.sort }}">
</form>
<div id="items">
{% block partial %}
{% include "_item_rows.html" %}
{% endblock %}
</div>
{% endblock %}
```

`_item_rows.html`:

```html
{% set base = "/kids/" ~ student.key ~ "?show=" ~ f.show ~ (("&source=" ~ f.source) if f.source else "") ~ (("&course=" ~ f.course_id) if f.course_id else "") ~ (("&kind=" ~ f.kind) if f.kind else "") ~ (("&flagged=" ~ f.flagged) if f.flagged else "") %}
<table class="items">
  <thead><tr>
    <th><a href="{{ base }}&sort=due" hx-get="{{ base }}&sort=due" hx-target="#items" hx-push-url="true">Due</a></th>
    <th><a href="{{ base }}&sort=course" hx-get="{{ base }}&sort=course" hx-target="#items" hx-push-url="true">Course</a></th>
    <th><a href="{{ base }}&sort=name" hx-get="{{ base }}&sort=name" hx-target="#items" hx-push-url="true">Item</a></th>
    <th><a href="{{ base }}&sort=status" hx-get="{{ base }}&sort=status" hx-target="#items" hx-push-url="true">Status</a></th>
    <th>Sources</th><th>Flag</th>
  </tr></thead>
  <tbody>
  {% for v in rows %}
  <tr class="{{ 'overdue' if v.overdue }}" id="row-{{ v.id }}">
    <td class="due">{{ v.due | md if v.due else '' }}</td>
    <td><a href="/kids/{{ student.key }}/courses/{{ v.course_id }}">{{ v.course_short }}</a></td>
    <td><a href="#detail-{{ v.id }}" hx-get="/items/{{ v.id }}" hx-target="#detail-{{ v.id }}" hx-swap="innerHTML">{{ v.name }}</a>
        {% if v.notes %}<span class="badge">{{ v.notes }} note{{ 's' if v.notes != 1 }}</span>{% endif %}
        {% if v.case_kinds %}<span class="badge warn" title="{{ v.case_kinds | join(', ') }}">reconcile</span>{% endif %}</td>
    <td>{{ v.status }}{% if v.actionable %} <span class="badge">actionable</span>{% endif %}</td>
    <td class="muted">{{ v.sources | join(' + ') }}</td>
    <td>{{ v.flag.replace('_', ' ') if v.flag else '' }}</td>
  </tr>
  <tr class="detail"><td colspan="6" id="detail-{{ v.id }}"></td></tr>
  {% else %}
  <tr><td colspan="6" class="muted">Nothing matches these filters.</td></tr>
  {% endfor %}
  </tbody>
</table>
```

`_item_detail.html`:

```html
<div class="card" data-focus>
  <h2>{{ item.name }} <span class="muted">· {{ item.course_short }} · {{ item.kind or 'online' }}{% if item.points %} · {{ item.points | round(1) }} pts{% endif %}</span></h2>
  {% if message %}<p><strong>{{ message }}</strong>{% if item.flag_text %} <span class="muted">{{ item.flag_text }}</span>{% endif %}</p>{% endif %}
  <table class="items">
    <tr><th>Source</th><th>Says</th><th>Score</th><th>Submitted</th></tr>
    {% if item.canvas %}<tr><td>Canvas</td><td>{{ item.status }}</td><td>{{ item.canvas.score if item.canvas.score is not none else item.canvas.grade or '' }}</td><td>{{ item.canvas.submitted_at | wd_md_time }}</td></tr>{% endif %}
    {% if item.hac %}<tr><td>HAC</td><td>{{ 'graded' if item.hac.score is not none else 'no grade' }}</td><td>{% if item.hac.score is not none %}{{ item.hac.score | round(1) | string | replace('.0', '') }}{% if item.points %}/{{ item.points | round(1) | string | replace('.0', '') }}{% endif %}{% endif %}</td><td></td></tr>{% endif %}
  </table>
  {% if cases %}<ul>{% for c in cases %}<li class="case {{ c.kind }}"><strong>{{ c.kind.replace('_', ' ') }}</strong>: {{ c.reason }}</li>{% endfor %}</ul>{% endif %}
  {% include "_flag_menu.html" %}
  {% include "_notes.html" %}
</div>
```

In `_item_detail.html`, the `_notes.html` include expects `target_type`, `target_id`, `notes`: set them with `{% set target_type = "item" %}{% set target_id = item.id %}` before the include.

`_flag_menu.html`:

```html
<form class="flagmenu" hx-post="/items/{{ item.id }}/flag" hx-target="closest .card" hx-swap="outerHTML">
  <span class="muted">Flag: {{ item.flag.replace('_', ' ') if item.flag else 'none' }}</span>
  <input name="text" placeholder="why (optional)" value="{{ item.flag_text }}">
  {% for f in ("done", "excused", "ignore", "follow_up", "ask_teacher") %}<button name="flag" value="{{ f }}">{{ f.replace('_', ' ') }}</button>{% endfor %}
  {% if item.flag %}<button name="flag" value="clear">clear</button>{% endif %}
</form>
```

`_notes.html`:

```html
<div class="notes" id="notes-{{ target_type }}-{{ target_id }}">
  {% for n in notes %}
  <div class="note">
    <div>{{ n.body }}</div>
    <div class="meta">{{ n.created_at | wd_md_time }}{% if n.updated_at != n.created_at %} · edited {{ n.updated_at | wd_md_time }}{% endif %}
      <form style="display:inline" hx-post="/notes/{{ n.id }}/edit" hx-target="#notes-{{ target_type }}-{{ target_id }}" hx-swap="outerHTML" hx-prompt="Edit the note"><button>edit</button></form>
      <form style="display:inline" hx-post="/notes/{{ n.id }}/delete" hx-target="#notes-{{ target_type }}-{{ target_id }}" hx-swap="outerHTML" hx-confirm="Delete this note?"><button>delete</button></form>
    </div>
  </div>
  {% else %}<p class="muted">No notes yet.</p>{% endfor %}
  <form hx-post="/notes" hx-target="#notes-{{ target_type }}-{{ target_id }}" hx-swap="outerHTML">
    <input type="hidden" name="target_type" value="{{ target_type }}"><input type="hidden" name="target_id" value="{{ target_id }}">
    <textarea name="body" placeholder="Add a note"></textarea><button>Add note</button>
  </form>
</div>
```

`course.html`:

```html
{% extends "base.html" %}
{% block title %}{{ course.short_name }} · {{ student.key | nickname }} · Lakota Sheet{% endblock %}
{% block content %}
<p><a href="/kids/{{ student.key }}">← {{ student.key | nickname }}</a></p>
<h2>{{ course.short_name }} <span class="muted">{{ course.name }}</span></h2>
<div class="cards">
  <div class="card"><h2>Grade</h2>
    {% if grade and grade.current is not none %}<p><span class="big">{{ grade.current }}</span> Canvas current{% if grade.letter %} · {{ grade.letter }}{% endif %}</p>{% endif %}
    {% set h = peer_grade if course.source == 'canvas' else grade %}
    {% if h and h.average is not none %}<p><span class="big">{{ h.average }}</span> HAC average{% if h.last_updated %} <span class="muted">updated {{ h.last_updated }}</span>{% endif %}</p>{% endif %}
    {% if not grade and not peer_grade %}<p class="muted">No grade observed yet.</p>{% endif %}
  </div>
  <div class="card"><h2>Teacher</h2>
    {% if course.teacher %}<p>{{ course.teacher }}</p>{% else %}<p class="muted">Not listed.</p>{% endif %}
    {% if course.teacher_email %}<p><a href="mailto:{{ course.teacher_email }}">{{ course.teacher_email }}</a></p>{% endif %}
    {% if peer %}<p class="muted">Also in {{ peer.source }} as {{ peer.name }}</p>{% endif %}
  </div>
</div>
<h3>Grade history</h3>
<table class="items"><tr><th>Seen</th><th>Canvas current</th><th>Canvas final</th><th>HAC average</th><th>Letter</th></tr>
{% for g in history %}<tr><td>{{ g.started_at | wd_md_time }}</td><td>{{ g.current if g.current is not none else '' }}</td><td>{{ g.final if g.final is not none else '' }}</td><td>{{ g.average if g.average is not none else '' }}</td><td>{{ g.letter or '' }}</td></tr>{% else %}<tr><td colspan="5" class="muted">Nothing yet.</td></tr>{% endfor %}
</table>
<h3>Notes</h3>
{% set target_type = "course" %}{% set target_id = course.id %}
{% include "_notes.html" %}
<h3>Items</h3>
{% set f = {"show": "all", "source": none, "course_id": course.id, "kind": none, "flagged": none, "sort": "due"} %}
{% include "_item_rows.html" %}
{% endblock %}
```

The teacher's email: `courses` has no email column (Plan A stored only `teacher`). The fixture and the test expect the address on the course page. Add it in this task: `ALTER` is not available (schema v1 is redefined in place until Plan B ships: no production database exists, per Plan A's ruling), so add `teacher_email TEXT` to the `courses` DDL in `db.py`, write it in `ingest._upsert_course` from the first staff entry's `email`, and extend `test_web_ingest.py`'s course assertion with the email. Keep `SCHEMA_VERSION = 1`.

- [ ] **Step 5: Run, then full suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_pages.py tests/test_web_app.py tests/test_web_ingest.py`
Expected: PASS. Then the full suite.

```bash
git add lakota_grades/web tests/test_web_pages.py tests/test_web_ingest.py
git commit -m "web: Dashboard and Kid pages; notes and the flag menu; course page

Closes #14

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The Reconcile page (issue #15)

**Files:**
- Create: `lakota_grades/web/routes/reconcile.py`, `templates/reconcile.html`, `templates/_case_group.html`, `tests/test_web_reconcile_page.py`
- Modify: `lakota_grades/web/app.py` (include the router)

**Interfaces:**
- Consumes: `reconcile.cases`, `reconcile.KINDS`, `stores.items.one`/`list_items`, Task 4's flag endpoint (the quick actions post to `/items/{id}/flag` and target the group).
- Produces: `GET /reconcile?kid=<key>&kind=<kind>`; `reconcile.grouped(conn, student, *, rules, now) -> [(ItemView, [Case])]` in `stores/items.py` (name it `with_cases`).

- [ ] **Step 1: Tests**

`tests/test_web_reconcile_page.py`:

```python
"""The Reconcile page: every case, grouped by item, per kid, with quick flags."""
from __future__ import annotations

from tests.web_fixtures import app_for, seed


def test_reconcile_lists_every_case_grouped_by_item(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/reconcile")
    assert r.status_code == 200
    body = r.text
    assert body.index("Alex") < body.index("Sam")
    assert "Quiz 1" in body and "Canvas says MISSING, HAC shows 28" in body
    assert "Essay draft" in body and "Turned in, not graded yet" in body
    assert "Lab notebook" in body and "Paper work with no grade" in body
    assert "Participation" in body and "Only HAC lists this" in body
    assert "Homework 4" in body and "No longer earns credit" in body
    assert body.count("Quiz 1") == 1                                # one group per item, however many reasons
    assert "disagree" in body and "past credit" in body            # kind labels
    assert 'hx-post="/items/' in body and 'value="done"' in body   # quick flags


def test_reconcile_filters_by_kid_and_kind(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.get("/reconcile?kid=Sam")
    assert "Sam" in r.text and "Quiz 1" not in r.text
    r = c.get("/reconcile?kind=past_credit")
    assert "Homework 4" in r.text and "Quiz 1" not in r.text
    assert c.get("/reconcile?kind=bogus").status_code == 200        # an unknown kind shows everything


def test_reconcile_summary_counts_and_empty_state(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reconcile").text
    assert "disagree 1" in body and "past credit 1" in body and "submitted ungraded 1" in body and "paper no grade 1" in body
    assert "one source 5" in body     # Participation, Lab notebook, Homework 4, Cell diagram, Safety quiz: each has a HAC twin course with no row
    from lakota_grades.web import db
    from lakota_grades.web.stores import flags
    conn = db.open_db(tmp_path)
    for name in ("Quiz 1", "Essay draft", "Lab notebook", "Participation", "Homework 4"):
        iid = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
        flags.set_flag(conn, iid, "ignore", now="2026-09-15T14:30:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/reconcile?kid=Alex").text
    assert "Nothing to reconcile" in body
```

Note the second half of that last test: an `ignore` flag hides `past_credit` (rule 5 requires no handled flag) but rules 1 to 4 do not look at flags, so Quiz 1's `disagree` would still show. Decide the page's rule and encode it: **the Reconcile page hides items with a handled flag** (the parent has ruled; the Kid page with `show=all` still shows them). Implement that in `with_cases` (skip views whose `handled` is true) and keep the test as written.

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_reconcile_page.py`
Expected: FAIL (404).

- [ ] **Step 2: `with_cases` in `stores/items.py`**

```python
def with_cases(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules,
               kind: str | None = None) -> list[tuple[ItemView, list[reconcile.Case]]]:
    """Every live item that carries at least one reconciliation case, with its cases, for the
    Reconcile page. Items the parent has already handled (done / excused / ignore) are left out:
    the page is for open questions, and the Kid page's `show=all` still lists them."""
    by_item: dict[int, list[reconcile.Case]] = {}
    for case in reconcile.cases(conn, student["id"], rules=rules, now=now):
        if kind is None or case.kind == kind:
            by_item.setdefault(case.item_id, []).append(case)
    views = {v.id: v for v in _views(conn, student, now=now, rules=rules) if v.id in by_item and not v.handled}
    out = [(views[i], cs) for i, cs in by_item.items() if i in views]
    return sorted(out, key=lambda pair: _sort_key("due")(pair[0]))
```

- [ ] **Step 3: Route and templates**

`routes/reconcile.py`:

```python
"""The Reconcile page: what the sources and the parent's flags do not agree on, per kid."""
from __future__ import annotations

import sqlite3
from collections import Counter

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ..stores import items, students
from .. import reconcile

router = APIRouter()


@router.get("/reconcile")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    q = request.query_params
    kid, kind = q.get("kid") or None, q.get("kind") or None
    if kind not in reconcile.KINDS:
        kind = None
    now, rules = state.now(), state.rules()
    kids = [s for s in students.visible(conn) if kid is None or s["key"] == kid]
    groups = [(s, items.with_cases(conn, s, now=now, rules=rules, kind=kind)) for s in kids]
    counts: Counter = Counter()
    for _, pairs in groups:
        for _, cases in pairs:
            counts.update(c.kind for c in cases)
    return render(request, conn, "reconcile.html", current="reconcile", groups=groups, kid=kid, kind=kind,
                  counts=[(k, counts.get(k, 0)) for k in reconcile.KINDS], KINDS=reconcile.KINDS)
```

`reconcile.html`:

```html
{% extends "base.html" %}
{% block title %}Reconcile · Lakota Sheet{% endblock %}
{% block content %}
<h2>Reconcile</h2>
<p class="muted">Where Canvas, Home Access Center and your own flags do not agree. Flag an item and it leaves this page.</p>
<div class="filters">
  <span>Kid:</span> <a href="/reconcile{{ ('?kind=' ~ kind) if kind else '' }}" class="badge">all</a>
  {% for s in students %}<a href="/reconcile?kid={{ s.key }}{{ ('&kind=' ~ kind) if kind else '' }}" class="badge">{{ s.key | nickname }}</a>{% endfor %}
  <span>Kind:</span>
  {% for k, n in counts %}<a href="/reconcile?kind={{ k }}{{ ('&kid=' ~ kid) if kid else '' }}" class="badge {{ 'current' if kind == k }}">{{ k.replace('_', ' ') }} {{ n }}</a>{% endfor %}
</div>
{% block partial %}
{% for s, pairs in groups %}
<h3>{{ s.key | nickname }}</h3>
{% for item, cases in pairs %}
{% include "_case_group.html" %}
{% else %}
<p class="muted">Nothing to reconcile for {{ s.key | nickname }}.</p>
{% endfor %}
{% else %}
<p class="muted">Nothing to reconcile.</p>
{% endfor %}
{% endblock %}
{% endblock %}
```

`_case_group.html`:

```html
<div class="card case {{ cases[0].kind }}" id="group-{{ item.id }}">
  <h2><a href="#detail-{{ item.id }}" hx-get="/items/{{ item.id }}" hx-target="#group-detail-{{ item.id }}">{{ item.name }}</a>
      <span class="muted">· {{ item.course_short }}{% if item.due %} · due {{ item.due | md }}{% endif %} · {{ item.status }}</span></h2>
  <ul>{% for c in cases %}<li><strong>{{ c.kind.replace('_', ' ') }}</strong>: {{ c.reason }}</li>{% endfor %}</ul>
  <form class="actions" hx-post="/items/{{ item.id }}/flag" hx-target="#group-{{ item.id }}" hx-swap="outerHTML">
    <input name="text" placeholder="why (optional)">
    {% for f in ("done", "excused", "ignore", "follow_up", "ask_teacher") %}<button name="flag" value="{{ f }}">{{ f.replace('_', ' ') }}</button>{% endfor %}
  </form>
  <div id="group-detail-{{ item.id }}"></div>
</div>
```

The quick-flag form targets the group and swaps `outerHTML` with the flag endpoint's `_item_detail.html` response: after a `done`/`excused`/`ignore` the group is replaced by the detail card saying "Marked done", which is the right feedback; a page reload drops it. Good enough for this plan; part 2 does not change it.

Include the router in `create_app` (`from .routes import reconcile as reconcile_routes`; add `reconcile_routes.router` to the loop).

- [ ] **Step 4: Run, full suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_reconcile_page.py` then the full suite.
Expected: PASS.

```bash
git add lakota_grades/web tests/test_web_reconcile_page.py
git commit -m "web: the Reconcile page, cases grouped by item with quick flags

Closes #15

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Done when

- `lakota-grades web` on this machine opens `http://127.0.0.1:8433/` showing the Dashboard with the header, one card per kid, and the printed-today card; `/kids/Alex` lists open items, filters swap the table in place, a row expands to sources, cases, notes and the flag menu; `/reconcile` groups every case by item.
- A second `lakota-grades web` opens the browser at the first and exits 0; `web.lock` disappears when the server stops.
- The spike files are gone, the Task 1 outcome is recorded above, and `test_packaging.py` pins their absence.
- Full suite green locally and in CI on both runners; no warnings.
- Not in this plan (part 2): Refresh now and any job, Settings, Diagnostics, Runs page, the service, the Windows entry point and installer, deleting `lakota_grades/app/`.


# Web App Plan B (part 2 of 2): Jobs, Settings, Service, and Retiring the Window

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the browser app self-sufficient: refresh, preview, print, diagnostics and test-login run from the page with live progress; the Runs, Settings and Diagnostics pages replace the tkinter window; the server runs as an always-on user service on Linux and a logon task on Windows; the Windows exe, installer and smoke test move to the browser app; `lakota_grades/app/` is deleted.

**Architecture:** One worker thread inside the server (`web/jobs.py`) runs one job at a time, using the runner's `run.lock` so a scheduled CLI run and a button press never overlap; progress lines stream to the page over server-sent events. The window's action functions move to `web/actions.py` unchanged in spirit (validate, save, test login, preview, print, doctor) and gain the `[web]` fields and the in-page editors. `host/service.py` is the fifth host adapter (Linux systemd user unit, Windows logon task) with the same injected-`run` tests as the others. `web/__main__.py` becomes the frozen entry point: no arguments makes sure the server is running and opens the browser.

**Tech Stack:** Python 3.12, FastAPI/uvicorn/Jinja2/htmx from part 1, `threading` + `queue`, `sse` via `StreamingResponse` and the browser's `EventSource`, `systemctl --user` on Linux, `schtasks` on Windows, PyInstaller + Inno Setup as in Plan 3.

**Spec:** `docs/superpowers/specs/2026-09-15-lakota-web-app-design.md`, sections 2, 3, 5 (Runs, Settings, Diagnostics), 8, 9, 10, 11, 12, 13.B, 15 (risks 3 and 4). GitHub milestone "Web app B: Server", issues #16 to #19; each task names its issue and closes it in the commit message. Issues #31 and #32 list residuals from Plans A and B1; the ones this plan closes are named in their task.

## Global Constraints

- One job at a time. A job kind is one of `refresh`, `preview`, `print`, `doctor`, `login`. Submitting while a job runs answers "busy" (HTTP 409 with the current job partial), never queues. `refresh`, `preview` and `print` hold `<home>/run.lock` (the runner's lock; `runner.Lock`, public in this plan) so a CLI run in progress makes the job FAIL with "already running", and vice versa.
- Every run writes a `runs` row: `preview`/`print` through `runner.run(trigger="web")` as today; `refresh` through `stores.runs.record(...)` with `report_key = "refresh"`. `doctor` and `login` are not runs and write nothing to `runs`.
- Progress lines are the runner's `echo` lines and the `lakota` loggers' INFO records (via `actions.forward_logs`), in order, each at most 300 characters; nothing a job logs ever contains a credential (`actions` already guarantees this for login).
- Settings: the OneLogin password field is accepted only when the request's client address is loopback (`127.0.0.1` or `::1`); from any other address the field is rendered as "set on this computer" and a posted password is a 400. Everything else on Settings works from the LAN. `config.toml` is written only by `actions.save` and `actions.save_editable`.
- The server re-reads settings after a successful save (`AppState.reload()`), so the next job and the next page use them; a changed `[web]` host/port takes effect on the next server start and the page says so.
- Always-on server: Linux `~/.config/systemd/user/lakota-web.service` (`Restart=on-failure`, `WantedBy=default.target`), managed by `lakota-grades service install|remove|show`; Windows logon task "Lakota Sheet - web" running `LakotaSheet.exe web --no-browser`, registered by the installer's `[Run]` step and removed by `[UninstallRun]`. Tony's hand-written units keep their names and are untouched (the unit this plan writes is `lakota-web.service`, a new name).
- `LakotaSheet.exe` with no arguments: if `http://127.0.0.1:<port>/health` answers as this app, open the browser; otherwise start `LakotaSheet.exe web --no-browser` detached and open the browser once it answers. `LAKOTA_WEB_NO_BROWSER=1` suppresses the browser (the smoke test). `lakota-grades web` stays the foreground server.
- Deleted at the end: `lakota_grades/app/` (actions, gui, `__main__`), `tests/test_app_gui.py`, `tests/test_app_main.py`, the `app` CLI command and every `tkinter`/`python3-tk` mention in docs. `tests/test_app_actions.py` moves to `tests/test_web_actions.py` with its tests intact.
- The full suite (`env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`, 288 passed at the start of this plan) stays green on Linux and in CI on both runners; the Windows build (`build.ps1` + `smoke.ps1`) is verified once on the runner before this plan merges, using a temporary push trigger on `release.yml` as Plan 3 did, removed before the final commit.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` and `Closes #<issue>` on its own line.

## What part 1 left (read before any task)

| Module | You use |
|---|---|
| `web/app.py` | `create_app(settings)`, `AppState(home, settings, tz, started_at, clock, extra)` with `rules()`, `now()`; `extra["env"]` (the Jinja overlay), `extra["warnings"]`; `get_state`, `get_db`, `Db`, `State`, `render`, `render_partial`, `is_htmx`, `page_context`; the same-origin middleware; the 404/validation handlers |
| `web/server.py` | `run(settings, *, host, port, open_browser, serve, opener, answers, wait_and_open)`, `port_answers(host, port)`, `_wait_and_open(url, opener, *, answers, tries, interval)`, `WebLock`, `_serve(app, host, port)` |
| `web/stores/runs.py` | `latest`, `recent(conn, limit)`, `printed_on(conn, day)` |
| `web/stores/students.py`, `items.py` | unchanged |
| `web/templates/base.html`, `_header.html` | the rail (add Runs, Settings, Diagnostics links) and the header (add the running-job badge) |
| `web/static/app.js` | one listener; this plan adds the `EventSource` helper |
| `runner.py` | `run(report_key, opts, settings, *, now, refresh, print_pdf, toast, echo) -> int`, `RunOptions(dry_run, force, reprint, date, kid, no_refresh, printer, options, notify, trigger)`, `LOG_NAME`, `LOCK_NAME`, `SKIP_SEED`, `_Lock` (becomes `Lock`), `_record_run` (stays private; the runs store gets its own `record`) |
| `app/actions.py` (moves) | `FormValues`, `load_form`, `validate`, `save(form, *, home, log, credstore, scheduling) -> SaveResult`, `test_login(*, home, log, settings, check, now) -> LoginResult`, `preview(*, home, log, settings, run, opener, today) -> Path|None`, `print_now(*, home, log, settings, run) -> int`, `status_line(home, describe)`, `open_editable`, `about_text`, `run_doctor(*, home, log, settings, run) -> bool`, `forward_logs(log)`, constants `REPORT_KEY`, `LOGIN_STAMP`, `APP_LOG`, `CONFIG_NAME`, `MAX_DAYS`, `EDITABLE` |
| `app/__main__.py` (moves) | `frozen_environment`, `setup_logging(home, stderr)`, `TERMINAL_ONLY`, `main(argv)` |
| `doctor.py` | `PROBES` list of `(name, probe)`, `checks`, `run(settings, home, *, probes) -> (report, ok)`, `REPORT_NAME` |
| `host/` | `scheduling.command_for(key)`, `scheduling.install/remove/describe`, `scheduling_windows.render_task_xml` and `task.xml`, `credentials.write/read_username`, `NotSupported`, `SchedulingError`, `ScheduleInfo`, `IS_WINDOWS`, `CREATE_NO_WINDOW` |
| `collector.py` | `collect(settings, include_hac=True, include_canvas=True, kids_filter=None) -> dict` (the snapshot; also written to disk), `load_snapshot(settings)` |
| `web/ingest.py` | `record(conn, snapshot, *, tz, now=None) -> IngestResult` |
| `config.py` | `Settings`, `load_settings()`, `settings_from_doc`, `load_config_doc`, `save_config_doc`, `WEEKDAYS`, `_validate_report_time`, `DEFAULT_HOME` |
| packaging | `packaging/windows/LakotaSheet.spec`, `installer.iss`, `smoke.ps1`, `build.ps1`; `.github/workflows/release.yml`; `tests/test_packaging.py` pins them |

## File map

| Path | Responsibility |
|---|---|
| `lakota_grades/web/jobs.py` (new) | `Job`, `Worker`: one thread, one job at a time, progress lines, SSE generator |
| `lakota_grades/web/actions.py` (moved from `app/actions.py`, modified) | the page actions: form load/validate/save (+ `[web]`), test login, preview, print, refresh, doctor, editors |
| `lakota_grades/web/routes/jobs.py`, `runs.py`, `settings.py`, `diagnostics.py` (new) | routers |
| `lakota_grades/web/templates/_job.html`, `runs.html`, `settings.html`, `_settings_files.html`, `diagnostics.html` (new); `base.html`, `_header.html`, `dashboard.html` (modify) | |
| `lakota_grades/web/static/app.js` (modify) | the `EventSource` helper |
| `lakota_grades/web/stores/runs.py` (modify) | `record`, `by_id` |
| `lakota_grades/runner.py` (modify) | `_Lock` → `Lock` |
| `lakota_grades/web/app.py` (modify) | `AppState.reload()`, `AppState.jobs`, routers, `page_context["job"]` |
| `lakota_grades/host/service.py`, `service_linux.py`, `service_windows.py`, `logon-task.xml` (new) | the always-on server adapter |
| `lakota_grades/doctor.py` (modify) | `web server` probe |
| `lakota_grades/cli.py` (modify) | `service` command; `app` command removed |
| `lakota_grades/web/__main__.py` (new, from `app/__main__.py`) | frozen entry point |
| `packaging/windows/LakotaSheet.spec`, `installer.iss`, `smoke.ps1` (modify); `README.md`, `docs/windows.md` (modify) | |
| `tests/test_web_jobs.py`, `test_web_runs_page.py`, `test_web_settings_page.py`, `test_web_diagnostics_page.py`, `test_host_service.py`, `test_web_main.py` (new); `tests/test_web_actions.py` (moved from `test_app_actions.py`); `tests/test_doctor.py`, `test_packaging.py`, `test_web_app.py` (modify); `tests/test_app_gui.py`, `test_app_main.py` (deleted) | |

---

### Task 1: `web/jobs.py`, the SSE endpoint, and "Refresh now" (issue #16, part 1)

**Files:**
- Create: `lakota_grades/web/jobs.py`, `lakota_grades/web/routes/jobs.py`, `lakota_grades/web/templates/_job.html`, `tests/test_web_jobs.py`
- Modify: `lakota_grades/runner.py` (`_Lock` → `Lock`, keep `_Lock = Lock` for one release), `lakota_grades/web/app.py` (`AppState.jobs`, `page_context["job"]`, router), `lakota_grades/web/stores/runs.py` (`record`), `lakota_grades/web/templates/_header.html`, `dashboard.html`, `lakota_grades/web/static/app.js`
- Move: `lakota_grades/app/actions.py` → `lakota_grades/web/actions.py` (with `tests/test_app_actions.py` → `tests/test_web_actions.py`); keep `lakota_grades/app/actions.py` as a two-line re-export shim (`from ..web.actions import *  # noqa`) until Task 6 deletes `app/`, so `app/gui.py` and `app/__main__.py` keep importing.

**Interfaces:**
- Consumes: `actions.preview/print_now/run_doctor/test_login/forward_logs`, `collector.collect`, `ingest.record`, `runner.Lock`, `runner.LOCK_NAME`, `db.open_db`, `db.now_iso`.
- Produces:
  - `runner.Lock(path)` (`acquire() -> bool`, `release()`, `held`)
  - `stores.runs.record(conn, report_key, started, finished, trigger, outcome, message, pdf_path=None, job_ref=None) -> int` and `stores.runs.by_id(conn, run_id) -> Row | None`
  - `actions.refresh(*, home, log, settings, collect=None, now=None) -> RefreshResult(ok, message, refresh_id)` — collects, ingests, records a `runs` row (`report_key="refresh"`, `trigger="web"`); takes `runner.Lock`; FAIL (not an exception) when the lock is held or collect raises
  - `jobs.KINDS = ("refresh", "preview", "print", "doctor", "login")`
  - `jobs.Job(id, kind, started_at, finished_at=None, outcome=None, message="", lines=[], pdf=None)`; `Job.done -> bool`
  - `jobs.Worker(state, *, actions=None)`; `Worker.current: Job | None`, `Worker.last: Job | None`, `Worker.submit(kind, **params) -> Job | None` (None when busy), `Worker.start()` (daemon thread), `Worker.run_pending()` (tests: run the queued job on the calling thread), `Worker.get(job_id) -> Job | None`, `Worker.events(job_id) -> Iterator[str]` (SSE frames: `data: <line>\n\n` per line as they arrive, then `event: done\ndata: <outcome>\n\n`)
  - routes: `POST /jobs/{kind}` (form params: `date` for print) → `_job.html` (200 started, 409 busy); `GET /jobs/{id}` → `_job.html`; `GET /jobs/{id}/events` → `text/event-stream`
  - `AppState.jobs: Worker | None` (set by `create_app(..., worker=True)`; `server.run` passes `worker=True`; tests construct with `worker=False` and attach a `Worker` themselves or use `app_for(..., worker=True)` — see the fixture change below), `page_context["job"]` = `state.jobs.current` when running

- [ ] **Step 1: Move `actions.py` (mechanical)**

```bash
git mv lakota_grades/app/actions.py lakota_grades/web/actions.py
git mv tests/test_app_actions.py tests/test_web_actions.py
```

In `web/actions.py`: change relative imports (`from .. import config, host, late_rules, runner` stays valid from `web/`; `from ..host import ...` likewise). Change the docstring's first line to "What the pages' buttons do. Plain functions, no web framework, every side effect behind an injectable parameter so the whole module is tested with fakes." In `preview`, make `opener` default to a no-op (`opener = opener or (lambda p: None)`) — the browser links the PDF, nothing opens a viewer on the server. In `tests/test_web_actions.py` change `from lakota_grades.app import actions` to `from lakota_grades.web import actions`; the preview test that asserts the opener was called must pass an explicit fake opener (it already does if it asserts on it; otherwise assert the returned path). Create `lakota_grades/app/actions.py` as the shim:

```python
"""Deleted in Plan B part 2, Task 6. Until then the window imports from here."""
from ..web.actions import *  # noqa: F401,F403
from ..web.actions import _settings_for, _table, _whole_number  # noqa: F401
```

(`import *` skips underscored names; add to that second line whatever else `app/gui.py` and `app/__main__.py` import from `actions` — `grep -n "actions\.\|from .actions" lakota_grades/app/gui.py lakota_grades/app/__main__.py` lists them — so the window and its tests keep passing until Task 6 deletes them.)

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_actions.py tests/test_app_gui.py tests/test_app_main.py`
Expected: PASS.

- [ ] **Step 2: `runner.Lock` and `runs.record`**

In `runner.py` rename `class _Lock` to `class Lock` and add `_Lock = Lock` after it (one release of compatibility; nothing else in the tree uses `_Lock` — `grep` to confirm and update `runner.run`'s own `lock = _Lock(...)` to `Lock`).

Append to `web/stores/runs.py`:

```python
def record(conn: sqlite3.Connection, report_key: str, started: str, finished: str, trigger: str, outcome: str,
           message: str, pdf_path: str | None = None, job_ref: str | None = None) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path, job_ref) VALUES (?,?,?,?,?,?,?,?)",
            (report_key, started, finished, trigger, outcome, message[:500], pdf_path, job_ref))
        return cur.lastrowid


def by_id(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
```

- [ ] **Step 3: Tests for `actions.refresh` and the worker**

`tests/test_web_jobs.py`:

```python
"""The jobs worker: one at a time, progress lines, the runner's lock, SSE frames, and the routes."""
from __future__ import annotations

from datetime import datetime

import pytest

from lakota_grades import config, runner
from lakota_grades.web import actions, db, jobs
from lakota_grades.web import app as webapp
from lakota_grades.web.stores import runs
from tests.web_fixtures import NOW, TZ, app_for, seed, snapshot


def _settings(home):
    return config.Settings(home=home)


def test_refresh_collects_ingests_and_records_a_run(tmp_path):
    lines = []
    r = actions.refresh(home=tmp_path, log=lines.append, settings=_settings(tmp_path), collect=lambda s: snapshot(), now=NOW)
    assert r.ok and r.refresh_id == 1 and "refresh" in r.message.lower()
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 10
    (row,) = runs.recent(conn)
    assert (row["report_key"], row["trigger"], row["outcome"]) == ("refresh", "web", "OK")
    conn.close()
    assert any("ingested" in ln for ln in lines)


def test_refresh_fails_softly_when_the_runner_lock_is_held(tmp_path):
    lock = runner.Lock(tmp_path / runner.LOCK_NAME)
    assert lock.acquire()
    try:
        r = actions.refresh(home=tmp_path, log=lambda s: None, settings=_settings(tmp_path), collect=lambda s: snapshot())
    finally:
        lock.release()
    assert not r.ok and "already running" in r.message
    conn = db.open_db(tmp_path)
    assert runs.recent(conn) == [] or runs.recent(conn)[0]["outcome"] == "FAIL"
    conn.close()


def test_refresh_reports_a_collector_error_as_fail_with_a_run_row(tmp_path):
    def boom(s):
        raise RuntimeError("portal timeout")
    r = actions.refresh(home=tmp_path, log=lambda s: None, settings=_settings(tmp_path), collect=boom)
    assert not r.ok and "portal timeout" in r.message
    conn = db.open_db(tmp_path)
    assert runs.recent(conn)[0]["outcome"] == "FAIL"
    conn.close()


class FakeActions:
    """Stand-ins for the five actions; each logs a line and returns what the real one returns."""
    def __init__(self):
        self.calls = []

    def refresh(self, *, home, log, settings):
        self.calls.append("refresh"); log("refreshing"); return actions.RefreshResult(True, "refresh OK", 1)

    def preview(self, *, home, log, settings):
        self.calls.append("preview"); log("building"); return home / "sheets" / "2026-09-15" / "sheet.pdf"

    def print_now(self, *, home, log, settings, date=None):
        self.calls.append(("print", date)); log("printing"); return 0

    def run_doctor(self, *, home, log, settings):
        self.calls.append("doctor"); log("OK    python: 3.12"); return True

    def test_login(self, *, home, log, settings):
        self.calls.append("login"); log("Canvas: OK"); return actions.LoginResult(True, {"Canvas": None}, "Login OK for Canvas.")


def _worker(tmp_path, fake=None):
    s = _settings(tmp_path)
    application = webapp.create_app(s, worker=False)
    w = jobs.Worker(application.state.lakota, actions=fake or FakeActions())
    application.state.lakota.jobs = w
    return application, w


def test_worker_runs_one_job_at_a_time_and_keeps_its_lines(tmp_path):
    application, w = _worker(tmp_path)
    job = w.submit("refresh")
    assert job is not None and job.kind == "refresh" and w.current is job and not job.done
    assert w.submit("doctor") is None                     # busy: refused, not queued
    w.run_pending()
    assert job.done and job.outcome == "OK" and job.lines == ["refreshing", "refresh OK"] and w.current is None and w.last is job
    second = w.submit("doctor")
    w.run_pending()
    assert second.id == job.id + 1 and second.outcome == "OK" and "python" in second.lines[0]


def test_worker_print_passes_the_date_and_maps_rc_to_outcome(tmp_path):
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    job = w.submit("print", date="2026-09-14")
    w.run_pending()
    assert ("print", "2026-09-14") in fake.calls and job.outcome == "OK"
    fake.print_now = lambda **kw: 1
    job = w.submit("print"); w.run_pending()
    assert job.outcome == "FAIL"


def test_worker_turns_an_exception_into_fail_and_frees_the_slot(tmp_path):
    fake = FakeActions()
    def boom(**kw):
        raise RuntimeError("kaboom")
    fake.preview = boom
    application, w = _worker(tmp_path, fake)
    job = w.submit("preview"); w.run_pending()
    assert job.outcome == "FAIL" and "kaboom" in job.message and w.current is None
    assert w.submit("doctor") is not None


def test_unknown_kind_is_rejected(tmp_path):
    application, w = _worker(tmp_path)
    with pytest.raises(ValueError):
        w.submit("dance")


def test_events_replay_the_lines_then_end_with_done(tmp_path):
    application, w = _worker(tmp_path)
    job = w.submit("login"); w.run_pending()
    frames = list(w.events(job.id))
    assert frames == ["data: Canvas: OK\n\n", "data: Login OK for Canvas.\n\n", "event: done\ndata: OK\n\n"]
    assert list(w.events(999)) == ["event: done\ndata: unknown\n\n"]


def test_events_stream_while_a_job_runs(tmp_path):
    """A job on the worker thread: the generator yields lines as they arrive and ends when the job ends."""
    import threading, time
    fake = FakeActions()
    gate = threading.Event()
    def slow(*, home, log, settings):
        log("step 1"); gate.wait(5); log("step 2"); return True
    fake.run_doctor = slow
    application, w = _worker(tmp_path, fake)
    w.start()
    job = w.submit("doctor")
    it = w.events(job.id)
    assert next(it) == "data: step 1\n\n"
    gate.set()
    assert next(it) == "data: step 2\n\n"
    assert next(it).startswith("event: done")
    for _ in range(50):
        if w.current is None: break
        time.sleep(0.05)
    assert w.current is None


def test_routes_start_a_job_answer_busy_and_stream_events(tmp_path):
    from fastapi.testclient import TestClient
    fake = FakeActions()
    application, w = _worker(tmp_path, fake)
    c = TestClient(application)
    r = c.post("/jobs/refresh")
    assert r.status_code == 200 and "Refreshing" in r.text and f'data-sse="/jobs/{w.current.id}/events"' in r.text
    assert c.post("/jobs/doctor").status_code == 409
    assert c.get("/").text.count("Refreshing") >= 1              # the header badge
    w.run_pending()
    r = c.get(f"/jobs/{w.last.id}")
    assert r.status_code == 200 and "OK" in r.text and "refreshing" in r.text and "data-sse" not in r.text
    with c.stream("GET", f"/jobs/{w.last.id}/events") as s:
        body = "".join(s.iter_text())
    assert "data: refreshing" in body and "event: done" in body
    assert c.post("/jobs/dance").status_code == 404
    assert c.get("/jobs/999").status_code == 404


def test_dashboard_offers_refresh_only_when_a_worker_exists(tmp_path):
    seed(tmp_path).close()
    assert 'hx-post="/jobs/refresh"' not in app_for(tmp_path).get("/").text
    application, w = _worker(tmp_path)
    from fastapi.testclient import TestClient
    assert 'hx-post="/jobs/refresh"' in TestClient(application).get("/").text
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_jobs.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 4: `actions.refresh`**

Append to `web/actions.py`:

```python
@dataclass
class RefreshResult:
    ok: bool
    message: str
    refresh_id: int | None


def refresh(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
            collect=None, now: datetime | None = None) -> RefreshResult:
    """Refresh now: pull Canvas and HAC, ingest the snapshot, record the run. Holds the runner's
    lock so a scheduled print in progress is never pulled out from under. Every failure is a
    result, never an exception -- the page shows it."""
    from .. import collector
    from . import db, ingest
    from .stores import runs as runstore
    settings = settings or config.load_settings()
    collect = collect or collector.collect
    tz = ZoneInfo(settings.timezone)
    started = now or datetime.now(tz)
    lock = runner.Lock(home / runner.LOCK_NAME)
    if not lock.acquire():
        log("A run is already in progress (run.lock present); try again in a minute.")
        return RefreshResult(False, "already running (run.lock present); nothing done", None)
    outcome, message, refresh_id = "FAIL", "", None
    try:
        log("Refreshing Canvas + HAC (1-3 minutes)...")
        with forward_logs(log):
            snap = collect(settings)
        bad = {k: v for k, v in (snap.get("sources") or {}).items() if v != "ok"}
        conn = db.open_db(home)
        try:
            r = ingest.record(conn, snap, tz=tz, now=now)
            refresh_id = r.refresh_id
            message = f"refresh {r.refresh_id}: {r.items} new items, {r.observations} changes, {r.grades} grade changes"
            if bad:
                message += "; " + "; ".join(f"{k}: {v}" for k, v in bad.items())
            outcome = "OK" if not bad else "FAIL"
            log(f"ingested {message}")
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001  a failed pull is a result
        message = f"refresh failed: {str(e)[:200]}"
        log(message)
    finally:
        lock.release()
        try:
            conn2 = db.open_db(home)
            try:
                runstore.record(conn2, "refresh", started.isoformat(), datetime.now(tz).isoformat(), "web", outcome, message)
            finally:
                conn2.close()
        except Exception as e:  # noqa: BLE001  the database is a passenger here too
            log(f"WARN could not record the run: {e}")
    return RefreshResult(outcome == "OK", message, refresh_id)
```

Add `from zoneinfo import ZoneInfo` if missing (it is imported already for `test_login`). Note the test `test_refresh_fails_softly_when_the_runner_lock_is_held` allows either no row or a FAIL row: this implementation writes a FAIL row on the lock path too, which is what the spec's "every run writes a row" wants.

- [ ] **Step 5: `web/jobs.py`**

```python
"""One worker thread inside the server: refresh, preview, print, doctor and test login, one at a
time, with progress lines the page streams over server-sent events (spec section 9).

The worker never touches the request's database connection; each action opens its own. A job
that holds the runner's lock (refresh, preview, print) fails cleanly when a scheduled CLI run
holds it first, and the CLI run fails cleanly the other way round -- that is the whole point
of sharing `run.lock`.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

from . import actions as _actions

KINDS = ("refresh", "preview", "print", "doctor", "login")
LABELS = {"refresh": "Refreshing", "preview": "Building today's sheet", "print": "Printing",
          "doctor": "Running diagnostics", "login": "Testing the login"}
MAX_LINE = 300
KEEP = 20                                     # finished jobs kept for /jobs/{id}


@dataclass
class Job:
    id: int
    kind: str
    started_at: datetime
    params: dict = field(default_factory=dict)
    finished_at: datetime | None = None
    outcome: str | None = None                # OK | FAIL
    message: str = ""
    lines: list[str] = field(default_factory=list)
    pdf: Path | None = None

    @property
    def done(self) -> bool:
        return self.finished_at is not None

    @property
    def label(self) -> str:
        return LABELS[self.kind]


class Worker:
    def __init__(self, state, *, actions=None):
        self.state = state
        self.actions = actions or _actions
        self.current: Job | None = None
        self.last: Job | None = None
        self._jobs: dict[int, Job] = {}
        self._queue: queue.Queue[Job] = queue.Queue(maxsize=1)
        self._cond = threading.Condition()
        self._next_id = 1
        self._thread: threading.Thread | None = None

    # -- submitting ---------------------------------------------------------------------
    def submit(self, kind: str, **params) -> Job | None:
        if kind not in KINDS:
            raise ValueError(f"unknown job kind {kind!r}; one of {', '.join(KINDS)}")
        with self._cond:
            if self.current is not None:
                return None
            job = Job(self._next_id, kind, self.state.now(), params)
            self._next_id += 1
            self._jobs[job.id] = job
            for old in sorted(self._jobs)[:-KEEP]:
                del self._jobs[old]
            self.current = job
        self._queue.put(job)
        return job

    def get(self, job_id: int) -> Job | None:
        return self._jobs.get(job_id)

    # -- running --------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="lakota-jobs", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while True:
            self._run(self._queue.get())

    def run_pending(self) -> None:
        """Tests: run the queued job on this thread."""
        try:
            job = self._queue.get_nowait()
        except queue.Empty:
            return
        self._run(job)

    def _log(self, job: Job):
        def log(line: str) -> None:
            with self._cond:
                job.lines.append(str(line)[:MAX_LINE])
                self._cond.notify_all()
        return log

    def _run(self, job: Job) -> None:
        log = self._log(job)
        settings, home = self.state.settings, self.state.home
        outcome, message = "FAIL", ""
        try:
            if job.kind == "refresh":
                r = self.actions.refresh(home=home, log=log, settings=settings)
                outcome, message = ("OK" if r.ok else "FAIL"), r.message
            elif job.kind == "preview":
                pdf = self.actions.preview(home=home, log=log, settings=settings)
                job.pdf = pdf
                outcome, message = ("OK", f"built {pdf}") if pdf else ("FAIL", "no sheet was built")
            elif job.kind == "print":
                rc = self.actions.print_now(home=home, log=log, settings=settings, date=job.params.get("date"))
                outcome, message = ("OK" if rc == 0 else "FAIL"), (job.lines[-1] if job.lines else "")
            elif job.kind == "doctor":
                ok = self.actions.run_doctor(home=home, log=log, settings=settings)
                outcome, message = ("OK" if ok else "FAIL"), ("All checks passed" if ok else "some checks failed")
            elif job.kind == "login":
                r = self.actions.test_login(home=home, log=log, settings=settings)
                outcome, message = ("OK" if r.ok else "FAIL"), r.message
        except Exception as e:  # noqa: BLE001  a job never takes the worker down
            message = f"{type(e).__name__}: {str(e)[:200]}"
            log(message)
        with self._cond:
            job.outcome, job.message, job.finished_at = outcome, message, self.state.now()
            self.current, self.last = None, job
            self._cond.notify_all()

    # -- streaming --------------------------------------------------------------------------
    def events(self, job_id: int) -> Iterator[str]:
        """SSE frames for one job: each line as it arrives, then `done`. Finished jobs replay."""
        job = self._jobs.get(job_id)
        if job is None:
            yield "event: done\ndata: unknown\n\n"
            return
        sent = 0
        while True:
            with self._cond:
                while sent >= len(job.lines) and not job.done:
                    self._cond.wait(timeout=15)
                    if sent >= len(job.lines) and not job.done:
                        yield ": keep-alive\n\n"
                batch = job.lines[sent:]
                finished = job.done
            for line in batch:
                yield f"data: {line}\n\n"
            sent += len(batch)
            if finished and sent >= len(job.lines):
                yield f"event: done\ndata: {job.outcome}\n\n"
                return
```

Note on `print_now`'s `date` parameter: today `actions.print_now` has no `date`; add `date: str | None = None` to it, passed into `runner.RunOptions(force=True, reprint=True, date=date)`, and extend its test (`test_print_now_forces_a_reprint`) to assert `date` reaches the options.

Note on `test_events_stream_while_a_job_runs`: the `: keep-alive` comment frame is only yielded after a 15 s wait, so the test's `next(it)` calls see data frames; if the test becomes slow, drop the timeout to `wait()` with no timeout and delete the keep-alive branch (uvicorn does not need it on localhost) — pick one and keep the test deterministic.

- [ ] **Step 6: `AppState.jobs`, `reload`, routes, templates**

In `app.py`:
- `AppState` gains `jobs: "Worker | None" = None` (a string annotation; import `Worker` lazily to avoid a cycle) and:

```python
    def reload(self) -> None:
        """Re-read config.toml after Settings saved it (env overrides stay in force when the
        server started from load_settings, because the process environment has not changed)."""
        from .. import config
        if self.home == config.DEFAULT_HOME:
            self.settings = config.load_settings()
        else:
            s = config.Settings(home=self.home)
            config.settings_from_doc(config.load_config_doc(self.home / "config.toml"), s)
            self.settings = s
        self.extra["env"].filters.update(_filters(self))
```

- `create_app(settings, *, home=None, worker: bool = True)`: after the state is built, `if worker: from .jobs import Worker; state.jobs = Worker(state); state.jobs.start()`.
- `page_context` adds `"job": state.jobs.current if state.jobs and state.jobs.current else None` and `"jobs": state.jobs is not None`.
- Routers: add `jobs.router`.
- `tests/web_fixtures.app_for(home, now=NOW, worker=False)` passes `worker=worker` through.

`routes/jobs.py`:

```python
"""Start a job, show it, stream it."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..app import Db, State, render_partial
from .. import jobs as jobmod

router = APIRouter()


def _worker(state) -> jobmod.Worker:
    if state.jobs is None:
        raise HTTPException(404, "no jobs worker in this server")
    return state.jobs


@router.post("/jobs/{kind}")
def start(kind: str, request: Request, date: str | None = Form(None), conn: sqlite3.Connection = Db, state=State):
    if kind not in jobmod.KINDS:
        raise HTTPException(404, f"no job kind {kind!r}")
    w = _worker(state)
    job = w.submit(kind, **({"date": date} if date else {}))
    if job is None:
        r = render_partial(request, conn, "_job.html", job=w.current, busy=True)
        r.status_code = 409
        return r
    return render_partial(request, conn, "_job.html", job=job, busy=False)


@router.get("/jobs/{job_id}")
def show(job_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    job = _worker(state).get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return render_partial(request, conn, "_job.html", job=job, busy=False)


@router.get("/jobs/{job_id}/events")
def events(job_id: int, state=State):
    w = _worker(state)
    return StreamingResponse(w.events(job_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
```

`templates/_job.html`:

```html
<div class="card job" id="job">
  {% if busy %}<p class="warn">Busy: {{ job.label }} (job {{ job.id }}) is still running.</p>{% endif %}
  <h2>{{ job.label }} <span class="muted">job {{ job.id }} · started {{ job.started_at | time12 }}</span>
    {% if job.done %}<span class="badge {{ job.outcome }}">{{ job.outcome }}</span>{% endif %}</h2>
  {% if job.done %}
    <p>{{ job.message }}{% if job.pdf %} · <a href="/runs?pdf={{ job.id }}">open the PDF from the Runs page</a>{% endif %}</p>
    <pre class="log">{{ job.lines | join('\n') }}</pre>
  {% else %}
    <pre class="log" data-sse="/jobs/{{ job.id }}/events" data-reload="/jobs/{{ job.id }}">{{ job.lines | join('\n') }}</pre>
  {% endif %}
</div>
```

`_header.html`: after the last-run span add `{% if job %}<span class="badge"><a href="/">{{ job.label }}…</a></span>{% endif %}`.

`dashboard.html`: the "Printed today" card's button block becomes:

```html
{% if jobs %}
<p class="actions">
  <button hx-post="/jobs/refresh" hx-target="#job" hx-swap="outerHTML">Refresh now</button>
  <button hx-post="/jobs/preview" hx-target="#job" hx-swap="outerHTML">Preview today's sheet</button>
  <button hx-post="/jobs/print" hx-target="#job" hx-swap="outerHTML" hx-confirm="Print today's sheet now?">Print now</button>
</p>
<div id="job">{% if job %}{% with busy=false %}{% include "_job.html" %}{% endwith %}{% endif %}</div>
{% endif %}
```

`static/app.js` gains:

```js
// Live job progress: a <pre data-sse=URL data-reload=URL> opens an EventSource, appends each
// line, and when the server says done, fetches the finished job partial over htmx.
function attachSse(root) {
  (root.querySelectorAll ? root.querySelectorAll("[data-sse]") : []).forEach(function (pre) {
    if (pre.dataset.attached) return;
    pre.dataset.attached = "1";
    var es = new EventSource(pre.dataset.sse);
    es.onmessage = function (e) { pre.textContent += (pre.textContent ? "\n" : "") + e.data; pre.scrollTop = pre.scrollHeight; };
    es.addEventListener("done", function () { es.close(); htmx.ajax("GET", pre.dataset.reload, { target: "#job", swap: "outerHTML" }); });
    es.onerror = function () { es.close(); };
  });
}
document.addEventListener("DOMContentLoaded", function () { attachSse(document); });
document.addEventListener("htmx:afterSwap", function (e) { attachSse(e.detail.target); });
```

Add to `app.css`: `pre.log { background: #111; color: #eee; padding: 8px; max-height: 320px; overflow: auto; font-size: 12px; }`.

`server.run`: `create_app(settings)` already defaults `worker=True`; nothing to change, but confirm the worker thread is daemon so Ctrl-C still exits.

- [ ] **Step 7: Run, full suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_jobs.py tests/test_web_actions.py tests/test_web_app.py` then the full suite.
Expected: PASS, pristine.

```bash
git add -A lakota_grades tests
git commit -m "web.jobs: one worker, live progress over SSE, Refresh/Preview/Print from the Dashboard; actions move to web/

Part of #16

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The Runs page, serving PDFs, reprint (issue #16, part 2)

**Files:**
- Create: `lakota_grades/web/routes/runs.py`, `lakota_grades/web/templates/runs.html`, `tests/test_web_runs_page.py`
- Modify: `lakota_grades/web/routes/jobs.py` (`GET /jobs/{id}/pdf`), `templates/_job.html` (link to it), `templates/base.html` (rail: Runs), `lakota_grades/web/app.py` (router)

**Interfaces:**
- Consumes: `stores.runs.recent/by_id`, `jobs.Worker.get`, `AppState.home`, `settings.sheets_archive`.
- Produces: `GET /runs` (`runs.html`, 100 most recent); `GET /runs/{id}/pdf` (FileResponse or 404); `GET /jobs/{id}/pdf`; `app.safe_pdf(state, path: str | None) -> Path | None` (the file exists and resolves under `state.home` or under `settings.sheets_archive`; otherwise None — never serve an arbitrary path).

- [ ] **Step 1: Tests**

`tests/test_web_runs_page.py`:

```python
"""The Runs page: history with outcome, the PDF link, reprint; PDFs are served only from the app's own folders."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lakota_grades.web import app as webapp, db, jobs
from lakota_grades.web.stores import runs
from tests.web_fixtures import app_for, seed
from tests.test_web_jobs import FakeActions


def _rows(home):
    conn = seed(home)
    pdf = home / "sheets" / "2026-09-15" / "sheet.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 fake")
    ids = [
        runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "2p Al=3 Sam=2", str(pdf)),
        runs.record(conn, "refresh", "2026-09-15T13:50:00-04:00", "2026-09-15T13:51:00-04:00", "web", "OK", "refresh 1: 10 new items"),
        runs.record(conn, "open-work", "2026-09-14T14:00:00-04:00", "2026-09-14T14:01:00-04:00", "schedule", "FAIL", "printer offline; PDF kept at /gone.pdf", "/gone.pdf"),
        runs.record(conn, "open-work", "2026-09-13T14:00:00-04:00", "2026-09-13T14:00:01-04:00", "cli", "SKIP", "outside print window"),
    ]
    conn.close()
    return ids, pdf


def test_runs_page_lists_history_newest_first_with_badges_and_links(tmp_path):
    ids, pdf = _rows(tmp_path)
    body = app_for(tmp_path).get("/runs").text
    assert body.index("2p Al=3 Sam=2") < body.index("refresh 1") < body.index("printer offline") < body.index("outside print window")
    assert 'class="badge OK"' in body and 'class="badge FAIL"' in body and 'class="badge SKIP"' in body
    assert f'href="/runs/{ids[0]}/pdf"' in body
    assert f'href="/runs/{ids[2]}/pdf"' not in body            # the file is gone: no link
    assert "Mon 9/14" in body and "schedule" in body and "cli" in body


def test_reprint_button_only_for_printable_ok_runs_when_a_worker_exists(tmp_path):
    ids, pdf = _rows(tmp_path)
    body = app_for(tmp_path).get("/runs").text
    assert 'hx-post="/jobs/print"' not in body                 # no worker: no button
    body = app_for(tmp_path, worker=True).get("/runs").text
    assert body.count('hx-post="/jobs/print"') == 1 and 'value="2026-09-15"' in body


def test_pdf_is_served_from_home_and_refused_elsewhere(tmp_path):
    ids, pdf = _rows(tmp_path)
    c = app_for(tmp_path)
    r = c.get(f"/runs/{ids[0]}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF")
    assert c.get(f"/runs/{ids[2]}/pdf").status_code == 404     # missing file
    assert c.get(f"/runs/{ids[1]}/pdf").status_code == 404     # no pdf on a refresh
    assert c.get("/runs/999/pdf").status_code == 404
    outside = tmp_path.parent / "elsewhere.pdf"
    outside.write_bytes(b"%PDF-1.4 no")
    conn = db.open_db(tmp_path)
    rid = runs.record(conn, "open-work", "2026-09-12T14:00:00-04:00", "2026-09-12T14:01:00-04:00", "cli", "OK", "x", str(outside))
    conn.close()
    assert c.get(f"/runs/{rid}/pdf").status_code == 404          # outside home and the archive


def test_pdf_under_the_archive_folder_is_allowed(tmp_path):
    from lakota_grades import config
    archive = tmp_path / "Drive" / "Sheets"
    archive.mkdir(parents=True)
    f = archive / "2026-09-15 Open Work.pdf"
    f.write_bytes(b"%PDF-1.4 archived")
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    rid = runs.record(conn, "open-work", "2026-09-15T14:00:00-04:00", "2026-09-15T14:01:00-04:00", "cli", "OK", "x", str(f))
    conn.close()
    s = config.Settings(home=tmp_path)
    s.sheets_archive = str(archive)
    assert TestClient(webapp.create_app(s, worker=False)).get(f"/runs/{rid}/pdf").status_code == 200


def test_job_pdf_after_a_preview(tmp_path):
    from lakota_grades import config
    seed(tmp_path).close()
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    fake = FakeActions()
    w = jobs.Worker(application.state.lakota, actions=fake)
    application.state.lakota.jobs = w
    pdf = tmp_path / "sheets" / "2026-09-15" / "sheet.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4 preview")
    c = TestClient(application)
    c.post("/jobs/preview")
    w.run_pending()
    body = c.get(f"/jobs/{w.last.id}").text
    assert f'href="/jobs/{w.last.id}/pdf"' in body
    assert c.get(f"/jobs/{w.last.id}/pdf").status_code == 200
    assert c.get("/jobs/999/pdf").status_code == 404
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_runs_page.py`
Expected: FAIL (404s).

- [ ] **Step 2: Implement**

In `app.py`:

```python
def safe_pdf(state: AppState, path: str | None) -> Path | None:
    """The PDF a run or job produced, only if it is really ours: an existing file under the
    home folder or under the archive folder. Anything else is not served, whatever the row says."""
    if not path:
        return None
    p = Path(path)
    try:
        resolved = p.resolve(strict=True)
    except OSError:
        return None
    roots = [state.home.resolve()]
    if state.settings.sheets_archive:
        roots.append(Path(state.settings.sheets_archive).resolve())
    return resolved if resolved.suffix.lower() == ".pdf" and any(resolved.is_relative_to(r) for r in roots) else None
```

`routes/runs.py`:

```python
"""Run history: what ran, how it went, the PDF, print it again."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..app import Db, State, render, safe_pdf
from ..stores import runs

router = APIRouter()


@router.get("/runs")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    rows = runs.recent(conn, 100)
    pdfs = {r["id"]: safe_pdf(state, r["pdf_path"]) for r in rows}
    return render(request, conn, "runs.html", current="runs", rows=rows, pdfs=pdfs)


@router.get("/runs/{run_id}/pdf")
def pdf(run_id: int, conn: sqlite3.Connection = Db, state=State):
    r = runs.by_id(conn, run_id)
    p = safe_pdf(state, r["pdf_path"]) if r else None
    if p is None:
        raise HTTPException(404, "no PDF for that run")
    return FileResponse(p, media_type="application/pdf", filename=p.name)
```

In `routes/jobs.py` add:

```python
@router.get("/jobs/{job_id}/pdf")
def job_pdf(job_id: int, state=State):
    from fastapi.responses import FileResponse
    from ..app import safe_pdf
    job = _worker(state).get(job_id)
    p = safe_pdf(state, str(job.pdf)) if job and job.pdf else None
    if p is None:
        raise HTTPException(404, "no PDF for that job")
    return FileResponse(p, media_type="application/pdf", filename=p.name)
```

and change `_job.html`'s link to `<a href="/jobs/{{ job.id }}/pdf">open the PDF</a>`.

`templates/runs.html`:

```html
{% extends "base.html" %}
{% block title %}Runs · Lakota Sheet{% endblock %}
{% block content %}
<h2>Runs</h2>
<div id="job">{% if job %}{% with busy=false %}{% include "_job.html" %}{% endwith %}{% endif %}</div>
<table class="items">
  <tr><th>Started</th><th>Report</th><th>How</th><th>Outcome</th><th>Message</th><th>PDF</th><th></th></tr>
  {% for r in rows %}
  <tr>
    <td>{{ r.started_at | wd_md_time }}</td><td>{{ r.report_key }}</td><td class="muted">{{ r.trigger }}</td>
    <td><span class="badge {{ r.outcome }}">{{ r.outcome }}</span></td>
    <td>{{ r.message }}</td>
    <td>{% if pdfs[r.id] %}<a href="/runs/{{ r.id }}/pdf">open</a>{% endif %}</td>
    <td>{% if jobs and r.outcome == 'OK' and pdfs[r.id] and r.report_key != 'refresh' %}
      <form hx-post="/jobs/print" hx-target="#job" hx-swap="outerHTML" hx-confirm="Print the {{ r.started_at | md }} sheet again?">
        <input type="hidden" name="date" value="{{ r.started_at[:10] }}"><button>Reprint</button></form>{% endif %}</td>
  </tr>
  {% else %}<tr><td colspan="7" class="muted">No runs yet.</td></tr>{% endfor %}
</table>
{% endblock %}
```

`base.html` rail: after Reconcile add `<div class="group">App</div><a href="/runs" class="{{ 'current' if current == 'runs' }}">Runs</a>` (Settings and Diagnostics links join in Tasks 3 and 5). Include the router in `create_app`.

- [ ] **Step 3: Run, full suite, commit**

```bash
git add lakota_grades/web tests/test_web_runs_page.py
git commit -m "web: the Runs page, PDFs served only from our own folders, reprint

Closes #16

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The Settings page (issue #17, part 1)

**Files:**
- Create: `lakota_grades/web/routes/settings.py`, `templates/settings.html`, `templates/_settings_files.html`, `tests/test_web_settings_page.py`
- Modify: `lakota_grades/web/actions.py` (`FormValues.port/allow_lan`, `validate`, `save` → `[web]` + `restart_needed`, `read_editable`, `save_editable`, `lan_url`, `print_now(date=)`), `tests/test_web_actions.py`, `templates/base.html` (rail: Settings), `lakota_grades/web/app.py` (router; `loopback(request)`)

**Interfaces:**
- Consumes: `actions.load_form/validate/save/status_line/about_text`, `host.printing.list_printers`, `AppState.reload`, `jobs` (Test login button → `POST /jobs/login`).
- Produces:
  - `actions.FormValues` gains `port: int = 8433`, `allow_lan: bool = False`; `validate` rejects a port outside 1024–65535; `save` writes `[web] port`/`allow_lan` and returns `SaveResult(..., restart_needed: bool)` (True when either changed against the previous file)
  - `actions.read_editable(home, name) -> str` (seeds the file first, never overwrites); `actions.save_editable(home, name, text) -> list[str]` (errors; empty = written); `actions.EDITABLE` unchanged; `actions.open_editable` deleted
  - `actions.lan_url(port, *, probe=None) -> str | None` (this machine's LAN address via a UDP socket "connect" to 10.255.255.255, no packet sent; None when unknown)
  - `app.loopback(request) -> bool` (`request.client.host in ("127.0.0.1", "::1", "testclient")` is NOT what we want — `testclient` is Starlette's default host; tests pass `client=("127.0.0.1", 1)` or `("192.168.1.9", 1)` explicitly, and the function checks only `127.0.0.1`/`::1`)
  - routes: `GET /settings`; `POST /settings` (form fields `username, password, printer, time, days_ahead, overdue_days, nicknames, archive, scheduled, port, allow_lan`) → the page with messages; `POST /settings/files/{name}` (form `text`) → `_settings_files.html`
  - `AppState.extra["credstore"]` / `extra["scheduling"]` when present are passed to `actions.save` (tests inject fakes)

- [ ] **Step 1: `actions` additions, tests first**

Append to `tests/test_web_actions.py`:

```python
def test_form_carries_web_fields_and_validates_the_port(tmp_path):
    (tmp_path / "config.toml").write_text('[web]\nport = 9000\nallow_lan = true\n')
    f = actions.load_form(tmp_path)
    assert (f.port, f.allow_lan) == (9000, True)
    assert actions.load_form(tmp_path / "none").port == 8433
    f = actions.FormValues(username="u", password="p", port=80)
    assert any("1024" in e for e in actions.validate(f, stored=""))
    f.port = 8433
    assert not [e for e in actions.validate(f, stored="") if "port" in e.lower()]


def test_save_writes_web_section_and_flags_a_restart(tmp_path):
    form = actions.FormValues(username="u", password="p", port=9000, allow_lan=True)
    r = actions.save(form, home=tmp_path, log=lambda s: None, credstore=FakeCred(), scheduling=NoScheduling())
    assert r.ok and r.restart_needed
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["web"] == {"port": 9000, "allow_lan": True}
    r = actions.save(form, home=tmp_path, log=lambda s: None, credstore=FakeCred(), scheduling=NoScheduling())
    assert r.ok and not r.restart_needed


def test_editables_seed_validate_and_write(tmp_path):
    text = actions.read_editable(tmp_path, "late-rules.toml")
    assert "[default]" in text and (tmp_path / "late-rules.toml").is_file()
    assert actions.read_editable(tmp_path, "no-print-days.txt").startswith("#")
    errs = actions.save_editable(tmp_path, "late-rules.toml", "[default]\nlate_days = 'seven'\n")
    assert errs and "[default]" in (tmp_path / "late-rules.toml").read_text()      # unchanged
    errs = actions.save_editable(tmp_path, "late-rules.toml", "[default]\nlate_days = 7\ncredit = '50%'\n")
    assert errs == [] and "late_days = 7" in (tmp_path / "late-rules.toml").read_text()
    assert actions.save_editable(tmp_path, "no-print-days.txt", "2026-12-25 Christmas\n") == []
    with pytest.raises(ValueError):
        actions.save_editable(tmp_path, "config.toml", "x")


def test_lan_url_uses_the_probe_and_tolerates_failure():
    assert actions.lan_url(8433, probe=lambda: "192.168.1.5") == "http://192.168.1.5:8433/"
    def boom():
        raise OSError("no network")
    assert actions.lan_url(8433, probe=boom) is None


def test_print_now_passes_the_date(tmp_path):
    seen = {}
    def fake_run(key, opts, settings, echo=None):
        seen["opts"] = opts
        return 0
    actions.print_now(home=tmp_path, log=lambda s: None, settings=config.Settings(home=tmp_path), run=fake_run, date="2026-09-14")
    assert seen["opts"].date == "2026-09-14" and seen["opts"].reprint and seen["opts"].force
```

`FakeCred` and `NoScheduling` already exist in that test file (used by the save tests); if their names differ, use the existing fakes. Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_actions.py -k "web_fields or restart or editables or lan_url or passes_the_date"`. Expected: FAIL.

- [ ] **Step 2: Implement in `actions.py`**

- `FormValues`: add `port: int = 8433`, `allow_lan: bool = False`.
- `load_form`: `port=_whole_number(_table_get(doc,"web","port")) or 8433` — simplest: after `s = _settings_for(home)`, `port=s.web_port, allow_lan=s.web_allow_lan` (`settings_from_doc` already parses `[web]`).
- `validate`: `n = _whole_number(form.port); if n is None or not 1024 <= n <= 65535: errors.append("Port must be a whole number between 1024 and 65535.")`.
- `save`: before writing, `prev = dict(_table(doc, "web"))`; then `web = _table(doc, "web"); web["port"], web["allow_lan"] = int(form.port), bool(form.allow_lan)`; `restart_needed = prev.get("port", 8433) != web["port"] or bool(prev.get("allow_lan", False)) != web["allow_lan"]`; `SaveResult` gains `restart_needed: bool = False`; set it on the success return; append a message "The server address changed; restart Lakota Sheet (or the service) for it to take effect." when true.
- Replace `open_editable` with:

```python
def read_editable(home: Path, name: str) -> str:
    """The file's text, seeding it first if it does not exist (never overwriting)."""
    if name not in EDITABLE:
        raise ValueError(f"not an editable settings file: {name}")
    path = home / name
    if name == "late-rules.toml":
        late_rules.ensure_seed(path)
    elif not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(runner.SKIP_SEED)
    return path.read_text(encoding="utf-8")


def save_editable(home: Path, name: str, text: str) -> list[str]:
    """Validate, then write. Errors mean nothing was written."""
    import tempfile
    if name not in EDITABLE:
        raise ValueError(f"not an editable settings file: {name}")
    if name == "late-rules.toml":
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as tmp:
            tmp.write(text)
        try:
            late_rules.load(Path(tmp.name))
        except late_rules.LateRulesError as e:
            return [str(e)]
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    else:
        runner.parse_skip_days(text)          # never raises; a line it cannot read is ignored, as the runner does
    path = home / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return []


def _lan_probe() -> str:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))      # no packet is sent; the OS picks the outbound address
        return s.getsockname()[0]


def lan_url(port: int, *, probe=None) -> str | None:
    try:
        ip = (probe or _lan_probe)()
    except OSError:
        return None
    return f"http://{ip}:{port}/" if ip and not ip.startswith("127.") else None
```

- `print_now(*, home, log, settings=None, run=None, date=None)`: `RunOptions(force=True, reprint=True, date=date)`.
- Delete `test_open_editable_seeds_then_opens` from the test file (the function is gone) and drop `open_editable` from the shim's needs.

Run the actions tests. Expected: PASS.

- [ ] **Step 3: Page tests**

`tests/test_web_settings_page.py`:

```python
"""Settings: the form round-trips config.toml, the password stays on this machine, the editors validate."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lakota_grades import config
from lakota_grades.host import NotSupported
from lakota_grades.web import app as webapp
from tests.web_fixtures import seed


class FakeCred:
    def __init__(self):
        self.written = []
    def write(self, user, pw):
        self.written.append((user, pw))
    def read_username(self):
        return self.written[-1][0] if self.written else None


class NoScheduling:
    def command_for(self, key):
        return ("exe", "run x", "wd")
    def install(self, *a, **k):
        raise NotSupported("systemd")
    def remove(self, key):
        raise NotSupported("systemd")
    def describe(self, key):
        from lakota_grades.host import ScheduleInfo
        return ScheduleInfo("systemd", False, None, None)


def _client(home, host="127.0.0.1"):
    seed(home).close()
    (home / "config.toml").write_text('[account]\nusername = "parent@example.org"\n[print]\nprinter = "Brother"\n[kids]\nnicknames = { Alex = "Al" }\n')
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.lakota.extra["credstore"] = FakeCred()
    application.state.lakota.extra["scheduling"] = NoScheduling()
    application.state.lakota.extra["printers"] = ["Brother", "Canon"]
    return TestClient(application, client=(host, 12345)), application


FORM = {"username": "parent@example.org", "password": "", "printer": "Canon", "time": "15:30", "days_ahead": "10",
        "overdue_days": "21", "nicknames": "Alex=Al", "archive": "", "port": "8433"}


def test_settings_page_shows_current_values_and_the_password_field_on_loopback(tmp_path):
    c, app = _client(tmp_path)
    body = c.get("/settings").text
    assert 'value="parent@example.org"' in body and 'name="password"' in body and 'type="password"' in body
    assert '<option value="Brother" selected' in body and 'value="Canon"' in body
    assert "Alex=Al" in body and 'name="port"' in body and 'name="allow_lan"' in body
    assert "[default]" in body and 'name="text"' in body                 # the late-rules editor, seeded
    assert 'hx-post="/jobs/login"' not in body                            # no worker: no Test login button
    assert "Lakota Sheet" in body and "MIT" in body                       # about


def test_password_is_set_on_this_computer_only(tmp_path):
    c, app = _client(tmp_path, host="192.168.1.9")
    body = c.get("/settings").text
    assert 'type="password"' not in body and "set on this computer" in body
    r = c.post("/settings", data={**FORM, "password": "hunter2"})
    assert r.status_code == 400 and app.state.lakota.extra["credstore"].written == []
    r = c.post("/settings", data=FORM)                                   # no password: fine from the LAN
    assert r.status_code == 200 and "Settings saved" in r.text


def test_save_round_trips_reloads_settings_and_stores_the_password(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings", data={**FORM, "password": "hunter2", "nicknames": "Alex=Dougie", "scheduled": "on"})
    assert r.status_code == 200 and "Settings saved" in r.text and "Password stored" in r.text
    assert app.state.lakota.extra["credstore"].written == [("parent@example.org", "hunter2")]
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["print"]["printer"] == "Canon" and doc["reports"]["open-work"]["time"] == "15:30" and doc["web"]["port"] == 8433
    assert app.state.lakota.settings.nicknames == {"Alex": "Dougie"}    # reloaded
    assert ">Dougie<" in c.get("/").text                                     # the rail uses the new nickname
    assert "Test login" in r.text                                           # scheduled is on but no login has passed yet: save still ok, the message says so
    (tmp_path / "login-ok.txt").write_text("2026-09-15T14:00:00-04:00")
    r = c.post("/settings", data={**FORM, "scheduled": "on"})
    assert "systemd" in r.text                                              # NotSupported from the fake scheduler, save still ok


def test_invalid_form_shows_errors_and_writes_nothing(tmp_path):
    c, app = _client(tmp_path)
    before = (tmp_path / "config.toml").read_text()
    r = c.post("/settings", data={**FORM, "time": "25:99", "days_ahead": "0", "port": "80"})
    assert r.status_code == 200 and "HH:MM" in r.text and "between 1 and" in r.text and "1024" in r.text
    assert (tmp_path / "config.toml").read_text() == before


def test_changing_the_port_says_restart(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings", data={**FORM, "port": "9000", "allow_lan": "on"})
    assert "restart" in r.text.lower()
    assert "Allow other devices" in r.text                                   # the LAN URL itself depends on this machine's network (lan_url is unit-tested)


def test_editors_validate_and_save(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings/files/late-rules.toml", data={"text": "[default]\nlate_days = 'x'\n"})
    assert r.status_code == 200 and "late-rules" in r.text and "[default]" in (tmp_path / "late-rules.toml").read_text()
    r = c.post("/settings/files/late-rules.toml", data={"text": "[default]\nlate_days = 3\n"})
    assert "Saved" in r.text and "late_days = 3" in (tmp_path / "late-rules.toml").read_text()
    r = c.post("/settings/files/no-print-days.txt", data={"text": "2026-12-25 Christmas\n"})
    assert "Saved" in r.text and "Christmas" in (tmp_path / "no-print-days.txt").read_text()
    assert c.post("/settings/files/config.toml", data={"text": "x"}).status_code == 404
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_web_settings_page.py`
Expected: FAIL (404).

- [ ] **Step 4: Route and templates**

In `app.py`:

```python
LOOPBACK = ("127.0.0.1", "::1")


def loopback(request: Request) -> bool:
    return bool(request.client) and request.client.host in LOOPBACK
```

`routes/settings.py`:

```python
"""Settings: everything config.toml holds, the two editable files, the network toggle."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, loopback, render, render_partial
from .. import actions

router = APIRouter()


def _printers(state) -> list[str]:
    if "printers" in state.extra:
        return state.extra["printers"]
    try:
        from ...host import printing
        return printing.list_printers()
    except Exception:  # noqa: BLE001  a printer list is a convenience, never a failure
        return []


def _page(request, conn, state, form, messages=(), errors=()):
    return render(request, conn, "settings.html", current="settings", form=form, messages=list(messages), errors=list(errors),
                  printers=_printers(state), loopback=loopback(request), status=actions.status_line(state.home),
                  lan_url=actions.lan_url(form.port) if form.allow_lan else None, about=actions.about_text(),
                  files={n: actions.read_editable(state.home, n) for n in sorted(actions.EDITABLE)})


@router.get("/settings")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _page(request, conn, state, actions.load_form(state.home))


@router.post("/settings")
def save(request: Request, username: str = Form(""), password: str = Form(""), printer: str = Form(""), time: str = Form("14:00"),
         days_ahead: str = Form("14"), overdue_days: str = Form("14"), nicknames: str = Form(""), archive: str = Form(""),
         scheduled: str | None = Form(None), port: str = Form("8433"), allow_lan: str | None = Form(None),
         conn: sqlite3.Connection = Db, state=State):
    if password and not loopback(request):
        raise HTTPException(400, "the password can only be set from a browser on this computer")
    form = actions.FormValues(username=username, password=password, printer=printer, time=time, days_ahead=days_ahead,
                              overdue_days=overdue_days, nicknames=nicknames, archive=archive, scheduled=bool(scheduled),
                              port=port, allow_lan=bool(allow_lan))
    lines: list[str] = []
    result = actions.save(form, home=state.home, log=lines.append,
                          credstore=state.extra.get("credstore"), scheduling=state.extra.get("scheduling"))
    if result.ok:
        state.reload()
        form = actions.load_form(state.home)
        return _page(request, conn, state, form, messages=result.messages)
    return _page(request, conn, state, form, errors=result.messages)


@router.post("/settings/files/{name}")
def save_file(name: str, request: Request, text: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    if name not in actions.EDITABLE:
        raise HTTPException(404, "not an editable file")
    errors = actions.save_editable(state.home, name, text)
    return render_partial(request, conn, "_settings_files.html", name=name, text=text if errors else actions.read_editable(state.home, name),
                          errors=errors, saved=not errors)
```

`validate` receives `days_ahead`/`port` as strings from the form; `_whole_number` handles that (it already does for the window's `StringVar`s). `save` casts with `int(...)` only after `validate` passed — keep that order.

`templates/settings.html`:

```html
{% extends "base.html" %}
{% block title %}Settings · Lakota Sheet{% endblock %}
{% block content %}
<h2>Settings</h2>
{% for m in messages %}<p class="ok">{{ m }}</p>{% endfor %}
{% for e in errors %}<p class="warn">{{ e }}</p>{% endfor %}
<form method="post" action="/settings" class="card">
  <p><label>OneLogin username <input name="username" value="{{ form.username }}"></label></p>
  <p>{% if loopback %}<label>OneLogin password <input name="password" type="password" placeholder="leave blank to keep the stored one"></label>
     <span class="muted">stored in this computer's credential store, never in a file</span>
     {% else %}<span class="muted">OneLogin password: set on this computer (open Lakota Sheet on the PC itself to change it).</span>{% endif %}</p>
  <p><label>Printer <select name="printer"><option value="" {{ 'selected' if not form.printer }}>System default</option>
     {% for p in printers %}<option value="{{ p }}" {{ 'selected' if p == form.printer }}>{{ p }}</option>{% endfor %}
     {% if form.printer and form.printer not in printers %}<option value="{{ form.printer }}" selected>{{ form.printer }}</option>{% endif %}</select></label></p>
  <p><label>Print time <input name="time" value="{{ form.time }}" size="5"></label>
     <label>Days ahead <input name="days_ahead" value="{{ form.days_ahead }}" size="3"></label>
     <label>Overdue days <input name="overdue_days" value="{{ form.overdue_days }}" size="3"></label></p>
  <p><label>Nicknames (one First=Nick per line)<br><textarea name="nicknames">{{ form.nicknames }}</textarea></label></p>
  <p><label>Archive folder <input name="archive" value="{{ form.archive }}" size="40"></label></p>
  <p><label><input type="checkbox" name="scheduled" {{ 'checked' if form.scheduled }}> Print the sheet automatically on school days</label>
     <span class="muted">{{ status }}</span></p>
  <p><label>Port <input name="port" value="{{ form.port }}" size="5"></label>
     <label><input type="checkbox" name="allow_lan" {{ 'checked' if form.allow_lan }}> Allow other devices on this network</label>
     {% if lan_url %}<span class="muted">Other devices: <a href="{{ lan_url }}">{{ lan_url }}</a></span>{% endif %}</p>
  <p><button>Save</button>
     {% if jobs %}<button type="button" hx-post="/jobs/login" hx-target="#job" hx-swap="outerHTML">Test login</button>{% endif %}</p>
</form>
<div id="job">{% if job %}{% with busy=false %}{% include "_job.html" %}{% endwith %}{% endif %}</div>
{% for name, text in files.items() %}
<h3>{{ name }}</h3>
{% with errors=[], saved=false %}{% include "_settings_files.html" %}{% endwith %}
{% endfor %}
<h3>About</h3>
<pre class="muted">{{ about }}</pre>
{% endblock %}
```

`templates/_settings_files.html`:

```html
<form class="card" id="file-{{ name | replace('.', '-') }}" hx-post="/settings/files/{{ name }}" hx-target="this" hx-swap="outerHTML">
  {% if saved %}<p class="ok">Saved {{ name }}.</p>{% endif %}
  {% for e in errors %}<p class="warn">{{ e }}</p>{% endfor %}
  <textarea name="text" rows="14">{{ text }}</textarea>
  <p><button>Save {{ name }}</button></p>
</form>
```

Add `.ok { color: var(--ok); }` to `app.css`. Rail: `<a href="/settings" class="{{ 'current' if current == 'settings' }}">Settings</a>`. Include the router. The `Settings` page's `files` loop passes `name`/`text` into the include via the loop variables (Jinja includes see the enclosing context).

Note for `test_save_round_trips...`: `status_line` uses `host.scheduling.describe` by default; on Linux that reports systemd. The test's `NoScheduling` is only passed to `save`; `status_line` may print "not scheduled" from the real Linux adapter, which is fine.

- [ ] **Step 5: Run, full suite, commit**

```bash
git add lakota_grades/web tests/test_web_settings_page.py tests/test_web_actions.py
git commit -m "web: the Settings page; the password stays on this computer; late-rules and no-print-days editors

Part of #17

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: `host/service.py`: the always-on server as a systemd user unit or a Windows logon task; `lakota-grades service` (issue #18)

**Files:**
- Create: `lakota_grades/host/service.py`, `service_linux.py`, `service_windows.py`, `logon-task.xml`, `tests/test_host_service.py`
- Modify: `lakota_grades/cli.py` (`service` command), `pyproject.toml` package-data already covers `host/*.xml`

**Interfaces:**
- Produces:
  - `host.ServiceInfo(managed_by: str, installed: bool, active: bool, detail: str)` (in `host/__init__.py`, beside `ScheduleInfo`)
  - `host.service.SERVICE_NAME = "Lakota Sheet - web"`, `UNIT = "lakota-web"`, `command_for() -> (exe, args, workdir)` (`args = "web --no-browser"` frozen, `"-m lakota_grades.cli web --no-browser"` from source)
  - `host.service.install_service(run=subprocess.run) -> str`, `remove_service(run=...) -> None`, `describe_service(run=...) -> ServiceInfo`
  - `service_linux.unit_text(exe, args, workdir) -> str`, `unit_path(unit_dir=None) -> Path`, `install(exe, args, workdir, run=..., unit_dir=None)`, `remove(run=..., unit_dir=None)`, `describe(run=...)`
  - `service_windows.render_logon_task_xml(name, exe, args, workdir) -> str`, `install(exe, args, workdir, run=...)`, `remove(run=...)`, `describe(run=...)`
  - CLI: `lakota-grades service install|remove|show`

- [ ] **Step 1: Tests**

`tests/test_host_service.py`:

```python
"""The always-on server adapter: unit text and systemctl argv on Linux, task XML and schtasks argv on Windows."""
from __future__ import annotations

import subprocess

import pytest

from lakota_grades.host import service, service_linux, service_windows


def _recorder(results=None):
    calls = []
    results = results or {}
    def run(argv, **kw):
        calls.append(argv)
        rc, out = results.get(tuple(argv[-2:]), (0, ""))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")
    return calls, run


def test_unit_text_is_a_restarting_user_service():
    text = service_linux.unit_text("/opt/venv/bin/python", "-m lakota_grades.cli web --no-browser", "/home/tony")
    assert "[Unit]" in text and "Description=Lakota Sheet web app" in text
    assert "ExecStart=/opt/venv/bin/python -m lakota_grades.cli web --no-browser" in text
    assert "WorkingDirectory=/home/tony" in text and "Restart=on-failure" in text and "RestartSec=5" in text
    assert "WantedBy=default.target" in text


def test_linux_install_writes_the_unit_and_enables_it_now(tmp_path):
    calls, run = _recorder()
    service_linux.install("/py", "-m lakota_grades.cli web --no-browser", "/wd", run=run, unit_dir=tmp_path)
    unit = tmp_path / "lakota-web.service"
    assert unit.is_file() and "ExecStart=/py -m lakota_grades.cli web --no-browser" in unit.read_text()
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "lakota-web.service"]]


def test_linux_remove_disables_and_deletes(tmp_path):
    (tmp_path / "lakota-web.service").write_text("x")
    calls, run = _recorder()
    service_linux.remove(run=run, unit_dir=tmp_path)
    assert not (tmp_path / "lakota-web.service").exists()
    assert calls == [["systemctl", "--user", "disable", "--now", "lakota-web.service"], ["systemctl", "--user", "daemon-reload"]]
    service_linux.remove(run=run, unit_dir=tmp_path)           # a second remove is fine


def test_linux_describe_reads_enabled_and_active():
    calls, run = _recorder({("is-enabled", "lakota-web.service"): (0, "enabled\n"), ("is-active", "lakota-web.service"): (0, "active\n")})
    info = service_linux.describe(run=run)
    assert (info.managed_by, info.installed, info.active) == ("systemd", True, True) and "active" in info.detail
    calls, run = _recorder({("is-enabled", "lakota-web.service"): (1, "disabled\n"), ("is-active", "lakota-web.service"): (3, "inactive\n")})
    info = service_linux.describe(run=run)
    assert (info.installed, info.active) == (False, False)


def test_linux_install_reports_a_systemctl_failure(tmp_path):
    calls, run = _recorder({("enable", "--now"): (1, "")})
    def failing(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus")
    with pytest.raises(service.ServiceError) as e:
        service_linux.install("/py", "x", "/wd", run=failing, unit_dir=tmp_path)
    assert "Failed to connect to bus" in str(e.value)


def test_logon_task_xml_runs_at_logon_and_restarts():
    xml = service_windows.render_logon_task_xml("Lakota Sheet - web", r"C:\App\LakotaSheet.exe", "web --no-browser", r"C:\App")
    assert "<LogonTrigger>" in xml and "<Command>C:\\App\\LakotaSheet.exe</Command>" in xml and "<Arguments>web --no-browser</Arguments>" in xml
    assert "<RestartOnFailure>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml and "InteractiveToken" in xml
    xml2 = service_windows.render_logon_task_xml("Lakota Sheet - web", r"C:\A & B\LakotaSheet.exe", "web --no-browser", r"C:\A & B")
    assert "<Command>C:\\A &amp; B\\LakotaSheet.exe</Command>" in xml2       # escaped


def test_windows_install_creates_and_starts_the_task(tmp_path):
    calls, run = _recorder()
    service_windows.install(r"C:\App\LakotaSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert calls[0][:4] == ["schtasks", "/Create", "/TN", "Lakota Sheet - web"] and "/XML" in calls[0] and "/F" in calls[0]
    assert calls[1] == ["schtasks", "/Run", "/TN", "Lakota Sheet - web"]


def test_windows_remove_ends_then_deletes_and_tolerates_absence():
    calls, run = _recorder()
    service_windows.remove(run=run)
    assert calls == [["schtasks", "/End", "/TN", "Lakota Sheet - web"], ["schtasks", "/Delete", "/TN", "Lakota Sheet - web", "/F"]]
    def missing(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="ERROR: The system cannot find the file specified.")
    service_windows.remove(run=missing)


def test_windows_describe_reads_status():
    out = "TaskName: \\Lakota Sheet - web\nStatus: Running\nNext Run Time: N/A\n"
    calls, run = _recorder({("/FO", "LIST"): (0, out)})
    def query(argv, **kw):
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
    info = service_windows.describe(run=query)
    assert (info.managed_by, info.installed, info.active) == ("task-scheduler", True, True)
    def absent(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="ERROR: The system cannot find the file specified.")
    assert service_windows.describe(run=absent).installed is False


def test_command_for_source_and_frozen(monkeypatch):
    exe, args, wd = service.command_for()
    assert args == "-m lakota_grades.cli web --no-browser"
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\App\LakotaSheet.exe")
    exe, args, wd = service.command_for()
    assert (exe, args, wd) == (r"C:\App\LakotaSheet.exe", "web --no-browser", r"C:\App")


def test_cli_service_show_prints_the_state(capsys, monkeypatch):
    from lakota_grades import cli
    from lakota_grades.host import ServiceInfo
    monkeypatch.setattr(service, "describe_service", lambda: ServiceInfo("systemd", True, True, "enabled, active"))
    with pytest.raises(SystemExit) as e:
        cli.main(["service", "show"])
    assert e.value.code == 0 and "enabled, active" in capsys.readouterr().out
```

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q tests/test_host_service.py`
Expected: FAIL (`ImportError`).

- [ ] **Step 2: Implement**

`host/__init__.py`: add

```python
class ServiceError(RuntimeError):
    """systemctl or schtasks refused; its stderr is in the message."""


@dataclass(frozen=True)
class ServiceInfo:
    managed_by: str                 # "systemd" | "task-scheduler"
    installed: bool
    active: bool
    detail: str
```

`host/service.py`:

```python
"""The always-on web server (spec section 10): a systemd user unit on Linux, a logon task on
Windows. Same shape as the other adapters: the platform picks an implementation at import,
every implementation takes `run=subprocess.run`, and the CLI and installer call these three."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import IS_WINDOWS
from . import ServiceError, ServiceInfo  # noqa: F401  re-exported

SERVICE_NAME = "Lakota Sheet - web"
UNIT = "lakota-web"


def command_for() -> tuple[str, str, str]:
    """(exe, args, workdir) that runs the server in the foreground from this installation."""
    if getattr(sys, "frozen", False):
        return sys.executable, "web --no-browser", str(Path(sys.executable).parent)
    return sys.executable, "-m lakota_grades.cli web --no-browser", str(Path.cwd())


if IS_WINDOWS:
    from . import service_windows as _impl
else:
    from . import service_linux as _impl


def install_service(run=subprocess.run) -> str:
    exe, args, workdir = command_for()
    _impl.install(exe, args, workdir, run=run)
    return f"{exe} {args}"


def remove_service(run=subprocess.run) -> None:
    _impl.remove(run=run)


def describe_service(run=subprocess.run) -> ServiceInfo:
    return _impl.describe(run=run)
```

`host/service_linux.py`:

```python
"""systemd user unit `lakota-web.service`, written and enabled by the app. Tony's hand-written
units keep their own names; this one is new and only ever managed here."""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import ServiceError, ServiceInfo

UNIT_FILE = "lakota-web.service"


def unit_path(unit_dir: Path | None = None) -> Path:
    return (unit_dir or Path.home() / ".config" / "systemd" / "user") / UNIT_FILE


def unit_text(exe: str, args: str, workdir: str) -> str:
    return (
        "[Unit]\nDescription=Lakota Sheet web app\nAfter=network-online.target\n\n"
        f"[Service]\nExecStart={exe} {args}\nWorkingDirectory={workdir}\nRestart=on-failure\nRestartSec=5\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def _systemctl(args: list[str], run) -> subprocess.CompletedProcess:
    return run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=60)


def install(exe: str, args: str, workdir: str, run=subprocess.run, unit_dir: Path | None = None) -> None:
    path = unit_path(unit_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit_text(exe, args, workdir), encoding="utf-8")
    for cmd in (["daemon-reload"], ["enable", "--now", UNIT_FILE]):
        p = _systemctl(cmd, run)
        if p.returncode != 0:
            raise ServiceError(f"systemctl --user {' '.join(cmd)} failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def remove(run=subprocess.run, unit_dir: Path | None = None) -> None:
    _systemctl(["disable", "--now", UNIT_FILE], run)          # absent is fine
    unit_path(unit_dir).unlink(missing_ok=True)
    _systemctl(["daemon-reload"], run)


def describe(run=subprocess.run) -> ServiceInfo:
    enabled = _systemctl(["is-enabled", UNIT_FILE], run)
    active = _systemctl(["is-active", UNIT_FILE], run)
    installed = enabled.returncode == 0
    is_active = (active.stdout or "").strip() == "active"
    detail = f"{(enabled.stdout or 'not installed').strip()}, {(active.stdout or 'inactive').strip()}"
    return ServiceInfo("systemd", installed, is_active, detail)
```

`host/logon-task.xml` (UTF-16 header like `task.xml`; a `LogonTrigger`, no time limit, restart on failure):

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{description}</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Enabled>true</Enabled></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author"><Exec><Command>{exe}</Command><Arguments>{args}</Arguments><WorkingDirectory>{workdir}</WorkingDirectory></Exec></Actions>
</Task>
```

`host/service_windows.py`:

```python
"""Logon task "Lakota Sheet - web": Task Scheduler starts the server when the user signs in
and restarts it if it dies. Registered by the installer, removed by the uninstaller."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from importlib import resources
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW, ServiceError, ServiceInfo

NAME = "Lakota Sheet - web"
_NOT_FOUND = "cannot find the file"


def render_logon_task_xml(name: str, exe: str, args: str, workdir: str) -> str:
    template = resources.files("lakota_grades.host").joinpath("logon-task.xml").read_text(encoding="utf-8")
    return (template.replace("{description}", escape("Lakota Sheet: the browser app's server"))
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))


def _schtasks(cmd: list[str], run) -> subprocess.CompletedProcess:
    return run(["schtasks", *cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=60)


def install(exe: str, args: str, workdir: str, run=subprocess.run) -> None:
    xml = render_logon_task_xml(NAME, exe, args, workdir)
    fd, path = tempfile.mkstemp(prefix="lakota-web-", suffix=".xml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))
        p = _schtasks(["/Create", "/TN", NAME, "/XML", path, "/F"], run)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if p.returncode != 0:
        raise ServiceError(f"schtasks /Create failed: {(p.stderr or p.stdout or '').strip()[:300]}")
    _schtasks(["/Run", "/TN", NAME], run)                       # start it now; the trigger covers the next logon


def remove(run=subprocess.run) -> None:
    _schtasks(["/End", "/TN", NAME], run)                       # stop a running server; absent is fine
    p = _schtasks(["/Delete", "/TN", NAME, "/F"], run)
    if p.returncode != 0 and _NOT_FOUND not in (p.stderr or ""):
        raise ServiceError(f"schtasks /Delete failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def describe(run=subprocess.run) -> ServiceInfo:
    p = _schtasks(["/Query", "/TN", NAME, "/FO", "LIST", "/V"], run)
    if p.returncode != 0:
        return ServiceInfo("task-scheduler", False, False, "not installed")
    fields = {}
    for line in (p.stdout or "").splitlines():
        m = re.match(r"^([A-Za-z ]+):\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1).strip(), m.group(2))
    status = fields.get("Status", "")
    return ServiceInfo("task-scheduler", True, status.lower() == "running", f"logon task {status or 'installed'}")
```

`cli.py`:

```python
def cmd_service(args) -> int:
    from .host import ServiceError, service
    try:
        if args.action == "install":
            print(f"Installed {service.SERVICE_NAME}: {service.install_service()}")
        elif args.action == "remove":
            service.remove_service()
            print(f"Removed {service.SERVICE_NAME}")
        info = service.describe_service()
        print(f"{service.SERVICE_NAME}: {info.detail} (managed by {info.managed_by})")
        return 0
    except ServiceError as e:
        print(str(e), file=sys.stderr)
        return 1
```

and the parser: `sv = sub.add_parser("service", help="install, remove or show the always-on web server (systemd user unit / Windows logon task)"); sv.add_argument("action", choices=["install", "remove", "show"]); sv.set_defaults(fn=cmd_service)`. Update the module docstring's command list.

- [ ] **Step 3: Run, full suite, commit**

```bash
git add lakota_grades/host lakota_grades/cli.py tests/test_host_service.py
git commit -m "host.service: the always-on server as a systemd user unit or a Windows logon task; lakota-grades service

Closes #18

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The Diagnostics page and the doctor's `web server` probe (issue #17, part 2)

**Files:**
- Create: `lakota_grades/web/routes/diagnostics.py`, `templates/diagnostics.html`, `tests/test_web_diagnostics_page.py`
- Modify: `lakota_grades/doctor.py` (`web server` probe), `tests/test_doctor.py`, `templates/base.html` (rail: Diagnostics), `lakota_grades/web/app.py` (router)

**Interfaces:**
- Consumes: `doctor.REPORT_NAME` (`doctor.txt`), `host.service.describe_service`, `web.server.port_answers`, jobs (`POST /jobs/doctor`).
- Produces: `GET /diagnostics`; `doctor._web_server(settings, home) -> str` registered last in `PROBES` as `("web server", _web_server)`; module-level seams `doctor._describe_service` and `doctor._port_answers` (tests monkeypatch them).

- [ ] **Step 1: Tests**

Append to `tests/test_doctor.py` (and change the probe-name list assertion to end with `"scheduler", "web server"`):

```python
def test_web_server_probe(monkeypatch, tmp_path):
    from lakota_grades.host import ServiceInfo
    s = Settings(home=tmp_path)
    monkeypatch.setattr(doctor, "_describe_service", lambda: ServiceInfo("systemd", False, False, "not installed"))
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: False)
    assert "not running" in doctor._web_server(s, tmp_path) and "lakota-grades web" in doctor._web_server(s, tmp_path)
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: True)
    assert "http://127.0.0.1:8433/" in doctor._web_server(s, tmp_path)
    monkeypatch.setattr(doctor, "_describe_service", lambda: ServiceInfo("systemd", True, True, "enabled, active"))
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: False)
    with pytest.raises(RuntimeError) as e:
        doctor._web_server(s, tmp_path)
    assert "installed" in str(e.value) and "does not answer" in str(e.value)
    def broken():
        raise OSError("no systemctl")
    monkeypatch.setattr(doctor, "_describe_service", broken)
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: True)
    assert "service state unknown" in doctor._web_server(s, tmp_path)
```

`tests/test_web_diagnostics_page.py`:

```python
"""Diagnostics: the last doctor report, and the button that runs a new one."""
from __future__ import annotations

from fastapi.testclient import TestClient

from lakota_grades import config
from lakota_grades.web import app as webapp, jobs
from tests.web_fixtures import app_for, seed
from tests.test_web_jobs import FakeActions


def test_page_shows_no_report_yet_then_the_report(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/diagnostics").text
    assert "not been run yet" in body and 'hx-post="/jobs/doctor"' not in body
    (tmp_path / "doctor.txt").write_text("OK    python: 3.12\nFAIL  printers: none\n1 check(s) failed\n")
    body = c.get("/diagnostics").text
    assert "FAIL  printers" in body and "1 check(s) failed" in body


def test_run_diagnostics_button_starts_the_job_and_the_page_shows_it(tmp_path):
    seed(tmp_path).close()
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    w = jobs.Worker(application.state.lakota, actions=FakeActions())
    application.state.lakota.jobs = w
    c = TestClient(application)
    assert 'hx-post="/jobs/doctor"' in c.get("/diagnostics").text
    r = c.post("/jobs/doctor")
    assert r.status_code == 200 and "Running diagnostics" in r.text
    w.run_pending()
    assert "OK    python" in c.get(f"/jobs/{w.last.id}").text
```

Run both files. Expected: FAIL.

- [ ] **Step 2: Implement**

`doctor.py`:

```python
def _describe_service():
    from .host import service
    return service.describe_service()


def _port_answers(host: str, port: int) -> bool:
    from .web.server import port_answers
    return port_answers(host, port, timeout=2.0)


def _web_server(s: Settings, home: Path) -> str:
    """Is the browser app reachable, and is the always-on service the reason?"""
    url = f"http://127.0.0.1:{s.web_port}/"
    try:
        info = _describe_service()
        state = f"{info.managed_by}: {info.detail}"
        installed = info.installed
    except Exception as e:  # noqa: BLE001  no systemctl / schtasks here
        state, installed = f"service state unknown ({type(e).__name__})", False
    if _port_answers("127.0.0.1", s.web_port):
        return f"answering at {url} ({state})"
    if installed:
        raise RuntimeError(f"the service is installed ({state}) but {url} does not answer; check app.log")
    return f"not running ({state}); start it with `lakota-grades web` or install the service"
```

Add `("web server", _web_server)` at the end of `PROBES`.

`routes/diagnostics.py`:

```python
"""Diagnostics: the doctor report, on demand."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ... import doctor

router = APIRouter()


@router.get("/diagnostics")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    path = state.home / doctor.REPORT_NAME
    report = path.read_text(encoding="utf-8") if path.is_file() else None
    return render(request, conn, "diagnostics.html", current="diagnostics", report=report)
```

`templates/diagnostics.html`:

```html
{% extends "base.html" %}
{% block title %}Diagnostics · Lakota Sheet{% endblock %}
{% block content %}
<h2>Diagnostics</h2>
{% if jobs %}<p><button hx-post="/jobs/doctor" hx-target="#job" hx-swap="outerHTML">Run diagnostics</button></p>{% endif %}
<div id="job">{% if job %}{% with busy=false %}{% include "_job.html" %}{% endwith %}{% endif %}</div>
<h3>Last report</h3>
{% if report %}<pre class="log">{{ report }}</pre>{% else %}<p class="muted">Diagnostics have not been run yet.</p>{% endif %}
{% endblock %}
```

Rail: `<a href="/diagnostics" class="{{ 'current' if current == 'diagnostics' }}">Diagnostics</a>`. Include the router.

- [ ] **Step 3: Run, full suite, commit**

```bash
git add lakota_grades tests
git commit -m "web: the Diagnostics page; doctor gains a web server probe

Closes #17

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Retire the window: the entry point, packaging, installer, smoke test, docs (issue #19)

**Files:**
- Create: `lakota_grades/web/__main__.py`, `tests/test_web_main.py`
- Delete: `lakota_grades/app/` (all), `tests/test_app_gui.py`, `tests/test_app_main.py`
- Modify: `lakota_grades/cli.py` (remove `app`), `lakota_grades/web/server.py` (`_serve` `log_config=None`), `packaging/windows/LakotaSheet.spec`, `installer.iss`, `smoke.ps1`, `tests/test_packaging.py`, `README.md`, `docs/windows.md`, `pyproject.toml` (package-data: `host/*.xml` already; confirm `web/templates/*.html`, `web/static/*`), `.github/workflows/release.yml` (temporary trigger, removed again)

**Interfaces:**
- Produces: `web.__main__.main(argv) -> int`; `web.__main__.launch(settings, *, answers=None, spawn=None, opener=None, wait=None) -> int`; `web.__main__.setup_logging(home, stderr)`, `frozen_environment`, `TERMINAL_ONLY`, `APP_LOG`; the exe contract in Global Constraints.

- [ ] **Step 1: Tests for the entry point**

`tests/test_web_main.py` (port the still-relevant tests from `tests/test_app_main.py`: `frozen_environment`, `setup_logging` idempotence, CLI dispatch, string exit translation, terminal-only refusal, exception logging; drop the GUI ones) and add:

```python
def test_launch_opens_the_browser_when_the_server_answers(tmp_path):
    from lakota_grades import config
    from lakota_grades.web import __main__ as entry
    s = config.Settings(home=tmp_path)
    opened, spawned = [], []
    rc = entry.launch(s, answers=lambda h, p: True, spawn=lambda argv: spawned.append(argv), opener=opened.append, wait=lambda url, opener, **kw: opener(url))
    assert rc == 0 and spawned == [] and opened == ["http://127.0.0.1:8433/"]


def test_launch_starts_a_detached_server_then_opens(tmp_path, monkeypatch):
    from lakota_grades import config
    from lakota_grades.web import __main__ as entry
    import sys
    s = config.Settings(home=tmp_path)
    opened, spawned = [], []
    rc = entry.launch(s, answers=lambda h, p: False, spawn=lambda argv: spawned.append(argv), opener=opened.append, wait=lambda url, opener, **kw: opener(url))
    assert rc == 0 and spawned == [[sys.executable, "-m", "lakota_grades.cli", "web", "--no-browser"]] and opened == ["http://127.0.0.1:8433/"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\App\LakotaSheet.exe")
    spawned.clear()
    entry.launch(s, answers=lambda h, p: False, spawn=lambda argv: spawned.append(argv), opener=opened.append, wait=lambda url, opener, **kw: None)
    assert spawned == [[r"C:\App\LakotaSheet.exe", "web", "--no-browser"]]


def test_launch_respects_no_browser_env(tmp_path, monkeypatch):
    from lakota_grades import config
    from lakota_grades.web import __main__ as entry
    monkeypatch.setenv("LAKOTA_WEB_NO_BROWSER", "1")
    opened = []
    rc = entry.launch(config.Settings(home=tmp_path), answers=lambda h, p: True, spawn=lambda argv: None, opener=opened.append, wait=lambda *a, **k: None)
    assert rc == 0 and opened == []


def test_main_without_args_launches(monkeypatch, tmp_path):
    from lakota_grades.web import __main__ as entry
    monkeypatch.setattr(entry, "DEFAULT_HOME", tmp_path)
    called = {}
    monkeypatch.setattr(entry, "launch", lambda s, **kw: called.setdefault("ok", 0))
    monkeypatch.setattr(entry, "load_settings", lambda: object())
    assert entry.main([]) == 0 and called == {"ok": 0}


def test_app_command_and_package_are_gone():
    import importlib, pathlib
    from lakota_grades import cli
    import pytest
    with pytest.raises(SystemExit):
        cli.main(["app"])
    assert not (pathlib.Path(cli.__file__).parent / "app").exists()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("lakota_grades.app")
```

- [ ] **Step 2: `web/__main__.py`**

```python
"""Entry point of the frozen Windows executable, and of `python -m lakota_grades.web`.

No arguments makes sure the server is running and opens the browser (spec section 10): if the
port already answers as this app, just open it; otherwise start `web --no-browser` detached
and open once it answers. Anything else is the ordinary CLI, so the scheduled task's
`LakotaSheet.exe run open-work`, the logon task's `LakotaSheet.exe web --no-browser` and the
uninstaller's `schedule remove` / `service remove` all come from the same binary. A windowed
exe has no stdout or stderr, so logging goes to <home>/app.log; stderr gets a copy only when
it exists.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from lakota_grades.config import DEFAULT_HOME, Settings, load_settings
from lakota_grades.web import server

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
TERMINAL_ONLY = ("login", "set-credentials")
APP_LOG = "app.log"


def frozen_environment(environ=os.environ, executable: str | None = None) -> None:
    """Point Playwright at the Chromium the installer puts next to the exe."""
    if getattr(sys, "frozen", False):
        exe = Path(executable or sys.executable)
        environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(exe.parent / "ms-playwright"))


def setup_logging(home: Path, stderr=sys.stderr) -> None:
    (unchanged body from app/__main__.py, with APP_LOG from this module)


def _server_argv() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "web", "--no-browser"]
    return [sys.executable, "-m", "lakota_grades.cli", "web", "--no-browser"]


def _spawn_detached(argv: list[str]) -> None:
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kw["start_new_session"] = True
    subprocess.Popen(argv, **kw)


def launch(settings: Settings, *, answers=None, spawn=None, opener=None, wait=None) -> int:
    answers = answers or server.port_answers
    spawn = spawn or _spawn_detached
    opener = opener or webbrowser.open
    wait = wait or server._wait_and_open
    url = f"http://127.0.0.1:{settings.web_port}/"
    quiet = os.environ.get("LAKOTA_WEB_NO_BROWSER") == "1"     # the smoke test: wait for the server, open nothing
    if not answers("127.0.0.1", settings.web_port):
        spawn(_server_argv())
    wait(url, (lambda u: None) if quiet else opener, answers=answers, tries=150, interval=0.2)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    frozen_environment()
    setup_logging(DEFAULT_HOME)
    log = logging.getLogger("lakota.web")
    if not argv:
        try:
            return launch(load_settings())
        except Exception:
            log.exception("the app could not start")
            return 1
    if argv[0] in TERMINAL_ONLY and sys.stdin is None:
        log.error("%s needs a terminal; use the Settings page instead", argv[0])
        return 2
    from lakota_grades import cli
    try:
        cli.main(argv)
    except SystemExit as e:
        (unchanged translation from app/__main__.py)
    except Exception:
        log.exception("%s failed", argv[0])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

With `LAKOTA_WEB_NO_BROWSER=1` the launch still waits until the server answers (so the smoke test's no-args exe exits only once the server is up) but opens nothing: the no-op opener above is what `test_launch_respects_no_browser_env` sees.

`server._serve`: `uvicorn.run(app, host=host, port=port, log_level="info", access_log=False, log_config=None)` so uvicorn's records propagate to the root logger (app.log in the frozen exe, stderr from the CLI).

- [ ] **Step 3: Delete the window**

```bash
git rm -r lakota_grades/app tests/test_app_gui.py tests/test_app_main.py
```

`cli.py`: delete `cmd_app` and its parser; update the docstring. `grep -rn "tkinter\|python3-tk\|lakota-grades app\|settings window" README.md docs lakota_grades` and fix every hit (README section "The settings window" becomes "The browser app": `lakota-grades web` opens it; `lakota-grades service install` keeps it running; the Settings page replaces the window; Test login / Preview / Print now / Run diagnostics are buttons on the Settings, Dashboard and Diagnostics pages). Keep `docs/windows.md`'s pinned phrases (`test_packaging.py::test_windows_page_exists_and_names_the_limitations`): "SmartScreen", "More info", "Run anyway", "multi-factor", "logged in", `%LOCALAPPDATA%\lakota-grades`, "Test login", "Print now", "no-print-days.txt", "late-rules.toml", "doctor.txt", "Task Scheduler", "Uninstall" — rewrite "First run" and "If something goes wrong" for the browser app (the shortcut opens `http://127.0.0.1:8433/`; Settings page; Test login button; Dashboard's Refresh now / Preview / Print now; Diagnostics page; the file table gains `lakota.db` and `web.lock`; "Allow other devices on this network" for a phone). Plan E writes the friend's full page; this task keeps the document true.

- [ ] **Step 4: Packaging**

`packaging/windows/LakotaSheet.spec`: entry `lakota_grades/web/__main__.py`; `datas` add

```python
datas += [(os.path.join(ROOT, "lakota_grades", "host", "logon-task.xml"), os.path.join("lakota_grades", "host"))]
datas += [(os.path.join(ROOT, "lakota_grades", "web", "templates"), os.path.join("lakota_grades", "web", "templates"))]
datas += [(os.path.join(ROOT, "lakota_grades", "web", "static"), os.path.join("lakota_grades", "web", "static"))]
```

and `hiddenimports += collect_submodules("uvicorn") + ["fastapi", "jinja2", "multipart", "anyio._backends._asyncio"]` (the Task 1 outcome of part 1). `app.py` resolves templates by `Path(__file__).parent`, which under PyInstaller one-folder is `_internal/lakota_grades/web/` — the datas destinations above put the folders exactly there. `console=False` stays.

`installer.iss`: `[Run]` becomes

```
Filename: "{app}\LakotaSheet.exe"; Parameters: "service install"; Flags: runhidden waituntilterminated
Filename: "{app}\LakotaSheet.exe"; Description: "Open Lakota Sheet"; Flags: nowait postinstall skipifsilent
```

`[UninstallRun]` gains, before the schedule line: `Filename: "{app}\LakotaSheet.exe"; Parameters: "service remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveService"`. The post-uninstall message: "Your settings, notes and flags (lakota.db), printed sheets and logs were kept in …".

`smoke.ps1`: replace step 3 (the window) with

```powershell
    # 3. the server: start it on a free port, fetch two pages, stop it
    $env:LAKOTA_WEB_PORT = "8765"
    $srv = Start-Process -FilePath $exe -ArgumentList "web","--no-browser" -PassThru -WindowStyle Hidden
    $up = $false
    foreach ($i in 1..60) { Start-Sleep -Milliseconds 500; try { $h = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/health; if ($h.Content -match '"lakota-grades"') { $up = $true; break } } catch {} }
    if (-not $up) { Get-Content (Join-Path $smokeHome "app.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }; Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue; throw "the server never answered /health" }
    foreach ($path in "/", "/diagnostics", "/settings") {
        $r = Invoke-WebRequest -UseBasicParsing ("http://127.0.0.1:8765" + $path)
        if ($r.StatusCode -ne 200 -or $r.Content -notmatch "Lakota Sheet") { Stop-Process -Id $srv.Id -Force; throw "GET $path failed" }
    }
    Write-Host "  server answered /, /diagnostics, /settings"
    # 3b. no-args launch finds the running server and exits 0 without opening a browser
    $env:LAKOTA_WEB_NO_BROWSER = "1"
    $p = Start-Process -FilePath $exe -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw "no-args launch failed (exit $($p.ExitCode))" }
    Stop-Process -Id $srv.Id -Force
    # 3c. the logon task round-trips through schtasks
    $p = Start-Process -FilePath $exe -ArgumentList "service","install" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw "service install failed (exit $($p.ExitCode))" }
    $q = & schtasks /Query /TN "Lakota Sheet - web" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "logon task not found after install: $q" }
    $p = Start-Process -FilePath $exe -ArgumentList "service","remove" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw "service remove failed (exit $($p.ExitCode))" }
    Write-Host "  logon task installed and removed"
```

and add `Remove-Item Env:\LAKOTA_WEB_PORT`, `Env:\LAKOTA_WEB_NO_BROWSER` to the `finally`. Note `service install` on the runner starts the server via `schtasks /Run` on the default port 8433 (the env var is not inherited by Task Scheduler); `service remove`'s `/End` stops it. Update the header comment.

`tests/test_packaging.py`: entry point `lakota_grades/web/__main__.py`; spec contains `web", "templates"`, `web", "static"`, `logon-task.xml`, `collect_submodules("uvicorn")`, `"fastapi"`; smoke contains `"web","--no-browser"`, `/health`, `/diagnostics`, `"service","install"`, `"service","remove"`, `LAKOTA_WEB_NO_BROWSER`, no `MainWindowHandle`; iss contains `Parameters: "service install"`, `Parameters: "service remove"`, `lakota.db`; keep the rest.

- [ ] **Step 5: Verify the Windows build once on the runner**

Temporarily add to `.github/workflows/release.yml` under `on:`: `push: { branches: ["ccswitch/**"] }` alongside the existing triggers (the publish step is gated on a tag and will not run). Commit, push, `gh run watch` the `release` run: `build.ps1` must reach "smoke OK" and produce the installer artifact. Iterate on hidden imports or the smoke script if needed (at most four pushes; else BLOCKED with the log). Then remove the temporary trigger, run `tests/test_packaging.py::test_release_workflow_triggers_and_gates`, and record the run URL in this task's report.

- [ ] **Step 6: Run, full suite, commit, push**

```bash
git add -A
git commit -m "Retire the window: the browser app is the entry point; installer registers the logon task; smoke test drives the server

Closes #19

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

---

## Done when

- On this machine: `lakota-grades web` opens the Dashboard; Refresh now streams progress and ends with a `runs` row; Preview builds and links the PDF; the Runs page lists history; Settings saves `config.toml`, reloads the header's nicknames, refuses a password from a LAN address; the editors validate; Diagnostics runs the doctor and its report includes the `web server` probe; `lakota-grades service install` writes and enables `lakota-web.service` (Tony decides whether to run it).
- The Windows runner built the installer and passed the smoke test (server pages, no-args launch, logon task) once during Task 6, and the temporary trigger is gone.
- `lakota_grades/app/` and its tests are gone; `lakota-grades app` no longer exists; README and docs/windows.md describe the browser app.
- Full suite green locally and in CI on both runners; no warnings.
- Not in this plan: Changes and Trends (Plan C), view reports and schedules (Plan D), the friend's page, QR code and docs polish (Plan E), the residuals in issues #31 and #32 not named above.


# Lakota Sheet as a local web app: design

Date: 2026-09-15. Status: approved in discussion, awaiting review of this document.
Supersedes section 8 (the tkinter app) and amends sections 9 and 13 of
`2026-09-14-windows-sheet-app-design.md`; everything else in that spec (the runner,
reports plugin layer, host adapters, `config.toml`, the CLI, the Windows bundle and
installer, Tony's Linux compatibility) stays in force.

## 1. Goal

One place to see, across Canvas and Home Access Center, what is **actually outstanding
and actionable** for each kid, to annotate it, and to print or schedule reports built
from it. The app is not a replacement for Canvas, HAC or ParentSquare; those remain
where the work is done and where the school communicates. This app fills the gaps
between them: reconciling what each source says, keeping the parent's own knowledge
(notes, flags) next to the data, showing how things move over time, and producing the
printed sheet and any other report a parent wants.

Single user. No kid-facing surface. No login: the app is reachable on the home network
and security is the network's isolation, by the owner's decision. The background job
(the scheduled print) keeps running through the operating system's own timers, so the
web server can be down without a sheet being missed.

## 2. What changes from the current design

| Today | Becomes |
|---|---|
| tkinter window (`lakota_grades/app/gui.py`) | Removed. The browser is the only UI. |
| One JSON snapshot, overwritten each refresh | Snapshot still written (the MCP server reads it); every refresh is also ingested into a SQLite database that keeps history, notes, flags, saved reports, schedules and run history. |
| The printed sheet reflects only the sources | Parent flags (done, excused, ignore, follow up, ask teacher) reach the sheet and the reports. |
| One report type, code-defined | Code reports (the plugin layer) plus saved **view** reports defined in the browser. |
| Scheduling: one task per code report | Any report, any schedule, on Windows (Task Scheduler) and Linux (systemd user units written by the app). |
| Windows exe opens a window | Windows exe with no arguments makes sure the server is running and opens the browser; the installer registers a logon task that keeps the server up. |

## 3. Architecture

One Python process, `lakota-grades web`, runs a FastAPI application on uvicorn and
serves server-rendered Jinja2 pages. In-page updates use htmx; charts use one small
vendored JavaScript library (uPlot); there is no front-end build step. Data lives in
`<home>/lakota.db` (SQLite through the standard library). Settings stay in
`config.toml`, so the CLI, the timers and the server share one source of truth.

```
lakota_grades/
  web/
    __init__.py
    app.py           create_app(settings, db) -> FastAPI; mounts routes, static, templates
    server.py        run(host, port, open_browser): uvicorn entry; port-in-use detection
    db.py            connect(), migrate(); schema versions; all SQL lives here or in stores/
    ingest.py        snapshot dict -> database rows (refresh, students, courses, items, observations, grades)
    stores/          one module per table family: notes.py, flags.py, reports.py, schedules.py, runs.py
    reconcile.py     the reconciliation rules (section 6)
    views.py         view-report definitions -> rows -> table/PDF
    jobs.py          background worker: refresh / build / print on demand, progress via SSE, shares runner's lock
    routes/          dashboard.py, kid.py, changes.py, trends.py, reports.py, schedules.py, runs.py, settings.py, diagnostics.py
    templates/       Jinja2 pages and htmx partials
    static/          app.css, htmx.min.js, uplot.min.js, app.js (small)
  reports/
    view.py          ViewReport: the saved-view report kind, registered alongside code reports
  host/
    scheduling_linux.py   gains install/remove that write ~/.config/systemd/user/lakota-<key>.{service,timer}
    service.py            install_service/remove_service/describe_service for the always-on web server (systemd unit on Linux; logon task on Windows)
```

The runner, reports registry, host adapters, `config.py`, `doctor.py` and the CLI are
reused unchanged except where named below. `lakota_grades/app/` (actions, gui,
`__main__`) is deleted; the PyInstaller entry point becomes `lakota_grades/web/__main__.py`
with the same "no arguments → app, else CLI" contract.

New dependencies: `fastapi`, `uvicorn`, `jinja2`, `python-multipart`. All ship wheels
for Linux, Windows and macOS and freeze under PyInstaller (a spike proves this first,
section 14).

## 4. Data

SQLite, one file, `PRAGMA journal_mode=WAL`, a `schema_version` table and forward-only
migrations in `web/db.py`. Times are stored as ISO strings in the settings time zone.

| Table | Purpose |
|---|---|
| `refreshes` | one row per refresh: started, finished, per-source health, ok |
| `students` | key (snapshot key), display name, nickname, hidden |
| `courses` | student, source, external id, name, short name, teacher, hidden |
| `items` | the assignment: student, course, stable key (`canvas:<id>`, `hac:<course>:<name>`), name, kind (online / paper / in class), points, due, assigned, first seen, last seen |
| `item_observations` | what a source said about an item at a refresh: status, score, grade, submitted, late, missing, excused. **Written only when it differs from the previous observation**, so the table is a change log. |
| `grade_observations` | per course per refresh: HAC average and letter, Canvas current and final. Written on change. |
| `notes` | body, created, updated; target is an item, a course or a student |
| `flags` | item, flag (`done`, `excused`, `ignore`, `follow_up`, `ask_teacher`), set at, cleared at, optional text. One active flag per item. |
| `reports` | saved view reports: name, definition (JSON, section 7), created, updated |
| `schedules` | report key or saved report id, days, time, printer or "PDF only", enabled |
| `runs` | every run, scheduled or on demand: report, started, outcome (OK / SKIP / FAIL), message, PDF path, job reference. The CLI runner writes here too. |

**Ingest.** After every refresh (CLI or on-demand), `ingest.record(snapshot)` upserts
students and courses, upserts items by stable key, and appends observations that
changed. Items the sources stop reporting keep their rows (last seen stops advancing);
the sheet's existing "not shown" logic decides what is still relevant. HAC rows have no
ids; the key uses the course and the assignment name, and `matching.same_item` (the
existing Canvas-to-HAC matcher) links a HAC item to its Canvas twin so one row carries
both sources. This is the first risk to retire (section 14).

**Flags reach the paper.** `open_items.open_items()` gains a `flags` argument. `done`,
`excused` and `ignore` remove an item from the open list (it is counted in "handled"
rather than "not shown"); `follow_up` and `ask_teacher` print a marker in the status
column. The runner loads flags from the database before building, so the scheduled
sheet reflects what was marked in the browser.

## 5. Pages

All pages are one responsive layout: a left rail on a desktop, a single column on a
phone. Every page shows the last refresh time and source health in the header.

- **Dashboard.** Per kid: actionable count, due today and tomorrow, new since yesterday,
  what printed today. One "Refresh now" button with live progress.
- **Kid.** The item list with filters (open / actionable / all, source, course, kind,
  flagged), sortable; each row expands to notes and a flag menu; the reconciliation
  badge (section 6) on rows where the sources disagree. Course drill-down: grade trend,
  teacher contact, course notes.
- **Reconcile.** The gap this app exists to fill (section 6).
- **Changes.** Everything that changed since a chosen time: new items, grades posted,
  items cleared, flags set. This is the "what happened while I wasn't looking" feed.
- **Trends.** Grade per class over time (HAC average, Canvas current), missing and late
  counts per week, on-time rate, days an item stays open; one kid or all kids.
- **Reports.** The list (code and view reports), the view builder (section 7), a
  browser preview, print to a chosen printer, export CSV or JSON.
- **Schedules.** Any report, days, time, printer or PDF-only, enabled; installs the OS
  task or unit on save.
- **Runs.** Run history with outcome and message, open the PDF, reprint.
- **Settings.** Everything `config.toml` holds (OneLogin username and password, printer,
  archive folder, nicknames, hidden courses), in-page editors for late-work rules and
  no-print days, and the network toggle (section 8).
- **Diagnostics.** The doctor report, run on demand.

## 6. Reconciliation: what "actionable" means

An item is **actionable** when the kid can still do something about it:

1. It is open in at least one source (not submitted, or submitted late and ungraded,
   or scored zero, or past due with no grade), **and**
2. it still earns credit under the late-work rules (`late_rules.toml`), **and**
3. it carries no `done`, `excused` or `ignore` flag.

The Reconcile page lists, per kid, the cases the sources cannot settle on their own,
each with a one-line reason and the flag menu right there:

- **Sources disagree.** Canvas says missing, HAC shows a grade (or the reverse).
- **Only one source knows.** An item HAC lists that Canvas never had (paper work), or
  a Canvas assignment HAC has not recorded.
- **Submitted, not graded.** Turned in on time or late and sitting ungraded past the
  due date; nothing to do but worth knowing.
- **Paper, no grade.** On-paper or in-class items past due with no grade: ask the kid.
- **Past the credit window.** Overdue items the rules say no longer earn credit, shown
  once so they can be flagged `ignore` and stop appearing.
- **Flagged, but the sources moved.** A `done` item that a source later marks missing,
  or a `follow_up` item that got a grade: the flag may be stale.

Flag choices from this page write to `flags`; the next sheet and every report honour
them. These rules live in `web/reconcile.py`, pure functions over database rows, tested
in isolation.

## 7. Reports

The registry (`reports.REPORTS`) resolves two kinds by key: **code reports** as today
(`open-work` and any future Python plugin) and **view reports** (`view:<id>`) defined
in the browser and stored in `reports`. Both satisfy the same `Report` protocol and
flow through the same runner, so a scheduled view report prints, archives, records and
toasts exactly like the open-work sheet.

A view definition is JSON: `scope` (kids), `source` (`items`, `grades`, `changes`),
`columns`, `filters` (field, operator, value), `group_by`, `sort`, `chart` (none /
line / bars over a chosen series), `title`, and print options (`orientation`,
`per_kid_sections`). The builder edits these with ordinary form controls and shows a
live preview table. Rendering: rows → an HTML table in the browser; the same rows →
the existing reportlab table engine for PDF (`sheet.py`'s table code is generalised to
take columns and rows, the open-work sheet keeps its bespoke layout). Templates ship as
seed rows: Open work (a view twin of the code report), Weekly summary, Grade trend,
Quarter recap.

Schedules: `schedules` rows map to `host.scheduling.install(key, time, days, exe,
args, workdir)` where `key` is the report key; on Windows one Task Scheduler task per
schedule (today's behaviour), on Linux the adapter gains a real `install`/`remove`
that writes `~/.config/systemd/user/lakota-<key>.service` and `.timer`
(`OnCalendar=<days> <time> <tz>`, `Persistent=true`) and enables them. Tony's existing
hand-written units keep their names and are untouched.

## 8. Access and security

No login. The server binds to `127.0.0.1:8433` by default. Settings has one toggle,
"Allow other devices on this network," which rebinds to `0.0.0.0` and shows the LAN
URL and a QR code for a phone. The owner accepts network isolation as the security
boundary.

The OneLogin password field originally accepted input only from a browser on the machine
itself (loopback client address). **That rule was removed in 2026-09** after it made the
app impossible to configure on a headless host: when the server runs under a dedicated
account with no desktop session, no request is ever loopback, so "open Lakota Sheet on the
PC itself" names a browser that does not exist. It also protected less than it appeared —
with no login at all, every device the `Host` check admits could already read the kids'
names and grades and the OneLogin username, and setting a password grants an attacker
nothing they did not already have.

What is kept is the asymmetry that actually matters: the stored password is **write-only**.
It is never rendered into the form, never returned by any route, and a blank field keeps
whatever is stored. Setting it from another device is allowed and says plainly that it
crosses the network in the clear (there is no HTTPS); reading it back is not possible from
anywhere. Everything else works from any device on the network.

The server never talks to anything but OneLogin, Canvas and HAC. Nothing is sent
anywhere else; there is no telemetry.

## 9. Jobs and the timers

On-demand refresh, build, print and doctor run on a single worker thread inside the
server (`web/jobs.py`), one at a time, using the runner's existing `run.lock` so a
scheduled CLI run and a button press never overlap. Progress lines (the runner's `echo`
and the scraper's log records, as the window had) stream to the page over
server-sent events. Every run, scheduled or on demand, writes a `runs` row; the
Runs page and a header badge read it. Desktop toasts stay for scheduled runs.

Scheduled runs are the OS timers calling the CLI (`lakota-grades run <key>`), as
today. The CLI runner ingests after refresh and writes `runs`, so the database is
complete whether or not the server was up.

## 10. Service model, per platform

| | Web server (always on) | Scheduled reports |
|---|---|---|
| Linux | `lakota-web.service` user unit, `Restart=on-failure`, installed by `lakota-grades service install` | systemd user timers, written by the app for new schedules; existing ones untouched |
| Windows | logon task "Lakota Sheet - web" running `LakotaSheet.exe web --no-browser`, registered by the installer; Start menu shortcut opens the browser | Task Scheduler tasks, one per schedule |
| macOS | launchd agent: adapter shape provided, packaging out of scope | launchd, same |

`LakotaSheet.exe` with no arguments: if the port answers, open the browser; else start
the server in the background and open the browser once it answers. `lakota-grades web`
runs the server in the foreground (what the unit and the logon task call).
`host/service.py` is the adapter (`install_service`, `remove_service`,
`describe_service`) with the same Linux/Windows split and injected-command tests as
the others.

## 11. Packaging, the friend, compatibility

- The PyInstaller spec adds `web/templates` and `web/static` as data; the smoke test
  gains "start `LakotaSheet.exe web --no-browser` on a free port, fetch `/`, fetch
  `/diagnostics`, stop it," and a Playwright page load of the dashboard.
- The installer registers the logon task and the uninstaller removes it along with the
  scheduled tasks; the "your data was kept" message now names `lakota.db`.
- `docs/windows.md` describes a browser app: the shortcut opens it, the phone toggle,
  notes and flags, the Reconcile page.
- Compatibility: CLI, MCP server, `config.toml`, `sheets/<date>/` and Tony's timers all
  keep working. The database starts empty and fills from the next refresh. The
  `doctor` gains `database` and `web server` probes.
- Deleted: `lakota_grades/app/`, `tests/test_app_*.py`, the `app` CLI command. The
  `TERMINAL_ONLY` guard and crash logging move to `web/__main__.py`.

## 12. Testing

- `web/db.py`, `ingest.py`, stores, `reconcile.py`, `views.py`: unit tests on a
  temporary database, including ingest of a sequence of fixture snapshots that proves
  observations are written only on change and that a HAC item links to its Canvas twin.
- Routes: FastAPI's `TestClient`, no network: every page renders with an empty database
  and with fixtures; notes and flags round-trip; a view report previews, prints (to a
  fake printer) and exports; that the OneLogin password can be set from another device but
  is never rendered back to one, and that a blank field keeps the stored one.
- `host/service.py` and the Linux scheduling `install`: injected-command tests
  asserting the unit text and the `systemctl` argv.
- The Windows build's smoke test covers the server start and page fetch; CI stays on
  both runners.

## 13. Delivery: five plans

Each ships on its own and keeps everything before it working.

- **A. Data.** `web/db.py`, `ingest.py`, notes and flags stores, `reconcile.py`, flags
  reaching `open_items` and the runner, `runs` written by the CLI, `doctor` probes.
  No UI yet, and no CLI commands for notes or flags: the browser is their only editor.
- **B. Server.** FastAPI app, Dashboard, Kid, Reconcile, Settings, Diagnostics, Runs;
  jobs with live progress; `host/service.py`; `lakota-grades web` and `service`
  commands; the Windows entry point, installer and smoke test; the window retired.
- **C. Time.** Changes feed and Trends with charts.
- **D. Reports.** View reports, the builder, preview, print, export, schedules on both
  platforms including the Linux unit writer.
- **E. Docs and polish.** The friend's page, README, the QR code, anything B left.

## 14. Out of scope for this version

Login and HTTPS; a kid-facing view; a layout designer; multiple households; macOS
packaging; email or push notifications; ParentSquare as a source (named here because it
is reachable through the same OneLogin portal and carries messages no gradebook has;
it would enter as a third source in the same ingest shape); any write-back to Canvas or
HAC.

## 15. Risks to retire first

1. **Stable keys for HAC items across refreshes** (no ids; names and courses can be
   edited by teachers). Plan A starts with an ingest test over real snapshots from
   Tony's cache history.
2. **FastAPI and uvicorn under PyInstaller** with Jinja2 templates as data: a
   throwaway spike on the Windows runner, as Plan 1 did for Chromium.
3. **A logon-task server surviving sleep and lock on Windows:** the doctor's `web
   server` probe and a manual check on a real PC.
4. **Port collisions and multiple instances:** the server takes an exclusive lock file
   beside the database; a second start opens the browser at the first.

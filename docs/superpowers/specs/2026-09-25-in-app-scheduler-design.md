# In-app scheduler (design)

Date: 2026-09-25. Decided by the maintainer, in order: the server runs schedules itself
("A"), on **both platforms**, with a clock thread inside the server, and a missed slot is
**caught up once**. Hand-written Linux units are no longer detected.

## 1. The problem

No schedule on `graphy` (Windows 11, the household's kiosk host) has ever fired.

Observed 2026-09-25 over SSH:

```
Name     : Fridge Sheet - data-refresh
Logon    : Interactive
Triggers : 05:00, 07:00, ... 21:00 (daily)
Last     : 11/30/1999 12:00:00 AM        # never
Result   : 0x41303                        # SCHED_S_TASK_HAS_NOT_RUN
```

The task was registered 2026-09-23 20:29. Eighteen trigger times passed before this was
written; it ran for none of them. Every row on graphy's Runs page has `trigger = web`.

**Cause.** `fridgesheet/host/task.xml` gives every task the app registers
`<LogonType>InteractiveToken</LogonType>`: *run only when the user is logged on*. The
Windows design (`2026-09-14-windows-sheet-app-design.md`, `install`) chose that on purpose,
on the assumption that the account the app runs as is the person at the keyboard. On graphy
it is not. The app runs as `lakotarunner`; the only interactive session is `dougs`'s.
`lakotarunner` is never logged on, so Task Scheduler skips each trigger silently: no error,
no missed-run count, no run row.

The always-on server's own task, `Fridge Sheet - web`, was registered by an administrator
with `LogonType=Password` and runs in session 0. Refreshes and prints started from the app
succeed there, so Credential Manager, Playwright and the printer all work from that context.
That process is the one reliable place on graphy that runs as the right account and is
always up.

Meanwhile nothing prints on a schedule anywhere. `dobby`'s hand-written
`lakota-print-sheet.timer` last printed Mon 2026-09-21 14:00 and was disabled that evening
at the maintainer's instruction; no report on graphy has ever had a schedule saved.

## 2. What is being built

The web server fires schedules itself, on Windows and Linux alike. `config.toml` stays the
only record of what is scheduled; the OS scheduler is no longer used for schedules at all.

Consequence, stated plainly: **schedules run only while the web server runs.** On Windows
the installer always registers the server's logon task. On Linux a household that wants
schedules must run `fridgesheet service install` (the systemd user unit that already
exists). `dobby` does not run it today.

## 3. Components

| Unit | Job | Depends on |
|---|---|---|
| `fridgesheet/schedule_plan.py` (new) | Pure functions: which schedules are due at `now`, and each one's next run. No I/O, no threads, no clock of its own. | `config`, `refresh_schedule`, `host` (day names, key constants) |
| `fridgesheet/web/clock.py` (new) | A daemon thread in the server. Every 60 s it reads settings, asks `schedule_plan` what is due, submits jobs to the existing `jobs.Worker`, and records what fired. Holds a heartbeat. | `schedule_plan`, `jobs.Worker`, `web/db.py` |
| `schedule_fires` table (schema 6, new) | `key TEXT PRIMARY KEY, slot TEXT NOT NULL` — the last slot fired, per schedule key, as an ISO datetime with offset. | `web/db.py` migration |
| `host/scheduling.py` (shrinks) | `remove_os_leftovers()` only: delete what earlier versions of this app registered with the OS. | `scheduling_windows.py` / `scheduling_linux.py`, both reduced to that one job |

Schedule keys are unchanged: a report's key (`open-work`, `view:3`) and
`host.DATA_REFRESH_KEY` (`data-refresh`) for the refresh. `host.is_reserved` keeps a report
from being scheduled under the refresh's key.

The `schedules` table from schema 1 has never been written or read. It is left as it is;
removing it is a separate cleanup.

### Removed

- `host/task.xml`, `render_task_xml`, `install`, `describe`, `blocking_name`,
  `display_name` and the task-name ownership code in `scheduling_windows.py`.
- `service_text`, `timer_text`, `install`, `describe`, `LEGACY_TIMERS`,
  `_HAND_WRITTEN_REFRESH`, `_FOREIGN_UNITS` and `blocking_name` in `scheduling_linux.py`.
  `MARKER` stays: it is how the cleanup recognises a unit this app wrote.
- `host.scheduling.command_for`, `install`, `describe`.
- In `web/schedules.py`: `_unmanageable`, `_installed_or_unknown`, `_describe_once`, every
  `scheduling.install`/`remove` call, and the `LOGIN_STAMP` gate on saving (a save no longer
  installs anything; a scheduled run without a working login fails visibly on the Runs page,
  as a manual one does).
- `fridgesheet schedule install`.
- The hidden `run --trigger schedule` CLI flag stays: it is harmless and a leftover OS task
  from an older version may still call it until the cleanup removes that task.

## 4. How a schedule fires

### The tick

Every 60 seconds, `Clock.tick(now)`:

1. Loads settings fresh, so a save on the Schedules page takes effect by the next tick.
2. Builds the list of enabled schedules: `[refresh]` when `enabled`, expanded to its times
   by `refresh_schedule.refresh_times`; and each `[reports.<key>]` with `enabled = true`
   whose key still resolves to a report.
3. Reads `schedule_fires`.
4. For each schedule, `schedule_plan.due(schedule, now, last_fired)` returns the slot to fire
   or None (rules below).
5. For each slot returned, submits a job to the worker. If `submit` returns a job, writes the
   slot to `schedule_fires`. If it returns None (the one worker slot is busy), writes
   nothing; the next tick tries again.
6. Stamps the heartbeat.

At most one job is submitted per tick, because the worker runs one job at a time and
`submit` refuses a second; any other due schedule waits for a later tick. Order within a
tick: the refresh first, then reports by key. A refresh due at the same minute as a print
therefore runs before it.

### The due rule

A schedule's slots are `(day, time)` pairs: every configured time on every configured day,
as wall-clock times in `settings.timezone`.

- `latest` = the most recent slot at or before `now`, searching back at most 7 days.
- No `latest` (for example, no days ticked): not due.
- No `last_fired` for this key (**first sight**): record `latest` as fired without running
  it. Upgrading at 4 PM, or ticking a 2 PM report on at 3 PM, must not print immediately.
- `latest > last_fired`: due; the slot to fire is `latest`.
- Otherwise not due.

Only the *latest* slot is ever fired, which makes catch-up one run however many slots were
missed. A PC asleep over a weekend makes one refresh and one print attempt when it wakes,
not a dozen.

Clock changes:

- A wall-clock time that does not exist (spring forward, 02:30) has no slot that day.
- A wall-clock time that occurs twice (fall back, 01:30) is one slot, at its first
  occurrence (`fold=0`). The second occurrence compares equal to `last_fired` and does not
  fire again.
- A system clock that jumps backwards leaves `latest <= last_fired`, so nothing fires again
  until the clock passes the recorded slot.

### What a job runs

Two new worker job kinds, `scheduled-refresh` and `scheduled-report`, both in `jobs.GATED`
so the open `POST /jobs/{kind}` route cannot start them.

- `scheduled-refresh` calls `actions.refresh(home=, log=, settings=, trigger="schedule")`,
  the same collect, ingest and record as the Refresh button. Its run is recorded under
  report key `refresh`, as today.
- `scheduled-report` calls a new `actions.scheduled_run(key)`, which calls
  `runner.run(key, RunOptions(no_refresh=True, trigger="schedule"), settings)`. That is
  exactly what the OS task ran (`run <key> --no-refresh --trigger schedule`), so every guard
  applies: no-print-days, already printed today, the print window, the stale-snapshot
  refusal, the configured printer, PDF-only. It is **not** `print_now`, which forces past all
  of those on purpose.

A catch-up print therefore behaves as it did under `Persistent=true` and
`StartWhenAvailable`: on the same day after the report's time it prints; the next morning
before that time the runner records `SKIP outside print window ... this is a catch-up run`.

A job that fails (Canvas down, printer offline) is an ordinary FAIL row on the Runs page with
"On a schedule". Its slot still counts as fired: no retry storm; the next slot tries again.
A job that hangs is taken off the slot by the worker's existing 15-minute deadline.

## 5. What a parent sees

### Schedules page

Each schedule row, and the refresh row, shows:

- **Next run**, from `schedule_plan.next_run(schedule, now)`: "today 2:00 PM",
  "Mon 5:00 AM".
- **Last scheduled run**: the newest `runs` row with `trigger = 'schedule'` for that key
  (report key `refresh` for the refresh row), with its outcome: "Thu 2:00 PM, OK". When
  there is none: "has not run on a schedule yet".
- A config problem that stops one schedule from expanding (`[refresh]` with end before
  start) is shown on that row instead of a next run, as today.

Page-level notices:

- **Schedules are paused.** When the clock's heartbeat is older than 3 minutes: "Schedules
  are paused: the scheduler inside Fridge Sheet has stopped. Restart Fridge Sheet." The same
  words go in the header status line. (If the page loads, the server is up, so this only
  appears if the clock thread itself has died.)
- **Linux, no service.** When `service.describe_service()` says the always-on unit is not
  installed and at least one schedule is enabled: "Schedules run only while Fridge Sheet is
  running. To keep it running after you sign out: `fridgesheet service install`."
- **Leftover the cleanup could not remove** (section 6): one line naming the task or unit
  and the command that removes it.

### Elsewhere

- `doctor`'s scheduler check reports "scheduler running; next run …" from the plan, and fails
  only when a schedule is enabled and the heartbeat is stale. Run from the CLI, where there is
  no clock, it reports the next run and says schedules need the server running.
- `actions.status_line` takes the next run from the plan.
- `fridgesheet schedule show [key]` prints each enabled schedule's next run and last
  scheduled run.

## 6. Leftovers from earlier versions

`host.scheduling.remove_os_leftovers() -> Leftovers` deletes, on:

- **Windows:** every task in the root folder whose name starts `Fridge Sheet - `, listed with
  `schtasks /Query /FO CSV /NH` rather than built from `config.toml`'s keys, so a task left by
  a report deleted long ago is found too. Never `Fridge Sheet - web` (the imported
  `service_windows.NAME`, compared stripped and case-folded, as today).
- **Linux:** every `fridgesheet-*.timer` / `.service` under `~/.config/systemd/user` whose
  first line is `MARKER`: `disable --now` the timer, delete both files, `daemon-reload`.
  A unit without the marker is never touched; the web server's own unit is never touched.

It returns what it removed and what it could not (with the error text). It runs:

- once at server start, on a background thread so it cannot delay the first page, with each
  removal logged and each failure kept for the Schedules page notice;
- from `fridgesheet schedule remove --all`, which the Windows uninstaller already runs.

On graphy this removes the dead `Fridge Sheet - data-refresh` task. Without it, the day
`lakotarunner` did sign in interactively, that task and the server would both fire.

## 7. Error handling

- A tick that raises (unreadable config, locked database) is logged; the thread continues and
  the next tick tries again. The heartbeat is stamped only by a tick that completes, so a
  clock that fails every tick shows as paused.
- A config error confined to one schedule skips only that schedule.
- `schedule_fires` write failure after a successful submit: logged. The slot may fire again
  on the next tick; the runner's already-printed guard stops a second print of the same day,
  and a second refresh is harmless.
- The clock never raises out of its thread.

## 8. Testing

The suite already blocks real `systemctl` and `schtasks` (`conftest._no_real_scheduler`),
injects `state.now()`, and can run a queued job on the test thread (`Worker.run_pending()`).

1. **`schedule_plan`** — table tests: due, not yet due, exactly on the minute; several
   refresh slots with only the latest missed one due; a weekend asleep is one slot; a day not
   ticked; first sight records and does not fire; spring-forward gap; fall-back repeat fires
   once; clock moved backwards; `next_run` for later today, tomorrow and next Monday.
2. **`Clock.tick(now)`**, called directly with a fake worker, no thread and no sleep: a due
   slot is submitted and recorded; a busy worker leaves it unrecorded and the next tick fires
   it; a new `Clock` on the same database does not fire it again; one job per tick, refresh
   first; a raising tick is logged and the next still runs; a broken schedule does not block
   the others; the heartbeat goes stale when ticks stop and is not stamped by a failing tick.
3. **Jobs** — `scheduled-refresh` records `trigger='schedule'`; `scheduled-report` calls
   `runner.run` with `no_refresh=True`, `trigger="schedule"` and none of `force`, `reprint`,
   `force_print`; both are refused by `POST /jobs/{kind}`.
4. **Pages and CLI** — Schedules page shows next run, last scheduled run, "has not run on a
   schedule yet", the paused notice, the Linux service notice, and a cleanup failure; saving
   writes `config.toml` and makes no OS call; doctor and `status_line` read the plan;
   `schedule show` output.
5. **Cleanup** — removes every listed `Fridge Sheet - *` task, including one for a key no
   longer in `config.toml`, never `Fridge Sheet - web` in any casing; removes marker-bearing Linux units only; reports what
   it could not remove.
6. **On graphy, after release** (manual; added to `docs/release-checklist.md`): install the
   release; confirm `Fridge Sheet - data-refresh` is gone from Task Scheduler; wait for the
   next refresh slot; confirm the Runs page shows a refresh "On a schedule". Nobody made
   this check after the last scheduling release, and it is the one that would have caught
   this.

## 9. Out of scope

- Scheduling anything while the server is down. Accepted as the cost of one path.
- Detecting hand-written units such as `lakota-print-sheet.timer`. If one is re-enabled next
  to an in-app schedule for the same report, the already-printed guard stops a second print
  on the same day (both use the same home directory), but it will pull data twice.
- Turning on graphy's weekday 2 PM Open Work Sheet: a configuration step once this ships.
- Dropping the unused `schedules` table.

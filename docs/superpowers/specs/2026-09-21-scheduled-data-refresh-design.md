# Scheduled data refreshes (design)

Date: 2026-09-21. Decided by the maintainer: *"I want to add the ability to schedule
multiple data refreshes per day, independent of when I schedule the one-pager to be
printed. Currently thinking of skipping the printing for my personal use case since I have
the page hosted on my kitchen kiosk."*

## 1. The problem

An app-installed schedule never refreshes. `host/scheduling.py::command_for` returns
`run <key> --no-refresh` for every key, and its docstring says why: a scheduled print
*"trusts the independently-scheduled data refresh (section 5's timer, or a manual Refresh
now) to have kept the snapshot warm."*

Section 5's timer is a **hand-written systemd unit**. On Linux a household sets it up from
`systemd/fridgesheet-refresh.{service,timer}`. On Windows nothing equivalent ships, so on a
Windows host nothing refreshes at all. The app can schedule the *consumer* of fresh data
and not the *producer*.

Observed on `graphy` (Windows 11, the household's kiosk host) on 2026-09-21: every run in
its history had `trigger = web` — a person clicking — and its snapshot was 20 hours old,
from a manual refresh the previous afternoon. A single refresh then brought in **12 new
items, 21 changes and 7 grade changes**, so the drift was real, not theoretical.

Two consequences:

- The kitchen kiosk shows stale data with nothing to correct it.
- `runner.MAX_DATA_AGE_HOURS = 24`: past 24 hours a `--no-refresh` run **fails outright**
  (`"snapshot is stale (N h old) and no refresh was requested; nothing printed"`). A print
  schedule installed on a Windows host is therefore guaranteed to fail within a day of the
  last manual refresh.

The household's Linux box (`dobby`) still carries both hand-written timers and is the only
machine refreshing or printing on a schedule. This feature is what lets it be retired.

## 2. What is being built

A refresh that the app schedules itself, several times a day, on both platforms,
independent of any report's schedule — and a banner that says so when the data goes stale
anyway.

**Not** in scope: real-time or on-demand fetching. That was raised in the same conversation
and is a separate investigation (section 8).

## 3. The schedulable unit

A reserved key, **`data-refresh`**, carried through the existing key machinery unchanged:

| | name |
|---|---|
| Windows task | `Fridge Sheet - data-refresh` (`host.task_name`) |
| Linux units | `fridgesheet-data-refresh.timer` / `.service` (`host.safe_key`) |

The name is deliberately **not** `fridgesheet-refresh.timer`. `scheduling_linux._HAND_WRITTEN_REFRESH`
protects that pair — and its `lakota-grades-*` predecessors — by name, so the app refuses to
install over them. Choosing a distinct name lets a hand-written refresh and an app-managed
one coexist on one machine, neither touching the other. README section 5 stays true and
becomes "the older way, still honoured".

`data-refresh` goes on a reserved-key list checked **case-folded**, for the reason
`_FOREIGN_TASKS_FOLDED` documents: Task Scheduler's namespace is case-insensitive, so a
hand-edited `[reports.Data-Refresh]` would otherwise collide with the app's own task. The
list holds the key, not the rendered name, because `task_name` only applies `safe_key` to
keys containing a colon.

Unchanged by this work: `_FOREIGN_UNITS`, `_FOREIGN_TASKS`, `LEGACY_TIMERS`,
`_check_ownership`, and the `install`/`remove`/`describe` contract. This adds a key to a
system that already handles keys.

## 4. What the schedule runs

`fridgesheet refresh` (CLI) is **not** the command. `cli.py::cmd_refresh` writes
`snapshot.json` and stops: it does not ingest into the web database and does not record a
run. The kiosk renders from the database, so a schedule wired to it would fire correctly,
report success, and never change what is on screen.

`web/actions.py::refresh` is the only path that does all three — collect, `ingest.record`,
`runs.record` — under the runner's lock. The schedule calls that.

- New CLI entry point: **`fridgesheet refresh --record`**, calling `web.actions.refresh`.
- `web.actions.refresh` gains a `trigger` parameter; its two `runs.record` calls stop
  hard-coding `"web"`. The schedule passes `"schedule"`.
- Bare `fridgesheet refresh` keeps its current snapshot-only behaviour. Nothing that exists
  today changes meaning.
- `command_for` grows one branch: `refresh --record` for `data-refresh`, the existing
  `run {key} --no-refresh` for every report. Prints still trust the snapshot — and now
  something keeps it warm.

Concurrency is already solved: `web.actions.refresh` holds the runner's lock, so an
interval that fires while the previous refresh is still running records
`FAIL: already running (run.lock present); nothing done` rather than starting a second
browser through OneLogin.

## 5. Configuration and expansion

A new top-level table, parsed beside `[web]` and `[reports]`:

```toml
[refresh]
enabled = true
every_hours = 3
start = "06:00"
end = "21:00"
days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
```

Parsing follows the convention `config.py` already established for `[reports]`: a value of
the wrong *shape* falls back to the default rather than raising, because a `TypeError`
escaping here tracebacks out of `schedule remove --all`, which the uninstaller runs hidden
with its exit code discarded, orphaning every scheduled task. The one exception mirrors
`_validate_report_time`: a `start` or `end` that is not `HH:MM` raises `ConfigError`,
because a refresh silently running at the wrong hour is worse than one that refuses to
install.

The interval expands to explicit times — one pure function, the feature's only algorithm:

```python
def refresh_times(start: str, end: str, every_hours: int) -> list[str]:
    """06:00, 21:00, every 3 -> ["06:00","09:00","12:00","15:00","18:00","21:00"]."""
```

| case | answer | why |
|---|---|---|
| `end` lands on a step | included | "between 6 and 9" should refresh at 9 |
| `end` falls mid-step (6→20, every 3) | last step 18:00 | never fire outside the window |
| `start == end` | one time | a single daily refresh is legitimate |
| `end < start` | `ConfigError` | overnight windows unsupported; say so |
| `every_hours <= 0` | `ConfigError` | would not terminate |
| `every_hours` > window | just `start` | one refresh, not zero |
| more than 12 times a day | `ConfigError` | see below |

`every_hours` is an **integer number of hours**. A non-integer is the wrong shape and falls
back to the default of 3, exactly as `[reports]` treats a malformed `days` — sub-hourly
refreshes are not a supported setting, so they are a fallback rather than a `ConfigError`.

The 12-a-day cap is not arbitrary. A refresh drives a real browser through OneLogin into
Canvas and HAC and takes 1–3 minutes on `dobby`, 8–10 on `graphy`. Hourly is already a
great many logins against the district's systems, so `every_hours = 1` across a full day
(24 expansions) is refused rather than becoming a self-inflicted denial of service on the
school. A household wanting hourly can have it inside a 12-hour window.

### Rendering

Both renderers take `times: list[str]` where they took `time: str`:

- `host/task.xml` gains a `{triggers}` placeholder; the single `<CalendarTrigger>` block is
  emitted once per time.
- `scheduling_linux.timer_text` emits one `OnCalendar=` line per time. systemd accepts
  repeats and unions their elapse points.
- `host.check_schedule` gains a sibling validating a list, so every time is checked before
  any file is written.

**A one-element list must render byte-identically to today's output.** Every report keeps
the single-time path, so every task already installed on `graphy` and `dobby` keeps its
exact current XML and unit text. No reinstall, no migration, nothing to re-verify on a
machine the author cannot reach.

### Why explicit triggers rather than a native repetition

Windows can express this natively —
`<Repetition><Interval>PT3H</Interval><Duration>PT15H</Duration></Repetition>` — and
`Duration` is exactly the window. systemd cannot: `OnUnitActiveSec=3h` has no duration
bound, so the window would have to be enforced either with additional `OnCalendar` lines or
inside the runner at execution time. That would put one user-facing control in the
scheduler on one platform and in the application on the other.

`OnUnitActiveSec` also measures from the last *activation*, so an 8-minute refresh pushes
each subsequent fire 8 minutes later, compounding — roughly 40 minutes of slip across a
15-hour window, and a different amount on every machine. Windows `<Repetition>` anchors to
the trigger start and does not drift, so the two platforms would disagree about what
"every 3 hours" means. Explicit times drift on neither.

Explicit times are also inspectable: `systemctl list-timers` and Task Scheduler both show
the real hours, matching what the Schedules page says. The `describe` / `manageable` /
`blocking_name` apparatus exists precisely so the app never lies about what it wrote.

## 6. Staleness

A scheduled refresh fails the way a manual one already does: `web.actions.refresh` catches
everything and always records a run in its `finally`, so a failure is a `FAIL` row on the
Runs page whichever way it started, and the next interval tries again. Nothing new.

The banner is the only new behaviour. One helper, read from the data rather than from the
schedule:

```python
def staleness(conn, now, ceiling_hours=MAX_DATA_AGE_HOURS) -> Staleness | None:
    """None when the data is fresh. Otherwise its age, the last refresh that
    actually succeeded, and why the most recent attempt did not."""
```

It joins `page_context` beside `refresh` and `sources`, and renders in `_header.html`,
where `warnings` already appear — so there is one bar on the page that says something is
wrong, not two competing ones.

> ⚠ **This data is 31 hours old.** Last good refresh Sun 3:03 PM · Canvas: login failed ·
> **[Refresh now]**

**[Refresh now]** is a link to the Dashboard, where that control already lives — not a
second place that starts a job. The header would otherwise need its own jobs-worker check,
htmx target and busy state, duplicating a surface that works.

Two constraints:

- **The ceiling is `runner.MAX_DATA_AGE_HOURS`, imported, never re-spelled.** That constant
  already decides when a `--no-refresh` run refuses to print. A banner with its own
  threshold could show a kiosk claiming the data is fine while the 2 PM print fails as
  stale — the app disagreeing with itself about one fact, the class of bug
  `docs/outcomes.md` exists to end.
- **It reports the last *successful* refresh, not the last attempt.** `page_context` shows
  `refreshes.latest(conn)` today, which on a host that has been failing to log in since
  Tuesday is true and useless. Those are different rows and the header holds only one.

The banner is driven purely by snapshot age. It does not know whether a schedule exists,
whether it fired, or whether the machine was asleep; a household that refreshes by hand
once a week gets the same honest banner. Tying it to schedule state would create a second
source of truth about freshness.

## 7. Testing

`tests/conftest.py::_no_real_scheduler` patches `Popen` at call time and blocks `systemctl`
and `schtasks` by program name however the argv is spelled — its own comment notes that
`systemctl --user` would otherwise reach the maintainer's live `lakota-print-sheet.timer`.
No test of this feature can touch a real scheduler. `web_fixtures.FakeScheduling` records
every `install`/`remove` for assertion.

1. **Expansion** — `tests/test_refresh_schedule.py`, pure functions: the seven rows of the
   table in section 5, one case each.
2. **Renderers** — `test_host_scheduling.py`, `test_host_scheduling_linux.py`: N times
   produce N triggers / N `OnCalendar=` lines; a one-element list renders byte-identically
   to today; `data-refresh` renders to a name absent from `_FOREIGN_UNITS` and
   `_FOREIGN_TASKS`, case-folded, asserted against the real sets rather than copies.
3. **Config** — `test_config.py`: `every_hours = "three"`, `days = 5`, `days = "Mon"` and a
   non-table `[refresh]` each keep defaults; a malformed `start`/`end` raises `ConfigError`.
4. **Wiring** — `test_web_schedules.py` with `FakeScheduling`: saving installs one task
   named `data-refresh` with the expected times, disabling removes it, and a report's
   schedule is untouched by either. `test_cli.py`: `refresh --record` reaches
   `web.actions.refresh` with `trigger="schedule"`; bare `refresh` still does not ingest.
5. **Staleness** — against a frozen clock: fresh data yields no banner; data past the
   ceiling yields one naming the last successful refresh rather than the last attempt; and
   one test asserting the banner's threshold **is** `runner.MAX_DATA_AGE_HOURS` by
   identity, so it and the print refusal cannot drift.

**What cannot be tested here.** Every layer stops at the OS scheduler, by policy. Whether
Task Scheduler actually fires a six-trigger task on `graphy` at 09:00 is unprovable in this
suite — the same gap as issue #15 item 2, now with more triggers to get wrong. The
mitigation is that a scheduled refresh writes a `runs` row with `trigger = schedule`, so
the Runs page is the evidence: after one day, either the rows are there or they are not.
That is a check the household can make from the kitchen.

## 8. Out of scope

- **Real-time or on-demand fetching.** Raised in the same conversation. The two sources are
  not comparable: Canvas is a REST API behind OneLogin SSO with `updated_at` on its
  records; HAC is a page scrape in a driven browser with no cheap change signal, and it is
  the gradebook of record. Tiered freshness — frequent Canvas, slow HAC — is plausible and
  the snapshot model already supports it (`stale` is keyed by source and carries its own
  fetch time), but it needs a feasibility spike first: *how cheaply can Canvas be asked
  what changed, without a full pull?* If that pays off it changes this feature's numbers,
  not its shape.
- **Per-source refresh cadence.** Follows the spike, not this work. The `[refresh]` table
  can gain a `sources` key later without a migration.
- **Retiring `dobby`'s hand-written timers.** A household operation, not code. Once a
  refresh schedule is installed on `graphy` and observed firing, `systemctl --user disable
  --now lakota-grades-refresh.timer lakota-print-sheet.timer` is the whole of it. The app
  keeps refusing to touch them either way.
- **Printing.** Unchanged. A household that prints keeps its report schedules; one that
  reads a kiosk can schedule refreshes and no prints at all, which is the maintainer's
  stated intent.

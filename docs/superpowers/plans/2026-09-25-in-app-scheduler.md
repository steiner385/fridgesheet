# In-app scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The web server fires every schedule itself — the data refresh and every report — on Windows and Linux, and Fridge Sheet stops registering Task Scheduler tasks and systemd timers.

**Architecture:** A pure planner (`fridgesheet/schedule_plan.py`) decides which schedule is due from `config.toml` and a `schedule_fires` table. A daemon thread in the server (`fridgesheet/web/clock.py`) asks it once a minute and submits the due run to the existing one-at-a-time `jobs.Worker` as one of two new internal job kinds. The OS adapters shrink to one job: removing what older versions registered.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, SQLite, `zoneinfo`, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-25-in-app-scheduler-design.md`

## Global Constraints

- The test command is `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest` (a set `PYTHONPATH` shadows the `tests` package; worktrees have no `.venv` of their own). Every "Run:" line below uses it; it is abbreviated `PYTEST` from here on.
- No test may run the real `systemctl` or `schtasks`; `tests/conftest.py`'s `_no_real_scheduler` enforces it. Every OS call takes an injectable `run=`.
- `config.toml` stays the only record of what is scheduled: `[reports.<key>]` (`enabled`, `time`, `days`, `printer`, `print`) and `[refresh]` (`enabled`, `every_hours`, `start`, `end`, `days`), formats unchanged.
- Schedule keys are unchanged: a report key (`open-work`, `view:3`) and `host.DATA_REFRESH_KEY` (`"data-refresh"`) for the refresh. The refresh's *runs* are recorded under report key `"refresh"`.
- Slot times are wall-clock times in `settings.timezone`.
- **Compare aware datetimes in UTC only.** Python ignores `fold` when both sides share a `tzinfo`, so two 01:30s on the fall-back night compare equal by wall time. Every comparison in `schedule_plan` goes through `_utc(dt) = dt.astimezone(timezone.utc)`.
- A scheduled report runs `runner.run(key, RunOptions(no_refresh=True, trigger="schedule"), settings)`: never `force`, `reprint` or `force_print`.
- `Fridge Sheet - web` (Windows, `service_windows.NAME`) and `fridgesheet-web.service` (Linux, `service_linux.UNIT_FILE`) are never removed by anything in this plan.
- The database moves to **schema 6** (`SCHEMA_VERSION` is already 5 on `main`; the spec's "schema 5" predates that and is corrected in Task 8).
- Copy the parent reads is plain words, no jargon: "Schedules are paused", "has not run on a schedule yet", "next: today 2:00 PM".
- Commit messages for code tasks carry no `[skip release]`; the docs-only commit in Task 8 does not need one either (it ships with the code).
- End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Fall-back night, 01:30 twice.** A refresh at 01:30 on 2026-11-01 (America/New_York) fires once, at the first 01:30 — pinned in Task 2 (`test_fall_back_repeat_fires_once`).
2. **Server started for the first time at 4 PM with a 2 PM report on.** Nothing prints on startup; the first print is tomorrow's 2 PM — pinned in Task 4 (`test_first_sight_does_not_fire`).
3. **Parent clicks Preview at 13:59 and it is still building at 14:00.** The 2 PM print is not lost; it fires on the next free tick — pinned in Task 4 (`test_busy_worker_defers_to_next_tick`).
4. **Report deleted while scheduled.** Its `[reports.view:N]` table is removed by the existing `forget()`, and the clock never tries to run a key that no longer resolves — pinned in Task 4 (`test_a_key_that_no_longer_resolves_is_ignored`).
5. **Cleanup meets the web server's own task in another casing** (`Fridge Sheet - WEB`). It is left alone — pinned in Task 7 (`test_windows_leftovers_never_include_the_web_task`).

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `fridgesheet/web/db.py` | modify | schema 6: `schedule_fires` |
| `fridgesheet/web/stores/fires.py` | create | read/write `schedule_fires` |
| `fridgesheet/schedule_plan.py` | create | pure: `Schedule`, `schedules_from`, `latest_slot`, `next_run`, `due` |
| `fridgesheet/web/actions.py` | modify | `scheduled_run`; `status_line` reads the plan |
| `fridgesheet/web/jobs.py` | modify | `scheduled-refresh`, `scheduled-report` kinds, gated |
| `fridgesheet/web/clock.py` | create | the tick, the thread, the heartbeat, `configured()`, `current()`, `start_background()` (clock + startup cleanup) |
| `fridgesheet/web/server.py` | modify | call `clock.start_background` after `create_app` — the real server only, never a test app |
| `fridgesheet/web/app.py` | modify | paused warning in the header |
| `fridgesheet/web/schedules.py` | modify | rows from config + plan + runs; saves write config only |
| `fridgesheet/web/routes/schedules.py`, `routes/settings.py` | modify | pass `now`, notices |
| `fridgesheet/web/templates/schedules.html` | modify | next run, last scheduled run, notices |
| `fridgesheet/doctor.py` | modify | `_scheduler` from the plan and the heartbeat |
| `fridgesheet/cli.py` | modify | `schedule show` / `remove <key>` / `remove --all`; `install` gone |
| `fridgesheet/host/scheduling.py`, `scheduling_windows.py`, `scheduling_linux.py` | shrink | `remove_os_leftovers()` only |
| `fridgesheet/host/task.xml` | delete | |
| `packaging/windows/FridgeSheet.spec`, `smoke.ps1` | modify | drop `task.xml`; smoke the cleanup instead of install |
| `docs/release-checklist.md`, `docs/product/features/report-scheduling.md`, the spec | modify | describe the new behaviour |

---

### Task 1: The `schedule_fires` table and its store

**Files:**
- Modify: `fridgesheet/web/db.py` (`SCHEMA_VERSION`, new `_SCHEMA_V6`, `migrate`)
- Create: `fridgesheet/web/stores/fires.py`
- Test: `tests/test_schedule_fires.py`

**Interfaces:**
- Produces: `db.SCHEMA_VERSION == 6`; table `schedule_fires(key TEXT PRIMARY KEY, slot TEXT NOT NULL)`; `fires.all(conn) -> dict[str, datetime]`; `fires.record(conn, key: str, slot: datetime) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_schedule_fires.py
"""The last slot each schedule fired: what stops a restart firing it twice."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web import db
from fridgesheet.web.stores import fires

TZ = ZoneInfo("America/New_York")


def test_a_new_database_has_the_table_and_no_rows(tmp_path):
    conn = db.open_db(tmp_path)
    assert db.SCHEMA_VERSION == 6
    assert fires.all(conn) == {}


def test_record_then_read_back_keeps_the_instant(tmp_path):
    conn = db.open_db(tmp_path)
    slot = datetime(2026, 9, 25, 14, 0, tzinfo=TZ)
    fires.record(conn, "open-work", slot)
    got = fires.all(conn)["open-work"]
    assert got == slot and got.utcoffset() == slot.utcoffset()


def test_recording_again_replaces_the_slot(tmp_path):
    conn = db.open_db(tmp_path)
    fires.record(conn, "data-refresh", datetime(2026, 9, 25, 5, 0, tzinfo=TZ))
    fires.record(conn, "data-refresh", datetime(2026, 9, 25, 7, 0, tzinfo=TZ))
    assert fires.all(conn) == {"data-refresh": datetime(2026, 9, 25, 7, 0, tzinfo=TZ)}


def test_a_version_5_file_migrates_to_6(tmp_path):
    conn = db.open_db(tmp_path)
    conn.execute("DROP TABLE schedule_fires")
    conn.execute("UPDATE schema_version SET version = 5")
    assert db.migrate(conn) == 6
    assert fires.all(conn) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST tests/test_schedule_fires.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.web.stores.fires'`

- [ ] **Step 3: Add the migration**

In `fridgesheet/web/db.py`: set `SCHEMA_VERSION = 6`; after `_SCHEMA_V4` add

```python
_SCHEMA_V6 = """
-- The last slot each schedule fired, per schedule key (a report key, or "data-refresh").
-- An ISO datetime with its UTC offset. What stops a restart firing a slot twice, and what
-- lets a slot missed while the server was down be caught up once (web/clock.py).
CREATE TABLE schedule_fires (
    key TEXT PRIMARY KEY,
    slot TEXT NOT NULL
);
"""
```

and at the end of `migrate`, before `return v`:

```python
    if v < 6:
        conn.executescript("BEGIN;\n" + _SCHEMA_V6 + "\nUPDATE schema_version SET version = 6;\nCOMMIT;")
        v = 6
```

Also update the module docstring's sentence "Schedules are *not* here" to: "Schedules are *not* here: `config.toml`'s `[reports.<key>]` and `[refresh]` hold them; `schedule_fires` only remembers the last slot each one fired (see the `schedules` table below, which nothing reads or writes)."

- [ ] **Step 4: Create the store**

```python
# fridgesheet/web/stores/fires.py
"""`schedule_fires`: the last slot each schedule fired. Written by the clock, read by it and
by nothing else -- the Runs page, not this table, is what a parent reads."""
from __future__ import annotations

import sqlite3
from datetime import datetime


def all(conn: sqlite3.Connection) -> dict[str, datetime]:
    return {r["key"]: datetime.fromisoformat(r["slot"]) for r in conn.execute("SELECT key, slot FROM schedule_fires")}


def record(conn: sqlite3.Connection, key: str, slot: datetime) -> None:
    conn.execute("INSERT INTO schedule_fires(key, slot) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET slot = excluded.slot", (key, slot.isoformat()))
```

- [ ] **Step 5: Run the tests**

Run: `PYTEST tests/test_schedule_fires.py tests/test_web_db.py tests/test_doctor.py -q`
Expected: all pass (the db and doctor tests compare against `db.SCHEMA_VERSION`, not a literal).

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/db.py fridgesheet/web/stores/fires.py tests/test_schedule_fires.py
git commit -m "Schema 6: schedule_fires, the last slot each schedule fired"
```

---

### Task 2: The planner, `schedule_plan`

**Files:**
- Create: `fridgesheet/schedule_plan.py`
- Test: `tests/test_schedule_plan.py`

**Interfaces:**
- Consumes: `refresh_schedule.refresh_times(start, end, every_hours) -> list[str]` (raises `config.ConfigError`); `host.DAY_NAMES`, `host.TIME_RE`, `host.DATA_REFRESH_KEY`; `config.Settings.refresh`, `Settings.report_config(key, default_time)`.
- Produces:
  - `Schedule(key: str, title: str, times: tuple[str, ...], days: tuple[str, ...])` (frozen dataclass)
  - `Due(slot: datetime, fire: bool)` (frozen dataclass; `fire=False` means first sight: record, do not run)
  - `REFRESH_TITLE = "Data refresh"`
  - `schedules_from(settings, reports: list[tuple[str, str, str]]) -> tuple[list[Schedule], dict[str, str]]` — `reports` is `(key, title, default_time)`; returns enabled schedules (refresh first, then reports sorted by key) and `{key: problem}` for ones that cannot run
  - `latest_slot(schedule, now) -> datetime | None`
  - `next_run(schedule, now) -> datetime | None`
  - `due(schedule, now, last_fired: datetime | None) -> Due | None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_schedule_plan.py
"""Which schedule is due, and when each runs next. Pure: no clock, no files, no threads."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet import config, host
from fridgesheet.schedule_plan import Due, Schedule, due, latest_slot, next_run, schedules_from

TZ = ZoneInfo("America/New_York")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
ALL = host.DAY_NAMES
PRINT = Schedule("open-work", "Open Work Sheet", ("14:00",), WEEKDAYS)
REFRESH = Schedule(host.DATA_REFRESH_KEY, "Data refresh", ("05:00", "07:00", "09:00"), ALL)


def at(y, mo, d, h, mi=0, fold=0):
    return datetime(y, mo, d, h, mi, tzinfo=TZ, fold=fold)


# 2026-09-25 is a Friday.

def test_not_yet_due_before_the_time():
    assert latest_slot(PRINT, at(2026, 9, 25, 13, 59)) == at(2026, 9, 24, 14)


def test_due_exactly_on_the_minute():
    assert latest_slot(PRINT, at(2026, 9, 25, 14, 0)) == at(2026, 9, 25, 14)


def test_the_latest_of_several_times_is_the_slot():
    assert latest_slot(REFRESH, at(2026, 9, 25, 8, 30)) == at(2026, 9, 25, 7)


def test_a_day_not_ticked_is_skipped():
    # Sunday 2026-09-27 at 15:00: the latest weekday slot is Friday's.
    assert latest_slot(PRINT, at(2026, 9, 27, 15)) == at(2026, 9, 25, 14)


def test_no_days_means_no_slot():
    assert latest_slot(Schedule("x", "x", ("14:00",), ()), at(2026, 9, 25, 15)) is None


def test_first_sight_records_without_firing():
    assert due(PRINT, at(2026, 9, 25, 16), None) == Due(at(2026, 9, 25, 14), fire=False)


def test_a_new_slot_fires():
    assert due(PRINT, at(2026, 9, 25, 14, 1), at(2026, 9, 24, 14)) == Due(at(2026, 9, 25, 14), fire=True)


def test_an_already_fired_slot_does_not_fire_again():
    assert due(PRINT, at(2026, 9, 25, 14, 30), at(2026, 9, 25, 14)) is None


def test_a_weekend_asleep_is_one_catch_up_not_many():
    # Last fired Friday 07:00; woken Monday 08:00. Only Monday's 07:00 is due.
    assert due(REFRESH, at(2026, 9, 28, 8), at(2026, 9, 25, 7)) == Due(at(2026, 9, 28, 7), fire=True)


def test_last_fired_in_another_offset_compares_by_instant():
    # Stored as UTC text; read back with a fixed offset. Same instant as 14:00 EDT.
    last = datetime.fromisoformat("2026-09-25T18:00:00+00:00")
    assert due(PRINT, at(2026, 9, 25, 15), last) is None


def test_spring_forward_gap_has_no_slot_that_day():
    # 2026-03-08: 02:00 -> 03:00 in America/New_York. 02:30 does not exist.
    s = Schedule("x", "x", ("02:30",), ALL)
    assert latest_slot(s, at(2026, 3, 8, 4)) == at(2026, 3, 7, 2, 30)


def test_fall_back_repeat_fires_once():
    # 2026-11-01: 01:30 happens twice. The slot is the first (fold=0); the second is not due.
    s = Schedule("x", "x", ("01:30",), ALL)
    first = at(2026, 11, 1, 1, 30, fold=0)
    assert due(s, at(2026, 11, 1, 1, 45, fold=0), at(2026, 10, 31, 1, 30)) == Due(first, fire=True)
    assert due(s, at(2026, 11, 1, 1, 45, fold=1), first) is None


def test_a_clock_moved_backwards_fires_nothing():
    assert due(PRINT, at(2026, 9, 25, 12), at(2026, 9, 25, 14)) is None


def test_next_run_later_today():
    assert next_run(PRINT, at(2026, 9, 25, 9)) == at(2026, 9, 25, 14)


def test_next_run_on_the_minute_is_the_next_one():
    assert next_run(PRINT, at(2026, 9, 24, 14)) == at(2026, 9, 25, 14)


def test_next_run_skips_the_weekend():
    assert next_run(PRINT, at(2026, 9, 25, 15)) == at(2026, 9, 28, 14)


def test_next_run_with_no_days_is_none():
    assert next_run(Schedule("x", "x", ("14:00",), ()), at(2026, 9, 25, 9)) is None


REPORTS = [("open-work", "Open Work Sheet", "14:00"), ("view:3", "Grade trend", "07:00")]


def _settings(doc):
    s = config.Settings()
    config.settings_from_doc(doc, s)
    return s


def test_schedules_from_lists_enabled_ones_refresh_first():
    s = _settings({"refresh": {"enabled": True, "every_hours": 2, "start": "05:00", "end": "09:00"},
                   "reports": {"view:3": {"enabled": True, "time": "07:15", "days": ["Mon"]},
                               "open-work": {"enabled": True}}})
    got, problems = schedules_from(s, REPORTS)
    assert [x.key for x in got] == [host.DATA_REFRESH_KEY, "open-work", "view:3"]
    assert got[0].times == ("05:00", "07:00", "09:00")
    assert got[1].times == ("14:00",) and got[2] == Schedule("view:3", "Grade trend", ("07:15",), ("Mon",))
    assert problems == {}


def test_disabled_and_unknown_keys_are_left_out():
    s = _settings({"reports": {"open-work": {"enabled": False}, "view:99": {"enabled": True}}})
    assert schedules_from(s, REPORTS) == ([], {})


def test_a_refresh_that_does_not_expand_is_a_problem_not_a_schedule():
    s = _settings({"refresh": {"enabled": True, "every_hours": 3, "start": "06:00", "end": "21:00"}})
    s.refresh.end = "05:00"                       # past the loader's own checks: a hand edit
    got, problems = schedules_from(s, REPORTS)
    assert got == [] and "overnight" in problems[host.DATA_REFRESH_KEY]


def test_an_enabled_report_with_no_days_is_not_a_schedule():
    s = _settings({"reports": {"open-work": {"enabled": True, "days": []}}})
    assert schedules_from(s, REPORTS) == ([], {})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTEST tests/test_schedule_plan.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.schedule_plan'`

- [ ] **Step 3: Write the implementation**

```python
# fridgesheet/schedule_plan.py
"""Which schedule is due, and when each one runs next.

Pure functions over settings, a moment and the last slot each schedule fired: no clock of
its own, no files, no threads. `web/clock.py` is what calls this once a minute and acts on it.

A schedule's *slots* are every configured time on every configured day, as wall-clock times
in the settings' time zone. Only the latest slot at or before now is ever due, so a machine
asleep for a weekend catches up once, not once per missed slot.

Every comparison is made in UTC. Python compares two aware datetimes that share a `tzinfo`
by wall time and ignores `fold`, so the two 01:30s of a fall-back night would compare equal;
in UTC they are an hour apart, which is what they are.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from . import host, refresh_schedule
from .config import ConfigError

REFRESH_TITLE = "Data refresh"
#: How far back `latest_slot` and forward `next_run` look. A week covers every day a
#: schedule can name.
HORIZON_DAYS = 7


@dataclass(frozen=True)
class Schedule:
    key: str                      # a report key, or host.DATA_REFRESH_KEY
    title: str
    times: tuple[str, ...]        # HH:MM
    days: tuple[str, ...]         # host.DAY_NAMES entries


@dataclass(frozen=True)
class Due:
    slot: datetime
    fire: bool                    # False: first sight -- record the slot, run nothing


def _utc(d: datetime) -> datetime:
    return d.astimezone(timezone.utc)


def _slot(day: date, hhmm: str, tz) -> datetime | None:
    """`hhmm` on `day` in `tz`, or None when that wall time does not exist that day (the
    spring-forward gap). A repeated wall time (fall back) is its first occurrence."""
    h, m = (int(x) for x in hhmm.split(":"))
    naive = datetime.combine(day, time(h, m))
    local = naive.replace(tzinfo=tz, fold=0)
    if _utc(local).astimezone(tz).replace(tzinfo=None) != naive:
        return None
    return local


def _slots_on(schedule: Schedule, day: date, tz) -> list[datetime]:
    if host.DAY_NAMES[day.weekday()] not in schedule.days:
        return []
    return sorted((s for t in schedule.times if (s := _slot(day, t, tz)) is not None), key=_utc)


def latest_slot(schedule: Schedule, now: datetime) -> datetime | None:
    tz = now.tzinfo
    for back in range(HORIZON_DAYS + 1):
        passed = [s for s in _slots_on(schedule, now.date() - timedelta(days=back), tz) if _utc(s) <= _utc(now)]
        if passed:
            return passed[-1]
    return None


def next_run(schedule: Schedule, now: datetime) -> datetime | None:
    tz = now.tzinfo
    for ahead in range(HORIZON_DAYS + 1):
        later = [s for s in _slots_on(schedule, now.date() + timedelta(days=ahead), tz) if _utc(s) > _utc(now)]
        if later:
            return later[0]
    return None


def due(schedule: Schedule, now: datetime, last_fired: datetime | None) -> Due | None:
    latest = latest_slot(schedule, now)
    if latest is None:
        return None
    if last_fired is None:
        return Due(latest, fire=False)
    if _utc(latest) > _utc(last_fired):
        return Due(latest, fire=True)
    return None


def schedules_from(settings, reports: list[tuple[str, str, str]]) -> tuple[list[Schedule], dict[str, str]]:
    """The enabled schedules, the refresh first and then reports by key, and a problem per key
    that is on but cannot run. `reports` is `(key, title, default_time)` for every report
    that exists: a `[reports.<key>]` table whose key no longer resolves is ignored."""
    out: list[Schedule] = []
    problems: dict[str, str] = {}
    rc = settings.refresh
    if rc.enabled and rc.days:
        try:
            times = refresh_schedule.refresh_times(rc.start, rc.end, rc.every_hours)
            out.append(Schedule(host.DATA_REFRESH_KEY, REFRESH_TITLE, tuple(times), tuple(rc.days)))
        except ConfigError as e:
            problems[host.DATA_REFRESH_KEY] = str(e)
    for key, title, default_time in sorted(reports):
        r = settings.report_config(key, default_time)
        if not (r.enabled and r.days):
            continue
        if not host.TIME_RE.match(str(r.time)):
            problems[key] = f"[reports.{key}] time must be HH:MM (24-hour), got {r.time!r}"
            continue
        out.append(Schedule(key, title, (r.time,), tuple(r.days)))
    return out, problems
```

- [ ] **Step 4: Run the tests**

Run: `PYTEST tests/test_schedule_plan.py -v`
Expected: all pass. If `test_a_refresh_that_does_not_expand...` fails because `RefreshConfig` is frozen or the loader rejects it earlier, build `s.refresh = config.RefreshConfig(enabled=True, start="06:00", end="05:00")` directly instead — the point is a refresh the expander refuses.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/schedule_plan.py tests/test_schedule_plan.py
git commit -m "schedule_plan: which schedule is due, and when each runs next"
```

---

### Task 3: Two internal job kinds

**Files:**
- Modify: `fridgesheet/web/actions.py` (add `scheduled_run` after `print_now`)
- Modify: `fridgesheet/web/jobs.py` (`KINDS`, `LABELS`, `GATED`, `_run`)
- Test: `tests/test_scheduled_jobs.py`

**Interfaces:**
- Consumes: `actions.refresh(*, home, log, settings, trigger)`, `runner.run`, `runner.RunOptions`.
- Produces: `actions.scheduled_run(*, home, log, settings=None, report_key, run=None) -> int`; job kinds `"scheduled-refresh"` (no params) and `"scheduled-report"` (param `report`), both in `jobs.GATED`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_scheduled_jobs.py
"""What a scheduled run does: the Refresh button's path, and the OS task's old command line."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fridgesheet import config, runner
from fridgesheet.web import actions, jobs
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed

TZ = ZoneInfo("America/New_York")


def test_scheduled_run_keeps_every_guard(tmp_path):
    seen = {}

    def fake_run(key, opts, settings, echo=None):
        seen["key"], seen["opts"] = key, opts
        return 0

    rc = actions.scheduled_run(home=tmp_path, log=lambda _l: None, settings=config.Settings(home=tmp_path),
                               report_key="view:3", run=fake_run)
    assert rc == 0 and seen["key"] == "view:3"
    o = seen["opts"]
    assert (o.no_refresh, o.trigger, o.force, o.reprint, o.force_print, o.dry_run) == (True, "schedule", False, False, False, False)


class _Actions:
    def __init__(self):
        self.calls = []

    def refresh(self, **kw):
        self.calls.append(("refresh", kw["trigger"]))
        return SimpleNamespace(ok=True, message="refresh 1: ok")

    def scheduled_run(self, **kw):
        self.calls.append(("report", kw["report_key"]))
        kw["log"]("OK printed")
        return 0


def _worker(tmp_path, acts):
    state = SimpleNamespace(settings=config.Settings(home=tmp_path), home=tmp_path,
                            now=lambda: datetime(2026, 9, 25, 14, tzinfo=TZ))
    return jobs.Worker(state, actions=acts)


def test_scheduled_refresh_records_as_schedule(tmp_path):
    acts = _Actions()
    w = _worker(tmp_path, acts)
    job = w.submit("scheduled-refresh")
    w.run_pending()
    assert acts.calls == [("refresh", "schedule")] and job.outcome == "OK"


def test_scheduled_report_runs_the_named_report(tmp_path):
    acts = _Actions()
    w = _worker(tmp_path, acts)
    job = w.submit("scheduled-report", report="open-work")
    w.run_pending()
    assert acts.calls == [("report", "open-work")] and job.outcome == "OK"


def test_neither_kind_can_be_started_from_the_open_route(tmp_path):
    assert {"scheduled-refresh", "scheduled-report"} <= set(jobs.GATED)
    assert not {"scheduled-refresh", "scheduled-report"} & set(jobs.OPEN_KINDS)
    seed(tmp_path).close()
    c = app_for(tmp_path)                                  # the kind check comes before the worker lookup
    for kind in ("scheduled-refresh", "scheduled-report"):
        assert c.post(f"/jobs/{kind}", headers=LOCAL_HOST_HEADERS).status_code == 404
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST tests/test_scheduled_jobs.py -v`
Expected: FAIL — `AttributeError: module 'fridgesheet.web.actions' has no attribute 'scheduled_run'`

- [ ] **Step 3: Add `scheduled_run`** in `fridgesheet/web/actions.py`, directly after `print_now`:

```python
def scheduled_run(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
                  report_key: str, run=None) -> int:
    """A report's scheduled run, fired by the server's own clock (web/clock.py).

    Exactly the command the OS task used to run -- `run <key> --no-refresh --trigger
    schedule` -- so every guard the runner has still decides: no-print days, already printed
    today, the print window (a catch-up the next morning is a SKIP, not yesterday's sheet),
    the stale-snapshot refusal, the report's own printer and its PDF-only switch. Not
    `print_now`, which forces past all of those because a person asked for paper."""
    settings = settings or config.load_settings()
    run = run or runner.run
    with forward_logs(log):
        return run(report_key, runner.RunOptions(no_refresh=True, trigger="schedule"), settings, echo=log)
```

- [ ] **Step 4: Add the job kinds** in `fridgesheet/web/jobs.py`:

```python
KINDS = ("refresh", "preview", "print", "reprint", "doctor", "login", "update",
         "scheduled-refresh", "scheduled-report")
LABELS = {"refresh": "Refreshing", "preview": "Building today's sheet", "print": "Printing",
          "reprint": "Printing again", "doctor": "Running diagnostics", "login": "Testing the login",
          "update": "Updating Fridge Sheet",
          "scheduled-refresh": "Refreshing on schedule", "scheduled-report": "Running a scheduled report"}
```

Change `GATED = ("update",)` to

```python
#: `scheduled-*` are the server's own clock's (web/clock.py): started by nothing a request can
#: reach, so the Runs page's "On a schedule" always means the clock, never a POST.
GATED = ("update", "scheduled-refresh", "scheduled-report")
```

and extend the comment above it by one line naming the two new kinds. In `_run`, before `elif job.kind == "doctor":`, add

```python
            elif job.kind == "scheduled-refresh":
                r = self.actions.refresh(home=home, log=log, settings=settings, trigger="schedule")
                outcome, message = ("OK" if r.ok else "FAIL"), r.message
            elif job.kind == "scheduled-report":
                rc = self.actions.scheduled_run(home=home, log=log, settings=settings,
                                                report_key=job.params["report"])
                outcome, message = ("OK" if rc == 0 else "FAIL"), (job.lines[-1] if job.lines else "")
```

- [ ] **Step 5: Run the tests**

Run: `PYTEST tests/test_scheduled_jobs.py tests/test_jobs_service_residuals.py tests/test_web_jobs.py -q` (skip any file that does not exist)
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/actions.py fridgesheet/web/jobs.py tests/test_scheduled_jobs.py
git commit -m "Two internal job kinds: a scheduled refresh and a scheduled report"
```

---

### Task 4: The clock

**Files:**
- Create: `fridgesheet/web/clock.py`
- Modify: `fridgesheet/web/app.py` (`create_app`'s `if worker:` block; `AppState.warnings`)
- Test: `tests/test_clock.py`

**Interfaces:**
- Consumes: `schedule_plan.schedules_from`, `schedule_plan.due`; `fires.all`, `fires.record`; `jobs.Worker.submit(kind, **params) -> Job | None`; `reports.available(home)`; `actions._settings_for(home)`.
- Produces:
  - `clock.TICK_SECONDS = 60`, `clock.STALE_AFTER = timedelta(minutes=3)`
  - `clock.PAUSED = "Schedules are paused: the scheduler inside Fridge Sheet has stopped. Restart Fridge Sheet."`
  - `clock.configured(home, settings=None) -> tuple[list[Schedule], dict[str, str]]`
  - `class Clock(state, *, submit=None)` with `tick(now) -> str | None` (the key submitted, if any), `stale(now) -> bool`, `last_tick: datetime | None`, `problems: dict[str, str]`, `start() -> None`
  - `clock.current() -> Clock | None` — the clock started in this process
  - `clock.start_background(state) -> Clock` — called once by `server.run`; Task 7 adds the cleanup thread to it
  - `state.extra["clock"]` holds the running `Clock`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_clock.py
"""The server's own clock, driven one tick at a time: no thread, no sleep."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fridgesheet import config, host
from fridgesheet.web import clock as clockmod, db
from fridgesheet.web.stores import fires

TZ = ZoneInfo("America/New_York")


def at(d, h, mi=0):
    return datetime(2026, 9, d, h, mi, tzinfo=TZ)


def _write(home, doc):
    config.save_config_doc(home / "config.toml", doc)


class FakeWorker:
    def __init__(self, busy=False):
        self.busy, self.submitted = busy, []

    def submit(self, kind, **params):
        if self.busy:
            return None
        self.submitted.append((kind, params))
        return object()


def _clock(home, worker):
    db.open_db(home).close()
    state = SimpleNamespace(home=home)
    return clockmod.Clock(state, submit=worker.submit)


ON_2PM = {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]}}}


def _fired(home):
    conn = db.open_db(home)
    try:
        return fires.all(conn)
    finally:
        conn.close()


def test_first_sight_does_not_fire(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    assert c.tick(at(25, 16)) is None and w.submitted == []
    assert _fired(tmp_path) == {"open-work": at(25, 14)}


def test_a_due_slot_is_submitted_and_recorded(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))                                  # first sight: records Thursday's 14:00
    assert c.tick(at(25, 14)) == "open-work"
    assert w.submitted == [("scheduled-report", {"report": "open-work"})]
    assert _fired(tmp_path)["open-work"] == at(25, 14)


def test_busy_worker_defers_to_next_tick(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    w.busy = True
    assert c.tick(at(25, 14)) is None and _fired(tmp_path)["open-work"] == at(24, 14)
    w.busy = False
    assert c.tick(at(25, 14, 1)) == "open-work"


def test_a_restart_does_not_fire_the_same_slot_again(tmp_path):
    _write(tmp_path, ON_2PM)
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    c.tick(at(25, 14))
    again = _clock(tmp_path, w)
    assert again.tick(at(25, 14, 5)) is None and len(w.submitted) == 1


def test_one_job_per_tick_refresh_first(tmp_path):
    _write(tmp_path, {**ON_2PM, "refresh": {"enabled": True, "every_hours": 1, "start": "13:00", "end": "14:00"}})
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    assert c.tick(at(25, 14)) == host.DATA_REFRESH_KEY
    assert c.tick(at(25, 14, 1)) == "open-work"
    assert [k for k, _ in w.submitted] == ["scheduled-refresh", "scheduled-report"]


def test_a_key_that_no_longer_resolves_is_ignored(tmp_path):
    _write(tmp_path, {"reports": {"view:42": {"enabled": True, "time": "14:00", "days": ["Fri"]}}})
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    assert c.tick(at(25, 14)) is None and w.submitted == [] and "view:42" not in _fired(tmp_path)


def test_a_broken_schedule_does_not_block_the_others(tmp_path):
    _write(tmp_path, {**ON_2PM, "refresh": {"enabled": True, "every_hours": 1, "start": "06:00", "end": "21:00"}})
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.tick(at(25, 9))
    assert host.DATA_REFRESH_KEY in c.problems             # 16 a day is over the cap of 12
    assert c.tick(at(25, 14)) == "open-work"


def test_a_raising_tick_is_logged_and_the_next_still_runs(tmp_path, caplog):
    (tmp_path / "config.toml").write_text("this is [not toml", encoding="utf-8")
    w = FakeWorker()
    c = _clock(tmp_path, w)
    c.safe_tick(at(25, 9))                                 # never raises
    assert "clock tick failed" in caplog.text and c.last_tick is None
    _write(tmp_path, ON_2PM)
    c.safe_tick(at(25, 10))
    assert c.last_tick == at(25, 10)


def test_the_heartbeat_goes_stale(tmp_path):
    _write(tmp_path, ON_2PM)
    c = _clock(tmp_path, FakeWorker())
    assert c.stale(at(25, 9))                              # never ticked
    c.tick(at(25, 9))
    assert not c.stale(at(25, 9, 2)) and c.stale(at(25, 9, 4))
```

- [ ] **Step 2: Run to verify it fails**

Run: `PYTEST tests/test_clock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.web.clock'`

- [ ] **Step 3: Write the clock**

```python
# fridgesheet/web/clock.py
"""The server's own clock: fires every schedule in `config.toml` (spec 2026-09-25).

Once a minute: read the settings fresh, ask `schedule_plan` which schedule is due, submit it
to the one jobs worker, and record the slot in `schedule_fires` once the worker took it. A
busy worker takes nothing and nothing is recorded, so the next minute tries again. At most
one job per tick, refresh first: the worker runs one at a time anyway, and a refresh due in
the same minute as a print should finish before the print reads the snapshot.

This replaced the OS scheduler. Task Scheduler ran every task "only when the user is logged
on", and on the household's kiosk the app's account never is -- not one schedule ever fired.
The server runs as the right account and is always up; it is the one place that can.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from .. import host, reports as registry, schedule_plan
from . import db
from .stores import fires

log = logging.getLogger("fridgesheet.web.clock")

TICK_SECONDS = 60
STALE_AFTER = timedelta(minutes=3)
PAUSED = "Schedules are paused: the scheduler inside Fridge Sheet has stopped. Restart Fridge Sheet."

_current: "Clock | None" = None


def current() -> "Clock | None":
    """The clock running in this process, None outside the server (the CLI, doctor from a
    terminal)."""
    return _current


def configured(home: Path, settings=None) -> tuple[list[schedule_plan.Schedule], dict[str, str]]:
    """Every enabled schedule for `home`, and a problem per one that cannot run. The one place
    that reads the report list for the planner, so the page, doctor and the clock agree."""
    if settings is None:
        from .actions import _settings_for
        settings = _settings_for(home)
    reports = [(r.key, r.title, r.default_time) for r in registry.available(home)]
    return schedule_plan.schedules_from(settings, reports)


class Clock:
    def __init__(self, state, *, submit=None):
        self.state = state
        self._submit = submit or (lambda kind, **p: state.jobs.submit(kind, **p))
        self.last_tick: datetime | None = None
        self.problems: dict[str, str] = {}
        self._thread: threading.Thread | None = None

    def tick(self, now: datetime) -> str | None:
        schedules, self.problems = configured(self.state.home)
        conn = db.open_db(self.state.home)
        try:
            fired = fires.all(conn)
            submitted, tried = None, False
            for s in schedules:
                d = schedule_plan.due(s, now, fired.get(s.key))
                if d is None:
                    continue
                if not d.fire:
                    fires.record(conn, s.key, d.slot)          # first sight: this slot is past
                    continue
                if tried:
                    continue                                   # one job per tick
                tried = True
                job = (self._submit("scheduled-refresh") if s.key == host.DATA_REFRESH_KEY
                       else self._submit("scheduled-report", report=s.key))
                if job is None:
                    continue                                   # busy: the next tick tries again
                try:
                    fires.record(conn, s.key, d.slot)
                except Exception as e:                         # noqa: BLE001  the job is already running
                    log.warning("could not record that %s fired at %s: %s", s.key, d.slot, e)
                submitted = s.key
        finally:
            conn.close()
        self.last_tick = now
        return submitted

    def safe_tick(self, now: datetime) -> None:
        """`tick`, never raising: one bad minute is a log line, not a dead clock. A failed tick
        does not stamp the heartbeat, so a clock failing every minute shows as paused."""
        try:
            self.tick(now)
        except Exception:                                      # noqa: BLE001
            log.exception("clock tick failed")

    def stale(self, now: datetime) -> bool:
        return self.last_tick is None or now - self.last_tick > STALE_AFTER

    def start(self) -> None:
        global _current
        _current = self
        stop = threading.Event()

        def loop() -> None:
            while not stop.is_set():
                self.safe_tick(self.state.now())
                stop.wait(TICK_SECONDS)

        self._thread = threading.Thread(target=loop, name="fridgesheet-clock", daemon=True)
        self._thread.start()
```

- [ ] **Step 4: Run the clock tests**

Run: `PYTEST tests/test_clock.py -v`
Expected: all pass. (`test_the_heartbeat_goes_stale` relies on `tick` stamping `last_tick`; `test_a_raising_tick...` relies on a parse error in `config.toml` raising out of `configured`.)

- [ ] **Step 5: Start it from the real server, and warn in the header** — the clock starts in `server.run`, not in `create_app`: five test files build apps with `create_app(worker=True)` and must not get a background clock (or, after Task 7, a cleanup thread reaching the real `systemctl`/`schtasks`). In `fridgesheet/web/clock.py` add:

```python
def start_background(state) -> "Clock":
    """What the real server starts beside the worker: the clock. `server.run` calls this once;
    `create_app` never does, so no test app ever runs a background clock."""
    c = Clock(state)
    state.extra["clock"] = c
    c.start()
    return c
```

and in `fridgesheet/web/server.py`, directly after `app = create_app(settings, worker=True)`:

```python
        from .clock import start_background
        start_background(app.state.fridgesheet)
```

Then in `AppState.warnings` (`fridgesheet/web/app.py`), append the paused notice:

```python
        out = list(self.extra.get("warnings") or []) + actions.no_print_days_problems(self.home)
        running = self.extra.get("clock")
        if running is not None and running.stale(self.now()):
            from .clock import PAUSED
            out.append(PAUSED)
        return out
```

(Keep the existing docstring; add one sentence: "And the scheduler's own heartbeat: a clock that has stopped ticking says so here.")

Add to `tests/test_clock.py`:

```python
def test_the_header_says_when_schedules_are_paused(tmp_path):
    from tests.web_fixtures import app_for, seed
    seed(tmp_path).close()
    c = app_for(tmp_path)
    stopped = _clock(tmp_path, FakeWorker())                # never ticked: stale
    c.app.state.fridgesheet.extra["clock"] = stopped
    assert clockmod.PAUSED in c.get("/").text
```

- [ ] **Step 6: Run the web tests**

Run: `PYTEST tests/test_clock.py tests/test_web_app.py tests/test_web_pages.py tests/test_web_server.py -q` (skip a file that does not exist)
Expected: all pass. No test goes through `server.run`'s serve path with a real clock; if one does (`grep -n "def serve\|server.run" tests/*.py`), it already stubs `serve` — stub `clock.start_background` beside it with `monkeypatch.setattr(clock, "start_background", lambda state: None)`.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/clock.py fridgesheet/web/app.py fridgesheet/web/server.py tests/test_clock.py
git commit -m "The server's own clock fires schedules once a minute"
```

---

### Task 5: The Schedules page stops asking the OS

**Files:**
- Modify: `fridgesheet/web/schedules.py`, `fridgesheet/web/routes/schedules.py`, `fridgesheet/web/templates/schedules.html`
- Modify: `fridgesheet/web/actions.py` (`status_line`), `fridgesheet/web/routes/settings.py:105`
- Modify tests: `tests/test_web_schedules.py`, `tests/test_web_schedules_page.py`, `tests/test_schedules_residuals.py`, `tests/test_config_errors_and_schedule_off.py`, `tests/test_web_actions.py`, `tests/test_web_settings_page.py`, `tests/web_fixtures.py`

**Interfaces:**
- Consumes: `clock.configured`, `schedule_plan.next_run`, `runs` table, `state.extra["describe_service"]` (a `() -> ServiceInfo`, already stubbed by `app_for`).
- Produces:
  - `Row` gains `next_run: datetime | None`, `last_run: str` (e.g. `"Thu 9/24 2:00 PM, OK"` or `""`), `problem: str`; loses `info`, `unsupported`.
  - `RefreshRow` gains `next_run`, `last_run`; loses `info`, `unsupported`.
  - `rows(home, *, now) -> list[Row]`, `refresh_row(home, *, now) -> RefreshRow`
  - `save(key, *, enabled, time, days, printer, prints, home, log) -> Outcome` — writes config, nothing else
  - `save_refresh(*, enabled, every_hours, start, end, days, home, log) -> Outcome`
  - `forget(key, *, home, log, title="") -> Outcome` — deletes the `[reports.<key>]` table only
  - `record_enabled(home, key, enabled, *, create=True)` — unchanged
  - `last_scheduled(conn, report_key) -> str` — `"Thu 9/24 2:00 PM, OK"` or `""`
  - `actions.status_line(home, *, now) -> str`
- Removed: `_describe_once`, `_unmanageable`, `_installed_or_unknown`, `install_refresh`, `LOGIN_STAMP`, every `scheduling=` parameter.

- [ ] **Step 1: Write the new page tests** — replace the body of `tests/test_web_schedules_page.py` below `test_days_is_hosts_day_names_not_a_fourth_spelling` with:

```python
def _client(tmp_path, now=None):
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    c = app_for(tmp_path, now=now or datetime(2026, 9, 25, 9, 0, tzinfo=TZ))
    c.app.state.fridgesheet.extra["printers"] = ["Brother", "Canon"]
    return c


def test_saving_writes_config_and_names_the_next_run(tmp_path):
    c = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Mon", "Fri"], "printer": "Brother", "prints": "on"})
    assert r.status_code == 200 and "Scheduled: Mon, Fri at 16:30" in r.text
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["view:1"] == {"enabled": True, "time": "16:30", "days": ["Mon", "Fri"],
                                        "printer": "Brother", "print": True}
    assert "next: Fri 9/25 4:30 PM" in r.text


def test_saving_needs_no_test_login(tmp_path):
    c = _client(tmp_path)                                  # no login-ok.txt written
    r = c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    assert "Test login" not in r.text and "Scheduled: Fri at 14:00" in r.text


def test_a_schedule_that_never_ran_says_so(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    assert "has not run on a schedule yet" in c.get("/schedules").text


def test_the_last_scheduled_run_is_shown(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Thu", "Fri"]})
    conn = db.open_db(tmp_path)
    runs.record(conn, "open-work", "2026-09-24T14:00:05-04:00", "2026-09-24T14:01:30-04:00", "schedule", "OK", "printed")
    runs.record(conn, "open-work", "2026-09-24T15:00:00-04:00", "2026-09-24T15:01:00-04:00", "web", "OK", "printed")
    conn.close()
    assert "last: Thu 9/24 2:00 PM, OK" in c.get("/schedules").text


def test_the_refresh_row_shows_next_and_last(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules/refresh", data={"enabled": "on", "every_hours": "2", "start": "05:00", "end": "21:00",
                                       "days": list(host.DAY_NAMES)})
    body = c.get("/schedules").text
    assert "next: Fri 9/25 11:00 AM" in body and "has not run on a schedule yet" in body


def test_turning_off_needs_no_day_and_touches_nothing_else(tmp_path):
    c = _client(tmp_path)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    r = c.post("/schedules", data={"key": "open-work", "time": "14:00"})
    assert "Open Work Sheet is not scheduled." in r.text
    assert tomllib.loads((tmp_path / "config.toml").read_text())["reports"]["open-work"]["enabled"] is False


def test_linux_without_the_service_says_how_to_keep_schedules_running(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seed(tmp_path).close()
    c = app_for(tmp_path, service_installed=False)
    c.post("/schedules", data={"key": "open-work", "enabled": "on", "time": "14:00", "days": ["Fri"]})
    assert "fridgesheet service install" in c.get("/schedules").text


def test_no_service_hint_when_nothing_is_scheduled(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seed(tmp_path).close()
    assert "fridgesheet service install" not in app_for(tmp_path, service_installed=False).get("/schedules").text
```

with imports at the top of the file: `from datetime import datetime`, `from zoneinfo import ZoneInfo`, `from fridgesheet.web.stores import runs`, `TZ = ZoneInfo("America/New_York")`, and drop `FakeScheduling` from the `tests.web_fixtures` import.

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_web_schedules_page.py -v`
Expected: FAIL — `"next: Fri 9/25 4:30 PM"` not in body (and the login test fails on "Test login").

- [ ] **Step 3: Rewrite `fridgesheet/web/schedules.py`**

Module docstring: "The Schedules page's work: `config.toml`'s `[reports.<key>]` and `[refresh]`. Saving writes the file and nothing else -- the server's own clock (web/clock.py) reads it every minute. What the page shows about a schedule comes from the app's own records: the plan's next run and the newest run with `trigger = 'schedule'`."

Replace the dataclasses and functions:

```python
@dataclass(frozen=True)
class Row:
    key: str
    title: str
    enabled: bool
    time: str
    days: list[str]
    printer: str
    prints: bool
    next_run: datetime | None = None
    last_run: str = ""
    problem: str = ""


def last_scheduled(conn, report_key: str) -> str:
    """The newest run this report's schedule made, in words -- "" when there is none."""
    row = conn.execute("SELECT started_at, outcome FROM runs WHERE report_key = ? AND trigger = 'schedule' "
                       "ORDER BY started_at DESC, id DESC LIMIT 1", (report_key,)).fetchone()
    if row is None:
        return ""
    started = datetime.fromisoformat(row["started_at"])
    return f"{dates.wd_md_time(started.replace(second=0, microsecond=0))}, {row['outcome']}"


def _plan(home: Path, now: datetime):
    schedules, problems = clock.configured(home)
    return {s.key: schedule_plan.next_run(s, now) for s in schedules}, problems


def rows(home: Path, *, now: datetime) -> list[Row]:
    s = _settings_for(home)
    nexts, problems = _plan(home, now)
    conn = db.open_db(home)
    try:
        out = []
        for report in registry.available(home):
            rc = s.report_config(report.key, report.default_time)
            out.append(Row(key=report.key, title=report.title, enabled=rc.enabled, time=rc.time or report.default_time,
                           days=list(rc.days), printer=rc.printer, prints=rc.prints,
                           next_run=nexts.get(report.key), last_run=last_scheduled(conn, report.key),
                           problem=problems.get(report.key, "")))
        return out
    finally:
        conn.close()
```

`forget` becomes:

```python
def forget(key: str, *, home: Path, log: Callable[[str], None], title: str = "") -> Outcome:
    """Drop `[reports.<key>]` for a report being deleted. `reports.id` is reissued by sqlite, so a
    left-behind `[reports."view:3"]` would become the *next* report's schedule."""
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    reports = doc.get("reports")
    if isinstance(reports, dict) and key in reports:
        del reports[key]
        config.save_config_doc(path, doc)
        log(f"Removed the schedule for {key}.")
        return Outcome(True, ["Its schedule was removed too."])
    return Outcome(True)
```

`save` keeps its reserved-key check, `registry.resolve`, `host.check_schedule(time, days, require_days=bool(enabled))` and the file write, then ends:

```python
    if not enabled:
        messages.append(f"{report.title} is not scheduled.")
        log(messages[-1])
        return Outcome(True, messages)
    messages.append(f"Scheduled: {', '.join(days)} at {time}" + ("" if prints else ", PDF only") + ".")
    log(messages[-1])
    return Outcome(True, messages)
```

`RefreshRow` drops `info`/`unsupported` and gains `next_run: datetime | None = None`, `last_run: str = ""`; `refresh_row(home, *, now)` fills them from `_plan(home, now)[0].get(host.DATA_REFRESH_KEY)` and `last_scheduled(conn, "refresh")`. `save_refresh` keeps validation and the file write, and ends with the enabled/disabled message only ("Refreshing at … on …." / "The data is not refreshed on a schedule."). Delete `install_refresh`, `_describe_once`, `_unmanageable`, `_installed_or_unknown`, `LOGIN_STAMP`. Keep `REFRESH_TITLE` as `REFRESH_TITLE = schedule_plan.REFRESH_TITLE`. Imports: `from datetime import datetime`; `from .. import config, dates, host, refresh_schedule, reports as registry, schedule_plan`; `from . import clock, db`.

- [ ] **Step 4: Update the route** — in `fridgesheet/web/routes/schedules.py`:

```python
def _notices(state, rows, refresh) -> list[str]:
    """Page-level lines: the Linux server not kept running, and any leftover the startup cleanup
    could not remove (Task 7 fills `extra["leftovers"]`)."""
    out = []
    anything_on = any(r.enabled for r in rows) or bool(refresh and refresh.enabled)
    if anything_on and not host.IS_WINDOWS:
        describe = state.extra.get("describe_service")
        if describe is None:
            from ...host import service
            describe = service.describe_service
        try:
            installed = describe().installed
        except Exception:                                  # noqa: BLE001  unknown is not "missing"
            installed = True
        if not installed:
            out.append("Schedules run only while Fridge Sheet is running. To keep it running after you "
                       "sign out: fridgesheet service install")
    for name, error, command in state.extra.get("leftovers") or []:
        out.append(f"An old scheduled task from an earlier version is still there: {name} ({error}). "
                   f"Remove it with: {command}")
    return out
```

In `_page`: `rows = schedules.rows(state.home, now=state.now())`, `refresh = schedules.refresh_row(state.home, now=state.now())`, pass `notices=_notices(state, rows, refresh)` to `render`. Remove every `scheduling=state.extra.get("scheduling")` argument in this file.

- [ ] **Step 5: Update the template** — in `schedules.html`, replace the intro paragraph with:

```html
<p class="muted">Fridge Sheet runs these itself, while it is running: a scheduled report builds and prints
   (or just keeps the PDF) from the last refresh. The time is also the earliest a catch-up run will print,
   so a run missed overnight does not print yesterday's sheet in the morning.</p>
{% for n in notices %}<p class="warn">{{ n }}</p>{% endfor %}
```

Add a status macro at the top of the content block and use it for the refresh form (after the "Refreshes at" line) and each report (replacing the whole `<p class="muted">` with `r.unsupported`/`r.info`):

```html
{% macro status(item) -%}
<p class="muted">
  {% if item.problem %}<span class="warn">{{ item.problem }}</span>
  {% elif item.enabled and item.next_run %}next: {{ item.next_run | wd_md_time }}
  {% elif not item.enabled %}not scheduled{% endif %}
  {% if item.enabled %} · {% if item.last_run %}last: {{ item.last_run }}{% else %}has not run on a schedule yet{% endif %}{% endif %}
</p>
{%- endmacro %}
```

Call it as `{{ status(refresh_schedule) }}` and `{{ status(r) }}`: both `Row` and `RefreshRow` carry `enabled`, `next_run`, `last_run` and `problem`. Delete `{% set locked = ... %}` and every `{{ locked }}` — nothing on this page is read-only any more. Dates read "Fri 9/25 2:00 PM" (the existing `wd_md_time` filter); the spec's "today 2:00 PM" was an illustration, not a copy requirement.

- [ ] **Step 6: `status_line`** — in `fridgesheet/web/actions.py`:

```python
def status_line(home: Path, *, now: datetime) -> str:
    """The Settings page's one line: the last run, and when the default report's schedule
    fires next -- from the plan, not from an OS scheduler."""
    from .. import schedule_plan
    from . import clock
    log_path = home / runner.LOG_NAME
    last = "No runs yet"
    if log_path.is_file():
        lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            last = lines[-1]
    try:
        schedules, _ = clock.configured(home)
    except Exception:                                      # noqa: BLE001  a status line never fails a page
        return f"{last} · schedule unknown"
    mine = [s for s in schedules if s.key == REPORT_KEY]
    nxt = schedule_plan.next_run(mine[0], now) if mine else None
    return f"{last} · next run {dates.wd_md_time(nxt)}" if nxt else f"{last} · not scheduled"
```

(import `dates` at the top if it is not already). In `routes/settings.py:105` change the argument to `status=actions.status_line(state.home, now=state.now())`.

- [ ] **Step 7: Bring the old tests over.** For each file, delete tests whose subject no longer exists and fix the rest; do not weaken an assertion that still describes shipped behaviour:
  - `tests/test_web_schedules.py`: delete tests of `_unmanageable`, `_installed_or_unknown`, `install`/`remove` calls, `NotSupported`/`SchedulingError` outcomes, the `login-ok.txt` gate, hand-written units. Keep and adapt: reserved key refused, validation (bad time, bad day), `require_days=False` when turning off, config write shape, `forget` deleting the table, `record_enabled`.
  - `tests/test_schedules_residuals.py`, `tests/test_config_errors_and_schedule_off.py`: same rule. A `ConfigError` config still renders the page with a message (#144) — keep that.
  - `tests/test_web_actions.py`, `tests/test_web_settings_page.py`: `status_line` now takes `now=`; assert on `"next run Fri 9/25 2:00 PM"` for an enabled `open-work` at 14:00 with `now` 2026-09-25 09:00.
  - `tests/web_fixtures.py`: delete `FakeScheduling` once nothing imports it (`grep -rn FakeScheduling tests`).
  - `tests/test_web_reports_page.py`, `tests/test_web_reports_residuals.py`, `tests/test_reports.py`: these call `forget` through report deletion; drop any `scheduling=` argument and any assertion on `sched.removed`.

Run: `grep -rn "scheduling=\|FakeScheduling\|extra\[\"scheduling\"\]\|LOGIN_STAMP\|install_refresh" fridgesheet tests`
Expected: no matches except in `fridgesheet/cli.py` and the CLI's own tests, which Task 6 rewrites (`schedule install data-refresh` calls `install_refresh` until then — do not run the CLI tests in this task).

- [ ] **Step 8: Run the web suite**

Run: `PYTEST tests/test_web_schedules_page.py tests/test_web_schedules.py tests/test_schedules_residuals.py tests/test_config_errors_and_schedule_off.py tests/test_web_actions.py tests/test_web_settings_page.py tests/test_web_reports_page.py tests/test_web_reports_residuals.py tests/test_reports.py -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add -A fridgesheet/web tests
git commit -m "Schedules page: saving writes config.toml only; rows show next and last scheduled run"
```

---

### Task 6: Doctor and the `schedule` command

**Files:**
- Modify: `fridgesheet/doctor.py` (`_scheduler`)
- Modify: `fridgesheet/cli.py` (`cmd_schedule`, parser for `schedule`)
- Modify tests: `tests/test_doctor.py`, CLI tests found by `grep -ln "cmd_schedule\|\"schedule\"" tests`

**Interfaces:**
- Consumes: `clock.configured`, `clock.current()`, `Clock.stale(now)`, `schedule_plan.next_run`, `schedules.last_scheduled`, `schedules.record_enabled`.
- Produces: `fridgesheet schedule show [report]`, `fridgesheet schedule remove <report>` (turns it off in `config.toml`), `fridgesheet schedule remove --all` (Task 7 fills it in; here it keeps calling the old code). `install` is no longer a choice.

- [ ] **Step 1: Write the failing doctor tests** in `tests/test_doctor.py` (replace existing `_scheduler` tests):

```python
def _sched_settings(tmp_path, doc):
    config.save_config_doc(tmp_path / "config.toml", doc)
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    return s


def test_scheduler_with_nothing_on(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "_current", None)
    assert doctor._scheduler(_sched_settings(tmp_path, {}), tmp_path) == "no schedules are on"


def test_scheduler_from_a_terminal_names_the_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "_current", None)
    s = _sched_settings(tmp_path, {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": list(host.DAY_NAMES)}}})
    out = doctor._scheduler(s, tmp_path)
    assert "next: open-work" in out and "only while the web server is running" in out


def test_scheduler_fails_when_the_clock_has_stopped(tmp_path, monkeypatch):
    stopped = SimpleNamespace(stale=lambda now: True)
    monkeypatch.setattr(clock, "_current", stopped)
    s = _sched_settings(tmp_path, {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": ["Fri"]}}})
    with pytest.raises(RuntimeError, match="paused"):
        doctor._scheduler(s, tmp_path)


def test_scheduler_fails_on_a_schedule_that_cannot_run(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "_current", None)
    s = _sched_settings(tmp_path, {"refresh": {"enabled": True, "every_hours": 1, "start": "06:00", "end": "21:00"}})
    with pytest.raises(RuntimeError, match="refreshes a day"):
        doctor._scheduler(s, tmp_path)
```

(imports: `from types import SimpleNamespace`, `from fridgesheet.web import clock`, `from fridgesheet import config, host` as needed.)

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_doctor.py -k scheduler -v`
Expected: FAIL (the old `_scheduler` calls `scheduling.describe`).

- [ ] **Step 3: Rewrite `_scheduler`**

```python
def _scheduler(s: Settings, home: Path) -> str:
    """The server's own clock fires schedules (web/clock.py). From a terminal there is no clock
    to ask, so this names what is next and says schedules need the server; inside the server a
    clock that has stopped ticking is a FAIL, and so is a schedule that is on but cannot run."""
    from datetime import datetime
    from . import schedule_plan
    from .web import clock
    schedules, problems = clock.configured(home, settings=s)
    if problems:
        raise RuntimeError("; ".join(f"{k}: {v}" for k, v in sorted(problems.items())))
    if not schedules:
        return "no schedules are on"
    now = datetime.now(ZoneInfo(s.timezone))
    nxt = min(((schedule_plan.next_run(x, now), x.key) for x in schedules if schedule_plan.next_run(x, now)),
              default=(None, ""))
    detail = f"{len(schedules)} on; next: {nxt[1]} {nxt[0]:%a %H:%M}" if nxt[0] else f"{len(schedules)} on"
    running = clock.current()
    if running is None:
        return detail + "; schedules run only while the web server is running"
    if running.stale(now):
        raise RuntimeError(clock.PAUSED)
    return "scheduler running; " + detail
```

- [ ] **Step 4: Rewrite `cmd_schedule` (all but `--all`)** — parser: `sc2.add_argument("action", choices=["remove", "show"])` and help text "show when schedules run next, or turn one off (`remove --all`: remove tasks older versions registered with the OS)". In `cmd_schedule`, keep the `if args.all:` dispatch unchanged for now, then:

```python
    from . import schedule_plan
    from .web import clock, db as web_db, schedules as page
    s = load_settings()
    key = args.report
    if args.action == "remove":
        if key != host.DATA_REFRESH_KEY:
            try:
                reports.resolve(key, s.home)
            except reports.ReportError as e:
                print(str(e), file=sys.stderr)
                return 1
        page.record_enabled(s.home, key, False, create=False)
        print(f"{key}: turned off in config.toml")
    schedules, problems = clock.configured(s.home, settings=s)
    now = datetime.now(ZoneInfo(s.timezone))
    conn = web_db.open_db(s.home)
    try:
        for x in schedules:
            nxt = schedule_plan.next_run(x, now)
            last = page.last_scheduled(conn, "refresh" if x.key == host.DATA_REFRESH_KEY else x.key)
            print(f"{x.key}: next {nxt:%a %m/%d %H:%M}" if nxt else f"{x.key}: no next run",
                  f"· last {last}" if last else "· has not run on a schedule yet")
    finally:
        conn.close()
    for k, v in sorted(problems.items()):
        print(f"{k}: {v}", file=sys.stderr)
    if not schedules:
        print("no schedules are on")
    return 1 if problems else 0
```

(imports inside the function: `from datetime import datetime`, `from zoneinfo import ZoneInfo`, `from . import host, reports`.)

- [ ] **Step 5: Bring the CLI tests over** — `grep -ln "cmd_schedule\|schedule install\|\"schedule\", \"install\"" tests`: delete `install` tests; adapt `show`/`remove <key>` tests to the new output. Add:

```python
def test_schedule_show_lists_next_and_last(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FRIDGESHEET_HOME", str(tmp_path))
    config.save_config_doc(tmp_path / "config.toml",
                           {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": list(host.DAY_NAMES)}}})
    assert cli.main(["schedule", "show"]) == 0
    out = capsys.readouterr().out
    assert "open-work: next" in out and "has not run on a schedule yet" in out
```

(If the CLI tests set the home a different way, follow the existing pattern in that file.)

- [ ] **Step 6: Run**

Run: `PYTEST tests/test_doctor.py tests/test_cli*.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/doctor.py fridgesheet/cli.py tests
git commit -m "Doctor and \`schedule show\` read the plan; \`schedule install\` is gone"
```

---

### Task 7: The OS adapters shrink to cleanup

**Files:**
- Rewrite: `fridgesheet/host/scheduling.py`, `fridgesheet/host/scheduling_windows.py`, `fridgesheet/host/scheduling_linux.py`
- Delete: `fridgesheet/host/task.xml`
- Modify: `fridgesheet/host/__init__.py` (drop `ScheduleInfo`, `safe_key`, `task_name`, `systemd_quote` if unused — check with grep first; keep `DATA_REFRESH_KEY`, `RESERVED_KEYS`, `is_reserved`, `check_schedule*`, `DAY_NAMES`, `TIME_RE`)
- Modify: `fridgesheet/cli.py` (`_cmd_schedule_remove_all`; delete `_removal_settings`, `_schedule_removal_keys`)
- Modify: `fridgesheet/web/clock.py` (`remove_leftovers`, and `start_background` starts it)
- Modify: `packaging/windows/FridgeSheet.spec`, `packaging/windows/smoke.ps1`, `tests/test_packaging.py`
- Delete tests: `tests/test_host_scheduling.py`, `tests/test_host_scheduling_linux.py` (replaced by `tests/test_os_leftovers.py`); remove `remove --all` tests of the deleted helpers from CLI test files.
- Test: `tests/test_os_leftovers.py`

**Interfaces:**
- Produces:
  - `scheduling.Leftovers(removed: list[str], failed: list[tuple[str, str, str]])` — `failed` is `(name, error, command a person can run)`
  - `scheduling.remove_os_leftovers(run=subprocess.run, *, unit_dir=None) -> Leftovers`
  - `scheduling_windows.leftovers(run) -> list[str]`, `scheduling_windows.remove_task(name, run) -> None` (raises `SchedulingError`)
  - `scheduling_linux.leftovers(unit_dir=None) -> list[str]` (timer file names), `scheduling_linux.remove_timer(name, run, unit_dir=None) -> None`
  - `state.extra["leftovers"]`: the `failed` list from the startup run

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_os_leftovers.py
"""Removing what earlier versions registered with the OS -- and nothing else."""
from __future__ import annotations

import subprocess

from fridgesheet.host import scheduling_linux as lin, scheduling_windows as win


def _run(answers):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        rc, out, err = answers.get(tuple(argv[1:3]), (0, "", ""))
        return subprocess.CompletedProcess(argv, rc, out, err)
    return calls, run


CSV = ('"\\Fridge Sheet - data-refresh","9/25/2026 7:00:00 AM","Ready"\n'
       '"\\Fridge Sheet - data-refresh","9/25/2026 9:00:00 AM","Ready"\n'
       '"\\Fridge Sheet - web","N/A","Running"\n'
       '"\\Fridge Sheet - WEB","N/A","Ready"\n'
       '"\\Fridge Sheet - view 7","9/28/2026 2:00:00 PM","Ready"\n'
       '"\\Microsoft\\Windows\\Fridge Sheet - elsewhere","N/A","Ready"\n'
       '"\\OneDrive Reporting Task","N/A","Ready"\n')


def test_windows_leftovers_are_this_apps_root_tasks_once_each():
    _, run = _run({("/Query", "/FO"): (0, CSV, "")})
    assert win.leftovers(run) == ["Fridge Sheet - data-refresh", "Fridge Sheet - view 7"]


def test_windows_leftovers_never_include_the_web_task():
    _, run = _run({("/Query", "/FO"): (0, CSV, "")})
    assert not any(n.strip().casefold() == "fridge sheet - web" for n in win.leftovers(run))


def test_windows_remove_task_tolerates_one_already_gone():
    _, run = _run({("/Delete", "/TN"): (1, "", "ERROR: The system cannot find the file specified.")})
    win.remove_task("Fridge Sheet - data-refresh", run)


MARK = lin.MARKER


def test_linux_leftovers_are_marked_timers_only(tmp_path):
    (tmp_path / "fridgesheet-open-work.timer").write_text(MARK + "[Timer]\n")
    (tmp_path / "fridgesheet-open-work.service").write_text(MARK + "[Service]\n")
    (tmp_path / "fridgesheet-print-sheet.timer").write_text("[Timer]\n")          # hand-written
    (tmp_path / "fridgesheet-web.service").write_text("[Service]\n")
    assert lin.leftovers(tmp_path) == ["fridgesheet-open-work.timer"]


def test_linux_remove_timer_disables_and_deletes_both_halves(tmp_path):
    (tmp_path / "fridgesheet-open-work.timer").write_text(MARK)
    (tmp_path / "fridgesheet-open-work.service").write_text(MARK)
    calls, run = _run({})
    lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)
    assert ["systemctl", "--user", "disable", "--now", "fridgesheet-open-work.timer"] in calls
    assert ["systemctl", "--user", "daemon-reload"] in calls
    assert list(tmp_path.iterdir()) == []


def test_linux_leaves_a_hand_edited_service_half(tmp_path):
    (tmp_path / "fridgesheet-open-work.timer").write_text(MARK)
    (tmp_path / "fridgesheet-open-work.service").write_text("[Service]\n# edited by hand\n")
    _, run = _run({})
    lin.remove_timer("fridgesheet-open-work.timer", run, tmp_path)
    assert [p.name for p in tmp_path.iterdir()] == ["fridgesheet-open-work.service"]


def test_remove_os_leftovers_reports_what_it_could_not_remove(tmp_path, monkeypatch):
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling, "IS_WINDOWS", True)
    _, run = _run({("/Query", "/FO"): (0, '"\\Fridge Sheet - data-refresh","N/A","Ready"\n', ""),
                   ("/Delete", "/TN"): (1, "", "ERROR: Access is denied.")})
    got = scheduling.remove_os_leftovers(run)
    assert got.removed == []
    (name, error, command), = got.failed
    assert name == "Fridge Sheet - data-refresh" and "denied" in error
    assert command == 'schtasks /Delete /TN "Fridge Sheet - data-refresh" /F'
```

- [ ] **Step 2: Run to verify they fail**

Run: `PYTEST tests/test_os_leftovers.py -v`
Expected: FAIL — `AttributeError: module 'fridgesheet.host.scheduling_windows' has no attribute 'leftovers'`

- [ ] **Step 3: Rewrite `scheduling_windows.py`**

```python
"""Windows: remove the Task Scheduler tasks earlier versions of this app registered.

Schedules are fired by the server's own clock now (web/clock.py). Every task an earlier
version registered was `InteractiveToken` -- "run only when the user is logged on" -- and on
the household's kiosk the app's account never is, so none of them ever ran. They are removed
so that the day that account *does* sign in, they do not fire alongside the clock.
"""
from __future__ import annotations

import csv
import subprocess

from . import CREATE_NO_WINDOW, SchedulingError
from .service_windows import NAME as _WEB_TASK

PREFIX = "Fridge Sheet - "
_WEB_FOLDED = _WEB_TASK.strip().casefold()
_NOT_FOUND = "cannot find the file"


def _schtasks(cmd: list[str], run) -> subprocess.CompletedProcess:
    return run(["schtasks", *cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=60)


def leftovers(run=subprocess.run) -> list[str]:
    """Every task in the root folder named `Fridge Sheet - *`, except the web server's own logon
    task in any casing (Task Scheduler's names are case-insensitive). Listed, not built from
    config.toml's keys, so a task left by a report deleted long ago is found too."""
    p = _schtasks(["/Query", "/FO", "CSV", "/NH"], run)
    if p.returncode != 0:
        raise SchedulingError(f"schtasks /Query failed: {(p.stderr or p.stdout or '').strip()[:300]}")
    names = set()
    for row in csv.reader((p.stdout or "").splitlines()):
        if not row or not row[0].startswith("\\") or row[0].count("\\") != 1:
            continue                                    # a header, a blank, or a task in a subfolder
        name = row[0][1:]
        if name.startswith(PREFIX) and name.strip().casefold() != _WEB_FOLDED:
            names.add(name)
    return sorted(names)


def remove_task(name: str, run=subprocess.run) -> None:
    if name.strip().casefold() == _WEB_FOLDED:
        raise SchedulingError(f"{name} is the web server's own task; refusing to remove it")
    p = _schtasks(["/Delete", "/TN", name, "/F"], run)
    if p.returncode != 0 and _NOT_FOUND not in (p.stderr or "").lower():
        raise SchedulingError((p.stderr or p.stdout or "").strip()[:300])


def command_for(name: str) -> str:
    return f'schtasks /Delete /TN "{name}" /F'
```

- [ ] **Step 4: Rewrite `scheduling_linux.py`**

```python
"""Linux: remove the systemd user units earlier versions of this app wrote.

Only a unit whose first line is `MARKER` was written by this app; anything else -- the
household's hand-written timers, the web server's own unit -- is never touched.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import SchedulingError
from .service_linux import UNIT_FILE as _WEB_UNIT

#: The first line of every unit an earlier version wrote.
MARKER = "# Written by Fridge Sheet. Edits here are lost when the schedule is saved.\n"
_NO_SUCH_UNIT = ("does not exist", "not loaded")


def _unit_dir(d: Path | None = None) -> Path:
    return d or Path.home() / ".config" / "systemd" / "user"


def _ours(path: Path) -> bool:
    try:
        return path.name != _WEB_UNIT and path.read_text(encoding="utf-8").startswith(MARKER)
    except (OSError, UnicodeDecodeError):
        return False


def leftovers(unit_dir: Path | None = None) -> list[str]:
    d = _unit_dir(unit_dir)
    return sorted(p.name for p in d.glob("fridgesheet-*.timer") if _ours(p))


def _systemctl(args: list[str], run) -> subprocess.CompletedProcess:
    return run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=60)


def remove_timer(name: str, run=subprocess.run, unit_dir: Path | None = None) -> None:
    d = _unit_dir(unit_dir)
    timer, service = d / name, d / name.replace(".timer", ".service")
    if not _ours(timer):
        raise SchedulingError(f"{name} was not written by this app; refusing to touch it")
    try:
        p = _systemctl(["disable", "--now", name], run)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise SchedulingError(f"systemctl --user disable --now {name}: {e}") from None
    text = f"{p.stderr or ''}\n{p.stdout or ''}".lower()
    if p.returncode != 0 and not any(s in text for s in _NO_SUCH_UNIT):
        raise SchedulingError((p.stderr or p.stdout or "").strip()[:300])
    timer.unlink(missing_ok=True)
    if _ours(service):
        service.unlink(missing_ok=True)
    try:
        _systemctl(["daemon-reload"], run)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


def command_for(name: str) -> str:
    return f"systemctl --user disable --now {name} && rm ~/.config/systemd/user/{name}"
```

- [ ] **Step 5: Rewrite `scheduling.py`**

```python
"""What is left of OS scheduling: removing what earlier versions registered.

Schedules are fired by the server's own clock (web/clock.py) on both platforms. This runs once
at server start and from `fridgesheet schedule remove --all`, which the Windows uninstaller calls.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from . import IS_WINDOWS, SchedulingError  # noqa: F401  re-exported
from . import DATA_REFRESH_KEY  # noqa: F401  re-exported


@dataclass
class Leftovers:
    removed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str, str]] = field(default_factory=list)   # (name, error, command)


def remove_os_leftovers(run=subprocess.run, *, unit_dir: Path | None = None) -> Leftovers:
    if IS_WINDOWS:
        from . import scheduling_windows as impl
        list_them, remove = (lambda: impl.leftovers(run)), (lambda n: impl.remove_task(n, run))
    else:
        from . import scheduling_linux as impl
        list_them, remove = (lambda: impl.leftovers(unit_dir)), (lambda n: impl.remove_timer(n, run, unit_dir))
    out = Leftovers()
    try:
        names = list_them()
    except (SchedulingError, OSError, subprocess.TimeoutExpired) as e:
        out.failed.append(("the list of scheduled tasks", str(e), ""))
        return out
    for name in names:
        try:
            remove(name)
            out.removed.append(name)
        except (SchedulingError, OSError, subprocess.TimeoutExpired) as e:
            out.failed.append((name, str(e), impl.command_for(name)))
    return out
```

(`IS_WINDOWS` is read from this module's globals so the test can monkeypatch `scheduling.IS_WINDOWS`.)

- [ ] **Step 6: Run the leftover tests**

Run: `PYTEST tests/test_os_leftovers.py -v`
Expected: all pass.

- [ ] **Step 7: Startup cleanup** — in `fridgesheet/web/clock.py`, extend `start_background` (Task 4) so the real server also removes old OS tasks, on its own thread so the first page never waits for `schtasks`:

```python
def remove_leftovers(state, remove=None) -> None:
    """Remove what earlier versions registered with the OS; keep what could not be removed for
    the Schedules page. Never raises: a server that cannot clean up still serves."""
    if remove is None:
        from ..host.scheduling import remove_os_leftovers as remove
    try:
        got = remove()
    except Exception as e:                                 # noqa: BLE001
        log.warning("could not remove old scheduled tasks: %s", e)
        return
    for name in got.removed:
        log.info("removed %s, which an earlier version registered", name)
    state.extra["leftovers"] = got.failed


def start_background(state) -> "Clock":
    c = Clock(state)
    state.extra["clock"] = c
    c.start()
    threading.Thread(target=remove_leftovers, args=(state,), name="fridgesheet-leftovers", daemon=True).start()
    return c
```

Add to `tests/test_clock.py`:

```python
def test_remove_leftovers_keeps_failures_for_the_page(tmp_path):
    from fridgesheet.host.scheduling import Leftovers
    state = SimpleNamespace(extra={})
    got = Leftovers(removed=["Fridge Sheet - open-work"], failed=[("Fridge Sheet - data-refresh", "denied", "cmd")])
    clockmod.remove_leftovers(state, remove=lambda: got)
    assert state.extra["leftovers"] == [("Fridge Sheet - data-refresh", "denied", "cmd")]


def test_remove_leftovers_never_raises(tmp_path):
    state = SimpleNamespace(extra={})
    clockmod.remove_leftovers(state, remove=lambda: (_ for _ in ()).throw(OSError("no schtasks")))
    assert "leftovers" not in state.extra
```

Add to `tests/test_web_schedules_page.py`:

```python
def test_a_leftover_that_could_not_be_removed_is_named_with_its_command(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.app.state.fridgesheet.extra["leftovers"] = [
        ("Fridge Sheet - data-refresh", "Access is denied.", 'schtasks /Delete /TN "Fridge Sheet - data-refresh" /F')]
    body = c.get("/schedules").text
    assert "Fridge Sheet - data-refresh" in body and "schtasks /Delete" in body
```

- [ ] **Step 8: `schedule remove --all`** — replace `_cmd_schedule_remove_all` with:

```python
def _cmd_schedule_remove_all() -> int:
    """The uninstaller's call: remove every task or unit an earlier version registered with the
    OS. Reads no config and creates nothing -- the list comes from the OS itself."""
    from .host import scheduling
    got = scheduling.remove_os_leftovers()
    for name in got.removed:
        print(f"Removed {name}")
    for name, error, command in got.failed:
        print(f"{name}: {error}" + (f" (remove it with: {command})" if command else ""), file=sys.stderr)
    return 1 if got.failed else 0
```

Delete `_removal_settings` and `_schedule_removal_keys`, and their tests (`grep -ln "_removal_settings\|_schedule_removal_keys" tests`).

- [ ] **Step 9: Delete the rest**

```bash
git rm fridgesheet/host/task.xml tests/test_host_scheduling.py tests/test_host_scheduling_linux.py
grep -rn "ScheduleInfo\|task_name\|safe_key\|systemd_quote\|command_for\|scheduling\.install\|scheduling\.describe\|blocking_name\|display_name\|render_task_xml\|LEGACY_TIMERS" fridgesheet tests packaging
```

Remove every remaining use; then remove from `host/__init__.py` each of `ScheduleInfo`, `safe_key`, `task_name`, `systemd_quote` that `grep` shows has no caller left (`systemd_quote` is likely still used by `service_linux` — keep it if so). In `packaging/windows/FridgeSheet.spec` delete the `task.xml` `datas` line (keep `logon-task.xml`, and make the next line `datas = [...]` instead of `datas += [...]`). In `tests/test_packaging.py:46` drop `"task.xml" in spec and`. In `packaging/windows/smoke.ps1` replace section 2b with:

```powershell
    # 2b. the uninstaller's cleanup runs against a real schtasks and finds nothing to remove
    $p = Start-Process -FilePath $exe -ArgumentList "schedule","remove","--all" -Wait -PassThru -WindowStyle Hidden
    if ($p.ExitCode -ne 0) { throw "schedule remove --all failed (exit $($p.ExitCode))" }
    Write-Host "  old-task cleanup ran clean"
```

- [ ] **Step 10: Run the whole suite**

Run: `PYTEST -q -x 2>&1 | tee /tmp/in-app-scheduler-task7.log | tail -20`
Expected: all pass except any failure that also fails on `origin/main` (compare with `git stash`-free check: `git worktree add /tmp/fs-base origin/main` and run the same failing test there).

- [ ] **Step 11: Commit**

```bash
git add -A fridgesheet tests packaging
git commit -m "OS scheduling shrinks to removing what earlier versions registered"
```

---

### Task 8: Docs, and the check nobody made last time

**Files:**
- Modify: `docs/release-checklist.md` (§5, and the §0b/§1 lines that mention `schedule install` or "Task Scheduler … Fridge Sheet - open-work")
- Modify: `docs/product/features/report-scheduling.md`, `docs/product/features/os-integration.md` (the `scheduling` adapter sentence)
- Modify: `docs/superpowers/specs/2026-09-25-in-app-scheduler-design.md` ("schema 5" → "schema 6"; "header status line" stays — Task 4 did it)
- Modify: `README.md` / user guide wherever it tells a household to install a systemd timer or says Task Scheduler runs the sheet (`grep -rn "timer\|Task Scheduler\|schedule install" README.md docs/*.md`)

- [ ] **Step 1: Rewrite release checklist §5** to:

```markdown
## 5. A schedule, end to end

Fridge Sheet fires schedules from inside the running server; Task Scheduler is no longer
involved. What no test can prove is a schedule actually firing on the real machine, as the
real account, and printing. The last scheduling release shipped without this check and not
one scheduled run ever happened (2026-09-25), so do not skip it.

- [ ] After installing, open **Task Scheduler**. **Expect:** no task named
  **"Fridge Sheet - data-refresh"** or **"Fridge Sheet - open-work"** (the server removed
  them at start); **"Fridge Sheet - web"** is still there.
- [ ] On the **Schedules** page, turn on **Refresh the data** with a window that includes the
  next hour, and Save. **Expect:** the row says **next:** with the next slot.
- [ ] Wait past that slot. **Expect:** the **Runs** page has a **refresh** row started **On a
  schedule**, and the Schedules row now says **last:** with its time and **OK**.
- [ ] Tick **Run this on a schedule** for Open Work Sheet, a few minutes from now, today ticked,
  **Print it** on, Save. Wait. **Expect:** it prints, and Runs shows it **On a schedule**.
- [ ] Nobody needs to be signed in as the app's account for any of this. Check it with the
  household's usual account signed in, not the app's.
```

- [ ] **Step 2: Update the feature and adapter docs** — in `report-scheduling.md`, replace the paragraph describing systemd timers / Task Scheduler with: "The server fires schedules itself, once a minute, from `config.toml` (`web/clock.py`, `schedule_plan.py`). A slot missed while the server was down is caught up once; a print caught up the next morning is refused by the runner's print window. Schedules run only while the server runs: on Windows the installer registers it; on Linux, `fridgesheet service install`." In `os-integration.md`, change the `scheduling` clause to "`scheduling` (remove the Task Scheduler tasks and systemd timers earlier versions registered)".

- [ ] **Step 3: Fix the spec's schema number**

Run: `sed -i 's/(schema 5, new)/(schema 6, new)/; s/`schedule_fires` table (schema 5)/`schedule_fires` table (schema 6)/' docs/superpowers/specs/2026-09-25-in-app-scheduler-design.md && grep -n "schema" docs/superpowers/specs/2026-09-25-in-app-scheduler-design.md`
Expected: every mention reads schema 6.

- [ ] **Step 4: Full suite, once more**

Run: `PYTEST -q 2>&1 | tee /tmp/in-app-scheduler-final.log | tail -5`
Expected: all pass (or only failures shown to fail identically on `origin/main`, listed in the PR).

- [ ] **Step 5: Commit**

```bash
git add docs README.md
git commit -m "Docs: the server fires schedules; the release checklist waits for one to fire"
```

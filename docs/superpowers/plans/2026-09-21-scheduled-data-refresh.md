# Scheduled Data Refreshes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Fridge Sheet schedule its own data refreshes, several times a day, on both platforms, independent of any report's print schedule — and say so on every page when the data goes stale anyway.

**Architecture:** A reserved `data-refresh` key flows through the key machinery that already schedules reports. A `[refresh]` config table holds an interval and a window; one pure function expands them into explicit clock times, which both renderers emit as multiple triggers. The schedule runs a new `fridgesheet refresh --record` entry point that calls `web.actions.refresh` (collect → ingest → record), because the existing CLI `refresh` writes only the snapshot and would leave the kiosk unchanged. A staleness helper shares `runner.MAX_DATA_AGE_HOURS` by import so the banner and the print refusal cannot disagree.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, sqlite3, systemd user units (Linux), Task Scheduler XML (Windows), pytest.

**Spec:** `docs/superpowers/specs/2026-09-21-scheduled-data-refresh-design.md`

## Global Constraints

- **Run tests with `.venv/bin/python -m pytest`.** The repo venv is gitignored; create it with `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"` if absent.
- **One pre-existing failure is expected:** `tests/test_host_credentials.py::test_settings_credentials_falls_back_to_store_username_then_errors` fails on a machine whose keyring holds real credentials. It fails identically on clean `main`. Do not try to fix it; do not count it as a regression.
- **No test may invoke a real scheduler.** `tests/conftest.py::_no_real_scheduler` blocks `systemctl` and `schtasks`. Use `tests.web_fixtures.FakeScheduling` or inject `run=`.
- **A one-element `times` list must render byte-identically to today's output.** Every report keeps its current task XML and unit text; nothing already installed may need reinstalling.
- **The staleness ceiling is `runner.MAX_DATA_AGE_HOURS`, imported, never re-spelled.** Its value today is `24`.
- **Reserved key spelling:** `data-refresh` (lowercase, hyphen). Task name renders as `Fridge Sheet - data-refresh`; Linux units as `fridgesheet-data-refresh.timer` / `.service`.
- **Config fall-back rule:** a value of the wrong *shape* keeps the default rather than raising. Only a malformed `start`/`end` time raises `ConfigError`. A `TypeError` escaping config parsing tracebacks out of `schedule remove --all`, which the uninstaller runs hidden with its exit code discarded.
- **Commit after every task.** End commit messages with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

## File Structure

| File | Responsibility |
|---|---|
| `fridgesheet/refresh_schedule.py` *(new)* | The interval→times expansion. Pure, no I/O. |
| `fridgesheet/config.py` | `RefreshConfig` dataclass + `[refresh]` parsing. |
| `fridgesheet/host/__init__.py` | `check_schedule_times`, `RESERVED_KEYS`, `DATA_REFRESH_KEY`. |
| `fridgesheet/host/task.xml` | `{triggers}` placeholder in place of one hard-coded trigger. |
| `fridgesheet/host/scheduling_windows.py` | Render N `<CalendarTrigger>` blocks. |
| `fridgesheet/host/scheduling_linux.py` | Emit N `OnCalendar=` lines. |
| `fridgesheet/host/scheduling.py` | `command_for` branch for `data-refresh`. |
| `fridgesheet/web/actions.py` | `refresh()` takes a `trigger`. |
| `fridgesheet/cli.py` | `refresh --record`. |
| `fridgesheet/web/schedules.py` | `refresh_row()` / `save_refresh()`. |
| `fridgesheet/web/routes/schedules.py` | `POST /schedules/refresh`. |
| `fridgesheet/web/templates/schedules.html` | The refresh editor. |
| `fridgesheet/web/staleness.py` *(new)* | The age helper. |
| `fridgesheet/web/app.py` | `staleness` into `page_context`. |
| `fridgesheet/web/templates/_header.html` | The banner. |

---

### Task 1: The interval→times expansion

**Files:**
- Create: `fridgesheet/refresh_schedule.py`
- Test: `tests/test_refresh_schedule.py`

**Interfaces:**
- Consumes: `config.ConfigError`
- Produces: `refresh_schedule.refresh_times(start: str, end: str, every_hours: int) -> list[str]`, `refresh_schedule.MAX_PER_DAY: int = 12`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_refresh_schedule.py`:

```python
"""The interval and window a parent sets, expanded into the clock times a scheduler takes."""
from __future__ import annotations

import pytest

from fridgesheet.config import ConfigError
from fridgesheet.refresh_schedule import MAX_PER_DAY, refresh_times


def test_a_window_that_lands_on_a_step_includes_the_end():
    assert refresh_times("06:00", "21:00", 3) == ["06:00", "09:00", "12:00", "15:00", "18:00", "21:00"]


def test_a_window_that_ends_mid_step_stops_before_it():
    """Never fire outside the window the parent set: 20:00 is the end, so 21:00 is not a time."""
    assert refresh_times("06:00", "20:00", 3) == ["06:00", "09:00", "12:00", "15:00", "18:00"]


def test_start_equal_to_end_is_one_refresh():
    assert refresh_times("06:00", "06:00", 3) == ["06:00"]


def test_an_interval_wider_than_the_window_is_one_refresh_not_none():
    assert refresh_times("06:00", "09:00", 5) == ["06:00"]


def test_an_end_before_the_start_is_refused():
    with pytest.raises(ConfigError, match="overnight"):
        refresh_times("21:00", "06:00", 3)


@pytest.mark.parametrize("every", [0, -1])
def test_a_non_positive_interval_is_refused(every):
    with pytest.raises(ConfigError, match="every_hours"):
        refresh_times("06:00", "21:00", every)


def test_more_than_twelve_a_day_is_refused():
    """A refresh drives a browser through OneLogin; 24 of them is a self-inflicted
    denial of service on the school, not a setting."""
    with pytest.raises(ConfigError, match="12"):
        refresh_times("00:00", "23:00", 1)
    assert len(refresh_times("06:00", "17:00", 1)) == MAX_PER_DAY


@pytest.mark.parametrize("bad", ["6:00", "25:00", "06:60", "noon", ""])
def test_a_time_that_is_not_a_time_is_refused(bad):
    with pytest.raises(ConfigError):
        refresh_times(bad, "21:00", 3)
    with pytest.raises(ConfigError):
        refresh_times("06:00", bad, 3)


def test_minutes_are_kept():
    assert refresh_times("06:30", "12:30", 2) == ["06:30", "08:30", "10:30", "12:30"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_refresh_schedule.py -q`
Expected: collection error, `ModuleNotFoundError: No module named 'fridgesheet.refresh_schedule'`

- [ ] **Step 3: Write the implementation**

Create `fridgesheet/refresh_schedule.py`:

```python
"""An interval and a window, as the clock times a scheduler actually takes.

A parent sets "every 3 hours between 06:00 and 21:00"; Task Scheduler and systemd both want
the individual times. Expanding here -- rather than leaning on Task Scheduler's `<Repetition>`
or systemd's `OnUnitActiveSec` -- keeps one meaning on both platforms: systemd has no way to
bound a repetition to a window, and `OnUnitActiveSec` counts from the last activation, so a
refresh that takes eight minutes would push every later run of the day eight minutes further
out, by a different amount on every machine.
"""
from __future__ import annotations

import re

from .config import ConfigError

#: The most refreshes a day this will install. A refresh drives a real browser through
#: OneLogin into Canvas and HAC -- one to three minutes on a fast box, eight to ten on a
#: slow one -- so an hourly pull around the clock is a great many logins against the
#: district's systems. Hourly inside a twelve-hour window is still available.
MAX_PER_DAY = 12

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _minutes(label: str, value: str) -> int:
    if not _TIME_RE.match(str(value)):
        raise ConfigError(f"[refresh] {label} must be HH:MM (24-hour), got {value!r}")
    h, m = (int(x) for x in str(value).split(":"))
    return h * 60 + m


def refresh_times(start: str, end: str, every_hours: int) -> list[str]:
    """The clock times to refresh at, inclusive of both ends where the step lands on them.

    `06:00`, `21:00`, every 3 -> `["06:00","09:00","12:00","15:00","18:00","21:00"]`.
    """
    first, last = _minutes("start", start), _minutes("end", end)
    if isinstance(every_hours, bool) or not isinstance(every_hours, int) or every_hours <= 0:
        raise ConfigError(f"[refresh] every_hours must be a whole number of hours above zero, got {every_hours!r}")
    if last < first:
        raise ConfigError(f"[refresh] end ({end}) is before start ({start}); overnight windows are not supported")
    step = every_hours * 60
    times = []
    at = first
    while at <= last:
        times.append(f"{at // 60:02d}:{at % 60:02d}")
        at += step
    if len(times) > MAX_PER_DAY:
        raise ConfigError(
            f"[refresh] every {every_hours} h from {start} to {end} is {len(times)} refreshes a day; "
            f"the most this will install is {MAX_PER_DAY}")
    return times
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_refresh_schedule.py -q`
Expected: PASS, 14 passed

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/refresh_schedule.py tests/test_refresh_schedule.py
git commit -m "refresh schedule: an interval and a window as explicit clock times

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: The `[refresh]` config table

**Files:**
- Modify: `fridgesheet/config.py` (add `RefreshConfig` after `ReportConfig` at line 162-168; parse in `settings_from_doc` after the `[reports]` loop that ends at line 330)
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `host.DAY_NAMES`
- Produces: `config.RefreshConfig(enabled: bool, every_hours: int, start: str, end: str, days: list[str])`, reachable as `Settings.refresh`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
# --- [refresh]: the app's own data-refresh schedule ------------------------------------

def _doc_refresh(**kw) -> dict:
    return {"refresh": {**kw}}


def test_refresh_defaults_when_the_table_is_absent():
    s = config.Settings()
    config.settings_from_doc({}, s)
    assert s.refresh.enabled is False
    assert s.refresh.every_hours == 3
    assert (s.refresh.start, s.refresh.end) == ("06:00", "21:00")
    assert s.refresh.days == list(host.DAY_NAMES)          # all seven; grades post at weekends


def test_refresh_reads_every_field():
    s = config.Settings()
    config.settings_from_doc(_doc_refresh(enabled=True, every_hours=4, start="07:00",
                                          end="19:00", days=["Mon", "Wed"]), s)
    assert s.refresh.enabled is True and s.refresh.every_hours == 4
    assert (s.refresh.start, s.refresh.end) == ("07:00", "19:00")
    assert s.refresh.days == ["Mon", "Wed"]


@pytest.mark.parametrize("bad", ["three", 2.5, None, [], True])
def test_a_misshapen_every_hours_keeps_the_default(bad):
    """The `[reports]` rule: a wrong *shape* falls back rather than raising, because a
    TypeError here tracebacks out of `schedule remove --all` during uninstall."""
    s = config.Settings()
    config.settings_from_doc(_doc_refresh(every_hours=bad), s)
    assert s.refresh.every_hours == 3


@pytest.mark.parametrize("bad", [5, "Mon", None, {}])
def test_misshapen_days_keep_the_default(bad):
    s = config.Settings()
    config.settings_from_doc(_doc_refresh(days=bad), s)
    assert s.refresh.days == list(host.DAY_NAMES)


def test_a_refresh_table_that_is_not_a_table_keeps_the_defaults():
    s = config.Settings()
    config.settings_from_doc({"refresh": "yes please"}, s)
    assert s.refresh.enabled is False and s.refresh.every_hours == 3


@pytest.mark.parametrize("field,bad", [("start", "6am"), ("end", "25:00"), ("start", 600)])
def test_a_time_that_is_not_a_time_is_a_config_error(field, bad):
    """The one exception to falling back: a refresh silently running at the wrong hour is
    worse than one that refuses to install."""
    s = config.Settings()
    with pytest.raises(config.ConfigError, match="refresh"):
        config.settings_from_doc(_doc_refresh(**{field: bad}), s)
```

Ensure `tests/test_config.py` imports `pytest` and `from fridgesheet import config, host` at the top; add whichever is missing.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -q -k refresh`
Expected: FAIL, `AttributeError: 'Settings' object has no attribute 'refresh'`

- [ ] **Step 3: Write the implementation**

In `fridgesheet/config.py`, add after the `ReportConfig` dataclass (which ends at line 168):

```python
@dataclass
class RefreshConfig:
    """`[refresh]`: the app's own data-refresh schedule, independent of any report's.

    An app-installed report schedule runs `--no-refresh` and trusts the snapshot to be warm.
    This is what keeps it warm. `days` defaults to all seven: grades post at weekends, and a
    kiosk on the wall is read then too.
    """
    enabled: bool = False
    every_hours: int = 3
    start: str = "06:00"
    end: str = "21:00"
    days: list[str] = field(default_factory=lambda: list(host.DAY_NAMES))
```

Add the field to `Settings` (beside `reports`):

```python
    refresh: RefreshConfig = field(default_factory=RefreshConfig)
```

Add a validator beside `_validate_report_time` (line 56):

```python
def _validate_refresh_time(field_name: str, value) -> None:
    """A [refresh].start/.end must be HH:MM, 24-hour. Raises ConfigError otherwise."""
    ok = False
    if _TIME_RE.match(str(value)):
        h, m = (int(x) for x in str(value).split(":"))
        ok = 0 <= h <= 23 and 0 <= m <= 59
    if not ok:
        raise ConfigError(f"[refresh] {field_name} must be HH:MM (24-hour), got {value!r}")
```

In `settings_from_doc`, after the `[reports]` loop (which ends at line 330), add:

```python
    raw_refresh = doc.get("refresh")
    if isinstance(raw_refresh, dict):
        start = raw_refresh.get("start", s.refresh.start)
        end = raw_refresh.get("end", s.refresh.end)
        _validate_refresh_time("start", start)
        _validate_refresh_time("end", end)
        # `bool` is an `int` subclass, so `every_hours = true` would otherwise read as 1.
        raw_every = raw_refresh.get("every_hours", s.refresh.every_hours)
        every = raw_every if isinstance(raw_every, int) and not isinstance(raw_every, bool) else s.refresh.every_hours
        raw_days = raw_refresh.get("days", host.DAY_NAMES)
        days = [str(d) for d in raw_days] if isinstance(raw_days, (list, tuple)) else list(host.DAY_NAMES)
        s.refresh = RefreshConfig(enabled=bool(raw_refresh.get("enabled", False)),
                                  every_hours=every, start=str(start), end=str(end), days=days)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS, all config tests

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/config.py tests/test_config.py
git commit -m "config: a [refresh] table for the app's own data-refresh schedule

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Multi-time validation and the reserved key

**Files:**
- Modify: `fridgesheet/host/__init__.py` (after `check_schedule`, line 72-80)
- Test: `tests/test_host_scheduling.py`

**Interfaces:**
- Consumes: `host.check_schedule`, `host.DAY_NAMES`
- Produces: `host.check_schedule_times(times: list[str], days: list[str]) -> None`, `host.DATA_REFRESH_KEY: str = "data-refresh"`, `host.RESERVED_KEYS: frozenset[str]`, `host.is_reserved(key: str) -> bool`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_host_scheduling.py`:

```python
# --- multi-time schedules and the reserved data-refresh key ----------------------------

def test_check_schedule_times_accepts_a_list():
    host.check_schedule_times(["06:00", "09:00", "12:00"], ["Mon", "Tue"])


def test_check_schedule_times_refuses_an_empty_list():
    with pytest.raises(host.SchedulingError, match="no times"):
        host.check_schedule_times([], ["Mon"])


def test_check_schedule_times_refuses_the_one_bad_time_among_good_ones():
    """Every time is checked before any file is written, so a bad one leaves nothing behind."""
    with pytest.raises(host.SchedulingError, match="HH:MM"):
        host.check_schedule_times(["06:00", "9:00", "12:00"], ["Mon"])


def test_the_data_refresh_key_is_reserved_however_it_is_spelled():
    """Task Scheduler's namespace is case-insensitive, so a hand-edited [reports.Data-Refresh]
    would otherwise collide with the app's own task."""
    for spelling in ("data-refresh", "Data-Refresh", "DATA-REFRESH", " data-refresh "):
        assert host.is_reserved(spelling), spelling
    assert not host.is_reserved("open-work")
    assert not host.is_reserved("view:3")


def test_the_reserved_key_does_not_collide_with_a_protected_name():
    """The whole point of the name: the hand-written refresh pair stays protected and the
    app's own schedule sits beside it."""
    from fridgesheet.host import scheduling_linux, scheduling_windows
    unit = scheduling_linux.timer_unit(host.DATA_REFRESH_KEY)
    assert unit not in scheduling_linux._FOREIGN_UNITS
    assert unit == "fridgesheet-data-refresh.timer"
    name = host.task_name(host.DATA_REFRESH_KEY)
    assert name.strip().casefold() not in scheduling_windows._FOREIGN_TASKS_FOLDED
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling.py -q -k "times or reserved"`
Expected: FAIL, `AttributeError: module 'fridgesheet.host' has no attribute 'check_schedule_times'`

- [ ] **Step 3: Write the implementation**

In `fridgesheet/host/__init__.py`, after `check_schedule` (line 80):

```python
def check_schedule_times(times: list[str], days: list[str]) -> None:
    """`check_schedule` for a schedule with several times a day.

    Every time is validated before any caller writes a file, so one bad time never leaves a
    half-installed schedule behind -- the same ordering `install` already relies on.
    """
    if not times:
        raise SchedulingError("no times configured for the schedule")
    for t in times:
        check_schedule(t, days)


#: The app's own data-refresh schedule. Deliberately *not* "refresh": on Linux that would
#: render to `fridgesheet-refresh.timer`, which `scheduling_linux._HAND_WRITTEN_REFRESH`
#: protects by name. A distinct key lets a household's hand-written refresh timer and this
#: one sit on the same machine, neither touching the other.
DATA_REFRESH_KEY = "data-refresh"

#: Keys a report may never claim. Compared stripped and case-folded, for the same reason
#: `scheduling_windows._FOREIGN_TASKS_FOLDED` is: Task Scheduler treats "Fridge Sheet -
#: Data-Refresh" and "Fridge Sheet - data-refresh" as one task, so a hand-edited
#: `[reports.Data-Refresh]` in config.toml would otherwise reach this app's own schedule.
#: The key is what is held here, not the rendered name: `task_name` only applies `safe_key`
#: to keys containing a colon.
RESERVED_KEYS = frozenset({DATA_REFRESH_KEY})
_RESERVED_FOLDED = frozenset(k.strip().casefold() for k in RESERVED_KEYS)


def is_reserved(key: str) -> bool:
    return str(key).strip().casefold() in _RESERVED_FOLDED
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/__init__.py tests/test_host_scheduling.py
git commit -m "host: validate a list of times, and reserve the data-refresh key

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Windows renders N triggers

**Files:**
- Modify: `fridgesheet/host/task.xml` (lines 6-17), `fridgesheet/host/scheduling_windows.py` (`render_task_xml` line 70-79, `install` line 86)
- Test: `tests/test_host_scheduling.py`

**Interfaces:**
- Consumes: `host.check_schedule_times`
- Produces: `scheduling_windows.render_task_xml(name, times: list[str], days, exe, args, workdir, description=None) -> str`, `scheduling_windows.install(key, times: list[str], days, exe, args, workdir, run=subprocess.run, *, title=None, home="", timezone="")`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_host_scheduling.py`:

```python
def test_one_time_renders_exactly_what_it_rendered_before():
    """The byte-identical promise: every task already installed keeps its current XML, so
    nothing on a machine the author cannot reach needs reinstalling."""
    xml = scheduling_windows.render_task_xml("Fridge Sheet - open-work", ["14:00"], ["Mon", "Fri"],
                                             "C:\\app\\FridgeSheet.exe", "run open-work --no-refresh", "C:\\app")
    assert xml.count("<CalendarTrigger>") == 1
    assert "<StartBoundary>2026-01-01T14:00:00</StartBoundary>" in xml
    assert "          <Monday />\n          <Friday />" in xml


def test_several_times_render_one_trigger_each():
    xml = scheduling_windows.render_task_xml("Fridge Sheet - data-refresh", ["06:00", "09:00", "12:00"],
                                             ["Mon"], "C:\\app\\FridgeSheet.exe", "refresh --record", "C:\\app")
    assert xml.count("<CalendarTrigger>") == 3
    for t in ("06:00", "09:00", "12:00"):
        assert f"<StartBoundary>2026-01-01T{t}:00</StartBoundary>" in xml
    assert xml.count("<Monday />") == 3          # every trigger carries its own day list


def test_a_bad_time_among_good_ones_renders_nothing():
    with pytest.raises(host.SchedulingError):
        scheduling_windows.render_task_xml("Fridge Sheet - data-refresh", ["06:00", "nope"], ["Mon"],
                                           "exe", "args", "wd")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling.py -q -k "renders"`
Expected: FAIL — `render_task_xml` receives a list where it expects a string; `check_schedule` rejects it.

- [ ] **Step 3: Write the implementation**

Replace `fridgesheet/host/task.xml` lines 6-17 (the `<Triggers>` block) with:

```xml
  <Triggers>
{triggers}
  </Triggers>
```

In `fridgesheet/host/scheduling_windows.py`, replace `render_task_xml`:

```python
_TRIGGER = """    <CalendarTrigger>
      <StartBoundary>2026-01-01T{time}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
{days}
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>"""


def render_task_xml(name: str, times: list[str], days: list[str], exe: str, args: str, workdir: str,
                    description: str | None = None) -> str:
    """The task XML, with one `<CalendarTrigger>` per time.

    A one-element `times` renders byte-for-byte what the single-trigger template rendered
    before, so every task already installed keeps the XML it has.
    """
    check_schedule_times(times, days)
    template = resources.files("fridgesheet.host").joinpath("task.xml").read_text(encoding="utf-8")
    day_xml = "\n".join(f"          <{_DAY_TAGS[d]} />" for d in days)
    triggers = "\n".join(_TRIGGER.format(time=t, days=day_xml) for t in times)
    desc = description or f"Fridge Sheet: {name.split(' - ', 1)[-1]}"
    return (template.replace("{description}", escape(desc))
                    .replace("{triggers}", triggers)
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))
```

Update the import at the top of the file so `check_schedule_times` is available beside `check_schedule`:

`scheduling_windows.py:10` currently reads:

```python
from . import CREATE_NO_WINDOW, DAY_NAMES, ScheduleInfo, SchedulingError, check_schedule, task_name
```

Replace `check_schedule` with `check_schedule_times`:

```python
from . import CREATE_NO_WINDOW, DAY_NAMES, ScheduleInfo, SchedulingError, check_schedule_times, task_name
```

Change `install`'s signature and its call:

```python
def install(key: str, times: list[str], days: list[str], exe: str, args: str, workdir: str, run=subprocess.run,
            *, title: str | None = None, home: str = "", timezone: str = "") -> None:
```

and inside it:

```python
    xml = render_task_xml(task_name(key), times, days, exe, args, workdir,
                          description=f"Fridge Sheet: {title}" if title else None)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling.py -q`
Expected: PASS. Other tests calling `install(key, "14:00", ...)` will now fail — update each to pass `["14:00"]`.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/task.xml fridgesheet/host/scheduling_windows.py tests/test_host_scheduling.py
git commit -m "windows: one CalendarTrigger per time, unchanged output for one time

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Linux emits N `OnCalendar=` lines

**Files:**
- Modify: `fridgesheet/host/scheduling_linux.py` (`timer_text` line 176-192, `install` line 232)
- Test: `tests/test_host_scheduling_linux.py`

**Interfaces:**
- Consumes: `host.check_schedule_times`
- Produces: `scheduling_linux.timer_text(key, title, times: list[str], days, timezone) -> str`, `scheduling_linux.install(key, times: list[str], days, exe, args, workdir, run=subprocess.run, *, title=None, home="", timezone="", unit_dir=None)`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_host_scheduling_linux.py`:

```python
def test_one_time_writes_the_timer_it_always_wrote():
    text = scheduling_linux.timer_text("open-work", "Open Work Sheet", ["14:00"],
                                       ["Mon", "Fri"], "America/New_York")
    assert text.count("OnCalendar=") == 1
    assert "OnCalendar=Mon,Fri 14:00 America/New_York" in text
    assert "Description=Fridge Sheet: Open Work Sheet (Mon, Fri at 14:00)" in text
    assert "Persistent=true" in text


def test_several_times_write_one_oncalendar_line_each():
    """systemd unions the elapse points of repeated OnCalendar= lines."""
    text = scheduling_linux.timer_text("data-refresh", "Data refresh", ["06:00", "09:00", "12:00"],
                                       ["Mon", "Tue"], "America/New_York")
    assert text.count("OnCalendar=") == 3
    for t in ("06:00", "09:00", "12:00"):
        assert f"OnCalendar=Mon,Tue {t} America/New_York" in text
    assert "(Mon, Tue at 06:00, 09:00, 12:00)" in text


def test_a_bad_time_among_good_ones_writes_nothing():
    with pytest.raises(host.SchedulingError):
        scheduling_linux.timer_text("data-refresh", "Data refresh", ["06:00", "24:00"],
                                    ["Mon"], "America/New_York")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling_linux.py -q -k "time"`
Expected: FAIL — `timer_text` joins a list where it expects a string.

- [ ] **Step 3: Write the implementation**

In `fridgesheet/host/scheduling_linux.py`, replace `timer_text`:

```python
def timer_text(key: str, title: str, times: list[str], days: list[str], timezone: str) -> str:
    """The timer that fires it.

    `OnCalendar` lists the days rather than writing a range: a list is right for any set a
    parent can tick, and a range would need contiguity logic that is one more thing to get
    wrong. Several times a day are several `OnCalendar=` lines -- systemd unions their
    elapse points -- rather than `OnUnitActiveSec`, which counts from the last activation and
    so drifts by however long the refresh took. The time zone is the app's configured one, so
    a laptop that travels still runs at the hour the household expects. `Persistent=true`
    fires a run missed while the machine was asleep -- the runner's own window guard then
    decides whether to print.
    """
    check_schedule_times(times, days)
    day_list = ",".join(days)
    suffix = f" {timezone}" if timezone else ""
    lines = "".join(f"OnCalendar={day_list} {t}{suffix}\n" for t in times)
    return (
        MARKER +
        f"[Unit]\nDescription=Fridge Sheet: {title} ({', '.join(days)} at {', '.join(times)})\n\n"
        f"[Timer]\nUnit={service_unit(key)}\n{lines}Persistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
```

Import `check_schedule_times` alongside the other `host` names at the top of the file.

Change `install`'s signature to take `times: list[str]` in place of `time: str`, and update its internal `timer_text(...)` call to pass `times` through. Its `check_schedule(time, days)` call (if present) becomes `check_schedule_times(times, days)`.

- [ ] **Step 4: Update the one production caller and the fake**

Both platforms' `install` now take a list, so the single caller must pass one.
`fridgesheet/web/schedules.py:236` currently reads:

```python
        scheduling.install(key, time, days, exe, args, workdir, title=report.title,
                           home=str(home), timezone=s.timezone)
```

Change it to pass a one-element list — a report still has exactly one time:

```python
        scheduling.install(key, [time], days, exe, args, workdir, title=report.title,
                           home=str(home), timezone=s.timezone)
```

And in `tests/web_fixtures.py`, `FakeScheduling.install` records `times` instead of `time`:

```python
    def install(self, key, times, days, exe, args, workdir, **kw):
        self._maybe_fail()
        self.installed.append({"key": key, "times": list(times), "days": list(days), **kw})
```

- [ ] **Step 5: Run the whole suite and fix the call sites it names**

Run: `.venv/bin/python -m pytest -q`
Expected: failures only in tests that call `install`/`timer_text`/`render_task_xml` with a bare
time string, or that assert on `installed[0]["time"]`. Change each to a one-element list and to
`["times"]`. Do not change any expected XML or unit text: a one-element list must render what it
rendered before, and a test that needed its expectations edited is a bug in Task 4 or 5, not in
the test.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/host/scheduling_linux.py fridgesheet/web/schedules.py \
        tests/web_fixtures.py tests/test_host_scheduling_linux.py
git commit -m "linux: one OnCalendar line per time, unchanged output for one time

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `command_for` knows the refresh key

**Files:**
- Modify: `fridgesheet/host/scheduling.py` (`command_for`, line 19-31)
- Test: `tests/test_host_scheduling.py`

**Interfaces:**
- Consumes: `host.DATA_REFRESH_KEY`
- Produces: `scheduling.command_for(key) -> tuple[str, str, str]` returning `refresh --record` args for the refresh key

- [ ] **Step 1: Write the failing test**

Append to `tests/test_host_scheduling.py`:

```python
def test_command_for_the_refresh_key_records_the_run(monkeypatch):
    """A report's schedule runs `--no-refresh` and trusts the snapshot. This is what makes
    the snapshot trustworthy -- and it must be `refresh --record`, not bare `refresh`, which
    writes snapshot.json and never ingests, so the kiosk would never change."""
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling.sys, "frozen", False, raising=False)
    _, args, _ = scheduling.command_for(host.DATA_REFRESH_KEY)
    assert args.endswith("refresh --record")
    assert "--no-refresh" not in args


def test_command_for_a_report_is_unchanged(monkeypatch):
    from fridgesheet.host import scheduling
    monkeypatch.setattr(scheduling.sys, "frozen", False, raising=False)
    _, args, _ = scheduling.command_for("open-work")
    assert args.endswith("run open-work --no-refresh")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling.py -q -k command_for`
Expected: FAIL — `args` is `-m fridgesheet.cli run data-refresh --no-refresh`

- [ ] **Step 3: Write the implementation**

In `fridgesheet/host/scheduling.py`, replace `command_for`:

```python
def command_for(key: str) -> tuple[str, str, str]:
    """(exe, args, workdir) that runs `key` from this installation.

    A report gets `--no-refresh` so a scheduled print never pulls Canvas/HAC itself: it
    trusts the independently-scheduled data refresh to have kept the snapshot warm, the same
    "one pull, many tools" design the README promises. An interactive `fridgesheet run`/
    `print-sheet` from a terminal keeps refreshing by default -- someone typing the command
    is presumably fine waiting for it.

    `DATA_REFRESH_KEY` is the other side of that bargain: the schedule that does the pulling.
    It runs `refresh --record` rather than bare `refresh`, because bare `refresh` writes
    `snapshot.json` and stops -- it does not ingest into the database the web app renders
    from, so a schedule wired to it would report success while the page never changed.
    """
    if key == DATA_REFRESH_KEY:
        if getattr(sys, "frozen", False):
            return sys.executable, "refresh --record", str(Path(sys.executable).parent)
        return sys.executable, "-m fridgesheet.cli refresh --record", str(Path.cwd())
    if getattr(sys, "frozen", False):
        return sys.executable, f"run {key} --no-refresh", str(Path(sys.executable).parent)
    return sys.executable, f"-m fridgesheet.cli run {key} --no-refresh", str(Path.cwd())
```

Add `DATA_REFRESH_KEY` to the re-export line at the top:

```python
from . import ScheduleInfo, SchedulingError, DATA_REFRESH_KEY, task_name  # noqa: F401
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_host_scheduling.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/scheduling.py tests/test_host_scheduling.py
git commit -m "scheduling: the refresh key runs refresh --record, not run --no-refresh

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `fridgesheet refresh --record`

**Files:**
- Modify: `fridgesheet/web/actions.py` (`refresh`, line 487-543), `fridgesheet/cli.py` (`cmd_refresh` line 117-121, parser line 411-415)
- Test: `tests/test_web_actions.py`, `tests/test_cli_refresh_record.py` *(new)*

**Interfaces:**
- Consumes: `web.actions.refresh`
- Produces: `web.actions.refresh(*, home, log, settings=None, collect=None, now=None, trigger: str = "web") -> RefreshResult`; CLI `fridgesheet refresh --record`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_refresh_record.py`:

```python
"""`refresh --record` -- what a scheduled data refresh actually runs.

Bare `refresh` writes snapshot.json and stops; it does not ingest into the database the web
app renders from. A schedule wired to it would fire, log success, and leave the kiosk showing
the same numbers, which is exactly the failure this flag exists to prevent.
"""
from __future__ import annotations

import pytest

from fridgesheet.web import db
from fridgesheet.web.stores import runs
from tests.web_fixtures import snapshot


def test_refresh_record_ingests_and_records_with_the_schedule_trigger(tmp_path, monkeypatch):
    from fridgesheet.web import actions
    lines = []
    result = actions.refresh(home=tmp_path, log=lines.append, collect=lambda s: snapshot(),
                             trigger="schedule")
    assert result.ok, result.message
    conn = db.open_db(tmp_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] > 0   # it ingested
        row = runs.latest(conn)
        assert row["report_key"] == "refresh" and row["trigger"] == "schedule"
    finally:
        conn.close()


def test_the_default_trigger_is_still_web(tmp_path):
    """The Refresh now button must keep saying what it always said."""
    from fridgesheet.web import actions
    actions.refresh(home=tmp_path, log=lambda _m: None, collect=lambda s: snapshot())
    conn = db.open_db(tmp_path)
    try:
        assert runs.latest(conn)["trigger"] == "web"
    finally:
        conn.close()


def test_the_cli_flag_is_wired_to_that_function(monkeypatch, tmp_path):
    from fridgesheet import cli
    seen = {}

    def fake_refresh(**kw):
        seen.update(kw)
        return type("R", (), {"ok": True, "message": "done", "refresh_id": 1})()

    monkeypatch.setattr("fridgesheet.web.actions.refresh", fake_refresh)
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    # `cli.main` ends in `sys.exit(args.fn(args))` (cli.py:461): it raises, never returns.
    with pytest.raises(SystemExit) as exc:
        cli.main(["refresh", "--record"])
    assert exc.value.code == 0
    assert seen["trigger"] == "schedule"


def test_bare_refresh_still_does_not_ingest(tmp_path, monkeypatch):
    from fridgesheet import cli
    called = {"actions": False}
    monkeypatch.setattr("fridgesheet.web.actions.refresh",
                        lambda **kw: called.__setitem__("actions", True))
    monkeypatch.setattr(cli.collector, "collect", lambda *a, **k: snapshot())
    monkeypatch.setattr(cli.collector, "summary", lambda *a, **k: {"sources": {"canvas": "ok"}})
    monkeypatch.setattr(cli, "load_settings", lambda: type("S", (), {"home": tmp_path})())
    with pytest.raises(SystemExit):
        cli.main(["refresh"])
    assert called["actions"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli_refresh_record.py -q`
Expected: FAIL — `refresh() got an unexpected keyword argument 'trigger'`

- [ ] **Step 3: Write the implementation**

In `fridgesheet/web/actions.py`, change the signature at line 487:

```python
def refresh(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
            collect=None, now: datetime | None = None, trigger: str = "web") -> RefreshResult:
```

Extend its docstring with:

```
    `trigger` is what the run is recorded as: "web" for the Refresh now button, "schedule"
    for the app's own data-refresh task. It is the only thing that differs between them --
    a scheduled refresh is this same collect / ingest / record, under the same lock.
```

Replace both hard-coded `"web"` arguments in the `runstore.record(...)` calls (lines 507 and 538) with `trigger`.

In `fridgesheet/cli.py`, replace `cmd_refresh`:

```python
def cmd_refresh(args) -> int:
    s = load_settings()
    if args.record:
        # The full path the Refresh now button takes: collect, ingest into the database the
        # web app renders from, and record the run. Bare `refresh` below writes only the
        # snapshot, which every MCP tool reads -- the database came later, with the web app.
        from .web import actions
        result = actions.refresh(home=s.home, log=lambda m: print(m), trigger="schedule")
        print(result.message)
        return 0 if result.ok else 1
    snap = collector.collect(s, include_hac=not args.no_hac, include_canvas=not args.no_canvas, kids_filter=args.kids)
    print(json.dumps(collector.summary(s, snap), indent=2))
    return 0 if all(v == "ok" for v in snap["sources"].values() if v) else 1
```

Add the flag to the parser at line 411-415:

```python
    r.add_argument("--record", action="store_true",
                   help="also ingest into the app's database and record the run (what a schedule runs)")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli_refresh_record.py tests/test_web_actions.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/actions.py fridgesheet/cli.py tests/test_cli_refresh_record.py
git commit -m "cli: refresh --record, the collect-ingest-record path a schedule runs

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: The Schedules page edits the refresh

**Files:**
- Modify: `fridgesheet/web/schedules.py` (add `refresh_row`/`save_refresh` after `save`, line 185+), `fridgesheet/web/routes/schedules.py`, `fridgesheet/web/templates/schedules.html`
- Test: `tests/test_web_schedules.py`, `tests/test_web_schedules_page.py`

**Interfaces:**
- Consumes: `config.RefreshConfig`, `refresh_schedule.refresh_times`, `host.DATA_REFRESH_KEY`, `scheduling.install/remove`
- Produces: `schedules.RefreshRow(enabled, every_hours, start, end, days, times, info, unsupported)`, `schedules.refresh_row(home, *, scheduling=None) -> RefreshRow`, `schedules.save_refresh(*, enabled, every_hours, start, end, days, home, log, scheduling=None) -> Outcome`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_schedules.py`:

```python
# --- the app's own data refresh --------------------------------------------------------

def test_saving_the_refresh_installs_one_task_with_every_time(tmp_path):
    from fridgesheet.web import schedules
    (tmp_path / schedules.LOGIN_STAMP).write_text("ok")
    fake = FakeScheduling()
    out = schedules.save_refresh(enabled=True, every_hours=3, start="06:00", end="12:00",
                                 days=["Mon", "Tue"], home=tmp_path, log=lambda _m: None,
                                 scheduling=fake)
    assert out.ok, out.errors
    assert len(fake.installed) == 1
    assert fake.installed[0]["key"] == "data-refresh"
    assert fake.installed[0]["times"] == ["06:00", "09:00", "12:00"]


def test_disabling_the_refresh_removes_the_task_and_keeps_the_settings(tmp_path):
    from fridgesheet import config
    from fridgesheet.web import schedules
    fake = FakeScheduling()
    schedules.save_refresh(enabled=False, every_hours=4, start="07:00", end="19:00",
                           days=["Mon"], home=tmp_path, log=lambda _m: None, scheduling=fake)
    assert fake.removed == ["data-refresh"]
    doc = config.load_config_doc(tmp_path / schedules.CONFIG_NAME)
    assert doc["refresh"]["every_hours"] == 4 and doc["refresh"]["enabled"] is False


def test_a_refusal_from_the_expansion_is_an_error_not_a_traceback(tmp_path):
    from fridgesheet.web import schedules
    fake = FakeScheduling()
    out = schedules.save_refresh(enabled=True, every_hours=1, start="00:00", end="23:00",
                                 days=["Mon"], home=tmp_path, log=lambda _m: None, scheduling=fake)
    assert not out.ok and any("12" in e for e in out.errors)
    assert fake.installed == []


def test_saving_the_refresh_leaves_a_report_schedule_alone(tmp_path):
    from fridgesheet.web import schedules
    (tmp_path / schedules.LOGIN_STAMP).write_text("ok")
    fake = FakeScheduling()
    schedules.save_refresh(enabled=True, every_hours=6, start="06:00", end="18:00",
                           days=["Mon"], home=tmp_path, log=lambda _m: None, scheduling=fake)
    assert [i["key"] for i in fake.installed] == ["data-refresh"]
    assert fake.removed == []
```

Append to `tests/test_web_schedules_page.py`:

```python
def test_the_page_shows_the_refresh_editor_with_its_expanded_times(tmp_path):
    body = app_for(tmp_path).get("/schedules").text
    assert "Refresh the data" in body
    assert 'name="every_hours"' in body and 'name="start"' in body and 'name="end"' in body
    assert 'hx-post="/schedules/refresh"' in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_schedules.py -q -k refresh`
Expected: FAIL, `AttributeError: module 'fridgesheet.web.schedules' has no attribute 'save_refresh'`

- [ ] **Step 3: Enforce the reserved key**

`host.is_reserved` exists from Task 3 and nothing calls it yet — a reserved list nothing
enforces is dead code. A report must not be able to claim the refresh key, because
`save` would then install a report's print command under the task the refresh schedule owns.

Add this test to `tests/test_web_schedules.py`:

```python
def test_a_report_may_not_claim_the_reserved_refresh_key(tmp_path):
    """config.toml is hand-editable and `schedule remove --all` feeds keys straight off
    disk, so a `[reports.data-refresh]` must be refused rather than installed over the
    app's own task."""
    from fridgesheet.web import schedules
    fake = FakeScheduling()
    out = schedules.save(key="Data-Refresh", enabled=True, time="14:00", days=["Mon"],
                         printer="", prints=True, home=tmp_path, log=lambda _m: None,
                         scheduling=fake)
    assert not out.ok and any("reserved" in e.lower() for e in out.errors)
    assert fake.installed == []
```

Then, in `fridgesheet/web/schedules.py::save`, ahead of the `registry.resolve` call at the
top of the function body:

```python
    if host.is_reserved(key):
        return Outcome(False, errors=[
            f"{key!r} is a name Fridge Sheet uses for its own data-refresh schedule; "
            "a report cannot be scheduled under it. Rename the report and save again."])
```

Run: `.venv/bin/python -m pytest tests/test_web_schedules.py -q -k reserved`
Expected: FAIL first (the save succeeds), then PASS once the guard is in.

- [ ] **Step 4: Write the refresh row and save**

In `fridgesheet/web/schedules.py`, add after `save`:

```python
@dataclass(frozen=True)
class RefreshRow:
    """The app's own data-refresh schedule, as the page shows it."""
    enabled: bool
    every_hours: int
    start: str
    end: str
    days: list[str]
    times: list[str]                        # the expansion, or [] when it does not expand
    problem: str = ""                       # why it does not expand, shown in place of the times
    info: host.ScheduleInfo | None = None
    unsupported: str = ""


def refresh_row(home: Path, *, scheduling=None) -> RefreshRow:
    if scheduling is None:
        from ..host import scheduling
    rc = _settings_for(home).refresh
    times, problem = [], ""
    try:
        times = refresh_schedule.refresh_times(rc.start, rc.end, rc.every_hours)
    except config.ConfigError as e:
        problem = str(e)
    info, unsupported = None, ""
    try:
        info = scheduling.describe(host.DATA_REFRESH_KEY)
    except host.NotSupported as e:
        unsupported = str(e)
    except Exception as e:                  # noqa: BLE001  same swallow as rows()
        log.warning("could not describe the data-refresh schedule (%s): %s", type(e).__name__, e)
        unsupported = f"the scheduler could not be read: {str(e)[:200]}"
    return RefreshRow(enabled=rc.enabled, every_hours=rc.every_hours, start=rc.start, end=rc.end,
                      days=list(rc.days), times=times, problem=problem, info=info, unsupported=unsupported)


def save_refresh(*, enabled: bool, every_hours: int, start: str, end: str, days: list[str],
                 home: Path, log: Callable[[str], None], scheduling=None) -> Outcome:
    """Write `[refresh]`, then make the host agree with it.

    Same order as `save`: validate before writing, write the file before calling the
    scheduler, so a scheduler that refuses costs the install and never the parent's typing.
    There is no ownership check: `data-refresh` is this app's own key and nothing else
    installs it -- the hand-written refresh pair lives at a different name and stays
    protected by `_HAND_WRITTEN_REFRESH`.
    """
    if scheduling is None:
        from ..host import scheduling
    try:
        times = refresh_schedule.refresh_times(start, end, every_hours)
        host.check_schedule_times(times, days)
    except (config.ConfigError, host.SchedulingError) as e:
        return Outcome(False, errors=[str(e)])

    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    tbl = _table(doc, "refresh")
    tbl.update(enabled=bool(enabled), every_hours=int(every_hours), start=str(start),
               end=str(end), days=[str(d) for d in days])
    config.save_config_doc(path, doc)
    messages = ["Saved the refresh schedule."]
    log(messages[-1])

    if not enabled:
        try:
            scheduling.remove(host.DATA_REFRESH_KEY)
        except host.NotSupported as e:
            return Outcome(True, messages + [str(e)])
        except host.SchedulingError as e:
            return Outcome(False, messages, [f"Saved, but the schedule could not be removed: {e}"])
        messages.append("The data is not refreshed on a schedule.")
        log(messages[-1])
        return Outcome(True, messages)

    if not (home / LOGIN_STAMP).exists():
        messages.append("Saved, but nothing is installed yet: run Test login on the Settings page first, "
                        "then save this schedule again.")
        log(messages[-1])
        return Outcome(True, messages)

    s = _settings_for(home)
    exe, args, workdir = scheduling.command_for(host.DATA_REFRESH_KEY)
    try:
        scheduling.install(host.DATA_REFRESH_KEY, times, days, exe, args, workdir,
                           title="Data refresh", home=str(home), timezone=s.timezone)
    except host.NotSupported as e:
        return Outcome(True, messages + [str(e)])
    except host.SchedulingError as e:
        return Outcome(False, messages, [f"Saved, but the schedule could not be installed: {e}"])
    messages.append(f"Refreshing at {', '.join(times)} on {', '.join(days)}.")
    log(messages[-1])
    return Outcome(True, messages)
```

Add `from .. import refresh_schedule` to the imports at the top of the file.

In `fridgesheet/web/routes/schedules.py`, pass `refresh=schedules.refresh_row(state.home, scheduling=state.extra.get("scheduling"))` into the template context of the GET handler, and add:

```python
@router.post("/schedules/refresh")
async def save_refresh(request: Request, conn: sqlite3.Connection = Db, state=State):
    form = await request.form()
    out = schedules.save_refresh(
        enabled=bool(form.get("enabled")),
        every_hours=int(form.get("every_hours") or 3),
        start=str(form.get("start") or "06:00"),
        end=str(form.get("end") or "21:00"),
        days=[str(d) for d in form.getlist("days")],
        home=state.home, log=lambda _m: None,
        scheduling=state.extra.get("scheduling"))
    state.reload()
    return _page(request, conn, state, messages=out.messages, errors=out.errors)
```

`routes/schedules.py:31` already has `_page(request, conn, state, *, messages=(), errors=())`, which the new handler reuses as written. Add `refresh=schedules.refresh_row(...)` and `DAY_NAMES=host.DAY_NAMES` to the `render(...)` call inside it (line 34) so both the GET and this POST get them.

In `fridgesheet/web/templates/schedules.html`, add above the per-report sections:

```html
<h3>Refresh the data</h3>
<p class="muted">How often Fridge Sheet pulls Canvas and HAC. A printed report reads whatever
  the last refresh left behind, so this is what keeps it — and the page on the wall — current.</p>
<form hx-post="/schedules/refresh" hx-target="body">
  <label><input type="checkbox" name="enabled" {{ 'checked' if refresh.enabled }}> Refresh on a schedule</label>
  <label>Every <input type="number" name="every_hours" min="1" max="24" value="{{ refresh.every_hours }}"> hours</label>
  <label>Between <input type="time" name="start" value="{{ refresh.start }}"></label>
  <label>and <input type="time" name="end" value="{{ refresh.end }}"></label>
  <span>{% for d in DAY_NAMES %}<label><input type="checkbox" name="days" value="{{ d }}"
    {{ 'checked' if d in refresh.days }}> {{ d }}</label>{% endfor %}</span>
  {% if refresh.problem %}<p class="warn">{{ refresh.problem }}</p>
  {% elif refresh.times %}<p class="muted">Refreshes at {{ refresh.times | join(', ') }}.</p>{% endif %}
  <button class="primary">Save</button>
</form>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_schedules.py tests/test_web_schedules_page.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/schedules.py fridgesheet/web/routes/schedules.py \
        fridgesheet/web/templates/schedules.html \
        tests/test_web_schedules.py tests/test_web_schedules_page.py
git commit -m "schedules: an editor for the app's own data refresh

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: The staleness banner

**Files:**
- Create: `fridgesheet/web/staleness.py`
- Modify: `fridgesheet/web/app.py` (`page_context`, line 143-156), `fridgesheet/web/templates/_header.html`, `fridgesheet/web/static/app.css`
- Test: `tests/test_web_staleness.py` *(new)*

**Interfaces:**
- Consumes: `runner.MAX_DATA_AGE_HOURS`, `web.stores.refreshes`
- Produces: `staleness.Staleness(hours: int, last_good: str | None, reason: str)`, `staleness.check(conn, now: datetime, ceiling_hours: int = MAX_DATA_AGE_HOURS) -> Staleness | None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_staleness.py`:

```python
"""The banner that says the data is old, and the one number it shares with the runner."""
from __future__ import annotations

import json
import re
from datetime import timedelta

from fridgesheet import runner
from fridgesheet.web import db, staleness
from tests.web_fixtures import NOW, app_for, seed


def _refresh(conn, at, ok, sources=None):
    conn.execute("INSERT INTO refreshes(started_at, finished_at, sources, ok) VALUES (?,?,?,?)",
                 (at.isoformat(), at.isoformat(), json.dumps(sources or {"canvas": "ok", "hac": "ok"}), int(ok)))
    conn.commit()


def test_the_ceiling_is_the_runners_own_constant():
    """A banner with its own threshold could say the data is fine while the 2 PM print
    refuses it as stale -- the app disagreeing with itself about one fact."""
    assert staleness.CEILING_HOURS is runner.MAX_DATA_AGE_HOURS


def test_fresh_data_has_no_banner(tmp_path):
    conn = seed(tmp_path)
    assert staleness.check(conn, NOW) is None
    conn.close()


def test_data_past_the_ceiling_reports_its_age(tmp_path):
    conn = db.open_db(tmp_path)
    _refresh(conn, NOW - timedelta(hours=31), ok=True)
    s = staleness.check(conn, NOW)
    conn.close()
    assert s is not None and s.hours == 31


def test_it_names_the_last_successful_refresh_not_the_last_attempt(tmp_path):
    """On a host that has been failing to log in since Sunday, "refreshed this morning" is
    true and useless: what a parent needs is when the data is actually from."""
    conn = db.open_db(tmp_path)
    _refresh(conn, NOW - timedelta(hours=40), ok=True)
    _refresh(conn, NOW - timedelta(hours=2), ok=False, sources={"canvas": "login_required: expired", "hac": "ok"})
    s = staleness.check(conn, NOW)
    conn.close()
    assert s.hours == 40
    assert "login_required" in s.reason and "canvas" in s.reason.lower()


def test_no_refresh_at_all_is_stale_rather_than_a_crash(tmp_path):
    conn = db.open_db(tmp_path)
    s = staleness.check(conn, NOW)
    conn.close()
    assert s is not None and s.last_good is None


def test_the_banner_renders_on_every_page_when_the_data_is_old(tmp_path):
    conn = db.open_db(tmp_path)
    _refresh(conn, NOW - timedelta(hours=31), ok=True)
    conn.close()
    for path in ("/", "/runs", "/settings"):
        body = app_for(tmp_path).get(path).text
        assert "31 hours old" in body, path
        banner = re.search(r'<p class="stale">.*?</p>', body, re.S)
        assert banner and 'href="/">Refresh now</a>' in banner.group(0), path


def test_no_banner_when_the_data_is_fresh(tmp_path):
    seed(tmp_path).close()
    assert "hours old" not in app_for(tmp_path).get("/").text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_staleness.py -q`
Expected: FAIL, `ImportError: cannot import name 'staleness'`

- [ ] **Step 3: Write the implementation**

Create `fridgesheet/web/staleness.py`:

```python
"""How old the data is, and whether that is old enough to say so on every page.

The ceiling is the runner's own, imported rather than re-spelled: past it a `--no-refresh`
run refuses to print ("snapshot is stale ... nothing printed"). A banner with a threshold of
its own could show a kiosk claiming the data is fine while the afternoon print fails as
stale -- the app disagreeing with itself about one fact.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..runner import MAX_DATA_AGE_HOURS
from ..dates import parse_iso                 # moved out of web/app.py in this task

CEILING_HOURS = MAX_DATA_AGE_HOURS


@dataclass(frozen=True)
class Staleness:
    hours: int                  # whole hours since the last refresh that actually succeeded
    last_good: str | None       # its ISO timestamp, or None when there has never been one
    reason: str                 # why the most recent attempt did not help, or ""


def _latest_good(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM refreshes WHERE ok = 1 ORDER BY id DESC LIMIT 1").fetchone()


def _why(conn: sqlite3.Connection) -> str:
    """The failing sources of the most recent attempt, if it failed."""
    row = conn.execute("SELECT * FROM refreshes ORDER BY id DESC LIMIT 1").fetchone()
    if row is None or row["ok"]:
        return ""
    try:
        bad = {k: v for k, v in json.loads(row["sources"]).items() if v != "ok"}
    except (ValueError, TypeError):
        return ""
    return "; ".join(f"{k.upper() if k == 'hac' else k.capitalize()}: {v}" for k, v in sorted(bad.items()))


def check(conn: sqlite3.Connection, now: datetime, ceiling_hours: int = CEILING_HOURS) -> Staleness | None:
    """None when the data is fresh enough to print from; a `Staleness` when it is not."""
    good = _latest_good(conn)
    if good is None:
        return Staleness(hours=ceiling_hours + 1, last_good=None, reason=_why(conn))
    started = parse_iso(good["started_at"])
    hours = int((now - started.astimezone(now.tzinfo)).total_seconds() // 3600)
    if hours < ceiling_hours:
        return None
    return Staleness(hours=hours, last_good=good["started_at"], reason=_why(conn))
```

`web/app.py:90::_parse` is the ISO parser the header filters already use. Importing it from
`app` here would be a cycle (`app` imports `staleness`), so in this step move the body of
`_parse` into `fridgesheet/dates.py` as `parse_iso`, delete it from `app.py`, and import it
there **under its old name** so the three call sites at `app.py:96,104,110` are untouched:

```python
from ..dates import parse_iso as _parse
```

`staleness.py` imports `parse_iso` directly. One parser, no cycle, no call-site churn.

In `fridgesheet/web/app.py`, add to the `page_context` dict:

```python
        "staleness": staleness.check(conn, state.now()),
```

and `from . import db, staleness, updates` at the top.

In `fridgesheet/web/templates/_header.html`, add immediately after the closing `</header>`:

```html
{% if staleness %}
{# One bar on the page that says something is wrong, beside `warnings` rather than competing
   with them. "Refresh now" is a link to the Dashboard, where that control already lives --
   the header would otherwise need its own jobs-worker check, htmx target and busy state. #}
<p class="stale">⚠ <strong>This data is {{ staleness.hours }} hours old.</strong>
  {% if staleness.last_good %}Last good refresh {{ staleness.last_good | wd_md_time }}.{% else %}Nothing has been refreshed yet.{% endif %}
  {% if staleness.reason %} {{ staleness.reason }}.{% endif %}
  <a href="/">Refresh now</a></p>
{% endif %}
```

In `fridgesheet/web/static/app.css`, add:

```css
/* The data is older than the runner will print from (web/staleness.py). Loud, because on a
   kiosk nobody reads the Runs page. */
.stale { background: #fdecea; border: 1px solid var(--warn); color: var(--warn);
         padding: 8px 12px; margin: 0 0 12px; border-radius: 4px; }
.stale a { color: var(--warn); }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_staleness.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all pass except the one documented `test_host_credentials` failure.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/staleness.py fridgesheet/web/app.py \
        fridgesheet/web/templates/_header.html fridgesheet/web/static/app.css \
        tests/test_web_staleness.py
git commit -m "web: say on every page when the data is older than the runner will print from

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Documentation

**Files:**
- Modify: `README.md` (section 5), `docs/windows.md`, `env.example`
- Test: `tests/test_rebrand.py` (or wherever doc assertions live) — no new test required; this task is verified by the full suite still passing.

- [ ] **Step 1: Update README section 5**

Add after the existing systemd instructions:

```markdown
Since 0.5.0 the app can schedule this itself, on Windows as well as Linux: tick **Refresh on
a schedule** on the Schedules page and set an interval and a window. It installs under its own
name (`fridgesheet-data-refresh.timer`, or the task `Fridge Sheet - data-refresh`), so a
hand-written timer from this section and the app's own schedule can both exist on one machine
— the app never touches the hand-written pair. If you use the app's schedule, disable the
hand-written one yourself:

    systemctl --user disable --now fridgesheet-refresh.timer
```

- [ ] **Step 2: Document `[refresh]` in `env.example`**

```toml
# [refresh] -- how often the app pulls Canvas and HAC by itself. A scheduled report reads
# whatever the last refresh left behind, so this is what keeps a printed sheet, and the
# browser page, current. At most 12 refreshes a day.
# [refresh]
# enabled = true
# every_hours = 3
# start = "06:00"
# end = "21:00"
# days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
```

- [ ] **Step 3: Note the staleness banner in `docs/windows.md`**

```markdown
If the data goes older than 24 hours, every page carries a banner saying how old it is and
when the last good refresh was. That is the same ceiling at which a scheduled print refuses
to run, so the banner and the missing sheet always agree about why.
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: unchanged — all pass except the documented `test_host_credentials` failure.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/windows.md env.example
git commit -m "docs: the app's own refresh schedule, and the staleness banner

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Verification

After Task 10, before opening a PR:

1. `.venv/bin/python -m pytest -q` — one documented failure, no others.
2. `git log --oneline main..HEAD` — ten commits, one per task.
3. Confirm by hand that no already-installed schedule changed: render a one-time report task and unit and diff against `git show main:fridgesheet/host/task.xml` expectations. Tasks 4 and 5 both pin this, so a green suite is the evidence.
4. The PR must say what cannot be verified here: whether Task Scheduler actually fires a multi-trigger task on `graphy`. The check is the Runs page after one day — rows with `trigger = schedule` at the configured hours, or not.

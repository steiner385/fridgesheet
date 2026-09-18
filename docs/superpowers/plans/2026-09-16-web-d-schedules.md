# Web app D part 2: schedules on both platforms

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Any report — the open-work sheet or a saved view — can be put on a weekly schedule from a Schedules page, and the app writes the systemd user units or the Windows task that makes it happen.

**Architecture:** `host/scheduling_linux.py` stops raising `NotSupported` and grows the same
shape its Windows sibling has had since Plan B: `install` writes
`~/.config/systemd/user/fridgesheet-<key>.service` and `.timer` and enables the timer, `remove`
disables and deletes them, `describe` reports on them — every one taking its
`run=subprocess.run` so the argv is asserted on any OS. One report key, one OS object:
`host.safe_key` turns `view:7` into the `view-7` that a unit name and a task name can both
carry. A new `web/schedules.py` holds the page's work as plain functions (config.toml's
`[reports.<key>]` and the scheduler, changed together), and `web/routes/schedules.py` is the
thin FastAPI layer over it. The schedule controls leave the Settings page so that a schedule
has exactly one editor.

**Tech Stack:** Python 3.12, systemd user units, Windows Task Scheduler, FastAPI + Jinja2 +
htmx, `sqlite3`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-fridgesheet-web-app-design.md` — sections 5
(Schedules page), 9 (jobs and the timers), 10 (service model per platform), 12 (testing),
13 (plan D).

**Issues closed:** #26 (Linux scheduling adapter), #27 (Schedules page), and the two
`cmd_schedule` items carried in #35.

## Global Constraints

- Python 3.12; standard library only for anything new here. No new dependency.
- Every `host/` function that runs a command takes `run=subprocess.run` as a keyword
  argument, so tests assert the argv on any platform. Every function that writes a unit
  takes `unit_dir: Path | None = None`, so tests write into `tmp_path`.
- **Never run a real `systemctl` or `schtasks` while implementing or testing this plan.**
  Tony's own units are live on this machine. Tests use injected fakes; there is no test
  that shells out.
- **Never write to, enable, disable or delete `fridgesheet-print-sheet.{service,timer}` or
  `fridgesheet-refresh.{service,timer}`.** They are hand-written, they are Tony's, and
  spec section 10 says existing ones are untouched. The app reads them and reports them;
  that is all.
- Existing behaviour that must not change: `task_name("open-work") == "Fridge Sheet - open-work"`,
  the Windows task XML, `ScheduleInfo` equality against 4-argument construction, and
  `doctor`'s scheduler probe continuing to find Tony's hand-written timer.
- Day names are `Mon Tue Wed Thu Fri Sat Sun` (`config.WEEKDAYS` is the Mon–Fri default).
  Times are `HH:MM`, 24-hour, validated with the same message on both platforms.
- The test command is
  `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q`.
  Run the whole suite at the end of every task; it is 448 tests and takes ~15 s.
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## Decisions this plan makes

These were open questions before the plan; an implementer must not re-litigate them.

**1. A unit or task name carries the report's id, never its title.**
`view:7` is a legal report key, an illegal systemd unit name (a colon introduces a unit
*instance*) and an illegal Task Scheduler name. `host.safe_key` reduces a key to
`[A-Za-z0-9._-]`, so `view:7` → `view-7` and `open-work` → `open-work` (unchanged — every
existing Windows task keeps its name). The report's **title never appears in the name**: a
title is user-editable, and a unit named `fridgesheet-weekly-summary-7.timer` would be orphaned
the first time a parent renamed the report — still firing every week, no longer findable by
`remove`. The human-readable name lives in the unit's `Description=`, which is rewritten on
every save and costs nothing when it goes stale.

**2. The generated units are `fridgesheet-<safe-key>.service` + `.timer`, never the legacy names.**
`scheduling_linux._unit` today maps `open-work` to `fridgesheet-print-sheet.timer`, which is
Tony's hand-written unit running the *old* `print-sheet` command. Writing there would
overwrite a unit the app did not author. The app writes `fridgesheet-open-work.{service,timer}`
instead, and:
- `describe` looks at the app's unit first and falls back to the legacy one read-only, so
  Tony's `doctor` and Settings keep reporting the timer that is actually printing his sheet.
  The fallback sets `ScheduleInfo.manageable = False`.
- `install` **refuses** with a `SchedulingError` when the legacy timer for that key is
  enabled, naming the exact `systemctl --user disable --now fridgesheet-print-sheet.timer` that
  clears the way. Installing alongside it would print the sheet twice every afternoon.
- `remove` never touches a legacy unit.

**3. `TimeoutStartSec=900` and `Type=oneshot` are not decoration.**
Tony's hand-written service documents why: a refresh of three kids across two sites (plus a
possible login) runs one to three minutes, and systemd's default 90-second start timeout
would `SIGTERM` it partway through every single run. The generated service carries the same
setting and the same reasoning in a comment.

**4. `OnCalendar` lists the days, it does not compute ranges.**
`Mon,Tue,Wed,Thu,Fri 14:00 America/New_York`, never `Mon..Fri`. A list is correct for any
set of days a parent can tick; a range needs contiguity logic that would be one more thing
to get wrong. The time zone comes from `settings.timezone`, so a laptop that travels still
prints at 2 PM Eastern.

**5. "Printer or PDF-only" is config, not argv.**
`[reports.<key>]` gains `printer = "..."` and `print = true|false`. The runner reads them,
so changing the printer for a schedule does not mean reinstalling a unit, and the CLI and
the web agree about what a scheduled run does. PDF-only is deliberately **not** `--dry-run`:
`--dry-run` also switches off the print-window guard and the already-printed-today guard,
and a scheduled PDF-only run wants both of those guards exactly as a printing run has them.

**6. The Schedules page is the only editor of a schedule.**
The `Scheduled printing` checkbox and the `Print time` field leave the Settings page
(Task 9). Two pages writing the same `[reports.open-work]` keys and calling the same
installer is how a page ends up showing one thing while the scheduler does another. Settings
keeps `Days ahead` and `Overdue days`, which are the open-work *report's* build options and
not schedule at all, and links to Schedules.

**7. The time on the Schedules page is also the runner's print window.**
`runner._window_open(now, rc_cfg.time)` reads the same `[reports.<key>].time`. This is
correct and wanted: a catch-up run the next morning must still refuse to print yesterday's
sheet. It is called out here so nobody "cleans up" by moving the time into the unit file
only.

---

## File structure

**Created:**
- `fridgesheet/web/schedules.py` — the Schedules page's work as plain functions: read
  every report's schedule (`rows`), and write one (`save`). No FastAPI import.
- `fridgesheet/web/routes/schedules.py` — `GET /schedules`, `POST /schedules`.
- `fridgesheet/web/templates/schedules.html` — one form per report.
- `tests/test_host_scheduling_linux.py` — the unit text, the argv, the legacy rules.
- `tests/test_web_schedules.py` — `schedules.rows` / `schedules.save` with a fake scheduler.
- `tests/test_web_schedules_page.py` — the page through `TestClient`.

**Modified:**
- `fridgesheet/host/__init__.py` — `safe_key`, `DAY_NAMES`, `check_schedule`,
  `ScheduleInfo.manageable`; `task_name` sanitises.
- `fridgesheet/host/scheduling_linux.py` — the whole module: unit text, install, remove,
  describe.
- `fridgesheet/host/scheduling_windows.py` — `render_task_xml` takes an optional
  `description`; day/time validation moves to `host.check_schedule`.
- `fridgesheet/config.py` — `ReportConfig.printer` and `.prints`, parsed from `printer`
  and `print`.
- `fridgesheet/runner.py` — the per-report printer and the PDF-only branch.
- `fridgesheet/reports/__init__.py` — `available(home)`.
- `fridgesheet/cli.py` — `cmd_schedule` resolves `view:<id>`; help text; `cmd_reports`
  lists saved reports too.
- `fridgesheet/web/actions.py` — `printer_names` moves here; the schedule fields leave
  `FormValues`, `validate`, `load_form` and `save`.
- `fridgesheet/web/routes/settings.py` — loses `_printers`, `time` and `scheduled`.
- `fridgesheet/web/templates/settings.html` — the schedule controls become a link.
- `fridgesheet/web/templates/base.html` — a Schedules link in the nav.
- `fridgesheet/web/app.py` — register the router.
- `tests/test_host_scheduling.py`, `tests/test_config.py`, `tests/test_runner.py`,
  `tests/test_reports.py`, `tests/test_web_actions.py`, `tests/test_web_settings_page.py`,
  `tests/test_web_pages.py` — follow the changes above.

---

### Task 1: One safe name for a report key, on both platforms

A report key reaches two operating-system namespaces, and `view:7` is legal in neither.
This task adds the single reduction both use, plus the shared day/time validation, plus the
`ScheduleInfo` field that lets a page tell "the app installed this" from "someone wrote this
by hand."

**Files:**
- Modify: `fridgesheet/host/__init__.py`
- Modify: `fridgesheet/host/scheduling_windows.py:17-30` (`render_task_xml`)
- Test: `tests/test_host_scheduling.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `host.safe_key(key: str) -> str`
  - `host.DAY_NAMES: tuple[str, ...]` — `("Mon","Tue","Wed","Thu","Fri","Sat","Sun")`
  - `host.check_schedule(time: str, days: list[str]) -> None` — raises `SchedulingError`
  - `host.ScheduleInfo(managed_by, installed, next_run, last_result, manageable=True)`
  - `host.task_name(key)` — now `f"Fridge Sheet - {safe_key(key)}"`
  - `scheduling_windows.render_task_xml(name, time, days, exe, args, workdir, description=None)`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_host_scheduling.py`:

```python
def test_safe_key_makes_a_name_both_operating_systems_accept():
    """A view report's key is `view:<id>`. A colon starts an instance name in systemd and is
    refused outright by Task Scheduler, so it never reaches either."""
    assert host.safe_key("open-work") == "open-work"          # every existing task keeps its name
    assert host.safe_key("view:7") == "view-7"
    assert host.safe_key("view:7:extra") == "view-7-extra"
    assert host.safe_key("a/b\\c d") == "a-b-c-d"
    assert host.safe_key("...") == "report"                   # nothing usable left
    assert host.safe_key("") == "report"
    assert host.task_name("view:7") == "Fridge Sheet - view 7"


def test_check_schedule_speaks_once_for_both_platforms():
    host.check_schedule("14:00", ["Mon", "Sun"])              # no exception
    with pytest.raises(scheduling.SchedulingError, match="Monday"):
        host.check_schedule("14:00", ["Mon", "Monday"])
    with pytest.raises(scheduling.SchedulingError, match="no days"):
        host.check_schedule("14:00", [])
    with pytest.raises(scheduling.SchedulingError, match="HH:MM"):
        host.check_schedule("9:00", ["Mon"])
    with pytest.raises(scheduling.SchedulingError, match="HH:MM"):
        host.check_schedule("24:00", ["Mon"])


def test_schedule_info_says_whether_the_app_may_change_it():
    """A hand-written unit is reported and left alone; the page reads `manageable` to decide
    whether to offer a Remove button. The default keeps every existing construction working."""
    assert host.ScheduleInfo("systemd", True, "x", None).manageable is True
    assert host.ScheduleInfo("systemd", True, "x", None, False).manageable is False
    assert host.ScheduleInfo("task-scheduler", True, "x", "0") == host.ScheduleInfo("task-scheduler", True, "x", "0")


def test_task_xml_description_can_be_the_reports_title():
    xml = scheduling_windows.render_task_xml("Fridge Sheet - view-7", "16:00", ["Fri"], "x", "run view:7", ".",
                                             description="Fridge Sheet: Weekly summary")
    assert "<Description>Fridge Sheet: Weekly summary</Description>" in xml


def test_windows_install_takes_the_same_keywords_as_the_linux_one():
    """One call site serves both platforms, so both signatures take `title`, `home` and
    `timezone`. Task Scheduler carries neither of the last two -- the task runs in the
    logged-in session's own environment, and StartBoundary is local time by definition."""
    seen = {}

    def run(cmd, **kw):
        seen["xml"] = Path(cmd[cmd.index("/XML") + 1]).read_text(encoding="utf-16")
        return _R(0, "SUCCESS")

    scheduling_windows.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=run,
                               title="Weekly summary", home="/anything", timezone="America/New_York")
    assert "<Description>Fridge Sheet: Weekly summary</Description>" in seen["xml"]
```

Add `import host` to the module's imports:

```python
from fridgesheet import host
from fridgesheet.host import NotSupported, scheduling, scheduling_linux, scheduling_windows
```

Note `task_name("view:7")` is `"Fridge Sheet - view 7"` — the dash-space-dash of
`"Fridge Sheet - view-7"` reads badly and Task Scheduler is happy with a space. `safe_key`
returns `view-7`; `task_name` replaces the hyphens it introduced with spaces for display
only. Keep the two separate: `safe_key` is for file names, `task_name` is for a title.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_host_scheduling.py -q`
Expected: FAIL — `AttributeError: module 'fridgesheet.host' has no attribute 'safe_key'`.

- [ ] **Step 3: Implement**

In `fridgesheet/host/__init__.py`, add `import re` to the imports and then, replacing the
existing `task_name`:

```python
DAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_key(key: str) -> str:
    """A report key reduced to what a systemd unit name and a Task Scheduler task name both take.

    `view:7` is a legal report key and illegal in both namespaces -- a colon introduces a unit
    instance in systemd and is refused outright by Task Scheduler. `open-work` comes back
    unchanged, so every task installed before this existed keeps the name it has.

    The report's title is deliberately not part of this. A title is user-editable, and an
    object named after one is orphaned by the first rename: still firing on its schedule, no
    longer the name `remove` computes. The title goes in the description instead.
    """
    return _UNSAFE.sub("-", key).strip("-") or "report"


def check_schedule(time: str, days: list[str]) -> None:
    """Raise `SchedulingError` unless this is a schedule both platforms can install."""
    bad = [d for d in days if d not in DAY_NAMES]
    if not days:
        raise SchedulingError("no days configured for the schedule")
    if bad:
        raise SchedulingError(f"unknown day name(s) {bad!r}; use {', '.join(DAY_NAMES)}")
    if not _TIME_RE.match(str(time)):
        raise SchedulingError(f"time must be HH:MM (24-hour), got {time!r}")


def task_name(key: str) -> str:
    """The Windows task's display name. `safe_key`'s hyphens read badly in a title, so they
    become spaces here; this is a label, not a file name."""
    return f"Fridge Sheet - {safe_key(key).replace('-', ' ') if ':' in key else key}"
```

`task_name` keeps a key with no colon verbatim so `open-work` stays `Fridge Sheet - open-work`.

And `ScheduleInfo`:

```python
@dataclass(frozen=True)
class ScheduleInfo:
    managed_by: str                 # "task-scheduler" | "systemd" | "systemd (hand-written)"
    installed: bool
    next_run: str | None
    last_result: str | None
    manageable: bool = True         # False: found, but this app did not write it and will not change it
```

In `fridgesheet/host/scheduling_windows.py`, delete `_TIME_RE` and the day/time checks from
`render_task_xml`, import `check_schedule` and `DAY_NAMES`, and take the description:

```python
from . import CREATE_NO_WINDOW, DAY_NAMES, ScheduleInfo, SchedulingError, check_schedule, task_name

_DAY_TAGS = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday",
             "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}


def render_task_xml(name: str, time: str, days: list[str], exe: str, args: str, workdir: str,
                    description: str | None = None) -> str:
    check_schedule(time, days)
    template = resources.files("fridgesheet.host").joinpath("task.xml").read_text(encoding="utf-8")
    day_xml = "\n".join(f"          <{_DAY_TAGS[d]} />" for d in days)
    desc = description or f"Fridge Sheet: {name.split(' - ', 1)[-1]}"
    return (template.replace("{description}", escape(desc))
                    .replace("{start}", f"2026-01-01T{time}:00")
                    .replace("{days}", day_xml)
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))
```

`SchedulingError` stays imported: `install` still raises it.

Then give `install` the keywords its Linux sibling will take in Task 3, so one call site
serves both platforms:

```python
def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run,
            *, title: str | None = None, home: str = "", timezone: str = "") -> None:
    """`home` and `timezone` are accepted and unused: a task runs in the logged-in session's
    own environment, and `StartBoundary` is local time by definition. They are in the
    signature so `scheduling.install` is one call on both platforms."""
    xml = render_task_xml(task_name(key), time, days, exe, args, workdir,
                          description=f"Fridge Sheet: {title}" if title else None)
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_host_scheduling.py -q`
Expected: PASS, including every pre-existing Windows test — the validation messages are
unchanged, which is the point of copying them verbatim.

Then the whole suite:
`env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q` → 448 + 4 passed.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/__init__.py fridgesheet/host/scheduling_windows.py tests/test_host_scheduling.py
git commit -m "host: one safe name and one schedule check for both platforms

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The text of a systemd user timer

Pure functions, no filesystem and no `systemctl`, so every line of the generated units is
pinned by a test that runs on any OS.

**Files:**
- Modify: `fridgesheet/host/scheduling_linux.py`
- Test: `tests/test_host_scheduling_linux.py` (create)

**Interfaces:**
- Consumes: `host.safe_key`, `host.check_schedule` (Task 1).
- Produces:
  - `scheduling_linux.unit_stem(key) -> str` — `"fridgesheet-open-work"`
  - `scheduling_linux.service_unit(key) -> str` / `timer_unit(key) -> str`
  - `scheduling_linux._unit_dir(d: Path | None = None) -> Path` — private, so the public
    keyword can be `unit_dir=`, matching `service_linux.install(..., unit_dir=None)`
  - `scheduling_linux.service_text(key, title, exe, args, workdir, home) -> str`
  - `scheduling_linux.timer_text(key, title, time, days, timezone) -> str`
  - `scheduling_linux.LEGACY_TIMERS: dict[str, str]`
  - `scheduling_linux.TIMEOUT_START_SEC: int`

- [ ] **Step 1: Write the failing test**

Create `tests/test_host_scheduling_linux.py`:

```python
"""The systemd user units the app writes for a scheduled report. Nothing here runs systemctl."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fridgesheet.host import ScheduleInfo, SchedulingError, scheduling_linux as sl


def test_unit_names_come_from_the_key_alone():
    assert sl.unit_stem("open-work") == "fridgesheet-open-work"
    assert sl.service_unit("open-work") == "fridgesheet-open-work.service"
    assert sl.timer_unit("view:7") == "fridgesheet-view-7.timer"          # no colon: systemd reads one as an instance
    assert sl.unit_stem("view:7") != sl.unit_stem("view:8")


def test_the_service_is_a_oneshot_that_is_given_time_to_finish():
    text = sl.service_text("open-work", "Open Work Sheet", "/venv/bin/fridgesheet", "run open-work",
                           "/home/tony", "/home/tony/.fridgesheet")
    assert "Description=Fridge Sheet: Open Work Sheet" in text
    assert "Type=oneshot" in text
    assert "ExecStart=/venv/bin/fridgesheet run open-work" in text
    assert "WorkingDirectory=/home/tony" in text
    assert "Environment=FRIDGESHEET_HOME=/home/tony/.fridgesheet" in text
    # The refresh inside is 3 kids x 2 sites plus a possible login: 1-3 minutes. systemd's
    # default 90 s start timeout would SIGTERM it partway through every run.
    assert "TimeoutStartSec=900" in text
    assert "[Install]" not in text            # a oneshot pulled by a timer is never enabled itself
    assert "network-online" not in text       # that target does not exist in a user manager's graph


def test_the_timer_lists_its_days_and_catches_up():
    text = sl.timer_text("open-work", "Open Work Sheet", "14:00", ["Mon", "Tue", "Wed", "Thu", "Fri"],
                         "America/New_York")
    assert "OnCalendar=Mon,Tue,Wed,Thu,Fri 14:00 America/New_York" in text
    assert "Mon.." not in text                # a list, not a range: correct for any set of days
    assert "Persistent=true" in text
    assert "Unit=fridgesheet-open-work.service" in text
    assert "WantedBy=timers.target" in text
    assert "Description=Fridge Sheet: Open Work Sheet (Mon, Tue, Wed, Thu, Fri at 14:00)" in text


def test_a_timer_with_no_time_zone_configured_still_writes_a_valid_line():
    text = sl.timer_text("view:7", "Weekly summary", "16:00", ["Fri"], "")
    assert "OnCalendar=Fri 16:00\n" in text


def test_bad_days_or_times_never_become_a_unit():
    with pytest.raises(SchedulingError, match="no days"):
        sl.timer_text("open-work", "t", "14:00", [], "America/New_York")
    with pytest.raises(SchedulingError, match="HH:MM"):
        sl.timer_text("open-work", "t", "2pm", ["Mon"], "America/New_York")


def test_the_hand_written_timer_is_named_but_never_generated():
    """Tony's own fridgesheet-print-sheet.timer runs the old print-sheet command. The app reports it
    and refuses to write over it; the unit it writes has a different name."""
    assert sl.LEGACY_TIMERS["open-work"] == "fridgesheet-print-sheet.timer"
    assert sl.timer_unit("open-work") not in sl.LEGACY_TIMERS.values()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_host_scheduling_linux.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'unit_stem'`.

- [ ] **Step 3: Implement**

Replace the top of `fridgesheet/host/scheduling_linux.py` (keep `describe` for now; Task 4
rewrites it):

```python
"""Scheduled reports on Linux: a systemd user timer per report, written by the app.

The app writes `fridgesheet-<key>.service` and `fridgesheet-<key>.timer` under
`~/.config/systemd/user` and enables the timer. It never writes, enables, disables or
deletes a unit it did not author: the hand-written `fridgesheet-print-sheet.timer` in
`LEGACY_TIMERS` is reported by `describe` and left alone by everything else (spec section
10, "existing ones untouched").
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import ScheduleInfo, SchedulingError, check_schedule, safe_key

#: Units this app did not write. Reported read-only; never installed over, never removed.
LEGACY_TIMERS = {"open-work": "fridgesheet-print-sheet.timer"}

#: A refresh is 3 kids x 2 sites plus a possible login: one to three minutes. systemd's
#: default start timeout is 90 s, which would SIGTERM the run partway through every time.
TIMEOUT_START_SEC = 900


def unit_stem(key: str) -> str:
    return f"fridgesheet-{safe_key(key)}"


def service_unit(key: str) -> str:
    return f"{unit_stem(key)}.service"


def timer_unit(key: str) -> str:
    return f"{unit_stem(key)}.timer"


def _unit_dir(d: Path | None = None) -> Path:
    """Private, so `install`/`remove` can take `unit_dir=` without shadowing it -- the same
    keyword `service_linux.install` already takes."""
    return d or Path.home() / ".config" / "systemd" / "user"


def service_text(key: str, title: str, exe: str, args: str, workdir: str, home: str) -> str:
    """The oneshot that runs the report.

    No `[Install]` section: the timer pulls this unit by name, so enabling it separately
    would be one more thing to leave behind. No `After=network-online.target` either -- that
    target is not in a user manager's unit graph, so it would document an ordering rather
    than create one.

    `FRIDGESHEET_HOME` is written explicitly so the unit keeps running against the home
    the app was configured with, whatever the environment of the session that fires it.
    """
    return (
        f"[Unit]\nDescription=Fridge Sheet: {title}\n\n"
        f"[Service]\nType=oneshot\n"
        f"Environment=FRIDGESHEET_HOME={home}\n"
        f"ExecStart={exe} {args}\n"
        f"WorkingDirectory={workdir}\n"
        f"TimeoutStartSec={TIMEOUT_START_SEC}\n"
    )


def timer_text(key: str, title: str, time: str, days: list[str], timezone: str) -> str:
    """The timer that fires it.

    `OnCalendar` lists the days rather than writing a range: a list is right for any set a
    parent can tick, and a range would need contiguity logic that is one more thing to get
    wrong. The time zone is the app's configured one, so a laptop that travels still prints
    at the hour the household expects. `Persistent=true` fires a run missed while the
    machine was asleep -- the runner's own window guard then decides whether to print.
    """
    check_schedule(time, days)
    when = f"{','.join(days)} {time}" + (f" {timezone}" if timezone else "")
    return (
        f"[Unit]\nDescription=Fridge Sheet: {title} ({', '.join(days)} at {time})\n\n"
        f"[Timer]\nUnit={service_unit(key)}\nOnCalendar={when}\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )
```

Delete the old `_unit` helper and the `_MSG` constant; `describe` temporarily breaks, which
Step 4 confirms and Task 4 repairs. To keep the suite green between tasks, leave `describe`
working by giving it a local name for now:

```python
def describe(key: str, run=subprocess.run):
    unit = LEGACY_TIMERS.get(key) or timer_unit(key)
    try:
        p = run(["systemctl", "--user", "show", unit, "-p", "NextElapseUSecRealtime", "--value"],
                capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ScheduleInfo("systemd", False, None, None)
    nxt = (p.stdout or "").strip()
    return ScheduleInfo("systemd", bool(nxt), nxt or None, None)
```

`install` and `remove` keep raising `NotSupported` until Task 3. Keep the import of
`NotSupported` while they do.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_host_scheduling_linux.py tests/test_host_scheduling.py -q`
Expected: PASS. The existing `test_linux_is_read_only_and_reads_systemd` still passes
because `install`/`remove` still raise.

Whole suite: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/scheduling_linux.py tests/test_host_scheduling_linux.py
git commit -m "host.scheduling_linux: the text of a report's timer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: Installing and removing the units

**Files:**
- Modify: `fridgesheet/host/scheduling_linux.py`
- Modify: `tests/test_host_scheduling.py:99-103` (the read-only test is no longer true)
- Test: `tests/test_host_scheduling_linux.py`

**Interfaces:**
- Consumes: everything Task 2 produced.
- Produces:
  - `scheduling_linux.install(key, time, days, exe, args, workdir, run=subprocess.run, *, title=None, home="", timezone="", unit_dir=None) -> None`
  - `scheduling_linux.remove(key, run=subprocess.run, *, unit_dir=None) -> None`
  - `scheduling_linux._is_enabled(unit, run) -> bool` (used again by Task 4)

  The two leading positional groups match `scheduling_windows.install`'s signature exactly,
  because `scheduling.install` is one name for both.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_host_scheduling_linux.py`:

```python
def _recorder(results=None):
    """A fake `run` that records argv and answers from a table keyed by the last two words."""
    calls = []
    results = results or {}
    def run(argv, **kw):
        calls.append(argv)
        rc, out = results.get(tuple(argv[-2:]), (0, ""))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")
    return calls, run


def test_install_writes_both_units_and_enables_only_the_timer(tmp_path):
    calls, run = _recorder({("is-enabled", "fridgesheet-print-sheet.timer"): (1, "disabled\n")})
    sl.install("open-work", "14:00", ["Mon", "Fri"], "/venv/bin/fridgesheet", "run open-work", "/home/tony",
               run=run, title="Open Work Sheet", home="/home/tony/.fridgesheet",
               timezone="America/New_York", unit_dir=tmp_path)

    service = (tmp_path / "fridgesheet-open-work.service").read_text()
    timer = (tmp_path / "fridgesheet-open-work.timer").read_text()
    assert "ExecStart=/venv/bin/fridgesheet run open-work" in service
    assert "OnCalendar=Mon,Fri 14:00 America/New_York" in timer

    assert calls == [
        ["systemctl", "--user", "is-enabled", "fridgesheet-print-sheet.timer"],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "fridgesheet-open-work.timer"],
    ]


def test_install_refuses_while_the_hand_written_timer_is_enabled(tmp_path):
    """Installing alongside it would print the sheet twice every afternoon. The message names
    the one command that clears the way."""
    calls, run = _recorder({("is-enabled", "fridgesheet-print-sheet.timer"): (0, "enabled\n")})
    with pytest.raises(SchedulingError, match="systemctl --user disable --now fridgesheet-print-sheet.timer"):
        sl.install("open-work", "14:00", ["Mon"], "x", "run open-work", ".", run=run, unit_dir=tmp_path)
    assert not list(tmp_path.iterdir())          # nothing written before the refusal
    assert calls == [["systemctl", "--user", "is-enabled", "fridgesheet-print-sheet.timer"]]


def test_a_report_with_no_legacy_unit_is_not_asked_about(tmp_path):
    calls, run = _recorder()
    sl.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=run, title="Weekly summary",
               home="/h", timezone="", unit_dir=tmp_path)
    assert (tmp_path / "fridgesheet-view-7.timer").is_file() and (tmp_path / "fridgesheet-view-7.service").is_file()
    assert calls[0] == ["systemctl", "--user", "daemon-reload"]


def test_install_with_bad_days_writes_nothing_and_runs_nothing(tmp_path):
    def run(argv, **kw):
        raise AssertionError("systemctl must not run")
    with pytest.raises(SchedulingError):
        sl.install("view:7", "16:00", ["Funday"], "x", "run view:7", ".", run=run, unit_dir=tmp_path)
    assert not list(tmp_path.iterdir())


def test_install_reports_what_systemctl_refused(tmp_path):
    def failing(argv, **kw):
        rc = 1 if argv[2] == "enable" else 0
        return subprocess.CompletedProcess(argv, rc, stdout="", stderr="Failed to connect to bus\n")
    with pytest.raises(SchedulingError, match="Failed to connect to bus"):
        sl.install("view:7", "16:00", ["Fri"], "x", "run view:7", ".", run=failing, unit_dir=tmp_path)


def test_remove_disables_deletes_both_units_and_reloads(tmp_path):
    (tmp_path / "fridgesheet-view-7.timer").write_text("x")
    (tmp_path / "fridgesheet-view-7.service").write_text("x")
    calls, run = _recorder()
    sl.remove("view:7", run=run, unit_dir=tmp_path)
    assert not (tmp_path / "fridgesheet-view-7.timer").exists()
    assert not (tmp_path / "fridgesheet-view-7.service").exists()
    assert calls == [
        ["systemctl", "--user", "disable", "--now", "fridgesheet-view-7.timer"],
        ["systemctl", "--user", "daemon-reload"],
    ]


def test_remove_is_quiet_about_a_unit_that_is_not_there(tmp_path):
    _, run = _recorder()
    def absent(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="",
                                           stderr="Failed to disable unit: Unit file fridgesheet-view-9.timer does not exist.\n")
    sl.remove("view:9", run=absent, unit_dir=tmp_path)          # no exception


def test_remove_raises_on_anything_else_systemctl_refuses(tmp_path):
    def busted(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus: No medium found\n")
    with pytest.raises(SchedulingError, match="No medium found"):
        sl.remove("view:9", run=busted, unit_dir=tmp_path)


def test_remove_never_touches_a_hand_written_unit(tmp_path):
    """`remove("open-work")` deletes the app's own units and leaves Tony's alone."""
    (tmp_path / "fridgesheet-print-sheet.timer").write_text("his")
    (tmp_path / "fridgesheet-print-sheet.service").write_text("his")
    calls, run = _recorder()
    sl.remove("open-work", run=run, unit_dir=tmp_path)
    assert (tmp_path / "fridgesheet-print-sheet.timer").read_text() == "his"
    assert all("print-sheet" not in " ".join(c) for c in calls)
```

And change `tests/test_host_scheduling.py:99-103` — the Linux adapter is no longer read-only:

```python
def test_linux_install_and_remove_are_no_longer_refused(tmp_path):
    """The read-only era is over: scheduling_linux writes units (tests/test_host_scheduling_linux.py
    covers what it writes). What stays refused is anything to do with a hand-written unit."""
    def run(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")      # is-enabled: not enabled
    scheduling_linux.install("view:3", "14:00", ["Mon"], "x", "run view:3", ".", run=run, unit_dir=tmp_path)
    assert (tmp_path / "fridgesheet-view-3.timer").is_file()
```

Leave the `NotSupported` import in that file only if something still uses it; if nothing
does, remove it from the import line.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_host_scheduling_linux.py -q`
Expected: FAIL — `NotSupported: scheduling on Linux is managed by systemd`.

- [ ] **Step 3: Implement**

In `fridgesheet/host/scheduling_linux.py`:

```python
#: What systemctl says when the unit is simply not there. Deliberately narrow, as
#: `service_linux`'s copy is: a user manager that is not running answers "Failed to connect
#: to bus: No such file or directory", and treating that as "already gone" would leave a
#: timer enabled while telling the parent it was removed.
_NO_SUCH_UNIT = ("does not exist", "not loaded")


def _systemctl(args: list[str], run) -> subprocess.CompletedProcess:
    return run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=60)


def _is_enabled(unit: str, run) -> bool:
    try:
        return _systemctl(["is-enabled", unit], run).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run,
            *, title: str | None = None, home: str = "", timezone: str = "", unit_dir: Path | None = None) -> None:
    """Write the pair and enable the timer.

    Validation happens before anything is written, so a bad day name leaves no half-installed
    schedule. A hand-written timer for this report stops the install outright: two timers for
    one report means the sheet prints twice.
    """
    check_schedule(time, days)
    legacy = LEGACY_TIMERS.get(key)
    if legacy and _is_enabled(legacy, run):
        raise SchedulingError(
            f"{legacy} already schedules this report and this app did not write it. "
            f"Turn it off first with: systemctl --user disable --now {legacy}")
    d = _unit_dir(unit_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / service_unit(key)).write_text(service_text(key, title or key, exe, args, workdir, home), encoding="utf-8")
    (d / timer_unit(key)).write_text(timer_text(key, title or key, time, days, timezone), encoding="utf-8")
    for cmd in (["daemon-reload"], ["enable", "--now", timer_unit(key)]):
        p = _systemctl(cmd, run)
        if p.returncode != 0:
            raise SchedulingError(f"systemctl --user {' '.join(cmd)} failed: "
                                  f"{(p.stderr or p.stdout or '').strip()[:300]}")


def remove(key: str, run=subprocess.run, *, unit_dir: Path | None = None) -> None:
    """Disable and delete the app's own pair. A unit that is not there is not an error; a
    hand-written unit is not this function's business and is never named."""
    p = _systemctl(["disable", "--now", timer_unit(key)], run)
    if p.returncode != 0:
        text = f"{p.stderr or ''}\n{p.stdout or ''}".lower()
        if not any(s in text for s in _NO_SUCH_UNIT):
            raise SchedulingError(f"systemctl --user disable --now {timer_unit(key)} failed: "
                                  f"{(p.stderr or p.stdout or '').strip()[:300]}")
    d = _unit_dir(unit_dir)
    (d / timer_unit(key)).unlink(missing_ok=True)
    (d / service_unit(key)).unlink(missing_ok=True)
    _systemctl(["daemon-reload"], run)
```

Remove the now-unused `NotSupported` import.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_host_scheduling_linux.py tests/test_host_scheduling.py -q`
Expected: PASS.

Whole suite. `tests/test_web_settings_page.py` has a `NoScheduling` fake that raises
`NotSupported`; it is a fake and keeps working.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/scheduling_linux.py tests/test_host_scheduling_linux.py tests/test_host_scheduling.py
git commit -m "host.scheduling_linux: install and remove a report's timer

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: Reporting on a schedule, including one the app did not write

**Files:**
- Modify: `fridgesheet/host/scheduling_linux.py` (`describe`)
- Test: `tests/test_host_scheduling_linux.py`

**Interfaces:**
- Consumes: Task 2's names, Task 1's `ScheduleInfo.manageable`.
- Produces: `scheduling_linux.describe(key, run=subprocess.run) -> ScheduleInfo`.

- [ ] **Step 1: Write the failing tests**

```python
def _systemctl_fake(answers):
    """answers maps a (verb, unit) pair to (returncode, stdout)."""
    calls = []
    def run(argv, **kw):
        calls.append(argv)
        rc, out = answers.get((argv[2], argv[-1] if argv[2] == "is-enabled" else argv[3]), (1, ""))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")
    return calls, run


def test_describe_reports_the_apps_own_timer(tmp_path):
    calls, run = _systemctl_fake({
        ("is-enabled", "fridgesheet-view-7.timer"): (0, "enabled\n"),
        ("show", "fridgesheet-view-7.timer"): (0, "Fri 2026-09-18 16:00:00 EDT\n"),
    })
    info = sl.describe("view:7", run=run)
    assert info == ScheduleInfo("systemd", True, "Fri 2026-09-18 16:00:00 EDT", None, True)


def test_describe_falls_back_to_the_hand_written_timer_and_marks_it_unmanageable():
    """Tony's fridgesheet-print-sheet.timer is what actually prints his sheet. Reporting "not
    scheduled" because the app did not write it would be a lie his doctor output would repeat."""
    _, run = _systemctl_fake({
        ("is-enabled", "fridgesheet-open-work.timer"): (1, ""),
        ("is-enabled", "fridgesheet-print-sheet.timer"): (0, "enabled\n"),
        ("show", "fridgesheet-print-sheet.timer"): (0, "Wed 2026-09-16 14:00:00 EDT\n"),
    })
    info = sl.describe("open-work", run=run)
    assert info.installed is True and info.manageable is False
    assert info.managed_by == "systemd (hand-written)"
    assert info.next_run == "Wed 2026-09-16 14:00:00 EDT"


def test_the_apps_own_timer_wins_over_a_legacy_one():
    _, run = _systemctl_fake({
        ("is-enabled", "fridgesheet-open-work.timer"): (0, "enabled\n"),
        ("show", "fridgesheet-open-work.timer"): (0, "Wed 2026-09-16 14:00:00 EDT\n"),
        ("is-enabled", "fridgesheet-print-sheet.timer"): (0, "enabled\n"),
    })
    assert sl.describe("open-work", run=run).manageable is True


def test_describe_says_not_scheduled_when_nothing_is_installed():
    _, run = _systemctl_fake({})
    assert sl.describe("open-work", run=run) == ScheduleInfo("systemd", False, None, None, True)


def test_describe_survives_a_machine_with_no_systemctl():
    def missing(argv, **kw):
        raise FileNotFoundError("systemctl")
    assert sl.describe("view:7", run=missing) == ScheduleInfo("systemd", False, None, None, True)
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — the current `describe` makes one `show` call and never asks `is-enabled`.

- [ ] **Step 3: Implement**

```python
def _next_elapse(unit: str, run) -> str | None:
    try:
        p = _systemctl(["show", unit, "-p", "NextElapseUSecRealtime", "--value"], run)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return (p.stdout or "").strip() or None


def describe(key: str, run=subprocess.run) -> ScheduleInfo:
    """What is scheduled for this report, whoever wrote it.

    The app's own timer is asked about first. A hand-written one (`LEGACY_TIMERS`) is the
    fallback and comes back with `manageable=False`, so a page shows it without offering a
    Remove button for a unit this app must not delete.

    `is-enabled` decides "installed", not the presence of a next elapse: a timer can be
    installed and enabled while systemd has no next time for it (a calendar that has passed
    for the day), and reporting that as "not scheduled" is how a parent ends up installing
    a second one.
    """
    for unit, managed_by, manageable in ((timer_unit(key), "systemd", True),
                                         (LEGACY_TIMERS.get(key), "systemd (hand-written)", False)):
        if unit and _is_enabled(unit, run):
            return ScheduleInfo(managed_by, True, _next_elapse(unit, run), None, manageable)
    return ScheduleInfo("systemd", False, None, None, True)
```

- [ ] **Step 4: Run the tests**

`tests/test_host_scheduling.py::test_linux_describe*` asserted the old single-call shape;
update it to the new one or delete it as superseded by
`tests/test_host_scheduling_linux.py` — say which in the commit message.

Whole suite, and check `doctor` specifically:
`env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_doctor.py -q`.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/host/scheduling_linux.py tests/test_host_scheduling_linux.py tests/test_host_scheduling.py
git commit -m "host.scheduling_linux: describe reports a hand-written timer too

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: A schedule's own printer, and a report that is never printed

**Files:**
- Modify: `fridgesheet/config.py:138-143` (`ReportConfig`), `:236-252` (parsing)
- Modify: `fridgesheet/runner.py:386-397`
- Test: `tests/test_config.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ReportConfig.printer: str` and `ReportConfig.prints: bool`; the runner's
  printer precedence `--printer` → `[reports.<key>].printer` → `[print].printer` → default.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`:

```python
def test_a_report_can_name_its_own_printer_and_ask_not_to_print(tmp_path):
    """Spec section 5: a schedule is "any report, days, time, printer or PDF-only". Those two
    live with the rest of the report's config so changing them never means reinstalling a unit."""
    doc = tomllib.loads(
        '[reports."view:7"]\n'
        'enabled = true\ntime = "16:00"\ndays = ["Fri"]\n'
        'printer = "Brother_MFC_J4335DW"\nprint = false\n')
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    rc = s.report_config("view:7", "16:00")
    assert rc.printer == "Brother_MFC_J4335DW" and rc.prints is False
    assert "printer" not in rc.options and "print" not in rc.options   # not build options


def test_a_report_prints_to_the_shared_printer_by_default(tmp_path):
    doc = tomllib.loads('[reports.open-work]\nenabled = true\ndays_ahead = 10\n')
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    rc = s.report_config("open-work", "14:00")
    assert rc.printer == "" and rc.prints is True and rc.options == {"days_ahead": 10}
```

In `tests/test_runner.py`. The `env` fixture yields `(s, calls, refresh, print_pdf, toast)`
and records prints in `calls["print"]` as `(pdf, printer, title)`; the three fakes are passed
to `_run` as keywords, exactly as `test_prints_toasts_and_records` at line 101 does.
`ReportConfig` is already imported there:

```python
def test_a_reports_own_printer_beats_the_shared_one(env):
    """Precedence: --printer, then the report's own, then [print].printer, then the default.
    The middle one is new: a schedule that prints somewhere else does not make every other
    report print there too."""
    s, calls, refresh, print_pdf, toast = env
    s.printer = "FromConfig"
    s.reports["open-work"] = ReportConfig(enabled=True, printer="Brother")
    _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][0][1] == "Brother"


def test_the_command_line_still_beats_the_reports_own_printer(env):
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, printer="Brother")
    _run(s, runner.RunOptions(printer="Office"), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][0][1] == "Office"


def test_a_pdf_only_report_builds_and_archives_but_never_prints(env):
    """PDF-only is a report's own setting, not `--dry-run`: a dry run also switches off the
    print-window and already-printed guards, and a scheduled PDF-only run wants both."""
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, prints=False)
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert calls["print"] == []
    day_dir = s.home / "sheets" / "2026-09-11"
    assert (day_dir / "sheet.pdf").is_file() and (day_dir / "rows.json").is_file()
    assert not (day_dir / "printed.txt").exists()      # nothing printed, so nothing recorded as printed
    log = (s.home / runner.LOG_NAME).read_text()
    assert " OK " in log and "PDF only" in log
    assert calls["toast"]                               # a scheduled run still says it happened


def test_a_pdf_only_run_still_obeys_the_print_window(env):
    """The guard that stops a catch-up the next morning from standing in for yesterday's run
    applies whether or not the result reaches a printer."""
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, time="14:00", prints=False)
    rc = _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=9),
              refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert rc == 0 and calls["print"] == []
    assert "outside print window" in (s.home / runner.LOG_NAME).read_text()
```

`tests/test_config.py` needs `import tomllib` if it does not already have it.

- [ ] **Step 2: Run to verify they fail**

Expected: FAIL — `TypeError: ReportConfig.__init__() got an unexpected keyword argument 'printer'`.

- [ ] **Step 3: Implement**

`fridgesheet/config.py`:

```python
@dataclass
class ReportConfig:
    enabled: bool = False
    time: str | None = None          # None -> not set in config.toml; report_config() resolves it
    days: list[str] = field(default_factory=lambda: list(WEEKDAYS))
    printer: str = ""                # blank -> [print].printer -> the system default
    prints: bool = True              # False -> build and archive, never send it to a printer
    options: dict = field(default_factory=dict)      # report-specific, e.g. days_ahead, overdue_days
```

`prints`, not `print`: the TOML key is `print`, but a field of that name shadows the builtin
wherever a `ReportConfig` is unpacked.

In the parsing loop:

```python
        known = {"enabled", "time", "days", "printer", "print"}
        ...
        s.reports[key] = ReportConfig(
            enabled=bool(sect.get("enabled", False)),
            time=time_val,
            days=[str(d) for d in sect.get("days", WEEKDAYS)],
            printer=str(sect.get("printer", "") or ""),
            prints=bool(sect.get("print", True)),
            options={k: v for k, v in sect.items() if k not in known},
        )
```

`fridgesheet/runner.py`, replacing lines 386-397:

```python
            if opts.dry_run:
                return finish("OK", f"dry-run built {built.pdf} {summary}", 0, toast_msg=None, pdf_path=built.pdf)
            if not rc_cfg.prints:
                # PDF only, by this report's own configuration. Nothing is written to
                # printed.txt: nothing was printed, and that file is the record of prints.
                return finish("OK", f"PDF only (not printed) {built.pdf} {summary}", 0,
                              toast_msg=summary, pdf_path=built.pdf)

            # --- print ------------------------------------------------------------------
            printer = opts.printer or rc_cfg.printer or settings.printer or None
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_config.py tests/test_runner.py -q`
Expected: PASS. Then the whole suite.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/config.py fridgesheet/runner.py tests/test_config.py tests/test_runner.py
git commit -m "runner: a report's own printer, and one that is only ever a PDF

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Every report a parent can schedule, and a CLI that knows about saved ones

Closes the two `cmd_schedule` items in #35.

**Files:**
- Modify: `fridgesheet/reports/__init__.py`
- Modify: `fridgesheet/cli.py:157-191` (`cmd_reports`, `cmd_schedule`), `:255` (help text)
- Test: `tests/test_reports.py`

**Interfaces:**
- Consumes: Task 5's `ReportConfig`.
- Produces: `reports.available(home: Path | None = None) -> list[Report]` — the code
  reports, then every saved view, each already a `Report` with `.key` and `.title`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_reports.py`, which needs these added to its imports:

```python
from fridgesheet import cli, host  # noqa: E402
from fridgesheet.web import db, views  # noqa: E402
from fridgesheet.web.stores import reports as store  # noqa: E402
```

```python
def test_available_lists_the_code_reports_and_every_saved_one(tmp_path):
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    got = reports.available(tmp_path)
    assert [r.key for r in got][0] == "open-work"
    assert "view:1" in [r.key for r in got]
    assert [r.title for r in got][-1] == "Weekly summary"


def test_available_without_a_home_is_the_code_reports():
    assert [r.key for r in reports.available()] == ["open-work"]


def test_available_never_fails_because_of_the_database(tmp_path):
    """Listing reports is what a page does before it can say anything at all. A database that
    is missing or unreadable costs the saved reports, not the page."""
    (tmp_path / "fridgesheet.db").write_bytes(b"this is not a database")
    assert [r.key for r in reports.available(tmp_path)] == ["open-work"]


def test_schedule_install_resolves_a_saved_report(tmp_path, monkeypatch):
    """`fridgesheet schedule install view:1` used to fail with "unknown report" because the
    command called the registry's `get` instead of `resolve` (#35).

    The idiom is `tests/test_print_sheet.py:185`: `cli.main` ends in `sys.exit`, so the exit
    code arrives as `SystemExit`, and `load_settings` is patched rather than the environment
    (`config.DEFAULT_HOME` is computed at import, so setting FRIDGESHEET_HOME here is too
    late to take effect).
    """
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    installed = {}

    class FakeScheduling:
        SchedulingError = host.SchedulingError
        @staticmethod
        def command_for(key):
            return ("/py", f"run {key}", "/wd")
        @staticmethod
        def install(key, time, days, exe, args, workdir, **kw):
            installed.update(key=key, time=time, days=list(days), title=kw.get("title"))
        @staticmethod
        def task_name(key):
            return f"Fridge Sheet - {key}"
        @staticmethod
        def describe(key):
            return host.ScheduleInfo("systemd", True, "Fri 16:00", None)

    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))
    monkeypatch.setattr("fridgesheet.host.scheduling", FakeScheduling)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install", "view:1"])
    assert e.value.code == 0
    assert installed["key"] == "view:1" and installed["title"] == "Weekly summary"
    assert installed["time"] == "16:00"          # the view report's own default_time
```

- [ ] **Step 2: Run to verify they fail**

Expected: FAIL — `AttributeError: module 'fridgesheet.reports' has no attribute 'available'`.

- [ ] **Step 3: Implement**

In `fridgesheet/reports/__init__.py`:

```python
def available(home: Path | None = None) -> list[Report]:
    """Every report a parent can run or schedule: the code reports first, then the saved views.

    A missing or unreadable database costs the saved reports and nothing else -- this is what
    a page calls before it can render anything, so it must not be the thing that fails.
    """
    out: list[Report] = list(REPORTS.values())
    if home is None:
        return out
    try:
        from ..web import db
        from ..web.stores import reports as store
        from .view import ViewReport
        conn = db.open_db(home)
        try:
            rows = list(store.all(conn))
        finally:
            conn.close()
    except Exception:       # noqa: BLE001  a listing is never worth a 500
        return out
    out.extend(ViewReport(r["id"], r["name"], r["definition"]) for r in rows)
    return out
```

and add `"available"` to `__all__`.

In `fridgesheet/cli.py`:

```python
def cmd_reports(args) -> int:
    from . import reports
    s = load_settings()
    for r in reports.available(s.home):
        rc = s.report_config(r.key, r.default_time)
        state = "enabled" if rc.enabled else "disabled"
        print(f"{r.key:<12} {r.title:<20} {state:<9} {rc.time} {','.join(rc.days)}"
              + ("" if rc.prints else "  (PDF only)"))
    return 0


def cmd_schedule(args) -> int:
    from . import reports
    from .host import NotSupported, scheduling
    s = load_settings()
    key = args.report
    try:
        if args.action == "install":
            r = reports.resolve(key, s.home)       # a saved view report is schedulable too (#35)
            rc = s.report_config(key, r.default_time)
            exe, a, wd = scheduling.command_for(key)
            scheduling.install(key, rc.time, rc.days, exe, a, wd, title=r.title,
                               home=str(s.home), timezone=s.timezone)
            print(f"Installed {scheduling.task_name(key)}: {','.join(rc.days)} at {rc.time}")
        elif args.action == "remove":
            scheduling.remove(key)
            print(f"Removed {scheduling.task_name(key)}")
        info = scheduling.describe(key)
        state = f"next run {info.next_run}" if info.installed else "not scheduled"
        print(f"{key}: {state} (managed by {info.managed_by}"
              + (f", last result {info.last_result}" if info.last_result else "") + ")")
        return 0
    except NotSupported as e:
        print(str(e), file=sys.stderr)
        return 2
    except (reports.ReportError, scheduling.SchedulingError) as e:
        print(str(e), file=sys.stderr)
        return 1
```

Both `scheduling.install` implementations already take `title`, `home` and `timezone` as of
Tasks 1 and 3, so this one call serves both platforms.

The help text at `cli.py:255`:

```python
    sc2 = sub.add_parser("schedule", help="install, remove or show a report's scheduled run "
                                          "(systemd user timers on Linux, Task Scheduler on Windows)")
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_reports.py tests/test_host_scheduling.py -q`, then the whole suite.

Also run the command for real, read-only, against a scratch home:

```bash
env -u PYTHONPATH FRIDGESHEET_HOME=/tmp/fridgesheet-plan-d2 \
  ~/fridgesheet/.venv/bin/python -m fridgesheet.cli reports
```

Expected: `open-work  Open Work Sheet  disabled  14:00 Mon,Tue,Wed,Thu,Fri`.
**Do not run `schedule install` outside a test.**

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/reports/__init__.py fridgesheet/cli.py tests/test_reports.py
git commit -m "reports: every report a parent can schedule, saved ones included

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: The Schedules page's work, without a web framework

**Files:**
- Create: `fridgesheet/web/schedules.py`
- Test: `tests/test_web_schedules.py` (create)

**Interfaces:**
- Consumes: `reports.available` (Task 6), `ReportConfig.printer/.prints` (Task 5),
  `host.check_schedule` (Task 1), `ScheduleInfo.manageable` (Task 1).
- Produces:
  - `schedules.Row(key, title, enabled, time, days, printer, prints, info, unsupported)`
  - `schedules.rows(home, *, scheduling=None) -> list[Row]`
  - `schedules.Outcome(ok, messages, errors)`
  - `schedules.save(key, *, enabled, time, days, printer, prints, home, log, scheduling=None) -> Outcome`

- [ ] **Step 1: Write the failing tests**

First add the fake to `tests/web_fixtures.py`, where the other shared test doubles live —
Task 8 uses it too, and a test module importing from another test module is how a rename in
one breaks the other:

```python
class FakeScheduling:
    """A scheduler that records every call and answers `describe` from a dict.

    Stands in for `host.scheduling` wherever a test would otherwise reach systemctl or
    schtasks. `info` maps a report key to the `ScheduleInfo` `describe` should return;
    `fail` makes `install` raise that message.
    """
    SchedulingError = host.SchedulingError

    def __init__(self, info=None, fail=None):
        self.installed, self.removed, self._info, self._fail = [], [], info or {}, fail

    def command_for(self, key):
        return ("/py", f"run {key}", "/wd")

    def install(self, key, time, days, exe, args, workdir, **kw):
        if self._fail:
            raise host.SchedulingError(self._fail)
        self.installed.append({"key": key, "time": time, "days": list(days), **kw})

    def remove(self, key, **kw):
        self.removed.append(key)

    def describe(self, key):
        return self._info.get(key, host.ScheduleInfo("systemd", False, None, None))

    def task_name(self, key):
        return f"Fridge Sheet - {key}"
```

with `from fridgesheet import host` added to that file's imports.

Then create `tests/test_web_schedules.py`:

```python
"""What the Schedules page does, with the scheduler injected. Nothing here runs systemctl."""
from __future__ import annotations

import tomllib
from pathlib import Path

from fridgesheet import host
from fridgesheet.web import db, schedules, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import FakeScheduling


def _home(tmp_path: Path) -> Path:
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    (tmp_path / "login-ok.txt").write_text("ok")
    return tmp_path


def test_rows_covers_every_report_with_what_the_scheduler_says(tmp_path):
    home = _home(tmp_path)
    (home / "config.toml").write_text('[reports.open-work]\nenabled = true\ntime = "14:00"\ndays = ["Mon", "Fri"]\n')
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd", True, "Fri 14:00", None)})
    got = {r.key: r for r in schedules.rows(home, scheduling=sched)}
    assert set(got) == {"open-work", "view:1"}
    assert got["open-work"].enabled and got["open-work"].days == ["Mon", "Fri"]
    assert got["open-work"].info.next_run == "Fri 14:00"
    assert got["view:1"].title == "Weekly summary"
    assert got["view:1"].time == "16:00"          # the view report's own default_time
    assert got["view:1"].enabled is False and got["view:1"].prints is True


def test_a_host_with_no_scheduler_still_renders_every_row(tmp_path):
    class NoScheduling(FakeScheduling):
        def describe(self, key):
            raise host.NotSupported("this host does not schedule anything")

    got = schedules.rows(_home(tmp_path), scheduling=NoScheduling())
    assert [r.unsupported for r in got] == ["this host does not schedule anything"] * 2
    assert all(r.info is None for r in got)


def test_save_writes_the_config_and_installs(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling()
    out = schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="Brother",
                         prints=False, home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and not out.errors
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"] == {"enabled": True, "time": "16:30", "days": ["Fri"],
                                        "printer": "Brother", "print": False}
    assert sched.installed[0]["key"] == "view:1"
    assert sched.installed[0]["title"] == "Weekly summary"     # the unit's Description, not its name
    assert sched.installed[0]["days"] == ["Fri"]


def test_turning_a_schedule_off_removes_the_unit_and_keeps_the_settings(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling()
    schedules.save("view:1", enabled=True, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None, scheduling=sched)
    schedules.save("view:1", enabled=False, time="16:30", days=["Fri"], printer="Brother", prints=True,
                   home=home, log=lambda s: None, scheduling=sched)
    assert sched.removed == ["view:1"]
    doc = tomllib.loads((home / "config.toml").read_text())
    assert doc["reports"]["view:1"]["enabled"] is False
    assert doc["reports"]["view:1"]["time"] == "16:30"     # kept, so turning it back on remembers


def test_a_bad_time_or_no_days_is_an_error_and_changes_nothing(tmp_path):
    home = _home(tmp_path)
    sched = FakeScheduling()
    for kw, match in ((dict(time="2pm", days=["Fri"]), "HH:MM"), (dict(time="16:00", days=[]), "no days")):
        out = schedules.save("view:1", enabled=True, printer="", prints=True, home=home,
                             log=lambda s: None, scheduling=sched, **kw)
        assert not out.ok and any(match in e for e in out.errors)
    assert not sched.installed and not (home / "config.toml").exists()


def test_an_unknown_report_is_refused(tmp_path):
    out = schedules.save("view:99", enabled=True, time="16:00", days=["Fri"], printer="", prints=True,
                         home=_home(tmp_path), log=lambda s: None, scheduling=FakeScheduling())
    assert not out.ok and any("view:99" in e for e in out.errors)


def test_a_scheduler_that_refuses_keeps_the_saved_settings(tmp_path):
    """The config is written before the scheduler is touched, so a systemctl that will not talk
    to the bus costs the install, never the parent's typing."""
    home = _home(tmp_path)
    sched = FakeScheduling(fail="Failed to connect to bus: No medium found")
    out = schedules.save("view:1", enabled=True, time="16:00", days=["Fri"], printer="", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert not out.ok
    assert any("No medium found" in e for e in out.errors)
    assert tomllib.loads((home / "config.toml").read_text())["reports"]["view:1"]["time"] == "16:00"


def test_a_schedule_waits_for_a_passing_test_login(tmp_path):
    """Same gate the Settings page has always had: a schedule that runs before the credentials
    work just fails every afternoon in the background."""
    home = _home(tmp_path)
    (home / "login-ok.txt").unlink()
    sched = FakeScheduling()
    out = schedules.save("open-work", enabled=True, time="14:00", days=["Mon"], printer="", prints=True,
                         home=home, log=lambda s: None, scheduling=sched)
    assert out.ok and not sched.installed
    assert any("Test login" in m for m in out.messages)
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `ModuleNotFoundError: No module named 'fridgesheet.web.schedules'`.

- [ ] **Step 3: Implement**

Create `fridgesheet/web/schedules.py`:

```python
"""The Schedules page's work: config.toml's `[reports.<key>]` and the OS timer or task,
changed together.

One editor for both halves of a schedule. When two pages could write the same keys, one of
them eventually shows a schedule the scheduler does not have.

Every side effect is injectable (`scheduling=`), so the tests never go near systemctl.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .. import config, host, reports as registry

CONFIG_NAME = "config.toml"
LOGIN_STAMP = "login-ok.txt"


@dataclass(frozen=True)
class Row:
    """One report's line on the page: what config.toml says, and what the host says."""
    key: str
    title: str
    enabled: bool
    time: str
    days: list[str]
    printer: str
    prints: bool
    info: host.ScheduleInfo | None = None   # None when this host does not schedule anything
    unsupported: str = ""                   # host.NotSupported's message, shown in place of the state


@dataclass
class Outcome:
    ok: bool
    messages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _settings_for(home: Path) -> config.Settings:
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / CONFIG_NAME), s)
    return s


def rows(home: Path, *, scheduling=None) -> list[Row]:
    if scheduling is None:
        from ..host import scheduling
    s = _settings_for(home)
    out: list[Row] = []
    for report in registry.available(home):
        rc = s.report_config(report.key, report.default_time)
        info, unsupported = None, ""
        try:
            info = scheduling.describe(report.key)
        except host.NotSupported as e:
            unsupported = str(e)
        except Exception as e:          # noqa: BLE001  a scheduler that will not answer is a line of text, not a 500
            unsupported = f"the scheduler could not be read: {str(e)[:200]}"
        out.append(Row(key=report.key, title=report.title, enabled=rc.enabled, time=rc.time or report.default_time,
                       days=list(rc.days), printer=rc.printer, prints=rc.prints, info=info, unsupported=unsupported))
    return out


def _table(doc: dict, key: str) -> dict:
    if not isinstance(doc.get(key), dict):
        doc[key] = {}
    return doc[key]


def save(key: str, *, enabled: bool, time: str, days: list[str], printer: str, prints: bool,
         home: Path, log: Callable[[str], None], scheduling=None) -> Outcome:
    """Write this report's schedule, then make the host agree with it.

    Validation first, so a bad time never reaches either the file or the scheduler. The file
    is written before the scheduler is called, so a scheduler that refuses costs the install
    and never the parent's typing -- the message says exactly that.
    """
    if scheduling is None:
        from ..host import scheduling
    try:
        report = registry.resolve(key, home)
    except registry.ReportError as e:
        return Outcome(False, errors=[str(e)])
    try:
        host.check_schedule(time, days)
    except host.SchedulingError as e:
        return Outcome(False, errors=[str(e)])

    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    rep = _table(_table(doc, "reports"), key)
    rep.update(enabled=bool(enabled), time=time, days=[str(d) for d in days],
               printer=printer.strip(), print=bool(prints))
    config.save_config_doc(path, doc)
    messages = [f"Saved {report.title}."]
    log(messages[-1])

    if not enabled:
        try:
            scheduling.remove(key)
        except host.NotSupported as e:
            return Outcome(True, messages + [str(e)])
        except host.SchedulingError as e:
            return Outcome(False, messages, [f"Saved, but the schedule could not be removed: {e}"])
        messages.append(f"{report.title} is not scheduled.")
        log(messages[-1])
        return Outcome(True, messages)

    if not (home / LOGIN_STAMP).exists():
        messages.append("Saved, but nothing is installed yet: run Test login on the Settings page first, "
                        "then save this schedule again.")
        log(messages[-1])
        return Outcome(True, messages)

    s = _settings_for(home)
    exe, args, workdir = scheduling.command_for(key)
    try:
        scheduling.install(key, time, days, exe, args, workdir, title=report.title,
                           home=str(home), timezone=s.timezone)
    except host.NotSupported as e:
        return Outcome(True, messages + [str(e)])
    except host.SchedulingError as e:
        return Outcome(False, messages, [f"Saved, but the schedule could not be installed: {e}"])
    messages.append(f"Scheduled: {', '.join(days)} at {time}" + ("" if prints else ", PDF only") + ".")
    log(messages[-1])
    return Outcome(True, messages)
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_web_schedules.py -q`
Expected: PASS. Then the whole suite.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/schedules.py tests/test_web_schedules.py tests/web_fixtures.py
git commit -m "web.schedules: one editor for a schedule's two halves

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: The Schedules page

**Files:**
- Create: `fridgesheet/web/routes/schedules.py`
- Create: `fridgesheet/web/templates/schedules.html`
- Modify: `fridgesheet/web/app.py:278-280`
- Modify: `fridgesheet/web/templates/base.html:21` (the nav)
- Modify: `fridgesheet/web/actions.py` (add `printer_names`)
- Modify: `fridgesheet/web/routes/settings.py:14-21` (use it)
- Test: `tests/test_web_schedules_page.py` (create)

**Interfaces:**
- Consumes: `schedules.rows`, `schedules.save` (Task 7).
- Produces: `GET /schedules`, `POST /schedules`;
  `actions.printer_names(extra: dict) -> list[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_web_schedules_page.py`:

```python
"""The Schedules page. The scheduler is a fake on `state.extra`, as the Settings page's is."""
from __future__ import annotations

import tomllib

from fastapi.testclient import TestClient

from fridgesheet import config, host
from fridgesheet.web import app as webapp, db, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import FakeScheduling, seed


def _client(tmp_path, sched=None):
    seed(tmp_path).close()
    conn = db.open_db(tmp_path)
    store.create(conn, "Weekly summary", views.defaults().to_json(), now="2026-09-16T08:00:00-04:00")
    conn.close()
    (tmp_path / "login-ok.txt").write_text("ok")
    s = config.Settings(home=tmp_path)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.extra["scheduling"] = sched or FakeScheduling()
    application.state.fridgesheet.extra["printers"] = ["Brother", "Canon"]
    return TestClient(application), application


def test_the_page_lists_every_report_with_its_state(tmp_path):
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd", True, "Wed 14:00", None)})
    c, _ = _client(tmp_path, sched)
    body = c.get("/schedules").text
    assert "Open Work Sheet" in body and "Weekly summary" in body
    assert "Wed 14:00" in body
    assert 'value="open-work"' in body and 'value="view:1"' in body
    assert '<option value="Brother"' in body                  # the printer list is offered
    assert 'name="days" value="Mon"' in body


def test_saving_a_schedule_installs_it_and_says_so(tmp_path):
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Mon", "Fri"], "printer": "Brother", "prints": "on"})
    assert r.status_code == 200
    assert "Scheduled: Mon, Fri at 16:30" in r.text
    assert sched.installed[0]["key"] == "view:1"
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["view:1"]["days"] == ["Mon", "Fri"]


def test_a_pdf_only_schedule_says_so_on_the_page(tmp_path):
    c, _ = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "16:30",
                                   "days": ["Fri"], "printer": "", "prints": ""})
    assert "PDF only" in r.text


def test_a_bad_time_comes_back_as_an_error_not_a_crash(tmp_path):
    sched = FakeScheduling()
    c, _ = _client(tmp_path, sched)
    r = c.post("/schedules", data={"key": "view:1", "enabled": "on", "time": "half four",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "HH:MM" in r.text
    assert not sched.installed


def test_a_hand_written_timer_is_shown_but_not_offered_for_removal(tmp_path):
    """The app reports Tony's own fridgesheet-print-sheet.timer and gives no button that would
    delete a unit it did not write."""
    sched = FakeScheduling({"open-work": host.ScheduleInfo("systemd (hand-written)", True, "Wed 14:00", None, False)})
    c, _ = _client(tmp_path, sched)
    body = c.get("/schedules").text
    assert "hand-written" in body
    assert "written outside this app" in body                 # the explanation, in the row


def test_an_unknown_key_is_a_bad_request_not_a_500(tmp_path):
    c, _ = _client(tmp_path)
    r = c.post("/schedules", data={"key": "view:404", "enabled": "on", "time": "16:00",
                                   "days": ["Fri"], "printer": "", "prints": "on"})
    assert r.status_code == 200 and "view:404" in r.text


def test_the_nav_links_to_it(tmp_path):
    c, _ = _client(tmp_path)
    assert 'href="/schedules"' in c.get("/").text
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — 404 from `/schedules`.

- [ ] **Step 3: Implement**

First move the printer list into `actions.py` so both pages use one copy:

```python
def printer_names(extra: dict) -> list[str]:
    """The printers to offer. `extra["printers"]` is the tests' seam; a host that cannot list
    them offers none, which is a shorter menu and never a failed page."""
    if "printers" in extra:
        return extra["printers"]
    try:
        from ..host import printing
        return printing.list_printers()
    except Exception:  # noqa: BLE001  a printer list is a convenience, never a failure
        return []
```

and in `routes/settings.py` delete `_printers` and call `actions.printer_names(state.extra)`.

Create `fridgesheet/web/routes/schedules.py`:

```python
"""Schedules: one row per report, days and a time, a printer or PDF only."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from .. import actions, schedules
from ..app import Db, State, render

router = APIRouter()

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _page(request, conn, state, *, messages=(), errors=()):
    return render(request, conn, "schedules.html", current="schedules",
                  rows=schedules.rows(state.home, scheduling=state.extra.get("scheduling")),
                  days=DAYS, printers=actions.printer_names(state.extra),
                  messages=list(messages), errors=list(errors))


@router.get("/schedules")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _page(request, conn, state)


@router.post("/schedules")
async def save(request: Request, conn: sqlite3.Connection = Db, state=State):
    """One row's form. `days` is a checkbox group, so it is read from the raw form rather than
    declared as a parameter -- FastAPI would give back only the last one."""
    form = await request.form()
    lines: list[str] = []
    out = schedules.save(
        form.get("key", ""),
        enabled=bool(form.get("enabled")),
        time=form.get("time", ""),
        days=[d for d in form.getlist("days") if d],
        printer=form.get("printer", ""),
        prints=bool(form.get("prints")),
        home=state.home, log=lines.append, scheduling=state.extra.get("scheduling"))
    state.reload()
    return _page(request, conn, state, messages=out.messages, errors=out.errors)
```

Check `state.reload()` exists and is what the Settings route calls after a config write; use
the same call.

Create `fridgesheet/web/templates/schedules.html`:

```html
{% extends "base.html" %}
{% block title %}Schedules · Fridge Sheet{% endblock %}
{% block content %}
<h2>Schedules</h2>
<p class="muted">A scheduled report runs itself: it refreshes, builds, and prints (or just keeps the PDF).
   The time is also the earliest a catch-up run will print, so a run missed overnight does not print yesterday's sheet in the morning.</p>
{% for m in messages %}<p class="ok">{{ m }}</p>{% endfor %}
{% for e in errors %}<p class="warn">{{ e }}</p>{% endfor %}

{% for r in rows %}
<form method="post" action="/schedules" class="schedule">
  <input type="hidden" name="key" value="{{ r.key }}">
  <h3>{{ r.title }} <span class="muted">{{ r.key }}</span></h3>
  <p class="muted">
    {% if r.unsupported %}{{ r.unsupported }}
    {% elif r.info and r.info.installed %}
      {{ r.info.managed_by }}{% if r.info.next_run %} · next run {{ r.info.next_run }}{% endif %}
      {% if not r.info.manageable %}<br>This one was written outside this app, so it is shown here but never changed here.{% endif %}
    {% else %}not scheduled{% endif %}
  </p>
  <label><input type="checkbox" name="enabled" {{ "checked" if r.enabled }}
         {{ "disabled" if r.info and not r.info.manageable }}> Run this on a schedule</label>
  <label>Time <input type="time" name="time" value="{{ r.time }}" required></label>
  <fieldset><legend>Days</legend>
    {% for d in days %}
    <label><input type="checkbox" name="days" value="{{ d }}" {{ "checked" if d in r.days }}> {{ d }}</label>
    {% endfor %}
  </fieldset>
  <label>Printer
    <select name="printer">
      <option value="">(the printer on the Settings page)</option>
      {% for p in printers %}<option value="{{ p }}" {{ "selected" if p == r.printer }}>{{ p }}</option>{% endfor %}
    </select>
  </label>
  <label><input type="checkbox" name="prints" {{ "checked" if r.prints }}> Print it (off: keep the PDF only)</label>
  <button {{ "disabled" if r.info and not r.info.manageable }}>Save</button>
</form>
{% endfor %}
{% endblock %}
```

A plain `method="post"` form, not htmx: the whole page changes when a schedule changes, and
a full response is the honest way to show it.

`base.html`, after the Reports link:

```html
      <a href="/schedules" class="{{ 'current' if current == 'schedules' }}">Schedules</a>
```

`app.py`: add `schedules as schedule_routes` to the `from .routes import ...` line and
`schedule_routes.router` to the tuple.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_web_schedules_page.py -q`, then the whole suite. `tests/test_web_pages.py` may assert the
exact nav; update it if so.

Then look at the page for real:

```bash
env -u PYTHONPATH FRIDGESHEET_HOME=/tmp/fridgesheet-plan-d2 \
  ~/fridgesheet/.venv/bin/python -m fridgesheet.cli web --no-browser --port 8451 &
curl -s localhost:8451/schedules | head -60
kill %1
```

A scratch home, never `~/.fridgesheet`. The page will say "not scheduled" for every row
on this machine unless the legacy fallback finds Tony's timer — which is the interesting
case to eyeball, so check what it prints.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/schedules.py fridgesheet/web/templates/schedules.html \
        fridgesheet/web/templates/base.html fridgesheet/web/app.py \
        fridgesheet/web/actions.py fridgesheet/web/routes/settings.py \
        tests/test_web_schedules_page.py
git commit -m "web: the Schedules page

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: One editor, not two — the schedule leaves Settings

**Files:**
- Modify: `fridgesheet/web/actions.py:36-46` (`FormValues`), `:63-77` (`load_form`),
  `:97-119` (`validate`), `:139-210` (`save`)
- Modify: `fridgesheet/web/routes/settings.py:36-53`
- Modify: `fridgesheet/web/templates/settings.html`
- Test: `tests/test_web_actions.py`, `tests/test_web_settings_page.py`

**Interfaces:**
- Consumes: the Schedules page (Task 8).
- Produces: `actions.FormValues` without `scheduled` and `time`; `actions.SaveResult`
  without `schedule_installed` and `schedule_error`; `actions.save` no longer takes
  `scheduling=`.

- [ ] **Step 1: Write the failing test**

In `tests/test_web_settings_page.py`:

```python
def test_settings_no_longer_edits_the_schedule(tmp_path):
    """Two pages writing `[reports.open-work].enabled` is how a page ends up showing a
    schedule the scheduler does not have. Schedules owns it; Settings links to it."""
    c, _ = _client(tmp_path)
    body = c.get("/settings").text
    assert 'name="scheduled"' not in body and 'name="time"' not in body
    assert 'href="/schedules"' in body
    assert 'name="days_ahead"' in body and 'name="overdue_days"' in body     # still the report's options


def test_saving_settings_never_touches_the_scheduler(tmp_path):
    class Exploding:
        def install(self, *a, **k):
            raise AssertionError("Settings must not install a schedule")
        def remove(self, *a, **k):
            raise AssertionError("Settings must not remove a schedule")
    c, app = _client(tmp_path)
    app.state.fridgesheet.extra["scheduling"] = Exploding()
    r = c.post("/settings", data={**FORM, "password": "pw"})
    assert r.status_code == 200 and "Settings saved" in r.text


def test_a_schedule_set_on_the_schedules_page_survives_a_settings_save(tmp_path):
    """The regression this task exists to prevent."""
    c, _ = _client(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[account]\nusername = "parent@example.org"\n'
        '[reports.open-work]\nenabled = true\ntime = "15:00"\ndays = ["Mon"]\n')
    c.post("/settings", data={**FORM, "password": "pw"})
    doc = tomllib.loads((tmp_path / "config.toml").read_text())
    assert doc["reports"]["open-work"]["enabled"] is True
    assert doc["reports"]["open-work"]["time"] == "15:00"
    assert doc["reports"]["open-work"]["days"] == ["Mon"]
```

`FORM` at the top of that file still has `"time": "15:30"`; remove that key so the test
posts what the new form posts.

In `tests/test_web_actions.py`, delete the tests that assert `save` installs or removes a
schedule (they move to `tests/test_web_schedules.py`, which already covers the behaviour)
and drop `scheduling=` from `_save`'s call.

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL — `name="scheduled"` is still in the page.

- [ ] **Step 3: Implement**

`actions.FormValues`: delete `time` and `scheduled`.

`actions.load_form`: delete the `time=` and `scheduled=` lines. It still reads
`rc.options` for `days_ahead`/`overdue_days`, so keep the `rc = s.report_config(...)` line.

`actions.validate`: delete the `_validate_report_time` block (lines 105-108).

`actions.save`:
- drop the `scheduling=None` parameter and its import,
- change the `rep.update(...)` line to
  `rep.update(days_ahead=int(form.days_ahead), overdue_days=int(form.overdue_days))`,
- **delete the `days` defaulting lines** (159-160): days belong to the Schedules page now,
  and writing them here would put `["Mon","Tue","Wed","Thu","Fri"]` over a parent's choice
  every time Settings was saved. This is the whole point of the task.
- delete the whole `installed`/`schedule_error` block (187-207) and return
  `SaveResult(True, messages, None, None, restart_needed)`.

Delete `SaveResult.schedule_installed` and `.schedule_error`, and the
`SaveResult(True, messages, None, ...)` third argument at every return. Nothing outside
`actions.py` reads them: the only readers are the `tests/test_web_actions.py` assertions
this task deletes (lines 167-226), which is verified — `grep -rn
"schedule_installed\|schedule_error" fridgesheet/ tests/` before and after should go from
those lines to nothing. `restart_needed` stays.

`routes/settings.py`: drop `time` and `scheduled` from the `save` signature and from the
`FormValues(...)` construction, and drop `scheduling=state.extra.get("scheduling")` from the
`actions.save` call.

`templates/settings.html`: replace the schedule fieldset with

```html
<p><a href="/schedules">Schedules</a> — when each report runs, and where it prints.</p>
```

Keep `days_ahead` and `overdue_days` where they are; they are the open-work report's build
options and have nothing to do with a timer. Check the template for a heading like
"Scheduled printing" and rewrite it rather than leaving an empty section.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_web_settings_page.py tests/test_web_actions.py -q`, then the whole suite.

Then load both pages for real against the scratch home, as in Task 8, and confirm Settings
has no schedule controls and Schedules has them all.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/actions.py fridgesheet/web/routes/settings.py \
        fridgesheet/web/templates/settings.html tests/test_web_actions.py tests/test_web_settings_page.py
git commit -m "web.settings: a schedule has one editor, and it is not this page

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## After the last task

1. **Whole-branch review.** Every plan in this series has had cross-task defects that the
   per-task gates could not see: a key scoped wrongly, a lock never released, two stores
   contradicting each other. Dispatch a reviewer over the whole diff with the spec and this
   plan, and pay particular attention to:
   - anything that could write, enable, disable or delete `fridgesheet-print-sheet.*`,
   - `[reports.<key>]` written by more than one code path,
   - `ScheduleInfo.manageable` reaching a button that would act on an unmanageable unit,
   - the `describe` fallback and `doctor`'s probe still agreeing.
2. **One fix wave**, then a scoped re-review of the fixes.
3. **File the residuals** as a GitHub issue in the series (#31–#35 are the precedent), and
   put its number in the issue body's "Deferrals" line. One is already known:
   `doctor._scheduler` probes `REPORT_KEY` alone, so a view report whose config says
   `enabled = true` with nothing installed is a silence the doctor does not break. Widening
   it to every key `reports.available` returns is a small change and a deliberate
   non-goal of this plan, which is already nine tasks.
4. **Close #26 and #27**, and strike the two `cmd_schedule` items from #35.
5. **Push and watch CI to completion on both runners.** The Windows job is the only place
   this plan's `safe_key` and task-name work is actually exercised against Task Scheduler's
   own rules, and it only runs on push.

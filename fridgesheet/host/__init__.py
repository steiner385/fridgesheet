# fridgesheet/host/__init__.py
"""OS adapters. This package is the only place that may look at the platform.

Each adapter module (`printing`, `credentials`, `scheduling`, `notify`, `opener`, `service`)
picks a `_linux` or `_windows` implementation at import time. Every implementation takes its
`run=subprocess.run` as an argument so tests assert on command lines on any OS.

This module also holds the exceptions and shared names each adapter's Linux/Windows pair
needs, so a sibling module (e.g. `scheduling_windows`) can import them without a cycle
through `scheduling.py`. The adapter modules (`credentials.py`, `printing.py`,
`scheduling.py`) re-export the names that used to live in them, so existing imports keep
working.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass

IS_WINDOWS: bool = sys.platform == "win32"

#: subprocess creationflags that keep a console window from flashing under a windowed exe.
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: the OS credential store's service name, keyed by SERVICE/username/password.
SERVICE: str = os.environ.get("FRIDGESHEET_KEYRING_SERVICE", "fridgesheet")


class NotSupported(RuntimeError):
    """The host has no implementation of this action (e.g. scheduling on Linux)."""


class PrintError(RuntimeError):
    """The print could not be handed to the spooler. The PDF is left on disk."""


class SchedulingError(RuntimeError):
    """schtasks refused; its stderr is in the message."""


@dataclass(frozen=True)
class ScheduleInfo:
    managed_by: str                 # "task-scheduler" | "systemd" | "systemd (hand-written)"
    installed: bool
    next_run: str | None
    last_result: str | None
    manageable: bool = True         # False: found, but this app did not write it and will not change it


DAY_NAMES: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

#: The one HH:MM (24-hour) pattern every clock-time validator in this app matches against --
#: `config._validate_report_time`/`_validate_refresh_time`, `refresh_schedule._minutes` and
#: `check_schedule` below. Three separate copies of this regex used to exist, all accepting
#: exactly the same language (this one, and `config`'s own looser `\d{2}:\d{2}$` plus a
#: separate 0-23/0-59 range check) -- harmless while they agreed, but the next person to loosen
#: one copy would not be touching the other two. `host` is the shared ancestor both `config`
#: (which already imports `host`) and `refresh_schedule` (which imports `config`) can reach
#: without either importing the other, so this is where the one copy lives. Each caller keeps
#: its own exception type and message -- `ConfigError` and `SchedulingError` mean different
#: things to different callers, and merging those would be its own kind of parallel-implementation.
TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
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
    return _UNSAFE.sub("-", key).strip("-.") or "report"


def check_schedule(time: str, days: list[str]) -> None:
    """Raise `SchedulingError` unless this is a schedule both platforms can install."""
    bad = [d for d in days if d not in DAY_NAMES]
    if not days:
        raise SchedulingError("no days configured for the schedule")
    if bad:
        raise SchedulingError(f"unknown day name(s) {bad!r}; use {', '.join(DAY_NAMES)}")
    if not TIME_RE.match(str(time)):
        raise SchedulingError(f"time must be HH:MM (24-hour), got {time!r}")


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


def task_name(key: str) -> str:
    """The Windows task's display name. `safe_key`'s hyphens read badly in a title, so they
    become spaces here; this is a label, not a file name."""
    return f"Fridge Sheet - {safe_key(key).replace('-', ' ') if ':' in key else key}"


class ServiceError(RuntimeError):
    """systemctl or schtasks refused; its stderr is in the message."""


@dataclass(frozen=True)
class ServiceInfo:
    managed_by: str                 # "systemd" | "task-scheduler"
    installed: bool
    active: bool
    detail: str
    #: The account the unit or task runs as, "" when unknown. A per-user logon task only
    #: fires for its owner, and a per-user install lives in that owner's profile, so an
    #: update run by anyone else builds a second copy and leaves the running one alone.
    owner: str = ""
    #: The exe+args the unit or task runs, "" when unknown. Added so `service_windows.install`
    #: can tell an already-registered task that is genuinely the one it would have created
    #: (safe to just start) from one pointing somewhere else (a real problem -- graphy,
    #: 2026-09-23). Defaults to "" so `service_linux.py` and every existing construction site
    #: keep working untouched.
    command: str = ""

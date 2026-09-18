# lakota_grades/host/__init__.py
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
SERVICE: str = os.environ.get("LAKOTA_KEYRING_SERVICE", "lakota-grades")


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
    return _UNSAFE.sub("-", key).strip("-.") or "report"


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
    return f"Lakota Sheet - {safe_key(key).replace('-', ' ') if ':' in key else key}"


class ServiceError(RuntimeError):
    """systemctl or schtasks refused; its stderr is in the message."""


@dataclass(frozen=True)
class ServiceInfo:
    managed_by: str                 # "systemd" | "task-scheduler"
    installed: bool
    active: bool
    detail: str

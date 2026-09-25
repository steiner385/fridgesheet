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

import getpass
import os
import re
import subprocess
import sys
from dataclasses import dataclass

IS_WINDOWS: bool = sys.platform == "win32"

#: subprocess creationflags that keep a console window from flashing under a windowed exe.
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: The OS credential store's default service name; entries are keyed by service/username/password.
DEFAULT_SERVICE = "fridgesheet"


def keyring_service() -> str:
    """The credential store's service name, `FRIDGESHEET_KEYRING_SERVICE` or the default.

    Read when asked, not at import (#148): `config.load_settings` is what reads `.env` into
    the environment, and every import of this package happens before that -- so a
    `FRIDGESHEET_KEYRING_SERVICE=` line in `.env`, which env.example suggests, was read once at
    import as unset and never again. `SERVICE` below is the same value under the name the rest
    of the code base (and `credentials.SERVICE`) has always used."""
    return os.environ.get("FRIDGESHEET_KEYRING_SERVICE", DEFAULT_SERVICE)


def __getattr__(name: str):
    if name == "SERVICE":
        return keyring_service()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def current_user() -> str:
    """The account this process is running as, "" when it cannot be determined (no
    password-database entry, some container/service contexts) -- callers must treat "" as
    "unknown, so do not assume a match", never as a value that could equal anything.

    Shared here, not duplicated, because two copies of this already drifted apart once:
    `cli._current_user` (self-update's ownership check, cli.py) and an earlier attempt at
    `service_windows._current_user` (the `/Create`-denied fallback's account check) were the
    same three lines with an incorrect comment claiming a `cli -> host -> cli` import cycle
    justified keeping them apart. There is no such cycle -- `cli.py` already imports from
    `.host` at module level (`from .host import credentials as credstore`) -- so both import
    this instead, each under its own aliased name so existing tests that monkeypatch the
    call site (`cli._current_user`, `service_windows._current_user`) keep working.
    """
    try:
        return getpass.getuser()
    except Exception:       # noqa: BLE001  no password-database entry; not worth dying for
        return ""


class NotSupported(RuntimeError):
    """The host has no implementation of this action (e.g. scheduling on Linux)."""


class PrintError(RuntimeError):
    """The print could not be handed to the spooler. The PDF is left on disk."""


class SchedulingError(RuntimeError):
    """schtasks refused; its stderr is in the message."""


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


def systemd_quote(word: str) -> str:
    """One word of a systemd `ExecStart=` line. systemd splits on whitespace and honours double
    quotes with backslash escapes (not shell rules), so a venv path with a space was cut in two
    (#7). A word with nothing to protect is returned as it is."""
    if word and not any(c.isspace() or c in '"\\\'' for c in word):
        return word
    return '"' + word.replace("\\", "\\\\").replace('"', '\\"') + '"'


def check_schedule(time: str, days: list[str], *, require_days: bool = True) -> None:
    """Raise `SchedulingError` unless this is a schedule both platforms can install.

    `require_days=False` is for a schedule being turned *off* (#146): no days is then a fine
    thing to save, but the time and any day named are still checked, because they are written
    to config.toml and a bad time there would break every later read of the file."""
    bad = [d for d in days if d not in DAY_NAMES]
    if not days and require_days:
        raise SchedulingError("no days configured for the schedule")
    if bad:
        raise SchedulingError(f"unknown day name(s) {bad!r}; use {', '.join(DAY_NAMES)}")
    if not TIME_RE.match(str(time)):
        raise SchedulingError(f"time must be HH:MM (24-hour), got {time!r}")


def check_schedule_times(times: list[str], days: list[str], *, require_days: bool = True) -> None:
    """`check_schedule` for a schedule with several times a day.

    Every time is validated before any caller writes a file, so one bad time never leaves a
    half-installed schedule behind -- the same ordering `install` already relies on.
    """
    if not times:
        raise SchedulingError("no times configured for the schedule")
    for t in times:
        check_schedule(t, days, require_days=require_days)


#: The app's own data-refresh schedule. Deliberately *not* "refresh": earlier versions rendered
#: a key to a systemd unit name, and "refresh" would have become the household's hand-written
#: `fridgesheet-refresh.timer`. The key outlived the OS scheduler, so it keeps its spelling.
DATA_REFRESH_KEY = "data-refresh"

#: Keys a report may never claim. Compared stripped and case-folded, so a hand-edited
#: `[reports.Data-Refresh]` in config.toml can never be mistaken for this app's own refresh
#: schedule.
RESERVED_KEYS = frozenset({DATA_REFRESH_KEY})
_RESERVED_FOLDED = frozenset(k.strip().casefold() for k in RESERVED_KEYS)


def is_reserved(key: str) -> bool:
    return str(key).strip().casefold() in _RESERVED_FOLDED


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

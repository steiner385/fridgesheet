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

import functools
import getpass
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

log = logging.getLogger("fridgesheet.host")

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


#: The zone the app assumes when this computer's cannot be read: the district it was written
#: for. `config.default_timezone` applies it, and `local_timezone` warns once when it does.
FALLBACK_TIMEZONE = "America/New_York"

#: Windows zone keys (`TimeZoneKeyName` in the registry, the same words `time.tzname` shows
#: on an English Windows) to the IANA names `zoneinfo` and `tzdata` know. Windows keeps its
#: own vocabulary and Python's `zoneinfo` cannot read it, so a map is the only bridge without
#: a new dependency; this one covers the zones a household using this app plausibly has --
#: the Americas, and a few beyond for a laptop that came from elsewhere. Anything not here
#: is None, and the fallback says so in the log.
WINDOWS_ZONES: dict[str, str] = {
    "Eastern Standard Time": "America/New_York",
    "US Eastern Standard Time": "America/Indiana/Indianapolis",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "US Mountain Standard Time": "America/Phoenix",
    "Pacific Standard Time": "America/Los_Angeles",
    "Alaskan Standard Time": "America/Anchorage",
    "Aleutian Standard Time": "America/Adak",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Atlantic Standard Time": "America/Halifax",
    "Newfoundland Standard Time": "America/St_Johns",
    "Canada Central Standard Time": "America/Regina",
    "SA Western Standard Time": "America/Puerto_Rico",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Samoa Standard Time": "Pacific/Apia",
    "UTC": "UTC",
    "Coordinated Universal Time": "UTC",
    "GMT Standard Time": "Europe/London",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest",
    "India Standard Time": "Asia/Kolkata",
    "Tokyo Standard Time": "Asia/Tokyo",
    "AUS Eastern Standard Time": "Australia/Sydney",
}


def is_timezone(name: str) -> bool:
    """Whether `zoneinfo` knows `name`: the one judge of a zone name in this app -- config.toml's,
    the environment's, the Settings page's and detection's answers all pass through here, so
    no caller keeps a list of zones of its own."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):    # unknown, "" or something path-like
        return False
    return True


def _windows_zone_name() -> str | None:
    """The zone Windows is set to, by its own name. The registry's `TimeZoneKeyName` is the
    canonical key whatever the display language; `time.tzname` is the same words on an
    English Windows and the translated ones elsewhere, so it is only the fallback."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation") as k:
            return str(winreg.QueryValueEx(k, "TimeZoneKeyName")[0]) or None
    except Exception:       # noqa: BLE001  not Windows, or a registry that will not answer
        pass
    import time
    return time.tzname[0] if time.tzname and time.tzname[0] else None


def detect_timezone(*, environ: dict | None = None, is_windows: bool | None = None,
                    localtime: Path = Path("/etc/localtime"), timezone_file: Path = Path("/etc/timezone"),
                    windows_zone=None) -> str | None:
    """This computer's IANA zone name, or None when it cannot be read.

    `TZ` first on either platform, when it names a zone (`:America/Chicago` and
    `America/Chicago` alike; a POSIX rule such as `EST5EDT,M3.2.0` is not a name and falls
    through). Then, on Linux, the target of the `/etc/localtime` symlink -- what glibc itself
    follows -- and Debian's `/etc/timezone` for an image that copied the file instead of
    linking it. On Windows, the registry's zone key through `WINDOWS_ZONES`. Every answer is
    checked with `is_timezone` before it is believed. No `tzlocal`: this is the whole of what
    that package does that this app needs.
    """
    env = os.environ if environ is None else environ
    raw = (env.get("TZ") or "").strip().lstrip(":")
    if raw and is_timezone(raw):
        return raw
    if IS_WINDOWS if is_windows is None else is_windows:
        name = (windows_zone or _windows_zone_name)()
        zone = WINDOWS_ZONES.get(name or "")
        return zone if zone and is_timezone(zone) else None
    try:
        target = os.readlink(localtime).replace("\\", "/")
    except OSError:                     # not a symlink, or not there
        target = ""
    if "zoneinfo/" in target:
        name = target.split("zoneinfo/", 1)[1]
        for prefix in ("posix/", "right/"):
            name = name.removeprefix(prefix)
        if is_timezone(name):
            return name
    try:
        name = timezone_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        name = ""
    return name if name and is_timezone(name) else None


@functools.cache
def local_timezone() -> str | None:
    """`detect_timezone()` once per process, warning once when it comes up empty: the app then
    assumes `FALLBACK_TIMEZONE` (config.default_timezone), and a household elsewhere should
    hear that it did rather than find its sheet a day off."""
    zone = detect_timezone()
    if zone is None:
        log.warning("could not read this computer's time zone; assuming %s until [general] timezone in "
                    "config.toml (the Settings page) or FRIDGESHEET_TIMEZONE says otherwise", FALLBACK_TIMEZONE)
    return zone


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

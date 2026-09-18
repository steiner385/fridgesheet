"""Scheduled reports on Linux: a systemd user timer per report, written by the app.

The app writes `lakota-<key>.service` and `lakota-<key>.timer` under
`~/.config/systemd/user` and enables the timer. It never writes, enables, disables or
deletes a unit it did not author: the hand-written `lakota-print-sheet.timer` in
`LEGACY_TIMERS` is reported by `describe` and left alone by everything else (spec section
10, "existing ones untouched").

A report key is caller-supplied and can render to any unit name (`safe_key("print-sheet")
== "print-sheet"`), so that promise is enforced by `_check_ownership`, not by trusting the
caller's key: every unit this app writes starts with `MARKER`, and `install`/`remove` refuse
outright, before writing or running anything, for a computed name that is either a known
hand-written unit (`_FOREIGN_UNITS`) or an existing file that does not start with `MARKER`.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import ScheduleInfo, SchedulingError, check_schedule, safe_key
from .service_linux import UNIT_FILE as _WEB_UNIT

#: Units this app did not write. Reported read-only; never installed over, never removed.
LEGACY_TIMERS = {"open-work": "lakota-print-sheet.timer"}

#: Unit names this app must refuse by name alone, before any file is even opened: the
#: hand-written report timer, the refresh pair that keeps grades current, and the always-on
#: web server's own unit. A report key is caller-supplied and unconstrained
#: (`safe_key("print-sheet") == "print-sheet"`), so a guard keyed on the report key -- like
#: `LEGACY_TIMERS.get(key)` -- misses a key that merely *renders* to one of these names. This
#: list is what `_check_ownership` checks first.
#:
#: `_WEB_UNIT` is imported from `service_linux`, not re-spelled, so it cannot drift from the
#: name `service install` actually writes -- the same reason `scheduling_windows` imports
#: `service_windows.NAME` for its own `_FOREIGN_TASKS`. Without this, a report key of "web"
#: (`service_unit("web") == "lakota-web.service"`) is refused only because the marker check
#: happens to fail once the real unit is on disk -- and not at all against an empty
#: `unit_dir`, e.g. before `service install` has ever run. An ownership promise that holds on
#: only one platform, or only after a coincidence of file layout, is not a promise.
_FOREIGN_UNITS = (frozenset(LEGACY_TIMERS.values())
                  | {"lakota-grades-refresh.service", "lakota-grades-refresh.timer", _WEB_UNIT})

#: A refresh is 3 kids x 2 sites plus a possible login: one to three minutes. systemd's
#: default start timeout is 90 s, which would SIGTERM the run partway through every time.
TIMEOUT_START_SEC = 900


def blocking_name(key: str) -> str:
    """The unit name to show a parent when `key`'s row is unmanageable: the hand-written unit
    at a *different* name that this key is known to alias (`LEGACY_TIMERS`), or -- for every
    other key -- the name this app would itself use, which is exactly the name a hand-written
    namesake pair occupies instead (`describe`'s case 2)."""
    return LEGACY_TIMERS.get(key, timer_unit(key))


def display_name(key: str) -> str:
    """What the CLI says it installed or removed for `key`: on Linux that is the pair of units
    this app writes, not a Windows task name.

    `host.task_name` is documented as *the Windows task's display name* and answers
    "Lakota Sheet - open-work" on both platforms, so `schedule remove --all` used to print a
    Windows task name once per report on a machine where what it removed was
    `lakota-open-work.service` and `lakota-open-work.timer`. `blocking_name` above is
    platform-dispatched for the same reason; this is the other half of it."""
    return f"{unit_stem(key)}.{{service,timer}}"


def unit_stem(key: str) -> str:
    return f"lakota-{safe_key(key)}"


def service_unit(key: str) -> str:
    return f"{unit_stem(key)}.service"


def timer_unit(key: str) -> str:
    return f"{unit_stem(key)}.timer"


def _unit_dir(d: Path | None = None) -> Path:
    """Private, so `install`/`remove` can take `unit_dir=` without shadowing it -- the same
    keyword `service_linux.install` already takes."""
    return d or Path.home() / ".config" / "systemd" / "user"


#: The first line of every unit this app writes. A unit file without it was written by
#: someone else, and this app will not overwrite, enable, disable or delete it.
MARKER = "# Written by Lakota Sheet. Edits here are lost when the schedule is saved.\n"


def _ours(path: Path) -> bool:
    """True when this app wrote the unit at `path` -- or when there is nothing there yet,
    which is a name we are free to take."""
    try:
        return path.read_text(encoding="utf-8").startswith(MARKER)
    except FileNotFoundError:
        return True
    except (OSError, UnicodeDecodeError):
        return False          # unreadable is not ours to destroy -- includes non-UTF-8 bytes,
                               # which raise ValueError's UnicodeDecodeError, not OSError


def _ours_pair(key: str, unit_dir: Path | None) -> bool:
    """True only when this app wrote *both* halves of the pair -- or neither exists yet.

    One shared predicate, so `_check_ownership` and `describe` cannot drift apart on what
    counts as foreign. A mismatched pair (one file marked, the other hand-edited -- e.g. a
    parent edits `lakota-<key>.service` by hand and loses the marker on line 1 while the
    timer is untouched) is foreign as a whole: `install`/`remove` refuse it via
    `_check_ownership`, so `describe` must report it unmanageable too, not just check the
    timer half.
    """
    d = _unit_dir(unit_dir)
    return _ours(d / timer_unit(key)) and _ours(d / service_unit(key))


def _check_ownership(key: str, unit_dir: Path | None) -> None:
    """Refuse before anything is written, run, disabled or deleted, for any unit this app did
    not author. Called first in both `install` and `remove`, before `check_schedule`, before
    any file is written, before any `run` call.

    Two checks, because either alone misses something: the name check (`_FOREIGN_UNITS`)
    catches the units we know about by name even when there is nothing at `unit_dir` to read
    -- systemd may still find them in a search path this app never looks at. The marker check
    (`_ours_pair`) catches every *other* hand-written unit, named or not, which a blocklist by
    construction cannot: this is the honest implementation of this module's docstring promise
    that it never touches a unit it did not write.
    """
    t, s = timer_unit(key), service_unit(key)
    if t in _FOREIGN_UNITS or s in _FOREIGN_UNITS:
        raise SchedulingError(f"{t} is not a unit this app writes; refusing to touch it")
    if not _ours_pair(key, unit_dir):
        raise SchedulingError(f"{t} was not written by this app; refusing to touch it")


def service_text(key: str, title: str, exe: str, args: str, workdir: str, home: str) -> str:
    """The oneshot that runs the report.

    No `[Install]` section: the timer pulls this unit by name, so enabling it separately
    would be one more thing to leave behind. No `After=network-online.target` either -- that
    target is not in a user manager's unit graph, so it would document an ordering rather
    than create one.

    `LAKOTA_GRADES_HOME` is written explicitly so the unit keeps running against the home
    the app was configured with, whatever the environment of the session that fires it.
    """
    return (
        MARKER +
        f"[Unit]\nDescription=Lakota Sheet: {title}\n\n"
        f"[Service]\nType=oneshot\n"
        f"Environment=LAKOTA_GRADES_HOME={home}\n"
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
        MARKER +
        f"[Unit]\nDescription=Lakota Sheet: {title} ({', '.join(days)} at {time})\n\n"
        f"[Timer]\nUnit={service_unit(key)}\nOnCalendar={when}\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n"
    )


#: What systemctl says when the unit is simply not there. Deliberately narrow, as
#: `service_linux`'s copy is: a user manager that is not running answers "Failed to connect
#: to bus: No such file or directory", and treating that as "already gone" would leave a
#: timer enabled while telling the parent it was removed.
_NO_SUCH_UNIT = ("does not exist", "not loaded")


def _systemctl(args: list[str], run) -> subprocess.CompletedProcess:
    return run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=60)


def _systemctl_checked(args: list[str], run) -> subprocess.CompletedProcess:
    """`_systemctl` for the two callers that must not let an exception escape as one.

    `_is_enabled` and `_next_elapse` answer "no" for a host with no systemctl and a systemctl
    that hangs; `install` and `remove` have to raise instead, because there is no honest "no"
    for a write. `SchedulingError` is the type every caller already handles -- `web/schedules.py`
    catches exactly `NotSupported` and `SchedulingError`, so anything else is a 500 on the
    Schedules page.
    """
    try:
        return _systemctl(args, run)
    except FileNotFoundError:
        raise SchedulingError("systemctl was not found on this machine, so a schedule cannot be "
                              "installed or removed here") from None
    except subprocess.TimeoutExpired:
        raise SchedulingError(f"systemctl --user {' '.join(args)} timed out after 60 s; "
                              "the user service manager may not be running") from None


def _is_enabled(unit: str, run) -> bool:
    try:
        return _systemctl(["is-enabled", unit], run).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run,
            *, title: str | None = None, home: str = "", timezone: str = "", unit_dir: Path | None = None) -> None:
    """Write the pair and enable the timer.

    The ownership check runs first, ahead of even `check_schedule`: a key that renders to a
    name this app did not write must never reach a write or a `run` call. Validation happens
    next, so a bad day name leaves no half-installed schedule. A hand-written timer *enabled*
    for this report's own key stops the install too: two timers for one report means the
    sheet prints twice.
    """
    _check_ownership(key, unit_dir)
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
        p = _systemctl_checked(cmd, run)
        if p.returncode != 0:
            raise SchedulingError(f"systemctl --user {' '.join(cmd)} failed: "
                                  f"{(p.stderr or p.stdout or '').strip()[:300]}")


def remove(key: str, run=subprocess.run, *, unit_dir: Path | None = None) -> None:
    """Disable and delete the app's own pair. A unit that is not there is not an error; a
    hand-written unit is refused by `_check_ownership` before anything else runs, and this
    function is never the one that names it.

    A hand-written timer *enabled* for this report's own key stops the removal too, the
    mirror of `install`'s check. Without it, removing `open-work` disables a
    `lakota-open-work.timer` that was never there, systemctl answers "does not exist", the
    caller reports the report unscheduled -- and `lakota-print-sheet.timer` goes on printing
    it every afternoon. A removal this app cannot perform must say so, not report success.
    """
    _check_ownership(key, unit_dir)
    legacy = LEGACY_TIMERS.get(key)
    if legacy and _is_enabled(legacy, run):
        raise SchedulingError(
            f"{legacy} still schedules this report and this app did not write it, so removing "
            f"anything here would not stop it. Turn it off with: systemctl --user disable --now {legacy}")
    p = _systemctl_checked(["disable", "--now", timer_unit(key)], run)
    if p.returncode != 0:
        text = f"{p.stderr or ''}\n{p.stdout or ''}".lower()
        if not any(s in text for s in _NO_SUCH_UNIT):
            raise SchedulingError(f"systemctl --user disable --now {timer_unit(key)} failed: "
                                  f"{(p.stderr or p.stdout or '').strip()[:300]}")
    d = _unit_dir(unit_dir)
    (d / timer_unit(key)).unlink(missing_ok=True)
    (d / service_unit(key)).unlink(missing_ok=True)
    _systemctl_checked(["daemon-reload"], run)


def _next_elapse(unit: str, run) -> str | None:
    try:
        p = _systemctl(["show", unit, "-p", "NextElapseUSecRealtime", "--value"], run)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return (p.stdout or "").strip() or None


def describe(key: str, run=subprocess.run, *, unit_dir: Path | None = None) -> ScheduleInfo:
    """What is scheduled for this report, whoever wrote it.

    Three answers, tried in order:

    1. The app's own timer (`timer_unit(key)`), if it is enabled.
    2. A hand-written *pair* sitting at that *same* name instead -- either half of it, not
       just the timer. `install`/`remove` already refuse to touch this one via
       `_check_ownership`, which checks both `lakota-<key>.timer` and `lakota-<key>.service`
       -- so `describe` must check the same pair with the same `_ours_pair`, or a report whose
       `.timer` is still marked but whose `.service` was hand-edited (losing the marker on
       line 1) would read as manageable here while `install`/`remove` refuse it.
    3. `LEGACY_TIMERS`: a hand-written unit under a *different* name this app knows about
       (the household's `lakota-print-sheet.timer`). Read-only, same as case 2.

    Ownership decides case 2 ahead of `is-enabled`, on purpose: `_is_enabled` asks systemd,
    `_ours_pair` reads two files at `unit_dir`, and the two can disagree -- a unit can be
    enabled with no file here (systemd found it on a search path this module never looks at)
    or have a file here without being enabled. What actually gates management is
    `_check_ownership`, and it reads the files regardless of enabled state, so a namesake pair
    that is present but currently *disabled* is still not this app's to install over.
    `describe` calls the exact same `_ours_pair` `_check_ownership` does for case 2, so the
    two can never contradict each other. Once the pair is confirmed ours (both marked, or
    neither there yet), `is-enabled` decides "installed" for cases 1 and 3: a timer can be
    enabled with no next elapse (a calendar that already passed today), and reporting that as
    "not scheduled" is how a parent ends up installing a second one.
    """
    own = timer_unit(key)
    if not _ours_pair(key, unit_dir):
        return ScheduleInfo("systemd (hand-written)", True, _next_elapse(own, run), None, False)
    if _is_enabled(own, run):
        return ScheduleInfo("systemd", True, _next_elapse(own, run), None, True)
    legacy = LEGACY_TIMERS.get(key)
    if legacy and _is_enabled(legacy, run):
        return ScheduleInfo("systemd (hand-written)", True, _next_elapse(legacy, run), None, False)
    return ScheduleInfo("systemd", False, None, None, True)

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from importlib import resources
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW, DAY_NAMES, ScheduleInfo, SchedulingError, check_schedule, task_name
from .service_windows import NAME as _WEB_TASK

#: Task Scheduler XML's day-element names, in `DAY_NAMES` order -- built *from* `DAY_NAMES`
#: rather than hardcoding its own copy of the seven keys, so a day added or reordered there
#: cannot silently leave this dict out of step with it (#31-#36 roll-up: `_DAY_TAGS`'s keys,
#: `host.DAY_NAMES` and `routes/schedules.py`'s `DAYS` were three spellings of one list).
#: `strict=True` makes that promise real rather than aspirational: without it, a `DAY_NAMES`
#: grown to eight entries with `_DAY_FULL_NAMES` left at seven would `zip` truncate to seven
#: silently, and the eighth day would pass `check_schedule` only to raise a bare `KeyError`
#: out of `render_task_xml` below -- a 500 on the Schedules page instead of a `SchedulingError`.
#: With `strict=True` the mismatch fails loudly here, at import time, instead.
_DAY_FULL_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAY_TAGS = dict(zip(DAY_NAMES, _DAY_FULL_NAMES, strict=True))
_NOT_FOUND = "cannot find the file"

#: Task names this module must refuse, whatever key renders to them: `scheduling_linux` has
#: `_FOREIGN_UNITS` for exactly this, and an ownership promise that holds on only one platform
#: is not a promise. `task_name("web")` is byte-for-byte `service_windows.NAME`, the always-on
#: logon task the installer registers -- deleting it as if it were a report's schedule takes
#: the web server away until someone reinstalls. The name is imported, never re-spelled, so
#: the two cannot drift.
_FOREIGN_TASKS = frozenset({_WEB_TASK})

#: The same names in the form `_check_ownership` actually compares against: stripped and
#: case-folded, because the namespace being protected is.
_FOREIGN_TASKS_FOLDED = frozenset(n.strip().casefold() for n in _FOREIGN_TASKS)


def blocking_name(key: str) -> str:
    """The task name to show a parent when `key`'s row is unmanageable. Task Scheduler has no
    `LEGACY_TIMERS`-style aliasing -- `describe` never sets `manageable=False` here at all --
    but this exists so `web/schedules.py` can call the same name on either platform without
    caring which one it is running on."""
    return task_name(key)


def display_name(key: str) -> str:
    """What the CLI says it installed or removed for `key`: on Windows that is the task's own
    name, exactly as Task Scheduler lists it. `scheduling_linux.display_name` answers with the
    unit pair instead, so `schedule remove --all` never names a Windows task on Linux."""
    return task_name(key)


def _check_ownership(key: str) -> None:
    """Refuse before any schtasks call, for a task this app does not schedule reports with.

    The comparison is stripped and case-folded because the namespace it is protecting is:
    Task Scheduler treats "Lakota Sheet - Web" and "Lakota Sheet - web" as one and the same
    task. An exact-string membership test guarded only the one spelling, so a `[reports.Web]`
    table hand-edited into config.toml -- which `schedule remove --all` feeds straight through
    from disk -- reached `schtasks /Delete /TN "Lakota Sheet - Web" /F` and took the web
    server's logon task with it. `scheduling_linux` deliberately has no equivalent: systemd
    unit names really are case-sensitive, so `lakota-Web.timer` is a different unit.
    """
    name = task_name(key)
    if name.strip().casefold() in _FOREIGN_TASKS_FOLDED:
        raise SchedulingError(f"{name} is not a task this app schedules reports with; refusing to touch it")


def render_task_xml(name: str, time: str, days: list[str], exe: str, args: str, workdir: str,
                    description: str | None = None) -> str:
    check_schedule(time, days)
    template = resources.files("lakota_grades.host").joinpath("task.xml").read_text(encoding="utf-8")
    day_xml = "\n".join(f"          <{_DAY_TAGS[d]} />" for d in days)
    desc = description or f"Lakota Sheet: {name.split(' - ', 1)[-1]}"
    return (template.replace("{description}", escape(desc))
                    .replace("{start}", f"2026-01-01T{time}:00")
                    .replace("{days}", day_xml)
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))


def _schtasks(cmd: list[str], run) -> subprocess.CompletedProcess:
    return run(["schtasks", *cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=60)


def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run,
            *, title: str | None = None, home: str = "", timezone: str = "") -> None:
    """`home` and `timezone` are accepted and unused: a task runs in the logged-in session's
    own environment, and `StartBoundary` is local time by definition. They are in the
    signature so `scheduling.install` is one call on both platforms.

    The ownership check runs first, ahead of even `check_schedule`, as the Linux one does: a
    key that renders to a task this app did not write must never reach a `schtasks` call."""
    _check_ownership(key)
    xml = render_task_xml(task_name(key), time, days, exe, args, workdir,
                          description=f"Lakota Sheet: {title}" if title else None)
    fd, path = tempfile.mkstemp(prefix="lakota-task-", suffix=".xml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))          # BOM + UTF-16LE, what schtasks /XML expects
        p = _schtasks(["/Create", "/TN", task_name(key), "/XML", path, "/F"], run)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if p.returncode != 0:
        raise SchedulingError(f"schtasks /Create failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def remove(key: str, run=subprocess.run) -> None:
    """Delete this report's task. A task this app did not write is refused before anything
    runs -- `remove` is the direction where getting it wrong costs the web server."""
    _check_ownership(key)
    p = _schtasks(["/Delete", "/TN", task_name(key), "/F"], run)
    if p.returncode != 0 and _NOT_FOUND not in (p.stderr or ""):
        raise SchedulingError(f"schtasks /Delete failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def describe(key: str, run=subprocess.run):
    p = _schtasks(["/Query", "/TN", task_name(key), "/FO", "LIST", "/V"], run)
    if p.returncode != 0:
        return ScheduleInfo("task-scheduler", False, None, None)
    fields = {}
    for line in (p.stdout or "").splitlines():
        m = re.match(r"^([A-Za-z ]+):\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1).strip(), m.group(2))
    return ScheduleInfo("task-scheduler", True, fields.get("Next Run Time") or None, fields.get("Last Result") or None)

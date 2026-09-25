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
    if p.returncode != 0 and _schtasks(["/Query", "/TN", name], run).returncode == 0:
        # Still registered, so the delete really failed. A task that is simply not there is
        # not an error -- and that is `/Query`'s exit code, not the words in `/Delete`'s
        # stderr: "cannot find the file" is "Das System kann die angegebene Datei nicht
        # finden." on a German Windows, and matching the English made every remove there
        # raise (#151).
        raise SchedulingError((p.stderr or p.stdout or "").strip()[:300])


def command_for(name: str) -> str:
    return f'schtasks /Delete /TN "{name}" /F'

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

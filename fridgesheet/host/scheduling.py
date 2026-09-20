"""The scheduled run of a report.

Windows: one Task Scheduler task per report, "Fridge Sheet - <key>", running only while
the user is logged in (InteractiveToken: Credential Manager and the printer need the
session) and catching up a missed start (the runner's window guard then decides).
Linux: one systemd user timer and service per report, written and enabled by this app under
`~/.config/systemd/user` -- and never a unit it did not author (`scheduling_linux`'s
`_check_ownership`), so the household's hand-written `fridgesheet-print-sheet.timer` is reported
by `describe` and left alone by `install` and `remove`.
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import IS_WINDOWS
from . import ScheduleInfo, SchedulingError, task_name  # noqa: F401  re-exported


def command_for(key: str) -> tuple[str, str, str]:
    """(exe, args, workdir) that runs the report from this installation.

    `--no-refresh` so a scheduled print never pulls Canvas/HAC itself: it trusts the
    independently-scheduled data refresh (section 5's timer, or a manual "Refresh now") to
    have kept the snapshot warm, the same "one pull, many tools" design the README promises.
    An interactive `fridgesheet run`/`print-sheet` from a terminal keeps refreshing by
    default -- someone typing the command is presumably fine waiting for it.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, f"run {key} --no-refresh", str(Path(sys.executable).parent)
    return sys.executable, f"-m fridgesheet.cli run {key} --no-refresh", str(Path.cwd())


if IS_WINDOWS:
    from . import scheduling_windows as _impl
else:
    from . import scheduling_linux as _impl

install = _impl.install
remove = _impl.remove
describe = _impl.describe
blocking_name = _impl.blocking_name
display_name = _impl.display_name

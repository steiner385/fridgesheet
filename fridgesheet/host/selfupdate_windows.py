r"""Hand off to the installer and wait to be killed by it.

`packaging/windows/installer.iss:117`, inside `PrepareToInstall`, runs before `[Files]`
copies a single file:

    Exec('taskkill.exe', '/IM FridgeSheet.exe /T /F', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

The /T takes the process *tree*. An installer launched as an ordinary child of this process
is inside that tree, so it would kill itself before copying a file.

**The original design assumed `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` put the
installer outside that tree. That assumption was tested on real Windows and is false.**
Measured on `windows-latest`, 2026-09-23 (GitHub Actions runs 35844316753 and 35844539925,
workflow `probe-detachment.yml`, branch `probe/windows-detachment`):

    parent=5500  A(flagged)=852  B(control)=5000  C(cmd-start)=6172  D(cmd-start,spaces)=6480
      ppid of 852  = 5500        <- A really was a recorded descendant
      ppid of 5000 = 5500        <- so was B
    taskkill exit code: 0
    RESULT  A flagged (DETACHED|NEW_GROUP):   KILLED
    RESULT  B control (no flags):             KILLED
    RESULT  C cmd /c start (reparented):      SURVIVED
    RESULT  D cmd /c start, path with spaces: SURVIVED

B dying alongside A is what makes this conclusive: the tree kill genuinely reached both, so
the flags contributed nothing. Why the flags can't work: both concern the console and Ctrl+C
routing -- neither is documented to change `InheritedFromUniqueProcessId`, which is the
field `taskkill /T` actually walks, and the only documented way to make a new process *not*
inherit that value from its real parent is `PROC_THREAD_ATTRIBUTE_PARENT_PROCESS`, which is
unreachable from `subprocess`.

`cmd /c start` (cases C and D above) survives instead -- not because it reparents anything,
but because **cmd.exe exits immediately** after launching the installer. By the time
`taskkill /T` walks the tree and snapshots `InheritedFromUniqueProcessId`, cmd.exe -- the
only thing that was ever really our child -- is already gone, and the installer it started
is recorded as a child of that long-dead cmd.exe, not of us.

So the installer is spawned as:

    cmd /c start "" /b <installer> /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=<path>

The empty `""` right after `start` is the window TITLE argument, and it is load-bearing, not
decorative: `start` reads a single quoted argument as a title when nothing else follows it,
so without the empty title, `start "C:\Users\John Smith\...\Setup.exe"` opens a window
titled after the path and never runs anything -- case D above (a path with a space) is what
proves the empty title makes this safe. `/b` means no new console window for the installer
itself, and `creationflags=CREATE_NO_WINDOW` on the `Popen` call keeps cmd.exe itself from
flashing a console under this frozen, windowless app (same constant, same reason, as
`service_windows.py`'s `_schtasks`).

`Popen`'s returned pid is **cmd.exe's**, not the installer's -- cmd.exe exits within
moments of being spawned, so nothing here or downstream may rely on that pid meaning
anything.

Nothing here needs changing in the installer: [Run]'s `service install` carries no
`skipifsilent`, and `service_windows.install` ends in `schtasks /Run`, so a silent install
re-registers the logon task and restarts the server by itself.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import CREATE_NO_WINDOW

INSTALLER_FLAGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")


def spawn_installer(installer: Path, log_path: Path, *, popen=subprocess.Popen) -> None:
    # `popen` here actually starts cmd.exe, not the installer -- see the module docstring
    # for why that's what survives installer.iss:117's `taskkill /IM FridgeSheet.exe /T /F`.
    # The Popen object this returns carries cmd.exe's pid, which is gone moments later, so
    # nothing may rely on it.
    popen(["cmd", "/c", "start", "", "/b", str(installer), *INSTALLER_FLAGS, f"/LOG={log_path}"],
          creationflags=CREATE_NO_WINDOW,
          close_fds=True, stdin=None, stdout=None, stderr=None)

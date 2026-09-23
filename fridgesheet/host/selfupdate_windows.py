"""Hand off to the installer and wait to be killed by it.

`packaging/windows/installer.iss`'s PrepareToInstall runs, before [Files] copies anything:

    Exec('taskkill.exe', '/IM FridgeSheet.exe /T /F', ...)

The /T takes the process *tree*. An installer launched as an ordinary child of this process
is inside that tree, so it would kill itself before copying a file. DETACHED_PROCESS and
CREATE_NEW_PROCESS_GROUP are what put it outside.

Nothing here needs changing in the installer: [Run]'s `service install` carries no
`skipifsilent`, and `service_windows.install` ends in `schtasks /Run`, so a silent install
re-registers the logon task and restarts the server by itself.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
INSTALLER_FLAGS = ("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART")


def spawn_installer(installer: Path, log_path: Path, *, popen=subprocess.Popen) -> None:
    popen([str(installer), *INSTALLER_FLAGS, f"/LOG={log_path}"],
          creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
          close_fds=True, stdin=None, stdout=None, stderr=None)

from pathlib import Path

import pytest

from fridgesheet.host import selfupdate_windows as sw


def test_the_installer_escapes_the_apps_process_tree():
    """installer.iss:117 runs `taskkill /IM FridgeSheet.exe /T /F` before it copies a file.
    /T takes the tree, so an installer launched as our child kills itself mid-upgrade. This
    assertion is the entire reason the handoff is shaped the way it is."""
    seen = {}

    def popen(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return None

    sw.spawn_installer(Path(r"C:\u\Setup.exe"), Path(r"C:\u\install.log"), popen=popen)
    flags = seen["kw"]["creationflags"]
    assert flags & sw.DETACHED_PROCESS
    assert flags & sw.CREATE_NEW_PROCESS_GROUP
    assert seen["kw"].get("close_fds") is True


def test_the_installer_runs_silently_and_writes_a_log():
    seen = {}
    sw.spawn_installer(Path(r"C:\u\Setup.exe"), Path(r"C:\u\install.log"),
                       popen=lambda cmd, **kw: seen.update(cmd=cmd))
    assert seen["cmd"][0] == r"C:\u\Setup.exe"
    assert "/VERYSILENT" in seen["cmd"]
    assert "/SUPPRESSMSGBOXES" in seen["cmd"]
    assert "/NORESTART" in seen["cmd"]
    assert r"/LOG=C:\u\install.log" in seen["cmd"]

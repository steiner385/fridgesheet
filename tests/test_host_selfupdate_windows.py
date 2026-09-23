from pathlib import Path

import pytest

from fridgesheet.host import CREATE_NO_WINDOW
from fridgesheet.host import selfupdate_windows as sw


def test_the_installer_escapes_the_apps_process_tree():
    """installer.iss:117 runs `taskkill /IM FridgeSheet.exe /T /F` before it copies a file.
    /T takes the tree, so an installer launched as our child kills itself mid-upgrade.

    Measured on real Windows (windows-latest, 2026-09-23, probe-detachment.yml): an installer
    spawned with `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` is STILL killed by that tree
    kill -- an unflagged control died right alongside it, proving the flags contribute
    nothing. `cmd /c start` survives instead, because cmd.exe exits immediately and breaks
    the recorded parent/child chain before taskkill snapshots it. This assertion is the
    entire reason the handoff is shaped the way it is."""
    seen = {}

    def popen(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return None

    sw.spawn_installer(Path(r"C:\u\Setup.exe"), Path(r"C:\u\install.log"), popen=popen)

    cmd = seen["cmd"]
    # The empty "" is the window TITLE argument to `start`, and it is load-bearing: without
    # it, `start "C:\Users\John Smith\...\Setup.exe"` reads the quoted path as a title and
    # never runs the installer. A test that would pass with "" dropped is worthless -- this
    # is exactly the spaces bug the empty title exists to prevent.
    assert cmd[:5] == ["cmd", "/c", "start", "", "/b"]
    assert cmd[5] == r"C:\u\Setup.exe"

    assert seen["kw"]["creationflags"] == CREATE_NO_WINDOW
    assert seen["kw"].get("close_fds") is True

    # The old flags proved to contribute nothing on real Windows (both the flagged process
    # and its unflagged control died to the same taskkill /T). They must be gone entirely,
    # not merely unused, so nobody mistakes their presence for meaning something.
    assert not hasattr(sw, "DETACHED_PROCESS")
    assert not hasattr(sw, "CREATE_NEW_PROCESS_GROUP")


def test_the_installer_runs_silently_and_writes_a_log():
    seen = {}
    sw.spawn_installer(Path(r"C:\u\Setup.exe"), Path(r"C:\u\install.log"),
                       popen=lambda cmd, **kw: seen.update(cmd=cmd))
    assert seen["cmd"][0] == "cmd"
    assert seen["cmd"][5] == r"C:\u\Setup.exe"
    assert "/VERYSILENT" in seen["cmd"]
    assert "/SUPPRESSMSGBOXES" in seen["cmd"]
    assert "/NORESTART" in seen["cmd"]
    assert r"/LOG=C:\u\install.log" in seen["cmd"]

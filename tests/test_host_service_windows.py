"""Windows logon task "Fridge Sheet - web" adapter tests."""
from __future__ import annotations

import subprocess

from fridgesheet.host import service_windows


QUERY_V = """\
Folder: \\
HostName:                             GRAPHY
TaskName:                             \\Fridge Sheet - web
Status:                               Running
Logon Mode:                           Interactive/Background
Task To Run:                          C:\\Users\\houserunner\\AppData\\Local\\Programs\\Fridge Sheet\\FridgeSheet.exe web --no-browser
Run As User:                          houserunner
"""


def _run_returning(stdout: str, code: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="")
    return run


def test_describe_reports_the_account_the_task_runs_as():
    """Seen on the household's Windows box, 2026-09-22: the logon task runs as one
    account while an SSH session arrives as another. A self-update by the wrong user
    builds a second install under a different profile and reports success -- the worst
    failure, because nothing visible changes."""
    info = service_windows.describe(run=_run_returning(QUERY_V))
    assert info.owner == "houserunner"
    assert info.installed and info.active


def test_owner_is_empty_rather_than_wrong_when_the_field_is_absent():
    info = service_windows.describe(run=_run_returning("Status:  Running\n"))
    assert info.owner == ""


def test_an_absent_task_has_no_owner():
    info = service_windows.describe(run=_run_returning("", code=1))
    assert info.installed is False and info.owner == ""

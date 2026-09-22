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
Task To Run:                          C:\\Users\\lakotarunner\\AppData\\Local\\Programs\\Fridge Sheet\\FridgeSheet.exe web --no-browser
Run As User:                          lakotarunner
"""


def _run_returning(stdout: str, code: int = 0):
    def run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="")
    return run


def test_describe_reports_the_account_the_task_runs_as():
    """Seen on graphy 2026-09-22: the task runs as `lakotarunner` while SSH arrives as
    `tony`. A self-update by the wrong user builds a second install and changes nothing
    anyone can see, so the owner has to be readable."""
    info = service_windows.describe(run=_run_returning(QUERY_V))
    assert info.owner == "lakotarunner"
    assert info.installed and info.active


def test_owner_is_empty_rather_than_wrong_when_the_field_is_absent():
    info = service_windows.describe(run=_run_returning("Status:  Running\n"))
    assert info.owner == ""


def test_an_absent_task_has_no_owner():
    info = service_windows.describe(run=_run_returning("", code=1))
    assert info.installed is False and info.owner == ""

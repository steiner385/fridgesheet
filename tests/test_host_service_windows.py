"""Windows logon task "Fridge Sheet - web" adapter tests."""
from __future__ import annotations

import subprocess

import pytest

from fridgesheet.host import ServiceError
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


def _run_sequence(responses: dict):
    """A fake `run` keyed by the schtasks subcommand (argv[1]: "/Create", "/Query", "/Run"),
    each entry a (returncode, stdout, stderr) triple. Records every call so a test can assert
    exactly which schtasks calls happened, and in what order -- in particular, that a
    mismatch never reaches `/Run` at all."""
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        code, out, err = responses[cmd[1]]
        return subprocess.CompletedProcess(cmd, code, stdout=out, stderr=err)
    return calls, run


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


def test_describe_reports_the_command_the_task_runs():
    info = service_windows.describe(run=_run_returning(QUERY_V))
    assert info.command == (r"C:\Users\houserunner\AppData\Local\Programs\Fridge Sheet\FridgeSheet.exe "
                            "web --no-browser")


def test_command_is_empty_rather_than_wrong_when_the_field_is_absent():
    info = service_windows.describe(run=_run_returning("Status:  Running\n"))
    assert info.command == ""


# -- install()'s fallback to /Run when /Create cannot (re)write an already-correct task ------
#
# graphy, 2026-09-23, real 0.4.1 -> 0.5.0 upgrade: the logon task was registered by an
# administrator while the app runs as the standard account `svc_fridgesheet`. `schtasks /Create
# ... /F` cannot overwrite a task it does not own ("ERROR: Access is denied."), so install()
# raised, [Run]'s `service install` exited 1, and because Inno Setup does not check [Run]
# exit codes the installer reported success while /health stayed unreachable and
# Get-Process FridgeSheet returned nothing -- until a human ran `schtasks /Run` by hand.


def test_create_succeeds_runs_and_returns_no_fallback_note():
    """Regression guard: today's happy path is unchanged -- /Create, then /Run, no error,
    and no /Query in between (nothing to fall back from)."""
    responses = {"/Create": (0, "", ""), "/Run": (0, "", "")}
    calls, run = _run_sequence(responses)
    note = service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert [c[1] for c in calls] == ["/Create", "/Run"]
    assert not note


def test_create_denied_matching_existing_task_falls_through_to_run(monkeypatch):
    """The genuine graphy case: /Create is refused, but Task Scheduler already has exactly
    the task we would have created, running as the account we are running as -- so /Run
    alone is enough, and install() must not raise."""
    query_out = ("Status:  Ready\n"
                "Task To Run:  C:\\App\\FridgeSheet.exe web --no-browser\n"
                "Run As User:  svc_fridgesheet\n")
    responses = {"/Create": (1, "", "ERROR: Access is denied."), "/Query": (0, query_out, ""), "/Run": (0, "", "")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    note = service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert [c[1] for c in calls] == ["/Create", "/Query", "/Run"]
    assert note        # caller can tell "re-registered" from "fell back to the existing one"


def test_create_denied_existing_task_points_at_a_different_exe_raises(monkeypatch):
    """A task that merely exists is not good enough -- one pointed at a stale install must
    still be a hard error, and must never be started."""
    query_out = ("Status:  Ready\n"
                "Task To Run:  C:\\Old\\FridgeSheet.exe web --no-browser\n"
                "Run As User:  svc_fridgesheet\n")
    responses = {"/Create": (1, "", "ERROR: Access is denied."), "/Query": (0, query_out, "")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    msg = str(e.value)
    assert "Old" in msg and "FridgeSheet.exe" in msg          # names the mismatch
    assert "/Run" not in [c[1] for c in calls]                # never started the wrong task


def test_create_denied_existing_task_runs_as_a_different_user_raises(monkeypatch):
    query_out = ("Status:  Ready\n"
                "Task To Run:  C:\\App\\FridgeSheet.exe web --no-browser\n"
                "Run As User:  Administrator\n")
    responses = {"/Create": (1, "", "ERROR: Access is denied."), "/Query": (0, query_out, "")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    msg = str(e.value)
    assert "Administrator" in msg and "svc_fridgesheet" in msg
    assert "/Run" not in [c[1] for c in calls]


def test_create_denied_no_existing_task_raises_the_genuine_first_install_case(monkeypatch):
    """The genuine first-install shape of #39: /Create failed and there is nothing
    registered to fall back to -- this must stay a hard error exactly as before."""
    responses = {"/Create": (1, "", "ERROR: Access is denied."),
                "/Query": (1, "", "ERROR: The system cannot find the file specified.")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert "Access is denied" in str(e.value)
    assert "/Run" not in [c[1] for c in calls]


def test_create_fails_for_an_unrelated_reason_with_a_matching_task_still_falls_through(monkeypatch):
    """Decision, and why: the fallback does not gate on *why* /Create failed, only on
    whether the already-registered task is genuinely the one we would have created (same
    command, same account). schtasks' stderr text for "you may not touch this task" is not
    a stable, parseable contract across locales and Windows versions, so keying safety off
    matching that text would be brittle in exactly the way the exe/user checks above are
    not. The exe/user match is what keeps this safe; the failure reason is not load-bearing."""
    query_out = ("Status:  Ready\n"
                "Task To Run:  C:\\App\\FridgeSheet.exe web --no-browser\n"
                "Run As User:  svc_fridgesheet\n")
    responses = {"/Create": (1, "", "ERROR: The task XML contains a value which is incorrectly formatted."),
                "/Query": (0, query_out, ""), "/Run": (0, "", "")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    note = service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert [c[1] for c in calls] == ["/Create", "/Query", "/Run"]
    assert note


def test_normalize_command_treats_quoting_casing_and_whitespace_as_equal():
    a = service_windows._normalize_command('"C:\\App\\FridgeSheet.exe"   web  --no-browser')
    b = service_windows._normalize_command("c:\\app\\fridgesheet.exe web --no-browser")
    assert a == b


def test_normalize_command_still_distinguishes_a_different_path():
    a = service_windows._normalize_command(r"C:\App\FridgeSheet.exe web --no-browser")
    b = service_windows._normalize_command(r"C:\Old\FridgeSheet.exe web --no-browser")
    assert a != b

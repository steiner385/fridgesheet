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
    mismatch never reaches `/Run` at all. Tests that must never legitimately reach `/Run`
    still supply a response for it: a guard that breaks and calls it anyway should fail a
    plain `assert "/Run" not in calls`, not blow up as a `KeyError` out of this fake."""
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
    responses = {"/Create": (1, "", "ERROR: Access is denied."), "/Query": (0, query_out, ""), "/Run": (0, "", "")}
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
    responses = {"/Create": (1, "", "ERROR: Access is denied."), "/Query": (0, query_out, ""), "/Run": (0, "", "")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    msg = str(e.value)
    assert "Administrator" in msg and "svc_fridgesheet" in msg
    assert "/Run" not in [c[1] for c in calls]


def test_create_denied_no_existing_task_falls_back_to_a_startup_shortcut(monkeypatch, tmp_path):
    """#10: a standard Windows user cannot create a task at all ("Access is denied" from
    schtasks and from the COM API alike), so a first install as that user used to end with an
    app that never starts itself -- and an installer that reported success. A standard user can
    always write their own Startup folder: the shortcut starts the server at every sign-in (the
    task's LogonTrigger, minus RestartOnFailure), and the server is started once now."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    responses = {"/Create": (1, "", "ERROR: Access is denied."),
                 "/Query": (1, "", "ERROR: The system cannot find the file specified."),
                 "/Run": (0, "", ""), "-NoProfile": (0, "", "")}
    calls, run = _run_sequence(responses)
    started = []
    note = service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run,
                                   start=lambda exe, args, wd: started.append((exe, args, wd)))
    assert "/Run" not in [c[1] for c in calls]                 # there is no task to run
    (ps,) = [c for c in calls if c[0] == "powershell"]
    script = ps[-1]
    lnk = service_windows.startup_shortcut()
    assert str(lnk) in script and "CreateShortcut" in script and "C:\\App\\FridgeSheet.exe" in script
    assert "'web --no-browser'" in script and "WindowStyle = 7" in script
    assert started == [(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App")]
    assert "Startup folder" in note and "Access is denied" in note


def test_a_startup_shortcut_that_cannot_be_written_is_still_a_hard_error(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    responses = {"/Create": (1, "", "ERROR: Access is denied."),
                 "/Query": (1, "", "ERROR: The system cannot find the file specified."),
                 "/Run": (0, "", ""), "-NoProfile": (1, "", "CreateShortcut failed")}
    calls, run = _run_sequence(responses)
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run,
                                start=lambda *a: pytest.fail("must not start"))
    assert "Access is denied" in str(e.value) and "CreateShortcut failed" in str(e.value)


def test_with_no_appdata_there_is_no_fallback(monkeypatch):
    monkeypatch.delenv("APPDATA", raising=False)
    responses = {"/Create": (1, "", "ERROR: Access is denied."),
                 "/Query": (1, "", "ERROR: The system cannot find the file specified."),
                 "/Run": (0, "", "")}
    calls, run = _run_sequence(responses)
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert "no existing" in str(e.value)


def test_a_quote_in_a_path_cannot_break_out_of_the_powershell_string(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path / "O'Brien"))
    responses = {"/Create": (1, "", "denied"), "/Query": (1, "", "not found"), "/Run": (0, "", ""), "-NoProfile": (0, "", "")}
    calls, run = _run_sequence(responses)
    service_windows.install(r"C:\Users\O'Brien\FridgeSheet.exe", "web --no-browser", r"C:\x", run=run, start=lambda *a: None)
    script = [c for c in calls if c[0] == "powershell"][0][-1]
    assert "O''Brien" in script and "O'Brien" not in script.replace("O''Brien", "")


def test_describe_and_remove_know_the_startup_shortcut(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    lnk = service_windows.startup_shortcut()
    lnk.parent.mkdir(parents=True)
    lnk.write_bytes(b"lnk")
    info = service_windows.describe(run=_run_returning("", code=1))
    assert info.installed and info.managed_by == "startup-folder"
    # A failed /Delete is followed by a /Query: absent is its exit code, not its stderr text.
    _, run = _run_sequence({"/End": (1, "", ""), "/Delete": (1, "", "ERROR: The system cannot find the file specified."),
                            "/Query": (1, "", "")})
    service_windows.remove(run=run)
    assert not lnk.exists()


def test_a_task_created_later_replaces_the_startup_shortcut(monkeypatch, tmp_path):
    """Once the task can be created (an admin ran the installer), the shortcut would start a
    second copy at sign-in; it goes."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    lnk = service_windows.startup_shortcut()
    lnk.parent.mkdir(parents=True)
    lnk.write_bytes(b"lnk")
    calls, run = _run_sequence({"/Create": (0, "", ""), "/Run": (0, "", "")})
    service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert not lnk.exists()

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


def test_create_succeeds_but_run_fails_does_not_raise(monkeypatch):
    """The asymmetry, pinned: on the ordinary /Create-succeeded path, a failing /Run is
    tolerated -- the task itself is correct and its own LogonTrigger starts it at the next
    sign-in, exactly as before this fix. Only the fallback path (below) turns a failing
    /Run into a raise."""
    responses = {"/Create": (0, "", ""), "/Run": (1, "", "ERROR: The service has not been started.")}
    calls, run = _run_sequence(responses)
    note = service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert [c[1] for c in calls] == ["/Create", "/Run"]
    assert not note


def test_fallback_matches_but_run_fails_raises_naming_the_run_failure(monkeypatch):
    """Without this, install() reproduces the exact bug it fixes one step later: /Create is
    denied, the existing task matches so install() decides to fall back, but /Run -- the
    entire remedy on this path -- also fails (its own ACL denial, the task Disabled, Task
    Scheduler unhappy), and nothing actually starts the server. This must raise, and the
    message must name the /Run failure, not the /Create failure that preceded it -- a reader
    tailing the install log needs to know which command actually left the server down."""
    query_out = ("Status:  Ready\n"
                "Task To Run:  C:\\App\\FridgeSheet.exe web --no-browser\n"
                "Run As User:  svc_fridgesheet\n")
    responses = {"/Create": (1, "", "ERROR: Access is denied."), "/Query": (0, query_out, ""),
                "/Run": (1, "", "ERROR: The service has not been started.")}
    calls, run = _run_sequence(responses)
    monkeypatch.setattr(service_windows, "_current_user", lambda: "svc_fridgesheet")
    with pytest.raises(ServiceError) as e:
        service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    msg = str(e.value)
    assert "/Run" in msg and "The service has not been started" in msg
    assert "Access is denied" not in msg          # names the /Run failure, not the earlier /Create one
    assert [c[1] for c in calls] == ["/Create", "/Query", "/Run"]


def test_normalize_command_treats_quoting_casing_and_whitespace_as_equal():
    a = service_windows._normalize_command('"C:\\App\\FridgeSheet.exe"   web  --no-browser')
    b = service_windows._normalize_command("c:\\app\\fridgesheet.exe web --no-browser")
    assert a == b


def test_normalize_command_still_distinguishes_a_different_path():
    a = service_windows._normalize_command(r"C:\App\FridgeSheet.exe web --no-browser")
    b = service_windows._normalize_command(r"C:\Old\FridgeSheet.exe web --no-browser")
    assert a != b

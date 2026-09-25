"""The always-on server adapter: unit text and systemctl argv on Linux, task XML and schtasks argv on Windows."""
from __future__ import annotations

import subprocess

import pytest

from fridgesheet.host import service, service_linux, service_windows


def _recorder(results=None):
    calls = []
    results = results or {}
    def run(argv, **kw):
        calls.append(argv)
        rc, out = results.get(tuple(argv[-2:]), (0, ""))
        return subprocess.CompletedProcess(argv, rc, stdout=out, stderr="")
    return calls, run


def test_unit_text_is_a_restarting_user_service():
    text = service_linux.unit_text("/opt/venv/bin/python", "-m fridgesheet.cli web --no-browser", "/home/tony")
    assert "[Unit]" in text and "Description=Fridge Sheet web app" in text
    assert "ExecStart=/opt/venv/bin/python -m fridgesheet.cli web --no-browser" in text
    assert "WorkingDirectory=/home/tony" in text and "Restart=on-failure" in text and "RestartSec=5" in text
    assert "WantedBy=default.target" in text
    assert "network-online" not in text          # not a real ordering in the user manager's unit graph


def test_linux_install_writes_the_unit_and_enables_it_now(tmp_path):
    calls, run = _recorder()
    service_linux.install("/py", "-m fridgesheet.cli web --no-browser", "/wd", run=run, unit_dir=tmp_path)
    unit = tmp_path / "fridgesheet-web.service"
    assert unit.is_file() and "ExecStart=/py -m fridgesheet.cli web --no-browser" in unit.read_text()
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "fridgesheet-web.service"]]


def test_linux_remove_disables_and_deletes(tmp_path):
    (tmp_path / "fridgesheet-web.service").write_text("x")
    calls, run = _recorder()
    service_linux.remove(run=run, unit_dir=tmp_path)
    assert not (tmp_path / "fridgesheet-web.service").exists()
    assert calls == [["systemctl", "--user", "disable", "--now", "fridgesheet-web.service"], ["systemctl", "--user", "daemon-reload"]]
    service_linux.remove(run=run, unit_dir=tmp_path)           # a second remove is fine

    def absent(argv, **kw):                                    # a unit that was never installed
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to disable unit: Unit file fridgesheet-web.service does not exist.")
    service_linux.remove(run=absent, unit_dir=tmp_path)         # still idempotent


def test_linux_remove_raises_when_disable_really_fails(tmp_path):
    """"Removed the service" must never be printed over a `disable --now` that did not work:
    the unit would still start the server at the next logon."""
    (tmp_path / "fridgesheet-web.service").write_text("x")
    def no_bus(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus: No such file or directory")
    with pytest.raises(service.ServiceError) as e:
        service_linux.remove(run=no_bus, unit_dir=tmp_path)
    assert "disable --now" in str(e.value) and "Failed to connect to bus" in str(e.value)
    assert (tmp_path / "fridgesheet-web.service").exists()           # nothing was deleted either


def test_linux_describe_reads_enabled_and_active():
    calls, run = _recorder({("is-enabled", "fridgesheet-web.service"): (0, "enabled\n"), ("is-active", "fridgesheet-web.service"): (0, "active\n")})
    info = service_linux.describe(run=run)
    assert (info.managed_by, info.installed, info.active) == ("systemd", True, True) and "active" in info.detail
    calls, run = _recorder({("is-enabled", "fridgesheet-web.service"): (1, "disabled\n"), ("is-active", "fridgesheet-web.service"): (3, "inactive\n")})
    info = service_linux.describe(run=run)
    assert (info.installed, info.active) == (False, False)


def test_linux_install_reports_a_systemctl_failure(tmp_path):
    calls = []
    def failing_enable(argv, **kw):
        calls.append(argv)
        if argv[-3:] == ["enable", "--now", "fridgesheet-web.service"]:
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
    with pytest.raises(service.ServiceError) as e:
        service_linux.install("/py", "x", "/wd", run=failing_enable, unit_dir=tmp_path)
    assert "Failed to connect to bus" in str(e.value)
    assert calls == [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", "fridgesheet-web.service"]]
    # A unit this attempt wrote and could not enable does not stay behind (#7).
    assert not (tmp_path / "fridgesheet-web.service").exists()


def test_linux_install_failing_on_upgrade_keeps_the_unit_that_was_there(tmp_path):
    unit = tmp_path / "fridgesheet-web.service"
    unit.write_text("[Service]\nExecStart=/old x\n")
    def failing_enable(argv, **kw):
        rc = 1 if argv[-3:] == ["enable", "--now", "fridgesheet-web.service"] else 0
        return subprocess.CompletedProcess(argv, rc, stdout="", stderr="Failed to connect to bus")
    with pytest.raises(service.ServiceError):
        service_linux.install("/py", "x", "/wd", run=failing_enable, unit_dir=tmp_path)
    assert unit.is_file()


def test_linux_install_reports_a_daemon_reload_failure(tmp_path):
    def failing_reload(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus")
    with pytest.raises(service.ServiceError) as e:
        service_linux.install("/py", "x", "/wd", run=failing_reload, unit_dir=tmp_path)
    assert "daemon-reload" in str(e.value) and "Failed to connect to bus" in str(e.value)


def test_logon_task_xml_runs_at_logon_and_restarts():
    xml = service_windows.render_logon_task_xml(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App")
    assert "<LogonTrigger>" in xml and "<Command>C:\\App\\FridgeSheet.exe</Command>" in xml and "<Arguments>web --no-browser</Arguments>" in xml
    assert "<RestartOnFailure>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml and "InteractiveToken" in xml
    xml2 = service_windows.render_logon_task_xml(r"C:\A & B\FridgeSheet.exe", "web --no-browser", r"C:\A & B")
    assert "<Command>C:\\A &amp; B\\FridgeSheet.exe</Command>" in xml2       # escaped


def test_windows_install_creates_and_starts_the_task(tmp_path):
    calls, run = _recorder()
    note = service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert calls[0][:4] == ["schtasks", "/Create", "/TN", "Fridge Sheet - web"] and "/XML" in calls[0] and "/F" in calls[0]
    assert calls[1] == ["schtasks", "/Run", "/TN", "Fridge Sheet - web"]
    assert not note                                              # today's path: nothing to report


def test_windows_remove_ends_then_deletes_and_tolerates_absence():
    calls, run = _recorder()
    service_windows.remove(run=run)
    assert calls == [["schtasks", "/End", "/TN", "Fridge Sheet - web"], ["schtasks", "/Delete", "/TN", "Fridge Sheet - web", "/F"]]
    def missing(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="ERROR: The system cannot find the file specified.")
    service_windows.remove(run=missing)


def test_windows_describe_reads_status():
    out = "TaskName: \\Fridge Sheet - web\nStatus: Running\nNext Run Time: N/A\n"
    calls = []
    def query(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
    info = service_windows.describe(run=query)
    assert calls == [["schtasks", "/Query", "/TN", "Fridge Sheet - web", "/FO", "LIST", "/V"]]
    assert (info.managed_by, info.installed, info.active) == ("task-scheduler", True, True)

    calls2 = []
    def absent(argv, **kw):
        calls2.append(argv)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="ERROR: The system cannot find the file specified.")
    info2 = service_windows.describe(run=absent)
    assert calls2 == [["schtasks", "/Query", "/TN", "Fridge Sheet - web", "/FO", "LIST", "/V"]]
    assert info2.installed is False


def test_command_for_source_and_frozen(monkeypatch):
    exe, args, wd = service.command_for()
    assert args == "-m fridgesheet.cli web --no-browser"
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\App\FridgeSheet.exe")
    exe, args, wd = service.command_for()
    assert (exe, args, wd) == (r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App")


def test_install_service_folds_a_fallback_note_into_its_report(monkeypatch):
    """`cmd_service` prints exactly `install_service()`'s return value -- this is how a
    fallback (graphy, 2026-09-23: /Create denied, existing task matched and was started
    instead of rewritten) becomes visible to whoever reads the install log, without
    `cmd_service` itself needing to know the fallback happened."""
    monkeypatch.setattr(service, "_impl", service_windows)
    monkeypatch.setattr(service_windows, "install", lambda exe, args, workdir, run, home: "started the existing task")
    monkeypatch.setattr(service, "command_for", lambda: ("/py", "-m fridgesheet.cli web --no-browser", "/wd"))
    assert service.install_service() == "/py -m fridgesheet.cli web --no-browser (started the existing task)"

    monkeypatch.setattr(service_windows, "install", lambda exe, args, workdir, run, home: "")
    assert service.install_service() == "/py -m fridgesheet.cli web --no-browser"


def test_cli_service_show_prints_the_state(capsys, monkeypatch):
    from fridgesheet import cli
    from fridgesheet.host import ServiceInfo
    monkeypatch.setattr(service, "describe_service", lambda: ServiceInfo("systemd", True, True, "enabled, active"))
    with pytest.raises(SystemExit) as e:
        cli.main(["service", "show"])
    assert e.value.code == 0 and "enabled, active" in capsys.readouterr().out


def test_unit_text_carries_the_home_the_timers_run_against():
    """Every report timer writes `FRIDGESHEET_HOME` into its unit; the web server's did not, so
    a custom home reached the timers and not the server -- two data folders (#151). Quoted
    the way `scheduling_linux.service_text` quotes it, so a path with a space loads."""
    text = service_linux.unit_text("/py", "x", "/wd", home="/home/tony/.fridgesheet")
    assert "Environment=FRIDGESHEET_HOME=/home/tony/.fridgesheet\n" in text
    spaced = service_linux.unit_text("/py", "x", "/wd", home="/home/tony/My Data/.fridgesheet")
    assert 'Environment="FRIDGESHEET_HOME=/home/tony/My Data/.fridgesheet"\n' in spaced
    assert "FRIDGESHEET_HOME" not in service_linux.unit_text("/py", "x", "/wd")   # nothing known: nothing written


def test_linux_install_writes_the_home_into_the_unit(tmp_path):
    calls, run = _recorder()
    service_linux.install("/py", "x", "/wd", run=run, unit_dir=tmp_path, home="/data/fs")
    assert "Environment=FRIDGESHEET_HOME=/data/fs\n" in (tmp_path / "fridgesheet-web.service").read_text()


def test_install_service_hands_the_home_to_the_platform(monkeypatch):
    seen = {}
    monkeypatch.setattr(service, "_impl", service_linux)
    monkeypatch.setattr(service_linux, "install", lambda exe, args, workdir, run, home: seen.update(home=home))
    monkeypatch.setattr(service, "command_for", lambda: ("/py", "x", "/wd"))
    service.install_service(home="/data/fs")
    assert seen["home"] == "/data/fs"


def test_cli_service_install_names_the_home_the_app_runs_against(monkeypatch, capsys):
    """The same home the schedule commands write into the timers: the resolved default
    (`FRIDGESHEET_HOME` or the OS location), without loading config.toml -- a broken config
    must not stop the installer from registering the server."""
    from fridgesheet import cli, config
    from fridgesheet.host import ServiceInfo
    seen = {}
    monkeypatch.setattr(service, "install_service", lambda **kw: seen.update(kw) or "/py x")
    monkeypatch.setattr(service, "describe_service", lambda: ServiceInfo("systemd", True, True, "enabled, active"))
    with pytest.raises(SystemExit) as e:
        cli.main(["service", "install"])
    assert e.value.code == 0 and seen["home"] == str(config.DEFAULT_HOME)


def test_windows_remove_decides_absence_by_exit_code_not_by_english_text():
    """A German Windows answers "Das System kann die angegebene Datei nicht finden."; matching
    "cannot find the file" made every remove there an error (#151). Whether the task is still
    registered is `/Query`'s exit code, which no locale changes."""
    calls = []
    def gone(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="FEHLER: Das System kann die angegebene Datei nicht finden.")
    service_windows.remove(run=gone)
    assert calls[1:] == [["schtasks", "/Delete", "/TN", "Fridge Sheet - web", "/F"], ["schtasks", "/Query", "/TN", "Fridge Sheet - web"]]

    def still_there(argv, **kw):
        rc = 1 if argv[1] == "/Delete" else 0
        return subprocess.CompletedProcess(argv, rc, stdout="", stderr="FEHLER: Zugriff verweigert")
    with pytest.raises(service.ServiceError, match="Zugriff verweigert"):
        service_windows.remove(run=still_there)

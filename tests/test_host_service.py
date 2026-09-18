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
    unit = tmp_path / "fridgesheet-web.service"
    assert unit.is_file() and "ExecStart=/py x" in unit.read_text()   # the unit is written before systemctl runs


def test_linux_install_reports_a_daemon_reload_failure(tmp_path):
    def failing_reload(argv, **kw):
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Failed to connect to bus")
    with pytest.raises(service.ServiceError) as e:
        service_linux.install("/py", "x", "/wd", run=failing_reload, unit_dir=tmp_path)
    assert "daemon-reload" in str(e.value) and "Failed to connect to bus" in str(e.value)


def test_logon_task_xml_runs_at_logon_and_restarts():
    xml = service_windows.render_logon_task_xml("Fridge Sheet - web", r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App")
    assert "<LogonTrigger>" in xml and "<Command>C:\\App\\FridgeSheet.exe</Command>" in xml and "<Arguments>web --no-browser</Arguments>" in xml
    assert "<RestartOnFailure>" in xml and "<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml and "InteractiveToken" in xml
    xml2 = service_windows.render_logon_task_xml("Fridge Sheet - web", r"C:\A & B\FridgeSheet.exe", "web --no-browser", r"C:\A & B")
    assert "<Command>C:\\A &amp; B\\FridgeSheet.exe</Command>" in xml2       # escaped


def test_windows_install_creates_and_starts_the_task(tmp_path):
    calls, run = _recorder()
    service_windows.install(r"C:\App\FridgeSheet.exe", "web --no-browser", r"C:\App", run=run)
    assert calls[0][:4] == ["schtasks", "/Create", "/TN", "Fridge Sheet - web"] and "/XML" in calls[0] and "/F" in calls[0]
    assert calls[1] == ["schtasks", "/Run", "/TN", "Fridge Sheet - web"]


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


def test_cli_service_show_prints_the_state(capsys, monkeypatch):
    from fridgesheet import cli
    from fridgesheet.host import ServiceInfo
    monkeypatch.setattr(service, "describe_service", lambda: ServiceInfo("systemd", True, True, "enabled, active"))
    with pytest.raises(SystemExit) as e:
        cli.main(["service", "show"])
    assert e.value.code == 0 and "enabled, active" in capsys.readouterr().out

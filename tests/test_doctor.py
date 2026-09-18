"""The self-check: every probe is isolated, a raising probe is a FAIL line, the report is
written to <home>/doctor.txt, and the CLI exit code follows the verdict."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from lakota_grades import cli, doctor, host
from lakota_grades.config import ReportConfig, Settings
from lakota_grades.host import ScheduleInfo, printing, scheduling


def _probes():
    return [
        ("python", lambda s, h: "3.12"),
        ("boom", lambda s, h: (_ for _ in ()).throw(RuntimeError("no such thing"))),
        ("printers", lambda s, h: "2 printers, default Office"),
    ]


def test_checks_isolate_each_probe(tmp_path):
    out = doctor.checks(Settings(home=tmp_path), tmp_path, probes=_probes())
    assert [(c.name, c.ok) for c in out] == [("python", True), ("boom", False), ("printers", True)]
    assert out[1].detail == "RuntimeError: no such thing"


def test_format_report_and_run_write_doctor_txt(tmp_path):
    report, ok = doctor.run(Settings(home=tmp_path), tmp_path, probes=_probes())
    assert not ok
    assert report.splitlines()[0] == "OK    python: 3.12"
    assert "FAIL  boom: RuntimeError: no such thing" in report
    assert report.splitlines()[-1] == "1 check(s) failed"
    assert (tmp_path / "doctor.txt").read_text(encoding="utf-8") == report
    report2, ok2 = doctor.run(Settings(home=tmp_path), tmp_path, probes=_probes()[:1])
    assert ok2 and report2.splitlines()[-1] == "All checks passed"


def test_real_probes_run_on_this_machine(tmp_path):
    """The default probe list must not crash; individual probes may FAIL here (no printer,
    no keyring) but each must produce a Check."""
    out = doctor.checks(Settings(home=tmp_path), tmp_path)
    names = [c.name for c in out]
    assert names == ["python", "home", "database", "timezone", "pdf", "chromium", "credential store", "printers", "print engine", "scheduler", "web server"]
    assert all(isinstance(c.detail, str) and c.detail for c in out)
    by = {c.name: c for c in out}
    assert by["python"].ok and by["home"].ok and by["database"].ok and by["timezone"].ok and by["pdf"].ok
    if not by["chromium"].ok:
        pytest.skip(f"no Playwright browser here: {by['chromium'].detail}")
    assert by["chromium"].ok and by["chromium"].detail.startswith("Chromium ")


def test_database_probe_reports_counts(tmp_path):
    from lakota_grades.web import db
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('t', '{}', 1)")
    conn.close()
    out = {c.name: c for c in doctor.checks(Settings(home=tmp_path), tmp_path, probes=[p for p in doctor.PROBES if p[0] == "database"])}
    assert out["database"].ok and "schema 1" in out["database"].detail and "1 refreshes" in out["database"].detail


def test_run_reports_an_unwritable_home_instead_of_raising(tmp_path):
    import os, stat
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("read-only directories are not enforced here")
    ro = tmp_path / "ro"
    ro.mkdir()
    ro.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        report, ok = doctor.run(Settings(home=ro), ro, probes=[("python", lambda s, h: "3.12")])
    finally:
        ro.chmod(stat.S_IRWXU)
    assert not ok and "FAIL  report: could not write" in report and not (ro / "doctor.txt").exists()


def test_cli_doctor_exit_code_follows_verdict(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))
    monkeypatch.setattr(doctor, "PROBES", _probes())
    with pytest.raises(SystemExit) as e:
        cli.main(["doctor"])
    assert e.value.code == 1 and "FAIL  boom" in capsys.readouterr().out
    monkeypatch.setattr(doctor, "PROBES", _probes()[:1])
    with pytest.raises(SystemExit) as e:
        cli.main(["doctor"])
    assert e.value.code == 0


def test_printers_probe_fails_when_it_cannot_print(monkeypatch, tmp_path):
    monkeypatch.setattr(printing, "list_printers", lambda: [])
    monkeypatch.setattr(printing, "default_printer", lambda: None)
    with pytest.raises(RuntimeError, match="no printers are installed"):
        doctor._printers(Settings(home=tmp_path), tmp_path)

    monkeypatch.setattr(printing, "list_printers", lambda: ["Office"])
    monkeypatch.setattr(printing, "default_printer", lambda: "Office")
    with pytest.raises(RuntimeError, match=r"configured printer 'Den' is not installed; installed: Office"):
        doctor._printers(Settings(home=tmp_path, printer="Den"), tmp_path)

    monkeypatch.setattr(printing, "default_printer", lambda: None)
    with pytest.raises(RuntimeError, match="no printer is configured and Windows has no default printer"):
        doctor._printers(Settings(home=tmp_path), tmp_path)

    monkeypatch.setattr(printing, "default_printer", lambda: "Office")
    detail = doctor._printers(Settings(home=tmp_path), tmp_path)
    assert detail == "1 printer(s), default Office, configured system default"


def test_scheduler_probe_flags_enabled_but_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduling, "describe", lambda key: ScheduleInfo("task-scheduler", False, None, None))
    s = Settings(home=tmp_path)
    s.reports["open-work"] = ReportConfig(enabled=True)
    with pytest.raises(RuntimeError, match="scheduled printing is on in config.toml but no task is installed"):
        doctor._scheduler(s, tmp_path)


def test_scheduler_probe_reports_last_result_when_scheduled(monkeypatch, tmp_path):
    monkeypatch.setattr(scheduling, "describe", lambda key: ScheduleInfo("task-scheduler", True, "2026-09-15 14:00", "printed"))
    detail = doctor._scheduler(Settings(home=tmp_path), tmp_path)
    assert detail == "task-scheduler: next run 2026-09-15 14:00; last result printed"


def test_credential_probe_round_trips_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    store: dict = {}

    class _Backend:
        pass

    fake_keyring = types.SimpleNamespace(
        get_keyring=lambda: _Backend(),
        set_password=lambda svc, user, pw: store.__setitem__((svc, user), pw),
        get_password=lambda svc, user: store.get((svc, user)),
        delete_password=lambda svc, user: store.pop((svc, user), None),
    )
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    detail = doctor._credential_store(Settings(home=tmp_path), tmp_path)
    assert detail == "keyring backend _Backend: round trip OK"
    assert (host.SERVICE, "doctor-probe") not in store          # the throwaway entry was removed


def test_credential_probe_raises_and_still_cleans_up_on_mismatch(monkeypatch, tmp_path):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    store: dict = {}
    fake_keyring = types.SimpleNamespace(
        get_keyring=lambda: object(),
        set_password=lambda svc, user, pw: store.__setitem__((svc, user), pw),
        get_password=lambda svc, user: "wrong-value",
        delete_password=lambda svc, user: store.pop((svc, user), None),
    )
    monkeypatch.setitem(sys.modules, "keyring", fake_keyring)
    with pytest.raises(RuntimeError, match="did not round-trip"):
        doctor._credential_store(Settings(home=tmp_path), tmp_path)
    assert (host.SERVICE, "doctor-probe") not in store           # cleaned up even though it failed


def test_web_server_probe(monkeypatch, tmp_path):
    from lakota_grades.host import ServiceInfo
    s = Settings(home=tmp_path)
    monkeypatch.setattr(doctor, "_describe_service", lambda: ServiceInfo("systemd", False, False, "not installed"))
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: False)
    assert "not running" in doctor._web_server(s, tmp_path) and "lakota-grades web" in doctor._web_server(s, tmp_path)
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: True)
    assert "http://127.0.0.1:8433/" in doctor._web_server(s, tmp_path)
    monkeypatch.setattr(doctor, "_describe_service", lambda: ServiceInfo("systemd", True, True, "enabled, active"))
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: False)
    with pytest.raises(RuntimeError) as e:
        doctor._web_server(s, tmp_path)
    assert "installed" in str(e.value) and "does not answer" in str(e.value)
    def broken():
        raise OSError("no systemctl")
    monkeypatch.setattr(doctor, "_describe_service", broken)
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: True)
    assert "service state unknown" in doctor._web_server(s, tmp_path)

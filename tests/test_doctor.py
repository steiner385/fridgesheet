"""The self-check: every probe is isolated, a raising probe is a FAIL line, the report is
written to <home>/doctor.txt, and the CLI exit code follows the verdict."""
from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from fridgesheet import cli, config, doctor, host
from fridgesheet.config import Settings
from fridgesheet.host import printing
from fridgesheet.web import clock


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
    assert names == ["python", "home", "database", "timezone", "no-print days", "pdf", "chromium", "credential store", "printers", "print engine", "scheduler", "web server", "old names"]
    assert all(isinstance(c.detail, str) and c.detail for c in out)
    by = {c.name: c for c in out}
    assert by["python"].ok and by["home"].ok and by["database"].ok and by["timezone"].ok and by["pdf"].ok
    if not by["chromium"].ok:
        pytest.skip(f"no Playwright browser here: {by['chromium'].detail}")
    assert by["chromium"].ok and by["chromium"].detail.startswith("Chromium ")


def test_database_probe_reports_counts(tmp_path):
    from fridgesheet.web import db
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('t', '{}', 1)")
    conn.close()
    out = {c.name: c for c in doctor.checks(Settings(home=tmp_path), tmp_path, probes=[p for p in doctor.PROBES if p[0] == "database"])}
    # The probe reports whatever version `migrate` brought the file to, so the assertion follows
    # `db.SCHEMA_VERSION` rather than pinning a number a later migration would silently outdate.
    assert out["database"].ok and f"schema {db.SCHEMA_VERSION}" in out["database"].detail and "1 refreshes" in out["database"].detail


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
    # Not "Windows": this probe runs on Linux too (#150), where CUPS is what has no default.
    with pytest.raises(RuntimeError, match="no printer is configured and this computer has no default printer"):
        doctor._printers(Settings(home=tmp_path), tmp_path)

    monkeypatch.setattr(printing, "default_printer", lambda: "Office")
    detail = doctor._printers(Settings(home=tmp_path), tmp_path)
    assert detail == "1 printer(s), default Office, configured system default"


def _sched_settings(tmp_path, doc):
    config.save_config_doc(tmp_path / "config.toml", doc)
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(doc, s)
    return s


def test_scheduler_with_nothing_on(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "_current", None)
    assert doctor._scheduler(_sched_settings(tmp_path, {}), tmp_path) == "no schedules are on"


def test_scheduler_from_a_terminal_names_the_next_run(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "_current", None)
    s = _sched_settings(tmp_path, {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": list(host.DAY_NAMES)}},
                                   "refresh": {"enabled": True}})
    out = doctor._scheduler(s, tmp_path)
    assert "2 on; next: " in out and "only while the web server is running" in out


def test_scheduler_fails_when_the_clock_has_stopped(tmp_path, monkeypatch):
    stopped = SimpleNamespace(stale=lambda now: True)
    monkeypatch.setattr(clock, "_current", stopped)
    s = _sched_settings(tmp_path, {"reports": {"open-work": {"enabled": True, "time": "14:00", "days": ["Fri"]}},
                                   "refresh": {"enabled": True}})
    with pytest.raises(RuntimeError, match="paused"):
        doctor._scheduler(s, tmp_path)


def test_scheduler_fails_on_a_schedule_that_cannot_run(tmp_path, monkeypatch):
    monkeypatch.setattr(clock, "_current", None)
    s = _sched_settings(tmp_path, {"refresh": {"enabled": True, "every_hours": 1, "start": "06:00", "end": "21:00"}})
    with pytest.raises(RuntimeError, match="refreshes a day"):
        doctor._scheduler(s, tmp_path)


def test_scheduler_probe_fails_when_a_report_is_scheduled_and_the_refresh_is_off(monkeypatch, tmp_path):
    """#120: a scheduled report runs with no refresh of its own and refuses a snapshot older
    than a day, so with the refresh off it prints once and then fails every day. Report-on-
    refresh-off is the broken state, whichever report it is; refresh-off with nothing
    scheduled is fine."""
    monkeypatch.setattr(clock, "_current", None)
    assert doctor._scheduler(_sched_settings(tmp_path, {}), tmp_path) == "no schedules are on"
    on = {"enabled": True, "time": "14:00", "days": list(host.DAY_NAMES)}
    s = _sched_settings(tmp_path, {"reports": {"open-work": on}})
    with pytest.raises(RuntimeError, match=r"open-work is scheduled but the data refresh is off"):
        doctor._scheduler(s, tmp_path)
    s = _sched_settings(tmp_path, {"reports": {"open-work": {**on, "enabled": False}}, "refresh": {"enabled": False}})
    assert doctor._scheduler(s, tmp_path) == "no schedules are on"
    s = _sched_settings(tmp_path, {"reports": {"open-work": on}, "refresh": {"enabled": True}})
    assert "2 on" in doctor._scheduler(s, tmp_path)


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
    from fridgesheet.host import ServiceInfo
    s = Settings(home=tmp_path)
    monkeypatch.setattr(doctor, "_describe_service", lambda: ServiceInfo("systemd", False, False, "not installed"))
    monkeypatch.setattr(doctor, "_port_answers", lambda host, port: False)
    assert "not running" in doctor._web_server(s, tmp_path) and "fridgesheet web" in doctor._web_server(s, tmp_path)
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


def test_timezone_probe_names_the_computers_clock_when_it_is_another_zone(monkeypatch, tmp_path):
    """On Windows a task fires on the PC's clock (#122): a household zone that is not the PC's
    is worth a word here, since the Schedules page shows next runs in the PC's time."""
    assert doctor._timezone(Settings(timezone="America/New_York"), tmp_path) == "America/New_York"
    monkeypatch.setattr(host, "local_timezone", lambda: "America/Los_Angeles")
    assert doctor._timezone(Settings(timezone="America/Chicago"), tmp_path) == \
        "America/Chicago (this computer's clock is America/Los_Angeles)"
    with pytest.raises(Exception):
        doctor._timezone(Settings(timezone="Eastern"), tmp_path)


def test_no_print_days_probe_reports_the_lines_it_cannot_read(tmp_path):
    """#147: `parse_skip_days` leaves out a reversed range or an impossible date. A hand-edited
    file is exactly the one nobody re-reads, so the doctor names each line it had to drop."""
    probe = [("no-print days", doctor._no_print_days)]
    s = Settings(home=tmp_path)
    first = doctor.checks(s, tmp_path, probes=probe)[0]
    assert first.ok and "not created yet" in first.detail
    (tmp_path / "no-print-days.txt").write_text(
        "2026-09-07 Labor Day\n2026-12-21..2026-12-01 Break\n2026-02-30\n", encoding="utf-8")
    c = doctor.checks(s, tmp_path, probes=probe)[0]
    assert not c.ok and "line 2" in c.detail and "line 3" in c.detail and "2026-02-30" in c.detail
    (tmp_path / "no-print-days.txt").write_text("2026-09-07 Labor Day\n2026-12-21..2026-12-23 Break\n", encoding="utf-8")
    c = doctor.checks(s, tmp_path, probes=probe)[0]
    assert c.ok and c.detail == "2 entries covering 4 days"

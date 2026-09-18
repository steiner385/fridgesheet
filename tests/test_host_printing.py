"""Printing adapters. Only command lines are asserted; nothing is printed."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from fridgesheet.host import printing, printing_linux, printing_windows


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _recorder(result=_R()):
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return result
    return seen, run


def test_linux_lists_and_defaults_from_lpstat():
    seen, run = _recorder(_R(0, "Brother_MFC accepting requests since Mon\nCanon_LBP accepting requests since Tue\n"))
    assert printing_linux.list_printers(run=run) == ["Brother_MFC", "Canon_LBP"]
    assert seen[0][0] == ["lpstat", "-a"]
    assert printing_linux.default_printer(run=lambda c, **k: _R(0, "system default destination: Canon_LBP\n")) == "Canon_LBP"
    assert printing_linux.default_printer(run=lambda c, **k: _R(0, "no system default destination\n")) is None
    assert printing_linux.list_printers(run=lambda c, **k: (_ for _ in ()).throw(FileNotFoundError())) == []


def test_linux_print_builds_lp_command_and_returns_the_request_id():
    seen, run = _recorder(_R(0, "request id is Brother_MFC-42 (1 file(s))\n"))
    job = printing_linux.print_pdf(Path("/tmp/s.pdf"), "Brother_MFC", "fridgesheet open work 2026-09-14", run=run)
    assert job == "Brother_MFC-42"
    cmd = seen[0][0]
    assert cmd[:3] == ["lp", "-d", "Brother_MFC"]
    assert "sides=two-sided-long-edge" in cmd and "media=Letter" in cmd and cmd[-1] == "/tmp/s.pdf"
    assert cmd[cmd.index("-t") + 1] == "fridgesheet open work 2026-09-14"


def test_linux_print_default_printer_omits_dash_d_and_failure_raises():
    seen, run = _recorder(_R(0, "request id is Canon-7 (1 file(s))\n"))
    printing_linux.print_pdf(Path("/tmp/s.pdf"), None, "t", run=run)
    assert "-d" not in seen[0][0]
    with pytest.raises(printing.PrintError) as e:
        printing_linux.print_pdf(Path("/tmp/s.pdf"), "X", "t", run=lambda c, **k: _R(1, "", "lp: The printer or class does not exist."))
    assert "does not exist" in str(e.value)


def test_linux_print_timeout_is_a_print_error():
    import subprocess as sp

    def slow(cmd, **kw):
        assert kw["timeout"] == 120
        raise sp.TimeoutExpired(cmd, kw["timeout"])

    with pytest.raises(printing.PrintError, match="120 s"):
        printing_linux.print_pdf(Path("/tmp/s.pdf"), "X", "t", run=slow)


@pytest.fixture
def win(monkeypatch, tmp_path):
    exe = tmp_path / "SumatraPDF.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(printing_windows, "sumatra_path", lambda: exe)
    monkeypatch.setattr(printing_windows, "list_printers", lambda run=None: ["Brother MFC-J4335DW", "Microsoft Print to PDF"])
    monkeypatch.setattr(printing_windows, "default_printer", lambda run=None: "Microsoft Print to PDF")
    return exe


def test_windows_print_runs_sumatra_silently_with_duplex(win):
    seen, run = _recorder(_R(0))
    at = datetime(2026, 9, 14, 14, 2)
    job = printing_windows.print_pdf(Path(r"C:\s\sheet.pdf"), "Brother MFC-J4335DW", "t", run=run, now=at)
    cmd, kw = seen[0]
    assert cmd == [str(win), "-print-to", "Brother MFC-J4335DW", "-print-settings", "duplexlong,paper=letter",
                   "-silent", "-exit-when-done", r"C:\s\sheet.pdf"]
    assert kw["creationflags"] == printing_windows.CREATE_NO_WINDOW
    assert job == "Brother MFC-J4335DW @ 14:02"


def test_windows_default_printer_and_errors(win):
    seen, run = _recorder(_R(0))
    job = printing_windows.print_pdf(Path("s.pdf"), None, "t", run=run, now=datetime(2026, 9, 14, 14, 2))
    assert "-print-to-default" in seen[0][0] and job == "Microsoft Print to PDF @ 14:02"
    with pytest.raises(printing.PrintError, match="not installed"):
        printing_windows.print_pdf(Path("s.pdf"), "Gone", "t", run=run)
    with pytest.raises(printing.PrintError, match="exit 1"):
        printing_windows.print_pdf(Path("s.pdf"), None, "t", run=lambda c, **k: _R(1))
    win.unlink()
    with pytest.raises(printing.PrintError, match="SumatraPDF"):
        printing_windows.print_pdf(Path("s.pdf"), None, "t", run=run)


def test_windows_print_timeout_is_a_print_error(win):
    import subprocess as sp

    def slow(cmd, **kw):
        raise sp.TimeoutExpired(cmd, kw["timeout"])

    with pytest.raises(printing.PrintError, match="300 s"):
        printing_windows.print_pdf(Path("s.pdf"), None, "t", run=slow)


def test_selector_exposes_the_same_names():
    for name in ("list_printers", "default_printer", "print_pdf", "PrintError"):
        assert hasattr(printing, name)


def test_printerror_is_the_shared_host_exception():
    import fridgesheet.host as host
    assert printing.PrintError is host.PrintError


def test_windows_list_printers_without_pywin32_is_a_print_error(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "win32print", None)
    with pytest.raises(printing.PrintError, match="pywin32"):
        printing_windows.list_printers()
    with pytest.raises(printing.PrintError, match="pywin32"):
        printing_windows.default_printer()


def test_printers_command_marks_the_default(monkeypatch, capsys):
    from fridgesheet import cli
    monkeypatch.setattr(printing, "list_printers", lambda: ["A", "B"])
    monkeypatch.setattr(printing, "default_printer", lambda: "B")
    with pytest.raises(SystemExit) as e:
        cli.main(["printers"])
    assert e.value.code == 0
    assert capsys.readouterr().out == "  A\n* B\n"

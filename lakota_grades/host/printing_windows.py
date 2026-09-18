from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import CREATE_NO_WINDOW, PrintError


def sumatra_path() -> Path:
    """LAKOTA_SUMATRA, else SumatraPDF.exe next to the frozen executable (Plan 3 puts it there)."""
    if os.environ.get("LAKOTA_SUMATRA"):
        return Path(os.environ["LAKOTA_SUMATRA"])
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "SumatraPDF.exe"


def _win32print():
    try:
        import win32print
    except ImportError as e:
        raise PrintError("pywin32 is not installed; reinstall Lakota Sheet or `pip install lakota-grades-mcp[windows]`") from e
    return win32print


def list_printers(run=subprocess.run) -> list[str]:
    win32print = _win32print()
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p["pPrinterName"] for p in win32print.EnumPrinters(flags, None, 2)]


def default_printer(run=subprocess.run) -> str | None:
    win32print = _win32print()
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def print_pdf(pdf: Path, printer: str | None, title: str, run=subprocess.run, now: datetime | None = None) -> str:
    exe = sumatra_path()
    if not exe.is_file():
        raise PrintError(f"SumatraPDF not found at {exe}; reinstall Lakota Sheet")
    if printer and printer not in list_printers():
        raise PrintError(f"printer {printer!r} is not installed (renamed or removed?)")
    target = ["-print-to", printer] if printer else ["-print-to-default"]
    cmd = [str(exe), *target, "-print-settings", "duplexlong,paper=letter", "-silent", "-exit-when-done", str(pdf)]
    try:
        r = run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=300)
    except subprocess.TimeoutExpired:
        raise PrintError(f"SumatraPDF did not finish within 300 s; PDF kept at {pdf}")
    if r.returncode != 0:
        raise PrintError(f"SumatraPDF exit {r.returncode}: {((r.stderr or r.stdout) or '').strip()[:200]}")
    name = printer or default_printer() or "default printer"
    return f"{name} @ {(now or datetime.now()):%H:%M}"

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from . import PrintError


def list_printers(run=subprocess.run) -> list[str]:
    try:
        p = run(["lpstat", "-a"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.split()[0] for line in (p.stdout or "").splitlines() if line.strip()]


def default_printer(run=subprocess.run) -> str | None:
    try:
        p = run(["lpstat", "-d"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"system default destination:\s*(\S+)", p.stdout or "")
    return m.group(1) if m else None


def print_pdf(pdf: Path, printer: str | None, title: str, run=subprocess.run, now: datetime | None = None) -> str:
    cmd = ["lp", *(["-d", printer] if printer else []), "-o", "sides=two-sided-long-edge", "-o", "media=Letter", "-t", title, pdf.as_posix()]
    try:
        r = run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        raise PrintError(f"lp did not return within 120 s; PDF kept at {pdf}")
    if r.returncode != 0:
        raise PrintError(f"lp failed ({r.returncode}): {((r.stderr or r.stdout) or '').strip()[:200]}")
    m = re.search(r"request id is (\S+)", r.stdout or "")
    return m.group(1) if m else (r.stdout or "").strip()

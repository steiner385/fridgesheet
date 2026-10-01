"""Diagnostics: the doctor report, on demand."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ... import doctor

router = APIRouter()

_CHECK = re.compile(r"^(OK|FAIL)\s+([^:]+):\s?(.*)$")
_SUMMARY = re.compile(r"^(All checks passed|\d+ check\(s\) failed)$")


def parse_report(text: str) -> tuple[list[dict], int, int]:
    """The doctor's text as lines for the checkup (2026-10-01): one dict per `OK name: detail`
    or `FAIL name: detail` line, a line of any other shape kept as `{"raw": line}` so nothing the
    file says is lost, and the summary line dropped (the day row's tally says it). Returns
    (lines, checks, failed)."""
    lines: list[dict] = []
    for raw in text.splitlines():
        if not raw.strip() or _SUMMARY.match(raw.strip()):
            continue
        m = _CHECK.match(raw)
        if m:
            lines.append({"ok": m.group(1) == "OK", "name": m.group(2).strip(), "detail": m.group(3).strip()})
        else:
            lines.append({"raw": raw})
    checks = [c for c in lines if "ok" in c]
    return lines, len(checks), sum(1 for c in checks if not c["ok"])


@router.get("/diagnostics")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    path = state.home / doctor.REPORT_NAME
    # Written by another process; a stray byte or a file in use must not make this a 500 (#4).
    checked_at = None
    try:
        report = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
        if report is not None:
            checked_at = datetime.fromtimestamp(path.stat().st_mtime, tz=state.tz)
    except OSError as e:
        report = f"The last doctor report could not be read: {e}"
    lines, n_checks, n_failed = parse_report(report) if report else ([], 0, 0)
    # Read only: the verdict was resolved once, at startup (`app.create_app`), and stashed in
    # `state.extra["last_update"]`. Calling `selfupdate.resolve_pending` from here would
    # archive the breadcrumb on a GET -- a page render must not mutate state, and the verdict
    # would then belong to whoever loaded this page first, not to the household.
    verdict = state.extra.get("last_update")
    return render(request, conn, "diagnostics.html", current="diagnostics", report=report, verdict=verdict,
                  lines=lines, n_checks=n_checks, n_failed=n_failed, checked_at=checked_at)

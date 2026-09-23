"""Diagnostics: the doctor report, on demand."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ... import doctor

router = APIRouter()


@router.get("/diagnostics")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    path = state.home / doctor.REPORT_NAME
    report = path.read_text(encoding="utf-8") if path.is_file() else None
    # Read only: the verdict was resolved once, at startup (`app.create_app`), and stashed in
    # `state.extra["last_update"]`. Calling `selfupdate.resolve_pending` from here would
    # archive the breadcrumb on a GET -- a page render must not mutate state, and the verdict
    # would then belong to whoever loaded this page first, not to the household.
    verdict = state.extra.get("last_update")
    return render(request, conn, "diagnostics.html", current="diagnostics", report=report, verdict=verdict)

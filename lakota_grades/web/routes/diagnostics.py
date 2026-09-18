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
    return render(request, conn, "diagnostics.html", current="diagnostics", report=report)

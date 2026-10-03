"""The report card (spec 2026-10-03 §7.1): a kid's classes, one line each, the official
average with the scale's letter and one sentence on how the gradebook arrived at it."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ... import grading
from ..app import Db, State, render, student_or_404
from ..stores import grades

router = APIRouter()


@router.get("/kids/{key}/report-card")
def page(key: str, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    lines = grades.report_card(conn, s, state.sources(), state.settings.grading, state.tz)
    return render(request, conn, "report_card.html", current=f"kid:{key}", workspace="report", student=s, lines=lines,
                  n_lines=len(lines), fmt_avg=grading.fmt_avg)

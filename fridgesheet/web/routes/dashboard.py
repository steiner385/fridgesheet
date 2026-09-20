"""The Dashboard: one card per kid with today's numbers, and what printed today."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render, safe_pdf
from ..stores import items, runs, students

router = APIRouter()


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    days_ahead = state.days_ahead()
    cards = [(s, items.dashboard_counts(conn, s, now=now, rules=rules, days_ahead=days_ahead)) for s in students.visible(conn)]
    return render(request, conn, "dashboard.html", current="dashboard", cards=cards,
                  printed=[(row, runs.describe(row), safe_pdf(state, row["pdf_path"]) is not None)
                           for row in runs.printed_on(conn, now.date())])

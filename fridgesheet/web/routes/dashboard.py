"""The Dashboard: one card per kid with today's numbers, and what printed today."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render, safe_pdf
from ..stores import items, plans, runs, students

router = APIRouter()


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    days_ahead = state.days_ahead()
    today = now.date().isoformat()
    cards = []
    for s in students.visible(conn):
        steps, minutes = plans.today_load(conn, s["id"], today)
        cards.append((s, items.dashboard_counts(conn, s, now=now, rules=rules, days_ahead=days_ahead, prefs=state.sources()),
                      dict(last_check=plans.last_checkin(conn, s["id"]), steps_today=steps, minutes_today=minutes)))
    return render(request, conn, "dashboard.html", current="dashboard", cards=cards, today=today,
                  printed=[(row, runs.describe(row), safe_pdf(state, row["pdf_path"]) is not None)
                           for row in runs.printed_on(conn, now.date())])

"""The Dashboard: one card per kid with today's numbers, and what printed today."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from . import checkin
from ..app import Db, State, render, safe_pdf
from ..stores import items, plans, runs, students

router = APIRouter()


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    today = now.date().isoformat()
    cards = []
    for s in students.visible(conn):
        school_has = checkin.school_has_ids(conn, s, state)
        steps, minutes = plans.today_load(conn, s["id"], today, exclude=school_has)
        work = items.open_work(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window())
        # The headline counts every red row, covered by a family step or not: a step is not
        # done until the school (or the family) says so (spec 2026-09-27 §8.3, review finding 1).
        must = items.must_finish(work, now.date())
        cards.append((s, items.dashboard_counts(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window()),
                      dict(last_check=plans.last_checkin(conn, s["id"]), steps_today=steps, minutes_today=minutes,
                           must_finish=len(must.red))))
    return render(request, conn, "dashboard.html", current="dashboard", cards=cards, today=today,
                  printed=[(row, runs.describe(row), safe_pdf(state, row["pdf_path"]) is not None)
                           for row in runs.printed_on(conn, now.date())])

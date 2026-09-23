"""The Open work page: the printed sheet's two questions, on a screen, per kid.

What is past due and can still be fixed (open, inside its late-work window, not handled),
and what is coming due. The Dashboard has the count and the Kid page has the filter; this
is the list itself, in the order a parent needs it tonight -- soonest-closing window first.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ..stores import items, students

router = APIRouter()


@router.get("/open")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules, days_ahead = state.now(), state.rules(), state.days_ahead()
    groups = [(s, items.open_work(conn, s, now=now, rules=rules, days_ahead=days_ahead, prefs=state.sources())) for s in students.visible(conn)]
    return render(request, conn, "open.html", current="open", groups=groups, days_ahead=days_ahead)

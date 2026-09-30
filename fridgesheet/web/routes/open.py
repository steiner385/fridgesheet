"""The Open work page: the printed sheet's two questions, on a screen, one kid at a time.

What is past due and can still be fixed (open, inside its late-work window, not handled),
and what is coming due. The Dashboard has the count and the Kid page has the filter; this
is the list itself, in the order the sheet prints it -- soonest-closing window first. The
kids are tabs (`?kid=Alex`); every kid's page is in the markup and the tabs hide the others,
so `?kid=all` lays every page out and a full load without script still turns the page.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render
from ..stores import items, students

router = APIRouter()


@router.get("/open")
def page(request: Request, kid: str | None = None, conn: sqlite3.Connection = Db, state=State):
    now, rules, window = state.now(), state.rules(), state.window()
    groups = [(s, items.open_work(conn, s, now=now, rules=rules, prefs=state.sources(), **window)) for s in students.visible(conn)]
    keys = [s["key"] for s, _ in groups]
    # The first kid's sheet by default; a tab or a saved address picks another, or every kid.
    shown = kid if kid == "all" or kid in keys else (keys[0] if keys else "all")
    return render(request, conn, "open.html", current="open", groups=groups, shown=shown, as_of=now, **window)

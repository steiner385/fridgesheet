"""Who is looking (spec 2026-09-27 §13.1): one tap, remembered by the browser, changed by
one tap. Not a login -- the household network is the boundary, as it is everywhere else."""
from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..app import Db, FAMILY, State, remember_who, render, student_or_404
from ..stores import students

router = APIRouter()


@router.get("/who")
def chooser(request: Request, conn: sqlite3.Connection = Db, state=State):
    # The cover is the planner opened to today (the Student Planner, 2026-10-01): the date is a
    # day row over the question, in the household's zone.
    return render(request, conn, "who.html", kids=students.visible(conn), today=state.now().date())


@router.post("/who")
def choose(request: Request, who: str = Form(...), conn: sqlite3.Connection = Db):
    if who != FAMILY:
        student_or_404(conn, who)
    return remember_who(RedirectResponse("/", status_code=303), who)


@router.get("/who/{who}")
def choose_by_link(who: str, conn: sqlite3.Connection = Db):
    """The choice as a link: what the QR code on a kid's page encodes, and the start URL of
    that kid's home-screen app (routes/pwa.py). A GET that sets a cookie is fine here because
    the cookie is not a credential (§13.1): it only says which pages to open first. Straight
    to the plan, not via `/`, so the first launch is one hop."""
    if who == FAMILY:
        return remember_who(RedirectResponse("/", status_code=303), who)
    s = student_or_404(conn, who)
    return remember_who(RedirectResponse(f"/kids/{quote(s['key'], safe='')}/plan", status_code=303), s["key"])

"""Who is looking (spec 2026-09-27 §13.1): one tap, remembered by the browser, changed by
one tap. Not a login -- the household network is the boundary, as it is everywhere else."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from ..app import Db, FAMILY, remember_who, render, student_or_404
from ..stores import students

router = APIRouter()


@router.get("/who")
def chooser(request: Request, conn: sqlite3.Connection = Db):
    return render(request, conn, "who.html", kids=students.visible(conn))


@router.post("/who")
def choose(request: Request, who: str = Form(...), conn: sqlite3.Connection = Db):
    if who != FAMILY:
        student_or_404(conn, who)
    return remember_who(RedirectResponse("/", status_code=303), who)

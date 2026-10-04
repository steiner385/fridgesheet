"""The report card (spec 2026-10-03 §7.1): a kid's classes, one line each, the official
average with the scale's letter and one sentence on how the gradebook arrived at it."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ... import grading
from ..app import Db, State, render, student_or_404
from ..stores import grades, guidance as guidance_store, items, students

router = APIRouter()


@router.get("/kids/{key}/report-card")
def page(key: str, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    lines = grades.report_card(conn, s, state.sources(), state.settings.grading, state.tz)
    # What would move each number (spec 2026-10-04 §7.1): the levers from the kid's open work,
    # judged on the family's official source for the class; sound accounts only say so.
    work = items.open_work(conn, s, now=state.now(), rules=state.rules(), prefs=state.sources(), **state.window())
    levers: dict[int, list] = {}
    for line in lines:
        if line.account is None:
            continue
        course = students.course(conn, line.course_id)
        if course["source"] != line.official_source and course["peer_course_id"]:
            course = students.course(conn, course["peer_course_id"]) or course
        g = guidance_store.for_class(conn, course, line.account, work, state.settings.grading)
        levers[line.course_id] = guidance_store.sentence_for(g)
    return render(request, conn, "report_card.html", current=f"kid:{key}", workspace="report", student=s, lines=lines,
                  n_lines=len(lines), fmt_avg=grading.fmt_avg, levers=levers)

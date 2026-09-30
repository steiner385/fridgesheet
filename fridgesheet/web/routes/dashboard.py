"""The Dashboard: the family's planner week, and one day box per kid with tonight's lines."""
from __future__ import annotations

import sqlite3
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from . import checkin
from ..app import Db, State, WHO_COOKIE, forget_who, render, safe_pdf, who_of
from ..stores import items, plans, runs, students
from ...dates import deadline_date, wd_md

router = APIRouter()

#: How many days the week strip shows, today first.
WEEK_DAYS = 5


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db, state=State):
    who, student = who_of(request, conn)
    if who is None:
        r = RedirectResponse("/who", status_code=303)
        return forget_who(r) if request.cookies.get(WHO_COOKIE) else r
    if student is not None:
        return RedirectResponse(f"/kids/{quote(student['key'], safe='')}/plan", status_code=303)
    now, rules = state.now(), state.rules()
    today = now.date().isoformat()
    days = [now.date() + timedelta(days=i) for i in range(WEEK_DAYS)]
    per_day: list[list[tuple[str, int]]] = [[] for _ in days]
    cards = []
    for s in students.visible(conn):
        school_has = checkin.school_has_ids(conn, s, state)
        steps, minutes = plans.today_load(conn, s["id"], today, exclude=school_has)
        work = items.open_work(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window())
        # The headline counts every red row, covered by a family step or not: a step is not
        # done until the school (or the family) says so (spec 2026-09-27 §8.3, review finding 1).
        # The Plan's own Must finish list leaves out rows an active family step covers (they sit
        # under "Our next steps"), so the card names those (`must_planned`) and the rest of the
        # list (`must_more`, paper, waiting and later): red minus planned plus more is the count
        # a parent then finds on "Must finish" (critique 2026-09-29: "3" became "Must finish 4").
        must = items.must_finish(work, now.date())
        covered = {st["item_id"] for st in plans.for_student(conn, s["id"]) if st["state"] != "done"}
        shown = items.must_finish(work, now.date(), covered)
        # The week strip: this kid's work by the day it has to be finished (the Student Planner,
        # Today; surface brief). The overdue rows that can still be fixed sit under tonight too,
        # named as late beside the count: "Sam 2 late" is not "Sam has 2 due tonight", and the
        # Plan's DUE TONIGHT box must not contradict the strip (re-critique 2026-09-30).
        counts = [0] * WEEK_DAYS
        for v in work.upcoming:
            if v.due is None:
                continue
            offset = (deadline_date(v.due) - now.date()).days
            if 0 <= offset < WEEK_DAYS:
                counts[offset] += 1
        late = len(must.overdue)
        for i, n in enumerate(counts):
            if n or (i == 0 and late):
                per_day[i].append((s["key"], n, late if i == 0 else 0))
        cards.append((s, items.dashboard_counts(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window()),
                      dict(last_check=plans.last_checkin(conn, s["id"]), steps_today=steps, minutes_today=minutes,
                           must_finish=len(must.red), must_planned=len(must.red) - len(shown.red),
                           must_more=len(shown) - len(shown.red)),
                      shown.red))
    week = [dict(label=("Tonight" if i == 0 else "Tomorrow" if i == 1 else ""), date=wd_md(d), counts=per_day[i])
            for i, d in enumerate(days)]
    return render(request, conn, "dashboard.html", current="dashboard", cards=cards, today=today, week=week, here="/",
                  printed=[(row, runs.describe(row), safe_pdf(state, row["pdf_path"]) is not None)
                           for row in runs.printed_on(conn, now.date())])

"""Trends: grade lines per class, weekly missing/late/on-time counts, and what has sat open
longest. The page renders holders; the two JSON endpoints feed uPlot."""
from __future__ import annotations

import sqlite3
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import outcomes
from ..app import Db, State, render, student_or_404
from ..stores import trends

router = APIRouter()

DEFAULT_WEEKS = 8
MAX_WEEKS = 52


def _weeks(request: Request) -> int:
    raw = request.query_params.get("weeks")
    try:
        n = int(raw) if raw else DEFAULT_WEEKS
    except ValueError:
        n = DEFAULT_WEEKS
    return max(1, min(n, MAX_WEEKS))


def _explicit_weeks(request: Request) -> int | None:
    """The clamped `weeks` the request actually asked for, or `None` when it didn't ask at
    all. `_weeks()` always returns a number -- it cannot tell "absent" from "8" -- but
    `grades.json` has a real "unfiltered" state an absent query param must reach: a course
    page with no Weeks selector fetches this URL with no `weeks` at all and means "everything",
    not "the same default window `_weeks()` would guess." A present-but-garbled value (e.g.
    `weeks=nonsense`) still counts as asking, so it falls back to the same default the other
    endpoints use rather than being treated as absent."""
    raw = request.query_params.get("weeks")
    return _weeks(request) if raw else None


def _student(conn, request: Request):
    kid = request.query_params.get("kid") or None
    return student_or_404(conn, kid) if kid else None


def _since(weeks: int, now: datetime) -> datetime:
    """The Monday that starts `trends.weekly_counts`' own `weeks`-wide window, as a datetime
    in `now`'s zone. The grade chart and the weekly chart must start at the same place when
    the "Weeks" filter changes, so this mirrors `weekly_counts`' own floor (the Monday of
    `now`'s week, back `weeks - 1` more weeks) rather than inventing a second definition."""
    monday = now.date() - timedelta(days=now.date().weekday()) - timedelta(weeks=weeks - 1)
    return datetime.combine(monday, time.min, tzinfo=now.tzinfo)


def _record(conn, student, *, now, rules):
    """How the past-due work came out, by `outcomes.classify` -- for one kid, or summed over
    every visible kid. The same tally the Dashboard cards show, so the two pages cannot
    disagree about a number."""
    from ..stores import items, students
    kids = [student] if student else students.visible(conn)
    tallies = [items.dashboard_counts(conn, s, now=now, rules=rules).record for s in kids]
    return outcomes.Tally(**{k: sum(getattr(t, k) for t in tallies) for k in ("on_time", "late", "not_done", "done_offline", "unknown")})


@router.get("/trends")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    sid = student["id"] if student else None
    weeks = _weeks(request)
    now = state.now()
    week_rows = trends.weekly_outcomes(conn, student_id=sid, weeks=weeks, now=now)
    # The grades-chart URL this page renders always embeds `weeks={{ weeks }}` (see
    # trends.html) -- unlike a direct grades.json caller with no Weeks selector (course.html),
    # a fetch that comes from this page never omits `weeks`, so grades.json will always treat
    # it as explicit. Match that here with the same clamped `weeks`, so the caption's course
    # list is never broader than the window the chart it captions will actually show.
    series = trends.grade_series(conn, student_id=sid, since=_since(weeks, now))
    return render(request, conn, "trends.html", current="trends",
                  kid=student["key"] if student else None, weeks=weeks,
                  series=series, course_names=sorted({s.course_short for s in series}),
                  week_rows=week_rows,
                  record=_record(conn, student, now=now, rules=state.rules()),
                  longest=trends.open_days(conn, student_id=sid, now=now))


@router.get("/trends/grades.json")
def grades_json(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    weeks = _explicit_weeks(request)
    since = _since(weeks, state.now()) if weeks is not None else None
    series = trends.grade_series(conn, student_id=student["id"] if student else None, since=since)
    course = request.query_params.get("course")
    if course:
        # A course that is not a number matches no course, so it answers with no series --
        # `?course=abc` must not quietly widen to "every class in the house".
        series = [s for s in series if s.course_id == int(course)] if course.isdigit() else []
    return JSONResponse({"series": [
        {"label": s.label, "points": [[t.timestamp(), v] for t, v in s.points]} for s in series]})


@router.get("/trends/weekly.json")
def weekly_json(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    rows = trends.weekly_outcomes(conn, student_id=student["id"] if student else None,
                                  weeks=_weeks(request), now=state.now())
    return JSONResponse({
        "weeks": [w.week_start.isoformat() for w in rows],
        "on_time": [w.on_time for w in rows], "late": [w.late for w in rows],
        "not_done": [w.not_done for w in rows], "done_offline": [w.done_offline for w in rows],
        "unknown": [w.unknown for w in rows],
    })

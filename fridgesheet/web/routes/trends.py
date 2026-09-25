"""Trends: grade lines per class, weekly missing/late/on-time counts, and what has sat open
longest. The page builds every chart's config itself (`charts.chart_config`) from the same
store results its caption and table read, and inlines it beside the canvas."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ... import dates
from .. import charts, outcomes
from ..app import Db, State, render, student_or_404
from ..stores import trends

router = APIRouter()

DEFAULT_WEEKS = 8
MAX_WEEKS = 52
#: The weekly chart's series, in the table's column order; the labels are the table's headers.
WEEKLY_SERIES = (("on_time", "On time"), ("late", "Late"), ("not_done", "Not done"),
                 ("done_offline", "On paper"), ("unknown", "Unknown"))


def weekly_chart(rows: list[trends.WeekOutcomes], now: datetime) -> charts.ChartData:
    """One bar per week, one segment per outcome -- the table beside it, drawn. Labels are
    the same `md_year` strings the report charts use, built here in the household's zone,
    so the chart cannot drift a day from the "Week of" column (the uPlot chart had to
    rebuild local midnight by hand in the browser to avoid exactly that)."""
    labels = tuple(dates.md_year(w.week_start, now) for w in rows)
    series = [charts.ChartSeries(label=label, color=charts.OUTCOME_COLORS[key],
                                 points=[(l, float(getattr(w, key))) for l, w in zip(labels, rows)])
              for key, label in WEEKLY_SERIES]
    return charts.ChartData(type="stacked_bar", x_label="Week of", y_label=charts.COUNT_LABEL,
                            series=series, labels=labels, title="Work due that week")


def chart_json(data: charts.ChartData) -> str:
    """`chart_config()`'s output, safe to inline inside `_chart_canvas.html`'s script tag."""
    return charts.escape_for_script_tag(json.dumps(charts.chart_config(data)))


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


def _record(conn, student, *, now, rules, prefs=None):
    """How the past-due work came out, by `outcomes.classify` -- for one kid, or summed over
    every visible kid. The same tally the Dashboard cards show, so the two pages cannot
    disagree about a number."""
    from ..stores import items, students
    kids = [student] if student else students.visible(conn)
    tallies = [items.dashboard_counts(conn, s, now=now, rules=rules, prefs=prefs).record for s in kids]
    return outcomes.Tally(**{k: sum(getattr(t, k) for t in tallies) for k in ("on_time", "late", "not_done", "done_offline", "unknown")})


@router.get("/trends")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    sid = student["id"] if student else None
    weeks = _weeks(request)
    now = state.now()
    week_rows = trends.weekly_outcomes(conn, student_id=sid, weeks=weeks, now=now, prefs=state.sources())
    # The grades-chart URL this page renders always embeds `weeks={{ weeks }}` (see
    # trends.html) -- unlike a direct grades.json caller with no Weeks selector (course.html),
    # a fetch that comes from this page never omits `weeks`, so grades.json will always treat
    # it as explicit. Match that here with the same clamped `weeks`, so the caption's course
    # list is never broader than the window the chart it captions will actually show.
    series = trends.grade_series(conn, student_id=sid, since=_since(weeks, now), prefs=state.sources())
    return render(request, conn, "trends.html", current="trends",
                  kid=student["key"] if student else None, weeks=weeks,
                  series=series, course_names=sorted({s.course_short for s in series}),
                  weekly_json=chart_json(weekly_chart(week_rows, now)),
                  week_rows=week_rows,
                  record=_record(conn, student, now=now, rules=state.rules(), prefs=state.sources()),
                  longest=trends.open_days(conn, student_id=sid, now=now, prefs=state.sources()))


@router.get("/trends/grades.json")
def grades_json(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    weeks = _explicit_weeks(request)
    since = _since(weeks, state.now()) if weeks is not None else None
    series = trends.grade_series(conn, student_id=student["id"] if student else None, since=since, prefs=state.sources())
    course = request.query_params.get("course")
    if course:
        # A course that is not a number matches no course, so it answers with no series --
        # `?course=abc` must not quietly widen to "every class in the house".
        series = [s for s in series if s.course_id == int(course)] if course.isdigit() else []
    return JSONResponse({"series": [
        {"label": s.label, "official": s.official, "points": [[t.timestamp(), v] for t, v in s.points]} for s in series]})

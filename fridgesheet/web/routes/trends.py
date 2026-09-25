"""Trends: grade lines per class, weekly missing/late/on-time counts, and what has sat open
longest. The page builds every chart's config itself (`charts.chart_config`) from the same
store results its caption and table read, and inlines it beside the canvas."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, time, timedelta

from fastapi import APIRouter, Request

from ... import dates
from .. import charts, outcomes
from ..app import Db, State, render, student_or_404
from ..stores import students as students_store, trends

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


def grade_chart(series: list[trends.GradeSeries], *, title: str, now: datetime) -> charts.ChartData | None:
    """One stepped line per course and source, each observation at the moment it was seen:
    `grade_observations` only holds rows where something changed, so a line holds its value
    until the next point -- and on to `now`, because the grade *is* still that today. The
    official source (sources.py) is drawn thicker and says so in its label, the words the
    Changes feed uses. None when there is nothing to draw -- the page prints its sentence
    rather than an empty chart."""
    if not series:
        return None
    return charts.ChartData(
        type="line", x_label="Seen", y_label="Grade", x_scale="time", stepped=True, title=title,
        hold_until=int(now.timestamp() * 1000),
        series=[charts.ChartSeries(label=s.label + (" · official" if s.official else ""), emphasis=s.official,
                                   points=[(int(t.timestamp() * 1000), v) for t, v in s.points])
                for s in series])


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
    now, prefs = state.now(), state.sources()
    week_rows = trends.weekly_outcomes(conn, student_id=sid, weeks=weeks, now=now, prefs=prefs)
    # One grade chart per kid, not one for the house (#40 item 12), each over the same
    # clamped `weeks` window, so the caption's course list is never broader than what is drawn.
    since = _since(weeks, now)
    kids = [student] if student else students_store.visible(conn)
    per_kid = [(s["key"], trends.grade_series(conn, student_id=s["id"], since=since, prefs=prefs)) for s in kids]

    def title(key: str) -> str:
        return "Grade per class" if student else f"{state.settings.nicknames.get(key, key)} — grade per class"

    return render(request, conn, "trends.html", current="trends",
                  kid=student["key"] if student else None, weeks=weeks,
                  course_names=sorted({gs.course_short for _, series in per_kid for gs in series}),
                  has_grades=any(series for _, series in per_kid),
                  grade_charts=[(key, chart_json(grade_chart(series, title=title(key), now=now)) if series else None)
                                for key, series in per_kid],
                  weekly_json=chart_json(weekly_chart(week_rows, now)),
                  week_rows=week_rows,
                  record=_record(conn, student, now=now, rules=state.rules(), prefs=prefs),
                  longest=trends.open_days(conn, student_id=sid, now=now, prefs=prefs))

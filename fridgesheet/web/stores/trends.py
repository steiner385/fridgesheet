"""The numbers behind the Trends page.

Three questions a parent actually asks: is this class's grade going up or down, are the
missing and late counts getting better week by week, and what has been sitting open the
longest. All three are reductions of the same change log the Changes feed walks, so nothing
here writes or caches -- at three kids and a school year it is a few thousand rows.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ... import sources
from ...open_items import HANDLED_FLAGS
from .. import db as _db, outcomes, reconcile
from . import students as _students

MAX_OPEN_DAYS_ROWS = 10


@dataclass
class GradeSeries:
    course_id: int
    course_short: str
    source: str                       # canvas | hac
    label: str
    points: list[tuple[datetime, float]] = field(default_factory=list)


@dataclass(frozen=True)
class WeekCounts:
    week_start: date
    missing: int = 0
    late: int = 0
    on_time: int = 0
    posted: int = 0


@dataclass(frozen=True)
class WeekOutcomes:
    """How the work *due* in one week came out, by `outcomes.classify`. Bucketed by due date,
    not by when a refresh happened to notice -- so a first-day install shows the year so far,
    not seven empty weeks and one with everything in it (#40 item 5)."""
    week_start: date
    on_time: int = 0
    late: int = 0
    not_done: int = 0
    done_offline: int = 0
    unknown: int = 0


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def grade_series(conn: sqlite3.Connection, *, student_id: int | None = None,
                 since: datetime | None = None) -> list[GradeSeries]:
    """One line per course per source: HAC's marking-period average and Canvas' current score.

    `grade_observations` only holds rows where something changed, so each point is a real
    move; a flat stretch is simply the absence of points between two of them.
    """
    sql = """SELECT g.*, r.started_at AS at, c.short_name AS course_short
             FROM grade_observations g JOIN refreshes r ON r.id = g.refresh_id
             JOIN courses c ON c.id = g.course_id JOIN students s ON s.id = c.student_id
             WHERE s.hidden = 0 AND c.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND c.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY g.course_id, g.refresh_id"
    out: dict[tuple[int, str], GradeSeries] = {}
    for r in conn.execute(sql, args):
        at = _dt(r["at"])
        if at is None:
            continue
        if since is not None:
            a, b = reconcile.comparable(at, since)
            if a < b:
                continue
        for column, source, word in (("average", "hac", "HAC average"), ("current", "canvas", "Canvas current")):
            value = r[column]
            if value is None:
                continue
            key = (r["course_id"], source)
            s = out.get(key)
            if s is None:
                s = out[key] = GradeSeries(r["course_id"], r["course_short"], source,
                                           f"{r['course_short']} ({word})")
            s.points.append((at, float(value)))
    return [s for s in out.values() if s.points]


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_counts(conn: sqlite3.Connection, *, student_id: int | None = None, weeks: int = 8,
                  now: datetime) -> list[WeekCounts]:
    """Per week: how many items turned missing, how many were handed in late, how many were
    handed in on time, and how many grades were posted. Oldest first, one row per week even
    when nothing happened, so a chart has an even x axis.

    `weeks` below 1 is treated as 1: a caller asking for no weeks wants this week, not an
    `IndexError`. Only the route clamps, and stores are called directly too."""
    weeks = max(1, weeks)
    starts = [_monday(now.date()) - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    buckets = {s: {"missing": 0, "late": 0, "on_time": 0, "posted": 0} for s in starts}
    floor = starts[0]
    sql = """SELECT o.*, r.started_at AS at, i.student_id AS student_id
             FROM item_observations o JOIN refreshes r ON r.id = o.refresh_id
             JOIN items i ON i.id = o.item_id JOIN students s ON s.id = i.student_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY o.item_id, o.source, o.refresh_id"
    prev: dict[tuple[int, str], sqlite3.Row] = {}
    for row in conn.execute(sql, args):
        key = (row["item_id"], row["source"])
        before = prev.get(key)
        prev[key] = row
        at = _dt(row["at"])
        if at is None:
            continue
        week = _monday(at.date())
        if week < floor or week not in buckets:
            continue
        b = buckets[week]
        if before is None:
            if row["missing"]:
                b["missing"] += 1
            if row["score"] is not None:
                b["posted"] += 1
            if row["submitted_at"]:
                b["late" if row["late"] else "on_time"] += 1
            continue
        if not before["missing"] and row["missing"]:
            b["missing"] += 1
        if before["score"] is None and row["score"] is not None:
            b["posted"] += 1
        if not before["submitted_at"] and row["submitted_at"]:
            b["late" if row["late"] else "on_time"] += 1
    return [WeekCounts(s, **buckets[s]) for s in starts]


def weekly_outcomes(conn: sqlite3.Connection, *, student_id: int | None = None, weeks: int = 8,
                    now: datetime, prefs=None) -> list[WeekOutcomes]:
    """Per week of *due date*: how the work that was due then came out. Oldest first, one
    row per week even when nothing was due, so a chart has an even x axis.

    `weekly_counts` above answers a different question -- what the gradebooks *did* each
    week (grades posted, items turning missing) -- and the Changes feed is held to it. This
    answers the one the Trends page's title asks. Only settled outcomes (`outcomes.PAST_DUE`)
    are counted, from `reconcile.live_items`, the same candidate set as the Kid page and the
    Dashboard record line, so the three cannot disagree about a number."""
    weeks = max(1, weeks)
    starts = [_monday(now.date()) - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    buckets = {s: {k: 0 for k in outcomes.PAST_DUE} for s in starts}
    ids = [s["id"] for s in _students.visible(conn)]
    if student_id is not None:
        ids = [i for i in ids if i == student_id]
    for sid in ids:
        latest = _db.latest_observations(conn, sid)
        for item in reconcile.live_items(conn, sid, now):
            due = reconcile.due_of(item)
            if due is None:
                continue
            week = _monday(due.date())
            if week not in buckets:
                continue
            outcome = outcomes.classify(item, latest.get(item["id"], {}), now,
                                        prefer=sources.assignments_for(prefs, item["kid"], item["course_name"]))
            if outcome in buckets[week]:
                buckets[week][outcome] += 1
    return [WeekOutcomes(w, **buckets[w]) for w in starts]


def on_time_rate(weeks: list[WeekCounts]) -> float | None:
    """On-time hand-ins as a fraction of all hand-ins, or None when nothing was handed in."""
    handed = sum(w.on_time + w.late for w in weeks)
    return (sum(w.on_time for w in weeks) / handed) if handed else None


def open_days(conn: sqlite3.Connection, *, student_id: int | None = None,
              now: datetime, prefs=None) -> list[tuple[str, float]]:
    """How long each still-open item has been open, longest first: the days since it was
    *due*, for items no source has cleared. Ten rows at most -- this is a chart, not an
    inventory.

    Since it was due, not since the app first saw it. The first cut measured from first
    sighting, which on the day the app is installed makes every row "0.2 days" and hides the
    one fact the card exists to show -- that an item due 8/21 has been sitting there for a
    month (#40 item 5, the second half). An open item with no due date (HAC lists real,
    undated work) falls back to first sighting, the only clock it has.

    The candidate set is `reconcile.live_items`, the same one the Kid and Reconcile pages
    work from, so this card cannot disagree with them about what "open" means. It carries
    both of that function's bounds -- the item is due on or after the school year began (a
    course-copy artifact from last year is not work), and a source still reported it in the
    most recent refresh that saw this student. The second matters most here: a dead item's day
    count only grows, so an item the gradebooks quietly stopped listing would climb to the top
    of a ten-row chart and, by the end of a quarter, fill the card with work nobody can act
    on. `live_items` also carries the active flag, so an item the parent has marked done,
    excused or ignore drops out exactly as it does on the Kid page.

    `live_items` takes one student and does not filter hidden students, so the loop walks the
    visible ones: three or four queries in total, not one per item.
    """
    ids = [s["id"] for s in _students.visible(conn)]
    if student_id is not None:
        ids = [i for i in ids if i == student_id]
    started_at = {r["id"]: r["started_at"] for r in conn.execute("SELECT id, started_at FROM refreshes")}
    out: list[tuple[str, float]] = []
    for sid in ids:
        latest = _db.latest_observations(conn, sid)
        for item in reconcile.live_items(conn, sid, now):
            if item["flag"] in HANDLED_FLAGS:
                continue
            if not reconcile.open_sources(item, latest.get(item["id"], {}), now,
                                          prefer=sources.assignments_for(prefs, item["kid"], item["course_name"])):
                continue
            since = reconcile.due_of(item) or _dt(started_at.get(item["first_seen"]))
            if since is None:
                continue
            a, b = reconcile.comparable(now, since)
            out.append((item["name"], max(0.0, round((a - b).total_seconds() / 86400, 1))))
    out.sort(key=lambda p: p[1], reverse=True)
    return out[:MAX_OPEN_DAYS_ROWS]

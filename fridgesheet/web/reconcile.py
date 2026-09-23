# fridgesheet/web/reconcile.py
"""What is open and actionable, over database rows.

Pure functions. An item is actionable when (1) at least one source still considers it open,
(2) the late-work rules say it still earns credit, and (3) no handled flag (done / excused /
ignore) is set. What the sources cannot settle by themselves, and whether the family has
anything to do about it, is `web/verdicts.py`'s question; this module used to answer it with
six "case" kinds for the Reconcile page, which Questions replaced.

Both entry points look only at items that are still live: reported by a source in the most
recent refresh that saw this student, and due on or after the school year began (see
`live_items`). The `items` table keeps everything it has ever seen so the change log has a
history; a page that asks a parent to decide something must not.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from .. import sources
from ..open_items import HANDLED_FLAGS, school_year_start
from . import db

def _due(item: sqlite3.Row) -> datetime | None:
    return datetime.fromisoformat(item["due"]) if item["due"] else None


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _comparable(a: datetime, b: datetime) -> tuple[datetime, datetime]:
    """Two timestamps that can be ordered, even when one carries a UTC offset and the other
    doesn't (a real hazard: refreshes.started_at and flags.set_at aren't guaranteed to share
    a layout). When both carry offsets, comparing the datetimes honours them, which string
    comparison does not reliably do. When only one does, this drops it and compares the wall
    clocks: that avoids the TypeError, and is right whenever the naive one was written in the
    same zone, which is how this app writes them. It is not a general fix for mixed zones."""
    if (a.tzinfo is None) != (b.tzinfo is None):
        return a.replace(tzinfo=None), b.replace(tzinfo=None)
    return a, b


due_of = _due
comparable = _comparable


def open_sources(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime, prefer: str = "canvas") -> set[str]:
    """Which sources consider the item open -- something the kid, or the parent, can still act
    on. Empty means settled.

    Defined by `outcomes.classify`, the same word every count uses (docs/outcomes.md): open is
    *not done* or *unknown*, plus *late* until it is graded -- handed in after the deadline
    and still unmarked is worth watching. This used to be its own rule, older than the
    outcome definition, and it called past-due paper work open whenever Canvas showed no
    submission -- which Canvas does forever for paper -- even when HAC had already graded it.
    "Concert Contract Due" sat on *Open the longest* for 27 days at 10/10, and the sheet would
    have printed PAPER — CHECK for it. Done on paper is done.

    The set names the sources that have not settled it: Canvas whenever it lists the item,
    HAC when it lists the item without a grade a day past due."""
    from . import outcomes                      # outcomes imports this module's helpers
    outcome = outcomes.classify(item, obs, now, prefer=prefer)
    c, h = obs.get("canvas"), obs.get("hac")
    # "Still ungraded" asks the family's assignments source first: under a HAC preference a
    # HAC grade settles a late hand-in, as it does in the Grade cell and on the printed sheet.
    graded = (h is not None and h["score"] is not None) if prefer == "hac" else False
    late_ungraded = outcome == outcomes.LATE and c is not None and c["score"] is None and not graded
    if outcome not in (outcomes.NOT_DONE, outcomes.UNKNOWN) and not late_ungraded:
        return set()
    out: set[str] = set()
    if c is not None:
        out.add("canvas")
    due = _due(item)
    if h is not None and h["score"] is None and due is not None and due < now - timedelta(days=1):
        out.add("hac")
    return out or ({"hac"} if h is not None else set())


def upcoming(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime, days_ahead: int = 14) -> bool:
    """Not open yet, but due within `days_ahead` days and still unsubmitted in Canvas: the
    sheet's DUE TODAY / DUE TOMORROW / DUE <weekday> rows."""
    due = _due(item)
    c = obs.get("canvas")
    if c is None or due is None or c["excused"] or c["published"] == 0:
        return False
    a, b = _comparable(due, now)
    if a <= b or a > b + timedelta(days=days_ahead):
        return False
    return c["state"] in ("unsubmitted", None) and c["score"] is None


def is_actionable(item: sqlite3.Row, obs: dict[str, sqlite3.Row], flag: str | None, rules, kid: str, now: datetime,
                  prefer: str = "canvas") -> bool:
    if flag in HANDLED_FLAGS or not open_sources(item, obs, now, prefer=prefer):
        return False
    due = _due(item)
    return due is None or now <= rules.deadline(kid, item["course_name"], due)


def live_items(conn: sqlite3.Connection, student_id: int, now: datetime) -> list[sqlite3.Row]:
    """The student's items that are still worth a parent's attention.

    `items` keeps every row it has ever seen, which is what makes the change log a history,
    but a reconciliation case has to be about something live. Two bounds: the item was still
    reported by a source in the most recent refresh that saw this student (an item the
    gradebooks have dropped raises no case), and it is due on or after the school year began
    (course-copy artifacts from last year are not work). An item with no due date passes the
    year floor -- HAC lists real, undated work.
    """
    rows = conn.execute(
        """SELECT i.*, c.name AS course_name, c.short_name AS course_short, c.source AS course_source, c.peer_course_id, c.external_id AS course_external_id,
                  pc.name AS peer_course_name, s.key AS kid,
                  COALESCE(c.teacher_email, pc.teacher_email) AS teacher_email,
                  COALESCE(c.teacher, pc.teacher) AS teacher, f.flag AS flag, f.set_at AS flag_set_at
           FROM items i JOIN courses c ON c.id = i.course_id JOIN students s ON s.id = i.student_id
           LEFT JOIN courses pc ON pc.id = c.peer_course_id
           LEFT JOIN flags f ON f.item_id = i.id AND f.cleared_at IS NULL
           WHERE i.student_id = ?
             AND i.last_seen = (SELECT MAX(last_seen) FROM items WHERE student_id = ?)""",
        (student_id, student_id)).fetchall()
    floor = school_year_start(now)
    return [r for r in rows if _on_or_after(_due(r), floor)]


def _on_or_after(due: datetime | None, floor: datetime) -> bool:
    if due is None:
        return True
    a, b = _comparable(due, floor)
    return a >= b


def actionable_items(conn: sqlite3.Connection, student_id: int, *, rules, now: datetime, prefs=None) -> list[sqlite3.Row]:
    latest = db.latest_observations(conn, student_id)
    out = [r for r in live_items(conn, student_id, now)
           if is_actionable(r, latest.get(r["id"], {}), r["flag"], rules, r["kid"], now,
                            prefer=sources.assignments_for(prefs, r["kid"], r["course_name"], r["peer_course_name"]))]
    return sorted(out, key=lambda r: (r["due"] or "", r["course_short"], r["name"]))

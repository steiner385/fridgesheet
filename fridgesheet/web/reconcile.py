# fridgesheet/web/reconcile.py
"""What is actionable, and what the sources cannot settle by themselves.

Pure functions over database rows. An item is actionable when (1) at least one source
still considers it open, (2) the late-work rules say it still earns credit, and (3) no
handled flag (done / excused / ignore) is set. The six case kinds are the situations the
Reconcile page shows a parent, each with a one-line reason and the flag menu.

Both entry points look only at items that are still live: reported by a source in the most
recent refresh that saw this student, and due on or after the school year began (see
`live_items`). The `items` table keeps everything it has ever seen so the change log has a
history; a page that asks a parent to decide something must not.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .. import sources
from ..open_items import HANDLED_FLAGS, MARKED_FLAGS, school_year_start
from . import db

KINDS = ("disagree", "one_source", "submitted_ungraded", "paper_no_grade", "past_credit", "stale_flag")


@dataclass(frozen=True)
class Case:
    kind: str
    item_id: int
    key: str
    course: str
    name: str
    due: datetime | None
    reason: str


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


def _score_text(o: sqlite3.Row | None) -> str:
    if o is None or o["score"] is None:
        return "no grade"
    return f"{o['score']:g}"


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

    The set names the sources that have not settled it, for the Reconcile page's "only one
    source" reasoning: Canvas whenever it lists the item, HAC when it lists the item without
    a grade a day past due."""
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
        """SELECT i.*, c.name AS course_name, c.short_name AS course_short, c.source AS course_source, c.peer_course_id,
                  pc.name AS peer_course_name, s.key AS kid,
                  COALESCE(c.teacher_email, pc.teacher_email) AS teacher_email, f.flag AS flag, f.set_at AS flag_set_at
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


def _refresh_times(conn: sqlite3.Connection) -> dict[int, str]:
    return {r["id"]: r["started_at"] for r in conn.execute("SELECT id, started_at FROM refreshes")}


def cases(conn: sqlite3.Connection, student_id: int, *, rules, now: datetime, prefs=None) -> list[Case]:
    """The six reconciliation cases below, one `Case` per reason found. A single item can
    carry more than one at once -- a `Case` is one reason, not a verdict -- so callers (the
    Plan B reconcile page) group the results by `item_id` to show a parent everything at once."""
    latest = db.latest_observations(conn, student_id)
    refresh_times = _refresh_times(conn)
    found: list[Case] = []
    for r in live_items(conn, student_id, now):
        obs = latest.get(r["id"], {})
        c, h = obs.get("canvas"), obs.get("hac")
        due = _due(r)
        past = due is not None and due < now
        opened = open_sources(r, obs, now, prefer=sources.assignments_for(prefs, r["kid"], r["course_name"], r["peer_course_name"]))
        flag = r["flag"]

        def add(kind: str, reason: str) -> None:
            found.append(Case(kind, r["id"], r["key"], r["course_short"], r["name"], due, reason))

        # 1. the sources disagree about whether the work is done
        if c is not None and h is not None:
            if (c["missing"] or (c["state"] == "graded" and c["score"] == 0)) and h["score"] not in (None, 0):
                add("disagree", f"Canvas says {'MISSING' if c['missing'] else 'ZERO'}, HAC shows {_score_text(h)}")
            elif h["score"] is None and c["state"] == "graded" and c["score"] not in (None, 0):
                add("disagree", f"HAC has no grade, Canvas shows {_score_text(c)}")
        # 2. only one source knows about the item at all
        if r["key"].startswith("hac:") and "hac" in opened:
            add("one_source", "Only HAC lists this; probably paper work")
        elif c is not None and h is None and past and r["peer_course_id"] is not None and "canvas" in opened:
            add("one_source", "Not in HAC's gradebook yet")
        # 3. turned in but Canvas hasn't graded it
        if c is not None and c["submitted_at"] and c["score"] is None and past:
            add("submitted_ungraded", "Turned in, not graded yet")
        # 4. paper or in-class work, past due, no grade posted anywhere
        # A HAC score answers the question this case asks, so it never fires once HAC has one.
        if (c is not None and r["kind"] in ("paper", "in class") and past and c["state"] in ("unsubmitted", None)
                and c["score"] is None and (h is None or h["score"] is None)):
            add("paper_no_grade", f"{r['kind'].capitalize()} work with no grade: ask")
        # 5. still open but past the late-work credit window
        if opened and flag not in HANDLED_FLAGS and due is not None:
            deadline = rules.deadline(r["kid"], r["course_name"], due)
            if now > deadline:
                add("past_credit", f"No longer earns credit (window closed {deadline:%a %m/%d}); flag ignore to hide")
        # 6. a flag the sources have since overtaken (an observation newer than the flag contradicts
        # it). Either source counts: for paper and in-class work the teacher fixes HAC, not Canvas.
        if flag and r["flag_set_at"]:
            said = flag.replace("_", " ")

            def newer(o) -> bool:
                started_at = refresh_times.get(o["refresh_id"]) if o is not None else None
                if not started_at:
                    return False
                refreshed, flagged = _comparable(_parse_ts(started_at), _parse_ts(r["flag_set_at"]))
                return refreshed > flagged

            if flag in HANDLED_FLAGS:
                if newer(c) and (c["missing"] or (c["state"] == "graded" and c["score"] == 0)):
                    add("stale_flag", f"Flagged {said} but Canvas now says {'MISSING' if c['missing'] else 'ZERO'}")
                elif newer(h) and h["score"] == 0:
                    add("stale_flag", f"Flagged {said} but HAC now shows a zero")
            elif flag in MARKED_FLAGS:
                if newer(c) and c["score"] is not None:
                    add("stale_flag", f"Flagged {said} but it is graded now ({_score_text(c)})")
                elif newer(h) and h["score"] is not None:
                    add("stale_flag", f"Flagged {said} but HAC has graded it now ({_score_text(h)})")
    return sorted(found, key=lambda x: (x.due or datetime.max.replace(tzinfo=now.tzinfo), x.course, x.name))

"""The Changes feed: what the sources and the parent did since a chosen moment.

`item_observations` and `grade_observations` are a change log -- Plan A's ingest writes a row
only when a source's view differs from the one before -- so two consecutive rows for one item
and source *are* a change, and the feed is a walk over consecutive pairs rather than a diff of
two whole snapshots. `items.first_seen` supplies the "new" events and the `flags` table
supplies the parent's own, which are the ones no gradebook can tell them about.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from ... import sources
from . import num

KINDS = ("new_item", "grade_posted", "grade_changed", "now_missing", "cleared", "flag_set", "flag_cleared", "course_grade")

#: The feed's window buttons: (key, label, days).
WINDOWS = (("1d", "Since yesterday", 1), ("3d", "Last 3 days", 3), ("7d", "Last week", 7), ("30d", "Last month", 30))
DEFAULT_WINDOW = "1d"

LABELS = {
    "new_item": "New", "grade_posted": "Grade posted", "grade_changed": "Grade changed",
    "now_missing": "Now missing", "cleared": "Cleared", "flag_set": "You answered",
    "flag_cleared": "You cleared a flag", "course_grade": "Class average",
}

#: How many events one call renders by default. A household's first refresh produces a
#: `new_item`-shaped event per item -- on the order of a thousand rows, all at one timestamp --
#: and a page that prints all of them is not a feed, it is a database dump.
DEFAULT_LIMIT = 500

#: How a family answer reads in the change log: the family's words, not the stored flag name.
_FLAG_WORDS = {"done": "it's done", "excused": "excused", "ignore": "let it go",
               "follow_up": "follow up", "ask_teacher": "ask the teacher"}


@dataclass(frozen=True)
class Event:
    kind: str
    at: datetime
    student_key: str
    student_id: int
    item_id: int | None = None
    item_name: str | None = None
    course_short: str | None = None
    source: str | None = None
    detail: str = ""
    flag: str | None = None

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, self.kind)


class Feed(list):
    """The events a call kept, newest first, and `total` -- how many matched before the cap.

    A plain `list` subclass so every existing caller (and `== []`) keeps working, with the one
    extra number the page needs to say "showing the newest 500 of 1,204".
    """

    def __init__(self, events=(), total: int | None = None, offset: int = 0):
        super().__init__(events)
        self.total = len(self) if total is None else total
        self.offset = offset                    # how many newer events a page skipped

    @property
    def dropped(self) -> int:
        """How many the cap left out, before and after this page."""
        return max(0, self.total - len(self))

    @property
    def first(self) -> int:
        return self.offset + 1 if self else 0

    @property
    def last(self) -> int:
        return self.offset + len(self)

    @property
    def has_older(self) -> bool:
        return self.last < self.total

    @property
    def has_newer(self) -> bool:
        return self.offset > 0


def window_start(key: str, now: datetime) -> datetime:
    days = next((d for k, _, d in WINDOWS if k == key), None)
    if days is None:
        days = next(d for k, _, d in WINDOWS if k == DEFAULT_WINDOW)
    return now - timedelta(days=days)


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _num(v) -> str:
    return num(v)


def _score_text(score, grade, points) -> str:
    if score is None:
        return str(grade) if grade else "no score"
    return f"{_num(score)}/{_num(points)}" if points else _num(score)


def _item_rows(conn: sqlite3.Connection, student_id: int | None) -> list[sqlite3.Row]:
    """Every item observation in refresh order, with what the row needs to describe itself."""
    sql = """SELECT o.*, r.started_at AS at, i.name AS item_name, i.points AS points, i.student_id AS student_id,
                    s.key AS student_key, c.short_name AS course_short
             FROM item_observations o
             JOIN refreshes r ON r.id = o.refresh_id
             JOIN items i ON i.id = o.item_id
             JOIN students s ON s.id = i.student_id
             JOIN courses c ON c.id = i.course_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY o.item_id, o.source, o.refresh_id"
    return conn.execute(sql, args).fetchall()


def _observation_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    """A grade appearing or changing, an item turning missing, an item ceasing to be open."""
    out: list[Event] = []
    prev: dict[tuple[int, str], sqlite3.Row] = {}
    for row in _item_rows(conn, student_id):
        key = (row["item_id"], row["source"])
        before = prev.get(key)
        prev[key] = row
        at = _dt(row["at"])
        common = dict(at=at, student_key=row["student_key"], student_id=row["student_id"],
                      item_id=row["item_id"], item_name=row["item_name"],
                      course_short=row["course_short"], source=row["source"])
        if before is None:
            # There is nothing to diff against, but the first sighting still *carries* a state,
            # and it is usually the state the parent cares about: HAC routinely lists an
            # assignment already scored, and a one-refresh install would otherwise show nothing
            # but "New" rows while Trends reported grades posted and an on-time rate from these
            # very observations. `trends.weekly_counts` counts the same three, so keep them in
            # step (tests/test_web_stores_agree.py holds the two stores to it).
            if row["score"] is not None:
                out.append(Event("grade_posted", detail=_score_text(row["score"], row["grade"], row["points"]), **common))
            if row["missing"]:
                out.append(Event("now_missing", detail="marked missing", **common))
            if row["submitted_at"]:
                out.append(Event("cleared", detail="submitted", **common))
            if row["excused"]:
                out.append(Event("cleared", detail="excused", **common))
            continue
        had, has = before["score"] is not None, row["score"] is not None
        if not had and has:
            out.append(Event("grade_posted", detail=_score_text(row["score"], row["grade"], row["points"]), **common))
        elif had and has and before["score"] != row["score"]:
            out.append(Event("grade_changed",
                             detail=f"{_score_text(before['score'], before['grade'], row['points'])}"
                                    f" → {_score_text(row['score'], row['grade'], row['points'])}", **common))
        if not before["missing"] and row["missing"]:
            out.append(Event("now_missing", detail="marked missing", **common))
        elif before["missing"] and not row["missing"]:
            out.append(Event("cleared", detail="no longer missing", **common))
        if not before["submitted_at"] and row["submitted_at"]:
            out.append(Event("cleared", detail="submitted", **common))
        if not before["excused"] and row["excused"]:
            out.append(Event("cleared", detail="excused", **common))
    return out


def _new_item_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    """An item the sources had not mentioned before.

    Items first seen in the earliest refresh *that recorded any item* are not "new": there was no before,
    so nothing changed, and a real household's first run would otherwise bury the feed under a
    thousand identically-timestamped rows. The bound is per-database, not per-student -- a kid
    added to an existing install genuinely is news. It is the earliest refresh with items,
    not the earliest refresh: on a real install the first refresh ran before the credentials
    were entered and recorded nothing, so the second one -- the real first look -- reported
    199 items as "New" (#40 item 11). The state those first observations carry
    (`grade_posted`, `now_missing`, `cleared`) still reaches the feed, from
    `_observation_events`, because unlike "new" it says something true.
    """
    sql = """SELECT i.id, i.name, r.started_at AS at, s.key AS student_key, i.student_id AS student_id,
                    c.short_name AS course_short
             FROM items i JOIN refreshes r ON r.id = i.first_seen
             JOIN students s ON s.id = i.student_id JOIN courses c ON c.id = i.course_id
             WHERE s.hidden = 0
               AND i.first_seen <> (SELECT MIN(first_seen) FROM items)"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    return [Event("new_item", _dt(r["at"]), r["student_key"], r["student_id"], item_id=r["id"],
                  item_name=r["name"], course_short=r["course_short"], detail="first seen")
            for r in conn.execute(sql, args)]


def _course_grade_events(conn: sqlite3.Connection, student_id: int | None, prefs=None) -> list[Event]:
    """A class average moving. One event per course per refresh that changed something."""
    sql = """SELECT g.*, r.started_at AS at, c.short_name AS course_short, c.name AS course_name, c.source AS course_source,
                    c.student_id AS student_id, s.key AS student_key, pc.name AS peer_course_name
             FROM grade_observations g JOIN refreshes r ON r.id = g.refresh_id
             JOIN courses c ON c.id = g.course_id JOIN students s ON s.id = c.student_id
             LEFT JOIN courses pc ON pc.id = c.peer_course_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND c.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY g.course_id, g.refresh_id"
    out: list[Event] = []
    prev: dict[int, sqlite3.Row] = {}
    for row in conn.execute(sql, args):
        before = prev.get(row["course_id"])
        prev[row["course_id"]] = row
        if before is None:
            continue
        pick = (prefs or sources.DEFAULT).resolve(row["student_key"], row["course_name"], row["peer_course_name"]).grades
        for field, word, src in (("average", "HAC average", "hac"), ("current", "Canvas current", "canvas")):
            a, b = before[field], row[field]
            if a is not None and b is not None and a != b:
                mark = " · official" if src == pick else ""
                out.append(Event("course_grade", _dt(row["at"]), row["student_key"], row["student_id"],
                                 course_short=row["course_short"], source=row["course_source"],
                                 detail=f"{word} {_num(a)} → {_num(b)}{mark}"))
    return out


def _flag_events(conn: sqlite3.Connection, student_id: int | None) -> list[Event]:
    sql = """SELECT f.*, i.name AS item_name, i.student_id AS student_id, s.key AS student_key,
                    c.short_name AS course_short
             FROM flags f JOIN items i ON i.id = f.item_id
             JOIN students s ON s.id = i.student_id JOIN courses c ON c.id = i.course_id
             WHERE s.hidden = 0"""
    args: list = []
    if student_id is not None:
        sql += " AND i.student_id = ?"
        args.append(student_id)
    out: list[Event] = []
    for r in conn.execute(sql, args):
        common = dict(student_key=r["student_key"], student_id=r["student_id"], item_id=r["item_id"],
                      item_name=r["item_name"], course_short=r["course_short"], flag=r["flag"])
        word = _FLAG_WORDS.get(r["flag"], r["flag"].replace("_", " "))
        out.append(Event("flag_set", _dt(r["set_at"]), detail=f"{word}: {r['text']}" if r["text"] else word, **common))
        if r["cleared_at"]:
            out.append(Event("flag_cleared", _dt(r["cleared_at"]), detail=f"was {word}", **common))
    return out


def since(conn: sqlite3.Connection, *, since: datetime, until: datetime | None = None,
          student_id: int | None = None, kinds: tuple[str, ...] | None = None,
          limit: int | None = DEFAULT_LIMIT, offset: int = 0, prefs=None) -> Feed:
    """Everything that happened in (`since`, `until`], newest first, then by student key,
    item name and kind.

    `kinds` filters to those event kinds; an unknown kind simply matches nothing, so a
    hand-typed query string cannot 500 the page.

    `limit` caps the returned list (`None` means no cap) and `offset` skips that many newer
    events first -- one page of a feed. The `Feed` still reports the full `total`, so a caller
    can say where this page sits in it.
    """
    from .. import reconcile
    events = (_observation_events(conn, student_id) + _new_item_events(conn, student_id)
              + _course_grade_events(conn, student_id, prefs) + _flag_events(conn, student_id))
    if kinds is not None:
        events = [e for e in events if e.kind in kinds]
    kept = []
    for e in events:
        if e.at is None:
            continue
        a, b = reconcile.comparable(e.at, since)
        if a <= b:
            continue
        if until is not None:
            a2, b2 = reconcile.comparable(e.at, until)
            if a2 > b2:
                continue
        kept.append(e)
    # Two passes, because only the time reverses: a single `reverse=True` over the whole tuple
    # would tie-break same-instant events in reverse-alphabetical student and item order.
    # `sort` is stable, so the ascending pass survives inside each timestamp.
    kept.sort(key=lambda e: (e.student_key, e.item_name or "", e.kind))
    kept.sort(key=lambda e: e.at, reverse=True)
    offset = max(0, offset)
    page = kept[offset:] if limit is None else kept[offset:offset + limit]
    return Feed(page, total=len(kept), offset=offset)


def for_item(conn: sqlite3.Connection, student_id: int, item_id: int, *, now: datetime, prefs=None) -> list[Event]:
    """What happened to one assignment, newest first: the same events the Changes page shows,
    over the whole school year, for the item's History on its detail card (#44)."""
    start = now - timedelta(days=400)
    return [e for e in since(conn, since=start, student_id=student_id, limit=None, prefs=prefs) if e.item_id == item_id]

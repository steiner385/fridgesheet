"""The item list behind the Kid page, the Dashboard counts and the Reconcile page.

One pass over a kid's live items (Plan A's `reconcile.live_items`) decorates each row with
what the browser shows: the sources that know it, whether it is open and actionable, its
active flag, a status phrase, the note count and the reconciliation case kinds. Routes
filter and sort these views; they never touch SQL.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ...dates import due_time
from ... import sources
from ...open_items import HANDLED_FLAGS, MARKED_FLAGS
from .. import db, outcomes, reconcile
from . import num

SHOW = ("open", "actionable", "all")
SORTS = ("due", "course", "name", "status")
DIRECTIONS = ("asc", "desc")
FLAGGED = ("any", "marked", "handled", "none")
DAYS_AHEAD = 14


@dataclass
class ItemView:
    id: int
    key: str
    name: str
    course_id: int
    course_short: str
    course_name: str
    kind: str
    points: float | None
    due: datetime | None
    sources: tuple[str, ...]
    open_in: set[str]
    actionable: bool
    upcoming: bool
    flag: str | None
    flag_text: str
    status: str
    canvas: sqlite3.Row | None
    hac: sqlite3.Row | None
    notes: int = 0
    case_kinds: list[str] = field(default_factory=list)
    # `status` above is one word -- the sheet's word -- and it was the whole Status column.
    # It folds three facts into one label: when it is due, whether it was handed in, and
    # whether (and how) it was graded. "Missing", "Zero", "3/5", "Paper, check", "Due Sun" and
    # "HAC, no grade" are answers to three different questions. These are the three facts
    # kept apart, for a table with a column each; `status` stays for the sort, the detail
    # card's "Says" and everything that already reads it.
    due_relative: str = ""          # "today", "tomorrow", "Sun", "3 days ago"
    #: "7:20am", "11:59pm", or "" for a HAC-only row, whose 23:59 this app invented rather
    #: than read (`dates.due_time`). Precomputed here, as `due_relative` is, so the templates
    #: never have to know which source a time came from.
    due_time: str = ""
    handed_in: str = ""             # "Yes", "Late", "No", "Excused", "—" (nothing to hand in online)
    handed_in_at: datetime | None = None
    grade: str = ""                 # "12.5/50", "0/50", "Missing", "Not yet", "Unpublished"
    grade_zero: bool = False        # a real zero, styled as the warning it is
    outcome: str = ""               # `outcomes.classify`: the one word every count and filter agrees on
    # The late-work register's answer for an open row (`late_rules`): the last moment the item
    # can still earn credit, and the credit text the parent wrote next to that rule. What the
    # printed sheet shows as "50% thru Sat 9/26"; None / "" for a row that is not open.
    late_until: datetime | None = None
    credit: str = ""

    @property
    def overdue(self) -> bool:
        return bool(self.open_in)

    @property
    def handled(self) -> bool:
        return self.flag in HANDLED_FLAGS


def _score(o: sqlite3.Row, points) -> str:
    if o["score"] is None:
        return o["grade"] or ""
    return f"{num(o['score'])}/{num(points)}" if points else num(o["score"])


def status_text(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime, prefer: str = "canvas") -> str:
    """The status column, in words a parent reads (the sheet's status words, unshouted)."""
    c, h = obs.get("canvas"), obs.get("hac")
    due = reconcile.due_of(item)
    past = due is not None and reconcile.comparable(due, now)[0] < reconcile.comparable(due, now)[1]
    if prefer == "hac" and h is not None and h["score"] is not None:
        if c is not None and c["excused"]:
            return "Excused"
        if c is not None and c["published"] == 0:
            return "Unpublished"
        return "Zero" if h["score"] == 0 and (item["points"] or 0) > 0 else _score(h, item["points"])
    if c is not None:
        if c["excused"]:
            return "Excused"
        if c["published"] == 0:
            return "Unpublished"
        if c["missing"]:
            return "Missing"
        if c["state"] == "graded" and c["score"] == 0:
            return "Zero"
        if c["late"] and c["score"] is None:
            return "Late, ungraded"
        if c["submitted_at"] and c["score"] is None:
            return "Submitted, ungraded"
        if c["score"] is not None:
            return _score(c, item["points"])
        if past:
            return "Paper, check" if item["kind"] == "paper" else "Missing"
        if due is not None:
            days = (due.date() - now.date()).days
            return "Due today" if days == 0 else "Due tomorrow" if days == 1 else "Due " + due.strftime("%a")
        return "No due date"
    if h is not None:
        if h["score"] is None:
            return "HAC, no grade" if past else "Not graded yet"
        return _score(h, item["points"])
    return ""


def due_relative(due: datetime | None, now: datetime) -> str:
    """The due date as a distance from today, for the muted second line of the Due cell."""
    if due is None:
        return ""
    days = (due.date() - now.date()).days
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    if 1 < days <= 6:
        return due.strftime("%a")
    if days < 0:
        return f"{-days} days ago"
    return ""


#: Kinds with nothing to hand in online. Canvas still lists them, unsubmitted forever, and
#: "No" there would read as the kid skipping work that was done on paper in class.
_NOTHING_TO_SUBMIT = ("paper", "in class")


def handed_in_text(item: sqlite3.Row, obs: dict[str, sqlite3.Row]) -> tuple[str, datetime | None]:
    """Whether it was handed in, and when. Only Canvas knows; HAC records grades, not
    submissions, so a HAC-only item answers "—" rather than pretending."""
    c = obs.get("canvas")
    if c is None:
        return ("—", None) if obs else ("", None)
    if c["excused"]:
        return "Excused", None
    if c["submitted_at"]:
        at = datetime.fromisoformat(c["submitted_at"])
        return ("Late" if c["late"] else "Yes"), at
    if item["kind"] in _NOTHING_TO_SUBMIT:
        return "—", None
    return "No", None


def grade_text(item: sqlite3.Row, obs: dict[str, sqlite3.Row], prefer: str = "canvas") -> tuple[str, bool]:
    """What the gradebook says about the work itself, and whether it is a real zero.

    Under the default, Canvas first: it carries the teacher's marks ("Missing", "Excused") as
    well as the score, and HAC only when Canvas has nothing. Under `prefer="hac"` a HAC score is
    shown whenever there is one, ahead of Canvas's score and its Missing mark; Unpublished and
    Excused still come first. A disagreement between the two is the Reconcile page's job."""
    c, h = obs.get("canvas"), obs.get("hac")
    if prefer == "hac" and h is not None and h["score"] is not None:
        if c is not None and c["published"] == 0:
            return "Unpublished", False
        if c is not None and c["excused"]:
            return "Excused", False
        return _score(h, item["points"]), h["score"] == 0 and (item["points"] or 0) > 0
    if c is not None:
        if c["published"] == 0:
            return "Unpublished", False
        if c["excused"]:
            return "Excused", False
        if c["score"] is not None:
            return _score(c, item["points"]), c["state"] == "graded" and c["score"] == 0
        if c["missing"]:
            return "Missing", False
        if c["submitted_at"]:
            return "Not yet", False
        if h is not None and h["score"] is not None:
            return _score(h, item["points"]), h["score"] == 0
        return "", False
    if h is not None:
        if h["score"] is None:
            return "Not yet", False
        return _score(h, item["points"]), h["score"] == 0
    return "", False


def _views(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules, days_ahead: int = DAYS_AHEAD,
           prefs=None) -> list[ItemView]:
    latest = db.latest_observations(conn, student["id"])
    kinds: dict[int, list[str]] = {}
    for case in reconcile.cases(conn, student["id"], rules=rules, now=now, prefs=prefs):
        kinds.setdefault(case.item_id, []).append(case.kind)
    note_counts = {r["target_id"]: r["n"] for r in conn.execute(
        "SELECT target_id, COUNT(*) AS n FROM notes WHERE target_type = 'item' GROUP BY target_id")}
    flag_text = {r["item_id"]: r["text"] for r in conn.execute("SELECT item_id, text FROM flags WHERE cleared_at IS NULL")}
    out: list[ItemView] = []
    for r in reconcile.live_items(conn, student["id"], now):
        obs = latest.get(r["id"], {})
        prefer = sources.assignments_for(prefs, r["kid"], r["course_name"], r["peer_course_name"])
        due = reconcile.due_of(r)
        handed, handed_at = handed_in_text(r, obs)
        grade, zero = grade_text(r, obs, prefer)
        open_in = reconcile.open_sources(r, obs, now, prefer=prefer)
        late_until, credit = None, ""
        if open_in and due is not None:
            late_until = rules.deadline(r["kid"], r["course_name"], due)
            credit = rules.resolve(r["kid"], r["course_name"]).credit
        out.append(ItemView(
            due_relative=due_relative(due, now), handed_in=handed, handed_in_at=handed_at, grade=grade, grade_zero=zero,
            due_time=due_time(due, from_canvas="canvas" in obs),
            outcome=outcomes.classify(r, obs, now, prefer=prefer), late_until=late_until, credit=credit,
            id=r["id"], key=r["key"], name=r["name"], course_id=r["course_id"], course_short=r["course_short"],
            course_name=r["course_name"], kind=r["kind"], points=r["points"], due=reconcile.due_of(r),
            sources=tuple(s for s in ("canvas", "hac") if s in obs),
            open_in=open_in,
            actionable=reconcile.is_actionable(r, obs, r["flag"], rules, r["kid"], now, prefer=prefer),
            upcoming=reconcile.upcoming(r, obs, now, days_ahead),
            flag=r["flag"], flag_text=flag_text.get(r["id"], ""), status=status_text(r, obs, now, prefer),
            canvas=obs.get("canvas"), hac=obs.get("hac"),
            notes=note_counts.get(r["id"], 0), case_kinds=kinds.get(r["id"], []),
        ))
    return out


def _keep(v: ItemView, show: str, source, course_ids, kind, flagged, outcome=None) -> bool:
    if outcome and v.outcome != outcome:
        return False
    if show == "open" and not ((v.open_in or v.upcoming) and not v.handled):
        return False
    if show == "actionable" and not v.actionable:
        return False
    if source == "both" and v.sources != ("canvas", "hac"):
        return False
    if source in ("canvas", "hac") and source not in v.sources:
        return False
    if course_ids and v.course_id not in course_ids:
        return False
    if kind and v.kind != kind:
        return False
    if flagged == "any" and not v.flag:
        return False
    if flagged == "marked" and v.flag not in MARKED_FLAGS:
        return False
    if flagged == "handled" and v.flag not in HANDLED_FLAGS:
        return False
    if flagged == "none" and v.flag:
        return False
    return True


_FAR = datetime.max.replace(tzinfo=None)


def _sort_key(sort: str):
    def due_key(v: ItemView):
        return (v.due.replace(tzinfo=None) if v.due else _FAR, v.course_short, v.name.lower())
    if sort == "course":
        return lambda v: (v.course_short, due_key(v))
    if sort == "name":
        return lambda v: (v.name.lower(), due_key(v))
    if sort == "status":
        return lambda v: (not v.actionable, not v.overdue, v.status, due_key(v))
    return due_key


def sorted_views(views: list[ItemView], sort: str = "due", direction: str = "asc") -> list[ItemView]:
    """Order rows the way `list_items` does. The course page merges two lists (a course and
    its twin in the other source) into one table and sorts the whole of it with this.

    `direction` reverses the whole comparison, tie-breakers included -- so "due, newest
    first" also runs its same-day items backwards. That is the reading a parent gets from a
    turned-around arrow: the table they were looking at, upside down. Reversing only the
    named column and leaving the tie-breakers ascending is the other defensible answer; it
    keeps same-day work alphabetical either way, at the cost of a table that is not quite
    the mirror of itself. Anything but "desc" sorts ascending, because a hand-typed or
    pasted `dir=` is a query string, not a promise."""
    return sorted(views, key=_sort_key(sort if sort in SORTS else "due"),
                  reverse=direction == "desc")


def list_items(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules, show: str = "open",
               source: str | None = None, course_id: int | None = None, kind: str | None = None,
               flagged: str | None = None, sort: str = "due", outcome: str | None = None,
               days_ahead: int = DAYS_AHEAD, direction: str = "asc", prefs=None) -> list[ItemView]:
    """`outcome` is a filter on `outcomes.classify`; when one is given, `show` is forced to
    "all", because "not done" work that is past its credit window is exactly what a parent
    filtering on "not done" wants to see and exactly what "open" hides."""
    if outcome:
        show = "all"
    if show not in SHOW:
        show = "open"
    # A course id names a class, and a class is one Canvas course plus its paired HAC course
    # (students.course_options offers the pair as one entry). Widen to both, so filtering by
    # "Honors Biology" also shows the lab HAC lists that Canvas never had.
    course_ids: set[int] = set()
    if course_id is not None:
        course_ids.add(course_id)
        peer = conn.execute("SELECT peer_course_id FROM courses WHERE id = ?", (course_id,)).fetchone()
        if peer and peer["peer_course_id"]:
            course_ids.add(peer["peer_course_id"])
    views = [v for v in _views(conn, student, now=now, rules=rules, days_ahead=days_ahead, prefs=prefs)
             if _keep(v, show, source, course_ids, kind, flagged, outcome)]
    return sorted_views(views, sort, direction)


def one(conn: sqlite3.Connection, student: sqlite3.Row, item_id: int, *, now: datetime, rules,
        days_ahead: int = DAYS_AHEAD, prefs=None) -> ItemView | None:
    return next((v for v in _views(conn, student, now=now, rules=rules, days_ahead=days_ahead, prefs=prefs) if v.id == item_id), None)


def with_cases(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules,
               kind: str | None = None, prefs=None) -> list[tuple[ItemView, list[reconcile.Case]]]:
    """Every live item that carries at least one reconciliation case, with its cases, for the
    Reconcile page. Items the parent has already handled (done / excused / ignore) are left out:
    the page is for open questions, and the Kid page's `show=all` still lists them.

    `kind` selects which *groups* appear, not which reasons: an item is kept when at least one
    of its cases has that kind, and a kept item still lists all of its cases, so a multi-kind
    item (e.g. both `past_credit` and `one_source`) doesn't lose a reason just because the page
    is filtered to a different one."""
    by_item: dict[int, list[reconcile.Case]] = {}
    for case in reconcile.cases(conn, student["id"], rules=rules, now=now, prefs=prefs):
        by_item.setdefault(case.item_id, []).append(case)
    if kind is not None:
        by_item = {i: cs for i, cs in by_item.items() if any(c.kind == kind for c in cs)}
    views = {v.id: v for v in _views(conn, student, now=now, rules=rules, prefs=prefs) if v.id in by_item and not v.handled}
    out = [(views[i], cs) for i, cs in by_item.items() if i in views]
    return sorted(out, key=lambda pair: _sort_key("due")(pair[0]))


@dataclass(frozen=True)
class OpenWork:
    """One kid's open work, the way the printed sheet divides it: what is past due and can
    still be fixed, what is coming due, and -- as the sheet's trailer counts them -- what is
    open but past its late-work window, and what the parent has flagged handled."""
    fixable: list[ItemView]         # actionable: open, inside the credit window, not handled; soonest-closing first
    upcoming: list[ItemView]        # unsubmitted Canvas work due within `days_ahead`, not handled; by due date
    past_window: list[ItemView]     # open, not handled, but the register says it no longer earns credit
    handled: list[ItemView]         # open or upcoming, but flagged done / excused / ignore

    @property
    def past_window_points(self) -> float:
        return sum((v.points or 0) for v in self.past_window)


def open_work(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules, days_ahead: int = DAYS_AHEAD,
              prefs=None) -> OpenWork:
    views = _views(conn, student, now=now, rules=rules, days_ahead=days_ahead, prefs=prefs)
    open_or_upcoming = [v for v in views if v.overdue or v.upcoming]
    handled = [v for v in open_or_upcoming if v.handled]
    live = [v for v in open_or_upcoming if not v.handled]
    fixable = [v for v in live if v.actionable]
    due_key = _sort_key("due")
    fixable.sort(key=lambda v: (v.late_until.replace(tzinfo=None) if v.late_until else _FAR, due_key(v)))
    return OpenWork(
        fixable=fixable,
        upcoming=sorted((v for v in live if v.upcoming and not v.overdue), key=due_key),
        past_window=sorted((v for v in live if v.overdue and not v.actionable), key=due_key),
        handled=sorted(handled, key=due_key),
    )


@dataclass(frozen=True)
class Counts:
    actionable: int
    due_today: int
    due_tomorrow: int
    new_since_yesterday: int
    record: outcomes.Tally = outcomes.Tally()    # how the past-due work came out, by `outcomes.classify`


def record_for(views: list[ItemView]) -> outcomes.Tally:
    return outcomes.tally(v.outcome for v in views)


def dashboard_counts(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules,
                     days_ahead: int = DAYS_AHEAD, prefs=None) -> Counts:
    views = _views(conn, student, now=now, rules=rules, days_ahead=days_ahead, prefs=prefs)
    today = now.date()
    due_today = sum(1 for v in views if v.upcoming and v.due and v.due.date() == today)
    due_tomorrow = sum(1 for v in views if v.upcoming and v.due and v.due.date() == today + timedelta(days=1))
    since = (now - timedelta(days=1)).isoformat()
    new = conn.execute(
        """SELECT COUNT(*) AS n FROM items i JOIN refreshes r ON r.id = i.first_seen
           WHERE i.student_id = ? AND r.started_at >= ?""", (student["id"], since)).fetchone()["n"]
    return Counts(sum(1 for v in views if v.actionable), due_today, due_tomorrow, new, record_for(views))

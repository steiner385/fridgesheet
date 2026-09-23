"""One definition of "open work", shared by the MCP tools and the printed sheet.

Open means the kid can still do something about it:

* Canvas items not submitted -- past due (MISSING, ZERO, PAPER — CHECK) or due within the
  next `days_ahead` days (DUE TODAY / DUE TOMORROW / DUE <weekday>) -- plus submissions
  turned in late and not yet graded (LATE). A graded late submission is finished business.
* HAC rows with a blank score after their due date (HAC — NO GRADE), deduped against the
  Canvas item they pair with.

Overdue items are shown only while the class still gives credit for them (see
`late_rules`) and only within `overdue_days`; anything older goes to `dropped`, which the
sheet reports as a count rather than as rows. Due dates before the current school year
are course-copy artifacts from last year and are ignored altogether.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable

from . import late_rules as _late_rules
from . import sources as _sources
from .matching import hac_item_key, match_course, same_item, short_course

OVERDUE_STATUSES = ("MISSING", "ZERO", "LATE", "PAPER — CHECK", "HAC — NO GRADE")
HANDLED_FLAGS = ("done", "excused", "ignore")     # these remove the item from the open list
MARKED_FLAGS = ("follow_up", "ask_teacher")       # these print a marker in the status column
ASSESSMENT_WORDS = ("quiz", "test", "assess", "exam")   # an assignment group naming one of these is graded work that counts


@dataclass
class Item:
    key: str
    kid: str
    course: str
    name: str
    due: datetime
    status: str
    overdue: bool
    source: str                      # canvas | hac | both
    kind: str                        # online | paper | in class | "" (HAC-only)
    points: float | None = None
    score: float | None = None
    assigned: datetime | None = None
    late_until: datetime | None = None
    credit: str = ""
    is_assessment: bool = False
    submission_types: list = field(default_factory=list)
    flag: str = ""

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("due", "assigned", "late_until"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@dataclass
class OpenWork:
    kid: str
    as_of: datetime
    items: list[Item]
    dropped: list[Item]             # overdue but past credit / too old; not shown as rows
    handled: list[Item] = field(default_factory=list)  # removed by a handled flag; not in items or dropped


@dataclass
class Diff:
    new: set
    changed: dict                   # key -> previous status
    cleared: list[dict]             # previous rows no longer open


def kind_of(submission_types: list | None) -> str:
    """How the work is handed in: online, on paper, or in class. Shared with `web.ingest`."""
    st = list(submission_types or [])
    if "on_paper" in st:
        return "paper"
    if not st or st == ["none"]:
        return "in class"
    return "online"


def _status(a: dict, due: datetime, now: datetime) -> str | None:
    """The status word for a Canvas assignment, or None when there is nothing open."""
    if a.get("excused") or not a.get("published", True):
        return None
    graded = a.get("state") == "graded"
    unsubmitted = a.get("state") in ("unsubmitted", None) and a.get("score") is None
    if a.get("missing"):
        return "MISSING"
    if graded and a.get("score") == 0:
        return "ZERO"
    if a.get("late") and a.get("score") is None:
        return "LATE"
    if due < now:
        if unsubmitted:
            return "PAPER — CHECK" if kind_of(a.get("submission_types")) == "paper" else "MISSING"
        return None
    if not unsubmitted:
        return None
    days = (due.date() - now.date()).days
    if days == 0:
        return "DUE TODAY"
    if days == 1:
        return "DUE TOMORROW"
    return "DUE " + due.strftime("%a").upper()


def school_year_start(now: datetime) -> datetime:
    """August 1st of the school year `now` falls in. Anything due before it is a course-copy
    artifact from last year, not work. Shared with `web.reconcile`, which needs the same floor."""
    return datetime(now.year if now.month >= 7 else now.year - 1, 8, 1, tzinfo=now.tzinfo)


def parse_hac_date(s: str | None, tz) -> datetime | None:
    """A HAC date (mm/dd/yyyy) in the settings time zone, or None when it is blank or odd.
    Shared with `web.ingest`, which must store the same instant the sheet prints."""
    try:
        return datetime.strptime(s or "", "%m/%d/%Y").replace(tzinfo=tz)
    except ValueError:
        return None


def open_items(entry: dict, kid: str, now: datetime, days_ahead: int = 14, overdue_days: int = 14,
               rules: _late_rules.LateRules | None = None, include_hac: bool = True,
               flags: dict[str, str] | None = None, prefs=None) -> OpenWork:
    rules = rules or _late_rules.LateRules(_late_rules.Rule(), [], [])
    flags = flags or {}
    tz = now.tzinfo
    horizon = now + timedelta(days=days_ahead)
    oldest = now - timedelta(days=overdue_days)
    year_start = school_year_start(now)
    # Rules name kids by first name; `kid` here is the printed label, which may be a nickname.
    first = ((entry.get("name") or kid).split() or [kid])[0]
    hac_classes = {h.get("name") or "": h for h in ((entry.get("hac") or {}).get("classes") or [])} if include_hac else {}

    items: list[Item] = []
    dropped: list[Item] = []
    handled: list[Item] = []
    canvas_names_by_course: dict[str, list[str]] = {}

    for c in ((entry.get("canvas") or {}).get("courses") or []):
        peer = match_course(c["name"], hac_classes) if hac_classes else None
        peer_rows = {a["name"]: a for a in (peer or {}).get("assignments", [])}
        pick = _sources.assignments_for(prefs, first, c["name"], (peer or {}).get("name"))
        for a in c["assignments"]:
            if not a.get("due_at"):
                continue
            due = datetime.fromisoformat(a["due_at"])
            if due < year_start:
                continue
            hac_row = next((r for n, r in peer_rows.items() if same_item(a["name"], n)), None)
            hac_score = (hac_row or {}).get("score")
            if pick == "hac" and hac_score is not None and not a.get("excused") and a.get("published", True):
                # The family reads this class's scores from HAC: its grade settles the item.
                status = "ZERO" if hac_score == 0 and (a.get("points_possible") or 0) > 0 else None
            else:
                status = _status(a, due, now)
            if status is None:
                continue
            # Canvas shows paper and in-class work as unsubmitted forever; a grade in HAC is the
            # proof it was handed in. The web app's outcome definition calls that *done on
            # paper* (docs/outcomes.md), and the sheet must not print PAPER — CHECK -- or
            # MISSING, for online work the teacher graded from a physical copy -- for work the
            # gradebook has already marked. A Canvas `missing` flag or a 0 still wins: those
            # are the teacher's word, and a disagreement is the Reconcile page's to show.
            if status in ("PAPER — CHECK", "MISSING") and not a.get("missing") and a.get("score") is None \
                    and hac_score not in (None, 0):
                continue
            overdue = status in OVERDUE_STATUSES
            if not overdue and due > horizon:
                continue
            assigned = None
            if hac_row:
                assigned = parse_hac_date(hac_row.get("assigned"), tz)
            if assigned is None:
                raw = a.get("unlock_at") or a.get("created_at")
                assigned = datetime.fromisoformat(raw) if raw else None
            course = short_course(c["name"])
            it = Item(
                key=f"canvas:{a['id']}", kid=kid, course=course, name=a["name"], due=due, status=status,
                overdue=overdue, source="both" if hac_row else "canvas", kind=kind_of(a.get("submission_types")),
                points=a.get("points_possible"), score=hac_score if pick == "hac" and hac_score is not None else a.get("score"), assigned=assigned,
                is_assessment=bool(a.get("group") and any(w in a["group"].lower() for w in ASSESSMENT_WORDS)),
                submission_types=list(a.get("submission_types") or []),
            )
            canvas_names_by_course.setdefault(c["name"], []).append(a["name"])
            it.flag = flags.get(it.key, "")
            if it.flag in HANDLED_FLAGS:
                handled.append(it)
                continue
            if overdue:
                rule = rules.resolve(kid, c["name"])
                it.late_until, it.credit = rules.deadline(kid, c["name"], due), rule.credit
                if due < oldest or now > it.late_until:
                    dropped.append(it)
                    continue
            items.append(it)

    all_canvas_names = [n for names in canvas_names_by_course.values() for n in names]
    for hname, h in hac_classes.items():
        peer_names = match_course(hname, canvas_names_by_course)
        already = peer_names if peer_names is not None else all_canvas_names
        for a in h.get("assignments", []):
            if any(same_item(a["name"], seen) for seen in already):
                continue
            due = parse_hac_date(a.get("due"), tz)
            if due is None:
                continue
            due = due.replace(hour=23, minute=59)
            if due < year_start or not (a.get("score") is None and a.get("score_raw") == "" and due < now - timedelta(days=1)):
                continue
            course = short_course(hname)
            it = Item(
                key=hac_item_key(hname, a["name"]), kid=kid, course=course, name=a["name"], due=due,
                status="HAC — NO GRADE", overdue=True, source="hac", kind="", points=a.get("points"),
                assigned=parse_hac_date(a.get("assigned"), tz),
                is_assessment=any(w in (a.get("category") or "").lower() for w in ("quiz", "assess")),
            )
            it.flag = flags.get(it.key, "")
            if it.flag in HANDLED_FLAGS:
                handled.append(it)
                continue
            rule = rules.resolve(kid, hname)
            it.late_until, it.credit = rules.deadline(kid, hname, due), rule.credit
            if due < oldest or now > it.late_until:
                dropped.append(it)
            else:
                items.append(it)

    items.sort(key=lambda i: (not i.overdue, i.due, i.course, i.name))
    dropped.sort(key=lambda i: (i.due, i.course, i.name))
    handled.sort(key=lambda i: (i.due, i.course, i.name))
    return OpenWork(kid=kid, as_of=now, items=items, dropped=dropped, handled=handled)


def compare(prev_rows: Iterable[dict], items: list[Item], handled: Iterable[Item] = ()) -> Diff:
    """What changed since the last sheet: keys not seen before, keys whose status word
    changed (with the old word), and previous rows that are no longer open.

    An item the parent marked done, excused or ignored is not "cleared since last sheet" --
    the kid did not finish it, someone struck it off -- and the sheet already reports it in
    the handled trailer, so it is left out of both lists.
    """
    prev = {r["key"]: r for r in prev_rows}
    cur = {i.key for i in items} | {i.key for i in handled}
    return Diff(
        new={i.key for i in items if i.key not in prev},
        changed={i.key: prev[i.key]["status"] for i in items if i.key in prev and prev[i.key]["status"] != i.status},
        cleared=[r for k, r in prev.items() if k not in cur],
    )

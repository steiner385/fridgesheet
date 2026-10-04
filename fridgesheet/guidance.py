"""What would move a class average, and by how much (spec
docs/superpowers/specs/2026-10-04-what-moves-the-grade-design.md).

Over an account (grading.Account) and the class's open rows, three kinds of lever:
  zero      a blank HAC row the gradebook already counts as zero: earning it raises `earned`
            with `possible` fixed, so its worth is 100 * credit * points / possible;
  missing   an overdue row still inside the late window that is not counted yet;
  upcoming  a posted row not yet due;
the last two add to both sides: 100 * (earned + credit*points) / (possible + points) - rebuilt.

Reach is the perfect points of not-yet-counted work needed for the next letter once every zero
is filled at its credit; slack is how many of the posted points may be lost and keep the current
letter. Both use posted work only: nothing here extrapolates what a teacher has not posted.

Which blank rows HAC already counts as zero is a heuristic: the account knows per category how
many blank points are inside its denominator (Line.zero_points), not which rows; HAC enters
zeros for work past due, so within a category the blank, past-due rows are taken oldest-due
first until their points reach that figure. It decides only whether a row's points are already
in `possible`, which changes a lever's worth by the difference between the two formulas.

Sound only when the account is exact. Otherwise levers keep their points and credit, worth is
None, and there is no reach or slack: points, never average points.

Pure: the web store builds rows from items.open_work; the MCP server from the snapshot.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from . import grading
from .late_rules import credit_fraction

_FAR = datetime.max


@dataclass(frozen=True)
class Lever:
    item_id: int | None
    name: str
    kind: str                 # "zero" | "missing" | "upcoming"
    points: float
    credit: float             # 1.0 unless the late rule names a percentage
    credit_known: bool        # False when the rule's credit text names none ("?")
    worth: float | None       # average points if earned at `credit`; None when not sound
    deadline: datetime | None # late_until for zero/missing, due for upcoming
    category: str


@dataclass(frozen=True)
class Reach:
    letter: str
    floor: float
    needed: float             # perfect points of not-yet-counted work, zeros filled first (<= 0: zeros alone)
    posted: float             # points of missing + upcoming levers
    reachable: bool


@dataclass(frozen=True)
class Slack:
    letter: str
    floor: float
    posted: float
    can_miss: float           # negative: the letter needs -can_miss of the next `posted`


@dataclass(frozen=True)
class Guidance:
    sound: bool
    letter: str
    levers: tuple[Lever, ...]
    best: Lever | None
    reach: Reach | None
    slack: Slack | None
    zero_points: float


def _sort_deadline(d: datetime | None) -> datetime:
    return d.replace(tzinfo=None) if d is not None else _FAR


def guide(account: grading.Account, rows: list[dict], scale: grading.GradeScale) -> Guidance:
    sound = account.match == "exact" and account.reported is not None and account.possible > 0
    letter = scale.letter(account.reported)
    budget = {l.category: float(l.zero_points) for l in account.lines}
    levers: list[Lever] = []
    for r in sorted(rows, key=lambda r: _sort_deadline(r.get("due"))):
        pts = float(r.get("points") or 0.0)
        if pts <= 0 or r.get("hac_scored"):
            continue
        frac = credit_fraction(r.get("credit_text"))
        credit, known = (1.0, False) if frac is None else (frac, True)
        if r.get("overdue"):
            cat = r.get("category") or ""
            if r.get("hac_blank") and budget.get(cat, 0.0) >= pts - 1e-9:
                budget[cat] -= pts
                kind = "zero"
            else:
                kind = "missing"
            deadline = r.get("late_until")
        elif r.get("upcoming"):
            kind, credit, known, deadline = "upcoming", 1.0, True, r.get("due")
        else:
            continue
        worth = None
        if sound:
            if kind == "zero":
                worth = 100.0 * credit * pts / account.possible
            else:
                worth = 100.0 * (account.earned + credit * pts) / (account.possible + pts) - (account.rebuilt or 0.0)
        levers.append(Lever(r.get("item_id"), r.get("name") or "", kind, pts, credit, known, worth, deadline, r.get("category") or ""))
    levers.sort(key=lambda l: (-(l.worth if l.worth is not None else l.points), _sort_deadline(l.deadline), l.name))
    zero_points = round(sum(l.points for l in levers if l.kind == "zero"), 2)
    reach = slack = None
    if sound:
        earned2 = account.earned + sum(l.credit * l.points for l in levers if l.kind == "zero")
        posted = round(sum(l.points for l in levers if l.kind != "zero"), 2)
        above = [(ltr, f) for ltr, f in scale.cuts if f > account.reported]
        if above:
            ltr, f = min(above, key=lambda c: c[1])
            needed = (f / 100 * account.possible - earned2) / (1 - f / 100)
            reach = Reach(ltr, f, round(needed, 1), posted, needed <= posted)
        current = next((f for ltr, f in scale.cuts if ltr == letter), None)
        if current is not None:
            can_miss = earned2 + posted - current / 100 * (account.possible + posted)
            slack = Slack(letter, current, posted, round(can_miss, 1))
    return Guidance(sound, letter, tuple(levers), levers[0] if levers else None, reach, slack, zero_points)


def fmt_worth(x) -> str:
    """Average points to one decimal; the phrase supplies the sign."""
    return "" if x is None else f"{float(x):.1f}"


def with_article(letter: str) -> str:
    """"an A", "a B": the letter as a sentence says it (the phrases carry no article)."""
    if not letter:
        return ""
    return ("an " if letter[0].upper() in "AEF" else "a ") + letter

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
    worth: float | None       # change in the average shown, if earned at `credit` (never below 0); None when not sound
    deadline: datetime | None # late_until for zero/missing, due for upcoming
    category: str
    cost: float | None = None # missing work only: what the zero it becomes would take off the average shown

    @property
    def stake(self) -> float:
        """The difference between earning it and leaving it: what ranks the levers."""
        return (self.worth or 0.0) + (self.cost or 0.0)


@dataclass(frozen=True)
class Reach:
    letter: str
    floor: float
    needed: float | None      # perfect points of not-yet-counted work, zeros filled first (<= 0: zeros alone);
                              # None in a weighted class, where points in one category are not points in another
    posted: float             # points of missing + upcoming levers
    reachable: bool
    ceiling: float | None = None  # weighted classes: the average if every posted lever is earned at its credit


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
    weighted = account.basis == "weighted"
    # A weighted class: category -> [earned, possible, weight], for the categories HAC weighs.
    cats = {l.category: [l.earned, l.possible, l.weight] for l in account.lines if weighted and l.weight is not None}
    levers: list[Lever] = []
    for r in sorted(rows, key=lambda r: _sort_deadline(r.get("due"))):
        pts = float(r.get("points") or 0.0)
        cat = r.get("category") or ""
        if r.get("counted_only"):
            # Past its window or answered: not a lever, but a blank past-due row HAC has zeroed
            # uses the category's budget first, oldest-due first, like any other.
            if r.get("hac_blank") and r.get("overdue") and pts > 0:
                budget[cat] = max(0.0, budget.get(cat, 0.0) - pts)
            continue
        if pts <= 0 or (r.get("hac_scored") and not r.get("hac_zero")):
            continue
        frac = credit_fraction(r.get("credit_text"))
        credit, known = (1.0, False) if frac is None else (frac, True)
        if r.get("hac_zero") and (r.get("overdue") or r.get("upcoming")):
            # An explicit zero is already inside `possible`: a zero lever, no budget needed.
            kind, deadline = "zero", (r.get("late_until") if r.get("overdue") else r.get("due"))
            if not r.get("overdue"):
                credit, known = 1.0, True
        elif r.get("overdue"):
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
        worth = cost = None
        if sound and weighted:
            worth, cost = _weighted_worth(cats, account.rebuilt or 0.0, cat, kind, pts, credit)
        elif sound:
            if kind == "zero":
                worth = 100.0 * credit * pts / account.possible
            else:
                worth = max(0.0, 100.0 * (account.earned + credit * pts) / (account.possible + pts) - (account.rebuilt or 0.0))
                if kind == "missing":
                    cost = (account.rebuilt or 0.0) - 100.0 * account.earned / (account.possible + pts)
        levers.append(Lever(r.get("item_id"), r.get("name") or "", kind, pts, credit, known, worth, deadline, cat, cost))
    levers.sort(key=lambda l: (-(l.stake if sound else l.points), _sort_deadline(l.deadline), l.name))
    zero_points = round(sum(l.points for l in levers if l.kind == "zero"), 2)
    reach = slack = None
    if sound and weighted:
        reach = _weighted_reach(cats, account, levers, scale)
    elif sound:
        earned2 = account.earned + sum(l.credit * l.points for l in levers if l.kind == "zero")
        posted = round(sum(l.points for l in levers if l.kind != "zero"), 2)
        above = [(ltr, f) for ltr, f in scale.cuts if account.reported < f < 100.0]   # a cut at 100 or above is no one's reach
        if above:
            ltr, f = min(above, key=lambda c: c[1])
            needed = (f / 100 * account.possible - earned2) / (1 - f / 100)
            reach = Reach(ltr, f, round(needed, 1), posted, needed <= posted)
        current = next((f for ltr, f in scale.cuts if ltr == letter), None)
        if current is not None:
            can_miss = earned2 + posted - current / 100 * (account.possible + posted)
            slack = Slack(letter, current, posted, round(can_miss, 1))
    return Guidance(sound, letter, tuple(levers), levers[0] if levers else None, reach, slack, zero_points)


def _weighted_avg(cats: dict[str, list]) -> float | None:
    live = [(e, p, w) for e, p, w in cats.values() if p]
    total = sum(w for _e, _p, w in live)
    return (100.0 * sum(w * e / p for e, p, w in live) / total) if total else None


def _with(cats: dict[str, list], cat: str, de: float, dp: float) -> dict[str, list]:
    out = {k: list(v) for k, v in cats.items()}
    out[cat][0] += de
    out[cat][1] += dp
    return out


def _weighted_worth(cats: dict[str, list], now: float, cat: str, kind: str, pts: float, credit: float) -> tuple[float | None, float | None]:
    """A lever's worth and cost in a weighted class: it moves only its own category's percent,
    which moves the average by that category's weight. A category HAC's table does not list
    carries no known weight, so the lever has no worth."""
    if cat not in cats:
        return None, None
    if kind == "zero":
        after = _weighted_avg(_with(cats, cat, credit * pts, 0.0))
        return (max(0.0, after - now) if after is not None else None), None
    after = _weighted_avg(_with(cats, cat, credit * pts, pts))
    worth = max(0.0, after - now) if after is not None else None
    cost = None
    if kind == "missing":
        blank = _weighted_avg(_with(cats, cat, 0.0, pts))
        cost = (now - blank) if blank is not None else None
    return worth, cost


def _weighted_reach(cats: dict[str, list], account: grading.Account, levers: list[Lever], scale: grading.GradeScale) -> Reach | None:
    """The next letter in a weighted class, as the ceiling the posted work allows: the average if
    every zero is filled and every posted lever earned at its credit. No point count: ten points
    of Quiz are not ten points of Assignments."""
    above = [(ltr, f) for ltr, f in scale.cuts if account.reported < f < 100.0]
    if not above:
        return None
    ltr, f = min(above, key=lambda c: c[1])
    state = {k: list(v) for k, v in cats.items()}
    for l in levers:
        if l.kind == "zero" and l.category in state:
            state[l.category][0] += l.credit * l.points
    zeros_only = _weighted_avg(state)
    for l in levers:
        if l.kind != "zero" and l.category in state:
            state[l.category][0] += l.credit * l.points
            state[l.category][1] += l.points
    ceiling = _weighted_avg(state)
    posted = round(sum(l.points for l in levers if l.kind != "zero"), 2)
    needed = 0.0 if zeros_only is not None and zeros_only >= f else None
    return Reach(ltr, f, needed, posted, ceiling is not None and ceiling >= f, round(ceiling, 2) if ceiling is not None else None)


def fmt_worth(x) -> str:
    """Average points to one decimal; the phrase supplies the sign."""
    return "" if x is None else f"{float(x):.1f}"


def with_article(letter: str) -> str:
    """"an A", "a B": the letter as a sentence says it (the phrases carry no article)."""
    if not letter:
        return ""
    return ("an " if letter[0].upper() in "AEF" else "a ") + letter

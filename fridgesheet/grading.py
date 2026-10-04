"""The account of a class average: what the gradebook's number is built from, and whether it
adds up (spec docs/superpowers/specs/2026-10-03-report-card-and-grade-account-design.md §4).

A finding, not a rule. On 2026-10-03 every one of this household's HAC classes that showed
category subtotal rows (thirteen of thirteen) had a marking-period average equal to total points
earned over total points possible across every category, to the hundredth. Four classes showed
no subtotal rows and two of those do not rebuild from their rows. So this module never asserts
straight points: it rebuilds the number from what the gradebook shows and reports whether the
rebuild matches (`Account.match`). A district that weights categories reads "off" on every
class, honestly, and that is the cue for a weights follow-up.

Canvas's `current_score` is over graded work only and its `final_score` counts unsubmitted work
as zero; this household's Canvas courses use no group weights (every `group_weight` is 0.0).

Pure: no database, no HTTP. `web/stores/grades.py` feeds it rows from SQLite; `server.py`
feeds it the snapshot. Both get the same arithmetic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger("fridgesheet.grading")

#: HAC prints two decimals; a rebuild from two-decimal subtotals drifts by at most a hundredth.
TOLERANCE = 0.011


@dataclass(frozen=True)
class Line:
    category: str
    earned: float
    possible: float
    rows: int                 # scored rows seen in this category (0 when only the subtotal is known)
    from_rows: bool           # True when the gradebook gave no subtotal and this was summed from the rows
    share: float              # possible / the account's total possible; a category's weight in a straight-points class

    @property
    def percent(self) -> float | None:
        return 100.0 * self.earned / self.possible if self.possible else None


@dataclass(frozen=True)
class Account:
    source: str               # "hac" | "canvas"
    reported: float | None    # HAC's marking-period average, or Canvas's current score
    lines: tuple[Line, ...]   # the gradebook's order, from_rows lines last
    earned: float
    possible: float
    rebuilt: float | None     # 100 * earned / possible; None when nothing is possible
    basis: str                # "subtotals" | "rows" | "none"
    match: str                # "exact" | "off" | "unknown"
    zero_points: float        # HAC: points of blank work already counted as zero inside the subtotals
    excused: int              # rows the gradebook excused; they never count
    final: float | None       # Canvas's final_score (unsubmitted as zero); None for HAC
    hidden: bool              # Canvas hides this grade
    missing: int              # Canvas rows marked missing: what `final` counts as zero


def _match(rebuilt: float | None, reported: float | None) -> str:
    if rebuilt is None or reported is None:
        return "unknown"
    return "exact" if abs(rebuilt - reported) <= TOLERANCE else "off"


def _lines(ordered: list[tuple[str, float, float, int, bool]]) -> tuple[Line, ...]:
    total = sum(p for _c, _e, p, _n, _f in ordered)
    return tuple(Line(c, e, p, n, f, (p / total) if total else 0.0) for c, e, p, n, f in ordered)


def account_hac(reported: float | None, subtotals: list[dict], rows: list[dict]) -> Account:
    """HAC's account. `subtotals` are the category rows `hac.classwork()` scrapes
    ({category, earned, possible, percent}); `rows` are the class's assignment rows
    ({category, score, points, excused}), from the snapshot or from item_observations."""
    scored: dict[str, list[float]] = {}      # category -> [earned, possible, n]
    blank: dict[str, float] = {}             # category -> points of unscored, unexcused rows
    excused = 0
    for r in rows:
        cat = r.get("category") or ""
        if r.get("excused"):
            excused += 1
            continue
        pts = r.get("points")
        if r.get("score") is None:
            if pts:
                blank[cat] = blank.get(cat, 0.0) + float(pts)
            continue
        if pts:
            s = scored.setdefault(cat, [0.0, 0.0, 0])
            s[0] += float(r["score"])
            s[1] += float(pts)
            s[2] += 1
    ordered: list[tuple[str, float, float, int, bool]] = []
    seen: set[str] = set()
    zero_points = 0.0
    for sub in subtotals:
        cat = sub.get("category") or ""
        earned, possible = float(sub.get("earned") or 0.0), float(sub.get("possible") or 0.0)
        n = scored.get(cat, [0.0, 0.0, 0])
        ordered.append((cat, earned, possible, int(n[2]), False))
        seen.add(cat)
        # How much of HAC's denominator the scored rows do not explain, capped at the blank work
        # that could explain it: a category whose rows the scraper never saw is not blank work.
        zero_points += min(max(0.0, possible - n[1]), blank.get(cat, 0.0))
    for cat, (e, p, n) in scored.items():
        if cat not in seen:
            ordered.append((cat, e, p, int(n), True))
    lines = _lines(ordered)
    earned = round(sum(l.earned for l in lines), 2)
    possible = round(sum(l.possible for l in lines), 2)
    rebuilt = (100.0 * earned / possible) if possible else None
    basis = "subtotals" if subtotals else ("rows" if lines else "none")
    return Account("hac", reported, lines, earned, possible, rebuilt, basis, _match(rebuilt, reported),
                   round(zero_points, 2), excused, None, False, 0)


def account_canvas(current: float | None, final: float | None, hidden: bool, rows: list[dict]) -> Account:
    """Canvas's account: one line per assignment group over graded rows
    ({group, score, points, excused, missing, state})."""
    groups: dict[str, list[float]] = {}
    order: list[str] = []
    excused = missing = 0
    for r in rows:
        if r.get("excused"):
            excused += 1
            continue
        if r.get("missing"):
            missing += 1
        pts = r.get("points")
        if r.get("score") is None or not pts:
            continue
        g = r.get("group") or ""
        if g not in groups:
            groups[g] = [0.0, 0.0, 0]
            order.append(g)
        groups[g][0] += float(r["score"])
        groups[g][1] += float(pts)
        groups[g][2] += 1
    lines = _lines([(g, groups[g][0], groups[g][1], int(groups[g][2]), True) for g in order])
    earned = round(sum(l.earned for l in lines), 2)
    possible = round(sum(l.possible for l in lines), 2)
    rebuilt = (100.0 * earned / possible) if possible else None
    return Account("canvas", current, lines, earned, possible, rebuilt, "rows" if lines else "none",
                   _match(rebuilt, current), 0.0, excused, final, bool(hidden), missing)


@dataclass(frozen=True)
class GradeScale:
    cuts: tuple[tuple[str, float], ...]     # (letter, floor), highest floor first
    below: str = "F"

    def letter(self, value: float | None) -> str:
        if value is None:
            return ""
        for letter, floor in self.cuts:
            if value >= floor:
                return letter
        return self.below


TEN_POINT = GradeScale((("A", 90.0), ("B", 80.0), ("C", 70.0), ("D", 60.0)), "F")


def scale_from_doc(doc: dict) -> GradeScale:
    """`[grading] scale = { A = 90, B = 80, ... }` and `below = "F"`. Any other shape warns and
    keeps the ten-point scale: a typo in a preference must not take the app down."""
    raw = doc.get("grading")
    if not isinstance(raw, dict):
        return TEN_POINT
    scale = raw.get("scale", None)
    if scale is None:
        return TEN_POINT
    if not isinstance(scale, dict) or not scale:
        log.warning("[grading] scale must be a table of letter = floor, got %r; using the ten-point scale", scale)
        return TEN_POINT
    cuts: list[tuple[str, float]] = []
    for letter, floor in scale.items():
        if isinstance(floor, bool) or not isinstance(floor, (int, float)):
            log.warning("[grading] scale: %s = %r is not a number; using the ten-point scale", letter, floor)
            return TEN_POINT
        cuts.append((str(letter), float(floor)))
    cuts.sort(key=lambda c: -c[1])
    below = raw.get("below", "F")
    return GradeScale(tuple(cuts), str(below) if below is not None else "F")


def fmt_points(x) -> str:
    """Points as a reader says them: 25, 520.5, 368.91."""
    if x is None:
        return ""
    x = round(float(x), 2)        # a raw float sum (24.999999999999996) is 25 to a reader
    if x == int(x):
        return str(int(x))
    return f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_avg(x) -> str:
    """An average, always two decimals, as HAC prints it."""
    return "" if x is None else f"{float(x):.2f}"

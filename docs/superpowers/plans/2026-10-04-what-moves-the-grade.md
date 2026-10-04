# What Moves the Grade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tell a kid or parent what would move a class average and by how much: the levers (blank work counted as zero, overdue work still accepted, posted work not yet due) with their worth in average points, the reach to the next letter and the slack under the current one, said on the report card line, in a "What moves it" section on the class page, and as a worth badge on Must-finish rows.

**Architecture:** `fridgesheet/guidance.py` is a pure engine over `grading.Account` and a list of open rows; it never decides what is open. `web/stores/guidance.py` builds those rows from `items.open_work` (the one definition of what is still to do) and the class's account, and chooses the report card's sentence. Three templates render it; the MCP `grades()` tool carries the same engine's output from the snapshot. No schema or config change.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, SQLite, pytest. Tests: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q <paths>` from the worktree root (PYTHONPATH must be unset; check the venv path still exists at the start of each task, `ls -d /home/tony/GitHub/fridgesheet/.venv /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/*/.venv`).

**Spec:** `docs/superpowers/specs/2026-10-04-what-moves-the-grade-design.md`

## Global Constraints

- Guidance is **sound** only when `account.match == "exact"` and `account.reported is not None`; otherwise levers carry points only (`worth None`), and `reach` and `slack` are None. No surface prints an average-point figure from an unsound account.
- Rows come only from `items.open_work(...).fixable + .upcoming` (deduplicated by id), filtered to the class's course ids; the engine never re-derives openness. Must-finish rows, groups and order are unchanged (`tests/test_open_work_parity.py`, `tests/test_web_tier_parity.py`).
- A row whose latest HAC observation has a score is never a lever (already counted). A row with no points is never a lever.
- Credit: `1.0` unless the late rule's credit text names a percentage (`late_rules.credit_fraction`); `"?"` or blank is full credit with `credit_known=False`.
- Reach and slack use posted work only. The early tier never says "can't".
- Numbers reach a phrase formatted: points via `grading.fmt_points`, worth via `guidance.fmt_worth` (one decimal, no sign; the phrase carries the `+`), averages via `grading.fmt_avg`. Every `gd.*`/`badge.worth` phrase has all three tiers with identical placeholders and no digits (`tests/test_phrasing.py`).
- Every new template block uses the section standard (`.sec`, `.sec-head`, `_item.html` for assignment lines) and no retired class; every radius and gap is a token.
- No commit on this branch carries `[skip release]` on a line of its own (it leaks into the squash message and skips the feature's release).

## Review Focus

1. **A class whose next letter is already the top of the scale** (Health at 100.00, "A"): no reach; the slack line must not divide by zero or claim a letter above A. Test in Task 3 (`test_at_the_top_letter_there_is_no_reach_only_slack`).
2. **A blank HAC row that is not yet due** (posted, future, HAC lists it blank): it is `upcoming`, never allocated as a zero, even when the category has zero points to spare. Test in Task 3 (`test_a_future_blank_row_is_upcoming_not_a_zero`).
3. **The same item in both `fixable` and `upcoming`** (an upcoming row is also `_fixable`): one lever, not two, and posted points counted once. Test in Task 4 (`test_rows_are_deduplicated_across_fixable_and_upcoming`).
4. **A lever with no deadline** (undated HAC-only work, `late_until None`): ranks last among ties and renders without "accepted until". Test in Task 3 (`test_a_lever_without_a_deadline_ranks_last_among_ties`) and Task 4 (`test_an_undated_lever_note_has_no_until`).
5. **A kid with no open work at all** on the Plan: `by_item` returns `{}` and the page renders without badges or errors. Test in Task 7 (`test_a_kid_with_nothing_open_gets_no_badges`).

---

### Task 1: `Line.zero_points` per category

**Files:**
- Modify: `fridgesheet/grading.py` (the `Line` dataclass, `_lines`, `account_hac`)
- Test: `tests/test_grading.py`

**Interfaces:**
- Produces: `grading.Line.zero_points: float` (blank points HAC counts as zero in that category; 0.0 for Canvas and from-rows lines). `Account.zero_points` stays the sum.

- [ ] **Step 1: Write the failing test** (append to `tests/test_grading.py`)

```python
def test_each_subtotal_line_carries_its_own_zero_points():
    # Algebra II: the 25 blank points sit in Assignments, none in Assessments.
    a = grading.account_hac(70.88, ALGEBRA_SUBS, ALGEBRA_ROWS)
    assert [(l.category, l.zero_points) for l in a.lines] == [("Assessments", 0.0), ("Assignments", 25.0)]
    assert a.zero_points == 25.0
    rows_line = grading.account_hac(86.57, [], [_row("Quiz", 11.0, 17.0)])
    assert rows_line.lines[0].zero_points == 0.0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_grading.py -k own_zero_points`
Expected: FAIL, `TypeError`/`AttributeError`: `Line` has no `zero_points`.

- [ ] **Step 3: Implement.** In `grading.py`, add to `Line` after `share`:

```python
    zero_points: float = 0.0  # HAC: blank points this category already counts as zero (spec 2026-10-04 §3)
```

Change `_lines` to carry a sixth tuple member:

```python
def _lines(ordered: list[tuple[str, float, float, int, bool, float]]) -> tuple[Line, ...]:
    total = sum(p for _c, _e, p, _n, _f, _z in ordered)
    return tuple(Line(c, e, p, n, f, (p / total) if total else 0.0, z) for c, e, p, n, f, z in ordered)
```

In `account_hac`, compute the per-category zero inside the subtotal loop and append it:

```python
    for sub in subtotals:
        cat = sub.get("category") or ""
        earned, possible = float(sub.get("earned") or 0.0), float(sub.get("possible") or 0.0)
        n = scored.get(cat, [0.0, 0.0, 0])
        z = round(min(max(0.0, possible - n[1]), blank.get(cat, 0.0)), 2)
        ordered.append((cat, earned, possible, int(n[2]), False, z))
        seen.add(cat)
        zero_points += z
    for cat, (e, p, n) in scored.items():
        if cat not in seen:
            ordered.append((cat, e, p, int(n), True, 0.0))
```

In `account_canvas`, the `_lines` call gains `0.0` as the sixth member: `(g, groups[g][0], groups[g][1], int(groups[g][2]), True, 0.0)`.

- [ ] **Step 4: Run the grading tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_grading.py tests/test_web_grades_store.py tests/test_server_tools.py`
Expected: all pass (`asdict` gains a key; nothing asserts the exact key set).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/grading.py tests/test_grading.py
git commit -m "grading: each subtotal line carries the blank points HAC counts as zero in that category"
```

---

### Task 2: `late_rules.credit_fraction`

**Files:**
- Modify: `fridgesheet/late_rules.py` (new function), `fridgesheet/web/verdicts.py:99-101` (`_credit_fraction` becomes a re-export)
- Test: `tests/test_late_rules.py` (append; create if absent with the same header style as `tests/test_grading.py`)

**Interfaces:**
- Produces: `late_rules.credit_fraction(credit: str | None) -> float | None` ("50%" → 0.5; "?" / "" / "half" → None).

- [ ] **Step 1: Write the failing test**

```python
from fridgesheet import late_rules


def test_credit_fraction_reads_a_percentage_and_nothing_else():
    assert late_rules.credit_fraction("50%") == 0.5
    assert late_rules.credit_fraction(" 75 % from the syllabus") == 0.75
    assert late_rules.credit_fraction("?") is None and late_rules.credit_fraction("") is None and late_rules.credit_fraction(None) is None
    assert late_rules.credit_fraction("half") is None
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_late_rules.py -k credit_fraction`
Expected: `AttributeError: module 'fridgesheet.late_rules' has no attribute 'credit_fraction'`.

- [ ] **Step 3: Implement.** In `late_rules.py` (it already imports `re`; add it if not):

```python
def credit_fraction(credit: str | None) -> float | None:
    """The fraction a rule's free-text credit names ("50%" -> 0.5), or None when it names none
    (the seeded "?", blank, or words). The one place credit text becomes a number: the
    verdicts' lower-HAC-score explanation and the grade guidance both read it."""
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%", credit or "")
    return float(m.group(1)) / 100 if m else None
```

In `verdicts.py`, replace the body of `_credit_fraction` with `return late_rules.credit_fraction(credit)` (import `from .. import late_rules` if the module does not already import it; check the file head).

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_late_rules.py tests/test_verdicts.py`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/late_rules.py fridgesheet/web/verdicts.py tests/test_late_rules.py
git commit -m "late_rules.credit_fraction: the one reader of a rule's credit text, shared by verdicts and guidance"
```

---

### Task 3: `guidance.py`, the engine

**Files:**
- Create: `fridgesheet/guidance.py`
- Test: `tests/test_guidance.py`

**Interfaces:**
- Consumes: `grading.Account` with `Line.zero_points` (Task 1), `grading.GradeScale`, `late_rules.credit_fraction` (Task 2).
- Produces: `guidance.Lever`, `guidance.Reach`, `guidance.Slack`, `guidance.Guidance`, `guidance.guide(account, rows, scale) -> Guidance`, `guidance.fmt_worth(x) -> str`. A `row` is a dict `{item_id, name, category, points, due, late_until, credit_text, overdue, upcoming, hac_blank, hac_scored}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_guidance.py
"""What moves the grade (spec 2026-10-04 §3-§4), on the household's own numbers."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fridgesheet import grading, guidance

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 10, 4, 9, 0, tzinfo=TZ)


def _sub(category, earned, possible):
    return {"category": category, "earned": earned, "possible": possible, "percent": ""}


def _hrow(category, score, points, excused=False):
    return {"category": category, "score": score, "points": points, "excused": excused}


def _row(name, points, *, category="Assignments", due_days=-5, overdue=True, upcoming=False, hac_blank=False,
         hac_scored=False, credit="?", late_days=14, item_id=None):
    due = NOW + timedelta(days=due_days)
    return {"item_id": item_id, "name": name, "category": category, "points": points, "due": due,
            "late_until": due + timedelta(days=late_days), "credit_text": credit, "overdue": overdue,
            "upcoming": upcoming, "hac_blank": hac_blank, "hac_scored": hac_scored}


# Concert Band: Daily 175/175, Playing 92/130; 25 blank points in Playing already counted as zero.
BAND = grading.account_hac(87.54, [_sub("Daily", 175.0, 175.0), _sub("Playing/Written Work", 92.0, 130.0)],
                           [_hrow("Daily", 175.0, 175.0), _hrow("Playing/Written Work", 92.0, 105.0),
                            _hrow("Playing/Written Work", None, 25.0)])


def test_zeros_alone_can_reach_the_next_letter():
    g = guidance.guide(BAND, [_row("Scale test", 25.0, category="Playing/Written Work", hac_blank=True)], grading.TEN_POINT)
    assert g.sound and g.letter == "B"
    (lever,) = g.levers
    assert lever.kind == "zero" and round(lever.worth, 2) == round(100 * 25 / 305, 2)      # earned grows, possible fixed
    assert g.reach.letter == "A" and g.reach.needed <= 0 and g.reach.reachable
    assert g.zero_points == 25.0


def test_missing_and_upcoming_levers_add_to_both_sides_of_the_fraction():
    # Honors Biology: 278.53 / 349 = 79.81; a 20-point lab not yet counted.
    bio = grading.account_hac(79.81, [_sub("Labs", 50.0, 80.0), _sub("Quiz", 95.83, 120.0), _sub("Daily", 132.7, 149.0)], [])
    g = guidance.guide(bio, [_row("Lab 5", 20.0, category="Labs", due_days=3, overdue=False, upcoming=True)], grading.TEN_POINT)
    (lever,) = g.levers
    assert lever.kind == "upcoming" and lever.credit == 1.0
    assert round(lever.worth, 2) == round(100 * (278.53 + 20) / 369 - bio.rebuilt, 2)
    assert g.reach.letter == "B" and round(g.reach.needed, 1) == 3.4 and g.reach.posted == 20.0 and g.reach.reachable


def test_reach_beyond_posted_work_is_reported_not_hidden():
    # Honors Algebra II: a B needs ~237 perfect points; 80 are posted.
    alg = grading.account_hac(70.88, [_sub("Assessments", 290.66, 400.0), _sub("Assignments", 78.25, 120.5)],
                              [_hrow("Assessments", 290.66, 400.0), _hrow("Assignments", 78.25, 95.5), _hrow("Assignments", None, 25.0)])
    rows = [_row("Blank quiz", 25.0, hac_blank=True), _row("Unit test", 80.0, category="Assessments", due_days=4, overdue=False, upcoming=True)]
    g = guidance.guide(alg, rows, grading.TEN_POINT)
    assert g.reach.letter == "B" and not g.reach.reachable and g.reach.needed > g.reach.posted == 80.0
    assert g.best.kind == "upcoming" and g.best.name == "Unit test"                  # more worth than the 25-point zero


def test_late_credit_halves_a_levers_worth_and_an_unknown_credit_is_flagged():
    g = guidance.guide(BAND, [_row("Scale test", 25.0, category="Playing/Written Work", hac_blank=True, credit="50%"),
                              _row("Rhythm sheet", 10.0, category="Playing/Written Work", credit="?")], grading.TEN_POINT)
    half, unknown = g.levers[0], g.levers[1]
    assert half.credit == 0.5 and half.credit_known and round(half.worth, 2) == round(100 * 12.5 / 305, 2)
    assert unknown.credit == 1.0 and not unknown.credit_known


def test_zero_allocation_is_oldest_due_first_within_the_category():
    rows = [_row("Newer", 15.0, category="Playing/Written Work", hac_blank=True, due_days=-2),
            _row("Older", 15.0, category="Playing/Written Work", hac_blank=True, due_days=-9),
            _row("Oldest", 5.0, category="Playing/Written Work", hac_blank=True, due_days=-12)]
    g = guidance.guide(BAND, rows, grading.TEN_POINT)
    kinds = {l.name: l.kind for l in g.levers}
    assert kinds == {"Oldest": "zero", "Older": "zero", "Newer": "missing"}            # 5 + 15 fill the 25; the newest is not counted yet


def test_a_future_blank_row_is_upcoming_not_a_zero():
    g = guidance.guide(BAND, [_row("Next scale", 25.0, category="Playing/Written Work", hac_blank=True, due_days=2, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.levers[0].kind == "upcoming" and g.zero_points == 0.0


def test_a_scored_row_and_a_pointless_row_are_never_levers():
    g = guidance.guide(BAND, [_row("Graded", 10.0, hac_scored=True), _row("Attendance", 0.0)], grading.TEN_POINT)
    assert g.levers == ()


def test_an_unsound_account_gives_points_but_no_worth_reach_or_slack():
    off = grading.account_hac(86.57, [], [_hrow("Quiz", 11.0, 17.0)])
    g = guidance.guide(off, [_row("Quiz 2", 17.0, category="Quiz", due_days=2, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert not g.sound and g.levers[0].worth is None and g.reach is None and g.slack is None


def test_at_the_top_letter_there_is_no_reach_only_slack():
    health = grading.account_hac(100.0, [_sub("Total Points", 585.0, 585.0)], [])
    g = guidance.guide(health, [_row("Unit quiz", 115.0, category="Total Points", due_days=5, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.reach is None and g.slack.letter == "A"
    assert round(g.slack.can_miss, 1) == round(585 + 115 - 0.9 * 700, 1) and g.slack.posted == 115.0


def test_negative_slack_says_how_much_of_the_next_points_the_letter_needs():
    # 88.0 B with 50 points posted: 44 + 50 - 0.8*100 = 14 may be missed; at 79.9 it goes negative.
    low = grading.account_hac(79.9, [_sub("A", 39.95, 50.0)], [])
    g = guidance.guide(low, [_row("Next", 10.0, category="A", due_days=1, overdue=False, upcoming=True)], grading.TEN_POINT)
    assert g.slack.letter == "C" and g.slack.can_miss > 0
    assert g.reach.letter == "B" and g.reach.reachable                                    # 80 is within the next 10


def test_ranking_is_worth_then_deadline_and_a_lever_without_a_deadline_ranks_last_among_ties():
    rows = [_row("B", 10.0, due_days=-3), _row("A", 10.0, due_days=-6)]
    undated = _row("U", 10.0, due_days=-4)
    undated["due"] = None
    undated["late_until"] = None
    g = guidance.guide(BAND, rows + [undated], grading.TEN_POINT)
    assert [l.name for l in g.levers] == ["A", "B", "U"]


def test_fmt_worth():
    assert guidance.fmt_worth(2.0) == "2.0" and guidance.fmt_worth(4.84) == "4.8" and guidance.fmt_worth(0.04) == "0.0"


def test_with_article():
    assert guidance.with_article("A") == "an A" and guidance.with_article("B") == "a B" and guidance.with_article("F") == "an F"
    assert guidance.with_article("A-") == "an A-" and guidance.with_article("") == ""
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_guidance.py`
Expected: collection error, no module `fridgesheet.guidance`.

- [ ] **Step 3: Write `fridgesheet/guidance.py`**

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_guidance.py`
Expected: 13 passed. If `test_zero_allocation_is_oldest_due_first_within_the_category` fails because "Newer" was taken (budget 25 − 5 − 15 = 5 < 15, so it must not be), check the `>= pts - 1e-9` comparison; a partial budget never makes a zero.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/guidance.py tests/test_guidance.py
git commit -m "guidance.py: the levers that move a class average, their worth, the reach to the next letter and the slack under this one"
```

---

### Task 4: The store and the sentences

**Files:**
- Create: `fridgesheet/web/stores/guidance.py`
- Modify: `fridgesheet/web/phrasing.py` (after the `copy.rc_how_canvas` entry)
- Test: `tests/test_web_guidance_store.py`

**Interfaces:**
- Consumes: `guidance.guide`, `grades.account_for`, `grades.ReportLine`, `items.open_work`, `students.course`, `students.latest_grades`, `late_rules`.
- Produces:
  - `guidance_store.rows_for(conn, work: items.OpenWork, course_ids: set[int]) -> list[dict]`
  - `guidance_store.for_class(conn, course: sqlite3.Row, account: grading.Account, work, scale) -> guidance.Guidance`
  - `guidance_store.by_item(conn, student, work, prefs, scale) -> dict[int, guidance.Lever]`
  - `guidance_store.sentence_for(g: guidance.Guidance) -> list[tuple[str, dict]]` (zero, one or two phrase keys with values)
  - phrasing keys `gd.*`, `copy.gd_*`, `badge.worth` as spec §5.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_guidance_store.py
"""Levers from the database's open work, and the report card's second sentence (spec 2026-10-04 §5-§6)."""
from __future__ import annotations

from fridgesheet import grading, sources
from fridgesheet.web import phrasing
from fridgesheet.web.stores import grades, guidance as gstore, items, students
from tests.web_fixtures import NOW, TZ, seed
from fridgesheet import late_rules


def _work(conn, key):
    s = students.by_key(conn, key)
    rules = late_rules.LateRules(late_rules.Rule(), [], [])
    return s, items.open_work(conn, s, now=NOW, rules=rules, prefs=sources.DEFAULT)


def _english(conn):
    return conn.execute("SELECT * FROM courses WHERE short_name = 'Honors English 9' AND source = 'hac'").fetchone()


def test_rows_are_deduplicated_across_fixable_and_upcoming(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    hac = _english(conn)
    rows = gstore.rows_for(conn, work, {hac["id"], hac["peer_course_id"]})
    names = [r["name"] for r in rows]
    assert len(names) == len(set(names))
    assert set(names) == {"Participation", "Lab notebook", "Vocabulary", "Worksheet 3", "Reading log"}   # Quiz 1 has HAC's 28/30: not open; Essay draft is in
    quiz = [r for r in rows if r["name"] == "Quiz 1"]
    assert quiz == []


def test_englishs_levers_and_reach_from_the_fixture(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    hac = _english(conn)
    account = grades.account_for(conn, hac, students.latest_grades(conn, s["id"]).get(hac["id"]))
    g = gstore.for_class(conn, hac, account, work, grading.TEN_POINT)
    assert g.sound and g.letter == "B"
    assert {l.name: l.kind for l in g.levers} == {"Participation": "missing", "Lab notebook": "missing", "Vocabulary": "upcoming",
                                                  "Worksheet 3": "upcoming", "Reading log": "upcoming"}
    assert all(round(l.worth, 1) == 2.0 for l in g.levers)                          # 100*(44+10)/(50+10) - 88
    assert g.best.name == "Vocabulary"                                              # equal worth: soonest deadline first
    assert g.reach.letter == "A" and g.reach.needed == 10.0 and g.reach.posted == 50.0 and g.reach.reachable


def test_the_report_cards_second_sentence_for_english_and_for_an_unsound_class(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    hac = _english(conn)
    latest = students.latest_grades(conn, s["id"])
    g = gstore.for_class(conn, hac, grades.account_for(conn, hac, latest.get(hac["id"])), work, grading.TEN_POINT)
    assert gstore.sentence_for(g) == [("gd.best", {"name": "Vocabulary", "points": "10", "worth": "2.0"}),
                                      ("gd.reach", {"letter": "an A", "needed": "10", "posted": "50"})]
    alg = conn.execute("SELECT * FROM courses WHERE short_name = 'Algebra I' AND source = 'hac'").fetchone()
    g2 = gstore.for_class(conn, alg, grades.account_for(conn, alg, latest.get(alg["id"])), work, grading.TEN_POINT)
    assert not g2.sound and gstore.sentence_for(g2) == []


def test_sentence_order_zeros_reach_then_best_then_reach_or_slack():
    from fridgesheet import guidance
    L = guidance.Lever(1, "Scale test", "zero", 25.0, 1.0, True, 8.2, None, "Playing")
    zeros = guidance.Guidance(True, "B", (L,), L, guidance.Reach("A", 90.0, -3.0, 0.0, True), None, 25.0)
    assert gstore.sentence_for(zeros) == [("gd.zeros_reach", {"zero_points": "25", "letter": "an A"})]
    far = guidance.Guidance(True, "C", (), None, guidance.Reach("B", 80.0, 237.5, 80.0, False), None, 0.0)
    assert gstore.sentence_for(far) == [("gd.reach_far", {"letter": "a B", "needed": "237.5", "posted": "80"})]
    top = guidance.Guidance(True, "A", (), None, None, guidance.Slack("A", 90.0, 115.0, 70.0), 0.0)
    assert gstore.sentence_for(top) == [("gd.keep", {"letter": "an A", "can_miss": "70", "posted": "115"})]
    hold = guidance.Guidance(True, "B", (), None, guidance.Reach("A", 90.0, 60.0, 10.0, False), guidance.Slack("B", 80.0, 10.0, -2.0), 0.0)
    assert gstore.sentence_for(hold) == [("gd.reach_far", {"letter": "an A", "needed": "60", "posted": "10"}), ("gd.hold", {"letter": "a B", "need": "2", "posted": "10"})]
    nothing = guidance.Guidance(True, "A", (), None, None, guidance.Slack("A", 90.0, 0.0, 10.0), 0.0)
    assert gstore.sentence_for(nothing) == [("gd.nothing_posted", {})]


def test_by_item_maps_every_open_row_of_a_sound_class_to_its_lever(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    by = gstore.by_item(conn, s, work, sources.DEFAULT, grading.TEN_POINT)
    vocab = conn.execute("SELECT id FROM items WHERE name = 'Vocabulary'").fetchone()["id"]
    assert round(by[vocab].worth, 1) == 2.0
    homework4 = conn.execute("SELECT id FROM items WHERE name = 'Homework 4'").fetchone()["id"]
    assert homework4 not in by                                                      # past the window: not open at all


def test_an_undated_lever_note_has_no_until():
    from fridgesheet import guidance
    L = guidance.Lever(1, "Reading", "missing", 5.0, 1.0, False, 0.9, None, "")
    key, values = gstore.lever_note(L, "older")
    assert key == "gd.lever_missing_undated" and "until" not in values and values["credit_note"] == " · late credit unknown, ask"


def test_every_gd_phrase_has_three_tiers_and_the_same_placeholders():
    for key, by_tier in phrasing.PHRASES.items():
        if key.startswith("gd.") or key.startswith("copy.gd_") or key == "badge.worth":
            assert set(by_tier) == {"early", "middle", "older"}, key
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_guidance_store.py`
Expected: collection error (`cannot import name 'guidance'` from stores).

- [ ] **Step 3: Add the phrases** to `PHRASES` after `copy.rc_how_canvas`:

```python
    # --- what moves the grade (spec 2026-10-04 §5) ----------------------------------------------
    "gd.zeros_reach":   {"early": "Turn in the {zero_points} points of blank work and it's a {letter}.",
                         "middle": "Turn in the {zero_points} points of blank work and it's a {letter}.",
                         "older": "Turn in the {zero_points} points of blank work and it's a {letter}."},
    "gd.best":          {"early": "Best move: {name} ({points} pts), worth up to +{worth}.",
                         "middle": "Best move: {name} ({points} pts), worth up to +{worth}.",
                         "older": "Best move: {name} ({points} pts), worth up to +{worth}."},
    "gd.reach":         {"early": "{needed} of the next {posted} points makes it a {letter}.",
                         "middle": "A {letter} needs {needed} of the next {posted} points.",
                         "older": "A {letter} needs {needed} of the next {posted} points."},
    "gd.reach_far":     {"early": "A {letter} would take {needed} points. There aren't that many posted yet. Keep going and ask your teacher what's coming.",
                         "middle": "A {letter} needs {needed} points: more than the {posted} posted so far.",
                         "older": "A {letter} needs {needed} points: more than the {posted} posted so far."},
    "gd.keep":          {"early": "Keeping the {letter}: you can miss up to {can_miss} of the next {posted} points.",
                         "middle": "Keeping the {letter}: you can miss up to {can_miss} of the next {posted} points.",
                         "older": "Keeping the {letter}: you can miss up to {can_miss} of the next {posted} points."},
    "gd.hold":          {"early": "To keep the {letter}, get {need} of the next {posted} points.",
                         "middle": "Keeping the {letter} needs {need} of the next {posted} points.",
                         "older": "Keeping the {letter} needs {need} of the next {posted} points."},
    "gd.nothing_posted": {"early": "Nothing to turn in and nothing coming yet. The next work your teacher posts decides it.",
                          "middle": "Nothing posted to turn in or come; the next work the teacher posts decides it.",
                          "older": "Nothing posted to turn in or come; the next work the teacher posts decides it."},
    "gd.not_sound":     {"early": "{n} things still open, {points} points. HAC's number doesn't match what we can see, so these are points, not average points.",
                         "middle": "{n} rows still open, {points} points. HAC's number does not rebuild from what we see, so these are points, not average points.",
                         "older": "{n} rows still open, {points} points. HAC's number does not rebuild from what we see, so these are points, not average points."},
    "gd.lever_zero":    {"early": "Blank, counts as zero now · accepted until {until}{credit_note}",
                         "middle": "Blank, counted as zero now · accepted until {until}{credit_note}",
                         "older": "Blank, counted as zero now · accepted until {until}{credit_note}"},
    "gd.lever_missing": {"early": "Not counted yet · accepted until {until}{credit_note}",
                         "middle": "Not counted yet · accepted until {until}{credit_note}",
                         "older": "Not counted yet · accepted until {until}{credit_note}"},
    "gd.lever_missing_undated": {"early": "Not counted yet{credit_note}", "middle": "Not counted yet{credit_note}", "older": "Not counted yet{credit_note}"},
    "gd.lever_upcoming": {"early": "Due {due} · not counted yet", "middle": "Due {due} · not counted yet", "older": "Due {due} · not counted yet"},
    "copy.gd_credit_at":      {"early": " at {credit}", "middle": " at {credit}", "older": " at {credit}"},
    "copy.gd_credit_unknown": {"early": " · late credit unknown, ask", "middle": " · late credit unknown, ask", "older": " · late credit unknown, ask"},
    "copy.gd_what_moves_it":  {"early": "What moves it", "middle": "What moves it", "older": "What moves it"},
    "badge.worth":      {"early": "worth +{worth}", "middle": "+{worth} on the average", "older": "+{worth} on the average"},
```

- [ ] **Step 4: Write `fridgesheet/web/stores/guidance.py`**

```python
"""Levers from the database (spec 2026-10-04 §6): rows from `items.open_work` (the one
definition of what is still to do), the class's account from `grades.account_for`, and the
report card's second sentence. The arithmetic is `fridgesheet.guidance`."""
from __future__ import annotations

import sqlite3

from ... import dates, grading, guidance
from . import grades, students


def _hac_categories(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    marks = ",".join("?" * len(item_ids))
    return {r["item_id"]: r["category"] for r in conn.execute(
        f"SELECT item_id, category FROM item_categories WHERE source = 'hac' AND item_id IN ({marks})", item_ids)}


def rows_for(conn: sqlite3.Connection, work, course_ids: set[int]) -> list[dict]:
    """The class's open rows as the engine wants them, each item once."""
    seen: set[int] = set()
    views = []
    for v in list(work.fixable) + list(work.upcoming):
        if v.course_id in course_ids and v.id not in seen:
            seen.add(v.id)
            views.append(v)
    cats = _hac_categories(conn, [v.id for v in views])
    return [{"item_id": v.id, "name": v.name, "category": cats.get(v.id, ""), "points": v.points, "due": v.due,
             "late_until": v.late_until, "credit_text": v.credit, "overdue": v.overdue, "upcoming": v.upcoming,
             "hac_blank": v.hac is not None and v.hac["score"] is None,
             "hac_scored": v.hac is not None and v.hac["score"] is not None} for v in views]


def _class_ids(conn: sqlite3.Connection, course: sqlite3.Row) -> set[int]:
    ids = {course["id"]}
    if course["peer_course_id"]:
        ids.add(course["peer_course_id"])
    return ids


def for_class(conn: sqlite3.Connection, course: sqlite3.Row, account: grading.Account, work, scale: grading.GradeScale) -> guidance.Guidance:
    return guidance.guide(account, rows_for(conn, work, _class_ids(conn, course)), scale)


def by_item(conn: sqlite3.Connection, student: sqlite3.Row, work, prefs, scale: grading.GradeScale) -> dict[int, guidance.Lever]:
    """item id -> its lever, for the Plan's badges: one guide per class a kid has open work in,
    on the family's official source for that class."""
    out: dict[int, guidance.Lever] = {}
    latest = students.latest_grades(conn, student["id"])
    done: set[int] = set()
    for v in list(work.fixable) + list(work.upcoming):
        if v.course_id in done:
            continue
        course = students.course(conn, v.course_id)
        if course is None:
            continue
        peer = students.course(conn, course["peer_course_id"]) if course["peer_course_id"] else None
        ids = _class_ids(conn, course)
        done |= ids
        pick = prefs.resolve(student["key"], course["name"], peer["name"] if peer else None).grades
        official = course if course["source"] == pick else (peer if peer is not None and peer["source"] == pick else course)
        account = grades.account_for(conn, official, latest.get(official["id"]))
        g = guidance.guide(account, rows_for(conn, work, ids), scale)
        for lever in g.levers:
            if lever.item_id is not None:
                out[lever.item_id] = lever
    return out


def lever_note(lever: guidance.Lever, tier: str) -> tuple[str, dict]:
    """The lever's one-line note under its item line (spec 2026-10-04 §5). `credit_note` is
    said here, in the kid's tier, so the outer phrase's values are plain strings."""
    from ..verdicts import words
    credit_note = ""
    if lever.kind != "upcoming":
        if lever.credit_known and lever.credit < 1.0:
            credit_note = words("copy.gd_credit_at", tier, {"credit": f"{round(lever.credit * 100)}%"})
        elif not lever.credit_known:
            credit_note = words("copy.gd_credit_unknown", tier)
    if lever.kind == "upcoming":
        return "gd.lever_upcoming", {"due": dates.wd_md(lever.deadline) if lever.deadline else ""}
    if lever.deadline is None:
        return "gd.lever_missing_undated", {"credit_note": credit_note}
    key = "gd.lever_zero" if lever.kind == "zero" else "gd.lever_missing"
    return key, {"until": dates.md(lever.deadline), "credit_note": credit_note}


def sentence_for(g: guidance.Guidance) -> list[tuple[str, dict]]:
    """The report card line's second sentence(s), in the spec's order; [] when not sound."""
    if not g.sound:
        return []
    out: list[tuple[str, dict]] = []
    art = guidance.with_article
    if g.reach is not None and g.reach.needed <= 0 and g.zero_points > 0:
        return [("gd.zeros_reach", {"zero_points": grading.fmt_points(g.zero_points), "letter": art(g.reach.letter)})]
    if g.best is not None:
        out.append(("gd.best", {"name": g.best.name, "points": grading.fmt_points(g.best.points), "worth": guidance.fmt_worth(g.best.worth)}))
        if g.reach is not None and g.reach.reachable and g.reach.needed > 0:
            out.append(("gd.reach", {"letter": art(g.reach.letter), "needed": grading.fmt_points(g.reach.needed), "posted": grading.fmt_points(g.reach.posted)}))
        return out
    if g.reach is not None and g.reach.posted > 0:
        key = "gd.reach" if g.reach.reachable else "gd.reach_far"
        out.append((key, {"letter": art(g.reach.letter), "needed": grading.fmt_points(g.reach.needed), "posted": grading.fmt_points(g.reach.posted)}))
    if g.slack is not None and g.slack.posted > 0:
        if g.slack.can_miss >= 0:
            if g.reach is None:
                out.append(("gd.keep", {"letter": art(g.slack.letter), "can_miss": grading.fmt_points(g.slack.can_miss), "posted": grading.fmt_points(g.slack.posted)}))
        else:
            out.append(("gd.hold", {"letter": art(g.slack.letter), "need": grading.fmt_points(-g.slack.can_miss), "posted": grading.fmt_points(g.slack.posted)}))
    if not out:
        out.append(("gd.nothing_posted", {}))
    return out
```

`verdicts.words` is the plain (uncapitalised) phrase formatter the templates' `words` filter wraps; `lever_note` uses it for the inner credit note so the note's values stay plain strings.

- [ ] **Step 5: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_guidance_store.py tests/test_phrasing.py`
Expected: pass. If `test_rows_are_deduplicated...` lists a different set, print `[(v.name, v.overdue, v.upcoming, v.actionable) for v in work.fixable + work.upcoming]` and adjust the expected set only if the open-work definition (not the row builder) explains the difference; record it in the ledger.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/stores/guidance.py fridgesheet/web/phrasing.py tests/test_web_guidance_store.py
git commit -m "stores/guidance: levers from the class's open work, the Plan's per-item worth, and the report card's second sentence"
```

---

### Task 5: The report card's second sentence

**Files:**
- Modify: `fridgesheet/web/routes/report_card.py`, `fridgesheet/web/templates/report_card.html:23`, `fridgesheet/web/static/app.css` (after `.report-card-page .report-line .how`)
- Test: `tests/test_web_report_card.py`

**Interfaces:**
- Consumes: `guidance_store.for_class`, `guidance_store.sentence_for`, `items.open_work`, `state.rules()`, `state.window()`.

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_the_line_says_what_would_move_it_when_the_account_is_sound(tmp_path):
    seed(tmp_path).close()
    lines = _lines(app_for(tmp_path).get("/kids/Alex/report-card").text)
    eng = next(l for l in lines if "Honors English 9" in l)
    assert '<p class="lever">Best move: Vocabulary (10 pts), worth up to +2.0. An A needs 10 of the next 50 points.</p>' in eng
    alg = next(l for l in lines if "Algebra I" in l)
    assert 'class="lever"' not in alg                                                  # no breakdown: no second sentence


def test_the_early_tier_says_it_without_cant(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex/report-card").text
    assert "Best move: Vocabulary (10 pts), worth up to +2.0." in body and "can't" not in body.split('class="lever"')[1][:200]


def test_the_lever_line_is_drawn_in_pencil_under_the_how():
    assert "var(--muted)" not in _rule(".report-card-page .report-line .lever")        # ink: it is the one thing to do
    assert "max-width: var(--measure)" in _rule(".report-card-page .report-line .lever")
```

The `{letter}` placeholder in `gd.zeros_reach`, `gd.reach`, `gd.reach_far`, `gd.keep` and `gd.hold` is the letter **with its article** ("an A", "a B"; `say` capitalises a sentence's first character, so "An A needs…"). `guidance.with_article(letter)` (Task 3) supplies it and `sentence_for` (Task 4) passes `guidance.with_article(g.reach.letter)` / `guidance.with_article(g.slack.letter)` as `letter`; the phrases carry no article of their own. Task 4's `test_sentence_order_...` expectations therefore read `{"letter": "an A", ...}` and `{"letter": "a B", ...}`.

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_report_card.py -k "would_move or without_cant or pencil_under"`
Expected: 3 failed.

- [ ] **Step 3: Route.** In `routes/report_card.py`:

```python
from ..stores import grades, guidance as guidance_store, items
...
    lines = grades.report_card(conn, s, state.sources(), state.settings.grading, state.tz)
    work = items.open_work(conn, s, now=state.now(), rules=state.rules(), prefs=state.sources(), **state.window())
    levers = {}
    for l in lines:
        if l.account is not None:
            course = students.course(conn, l.course_id)
            official = course if course["source"] == l.official_source else (students.course(conn, course["peer_course_id"]) if course["peer_course_id"] else course)
            levers[l.course_id] = guidance_store.sentence_for(guidance_store.for_class(conn, official, l.account, work, state.settings.grading))
    return render(..., levers=levers, ...)
```

(import `students` from `..stores`.) **Template**, after the `.how` line:

```jinja
      {% set said = levers.get(l.course_id) or [] %}
      {% if said %}<p class="lever">{% for key, values in said %}{{ key | say(tier, values) }}{% if not loop.last %} {% endif %}{% endfor %}</p>{% endif %}
```

**CSS**: `.report-card-page .report-line .lever { margin: var(--s1) 0 0; max-width: var(--measure); }`.

- [ ] **Step 4: Run the report card tests and parity**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_report_card.py tests/test_web_tier_parity.py tests/test_web_page_layout.py`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/report_card.py fridgesheet/web/templates/report_card.html fridgesheet/web/static/app.css tests/test_web_report_card.py fridgesheet/guidance.py tests/test_guidance.py fridgesheet/web/stores/guidance.py
git commit -m "The report card line says the best move and the reach: what would move this class's number"
```

---

### Task 6: The class page's "What moves it"

**Files:**
- Modify: `fridgesheet/web/routes/kid.py` (the `course` route), `fridgesheet/web/templates/course.html` (after `</section>` of `.grade-account`, before `{% include "_chart_scripts.html" %}`), `fridgesheet/web/static/app.css`
- Test: `tests/test_web_class_page.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def _moves(body: str) -> str:
    assert 'class="sec what-moves-it"' in body, "no What moves it section"
    return body.split('class="sec what-moves-it"', 1)[1].split("</section>", 1)[0]


def test_what_moves_it_lists_levers_with_worth_badges_under_the_reach_line(tmp_path):
    cid = _course(tmp_path, source="hac")
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "<h3>What moves it</h3>" in sec and '<span class="count">5 levers</span>' in sec
    assert '<p class="lead">An A needs 10 of the next 50 points.' in sec
    assert sec.index("Vocabulary") < sec.index("Participation")                        # worth ties: soonest deadline first
    assert sec.count('<span class="badge">+2.0</span>') == 5
    assert "Not counted yet · accepted until 9/22 · late credit unknown, ask" in sec    # Participation: due 9/08, 14 days, credit "?"
    assert "Due Sat 9/20 · not counted yet" in sec                                        # Reading log


def test_an_unsound_class_lists_points_not_average_points(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'hac' AND short_name = 'Honors English 9'").fetchone()["id"]
    with conn:
        conn.execute("UPDATE grade_observations SET average = 70.0 WHERE course_id = ?", (cid,))     # 44/50 no longer rebuilds it
    conn.close()
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "5 rows still open, 50 points." in sec and 'class="badge">+' not in sec


def test_a_class_with_nothing_open_is_one_sentence(tmp_path):
    cid = _course(tmp_path, short="Algebra I", source="hac")
    conn = seed(tmp_path)
    conn.close()
    sec = _moves(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "<ol" not in sec and ("decides it" in sec or "nothing to rebuild" in sec or "does not rebuild" in sec)
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_class_page.py -k "what_moves or unsound_class or nothing_open"`
Expected: 3 failed, "no What moves it section".

- [ ] **Step 3: Route.** In `kid.py::course`, after `accounts = sorted(...)`:

```python
    work = items.open_work(conn, s, now=now, rules=rules, prefs=prefs, **state.window())
    moves = grade_accounts_guidance.for_class(conn, c if c["source"] == pick else (peer or c), accounts[0], work, state.settings.grading) if accounts else None
    moves_said = grade_accounts_guidance.sentence_for(moves) if moves else []
    lever_views = {v.id: v for v in list(work.fixable) + list(work.upcoming)}
```

with `from ..stores import guidance as grade_accounts_guidance` added to the imports, and pass `moves=moves, moves_said=moves_said, lever_views=lever_views, lever_note=grade_accounts_guidance.lever_note, fmt_worth=guidance.fmt_worth` to `render` (import `from ... import grading, guidance, sources`).

**Template**, after the `.grade-account` section:

```jinja
{# What moves it (spec 2026-10-04 §7.2): the reach or slack line, then the levers as item
   lines ranked by worth, each with its worth badge and its note. Points only when the
   account is not exact. #}
{% if moves is not none %}
<section class="sec what-moves-it" aria-labelledby="moves-head">
  <div class="sec-head"><h3 id="moves-head">{{ 'copy.gd_what_moves_it' | say(acct_tier) }}</h3><span class="count">{% if moves.levers %}{{ moves.levers | length }} lever{{ 's' if moves.levers | length != 1 }}{% endif %}</span></div>
  {% if not moves.sound and moves.levers %}
  <p class="lead">{{ 'gd.not_sound' | say(acct_tier, {'n': moves.levers | length, 'points': fmt_points(moves.levers | sum(attribute='points'))}) }}</p>
  {% elif moves_said %}
  <p class="lead">{% for key, values in moves_said %}{{ key | say(acct_tier, values) }}{% if not loop.last %} {% endif %}{% endfor %}</p>
  {% elif not moves.levers %}
  <p class="lead">{{ 'gd.nothing_posted' | say(acct_tier) }}</p>
  {% endif %}
  {% if moves.levers %}
  <ol class="levers">
  {% for lever in moves.levers if lever.item_id in lever_views %}
    {% set item = lever_views[lever.item_id] %}{% set density = 'line' %}{% set read_only = true %}{% set on_class_page = true %}
    {% set badges = ['+' ~ fmt_worth(lever.worth)] if lever.worth is not none else [] %}
    {% set nk, nv = lever_note(lever, acct_tier) %}{% set says = nk | say(acct_tier, nv) %}
    <li>{% include "_item.html" %}</li>
  {% endfor %}
  </ol>
  {% endif %}
</section>
{% endif %}
```

Check `_item.html`'s `line` density draws `says` (it does for the detail/card; if the line density omits it, pass the note as the line's `word` instead and note the ruling). **CSS**:

```css
/* What moves it (spec 2026-10-04 §7.2): the reach line, then the levers as planner lines. */
.what-moves-it .lead { margin: 0 0 var(--s2); max-width: var(--measure); }
.what-moves-it .levers { list-style: none; margin: 0; padding: 0; }
.what-moves-it .levers > li { border-bottom: 1px solid var(--rule); }
```

- [ ] **Step 4: Run the class page tests and the section/layout tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_class_page.py tests/test_web_section_and_card.py tests/test_web_page_layout.py tests/test_phrasing.py`
Expected: pass. The `.when` word on a read-only line is the sheet's word; the note must appear under it (`says`), not replace it.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/kid.py fridgesheet/web/templates/course.html fridgesheet/web/static/app.css tests/test_web_class_page.py
git commit -m "The class page says what moves it: the reach, then every lever as a planner line with its worth"
```

---

### Task 7: The Must-finish worth badge

**Files:**
- Modify: `fridgesheet/web/routes/checkin.py::_context` (after `work = items.open_work(...)`), `fridgesheet/web/templates/_must_finish.html:47-48`
- Test: `tests/test_web_checkin.py`

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_a_must_finish_row_carries_its_worth_on_the_average(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    tonight = _section(body, "tonight")
    assert "Vocabulary" in tonight and '<span class="badge">+2.0 on the average</span>' in tonight
    early = client_with_grades(tmp_path, Alex=5).get("/kids/Alex/plan").text
    assert '<span class="badge">worth +2.0</span>' in _section(early, "tonight")


def test_a_kid_with_nothing_open_gets_no_badges(tmp_path):
    conn = seed(tmp_path)
    with conn:
        conn.execute("UPDATE item_observations SET state = 'graded', score = 10, missing = 0 WHERE source = 'canvas'")
        conn.execute("UPDATE item_observations SET state = 'graded', score = 10 WHERE source = 'hac'")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    assert "on the average" not in body and body.count('id="must-finish"') == 1
```

(`client_with_grades` is in `tests.web_fixtures`; import it at the file head if absent.)

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_checkin.py -k "worth_on_the_average or nothing_open_gets_no_badges"`
Expected: the first fails (no badge); the second may pass already (keep it: it pins the empty case).

- [ ] **Step 3: Implement.** In `_context`, after `must = items.must_finish(work, now.date(), covered)`:

```python
    worth_by_item = {iid: lever for iid, lever in guidance_store.by_item(conn, student, work, state.sources(), state.settings.grading).items()
                     if lever.worth is not None and lever.worth >= 0.05}
```

(import `from ..stores import guidance as guidance_store` and `from ... import guidance`), and add `worth_by_item=worth_by_item, fmt_worth=guidance.fmt_worth` to the returned context dict. In `_must_finish.html`, after the existing badge line (48):

```jinja
    {% if worth_by_item is defined and view.id in worth_by_item %}{% set badges = badges + [('badge.worth' | say(tier, {'worth': fmt_worth(worth_by_item[view.id].worth)}))] %}{% endif %}
```

- [ ] **Step 4: Run the plan tests, parity, and the printed plan**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_checkin.py tests/test_open_work_parity.py tests/test_web_tier_parity.py tests/test_must_finish.py tests/test_web_plan_steps_everywhere.py tests/test_web_today_planner.py`
Expected: pass (`plan_print.html` shares `_context`, so the printed plan carries the badge too).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/checkin.py fridgesheet/web/templates/_must_finish.html tests/test_web_checkin.py
git commit -m "Every Must-finish row says what it is worth on the class average; the list itself is unchanged"
```

---

### Task 8: MCP `grades()` carries guidance

**Files:**
- Modify: `fridgesheet/server.py` (`grades`, `_hac_account`; a new `_guidance`)
- Test: `tests/test_server_tools.py`

- [ ] **Step 1: Write the failing test** (append; the `graded` fixture's Biology has one scored Labs row and `categories` Labs 44/50)

```python
def test_grades_carries_what_moves_it(graded, monkeypatch):
    monkeypatch.setattr(server._settings(), "sources", sources.DEFAULT)
    bio = {c["course"]: c for c in server.grades("Alex")["classes"]}["Honors Biology S1-2027-Nance"]
    g = bio["guidance"]
    assert g["sound"] and g["letter"] == "B"
    assert g["reach"]["letter"] == "A" and g["levers"] == []           # nothing open in the fixture: reach only
```

Then extend the fixture's Canvas course with one upcoming assignment (`due_at` three days out, 20 points, unsubmitted, group "Labs") and assert `g["levers"][0]["kind"] == "upcoming"` and `g["best"]["points"] == 20.0`.

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_server_tools.py -k what_moves_it`
Expected: `KeyError: 'guidance'`.

- [ ] **Step 3: Implement** in `server.py`:

```python
from . import collector, grading, guidance, late_rules, open_items

def _guidance(h: dict | None, c: dict | None, now: datetime, rules, kid: str, course_name: str, peer: str | None) -> dict | None:
    """guidance.guide over the snapshot: HAC blank rows and Canvas open rows of one class, the
    late rules as the sheet reads them. Flags set in the app are not applied here (as missing_work)."""
    if h is None:
        return None
    account = grading.account_hac(h.get("marking_period_avg"), h.get("categories") or [],
                                  [{"category": r.get("category"), "score": r.get("score"), "points": r.get("points"), "excused": open_items.hac_excused(r)}
                                   for r in (h.get("assignments") or [])])
    rows = []
    for r in h.get("assignments") or []:
        due = open_items.parse_hac_date(r.get("due"), now.tzinfo)
        if r.get("score") is not None or open_items.hac_excused(r) or due is None:
            continue
        late_until = rules.deadline(kid, course_name, due, peer)
        if due < now and now > late_until:
            continue
        rows.append({"item_id": None, "name": r.get("name"), "category": r.get("category"), "points": r.get("points"), "due": due,
                     "late_until": late_until, "credit_text": rules.resolve(kid, course_name, peer).credit,
                     "overdue": due < now, "upcoming": due >= now, "hac_blank": True, "hac_scored": False})
    hac_names = {open_items.norm_name(r.get("name") or "") for r in (h.get("assignments") or [])}
    for a in (c or {}).get("assignments") or []:
        if a.get("score") is not None or a.get("excused") or not a.get("due_at") or open_items.norm_name(a.get("name") or "") in hac_names:
            continue
        due = datetime.fromisoformat(a["due_at"])
        late_until = rules.deadline(kid, course_name, due, peer)
        if due < now and (now > late_until or a.get("state") == "submitted"):
            continue
        rows.append({"item_id": a.get("id"), "name": a.get("name"), "category": a.get("group"), "points": a.get("points_possible"), "due": due,
                     "late_until": late_until, "credit_text": rules.resolve(kid, course_name, peer).credit,
                     "overdue": due < now, "upcoming": due >= now, "hac_blank": False, "hac_scored": False})
    return asdict(guidance.guide(account, rows, _settings().grading))
```

Check `open_items` exports `parse_hac_date` and `norm_name` (`matching.norm_name` otherwise; import from there). In `grades()`, compute `now` and `rules` once (as `_open_work` does), and add `"guidance": _guidance(h or None, c, now, rules, key, c["name"], h.get("name"))` to the Canvas-course dicts and `_guidance(h, None, now, rules, key, name, None)` to the HAC-only ones. Extend the docstring: *"`guidance` is what would move the number (guidance.Guidance): the levers with their worth in average points when `sound`, the reach to the next letter and the slack under this one, from posted work only."*

- [ ] **Step 4: Run the server tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_server_tools.py`
Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/server.py tests/test_server_tools.py
git commit -m "The MCP grades tool carries what moves each class: levers, reach and slack from the same engine"
```

---

### Task 9: Documentation and the whole suite

**Files:**
- Modify: `docs/user-guide.md` (§6.2 Plan, §6.5 Report card), `docs/outcomes.md`, `DESIGN.md` (the report card paragraph), `.impeccable/surfaces/fridgesheet-web-templates-report_card-html.md` and `...course-html.md` (Scope), `docs/product/features/report-card.md`

- [ ] **Step 1: User guide.** In §6.5 after the letter paragraph add:

```markdown
**What moves it.** Under each class's sentence, a second one names the best move and the
distance to the next letter: *Best move: Vocabulary (10 pts), worth up to +2.0. An A needs 10
of the next 50 points.* Three kinds of lever count: blank work HAC already counts as zero (turn
it in and the average rises with nothing added to the total), overdue work still inside the
late window that HAC has not counted yet, and posted work not yet due. A lever is worth its
full points unless your late rule names a percentage ([§13](#late-work-rules)), in which case
the credited worth is shown; work past its late deadline, or answered Too late or Let it go, is
not a lever. "The next N points" means work the school has posted: nothing is guessed about
work not posted yet. When a letter would take more than that, the page says so. On the class
page, **What moves it** lists every lever as a line with its worth and when it is accepted
until. Where HAC's number does not add up from what the app can see, these are points, not
average points.
```

In §6.2 (Plan), add a bullet: `- Every Must-finish row carries what it is worth on the class average (*+2.0 on the average*); the list and its order do not change.` In `docs/outcomes.md`, after the report card sentence: "and says what would move it: which open rows are worth the most and what the next scores must be to reach or keep a letter, from posted work only."

- [ ] **Step 2: DESIGN.md.** In the report card paragraph, after the `.how` sentence: "then, when the account is exact, `.lever` in Ink: the best move and the reach to the next letter (`gd.*`; the early tier never says what cannot be done)." After the class page's section: "then `section.sec.what-moves-it`: the reach or slack line as `.lead`, the levers as read-only planner lines (`_item.html`, line density) each with its worth as a badge and its note as the line's sentence." Add to the component list under the report card: "the worth badge on a Must-finish row (`badge.worth`), the planner's badge style, annotated only."

- [ ] **Step 3: Briefs and feature doc.** Append one sentence to each brief's Scope naming the new line/section and the spec; in `docs/product/features/report-card.md` add a paragraph "What moves it" summarising §2 of the spec and the sound gate.

- [ ] **Step 4: Run the whole suite**

```bash
git add -A docs DESIGN.md .impeccable
env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q -p no:cacheprovider tests/ 2>&1 | tee /tmp/fridgesheet-guidance-suite.log | tail -3
```

Expected: all pass (`test_rebrand` scans every tracked file; `test_user_guide_defects` reads the guide).

- [ ] **Step 5: Commit**

```bash
git add -A docs DESIGN.md .impeccable
git commit -m "Docs: what moves the grade, on the report card, the class page and the Plan"
```

---

### Task 10: Finish the branch

- [ ] **Step 1:** Confirm no commit on the branch carries the skip marker on its own line: `git log --format=%B origin/main..HEAD | grep -n '^\s*\[skip release\]\s*$'` must print nothing.
- [ ] **Step 2:** `git fetch origin && git rebase origin/main`; re-run the whole suite if anything was rebased over.
- [ ] **Step 3:** Push, open the PR against `main` (title in the repo's voice: "What moves the grade: the best move and the reach on every report card line, What moves it on the class page, and each Must-finish row's worth on the average"; body: spec path, the §1 table in prose, the three decisions, the sound gate, follow-ups from spec §11), end the body with the attribution line, and arm auto-merge at once: `gh pr merge <n> --auto --squash`.
- [ ] **Step 4:** Share the PR URL as an artifact.

# Report Card and Grade Account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Report card page per kid (every class on one line with its official average, a letter and one sentence on how it is figured) and a "How it's figured" section on each class page, backed by stored HAC category subtotals and one pure grading module.

**Architecture:** `fridgesheet/grading.py` is a pure module that turns a reported average, HAC's category subtotal rows and the class's assignment rows into an `Account` (lines, rebuilt total, a match check, what the gap is made of) and turns a number into a letter through a `GradeScale`. Schema v10 adds `category_observations` (HAC subtotals per refresh, written on change) and `item_categories` (which category each gradebook files an item under). `web/stores/grades.py` reads those into accounts and report-card lines; a new route renders the page; the class page gains a section; the MCP server's `grades()` tool and the doctor gain the same account.

**Tech Stack:** Python 3.12, FastAPI + Jinja2, SQLite, pytest. Tests run with `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q` from the worktree root (PYTHONPATH shadows the `tests` package otherwise).

**Spec:** `docs/superpowers/specs/2026-10-03-report-card-and-grade-account-design.md`

## Global Constraints

- Schema changes are forward-only migrations, one per version; `SCHEMA_VERSION` goes from 9 to 10 and `tests/test_schedule_fires.py` pins the number twice (lines 15 and 39): update both to 10.
- Every full-page template includes `_page_head.html`, sets `page_title`, writes no `<h2>` of its own, and uses no retired class (`tests/test_web_section_and_card.py::RETIRED` and the template list at line 396); sections are `section.sec` with a `div.sec-head` holding an `h3` and optional `span.count`; quiet folds are `details.sec.quiet > summary > h3`.
- Every `border-radius` and gap in `app.css` is a token or one of the listed exceptions (`test_every_radius_and_gap_is_a_token`).
- A rail link's words are the page title's words exactly: the new tab and title are both `Report card`.
- Every `copy.*`/`rc.*` phrase has all three tiers (`early`, `middle`, `older`), the same `{placeholders}` in every tier, and no digit or time word a tier's `older` phrase lacks (`tests/test_phrasing.py`). Numbers are formatted before they reach a phrase.
- Every tier renders the same rows: the report card gives each class line `id="row-<course_id>"` and `tests/test_web_tier_parity.py` gets the path.
- No tracked file may contain the old product name (`tests/test_rebrand.py`); `git add` new files before running the suite.
- `[skip release]` goes in the commit message of a docs-only commit; this feature's final squash commit is a release.
- Numbers shown to a reader: points as an integer when whole, else two decimals (`grading.fmt_points`); averages always two decimals (`grading.fmt_avg`).
- Match tolerance is one constant, `grading.TOLERANCE = 0.011`.

## Review Focus

1. **A category with zero possible points** (a new HAC category before anything is graded, `0/0`): percent must be `None`, share `0`, no `ZeroDivisionError`, and the row renders "—". Test in Task 1 (`test_a_category_with_nothing_possible_has_no_percent`) and Task 6 (the table prints a dash).
2. **Extra credit above 100** (Latin Quiz 61/60, Band Daily 91/90): percent above 100 renders as is, the letter for a value above the top floor is the top letter. Test in Task 1 (`test_extra_credit_reads_above_a_hundred_and_earns_the_top_letter`).
3. **A HAC class with subtotal rows but no reported average yet** (a class whose header shows no "Marking Period Avg"): `match == "unknown"`, the report card line says `rc.no_grade`, the class page shows the table with the check line "HAC has not posted an average yet". Tests in Task 1 (`test_no_reported_average_is_unknown_not_off`) and Task 4 (`test_a_class_without_an_average_is_still_a_line`).
4. **A Canvas-only course with the grade hidden** (Technology 5th, STEAM): the line is present with "—", `rc.canvas_hidden`; the class page section is one sentence. Tests in Task 4 (`test_a_hidden_canvas_only_course_is_a_line_that_says_so`) and Task 6.
5. **An item folded by `_fold_item`** (the v7 re-key case) must carry its `item_categories` rows to the surviving item without violating the primary key when both have one. Test in Task 2 (`test_fold_item_carries_categories_and_prefers_the_twins`).

---

### Task 1: `grading.py`, the pure account

**Files:**
- Create: `fridgesheet/grading.py`
- Test: `tests/test_grading.py`

**Interfaces:**
- Consumes: nothing in the repo.
- Produces (used by Tasks 4, 5, 8):
  - `grading.Line(category: str, earned: float, possible: float, rows: int, from_rows: bool, share: float)` with property `percent -> float | None`
  - `grading.Account(source, reported, lines, earned, possible, rebuilt, basis, match, zero_points, excused, final, hidden, missing)`
  - `grading.account_hac(reported: float | None, subtotals: list[dict], rows: list[dict]) -> Account` where a subtotal is `{"category", "earned", "possible", "percent"}` as `hac.classwork()` emits and a row is `{"category", "score", "points", "excused"}`
  - `grading.account_canvas(current, final, hidden: bool, rows: list[dict]) -> Account` where a row is `{"group", "score", "points", "excused", "missing", "state"}`
  - `grading.GradeScale(cuts: tuple[tuple[str, float], ...], below: str = "F")` with `letter(value) -> str`; `grading.TEN_POINT`; `grading.scale_from_doc(doc: dict) -> GradeScale`
  - `grading.fmt_points(x) -> str`, `grading.fmt_avg(x) -> str`, `grading.TOLERANCE`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grading.py
"""The account of a class average (spec 2026-10-03 §4), on the household's own numbers.

Every HAC class whose subtotal rows the scraper saw rebuilt to HAC's marking-period average as
straight total points; the module checks that on each class rather than assuming it."""
from __future__ import annotations

import logging

import pytest

from fridgesheet import grading


def _sub(category, earned, possible, percent=""):
    return {"category": category, "earned": earned, "possible": possible, "percent": percent}


def _row(category, score, points, excused=False):
    return {"category": category, "score": score, "points": points, "excused": excused}


# Honors Algebra II, 2026-10-03: two subtotals, 25 points of blank work already counted as zero.
ALGEBRA_SUBS = [_sub("Assessments", 290.66, 400.0, "72.665%"), _sub("Assignments", 78.25, 120.5, "64.937%")]
ALGEBRA_ROWS = [_row("Assessments", 290.66, 400.0), _row("Assignments", 78.25, 95.5),
                _row("Assignments", None, 15.0), _row("Assignments", None, 10.0), _row("Assignments", None, 5.0)]


def test_straight_points_rebuild_matches_hac_within_a_hundredth():
    a = grading.account_hac(70.88, ALGEBRA_SUBS, ALGEBRA_ROWS)
    assert a.basis == "subtotals" and a.match == "exact"
    assert (a.earned, a.possible) == (368.91, 520.5)
    assert round(a.rebuilt, 2) == 70.87
    assert [l.category for l in a.lines] == ["Assessments", "Assignments"]
    assert round(a.lines[0].share, 3) == round(400 / 520.5, 3)


def test_blank_work_counted_as_zero_is_capped_by_the_blank_rows_that_could_explain_it():
    a = grading.account_hac(70.88, ALGEBRA_SUBS, ALGEBRA_ROWS)
    assert a.zero_points == 25.0                      # 120.5 - 95.5 = 25, and 30 points of blanks exist
    fewer_blanks = [r for r in ALGEBRA_ROWS if r["points"] != 10.0]       # only 20 points of blank rows
    assert grading.account_hac(70.88, ALGEBRA_SUBS, fewer_blanks).zero_points == 20.0
    no_rows = grading.account_hac(70.88, ALGEBRA_SUBS, [])
    assert no_rows.zero_points == 0.0                 # rows the scraper never saw are not blank work


def test_a_category_with_rows_but_no_subtotal_row_is_summed_from_the_rows_and_listed_last():
    # Honors Biology: HAC's category table leaves Final Exam out; its rows make the rebuild exact.
    subs = [_sub("Assignments", 9.5, 12.0), _sub("Daily", 88.5, 100.0), _sub("Homework", 22.7, 25.0),
            _sub("Labs", 50.0, 80.0), _sub("Quiz", 95.83, 120.0)]
    rows = [_row("Daily", 88.5, 100.0), _row("Final Exam", 12.0, 12.0), _row("Labs", None, 20.0)]
    a = grading.account_hac(79.81, subs, rows)
    assert a.match == "exact" and round(a.rebuilt, 2) == 79.81
    assert a.lines[-1].category == "Final Exam" and a.lines[-1].from_rows and a.lines[-1].rows == 1
    assert all(not l.from_rows for l in a.lines[:-1])


def test_without_subtotal_rows_the_account_is_built_from_the_rows_and_says_when_it_is_off():
    # Math Plus 5th: HAC shows no category table and the rows do not rebuild its number.
    rows = [_row("Assignments", 38.0, 40.0), _row("Quiz", 11.0, 17.0), _row("Daily", 25.0, 25.0)]
    a = grading.account_hac(86.57, [], rows)
    assert a.basis == "rows" and a.match == "off"
    assert round(a.rebuilt, 2) == 90.24 and a.zero_points == 0.0
    assert all(l.from_rows for l in a.lines) and sum(l.rows for l in a.lines) == 3


def test_excused_rows_are_counted_and_never_summed():
    rows = [_row("Assignments", 28.0, 30.0), _row("Assignments", None, 10.0, excused=True)]
    a = grading.account_hac(93.33, [_sub("Assignments", 28.0, 30.0)], rows)
    assert a.excused == 1 and a.zero_points == 0.0 and a.match == "exact"


def test_nothing_at_all_is_basis_none_and_unknown():
    a = grading.account_hac(None, [], [])
    assert (a.basis, a.match, a.rebuilt, a.lines) == ("none", "unknown", None, ())


def test_no_reported_average_is_unknown_not_off():
    a = grading.account_hac(None, [_sub("Assignments", 28.0, 30.0)], [_row("Assignments", 28.0, 30.0)])
    assert a.match == "unknown" and round(a.rebuilt, 2) == 93.33


def test_a_category_with_nothing_possible_has_no_percent():
    a = grading.account_hac(88.0, [_sub("Assignments", 44.0, 50.0), _sub("Project", 0.0, 0.0)], [])
    assert a.lines[1].percent is None and a.lines[1].share == 0.0 and a.match == "exact"


def test_extra_credit_reads_above_a_hundred_and_earns_the_top_letter():
    a = grading.account_hac(101.67, [_sub("Quiz", 61.0, 60.0)], [_row("Quiz", 61.0, 60.0)])
    assert round(a.lines[0].percent, 2) == 101.67 and a.match == "exact"
    assert grading.TEN_POINT.letter(101.67) == "A"


def test_canvas_account_is_by_group_over_graded_rows_and_carries_final_hidden_and_missing():
    rows = [{"group": "Homework", "score": 68.8, "points": 100.0, "excused": False, "missing": False, "state": "graded"},
            {"group": "Homework", "score": None, "points": 10.0, "excused": False, "missing": True, "state": "unsubmitted"},
            {"group": "Labs", "score": None, "points": 20.0, "excused": False, "missing": True, "state": "unsubmitted"},
            {"group": "Labs", "score": None, "points": 5.0, "excused": True, "missing": False, "state": "unsubmitted"}]
    a = grading.account_canvas(68.8, 51.1, False, rows)
    assert a.source == "canvas" and a.basis == "rows" and a.match == "exact"
    assert [(l.category, l.earned, l.possible, l.rows) for l in a.lines] == [("Homework", 68.8, 100.0, 1)]
    assert (a.final, a.hidden, a.missing, a.excused) == (51.1, False, 2, 1)
    hidden = grading.account_canvas(None, None, True, rows)
    assert hidden.hidden and hidden.match == "unknown"


def test_the_ten_point_scale_at_every_floor_and_on_none():
    s = grading.TEN_POINT
    assert [s.letter(v) for v in (100, 90, 89.99, 80, 79.5, 70, 69, 60, 59.99, 0)] == ["A", "A", "B", "B", "C", "C", "D", "D", "F", "F"]
    assert s.letter(None) == ""


def test_a_scale_from_config_sorts_by_floor_and_allows_plus_and_minus():
    s = grading.scale_from_doc({"grading": {"scale": {"A": 93, "A-": 90, "B+": 87, "B": 83}, "below": "C"}})
    assert s.cuts == (("A", 93.0), ("A-", 90.0), ("B+", 87.0), ("B", 83.0)) and s.below == "C"
    assert [s.letter(v) for v in (95, 91, 88, 83, 50)] == ["A", "A-", "B+", "B", "C"]


def test_a_malformed_grading_section_warns_and_keeps_the_default(caplog):
    with caplog.at_level(logging.WARNING, logger="fridgesheet.grading"):
        assert grading.scale_from_doc({"grading": {"scale": "A B C"}}) == grading.TEN_POINT
        assert grading.scale_from_doc({"grading": {"scale": {"A": "ninety"}}}) == grading.TEN_POINT
    assert "[grading]" in caplog.text
    assert grading.scale_from_doc({}) == grading.TEN_POINT


def test_number_formatting_for_phrases():
    assert grading.fmt_points(25.0) == "25" and grading.fmt_points(368.91) == "368.91" and grading.fmt_points(520.5) == "520.5"
    assert grading.fmt_avg(70.874) == "70.87" and grading.fmt_avg(100.0) == "100.00" and grading.fmt_avg(None) == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_grading.py`
Expected: FAIL at import, `ModuleNotFoundError: No module named 'fridgesheet.grading'`.

- [ ] **Step 3: Write `fridgesheet/grading.py`**

```python
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
            s[0] += float(r["score"]); s[1] += float(pts); s[2] += 1
    ordered: list[tuple[str, float, float, int, bool]] = []
    seen: set[str] = set()
    zero_points = 0.0
    for sub in subtotals:
        cat = sub.get("category") or ""
        earned, possible = float(sub.get("earned") or 0.0), float(sub.get("possible") or 0.0)
        n = scored.get(cat, [0.0, 0.0, 0])
        ordered.append((cat, earned, possible, n[2], False))
        seen.add(cat)
        # How much of HAC's denominator the scored rows do not explain, capped at the blank work
        # that could explain it: a category whose rows the scraper never saw is not blank work.
        zero_points += min(max(0.0, possible - n[1]), blank.get(cat, 0.0))
    for cat, (e, p, n) in scored.items():
        if cat not in seen:
            ordered.append((cat, e, p, n, True))
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
        groups[g][0] += float(r["score"]); groups[g][1] += float(pts); groups[g][2] += 1
    lines = _lines([(g, groups[g][0], groups[g][1], groups[g][2], True) for g in order])
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
    x = float(x)
    if x == int(x):
        return str(int(x))
    s = f"{x:.2f}".rstrip("0")
    return s


def fmt_avg(x) -> str:
    """An average, always two decimals, as HAC prints it."""
    return "" if x is None else f"{float(x):.2f}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_grading.py`
Expected: 15 passed. If `test_straight_points_rebuild_matches_hac_within_a_hundredth` fails on `a.earned == 368.91`, check the `round(..., 2)` on `earned`/`possible` is present.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/grading.py tests/test_grading.py
git commit -m "grading.py: the account of a class average, checked against the gradebook's number rather than assumed"
```

---

### Task 2: Schema version 10

**Files:**
- Modify: `fridgesheet/web/db.py:18` (`SCHEMA_VERSION`), after line 233 (`_SCHEMA_V10`), `_fold_item` at lines 313-339, `migrate` after line 437
- Modify: `tests/test_schedule_fires.py:15,39` (the pinned 9s)
- Test: `tests/test_web_db.py`

**Interfaces:**
- Produces: tables `category_observations(id, refresh_id, course_id, category, earned, possible, percent)` and `item_categories(item_id, source, category)` as in the spec §5, used by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_db.py`)

```python
def test_schema_10_carries_the_category_tables(tmp_path):
    conn = db.open_db(tmp_path)
    assert db.SCHEMA_VERSION == 10
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(category_observations)")}
    assert cols == {"id", "refresh_id", "course_id", "category", "earned", "possible", "percent"}
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(item_categories)")}
    assert cols == {"item_id", "source", "category"}
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='category_observations_course'").fetchone()


def test_a_version_9_file_migrates_to_10(tmp_path):
    conn = db.open_db(tmp_path)
    conn.execute("DROP TABLE category_observations")
    conn.execute("DROP TABLE item_categories")
    conn.execute("UPDATE schema_version SET version = 9")
    assert db.migrate(conn) == 10
    assert conn.execute("SELECT count(*) FROM item_categories").fetchone()[0] == 0


def test_fold_item_carries_categories_and_prefers_the_twins(tmp_path):
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'hac', 'Bio', 'Bio')")
        for iid, key in ((1, "hac:bio:lab"), (2, "hac:bio:lab:2026-09-10")):
            conn.execute("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (?, 1, 1, ?, 'Lab', 1, 1)", (iid, key))
        conn.execute("INSERT INTO item_categories(item_id, source, category) VALUES (1, 'hac', 'Old')")
        conn.execute("INSERT INTO item_categories(item_id, source, category) VALUES (2, 'hac', 'Labs')")
        conn.execute("INSERT INTO item_categories(item_id, source, category) VALUES (2, 'canvas', 'LABS')")
        db._fold_item(conn, 2, into=1)
    rows = conn.execute("SELECT source, category FROM item_categories WHERE item_id = 1 ORDER BY source").fetchall()
    assert [(r["source"], r["category"]) for r in rows] == [("canvas", "LABS"), ("hac", "Labs")]   # the twin's later sighting wins
    assert conn.execute("SELECT count(*) FROM item_categories WHERE item_id = 2").fetchone()[0] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_db.py -k "schema_10 or version_9 or fold_item_carries"`
Expected: 3 failed (`SCHEMA_VERSION == 10` false; no such table).

- [ ] **Step 3: Add the migration**

In `fridgesheet/web/db.py`, change line 18 to `SCHEMA_VERSION = 10`. After `_SCHEMA_V9` (line 233) add:

```python
_SCHEMA_V10 = """
-- HAC's category subtotal rows for one class, as the gradebook showed them at a refresh: what
-- the marking-period average is built from (spec 2026-10-03 §5). A set is written only when it
-- differs from the class's latest set, the way grade_observations is written only when the
-- number moves, so the table is the history of the breakdown and the latest set per course is
-- its state.
CREATE TABLE category_observations (
    id INTEGER PRIMARY KEY,
    refresh_id INTEGER NOT NULL REFERENCES refreshes(id),
    course_id INTEGER NOT NULL REFERENCES courses(id),
    category TEXT NOT NULL,
    earned REAL,
    possible REAL,
    percent TEXT,                    -- as printed ("91.354%"), for diagnostics
    UNIQUE (refresh_id, course_id, category)
);
CREATE INDEX category_observations_course ON category_observations(course_id, refresh_id);
-- Which category (HAC) or assignment group (Canvas) each gradebook files an item under. One
-- row per item and source, overwritten each refresh: a label, not a history. Not a column on
-- item_observations, where a new field rewrites every row on the first refresh after the
-- upgrade and Changes reads the rewrite as the school moving.
CREATE TABLE item_categories (
    item_id INTEGER NOT NULL REFERENCES items(id),
    source TEXT NOT NULL CHECK (source IN ('canvas', 'hac')),
    category TEXT NOT NULL,
    PRIMARY KEY (item_id, source)
);
"""
```

In `migrate`, after the `if v < 9:` block (line 437) add:

```python
    if v < 10:
        conn.executescript("BEGIN;\n" + _SCHEMA_V10 + "\nUPDATE schema_version SET version = 10;\nCOMMIT;")
        v = 10
```

In `_fold_item`, after the `plan_steps` UPDATE (line 331) add:

```python
    # The twin is the later sighting, so its category label wins where both have one.
    conn.execute("DELETE FROM item_categories WHERE item_id = ? AND source IN (SELECT source FROM item_categories WHERE item_id = ?)", (into, src))
    conn.execute("UPDATE item_categories SET item_id = ? WHERE item_id = ?", (into, src))
```

In `tests/test_schedule_fires.py` change both `== 9` to `== 10` (lines 15 and 39).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_db.py tests/test_schedule_fires.py tests/test_migrate.py tests/test_doctor.py`
Expected: all pass (doctor's database probe follows `db.SCHEMA_VERSION`).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/db.py tests/test_web_db.py tests/test_schedule_fires.py
git commit -m "Schema v10: HAC category subtotals per refresh, and which category each gradebook files an item under"
```

---

### Task 3: Ingest writes the categories; the shared fixture carries them

**Files:**
- Modify: `fridgesheet/web/ingest.py` (`IngestResult` lines 34-43, `_observe_grade` area after line 160, the Canvas loop at lines 230-242, the HAC loop at lines 253-330)
- Modify: `tests/web_fixtures.py:73-120` (`snapshot()`)
- Test: `tests/test_web_ingest.py`

**Interfaces:**
- Consumes: Task 2's tables.
- Produces: `IngestResult.categories: int` (subtotal rows written); rows in both tables after `ingest.record`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_ingest.py`; the file's `snapshot(fetched)` builds Alex with one Canvas course of two assignments and one HAC class)

```python
def _with_categories(snap: dict) -> dict:
    snap = copy.deepcopy(snap)
    hac = snap["students"]["Alex"]["hac"]["classes"][0]
    hac["categories"] = [{"category": "Assessments", "earned": 28.0, "possible": 30.0, "percent": "93.333%"},
                         {"category": "Assignments", "earned": 10.0, "possible": 10.0, "percent": "100.000%"}]
    for row in hac["assignments"]:
        row["category"] = "Assessments" if row["name"] == "Quiz 1" else "Assignments"
    return snap


def test_subtotals_are_written_once_and_again_only_when_one_changes(tmp_path):
    conn = db.open_db(tmp_path)
    r1 = ingest.record(conn, _with_categories(snapshot(T1)), tz=TZ, now=T1)
    assert r1.categories == 2
    r2 = ingest.record(conn, _with_categories(snapshot(T2)), tz=TZ, now=T2)
    assert r2.categories == 0                                   # nothing moved: no new set
    moved = _with_categories(snapshot(T2))
    moved["students"]["Alex"]["hac"]["classes"][0]["categories"][0]["earned"] = 29.0
    r3 = ingest.record(conn, moved, tz=TZ, now=T2)
    assert r3.categories == 2                                   # the whole set is rewritten under the new refresh
    sets = conn.execute("SELECT refresh_id, category, earned FROM category_observations ORDER BY id").fetchall()
    assert [(s["refresh_id"], s["category"], s["earned"]) for s in sets] == [
        (r1.refresh_id, "Assessments", 28.0), (r1.refresh_id, "Assignments", 10.0),
        (r3.refresh_id, "Assessments", 29.0), (r3.refresh_id, "Assignments", 10.0)]


def test_each_gradebook_files_an_item_under_its_own_category_name(tmp_path):
    conn = db.open_db(tmp_path)
    ingest.record(conn, _with_categories(snapshot(T1)), tz=TZ, now=T1)
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    rows = conn.execute("SELECT source, category FROM item_categories WHERE item_id = ? ORDER BY source", (quiz,)).fetchall()
    assert [(r["source"], r["category"]) for r in rows] == [("canvas", "Homework"), ("hac", "Assessments")]
    only_hac = conn.execute("SELECT i.id FROM items i JOIN courses c ON c.id = i.course_id WHERE c.source = 'hac'").fetchone()
    if only_hac is not None:       # a HAC-only row carries HAC's name and nothing from Canvas
        got = conn.execute("SELECT source, category FROM item_categories WHERE item_id = ?", (only_hac["id"],)).fetchall()
        assert [(r["source"], r["category"]) for r in got] == [("hac", "Assignments")]


def test_a_category_is_relabelled_in_place_not_appended(tmp_path):
    conn = db.open_db(tmp_path)
    ingest.record(conn, _with_categories(snapshot(T1)), tz=TZ, now=T1)
    renamed = _with_categories(snapshot(T2))
    for row in renamed["students"]["Alex"]["hac"]["classes"][0]["assignments"]:
        row["category"] = "Tests"
    ingest.record(conn, renamed, tz=TZ, now=T2)
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    assert conn.execute("SELECT category FROM item_categories WHERE item_id = ? AND source = 'hac'", (quiz,)).fetchone()["category"] == "Tests"
    assert conn.execute("SELECT count(*) FROM item_categories WHERE item_id = ?", (quiz,)).fetchone()[0] == 2
```

Check the test file's `snapshot()` HAC class (lines 48-60 of `tests/test_web_ingest.py`) actually lists a "Quiz 1" row that pairs with the Canvas "Quiz 1"; if its HAC rows are named differently, use the names it has for `quiz` and the category mapping.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_ingest.py -k "subtotals or own_category_name or relabelled"`
Expected: 3 failed (`IngestResult` has no `categories`; empty tables).

- [ ] **Step 3: Implement in `fridgesheet/web/ingest.py`**

Add to `IngestResult` after `missing`:

```python
    categories: int = 0              # HAC category subtotal rows written (a class's set, when it changed)
```

After `_observe_grade` add:

```python
def _observe_categories(conn, refresh_id: int, course_id: int, subtotals: list[dict]) -> int:
    """Write a HAC class's category subtotal rows under this refresh when the set differs from
    the class's latest set (spec 2026-10-03 §5). Returns the rows written."""
    new = [((s.get("category") or ""), s.get("earned"), s.get("possible")) for s in subtotals or []]
    if not new:
        return 0
    latest_refresh = conn.execute("SELECT MAX(refresh_id) AS r FROM category_observations WHERE course_id = ?", (course_id,)).fetchone()["r"]
    if latest_refresh is not None:
        last = [(r["category"], r["earned"], r["possible"]) for r in conn.execute(
            "SELECT category, earned, possible FROM category_observations WHERE course_id = ? AND refresh_id = ? ORDER BY id",
            (course_id, latest_refresh))]
        if last == new:
            return 0
    for s in subtotals:
        conn.execute("INSERT OR REPLACE INTO category_observations(refresh_id, course_id, category, earned, possible, percent) VALUES (?,?,?,?,?,?)",
                     (refresh_id, course_id, s.get("category") or "", s.get("earned"), s.get("possible"), s.get("percent")))
    return len(new)


def _file_category(conn, item_id: int, source: str, category) -> None:
    """Which category this gradebook files the item under; overwritten each refresh, never a history."""
    if category:
        conn.execute("INSERT OR REPLACE INTO item_categories(item_id, source, category) VALUES (?, ?, ?)", (item_id, source, str(category)))
```

In `record`, add `n_categories = 0` beside the other counters (line 211). In the Canvas loop, right after `n_obs += _observe(conn, refresh_id, item_id, "canvas", _canvas_values(a))` (line 239) add:

```python
                    _file_category(conn, item_id, "canvas", a.get("group"))
```

In the HAC loop, after `n_grades += _observe_grade(conn, refresh_id, hid, h.get("marking_period_avg"), ...)` (line 262) add:

```python
                n_categories += _observe_categories(conn, refresh_id, hid, h.get("categories") or [])
```

After `n_obs += _observe(conn, refresh_id, twin, "hac", _hac_values(row))` (twin branch) add `_file_category(conn, twin, "hac", row.get("category"))`; after the HAC-only `n_obs += _observe(conn, refresh_id, item_id, "hac", _hac_values(row))` add `_file_category(conn, item_id, "hac", row.get("category"))`.

Change the return to pass the count: `IngestResult(refresh_id, n_students, n_courses, n_items, n_obs, n_grades, tuple(...), tuple(...), categories=n_categories)`.

- [ ] **Step 4: Extend the shared fixture** in `tests/web_fixtures.py::snapshot()`:

Alex's HAC "Honors English 9 S1" (currently `"categories": []`): make it

```python
                     "assignments": [_h("Quiz 1", "09/12/2026", 28.0, points=30.0), _h("Participation", "09/08/2026", None)],
                     "categories": [{"category": "Assignments", "earned": 28.0, "possible": 30.0, "percent": "93.333%"},
                                    {"category": "Daily", "earned": 16.0, "possible": 20.0, "percent": "80.000%"}]},
```

(44 of 50 is exactly 88.0, the average every other test already asserts; Daily has no rows, so it is a subtotal-only line; Participation is blank in "Assignments", whose rows explain its 30 points, so `zero_points` is 0.) Leave Algebra I's `"categories": []` (the rows basis with no rows: basis `none`). Sam's Science Canvas grade: change `"final_score": None` to `"final_score": 60.0` so a Canvas account with `final < current` exists.

Then run the whole web suite to see what the fixture change moved: `env -u PYTHONPATH .../python -m pytest -q tests/ -x -q 2>&1 | tail -5`. A test that asserted `final_score` None for Sam (grep `final` in tests/test_web_*.py) is updated to the new value, not deleted.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_ingest.py tests/test_web_stores.py tests/test_web_official_grade.py tests/test_web_class_page.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/ingest.py tests/test_web_ingest.py tests/web_fixtures.py
git commit -m "Ingest keeps HAC's category subtotals and each gradebook's category for every item"
```

---

### Task 4: `stores/grades.py`: accounts and report-card lines from the database

**Files:**
- Create: `fridgesheet/web/stores/grades.py`
- Test: `tests/test_web_grades_store.py`

**Interfaces:**
- Consumes: `grading.account_hac/account_canvas/GradeScale/fmt_*` (Task 1); tables (Task 2); `students.courses`, `students.latest_grades` (`stores/students.py`); `sources.SourcePrefs.resolve(kid, course, peer).grades`, `sources.pick_value`; `dates.wd_md`.
- Produces (used by Tasks 6, 7, 8):
  - `grades.latest_subtotals(conn, course_id) -> list[sqlite3.Row]`
  - `grades.subtotal_history(conn, course_id) -> list[list[sqlite3.Row]]`
  - `grades.hac_rows(conn, course) -> list[dict]`, `grades.canvas_rows(conn, course) -> list[dict]`
  - `grades.account_for(conn, course: sqlite3.Row, grade_row: sqlite3.Row | None) -> grading.Account | None`
  - `grades.how_for(account: grading.Account | None) -> tuple[str, dict]`
  - `grades.ReportLine` and `grades.report_card(conn, student, prefs, scale, tz) -> list[ReportLine]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_grades_store.py
"""Accounts and report-card lines read from the database (spec 2026-10-03 §6)."""
from __future__ import annotations

from zoneinfo import ZoneInfo

from fridgesheet import grading, sources
from fridgesheet.web.stores import grades, students
from tests.web_fixtures import seed

TZ = ZoneInfo("America/New_York")


def _course(conn, short, source):
    return conn.execute("SELECT * FROM courses WHERE short_name = ? AND source = ?", (short, source)).fetchone()


def test_latest_subtotals_are_the_newest_set_in_hacs_order(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    subs = grades.latest_subtotals(conn, eng["id"])
    assert [(s["category"], s["earned"], s["possible"]) for s in subs] == [("Assignments", 28.0, 30.0), ("Daily", 16.0, 20.0)]
    assert grades.subtotal_history(conn, eng["id"]) == [subs]


def test_hac_rows_come_from_the_twin_course_too(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    rows = sorted(grades.hac_rows(conn, eng), key=lambda r: r["name"])
    assert [(r["name"], r["category"], r["score"], r["points"]) for r in rows] == [
        ("Participation", "Assignments", None, 10.0), ("Quiz 1", "Assignments", 28.0, 30.0)]


def test_the_hac_account_rebuilds_the_fixtures_average(tmp_path):
    conn = seed(tmp_path)
    eng = _course(conn, "Honors English 9", "hac")
    s = students.by_key(conn, "Alex")
    a = grades.account_for(conn, eng, students.latest_grades(conn, s["id"]).get(eng["id"]))
    assert a.source == "hac" and a.basis == "subtotals" and a.match == "exact"
    assert (a.reported, a.earned, a.possible) == (88.0, 44.0, 50.0)
    assert [l.rows for l in a.lines] == [1, 0]


def test_the_canvas_account_carries_final_and_missing(tmp_path):
    conn = seed(tmp_path)
    sci = _course(conn, "Science 7", "canvas")
    s = students.by_key(conn, "Sam")
    a = grades.account_for(conn, sci, students.latest_grades(conn, s["id"]).get(sci["id"]))
    assert a.source == "canvas" and (a.reported, a.final, a.missing) == (85.0, 60.0, 1)


def test_report_card_is_one_line_per_class_official_first_with_the_scales_letter(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    lines = grades.report_card(conn, s, sources.DEFAULT, grading.TEN_POINT, TZ)
    by = {l.short_name: l for l in lines}
    assert sorted(by) == ["Algebra I", "Honors English 9"]
    eng = by["Honors English 9"]
    assert (eng.official, eng.official_source, eng.letter) == (88.0, "hac", "B")
    assert eng.course_id == _course(conn, "Honors English 9", "canvas")["id"]        # a paired class links the Canvas page
    assert eng.as_of == "9/11" and eng.account.source == "hac" and eng.other.source == "canvas"
    assert eng.how == ("rc.adds_up", {"earned": "44", "possible": "50"})
    alg = by["Algebra I"]
    assert (alg.official, alg.official_source, alg.letter) == (79.5, "hac", "C")
    assert alg.how == ("rc.no_breakdown", {"reported": "79.50"})                      # no subtotals, no HAC rows


def test_report_card_follows_the_familys_source_choice(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    prefs = sources.DEFAULT.with_default("canvas", "canvas")
    eng = next(l for l in grades.report_card(conn, s, prefs, grading.TEN_POINT, TZ) if l.short_name == "Honors English 9")
    assert (eng.official, eng.official_source, eng.letter) == (91.2, "canvas", "A")
    assert eng.account.source == "canvas"


def test_a_class_without_an_average_is_still_a_line(tmp_path):
    conn = seed(tmp_path)
    with conn:
        conn.execute("UPDATE grade_observations SET average = NULL WHERE course_id = ?", (_course(conn, "Algebra I", "hac")["id"],))
        conn.execute("UPDATE grade_observations SET current = NULL WHERE course_id = ?", (_course(conn, "Algebra I", "canvas")["id"],))
    s = students.by_key(conn, "Alex")
    alg = next(l for l in grades.report_card(conn, s, sources.DEFAULT, grading.TEN_POINT, TZ) if l.short_name == "Algebra I")
    assert (alg.official, alg.letter, alg.how) == (None, "", ("rc.no_grade", {}))


def test_a_hidden_canvas_only_course_is_a_line_that_says_so(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Sam")
    with conn:
        rid = conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('2026-09-15T14:00:00-04:00', '{}', 1)").lastrowid
        cid = conn.execute("INSERT INTO courses(student_id, source, name, short_name) VALUES (?, 'canvas', 'Technology 7-2027-Dunn', 'Technology 7')", (s["id"],)).lastrowid
        conn.execute("INSERT INTO grade_observations(refresh_id, course_id, average, letter, current, final, last_updated) VALUES (?, ?, NULL, NULL, NULL, NULL, NULL)", (rid, cid))
    tech = next(l for l in grades.report_card(conn, s, sources.DEFAULT, grading.TEN_POINT, TZ) if l.short_name == "Technology 7")
    assert tech.official is None and tech.how == ("rc.canvas_hidden", {})


def test_how_for_picks_the_sentence_in_the_specs_order():
    sub = [{"category": "A", "earned": 50.0, "possible": 100.0, "percent": ""}]
    assert grades.how_for(None) == ("rc.no_grade", {})
    assert grades.how_for(grading.account_hac(None, sub, [])) == ("rc.no_grade", {})
    canvas = grading.account_canvas(84.42, 68.94, False, [{"group": "A", "score": 84.42, "points": 100.0, "excused": False, "missing": True, "state": "unsubmitted"}])
    assert grades.how_for(canvas) == ("rc.canvas_partial", {"current": "84.42", "final": "68.94", "missing": "1"})
    zeros = grading.account_hac(50.0, sub, [{"category": "A", "score": 50.0, "points": 75.0, "excused": False}, {"category": "A", "score": None, "points": 25.0, "excused": False}])
    assert grades.how_for(zeros) == ("rc.adds_up_zeros", {"earned": "50", "possible": "100", "zero_points": "25"})
    off_rows = grading.account_hac(86.57, [], [{"category": "A", "score": 74.0, "points": 82.0, "excused": False}])
    assert grades.how_for(off_rows) == ("rc.rows_dont_add_up", {"rebuilt": "90.24", "reported": "86.57", "rows": "1"})
    off = grading.account_hac(79.0, sub, [])
    assert grades.how_for(off) == ("rc.dont_add_up", {"rebuilt": "50.00", "reported": "79.00"})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_grades_store.py`
Expected: FAIL at import (`cannot import name 'grades'`).

- [ ] **Step 3: Write `fridgesheet/web/stores/grades.py`**

```python
"""The account of each class's average, and the report card's lines, read from the database
(spec 2026-10-03 §6). The arithmetic is `fridgesheet.grading`; this module only gathers rows."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ... import dates, grading
from ...sources import pick_value
from . import students


def latest_subtotals(conn: sqlite3.Connection, course_id: int) -> list[sqlite3.Row]:
    """The newest set of HAC category subtotal rows for a course, in HAC's order."""
    return conn.execute(
        """SELECT * FROM category_observations WHERE course_id = ?
           AND refresh_id = (SELECT MAX(refresh_id) FROM category_observations WHERE course_id = ?) ORDER BY id""",
        (course_id, course_id)).fetchall()


def subtotal_history(conn: sqlite3.Connection, course_id: int) -> list[list[sqlite3.Row]]:
    """Every set, oldest first: one list per refresh that changed the breakdown."""
    out: dict[int, list[sqlite3.Row]] = {}
    for r in conn.execute("SELECT * FROM category_observations WHERE course_id = ? ORDER BY refresh_id, id", (course_id,)):
        out.setdefault(r["refresh_id"], []).append(r)
    return list(out.values())


_ROWS = """SELECT i.id, i.name, i.points, o.score, o.excused, o.missing, o.state, ic.category
           FROM items i
           JOIN item_observations o ON o.item_id = i.id AND o.source = :src
             AND o.id = (SELECT o2.id FROM item_observations o2 WHERE o2.item_id = i.id AND o2.source = :src
                         ORDER BY o2.refresh_id DESC, o2.id DESC LIMIT 1)
           LEFT JOIN item_categories ic ON ic.item_id = i.id AND ic.source = :src
           WHERE i.course_id IN (:own, :peer)"""


def hac_rows(conn: sqlite3.Connection, course: sqlite3.Row) -> list[dict]:
    """A HAC course's rows: its own HAC-only items plus the HAC observations hanging on its
    Canvas twin's items (ingest attaches a paired HAC row to the Canvas item)."""
    peer = course["peer_course_id"] if course["peer_course_id"] is not None else -1
    return [{"name": r["name"], "category": r["category"] or "", "score": r["score"], "points": r["points"], "excused": bool(r["excused"])}
            for r in conn.execute(_ROWS, {"src": "hac", "own": course["id"], "peer": peer})]


def canvas_rows(conn: sqlite3.Connection, course: sqlite3.Row) -> list[dict]:
    return [{"name": r["name"], "group": r["category"] or "", "score": r["score"], "points": r["points"],
             "excused": bool(r["excused"]), "missing": bool(r["missing"]), "state": r["state"]}
            for r in conn.execute(_ROWS, {"src": "canvas", "own": course["id"], "peer": -1})]


def account_for(conn: sqlite3.Connection, course: sqlite3.Row, grade_row: sqlite3.Row | None) -> grading.Account:
    """This course's own account: HAC's from its subtotals and rows, Canvas's from its rows."""
    if course["source"] == "hac":
        subs = [{"category": s["category"], "earned": s["earned"], "possible": s["possible"], "percent": s["percent"]}
                for s in latest_subtotals(conn, course["id"])]
        return grading.account_hac(grade_row["average"] if grade_row else None, subs, hac_rows(conn, course))
    current = grade_row["current"] if grade_row else None
    final = grade_row["final"] if grade_row else None
    return grading.account_canvas(current, final, grade_row is not None and current is None and final is None, canvas_rows(conn, course))


def how_for(account: grading.Account | None) -> tuple[str, dict]:
    """The one-line "how" for a report-card line: the phrasing key and its values, chosen in
    the spec's order (§6). Numbers are formatted here, so phrases carry none of their own."""
    if account is None or account.reported is None:
        if account is not None and account.source == "canvas" and account.hidden:
            return "rc.canvas_hidden", {}
        return "rc.no_grade", {}
    a = account
    if a.source == "canvas":
        if a.hidden:
            return "rc.canvas_hidden", {}
        if a.final is not None and a.final < a.reported:
            return "rc.canvas_partial", {"current": grading.fmt_avg(a.reported), "final": grading.fmt_avg(a.final), "missing": str(a.missing)}
    if a.basis == "none":
        return "rc.no_breakdown", {"reported": grading.fmt_avg(a.reported)}
    if a.match == "exact":
        if a.source == "hac" and a.basis == "subtotals" and a.zero_points > 0:
            return "rc.adds_up_zeros", {"earned": grading.fmt_points(a.earned), "possible": grading.fmt_points(a.possible), "zero_points": grading.fmt_points(a.zero_points)}
        return "rc.adds_up", {"earned": grading.fmt_points(a.earned), "possible": grading.fmt_points(a.possible)}
    if a.match == "off":
        if a.source == "hac" and a.basis == "rows":
            return "rc.rows_dont_add_up", {"rebuilt": grading.fmt_avg(a.rebuilt), "reported": grading.fmt_avg(a.reported), "rows": str(sum(l.rows for l in a.lines))}
        return "rc.dont_add_up", {"rebuilt": grading.fmt_avg(a.rebuilt), "reported": grading.fmt_avg(a.reported)}
    return "rc.no_breakdown", {"reported": grading.fmt_avg(a.reported)}


@dataclass(frozen=True)
class ReportLine:
    course_id: int            # the page to link: the Canvas course when paired, else the lone course
    short_name: str
    name: str
    official: float | None
    official_source: str      # "hac" | "canvas" | ""
    letter: str
    as_of: str                # HAC's last_updated without the year, or the refresh day for Canvas
    account: grading.Account | None     # the official source's account
    other: grading.Account | None       # the other source's, when it has a number
    how: tuple[str, dict]


def _as_of(grade_row: sqlite3.Row | None, source: str, conn, tz) -> str:
    if grade_row is None:
        return ""
    if source == "hac":
        return re.sub(r"/\d{4}$", "", grade_row["last_updated"] or "")
    r = conn.execute("SELECT started_at FROM refreshes WHERE id = ?", (grade_row["refresh_id"],)).fetchone()
    return dates.wd_md(datetime.fromisoformat(r["started_at"]).astimezone(tz)) if r else ""


def report_card(conn: sqlite3.Connection, student: sqlite3.Row, prefs, scale: grading.GradeScale, tz) -> list[ReportLine]:
    """One line per class (a Canvas course and its HAC peer are one class), the sheet's order."""
    rows = students.courses(conn, student["id"])
    by_id = {r["id"]: r for r in rows}
    grades = students.latest_grades(conn, student["id"])
    out: list[ReportLine] = []
    seen: set[int] = set()
    for r in rows:
        if r["id"] in seen:
            continue
        peer = by_id.get(r["peer_course_id"]) if r["peer_course_id"] else None
        seen.add(r["id"])
        if peer is not None:
            seen.add(peer["id"])
        canvas = r if r["source"] == "canvas" else peer
        hac = r if r["source"] == "hac" else peer
        canvas_g = grades.get(canvas["id"]) if canvas is not None else None
        hac_g = grades.get(hac["id"]) if hac is not None else None
        pick = prefs.resolve(student["key"], r["name"], peer["name"] if peer else None).grades
        official, src = pick_value(pick, canvas_g["current"] if canvas_g else None, hac_g["average"] if hac_g else None)
        accounts = {}
        if canvas is not None:
            accounts["canvas"] = account_for(conn, canvas, canvas_g)
        if hac is not None:
            accounts["hac"] = account_for(conn, hac, hac_g)
        lead_src = src or (pick if pick in accounts else next(iter(accounts), ""))
        account = accounts.get(lead_src)
        other = next((a for s, a in accounts.items() if s != lead_src and a.reported is not None), None)
        link = canvas if canvas is not None else hac
        out.append(ReportLine(link["id"], link["short_name"], link["name"], official, src or "", scale.letter(official),
                              _as_of(hac_g if lead_src == "hac" else canvas_g, lead_src, conn, tz), account, other, how_for(account)))
    return sorted(out, key=lambda l: l.short_name.lower())
```

Note `rc.no_breakdown` is a key the spec's §6 table did not list: a class with a number but nothing to rebuild from (the fixture's Algebra I, a HAC class whose rows the scraper paired away and that shows no subtotals). The spec's `rc.no_grade` is for no number at all. Record the addition in the spec's §6 table and §8 as part of Task 9.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_grades_store.py`
Expected: 10 passed. If `test_hac_rows_come_from_the_twin_course_too` returns no rows, check that the seed's Quiz 1 HAC row paired to the Canvas item (it does in `test_web_official_grade.py`) and that `_file_category` ran in the twin branch.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/stores/grades.py tests/test_web_grades_store.py
git commit -m "stores/grades: each class's account and the report card's lines, from the database"
```

---

### Task 5: `[grading]` in config.toml

**Files:**
- Modify: `fridgesheet/config.py:259-260` (Settings field), `settings_from_doc` end at line 475
- Test: `tests/test_grading_config.py`

**Interfaces:**
- Consumes: `grading.scale_from_doc`, `grading.TEN_POINT`, `grading.GradeScale`.
- Produces: `Settings.grading: grading.GradeScale`, read by routes as `state.settings.grading`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_grading_config.py
from fridgesheet import config, grading


def test_settings_default_to_the_ten_point_scale(tmp_path):
    assert config.Settings(home=tmp_path).grading == grading.TEN_POINT


def test_a_grading_section_sets_the_scale_and_survives_a_reload(tmp_path):
    (tmp_path / "config.toml").write_text('[grading]\nscale = { A = 93, "A-" = 90, B = 83 }\nbelow = "C"\n', encoding="utf-8")
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(config.load_config_doc(tmp_path / "config.toml"), s)
    assert s.grading.cuts == (("A", 93.0), ("A-", 90.0), ("B", 83.0)) and s.grading.letter(85) == "B" and s.grading.letter(10) == "C"


def test_a_bad_grading_section_keeps_the_default_without_raising(tmp_path):
    (tmp_path / "config.toml").write_text('[grading]\nscale = "ten"\n', encoding="utf-8")
    s = config.Settings(home=tmp_path)
    config.settings_from_doc(config.load_config_doc(tmp_path / "config.toml"), s)
    assert s.grading == grading.TEN_POINT
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_grading_config.py`
Expected: `AttributeError: 'Settings' object has no attribute 'grading'`.

- [ ] **Step 3: Implement**

In `fridgesheet/config.py`, next to the `sources` import (line 38) add `from . import grading as _grading`. In `Settings`, after the `sources` field (line 260) add:

```python
    #: [grading]: the letter for an average on the report card (grading.GradeScale); the
    #: ten-point scale unless config.toml says otherwise.
    grading: "_grading.GradeScale" = field(default_factory=lambda: _grading.TEN_POINT)
```

At the end of `settings_from_doc`, after `s.sources = _sources.from_doc(doc)` (line 475) add:

```python
    s.grading = _grading.scale_from_doc(doc)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_grading_config.py tests/test_config.py`
Expected: pass (if `tests/test_config.py` does not exist, run `tests/ -k config`).

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/config.py tests/test_grading_config.py
git commit -m "[grading] scale in config.toml: the report card's letters, ten-point unless told otherwise"
```

---

### Task 6: The class page's "How it's figured" section

**Files:**
- Modify: `fridgesheet/web/phrasing.py` (new keys inside `PHRASES`, after `copy.sources_hint` at line 129)
- Modify: `fridgesheet/web/routes/kid.py:161-215` (`course` route context)
- Modify: `fridgesheet/web/templates/course.html` (after `</section>` of `.grade-record`, line 53)
- Modify: `fridgesheet/web/static/app.css` (after the `.class-record` rules, line 1058)
- Test: `tests/test_web_class_page.py`

**Interfaces:**
- Consumes: `grades.account_for`, `grades.how_for` (Task 4); `state.settings.grading` (Task 5); `grading.fmt_points/fmt_avg`.
- Produces: phrasing keys `rc.*` and `copy.rc_*` (Task 7 reuses them); template context `account`, `other_account`, `scale_letter`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_class_page.py`)

```python
def _account_section(body: str) -> str:
    assert 'class="sec grade-account"' in body, "no How it's figured section"
    return body.split('class="sec grade-account"', 1)[1].split("</section>", 1)[0]


def test_how_its_figured_shows_hacs_categories_their_share_and_the_check(tmp_path):
    cid = _course(tmp_path, source="hac")
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    sec = _account_section(body)
    assert "<h3>How it&#39;s figured</h3>" in sec or "<h3>How it's figured</h3>" in sec
    assert '<span class="count">2 categories</span>' in sec
    assert '<div class="table-wrap"><table class="categories">' in sec.replace("\n", "")
    assert re.search(r"<td>Assignments</td>\s*<td>28</td>\s*<td>30</td>\s*<td>93\.33%</td>\s*<td>60%</td>", sec)
    assert re.search(r"<td>Daily</td>\s*<td>16</td>\s*<td>20</td>\s*<td>80\.00%</td>\s*<td>40%</td>", sec)
    assert re.search(r"<tfoot>.*<td>Total</td>\s*<td>44</td>\s*<td>50</td>\s*<td>88\.00%</td>", sec, re.S)
    assert re.search(r'<p class="check ok">✓ Adds up: 44 of 50 points\. HAC says 88\.00\.</p>', sec)


def test_the_twins_page_leads_with_the_official_account_and_says_what_canvas_counts(tmp_path):
    cid = _course(tmp_path, source="canvas")
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert sec.index("<h4>HAC</h4>") < sec.index("<h4>Canvas</h4>")                   # official first, whatever page it is
    assert "Canvas counts graded work only" in sec or "Canvas current 91.20" in sec


def test_a_class_with_no_breakdown_is_one_sentence(tmp_path):
    cid = _course(tmp_path, short="Algebra I", source="hac")
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert "<table" not in sec
    assert "HAC says 79.50" in sec and "nothing to rebuild it from" in sec


def test_a_category_with_nothing_possible_prints_a_dash(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'hac' AND short_name = 'Honors English 9'").fetchone()["id"]
    rid = conn.execute("SELECT MAX(refresh_id) FROM category_observations").fetchone()[0]
    with conn:
        conn.execute("INSERT INTO category_observations(refresh_id, course_id, category, earned, possible, percent) VALUES (?, ?, 'Project', 0, 0, '')", (rid, cid))
    conn.close()
    sec = _account_section(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert re.search(r"<td>Project</td>\s*<td>0</td>\s*<td>0</td>\s*<td>—</td>\s*<td>0%</td>", sec)


def test_the_account_is_drawn_in_the_planners_rules():
    for sel in (".grade-account table.categories", ".grade-account .check", ".grade-account .check.off"):
        _rule(sel)
    assert "var(--warn)" in _rule(".grade-account .check.off")                     # off is the one red the planner allows
    assert "text-align: right" in _rule(".grade-account table.categories td + td")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_class_page.py -k "figured or twins_page_leads or no_breakdown or nothing_possible or planners_rules"`
Expected: 5 failed, "no How it's figured section".

- [ ] **Step 3: Add the phrases** to `PHRASES` in `fridgesheet/web/phrasing.py` (after `copy.sources_hint`):

```python
    # --- the report card and the account of an average (spec 2026-10-03 §6, §8) --------------
    "rc.no_grade":          {"early": "No average yet.", "middle": "No average yet.", "older": "No average yet."},
    "rc.no_breakdown":      {"early": "HAC says {reported}. We can't see what it's made of.",
                             "middle": "HAC says {reported}; there is nothing to rebuild it from.",
                             "older": "HAC says {reported}; there is nothing to rebuild it from."},
    "rc.canvas_hidden":     {"early": "Canvas hides this class's grade.", "middle": "Canvas hides this class's grade.", "older": "Canvas hides this class's grade."},
    "rc.canvas_partial":    {"early": "Canvas only counts graded work: {current} now, {final} if the {missing} missing stay at zero.",
                             "middle": "Canvas counts graded work only: {current} now, {final} if the {missing} missing stay at zero.",
                             "older": "Canvas counts graded work only: {current} now, {final} if the {missing} missing stay at zero."},
    "rc.adds_up":           {"early": "Your points: {earned} out of {possible}.", "middle": "Adds up: {earned} of {possible} points.", "older": "Adds up: {earned} of {possible} points."},
    "rc.adds_up_zeros":     {"early": "Your points: {earned} out of {possible}. {zero_points} points of blank work count as zero.",
                             "middle": "Adds up: {earned} of {possible} points. {zero_points} points of unscored work count as zero.",
                             "older": "Adds up: {earned} of {possible} points. {zero_points} points of unscored work count as zero."},
    "rc.rows_dont_add_up":  {"early": "HAC says {reported}. The {rows} graded rows we can see add up to {rebuilt}. Ask your teacher how it's figured.",
                             "middle": "HAC says {reported}; the {rows} scored rows we can see add up to {rebuilt}. HAC may weight categories or count work we can't see.",
                             "older": "HAC says {reported}; the {rows} scored rows we can see add up to {rebuilt}. HAC may weight categories or count work we cannot see."},
    "rc.dont_add_up":       {"early": "The categories add up to {rebuilt}. HAC says {reported}. Ask your teacher how it's figured.",
                             "middle": "The categories add up to {rebuilt}; HAC says {reported}.",
                             "older": "The categories add up to {rebuilt}; HAC says {reported}."},
    "copy.rc_hac_says":     {"early": "HAC says {reported}.", "middle": "HAC says {reported}.", "older": "HAC says {reported}."},
    "copy.rc_hac_no_avg":   {"early": "HAC hasn't posted an average yet.", "middle": "HAC has not posted an average yet.", "older": "HAC has not posted an average yet."},
    "copy.rc_lead_hac":     {"early": "HAC adds up every point you earned and divides by every point possible, in all categories.",
                             "middle": "HAC's marking-period average is total points: everything earned over everything possible, across all categories.",
                             "older": "HAC's marking-period average is total points: everything earned over everything possible, across all categories."},
    "copy.rc_lead_hac_rows": {"early": "HAC didn't show a category table for this class, so this is added up from the rows we can see.",
                              "middle": "HAC showed no category table for this class; this is summed from the rows we can see.",
                              "older": "HAC showed no category table for this class; this is summed from the rows we can see."},
    "copy.rc_lead_from_rows": {"early": "A row marked from the rows is a category HAC's table leaves out.",
                               "middle": "A line marked from the rows is a category HAC's own table leaves out.",
                               "older": "A line marked from the rows is a category HAC's own table leaves out."},
    "copy.rc_lead_canvas":  {"early": "Canvas only counts work that's been graded.", "middle": "Canvas counts graded work only.", "older": "Canvas counts graded work only."},
    "copy.rc_excused":      {"early": "{excused} excused rows don't count.", "middle": "{excused} excused rows never count.", "older": "{excused} excused rows never count."},
    "copy.rc_unscored":     {"early": "{zero_points} points of blank work count as zero so far.", "middle": "{zero_points} points of unscored work count as zero so far.", "older": "{zero_points} points of unscored work count as zero so far."},
    "copy.rc_from_rows":    {"early": "from the rows", "middle": "from the rows", "older": "from the rows"},
    "copy.rc_share":        {"early": "Share of the grade", "middle": "Share of the grade", "older": "Share of the grade"},
    "copy.rc_no_grade_either": {"early": "No grade yet from either gradebook.", "middle": "No grade yet from either gradebook.", "older": "No grade yet from either gradebook."},
```

Run `pytest -q tests/test_phrasing.py` and fix any tier that invents a number or drops a placeholder before going on.

- [ ] **Step 4: Extend the route** in `fridgesheet/web/routes/kid.py::course`. Add `from ..stores import grades as grade_accounts` to the imports (the module already imports `students`, `items`, `notes`, `trends` from `..stores`). Before the `return render(...)` add:

```python
    # How the average is figured (spec 2026-10-03 §7.2): this course's own account and the
    # twin's, the official source's first whichever page this is.
    account = grade_accounts.account_for(conn, c, grades.get(course_id))
    other_account = grade_accounts.account_for(conn, peer, grades.get(peer["id"])) if peer else None
    accounts = sorted([a for a in (account, other_account) if a is not None], key=lambda a: a.source != pick)
```

and pass `accounts=accounts, how_for=grade_accounts.how_for, fmt_points=grading.fmt_points, fmt_avg=grading.fmt_avg` in the `render` call (add `from ... import grading` to the imports; the route file imports `from ... import sources` already, follow that form).

- [ ] **Step 5: Add the section** to `course.html` after line 53 (`</section>` closing `.grade-record`), before `{% include "_chart_scripts.html" %}`:

```jinja
{# How the average is figured (spec 2026-10-03 §7.2): the official gradebook's account first,
   the other's beneath under its name. HAC's is its category table with each category's share
   of the grade and the check against HAC's number; Canvas's is a sentence unless Canvas is the
   official source. Off is the one Red Pen on the page: the school's record and what we see disagree. #}
{% set tier = student.key | tier_of %}
{% set n_cats = accounts[0].lines | length if accounts else 0 %}
<section class="sec grade-account" aria-labelledby="account-head">
  <div class="sec-head"><h3 id="account-head">How it's figured</h3><span class="count">{% if n_cats %}{{ n_cats }} categor{{ 'y' if n_cats == 1 else 'ies' }}{% endif %}</span></div>
  {% if not accounts or accounts | map(attribute='reported') | reject('none') | list | length == 0 and accounts | map(attribute='lines') | map('length') | sum == 0 %}
  <p class="muted">{{ 'copy.rc_no_grade_either' | say(tier) }}</p>
  {% else %}
  {% for a in accounts %}
  {% set key, values = how_for(a) %}
  {% if accounts | length > 1 %}<h4>{{ SOURCE_LABELS[a.source] }}</h4>{% endif %}
  {% if a.basis == 'none' %}
  <p class="check">{% if a.source == 'hac' %}{{ 'rc.no_breakdown' | say(tier, {'reported': fmt_avg(a.reported)}) if a.reported is not none else 'copy.rc_hac_no_avg' | say(tier) }}{% else %}{{ key | say(tier, values) }}{% endif %}</p>
  {% elif loop.first or a.source == 'hac' %}
  <p class="lead">{{ ('copy.rc_lead_hac_rows' if a.basis == 'rows' else 'copy.rc_lead_hac') | say(tier) if a.source == 'hac' else 'copy.rc_lead_canvas' | say(tier) }}{% if a.lines | selectattr('from_rows') | list and a.basis == 'subtotals' %} {{ 'copy.rc_lead_from_rows' | say(tier) }}{% endif %}</p>
  <div class="table-wrap"><table class="categories">
    <thead><tr><th>Category</th><th>Earned</th><th>Possible</th><th>Percent</th><th>{{ 'copy.rc_share' | say(tier) }}</th></tr></thead>
    <tbody>
    {% for l in a.lines %}
    <tr{% if l.from_rows and a.basis == 'subtotals' %} class="from-rows"{% endif %}><td>{{ l.category }}{% if l.from_rows and a.basis == 'subtotals' %} <span class="muted">{{ 'copy.rc_from_rows' | say(tier) }}</span>{% endif %}</td>
      <td>{{ fmt_points(l.earned) }}</td><td>{{ fmt_points(l.possible) }}</td><td>{% if l.percent is none %}—{% else %}{{ fmt_avg(l.percent) }}%{% endif %}</td><td>{{ (l.share * 100) | round | int }}%</td></tr>
    {% endfor %}
    </tbody>
    <tfoot><tr><td>Total</td><td>{{ fmt_points(a.earned) }}</td><td>{{ fmt_points(a.possible) }}</td><td>{% if a.rebuilt is none %}—{% else %}{{ fmt_avg(a.rebuilt) }}%{% endif %}</td><td></td></tr></tfoot>
  </table></div>
  {% if a.reported is none %}
  <p class="check">{{ ('copy.rc_hac_no_avg' if a.source == 'hac' else 'rc.canvas_hidden') | say(tier) }}</p>
  {% elif a.match == 'exact' %}
  <p class="check ok">✓ {{ ('rc.adds_up' | say(tier, {'earned': fmt_points(a.earned), 'possible': fmt_points(a.possible)})) }} {{ ('copy.rc_hac_says' | say(tier, {'reported': fmt_avg(a.reported)})) if a.source == 'hac' else '' }}</p>
  {% else %}
  <p class="check off">{{ key | say(tier, values) }}</p>
  {% endif %}
  {% if a.source == 'hac' and (a.zero_points > 0 or a.excused) %}
  <p class="check-detail muted">{% if a.zero_points > 0 %}{{ 'copy.rc_unscored' | say(tier, {'zero_points': fmt_points(a.zero_points)}) }} {% endif %}{% if a.excused %}{{ 'copy.rc_excused' | say(tier, {'excused': a.excused}) }}{% endif %}</p>
  {% endif %}
  {% else %}
  <p class="check">{{ key | say(tier, values) if key != 'rc.adds_up' else 'copy.rc_lead_canvas' | say(tier) ~ ' Canvas current ' ~ fmt_avg(a.reported) ~ '.' }}</p>
  {% endif %}
  {% endfor %}
  {% endif %}
</section>
```

The `{% set tier %}` must come before `_chart_scripts.html`; `SOURCE_LABELS` is already in the context from `source_ctx`. The "off" branch of a Canvas-second account falls into the last `{% else %}` and reads `rc.canvas_partial` or `rc.dont_add_up` as one sentence.

- [ ] **Step 6: Add the CSS** after line 1058 (`.class-record .notes`):

```css
/* How it's figured (spec 2026-10-03 §7.2): the category table flat on the page, numbers right,
   the check line in ink with a ✓, or in Red Pen when the school's number and ours disagree. */
.grade-account .lead { margin: 0 0 var(--s2); color: var(--muted); max-width: var(--measure); }
.grade-account h4 { margin: var(--s3) 0 var(--s1); font-size: var(--type-small); font-weight: 650; letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
.grade-account table.categories { border-collapse: collapse; min-width: 28em; }
.grade-account table.categories th, .grade-account table.categories td { padding: 4px 8px; border-bottom: 1px solid var(--rule); text-align: left; }
.grade-account table.categories th + th, .grade-account table.categories td + td { text-align: right; }
.grade-account table.categories tfoot td { font-weight: 650; border-bottom: 0; }
.grade-account table.categories tr.from-rows td { color: var(--muted); }
.grade-account .check { margin: var(--s2) 0 0; max-width: var(--measure); }
.grade-account .check.off { color: var(--warn); }
.grade-account .check-detail { margin: 0; font-size: var(--type-small); max-width: var(--measure); }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_class_page.py tests/test_phrasing.py tests/test_web_section_and_card.py tests/test_web_page_layout.py`
Expected: all pass. If `test_how_its_figured_...` fails on the ✓ line, print `sec` and align the regex to the exact whitespace the template emits rather than loosening the assertion's words.

- [ ] **Step 8: Commit**

```bash
git add fridgesheet/web/phrasing.py fridgesheet/web/routes/kid.py fridgesheet/web/templates/course.html fridgesheet/web/static/app.css tests/test_web_class_page.py
git commit -m "The class page says how its average is figured: HAC's categories with their share of the grade, the total, and whether it adds up"
```

---

### Task 7: The Report card page and its two navigations

**Files:**
- Create: `fridgesheet/web/routes/report_card.py`, `fridgesheet/web/templates/report_card.html`
- Modify: `fridgesheet/web/app.py:731-732` (router tuple), `fridgesheet/web/templates/base.html:34-36` (kid nav), `fridgesheet/web/templates/_child_nav.html:3-5`, `fridgesheet/web/static/app.css`, `fridgesheet/web/phrasing.py`
- Modify: `tests/test_web_tier_parity.py:27` (paths), `tests/test_web_checkin.py:576` (the tab tuple, if it asserts the full list)
- Test: `tests/test_web_report_card.py`

**Interfaces:**
- Consumes: `grades.report_card` (Task 4), `state.settings.grading` (Task 5), `rc.*` phrases (Task 6).
- Produces: `GET /kids/{key}/report-card`, `workspace == "report"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_report_card.py
"""The report card (spec 2026-10-03 §7.1): every class one ruled line with the official number,
the scale's letter, whose number in pencil, and one sentence on how it is figured; a fourth
tab on the kid's rail and in the grown-up's child nav; prints as it stands."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web import app as webapp
from tests.web_fixtures import app_for, client_with_grades, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _lines(body: str) -> list[str]:
    return re.findall(r'<li class="report-line"[^>]*>(.*?)</li>', body, re.S)


def test_one_line_per_class_with_number_letter_whose_and_how(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert '<h2>Report card <span class="subtitle">Alex' in body
    assert '<span class="count">2 classes</span>' in body
    lines = _lines(body)
    assert len(lines) == 2
    eng = next(l for l in lines if "Honors English 9" in l)
    assert re.search(r'<span class="big">88\.00</span>\s*<span class="letter">B</span>', eng)
    assert '<p class="whose">HAC average · as of 9/11</p>' in eng
    assert '<p class="how">Adds up: 44 of 50 points.</p>' in eng
    cid = seed(tmp_path).execute("SELECT id FROM courses WHERE source='canvas' AND short_name='Honors English 9'").fetchone()["id"]
    assert f'href="/kids/Alex/courses/{cid}"' in eng                      # a paired class links the Canvas page


def test_a_class_without_a_number_is_a_line_with_a_dash(tmp_path):
    conn = seed(tmp_path)
    with conn:
        conn.execute("UPDATE grade_observations SET average = NULL, current = NULL")
    conn.close()
    lines = _lines(app_for(tmp_path).get("/kids/Alex/report-card").text)
    assert len(lines) == 2 and all('<span class="big">—</span>' in l and "No average yet." in l for l in lines)


def test_every_line_has_a_row_id_so_tiers_can_be_compared(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert len(re.findall(r'<li class="report-line" id="row-\d+"', body)) == 2


def test_the_how_is_said_in_the_kids_tier(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex/report-card").text
    assert "Your points: 44 out of 50." in body


def test_the_fold_explains_how_averages_are_figured(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert re.search(r'<details class="sec quiet how-figured">\s*<summary><h3>How averages are figured</h3>', body)
    assert "total points" in body and "graded work only" in body


def test_report_card_is_the_fourth_tab_in_both_shells(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/kids/Alex/report-card").text
    nav = re.search(r'<nav class="child-nav".*?</nav>', body, re.S).group(0)
    assert nav.index(">Assignments<") < nav.index('aria-current="page">Report card<')
    kid = app_for(tmp_path)
    kid.cookies.set(webapp.WHO_COOKIE, "Alex")
    rail = re.search(r'<nav class="kid">.*?</nav>', kid.get("/kids/Alex/report-card").text, re.S).group(0)
    assert rail.index('href="/kids/Alex"') < rail.index('href="/kids/Alex/report-card" class="current">Report card</a>') < rail.index('<details class="rail-more"')


def test_the_page_prints_its_lines_and_the_print_button_is_the_pages_only_action(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert '<p class="page-actions"><button type="button" data-print>Print</button></p>' in body
    assert body.count("<h2>") == 1


def test_an_unknown_kid_is_404(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).get("/kids/Nobody/report-card").status_code == 404


def test_the_lines_are_drawn_in_the_planners_rules():
    for sel in (".report-card-page .report-lines", ".report-card-page .report-line", ".report-card-page .report-line .big", ".report-card-page .report-line .whose"):
        _rule(sel)
    assert "border-bottom: 1px solid var(--rule)" in _rule(".report-card-page .report-line")
```

Add `"/kids/Alex/report-card"` to the `path` parametrize list in `tests/test_web_tier_parity.py:27`. Check `tests/test_web_checkin.py:576`: if it asserts the child nav's full tab list, add `("/kids/Alex/report-card", "Report card")`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_report_card.py`
Expected: 9 failed (404 on the route, no CSS rules).

- [ ] **Step 3: The route** `fridgesheet/web/routes/report_card.py`:

```python
"""The report card (spec 2026-10-03 §7.1): a kid's classes, one line each, the official
average with the scale's letter and one sentence on how the gradebook arrived at it."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ... import grading
from ..app import Db, State, render, student_or_404
from ..stores import grades

router = APIRouter()


@router.get("/kids/{key}/report-card")
def page(key: str, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    lines = grades.report_card(conn, s, state.sources(), state.settings.grading, state.tz)
    return render(request, conn, "report_card.html", current=f"kid:{key}", workspace="report", student=s, lines=lines,
                  n_lines=len(lines), fmt_avg=grading.fmt_avg)
```

Register it in `app.py`: add `report_card as report_card_routes` to the `from .routes import ...` line and `report_card_routes.router` to the tuple after `kid.router`.

- [ ] **Step 4: The template** `fridgesheet/web/templates/report_card.html`:

```jinja
{% extends "base.html" %}
{% block title %}Report card · {{ student.key | nickname }} · Fridge Sheet{% endblock %}
{% block content %}
{# The report card (the Student Planner; spec 2026-10-03 §7.1): every class one ruled line, the
   class's name a link to its page, the official number at Display size with the scale's letter,
   whose number in pencil, and one sentence on how it is figured in the kid's words. The one
   fold beneath says how the two gradebooks figure an average. It prints as it stands. #}
{% set tier = student.key | tier_of %}
{% set page_crumb = student.key | nickname %}{% set page_crumb_href = "/kids/" ~ (student.key | urlencode) %}
{% set page_title = "Report card" %}{% set page_subtitle = (student.key | nickname) ~ " · marking period so far" %}
{% set page_actions %}<button type="button" data-print>Print</button>{% endset %}
{% include "_page_head.html" %}
{% include "_child_nav.html" %}
<div class="planner-main report-card-page">
<section class="sec report-lines" aria-labelledby="classes-head">
  <div class="sec-head"><h3 id="classes-head">Classes</h3><span class="count">{{ n_lines }} class{{ 'es' if n_lines != 1 }}</span></div>
  <ol class="report-lines">
  {% for l in lines %}
    <li class="report-line" id="row-{{ l.course_id }}">
      <p class="head"><a class="class" href="/kids/{{ student.key | urlencode }}/courses/{{ l.course_id }}">{{ l.short_name }}</a>
        <span class="avg"><span class="big">{% if l.official is none %}—{% else %}{{ fmt_avg(l.official) }}{% endif %}</span>{% if l.letter %} <span class="letter">{{ l.letter }}</span>{% endif %}</span></p>
      {% if l.official_source %}<p class="whose">{{ 'HAC average' if l.official_source == 'hac' else 'Canvas current' }}{% if l.as_of %} · as of {{ l.as_of }}{% endif %}</p>{% endif %}
      <p class="how">{{ l.how[0] | say(tier, l.how[1]) }}</p>
    </li>
  {% else %}
    <li class="report-line empty"><p class="muted">No classes yet.</p></li>
  {% endfor %}
  </ol>
</section>
<details class="sec quiet how-figured">
  <summary><h3>How averages are figured</h3></summary>
  <p>{{ 'copy.rc_how_hac' | say(tier) }}</p>
  <p>{{ 'copy.rc_how_canvas' | say(tier) }}</p>
</details>
</div>
{% endblock %}
```

`_child_nav.html` reads `workspace`, `last_check`, `done_so_far`; on this page `workspace == 'report'` takes neither `tab-hint` branch except the `{% elif last_check %}` one, which reads an undefined `last_check` as false. Confirm the include renders without error; if it raises on `today` or `done_so_far`, wrap its hint block in `{% if workspace in ('all', 'checkin', 'plan') %}`.

Add to `PHRASES` (after `copy.rc_no_grade_either`):

```python
    "copy.rc_how_hac":      {"early": "HAC adds up every point you earned and divides by every point possible, in every category. Blank work counts as zero once the teacher enters it. Excused work never counts.",
                             "middle": "HAC's average is total points: everything earned over everything possible, across every category. Unscored work counts as zero once the teacher enters it; excused work never counts.",
                             "older": "HAC's marking-period average is total points: everything earned over everything possible, across every category. Unscored work counts as zero once the teacher enters it; excused work never counts."},
    "copy.rc_how_canvas":   {"early": "Canvas only counts graded work. Its other number is what you'd have if missing work stays missing. Some teachers hide it.",
                             "middle": "Canvas counts graded work only. Its final is what the grade would be if missing work stays at zero. Some teachers hide the grade.",
                             "older": "Canvas counts graded work only; its final is the grade if missing work stays at zero. Some teachers hide the grade entirely."},
```

- [ ] **Step 5: The navigations.** In `base.html`, after the Assignments link (line 35) add:

```jinja
      <a href="/kids/{{ me | urlencode }}/report-card" class="{{ 'current' if current == 'kid:' ~ me and workspace is defined and workspace == 'report' }}">Report card</a>
```

In `_child_nav.html`, after the Assignments link (line 5) add:

```jinja
  <a href="/kids/{{ student.key | urlencode }}/report-card" {{ 'aria-current="page"' | safe if workspace == 'report' }}>Report card</a>
```

- [ ] **Step 6: The CSS**, after the `.grade-account` rules from Task 6:

```css
/* The report card (spec 2026-10-03 §7.1): every class one ruled line under a hairline, the
   name at the left, the number at Display size with its letter at the right, whose number and
   the one-line how in pencil beneath. The fold is the page's only prose. */
.report-card-page { max-width: 1100px; padding-bottom: var(--s4); }
.report-card-page .report-lines { list-style: none; margin: 0; padding: 0; }
.report-card-page .report-line { padding: var(--s2) 0; border-bottom: 1px solid var(--rule); }
.report-card-page .report-line .head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: var(--s1) var(--s3); margin: 0; }
.report-card-page .report-line .class { font-weight: 650; text-decoration: none; }
.report-card-page .report-line .big { font-size: calc(var(--type-root) * 1.75); font-weight: 600; }
.report-card-page .report-line .letter { font-weight: 400; margin-left: var(--s1); }
.report-card-page .report-line .whose { margin: 0; font-size: var(--type-small); color: var(--muted); }
.report-card-page .report-line .how { margin: var(--s1) 0 0; max-width: var(--measure); }
.report-card-page > details.sec.quiet { margin: var(--s4) 0 0; }
.report-card-page .how-figured p { max-width: var(--measure); }
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_web_report_card.py tests/test_web_tier_parity.py tests/test_web_shell.py tests/test_web_who.py tests/test_web_words_nav.py tests/test_web_checkin.py tests/test_web_page_layout.py tests/test_web_section_and_card.py tests/test_phrasing.py`
Expected: all pass. `test_web_shell.py:95` asserts `/kids/Sam` comes before `rail-more` before `check-in`; the new tab sits between the first two and keeps that order.

- [ ] **Step 8: Look at it in a browser** (the phone viewport in particular, Risk 4 in the spec). From the worktree: `python -m fridgesheet.web` with a seeded home is awkward; use the test client's HTML instead: write `app_for(tmp).get("/kids/Alex/report-card").text` to `/tmp/report-card.html` from a one-off script and open it with the venv's Playwright at 390px and 1280px, screenshotting to `/tmp/report-card-phone.png` and `/tmp/report-card-desk.png`. Check the four kid tabs fit on one ruled row at 390px. If they wrap, add `.rail nav.kid a { padding-inline: var(--s1); }` under the existing phone breakpoint (`@media (max-width: 1023px)`, line 233) rather than shortening the label.

- [ ] **Step 9: Commit**

```bash
git add fridgesheet/web/routes/report_card.py fridgesheet/web/templates/report_card.html fridgesheet/web/app.py fridgesheet/web/templates/base.html fridgesheet/web/templates/_child_nav.html fridgesheet/web/static/app.css fridgesheet/web/phrasing.py tests/test_web_report_card.py tests/test_web_tier_parity.py tests/test_web_checkin.py
git commit -m "The report card: every class one ruled line with the official average, the scale's letter and how it is figured; a fourth tab on the kid's rail"
```

---

### Task 8: The MCP `grades()` account and the doctor's "averages" probe

**Files:**
- Modify: `fridgesheet/server.py:96-130` (`grades`)
- Modify: `fridgesheet/doctor.py` (a probe after `_database`; the `PROBES` list)
- Test: `tests/test_server_tools.py`, `tests/test_doctor.py:43-50`

**Interfaces:**
- Consumes: `grading.account_hac/account_canvas`, `stores.grades.account_for`, `students.visible/courses/latest_grades`.
- Produces: `grades()` keys `account` and `canvas_account`; doctor probe `"averages"`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_server_tools.py` (uses the `graded` fixture at line 60; extend its Biology HAC class first with `"categories": [{"category": "Labs", "earned": 44.0, "possible": 50.0, "percent": "88.000%"}]` and `"assignments": [{"name": "Lab 1", "due": "09/10/2026", "assigned": "09/01/2026", "category": "Labs", "score": 44.0, "score_raw": "44.00", "points": 50.0, "percent": "88.00%"}]`):

```python
def test_grades_carries_the_account_of_each_number(graded, monkeypatch):
    monkeypatch.setattr(server._settings(), "sources", sources.DEFAULT)
    bio = {c["course"]: c for c in server.grades("Alex")["classes"]}["Honors Biology S1-2027-Nance"]
    assert bio["account"]["source"] == "hac" and bio["account"]["match"] == "exact"
    assert bio["account"]["lines"][0]["category"] == "Labs" and bio["account"]["earned"] == 44.0
    assert bio["canvas_account"]["source"] == "canvas" and bio["canvas_account"]["reported"] == 91.2
    hawk = {c["course"]: c for c in server.grades("Alex")["classes"]}["Hawk Time"]
    assert hawk["account"]["basis"] == "none" and hawk["account"]["match"] == "unknown"
```

In `tests/test_doctor.py::test_real_probes_run_on_this_machine` (line 47) insert `"averages"` after `"database"` in the names list, and add:

```python
def test_averages_probe_counts_the_classes_that_add_up(tmp_path):
    from tests.web_fixtures import seed
    seed(tmp_path).close()
    out = {c.name: c for c in doctor.checks(Settings(home=tmp_path), tmp_path, probes=[p for p in doctor.PROBES if p[0] == "averages"])}
    assert out["averages"].ok
    assert out["averages"].detail.startswith("1 of 1 HAC classes with a breakdown add up")
    assert "no breakdown: Alex's Algebra I" in out["averages"].detail
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_server_tools.py tests/test_doctor.py -k "account or averages or real_probes"`
Expected: KeyError `'account'`; the names list differs.

- [ ] **Step 3: `server.py`.** Add `from . import grading` to the imports. In `grades()`, inside the Canvas-courses loop, before `out["classes"].append(...)`:

```python
        hac_rows = [{"category": r.get("category"), "score": r.get("score"), "points": r.get("points"), "excused": open_items.hac_excused(r)} for r in (h.get("assignments") or [])]
        canvas_rows = [{"group": a.get("group"), "score": a.get("score"), "points": a.get("points_possible"), "excused": a.get("excused"), "missing": a.get("missing"), "state": a.get("state")} for a in (c.get("assignments") or [])]
        account = grading.account_hac(h.get("marking_period_avg"), h.get("categories") or [], hac_rows) if h else None
        canvas_account = grading.account_canvas(c["grade"]["current_score"], c["grade"]["final_score"], c["grade"]["hidden"], canvas_rows)
```

and add to the appended dict: `"account": asdict(account) if account else None, "canvas_account": asdict(canvas_account),` (import `from dataclasses import asdict`). In the HAC-only loop add `"account": asdict(grading.account_hac(h.get("marking_period_avg"), h.get("categories") or [], [...same hac_rows comprehension over h...]))` and `"canvas_account": None`. Extend the docstring: *"`account` is how the official number is built (grading.Account): its category lines, the rebuilt total, and `match`: "exact" when the rebuild equals HAC's number, "off" when it does not (HAC may weight categories, or count work the scraper cannot see), "unknown" when there is no number to check. Never present an "off" rebuild as the grade."*

- [ ] **Step 4: `doctor.py`.** After `_database` add:

```python
def _averages(s: Settings, home: Path) -> str:
    """Whether each HAC class's marking-period average rebuilds from its category subtotals
    (grading.Account). "off" on a class is the scraper missing rows or HAC weighting categories;
    either way the household should know (spec 2026-10-03 §7.3)."""
    from .web import db as webdb
    from .web.stores import grades, students
    conn = webdb.open_db(home)
    try:
        exact = checked = 0
        off: list[str] = []
        none: list[str] = []
        for st in students.visible(conn):
            latest = students.latest_grades(conn, st["id"])
            for c in students.courses(conn, st["id"]):
                if c["source"] != "hac":
                    continue
                a = grades.account_for(conn, c, latest.get(c["id"]))
                label = f"{st['key']}'s {c['short_name']}"
                if a.basis == "none" or a.match == "unknown":
                    none.append(label)
                    continue
                checked += 1
                if a.match == "exact":
                    exact += 1
                else:
                    off.append(label)
    finally:
        conn.close()
    parts = [f"{exact} of {checked} HAC classes with a breakdown add up"]
    if off:
        parts.append("off: " + ", ".join(off))
    if none:
        parts.append("no breakdown: " + ", ".join(none))
    return "; ".join(parts)
```

and insert `("averages", _averages),` after `("database", _database),` in `PROBES`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q tests/test_server_tools.py tests/test_doctor.py tests/test_web_diagnostics_page.py tests/test_web_diagnostics_planner.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/server.py fridgesheet/doctor.py tests/test_server_tools.py tests/test_doctor.py
git commit -m "The MCP grades tool and the doctor carry the account of each average: what it is built from and whether it adds up"
```

---

### Task 9: Documentation and DESIGN.md

**Files:**
- Modify: `DESIGN.md:406, 447, 896, 1152-1154`; `docs/user-guide.md:328-331, 465-484, 723-755, 804`; `docs/outcomes.md:86-88`; `docs/product/features/canvas-hac-ingestion.md`; `docs/superpowers/specs/2026-10-03-report-card-and-grade-account-design.md` §6 and §8
- Create: `docs/product/features/report-card.md`, `.impeccable/surfaces/fridgesheet-web-templates-report_card-html.md`
- Test: `tests/test_rebrand.py`, `tests/test_tokens.py`, `tests/test_user_guide_defects.py`

- [ ] **Step 1: DESIGN.md.** Rename Trends's nickname at lines 406, 447 and 896 from "the report card page" to "the year so far page" (keep the seed and date). At line 1152 change the component's name to `**The year so far page** (Trends):`. After the Changes paragraph in the build log (the paragraph starting "**The planner's log** (Changes)") add:

```markdown
**The report card** (`/kids/{key}/report-card`, 2026-10-03): under the crumb and the title
("Report card", the kid's nickname and "marking period so far" in the subtitle, Print the page's
one action), `.planner-main.report-card-page` holding one `section.sec.report-lines` ("Classes"
with its count) whose `ol.report-lines` is one ruled line per class under a hairline: the class's
short name a Ballpoint link at the left, the official number at 1.75× root in ink with the
scale's letter at 400 beside it at the right, whose number and "as of" in pencil beneath, then
one sentence in the kid's tier on how it is figured (`rc.*`, phrasing.py). A class with no number
shows an em dash and "No average yet." The one fold beneath, `details.sec.quiet.how-figured`,
says how HAC (total points) and Canvas (graded work only) figure an average. On the class page,
`section.sec.grade-account` ("How it's figured") follows the grade strip: the official
gradebook's account first, HAC's as `table.categories` flat on the page (Category, Earned,
Possible, Percent, Share of the grade, a Total row), its check line with a ✓ in ink or, when the
rebuild and HAC's number disagree, in Red Pen; Canvas's as a sentence. Nothing on either page
asserts the straight-points rule: the account checks it and says when it cannot.
```

- [ ] **Step 2: The surface brief.** Create `.impeccable/surfaces/fridgesheet-web-templates-report_card-html.md` in the form of the Trends brief (frontmatter `version: 1`, `slug`, `primary_target: "fridgesheet/web/templates/report_card.html"`, `related_targets: ["fridgesheet/web/routes/report_card.py","fridgesheet/web/stores/grades.py","fridgesheet/web/templates/course.html"]`), then `# Surface brief: the report card`, a Scope paragraph (route, audience: the kid and the parent; job: read every class's grade the way the paper report card reads and see in one sentence how it is figured; proof: HAC's own subtotals and the check against its number; constraints: same rows in every tier, title equals the rail word, prints as it stands), and a Direction contract with THESIS ("The report card is the planner's grade page: one ruled line per class, the number at the right as a teacher writes it, one plain sentence on how it is figured. It refuses the progress ring and the card grid."), OWN-WORLD, STORY, FIRST VIEWPORT (the fixture's two lines as the example), FORM (code-led, composition in the settled world, no roll), FINISH (the finish review and DESIGN.md). Add one sentence to the class page's brief Scope: "and, since 2026-10-03, the 'How it's figured' section after the strip (spec 2026-10-03 §7.2)."

- [ ] **Step 3: The user guide.** Line 328-331: "Each child has four tabs: **Check-in · Plan · Assignments · Report card**." After §6.4 (before the `---` at line 482) add:

```markdown
### 6.5 Report card

Every class on one line, the way the paper one reads: the class, the official average (HAC's
marking-period average unless you chose Canvas for class averages) with its letter, whose
number it is and when the gradebook last changed it, and one sentence on how it is figured:

- *Adds up: 368.91 of 520.5 points. 25 points of unscored work count as zero.* HAC's number
  is total points earned over total points possible across every category, and the app
  rebuilt it from HAC's own category subtotals to the hundredth.
- *HAC says 86.57; the 10 scored rows we can see add up to 90.24.* HAC showed no category
  table for this class and the rows do not rebuild its number. HAC may weight categories, or
  count work the app cannot see. Ask the teacher how the class is figured.
- *Canvas counts graded work only: 84.42 now, 68.94 if the 3 missing stay at zero.* For a
  class whose official number comes from Canvas.

The letter is from the ten-point scale (A 90, B 80, C 70, D 60, F below) unless `[grading]`
in `config.toml` says otherwise ([§13](#what-settings-doesnt-show)). **Print** prints the page.
The fold at the foot says how each gradebook figures an average, in the child's words.

On a class page, **How it's figured** sits under the grade strip: HAC's categories with points
earned, points possible, the percent, and each category's share of the grade (its possible
points over all possible points, which in a total-points class is its weight); the total; and
whether it adds up to HAC's number. A category HAC's table leaves out but whose rows it lists
is marked *from the rows*. Canvas's part is one sentence: what its current score counts and
what its final would be if missing work stays missing.
```

In §6.4's bullets add after the Sources line: `- **How it's figured** — HAC's categories, their share of the grade, and whether they add up to HAC's number ([§6.5](#65-report-card)).` In §13 "What Settings doesn't show" (line 804) add a bullet:

```markdown
- **The letter scale.** `[grading]` in `config.toml`: `scale = { A = 90, B = 80, C = 70, D = 60 }`
  (each letter's floor; plus and minus letters work the same way, `"A-" = 90`) and
  `below = "F"` for everything under the lowest floor. Absent, the ten-point scale.
```

- [ ] **Step 4: The rest.** `docs/outcomes.md` after line 88's bullet, add the sentence: "Since 2026-10-03 the app rebuilds that average from HAC's own category subtotals (total points, in every class checked) and says on the report card when it cannot." `docs/product/features/canvas-hac-ingestion.md`: in the section describing the database tables (search "grade_observations"), add: "`category_observations` keeps HAC's category subtotal rows per refresh, written when the set changes; `item_categories` keeps which category or group each gradebook files an item under." Create `docs/product/features/report-card.md` with the frontmatter form of `trends-and-changes.md` (`slug: report-card`, `title: Report Card & the Account of an Average`, `state: live`, `parent: actionable-work-model`) and the sections Problem, Target users, Desired outcome, Success metrics, Non-goals, each two to five sentences drawn from the spec's §1, §2, §13. In the spec, add the `rc.no_breakdown` row to the §6 table (condition: `basis == "none"` with a reported number; values `reported`) and to the §8 phrase table.

- [ ] **Step 5: Run the full suite**

```bash
git add -A docs DESIGN.md .impeccable
env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q 2>&1 | tee /tmp/fridgesheet-report-card-suite.log | tail -5
```

Expected: all pass. `test_rebrand` scans every tracked file, `test_tokens` holds DESIGN.md's frontmatter to `tokens.py` (untouched), `test_user_guide_defects` reads the guide.

- [ ] **Step 6: Commit**

```bash
git add -A docs DESIGN.md .impeccable
git commit -m "Docs: the report card and how an average is figured; Trends is the year so far page"
```

---

### Task 10: Finish the branch

- [ ] **Step 1:** Run the whole suite once more from a clean tree and confirm the tail reads `passed` with no failures: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python -m pytest -q 2>&1 | tail -3`.
- [ ] **Step 2:** `gh pr list --search "grading.py"` and `--search "report_card"` for in-flight PRs touching the same files; rebase on `origin/main` if any merged since `1f9f278`.
- [ ] **Step 3:** Push and open the PR against `main` with a title in the repo's voice ("The report card: every class one line with its official average and how it is figured; the class page's 'How it's figured'; HAC's category subtotals kept per refresh") and a body that lists the spec path, the §1 finding, the schema bump, and the follow-ups from spec §13. End the body with the attribution line. Arm auto-merge at once: `gh pr merge <n> --auto --squash`.
- [ ] **Step 4:** Share the PR URL as an artifact.

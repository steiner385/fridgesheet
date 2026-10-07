# Assignments as a To-do List: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/kids/{key}` opens on one deadline-ordered list of every open item, with gradebook
questions, waiting and missed work beneath it and finished work in a Done view. Every item
appears exactly once.

**Architecture:** One pure function, `items.assignments(views, today)`, sorts each `ItemView` into
exactly one group. The route renders the To do view from those groups. The Done view is the
existing weekly pages (`weeks_of` + `_weeks.html`) over the done group, or over any legacy filter
the URL carries. Rows reuse `_needs_now_row.html` (with answers) and `_week_line.html` (plain), so
answering, Undo and Close keep their existing slots.

**Tech Stack:** FastAPI, Jinja2, htmx, sqlite, pytest (`env -u PYTHONPATH .venv/bin/python -m pytest`).

**Spec:** `docs/superpowers/specs/2026-10-06-assignments-to-do-design.md`

## Global Constraints

- Child-facing copy goes through `phrasing.PHRASES` `copy.*` keys at all three tiers (early, middle, older).
- Tier parity: every tier gets the same rows and actions.
- Section-and-card standard: `.sec` / `.sec-head` sections, and rows through `_item.html`.
- The class page (`course.html`), Check-in (`_must_finish.html`), `open_work`, `must_finish` and the printed sheet stay unchanged.
- Old query parameters (`show`, `outcome`, `flagged`, `verdict`, `source`, `kind`, `type`, `sort`) keep working and open the Done view.
- Commit messages end with the Co-Authored-By line. The PR gets auto-merge armed (`gh pr merge --auto --squash`).

## Review Focus

1. Work due after the `days_ahead` window (`not_due_yet` but not `upcoming`) must land in To do → Later, not in Done. Test: `test_far_future_work_is_to_do_not_done`.
2. A handled row (marked done or let go) that is still upcoming goes to Done, not To do. Test: `test_handled_upcoming_row_is_done`.
3. A to-do row that also asks a question appears once, in To do, with its question on the row. Test: `test_a_to_do_row_that_asks_stays_in_to_do`.
4. A legacy deep link `/kids/X?show=all#row-<id>` still finds the row's anchor. Test: `test_show_all_link_lands_on_the_row`.
5. A row past its late-work window never says late work "is usually accepted until" a date that has passed. Test: `test_a_missed_row_says_the_window_in_the_past_tense`.

---

### Task 1: The partition

**Files:**
- Modify: `fridgesheet/web/stores/items.py` (add `Assignments`, `_group` and `assignments` after `needs_you_now`)
- Test: `tests/test_assignments_partition.py`

**Interfaces:**
- Produces: `items.assignments(views: list[ItemView], today: date) -> Assignments`. Its fields are `overdue, tonight, tomorrow, this_week, later, question, waiting, missed, done: list[ItemView]`, and its properties are `to_do` and `groups -> dict[str, list]`.

- [ ] **Step 1: Write the failing tests**

```python
"""Assignments' one partition (spec 2026-10-06): every one of a kid's rows lands in exactly one
group, so the page's sections cannot disagree."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fridgesheet.web.stores import items, plans, students
from tests.web_fixtures import NOW, _a, marked_ahead, seed, snapshot
from fridgesheet.web import late_rules as _lr  # noqa: F401  (rules come from the store default)


def _views(conn, key):
    s = students.by_key(conn, key)
    return items.list_items(conn, s, now=NOW, rules=_rules(), show="all")
...
```
(The test file in the commit is the source of truth. Its tests are: the groups are disjoint and
cover `list_items(show="all")` for every fixture kid; Vocabulary (due tonight) is in `tonight` and
Worksheet 3 in `tomorrow`; Cell diagram and Safety quiz are in `overdue`, Safety quiz first; a
step on Safety quiz does not remove it from `overdue`; Participation is in `question`; Lab
notebook (paper) is in `waiting`; Homework 4 (8/20, past the window) is in `missed`; Essay draft
is in `done`; plus Review Focus 1–3.)

- [ ] **Step 2: Run, expect failure** `pytest tests/test_assignments_partition.py` → `AttributeError: module ... has no attribute 'assignments'`.

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True)
class Assignments:
    overdue: list[ItemView]; tonight: list[ItemView]; tomorrow: list[ItemView]
    this_week: list[ItemView]; later: list[ItemView]
    question: list[ItemView]; waiting: list[ItemView]; missed: list[ItemView]; done: list[ItemView]

    @property
    def to_do(self): return self.overdue + self.tonight + self.tomorrow + self.this_week + self.later


def _group(v: ItemView) -> str:
    if not v.handled and not v.overdue and (v.upcoming or v.outcome == outcomes.NOT_DUE):
        return "to_do"
    if v.overdue and not v.handled and v.actionable and v.outcome == outcomes.NOT_DONE:
        return "to_do"
    if v.asks:
        return "question"
    if _fixable(v) or v.verdict.state == "waiting" or v.verdict.kind in ("asked", "following_up"):
        return "waiting"
    if _past_window(v):
        return "missed"
    return "done"


def assignments(views, today):
    # sort each to-do row into its band by deadline_date; overdue by late_until, then due
```

- [ ] **Step 4: Run, expect pass.** **Step 5: Commit.**

### Task 2: A missed row speaks in the past tense

**Files:** `fridgesheet/web/templates/_item.html:65-68`, `fridgesheet/web/phrasing.py` (add
`copy.late_closed`), test in `tests/test_web_assignments_to_do.py`.

- [ ] Failing test: on Sam's page at NOW + 30 days, Safety quiz's line contains "was accepted until" and not "is usually accepted until".
- [ ] Implement: in `_item.html` set `late` only when `item.actionable`, and set `closed = late_line and item.overdue and not item.actionable and item.late_until`. When `closed`, render `copy.late_closed` ("Late work was accepted until {when}.").
- [ ] Pass, then commit.

### Task 3: The To do view and the Done view

**Files:**
- Modify: `fridgesheet/web/routes/kid.py` (`kid()` and `weeks_of` gets `always_this_week`)
- Create: `fridgesheet/web/templates/_to_do.html`
- Modify: `fridgesheet/web/templates/kid.html`, `_verdict_sections.html` (drop "Waiting, nothing to do yet")
- Delete: `fridgesheet/web/templates/_needs_now.html`; remove `items.needs_you_now`
- Modify: `fridgesheet/web/phrasing.py`: `copy.to_do`, `copy.done_view`, `copy.check_with_teacher`, `copy.waiting_on_grade`, `copy.missed_too_late`, `copy.band_overdue`, `copy.band_this_week`, `copy.band_later`, `copy.nothing_to_do`, `copy.back_to_to_do`
- Test: `tests/test_web_assignments_to_do.py`

Tests (written first, run red, then green):
- To do is the default: `id="to-do"` comes before `id="check-teacher"`, there is no `id="needs-now"`, and there is no "More filters".
- Alex's bands, in order: tonight [Vocabulary] then tomorrow [Worksheet 3]. Those rows carry `qn-` answer slots.
- Sam: overdue [Safety quiz, Cell diagram], with a step shown under Safety quiz and the row kept.
- Participation sits in Check with the teacher and answers with slot `qn-`.
- Every open item appears exactly once: each id appears in exactly one `id="(nn|row)-<id>"` box.
- `?view=done` shows `data-week` boxes holding Essay draft and does not show Vocabulary.
- `?show=all` and `?outcome=not_done` open the Done view (Review Focus 4: `id="row-<cell>"` is present for `?show=all`).
- The Class picker narrows To do (`?course=<alg>` leaves only Homework 4 under Missed).
- An answer posted with slot `qn-<id>` still swaps and Undo puts it back (existing route, re-asserted).

The To do markup: `section#to-do.sec` with bands as `div.mf-section[data-band]` (overdue, tonight
and tomorrow through `_needs_now_row.html`; this week through `_week_line.html`); Later as a
`details.mf-section.folded[data-band=later]` whose summary reads "Later · {n} due {from} – {to}".
Then `section#check-teacher.sec`, `details#waiting.sec.quiet` and `details#missed.sec.quiet`. The
view toggle is `p.view-toggle` with two links, the current one `aria-current="page"`.

### Task 4: Move the existing tests to the new page

`test_web_needs_you_now.py` becomes the To do tests. Its cases are rewritten onto `#to-do` and
`#check-teacher`, and the "covered by a step" case is inverted (a step no longer hides a row).
`test_web_weekly_pages.py`, `test_web_plan_reset.py`, `test_web_section_and_card.py`,
`test_web_kid_table.py`, `test_web_work_types_pages.py`, `test_web_pwa.py` and
`test_web_changes_page.py` request `?view=done` (or `?show=all`) wherever they assert the weekly
pages or the filter form. Update `tests/web_fixtures.py: items_block` / `needs_row` to the new
sections. Update the surface brief `.impeccable/surfaces/fridgesheet-web-templates-kid-html.md`
thesis. Run the full suite: everything green except failures that were already there before
this work.

### Task 5: Check it on prod's data, then ship

- Rerun `/tmp/fs-audit/dump_doug.py` (adapted to `items.assignments`) against `/tmp/prodsnap/home`: Doug's four rows land where the spec's table says.
- Screenshot `/kids/Douglas` with venv Playwright at 390px and 1280px, run from the worktree.
- Push the branch, `gh pr create`, then `gh pr merge --auto --squash`.

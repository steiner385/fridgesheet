# Questions, not cases: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Reconcile page's six "cases" with one verdict per item. The app settles what the records settle, waits on what time will settle, and asks the family only when they have something to do.

**Architecture:** A new pure module, `fridgesheet/web/verdicts.py`, turns one item's latest observations and flag into a `Verdict` with one of four states. `ItemView` carries it. The kid page renders three sections above a quieter work list, and a new Questions page shows every kid's questions. `outcomes.classify` and the printed sheet change precedence so a real HAC grade beats Canvas's automatic "missing". The old case machinery is deleted last, once nothing reads it.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, htmx 2, SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-09-23-questions-not-cases-design.md`

## Before you start

- **PR #27 must be merged into `main` first.** This plan uses its `phrase` filter, the `tier_of` filter and `fridgesheet/web/phrasing.py`. If `fridgesheet/web/phrasing.py` does not exist on `main`, stop and report.
- Branch from `main`: `git switch -c ux/questions origin/main`.
- Run tests with: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider`. Without `env -u PYTHONPATH`, another checkout's `tests` package shadows this one.
- Baseline: the full suite passes before Task 1. Record the count.

## Global Constraints

- No database schema change. No ingest change.
- Grace period before asking about ungraded paper, in-class or HAC-only work: **7 calendar days** past the due date (`(now.date() - due.date()).days >= 7`).
- HAC still blank after Canvas graded it: ask after **7 calendar days**, counted from the refresh that recorded Canvas's latest observation.
- Score tolerance: two scores differ when they are more than **0.5 points** apart on the item's scale.
- A HAC score above zero beats Canvas's `missing` flag, **except** when Canvas's latest observation comes from a later refresh than HAC's (`refresh_id` greater). A missing `refresh_id` on either side counts as "not newer".
- There is no "Not now" answer.
- Every user-visible sentence a verdict produces goes through `phrasing.phrase(key, tier)`, with the same placeholders in every tier. The fabrication guard in `tests/test_phrasing.py` must keep passing.
- Dates in sentences are formatted as `f"{d.month}/{d.day}"`, never `strftime("%-m")`, which fails on Windows.
- Red text is only for school-recorded not-done: Canvas `missing`, or a zero.
- Commit after every task. Each commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **An item with no due date.** HAC lists real undated work. The verdict must not crash on the grace calculation. It must return a status, never a question. The test goes in Task 4.
2. **No points, or zero points.** Score comparisons must be skipped, not divided by zero. An extra-credit item with `points = 0` must not be called a zero. The test goes in Task 3.
3. **A class with no HAC twin.** A Canvas-only course (`peer_course_id` is NULL) must never produce "HAC still has nothing". The test goes in Task 4.
4. **Flag timestamps with and without a time zone.** `flags.set_at` is written by `db.now_iso(tz)`, but older rows and tests use naive strings. The stale check must compare them through `reconcile._comparable`. The test goes in Task 2.
5. **Double submission of an answer.** A parent double-taps "HAC is right, it's done". The second POST must leave one active flag and render the same answered line. The test goes in Task 8.

---

### Task 1: HAC's grade beats Canvas's automatic "missing" in `classify`

**Files:**
- Modify: `fridgesheet/web/outcomes.py` (`classify` and two new helpers)
- Modify: `docs/outcomes.md` (one new paragraph)
- Modify: `tests/web_fixtures.py` (docstring line for Quiz 1 only)
- Test: `tests/test_web_outcomes.py`
- Update expectations in: `tests/test_web_checkin.py`, `tests/test_web_items_prefer.py`, `tests/test_web_open_page.py`, `tests/test_web_open_sources.py`, `tests/test_web_outcomes.py`, `tests/test_web_pages.py`, `tests/test_web_sources_threading.py`, `tests/test_web_stores_pages.py`, `tests/test_web_tier_wording.py`, `tests/test_web_trends_store.py`, `tests/test_web_views.py`

**Interfaces:**
- Produces: `outcomes.newer(a, b) -> bool`. It is True only when both observations carry a `refresh_id` and `a`'s is greater. Tasks 2 and 3 use it.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_outcomes.py`)

```python
from fridgesheet.web import outcomes as _o


def _obs_row(refresh_id, **kw):
    base = dict(refresh_id=refresh_id, state="unsubmitted", score=None, grade=None, submitted_at=None,
                late=0, missing=0, excused=0, published=1)
    base.update(kw)
    return base


def _hac_row(refresh_id, score):
    return dict(refresh_id=refresh_id, state="graded", score=score, grade=None, submitted_at=None,
                late=None, missing=None, excused=None, published=None)


_ITEM = {"kind": "online", "due": "2026-09-12T23:59:00-04:00", "points": 30.0}
_NOW = datetime(2026, 9, 15, 14, 0, tzinfo=ZoneInfo("America/New_York"))


def test_a_hac_grade_beats_canvas_automatic_missing():
    """Spec 4.2: Canvas's `missing` is often its late policy's automatic mark; a real HAC
    grade is the teacher's assessment."""
    obs = {"canvas": _obs_row(2, missing=1), "hac": _hac_row(2, 28.0)}
    assert _o.classify(_ITEM, obs, _NOW) == _o.DONE_OFFLINE


def test_a_missing_mark_newer_than_the_hac_grade_still_wins():
    obs = {"canvas": _obs_row(3, missing=1), "hac": _hac_row(2, 28.0)}
    assert _o.classify(_ITEM, obs, _NOW) == _o.NOT_DONE


def test_a_hac_zero_never_beats_the_missing_flag():
    obs = {"canvas": _obs_row(2, missing=1), "hac": _hac_row(2, 0.0)}
    assert _o.classify(_ITEM, obs, _NOW) == _o.NOT_DONE


def test_observations_without_a_refresh_id_are_never_newer():
    obs = {"canvas": {**_obs_row(0, missing=1)}, "hac": _hac_row(2, 28.0)}
    del obs["canvas"]["refresh_id"]
    assert _o.classify(_ITEM, obs, _NOW) == _o.DONE_OFFLINE
    assert _o.newer(obs["canvas"], obs["hac"]) is False
```

Add `from datetime import datetime` and `from zoneinfo import ZoneInfo` at the top of the file if they are not already imported.

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_outcomes.py -k "beats or newer or never_beats or refresh_id"`
Expected: FAIL. The first test returns `not_done`, and `newer` does not exist.

- [ ] **Step 3: Implement the change in `fridgesheet/web/outcomes.py`**

Add these two functions above `_is_past`:

```python
def _refresh_id(o) -> int | None:
    return o["refresh_id"] if o is not None and "refresh_id" in o.keys() else None


def newer(a, b) -> bool:
    """Whether observation `a` was recorded in a later refresh than `b`. Refresh ids only
    grow, and ingest writes an observation only when something changed, so this is "did
    `a`'s source change after `b`'s did". An unknown id is never newer."""
    ra, rb = _refresh_id(a), _refresh_id(b)
    return ra is not None and rb is not None and ra > rb
```

In `classify`, replace the line `hac_decides = prefer == "hac" and h_score is not None` with:

```python
    # A real HAC grade is the teacher's assessment, and Canvas's `missing` is often its late
    # policy's automatic mark, so HAC decides whenever it has a grade above zero -- unless
    # Canvas changed after HAC did, which is the teacher saying something new. Under the HAC
    # preference HAC decides whenever it has any score, as before.
    hac_graded = h_score is not None and h_score > 0
    hac_decides = h_score is not None and (prefer == "hac" or (hac_graded and not newer(c, h)))
```

Update the `classify` docstring's second paragraph. Replace "Under "canvas" a Canvas score wins and HAC fills the gap." with "Under "canvas" a Canvas score wins and HAC fills the gap, and a HAC grade above zero also overrides Canvas's `missing` flag unless Canvas changed later (docs/outcomes.md)."

- [ ] **Step 4: Run the new tests and confirm they pass**

Run the same command as Step 2. Expected: PASS.

- [ ] **Step 5: Run the full suite and update the 22 expectations that encode the old rule**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee /tmp/task1.log | grep -E "^FAILED|passed|failed"`
Expected: 22 failures, all in the files listed under **Update expectations**. Each assumes the seeded Quiz 1, with Canvas missing and HAC 28/30 in one refresh, is open, not done or actionable. It is now `done_offline`, not open and not actionable. For each failure:
- If the test asserts Quiz 1 appears in an open, actionable or "needs clarification" list, change it to assert Quiz 1 is absent, and keep the other items' assertions.
- If it asserts a count that included Quiz 1, lower that count by one. Alex's dashboard "3 actionable" becomes "2 actionable".
- `tests/test_web_open_sources.py::test_a_teachers_flag_or_zero_is_open_whatever_hac_says` and `tests/test_web_outcomes.py::test_honors_algebra_quiz_canvas_missing_hac_48` test the old rule on purpose. Rename them to `..._unless_hac_has_a_grade` and `test_honors_algebra_quiz_canvas_missing_hac_48_is_done_on_paper`. Assert the new outcome, and keep their HAC-zero halves asserting `not_done`.
- Do not change any assertion about an item other than Quiz 1 without writing down why in the commit message.

Re-run until the suite passes.

- [ ] **Step 6: Update the fixture docstring and `docs/outcomes.md`**

In `tests/web_fixtures.py`, change the Quiz 1 docstring line to:
`  77 Quiz 1        due 9/12  Canvas MISSING, HAC 28/30           -> done on paper (HAC's grade beats the automatic flag)`

In `docs/outcomes.md`, under the section that explains Canvas's `missing` flag, add:

> **A HAC grade beats Canvas's automatic "missing".** When HAC has a score above zero, the work counts as done on paper even if Canvas still shows it missing. Canvas's late policy sets that flag by itself, while a HAC grade is the teacher's assessment. The exception is when Canvas changed after HAC did, meaning a later refresh recorded the missing mark. Then the app asks instead of deciding. Example: Quiz 1, missing in Canvas and 28/30 in HAC, both seen in the same refresh, is done.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/outcomes.py docs/outcomes.md tests/
git commit -m "outcomes: a HAC grade beats Canvas's automatic missing unless Canvas changed later"
```

---

### Task 2: The printed sheet follows the same precedence

**Files:**
- Modify: `fridgesheet/open_items.py` (the `status in ("PAPER — CHECK", "MISSING")` skip)
- Test: `tests/test_open_items.py`

The sheet reads a snapshot, which has no refresh history, so it cannot apply the "Canvas changed later" exception. A HAC grade above zero drops the row from the sheet unconditionally. The web app's question still catches the rare exception.

- [ ] **Step 1: Write the failing test** (append to `tests/test_open_items.py`)

The file already has `canvas_item`, `entry` and `NOW` (Fri 9/11). `WS 1` is due the day before.

```python
def _entry_with_ws(hac_score):
    hac = [{"name": "Honors Biology - 3", "assignments": [
        {"name": "WS 1", "score": hac_score, "due": "09/10/2026", "assigned": "09/01/2026", "points": 10.0}]}]
    return entry([canvas_item(missing=True)], hac_classes=hac)


def test_a_hac_grade_drops_an_auto_missing_row_from_the_sheet():
    work = open_items.open_items(_entry_with_ws(9.0), "Alex", NOW)
    assert "WS 1" not in [i.name for i in work.items]


def test_a_hac_zero_keeps_the_missing_row():
    work = open_items.open_items(_entry_with_ws(0.0), "Alex", NOW)
    assert "WS 1" in [i.name for i in work.items]
```

- [ ] **Step 2: Run and confirm the first test fails**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_open_items.py -k "auto_missing or keeps_the_missing"`
Expected: the first FAILS because WS 1 is still listed. The second PASSES. If the second fails because the two course names don't pair, check `matching.match_course("Honors Biology S1-2027-Nance", {"Honors Biology - 3": ...})` and use the HAC name it pairs with.

- [ ] **Step 3: Implement**

In `fridgesheet/open_items.py`, replace:

```python
            if status in ("PAPER — CHECK", "MISSING") and not a.get("missing") and a.get("score") is None \
                    and hac_score not in (None, 0):
                continue
```

with:

```python
            # A grade above zero in HAC settles it, including over Canvas's `missing`, which is
            # often the late policy's automatic mark (docs/outcomes.md). The web app also
            # asks when Canvas changed after HAC; a snapshot has no history, so the sheet
            # cannot, and follows HAC.
            if status in ("PAPER — CHECK", "MISSING") and a.get("score") is None and hac_score not in (None, 0):
                continue
```

Update the comment block above it so it no longer says "A Canvas `missing` flag or a 0 still wins". Say instead "A 0 in either source still wins".

- [ ] **Step 4: Run the file's tests and the full suite**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_open_items.py tests/test_sheet.py tests/test_sheet_table.py tests/test_print_sheet.py`
Then run the full suite. Update any sheet test that asserted a missing-in-Canvas, graded-in-HAC row prints. The rule change intends that it no longer prints.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/open_items.py tests/
git commit -m "sheet: a HAC grade above zero drops an auto-missing row, matching classify"
```

---

### Task 3: `verdicts.py`: the flag rules, the HAC-zero rules and the score rules

**Files:**
- Create: `fridgesheet/web/verdicts.py`
- Create: `tests/test_verdicts.py`

**Interfaces:**
- Consumes: `outcomes.classify`, `outcomes.newer` (Task 1); `reconcile.due_of`, `reconcile._comparable`, `reconcile._parse_ts`; `HANDLED_FLAGS`, `MARKED_FLAGS` from `fridgesheet.open_items`.
- Produces:
  - Constants `QUESTION = "question"`, `DECIDED = "decided"`, `WAITING = "waiting"`, `STATUS = "status"`, `GRACE_DAYS = 7`, `TOLERANCE = 0.5`.
  - `@dataclass(frozen=True) class Answer: key: str; flag: str | None`. `key` is a phrase key such as `"a.ask_teacher"`. `flag` is a flag name, or `"confirm"`, `"clear"`, or `None` for "open the plan-step form".
  - `@dataclass(frozen=True) class Verdict: state: str; kind: str; facts: dict = field(default_factory=dict); answers: tuple[Answer, ...] = (); asks_on: date | None = None`.
  - `verdict(item, obs, *, flag, flag_set_at, now, rules, refresh_times, prefer="canvas") -> Verdict`. `item` is a `reconcile.live_items` row. It carries `kind`, `due`, `points`, `kid`, `course_name`, `peer_course_id`.

- [ ] **Step 1: Write the failing tests** (`tests/test_verdicts.py`)

```python
"""One verdict per item (spec section 4.1). Plain dicts stand in for observation rows."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet import late_rules
from fridgesheet.web import verdicts as V

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)
RULES = late_rules.LateRules(late_rules.Rule(late_days=7, credit="50%"), [], [])
TIMES = {1: "2026-09-01T06:00:00-04:00", 2: "2026-09-08T06:00:00-04:00", 3: "2026-09-15T06:00:00-04:00"}


def item(kind="online", due="2026-09-12T23:59:00-04:00", points=30.0, peer=2):
    return {"kind": kind, "due": due, "points": points, "kid": "Alex", "course_name": "Honors English 9 S1",
            "peer_course_id": peer}


def canvas(rid=3, **kw):
    base = dict(refresh_id=rid, state="unsubmitted", score=None, grade=None, submitted_at=None, late=0,
                missing=0, excused=0, published=1)
    base.update(kw)
    return base


def hac(rid=3, score=None):
    return dict(refresh_id=rid, state="graded" if score is not None else "ungraded", score=score, grade=None,
                submitted_at=None, late=None, missing=None, excused=None, published=None)


def run(it, obs, flag=None, flag_set_at="", now=NOW):
    return V.verdict(it, obs, flag=flag, flag_set_at=flag_set_at, now=now, rules=RULES, refresh_times=TIMES)


def test_hac_grade_over_automatic_missing_is_decided():
    v = run(item(), {"canvas": canvas(missing=1), "hac": hac(score=28.0)})
    assert (v.state, v.kind) == (V.DECIDED, "graded_in_hac")
    assert v.facts == {"hac": "28 of 30"}
    assert [a.flag for a in v.answers] == ["done", "ask_teacher"]      # what "Not right?" offers


def test_missing_recorded_after_the_hac_grade_is_a_question():
    v = run(item(), {"canvas": canvas(rid=3, missing=1), "hac": hac(rid=2, score=28.0)})
    assert (v.state, v.kind) == (V.QUESTION, "missing_after_grade")


def test_submitted_online_but_hac_zero_is_a_question_with_the_timestamp():
    v = run(item(), {"canvas": canvas(state="submitted", submitted_at="2026-09-14T20:02:00-04:00"), "hac": hac(score=0.0)})
    assert (v.state, v.kind) == (V.QUESTION, "submitted_hac_zero")
    assert v.facts == {"when": "Mon 9/14, 8:02 PM"}


def test_excused_in_canvas_but_hac_zero_is_a_question():
    v = run(item(), {"canvas": canvas(excused=1), "hac": hac(score=0.0)})
    assert (v.state, v.kind) == (V.QUESTION, "excused_hac_zero")


def test_hac_lower_than_canvas_is_a_question():
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=20.0), "hac": hac(score=15.0)})
    assert (v.state, v.kind) == (V.QUESTION, "hac_lower")
    assert v.facts == {"canvas": "20 of 25", "hac": "15 of 25"}


def test_hac_higher_than_canvas_is_not_a_question():
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=15.0), "hac": hac(score=20.0)})
    assert v.state == V.STATUS


def test_a_gap_within_half_a_point_is_the_same_score():
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=20.0), "hac": hac(score=19.6)})
    assert v.state == V.STATUS


def test_hac_applying_the_late_penalty_is_explained():
    # 50% credit rule: Canvas has the raw 20, HAC entered 10.
    v = run(item(points=25.0), {"canvas": canvas(state="graded", score=20.0, late=1), "hac": hac(score=10.0)})
    assert (v.state, v.kind) == (V.DECIDED, "scores_explained")
    assert v.facts == {"why": "late"}


def test_hac_as_a_percentage_is_explained():
    # Canvas 180/200 is 90%; HAC typed 90. Points above 100 make HAC's number look lower.
    v = run(item(points=200.0), {"canvas": canvas(state="graded", score=180.0), "hac": hac(score=90.0)})
    assert (v.state, v.kind) == (V.DECIDED, "scores_explained")
    assert v.facts == {"why": "scale"}


def test_no_points_skips_score_comparison():
    """Review Focus 2: no division, and an extra-credit 0-point item is not a zero."""
    v = run(item(points=0.0), {"canvas": canvas(state="graded", score=2.0), "hac": hac(score=0.0)})
    assert v.state == V.STATUS
    v = run(item(points=None), {"canvas": canvas(state="graded", score=2.0), "hac": hac(score=1.0)})
    assert v.state == V.STATUS


def test_a_handled_flag_is_an_answered_status():
    v = run(item(), {"canvas": canvas(missing=1)}, flag="done", flag_set_at="2026-09-15T08:00:00-04:00")
    assert (v.state, v.kind) == (V.STATUS, "answered")


def test_ask_teacher_is_an_asked_status_with_its_date():
    v = run(item(), {"canvas": canvas(missing=1)}, flag="ask_teacher", flag_set_at="2026-09-15T08:00:00-04:00")
    assert (v.state, v.kind) == (V.STATUS, "asked")
    assert v.facts == {"when": "9/15"}


def test_a_done_flag_contradicted_later_is_a_stale_answer():
    v = run(item(), {"canvas": canvas(rid=3, missing=1)}, flag="done", flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "stale_answer")
    assert v.facts == {"flag": "done", "when": "9/10", "change": "Canvas now says missing"}
    assert [a.flag for a in v.answers] == ["confirm", "clear", "ask_teacher"]


def test_stale_check_accepts_a_naive_flag_timestamp():
    """Review Focus 4: older flag rows carry no offset."""
    v = run(item(), {"canvas": canvas(rid=3, missing=1)}, flag="done", flag_set_at="2026-09-10T08:00:00")
    assert v.kind == "stale_answer"
```

- [ ] **Step 2: Run and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verdicts.py`
Expected: FAIL with `ModuleNotFoundError: fridgesheet.web.verdicts`.

- [ ] **Step 3: Implement `fridgesheet/web/verdicts.py`**

```python
"""One verdict per item: what the app concluded, and whether the family has anything to do.

The Reconcile page used to raise a "case" for every way Canvas and HAC differed, and asked
about all of them. Most needed nobody: a grade that has not flowed to HAC yet will flow, and
a teacher who graded only in HAC graded it. A verdict has one of four states. `decided`
means the records settle it and the app says why. `waiting` means time will settle it.
`question` means the family can do something. `status` is a plain fact. The rules below
run in order; the first that matches wins (spec, section 4.1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..open_items import HANDLED_FLAGS, MARKED_FLAGS
from . import outcomes, reconcile

QUESTION, DECIDED, WAITING, STATUS = "question", "decided", "waiting", "status"
GRACE_DAYS = 7
TOLERANCE = 0.5


@dataclass(frozen=True)
class Answer:
    key: str                # phrase key for the button label
    flag: str | None        # a flag, "confirm", "clear", or None: open the plan-step form


@dataclass(frozen=True)
class Verdict:
    state: str
    kind: str
    facts: dict = field(default_factory=dict)      # values for the "facts.<kind>" phrase
    answers: tuple[Answer, ...] = ()
    asks_on: date | None = None                    # waiting only: the day it becomes a question


ASK = Answer("a.ask_teacher", "ask_teacher")
ANSWERS = {
    "missing_after_grade": (Answer("a.hac_right_done", "done"), ASK),
    "graded_in_hac": (Answer("a.hac_right_done", "done"), ASK),
    "hac_lower": (ASK, Answer("a.hac_right", "ignore")),
    "scores_explained": (ASK, Answer("a.hac_right", "ignore")),
    "submitted_hac_zero": (ASK, Answer("a.zero_right", "ignore")),
    "excused_hac_zero": (ASK, Answer("a.leave_it", "ignore")),
    "hac_still_blank": (ASK, Answer("a.its_fine", "ignore")),
    "hac_lag": (ASK,),
    "still_ungraded": (Answer("a.handed_in", "done"), Answer("a.plan_it", None), ASK),
    "awaiting_grade": (ASK,),
    "stale_answer": (Answer("a.still_done", "confirm"), Answer("a.reopen", "clear"), ASK),
}


def _n(x: float) -> str:
    return f"{x:g}"


def _of(score: float, points) -> str:
    return f"{_n(score)} of {_n(points)}" if points else _n(score)


def _md(ts: str) -> str:
    d = reconcile._parse_ts(ts)
    return f"{d.month}/{d.day}"


def _md_time(ts: str) -> str:
    d = reconcile._parse_ts(ts)
    hour = d.hour % 12 or 12
    return f"{d:%a} {d.month}/{d.day}, {hour}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def _credit_fraction(credit: str) -> float | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%", credit or "")
    return float(m.group(1)) / 100 if m else None


def _observed_at(o, refresh_times: dict[int, str]) -> datetime | None:
    started = refresh_times.get(o["refresh_id"]) if o is not None and "refresh_id" in o.keys() else None
    return reconcile._parse_ts(started) if started else None


def _after(o, set_at: str, refresh_times) -> bool:
    seen = _observed_at(o, refresh_times)
    if seen is None or not set_at:
        return False
    a, b = reconcile._comparable(seen, reconcile._parse_ts(set_at))
    return a > b


def _stale_change(flag, set_at, c, h, refresh_times) -> str | None:
    """What the school recorded after the family's answer that contradicts it, or None."""
    if flag in HANDLED_FLAGS:
        if c is not None and _after(c, set_at, refresh_times) and (c["missing"] or (c["state"] == "graded" and c["score"] == 0)):
            return "Canvas now says missing" if c["missing"] else "Canvas now shows a zero"
        if h is not None and _after(h, set_at, refresh_times) and h["score"] == 0:
            return "HAC now shows a zero"
    if flag in MARKED_FLAGS:
        if c is not None and _after(c, set_at, refresh_times) and c["score"] is not None:
            return f"Canvas has graded it: {_n(c['score'])}"
        if h is not None and _after(h, set_at, refresh_times) and h["score"] is not None:
            return f"HAC has graded it: {_n(h['score'])}"
    return None


def _scores(c, h, points, late_credit: float | None) -> Verdict | None:
    cs, hs = (c["score"] if c is not None else None), (h["score"] if h is not None else None)
    if cs is None or hs is None or not points:
        return None
    if cs - hs <= TOLERANCE:                           # HAC equal or higher: nothing to fix
        return None
    if abs(hs - cs / points * 100) <= TOLERANCE:
        return Verdict(DECIDED, "scores_explained", {"why": "scale"}, ANSWERS["scores_explained"])
    if c["late"] and late_credit is not None and abs(hs - cs * late_credit) <= TOLERANCE:
        return Verdict(DECIDED, "scores_explained", {"why": "late"}, ANSWERS["scores_explained"])
    return Verdict(QUESTION, "hac_lower", {"canvas": _of(cs, points), "hac": _of(hs, points)}, ANSWERS["hac_lower"])


def verdict(item, obs, *, flag, flag_set_at, now, rules, refresh_times, prefer="canvas") -> Verdict:
    c, h = obs.get("canvas"), obs.get("hac")
    points = item["points"]
    hs = h["score"] if h is not None else None

    # 1-2b: the family's own answer, unless the school has since contradicted it.
    if flag:
        change = _stale_change(flag, flag_set_at, c, h, refresh_times)
        if change:
            return Verdict(QUESTION, "stale_answer",
                           {"flag": flag.replace("_", " "), "when": _md(flag_set_at), "change": change},
                           ANSWERS["stale_answer"])
        if flag in HANDLED_FLAGS:
            return Verdict(STATUS, "answered")
        return Verdict(STATUS, "asked", {"when": _md(flag_set_at)} if flag_set_at else {})

    # 3-4: HAC counts a zero that Canvas says should not be there.
    if c is not None and h is not None and hs == 0 and (points or 0) > 0:
        if c["excused"]:
            return Verdict(QUESTION, "excused_hac_zero", {}, ANSWERS["excused_hac_zero"])
        if c["submitted_at"]:
            return Verdict(QUESTION, "submitted_hac_zero", {"when": _md_time(c["submitted_at"])}, ANSWERS["submitted_hac_zero"])

    # 5-6: a real HAC grade against Canvas's missing flag.
    if hs is not None and hs > 0 and c is not None and c["missing"]:
        kind = "missing_after_grade" if outcomes.newer(c, h) else "graded_in_hac"
        return Verdict(QUESTION if kind == "missing_after_grade" else DECIDED, kind, {"hac": _of(hs, points)}, ANSWERS[kind])

    # 7-8: both have a score and HAC is lower.
    credit = _credit_fraction(rules.resolve(item["kid"], item["course_name"]).credit)
    scored = _scores(c, h, points, credit)
    if scored is not None:
        return scored

    return _waiting_or_status(item, c, h, now=now, rules=rules, refresh_times=refresh_times, prefer=prefer, obs=obs)


def _waiting_or_status(item, c, h, *, now, rules, refresh_times, prefer, obs) -> Verdict:
    """Rules 9-15. Replaced in Task 4; until then everything left is a status."""
    return Verdict(STATUS, outcomes.classify(item, obs, now, prefer=prefer))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verdicts.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/verdicts.py tests/test_verdicts.py
git commit -m "verdicts: flag, HAC-zero and score rules (spec 4.1 rules 1-8)"
```

---

### Task 4: `verdicts.py`: waiting, grace periods and too late for credit

**Files:**
- Modify: `fridgesheet/web/verdicts.py` (replace `_waiting_or_status`)
- Test: `tests/test_verdicts.py`

**Interfaces:**
- Consumes: Task 3's module.
- Produces: the full `verdict()`. Waiting verdicts set `asks_on`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verdicts.py`)

```python
def test_canvas_graded_hac_blank_is_waiting_until_seven_days():
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=18.0), "hac": hac(rid=3)})
    assert (v.state, v.kind) == (V.WAITING, "hac_lag")
    assert v.asks_on.isoformat() == "2026-09-22"


def test_canvas_graded_hac_blank_after_seven_days_is_a_question():
    v = run(item(), {"canvas": canvas(rid=2, state="graded", score=18.0), "hac": hac(rid=2)})
    assert (v.state, v.kind) == (V.QUESTION, "hac_still_blank")
    assert v.facts == {"canvas": "18 of 30", "when": "9/8"}


def test_a_class_with_no_hac_twin_never_waits_for_hac():
    """Review Focus 3."""
    v = run(item(peer=None), {"canvas": canvas(rid=1, state="graded", score=18.0)})
    assert v.state == V.STATUS


def test_a_canvas_zero_with_hac_blank_is_not_done_not_a_hac_question():
    v = run(item(), {"canvas": canvas(rid=1, state="graded", score=0.0), "hac": hac(rid=1)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")


def test_submitted_and_ungraded_is_waiting_on_the_teacher():
    v = run(item(), {"canvas": canvas(state="submitted", submitted_at="2026-09-14T20:00:00-04:00")})
    assert (v.state, v.kind) == (V.WAITING, "teacher_grading")


def test_paper_with_no_grade_waits_seven_calendar_days():
    v = run(item(kind="paper", due="2026-09-10T23:59:00-04:00"), {"canvas": canvas()})
    assert (v.state, v.kind) == (V.WAITING, "awaiting_grade")
    assert v.asks_on.isoformat() == "2026-09-17"


def test_paper_with_no_grade_after_seven_days_is_a_question():
    v = run(item(kind="paper", due="2026-09-08T23:59:00-04:00"), {"canvas": canvas()})
    assert (v.state, v.kind) == (V.QUESTION, "still_ungraded")
    assert v.facts == {"kind": "paper", "due": "Tue 9/8"}


def test_hac_only_with_no_grade_follows_the_same_grace():
    v = run(item(kind="", due="2026-09-08T23:59:00-04:00", peer=None), {"hac": hac()})
    assert v.kind == "still_ungraded"


def test_an_undated_item_is_a_status_never_a_question():
    """Review Focus 1."""
    v = run(item(kind="paper", due=None), {"canvas": canvas()})
    assert v.state == V.STATUS


def test_open_work_past_its_credit_window_is_a_status():
    v = run(item(due="2026-08-20T23:59:00-04:00"), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "past_credit")


def test_open_work_inside_its_window_is_a_not_done_status():
    v = run(item(due="2026-09-12T23:59:00-04:00"), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")
```

- [ ] **Step 2: Run and confirm the new tests fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verdicts.py`
Expected: the new waiting and question tests FAIL, because everything is a status. `test_an_undated_item...` and `test_a_class_with_no_hac_twin...` may already pass. Keep them as guards.

- [ ] **Step 3: Implement.** Replace `_waiting_or_status` in `fridgesheet/web/verdicts.py`:

```python
def _days_past(due: datetime | None, now: datetime) -> int | None:
    return None if due is None else (now.date() - due.date()).days


def _waiting_or_status(item, c, h, *, now, rules, refresh_times, prefer, obs) -> Verdict:
    outcome = outcomes.classify(item, obs, now, prefer=prefer)
    points = item["points"]
    due = reconcile.due_of(item)
    cs = c["score"] if c is not None else None
    hs = h["score"] if h is not None else None

    # 9-10: Canvas graded it and HAC, which this class has, still has nothing.
    if cs is not None and cs > 0 and hs is None and item["peer_course_id"] is not None:
        seen = _observed_at(c, refresh_times)
        if seen is not None:
            asks_on = seen.date() + timedelta(days=GRACE_DAYS)
            if now.date() >= asks_on:
                return Verdict(QUESTION, "hac_still_blank", {"canvas": _of(cs, points), "when": f"{seen.month}/{seen.day}"},
                               ANSWERS["hac_still_blank"])
            return Verdict(WAITING, "hac_lag", {"canvas": _of(cs, points)}, ANSWERS["hac_lag"], asks_on=asks_on)

    # 11: handed in online, no grade anywhere.
    if c is not None and c["submitted_at"] and cs is None and hs is None:
        return Verdict(WAITING, "teacher_grading", {"when": _md(c["submitted_at"])})

    # 12-13: nothing to submit online, past due, no grade anywhere.
    if outcome == outcomes.UNKNOWN and due is not None:
        asks_on = due.date() + timedelta(days=GRACE_DAYS)
        facts = {"kind": item["kind"] or "HAC-only", "due": f"{due:%a} {due.month}/{due.day}"}
        if _days_past(due, now) >= GRACE_DAYS:
            return Verdict(QUESTION, "still_ungraded", facts, ANSWERS["still_ungraded"])
        return Verdict(WAITING, "awaiting_grade", facts, ANSWERS["awaiting_grade"], asks_on=asks_on)

    # 14: not done and past the late-work window.
    if outcome == outcomes.NOT_DONE and due is not None and now > rules.deadline(item["kid"], item["course_name"], due):
        return Verdict(STATUS, "past_credit")

    # 15: a plain outcome.
    return Verdict(STATUS, outcome)
```

- [ ] **Step 4: Run and confirm all verdict tests pass**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verdicts.py`
Expected: PASS. If `test_open_work_past_its_credit_window_is_a_status` fails because `now > deadline` compares naive with aware datetimes, compare through `reconcile._comparable(now, deadline)` as `reconcile.cases` does.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/verdicts.py tests/test_verdicts.py
git commit -m "verdicts: waiting, the 7-day grace periods and past-credit (spec 4.1 rules 9-15)"
```

---

### Task 5: The words: phrase entries and the `say` filter

**Files:**
- Modify: `fridgesheet/web/phrasing.py` (new entries)
- Modify: `fridgesheet/web/verdicts.py` (add `say`)
- Modify: `fridgesheet/web/app.py` (register a `say` Jinja filter next to `phrase`)
- Test: `tests/test_phrasing.py`, `tests/test_verdicts.py`

**Interfaces:**
- Produces: `verdicts.say(key: str, tier: str, values: dict | None = None) -> str`. It looks up `phrasing.phrase(key, tier)` and formats it with `values`. Keys are `facts.<kind>`, `ask.<kind>`, `a.<answer>` and `where.<kind>`. The Jinja filter is `{{ 'facts.' ~ v.verdict.kind | say(tier, v.verdict.facts) }}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_verdicts.py`:

```python
def test_every_question_kind_has_facts_ask_and_answer_words():
    for kind, answers in V.ANSWERS.items():
        assert V.say("facts." + kind, "", _sample_facts(kind)) != "facts." + kind, kind
        for a in answers:
            assert V.say(a.key, "") != a.key, a.key
    for kind in ("missing_after_grade", "hac_lower", "submitted_hac_zero", "excused_hac_zero",
                 "hac_still_blank", "still_ungraded", "stale_answer"):
        assert V.say("ask." + kind, "") != "ask." + kind, kind


def _sample_facts(kind):
    return {"hac": "28 of 30", "canvas": "20 of 25", "when": "9/14", "why": "late", "flag": "done",
            "change": "Canvas now says missing", "kind": "paper", "due": "Thu 9/10"}


def test_facts_are_filled_in_and_escaped_by_the_template_not_here():
    assert V.say("facts.graded_in_hac", "", {"hac": "28 of 30"}) == "HAC has 28 of 30. Canvas still shows its automatic \"missing\"."
```

Append to `tests/test_phrasing.py`:

```python
import string


def _placeholders(s):
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def test_every_tier_of_a_sentence_uses_the_same_placeholders():
    for key, by_tier in phrasing.PHRASES.items():
        sets = {tier: _placeholders(words) for tier, words in by_tier.items()}
        assert len({frozenset(s) for s in sets.values()}) == 1, (key, sets)
```

If `phrasing` is imported under another name in that file, use that name.

- [ ] **Step 2: Run and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verdicts.py tests/test_phrasing.py`
Expected: FAIL. `say` does not exist.

- [ ] **Step 3: Implement**

In `fridgesheet/web/verdicts.py` add:

```python
from . import phrasing


def say(key: str, tier: str, values: dict | None = None) -> str:
    """The words for `key` at `tier`, with the verdict's facts filled in. The template's
    autoescaping applies to the result, so a value is never markup."""
    return phrasing.phrase(key, tier).format(**(values or {}))
```

In `fridgesheet/web/app.py`, in `_filters`, import `verdicts` and add `"say": lambda key, tier, values=None: verdicts.say(key, tier, values)` to the returned dict next to `"phrase": phrase`.

In `fridgesheet/web/phrasing.py`, add these entries to `PHRASES`. Each tier keeps the same placeholders and adds no number, date or time the `older` text lacks.

```python
    # --- verdicts: what the records show (facts), what we ask, and the answers -----------
    "facts.missing_after_grade": {"early": "HAC has {hac}, but Canvas marked it missing after that.", "middle": "HAC has {hac}, but Canvas marked it missing after that.", "older": "HAC has {hac}, but Canvas marked it missing after that."},
    "facts.graded_in_hac":   {"early": "HAC has {hac}. Canvas still says missing, but that's automatic.", "middle": "HAC has {hac}. Canvas's \"missing\" is automatic.", "older": "HAC has {hac}. Canvas still shows its automatic \"missing\"."},
    "facts.hac_lower":       {"early": "Canvas has {canvas}. HAC has {hac}.", "middle": "Canvas has {canvas}. HAC has {hac}.", "older": "Canvas has {canvas}. HAC has {hac}."},
    "facts.scores_explained": {"early": "The scores differ ({why}), and that's expected.", "middle": "The scores differ because of the {why} rule.", "older": "Canvas and HAC differ, explained by the {why} rule."},
    "facts.submitted_hac_zero": {"early": "You handed it in on {when}. HAC shows a zero.", "middle": "Handed in on Canvas {when}. HAC counts a zero.", "older": "Handed in on Canvas {when}. HAC counts a zero."},
    "facts.excused_hac_zero": {"early": "Your teacher excused it, but HAC shows a zero.", "middle": "Excused in Canvas, but HAC counts a zero.", "older": "Excused in Canvas. HAC counts a zero."},
    "facts.hac_still_blank": {"early": "Canvas has {canvas} since {when}. HAC doesn't have it yet.", "middle": "Canvas has {canvas} since {when}. HAC still has nothing.", "older": "Canvas graded it {canvas} on {when}. HAC still has nothing."},
    "facts.hac_lag":         {"early": "Canvas has {canvas}. HAC will catch up.", "middle": "Canvas has {canvas}; waiting for HAC.", "older": "Canvas has {canvas}; waiting for HAC to catch up."},
    "facts.teacher_grading": {"early": "Handed in {when}, waiting for a grade.", "middle": "Handed in {when}, not graded yet.", "older": "Handed in {when}, waiting for the teacher to grade it."},
    "facts.still_ungraded":  {"early": "This was {kind} work, due {due}. There's still no grade.", "middle": "{kind} work, due {due}. Still no grade anywhere.", "older": "{kind} work, due {due}. A week on, no grade anywhere."},
    "facts.awaiting_grade":  {"early": "This was {kind} work, due {due}. No grade yet.", "middle": "{kind} work, due {due}. No grade yet.", "older": "{kind} work, due {due}. No grade yet; grading paper takes time."},
    "facts.stale_answer":    {"early": "You said {flag} on {when}. {change}.", "middle": "You said {flag} on {when}. {change}.", "older": "You said {flag} on {when}. {change}."},
    "ask.missing_after_grade": {"early": "Which one is right?", "middle": "Which is right?", "older": "Which is right?"},
    "ask.hac_lower":         {"early": "Should we ask your teacher?", "middle": "Ask the teacher to fix HAC?", "older": "Ask the teacher to fix HAC?"},
    "ask.submitted_hac_zero": {"early": "Should we tell your teacher?", "middle": "Tell the teacher?", "older": "Tell the teacher?"},
    "ask.excused_hac_zero":  {"early": "Should we ask your teacher?", "middle": "Ask to have it excused in HAC?", "older": "Ask to have it excused in HAC?"},
    "ask.hac_still_blank":   {"early": "Should we ask your teacher?", "middle": "Ask the teacher to enter it?", "older": "Ask the teacher to enter it?"},
    "ask.still_ungraded":    {"early": "Did you hand it in?", "middle": "Was it handed in?", "older": "Was it handed in?"},
    "ask.stale_answer":      {"early": "Is it still done?", "middle": "Still done?", "older": "Still done?"},
    "a.ask_teacher":         {"early": "Ask the teacher", "middle": "Ask the teacher", "older": "Ask the teacher"},
    "a.hac_right_done":      {"early": "HAC is right, it's done", "middle": "HAC is right, it's done", "older": "HAC is right, it's done"},
    "a.hac_right":           {"early": "HAC is right", "middle": "HAC is right", "older": "HAC is right"},
    "a.zero_right":          {"early": "The zero is right", "middle": "The zero is right", "older": "The zero is right"},
    "a.leave_it":            {"early": "Leave it", "middle": "Leave it", "older": "Leave it"},
    "a.its_fine":            {"early": "It's fine", "middle": "It's fine", "older": "It's fine"},
    "a.handed_in":           {"early": "Yes, I handed it in", "middle": "Yes, handed in", "older": "Yes, handed in"},
    "a.plan_it":             {"early": "Not yet, let's plan it", "middle": "Not yet, plan it", "older": "Not yet, plan it"},
    "a.still_done":          {"early": "Yes, still done", "middle": "Yes, still done", "older": "Yes, still done"},
    "a.reopen":              {"early": "No, open it again", "middle": "No, reopen it", "older": "No, reopen it"},
```

Also add the "where it stands" words used by Task 9:

```python
    "where.answered":        {"early": "You answered this", "middle": "Answered", "older": "Answered"},
    "where.asked":           {"early": "Asked the teacher", "middle": "Asked the teacher", "older": "Asked the teacher"},
    "where.past_credit":     {"early": "Too late to fix", "middle": "Too late for credit", "older": "Too late for credit"},
    "where.teacher_grading": {"early": "Handed in, waiting", "middle": "Handed in, not graded", "older": "Handed in, not graded"},
    "where.awaiting_grade":  {"early": "Waiting for a grade", "middle": "Waiting for a grade", "older": "Waiting for a grade"},
    "where.hac_lag":         {"early": "Waiting for HAC", "middle": "Waiting for HAC", "older": "Graded in Canvas, not yet in HAC"},
    "where.graded_in_hac":   {"early": "Done: {hac} in HAC", "middle": "Done: {hac} in HAC", "older": "Done · {hac} in HAC"},
    "where.scores_explained": {"early": "Scores differ ({why}), that's expected", "middle": "Scores differ ({why})", "older": "Scores differ ({why} rule)"},
    "where.missing_after_grade": {"early": "Canvas says missing, HAC {hac}", "middle": "Canvas says missing, HAC {hac}", "older": "Missing in Canvas · {hac} in HAC"},
    "where.hac_lower":       {"early": "HAC {hac}, Canvas {canvas}", "middle": "HAC {hac}, Canvas {canvas}", "older": "HAC {hac}, Canvas {canvas}"},
    "where.submitted_hac_zero": {"early": "Handed in, HAC shows zero", "middle": "Handed in · HAC shows zero", "older": "Handed in · HAC shows zero"},
    "where.excused_hac_zero": {"early": "Excused, HAC shows zero", "middle": "Excused · HAC shows zero", "older": "Excused · HAC shows zero"},
    "where.hac_still_blank": {"early": "Canvas {canvas}, not in HAC yet", "middle": "Canvas {canvas}, not in HAC yet", "older": "Canvas {canvas} · not in HAC"},
    "where.still_ungraded":  {"early": "No grade yet", "middle": "No grade after a week", "older": "No grade after a week"},
    "where.stale_answer":    {"early": "This changed after you answered", "middle": "Changed since you answered", "older": "Changed since your answer"},
```

The `test_phrasing.py` fabrication guard compares numbers, dates and time words between tiers. The `{placeholders}` are not digits, so the entries above pass. Run it to confirm.

- [ ] **Step 4: Run and confirm they pass**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verdicts.py tests/test_phrasing.py`
Expected: PASS. If `test_the_table_covers_the_words_a_child_actually_meets` fails because it lists the table's keys, add the new keys to its expectation. Keep its intent: every word a child sees has an entry.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/phrasing.py fridgesheet/web/verdicts.py fridgesheet/web/app.py tests/
git commit -m "verdicts: tier-aware sentences for every question, answer and status"
```

---

### Task 6: `ItemView.verdict`

**Files:**
- Modify: `fridgesheet/web/stores/items.py` (`ItemView`, `_views`)
- Test: `tests/test_web_stores_pages.py`

**Interfaces:**
- Consumes: `verdicts.verdict`.
- Produces: `ItemView.verdict: verdicts.Verdict`. It defaults to `Verdict("status", "")`, so unit-built views stay valid. Later tasks read `v.verdict.state`, `.kind`, `.facts`, `.answers` and `.asks_on`. Leave `case_kinds` in place until Task 12.
- Also produces `ItemView.canvas_as_of: str` and `ItemView.hac_as_of: str`, the ISO `started_at` of the refresh that recorded each source's latest observation, or `""`. Also `ItemView.teacher_email: str`, the course's `courses.teacher_email`, or `""`. Task 8 renders all three.

- [ ] **Step 1: Write the failing test** (append to `tests/test_web_stores_pages.py`)

```python
def test_each_seeded_item_carries_the_expected_verdict(tmp_path):
    """The household in tests/web_fixtures.py, at its frozen clock (Tue 9/15 2 PM)."""
    from fridgesheet.web.stores import items, students
    conn = seed(tmp_path)
    alex = next(s for s in students.visible(conn) if s["key"] == "Alex")
    views = {v.name: v.verdict for v in items.list_items(conn, alex, now=NOW, rules=RULES, show="all")}
    assert (views["Quiz 1"].state, views["Quiz 1"].kind) == ("decided", "graded_in_hac")
    assert (views["Participation"].state, views["Participation"].kind) == ("question", "still_ungraded")
    assert (views["Lab notebook"].state, views["Lab notebook"].kind) == ("waiting", "awaiting_grade")
    assert (views["Essay draft"].state, views["Essay draft"].kind) == ("waiting", "teacher_grading")
    assert (views["Homework 4"].state, views["Homework 4"].kind) == ("status", "past_credit")


def test_views_carry_as_of_times_and_the_teacher_email(tmp_path):
    from fridgesheet.web.stores import items, students
    conn = seed(tmp_path)
    alex = next(s for s in students.visible(conn) if s["key"] == "Alex")
    quiz = next(v for v in items.list_items(conn, alex, now=NOW, rules=RULES, show="all") if v.name == "Quiz 1")
    started = conn.execute("SELECT started_at FROM refreshes ORDER BY id DESC LIMIT 1").fetchone()["started_at"]
    assert quiz.canvas_as_of == started and quiz.hac_as_of == started
    assert quiz.teacher_email == "hoch@example.org"
```

Use whatever `seed`, `NOW` and `RULES` names the file already imports. If it has no `RULES`, build `late_rules.LateRules(late_rules.Rule(), [], [])`. The default window is 14 days, and Homework 4 at 8/20 is past it.

- [ ] **Step 2: Run and confirm it fails**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_stores_pages.py -k verdict`
Expected: FAIL with `AttributeError: 'ItemView' object has no attribute 'verdict'`.

- [ ] **Step 3: Implement**

In `fridgesheet/web/stores/items.py`:
- Import: `from .. import db, outcomes, reconcile, verdicts`.
- Add the field to `ItemView`, after `credit`: `verdict: verdicts.Verdict = field(default_factory=lambda: verdicts.Verdict("status", ""))`.
- In `_views`, before the loop, load refresh times: `refresh_times = {r["id"]: r["started_at"] for r in conn.execute("SELECT id, started_at FROM refreshes")}`.
- In the `ItemView(...)` call add:

```python
            verdict=verdicts.verdict(r, obs, flag=r["flag"], flag_set_at=r["flag_set_at"] or "", now=now, rules=rules,
                                     refresh_times=refresh_times, prefer=prefer),
```

`live_items` rows already carry `flag_set_at`, `kid`, `course_name` and `peer_course_id`.

Add the other three fields to `ItemView` next to `verdict`: `canvas_as_of: str = ""`, `hac_as_of: str = ""` and `teacher_email: str = ""`. Fill them in the constructor call:

```python
            canvas_as_of=refresh_times.get(obs["canvas"]["refresh_id"], "") if "canvas" in obs else "",
            hac_as_of=refresh_times.get(obs["hac"]["refresh_id"], "") if "hac" in obs else "",
            teacher_email=r["teacher_email"] or "",
```

In `fridgesheet/web/reconcile.py` `live_items`, add `c.teacher_email AS teacher_email` to the SELECT list. The HAC course usually has no email, so for a HAC-only row also try the peer course: `COALESCE(c.teacher_email, pc.teacher_email) AS teacher_email`.

- [ ] **Step 4: Run and confirm it passes, then run the full suite**

Run the Step 2 command, then the full suite. Expected: PASS everywhere, since nothing reads `verdict` yet.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/stores/items.py tests/test_web_stores_pages.py
git commit -m "items: every view carries its verdict"
```

---

### Task 7: `flags.confirm`: re-dating a re-confirmed answer

**Files:**
- Modify: `fridgesheet/web/stores/flags.py`
- Test: `tests/test_flag_set_at.py`

**Interfaces:**
- Produces: `flags.confirm(conn, item_id, *, now: str) -> int | None`. It re-inserts the active flag with `set_at = now` and returns the new row id, or None when no flag is active.

- [ ] **Step 1: Write the failing test** (append to `tests/test_flag_set_at.py`)

```python
def test_confirming_an_answer_restarts_its_date(tmp_path):
    """Spec 5.1: "Yes, still done" must stop the stale question returning on the next refresh."""
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "done", now=ASKED, text="handed in on paper")
    assert flags.confirm(conn, qid, now="2026-09-16T08:00:00-04:00") is not None
    active = flags.active(conn, qid)
    assert (active["flag"], active["set_at"], active["text"]) == ("done", "2026-09-16T08:00:00-04:00", "handed in on paper")
    assert len(flags.history(conn, qid)) == 2


def test_confirming_with_no_flag_does_nothing(tmp_path):
    conn = seed(tmp_path)
    assert flags.confirm(conn, _item_id(conn, "Quiz 1"), now=ASKED) is None
```

- [ ] **Step 2: Run and confirm it fails**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_flag_set_at.py -k confirm`
Expected: FAIL with `AttributeError: ... no attribute 'confirm'`.

- [ ] **Step 3: Implement** (in `fridgesheet/web/stores/flags.py`, after `set_flag`)

```python
def confirm(conn: sqlite3.Connection, item_id: int, *, now: str) -> int | None:
    """Re-affirm the active flag as of `now`. Setting the same flag keeps its date (an edit of
    its reason); confirming is the family saying "still true, as of today" after the school
    contradicted it, so the stale check must measure from today."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("SELECT flag, text FROM flags WHERE item_id = ? AND cleared_at IS NULL", (item_id,)).fetchone()
        if cur is None:
            return None
        conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        return conn.execute("INSERT INTO flags(item_id, flag, text, set_at) VALUES (?, ?, ?, ?)",
                            (item_id, cur["flag"], cur["text"], now)).lastrowid
```

- [ ] **Step 4: Run and confirm it passes**

Run the Step 2 command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/stores/flags.py tests/test_flag_set_at.py
git commit -m "flags: confirm re-dates an answer the school contradicted"
```

---

### Task 8: Answering a question: route and partials

**Files:**
- Create: `fridgesheet/web/routes/questions.py` (the answer and undo routes. Task 11 adds the page route)
- Create: `fridgesheet/web/templates/_question.html`, `_answered.html`, `_record.html`
- Modify: `fridgesheet/web/app.py` (include the router the way the other routers are included)
- Test: `tests/test_web_questions.py`

**Interfaces:**
- Consumes: `ItemView.verdict`, `flags.set_flag`, `flags.clear`, `flags.confirm`, `verdicts.say`.
- Produces:
  - `POST /items/{item_id}/answer` with form fields `answer` (a flag name, `confirm` or `clear`) and `prev` (the flag before, or empty). It returns `_answered.html` for that item.
  - `POST /items/{item_id}/undo` with form field `prev`. It restores `prev` (set it, or clear it if empty) and returns `_question.html` for that item.
  - `_question.html` expects `item` (ItemView), `student` and `tier`. It renders one card with `id="q-{{ item.id }}"`.

- [ ] **Step 1: Write the failing tests** (`tests/test_web_questions.py`)

```python
"""Answering a question card (spec 5 and 6.1)."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_answering_sets_the_flag_and_collapses_to_one_line_with_undo(tmp_path):
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    c = app_for(tmp_path)
    r = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    assert r.status_code == 200
    assert f'id="q-{pid}"' in r.text and "Undo" in r.text and "Participation" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, pid)["flag"] == "done"


def test_undo_restores_the_previous_state_and_the_question(tmp_path):
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    c = app_for(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    r = c.post(f"/items/{pid}/undo", data={"prev": ""})
    assert "Was it handed in?" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, pid) is None


def test_a_double_submitted_answer_leaves_one_flag(tmp_path):
    """Review Focus 5."""
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    c = app_for(tmp_path)
    first = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    second = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    assert "Undo" in first and "Undo" in second
    conn = db.open_db(tmp_path)
    assert len([r for r in flags.history(conn, pid) if r["cleared_at"] is None]) == 1


def test_asking_the_teacher_offers_their_email(tmp_path):
    """Spec 5: the asked line carries a mailto when the course has a teacher email."""
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    body = app_for(tmp_path).post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    assert "mailto:hoch@example.org" in body


def test_the_record_says_as_of_when(tmp_path):
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    c = app_for(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    assert "as of" in c.post(f"/items/{pid}/undo", data={"prev": ""}).text


def test_an_unknown_answer_is_refused(tmp_path):
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    assert app_for(tmp_path).post(f"/items/{pid}/answer", data={"answer": "bogus", "prev": ""}).status_code == 400


def test_the_question_card_offers_the_record_and_plan_links(tmp_path):
    conn = seed(tmp_path); pid = _id(conn, "Participation"); conn.close()
    c = app_for(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    body = c.post(f"/items/{pid}/undo", data={"prev": ""}).text
    assert "See the record" in body and "Add a note" in body
    assert f"check-in/step?item_id={pid}" in body          # the "Not yet, plan it" answer
```

- [ ] **Step 2: Run and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_questions.py`
Expected: FAIL with 404 or 405, because the routes don't exist.

- [ ] **Step 3: Implement the route** (`fridgesheet/web/routes/questions.py`)

```python
"""Questions: answer one, undo an answer. The page itself is added in Task 11."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, render_partial
from ..stores import flags, items, students
from .. import db

router = APIRouter()
ANSWERS = set(flags.FLAGS) | {"confirm", "clear"}


def _view(conn, state, item_id):
    s = students.owner_of_item(conn, item_id)
    v = items.one(conn, s, item_id, now=state.now(), rules=state.rules(), prefs=state.sources()) if s is not None else None
    if v is None:
        raise HTTPException(404, "no such item")
    return s, v


def _apply(conn, item_id, answer, now):
    if answer == "clear" or answer == "":
        flags.clear(conn, item_id, now=now)
    elif answer == "confirm":
        flags.confirm(conn, item_id, now=now)
    else:
        flags.set_flag(conn, item_id, answer, now=now)


@router.post("/items/{item_id}/answer")
def answer(item_id: int, request: Request, answer: str = Form(...), prev: str = Form(""),
           conn: sqlite3.Connection = Db, state=State):
    if answer not in ANSWERS:
        raise HTTPException(400, f"unknown answer {answer!r}")
    _view(conn, state, item_id)
    _apply(conn, item_id, answer, db.now_iso(state.tz))
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_answered.html", student=s, item=v, prev=prev)


@router.post("/items/{item_id}/undo")
def undo(item_id: int, request: Request, prev: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    if prev and prev not in flags.FLAGS:
        raise HTTPException(400, f"unknown flag {prev!r}")
    _view(conn, state, item_id)
    _apply(conn, item_id, prev or "clear", db.now_iso(state.tz))
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_question.html", student=s, item=v)
```

Register the router in `fridgesheet/web/app.py` the same way `routes.flags` is registered.

- [ ] **Step 4: Implement the partials**

`fridgesheet/web/templates/_record.html`:

```html
{# The school record behind a verdict: what each source says, and as of when. #}
<div class="record" id="record-{{ item.id }}">
  {% if item.canvas %}<div><span class="src">Canvas{% if item.canvas_as_of %} <small>as of {{ item.canvas_as_of | wd_md_time }}</small>{% endif %}</span><span>{% if item.canvas.missing %}marked missing{% elif item.canvas.submitted_at %}handed in {{ item.canvas.submitted_at | wd_md_time }}{% elif item.kind in ('paper', 'in class') %}nothing to submit online{% else %}nothing submitted{% endif %}{% if item.canvas.score is not none %} · {{ item.canvas.score | round(1) | string | replace('.0', '') }}{% if item.points %} of {{ item.points | round(1) | string | replace('.0', '') }}{% endif %}{% endif %}</span></div>{% endif %}
  {% if item.hac %}<div><span class="src">HAC{% if item.hac_as_of %} <small>as of {{ item.hac_as_of | wd_md_time }}</small>{% endif %}</span><span>{% if item.hac.score is not none %}{{ item.hac.score | round(1) | string | replace('.0', '') }}{% if item.points %} of {{ item.points | round(1) | string | replace('.0', '') }}{% endif %}{% else %}no grade{% endif %}</span></div>{% endif %}
</div>
```

`fridgesheet/web/templates/_question.html`:

```html
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
{% set vd = item.verdict %}
<div class="q card" id="q-{{ item.id }}" data-focus>
  <div class="what"><span><b tabindex="-1" data-focus-target>{{ item.name }}</b> · {{ item.course_short }}{% if item.kind in ('paper', 'in class') %} · {{ item.kind }}{% endif %}</span>{% if item.due %}<span>due {{ item.due | wd_md }}</span>{% endif %}</div>
  <p class="facts">{{ ('facts.' ~ vd.kind) | say(tier, vd.facts) }}</p>
  {% if vd.state == 'question' %}<p class="ask">{{ ('ask.' ~ vd.kind) | say(tier) }}</p>{% endif %}
  <div class="answers">
    {% for a in vd.answers %}
      {% if a.flag is none %}<a class="button-link" href="/kids/{{ student.key | urlencode }}/check-in/step?item_id={{ item.id }}">{{ a.key | say(tier) }}</a>
      {% else %}<form hx-post="/items/{{ item.id }}/answer" hx-target="#q-{{ item.id }}" hx-swap="outerHTML"><input type="hidden" name="prev" value="{{ item.flag or '' }}"><button name="answer" value="{{ a.flag }}" class="{{ 'primary' if loop.first }}">{{ a.key | say(tier) }}</button></form>{% endif %}
    {% endfor %}
  </div>
  <details class="more"><summary>See the record</summary>{% include "_record.html" %}</details>
  <p class="more"><a href="#detail-{{ item.id }}" hx-get="/items/{{ item.id }}" hx-target="#q-{{ item.id }}" hx-swap="outerHTML">Add a note</a></p>
</div>
```

`fridgesheet/web/templates/_answered.html`:

```html
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
<div class="done-line" id="q-{{ item.id }}" role="status" data-focus>
  <span class="tick" aria-hidden="true">✓</span>
  <span tabindex="-1" data-focus-target><b>{{ item.name }}</b>: {{ ('where.' ~ item.verdict.kind) | say(tier, item.verdict.facts) }}{% if item.verdict.kind == 'asked' and item.teacher_email %} · <a href="mailto:{{ item.teacher_email }}?subject={{ ('About ' ~ item.name) | urlencode }}">Email the teacher</a>{% endif %}</span>
  <form hx-post="/items/{{ item.id }}/undo" hx-target="#q-{{ item.id }}" hx-swap="outerHTML"><input type="hidden" name="prev" value="{{ prev }}"><button class="link">Undo</button></form>
</div>
```

Add to `fridgesheet/web/static/app.css`, taking the values from mockup v4:

```css
/* Questions (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md) */
.q { background: var(--paper); border: 1px solid var(--rule); border-radius: 10px; padding: 14px 16px 12px; margin-bottom: 10px; }
.q .what { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; color: var(--muted); }
.q .what b { color: var(--ink); font-size: 15px; }
.q .facts { margin: 6px 0 2px; }
.q .ask { font-weight: 600; margin: 8px 0 10px; }
.q .answers { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.q .answers form { display: inline; margin: 0; }
.q .more { margin-top: 10px; font-size: 13px; }
.record { margin-top: 8px; padding: 10px 12px; background: var(--wash); border-radius: 8px; font-size: 13px; }
.record div { display: grid; grid-template-columns: 170px 1fr; gap: 8px; }
.record .src small { color: var(--muted); }
.record .src { color: var(--muted); }
.done-line { display: flex; align-items: center; gap: 10px; background: #edf6ee; border-radius: 10px; padding: 10px 16px; margin-bottom: 10px; }
.done-line .tick { color: var(--ok); font-weight: 700; }
.done-line form { margin-left: auto; }
button.link { border: none; background: none; color: var(--muted); text-decoration: underline; cursor: pointer; }
```

- [ ] **Step 5: Run and confirm the tests pass**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_questions.py`
Expected: PASS. After an answer, Participation's verdict is `answered`, and `where.answered` renders "Answered". The HAC-only Participation row has no email of its own, so `teacher_email` comes from the peer Canvas course, which is Mr. Hoch's.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/routes/questions.py fridgesheet/web/templates/_question.html fridgesheet/web/templates/_answered.html fridgesheet/web/templates/_record.html fridgesheet/web/app.py fridgesheet/web/static/app.css tests/test_web_questions.py
git commit -m "questions: answer a card in place, with undo"
```

---

### Task 9: The kid page: questions, decided, waiting, and a quiet work list

**Files:**
- Modify: `fridgesheet/web/routes/kid.py` (`kid`)
- Modify: `fridgesheet/web/templates/kid.html`, `fridgesheet/web/templates/_item_rows.html`
- Create: `fridgesheet/web/templates/_verdict_sections.html`
- Modify: `fridgesheet/web/static/app.css` (the red rule, #34)
- Test: `tests/test_web_kid_questions.py`; update `tests/test_web_kid_table.py`, `tests/test_web_pages.py` and `tests/test_web_tier_*.py`

**Interfaces:**
- Consumes: `ItemView.verdict`, `_question.html`, `verdicts.say`.
- Produces: `kid.html` renders `_verdict_sections.html` with `questions`, `decided` and `waiting` (lists of ItemView), computed with `show="all"` whatever the table filter says.

- [ ] **Step 1: Write the failing tests** (`tests/test_web_kid_questions.py`)

```python
"""The kid page's three sections above the work list (spec 6.1)."""
from __future__ import annotations

import re

from tests.web_fixtures import app_for, seed


def _page(tmp_path, q=""):
    seed(tmp_path).close()
    return app_for(tmp_path).get(f"/kids/Alex{q}").text


def test_alex_has_one_question_one_decided_and_two_waiting(tmp_path):
    body = _page(tmp_path)
    assert "1 question about" in body
    assert re.search(r'id="q-\d+"[^>]*>.*?Participation', body, re.S)
    decided = body[body.index("Decided for you"):body.index("Waiting")]
    assert "Quiz 1" in decided and "Not right?" in decided
    waiting = body[body.index("Waiting"):body.index('id="items"')]
    assert "Essay draft" in waiting and "Lab notebook" in waiting and "Ask now" in waiting


def test_sections_ignore_the_table_filter(tmp_path):
    assert "1 question about" in _page(tmp_path, "?course=999")


def test_the_work_list_has_three_columns_and_no_sources_or_actionable(tmp_path):
    body = _page(tmp_path, "?show=all")
    table = body[body.index('id="items"'):]
    assert "Where it stands" in table and "Sources" not in table and "actionable" not in table


def test_red_marks_only_school_recorded_not_done(tmp_path):
    table = _page(tmp_path, "?show=all")
    rows = dict(re.findall(r'<tr[^>]*id="row-\d+"[^>]*>.*?<a[^>]*>([^<]+)</a>.*?<td class="where([^"]*)"', table, re.S))
    assert "red" in rows["Homework 4"]            # Canvas marked it missing
    assert "red" not in rows["Lab notebook"]      # the app is waiting, not the school saying no
    assert "red" not in rows["Quiz 1"]            # decided done


def test_more_filters_keeps_the_old_selects_behind_a_disclosure(tmp_path):
    body = _page(tmp_path)
    more = body[body.index("<details class=\"more-filters\""):]
    for name in ("source", "kind", "flagged", "outcome"):
        assert f'name="{name}"' in more
```

- [ ] **Step 2: Run and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_kid_questions.py`
Expected: FAIL. None of the sections exist yet.

- [ ] **Step 3: Implement the route**

In `fridgesheet/web/routes/kid.py`, `kid()`, after `rows = ...`:

```python
    everything = items.list_items(conn, s, now=now, rules=rules, days_ahead=state.days_ahead(), prefs=state.sources(), show="all")
    by_state = {st: [v for v in everything if v.verdict.state == st] for st in ("question", "decided", "waiting")}
```

Pass `questions=by_state["question"], decided=by_state["decided"], waiting=by_state["waiting"]` to `render`.

- [ ] **Step 4: Implement `_verdict_sections.html`**

```html
{% set tier = student.key | tier_of %}
{% if questions %}
<section class="questions" aria-labelledby="q-head">
  <div class="section-head"><h3 id="q-head">{{ questions | length }} question{{ 's' if questions | length != 1 }} about {{ student.key | nickname }}'s work</h3><span class="muted">Answering one takes it off this list</span></div>
  {% for item in questions %}{% include "_question.html" %}{% endfor %}
</section>
{% endif %}
{% if decided %}
<section class="decided" aria-labelledby="d-head">
  <h3 id="d-head" class="quiet-head">Decided for you</h3>
  <div class="lines">{% for item in decided %}
    <div class="line" id="q-{{ item.id }}"><span class="tick" aria-hidden="true">✓</span><span><b>{{ item.name }}</b> <span class="muted">{{ ('facts.' ~ item.verdict.kind) | say(tier, item.verdict.facts) }}</span></span>
      <a href="#q-{{ item.id }}" hx-post="/items/{{ item.id }}/undo" hx-vals='{"prev": "{{ item.flag or '' }}"}' hx-target="#q-{{ item.id }}" hx-swap="outerHTML">Not right?</a></div>
  {% endfor %}</div>
</section>
{% endif %}
{% if waiting %}
<details class="quiet"><summary>Waiting, nothing to do yet ({{ waiting | length }})</summary>
  <div class="lines">{% for item in waiting %}
    <div class="line" id="q-{{ item.id }}"><span class="clock" aria-hidden="true">◷</span><span><b>{{ item.name }}</b> <span class="muted">{{ ('facts.' ~ item.verdict.kind) | say(tier, item.verdict.facts) }}{% if item.verdict.asks_on %} Asks you after {{ item.verdict.asks_on | wd_md }}.{% endif %}</span></span>
      {% if item.verdict.answers %}<form hx-post="/items/{{ item.id }}/answer" hx-target="#q-{{ item.id }}" hx-swap="outerHTML"><input type="hidden" name="prev" value=""><button class="link" name="answer" value="ask_teacher">Ask now</button></form>{% endif %}</div>
  {% endfor %}</div>
</details>
{% endif %}
```

"Not right?" posts to `/undo` with the current flag. That renders `_question.html` for the item, and the card shows the decided verdict's answers, which Task 3 attached to every decided verdict.

- [ ] **Step 5: Implement `kid.html` and `_item_rows.html`**

In `kid.html`, include `_verdict_sections.html` between `_child_nav.html` and the filter form. Replace the filter form's contents with:

```html
  <span class="seg" role="group" aria-label="Show">
    <label><input type="radio" name="show" value="open" {{ 'checked' if f.show != 'all' }}> Open</label>
    <label><input type="radio" name="show" value="all" {{ 'checked' if f.show == 'all' }}> Everything</label>
  </span>
  <label>Class <select name="course"><option value="">All classes</option>{% for cid, label in course_options %}<option value="{{ cid }}" {{ 'selected' if f.course_id == cid }}>{{ label }}</option>{% endfor %}</select></label>
  <details class="more-filters"{{ ' open' if f.source or f.kind or f.flagged or f.outcome }}><summary>More filters</summary>
    <label>Which gradebook <select name="source"><option value="">either</option><option value="canvas" {{ 'selected' if f.source == 'canvas' }}>in Canvas</option><option value="hac" {{ 'selected' if f.source == 'hac' }}>in HAC</option><option value="both" {{ 'selected' if f.source == 'both' }}>in both</option></select></label>
    <label>Kind of work <select name="kind"><option value="">any</option>{% for v in ("online", "paper", "in class") %}<option value="{{ v }}" {{ 'selected' if f.kind == v }}>{{ v }}</option>{% endfor %}</select></label>
    <label>Your answer <select name="flagged"><option value="">any</option><option value="any" {{ 'selected' if f.flagged == 'any' }}>answered or asked</option><option value="handled" {{ 'selected' if f.flagged == 'handled' }}>done, excused or let go</option><option value="marked" {{ 'selected' if f.flagged == 'marked' }}>asked the teacher or following up</option><option value="none" {{ 'selected' if f.flagged == 'none' }}>not answered</option></select></label>
    <label>Outcome <select name="outcome"><option value="">any</option>{% for v in OUTCOMES %}<option value="{{ v }}" {{ 'selected' if f.outcome == v }}>{{ OUTCOME_LABELS[v] }}</option>{% endfor %}</select></label>
  </details>
  <input type="hidden" name="sort" value="{{ f.sort }}">
  <input type="hidden" name="dir" value="{{ f.direction }}">
```

In `_item_rows.html`, replace the header and row with three columns. Keep the `sortable` macro and the `tier` line at the top of the file.

```html
<table class="items work">
  <thead><tr>
    {{ sortable('due', 'Due') }}
    {{ sortable('name', 'Assignment') }}
    {{ sortable('status', 'Where it stands') }}
  </tr></thead>
  <tbody>
  {% for v in rows %}
  <tr id="row-{{ v.id }}">
    <td class="due">{{ v.due | md if v.due else '' }}{% if tier == 'early' %}{% if v.due_part %} <span class="at">{{ v.due_part }}</span>{% endif %}{% elif v.due_time %} <span class="at">{{ v.due_time }}</span>{% endif %}{% if v.due_relative %}<small class="rel">{{ v.due_relative }}</small>{% endif %}</td>
    <td class="item"><a href="#detail-{{ v.id }}" hx-get="/items/{{ v.id }}" hx-target="#detail-{{ v.id }}" hx-swap="innerHTML">{{ v.name }}</a>
        {% if v.verdict.state == 'question' %}<a class="qmark" href="#q-{{ v.id }}">question</a>{% endif %}
        {% if v.notes %}<span class="badge">{{ v.notes }} note{{ 's' if v.notes != 1 }}</span>{% endif %}
        <small><a href="/kids/{{ student.key | urlencode }}/courses/{{ v.course_id }}">{{ v.course_short }}</a>{% if v.kind in ('paper', 'in class') %} · {{ v.kind }}{% endif %}</small></td>
    {# Red only when the school recorded not-done and the app did not settle it otherwise. #}
    {% set school_no = (v.grade == 'Missing' or v.grade_zero) and v.verdict.state != 'decided' %}
    <td class="where{{ ' red' if school_no }}">{% if v.verdict.state != 'status' or v.verdict.kind in ('answered', 'asked', 'past_credit') %}{{ ('where.' ~ v.verdict.kind) | say(tier, v.verdict.facts) }}{% elif v.grade %}{{ v.grade | phrase(tier) }}{% else %}{{ v.status | phrase(tier) }}{% endif %}</td>
  </tr>
  <tr class="detail"><td colspan="3" id="detail-{{ v.id }}"></td></tr>
  {% else %}
  <tr><td colspan="3" class="muted">Nothing matches these filters.</td></tr>
  {% endfor %}
  </tbody>
</table>
```

`course.html` includes the same partial and gets the same three columns. That is intended.

- [ ] **Step 6: The red rule (#34)** in `fridgesheet/web/static/app.css`

Replace `tr.overdue td.due { color: var(--warn); }` with nothing. Replace `td.grade.zero, td.grade.missing, td.handed.no { color: var(--warn); font-weight: 600; }` with:

```css
td.where.red { color: var(--warn); font-weight: 600; }
table.work td.item small { display: block; color: var(--muted); font-size: 13px; }
table.work td.item small a { color: inherit; }
table.work td.due small.rel { display: block; }
.qmark { font-size: 12px; color: var(--accent); background: #eaf1fa; border-radius: 10px; padding: 0 8px; margin-left: 6px; text-decoration: none; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; }
.quiet-head { font-size: 14px; color: var(--muted); }
.lines { background: var(--paper); border: 1px solid var(--rule); border-radius: 10px; padding: 4px 16px; margin-bottom: 10px; }
.lines .line { display: flex; gap: 10px; align-items: baseline; padding: 8px 0; border-bottom: 1px solid var(--rule); }
.lines .line:last-child { border-bottom: none; }
.lines .line > a, .lines .line > form { margin-left: auto; font-size: 13px; }
.seg label { margin-right: 8px; }
.more-filters { display: inline-block; }
```

- [ ] **Step 7: Run the new tests, then the full suite, and update the table tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_kid_questions.py` and expect PASS. Then run the full suite. Update tests that assert the old columns or old words. They are in `tests/test_web_kid_table.py`, `tests/test_web_pages.py`, `tests/test_web_course_*.py`, `tests/test_web_tier_*.py` and `tests/test_web_status_parts.py`. Change them as follows:
- "Handed in", "Grade" and "Sources" headers become "Where it stands".
- `colspan="6"` becomes `colspan="3"`.
- The `actionable` badge is gone.
- The tier parity test (`tests/test_web_tier_parity.py`) must still pass unchanged. It compares row ids, which this task keeps. Add one case to it that compares the set of `id="q-..."` ids on `/kids/Alex` across every tier. Build it the same way the file's existing cases are built. A younger tier must never hide a question.

Do not weaken a test's intent. If a test checked that a zero is red, it now checks that `td.where` has class `red`.

- [ ] **Step 8: Commit**

```bash
git add fridgesheet/web/ tests/
git commit -m "kid page: questions, decided and waiting above a three-column work list"
```

---

### Task 10: The item detail becomes the question card plus notes

**Files:**
- Modify: `fridgesheet/web/templates/_item_detail.html`
- Modify: `fridgesheet/web/routes/kid.py` (`item_detail`: drop `cases`), `fridgesheet/web/routes/flags.py` (drop `cases`)
- Test: `tests/test_web_pages.py`

**Interfaces:**
- Consumes: `_question.html`, `_record.html`, `_flag_menu.html` and `_notes.html`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_web_pages.py`)

```python
def test_item_detail_is_the_verdict_the_record_notes_and_a_more_menu(tmp_path):
    conn = seed(tmp_path)
    pid = _item_id(conn, "Participation")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{pid}").text
    assert "Was it handed in?" in body                     # the question card
    assert 'class="record"' in body                        # the evidence
    assert "<summary>More</summary>" in body and 'value="excused"' in body   # the raw flags, behind More
    assert "<th>Says</th>" not in body                     # the old Source/Says table is gone
```

- [ ] **Step 2: Run and confirm it fails**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_pages.py -k verdict_the_record`
Expected: FAIL.

- [ ] **Step 3: Implement.** Replace `_item_detail.html`:

```html
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
<div class="card" data-focus>
  <h2 tabindex="-1" data-focus-target>{{ item.name }} <span class="muted">· {{ item.course_short }}{% if item.kind %} · {{ item.kind }}{% endif %}{% if item.points %} · {{ item.points | round(1) | string | replace('.0', '') }} pts{% endif %}</span></h2>
  {% if message %}<p role="status"><strong>{{ message }}</strong></p>{% endif %}
  {% if item.verdict.state in ('question', 'decided', 'waiting') %}{% include "_question.html" %}{% else %}{% include "_record.html" %}{% endif %}
  <p><a href="/kids/{{ student.key | urlencode }}/check-in/step?item_id={{ item.id }}">Plan a step</a></p>
  <details><summary>More</summary>{% include "_flag_menu.html" %}</details>
  {% set target_type = "item" %}{% set target_id = item.id %}
  {% include "_notes.html" %}
</div>
```

In `routes/kid.py` `item_detail` and `routes/flags.py` `set_item_flag`, delete the `cases = [...]` lines and the `cases=cases` argument.

- [ ] **Step 4: Run the full suite and fix the detail-card tests**

Expected failures are in the tests that asserted `Choose a next step`, the Source/Says table, or a case reason in the detail. They include `test_item_detail_shows_both_sources_cases_notes_and_the_flag_menu` and tests in `tests/test_reconcile_traps.py`. Change them as follows:
- "Choose a next step" becomes "Plan a step".
- The case reason becomes the verdict sentence.
- The flag buttons are asserted inside `<details>`.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/ tests/
git commit -m "item detail: the verdict and its record, with raw flags behind More"
```

---

### Task 11: The Questions page, the redirect, the nav and "can't pair these"

**Files:**
- Modify: `fridgesheet/web/routes/questions.py` (add `GET /questions`, and the bulk past-credit route moved from `routes/reconcile.py`)
- Modify: `fridgesheet/web/routes/reconcile.py` (keep only a redirect)
- Create: `fridgesheet/web/templates/questions.html`
- Modify: `fridgesheet/web/templates/base.html` (nav label and counts), `fridgesheet/web/app.py` (`page_context` adds `question_counts`), `fridgesheet/web/templates/open.html` (past-credit link target)
- Modify: `fridgesheet/web/stores/items.py` (add `near_twins`)
- Test: `tests/test_web_questions_page.py`

**Interfaces:**
- Produces: `items.near_twins(conn, views: list[ItemView]) -> list[tuple[ItemView, ItemView]]`. It returns pairs of one-source items in paired courses, due within 3 days of each other, whose titles share at least 40% of their words (Jaccard over `matching.norm_name(...).split()`), and which `matching.same_item` did not pair.

- [ ] **Step 1: Write the failing tests** (`tests/test_web_questions_page.py`)

```python
"""The Questions page, which replaces Reconcile (spec 6.2)."""
from __future__ import annotations

from tests.web_fixtures import app_for, seed


def test_questions_groups_every_kids_questions(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/questions").text
    assert "<h2>Questions</h2>" in body
    assert "Alex" in body and "Participation" in body and "Was it handed in?" in body
    assert "Quiz 1" not in body                          # decided, not asked


def test_reconcile_redirects_to_questions_keeping_the_kid(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/reconcile?kid=Alex", follow_redirects=False)
    assert r.status_code in (301, 307, 308) and r.headers["location"] == "/questions?kid=Alex"


def test_the_nav_says_questions_with_a_count(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    assert ">Questions" in body and "Reconcile" not in body


def test_bulk_let_go_appears_only_with_two_or_more_past_credit_items(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/questions").text
    assert "too late for credit" not in body             # Alex has one (Homework 4), Sam none
```

Add to `tests/test_web_stores_pages.py`:

```python
def test_near_twins_lists_a_missed_pairing_and_not_unrelated_work(tmp_path):
    from fridgesheet.web import ingest
    from fridgesheet.web.stores import items, students
    from tests.web_fixtures import snapshot, TZ
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    eng["assignments"].append(dict(eng["assignments"][-1], id=83, name="Participation grade",
                                   due_at="2026-09-09T23:59:00-04:00", submission_types=["none"]))
    conn = seed(tmp_path, snap)
    alex = next(s for s in students.visible(conn) if s["key"] == "Alex")
    views = items.list_items(conn, alex, now=NOW, rules=RULES, show="all")
    pairs = {(c.name, h.name) for c, h in items.near_twins(conn, views)}
    assert ("Participation grade", "Participation") in pairs
    assert not any(c == "Lab notebook" for c, _ in pairs)
```

`seed(home, snap)` takes a snapshot as its second argument. If the ingest pairs "Participation grade" with "Participation" on its own, which it should not at 50% word overlap and different dates, the first assertion will fail. In that case pick a title with 40–69% word overlap instead.

- [ ] **Step 2: Run and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_web_questions_page.py`
Expected: FAIL. `/questions` returns 404.

- [ ] **Step 3: Implement `near_twins`** (in `fridgesheet/web/stores/items.py`)

```python
from ...matching import norm_name, same_item


def near_twins(conn: sqlite3.Connection, views: list[ItemView]) -> list[tuple[ItemView, ItemView]]:
    """One-source items that are probably one assignment the pairing missed: in a course and
    its twin, due within three days, titles sharing at least 40% of their words. For the
    maintainer (spec cause 7), never a question for the family."""
    peers = {r["id"]: r["peer_course_id"] for r in conn.execute("SELECT id, peer_course_id FROM courses")}
    canvas_only = [v for v in views if v.sources == ("canvas",)]
    hac_only = [v for v in views if v.sources == ("hac",)]
    out = []
    for c in canvas_only:
        for h in hac_only:
            if peers.get(c.course_id) != h.course_id or c.due is None or h.due is None:
                continue
            a, b = reconcile.comparable(c.due, h.due)
            if abs((a - b).days) > 3 or same_item(c.name, h.name):
                continue
            wa, wb = set(norm_name(c.name).split()), set(norm_name(h.name).split())
            if wa and wb and len(wa & wb) / len(wa | wb) >= 0.4:
                out.append((c, h))
    return out
```

- [ ] **Step 4: Implement the page route and the redirect**

In `fridgesheet/web/routes/questions.py`, add these imports: `from fastapi.responses import RedirectResponse`, `from ..app import render`, and `from ..stores import students`. Then add:

```python
@router.get("/questions")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    kid = request.query_params.get("kid") or None
    now, rules, prefs = state.now(), state.rules(), state.sources()
    groups = []
    for s in students.visible(conn):
        if kid and s["key"] != kid:
            continue
        views = items.list_items(conn, s, now=now, rules=rules, show="all", prefs=prefs)
        groups.append({
            "student": s,
            "questions": [v for v in views if v.verdict.state == "question"],
            "past_credit": [v for v in views if v.verdict.kind == "past_credit"],
            "twins": items.near_twins(conn, views),
        })
    return render(request, conn, "questions.html", current="questions", groups=groups, kid=kid)


@router.post("/questions/let-go")
def let_go(request: Request, kid: str = Form(...), conn: sqlite3.Connection = Db, state=State):
    """Ignore every one of one kid's past-credit items, after the page's confirm. One kid at a
    time: a button that hides a whole household's work in one click hides a problem."""
    s = next((s for s in students.visible(conn) if s["key"] == kid), None)
    if s is None:
        raise HTTPException(404, f"no student {kid!r}")
    now = db.now_iso(state.tz)
    for v in items.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", prefs=state.sources()):
        if v.verdict.kind == "past_credit":
            flags.set_flag(conn, v.id, "ignore", now=now, text="past the late-work window")
    return RedirectResponse(f"/questions?kid={kid}", status_code=303)
```

Replace the body of `fridgesheet/web/routes/reconcile.py` with:

```python
"""`/reconcile` was the page of cases; it is now Questions (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md)."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/reconcile")
def page(request: Request):
    kid = request.query_params.get("kid")
    return RedirectResponse("/questions" + (f"?{urlencode({'kid': kid})}" if kid else ""), status_code=308)
```

- [ ] **Step 5: Implement `questions.html`**

```html
{% extends "base.html" %}
{% block title %}Questions · Fridge Sheet{% endblock %}
{% block content %}
<h2>Questions</h2>
<p class="muted">Where the school's records disagree, or say too little to act on. Answer one and it leaves this page.</p>
{% for g in groups %}
{% set student = g.student %}{% set tier = student.key | tier_of %}
<section class="kid-questions">
  <div class="section-head"><h3>{{ student.key | nickname }} · {{ g.questions | length }}</h3><a href="/kids/{{ student.key | urlencode }}">Open {{ student.key | nickname }}'s work →</a></div>
  {% if g.past_credit | length >= 2 %}
  <form class="lines bulk" method="post" action="/questions/let-go" data-confirm="Let all {{ g.past_credit | length }} go? They leave the sheet and this page; nothing is deleted.">
    <input type="hidden" name="kid" value="{{ student.key }}">
    <span>{{ g.past_credit | length }} of {{ student.key | nickname }}'s assignments are too late for credit.</span> <button>Let all {{ g.past_credit | length }} go</button>
  </form>
  {% endif %}
  {% for item in g.questions %}{% include "_question.html" %}{% else %}<p class="muted">Nothing to ask about {{ student.key | nickname }}'s work.</p>{% endfor %}
  {% if g.twins %}
  <details class="quiet"><summary>Can't pair these ({{ g.twins | length }})</summary>
    <p class="muted">These may be one assignment listed under two names. The app keeps them apart; nothing is asked of the family.</p>
    <ul>{% for c, h in g.twins %}<li>Canvas "{{ c.name }}" ({{ c.due | wd_md }}) and HAC "{{ h.name }}" ({{ h.due | wd_md }})</li>{% endfor %}</ul>
  </details>
  {% endif %}
</section>
{% endfor %}
{% endblock %}
```

- [ ] **Step 6: Implement the nav and counts**

In `fridgesheet/web/app.py` add:

```python
def question_counts(conn: sqlite3.Connection, state) -> dict[str, int]:
    """How many questions each kid has, for the rail. This runs every verdict for every kid on
    every page render: fine at household scale (tens of items per kid). If it ever shows up in
    a profile, cache it per refresh id."""
    from .stores import items as items_store
    out = {}
    for s in students.visible(conn):
        views = items_store.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", prefs=state.sources())
        out[s["key"]] = sum(1 for v in views if v.verdict.state == "question")
    return out
```

In `page_context`, add `"question_counts": question_counts(conn, state),` to the returned dict. The import is local because `stores.items` imports `app`-level modules, and a top-level import risks a cycle.

In `base.html`, change the Reconcile nav link to `<a href="/questions" class="{{ 'current' if current == 'questions' }}">Questions{% set n = question_counts.values() | sum %}{% if n %} <span class="count">{{ n }}</span>{% endif %}</a>`. Next to each kid link, add `{% if question_counts.get(s.key) %} <span class="count">{{ question_counts[s.key] }}</span>{% endif %}`. Add `.rail .count { color: var(--accent); font-weight: 600; font-size: 12px; }` to `app.css`.

In `open.html`, point the past-credit link at `/kids/{{ s.key }}?show=all&outcome=not_done` instead of `/reconcile?...`. Then run `grep -rn "reconcile" fridgesheet/web/templates fridgesheet/web/routes`. Expect only `routes/reconcile.py`'s redirect and `templates/reconcile.html`, which Task 12 deletes. Repoint any other link to `/questions`.

- [ ] **Step 7: Run and confirm the tests pass, then run the full suite**

Expected: the new tests PASS. `tests/test_web_reconcile_page.py` and `tests/test_web_reconcile_bulk.py` now fail, because the page they test is gone. Delete `test_web_reconcile_page.py`. Rewrite `test_web_reconcile_bulk.py` as `tests/test_web_questions_bulk.py`. Keep its intent: one kid only, an unknown kid returns 404, and only past-credit items are flagged. Aim it at `/questions/let-go`.

- [ ] **Step 8: Commit**

```bash
git add fridgesheet/web/ tests/
git commit -m "Questions page replaces Reconcile; nav counts; can't-pair list for the maintainer"
```

---

### Task 12: Move the remaining readers to verdicts, then delete the case machinery

**Files:**
- Modify: `fridgesheet/web/routes/checkin.py` (`_group`, `queue_for`), `fridgesheet/web/templates/_planning_evidence.html`, `fridgesheet/web/templates/open.html`, `fridgesheet/web/views.py`
- Modify: `fridgesheet/web/stores/items.py` (delete `case_kinds`, `with_cases` and the `reconcile.cases` call)
- Modify: `fridgesheet/web/reconcile.py` (delete `Case`, `KINDS`, `cases`, `_score_text` if unused)
- Modify: `fridgesheet/web/phrasing.py` (delete the six case-kind entries)
- Delete: `fridgesheet/web/templates/reconcile.html`, `fridgesheet/web/templates/_case_group.html`
- Tests: `tests/test_checkin_queue.py`, `tests/test_reconcile.py`, `tests/test_reconcile_traps.py`, `tests/test_web_checkin.py`, `tests/test_phrasing.py`, `tests/test_web_views.py`

- [ ] **Step 1: Write the failing check-in tests** (replace `tests/test_checkin_queue.py`'s `view()` helper and tests)

```python
from fridgesheet.web import verdicts as V


def view(**kw):
    base = dict(id=1, outcome=outcomes.NOT_DONE, canvas=None, hac=None, grade_zero=False,
                open_in={"canvas"}, upcoming=False, due=None, handled=False, verdict=V.Verdict(V.STATUS, "not_done"))
    base.update(kw)
    return SimpleNamespace(**base)


def test_handled_work_stays_out_of_review():
    assert checkin.queue_for(view(handled=True, verdict=V.Verdict(V.STATUS, "answered")), covered=set()) is None


def test_a_stale_answer_needs_clarification_even_when_handled():
    v = view(handled=True, open_in=set(), verdict=V.Verdict(V.QUESTION, "stale_answer"))
    assert checkin.queue_for(v, covered=set()) == "Needs clarification"


def test_any_question_needs_clarification():
    assert checkin.queue_for(view(verdict=V.Verdict(V.QUESTION, "hac_lower")), covered=set()) == "Needs clarification"


def test_waiting_on_the_teacher_is_the_waiting_group():
    v = view(open_in=set(), verdict=V.Verdict(V.WAITING, "teacher_grading"))
    assert checkin.queue_for(v, covered=set()) == "Submitted · waiting for a grade"


def test_work_with_an_agreed_step_stays_out_of_review():
    assert checkin.queue_for(view(verdict=V.Verdict(V.QUESTION, "hac_lower")), covered={1}) is None


def test_open_work_is_work_to_consider():
    assert checkin.queue_for(view(), covered=set()) == "Work to consider"
```

- [ ] **Step 2: Run and confirm they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_checkin_queue.py`
Expected: the question and waiting tests FAIL.

- [ ] **Step 3: Implement the check-in change** (`fridgesheet/web/routes/checkin.py`)

```python
def queue_for(v, covered: set[int]) -> str | None:
    """The review group for one item at a check-in, or None to leave it out. A question is
    something to clarify together; waiting on the teacher is its own group; handled work
    stays out unless the school has since contradicted the answer."""
    if v.id in covered:
        return None
    if v.handled:
        return QUEUES[1] if v.verdict.kind == "stale_answer" else None
    if v.verdict.state == "question":
        return QUEUES[1]
    if v.verdict.kind == "teacher_grading":
        return QUEUES[2]
    return _group(v)
```

In `_group`, change `uncertain = v.grade_zero or v.outcome == outcomes.UNKNOWN or "disagree" in v.case_kinds` to `uncertain = v.grade_zero or v.outcome == outcomes.UNKNOWN`.

- [ ] **Step 4: Move the other readers**

- `_planning_evidence.html`: replace the two `case_kinds` lines with `{% if view.verdict.state in ('question', 'decided') %}<p class="review-note">{{ ('facts.' ~ view.verdict.kind) | say(tier | default(''), view.verdict.facts) }}</p>{% endif %}`. Keep the `outcome == 'unknown'` note but drop its `'disagree' not in view.case_kinds` clause.
- `open.html` `item_cell`: replace the `case_kinds` loop with `{%- if v.verdict.state == 'question' %} <span class="qmark">question</span>{% endif %}`.
- `views.py`: set `"cases"` to `v.verdict.kind.replace("_", " ") if v.verdict.state in ("question", "decided", "waiting") else ""`. Keep the key so saved reports keep their column.
- `stores/items.py`: delete the `kinds` loop, the `case_kinds` field and argument, and `with_cases`.
- `reconcile.py`: delete `Case`, `KINDS`, `cases()` and any helper only they used. Run `grep -rn "reconcile\.\(cases\|KINDS\|Case\)" fridgesheet tests` and expect no output.
- `phrasing.py`: delete the entries `disagree`, `past_credit`, `one_source`, `paper_no_grade`, `submitted_ungraded` and `stale_flag`. Update `tests/test_phrasing.py` wherever it names them.
- Delete `templates/reconcile.html` and `templates/_case_group.html`.

- [ ] **Step 5: Port or delete the case tests**

- `tests/test_reconcile.py`: keep the tests of `open_sources`, `actionable_items`, `live_items` and the year floor. For each test of `cases()` (`_kinds`), move its scenario to `tests/test_verdicts.py` as a verdict assertion when a verdict rule covers it. Otherwise delete it, and name it in the commit message with the reason. For example, "one_source for a canvas-only item past due" has no question now: a missing HAC twin is lag or status.
- `tests/test_reconcile_traps.py`: the Enter-key and focus tests still apply to `_flag_menu.html`, now inside **More**. Keep them and point them at `/items/{id}`. Delete the tests that read the outer Reconcile card, since that card is gone.

- [ ] **Step 6: Run the full suite**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee /tmp/task12.log | tail -3`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add -A fridgesheet tests
git commit -m "Retire reconcile cases: check-in, open work, reports and evidence read the verdict"
```

---

### Task 13: Documentation and a browser check

**Files:**
- Modify: `README.md` (any mention of the Reconcile page), `docs/outcomes.md` (a short "Questions" section pointing at `verdicts.py`)
- No code unless the browser check finds a defect. Fix any defect under TDD before continuing.

- [ ] **Step 1: Update the docs**

Run: `grep -rn -i "reconcile" README.md docs/ --include=*.md | grep -v superpowers`
Rewrite each user-facing mention to describe the Questions page and the three sections on a kid's page. Leave the historical specs and plans alone.

- [ ] **Step 2: Start a seeded server**

Write `/tmp/fs_serve.py`:

```python
import sys, tempfile
from pathlib import Path
sys.path.insert(0, "<absolute path to this worktree>")
import uvicorn
from fridgesheet import config, host
from fridgesheet.web import app as webapp
from tests.web_fixtures import NOW, seed

home = Path(tempfile.mkdtemp(prefix="fs-questions-"))
seed(home).close()
application = webapp.create_app(config.Settings(home=home), worker=False)
application.state.fridgesheet.clock = lambda: NOW
application.state.fridgesheet.extra["describe_service"] = lambda: host.ServiceInfo("x", installed=True, active=True, detail="stub")
uvicorn.run(application, host="127.0.0.1", port=8433, log_level="warning")
```

Port 8433 is the one the app's host guard accepts. Run it with `env -u PYTHONPATH .venv/bin/python /tmp/fs_serve.py &` and wait until `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8433/` prints 200.

- [ ] **Step 3: Check these in Chrome and record each result**

| Page | Expected |
|---|---|
| `/kids/Alex` | "1 question about Alex's work" (Participation); "Decided for you" shows Quiz 1 with "Not right?"; Waiting (2) holds Essay draft and Lab notebook ("Asks you after Thu 9/17"); the table has three columns; Homework 4 is red; Quiz 1 and Lab notebook are not |
| Answer "Yes, handed in" on Participation | The card collapses to a green line with Undo, and focus is on the line |
| Undo | The card returns with its question |
| "Not right?" on Quiz 1 | A card with "HAC is right, it's done" and "Ask the teacher" |
| `/questions` | Alex's group shows Participation; Sam's group says there is nothing to ask |
| `/reconcile` | Redirects to `/questions` |
| Resize to 390 px wide | Answer buttons wrap and stay tappable; no horizontal scroll on the kid page |

- [ ] **Step 4: Stop the server and run the full suite once more**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tail -1`
Expected: all PASS.

- [ ] **Step 5: Commit, push and open the PR**

```bash
git add README.md docs/
git commit -m "docs: Questions replaces Reconcile"
git push -u origin ux/questions
gh pr create --base main --title "Questions, not cases: the app decides what the records settle" --body "..."
```

In the PR body, name the issues it closes: #55, #39, #45, #46, #49 and #50. Name the issues it covers in part, with what remains of each: #34, #44, #47, #51 and #52. Include the browser-check table from Step 3 with actual results. Include the full-suite count. End the body with `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

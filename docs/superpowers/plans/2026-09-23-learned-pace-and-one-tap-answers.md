# Learned Pace and One-Tap Answers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verdicts wait for each class's learned grading pace instead of a fixed seven days and say so on the card, and every check-in card offers one-tap Today / Tomorrow / It's handed in / Ask the teacher answers.

**Architecture:** A new `pace` module turns the observation history into per-class grade-lag and HAC-lag estimates at render time (no schema change). `verdicts.verdict` takes a `Pace` the way it takes late-work `rules`, uses it for the two grace-period rules, and attaches a `pace` fact the templates phrase in the kid's tier. The answer endpoint gains `plan:today` / `plan:tomorrow`, which create a plan step with defaults and swap the plan panel in out of band.

**Tech Stack:** Python 3.12, FastAPI + Jinja2 + htmx, SQLite, pytest. Run tests with the main checkout's venv: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q`.

**Spec:** `docs/superpowers/specs/2026-09-23-learned-pace-and-one-tap-answers-design.md`

## Global Constraints

- No schema migration; `db.SCHEMA_VERSION` stays 2. No change to `ingest.py`.
- Every new phrase key has all three tiers (`early`, `middle`, `older`) with identical `{placeholders}`, and no younger tier states a number or date/time word its `older` phrase lacks (`tests/test_phrasing.py` enforces both).
- Every sentence about the pace names Fridge Sheet as its subject, never the teacher or the school (spec 4.6; `docs/product/features/data-correctness.md`).
- The app never writes a flag or a step on the family's behalf: a decided follow-up keeps its `follow_up` flag (spec 5).
- Zero scores are not pace samples; an item first seen already graded is not a sample (spec 4.1).
- Defaults in `pace.estimate`: minimum 3 samples, 80th percentile by nearest rank, floor 1 day, cap 21 days, default 7 (spec 4.3). These four numbers live only in `fridgesheet/web/pace.py`.
- One deliberate deviation from spec 6.5: the check-in card's link to the step form keeps the words "Plan a step" (issue #69 chose one name for that link everywhere); "Add details" is the done-line's link to the step just created.
- One deliberate reading of spec 6.2: the item detail's rule is unchanged (it renders the question card whenever the verdict has answers), so it now shows Today / Tomorrow for upcoming work too. The Questions page lists only questions and is unaffected.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. **A course whose only graded items are HAC placeholder zeros** must fall through to the default, not learn "0 days". Pinned in Task 1 (`test_zeros_are_not_samples`).
2. **An item graded in Canvas before the app existed** (first-scored refresh equals `first_seen`) must not produce a 0-day sample that drags the percentile down. Pinned in Task 2 (`test_an_item_first_seen_already_graded_is_not_a_sample`).
3. **A plan answer on an item that already has an active step** must not create a second commitment. Pinned in Task 8 (`test_a_plan_answer_on_covered_work_is_refused`).
4. **Undo after the family edited the step** must leave the edited step alone. Pinned in Task 8 (`test_undo_leaves_an_edited_step_alone`).
5. **A follow-up overtaken by a zero** must stay a question; only good news settles it. Pinned in Task 5 (`test_a_follow_up_overtaken_by_a_zero_is_still_a_question`).

---

### Task 1: The estimate and the fallback chain (`pace.py`)

**Files:**
- Create: `fridgesheet/web/pace.py`
- Test: `tests/test_pace.py`

**Interfaces:**
- Produces:
  - `Estimate(days: int, n: int, scope: str)` frozen dataclass; `scope` ∈ `{"course_kind", "course", "teacher", "default"}`.
  - `estimate(samples: list[int]) -> int | None`.
  - `kind_group(kind: str) -> str` → `"online"` or `"offline"`.
  - `Pace(grade: dict[tuple[int, str], list[int]], hac: dict[tuple[int, str], list[int]], classes: dict[int, int], teachers: dict[int, str])` with `grade_days(item) -> Estimate` and `hac_days(item) -> Estimate`. `item` is any mapping with `course_id`, `kind` and `teacher` keys (a `sqlite3.Row` or a dict). `classes` maps a `course_id` to its class id (the smaller of its own id and its peer's); sample tables are keyed by `(class_id, kind_group)`; `teachers` maps class id to a normalised teacher name.
  - `DEFAULT = Pace({}, {}, {}, {})`, `DEFAULT_DAYS = 7`.

- [ ] **Step 1: Write the failing tests**

```python
"""The learned pace: what the history says a class usually takes (spec section 4)."""
from __future__ import annotations

from fridgesheet.web import pace as P


def test_fewer_than_three_samples_is_no_estimate():
    assert P.estimate([]) is None
    assert P.estimate([4, 5]) is None


def test_the_estimate_is_the_80th_percentile_by_nearest_rank():
    assert P.estimate([1, 2, 3, 4, 10]) == 4          # rank ceil(0.8 * 5) = 4 -> 4th smallest
    assert P.estimate([3, 3, 3]) == 3                  # rank ceil(2.4) = 3
    assert P.estimate([2, 9, 1, 4]) == 4               # sorted 1,2,4,9; rank ceil(3.2) = 4


def test_floor_and_cap():
    assert P.estimate([0, 0, 0]) == 1
    assert P.estimate([30, 40, 50]) == 21


def test_zeros_are_not_samples():
    """Review Focus 1: the store never feeds zeros in, and a table of nothing is the default."""
    pace = P.Pace(grade={(5, "offline"): []}, hac={}, classes={5: 5}, teachers={})
    assert pace.grade_days({"course_id": 5, "kind": "paper", "teacher": "Hoch"}) == P.Estimate(7, 0, "default")


def test_kind_group():
    assert P.kind_group("online") == "online"
    for kind in ("paper", "in class", ""):
        assert P.kind_group(kind) == "offline", kind


def _item(course_id=5, kind="paper", teacher="Michael Hoch"):
    return {"course_id": course_id, "kind": kind, "teacher": teacher}


def test_the_course_and_kind_group_come_first():
    pace = P.Pace(grade={(5, "offline"): [9, 10, 12], (5, "online"): [1, 1, 1]}, hac={}, classes={5: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(kind="paper")) == P.Estimate(12, 3, "course_kind")
    assert pace.grade_days(_item(kind="online")) == P.Estimate(1, 3, "course_kind")


def test_then_the_whole_course_pooled_across_kinds():
    pace = P.Pace(grade={(5, "offline"): [9], (5, "online"): [1, 2]}, hac={}, classes={5: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(kind="paper")) == P.Estimate(9, 3, "course")


def test_then_the_same_teacher_across_the_household_same_kind():
    pace = P.Pace(grade={(5, "offline"): [2], (8, "offline"): [6, 7], (9, "offline"): [40, 40, 40]}, hac={},
                  classes={5: 5, 8: 8, 9: 9}, teachers={5: "michael hoch", 8: "michael hoch", 9: "dana lee"})
    assert pace.grade_days(_item(course_id=5, kind="paper", teacher=" Michael HOCH ")) == P.Estimate(7, 3, "teacher")


def test_a_different_teacher_is_never_pooled():
    pace = P.Pace(grade={(9, "offline"): [40, 40, 40]}, hac={}, classes={5: 5, 9: 9}, teachers={5: "michael hoch", 9: "dana lee"})
    assert pace.grade_days(_item(course_id=5)) == P.Estimate(7, 0, "default")


def test_an_unknown_course_and_a_blank_teacher_are_the_default():
    pace = P.Pace(grade={(5, "offline"): [9, 10, 12]}, hac={}, classes={5: 5}, teachers={5: ""})
    assert pace.grade_days(_item(course_id=77, teacher="")) == P.Estimate(7, 0, "default")
    assert pace.grade_days(_item(course_id=5, teacher="")).scope == "course_kind"     # its own history still counts


def test_a_hac_twin_shares_its_canvas_course_history():
    pace = P.Pace(grade={(5, "offline"): [9, 10, 12]}, hac={}, classes={5: 5, 6: 5}, teachers={5: "michael hoch"})
    assert pace.grade_days(_item(course_id=6, kind="")) == P.Estimate(12, 3, "course_kind")


def test_hac_days_reads_the_hac_table():
    pace = P.Pace(grade={}, hac={(5, "online"): [2, 3, 5]}, classes={5: 5}, teachers={})
    assert pace.hac_days(_item(kind="online")) == P.Estimate(5, 3, "course_kind")
    assert pace.hac_days(_item(kind="paper")) == P.Estimate(5, 3, "course")


def test_the_default_pace_object_always_answers_seven():
    assert P.DEFAULT.grade_days(_item()) == P.Estimate(7, 0, "default")
    assert P.DEFAULT.hac_days(_item()) == P.Estimate(7, 0, "default")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_pace.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'fridgesheet.web.pace'`

- [ ] **Step 3: Write the module**

```python
"""How long a class usually takes: the app's own count, from its own history.

Every grace period used to be one global seven days. Grading pace is a property of a course
and a teacher, and of the kind of work: a stack of paper reading guides is graded in a batch
a week or two on, an online quiz the same evening. The observation table already holds when
the app first saw each grade, so the pace can be learned at render time with no new table
(docs/superpowers/specs/2026-09-23-learned-pace-and-one-tap-answers-design.md, section 4).

`estimate` is the one tunable: its four numbers are policy, and nothing else in the app
knows them. It returns a high percentile rather than a mean so one slow week does not make
the app nag and one fast week does not make it ask early, and it is capped so a teacher who
grades once a quarter cannot silence a real problem for a quarter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_DAYS = 7      # what the chain bottoms out on: the grace period the app always had
MIN_SAMPLES = 3       # fewer, and a group does not get its own number
PERCENTILE = 0.8      # nearest-rank
FLOOR_DAYS = 1
CAP_DAYS = 21

COURSE_KIND, COURSE, TEACHER, DEFAULT_SCOPE = "course_kind", "course", "teacher", "default"


@dataclass(frozen=True)
class Estimate:
    days: int
    n: int          # samples behind the number; 0 for the default
    scope: str      # course_kind | course | teacher | default


def estimate(samples: list[int]) -> int | None:
    """Days to allow, or None when the samples are too few to say."""
    if len(samples) < MIN_SAMPLES:
        return None
    ordered = sorted(samples)
    rank = max(1, math.ceil(PERCENTILE * len(ordered)))
    return min(CAP_DAYS, max(FLOOR_DAYS, ordered[rank - 1]))


def kind_group(kind: str) -> str:
    """Online work is graded on a different rhythm from paper; that split is most of what
    there is to learn. HAC-only items carry an empty kind and are offline."""
    return "online" if kind == "online" else "offline"


def teacher_key(name: str | None) -> str:
    return " ".join((name or "").split()).lower()


@dataclass(frozen=True)
class Pace:
    """Samples per (class id, kind group), for grade lag and for HAC lag, plus the two maps
    that let an item find its class: `classes` (course id -> class id, so a HAC twin shares
    its Canvas course's history) and `teachers` (class id -> normalised teacher name)."""
    grade: dict[tuple[int, str], list[int]]
    hac: dict[tuple[int, str], list[int]]
    classes: dict[int, int]
    teachers: dict[int, str]

    def grade_days(self, item) -> Estimate:
        return self._lookup(self.grade, item)

    def hac_days(self, item) -> Estimate:
        return self._lookup(self.hac, item)

    def _lookup(self, table, item) -> Estimate:
        if not table:                       # nothing learned at all: the default, without reading the item
            return Estimate(DEFAULT_DAYS, 0, DEFAULT_SCOPE)
        cid = self.classes.get(item["course_id"], item["course_id"])
        group = kind_group(item["kind"] or "")
        own = table.get((cid, group), [])
        if (days := estimate(own)) is not None:
            return Estimate(days, len(own), COURSE_KIND)
        pooled = [s for (c, _), ss in table.items() if c == cid for s in ss]
        if (days := estimate(pooled)) is not None:
            return Estimate(days, len(pooled), COURSE)
        teacher = teacher_key(item["teacher"])
        if teacher:
            same = {c for c, t in self.teachers.items() if t == teacher}
            by_teacher = [s for (c, g), ss in table.items() if c in same and g == group for s in ss]
            if (days := estimate(by_teacher)) is not None:
                return Estimate(days, len(by_teacher), TEACHER)
        return Estimate(DEFAULT_DAYS, 0, DEFAULT_SCOPE)


DEFAULT = Pace({}, {}, {}, {})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_pace.py`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/pace.py tests/test_pace.py
git commit -m "feat(pace): the estimate and its fallback chain

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The sample query (`stores/pace.py`)

**Files:**
- Create: `fridgesheet/web/stores/pace.py`
- Test: `tests/test_pace_store.py`

**Interfaces:**
- Consumes: `pace.Pace`, `pace.kind_group`, `pace.teacher_key` from Task 1.
- Produces: `load(conn) -> pace.Pace` for the whole household (teacher pooling crosses kids, so it is not per student).

- [ ] **Step 1: Write the failing tests**

```python
"""Samples from the observation history (spec 4.1, 4.2). Built directly on the schema so each
case is one item with a hand-written history."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import pace as store


def _refresh(conn, at):
    return conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES (?, '{}', 1)", (at,)).lastrowid


def _course(conn, sid, source, name, teacher="Michael Hoch", peer=None):
    return conn.execute("INSERT INTO courses(student_id, source, name, short_name, teacher, peer_course_id) VALUES (?, ?, ?, ?, ?, ?)",
                        (sid, source, name, name[:4], teacher, peer)).lastrowid


def _item(conn, sid, cid, name, *, kind="paper", due="2026-09-10T23:59:00-04:00", first_seen):
    return conn.execute("INSERT INTO items(student_id, course_id, key, name, kind, points, due, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, 10, ?, ?, ?)",
                        (sid, cid, f"canvas:{name}", name, kind, due, first_seen, first_seen)).lastrowid


def _obs(conn, rid, iid, source, score=None, submitted_at=None):
    conn.execute("INSERT INTO item_observations(refresh_id, item_id, source, state, score, submitted_at, late, missing, excused, published) "
                 "VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 1)", (rid, iid, source, "graded" if score is not None else "unsubmitted", score, submitted_at))


def _home(tmp_path):
    conn = db.open_db(tmp_path)
    sid = conn.execute("INSERT INTO students(key, name) VALUES ('Alex', 'Alex')").lastrowid
    r1, r2, r3 = (_refresh(conn, at) for at in ("2026-09-08T06:00:00-04:00", "2026-09-15T06:00:00-04:00", "2026-09-22T06:00:00-04:00"))
    cid = _course(conn, sid, "canvas", "Honors English 9")
    return conn, sid, cid, (r1, r2, r3)


def test_grade_lag_is_days_from_due_to_the_first_scored_refresh(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Reading guide", first_seen=r1)            # due 9/10
    _obs(conn, r1, iid, "canvas")                                           # ungraded when first seen
    _obs(conn, r3, iid, "canvas", score=8.0)                                # graded, seen 9/22
    pace = store.load(conn)
    assert pace.grade[(cid, "offline")] == [12]


def test_online_work_anchors_on_its_submission(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Quiz", kind="online", first_seen=r1)
    _obs(conn, r1, iid, "canvas")
    _obs(conn, r2, iid, "canvas", score=8.0, submitted_at="2026-09-13T20:00:00-04:00")    # seen 9/15
    assert store.load(conn).grade[(cid, "online")] == [2]


def test_an_item_first_seen_already_graded_is_not_a_sample(tmp_path):
    """Review Focus 2."""
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Old quiz", first_seen=r2)
    _obs(conn, r2, iid, "canvas", score=8.0)
    assert (cid, "offline") not in store.load(conn).grade


def test_zeros_and_ungraded_items_are_not_samples(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    zero = _item(conn, sid, cid, "Missing one", first_seen=r1)
    _obs(conn, r1, zero, "canvas")
    _obs(conn, r2, zero, "canvas", score=0.0)
    open_ = _item(conn, sid, cid, "Still open", first_seen=r1)
    _obs(conn, r1, open_, "canvas")
    assert store.load(conn).grade == {}


def test_an_item_with_no_due_date_and_no_submission_is_not_a_sample(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Undated", due=None, first_seen=r1)
    _obs(conn, r1, iid, "canvas")
    _obs(conn, r2, iid, "canvas", score=8.0)
    assert store.load(conn).grade == {}


def test_a_grade_seen_before_the_due_date_is_a_zero_day_lag(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    iid = _item(conn, sid, cid, "Early", due="2026-09-30T23:59:00-04:00", first_seen=r1)
    _obs(conn, r1, iid, "canvas")
    _obs(conn, r2, iid, "canvas", score=8.0)
    assert store.load(conn).grade[(cid, "offline")] == [0]


def test_hac_lag_is_days_between_the_two_first_scored_refreshes(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    hac = _course(conn, sid, "hac", "Honors English 9 S1", peer=cid)
    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hac, cid))
    iid = _item(conn, sid, cid, "Essay", first_seen=r1)
    _obs(conn, r1, iid, "canvas"); _obs(conn, r1, iid, "hac")
    _obs(conn, r2, iid, "canvas", score=8.0)
    _obs(conn, r3, iid, "hac", score=8.0)
    pace = store.load(conn)
    assert pace.hac[(cid, "offline")] == [7]
    assert pace.classes == {cid: cid, hac: cid}                 # the twin shares the Canvas course's history


def test_teachers_are_keyed_by_class_and_normalised(tmp_path):
    conn, sid, cid, _ = _home(tmp_path)
    assert store.load(conn).teachers == {cid: "michael hoch"}


def test_a_hac_only_item_borrows_its_twins_teacher(tmp_path):
    conn, sid, cid, (r1, r2, r3) = _home(tmp_path)
    hac = _course(conn, sid, "hac", "Honors English 9 S1", teacher=None, peer=cid)
    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hac, cid))
    assert store.load(conn).teachers[cid] == "michael hoch"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_pace_store.py`
Expected: FAIL with `ImportError: cannot import name 'pace' from 'fridgesheet.web.stores'`

- [ ] **Step 3: Write the store**

```python
"""The pace samples, read from the observation history (spec 4.1).

Ingest writes an observation only when a field changed, so the first row per (item, source)
that carries a score above zero is when the app first saw that grade. Its refresh's
`started_at` is `seen`; the anchor is the Canvas submission when there is one, else the
due date. One sample per item and source; an item the app met already graded is not one.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .. import pace as P


def _date(s: str):
    return datetime.fromisoformat(s).date()


def load(conn: sqlite3.Connection) -> P.Pace:
    """The whole household's pace: teacher pooling crosses kids."""
    classes: dict[int, int] = {}
    teachers: dict[int, str] = {}
    for c in conn.execute("SELECT c.id, c.peer_course_id, COALESCE(c.teacher, pc.teacher) AS teacher "
                          "FROM courses c LEFT JOIN courses pc ON pc.id = c.peer_course_id"):
        cid = min(c["id"], c["peer_course_id"]) if c["peer_course_id"] else c["id"]
        classes[c["id"]] = cid
        if P.teacher_key(c["teacher"]):
            teachers[cid] = P.teacher_key(c["teacher"])

    refresh_times = {r["id"]: r["started_at"] for r in conn.execute("SELECT id, started_at FROM refreshes")}
    first: dict[tuple[int, str], sqlite3.Row] = {}
    for o in conn.execute(
            """SELECT o.item_id, o.source, o.refresh_id, o.submitted_at,
                      i.first_seen, i.due, i.kind, i.course_id
               FROM item_observations o JOIN items i ON i.id = o.item_id
               WHERE o.score IS NOT NULL AND o.score > 0
               ORDER BY o.item_id, o.source, o.refresh_id, o.id"""):
        first.setdefault((o["item_id"], o["source"]), o)

    grade: dict[tuple[int, str], list[int]] = {}
    seen_at: dict[tuple[int, str], object] = {}
    for (iid, source), o in first.items():
        if o["refresh_id"] == o["first_seen"]:            # met already graded: says nothing about pace
            continue
        seen = _date(refresh_times[o["refresh_id"]])
        seen_at[(iid, source)] = (seen, o)
        anchor = _date(o["submitted_at"]) if source == "canvas" and o["submitted_at"] else (_date(o["due"]) if o["due"] else None)
        if anchor is None:
            continue
        key = (classes.get(o["course_id"], o["course_id"]), P.kind_group(o["kind"] or ""))
        grade.setdefault(key, []).append(max(0, (seen - anchor).days))

    hac: dict[tuple[int, str], list[int]] = {}
    for (iid, source), (seen, o) in seen_at.items():
        if source != "canvas" or (iid, "hac") not in seen_at:
            continue
        hac_seen, _ = seen_at[(iid, "hac")]
        key = (classes.get(o["course_id"], o["course_id"]), P.kind_group(o["kind"] or ""))
        hac.setdefault(key, []).append(max(0, (hac_seen - seen).days))
    return P.Pace(grade=grade, hac=hac, classes=classes, teachers=teachers)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_pace_store.py`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/stores/pace.py tests/test_pace_store.py
git commit -m "feat(pace): samples from the observation history

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Verdicts wait for the learned pace

**Files:**
- Modify: `fridgesheet/web/verdicts.py` (`Verdict`, `verdict`, `_waiting_or_status`, new `pace_key`)
- Modify: `fridgesheet/web/stores/items.py:282-345` (`_views` loads the pace once and passes it)
- Test: `tests/test_verdicts.py`

**Interfaces:**
- Consumes: `pace.Pace`, `pace.Estimate`, `pace.DEFAULT` from Task 1; `stores.pace.load` from Task 2.
- Produces: `verdict(..., pace=None)` keyword; `Verdict.pace: dict | None` with keys `which` (`"grade"` | `"hac"`), `days`, `n`, `scope`, `what`, `by`, `elapsed` (a string such as `"10 days"`), `passed` (bool); `pace_key(v: Verdict) -> str | None` returning a phrase key from `{"pace.expect", "pace.passed", "pace.default", "pace.hac_expect", "pace.hac_passed", "pace.hac_default"}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verdicts.py`)

```python
# --- the learned pace (spec 4.5, 4.6) ------------------------------------------------------------

from fridgesheet.web import pace as P


class _Fixed:
    """A Pace that answers one number for everything."""
    def __init__(self, days, n=6, scope="course_kind"):
        self.est = P.Estimate(days, n, scope)

    def grade_days(self, item):
        return self.est

    def hac_days(self, item):
        return self.est


def _paced(it, obs, pace, now=NOW):
    return V.verdict(it, obs, flag=None, flag_set_at="", now=now, rules=RULES, refresh_times=TIMES, pace=pace)


def test_paper_work_waits_for_the_learned_pace_not_seven_days():
    v = _paced(item(kind="paper", due="2026-09-05T23:59:00-04:00"), {"canvas": canvas()}, _Fixed(12))
    assert (v.state, v.kind) == (V.WAITING, "awaiting_grade")            # 10 days on, 12 allowed
    assert v.asks_on.isoformat() == "2026-09-17"
    assert v.pace == {"which": "grade", "days": 12, "n": 6, "scope": "course_kind", "what": "assignments in this class",
                      "by": "Thu 9/17", "elapsed": "10 days", "passed": False}
    assert V.pace_key(v) == "pace.expect"


def test_paper_work_past_the_learned_pace_is_a_question_that_says_so():
    v = _paced(item(kind="paper", due="2026-09-01T23:59:00-04:00"), {"canvas": canvas()}, _Fixed(12))
    assert (v.state, v.kind) == (V.QUESTION, "still_ungraded")
    assert v.pace["elapsed"] == "14 days" and v.pace["passed"] is True and V.pace_key(v) == "pace.passed"


def test_hac_lag_waits_for_the_learned_hac_pace():
    v = _paced(item(), {"canvas": canvas(rid=2, state="graded", score=18.0), "hac": hac(rid=2)}, _Fixed(10))
    assert (v.state, v.kind) == (V.WAITING, "hac_lag")                   # seen 9/8, 7 days on, 10 allowed
    assert v.asks_on.isoformat() == "2026-09-18"
    assert v.pace["which"] == "hac" and V.pace_key(v) == "pace.hac_expect"
    v = _paced(item(), {"canvas": canvas(rid=1, state="graded", score=18.0), "hac": hac(rid=1)}, _Fixed(10))
    assert v.kind == "hac_still_blank" and V.pace_key(v) == "pace.hac_passed"


def test_submitted_ungraded_carries_the_pace_sentence_but_keeps_waiting():
    sub = "2026-09-01T20:00:00-04:00"
    v = _paced(item(), {"canvas": canvas(state="submitted", submitted_at=sub)}, _Fixed(4))
    assert (v.state, v.kind) == (V.WAITING, "teacher_grading")
    assert v.asks_on is None
    assert v.pace["by"] == "Sat 9/5" and V.pace_key(v) == "pace.passed"


def test_the_default_scope_is_seven_days_and_says_it_has_no_history():
    v = run(item(kind="paper", due="2026-09-10T23:59:00-04:00"), {"canvas": canvas()})   # no pace given
    assert v.asks_on.isoformat() == "2026-09-17"
    assert v.pace["scope"] == "default" and V.pace_key(v) == "pace.default"
    v = _paced(item(), {"canvas": canvas(rid=3, state="graded", score=18.0), "hac": hac(rid=3)}, P.DEFAULT)
    assert V.pace_key(v) == "pace.hac_default"


def test_the_teacher_scope_is_attributed_to_the_teacher():
    v = _paced(item(kind="paper", due="2026-09-10T23:59:00-04:00"), {"canvas": canvas()}, _Fixed(9, scope="teacher"))
    assert v.pace["what"] == "assignments from this teacher"


def test_verdicts_without_a_grace_period_carry_no_pace():
    assert run(item(), {"canvas": canvas(missing=1)}).pace is None
    assert V.pace_key(V.Verdict(V.STATUS, "not_done")) is None


def test_one_day_elapsed_is_singular():
    v = _paced(item(kind="paper", due="2026-09-14T23:59:00-04:00"), {"canvas": canvas()}, _Fixed(5))
    assert v.pace["elapsed"] == "1 day"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_verdicts.py -k "pace or learned or singular or scope"`
Expected: FAIL with `TypeError: verdict() got an unexpected keyword argument 'pace'`

- [ ] **Step 3: Change `verdicts.py`**

Add the import and the `pace` field:

```python
from . import outcomes, pace as _pace, phrasing, reconcile
```

```python
@dataclass(frozen=True)
class Verdict:
    state: str
    kind: str
    facts: dict = field(default_factory=dict)      # values for the "facts.<kind>" phrase
    answers: tuple[Answer, ...] = ()
    asks_on: date | None = None                    # waiting only: the day it becomes a question
    #: The learned pace behind a grace period, for the "pace.*" sentence (spec 4.6); None when
    #: no grace period governs this verdict. Keys: which, days, n, scope, what, by, elapsed.
    pace: dict | None = None
```

Add, after `_days_past`:

```python
#: What the count is attributed to, by scope. The subject is always Fridge Sheet's count.
WHAT = {_pace.COURSE_KIND: "assignments in this class", _pace.COURSE: "assignments in this class",
        _pace.TEACHER: "assignments from this teacher", _pace.DEFAULT_SCOPE: "assignments in this class"}


def _pace_facts(est: _pace.Estimate, which: str, anchor: date, now: datetime) -> dict:
    by = anchor + timedelta(days=est.days)
    elapsed = (now.date() - anchor).days
    return {"which": which, "days": est.days, "n": est.n, "scope": est.scope, "what": WHAT[est.scope],
            "by": f"{by:%a} {by.month}/{by.day}", "elapsed": f"{elapsed} day{'' if elapsed == 1 else 's'}",
            "passed": elapsed >= est.days}


def pace_key(v: Verdict) -> str | None:
    """Which "pace.*" sentence a verdict's pace calls for, or None."""
    p = v.pace
    if not p:
        return None
    prefix = "pace.hac_" if p["which"] == "hac" else "pace."
    if p["scope"] == _pace.DEFAULT_SCOPE:
        return prefix + "default"
    return prefix + ("passed" if p["passed"] else "expect")
```

Change `verdict`'s signature and its last line:

```python
def verdict(item, obs, *, flag, flag_set_at, now, rules, refresh_times, prefer="canvas", prev_obs=None, pace=None) -> Verdict:
    pace = pace or _pace.DEFAULT
    ...
    return _waiting_or_status(item, c, h, now=now, rules=rules, refresh_times=refresh_times, prefer=prefer, obs=obs, pace=pace)
```

Change `_waiting_or_status` (signature plus rules 9 to 13):

```python
def _waiting_or_status(item, c, h, *, now, rules, refresh_times, prefer, obs, pace) -> Verdict:
    ...
    # 9-10: Canvas graded it and HAC, which this class has, still has nothing. How long to
    # allow is what this class's history says HAC usually takes (spec 4.5).
    if not settled_not_done and cs is not None and cs > 0 and hs is None and item["peer_course_id"] is not None:
        seen = _observed_at(c, refresh_times)
        if seen is not None:
            est = pace.hac_days(item)
            asks_on = seen.date() + timedelta(days=est.days)
            facts_p = _pace_facts(est, "hac", seen.date(), now)
            if now.date() >= asks_on:
                return Verdict(QUESTION, "hac_still_blank", {"canvas": _of(cs, points), "when": f"{seen.month}/{seen.day}"},
                               ANSWERS["hac_still_blank"], pace=facts_p)
            return Verdict(WAITING, "hac_lag", {"canvas": _of(cs, points)}, ANSWERS["hac_lag"], asks_on=asks_on, pace=facts_p)

    # 11: handed in online, no grade anywhere. Still waits without asking; the pace sentence
    # shows so the family sees the count before the app acts on it (spec section 8).
    if not settled_not_done and c is not None and c["submitted_at"] and cs is None and hs is None:
        submitted = reconcile._parse_ts(c["submitted_at"]).date()
        return Verdict(WAITING, "teacher_grading", {"when": _md(c["submitted_at"])}, ANSWERS["teacher_grading"],
                       pace=_pace_facts(pace.grade_days(item), "grade", submitted, now))

    # 12-13: nothing to submit online, past due, no grade anywhere.
    if outcome == outcomes.UNKNOWN and due is not None:
        est = pace.grade_days(item)
        asks_on = due.date() + timedelta(days=est.days)
        facts = {"kind": item["kind"] or "HAC-only", "due": f"{due:%a} {due.month}/{due.day}"}
        facts_p = _pace_facts(est, "grade", due.date(), now)
        if now.date() >= asks_on:
            return Verdict(QUESTION, "still_ungraded", facts, ANSWERS["still_ungraded"], pace=facts_p)
        return Verdict(WAITING, "awaiting_grade", facts, ANSWERS["awaiting_grade"], asks_on=asks_on, pace=facts_p)
```

`ANSWERS["teacher_grading"]` does not exist yet; add it to the table now so this compiles (Task 6 fills in the rest of the table):

```python
    "teacher_grading": (ASK,),
```

`GRACE_DAYS` is no longer read by the rules; delete the constant and point the module docstring's grace mention at `pace.DEFAULT_DAYS`. Grep for other readers first: `grep -rn GRACE_DAYS fridgesheet tests` should show none after the edit.

Note on rule 13: the old code compared `_days_past(due, now) >= GRACE_DAYS`, which is `now.date() - due.date()`; `now.date() >= due.date() + days` is the same comparison. Delete `_days_past` if nothing else uses it.

- [ ] **Step 4: Pass the pace from the items store**

In `fridgesheet/web/stores/items.py`, import the store and load once per `_views`:

```python
from . import plans, pace as pace_store
```

In `_views`, after `checked = last_checked(conn)`:

```python
    pace = pace_store.load(conn)
```

and in the `verdicts.verdict(...)` call add `pace=pace`.

- [ ] **Step 5: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_verdicts.py tests/test_phrasing.py tests/test_web_checkin_verdicts.py tests/test_web_questions.py`
Expected: all pass. (`ANSWERS["teacher_grading"]` needs a `facts.teacher_grading` phrase for `test_the_table_covers_the_words_a_child_actually_meets`; that phrase already exists.)

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/verdicts.py fridgesheet/web/stores/items.py tests/test_verdicts.py
git commit -m "feat(verdicts): grace periods follow the learned pace and carry it as a fact

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The pace sentence, in three tiers, on the cards

**Files:**
- Modify: `fridgesheet/web/phrasing.py` (six `pace.*` keys)
- Modify: `fridgesheet/web/app.py:174-178` (`pace_key` filter)
- Modify: `fridgesheet/web/templates/_planning_evidence.html`
- Modify: `fridgesheet/web/templates/_question.html`
- Test: `tests/test_phrasing.py`, `tests/test_web_checkin_verdicts.py`

**Interfaces:**
- Consumes: `verdicts.pace_key` and `Verdict.pace` from Task 3.
- Produces: Jinja filter `pace_key`; phrase keys `pace.expect`, `pace.passed`, `pace.default`, `pace.hac_expect`, `pace.hac_passed`, `pace.hac_default`, each with placeholders `{n} {what} {days} {by}` / `{n} {what} {days} {elapsed}` / `{days}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phrasing.py`:

```python
def test_the_pace_sentences_exist_and_name_fridge_sheet_not_the_teacher():
    for key in ("pace.expect", "pace.passed", "pace.default", "pace.hac_expect", "pace.hac_passed", "pace.hac_default"):
        assert key in phrasing.PHRASES, key
        for tier in tiers.TIERS:
            words = phrasing.phrase(key, tier)
            assert "Fridge Sheet" in words, (key, tier)
            assert "teacher will" not in words.lower() and "school will" not in words.lower(), (key, tier)
```

Append to `tests/test_web_checkin_verdicts.py`:

```python
# --- the pace sentence (spec 4.6) --------------------------------------------------------------

def test_a_waiting_card_says_what_fridge_sheet_expects_and_why(tmp_path):
    """Lab notebook: paper, due 9/10, no grade, no history -> the default sentence."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    card = _groups(body)["Waiting on the school"]
    assert "Fridge Sheet has no earlier grades from this class to go on" in card
    assert "allows 7 days" in card


def test_the_pace_sentence_shows_on_the_question_card_too(tmp_path):
    """Participation: HAC-only, due 9/8, a week on -> still_ungraded, the default sentence."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert "Fridge Sheet has no earlier grades from this class to go on" in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_phrasing.py tests/test_web_checkin_verdicts.py -k "pace"`
Expected: FAIL, `assert 'pace.expect' in PHRASES` and the check-in body lacks the sentence.

- [ ] **Step 3: Add the phrases** (in `phrasing.PHRASES`, after the `where.stale_answer` row)

```python
    # --- the learned pace: Fridge Sheet's own count, never the school's word (spec 4.6) ----
    "pace.expect":      {"early": "Fridge Sheet counted {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}."},
    "pace.passed":      {"early": "Fridge Sheet counted {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}."},
    "pace.default":     {"early": "Fridge Sheet has no earlier grades from this class to go on, so it allows {days} days.",
                         "middle": "Fridge Sheet has no earlier grades from this class to go on, so it allows {days} days.",
                         "older": "Fridge Sheet has no earlier grades from this class to go on, so it allows {days} days."},
    "pace.hac_expect":  {"early": "Fridge Sheet counted {n} earlier {what}: HAC usually catches up within about {days} days, so look for it by {by}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days, so look for it by {by}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days, so look for it by {by}."},
    "pace.hac_passed":  {"early": "Fridge Sheet counted {n} earlier {what}: HAC usually catches up within about {days} days. It has been {elapsed}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days. It has been {elapsed}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days. It has been {elapsed}."},
    "pace.hac_default": {"early": "Fridge Sheet has no earlier HAC grades from this class to go on, so it allows {days} days.",
                         "middle": "Fridge Sheet has no earlier HAC grades from this class to go on, so it allows {days} days.",
                         "older": "Fridge Sheet has no earlier HAC grades from this class to go on, so it allows {days} days."},
```

- [ ] **Step 4: Register the filter** (`app.py`, in the dict `_filters` returns)

```python
            "has_phrase": verdicts.has_phrase, "mailto_body": mailto_body, "pace_key": verdicts.pace_key}
```

- [ ] **Step 5: Show the sentence**

In `_planning_evidence.html`, after the two `review-note` lines for question/decided and waiting:

```jinja
  {% set pk = view.verdict | pace_key %}{% if pk %}<p class="review-note app-count">{{ pk | say(tier | default(''), view.verdict.pace) }}</p>{% endif %}
```

In `_question.html`, after the `facts` paragraph and before the `ask` line:

```jinja
  {% set pk = vd | pace_key %}{% if pk %}<p class="facts app-count">{{ pk | say(tier, vd.pace) }}</p>{% endif %}
```

- [ ] **Step 6: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_phrasing.py tests/test_web_checkin_verdicts.py tests/test_web_questions.py tests/test_web_kid_questions.py`
Expected: all pass, including `test_no_phrase_invents_a_number_a_date_or_a_time` for every tier.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/phrasing.py fridgesheet/web/app.py fridgesheet/web/templates/_planning_evidence.html fridgesheet/web/templates/_question.html tests/test_phrasing.py tests/test_web_checkin_verdicts.py
git commit -m "feat(check-in): cards say what Fridge Sheet expects and why

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: A follow-up overtaken by good news is decided

**Files:**
- Modify: `fridgesheet/web/verdicts.py:105-163` (`_stale_change`, `verdict` rule 1, `ANSWERS["followed_up_then_graded"]`)
- Test: `tests/test_verdicts.py`

**Interfaces:**
- Produces: `_stale_change(...) -> tuple[str, bool] | None` (text, good news).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_verdicts.py`; also edit the existing `test_a_graded_follow_up_does_not_say_you_asked_the_teacher`)

Replace the body of the existing test:

```python
def test_a_graded_follow_up_does_not_say_you_asked_the_teacher():
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=28.0)}, flag="follow_up",
            flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.DECIDED, "followed_up_then_graded")           # spec 5: good news settles it
    assert [a.action for a in v.answers] == ["confirm", "done"]
    assert "asked the teacher" not in V.say("facts." + v.kind, "", v.facts).lower()
```

This task also renames `Answer.flag` to `Answer.action` (Task 6 adds the plan actions on top). In `verdicts.py`:

```python
@dataclass(frozen=True)
class Answer:
    key: str                # phrase key for the button label
    action: str | None      # a flag, "confirm", "clear", or None: open the plan-step form (until Task 6)
```

In `tests/test_verdicts.py` change every `[a.flag for a in v.answers]` to `[a.action for a in v.answers]` (six places; `grep -n "a.flag" tests/test_verdicts.py`). In `templates/_answers.html` change `a.flag is none` to `a.action is none` and `value="{{ a.flag }}"` to `value="{{ a.action }}"`.

Append:

```python
def test_a_follow_up_overtaken_by_a_zero_is_still_a_question():
    """Review Focus 5."""
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=0.0)}, flag="follow_up",
            flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "followed_up_then_graded")


def test_a_follow_up_closed_by_canvas_dropping_missing_is_decided():
    v = _run_prev({"canvas": canvas(rid=3, missing=0)}, {"canvas": canvas(rid=1, missing=1)},
                  "follow_up", "2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.DECIDED, "followed_up_then_graded")


def test_an_ask_overtaken_by_good_news_is_still_a_question():
    v = run(item(), {"canvas": canvas(rid=3, state="graded", score=28.0)}, flag="ask_teacher",
            flag_set_at="2026-09-10T08:00:00-04:00")
    assert (v.state, v.kind) == (V.QUESTION, "asked_then_graded")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_verdicts.py -k "follow_up or overtaken"`
Expected: FAIL, `(QUESTION, "followed_up_then_graded") != (DECIDED, ...)`

- [ ] **Step 3: Change `_stale_change` to say whether the news is good**

```python
def _stale_change(flag, set_at, c, h, refresh_times, prev=None, points=None) -> tuple[str, bool] | None:
    """What the school recorded after the family's answer that contradicts it, as (text, good),
    or None. `good` is a grade above zero or Canvas dropping its missing mark: for a follow-up,
    that answers the reminder (spec 5). ..."""
    prev = prev or {}
    if flag in HANDLED_FLAGS:
        if c is not None and _after(c, set_at, refresh_times) and (c["missing"] or (c["state"] == "graded" and c["score"] == 0)):
            return ("Canvas now says missing" if c["missing"] else "Canvas now shows a zero"), False
        if h is not None and _after(h, set_at, refresh_times) and h["score"] == 0:
            return "HAC now shows a zero", False
    if flag in MARKED_FLAGS:
        for label, o in (("Canvas", c), ("HAC", h)):
            if o is None or not _after(o, set_at, refresh_times):
                continue
            before = prev.get(label.lower())
            if label == "Canvas" and before is not None and before["missing"] and not o["missing"]:
                return "Canvas no longer marks it missing", True
            if o["score"] is not None:
                if before is None or before["score"] is None:
                    return f"{label} has graded it: {_of(o['score'], points)}", o["score"] > 0
                if abs(before["score"] - o["score"]) > TOLERANCE:
                    return f"{label} changed the grade: {_n(before['score'])} → {_of(o['score'], points)}", o["score"] > 0
    return None
```

Keep the rest of the existing docstring text below the first paragraph.

Rule 1 in `verdict`:

```python
    if flag:
        change = _stale_change(flag, flag_set_at, c, h, refresh_times, prev_obs, points)
        if change:
            text, good = change
            kind = {"ask_teacher": "asked_then_graded", "follow_up": "followed_up_then_graded"}.get(flag, "stale_answer")
            # A follow-up is the family's own reminder; good news answers it. The flag stays:
            # the app never records a family answer on the family's behalf.
            state = DECIDED if (flag == "follow_up" and good) else QUESTION
            return Verdict(state, kind,
                           {"flag": FLAG_WORDS.get(flag, flag.replace("_", " ")), "when": _md(flag_set_at), "change": text},
                           ANSWERS[kind])
```

And the answers row, so "not settled" is the first (primary) tap:

```python
    "followed_up_then_graded": (Answer("a.keep_following", "confirm"), Answer("a.its_done", "done")),
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_verdicts.py tests/test_web_answer_trail.py tests/test_web_kid_questions.py tests/test_checkin_queue.py`
Expected: all pass. If `test_web_answer_trail.py` asserts a graded follow-up is a question, read its docstring: it was written for #81 before spec 5, so update its expectation to the decided state and say so in the test's comment.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/verdicts.py fridgesheet/web/templates/_answers.html tests/test_verdicts.py tests/test_web_answer_trail.py
git commit -m "feat(verdicts): a follow-up overtaken by good news is decided, not asked

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The answer model: `action`, and answers on every card kind

**Files:**
- Modify: `fridgesheet/web/verdicts.py:25-65` (`Answer`, `ANSWERS`), `_waiting_or_status` rule 15
- Modify: `fridgesheet/web/phrasing.py` (`a.today`, `a.tomorrow`, `a.add_details`, `step.work_on_it`, `where.planned_today`, `where.planned_tomorrow`, `facts.not_due_yet`)
- Modify: `fridgesheet/web/templates/_answers.html`
- Modify: `fridgesheet/web/templates/_question.html` (a "Plan a step" link in the `more` line)
- Modify: `fridgesheet/web/app.py:185` (`request_key` template global)
- Test: `tests/test_verdicts.py`, `tests/test_phrasing.py`, `tests/test_web_questions.py`

**Interfaces:**
- Produces: `Answer(key: str, action: str)`; `action` ∈ flag names ∪ `{"confirm", "clear", "plan:today", "plan:tomorrow"}`; `PLAN_ACTIONS = ("plan:today", "plan:tomorrow")`. Template global `request_key()` → a fresh uuid4 string. Hidden field `request_key` on every answer form.

- [ ] **Step 1: Write the failing tests**

In `tests/test_verdicts.py` update these two expectations:

```python
def test_missing_work_offers_handed_in_and_plan_without_asking():
    """#74: a red row with no question still needs a one-tap "it's handed in"."""
    v = run(item(), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "not_done")
    assert [a.action for a in v.answers] == ["done", "plan:today", "plan:tomorrow"]
    assert V.say("facts.not_done", "", v.facts) == "Canvas marks it missing."


def test_past_credit_work_offers_let_it_go():
    v = run(item(due="2026-08-20T23:59:00-04:00"), {"canvas": canvas(missing=1)})
    assert (v.state, v.kind) == (V.STATUS, "past_credit")
    assert [a.action for a in v.answers] == ["ignore", "done", "plan:today"]
```

Append:

```python
# --- one-tap answers on every card (spec 6.2) ------------------------------------------------------

def test_upcoming_work_offers_today_tomorrow_and_handed_in():
    v = run(item(due="2026-09-20T23:59:00-04:00"), {"canvas": canvas()})
    assert (v.state, v.kind) == (V.STATUS, "not_due_yet")
    assert [a.action for a in v.answers] == ["plan:today", "plan:tomorrow", "done"]


def test_undated_work_offers_the_same():
    v = run(item(due=None, kind="paper"), {"canvas": canvas()})
    assert v.kind == "not_due_yet" and [a.action for a in v.answers] == ["plan:today", "plan:tomorrow", "done"]


def test_still_ungraded_offers_handed_in_today_tomorrow_and_ask():
    v = run(item(kind="paper", due="2026-09-01T23:59:00-04:00"), {"canvas": canvas()})
    assert v.kind == "still_ungraded"
    assert [a.action for a in v.answers] == ["done", "plan:today", "plan:tomorrow", "ask_teacher"]


def test_waiting_cards_offer_ask_the_teacher():
    sub = "2026-09-14T20:00:00-04:00"
    assert [a.action for a in run(item(), {"canvas": canvas(state="submitted", submitted_at=sub)}).answers] == ["ask_teacher"]


def test_no_answer_opens_a_form_any_more():
    for answers in V.ANSWERS.values():
        for a in answers:
            assert a.action is not None and a.action in V.ACTIONS, a
```

In `tests/test_phrasing.py` append:

```python
def test_the_one_tap_words_exist_in_every_tier():
    for key in ("a.today", "a.tomorrow", "a.add_details", "step.work_on_it", "where.planned_today", "where.planned_tomorrow", "facts.not_due_yet"):
        assert key in phrasing.PHRASES, key
```

In `tests/test_web_questions.py` append:

```python
def test_every_answer_form_carries_a_request_key(tmp_path):
    import re
    c, pid = _setup(tmp_path)
    forms = re.findall(r'<form hx-post="/items/%d/answer".*?</form>' % pid, c.get(f"/items/{pid}").text, re.S)
    assert forms
    keys = {re.search(r'name="request_key" value="([^"]+)"', f).group(1) for f in forms}
    assert len(keys) == 1 and len(next(iter(keys))) == 36       # one uuid per card, shared by its buttons
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_verdicts.py tests/test_phrasing.py tests/test_web_questions.py`
Expected: FAIL with `AttributeError: 'Answer' object has no attribute 'action'` and the missing keys.

- [ ] **Step 3: Change the model and the table** (`verdicts.py`)

```python
@dataclass(frozen=True)
class Answer:
    key: str                # phrase key for the button label
    action: str             # a flag, "confirm", "clear", or a plan action ("plan:today", "plan:tomorrow")


PLAN_ACTIONS = ("plan:today", "plan:tomorrow")
ACTIONS = HANDLED_FLAGS + MARKED_FLAGS + ("confirm", "clear") + PLAN_ACTIONS

ASK = Answer("a.ask_teacher", "ask_teacher")
TODAY, TOMORROW = Answer("a.today", "plan:today"), Answer("a.tomorrow", "plan:tomorrow")
```

Rows in `ANSWERS` that change or appear (leave the others as they are):

```python
    "still_ungraded": (Answer("a.handed_in", "done"), TODAY, TOMORROW, ASK),
    "teacher_grading": (ASK,),
    "not_done": (Answer("a.handed_in_behind", "done"), TODAY, TOMORROW),
    "past_credit": (Answer("a.let_go", "ignore"), Answer("a.handed_in_behind", "done"), TODAY),
    # Upcoming or undated work with nothing handed in: the plan is the answer (spec 6.2).
    "not_due_yet": (TODAY, TOMORROW, Answer("a.handed_in_behind", "done")),
```

Rule 15 in `_waiting_or_status`, replacing the last two lines:

```python
    # 15: a plain outcome. Work the school recorded as not done still offers a one-tap answer,
    # and so does work not yet due: `classify` only says NOT_DUE when nothing is handed in.
    if outcome == outcomes.NOT_DONE:
        return Verdict(STATUS, outcome, {"school": _school_says(c, h, points)}, ANSWERS["not_done"])
    if outcome == outcomes.NOT_DUE:
        return Verdict(STATUS, outcome, {}, ANSWERS["not_due_yet"])
    return Verdict(STATUS, outcome)
```

`outcomes.NOT_DUE == "not_due_yet"`, so the kind and the table key agree.

- [ ] **Step 4: Add the phrases** (`phrasing.PHRASES`)

```python
    # --- one-tap answers: plan it, and what the done-line then says (spec 6) --------------
    "a.today":               {"early": "Today", "middle": "Today", "older": "Today"},
    "a.tomorrow":            {"early": "Tomorrow", "middle": "Tomorrow", "older": "Tomorrow"},
    "a.add_details":         {"early": "Add details", "middle": "Add details", "older": "Add details"},
    "step.work_on_it":       {"early": "Work on it", "middle": "Work on it", "older": "Work on it"},
    "where.planned_today":   {"early": "You'll work on it today", "middle": "Planned for today", "older": "Planned for today"},
    "where.planned_tomorrow": {"early": "You'll work on it tomorrow", "middle": "Planned for tomorrow", "older": "Planned for tomorrow"},
    "facts.not_due_yet":     {"early": "Nothing handed in yet.", "middle": "Nothing handed in yet.", "older": "Nothing handed in yet."},
```

- [ ] **Step 5: The template global and the answers partial**

`app.py`, right after `ENV = jinja2.Environment(...)`:

```python
from uuid import uuid4
ENV.globals["request_key"] = lambda: str(uuid4())      # one token per rendered card (spec 6.3)
```

(Put the import with the other imports at the top of the file.)

`_answers.html`, whole file:

```jinja
{# A verdict's answer buttons, swapping the element `qid` names (set by the includer). Shared by the
   question card and the check-in's review cards, so both offer the same answers. Every button is a
   one-tap POST; a plan action creates a step with defaults (spec 6.3). One request key per card, so
   a double-click or a retried POST lands on one step. #}
  {% set token = request_key() %}
  <div class="answers">
    {% for a in vd.answers %}<form hx-post="/items/{{ item.id }}/answer" hx-target="#{{ qid }}" hx-swap="outerHTML"><input type="hidden" name="prev" value="{{ item.flag or '' }}"><input type="hidden" name="prev_set_at" value="{{ item.flag_set_at or '' }}"><input type="hidden" name="slot" value="{{ qid }}"><input type="hidden" name="request_key" value="{{ token }}"><button name="answer" value="{{ a.action }}" class="{{ 'primary' if loop.first }}">{{ a.key | say(tier) }}</button></form>{% endfor %}
  </div>
```

`_question.html`: the `more` line gains the step-form link so the question card keeps a way to the form (the old "Not yet, plan it" link is gone):

```jinja
  {% if not (slot is defined and slot and slot.startswith('qd-')) %}<p class="more"><a href="#detail-{{ item.id }}" hx-get="/items/{{ item.id }}" hx-target="#{{ qid }}" hx-swap="outerHTML">Add a note</a> · <a href="/kids/{{ student.key | urlencode }}/check-in/step?item_id={{ item.id }}&amp;return_to={{ here | urlencode }}">Plan a step</a></p>{% endif %}
```

- [ ] **Step 6: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_verdicts.py tests/test_phrasing.py tests/test_web_questions.py tests/test_web_checkin_verdicts.py tests/test_web_kid_questions.py tests/test_web_questions_page.py`
Expected: all pass. `test_the_question_card_offers_the_record_and_plan_links` still finds `check-in/step?item_id=` through the new "Plan a step" link. The route does not accept `plan:*` yet; nothing posts it until Task 8.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/verdicts.py fridgesheet/web/phrasing.py fridgesheet/web/app.py fridgesheet/web/templates/_answers.html fridgesheet/web/templates/_question.html tests/test_verdicts.py tests/test_phrasing.py tests/test_web_questions.py
git commit -m "feat(answers): every card kind that can take an answer offers one tap

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: The plan panel as a partial, and answers on every check-in card

**Files:**
- Create: `fridgesheet/web/templates/_plan_panel.html`
- Modify: `fridgesheet/web/templates/checkin.html:22-73`
- Test: `tests/test_web_checkin_verdicts.py`

**Interfaces:**
- Produces: `_plan_panel.html`, whose root is `<section id="plan" class="plan-panel" ...>` and which sets `hx-swap-oob="true"` when the includer set `oob`. Context it reads: `student, base, steps, completed, completed_for, states, today, total_minutes, unestimated, last_check, over`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_checkin_verdicts.py`)

```python
# --- one tap on every card (spec 6.2, 6.5) --------------------------------------------------------

def _card(body, pid):
    return re.search(r'<article class="card review-card" id="qc-%d".*?</article>' % pid, body, re.S).group(0)


def test_an_upcoming_card_offers_today_tomorrow_and_handed_in(tmp_path):
    vid = _id(tmp_path, "Vocabulary")                      # due today, nothing handed in
    card = _card(app_for(tmp_path).get("/kids/Alex/check-in").text, vid)
    assert 'value="plan:today"' in card and 'value="plan:tomorrow"' in card and 'value="done"' in card
    assert 'class="ask"' not in card                        # a status, not a question


def test_a_waiting_card_offers_ask_the_teacher(tmp_path):
    eid = _id(tmp_path, "Essay draft")                      # submitted, ungraded
    card = _card(app_for(tmp_path).get("/kids/Alex/check-in").text, eid)
    assert 'value="ask_teacher"' in card


def test_the_plan_panel_is_one_partial_with_its_id(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    sections = re.findall(r'<section id="plan"[^>]*>', body)          # `id="plan-heading"` is a different id
    assert len(sections) == 1 and "hx-swap-oob" not in sections[0]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_checkin_verdicts.py -k "upcoming or waiting_card or panel"`
Expected: FAIL: the upcoming card has no `plan:today` button.

- [ ] **Step 3: Extract the panel**

Create `_plan_panel.html` with exactly the markup of `checkin.html` lines 49 to 73 (the `<section id="plan" ...>` through its `</section>`), changing only the opening tag:

```jinja
{# "Our next steps": the family's plan for this kid. Rendered on the check-in and the plan
   page, and swapped in out of band after a one-tap plan answer (spec 6.5). #}
<section id="plan" class="plan-panel" aria-labelledby="plan-heading"{% if oob is defined and oob %} hx-swap-oob="true"{% endif %}>
```

In `checkin.html` replace those lines with:

```jinja
{% include "_plan_panel.html" %}
```

- [ ] **Step 4: Answers on every card**

In `checkin.html` replace lines 33 to 35 (the `{% if view.asks %}` block) with:

```jinja
      {% if view.verdict.answers %}{% set item = view %}{% set qid = 'qc-' ~ view.id %}{% set vd = view.verdict %}{% set tier = student.key | tier_of %}
      {% if vd.state == 'question' %}<p class="ask">{{ ('ask.' ~ vd.kind) | say(tier) }}</p>{% endif %}
      {% include "_answers.html" %}{% endif %}
```

The queue already leaves out items an active step covers, so no `view.step` check is needed here.

- [ ] **Step 5: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_checkin_verdicts.py tests/test_web_checkin.py tests/test_print_sheet.py`
Expected: all pass. `test_one_name_for_planning_a_step` still finds `>Plan a step<` on the card.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/templates/_plan_panel.html fridgesheet/web/templates/checkin.html tests/test_web_checkin_verdicts.py
git commit -m "feat(check-in): answers on every card; the plan panel is a partial

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The plan answers: create a step, undo it, refresh the panel

**Files:**
- Modify: `fridgesheet/web/routes/questions.py` (`ANSWERS`, `answer`, `undo`, new `_plan_step`)
- Modify: `fridgesheet/web/templates/_answered.html`
- Modify: `fridgesheet/web/templates/_after_answer.html`
- Test: `tests/test_web_questions.py`

**Interfaces:**
- Consumes: `verdicts.PLAN_ACTIONS`, `verdicts.ACTIONS` (Task 6); `plans.save`, `plans.one`, `plans.delete`, `plans.evidence`; `checkin._context` (existing); `_plan_panel.html` (Task 7); phrase `step.work_on_it`, `where.planned_*`, `a.add_details` (Task 6).
- Produces: `POST /items/{id}/answer` accepts `answer=plan:today|plan:tomorrow` with `request_key`; `POST /items/{id}/undo` accepts `step_id`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_questions.py`)

```python
# --- plan answers (spec 6.3, 6.4, 6.5) ---------------------------------------------------------------

from uuid import uuid4

from fridgesheet.web.stores import plans


def _steps(home):
    conn = db.open_db(home)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM plan_steps ORDER BY id")]
    finally:
        conn.close()


def _plan(c, pid, when="plan:today", key=None, slot=""):
    return c.post(f"/items/{pid}/answer", data={"answer": when, "prev": "", "request_key": key or str(uuid4()), "slot": slot})


def test_today_creates_a_step_with_the_documented_defaults(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    r = _plan(c, vid, "plan:today", slot=f"qc-{vid}")
    assert r.status_code == 200
    (step,) = _steps(tmp_path)
    assert (step["title"], step["next_step"], step["owner"], step["planned_for"], step["minutes"], step["state"], step["position"]) == \
        ("Vocabulary", "Work on it", "Alex", "2026-09-15", None, "planned", 10)
    assert step["item_id"] == vid and step["family_account"] == "" and step["revision"] == 1
    assert "Planned for today" in r.text and "Undo" in r.text
    assert f'check-in/step?step_id={step["id"]}' in r.text and "Add details" in r.text


def test_tomorrow_plans_for_the_next_day(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid, "plan:tomorrow")
    assert _steps(tmp_path)[0]["planned_for"] == "2026-09-16"


def test_the_same_request_key_twice_is_one_step(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    key = str(uuid4())
    first, second = _plan(c, vid, key=key), _plan(c, vid, key=key)
    assert first.status_code == 200 and second.status_code == 200
    assert len(_steps(tmp_path)) == 1


def test_a_plan_answer_on_covered_work_is_refused(tmp_path):
    """Review Focus 3: one commitment per assignment from a tap."""
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    r = _plan(c, vid, "plan:tomorrow")
    assert r.status_code == 409 and len(_steps(tmp_path)) == 1


def test_a_plan_answer_without_a_request_key_is_refused(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    assert c.post(f"/items/{vid}/answer", data={"answer": "plan:today", "prev": ""}).status_code == 400


def test_the_response_carries_the_plan_panel_out_of_band(tmp_path):
    import re
    c, vid = _setup(tmp_path, "Vocabulary")
    body = _plan(c, vid).text
    section = re.search(r'<section id="plan"[^>]*hx-swap-oob="true"[^>]*>.*?</section>', body, re.S)
    assert section, body[:2000]
    assert "Vocabulary" in section.group(0)                                 # the step is in the panel
    assert "1 step without an estimate" in section.group(0)


def test_undo_deletes_an_unedited_step_and_brings_the_card_back(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    body = _plan(c, vid, slot=f"qc-{vid}").text
    sid = _steps(tmp_path)[0]["id"]
    assert f'name="step_id" value="{sid}"' in body
    r = c.post(f"/items/{vid}/undo", data={"prev": "", "step_id": str(sid), "slot": f"qc-{vid}"})
    assert r.status_code == 200 and _steps(tmp_path) == []
    assert 'value="plan:today"' in r.text and 'id="plan"' in r.text


def test_undo_leaves_an_edited_step_alone(tmp_path):
    """Review Focus 4."""
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    step = _steps(tmp_path)[0]
    conn = db.open_db(tmp_path)
    plans.save(conn, step["student_id"], {**{k: step[k] for k in plans.FIELDS}, "minutes": 20}, now="2026-09-15T15:00:00-04:00",
               request_key=str(uuid4()), item_id=vid, step_id=step["id"], revision=1)
    conn.close()
    r = c.post(f"/items/{vid}/undo", data={"prev": "", "step_id": str(step["id"])})
    assert r.status_code == 200 and _steps(tmp_path)[0]["minutes"] == 20


def test_undo_with_another_kids_step_is_refused(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    sid = _steps(tmp_path)[0]["id"]
    other = _id(db.open_db(tmp_path), "Cell diagram")                      # Sam's
    assert c.post(f"/items/{other}/undo", data={"prev": "", "step_id": str(sid)}).status_code == 404
    assert len(_steps(tmp_path)) == 1


def test_a_planned_item_leaves_the_check_in_queue(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    body = c.get("/kids/Alex/check-in").text
    assert f'id="qc-{vid}"' not in body and "Vocabulary" in body.split('<section id="plan"')[1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_questions.py -k "plan or undo_deletes or undo_leaves or another_kids or request_key or panel"`
Expected: FAIL with 400 `unknown answer 'plan:today'`.

- [ ] **Step 3: The route**

`routes/questions.py`: imports and the answer set.

```python
from datetime import timedelta

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..app import Db, State, render, render_partial
from ..stores import flags, items, plans, students
from .. import db, phrasing, tiers, verdicts
from . import checkin

router = APIRouter()
ANSWERS = set(verdicts.ACTIONS)
```

The step builder and the two routes:

```python
def _plan_step(conn, state, student, view, action: str, request_key: str) -> int:
    """A step from one tap, with the defaults the step form would have offered (spec 6.3)."""
    day = state.now().date() + (timedelta(days=1) if action == "plan:tomorrow" else timedelta(0))
    tier = tiers.for_student(state.settings, student["key"])
    said = [t for t in (view.flag_text, view.latest_note["body"] if view.latest_note else "") if t]
    values = dict(title=view.name, family_account="\n".join(said), next_step=phrasing.phrase("step.work_on_it", tier),
                  owner=state.settings.nicknames.get(student["key"], student["key"]), planned_for=day.isoformat(),
                  minutes=None, state="planned", position=10, evidence=plans.evidence(view), recorded_by="")
    return plans.save(conn, student["id"], values, now=db.now_iso(state.tz), request_key=request_key, item_id=view.id)


def _card(request, conn, state, item_id, slot, status_code=200, **extra) -> HTMLResponse:
    s, v = _view(conn, state, item_id)
    r = render_partial(request, conn, "_question.html", student=s, item=v, slot=_slot(slot, item_id), **extra)
    r.status_code = status_code
    return r


@router.post("/items/{item_id}/answer")
def answer(item_id: int, request: Request, answer: str = Form(...), prev: str = Form(""), prev_set_at: str = Form(""),
           slot: str = Form(""), request_key: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    if answer not in ANSWERS:
        raise HTTPException(400, f"unknown answer {answer!r}")
    s, v = _view(conn, state, item_id)
    if answer in verdicts.PLAN_ACTIONS:
        if not 1 <= len(request_key) <= 100:
            raise HTTPException(400, "a plan answer needs its request key")
        # A retried POST (double-click, flaky network) carries the key of the step it already
        # made: answer with that step again rather than refusing it as "already covered".
        earlier = plans.by_request_key(conn, s["id"], request_key)
        if earlier is not None and earlier["item_id"] == item_id:
            step_id = earlier["id"]
        elif v.step is not None:
            return _card(request, conn, state, item_id, slot, status_code=409)
        else:
            try:
                step_id = _plan_step(conn, state, s, v, answer, request_key)
            except plans.Conflict:
                return _card(request, conn, state, item_id, slot, status_code=409)
        s, v = _view(conn, state, item_id)
        ctx = checkin._context(conn, s, state)
        ctx.update(item=v, prev=prev, prev_set_at=prev_set_at, slot=_slot(slot, item_id),
                   step_id=step_id, planned=answer[len("plan:"):], plan_panel=True)
        return render_partial(request, conn, "_answered.html", **ctx)
    _apply(conn, item_id, answer, db.now_iso(state.tz))
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_answered.html", student=s, item=v, prev=prev, prev_set_at=prev_set_at,
                          slot=_slot(slot, item_id))


@router.post("/items/{item_id}/undo")
def undo(item_id: int, request: Request, prev: str = Form(""), prev_set_at: str = Form(""), slot: str = Form(""),
         step_id: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """Put the item back as it was before the answer: the earlier flag with its original date
    (so a question the school raised comes back), or no flag at all. For a plan answer, the
    step it created is deleted if nobody has edited it since (spec 6.4)."""
    if prev and prev not in flags.FLAGS:
        raise HTTPException(400, f"unknown flag {prev!r}")
    s, v = _view(conn, state, item_id)
    if step_id:
        if not step_id.isdigit():
            raise HTTPException(404, "no such step")
        step = plans.one(conn, s["id"], int(step_id))
        if step is None or step["item_id"] != item_id:
            raise HTTPException(404, "no such step")
        if step["revision"] == 1:
            plans.delete(conn, s["id"], step["id"])
        s, v = _view(conn, state, item_id)
        ctx = checkin._context(conn, s, state)
        ctx.update(item=v, slot=_slot(slot, item_id), undone=True, plan_panel=True)
        return render_partial(request, conn, "_question.html", **ctx)
    now = db.now_iso(state.tz)
    if prev and prev_set_at:
        flags.restore(conn, item_id, prev, set_at=prev_set_at, now=now)
    else:
        _apply(conn, item_id, prev or "clear", now)
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_question.html", student=s, item=v, slot=_slot(slot, item_id), undone=True)
```

`plans.one` checks the student, so a step that belongs to another kid comes back `None` and is a 404; a step that belongs to this kid but another item is refused the same way.

Add the lookup the route uses to `fridgesheet/web/stores/plans.py`, after `one`:

```python
def by_request_key(conn, student_id, request_key):
    """The step a form token already created, or None: how a retried POST finds its own step."""
    row = conn.execute("SELECT * FROM plan_steps WHERE student_id = ? AND request_key = ?", (student_id, request_key)).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4: The done-line and the out-of-band panel**

`_answered.html`, whole file:

```jinja
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
{% set qid = slot if slot is defined and slot else 'q-' ~ item.id %}
{% set said = (('where.planned_' ~ planned) | say(tier)) if planned is defined and planned else (item | standing(tier)) %}
<div class="done-line" id="{{ qid }}" data-focus data-announce="{{ item.name }}: {{ said }}">
  <span class="tick" aria-hidden="true">✓</span>
  <span tabindex="-1" data-focus-target><b>{{ item.name }}</b>: {{ said }}{% if item.verdict.kind == 'asked' and item.teacher_email %} · <a href="mailto:{{ item.teacher_email }}?subject={{ ('About ' ~ item.name) | urlencode }}">Email the teacher</a>{% endif %}{% if step_id is defined and step_id %} · <a href="/kids/{{ student.key | urlencode }}/check-in/step?step_id={{ step_id }}&amp;return_to={{ here | urlencode }}">{{ 'a.add_details' | say(tier) }}</a>{% endif %}</span>
  <form hx-post="/items/{{ item.id }}/undo" hx-target="#{{ qid }}" hx-swap="outerHTML"><input type="hidden" name="prev" value="{{ prev | default('') }}"><input type="hidden" name="prev_set_at" value="{{ prev_set_at | default('') }}"><input type="hidden" name="slot" value="{{ qid }}">{% if step_id is defined and step_id %}<input type="hidden" name="step_id" value="{{ step_id }}">{% endif %}<button class="link">Undo</button></form>
</div>
{% include "_after_answer.html" %}
```

`_after_answer.html`, append at the end:

```jinja
{# After a plan answer or its undo: the plan panel, so the step appears (or disappears) without a
   reload. Pages without a #plan element drop the swap (spec 6.5). #}
{% if plan_panel is defined and plan_panel %}{% set oob = true %}{% include "_plan_panel.html" %}{% endif %}
```

- [ ] **Step 5: Run the tests**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q tests/test_web_questions.py tests/test_web_checkin_verdicts.py tests/test_web_checkin.py tests/test_web_kid_questions.py tests/test_web_answer_trail.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/routes/questions.py fridgesheet/web/stores/plans.py fridgesheet/web/templates/_answered.html fridgesheet/web/templates/_after_answer.html tests/test_web_questions.py
git commit -m "feat(answers): Today and Tomorrow create a plan step in place, with undo

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Docs, the whole suite, and a look at the real page

**Files:**
- Modify: `docs/outcomes.md:64`
- Modify: `fridgesheet/web/verdicts.py:1-10` (module docstring)

- [ ] **Step 1: Update the outcomes doc**

In `docs/outcomes.md` line 64, replace the three mentions of a fixed seven days:

> waits on what time will settle (a Canvas grade not yet in HAC; paper work with no grade for less time than that class usually takes; work handed in and not graded), and asks only when the family can act: HAC lower than Canvas, a HAC zero on work handed in online or excused in Canvas, HAC still blank longer than it usually takes for that class, paper or HAC-only work with no grade longer than that class usually takes, or a newer record contradicting your own answer. "Usually takes" is Fridge Sheet's own count from that class's earlier grades (`web/pace.py`), 7 days until there are enough of them.

- [ ] **Step 2: Update the verdicts docstring**

Add to the module docstring of `verdicts.py`, after the sentence ending "the first that matches wins":

```
The two grace periods (HAC catching up; paper work with no grade) are not a fixed week: they are
what this class's history says it usually takes (web/pace.py), and the card says so.
```

- [ ] **Step 3: Run the whole suite**

Run: `env -u PYTHONPATH /home/tony/GitHub/fridgesheet/.venv/bin/python -m pytest -q 2>&1 | tee /tmp/fridgesheet-pace-suite.log | tail -5`
Expected: all pass, 0 failed. Fix anything that fails before going on; do not skip.

- [ ] **Step 4: See it on a real database**

Copy the household's home folder (the one holding `fridgesheet.db` and `config.toml`, `~/.fridgesheet` by default) to a scratch folder and start the web app against the copy: `fridgesheet web` reads its home from `FRIDGESHEET_HOME` (check `fridgesheet web --help` for the exact flag if that variable is not honoured). Open a kid's check-in and confirm: waiting cards carry a "Fridge Sheet's count …" or "… no earlier grades …" line; an upcoming card shows Today, Tomorrow, It's handed in; tapping Today moves the card into "Our next steps" without a reload; Undo brings it back. Record what you saw in the PR description. If the live database cannot be reached, say so in the PR and skip this step.

- [ ] **Step 5: Commit**

```bash
git add docs/outcomes.md fridgesheet/web/verdicts.py
git commit -m "docs: the grace period is the class's learned pace

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

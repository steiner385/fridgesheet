# The Plan Fills Itself Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The kid's plan page opens with a "Must finish" list computed from the school record, greys family steps the school now shows as handed in, moves questions below the plan, records what the list held at each check-in, and lets the kid ask Canvas again from the page.

**Architecture:** A derived list, never stored: `items.must_finish` partitions the rows `items.open_work` already computes (the same rows as the Open work page and the printed sheet) into six sections by outcome and deadline, minus items an active family step covers. `checkin._context` carries the sections, a witness line per covered step, and the reordered review groups into the existing templates. The only schema change is one `seen` column on `checkins`.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, htmx, SQLite, pytest. Run tests with `env -u PYTHONPATH <venv>/bin/python -m pytest` (a sibling worktree's `.venv` works; `PYTHONPATH` shadows the `tests` package).

**Spec:** `docs/superpowers/specs/2026-09-27-plan-fills-itself-design.md` (sections 1–12, 14–17; section 13, kid mode, is `2026-09-27-kid-mode.md`)

## Global Constraints

- The app never inserts, completes or deletes a `plan_steps` row on its own. Every write of a family row is a POST a person made (spec §2, §14).
- Must finish is exactly `open_work(...).fixable + open_work(...).upcoming` minus covered ids; no second definition of "turned in" (spec §4.1, §4.5).
- Every new heading, badge, sentence or button label is a `phrasing.PHRASES` key in three tiers (`early`, `middle`, `older`); no younger tier states a number, date or time its `older` entry does not (spec §11; `tests/test_phrasing.py` holds this).
- Every child sees every row and every action on every tier; tiers change words, type and colour only (`tests/test_web_tier_parity.py`).
- `too_late` and `ignore` answers never render on a Must-finish row (spec §4.4).
- A witness line names Canvas, HAC or the family, never "the school" for a family answer (spec §6).
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. **An item due at 00:30 tomorrow, read at 9 pm tonight:** it must sit in Due tonight, not Due tomorrow (`dates.deadline_date`). Pinned in Task 1.
2. **A HAC zero on work handed in online:** its verdict is the `submitted_hac_zero` question; the row must keep "Ask the teacher" first and show the zero-to-check badge, never "It's handed in" first. Pinned in Task 4.
3. **A `done` flag the school later contradicts (`stale_answer`):** the step must un-grey and count in the minutes again; the item must come back into Must finish or Worth checking. Pinned in Task 5.
4. **Finishing a check-in when Must finish is empty:** `seen` must be `[]`, and no row may badge "On Sunday's list" afterwards for an item that appears later. Pinned in Task 6.
5. **A refresh started from the plan page while another job runs:** the 409 "Busy" card must render into `#job` on the plan page, and the page must not reload. Pinned in Task 9.

---

### Task 1: `items.must_finish`, the six sections

**Files:**
- Modify: `fridgesheet/web/stores/items.py` (after `open_work`, ~line 550)
- Modify: `fridgesheet/reports/open_work.py:47-56` (`sheet_status` moves; keep the name here as an alias)
- Test: `tests/test_must_finish.py` (new)

**Interfaces:**
- Consumes: `items.open_work(conn, student, *, now, rules, days_ahead, overdue_days, prefs) -> OpenWork` with `.fixable` and `.upcoming` lists of `ItemView`; `ItemView.outcome`, `.due`, `.id`; `dates.deadline_date(due) -> date`; `outcomes.NOT_DONE / UNKNOWN / LATE`.
- Produces:
  - `items.MustFinish` frozen dataclass: `tonight, tomorrow, overdue, paper, waiting, later: list[ItemView]`; `.red -> list[ItemView]` (tonight + tomorrow + overdue); `.unpicked -> list[ItemView]` (red + paper); `.ids -> set[int]` (every section); `.__len__`.
  - `items.must_finish(work: OpenWork, today: date, covered: set[int] = frozenset()) -> MustFinish`.
  - `items.sheet_status(v: ItemView) -> str` (the sheet's word: DUE TONIGHT, MISSING, ZERO, PAPER — CHECK …), moved from `reports/open_work.py` so templates can use it without importing the report package (which pulls reportlab).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_must_finish.py
"""Must finish: the Open work rows, sectioned for tonight (spec 2026-09-27 §4)."""
from __future__ import annotations

from datetime import datetime, timedelta

from fridgesheet import late_rules
from fridgesheet.web.stores import items, students
from tests.web_fixtures import NOW, TZ, _a, _h, seed, snapshot

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _work(tmp_path, key="Alex", snap=None, now=NOW):
    conn = seed(tmp_path, snap)
    s = students.by_key(conn, key)
    w = items.open_work(conn, s, now=now, rules=RULES, days_ahead=14, overdue_days=14)
    conn.close()
    return w


def _names(views):
    return [v.name for v in views]


def test_the_fixture_lands_in_the_documented_sections(tmp_path):
    mf = items.must_finish(_work(tmp_path), NOW.date())
    assert _names(mf.tonight) == ["Vocabulary"]                 # due 9/15 23:59, read at 9/15 14:00
    assert _names(mf.tomorrow) == ["Worksheet 3"]               # due 9/16
    assert _names(mf.later) == ["Reading log"]                  # due 9/20, within 14 days
    assert _names(mf.overdue) == []                             # Homework 4 is past its window: not fixable
    assert set(_names(mf.paper)) == {"Lab notebook", "Participation"}   # paper, no grade; HAC-only, no grade
    assert mf.waiting == []
    assert "Essay draft" not in _names(mf.red + mf.paper + mf.waiting + mf.later)   # submitted on time: not open
    assert "Quiz 1" not in [v.name for v in mf.red]                                # HAC's 28/30 settles it


def test_sam_has_two_overdue_rows_a_missing_and_a_zero(tmp_path):
    mf = items.must_finish(_work(tmp_path, "Sam"), NOW.date())
    assert set(_names(mf.overdue)) == {"Cell diagram", "Safety quiz"}
    assert mf.red == mf.overdue and mf.paper == [] and len(mf) == 2


def test_the_sections_partition_fixable_and_upcoming(tmp_path):
    for key in ("Alex", "Sam"):
        w = _work(tmp_path, key)
        mf = items.must_finish(w, NOW.date())
        assert mf.ids == {v.id for v in w.fixable + w.upcoming}
        sections = [mf.tonight, mf.tomorrow, mf.overdue, mf.paper, mf.waiting, mf.later]
        assert sum(len(s) for s in sections) == len(mf.ids)


def test_a_covered_item_is_left_out_of_every_section(tmp_path):
    w = _work(tmp_path)
    vocab = next(v for v in w.upcoming if v.name == "Vocabulary")
    mf = items.must_finish(w, NOW.date(), covered={vocab.id})
    assert "Vocabulary" not in _names(mf.tonight) and vocab.id not in mf.ids


def test_a_deadline_in_the_first_hour_belongs_to_the_evening_before(tmp_path):
    """Review Focus 1: due 9/16 00:30, read 9/15 at 2 pm, is tonight (#139)."""
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    eng["assignments"].append(_a(83, "Midnight quiz", "09-16", due_at="2026-09-16T00:30:00-04:00"))
    mf = items.must_finish(_work(tmp_path, snap=snap), NOW.date())
    assert "Midnight quiz" in _names(mf.tonight) and "Midnight quiz" not in _names(mf.tomorrow)


def test_a_late_hand_in_with_no_grade_is_waiting(tmp_path):
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    for a in eng["assignments"]:
        if a["name"] == "Lab notebook":
            a.update(submission_types=["online_upload"], state="submitted", late=True,
                     submitted_at="2026-09-12T20:00:00-04:00", seconds_late=100000)
    mf = items.must_finish(_work(tmp_path, snap=snap), NOW.date())
    assert _names(mf.waiting) == ["Lab notebook"] and "Lab notebook" not in _names(mf.paper)


def test_unpicked_is_the_open_groups_not_the_folded_ones(tmp_path):
    mf = items.must_finish(_work(tmp_path), NOW.date())
    assert set(_names(mf.unpicked)) == {"Vocabulary", "Worksheet 3", "Lab notebook", "Participation"}


def test_sheet_status_is_the_sheets_word(tmp_path):
    w = _work(tmp_path, "Sam")
    words = {v.name: items.sheet_status(v) for v in w.fixable}
    assert words == {"Cell diagram": "MISSING", "Safety quiz": "ZERO"}
    w = _work(tmp_path)
    assert {v.name: items.sheet_status(v) for v in w.upcoming}["Vocabulary"] == "DUE TODAY"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_must_finish.py -v`
Expected: FAIL with `AttributeError: module 'fridgesheet.web.stores.items' has no attribute 'must_finish'`

- [ ] **Step 3: Add `sheet_status`, `MustFinish` and `must_finish` to the items store**

In `fridgesheet/web/stores/items.py`, after the `open_work` function:

```python
def sheet_status(v: ItemView) -> str:
    """The sheet's word for a page row: DUE TODAY / DUE SUN for what is coming due, else the
    capitals of its status phrase (`sheet.STATUS_WORD`), else ZERO for a gradebook's zero.
    Lives here (not in `reports/open_work.py`) so a template can say it without importing
    the report package."""
    from ... import sheet                       # sheet imports phrasing only; no reportlab
    if v.upcoming and not v.overdue:
        return v.status.upper()
    if v.status in sheet.STATUS_WORD:
        return sheet.STATUS_WORD[v.status]
    if v.grade_zero:
        return "ZERO"
    return v.status.upper()


@dataclass(frozen=True)
class MustFinish:
    """Open work's rows, sectioned for tonight (spec 2026-09-27 §4.2). The three `fixable`
    sections partition it by outcome; the three `upcoming` sections by deadline."""
    tonight: list[ItemView]
    tomorrow: list[ItemView]
    overdue: list[ItemView]
    paper: list[ItemView]
    waiting: list[ItemView]
    later: list[ItemView]

    @property
    def red(self) -> list[ItemView]:
        return self.tonight + self.tomorrow + self.overdue

    @property
    def unpicked(self) -> list[ItemView]:
        """The rows shown open on the page: what "not picked yet" counts."""
        return self.red + self.paper

    @property
    def ids(self) -> set[int]:
        return {v.id for s in (self.tonight, self.tomorrow, self.overdue, self.paper, self.waiting, self.later) for v in s}

    def __len__(self) -> int:
        return len(self.ids)


def must_finish(work: OpenWork, today: date, covered: set[int] = frozenset()) -> MustFinish:
    """Open work's `fixable + upcoming`, minus items an active family step covers, in the
    six sections. `fixable` and `upcoming` are disjoint (an upcoming row has nothing open),
    and an open row's outcome is one of not done, unknown or late (`reconcile.open_sources`),
    so every row lands in exactly one section."""
    up = [v for v in work.upcoming if v.id not in covered]
    fix = [v for v in work.fixable if v.id not in covered]
    tomorrow = today + timedelta(days=1)
    return MustFinish(
        tonight=[v for v in up if deadline_date(v.due) <= today],
        tomorrow=[v for v in up if deadline_date(v.due) == tomorrow],
        later=[v for v in up if deadline_date(v.due) > tomorrow],
        overdue=[v for v in fix if v.outcome == outcomes.NOT_DONE],
        paper=[v for v in fix if v.outcome == outcomes.UNKNOWN],
        waiting=[v for v in fix if v.outcome == outcomes.LATE],
    )
```

Check the imports at the top of `items.py`: `date` and `timedelta` from `datetime`, `deadline_date` from `...dates`, `outcomes` from `..` — add any that are missing.

In `fridgesheet/reports/open_work.py`, replace the body of `sheet_status` with a delegation so the sheet and the page cannot drift:

```python
def sheet_status(v: items_store.ItemView) -> str:
    """The sheet's word for a page row (moved to the items store; kept here by name)."""
    return items_store.sheet_status(v)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_must_finish.py tests/test_open_work_parity.py -v`
Expected: all PASS (the parity tests prove the moved `sheet_status` still agrees with the sheet)

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/stores/items.py fridgesheet/reports/open_work.py tests/test_must_finish.py
git commit -m "Must finish: Open work's rows in six sections for tonight (spec 2026-09-27 §4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The words, in three tiers

**Files:**
- Modify: `fridgesheet/web/phrasing.py` (the `copy.*` block, ~line 114–135; and after `where.stale_answer`)
- Test: `tests/test_phrasing.py`

**Interfaces:**
- Produces the phrase keys every later task's template reads. Exact keys and `older` text:

| Key | older | Values |
|---|---|---|
| `copy.must_finish` | Must finish | |
| `copy.must_finish_hint` | The school says these are not in yet. They leave when it says they are, or when you say so. | |
| `copy.list_as_of` | The school's list as of {when}. | when |
| `copy.due_tonight` | Due tonight | |
| `copy.due_tomorrow` | Due tomorrow | |
| `copy.overdue_fixable` | Overdue, still fixable | |
| `copy.on_paper_no_grade` | On paper, no grade yet | |
| `copy.handed_in_waiting` | Handed in, waiting for a grade | |
| `copy.coming_due_later` | Coming due later | |
| `copy.worth_checking` | Worth checking | |
| `copy.other_open` | Other open work | |
| `copy.school_has_it` | The school has it | |
| `copy.tonight_steps` | Tonight: {steps} step{s}, {minutes} min | steps, s, minutes |
| `copy.tonight_unpicked` | {n} must-finish not picked yet | n |
| `copy.tonight_school_has` | {n} the school has, not counted | n |
| `copy.check_again` | Check Canvas again | |
| `copy.asked_the_school` | Asked the school | |
| `copy.nothing_due` | Nothing due by tomorrow | |
| `copy.not_done_due_by_tomorrow` | not done, due by tomorrow | |
| `copy.details` | Details | |
| `badge.must_finish` | Must finish · {word} | word |
| `badge.zero_to_check` | Zero to check | |
| `badge.changed_since_answer` | Changed since your answer | |
| `badge.seen_at_checkin` | On {day}'s list | day |
| `badge.new_since_checkin` | New since {day} | day |
| `record.canvas_handed_in` | Canvas: handed in {when} | when |
| `record.graded_in` | {source}: graded {score} | source, score |
| `record.you_said_handed_in` | You answered It's handed in, {when} | when |
| `record.you_said_excused` | You answered excused, {when} | when |
| `record.canvas_excused` | Canvas: excused | |
| `a.mark_step_complete` | Mark step complete | |

- [ ] **Step 1: Write the failing test**

Append to `tests/test_phrasing.py`:

```python
MUST_FINISH_KEYS = (
    "copy.must_finish", "copy.must_finish_hint", "copy.list_as_of", "copy.due_tonight", "copy.due_tomorrow",
    "copy.overdue_fixable", "copy.on_paper_no_grade", "copy.handed_in_waiting", "copy.coming_due_later",
    "copy.worth_checking", "copy.other_open", "copy.school_has_it", "copy.tonight_steps", "copy.tonight_unpicked",
    "copy.tonight_school_has", "copy.check_again", "copy.asked_the_school", "copy.nothing_due",
    "copy.not_done_due_by_tomorrow", "copy.details", "badge.must_finish", "badge.zero_to_check", "badge.changed_since_answer",
    "badge.seen_at_checkin", "badge.new_since_checkin", "record.canvas_handed_in", "record.graded_in",
    "record.you_said_handed_in", "record.you_said_excused", "record.canvas_excused", "a.mark_step_complete",
)


@pytest.mark.parametrize("key", MUST_FINISH_KEYS)
def test_the_must_finish_words_exist_in_three_tiers(key):
    """Spec 2026-09-27 §11: every heading, badge and button on the plan page is in the table."""
    assert set(phrasing.PHRASES[key]) == set(tiers.TIERS), key
    assert all(phrasing.PHRASES[key][t].strip() for t in tiers.TIERS), key


def test_the_early_tier_says_the_school_has_it_and_never_says_estimate():
    assert phrasing.phrase("copy.school_has_it", "early") == "The school has it"
    assert "estimate" not in phrasing.phrase("copy.tonight_unpicked", "early")


def test_a_witness_line_names_its_witness_not_the_school():
    for t in tiers.TIERS:
        assert phrasing.phrase("record.canvas_handed_in", t).startswith("Canvas")
        assert "You" in phrasing.phrase("record.you_said_handed_in", t)
        assert "school" not in phrasing.phrase("record.you_said_handed_in", t).lower()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_phrasing.py -k "must_finish or witness or school_has" -v`
Expected: FAIL with `KeyError: 'copy.must_finish'`

- [ ] **Step 3: Add the phrases**

In `fridgesheet/web/phrasing.py`, inside `PHRASES`, after the `copy.tab_all` entry:

```python
    # --- the plan page that fills itself (spec 2026-09-27 §4-§9, §11) ------------------------
    "copy.must_finish":      {"early": "Must finish", "middle": "Must finish", "older": "Must finish"},
    "copy.must_finish_hint": {"early": "The school says these aren't in yet. They go away when it says they are, or when you say so.",
                              "middle": "The school says these are not in yet. They leave when it says they are, or when you say so.",
                              "older": "The school says these are not in yet. They leave when it says they are, or when you say so."},
    "copy.list_as_of":       {"early": "The school's list as of {when}.", "middle": "The school's list as of {when}.", "older": "The school's list as of {when}."},
    "copy.due_tonight":      {"early": "Due tonight", "middle": "Due tonight", "older": "Due tonight"},
    "copy.due_tomorrow":     {"early": "Due tomorrow", "middle": "Due tomorrow", "older": "Due tomorrow"},
    "copy.overdue_fixable":  {"early": "Late, but you can still fix it", "middle": "Overdue, still fixable", "older": "Overdue, still fixable"},
    "copy.on_paper_no_grade": {"early": "On paper, no grade yet", "middle": "On paper, no grade yet", "older": "On paper, no grade yet"},
    "copy.handed_in_waiting": {"early": "Handed in, waiting for a grade", "middle": "Handed in, waiting for a grade", "older": "Handed in, waiting for a grade"},
    "copy.coming_due_later": {"early": "Due later", "middle": "Coming due later", "older": "Coming due later"},
    "copy.worth_checking":   {"early": "Worth a look", "middle": "Worth checking", "older": "Worth checking"},
    "copy.other_open":       {"early": "Other open work", "middle": "Other open work", "older": "Other open work"},
    "copy.school_has_it":    {"early": "The school has it", "middle": "The school has it", "older": "The school has it"},
    "copy.tonight_steps":    {"early": "Tonight: {steps} step{s}, {minutes} min", "middle": "Tonight: {steps} step{s}, {minutes} min", "older": "Tonight: {steps} step{s}, {minutes} min"},
    "copy.tonight_unpicked": {"early": "{n} not picked yet", "middle": "{n} must-finish not picked yet", "older": "{n} must-finish not picked yet"},
    "copy.tonight_school_has": {"early": "{n} the school has, not counted", "middle": "{n} the school has, not counted", "older": "{n} the school has, not counted"},
    "copy.check_again":      {"early": "Check Canvas again", "middle": "Check Canvas again", "older": "Check Canvas again"},
    "copy.asked_the_school": {"early": "Asked the school", "middle": "Asked the school", "older": "Asked the school"},
    "copy.nothing_due":      {"early": "Nothing due by tomorrow", "middle": "Nothing due by tomorrow", "older": "Nothing due by tomorrow"},
    "copy.not_done_due_by_tomorrow": {"early": "not done, due by tomorrow", "middle": "not done, due by tomorrow", "older": "not done, due by tomorrow"},
    "copy.details":          {"early": "Details", "middle": "Details", "older": "Details"},
    "badge.must_finish":     {"early": "Must finish · {word}", "middle": "Must finish · {word}", "older": "Must finish · {word}"},
    "badge.zero_to_check":   {"early": "Zero to check", "middle": "Zero to check", "older": "Zero to check"},
    "badge.changed_since_answer": {"early": "Changed after you answered", "middle": "Changed since you answered", "older": "Changed since your answer"},
    "badge.seen_at_checkin": {"early": "On {day}'s list", "middle": "On {day}'s list", "older": "On {day}'s list"},
    "badge.new_since_checkin": {"early": "New since {day}", "middle": "New since {day}", "older": "New since {day}"},
    "record.canvas_handed_in": {"early": "Canvas: handed in {when}", "middle": "Canvas: handed in {when}", "older": "Canvas: handed in {when}"},
    "record.graded_in":      {"early": "{source}: graded {score}", "middle": "{source}: graded {score}", "older": "{source}: graded {score}"},
    "record.you_said_handed_in": {"early": "You said it's handed in, {when}", "middle": "You answered It's handed in, {when}", "older": "You answered It's handed in, {when}"},
    "record.you_said_excused": {"early": "You said it's excused, {when}", "middle": "You answered excused, {when}", "older": "You answered excused, {when}"},
    "record.canvas_excused": {"early": "Canvas: excused", "middle": "Canvas: excused", "older": "Canvas: excused"},
    "a.mark_step_complete":  {"early": "Mark step complete", "middle": "Mark step complete", "older": "Mark step complete"},
```

Also reword `copy.queue_hint` for its new place under Worth checking (spec §7):

```python
    "copy.queue_hint":     {"early": "These aren't tonight's must-dos. Look when you have time.",
                            "middle": "These are not tonight's must-dos. Look when there is time.",
                            "older": "These are not tonight's obligations. Look when there is time."},
```

- [ ] **Step 4: Run the phrasing tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_phrasing.py -v`
Expected: all PASS, including the existing number-parity test over the whole table

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/phrasing.py tests/test_phrasing.py
git commit -m "Phrases for the plan that fills itself, in three tiers (spec 2026-09-27 §11)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Schema v9 and the plans store: `seen`, `complete`, `today_load(exclude)`

**Files:**
- Modify: `fridgesheet/web/db.py` (`SCHEMA_VERSION`, a `_SCHEMA_V9` block, the `migrate` chain ~line 425)
- Modify: `fridgesheet/web/stores/plans.py:87-105`
- Test: `tests/test_web_checkin.py` (append), `tests/test_migrate.py` (append)

**Interfaces:**
- Consumes: `plans.finish(conn, student_id, *, now, next_check, available_minutes, summary, request_key, recorded_by="")`; `plans.today_load(conn, student_id, today) -> (int, int)`; `plans.Conflict`.
- Produces:
  - `plans.finish(..., seen: list[int] = ())` stores `json.dumps(sorted(seen))` in `checkins.seen`.
  - `plans.history` / `plans.last_checkin` rows carry `seen` (a JSON string column; callers `json.loads` it).
  - `plans.today_load(conn, student_id, today, exclude: set[int] = frozenset()) -> (int, int)`: steps whose `item_id` is in `exclude` are not counted.
  - `plans.complete(conn, student_id, step_id, *, now: str, revision: int, recorded_by: str = "") -> None`; raises `plans.Conflict` when the revision does not match or the step is missing.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_checkin.py`:

```python
# --- spec 2026-09-27: seen ids, one-tap complete, excluded steps -----------------------------

def test_finishing_records_which_must_finish_ids_the_list_held(tmp_path):
    conn = seed(tmp_path)
    plans.finish(conn, 1, now=NOW.isoformat(), next_check="2026-09-20", available_minutes=30, summary="x",
                 request_key=str(uuid4()), seen=[81, 80])
    last = plans.last_checkin(conn, 1)
    assert last["seen"] == "[80, 81]"
    plans.finish(conn, 1, now=NOW.isoformat(), next_check="2026-09-21", available_minutes=30, summary="y", request_key=str(uuid4()))
    assert plans.last_checkin(conn, 1)["seen"] == "[]"
    conn.close()


def test_complete_marks_a_step_done_with_the_revision_check(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    values = {k: v for k, v in _form(title="Vocabulary").items() if k in plans.FIELDS}
    values.update(minutes=None, position=10, evidence="{}")
    sid = plans.save(conn, 1, values, now=NOW.isoformat(), request_key=str(uuid4()), item_id=vid)
    plans.complete(conn, 1, sid, now=NOW.isoformat(), revision=1, recorded_by="Dad")
    step = plans.one(conn, 1, sid)
    assert (step["state"], step["revision"], step["recorded_by"]) == ("done", 2, "Dad")
    with pytest.raises(plans.Conflict):
        plans.complete(conn, 1, sid, now=NOW.isoformat(), revision=1)        # stale revision
    with pytest.raises(plans.Conflict):
        plans.complete(conn, 2, sid, now=NOW.isoformat(), revision=2)        # another child's id
    conn.close()


def test_today_load_leaves_out_steps_the_school_has(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    base = {k: v for k, v in _form(planned_for="2026-09-15").items() if k in plans.FIELDS}
    base.update(position=10, evidence="{}")
    plans.save(conn, 1, {**base, "minutes": 20}, now=NOW.isoformat(), request_key=str(uuid4()), item_id=vid)
    plans.save(conn, 1, {**base, "title": "Other", "minutes": 10}, now=NOW.isoformat(), request_key=str(uuid4()))
    assert plans.today_load(conn, 1, "2026-09-15") == (2, 30)
    assert plans.today_load(conn, 1, "2026-09-15", exclude={vid}) == (1, 10)
    conn.close()
```

Add `import pytest` at the top of `tests/test_web_checkin.py` if it is not there.

Append to `tests/test_migrate.py`:

```python
# --- schema v9: checkins.seen ------------------------------------------------------------------

def test_a_v8_database_gains_seen_with_an_empty_list_on_old_rows(tmp_path):
    from fridgesheet.web import db
    from tests.web_fixtures import NOW, seed
    conn = seed(tmp_path)
    conn.execute("INSERT INTO checkins(student_id, finished_at, next_check, available_minutes, summary, plan, request_key) "
                 "VALUES (1, ?, '2026-09-20', 30, 's', '[]', 'k1')", (NOW.isoformat(),))
    conn.commit()
    conn.execute("ALTER TABLE checkins DROP COLUMN seen")            # back to the v8 shape
    conn.execute("UPDATE schema_version SET version = 8")
    conn.commit()
    conn.close()
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == db.SCHEMA_VERSION >= 9
    assert conn.execute("SELECT seen FROM checkins").fetchone()[0] == "[]"
    conn.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py -k "seen or complete_marks or leaves_out" tests/test_migrate.py -k v8 -v`
Expected: FAIL (`TypeError: finish() got an unexpected keyword argument 'seen'`; `AttributeError: complete`; `sqlite3.OperationalError: no such column: seen`)

- [ ] **Step 3: Bump the schema and extend the store**

In `fridgesheet/web/db.py`, set `SCHEMA_VERSION = 9` (find the current `SCHEMA_VERSION = 8`), add after `_SCHEMA_V8`:

```python
_SCHEMA_V9 = """
-- The Must-finish item ids the list held when the check-in was finished (spec 2026-09-27
-- §8.2): a JSON list. Not an agreement -- the school record, so a later reader can tell
-- "seen on Sunday" from "new since Sunday". Existing rows read as an empty list.
ALTER TABLE checkins ADD COLUMN seen TEXT NOT NULL DEFAULT '[]';
"""
```

and in `migrate`, after the `v < 8` block:

```python
    if v < 9:
        conn.executescript("BEGIN;\n" + _SCHEMA_V9 + "\nUPDATE schema_version SET version = 9;\nCOMMIT;")
        v = 9
```

In `fridgesheet/web/stores/plans.py`:

```python
def finish(conn, student_id, *, now, next_check, available_minutes, summary, request_key, recorded_by="", seen=()):
    # Keep a snapshot of the agreement, so subsequent edits do not rewrite the conversation.
    # `seen` is the school's list at that moment, kept apart from the plan (spec 2026-09-27 §8.2).
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        plan = [s for s in for_student(conn, student_id) if s["state"] != "done"]
        conn.execute(
            "INSERT INTO checkins(student_id, finished_at, next_check, available_minutes, summary, plan, recorded_by, request_key, seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(request_key) DO NOTHING",
            (student_id, now, next_check, available_minutes, summary, json.dumps(plan), recorded_by, request_key,
             json.dumps(sorted(int(i) for i in seen))))


def complete(conn, student_id, step_id, *, now, revision, recorded_by=""):
    """One tap: the step is done, in the family's own record. The same revision check `save`
    makes, so a step edited in another window is not closed underneath its editor."""
    cur = conn.execute(
        "UPDATE plan_steps SET state = 'done', recorded_by = ?, updated_at = ?, revision = revision + 1 "
        "WHERE student_id = ? AND id = ? AND revision = ?", (recorded_by, now, student_id, step_id, revision))
    if not cur.rowcount:
        raise Conflict("This step changed in another window. Reload the page and try again.")


def today_load(conn, student_id, today: str, exclude=frozenset()) -> tuple[int, int]:
    """(steps, minutes) the family planned for `today`: work to do and help-needed steps dated
    today. Waiting steps are on the teacher, and their date is when to look again. Steps on
    work the school now shows as handed in (`exclude`, item ids) are left out, as the plan
    page leaves them out of its total (spec 2026-09-27 §6)."""
    rows = conn.execute(
        "SELECT item_id, minutes FROM plan_steps WHERE student_id = ? AND planned_for = ? AND state IN ('planned', 'blocked')",
        (student_id, today)).fetchall()
    kept = [r for r in rows if r["item_id"] is None or r["item_id"] not in exclude]
    return len(kept), sum(r["minutes"] or 0 for r in kept)
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py tests/test_migrate.py tests/test_web_plan_steps_everywhere.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/db.py fridgesheet/web/stores/plans.py tests/test_web_checkin.py tests/test_migrate.py
git commit -m "Schema v9: a check-in records what Must finish held; one-tap complete; today's load leaves out what the school has

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The Must-finish section on the check-in and plan pages

**Files:**
- Modify: `fridgesheet/web/routes/checkin.py` (`QUEUES` constants, `_context`, a new `_witness`)
- Modify: `fridgesheet/web/app.py` (`_filters`: add `sheet_word`)
- Modify: `fridgesheet/web/verdicts.py:65` (`ANSWERS["awaiting_grade"]` gains "It's handed in")
- Create: `fridgesheet/web/templates/_must_finish.html`
- Modify: `fridgesheet/web/templates/_answers.html`
- Modify: `fridgesheet/web/templates/checkin.html`
- Modify: `fridgesheet/web/static/app.css` (append)
- Test: `tests/test_web_checkin.py`, `tests/test_web_checkin_verdicts.py`, `tests/test_open_work_parity.py`

**Interfaces:**
- Consumes: `items.must_finish`, `items.MustFinish`, `items.sheet_status` (Task 1); the phrase keys (Task 2); `plans.history` rows' `seen` (Task 3).
- Produces (context keys every later task reads):
  - `must_finish: items.MustFinish` (covered ids removed)
  - `seen: set[int]` — ids in the last check-in's `seen`, empty before the first check-in; `seen_day: str` — `wd_md` of `last_check["finished_at"]` or `""`
  - `queues` keyed by the renamed labels: `WORTH_CHECKING = "Worth checking"`, `WAITING = "Waiting on the school"`, `OTHER_OPEN = "Other open work"`; Must-finish ids appear in none of them
  - Template `_answers.html` accepts optional `exclude` (list of action strings) and `first` (an action string) from its includer.
  - Filter `sheet_word(view, tier) -> str`: `sheet.status_word(items.sheet_status(view), tier)`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_checkin.py`, update the `_queues` helper's label set and the first queue test for the renamed groups, then append the new tests:

```python
def _queues(body: str) -> dict[str, str]:
    """The review groups' HTML, by label, so a test can say which group a row is in."""
    groups = re.split(r'<details class="queue-group"', body)[1:]
    out = {}
    for g in groups:
        label = re.search(r"<summary>(.*?) <span", g)
        if label and label.group(1) in ("Other open work", "Worth checking", "Waiting on the school"):
            out[label.group(1)] = g
    return out


def test_check_in_sorts_the_school_record_into_three_review_groups(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/kids/Alex/check-in")
    assert r.status_code == 200
    q = _queues(r.text)
    assert set(q) == {"Other open work", "Worth checking", "Waiting on the school"}
    assert "Homework 4" in q["Other open work"]                     # past its window: open, not fixable
    for name in ("Vocabulary", "Worksheet 3", "Reading log", "Lab notebook", "Participation"):
        assert name not in q["Other open work"], name               # these are in Must finish now
    assert "Essay draft" in q["Waiting on the school"]
    assert "Quiz 1" not in r.text.split('id="plan"')[0]             # HAC's 28/30 settles it (docs/outcomes.md)


def _section(body: str, key: str) -> str:
    """The HTML of one Must-finish section, by its data-section key."""
    m = re.search(rf'<div class="mf-section" data-section="{key}">(.*?)</div><!-- /{key} -->', body, re.S)
    return m.group(1) if m else ""


def test_must_finish_opens_the_plan_with_the_school_list_in_sections(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    assert body.index('id="must-finish"') < body.index('id="plan"')
    assert "Vocabulary" in _section(body, "tonight") and "DUE TODAY" in _section(body, "tonight")
    assert "Worksheet 3" in _section(body, "tomorrow")
    assert "Reading log" in _section(body, "later")
    paper = _section(body, "paper")
    assert "Lab notebook" in paper and "Participation" in paper
    assert "The school's list as of" in body


def test_a_must_finish_row_never_offers_too_late_or_let_it_go(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/kids/Sam/plan").text
    overdue = _section(body, "overdue")
    assert "Cell diagram" in overdue and "Safety quiz" in overdue
    assert 'value="too_late"' not in overdue and 'value="ignore"' not in overdue
    assert 'value="done"' in overdue and 'value="plan:today"' in overdue
    # The verdict table itself still carries them: the row filtered, the answers did not change.
    from fridgesheet.web import verdicts as V
    assert any(a.action == "too_late" for a in V.ANSWERS["not_done"])


def test_a_paper_row_puts_handed_in_first(tmp_path):
    seed(tmp_path).close()
    paper = _section(app_for(tmp_path).get("/kids/Alex/plan").text, "paper")
    lab = paper[paper.index("Lab notebook"):]
    assert lab.index('value="done"') < lab.index('value="ask_teacher"')
    assert re.search(r'<button name="answer" value="done" class="primary"', lab)


def test_a_zero_on_handed_in_work_keeps_ask_the_teacher_first(tmp_path):
    """Review Focus 2: finishing first must not mean tapping away a wrong zero."""
    snap = snapshot()
    sci = snap["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci["assignments"]:
        if a["name"] == "Safety quiz":
            a.update(state="submitted", submitted_at="2026-09-10T20:00:00-04:00", score=None, grade=None)
    snap["students"]["Sam"]["hac"]["classes"][0]["assignments"] = [_h("Safety quiz", "09/11/2026", 0.0)]
    seed(tmp_path, snap).close()
    overdue = _section(app_for(tmp_path).get("/kids/Sam/plan").text, "overdue")
    quiz = overdue[overdue.index("Safety quiz"):]
    assert "Zero to check" in quiz
    assert re.search(r'<button name="answer" value="ask_teacher" class="primary"', quiz)
    assert 'value="ignore"' not in quiz and 'value="done" class="primary"' not in quiz


def test_a_must_finish_item_is_in_no_review_group(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    q = _queues(body)
    for name in ("Lab notebook", "Participation"):                  # paper with no grade used to be a question or waiting
        assert name in _section(body, "paper")
        assert all(name not in g for g in q.values()), name


def test_the_must_finish_ids_are_open_works_rows_minus_the_plan(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", planned_for="2026-09-15"), item_id=vid)
    body = c.get("/kids/Alex/plan").text
    ids = set(re.findall(r'id="mf-(\d+)"', body))
    assert str(vid) not in ids and len(ids) == 4                    # Worksheet 3, Reading log, Lab notebook, Participation
```

Append to `tests/test_open_work_parity.py`:

```python
def test_must_finish_is_open_works_rows_minus_covered(tmp_path):
    """Spec 2026-09-27 §4.1: the plan's list is exactly `fixable + upcoming`, less the plan."""
    from fridgesheet.web.stores import plans
    from uuid import uuid4
    conn = seed(tmp_path)
    page = _page(conn, NOW)
    for key, w in page.items():
        mf = items.must_finish(w, NOW.date())
        assert mf.ids == {v.id for v in w.fixable + w.upcoming}, key
    alex = students.by_key(conn, "Alex")
    vocab = next(v for v in page["Alex"].upcoming if v.name == "Vocabulary")
    values = dict(title="Vocabulary", family_account="", next_step="Do it", owner="Alex", planned_for="2026-09-15",
                  minutes=None, state="planned", position=10, evidence="{}", recorded_by="")
    plans.save(conn, alex["id"], values, now=NOW.isoformat(), request_key=str(uuid4()), item_id=vocab.id)
    covered = {s["item_id"] for s in plans.for_student(conn, alex["id"]) if s["state"] != "done"}
    mf = items.must_finish(page["Alex"], NOW.date(), covered)
    assert mf.ids == {v.id for v in page["Alex"].fixable + page["Alex"].upcoming} - {vocab.id}
    conn.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py tests/test_open_work_parity.py -k "must_finish or review_groups or paper_row or zero_on or too_late or no_review" -v`
Expected: FAIL (no `id="must-finish"`; the queue labels are still "Questions"/"To do")

- [ ] **Step 3: The route: renamed groups, Must finish, seen, answers filter**

In `fridgesheet/web/routes/checkin.py`:

Replace the constants block:

```python
#: The review groups under the plan (spec 2026-09-27 §7). "Worth checking" is what the
#: verdicts call a question; "Waiting on the school" is not the plan's "Waiting" state, which
#: is our own step on hold; "Other open work" is open work Must finish does not list (past
#: its window, undated and untouched, upcoming with no Canvas row).
WORTH_CHECKING, WAITING, OTHER_OPEN = "Worth checking", "Waiting on the school", "Other open work"
QUEUES = (WORTH_CHECKING, WAITING, OTHER_OPEN)
#: A question kind that opens Worth checking by itself: a zero the school may have wrong, an
#: answer it contradicted, or a question that was asked and has since been graded (§7).
OPENS_WORTH_CHECKING = frozenset(("submitted_hac_zero", "excused_hac_zero", "hac_lower", "stale_answer",
                                  "asked_then_graded", "followed_up_then_graded"))
```

Update `_group` and `queue_for` to return the new names (`TO_DO` → `OTHER_OPEN`, `QUESTIONS` → `WORTH_CHECKING`), and give `queue_for` a third parameter:

```python
def queue_for(v, covered: set[int], listed: set[int] = frozenset()) -> str | None:
    """The review group for one item at a check-in, or None to leave it out. Work Must finish
    lists (`listed`) is in one place only (§5); a question is something to clarify together;
    waiting on the teacher is its own group; work with an agreed step is already in the plan;
    handled work stays out unless the school has since contradicted the answer."""
    if v.id in covered or v.id in listed:
        return None
    if v.handled:
        return WORTH_CHECKING if v.verdict.kind == "stale_answer" else None
    if v.verdict.state == "question":
        return WORTH_CHECKING
    if v.verdict.state == "waiting":
        return WAITING
    return _group(v)
```

In `_context`, after `covered` is computed and before the queues loop, build the list, and pass `listed` to `queue_for`:

```python
    work = items.open_work(conn, student, now=now, rules=rules, prefs=state.sources(), **state.window())
    must = items.must_finish(work, now.date(), covered)
    seen = set(json.loads(last_check["seen"])) if last_check else set()
    seen_day = dates.wd_md(datetime.fromisoformat(last_check["finished_at"]).astimezone(state.tz)) if last_check else ""
    queues = {label: [] for label in QUEUES}
    for v in views:
        group = queue_for(v, covered, must.ids)
        if group:
            queues[group].append(v)
    worth_open = any(v.verdict.kind in OPENS_WORTH_CHECKING for v in queues[WORTH_CHECKING])
    latest = refreshes.latest(conn)
    data_as_of = latest["started_at"] if latest else None
```

and add to the returned dict: `must_finish=must, seen=seen, seen_day=seen_day, worth_open=worth_open, data_as_of=data_as_of, asked=[]` (Task 5 fills `asked`). Import `json`, `dates` from `...`, and `refreshes` from `..stores`. Keep `waiting_group=WAITING` and add `worth_group=WORTH_CHECKING`.

In `fridgesheet/web/app.py` `_filters`, add beside `phrase`:

```python
    def sheet_word(view, tier: str = "") -> str:
        """The sheet's word for a row, in the kid's tier: DUE TONIGHT, MISSING, or "Teacher
        hasn't got it" (sheet.status_word)."""
        from .stores import items as items_store
        return sheet.status_word(items_store.sheet_status(view), tier)
```

and register it in the returned dict as `"sheet_word": sheet_word`. Add `from .. import sheet` (the `fridgesheet.sheet` module) to the imports if absent.

Rewrite `fridgesheet/web/templates/_answers.html` so an includer can drop or promote actions:

```jinja
{# A verdict's answer buttons, swapping the element `qid` names (set by the includer). Shared by the
   question card, the check-in's review cards and the Must-finish rows, so all offer the same answers.
   Every button is a one-tap POST; a plan action creates a step with defaults (spec 6.3). One request
   key per card, so a double-click or a retried POST lands on one step. Work that already has an
   active step is not offered a second one-tap plan: the item detail's "Plan another step" link is
   the way to that. The first answer is the filled default, except on a waiting card: its own
   sentence says time will settle it (kids' UX audit F9).
   `exclude` (a list of actions) drops answers -- Must finish drops the two handled flags that would
   dismiss a row (spec 2026-09-27 §4.4); `first` (an action) moves one to the front. #}
  {% set token = request_key() %}
  {% set drop = exclude if exclude is defined and exclude else [] %}
  {% set answers = vd.answers | rejectattr('action', 'in', drop) | list %}
  {% if first is defined and first %}{% set answers = (answers | selectattr('action', 'equalto', first) | list) + (answers | rejectattr('action', 'equalto', first) | list) %}{% endif %}
  <div class="answers">
    {% for a in answers if not (a.action.startswith('plan:') and item.step) %}<form hx-post="/items/{{ item.id }}/answer" hx-target="#{{ qid }}" hx-swap="outerHTML"><input type="hidden" name="prev" value="{{ item.flag or '' }}"><input type="hidden" name="prev_set_at" value="{{ item.flag_set_at or '' }}"><input type="hidden" name="slot" value="{{ qid }}"><input type="hidden" name="request_key" value="{{ token }}"><button name="answer" value="{{ a.action }}" class="{{ 'primary' if loop.first and (vd.state != 'waiting' or (first is defined and first)) }}">{{ a.key | say(tier) }}</button></form>{% endfor %}
  </div>
```

(An includer that names a `first` action wants it filled even on a waiting verdict: the paper group's "It's handed in".)

Note `questions.py:_SLOT` accepts `q-`, `qd-`, `qc-` slots; Must-finish rows use `qc-<id>` too, so the answer route swaps the row and the check-in card alike.

Create `fridgesheet/web/templates/_must_finish.html`:

```jinja
{# Must finish (spec 2026-09-27 §4): Open work's rows, sectioned for tonight. Computed from the
   school record every time, never stored; a row leaves when the record says the work is in or
   the family answers "It's handed in". Its own section, outside #plan, so the out-of-band swap
   after an answer cannot replace the row a done-line and its Undo sit in (§12). #}
{% set tier = student.key | tier_of %}
<section id="must-finish" class="must-finish" aria-labelledby="mf-heading">
  <div class="workspace-heading"><h3 id="mf-heading">{{ 'copy.must_finish' | say(tier) }}</h3>{% if jobs %}<button type="button" hx-post="/jobs/refresh" hx-vals='{"reload_page": "1"}' hx-target="#job" hx-swap="outerHTML">{{ 'copy.check_again' | say(tier) }}</button>{% endif %}</div>
  <p class="muted">{{ 'copy.must_finish_hint' | say(tier) }}{% if data_as_of %} {{ 'copy.list_as_of' | say(tier, {'when': data_as_of | wd_md_time}) }}{% endif %}</p>
  {% if job %}{% with busy=false %}{% include "_job.html" %}{% endwith %}{% else %}<div id="job"></div>{% endif %}
  {# One loop over the six sections, no macro: a Jinja macro cannot see the template's own
     `{% set %}` variables (`tier`), and `_answers.html` is included per row with `item`, `qid`,
     `vd`, `exclude` and `first` set in this scope. Each tuple: key, heading phrase, rows, red,
     grey, the action to put first (or none), and whether the section folds. #}
  {% set sections = [
    ('tonight',  'copy.due_tonight',       must_finish.tonight,  true,  false, none,   false),
    ('tomorrow', 'copy.due_tomorrow',      must_finish.tomorrow, true,  false, none,   false),
    ('overdue',  'copy.overdue_fixable',   must_finish.overdue,  true,  false, none,   false),
    ('paper',    'copy.on_paper_no_grade', must_finish.paper,    false, false, 'done', false),
    ('waiting',  'copy.handed_in_waiting', must_finish.waiting,  false, true,  none,   true),
    ('later',    'copy.coming_due_later',  must_finish.later,    false, false, none,   true),
  ] %}
  {% set exclude = ['too_late', 'ignore'] %}
  {% for key, label, rows, red, grey, first, fold in sections if rows %}
  {% if fold %}<details class="mf-fold"><summary>{{ label | say(tier) }} <span class="badge">{{ rows | length }}</span></summary>{% endif %}
  <div class="mf-section" data-section="{{ key }}">{% if not fold %}<h4>{{ label | say(tier) }}</h4>{% endif %}
    {% for view in rows %}{% set qid = 'qc-' ~ view.id %}{% set item = view %}{% set vd = view.verdict %}
    {% if key == 'paper' %}{% set pk = vd | pace_key %}{% if pk and loop.changed(view.course_id) %}<p class="mf-paper">{{ pk | say(tier, vd.pace) }}</p>{% endif %}{% endif %}
    <div class="mf-row{{ ' red' if red }}{{ ' grey' if grey }}" id="mf-{{ view.id }}">
      <p class="line"><span class="eyebrow">{{ view.course_short }}</span><span class="word">{{ view | sheet_word(tier) }}</span>{% if view.due and not (view.upcoming and not view.overdue) %}<span class="muted">due {{ view.due | wd_md }}</span>{% elif view.due_time %}<span class="muted">{{ view.due_time }}</span>{% endif %}
        {% if vd.kind in ('submitted_hac_zero', 'excused_hac_zero', 'hac_lower') %}<span class="badge">{{ 'badge.zero_to_check' | say(tier) }}</span>{% elif vd.kind == 'stale_answer' %}<span class="badge">{{ 'badge.changed_since_answer' | say(tier) }}</span>{% endif %}
        {% if seen_day %}<span class="badge">{{ ('badge.seen_at_checkin' if view.id in seen else 'badge.new_since_checkin') | say(tier, {'day': seen_day}) }}</span>{% endif %}</p>
      <a href="/kids/{{ student.key | urlencode }}?show=all#row-{{ view.id }}"><strong>{{ view.name }}</strong></a>
      {% if vd.state == 'question' %}<p class="ask">{{ ('ask.' ~ vd.kind) | say(tier) }}</p>{% endif %}
      {% if view.open_in and view.due and view.late_until %}<p class="muted">Late work is usually accepted until {{ view.late_until | wd_md }} (from your late-work rules). Ask the teacher if you need longer.</p>{% endif %}
      <div id="{{ qid }}">{% if vd.answers and not grey %}{% include "_answers.html" %}{% endif %}</div>
      <p class="row-links"><a href="{{ base }}/step?item_id={{ view.id }}&amp;return_to={{ here | urlencode }}">{{ 'a.add_details' | say(tier) }}</a> · <details class="inline"><summary>{{ 'copy.details' | say(tier) }}</summary>{% include "_planning_evidence.html" %}</details></p>
    </div>
    {% endfor %}
  </div><!-- /{{ key }} -->
  {% if fold %}</details>{% endif %}
  {% endfor %}
  {% if not must_finish | length %}<p class="muted">{{ 'copy.nothing_due' | say(tier) }}</p>{% endif %}
</section>
```

Two things this template needs from elsewhere in this task:

- `copy.details` is a phrase (already in the Task 2 table and test list).
- A paper row with no grade inside its class's grading pace has the `awaiting_grade` verdict, whose answers today are only "Ask the teacher" (`verdicts.ANSWERS["awaiting_grade"] == (ASK,)`). The persona review that produced this design asked for "It's handed in" on every Must-finish row, and spec §4.4 puts it first on the paper group. In `fridgesheet/web/verdicts.py` change that entry to:

```python
    "awaiting_grade": (ASK, Answer("a.handed_in", "done")),
```

The check-in's waiting card gains a second, unfilled button ("Yes, handed in"), which is the honest offer on a paper card. Update any test that asserts `awaiting_grade` carries one answer (search `tests/test_verdicts.py` and `tests/test_web_checkin_verdicts.py` for `awaiting_grade`; the two hits at the time of writing assert only `(state, kind)`).

The `hx-vals` on the Check Canvas again button is consumed in Task 9; until then the jobs route ignores the extra field.

In `fridgesheet/web/templates/checkin.html`, restructure the body after the intro:

```jinja
<div class="checkin-layout {{ 'plan-only' if plan_only }}">
<div class="checkin-main">
{% include "_must_finish.html" %}
{% include "_plan_panel.html" %}
{% if not plan_only %}
<section class="card finish-checkin">
  … (the existing Agree and wrap up form, unchanged) …
</section>
{% endif %}
{% if asked %}<p class="asked-line"><strong>{{ 'copy.asked_the_school' | say(tier) }}:</strong> {% for v, key, when in asked %}<a href="/kids/{{ student.key | urlencode }}?show=all#row-{{ v.id }}">{{ v.name }}</a>: {{ key | say(tier, {'when': when}) }}{{ ' · ' if not loop.last }}{% endfor %}</p>{% endif %}
<section class="review-queue" aria-labelledby="review-heading">
  <h3 id="review-heading" class="sr-only">Review</h3>
  {% for label, rows in queues.items() %}
  <details class="queue-group" {{ 'open' if (label == worth_group and worth_open) }}>
    <summary>{{ label }} <span class="badge">{{ rows | length }}</span></summary>
    {% if label == worth_group %}<p class="muted">{{ 'copy.queue_hint' | say(tier) }}</p>{% endif %}
    <div class="review-grid">
    … (the existing review-card loop, unchanged) …
    </div>
  </details>
  {% endfor %}
  <p><a href="/kids/{{ student.key | urlencode }}?show=all">Browse all work</a> to plan something outside this list.</p>
  {% include "_sources_hint.html" %}
</section>
</div>
</div>
{% if not plan_only %}<nav class="halves" aria-label="Check-in sections"><a href="#must-finish">{{ 'copy.must_finish' | say(tier) }} <span class="badge">{{ must_finish | length }}</span></a><a href="#plan">Next steps <span class="badge">{{ steps | length }}</span></a></nav>{% endif %}
```

The `asked` context key is produced in Task 5; until then pass `asked=[]` from `_context`. Remove the `checkin-side` wrapper: the plan is no longer a sticky side column (the mockup showed it capping the page at one viewport). Delete the `.checkin-layout { grid-template-columns: … 1.4fr … 1fr }` two-column rule's effect by changing it to a single column with `max-width: var(--measure)`:

```css
.checkin-layout { display: grid; grid-template-columns: minmax(0, 1fr); max-width: 960px; gap: 24px; align-items: start; }
```

Append to `app.css`:

```css
/* Must finish (spec 2026-09-27 §4): the school's list, sectioned for tonight. Red is only for
   rows the school records as not in; paper with no grade is not red; a hand-in waiting for a
   grade is grey. */
.must-finish { margin: 0 0 24px; }
.must-finish h4 { margin: 18px 0 6px; font-size: 15px; }
.mf-row { border: 1px solid var(--rule); border-left: 4px solid var(--rule); border-radius: 8px; padding: 10px 14px; margin: 8px 0; background: var(--paper); overflow-wrap: anywhere; }
.mf-row.red { border-left-color: var(--warn); }
.mf-row.grey { color: var(--muted); }
.mf-row .line { display: flex; flex-wrap: wrap; gap: 6px 12px; align-items: baseline; margin: 0 0 6px; }
.mf-row .line .eyebrow { margin: 0; }
.mf-row .line .word { font-weight: 700; }
.mf-row.red .line .word { color: var(--warn); }
.mf-row .answers { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 6px; }
.mf-row .answers form { display: inline; margin: 0; }
.mf-row .ask { font-weight: 600; margin: 4px 0 6px; }
.mf-row .row-links { margin: 6px 0 0; font-size: var(--type-small); }
.mf-paper { border-left: 3px solid #a2bdb3; padding-left: 10px; margin: 6px 0 10px; color: #4f5754; font-size: var(--type-small); }
details.mf-fold > summary { padding: 8px 0; cursor: pointer; font-weight: 600; }
.asked-line { margin: 16px 0 0; }
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py tests/test_web_checkin_verdicts.py tests/test_checkin_queue.py tests/test_open_work_parity.py tests/test_web_questions.py tests/test_web_tier_parity.py tests/test_web_a11y.py -v`
Expected: the new tests PASS. Existing tests that named "Questions" / "To do" / `1 step without an estimate` fail: update `tests/test_checkin_queue.py` assertions to `"Worth checking"` and `"Other open work"`, and any test in `test_web_checkin.py` / `test_web_checkin_verdicts.py` / `test_web_questions.py` asserting the old group names, so they assert the new ones. Do not change what those tests check about rows.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/checkin.py fridgesheet/web/app.py fridgesheet/web/verdicts.py fridgesheet/web/phrasing.py fridgesheet/web/templates/_must_finish.html fridgesheet/web/templates/_answers.html fridgesheet/web/templates/checkin.html fridgesheet/web/static/app.css tests/
git commit -m "The plan opens with Must finish: the school's list in six sections, one item in one place (spec 2026-09-27 §4-§5, §7)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Family steps the school shows as in; the total sentence; asked lines

**Files:**
- Modify: `fridgesheet/web/routes/checkin.py` (`_witness`, `_context`, a `complete` route)
- Modify: `fridgesheet/web/templates/_plan_panel.html`
- Modify: `fridgesheet/web/static/app.css` (append)
- Test: `tests/test_web_checkin.py`, `tests/test_web_questions.py`

**Interfaces:**
- Consumes: `plans.complete`, `plans.today_load(exclude)` (Task 3); `phrase keys record.*`, `copy.tonight_*`, `badge.must_finish`, `a.mark_step_complete` (Task 2); `must_finish`, `seen` (Task 4).
- Produces:
  - `checkin.witness(view, tz) -> tuple[str, dict] | None`: a phrase key and its values, or None (spec §6 table).
  - `checkin.school_has_ids(conn, student, state) -> set[int]`: item ids of active steps with a witness; the dashboard reads it (Task 7).
  - Context: each active `step` gains `step["witness"]` (`(key, values)` or None) and `step["must_word"]` (the sheet's word when the item is in `open_work.fixable + upcoming`, else `""`); `total_minutes` and `today_steps` exclude witnessed steps; `unpicked = len(must_finish.unpicked)`; `school_has_n`; `asked: list[(view, key, when)]`.
  - Route `POST /kids/{key}/check-in/step/{step_id}/complete` with form fields `revision`, `recorded_by` (optional), `return_to` (optional); 303 to `_after_save`; 409 re-rendering the page with the conflict message.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_checkin.py`:

```python
def _plan_step_for(c, conn, key, name, **over):
    iid = _item_id(conn, name)
    _post_step(c, key, _form(title=name, planned_for="2026-09-15", **over), item_id=iid)
    return iid


def test_a_step_the_school_shows_as_in_is_greyed_with_canvas_as_the_witness(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Essay draft", minutes="20")          # submitted 9/14 8 pm
    _plan_step_for(c, conn, "Alex", "Vocabulary", minutes="15")           # not handed in
    conn.close()
    body = c.get("/kids/Alex/plan").text
    panel = body[body.index('id="plan"'):]
    assert "The school has it" in panel
    assert "Canvas: handed in Sun 9/14 8:00 PM" in panel
    assert "Mark step complete" in panel
    assert "Tonight: 1 step, 15 min" in panel and "1 the school has, not counted" in panel
    assert "3 must-finish not picked yet" in panel                         # Worksheet 3, Lab notebook, Participation; Vocabulary is covered


def test_the_familys_own_done_answer_is_named_as_theirs(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    vid = _plan_step_for(c, conn, "Alex", "Vocabulary")
    flags.set_flag(conn, vid, "done", now="2026-09-15T13:00:00-04:00")
    conn.close()
    panel = c.get("/kids/Alex/plan").text.split('id="plan"')[1]
    assert "You answered It's handed in, Tue 9/15" in panel
    assert "Canvas: handed in" not in panel and "school says" not in panel.lower()


def test_a_stale_answer_ungreys_the_step(tmp_path):
    """Review Focus 3: the school contradicted the family's `done`; the step is live again."""
    from tests.web_fixtures import history
    conn = history(tmp_path)                                                # Quiz 1: HAC 28/30 day 2, Canvas MISSING day 3
    c = app_for(tmp_path)
    qid = _plan_step_for(c, conn, "Alex", "Quiz 1", minutes="10")
    flags.set_flag(conn, qid, "done", now="2026-09-14T09:00:00-04:00")      # answered before day 3's mark
    conn.close()
    panel = c.get("/kids/Alex/plan").text.split('id="plan"')[1]
    assert "The school has it" not in panel
    assert "Tonight: 1 step, 10 min" in panel


def test_mark_step_complete_is_one_post_with_the_revision(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Essay draft")
    (step,) = _step_rows(tmp_path)
    conn.close()
    r = c.post(f"/kids/Alex/check-in/step/{step['id']}/complete", data={"revision": "1", "recorded_by": "Mom"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"
    (step,) = _step_rows(tmp_path)
    assert (step["state"], step["revision"], step["recorded_by"]) == ("done", 2, "Mom")
    r = c.post(f"/kids/Alex/check-in/step/{step['id']}/complete", data={"revision": "1"})
    assert r.status_code == 409 and "changed in another window" in r.text


def test_a_covered_step_carries_the_sheets_word(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Worksheet 3")
    conn.close()
    panel = c.get("/kids/Alex/plan").text.split('id="plan"')[1]
    assert "Must finish · DUE TOMORROW" in panel


def test_asked_the_school_lines_sit_above_worth_checking(tmp_path):
    conn = seed(tmp_path)
    lab = _item_id(conn, "Lab notebook")
    flags.set_flag(conn, lab, "ask_teacher", now="2026-09-13T09:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    assert "Asked the school" in body and "Lab notebook</a>: Asked the teacher on Sun 9/13" in body
    assert body.index("Asked the school") < body.index("Worth checking")
```

Append to `tests/test_web_questions.py`:

```python
def test_the_plan_panel_after_an_answer_says_tonight_in_one_sentence(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    body = _plan(c, vid).text
    assert "Tonight: 1 step, 0 min" in body and "without an estimate" not in body
```

and change the existing `test_the_response_carries_the_plan_panel_out_of_band` assertion `"1 step without an estimate" in section.group(0)` to `"Tonight: 1 step, 0 min" in section.group(0)`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py -k "school_shows or own_done or stale_answer_ungreys or mark_step or sheets_word or asked_the_school" tests/test_web_questions.py -k tonight -v`
Expected: FAIL (`The school has it` absent; 404 on the complete route; `Tonight:` absent)

- [ ] **Step 3: The witness, the totals, the route**

In `fridgesheet/web/routes/checkin.py`, add above `_context`:

```python
def witness(view, tz) -> tuple[str, dict] | None:
    """Who says this assignment is in, or None (spec 2026-09-27 §6). Canvas, HAC or the
    family, by name; never "the school" for the family's own answer. A stale answer -- the
    school contradicted the family -- is nobody's witness: the step stays live."""
    if view is None or view.verdict.kind == "stale_answer":
        return None
    c = view.canvas
    if c is not None and c["submitted_at"]:
        return "record.canvas_handed_in", {"when": dates.wd_md_time(datetime.fromisoformat(c["submitted_at"]).astimezone(tz))}
    if view.outcome == outcomes.DONE_OFFLINE:
        return "record.graded_in", {"source": "HAC" if view.grade_source == "hac" else "Canvas", "score": view.grade}
    if view.flag == "done":
        return "record.you_said_handed_in", {"when": dates.wd_md(datetime.fromisoformat(view.flag_set_at).astimezone(tz))}
    if view.flag == "excused":
        return "record.you_said_excused", {"when": dates.wd_md(datetime.fromisoformat(view.flag_set_at).astimezone(tz))}
    if c is not None and c["excused"]:
        return "record.canvas_excused", {}
    return None


def school_has_ids(conn, student, state) -> set[int]:
    """Item ids of this kid's active steps whose assignment the school shows as in: what
    the dashboard leaves out of "N steps planned today" (§8.3)."""
    steps = [s for s in plans.for_student(conn, student["id"]) if s["state"] != "done" and s["item_id"] is not None]
    if not steps:
        return set()
    views = {v.id: v for v in items.list_items(conn, student, now=state.now(), rules=state.rules(), show="all",
                                                prefs=state.sources(), **state.window())}
    return {s["item_id"] for s in steps if witness(views.get(s["item_id"]), state.tz) is not None}
```

In `_context`, in the `for step in steps:` loop add:

```python
        step["witness"] = witness(view, state.tz) if step["state"] != "done" else None
        step["must_word"] = ""
```

After `must` is built (Task 4), mark covered steps with the sheet's word and compute the asked lines:

```python
    listed = {v.id: v for v in work.fixable + work.upcoming}
    for step in steps:
        if step["item_id"] in listed and step["state"] != "done":
            step["must_word"] = items.sheet_status(listed[step["item_id"]])
    asked = [(v, "where.asked" if v.flag == "ask_teacher" else "where.following_up",
              dates.wd_md(datetime.fromisoformat(v.flag_set_at).astimezone(state.tz)))
             for v in views if v.flag in ("ask_teacher", "follow_up") and v.id not in covered]
```

Change `today_steps` and the totals:

```python
    today_steps = [s for s in active if s["state"] in ("planned", "blocked") and s["planned_for"] == today and not s["witness"]]
    total = sum(s["minutes"] or 0 for s in today_steps)
    school_has_n = sum(1 for s in active if s["witness"])
```

and add to the returned dict: `today_steps_n=len(today_steps), unpicked=len(must.unpicked), school_has_n=school_has_n, asked=asked`. Remove `unestimated` from the dict and the template.

Add the route after `delete_step`:

```python
@router.post("/kids/{key}/check-in/step/{step_id}/complete")
async def complete_step(key: str, step_id: int, request: Request, conn=Db, state=State):
    """One tap on a step the school shows as in (spec 2026-09-27 §6). The family's own record,
    with the same revision check the form makes; the app never completes a step itself."""
    student = student_or_404(conn, key)
    form = await request.form()
    revision = str(form.get("revision", ""))
    return_to = safe_return(str(form.get("return_to", "")))
    try:
        if not revision.isdigit():
            raise plans.Conflict("Reload this page before completing the step.")
        plans.complete(conn, student["id"], step_id, now=state.now().isoformat(), revision=int(revision),
                       recorded_by=str(form.get("recorded_by", "")).strip()[:100])
    except plans.Conflict as exc:
        ctx = _context(conn, student, state)
        ctx.update(error=str(exc), plan_only=request.url.path.endswith("/plan"))
        return render(request, conn, "checkin.html", status_code=409, **ctx)
    return RedirectResponse(_after_save(key, return_to), status_code=303)
```

In `fridgesheet/web/templates/_plan_panel.html`, replace the total line and the step loop:

```jinja
{% set tier = student.key | tier_of %}
<section id="plan" class="plan-panel" aria-labelledby="plan-heading"{% if oob is defined and oob %} hx-swap-oob="true"{% endif %}>
  <div class="workspace-heading"><h3 id="plan-heading">Our next steps</h3><a class="button-link" href="{{ base }}/step?return_to={{ here | urlencode }}">Add a task</a></div>
  <p class="plan-total"><strong>{{ 'copy.tonight_steps' | say(tier, {'steps': today_steps_n, 's': '' if today_steps_n == 1 else 's', 'minutes': total_minutes}) }}</strong>{% if unpicked %} · {{ 'copy.tonight_unpicked' | say(tier, {'n': unpicked}) }}{% endif %}{% if school_has_n %} · {{ 'copy.tonight_school_has' | say(tier, {'n': school_has_n}) }}{% endif %}</p>
  {% if last_check %}<p class="muted">Last agreed time budget: {{ last_check.available_minutes }} min{% if not budget_today %} (agreed {{ last_check.finished_at | wd_md }}, for that day){% endif %}{% if over > 0 %} · <strong class="warn">{{ total_minutes }} min planned today, {{ last_check.available_minutes }} min available: {{ over }} min over. Move a step to another day.</strong>{% endif %}</p>{% endif %}
  {% for label in ('planned', 'blocked', 'waiting') %}
  <h4>{{ states[label] }}</h4>
  {% for step in steps if step.state == label and not step.witness %}
  <article class="card plan-card">
    {% if step.view %}<p class="eyebrow">{{ step.view.course_short }}{% if step.must_word %} · <span class="badge">{{ 'badge.must_finish' | say(tier, {'word': step.must_word}) }}</span>{% endif %}</p>{% endif %}
    … (the rest of the card exactly as it is today) …
  </article>
  {% else %}<p class="muted">No steps here yet.</p>{% endfor %}
  {% endfor %}
  {% if school_has_n %}
  <h4>{{ 'copy.school_has_it' | say(tier) }}</h4>
  {% for step in steps if step.witness %}
  <article class="card plan-card school-has-it">
    {% if step.view %}<p class="eyebrow">{{ step.view.course_short }}</p>{% endif %}
    <h4>{{ step.title }}</h4><p class="next-step">{{ step.next_step }}</p>
    <p><strong>{{ step.owner }}</strong> · Planned for {{ step.planned_for | wd_md }}{% if step.minutes %} · {{ step.minutes }} min{% endif %}</p>
    <p class="witness">{{ step.witness[0] | say(tier, step.witness[1]) }}</p>
    <form method="post" action="{{ base }}/step/{{ step.id }}/complete" class="answers"><input type="hidden" name="revision" value="{{ step.revision }}"><input type="hidden" name="return_to" value="{{ here }}"><button>{{ 'a.mark_step_complete' | say(tier) }}</button> <a href="{{ base }}/step?step_id={{ step.id }}&amp;return_to={{ here | urlencode }}">Edit</a></form>
  </article>
  {% endfor %}
  {% endif %}
  <details class="queue-group"><summary>Completed steps <span class="badge">{{ completed | length }}</span></summary>
    … (unchanged) …
  </details>
</section>
```

Append to `app.css`:

```css
.plan-card.school-has-it { opacity: .75; background: #f4f6f4; }
.plan-card.school-has-it > h4 { text-decoration: line-through; text-decoration-thickness: 1px; }
.witness { border-left: 3px solid #6e8f85; padding-left: 10px; margin: 6px 0; }
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py tests/test_web_questions.py tests/test_web_plan_steps_everywhere.py tests/test_web_checkin_verdicts.py -v`
Expected: all PASS (fix any existing assertion on `min estimated for today` to the new sentence)

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/checkin.py fridgesheet/web/templates/_plan_panel.html fridgesheet/web/static/app.css tests/
git commit -m "A step the school shows as in is greyed with its witness named, one tap to complete; the total is one sentence; asked-the-school lines (spec 2026-09-27 §6-§8)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The check-in snapshot records what Must finish held

**Files:**
- Modify: `fridgesheet/web/routes/checkin.py` (`finish`)
- Test: `tests/test_web_checkin.py`

**Interfaces:**
- Consumes: `plans.finish(seen=)` (Task 3); `_context`'s `must_finish` (Task 4); the `seen`/`seen_day` badges in `_must_finish.html` (Task 4).
- Produces: nothing new; the route passes `seen=list(must_finish.ids)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_checkin.py`:

```python
def test_finishing_a_check_in_snapshots_the_must_finish_ids_and_rows_badge_against_it(tmp_path):
    conn = seed(tmp_path)
    vid, wid = _item_id(conn, "Vocabulary"), _item_id(conn, "Worksheet 3")
    conn.close()
    c = app_for(tmp_path)
    assert "'s list" not in c.get("/kids/Alex/plan").text                       # no check-in yet: no badge
    r = c.post("/kids/Alex/check-in/finish", data=_finish(), follow_redirects=False)
    assert r.status_code == 303
    conn = db.open_db(tmp_path)
    seen = json.loads(plans.last_checkin(conn, 1)["seen"])
    conn.close()
    assert vid in seen and wid in seen
    body = c.get("/kids/Alex/plan").text
    assert body.count("On Tue 9/15's list") == 5                                  # Vocabulary, Worksheet 3, Reading log, Lab notebook, Participation
    assert "New since Tue 9/15" not in body


def test_a_row_that_appears_after_the_check_in_is_new_since(tmp_path):
    """Review Focus 4: an empty list at finish means nothing is "on the list" later."""
    snap = snapshot()
    snap["students"]["Kim"] = {"name": "Kim Example", "canvas_id": 3, "hac_name": "Kim Example",
                               "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    conn = seed(tmp_path, snap)
    conn.close()
    c = app_for(tmp_path)
    c.post("/kids/Kim/check-in/finish", data=_finish(), follow_redirects=False)
    conn = db.open_db(tmp_path)
    kim = conn.execute("SELECT id FROM students WHERE key = 'Kim'").fetchone()["id"]
    assert plans.last_checkin(conn, kim)["seen"] == "[]"
    conn.close()
    later = snapshot()
    later["students"]["Kim"] = {"name": "Kim Example", "canvas_id": 3, "hac_name": "Kim Example",
                                "canvas": {"courses": [{"id": 9, "name": "Art 6 S1-2027-Ng", "course_code": "ART6",
                                    "grade": {"current_score": None, "final_score": None, "current_grade": None, "hidden": False},
                                    "staff": [], "assignments": [_a(300, "Sketchbook", "09-16")]}]},
                                "hac": {"week_view": [], "classes": []}}
    conn = db.open_db(tmp_path)
    ingest.record(conn, later, tz=TZ, now=NOW + timedelta(hours=1))
    conn.close()
    body = c.get("/kids/Kim/plan").text
    assert "Sketchbook" in body and "New since Tue 9/15" in body and "'s list" not in body
```

Add `import json` and `from tests.web_fixtures import _a` to the file's imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py -k "snapshots_the_must or new_since" -v`
Expected: FAIL (`seen` is `[]` after finishing)

- [ ] **Step 3: Pass `seen` from the route**

In `finish` in `checkin.py`, compute the list before saving:

```python
        seen = _context(conn, student, state)["must_finish"].ids
        plans.finish(conn, student["id"], now=state.now().isoformat(), next_check=next_check,
                     available_minutes=available, summary=summary, request_key=token, recorded_by=recorded_by,
                     seen=seen)
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/checkin.py tests/test_web_checkin.py
git commit -m "Finishing a check-in records what Must finish held, so a row can say it was seen (spec 2026-09-27 §8.2)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: The dashboard headline

**Files:**
- Modify: `fridgesheet/web/routes/dashboard.py`
- Modify: `fridgesheet/web/templates/dashboard.html:13-18`
- Test: `tests/test_web_pages.py`, `tests/test_web_open_today.py`

**Interfaces:**
- Consumes: `items.open_work`, `items.must_finish` (Task 1); `checkin.school_has_ids` (Task 5); `plans.today_load(exclude)` (Task 3); phrases `copy.nothing_due`, `copy.not_done_due_by_tomorrow` (Task 2).
- Produces: each card's third tuple gains `must_finish: int` (red rows, covered removed); the two lines "N still fixable" and "N due today · N due tomorrow" leave the card.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_pages.py`, replace the two assertions in `test_dashboard_cards_per_kid` that read `still fixable` / `due today` with:

```python
    def card(key):
        """One kid's card, by its heading; the rail names every kid before the cards do."""
        start = body.index(f'<h3><a href="/kids/{key}/check-in">')
        return body[start:body.index("</div>", start)]
    assert '<span class="big">2</span> not done, due by tomorrow' in card("Alex")   # Vocabulary tonight, Worksheet 3 tomorrow
    assert '<span class="big">2</span> not done, due by tomorrow' in card("Sam")    # Cell diagram, Safety quiz
    assert 'href="/kids/Alex/plan"><span class="big">' in card("Alex")
    assert "still fixable" not in body and "due today" not in body
```

Append:

```python
def _card(body: str, key: str) -> str:
    start = body.index(f'<h3><a href="/kids/{key}/check-in">')
    return body[start:body.index("</div>", start)]


def test_a_kid_with_nothing_due_reads_nothing_due(tmp_path):
    from tests.web_fixtures import snapshot
    snap = snapshot()
    snap["students"]["Kim"] = {"name": "Kim Example", "canvas_id": 3, "hac_name": "Kim Example",
                               "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    seed(tmp_path, snap).close()
    assert "Nothing due by tomorrow" in _card(app_for(tmp_path).get("/").text, "Kim")


def test_the_family_line_leaves_out_a_step_the_school_has(tmp_path):
    from uuid import uuid4
    from fridgesheet.web.stores import plans
    conn = seed(tmp_path)
    essay = _item_id(conn, "Essay draft")
    values = dict(title="Essay draft", family_account="", next_step="x", owner="Alex", planned_for="2026-09-15",
                  minutes=20, state="planned", position=10, evidence="{}", recorded_by="")
    plans.save(conn, 1, values, now=NOW.isoformat(), request_key=str(uuid4()), item_id=essay)
    conn.close()
    assert "No steps planned today" in _card(app_for(tmp_path).get("/").text, "Alex")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_pages.py -k "dashboard_cards or nothing_due or family_line" -v`
Expected: FAIL

- [ ] **Step 3: The route and the card**

`fridgesheet/web/routes/dashboard.py`:

```python
from . import checkin
from ..stores import items, plans, runs, students


@router.get("/")
def dashboard(request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    today = now.date().isoformat()
    cards = []
    for s in students.visible(conn):
        school_has = checkin.school_has_ids(conn, s, state)
        steps, minutes = plans.today_load(conn, s["id"], today, exclude=school_has)
        covered = {st["item_id"] for st in plans.for_student(conn, s["id"]) if st["state"] != "done"}
        work = items.open_work(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window())
        must = items.must_finish(work, now.date(), covered)
        cards.append((s, items.dashboard_counts(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window()),
                      dict(last_check=plans.last_checkin(conn, s["id"]), steps_today=steps, minutes_today=minutes,
                           must_finish=len(must.red))))
    return render(request, conn, "dashboard.html", current="dashboard", cards=cards, today=today,
                  printed=[(row, runs.describe(row), safe_pdf(state, row["pdf_path"]) is not None)
                           for row in runs.printed_on(conn, now.date())])
```

In `dashboard.html`, replace lines 16–18 (the questions tally, the fixable tally, the due-today line) with:

```jinja
    {% set tier = s.key | tier_of %}
    <p class="tally">{% if plan.must_finish %}<a href="/kids/{{ s.key | urlencode }}/plan"><span class="big">{{ plan.must_finish }}</span> {{ 'copy.not_done_due_by_tomorrow' | say(tier) }}</a>{% else %}{{ 'copy.nothing_due' | say(tier) }}{% endif %}</p>
    <p class="tally">{% if c.questions %}<a href="/questions?kid={{ s.key | urlencode }}"><span class="big">{{ c.questions }}</span> question{{ 's' if c.questions != 1 }} to answer</a>{% else %}Nothing to answer{% endif %}</p>
    <p class="muted">{{ c.new_since_yesterday }} new since yesterday</p>
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_pages.py tests/test_web_open_today.py tests/test_print_confirm_and_empty_today.py -v`
Expected: all PASS (update any other assertion on the removed lines)

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/dashboard.py fridgesheet/web/templates/dashboard.html tests/
git commit -m "Today: one headline per kid, not done and due by tomorrow, linking to the plan (spec 2026-09-27 §8.3)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: The printed plan

**Files:**
- Modify: `fridgesheet/web/templates/plan_print.html`
- Test: `tests/test_web_checkin.py`

**Interfaces:**
- Consumes: `must_finish`, `seen`, `seen_day`, `data_as_of` (Task 4); `step.witness` (Task 5); `last_check.recorded_by`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_checkin.py`:

```python
def test_the_printed_plan_leads_with_must_finish_as_boxes_and_names_people(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Essay draft", recorded_by="Mom")
    conn.close()
    c.post("/kids/Alex/check-in/finish", data=_finish(recorded_by="Dad"), follow_redirects=False)
    body = c.get("/kids/Alex/plan/print").text
    assert body.index("Must finish") < body.index("Our next steps")
    assert "□ Vocabulary" in body and "□ Worksheet 3" in body
    assert "□ Lab notebook" not in body and "Reading log" not in body                # paper and later stay off paper
    assert "The school's list as of Tue 9/15" in body and "It changes daily" in body
    assert "On Tue 9/15's list" in body
    assert "Recorded by Dad" in body and "by Mom" in body
    assert "The school has it" in body and "Canvas: handed in" in body and "□ Essay draft" not in body
    assert "Worth checking" not in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py -k printed_plan_leads -v`
Expected: FAIL

- [ ] **Step 3: The print template**

Replace the `<article class="print-plan">` body in `plan_print.html`:

```jinja
{% set tier = student.key | tier_of %}
<article class="print-plan">
<p>Printed {{ now | wd_md_time }}</p>
{% if last_check %}<p>Next check-in: {{ last_check.next_check | wd_md }} · Last agreed time budget: {{ last_check.available_minutes }} minutes · Agreed {{ last_check.finished_at | wd_md_time }}{% if last_check.recorded_by %} · Recorded by {{ last_check.recorded_by }}{% endif %}</p>{% if last_check.summary %}<p class="family-account">{{ last_check.summary }}</p>{% endif %}{% endif %}
<h3>{{ 'copy.must_finish' | say(tier) }}</h3>
<p class="muted">{% if data_as_of %}{{ 'copy.list_as_of' | say(tier, {'when': data_as_of | wd_md_time}) }} {% endif %}It changes daily; the plan page is current.</p>
{% for label, rows in (('copy.due_tonight', must_finish.tonight), ('copy.due_tomorrow', must_finish.tomorrow), ('copy.overdue_fixable', must_finish.overdue)) if rows %}
<h4>{{ label | say(tier) }}</h4>
{% for v in rows %}<div class="print-step"><h4>□ {{ v.name }} <span class="muted">· {{ v.course_short }} · {{ v | sheet_word(tier) }}</span></h4>{% if seen_day %}<p class="muted">{{ ('badge.seen_at_checkin' if v.id in seen else 'badge.new_since_checkin') | say(tier, {'day': seen_day}) }}</p>{% endif %}</div>{% endfor %}
{% else %}<p class="muted">{{ 'copy.nothing_due' | say(tier) }}</p>{% endfor %}
<h3>Our next steps</h3>
{% for label in ('planned', 'blocked', 'waiting') %}
<h4>{{ states[label] }}</h4>
{% for step in steps if step.state == label and not step.witness %}<div class="print-step"><h4>□ {{ step.title }}{% if step.view %} <span class="muted">· {{ step.view.course_short }}</span>{% endif %}</h4><p>{{ step.next_step }}</p><p><strong>{{ step.owner }}</strong> · {{ 'Check again' if label in ('waiting', 'blocked') else 'Planned for' }} {{ step.planned_for | wd_md }}{% if step.planned_for < today %} · revisit this date{% endif %}{% if step.minutes %} · {{ step.minutes }} minutes{% endif %}{% if step.changed %} · school record changed since this step was saved{% endif %}{% if step.since == 'added' %} · added since the check-in{% elif step.since == 'edited' %} · edited since the check-in{% endif %}{% if step.created_by %} · recorded by {{ step.created_by }}{% elif step.recorded_by %} · by {{ step.recorded_by }}{% endif %}</p></div>{% else %}<p class="muted">None.</p>{% endfor %}
{% endfor %}
{% if school_has_n %}<h4>{{ 'copy.school_has_it' | say(tier) }}</h4>
{% for step in steps if step.witness %}<div class="print-step"><h4>{{ step.title }}{% if step.view %} <span class="muted">· {{ step.view.course_short }}</span>{% endif %}</h4><p class="muted">{{ step.witness[0] | say(tier, step.witness[1]) }}</p></div>{% endfor %}{% endif %}
<p class="muted">Checking off a step records your progress. Confirm hand-in separately when the school requires it.</p>
</article>
```

Note: `created_by` is set from the form's `recorded_by` on create (`plans.save` writes `created_by=values["recorded_by"]`), so "recorded by Mom" prints for a step Mom typed.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_checkin.py tests/test_web_pages.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates/plan_print.html tests/test_web_checkin.py
git commit -m "The printed plan leads with Must finish as boxes, stamped as-of, with names on the steps (spec 2026-09-27 §10)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Check Canvas again

**Files:**
- Modify: `fridgesheet/web/routes/jobs.py:29-66`
- Modify: `fridgesheet/web/templates/_job.html`
- Modify: `fridgesheet/web/static/app.js:87-107`
- Test: `tests/test_web_jobs.py`, `tests/test_web_checkin.py`

**Interfaces:**
- Consumes: the button in `_must_finish.html` (Task 4) posting `reload_page=1` to `/jobs/refresh`.
- Produces: `POST /jobs/{kind}` accepts `reload_page: bool = Form(False)` and renders `_job.html` with `reload_page`; `_job.html` puts `data-reload-page="1"` on the live `<pre>` when set; `attachSse` reloads the page on `done` when the attribute is present.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_jobs.py`:

```python
def test_a_refresh_from_the_plan_page_asks_for_a_page_reload_when_done(tmp_path):
    """The file's `_worker` helper wires a `FakeActions` worker that never touches Canvas."""
    from fastapi.testclient import TestClient
    seed(tmp_path).close()
    application, w = _worker(tmp_path)
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    r = c.post("/jobs/refresh", data={"reload_page": "1"})
    assert r.status_code == 200 and 'data-reload-page="1"' in r.text and f'data-sse="/jobs/{w.current.id}/events"' in r.text
    w.run_pending()
    assert 'data-reload-page' not in c.get(f"/jobs/{w.last.id}").text        # the finished card never reloads
    r = c.post("/jobs/refresh")
    assert r.status_code == 200 and 'data-reload-page' not in r.text          # only the plan page asks for it
    w.run_pending()


def test_a_busy_worker_answers_the_plan_page_with_the_busy_card(tmp_path):
    """Review Focus 5: the 409 card lands in #job; nothing reloads."""
    from fastapi.testclient import TestClient
    seed(tmp_path).close()
    application, w = _worker(tmp_path)
    c = TestClient(application, headers=LOCAL_HOST_HEADERS)
    assert c.post("/jobs/doctor").status_code == 200
    r = c.post("/jobs/refresh", data={"reload_page": "1"})
    assert r.status_code == 409 and 'id="job"' in r.text and "Busy" in r.text
    assert 'data-reload-page' not in r.text
    w.run_pending()
```

Append to `tests/test_web_checkin.py`:

```python
def test_the_plan_page_offers_check_canvas_again_only_with_a_worker(tmp_path):
    from fastapi.testclient import TestClient
    from fridgesheet import config
    from fridgesheet.web import app as webapp, jobs
    from tests.web_fixtures import LOCAL_HOST_HEADERS
    seed(tmp_path).close()
    without = app_for(tmp_path).get("/kids/Alex/plan").text
    assert "Check Canvas again" not in without
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    application.state.fridgesheet.jobs = jobs.Worker(application.state.fridgesheet, actions=None)
    with_worker = TestClient(application, headers=LOCAL_HOST_HEADERS).get("/kids/Alex/plan").text
    assert "Check Canvas again" in with_worker and 'hx-post="/jobs/refresh"' in with_worker and '"reload_page": "1"' in with_worker
```

(`jobs.Worker(..., actions=None)` builds a worker that would run the real actions if a job were submitted; this test only renders a page, so nothing is submitted.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_jobs.py -k "plan_page or busy_worker_answers" tests/test_web_checkin.py -k check_canvas -v`
Expected: FAIL (`data-reload-page` absent)

- [ ] **Step 3: Thread `reload_page` through**

In `fridgesheet/web/routes/jobs.py`, add the form field and pass it to both renders:

```python
@router.post("/jobs/{kind}")
def start(kind: str, request: Request, date: str | None = Form(None), report: str = Form("open-work"),
          refresh_first: bool = Form(False), run_id: int | None = Form(None), reload_page: bool = Form(False),
          conn: sqlite3.Connection = Db, state=State):
```

…and in the two `render_partial(request, conn, "_job.html", …)` calls add `reload_page=reload_page and job is not None and not busy` — concretely: the 409 branch passes `reload_page=False`; the success branch passes `reload_page=reload_page`.

In `_job.html`, the live `<pre>`:

```jinja
    <pre class="log" data-sse="/jobs/{{ job.id }}/events" data-reload="/jobs/{{ job.id }}"{% if reload_page is defined and reload_page %} data-reload-page="1"{% endif %}>{{ job.lines | join('\n') }}</pre>
```

In `app.js` `attachSse`, the `done` listener:

```js
    es.addEventListener("done", function () {
      es.close();
      // A refresh started from a kid's plan page (spec 2026-09-27 §9): the list above the
      // card is stale now, so the page reloads instead of the card.
      if (pre.dataset.reloadPage) { location.reload(); return; }
      htmx.ajax("GET", pre.dataset.reload, { target: "#job", swap: "outerHTML" });
    });
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest tests/test_web_jobs.py tests/test_web_checkin.py tests/test_web_a11y.py -v`
Expected: all PASS

- [ ] **Step 5: Docs, then commit**

- `docs/outcomes.md`, "Where each outcome shows up": add a row **Plan page, "Must finish"** — "The Open work page's rows, sectioned for tonight: due tonight, due tomorrow, overdue and still fixable (red), paper with no grade (not red), handed in and waiting for a grade (grey), coming due later (folded). Minus what the family already has a step for. Tonight-first, where the sheet is overdue-first."
- `docs/product/features/check-in-planning.md`: in "Desired outcome" add the sentence "The plan opens with *Must finish*, computed from the school record every time (the Open work rows), a family step the school now shows as handed in is greyed with its witness named, and the check-in records which Must-finish items it saw." Add the spec to Evidence.
- `docs/user-guide.md`: in the plan page section, describe Must finish, the greyed steps, Worth checking, and Check Canvas again in three short paragraphs.

```bash
git add fridgesheet/web/routes/jobs.py fridgesheet/web/templates/_job.html fridgesheet/web/static/app.js docs/ tests/
git commit -m "Check Canvas again from the plan page; the page reloads when the refresh is done (spec 2026-09-27 §9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 6: Run the whole suite once**

Run: `env -u PYTHONPATH .venv/bin/python -m pytest -q 2>&1 | tee /tmp/plan-fills-itself-suite.log | tail -5`
Expected: all PASS. Fix anything the earlier tasks' targeted runs missed before moving to the kid-mode plan.

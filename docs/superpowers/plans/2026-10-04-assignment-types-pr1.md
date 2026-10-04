# Assignment Types, PR 1 (foundation, labels, filter) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every item gets one of four families (tests & quizzes, everyday work, labs & projects, participation), inferred at read time, correctable by a grown-up per item or per class, shown as a word on rows and the printed sheet, filterable on the kid and class pages, and audited in Diagnostics.

**Architecture:** A pure classifier (`fridgesheet/work_types.py`) walks a six-rung ladder over facts the database already holds plus one new ingest bit (`items.online_quiz`). Corrections and class rules live in two new tables (schema 14), read by a small store (`web/stores/work_types.py`) that `stores/items._views` calls once per request, so each `ItemView` carries `family`, `family_rung` and its reason. Nothing stores the family itself.

**Tech Stack:** Python 3, SQLite (forward-only migrations in `web/db.py`), FastAPI + Jinja2 + htmx, pytest with `tests/web_fixtures.py`, reportlab for the sheet.

**Spec:** `docs/superpowers/specs/2026-10-04-assignment-types-design.md` (§4, §5, §6; §10 item 1). PRs 2 (§7) and 3 (§8) get their own plans.

## Global Constraints

- Families, exactly: `FAMILIES = ("assessment", "practice", "lab_project", "participation")`.
- Ladder, first answer wins: 1 correction › 2 class rule › 3 `online_quiz` › 4 gradebook name (HAC category, then Canvas group; generic names skipped) › 5 item-name keyword › 6 practice.
- Generic names, compared case-folded and stripped: `assignments`, `imported assignments`, `total points`, `""`.
- Rule precedence: a `group` rule beats a `name_prefix` rule; longest prefix wins; ties go to the newest (`created_at`, then `id`).
- Rule `value` is stored case-folded and stripped; a rule made on either course of a Canvas/HAC pair applies to both.
- Schema version becomes **14** (12 is HAC's category weights, #254; 13 is Reset, #258). Main moves daily: before Task 2, read `SCHEMA_VERSION` in `fridgesheet/web/db.py` and take the next free number, renaming `_migrate_v14` and the tests to match.
- `online_quiz` lives on `items`, never on `item_observations` (a new observed field reads as the school moving in Changes).
- Everyday work (`practice`) shows **no** word on a row or the sheet.
- Every new `phrasing.PHRASES` key has `early`, `middle` and `older` entries, and no tier states a number, date or time its `older` entry does not (`tests/test_phrasing.py`).
- Corrections and rules are grown-up only: the form shows and the POSTs succeed only when `who_of(...)[0] == FAMILY`.
- New page sections use `.sec` / `.sec-head` (the retired-class tests fail otherwise).
- Run tests as `env -u PYTHONPATH <venv>/bin/python -m pytest …` (a sibling worktree's `.venv`, e.g. `../3c8edee2/.venv`); PYTHONPATH shadows the `tests` package.
- Commit messages for this PR's commits are ordinary (a release is wanted); the final squash title describes the feature.

## Review Focus

1. **A rule made on the HAC-only twin of a class** (course pair): it must apply to the Canvas items too. Test in Task 3 (`test_a_rule_made_on_either_course_of_a_pair_applies_to_both`).
2. **Two items folded together by the identity migration** where only the HAC-only one carried a correction: the survivor keeps it, and no orphan `item_types` row blocks the item delete (FK on). Test in Task 2 (`test_folding_items_carries_the_correction_and_online_quiz`).
3. **A child's browser posting the correction form directly** (the cookie names a kid): 403, nothing written. Test in Task 6 (`test_a_child_cannot_correct_a_type`).
4. **A hand-typed `?type=bogus`**: ignored like an unknown `?outcome=`, page renders all rows. Test in Task 5 (`test_an_unknown_type_is_ignored`).
5. **A generic group rule for a non-practice family** ("Assignments → test/quiz" would turn a whole class into tests): saved for the item only, with a message. Test in Task 6 (`test_a_generic_group_rule_is_only_for_everyday_work`).

---

## File Structure

| File | Responsibility |
|---|---|
| Create `fridgesheet/work_types.py` | Pure classifier: families, keywords, `Facts`, `Rule`, `Typed`, `family_of`, `prefix_suggestion`, `is_generic`, `RANK`, `coverage` |
| Create `fridgesheet/web/stores/work_types.py` | DB reads/writes for corrections and rules; `classify` for a student's rows; `rule_reach` |
| Modify `fridgesheet/web/db.py` | Schema 14 migration; `_fold_item` carries `item_types` and `online_quiz` |
| Modify `fridgesheet/web/ingest.py` | `_upsert_item(..., online_quiz=)`; Canvas loop passes it |
| Modify `fridgesheet/web/stores/items.py` | `ItemView.family/family_rung/family_why/family_values`; `_views` classifies; `list_items(family=)` / `_keep` |
| Modify `fridgesheet/web/phrasing.py` | `type.*` row words, `copy.type_*` filter labels, `type.why.*` reasons |
| Modify `fridgesheet/web/templates/_item.html` | Family word in the line and card meta; type line + form at detail density |
| Create `fridgesheet/web/templates/_type_form.html` | The correction form (grown-ups only) |
| Create `fridgesheet/web/templates/_type_links.html` | The "All 48 · Tests & quizzes 9 · …" link row |
| Modify `fridgesheet/web/routes/kid.py` | `?type=` on the kid and class pages; type links; rule list; `POST /items/{id}/type`; rule removal |
| Modify `fridgesheet/web/templates/kid.html`, `course.html` | Include the link row; class page "Type rules" section |
| Modify `fridgesheet/web/routes/diagnostics.py`, `templates/diagnostics.html` | "Types" coverage section |
| Modify `fridgesheet/open_items.py` | `Item.family`; snapshot path classifies (no rules) |
| Modify `fridgesheet/reports/open_work.py` | `from_views` passes `family` |
| Modify `fridgesheet/sheet.py` | Family word in the Via cell |
| Modify `fridgesheet/server.py` | `missing_work` sorts by `work_types.RANK` |
| Modify spec | §1 weights, §5 schema 14, §6.2 sheet, §6.4 "applies to N", §7.2 weighted formula |
| Tests | `tests/test_work_types.py`, `tests/test_web_work_types_store.py`, `tests/test_web_work_types_pages.py`, `tests/test_work_types_sheet.py` |

---

### Task 1: The classifier

**Files:**
- Create: `fridgesheet/work_types.py`
- Test: `tests/test_work_types.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `FAMILIES: tuple[str, ...]`, `RANK: dict[str, int]` (`assessment 0, lab_project 1, practice 2, participation 3`)
  - `@dataclass(frozen=True) Facts(name: str, canvas_group: str | None = None, hac_category: str | None = None, online_quiz: bool = False)`
  - `@dataclass(frozen=True) Rule(id: int, field: str, value: str, family: str, created_at: str)`; `field in ("group", "name_prefix")`
  - `@dataclass(frozen=True) Typed(family: str, rung: int, why: str, values: dict)`; `why` is a phrasing key (`type.why.*`)
  - `family_of(facts: Facts, rules: Sequence[Rule] = (), correction: str | None = None) -> Typed`
  - `keyword_family(text: str | None) -> str | None`
  - `is_generic(name: str | None) -> bool`
  - `fold(text: str | None) -> str` (case-fold + strip)
  - `gradebook_name(facts: Facts) -> str | None` (HAC category if present and non-empty, else Canvas group)
  - `prefix_suggestion(name: str) -> str | None`
  - `coverage(typed: Iterable[Typed]) -> dict[int, int]` (rungs 1–6, zeros included)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_work_types.py
"""The assignment-type classifier (spec 2026-10-04 assignment types §4): four families, a
six-rung ladder, keyword rows tried in order."""
from __future__ import annotations

import pytest

from fridgesheet import work_types as wt
from fridgesheet.work_types import Facts, Rule


# Names and gradebook labels from the household's snapshot (spec §1).
@pytest.mark.parametrize("facts, family", [
    (Facts("WS #2-4 A", canvas_group="Assignments", hac_category="Assignments"), "practice"),
    (Facts("Concept 2:  Cell Transport Video Notes Part 1", canvas_group="Assignments"), "practice"),
    (Facts("Unit 3 Test", canvas_group="Assignments"), "assessment"),
    (Facts("Chapter 4", canvas_group="Quizzes & Tests"), "assessment"),
    (Facts("Ch 2", hac_category="Pre-Tests"), "assessment"),
    (Facts("Week 3", canvas_group="Assessments"), "assessment"),
    (Facts("Density", hac_category="Labs"), "lab_project"),
    (Facts("Density", canvas_group="LABS"), "lab_project"),
    (Facts("Scales", hac_category="Playing/Written Work"), "participation"),
    (Facts("Fall concert", hac_category="Concert Attendance"), "participation"),
    (Facts("p. 41", canvas_group="HMWK"), "practice"),
    (Facts("p. 41", hac_category="Homework Completion"), "practice"),
    (Facts("Bell work", hac_category="Daily"), "practice"),
    (Facts("Socratic Seminar", hac_category="Assignments"), "participation"),
    (Facts("Lab Quiz"), "assessment"),                          # assessment row is tried first
    (Facts("Label the map"), "practice"),                       # "lab" needs a word boundary
    (Facts("Example problems"), "practice"),                    # "exam" needs a word boundary
    (Facts("Lab3 write-up"), "lab_project"),                    # a digit is a boundary
])
def test_real_names_get_the_family_a_parent_would_give(facts, family):
    assert wt.family_of(facts).family == family


def test_each_rung_of_the_ladder_answers_in_order():
    f = Facts("Unit 3 Test", canvas_group="Labs", hac_category="Homework", online_quiz=True)
    rule = Rule(1, "name_prefix", "unit", "participation", "2026-10-04T10:00:00")
    assert wt.family_of(f, [rule], "practice").rung == 1
    assert wt.family_of(f, [rule], "practice").family == "practice"
    assert (wt.family_of(f, [rule]).rung, wt.family_of(f, [rule]).family) == (2, "participation")
    assert (wt.family_of(f).rung, wt.family_of(f).family) == (3, "assessment")
    no_quiz = Facts("Unit 3 Test", canvas_group="Labs", hac_category="Homework")
    assert (wt.family_of(no_quiz).rung, wt.family_of(no_quiz).family) == (4, "practice")   # HAC before Canvas
    only_name = Facts("Unit 3 Test", canvas_group="Assignments")
    assert (wt.family_of(only_name).rung, wt.family_of(only_name).family) == (5, "assessment")
    nothing = Facts("Evidence Tracker", canvas_group="Assignments", hac_category="Total Points")
    t = wt.family_of(nothing)
    assert (t.rung, t.family, t.why) == (6, "practice", "type.why.default")


def test_hac_wins_at_rung_four_but_a_generic_hac_name_defers_to_canvas():
    assert wt.family_of(Facts("x", canvas_group="Quiz", hac_category="Labs")).family == "lab_project"
    assert wt.family_of(Facts("x", canvas_group="Quiz", hac_category="Assignments")).family == "assessment"
    t = wt.family_of(Facts("x", canvas_group="Quiz", hac_category="Assignments"))
    assert (t.why, t.values) == ("type.why.canvas", {"name": "Quiz"})


def test_a_non_generic_gradebook_name_with_no_keyword_falls_through_to_the_item_name():
    t = wt.family_of(Facts("Chapter 2 Test", canvas_group="Smartbook"))
    assert (t.rung, t.family) == (5, "assessment")


def test_rules_group_beats_prefix_longest_prefix_then_newest():
    f = Facts("WS #2-4 A", canvas_group="Classwork")
    group = Rule(1, "group", "classwork", "participation", "2026-10-01T00:00:00")
    short = Rule(2, "name_prefix", "ws", "assessment", "2026-10-03T00:00:00")
    long_ = Rule(3, "name_prefix", "ws #", "lab_project", "2026-10-02T00:00:00")
    assert wt.family_of(f, [short, long_, group]).family == "participation"
    assert wt.family_of(f, [short, long_]).family == "lab_project"
    older = Rule(4, "name_prefix", "ws #", "assessment", "2026-09-01T00:00:00")
    assert wt.family_of(f, [older, long_]).family == "lab_project"


def test_a_group_rule_matches_either_gradebook_name_case_folded():
    rule = Rule(1, "group", "assignments", "practice", "t")
    assert wt.family_of(Facts("Unit Test", hac_category=" ASSIGNMENTS "), [rule]).rung == 2
    assert wt.family_of(Facts("Unit Test", canvas_group="Assignments"), [rule]).rung == 2
    assert wt.family_of(Facts("Unit Test", canvas_group="Homework"), [rule]).rung == 5


def test_generic_names():
    assert wt.is_generic("Imported Assignments") and wt.is_generic("  total points ")
    assert wt.is_generic(None) and wt.is_generic("")
    assert not wt.is_generic("Homework")


@pytest.mark.parametrize("name, prefix", [
    ("WS #2-4 A", "WS #"), ("Unit #0 - Canvas Review", "Unit #"), ("Chapter 1.3 Reading Guide", "Chapter"),
    ("7", None), ("A1 warmup", None), ("Most Dangerous Game Evidence Tracker", "Most Dangerous Game Evidence Tracker"),
])
def test_prefix_suggestion_is_the_text_before_the_first_digit(name, prefix):
    assert wt.prefix_suggestion(name) == prefix


def test_coverage_counts_every_rung():
    typed = [wt.family_of(Facts("Unit Test")), wt.family_of(Facts("x")), wt.family_of(Facts("y"))]
    assert wt.coverage(typed) == {1: 0, 2: 0, 3: 0, 4: 0, 5: 1, 6: 2}


def test_rank_orders_tests_first():
    assert sorted(wt.FAMILIES, key=wt.RANK.__getitem__) == ["assessment", "lab_project", "practice", "participation"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_work_types.py -q -p no:cacheprovider`
Expected: FAIL, `ModuleNotFoundError: No module named 'fridgesheet.work_types'`.

- [ ] **Step 3: Write the module**

```python
# fridgesheet/work_types.py
"""What kind of work an item is (spec 2026-10-04 assignment types §4).

Canvas has no assignment type. Teachers name assignment groups (Canvas) and categories (HAC)
to weight the grade, and the names say what the work is only when the teacher happens to
weight by kind. So the type is inferred, in four families a parent would talk about
differently, by the first rung of a ladder that answers:

  1. a grown-up's correction on this item
  2. a class rule ("filed under X", "name starts with Y")
  3. Canvas's own `online_quiz`
  4. the gradebook's name for the item, HAC's category before Canvas's group, generic
     buckets ("Assignments", "Total Points") skipped
  5. a keyword in the item's name
  6. everyday work: on the household's data every unlabelled item was a worksheet, notes or
     a tracker, never a hidden test (spec §1), so nothing named is evidence, not a gap

Pure: no database, no clock. The family is computed on every read, never stored, so a better
keyword list or a new rule relabels every item, past ones included.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

FAMILIES: tuple[str, ...] = ("assessment", "practice", "lab_project", "participation")
#: The order the sheet, the MCP server and (PR 2) Must-finish break ties in: tests first.
RANK: dict[str, int] = {"assessment": 0, "lab_project": 1, "practice": 2, "participation": 3}
GENERIC: frozenset[str] = frozenset({"assignments", "imported assignments", "total points", ""})

#: (family, word patterns), tried in this order, first match wins: "Lab Quiz" is a quiz.
#: Each pattern must stand alone: no letter on either side ("lab" is not in "label").
KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("assessment", ("tests?", "exams?", "finals?", "midterms?", "quiz", "quizzes", "pre-?tests?",
                    "assessments?", "check ?points?", "summative")),
    ("lab_project", ("labs?", "projects?", "presentations?", "research", "essays?")),
    ("participation", ("participation", "attendance", "concerts?", "performances?", "playing", "seminars?")),
    ("practice", ("homework", "hmwk", "hw", "class ?work", "daily", "warm-?ups?", "bell ?ringers?",
                  "exit tickets?", "worksheets?", "ws")),
)
_PATTERNS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (fam, re.compile(r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])")) for fam, words in KEYWORDS)


@dataclass(frozen=True)
class Facts:
    name: str
    canvas_group: str | None = None
    hac_category: str | None = None
    online_quiz: bool = False


@dataclass(frozen=True)
class Rule:
    id: int
    field: str          # "group" | "name_prefix"
    value: str          # case-folded, stripped
    family: str
    created_at: str


@dataclass(frozen=True)
class Typed:
    family: str
    rung: int           # 1..6, the ladder step that answered
    why: str            # a phrasing key, type.why.*
    values: dict = field(default_factory=dict)


def fold(text: str | None) -> str:
    return (text or "").casefold().strip()


def is_generic(name: str | None) -> bool:
    return fold(name) in GENERIC


def keyword_family(text: str | None) -> str | None:
    t = fold(text)
    return next((fam for fam, rx in _PATTERNS if rx.search(t)), None)


def gradebook_name(facts: Facts) -> str | None:
    """The name a group rule offers to pin: HAC's category, else Canvas's group."""
    return next((n.strip() for n in (facts.hac_category, facts.canvas_group) if n and n.strip()), None)


def _rule_order(r: Rule) -> tuple:
    # group rules first; then longer prefixes; then newest (created_at, id), all descending.
    return (r.field == "group", len(r.value) if r.field == "name_prefix" else 0, r.created_at, r.id)


def _matches(rule: Rule, facts: Facts) -> bool:
    if rule.field == "group":
        return rule.value in (fold(facts.canvas_group), fold(facts.hac_category)) and rule.value != ""
    return bool(rule.value) and fold(facts.name).startswith(rule.value)


def family_of(facts: Facts, rules: Sequence[Rule] = (), correction: str | None = None) -> Typed:
    if correction in FAMILIES:
        return Typed(correction, 1, "type.why.correction")
    for rule in sorted(rules, key=_rule_order, reverse=True):
        if _matches(rule, facts):
            why = "type.why.rule_group" if rule.field == "group" else "type.why.rule_prefix"
            return Typed(rule.family, 2, why, {"value": rule.value})
    if facts.online_quiz:
        return Typed("assessment", 3, "type.why.online_quiz")
    for name, why in ((facts.hac_category, "type.why.hac"), (facts.canvas_group, "type.why.canvas")):
        if not is_generic(name):
            fam = keyword_family(name)
            if fam:
                return Typed(fam, 4, why, {"name": name.strip()})
    fam = keyword_family(facts.name)
    if fam:
        return Typed(fam, 5, "type.why.name")
    return Typed("practice", 6, "type.why.default")


def prefix_suggestion(name: str) -> str | None:
    """The text before the name's first digit, as a name-prefix rule would pin it ("WS #2-4 A"
    is "WS #"); None when that is shorter than two characters."""
    head = re.match(r"[^\d]*", name or "").group(0).strip()
    return head if len(head) >= 2 else None


def coverage(typed: Iterable[Typed]) -> dict[int, int]:
    out = {r: 0 for r in range(1, 7)}
    for t in typed:
        out[t.rung] += 1
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_work_types.py -q -p no:cacheprovider`
Expected: all PASS. If "Socratic Seminar" or "Most Dangerous Game…" fails, fix the pattern, not the test: those are real household names.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/work_types.py tests/test_work_types.py
git commit -m "Assignment types: the four-family classifier and its six-rung ladder"
```

---

### Task 2: Schema 14, the online-quiz bit, and folding

**Files:**
- Modify: `fridgesheet/web/db.py` (`SCHEMA_VERSION`, `migrate`, new `_migrate_v14`, `_fold_item`)
- Modify: `fridgesheet/web/ingest.py:91-131` (`_upsert_item`), `:265-270` (Canvas loop)
- Test: `tests/test_web_work_types_store.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: tables `item_types(item_id PK, family, set_at)`, `type_rules(id, course_id, field, value, family, created_at, UNIQUE(course_id, field, value))`; column `items.online_quiz`; `_upsert_item(..., online_quiz: bool = False)` keyword.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_work_types_store.py
"""Assignment types in the database (spec 2026-10-04 assignment types §5): schema 14, the
online-quiz bit at ingest, corrections and rules carried and read."""
from __future__ import annotations

import pytest

from fridgesheet.web import db
from web_fixtures import seed, snapshot


def _items(conn):
    return {r["name"]: r for r in conn.execute("SELECT * FROM items")}


def test_schema_14_adds_the_two_tables_and_the_column(tmp_path):
    conn = db.open_db(tmp_path)
    assert db.SCHEMA_VERSION == 14 and db.migrate(conn) == 14
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    assert "online_quiz" in cols
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"item_types", "type_rules"} <= tables


def test_the_v14_migration_runs_again_on_a_file_rolled_back_to_13(tmp_path):
    conn = db.open_db(tmp_path)
    conn.execute("UPDATE schema_version SET version = 13")
    assert db.migrate(conn) == 14                       # column and tables already there: no error


def test_ingest_records_canvas_online_quizzes(tmp_path):
    snap = snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"][0]["submission_types"] = ["online_quiz"]
    conn = seed(tmp_path, snap)
    rows = _items(conn)
    assert rows["Quiz 1"]["online_quiz"] == 1
    assert rows["Essay draft"]["online_quiz"] == 0


def test_folding_items_carries_the_correction_and_online_quiz(tmp_path):
    conn = seed(tmp_path)
    a, b = [r["id"] for r in conn.execute("SELECT id FROM items ORDER BY id LIMIT 2")]
    with conn:
        conn.execute("UPDATE items SET online_quiz = 1 WHERE id = ?", (a,))
        conn.execute("INSERT INTO item_types(item_id, family, set_at) VALUES (?, 'lab_project', 't')", (a,))
        db._fold_item(conn, a, into=b)
    assert conn.execute("SELECT family FROM item_types WHERE item_id = ?", (b,)).fetchone()["family"] == "lab_project"
    assert conn.execute("SELECT COUNT(*) FROM item_types WHERE item_id = ?", (a,)).fetchone()[0] == 0
    assert conn.execute("SELECT online_quiz FROM items WHERE id = ?", (b,)).fetchone()[0] == 1


def test_folding_keeps_the_survivors_own_correction(tmp_path):
    conn = seed(tmp_path)
    a, b = [r["id"] for r in conn.execute("SELECT id FROM items ORDER BY id LIMIT 2")]
    with conn:
        conn.execute("INSERT INTO item_types(item_id, family, set_at) VALUES (?, 'lab_project', 't1')", (a,))
        conn.execute("INSERT INTO item_types(item_id, family, set_at) VALUES (?, 'assessment', 't2')", (b,))
        db._fold_item(conn, a, into=b)
    assert [r["family"] for r in conn.execute("SELECT family FROM item_types")] == ["assessment"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_store.py -q -p no:cacheprovider`
Expected: FAIL on `db.SCHEMA_VERSION == 14` and missing column/table.

- [ ] **Step 3: Implement the migration**

In `fridgesheet/web/db.py`: set `SCHEMA_VERSION = 14`; after the `if v < 13:` block in `migrate` add:

```python
    if v < 14:
        with conn:
            conn.execute("BEGIN")
            _migrate_v14(conn)
            conn.execute("UPDATE schema_version SET version = 14")
        v = 14
```

and after `_migrate_v12` (the last function-style migration):

```python
def _migrate_v14(conn: sqlite3.Connection) -> None:
    """Assignment types (spec 2026-10-04 assignment types §5): Canvas's own `online_quiz` on the
    item, a grown-up's correction per item, and class rules. The family itself is never stored
    (`work_types.family_of` reads these on every view). Each step checks first, so a file rolled
    back to an older version number migrates again."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)")}
    if "online_quiz" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN online_quiz INTEGER NOT NULL DEFAULT 0")
    conn.execute("""CREATE TABLE IF NOT EXISTS item_types (
        item_id INTEGER PRIMARY KEY REFERENCES items(id),
        family TEXT NOT NULL CHECK (family IN ('assessment','practice','lab_project','participation')),
        set_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS type_rules (
        id INTEGER PRIMARY KEY,
        course_id INTEGER NOT NULL REFERENCES courses(id),
        field TEXT NOT NULL CHECK (field IN ('group','name_prefix')),
        value TEXT NOT NULL,
        family TEXT NOT NULL CHECK (family IN ('assessment','practice','lab_project','participation')),
        created_at TEXT NOT NULL,
        UNIQUE (course_id, field, value))""")
```

- [ ] **Step 4: Carry corrections and the bit in `_fold_item`**

In `_fold_item`, after the `item_categories` block and before `t = conn.execute("SELECT * FROM items ...")`:

```python
    # A grown-up's type correction: the surviving item keeps its own, else takes the twin's.
    # The table arrives in v14; the v7 migration folds on an older file, so it may not exist.
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='item_types'").fetchone():
        if conn.execute("SELECT 1 FROM item_types WHERE item_id = ?", (into,)).fetchone():
            conn.execute("DELETE FROM item_types WHERE item_id = ?", (src,))
        else:
            conn.execute("UPDATE item_types SET item_id = ? WHERE item_id = ?", (into, src))
```

and, so the bit survives, after the existing `UPDATE items SET name = ? …` statement:

```python
    if "online_quiz" in t.keys():
        conn.execute("UPDATE items SET online_quiz = MAX(online_quiz, ?) WHERE id = ?", (t["online_quiz"], into))
```

- [ ] **Step 5: Record the bit at ingest**

In `fridgesheet/web/ingest.py` `_upsert_item`: add keyword `online_quiz: bool = False` after `lock_at`; add `online_quiz = ?` to the UPDATE (after `lock_at = ?`) with `int(online_quiz)` in the tuple at the matching position; add `online_quiz` to the INSERT column list and `int(online_quiz)` to its values (the VALUES gets one more `?`). In the Canvas loop call, add `online_quiz="online_quiz" in (a.get("submission_types") or [])` beside `unlock_at=…, lock_at=…`. HAC-only rows keep the default.

- [ ] **Step 6: Run the tests and the existing DB/ingest suites**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_store.py tests/test_web_db.py tests/test_web_ingest.py tests/test_item_identity.py tests/test_migrate.py -q -p no:cacheprovider`
Expected: all PASS. A test pinning `SCHEMA_VERSION == 13` (grep `SCHEMA_VERSION\b.*13` in tests) is updated to 14.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/db.py fridgesheet/web/ingest.py tests/test_web_work_types_store.py tests
git commit -m "Assignment types: schema 14 (corrections, class rules, Canvas's online-quiz bit), carried when items fold"
```

---

### Task 3: The store, and every ItemView carrying its family

**Files:**
- Create: `fridgesheet/web/stores/work_types.py`
- Modify: `fridgesheet/web/stores/items.py` (`ItemView` fields, `_views`, `_keep`, `list_items`)
- Test: `tests/test_web_work_types_store.py` (append)

**Interfaces:**
- Consumes: `work_types.Facts`, `Rule`, `Typed`, `family_of`, `fold`, `FAMILIES` (Task 1); tables from Task 2.
- Produces:
  - `pair(conn, course_id: int) -> set[int]`
  - `rules_for(conn, course_ids: set[int]) -> list[sqlite3.Row]` (ordered newest first)
  - `classify(conn, student_id: int, rows: list[sqlite3.Row]) -> dict[int, Typed]` (rows need `id`, `name`, `course_id`, `online_quiz`)
  - `facts_for(conn, item_id: int) -> work_types.Facts`
  - `set_correction(conn, item_id: int, family: str, now: str) -> None`, `clear_correction(conn, item_id: int) -> None`
  - `add_rule(conn, course_id: int, field: str, value: str, family: str, now: str) -> None` (upsert on the unique key)
  - `remove_rule(conn, rule_id: int) -> sqlite3.Row | None` (returns the removed row)
  - `rule_reach(conn, student_id: int, course_id: int, field: str, value: str) -> int` (items in the class pair the rule would match)
  - `ItemView.family: str = "practice"`, `family_rung: int = 6`, `family_why: str = "type.why.default"`, `family_values: dict`
  - `items.list_items(..., family: str | None = None)`; `items.FAMILY_FILTER = work_types.FAMILIES`

- [ ] **Step 1: Write the failing tests (append)**

```python
from fridgesheet import work_types as wt
from fridgesheet.web.stores import items, students, work_types as type_store
from web_fixtures import NOW, app_for

class _Rules:   # the late rules the views need, with no deadlines set
    @staticmethod
    def deadline(*a, **k): return None
    @staticmethod
    def resolve(*a, **k):
        from types import SimpleNamespace
        return SimpleNamespace(credit="")


def _views(conn, key="Alex"):
    s = students.by_key(conn, key)
    return {v.name: v for v in items.list_items(conn, s, now=NOW, rules=_Rules(), show="all")}


def _course(conn, name_like):
    return conn.execute("SELECT * FROM courses WHERE name LIKE ?", (f"%{name_like}%",)).fetchall()


def test_every_view_carries_a_family_and_the_rung_that_gave_it(tmp_path):
    snap = snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"][0]["submission_types"] = ["online_quiz"]
    conn = seed(tmp_path, snap)
    v = _views(conn)
    assert (v["Quiz 1"].family, v["Quiz 1"].family_rung) == ("assessment", 3)
    assert v["Quiz 1"].is_assessment
    assert (v["Essay draft"].family, v["Essay draft"].family_rung) == ("practice", 4)   # group "Homework"
    assert (v["Lab notebook"].family, v["Lab notebook"].family_rung) == ("practice", 4)  # group beats name
    assert v["Participation"].family == "participation"                               # HAC-only, by name


def test_a_correction_wins_and_clearing_it_restores_the_guess(tmp_path):
    conn = seed(tmp_path)
    iid = _views(conn)["Lab notebook"].id
    type_store.set_correction(conn, iid, "lab_project", "2026-10-04T10:00:00")
    assert (_views(conn)["Lab notebook"].family, _views(conn)["Lab notebook"].family_rung) == ("lab_project", 1)
    type_store.clear_correction(conn, iid)
    assert _views(conn)["Lab notebook"].family == "practice"


def test_a_rule_made_on_either_course_of_a_pair_applies_to_both(tmp_path):
    conn = seed(tmp_path)
    hac_course = [c for c in _course(conn, "English") if c["source"] == "hac"][0]
    type_store.add_rule(conn, hac_course["id"], "group", "Homework", "lab_project", "2026-10-04T10:00:00")
    v = _views(conn)
    assert (v["Essay draft"].family, v["Essay draft"].family_rung) == ("lab_project", 2)   # a Canvas item
    assert v["Homework 4"].family == "practice"                                          # Algebra: another class


def test_rule_reach_counts_the_items_a_rule_would_cover(tmp_path):
    conn = seed(tmp_path)
    sid = students.by_key(conn, "Alex")["id"]
    canvas_eng = [c for c in _course(conn, "English") if c["source"] == "canvas"][0]
    assert type_store.rule_reach(conn, sid, canvas_eng["id"], "group", "homework") == 6
    assert type_store.rule_reach(conn, sid, canvas_eng["id"], "name_prefix", "quiz") == 1


def test_add_rule_folds_the_value_and_replaces_its_own_family(tmp_path):
    conn = seed(tmp_path)
    cid = _course(conn, "English")[0]["id"]
    type_store.add_rule(conn, cid, "name_prefix", "  WS # ", "practice", "t1")
    type_store.add_rule(conn, cid, "name_prefix", "ws #", "assessment", "t2")
    rows = conn.execute("SELECT value, family FROM type_rules").fetchall()
    assert [(r["value"], r["family"]) for r in rows] == [("ws #", "assessment")]


def test_list_items_filters_by_family(tmp_path):
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    shown = items.list_items(conn, s, now=NOW, rules=_Rules(), show="all", family="participation")
    assert [v.name for v in shown] == ["Participation"]
    every = items.list_items(conn, s, now=NOW, rules=_Rules(), show="all", family="nonsense")
    assert len(every) == len(_views(conn))
```

Check `tests/web_fixtures.py` or an existing store test for a ready-made rules object before keeping `_Rules`: `grep -n "rules=" tests/test_web_stores.py | head` and reuse whatever those tests pass (e.g. `late_rules.load(...)` or `state.rules()`); replace `_Rules()` with it if one exists.

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_store.py -q -p no:cacheprovider`
Expected: FAIL, no module `fridgesheet.web.stores.work_types`.

- [ ] **Step 3: Write the store**

```python
# fridgesheet/web/stores/work_types.py
"""Corrections and class rules for assignment types (spec 2026-10-04 assignment types §5, §6).

`work_types.family_of` decides; this module only reads what it needs and writes what a
grown-up chose. A class is a Canvas course and its paired HAC course, so a rule made on
either applies to both, as a class filter does (`items.list_items`)."""
from __future__ import annotations

import sqlite3

from ... import work_types
from ...work_types import Facts, Rule, Typed


def pair(conn: sqlite3.Connection, course_id: int) -> set[int]:
    row = conn.execute("SELECT peer_course_id FROM courses WHERE id = ?", (course_id,)).fetchone()
    return {course_id} | ({row["peer_course_id"]} if row and row["peer_course_id"] else set())


def rules_for(conn: sqlite3.Connection, course_ids: set[int]) -> list[sqlite3.Row]:
    if not course_ids:
        return []
    marks = ",".join("?" * len(course_ids))
    return conn.execute(f"SELECT * FROM type_rules WHERE course_id IN ({marks}) ORDER BY created_at DESC, id DESC",
                        tuple(course_ids)).fetchall()


def _rule(r: sqlite3.Row) -> Rule:
    return Rule(r["id"], r["field"], r["value"], r["family"], r["created_at"])


def _categories(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    for i in range(0, len(item_ids), 500):                 # SQLite's bound-parameter limit
        chunk = item_ids[i:i + 500]
        for r in conn.execute(f"SELECT item_id, source, category FROM item_categories WHERE item_id IN ({','.join('?' * len(chunk))})", chunk):
            out.setdefault(r["item_id"], {})[r["source"]] = r["category"]
    return out


def _facts(row, cats: dict[str, str]) -> Facts:
    return Facts(row["name"], canvas_group=cats.get("canvas"), hac_category=cats.get("hac"),
                 online_quiz=bool(row["online_quiz"]) if "online_quiz" in row.keys() else False)


def facts_for(conn: sqlite3.Connection, item_id: int) -> Facts:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _facts(row, _categories(conn, [item_id]).get(item_id, {}))


def classify(conn: sqlite3.Connection, student_id: int, rows: list) -> dict[int, Typed]:
    """Each row's family. One read each of categories, corrections and the student's rules."""
    ids = [r["id"] for r in rows]
    cats = _categories(conn, ids)
    corrections = {r["item_id"]: r["family"] for r in conn.execute(
        "SELECT t.item_id, t.family FROM item_types t JOIN items i ON i.id = t.item_id WHERE i.student_id = ?", (student_id,))}
    by_course: dict[int, list[Rule]] = {}
    for r in conn.execute("""SELECT t.*, c.peer_course_id FROM type_rules t JOIN courses c ON c.id = t.course_id
                             WHERE c.student_id = ?""", (student_id,)):
        for cid in (r["course_id"], r["peer_course_id"]):
            if cid:
                by_course.setdefault(cid, []).append(_rule(r))
    return {r["id"]: work_types.family_of(_facts(r, cats.get(r["id"], {})), by_course.get(r["course_id"], ()),
                                          corrections.get(r["id"])) for r in rows}


def set_correction(conn: sqlite3.Connection, item_id: int, family: str, now: str) -> None:
    if family not in work_types.FAMILIES:
        raise ValueError(f"unknown family {family!r}")
    conn.execute("INSERT OR REPLACE INTO item_types(item_id, family, set_at) VALUES (?, ?, ?)", (item_id, family, now))


def clear_correction(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM item_types WHERE item_id = ?", (item_id,))


def add_rule(conn: sqlite3.Connection, course_id: int, field: str, value: str, family: str, now: str) -> None:
    if field not in ("group", "name_prefix") or family not in work_types.FAMILIES or not work_types.fold(value):
        raise ValueError("a rule needs a field, a value and a family")
    conn.execute("""INSERT INTO type_rules(course_id, field, value, family, created_at) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, field, value) DO UPDATE SET family = excluded.family, created_at = excluded.created_at""",
                 (course_id, field, work_types.fold(value), family, now))


def remove_rule(conn: sqlite3.Connection, rule_id: int) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM type_rules WHERE id = ?", (rule_id,)).fetchone()
    if row is not None:
        conn.execute("DELETE FROM type_rules WHERE id = ?", (rule_id,))
    return row


def rule_reach(conn: sqlite3.Connection, student_id: int, course_id: int, field: str, value: str) -> int:
    """How many of the student's items in this class (both courses of the pair) the rule
    would match: the "applies to N items" a grown-up sees before saving it."""
    ids = pair(conn, course_id)
    marks = ",".join("?" * len(ids))
    rows = conn.execute(f"SELECT * FROM items WHERE student_id = ? AND course_id IN ({marks})", (student_id, *ids)).fetchall()
    cats = _categories(conn, [r["id"] for r in rows])
    probe = Rule(0, field, work_types.fold(value), "practice", "")
    return sum(1 for r in rows if work_types._matches(probe, _facts(r, cats.get(r["id"], {}))))
```

Rename `work_types._matches` to the public `work_types.matches` (and update its one caller in `family_of`), since the store uses it; adjust the line above to `work_types.matches(...)`.

- [ ] **Step 4: Give every ItemView its family**

In `fridgesheet/web/stores/items.py`:

1. Import: `from ... import config, sources, work_types` and `from . import num, plans, pace as pace_store, work_types as type_store`.
2. Constant beside `VERDICTS`: `FAMILY_FILTER = work_types.FAMILIES`.
3. `ItemView`, after `is_assessment`:

```python
    #: What kind of work this is (spec 2026-10-04 assignment types): the family, the ladder rung
    #: that decided it, and why, as a phrasing key and its values for the detail card.
    family: str = "practice"
    family_rung: int = 6
    family_why: str = "type.why.default"
    family_values: dict = field(default_factory=dict)
```

4. `_views`: replace `for r in reconcile.live_items(conn, student["id"], now):` with

```python
    live = reconcile.live_items(conn, student["id"], now)
    typed = type_store.classify(conn, student["id"], live)
    for r in live:
        t = typed[r["id"]]
```

and in the `ItemView(...)` call replace `is_assessment=bool(r["is_assessment"]),` with

```python
            is_assessment=t.family == "assessment",
            family=t.family, family_rung=t.rung, family_why=t.why, family_values=t.values,
```

(The `items.is_assessment` column is no longer read; it stays until a later schema drops it.)

5. `_keep`: add parameter `family=None` (last) and, first in the body, `if family in FAMILY_FILTER and v.family != family: return False`.
6. `list_items`: add parameter `family: str | None = None`; pass it through: `_keep(v, show, source, course_ids, kind, flagged, outcome, verdict, family)`.

- [ ] **Step 5: Run the tests**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_store.py tests/test_work_types.py tests/test_web_stores.py tests/test_open_work_parity.py -q -p no:cacheprovider`
Expected: all PASS. If `test_rule_reach…` gives a count other than 6, count the fixture's English items with group `Homework` (all six `_a(...)` rows default to it) and correct the expectation only if the fixture changed.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/work_types.py fridgesheet/web/stores/work_types.py fridgesheet/web/stores/items.py tests/test_web_work_types_store.py
git commit -m "Assignment types: every item view carries its family, from corrections, class rules and the ladder"
```

---

### Task 4: The word on the row, the sheet and the MCP order

**Files:**
- Modify: `fridgesheet/web/phrasing.py` (new keys)
- Modify: `fridgesheet/web/templates/_item.html:39-40` (line meta), `:59` (card meta)
- Modify: `fridgesheet/open_items.py` (`Item.family`; both `Item(...)` builders at `:333-340`, `:381-385`)
- Modify: `fridgesheet/reports/open_work.py:62`
- Modify: `fridgesheet/sheet.py:164` (Via cell)
- Modify: `fridgesheet/server.py:229-232`
- Test: `tests/test_web_work_types_pages.py` (new), `tests/test_work_types_sheet.py` (new)

**Interfaces:**
- Consumes: `ItemView.family` (Task 3), `work_types.family_of`, `Facts`, `RANK` (Task 1).
- Produces: phrasing keys `type.assessment`, `type.lab_project`, `type.participation`; `copy.type_all`, `copy.type_assessment`, `copy.type_practice`, `copy.type_lab_project`, `copy.type_participation`; `type.why.correction|rule_group|rule_prefix|online_quiz|hac|canvas|name|default`; `open_items.Item.family: str = "practice"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_web_work_types_pages.py
"""Assignment types on the pages (spec 2026-10-04 assignment types §6)."""
from __future__ import annotations

import re

from fridgesheet.web import app as webapp
from web_fixtures import app_for, seed, snapshot


def _quiz_snapshot():
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"]
    eng[0]["group"] = "Quizzes & Tests"             # Quiz 1 -> assessment
    eng[5]["group"] = "Labs"                        # Lab notebook -> lab_project
    return snap


def _item_ids(conn):
    return {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM items")}


def test_the_row_says_the_family_and_everyday_work_says_nothing(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    ids = _item_ids(conn)
    page = app_for(tmp_path).get("/kids/Alex?show=all").text
    def line(name):
        m = re.search(rf'id="row-{ids[name]}".*?</div>', page, re.S)
        return m.group(0) if m else ""
    assert "test/quiz" in line("Quiz 1")
    assert "lab/project" in line("Lab notebook")
    assert not re.search(r"test/quiz|lab/project|participation", line("Essay draft"))
```

```python
# tests/test_work_types_sheet.py
"""The family on the printed sheet and in the MCP server's order (assignment types §6.2)."""
from __future__ import annotations

from fridgesheet import open_items, work_types


def test_snapshot_items_carry_a_family_without_rules():
    it = open_items.Item(key="k", kid="Alex", course="ENG", name="Unit Test", due=None, status="MISSING",
                         overdue=True, source="canvas", kind="online")
    assert it.family == "practice"                  # the default before classification
    assert "family" in it.to_dict()


def test_mcp_order_puts_tests_first_then_points():
    rows = [{"family": "practice", "points": 50}, {"family": "assessment", "points": 5}, {"family": "lab_project", "points": 20}]
    rows.sort(key=lambda r: (work_types.RANK.get(r["family"], 9), -(r["points"] or 0)))
    assert [r["family"] for r in rows] == ["assessment", "lab_project", "practice"]
```

Add one sheet-level test beside the existing sheet-table tests: open `tests/test_sheet_table.py`, find the helper that builds a one-row `OpenWork` and renders the table data (grep `def _row\|Item(` in that file), and add a case with `family="assessment"` asserting the Via cell text ends with `· test/quiz`, and one with `family="practice"` asserting it does not contain `everyday`. Use that file's own helpers so the test reads like its neighbours.

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py tests/test_work_types_sheet.py -q -p no:cacheprovider`
Expected: FAIL (no `test/quiz` on the row; `Item` has no `family`).

- [ ] **Step 3: Add the phrases**

In `fridgesheet/web/phrasing.py`, inside `PHRASES`, after the status-word block:

```python
    # --- what kind of work it is (spec 2026-10-04 assignment types §6) ------------------------
    # The word on a row; everyday work has none, as a row says "paper" but never "online".
    "type.assessment":     {"early": "test or quiz", "middle": "test/quiz", "older": "test/quiz"},
    "type.lab_project":    {"early": "lab or project", "middle": "lab/project", "older": "lab/project"},
    "type.participation":  {"early": "taking part", "middle": "participation", "older": "participation"},
    # The filter's labels, plural.
    "copy.type_all":            {"early": "All", "middle": "All", "older": "All"},
    "copy.type_assessment":     {"early": "Tests and quizzes", "middle": "Tests & quizzes", "older": "Tests & quizzes"},
    "copy.type_practice":       {"early": "Everyday work", "middle": "Everyday work", "older": "Everyday work"},
    "copy.type_lab_project":    {"early": "Labs and projects", "middle": "Labs & projects", "older": "Labs & projects"},
    "copy.type_participation":  {"early": "Taking part", "middle": "Participation", "older": "Participation"},
    # Why the app gave the type it did (the detail card's type line, grown-ups).
    "type.why.correction":  {"early": "you set it", "middle": "you set it", "older": "you set it"},
    "type.why.rule_group":  {"early": "your rule: filed under “{value}”", "middle": "your rule: filed under “{value}”", "older": "your rule: filed under “{value}”"},
    "type.why.rule_prefix": {"early": "your rule: name starts with “{value}”", "middle": "your rule: name starts with “{value}”", "older": "your rule: name starts with “{value}”"},
    "type.why.online_quiz": {"early": "Canvas calls it a quiz", "middle": "Canvas calls it a quiz", "older": "a Canvas quiz"},
    "type.why.hac":         {"early": "HAC files it under “{name}”", "middle": "HAC category “{name}”", "older": "HAC category “{name}”"},
    "type.why.canvas":      {"early": "Canvas files it under “{name}”", "middle": "Canvas group “{name}”", "older": "Canvas group “{name}”"},
    "type.why.name":        {"early": "from its name", "middle": "from its name", "older": "from its name"},
    "type.why.default":     {"early": "nothing says, so everyday work", "middle": "no type named; read as everyday work", "older": "no type named; read as everyday work"},
```

- [ ] **Step 4: Say it on the row**

In `_item.html`, replace line 39–40:

```jinja
{% set line_kind = item.kind if item.kind in ('paper', 'outside Canvas') else '' %}
{% set type_word = ('type.' ~ item.family) | say(tier) if item.family is defined and item.family and item.family != 'practice' else '' %}
{% set line_meta = [line_kind, type_word, due_text] | select | join(' · ') %}
```

In the card head (line 59), after `{% if item.kind in ('paper', 'outside Canvas') %} · {{ item.kind }}{% endif %}` insert:

```jinja
{% if item.family is defined and item.family and item.family != 'practice' %} · {{ ('type.' ~ item.family) | say(tier) }}{% endif %}
```

- [ ] **Step 5: The sheet and the MCP server**

`fridgesheet/open_items.py`:
1. `from . import work_types` (beside the other package imports).
2. `Item`: add `family: str = "practice"` after `is_assessment`.
3. Canvas builder (`:333-340`): before `it = Item(`, compute
   `typed = work_types.family_of(work_types.Facts(a["name"], canvas_group=a.get("group"), hac_category=(hac_row or {}).get("category"), online_quiz="online_quiz" in (a.get("submission_types") or [])))`
   and pass `is_assessment=typed.family == "assessment", family=typed.family,` in place of the existing `is_assessment=…`.
4. HAC builder (`:381-385`): `typed = work_types.family_of(work_types.Facts(a["name"], hac_category=a.get("category")))`, and the same two keyword arguments.
   (No rules or corrections here: this path is the snapshot alone, which already ignores the app's flags.)

`fridgesheet/reports/open_work.py:62`: add `family=v.family,` after `is_assessment=v.is_assessment,`.

`fridgesheet/sheet.py:164`:

```python
        word = phrasing.phrase(f"type.{it.family}", ks.tier) if it.family != "practice" else ""
        via = it.source.capitalize() + (f" · {it.kind}" if it.kind else " · —") + (f" · {word}" if word else "")
```

`fridgesheet/server.py:229-232`: docstring "Sorted with assessments first" becomes "Sorted tests and quizzes first, then labs and projects, everyday work, participation; then by points."; the sort becomes `rows.sort(key=lambda r: (work_types.RANK.get(r["family"], len(work_types.RANK)), -(r["points"] or 0)))` with `from . import work_types` added to the imports.

- [ ] **Step 6: Run the tests**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py tests/test_work_types_sheet.py tests/test_sheet_table.py tests/test_sheet.py tests/test_phrasing.py tests/test_web_tier_parity.py tests/test_web_tier_wording.py tests/test_server_tools.py tests/test_open_items.py -q -p no:cacheprovider`
Expected: all PASS. If `test_phrasing.py::test_the_table_covers_the_words_a_child_actually_meets` or a tier-parity test enumerates template words, add the new keys where that test expects them rather than weakening it.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet tests
git commit -m "Assignment types: the family's word on every row and the printed sheet, and the MCP server's order"
```

---

### Task 5: The type filter on the kid and class pages

**Files:**
- Create: `fridgesheet/web/templates/_type_links.html`
- Modify: `fridgesheet/web/routes/kid.py` (`_filters`, `_sort_base`, `kid`, `course`, new `type_links`)
- Modify: `fridgesheet/web/templates/kid.html` (above the weekly pages), `course.html:147-148` (inside the Assignments section head)
- Test: `tests/test_web_work_types_pages.py` (append)

**Interfaces:**
- Consumes: `items.list_items(family=)`, `items.FAMILY_FILTER` (Task 3); `copy.type_*` keys (Task 4).
- Produces: `kid.type_links(base: str, params: list[tuple[str, str]], counts: dict[str, int], current: str | None) -> list[dict]` with keys `key` (phrasing key), `n`, `href`, `current: bool`.

- [ ] **Step 1: Write the failing tests (append)**

```python
def test_the_type_filter_shows_one_family_and_counts_each(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    c = app_for(tmp_path)
    page = c.get("/kids/Alex?show=all&type=assessment").text
    assert "Quiz 1" in page and "Essay draft" not in page
    links = re.search(r'<p class="type-links">(.*?)</p>', page, re.S).group(1)
    assert re.search(r"Tests &amp; quizzes\D*1", links) and re.search(r"Labs &amp; projects\D*1", links)
    assert 'aria-current="true"' in links


def test_the_type_filter_combines_with_outcome(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    page = app_for(tmp_path).get("/kids/Alex?type=assessment&outcome=not_done").text
    assert "Quiz 1" in page                                   # missing, so not done
    assert "Homework 4" not in page                           # not done, but everyday work


def test_an_unknown_type_is_ignored(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    c = app_for(tmp_path)
    assert c.get("/kids/Alex?show=all&type=bogus").text.count('id="row-') == c.get("/kids/Alex?show=all").text.count('id="row-')


def test_the_class_page_filters_by_type_too(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND name LIKE '%English%'").fetchone()["id"]
    page = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}?type=lab_project").text
    assert "Lab notebook" in page and "Quiz 1" not in page
```

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py -q -p no:cacheprovider`
Expected: the four new tests FAIL.

- [ ] **Step 3: Read `?type=` and build the links**

In `fridgesheet/web/routes/kid.py`:

`_filters`: add `"family": q.get("type") if q.get("type") in items.FAMILY_FILTER else None,`.
`_sort_base`: add `("type", f["family"])` to the tuple of `(name, value)` pairs.

Add:

```python
def type_links(base: str, params: list[tuple[str, str]], counts: dict[str, int], current: str | None) -> list[dict]:
    """The type filter as a row of links with counts (spec 2026-10-04 assignment types §6.3),
    in the dashboard's outcome-link style: All, then each family that has work, keeping every
    other filter in force."""
    keep = [(k, v) for k, v in params if k != "type" and v not in (None, "")]
    def href(family: str | None) -> str:
        q = keep + ([("type", family)] if family else [])
        return f"{base}?{urlencode(q)}" if q else base
    out = [{"key": "copy.type_all", "n": sum(counts.values()), "href": href(None), "current": current is None}]
    out += [{"key": f"copy.type_{fam}", "n": counts[fam], "href": href(fam), "current": current == fam}
            for fam in sorted(counts, key=work_types.RANK.__getitem__) if counts[fam]]
    return out
```

with `from ... import grading, guidance, sources, work_types` and `from collections import Counter`.

In `kid(...)`: `f` now carries `family`; `list_items(**f)` filters by it. After `listed = …`, compute

```python
    unfiltered = listed if not f["family"] else items.list_items(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window(), **{**f, "show": "all", "family": None})
    counts = Counter(v.family for v in unfiltered)
```

(`listed` is the "all" list under the other filters; with a type in force it is already narrowed, so the counts take one more call.) Pass `type_links=type_links(f"/kids/{quote(key)}", [(k, str(v)) for k, v in _sort_base_params(f)], counts, f["family"])` to `render`, where `_sort_base_params(f)` is the list `_sort_base` already builds; extract that list into `_sort_base_params(f) -> list[tuple[str, object]]` and have `_sort_base` call it, so the two cannot drift.

In `course(...)`: read `family = request.query_params.get("type") if request.query_params.get("type") in items.FAMILY_FILTER else None`; build `every = items.list_items(..., show="all", course_id=course_id, sort=sort, direction=direction, prefs=prefs)` as today, then `rows = [v for v in every if not family or v.family == family]`, `counts = Counter(v.family for v in every)`, and pass `type_links=type_links(f"/kids/{quote(key)}/courses/{course_id}", [("sort", sort), ("dir", direction)], counts, family)`. Make the class page's `sort_base` carry the type: `f"/kids/{quote(key)}/courses/{course_id}?" + (f"type={family}&" if family else "")`.

- [ ] **Step 4: The link row**

```jinja
{# fridgesheet/web/templates/_type_links.html
   The type filter (spec 2026-10-04 assignment types §6.3): All, then each family with work,
   counts beside; the one in force is marked for screen readers and drawn as current. #}
{% if type_links is defined and type_links | length > 2 %}
<p class="type-links">{% for l in type_links %}{% if not loop.first %} · {% endif %}<a href="{{ l.href }}"{% if l.current %} aria-current="true" class="current"{% endif %}>{{ l.key | say(tier) }} {{ l.n }}</a>{% endfor %}</p>
{% endif %}
```

(`> 2`: All plus one family is no choice at all.) `tier` must be defined where it is included; on `kid.html` use `{% set tier = student.key | tier_of %}` if the page has not set it already (grep `set tier` in `kid.html` first).

Include it in `kid.html` directly above the weekly pages' container (the element the filters' form targets; grep `id="items"` in `kid.html`), and in `course.html` just inside `<section class="sec class-work">`, after its `sec-head`.

Add to `fridgesheet/web/static/app.css` beside the outcome-line rule (grep `.outcome-line`): `.type-links a.current { font-weight: 600; text-decoration: none; }`.

- [ ] **Step 5: Run the tests**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py tests/test_web_kid_table.py tests/test_web_class_page.py tests/test_web_course_filter.py tests/test_web_weekly_pages.py tests/test_web_page_layout.py tests/test_web_section_and_card.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet tests
git commit -m "Assignment types: a type filter with counts on the kid and class pages, combining with the others"
```

---

### Task 6: Correcting a type, and class rules

**Files:**
- Create: `fridgesheet/web/templates/_type_form.html`
- Modify: `fridgesheet/web/templates/_item.html` (detail density, before `{% if is_detail %}{% include "_record.html" %}{% endif %}`)
- Modify: `fridgesheet/web/routes/kid.py` (`item_detail` context; new `POST /items/{item_id}/type`; class page rules; `POST /kids/{key}/courses/{course_id}/type-rules/{rule_id}/remove`)
- Modify: `fridgesheet/web/templates/course.html` (a "Type rules" section after "What moves it")
- Test: `tests/test_web_work_types_pages.py` (append)

**Interfaces:**
- Consumes: `type_store.facts_for`, `set_correction`, `clear_correction`, `add_rule`, `remove_rule`, `rule_reach`, `rules_for`, `pair` (Task 3); `work_types.family_of`, `gradebook_name`, `is_generic`, `prefix_suggestion`, `fold` (Task 1); `webapp.who_of`, `webapp.FAMILY`.
- Produces: `type_offer(conn, s, v) -> dict` in `kid.py` with keys `group` (str|None), `group_n` (int), `group_generic` (bool), `prefix` (str|None), `prefix_n` (int).

- [ ] **Step 1: Write the failing tests (append)**

```python
def _post_type(c, iid, **form):
    return c.post(f"/items/{iid}/type", data=form)


def test_a_grown_up_corrects_one_item(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    iid = _item_ids(conn)["Essay draft"]
    c = app_for(tmp_path)
    detail = c.get(f"/items/{iid}").text
    assert "Type:" in detail and 'name="family"' in detail
    r = _post_type(c, iid, family="lab_project")
    assert r.status_code == 200 and "lab/project" in r.text
    assert conn.execute("SELECT family FROM item_types WHERE item_id = ?", (iid,)).fetchone()["family"] == "lab_project"


def test_choosing_the_guess_again_clears_the_correction(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    iid = _item_ids(conn)["Essay draft"]
    c = app_for(tmp_path)
    _post_type(c, iid, family="lab_project")
    _post_type(c, iid, family="practice")                    # what the ladder says anyway
    assert conn.execute("SELECT COUNT(*) FROM item_types").fetchone()[0] == 0


def test_a_correction_can_become_a_class_rule(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    ids = _item_ids(conn)
    c = app_for(tmp_path)
    detail = c.get(f"/items/{ids['Essay draft']}").text
    assert re.search(r"applies to 4 items", detail)        # group "Homework": the 4 English items left in it
    _post_type(c, ids["Essay draft"], family="participation", also_group="1")
    page = c.get("/kids/Alex?show=all&type=participation").text
    assert "Reading log" in page and "Worksheet 3" in page   # the rule reached the rest of the group
    assert conn.execute("SELECT COUNT(*) FROM item_types").fetchone()[0] == 0   # the rule covers it


def test_a_generic_group_rule_is_only_for_everyday_work(tmp_path):
    snap = _quiz_snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"][1]["group"] = "Assignments"
    conn = seed(tmp_path, snap)
    iid = _item_ids(conn)["Essay draft"]
    r = _post_type(app_for(tmp_path), iid, family="assessment", also_group="1")
    assert conn.execute("SELECT COUNT(*) FROM type_rules").fetchone()[0] == 0
    assert "only for everyday work" in r.text
    assert conn.execute("SELECT family FROM item_types WHERE item_id = ?", (iid,)).fetchone()["family"] == "assessment"


def test_the_class_page_lists_its_rules_and_removes_one(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    ids = _item_ids(conn)
    c = app_for(tmp_path)
    _post_type(c, ids["Essay draft"], family="participation", also_group="1")
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND name LIKE '%English%'").fetchone()["id"]
    page = c.get(f"/kids/Alex/courses/{cid}").text
    assert "Type rules" in page and "homework" in page.lower()
    rule = conn.execute("SELECT id FROM type_rules").fetchone()["id"]
    r = c.post(f"/kids/Alex/courses/{cid}/type-rules/{rule}/remove", follow_redirects=False)
    assert r.status_code == 303 and conn.execute("SELECT COUNT(*) FROM type_rules").fetchone()[0] == 0


def test_a_child_cannot_correct_a_type(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    iid = _item_ids(conn)["Essay draft"]
    c = app_for(tmp_path)
    c.cookies.set(webapp.WHO_COOKIE, "Alex")
    assert 'name="family"' not in c.get(f"/items/{iid}").text
    assert _post_type(c, iid, family="assessment").status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM item_types").fetchone()[0] == 0
```

Before trusting the counts: in the fixture Alex's Canvas English course has six items, all group "Homework"; `_quiz_snapshot` moves Quiz 1 and Lab notebook out, leaving four (Essay draft, Reading log, Worksheet 3, Vocabulary). If the fixture differs when you run it, recount and correct the expectation, not the code.

- [ ] **Step 2: Run them to verify they fail**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py -q -p no:cacheprovider`
Expected: the six new tests FAIL (404 on the POST; no form).

- [ ] **Step 3: The offer, the routes**

In `fridgesheet/web/routes/kid.py`:

```python
from ..app import FAMILY, who_of
from ..stores import work_types as type_store


def type_offer(conn: sqlite3.Connection, s, v) -> dict:
    """What the correction form can offer beyond this item (spec 2026-10-04 assignment types
    §6.4): pin the gradebook name, or the name's prefix, for the whole class, each with how many
    items it applies to. A prefix is offered only when it reaches two items besides this one."""
    facts = type_store.facts_for(conn, v.id)
    group = work_types.gradebook_name(facts)
    prefix = work_types.prefix_suggestion(v.name)
    prefix_n = type_store.rule_reach(conn, s["id"], v.course_id, "name_prefix", prefix) if prefix else 0
    return {"group": group, "group_generic": work_types.is_generic(group),
            "group_n": type_store.rule_reach(conn, s["id"], v.course_id, "group", group) if group else 0,
            "prefix": prefix if prefix_n >= 3 else None, "prefix_n": prefix_n}


def _grown_up(request: Request, conn: sqlite3.Connection) -> bool:
    return who_of(request, conn)[0] == FAMILY
```

In `item_detail`, add to the `render_partial` context: `type_offer=type_offer(conn, s, v) if _grown_up(request, conn) else None`.

```python
@router.post("/items/{item_id}/type")
def set_item_type(item_id: int, request: Request, family: str = Form(...), also_group: str = Form(""),
                  also_prefix: str = Form(""), card: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """A grown-up's type for one item, and optionally a class rule made from it. A rule on a
    generic bucket ("Assignments") is only for everyday work: pinning a whole class's catch-all
    to tests would relabel every worksheet. The item's own correction is dropped whenever the
    ladder (rules included) already gives the chosen family, so nothing redundant is stored."""
    if not _grown_up(request, conn):
        raise HTTPException(403, "a grown-up sets types")
    s = students.owner_of_item(conn, item_id)
    if s is None:
        raise HTTPException(404, "no such item")
    if family not in work_types.FAMILIES:
        raise HTTPException(400, f"unknown type {family!r}")
    now_s, now, rules = db.now_iso(state.tz), state.now(), state.rules()
    v = items.one(conn, s, item_id, now=now, rules=rules, prefs=state.sources(), **state.window())
    offer = type_offer(conn, s, v)
    message = "Type saved"
    with conn:
        if also_group and offer["group"]:
            if offer["group_generic"] and family != "practice":
                message = f"Saved for this item only: a rule on “{offer['group']}” is only for everyday work."
            else:
                type_store.add_rule(conn, v.course_id, "group", offer["group"], family, now_s)
        if also_prefix and offer["prefix"]:
            type_store.add_rule(conn, v.course_id, "name_prefix", offer["prefix"], family, now_s)
        type_store.clear_correction(conn, item_id)
        guess = items.one(conn, s, item_id, now=now, rules=rules, prefs=state.sources(), **state.window())
        if guess.family != family:
            type_store.set_correction(conn, item_id, family, now_s)
    v = items.one(conn, s, item_id, now=now, rules=rules, prefs=state.sources(), **state.window())
    return render_partial(request, conn, "_item_detail.html", student=s, item=v,
                          item_history=changes.for_item(conn, s["id"], item_id, now=now, prefs=state.sources()), message=message,
                          notes=notes.for_target(conn, "item", item_id), card=card_for(card, item_id),
                          type_offer=type_offer(conn, s, v))


@router.post("/kids/{key}/courses/{course_id}/type-rules/{rule_id}/remove")
def remove_type_rule(key: str, course_id: int, rule_id: int, request: Request, conn: sqlite3.Connection = Db):
    if not _grown_up(request, conn):
        raise HTTPException(403, "a grown-up sets types")
    s = student_or_404(conn, key)
    c = students.course(conn, course_id)
    if c is None or c["student_id"] != s["id"]:
        raise HTTPException(404, "no such course")
    rule = conn.execute("SELECT course_id FROM type_rules WHERE id = ?", (rule_id,)).fetchone()
    if rule is None or rule["course_id"] not in type_store.pair(conn, course_id):
        raise HTTPException(404, "no such rule")
    with conn:
        type_store.remove_rule(conn, rule_id)
    return RedirectResponse(f"/kids/{quote(key)}/courses/{course_id}", status_code=303)
```

Add `from .. import actions, db, outcomes`. In `course(...)` pass `type_rules=type_store.rules_for(conn, type_store.pair(conn, course_id))` and `grown_up=_grown_up(request, conn)`.

Note the `with conn:` blocks: the connection is autocommit (`isolation_level=None`), so `with conn` does not open a transaction by itself; match what `flags.set_flag` callers do (grep `with conn` in `routes/flags.py` and `stores/flags.py`) and drop the `with` if they write bare.

- [ ] **Step 4: The form and the type line**

```jinja
{# fridgesheet/web/templates/_type_form.html
   A grown-up's type for this item (spec 2026-10-04 assignment types §6.4): the family, why the
   app gave it, and Change; the class-wide checkboxes say how many items each would reach. #}
<div class="type-line">
  <p>Type: {{ ('copy.type_' ~ item.family) | say('') }} · <span class="muted">{{ item.family_why | say('', item.family_values) }}</span></p>
  {% if type_offer %}
  <details><summary>Change</summary>
    <form hx-post="/items/{{ item.id }}/type" hx-target="closest .item" hx-swap="outerHTML">
      <input type="hidden" name="card" value="{{ card }}">
      <fieldset><legend>This is</legend>
        {% for fam in ('assessment', 'practice', 'lab_project', 'participation') %}
        <label><input type="radio" name="family" value="{{ fam }}" {{ 'checked' if item.family == fam }}> {{ ('copy.type_' ~ fam) | say('') }}</label>
        {% endfor %}
      </fieldset>
      {% if type_offer.group %}<label><input type="checkbox" name="also_group" value="1"> Also every item in {{ item.course_short }} filed under “{{ type_offer.group }}”{% if type_offer.group_generic %} (everyday work only){% endif %} <span class="muted">· applies to {{ type_offer.group_n }} item{{ 's' if type_offer.group_n != 1 }}</span></label>{% endif %}
      {% if type_offer.prefix %}<label><input type="checkbox" name="also_prefix" value="1"> Also every item in {{ item.course_short }} whose name starts with “{{ type_offer.prefix }}” <span class="muted">· applies to {{ type_offer.prefix_n }} items</span></label>{% endif %}
      <button>Save</button>
    </form>
  </details>
  {% endif %}
</div>
```

In `_item.html`, at detail density, immediately before `{% if is_detail %}{% include "_record.html" %}{% endif %}`:

```jinja
  {% if is_detail and type_offer is defined and type_offer is not none %}{% include "_type_form.html" %}{% endif %}
```

Check the htmx target against the flag menu's form in `_flag_menu.html` (it replaces the detail card); copy its `hx-target`/`hx-swap` exactly rather than `closest .item` if they differ, so a saved type and a saved flag behave the same.

- [ ] **Step 5: The class page's rules**

In `course.html`, after the "What moves it" section and before `<section class="sec class-work">`:

```jinja
{# Type rules (spec 2026-10-04 assignment types §6.4): made from a correction, listed here,
   one Remove each. Shown only when the class has any. #}
{% if type_rules %}
<section class="sec type-rules">
  <div class="sec-head"><h3>Type rules</h3><span class="count">{{ type_rules | length }}</span></div>
  <ul>{% for r in type_rules %}<li>{{ 'Filed under' if r.field == 'group' else 'Name starts with' }} “{{ r.value }}” → {{ ('copy.type_' ~ r.family) | say('') }}{% if grown_up %} <form method="post" action="/kids/{{ student.key | urlencode }}/courses/{{ course.id }}/type-rules/{{ r.id }}/remove" class="inline"><button class="link">Remove</button></form>{% endif %}</li>{% endfor %}</ul>
</section>
{% endif %}
```

- [ ] **Step 6: Run the tests**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py tests/test_web_class_page.py tests/test_web_actions.py tests/test_web_harden.py tests/test_web_a11y.py tests/test_web_section_and_card.py tests/test_web_who.py -q -p no:cacheprovider`
Expected: all PASS. `test_web_harden.py` checks every POST route for same-origin handling; if it enumerates routes, the two new ones must be listed the way `/items/{item_id}/flag` is.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet tests
git commit -m "Assignment types: a grown-up corrects an item's type, optionally for the whole class, and the class page lists the rules"
```

---

### Task 7: Diagnostics coverage

**Files:**
- Modify: `fridgesheet/web/routes/diagnostics.py`
- Modify: `fridgesheet/web/templates/diagnostics.html` (a section after the doctor's lines)
- Test: `tests/test_web_work_types_pages.py` (append)

**Interfaces:**
- Consumes: `items.list_items`, `ItemView.family_rung`, `course_short` (Task 3); `work_types.coverage` (Task 1).
- Produces: `type_coverage(conn, state) -> list[dict]` with `kid`, `course`, `n`, `rungs: dict[int, int]`.

- [ ] **Step 1: Write the failing test (append)**

```python
def test_diagnostics_shows_how_each_class_was_typed(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    page = app_for(tmp_path).get("/diagnostics").text
    sec = re.search(r'<section class="sec type-coverage">(.*?)</section>', page, re.S).group(1)
    assert "Types" in sec and ("ENG" in sec or "English" in sec)
    assert re.search(r"Everyday by default", sec)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py::test_diagnostics_shows_how_each_class_was_typed -q -p no:cacheprovider`
Expected: FAIL (no section).

- [ ] **Step 3: Build it**

In `fridgesheet/web/routes/diagnostics.py`:

```python
from collections import defaultdict

from ... import work_types
from ..stores import items, students


def type_coverage(conn: sqlite3.Connection, state) -> list[dict]:
    """Per kid and class, which ladder rung typed each item (spec 2026-10-04 assignment types
    §6.5). A class typed wholly "by default" is one whose names defeat the classifier: the cue
    for a grown-up to add a rule."""
    out = []
    for s in students.visible(conn):
        views = items.list_items(conn, s, now=state.now(), rules=state.rules(), prefs=state.sources(), show="all", **state.window())
        by_class = defaultdict(list)
        for v in views:
            by_class[v.course_short].append(v)
        for course, vs in sorted(by_class.items()):
            rungs = {r: 0 for r in range(1, 7)}
            for v in vs:
                rungs[v.family_rung] += 1
            out.append({"kid": s["key"], "course": course, "n": len(vs), "rungs": rungs})
    return out
```

and pass `types=type_coverage(conn, state)` to `render`.

In `diagnostics.html`, after the section that lists the doctor's lines:

```jinja
{# How each class's work was typed (spec 2026-10-04 assignment types §6.5). #}
{% if types %}
<section class="sec type-coverage">
  <div class="sec-head"><h3>Types</h3><span class="count">{{ types | length }} classes</span></div>
  <table class="items"><thead><tr><th>Kid</th><th>Class</th><th class="num">Items</th><th class="num">You set</th><th class="num">Your rules</th><th class="num">Canvas quiz</th><th class="num">Gradebook name</th><th class="num">Item name</th><th class="num">Everyday by default</th></tr></thead>
  <tbody>{% for t in types %}<tr><td>{{ t.kid | nickname }}</td><td>{{ t.course }}</td><td class="num">{{ t.n }}</td>{% for r in range(1, 7) %}<td class="num">{{ t.rungs[r] }}</td>{% endfor %}</tr>{% endfor %}</tbody></table>
  <p class="field-help">“Everyday by default” means nothing named a type. A class where that is every item has names the app cannot read: correct one item there and make it a rule.</p>
</section>
{% endif %}
```

Check that `nickname` is a filter in the Jinja env (`grep -n '"nickname"' fridgesheet/web/app.py`); use `t.kid` plain if not.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ../3c8edee2/.venv/bin/python -m pytest tests/test_web_work_types_pages.py tests/test_web_diagnostics_page.py tests/test_web_diagnostics_planner.py tests/test_web_page_layout.py -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet tests
git commit -m "Assignment types: Diagnostics shows how each class's work was typed"
```

---

### Task 8: Spec amendments, the full suite, the PR

**Files:**
- Modify: `docs/superpowers/specs/2026-10-04-assignment-types-design.md`

- [ ] **Step 1: Amend the spec to what main and this build are**

- §1, "The weights are points": add "Since #254 the scraper also reads HAC's six-column category table, so a weighted class's categories carry their weight (`grading.Line.weight`, basis `weighted`)."
- §5: "schema 12" → "schema 14" (heading and text); "(12 is HAC's category weights, #254; 13 is Reset, #258)".
- §6.2: replace "prints the same word where it prints the assessment mark today, and sorts by family rank (§7.1) in place of `not is_assessment`" with "adds the word to the row's Via cell ("Canvas · paper · test/quiz"); the sheet had no assessment mark before. The MCP server's `missing_work` sorts by family rank (`work_types.RANK`) where it sorted by `is_assessment`."
- §6.4: "changes N items" → "applies to N items" (the count of items the rule matches, both courses of the class); "less than two other items" stays as "reaches two items besides this one".
- §7.2: replace the Share row with "Σ over the family's rows of (row possible ÷ its category's possible) × that category's line share: in a straight-points class this is family possible ÷ total possible; in a weighted class it carries each category's weight."
- §4.1: the module is `fridgesheet/work_types.py` (not `types.py`, which would shadow the standard library's `types` that tests import).

- [ ] **Step 2: Run the whole suite**

```bash
V=$(ls -d ../*/.venv | head -1)
env -u PYTHONPATH $V/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee /tmp/fridgesheet-assignment-types-pr1.log | tail -5
```

Expected: every test passes. `test_rebrand` scans every tracked file, so `git add` new files first.

- [ ] **Step 3: Look at it in the browser**

Start the app from this worktree (memory: running outside the worktree serves main's code) on the audit port, seed from the prod snapshot copy at `/tmp/fridgesheet-prod-snapshot.json`, and check: a kid page shows test/quiz and lab/project words; the type link row counts; a correction with a rule changes the class; Diagnostics shows coverage. Use the venv's Playwright (memory: MCP Chrome is usually locked). Kill the server in its own Bash call.

- [ ] **Step 4: Commit, push, open the PR, arm auto-merge**

```bash
git add docs/superpowers/specs/2026-10-04-assignment-types-design.md
git commit -m "Assignment types spec: schema 14, the sheet's Via word, applies-to counts, the weighted share formula"
gh pr list --search "items.py" --state open      # coordinate with anything touching the same files
git push -u origin viberpit/assignment-types
gh pr create --title "Assignment types: every item is a test or quiz, everyday work, a lab or project, or participation, inferred from the gradebooks' names, corrected by a grown-up per item or per class, shown on rows and the sheet, filtered on the kid and class pages, and audited in Diagnostics" --body-file /tmp/assignment-types-pr1-body.md
gh pr merge --auto --squash
```

The PR body (written to `/tmp/assignment-types-pr1-body.md`) summarises §1's probe numbers, the ladder, schema 14, what each page gains, the test files, and ends with the attribution line from the session's instructions.

---

## Self-Review

- **Spec coverage.** §4.1 keywords → Task 1; §4.2 ladder → Task 1; §4.3 coverage → Tasks 1 and 7; §5.1 migration and fold → Task 2; §5.2 rule matching → Task 1 (`_rule_order`, `matches`) and Task 3 (pairs); §6.1 reading → Task 3; §6.2 word and sheet → Task 4; §6.3 filter → Task 5; §6.4 correcting and rules list → Task 6; §6.5 Diagnostics → Task 7; §9's tests for these sections → Tasks 1–7; spec corrections → Task 8. §7 and §8 are PRs 2 and 3.
- **Placeholders.** Three steps ask the implementer to look something up before writing (the late-rules object in Task 3, a sheet-table helper in Task 4, the flag menu's htmx target in Task 6); each says what to grep and what to do with the answer.
- **Type consistency.** `Typed(family, rung, why, values)` is used by `ItemView.family/family_rung/family_why/family_values`; `work_types.matches` (renamed in Task 3 Step 3) is used by `rule_reach`; `type_store` is the alias for `web/stores/work_types.py` everywhere; `items.FAMILY_FILTER` is used by `kid._filters` and `course`.
- **Review Focus.** All five lines have tests in their owning tasks (Tasks 2, 3, 5, 6).

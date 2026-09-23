# Source of Truth for Grades and Assignments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a family choose Canvas or HAC as the authoritative source for assignment scores and for class averages, with a household default and per-kid / per-class override rules.

**Architecture:** A new pure module `fridgesheet/sources.py` parses a `[sources]` table from `config.toml` into a frozen `SourcePrefs` and resolves `(kid, course) -> Choice(assignments, grades)`. Ingest is untouched; every read-time place that picks one source's value (outcome classification, grade/status cells, the printed sheet, MCP tools, course-page average, trends, changes, report builder) takes an optional `prefs` / `prefer` argument whose default reproduces today's behaviour exactly. The Settings page edits the defaults; the course page writes one kid+class rule.

**Tech Stack:** Python 3.11+, FastAPI + Jinja2 + htmx, SQLite (stdlib), `tomllib` / `tomli_w`, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-source-of-truth-design.md`

## Global Constraints

- Values are exactly `"canvas"` or `"hac"`; built-in defaults are `assignments = "canvas"`, `grades = "hac"`.
- A bad value in `[sources]` logs a warning and is treated as unset. Loading config never fails because of `[sources]`.
- Each field (`assignments`, `grades`) resolves independently: first matching rule that sets that field, else household default, else built-in default.
- Ingest (`fridgesheet/web/ingest.py`) and the database schema do not change.
- Submitted / late / excused / unpublished always come from Canvas regardless of preference.
- Every new `prefs=` / `prefer=` parameter defaults to today's behaviour (`None` / `"canvas"`), so each task leaves the suite green on its own.
- `reconcile.cases` kind `"disagree"` is unchanged: a rule picks the headline, it never hides a disagreement.
- Config is written only through `config.save_config_doc` (atomic, mode 0600).
- Run tests with `env -u PYTHONPATH python3 -m pytest` from the worktree root (there is no `.venv` in this worktree; `PYTHONPATH` shadows the `tests` package).
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Deviations from the spec (decided while planning)

- **Rules match courses on whole words.** The spec reused late-rules' plain substring match. Plain substring lets a rule for `Algebra I` also catch `Algebra II`, and a source rule silently flipping a second class's grades is worse than a late-days rule doing it. `SourceRule` matches the pattern only where it is bounded by non-alphanumerics. Late rules keep their current behaviour.
- **The course-page control writes the class's short name**, not the Canvas full name. The full Canvas name (`Honors Algebra II S1-2027-Hoch`) is not a substring of the paired HAC name (`Honors Algebra II - 3`), so a rule written from it would miss every HAC-only row in that class. The short name is contained in both.
- **The sheet resolves the kid by first name, not by printed label.** `open_items` receives the nickname as `kid`; a rule for `Douglas` must still apply when the sheet prints `Dougie`.

## Review Focus

1. **A rule for `Algebra I` must not apply to `Algebra II`.** Pinned in Task 1 (`test_course_pattern_matches_whole_words_only`).
2. **A rule written from the course page must apply to HAC-only rows of that class**, whose course name is HAC's. Pinned in Task 1 (`test_short_name_rule_matches_both_sources_names`) and Task 9.
3. **Hand-edited junk in `[sources]`** (`sources = "hac"`, `rule = 3`, `grades = "HAC "`, `assignments = "powerschool"`) must load, warn, and fall back. Pinned in Task 1 and Task 2.
4. **Saving the main Settings form must not wipe override rules.** Pinned in Task 8 (`test_saving_the_form_keeps_rules`).
5. **HAC preference with a HAC zero and a Canvas score** must read as not done, both in the app and on the printed sheet. Pinned in Task 3 and Task 5.

## File Map

| File | Change | Responsibility |
|---|---|---|
| `fridgesheet/matching.py` | modify | shared `kid_matches`, `course_matches` |
| `fridgesheet/late_rules.py` | modify | use the shared matchers (behaviour unchanged) |
| `fridgesheet/sources.py` | create | `Choice`, `SourceRule`, `SourcePrefs`, `from_doc`, `pick_value` |
| `fridgesheet/config.py` | modify | `Settings.sources`, parsed in `settings_from_doc` |
| `fridgesheet/web/outcomes.py` | modify | `classify(..., prefer=)` |
| `fridgesheet/web/reconcile.py` | modify | `open_sources` / `is_actionable` / `cases` / `actionable_items` take preference |
| `fridgesheet/web/stores/items.py` | modify | `grade_text` / `status_text` take `prefer`; views thread `prefs` |
| `fridgesheet/web/stores/trends.py` | modify | outcomes and open-days take `prefs`; `GradeSeries.official` |
| `fridgesheet/web/stores/changes.py` | modify | grade events mark the official source |
| `fridgesheet/web/views.py` | modify | `build(..., prefs=)`; grades `official` column |
| `fridgesheet/web/app.py` | modify | `AppState.sources()` |
| `fridgesheet/web/routes/*.py` | modify | pass `prefs=state.sources()` |
| `fridgesheet/open_items.py` | modify | `open_items(..., prefs=)` |
| `fridgesheet/reports/open_work.py`, `fridgesheet/server.py` | modify | pass prefs; MCP `grades()` gains `official` |
| `fridgesheet/web/actions.py`, `routes/settings.py`, `templates/settings.html` | modify | default dropdowns, rule list, remove |
| `fridgesheet/web/routes/kid.py`, `templates/course.html` | modify | official average headline; per-class control |
| `docs/outcomes.md`, `README.md` | modify | documentation |

---

### Task 1: The resolver (`sources.py`) and shared matchers

**Files:**
- Modify: `fridgesheet/matching.py` (append after `short_course`, line 73)
- Modify: `fridgesheet/late_rules.py:73-80` (`Rule.matches`)
- Create: `fridgesheet/sources.py`
- Test: `tests/test_sources.py` (create)

**Interfaces:**
- Consumes: `matching.short_course(name) -> str`
- Produces:
  - `matching.kid_matches(pattern: str, kid: str) -> bool`
  - `matching.course_matches(pattern: str, course: str, *, whole_words: bool = False) -> bool`
  - `sources.SOURCES = ("canvas", "hac")`, `sources.LABELS = {"canvas": "Canvas", "hac": "HAC"}`
  - `sources.Choice(assignments: str = "canvas", grades: str = "hac")` (frozen)
  - `sources.SourceRule(kid="", course="", assignments: str|None = None, grades: str|None = None)` with `.matches(kid, course) -> bool`, `.targets(kid, course) -> bool`
  - `sources.SourcePrefs(default: Choice = Choice(), rules: tuple[SourceRule, ...] = ())` with `.resolve(kid, course) -> Choice`, `.deciding_rule(kid, course, field) -> SourceRule | None`, `.rule_for(kid, course) -> SourceRule | None`, `.with_rule(kid, course, assignments, grades) -> SourcePrefs`, `.without_rule(kid, course) -> SourcePrefs`, `.with_default(assignments, grades) -> SourcePrefs`, `.to_doc() -> dict`
  - `sources.DEFAULT = SourcePrefs()`
  - `sources.from_doc(doc: dict) -> SourcePrefs` (reads `doc["sources"]`)
  - `sources.assignments_for(prefs: SourcePrefs | None, kid: str, course: str) -> str`
  - `sources.pick_value(pick: str, canvas_value, hac_value) -> tuple[value, str | None]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sources.py`:

```python
"""Which source is authoritative, per family, kid and class (docs/superpowers/specs/2026-09-22-source-of-truth-design.md)."""
from __future__ import annotations

import logging
import tomllib

import tomli_w

from fridgesheet import sources
from fridgesheet.matching import course_matches, kid_matches


def prefs(text: str) -> sources.SourcePrefs:
    return sources.from_doc(tomllib.loads(text))


def test_no_table_means_canvas_assignments_hac_grades():
    p = sources.from_doc({})
    assert p.resolve("Alex", "Honors Biology S1-2027-Nance") == sources.Choice("canvas", "hac")
    assert p == sources.DEFAULT


def test_household_default_applies_everywhere():
    p = prefs('[sources]\nassignments = "hac"\ngrades = "canvas"\n')
    assert p.resolve("Sam", "Science 7 - 1") == sources.Choice("hac", "canvas")


def test_fields_resolve_independently():
    p = prefs('[sources]\n'
              '[[sources.rule]]\nkid = "Douglas"\ngrades = "canvas"\n\n'
              '[[sources.rule]]\ncourse = "Band"\nassignments = "hac"\n')
    assert p.resolve("Douglas", "Concert Band S1-2027-Desmond") == sources.Choice("hac", "canvas")
    assert p.resolve("Douglas", "Honors English 9") == sources.Choice("canvas", "canvas")
    assert p.resolve("Melanie", "Concert Band") == sources.Choice("hac", "hac")


def test_first_matching_rule_that_sets_the_field_wins():
    p = prefs('[sources]\n'
              '[[sources.rule]]\nkid = "Douglas"\ncourse = "Honors Algebra II"\nassignments = "hac"\n\n'
              '[[sources.rule]]\ncourse = "Honors Algebra II"\nassignments = "canvas"\ngrades = "canvas"\n')
    assert p.resolve("Douglas", "Honors Algebra II S1-2027-Ho") == sources.Choice("hac", "canvas")
    assert p.resolve("Kayla", "Honors Algebra II - 2") == sources.Choice("canvas", "canvas")


def test_kid_is_a_prefix_match_either_way():
    p = prefs('[[sources.rule]]\nkid = "Alex"\ngrades = "canvas"\n')
    assert p.resolve("Alexander", "X").grades == "canvas"
    assert p.resolve("Al", "X").grades == "canvas"
    assert p.resolve("Sam", "X").grades == "hac"


def test_course_pattern_matches_whole_words_only():
    """Review focus 1: a rule for Algebra I must never flip Algebra II's grades."""
    p = prefs('[[sources.rule]]\ncourse = "Algebra I"\ngrades = "canvas"\n')
    assert p.resolve("Alex", "Algebra I S1-2027-Lee").grades == "canvas"
    assert p.resolve("Alex", "Algebra I - 2").grades == "canvas"
    assert p.resolve("Alex", "Algebra II S1-2027-Hoch").grades == "hac"
    assert p.resolve("Alex", "Honors Algebra II - 3").grades == "hac"


def test_short_name_rule_matches_both_sources_names():
    """Review focus 2: the course-page control writes the short name; HAC-only rows carry HAC's name."""
    p = sources.DEFAULT.with_rule("Douglas", "Honors Algebra II", "hac", None)
    assert p.resolve("Douglas", "Honors Algebra II S1-2027-Hoch").assignments == "hac"
    assert p.resolve("Douglas", "Honors Algebra II - 3").assignments == "hac"


def test_bad_values_warn_and_fall_through(caplog):
    """Review focus 3: a typo in a preference must not take the app down."""
    caplog.set_level(logging.WARNING, logger="fridgesheet.sources")
    p = prefs('[sources]\nassignments = "powerschool"\ngrades = " HAC "\n'
              '[[sources.rule]]\ncourse = "Band"\ngrades = 7\n')
    assert p.default == sources.Choice("canvas", "hac")            # "HAC " is tolerated, powerschool is not
    assert p.resolve("Alex", "Band").grades == "hac"               # the rule's bad value is unset, not fatal
    assert "powerschool" in caplog.text and "7" in caplog.text


def test_wrong_shapes_are_ignored(caplog):
    caplog.set_level(logging.WARNING, logger="fridgesheet.sources")
    assert sources.from_doc({"sources": "hac"}) == sources.DEFAULT
    assert sources.from_doc({"sources": {"rule": 3}}) == sources.DEFAULT
    assert sources.from_doc({"sources": {"rule": [3, {"course": "Band", "grades": "canvas"}]}}).resolve("A", "Band").grades == "canvas"


def test_with_rule_replaces_rather_than_duplicates_and_all_default_removes():
    p = sources.DEFAULT.with_rule("Alex", "Band", "hac", None)
    p = p.with_rule("alex", "band", None, "canvas")
    assert len(p.rules) == 1 and p.rules[0].grades == "canvas" and p.rules[0].assignments is None
    assert p.with_rule("Alex", "Band", None, None).rules == ()
    assert p.without_rule("ALEX", "Band").rules == ()


def test_deciding_rule_names_what_is_in_force():
    p = prefs('[[sources.rule]]\nkid = "Alex"\ngrades = "canvas"\n')
    assert p.deciding_rule("Alex", "Band", "grades").kid == "Alex"
    assert p.deciding_rule("Alex", "Band", "assignments") is None
    assert p.rule_for("Alex", "Band") is None                     # only an exact kid+course rule


def test_to_doc_round_trips_through_toml():
    p = sources.DEFAULT.with_default("hac", "canvas").with_rule("Alex", "Band", "hac", None)
    doc = {"sources": p.to_doc()}
    assert sources.from_doc(tomllib.loads(tomli_w.dumps(doc))) == p
    assert "rule" not in sources.DEFAULT.to_doc()


def test_pick_value_prefers_then_fills_the_gap():
    assert sources.pick_value("hac", 91.2, 88.0) == (88.0, "hac")
    assert sources.pick_value("canvas", 91.2, 88.0) == (91.2, "canvas")
    assert sources.pick_value("hac", 91.2, None) == (91.2, "canvas")
    assert sources.pick_value("canvas", None, None) == (None, None)


def test_assignments_for_defaults_to_canvas_without_prefs():
    assert sources.assignments_for(None, "Alex", "Band") == "canvas"


def test_shared_matchers_keep_late_rules_semantics():
    assert kid_matches("", "anyone") and kid_matches("Alex", "Al") and not kid_matches("Alex", "Sam")
    assert course_matches("Algebra I", "Algebra II")                          # late rules: plain substring, unchanged
    assert not course_matches("Algebra I", "Algebra II", whole_words=True)
    assert course_matches("English 9", "Honors English 9 S1-2027-Hoch", whole_words=True)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_sources.py -q`
Expected: collection error, `ImportError: cannot import name 'sources' from 'fridgesheet'`.

- [ ] **Step 3: Add the shared matchers to `matching.py`**

Append after `short_course` (after line 73):

```python
def kid_matches(pattern: str, kid: str) -> bool:
    """A rule's kid against a student's first name: empty matches everyone; otherwise a prefix
    match either way, so "Alex" and "Alexander" (and a nickname "Al") are one kid."""
    if not pattern:
        return True
    a, b = pattern.lower(), (kid or "").lower()
    return a.startswith(b) or b.startswith(a)


def course_matches(pattern: str, course: str, *, whole_words: bool = False) -> bool:
    """A rule's course against a class name, or that name with its term/teacher tail removed.

    Empty matches every class. Late rules use a plain case-insensitive substring. Source rules
    ask for `whole_words`, so "Algebra I" does not also mean "Algebra II": a rule that flips
    which gradebook a class's grades come from must not reach a second class by accident."""
    if not pattern:
        return True
    p = pattern.lower().strip()
    names = ((course or "").lower(), short_course(course).lower())
    if not whole_words:
        return any(p in n for n in names)
    rx = re.compile(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])")
    return any(rx.search(n) for n in names)
```

- [ ] **Step 4: Make `late_rules.Rule.matches` use them (same behaviour)**

Replace `fridgesheet/late_rules.py:73-80` (the whole `matches` method) with:

```python
    def matches(self, kid: str, course: str) -> bool:
        return kid_matches(self.kid, kid) and course_matches(self.course, course)
```

and change the import on line 28 to:

```python
from .matching import course_matches, kid_matches
```

(`short_course` is no longer used directly in `late_rules.py`; check with `grep -n short_course fridgesheet/late_rules.py` and drop it from the import only if nothing else uses it.)

- [ ] **Step 5: Create `fridgesheet/sources.py`**

```python
"""Which source is authoritative: Canvas or HAC, for assignment scores and for class averages.

Both sources are always read and stored; this only decides which value is the headline when
both have one, and the other still fills gaps. Configured in config.toml:

    [sources]
    assignments = "canvas"        # household defaults (these are the built-in values)
    grades = "hac"

    [[sources.rule]]              # kid and course optional; first rule that sets a field wins
    kid = "Douglas"               #   prefix match either way (Alex ~ Alexander)
    course = "Honors Algebra II"  #   whole words of the class name or its short name
    assignments = "hac"

A bad value warns and is ignored: a typo in a preference must not take the app down.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from .matching import course_matches, kid_matches

log = logging.getLogger("fridgesheet.sources")

SOURCES = ("canvas", "hac")
LABELS = {"canvas": "Canvas", "hac": "HAC"}
FIELDS = ("assignments", "grades")


@dataclass(frozen=True)
class Choice:
    assignments: str = "canvas"
    grades: str = "hac"


@dataclass(frozen=True)
class SourceRule:
    kid: str = ""
    course: str = ""
    assignments: str | None = None
    grades: str | None = None

    def matches(self, kid: str, course: str) -> bool:
        return kid_matches(self.kid, kid) and course_matches(self.course, course, whole_words=True)

    def targets(self, kid: str, course: str) -> bool:
        """Exactly this kid and this class, as the course-page control writes it."""
        return self.kid.lower() == (kid or "").lower() and self.course.lower() == (course or "").lower()


@dataclass(frozen=True)
class SourcePrefs:
    default: Choice = Choice()
    rules: tuple[SourceRule, ...] = ()

    def deciding_rule(self, kid: str, course: str, field: str) -> SourceRule | None:
        for r in self.rules:
            if getattr(r, field) is not None and r.matches(kid, course):
                return r
        return None

    def resolve(self, kid: str, course: str) -> Choice:
        out = {}
        for f in FIELDS:
            r = self.deciding_rule(kid, course, f)
            out[f] = getattr(r, f) if r is not None else getattr(self.default, f)
        return Choice(**out)

    def rule_for(self, kid: str, course: str) -> SourceRule | None:
        return next((r for r in self.rules if r.targets(kid, course)), None)

    def without_rule(self, kid: str, course: str) -> "SourcePrefs":
        return replace(self, rules=tuple(r for r in self.rules if not r.targets(kid, course)))

    def with_rule(self, kid: str, course: str, assignments: str | None, grades: str | None) -> "SourcePrefs":
        """Add or replace the exact kid+class rule; both fields None removes it."""
        if assignments is None and grades is None:
            return self.without_rule(kid, course)
        new = SourceRule(kid=kid, course=course, assignments=assignments, grades=grades)
        rules = list(self.rules)
        for i, r in enumerate(rules):
            if r.targets(kid, course):
                rules[i] = new
                return replace(self, rules=tuple(rules))
        return replace(self, rules=(*rules, new))

    def with_default(self, assignments: str, grades: str) -> "SourcePrefs":
        return replace(self, default=Choice(assignments, grades))

    def to_doc(self) -> dict:
        doc: dict = {"assignments": self.default.assignments, "grades": self.default.grades}
        rules = []
        for r in self.rules:
            d = {k: v for k, v in (("kid", r.kid), ("course", r.course), ("assignments", r.assignments), ("grades", r.grades)) if v}
            rules.append(d)
        if rules:
            doc["rule"] = rules
        return doc


DEFAULT = SourcePrefs()


def _value(raw, where: str) -> str | None:
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if v in SOURCES:
        return v
    log.warning("config.toml [sources] %s: %r is not \"canvas\" or \"hac\"; ignoring it", where, raw)
    return None


def from_doc(doc: dict) -> SourcePrefs:
    raw = doc.get("sources")
    if raw is None:
        return DEFAULT
    if not isinstance(raw, dict):
        log.warning("config.toml [sources] is not a table; using the defaults")
        return DEFAULT
    base = Choice()
    default = Choice(assignments=_value(raw.get("assignments"), "assignments") or base.assignments,
                     grades=_value(raw.get("grades"), "grades") or base.grades)
    raw_rules = raw.get("rule")
    if raw_rules is not None and not isinstance(raw_rules, list):
        log.warning("config.toml [sources] rule is not a list of tables; ignoring it")
        raw_rules = []
    rules = []
    for n, d in enumerate(raw_rules or [], start=1):
        if not isinstance(d, dict):
            log.warning("config.toml [sources] rule %d is not a table; ignoring it", n)
            continue
        rules.append(SourceRule(kid=str(d.get("kid", "")).strip(), course=str(d.get("course", "")).strip(),
                                assignments=_value(d.get("assignments"), f"rule {n} assignments"),
                                grades=_value(d.get("grades"), f"rule {n} grades")))
    return SourcePrefs(default, tuple(rules))


def assignments_for(prefs: SourcePrefs | None, kid: str, course: str) -> str:
    return (prefs or DEFAULT).resolve(kid, course).assignments


def pick_value(pick: str, canvas_value, hac_value):
    """(value, source) from the preferred source, or the other when it has nothing."""
    order = (("hac", hac_value), ("canvas", canvas_value)) if pick == "hac" else (("canvas", canvas_value), ("hac", hac_value))
    for src, v in order:
        if v is not None:
            return v, src
    return None, None
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_sources.py tests/test_late_rules.py tests/test_matching.py -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/sources.py fridgesheet/matching.py fridgesheet/late_rules.py tests/test_sources.py
git commit -m "sources: resolve which gradebook is authoritative, per family, kid and class

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 2: `Settings.sources` from `config.toml`

**Files:**
- Modify: `fridgesheet/config.py` (`Settings` at line 190; `settings_from_doc` at line 299)
- Modify: `fridgesheet/web/app.py:74` (add `AppState.sources` after `rules`)
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: `sources.from_doc`, `sources.SourcePrefs`, `sources.DEFAULT`
- Produces: `Settings.sources: SourcePrefs`; `AppState.sources() -> SourcePrefs`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_config.py`)

```python
def test_sources_table_reaches_settings():
    from fridgesheet import sources
    s = config.Settings()
    config.settings_from_doc({"sources": {"grades": "canvas", "rule": [{"course": "Band", "assignments": "hac"}]}}, s)
    assert s.sources.resolve("Alex", "Concert Band") == sources.Choice("hac", "canvas")


def test_settings_default_sources_are_canvas_assignments_hac_grades():
    from fridgesheet import sources
    assert config.Settings().sources == sources.DEFAULT


def test_a_bad_sources_table_does_not_fail_the_load():
    s = config.Settings()
    config.settings_from_doc({"sources": "hac"}, s)             # no exception
    config.settings_from_doc({"sources": {"grades": 3}}, s)
    assert s.sources.default.grades == "hac"
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_config.py -q -k sources`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'sources'`.

- [ ] **Step 3: Implement**

In `config.py`, add `from . import sources as _sources` beside the other package imports at the top, then add to `Settings` after `refresh` (line 205):

```python
    #: [sources]: which gradebook is authoritative for assignments and for class averages (sources.py).
    sources: "_sources.SourcePrefs" = field(default_factory=lambda: _sources.DEFAULT)
```

At the end of `settings_from_doc` (after the `[refresh]` block, line 363):

```python
    s.sources = _sources.from_doc(doc)
```

In `web/app.py`, after `rules()` (line 87):

```python
    def sources(self) -> "SourcePrefs":
        """Which gradebook is authoritative per kid and class. Read from settings, which
        Settings and the course-page control reload after they write config.toml."""
        return self.settings.sources
```

and add `from ..sources import SourcePrefs` to `app.py`'s imports.

If `from . import sources` in `config.py` creates an import cycle (it should not: `sources` imports only `matching`), verify with `env -u PYTHONPATH python3 -c "import fridgesheet.config, fridgesheet.web.app"`.

- [ ] **Step 4: Run to verify pass**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_config.py tests/test_sources.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/config.py fridgesheet/web/app.py tests/test_config.py
git commit -m "config: read [sources] into Settings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Preference-aware outcome, grade cell and status cell

The pure functions that pick one source's score. No threading yet; every new parameter defaults to `"canvas"`, which is today's behaviour.

Semantics under `prefer="hac"` when HAC has a score for the item:
- The HAC score decides done-or-not. A HAC zero (with points > 0) is *not done*. A HAC score above zero is done, even when Canvas says `missing` (the Honors Algebra II quiz: Canvas missing, HAC 48/50).
- Excused and unpublished still come from Canvas and still come first.
- A Canvas submission still decides *on time* versus *late* when the HAC score is above zero.
- When HAC has no score, everything behaves exactly as under `"canvas"`.

**Files:**
- Modify: `fridgesheet/web/outcomes.py:78-112` (`classify`)
- Modify: `fridgesheet/web/stores/items.py:85-115` (`status_text`), `:157-182` (`grade_text`)
- Modify: `fridgesheet/web/reconcile.py:67-94` (`open_sources`), `:110-114` (`is_actionable`)
- Test: `tests/test_web_outcomes.py` (append), `tests/test_web_items_prefer.py` (create)

**Interfaces:**
- Produces:
  - `outcomes.classify(item, obs, now, prefer: str = "canvas") -> str`
  - `items.status_text(item, obs, now, prefer: str = "canvas") -> str`
  - `items.grade_text(item, obs, prefer: str = "canvas") -> tuple[str, bool]`
  - `reconcile.open_sources(item, obs, now, prefer: str = "canvas") -> set[str]`
  - `reconcile.is_actionable(item, obs, flag, rules, kid, now, prefer: str = "canvas") -> bool`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web_outcomes.py` (it already defines `canvas`, `hac`, `item`, `NOW`, `PAST`):

```python
# --- which source decides the score (docs/superpowers/specs/2026-09-22-source-of-truth-design.md) ---

def test_honors_algebra_quiz_canvas_missing_hac_48():
    """Real, 2026-09-21: Canvas marked the calculator quiz missing; HAC recorded 48/50."""
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    it = item(points=50)
    assert oc.classify(it, obs, NOW) == oc.NOT_DONE                      # today: Canvas's flag wins
    assert oc.classify(it, obs, NOW, prefer="hac") == oc.DONE_OFFLINE


def test_hac_preference_reads_hac_zero_as_not_done_over_a_canvas_score():
    """Review focus 5."""
    obs = {"canvas": canvas(state="graded", score=8), "hac": hac(0.0)}
    assert oc.classify(item(), obs, NOW) == oc.DONE_OFFLINE
    assert oc.classify(item(), obs, NOW, prefer="hac") == oc.NOT_DONE


def test_hac_preference_keeps_canvas_timing_and_marks():
    sub = {"canvas": canvas(submitted_at=PAST, late=1, state="graded", score=3), "hac": hac(9.0)}
    assert oc.classify(item(), sub, NOW, prefer="hac") == oc.LATE
    assert oc.classify(item(), {"canvas": canvas(excused=1), "hac": hac(0.0)}, NOW, prefer="hac") == oc.EXCUSED
    assert oc.classify(item(), {"canvas": canvas(published=0), "hac": hac(9.0)}, NOW, prefer="hac") == oc.UNPUBLISHED


def test_hac_preference_with_no_hac_score_changes_nothing():
    for obs in ({"canvas": canvas(missing=1), "hac": hac(None)}, {"canvas": canvas(state="graded", score=7)},
                {"canvas": canvas(), "hac": hac(None)}):
        assert oc.classify(item(), obs, NOW, prefer="hac") == oc.classify(item(), obs, NOW)


def test_canvas_preference_fills_the_gap_from_hac():
    assert oc.classify(item(kind="paper"), {"canvas": canvas(), "hac": hac(9.0)}, NOW, prefer="canvas") == oc.DONE_OFFLINE
```

Create `tests/test_web_items_prefer.py`:

```python
"""The Grade and Status cells follow the assignments preference; the Handed-in cell never does."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web import reconcile
from fridgesheet.web.stores import items

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 21, 16, 0, tzinfo=TZ)
PAST = "2026-09-10T23:59:00-04:00"


def canvas(**kw):
    base = dict(state="unsubmitted", score=None, grade=None, submitted_at=None, late=0, missing=0, excused=0, published=1)
    base.update(kw)
    return base


def hac(score=None):
    return dict(state="graded" if score is not None else "ungraded", score=score, grade=None, submitted_at=None,
                late=None, missing=None, excused=None, published=None)


def item(points=50, kind="online"):
    return {"kind": kind, "due": PAST, "points": points}


def test_grade_cell_shows_the_preferred_score():
    obs = {"canvas": canvas(state="graded", score=12.5, grade="12.5"), "hac": hac(48.0)}
    assert items.grade_text(item(), obs) == ("12.5/50", False)
    assert items.grade_text(item(), obs, prefer="hac") == ("48/50", False)


def test_grade_cell_hac_preference_over_canvas_missing():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert items.grade_text(item(), obs) == ("Missing", False)
    assert items.grade_text(item(), obs, prefer="hac") == ("48/50", False)


def test_grade_cell_hac_zero_is_flagged_as_a_zero():
    assert items.grade_text(item(), {"canvas": canvas(state="graded", score=40), "hac": hac(0.0)}, prefer="hac") == ("0/50", True)


def test_grade_cell_falls_back_when_the_preferred_source_is_silent():
    obs = {"canvas": canvas(state="graded", score=41), "hac": hac(None)}
    assert items.grade_text(item(), obs, prefer="hac") == ("41/50", False)


def test_status_cell_follows_the_preference():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert items.status_text(item(), obs, NOW) == "Missing"
    assert items.status_text(item(), obs, NOW, prefer="hac") == "48/50"
    assert items.status_text(item(), {"canvas": canvas(excused=1), "hac": hac(48.0)}, NOW, prefer="hac") == "Excused"


def test_handed_in_is_canvas_only_whatever_the_preference():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert items.handed_in_text(item(), obs) == ("No", None)            # signature unchanged: no prefer


def test_open_sources_settles_when_hac_is_preferred_and_graded():
    obs = {"canvas": canvas(missing=1), "hac": hac(48.0)}
    assert reconcile.open_sources(item(), obs, NOW) == {"canvas"}
    assert reconcile.open_sources(item(), obs, NOW, prefer="hac") == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_web_outcomes.py tests/test_web_items_prefer.py -q`
Expected: FAIL with `TypeError: classify() got an unexpected keyword argument 'prefer'` (and the same for the others).

- [ ] **Step 3: Implement `classify`**

Replace `outcomes.py:78-112` with:

```python
def classify(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime, prefer: str = "canvas") -> str:
    """One outcome for one item, from the latest observation of each source.

    Canvas carries the teacher's marks and the submission; HAC carries only a grade. `prefer`
    is the family's assignments source (sources.py). Under "canvas" a Canvas score wins and HAC
    fills the gap. Under "hac" a HAC score, when there is one, decides done-or-not -- it
    overrides Canvas's `missing` flag and Canvas's own score -- while excused, unpublished and
    the submission's timing still come from Canvas, which is the only source that knows them.
    The order of the checks is the order of certainty: a mark or a zero settles it; a
    submission settles it; a grade with no submission means done by hand; then it is either
    not due, not done, or -- for work that could never be submitted online -- not known."""
    c, h = obs.get("canvas"), obs.get("hac")
    if c is None and h is None:
        return NO_DATA
    if c is not None:
        if c["excused"]:
            return EXCUSED
        if c["published"] == 0:
            return UNPUBLISHED
    c_score = c["score"] if c is not None else None
    h_score = h["score"] if h is not None else None
    hac_decides = prefer == "hac" and h_score is not None
    score = h_score if hac_decides else (c_score if c_score is not None else h_score)
    points = item["points"] or 0
    zero = score == 0 and points > 0
    if c is not None:
        if (c["missing"] and not hac_decides) or zero:
            return NOT_DONE
        if c["submitted_at"]:
            return LATE if c["late"] else ON_TIME
        if score is not None:
            return DONE_OFFLINE
        if not _is_past(item, now):
            return NOT_DUE
        return UNKNOWN if item["kind"] in _NOTHING_TO_SUBMIT else NOT_DONE
    # HAC only: a grade or nothing.
    if zero:
        return NOT_DONE
    if score is not None:
        return DONE_OFFLINE
    return UNKNOWN if _is_past(item, now) else NOT_DUE
```

- [ ] **Step 4: Implement `grade_text` and `status_text`**

In `stores/items.py`, change `grade_text` (line 157) to:

```python
def grade_text(item: sqlite3.Row, obs: dict[str, sqlite3.Row], prefer: str = "canvas") -> tuple[str, bool]:
    """What the gradebook says about the work itself, and whether it is a real zero.

    Under the default, Canvas first: it carries the teacher's marks ("Missing", "Excused") as
    well as the score, and HAC only when Canvas has nothing. Under `prefer="hac"` a HAC score is
    shown whenever there is one, ahead of Canvas's score and its Missing mark; Unpublished and
    Excused still come first. A disagreement between the two is the Reconcile page's job."""
    c, h = obs.get("canvas"), obs.get("hac")
    if prefer == "hac" and h is not None and h["score"] is not None:
        if c is not None and c["published"] == 0:
            return "Unpublished", False
        if c is not None and c["excused"]:
            return "Excused", False
        return _score(h, item["points"]), h["score"] == 0 and (item["points"] or 0) > 0
    if c is not None:
```

(the rest of the body, from `if c["published"] == 0:` on, is unchanged).

Change `status_text` (line 85) signature to `def status_text(item, obs, now, prefer: str = "canvas") -> str:` and insert, directly after `past = ...` (line 89):

```python
    if prefer == "hac" and h is not None and h["score"] is not None:
        if c is not None and c["excused"]:
            return "Excused"
        if c is not None and c["published"] == 0:
            return "Unpublished"
        return "Zero" if h["score"] == 0 and (item["points"] or 0) > 0 else _score(h, item["points"])
```

- [ ] **Step 5: Implement `open_sources` and `is_actionable`**

In `reconcile.py`, change line 67 to `def open_sources(item, obs, now, prefer: str = "canvas") -> set[str]:` and line 83 to `outcome = outcomes.classify(item, obs, now, prefer=prefer)`.

Change `is_actionable` (line 110-111) to:

```python
def is_actionable(item: sqlite3.Row, obs: dict[str, sqlite3.Row], flag: str | None, rules, kid: str, now: datetime,
                  prefer: str = "canvas") -> bool:
    if flag in HANDLED_FLAGS or not open_sources(item, obs, now, prefer=prefer):
```

- [ ] **Step 6: Run the whole suite**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task3.log | tail -5`
Expected: all pass (every existing caller still gets `"canvas"`).

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/outcomes.py fridgesheet/web/stores/items.py fridgesheet/web/reconcile.py tests/test_web_outcomes.py tests/test_web_items_prefer.py
git commit -m "outcomes: let the assignments preference decide the score

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 4: Thread the preference through the web stores and routes

Every store that classifies items gains `prefs: SourcePrefs | None = None` and resolves the
assignments source per item from the item's kid (`r["kid"]`) and course name (`r["course_name"]`),
both already selected by `reconcile.live_items`. Every route passes `prefs=state.sources()`.

**Files:**
- Modify: `fridgesheet/web/stores/items.py` (`_views`, `list_items`, `one`, `with_cases`, `open_work`, `dashboard_counts`)
- Modify: `fridgesheet/web/reconcile.py` (`cases`, `actionable_items`)
- Modify: `fridgesheet/web/stores/trends.py` (`weekly_outcomes`, `open_days`)
- Modify: `fridgesheet/web/views.py` (`build`, `_item_rows`)
- Modify routes: `dashboard.py`, `kid.py`, `trends.py`, `open.py`, `checkin.py`, `flags.py`, `reports.py`, `reconcile.py` under `fridgesheet/web/routes/`
- Test: `tests/test_web_sources_threading.py` (create)

**Interfaces:**
- Consumes: `sources.assignments_for`, `AppState.sources()`, the `prefer=` parameters from Task 3
- Produces: `prefs=` keyword (default `None`) on `items._views`, `items.list_items`, `items.one`, `items.with_cases`, `items.open_work`, `items.dashboard_counts`, `reconcile.cases`, `reconcile.actionable_items`, `trends.weekly_outcomes`, `trends.open_days`, `views.build`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_sources_threading.py`:

```python
"""The assignments preference reaches every page, through the stores. Fixture: Alex's Quiz 1 is
MISSING in Canvas and 28/30 in HAC (tests/web_fixtures.py)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from fridgesheet import config, late_rules, sources
from fridgesheet.web import app as webapp, reconcile
from fridgesheet.web.stores import items, students
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])
HAC = sources.DEFAULT.with_default("hac", "hac")


def client(home, toml: str) -> TestClient:
    (home / "config.toml").write_text(toml)
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.clock = lambda: NOW
    return TestClient(application, headers=LOCAL_HOST_HEADERS)


def quiz(views):
    return next(v for v in views if v.name == "Quiz 1")


def test_list_items_follows_prefs(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    default = quiz(items.list_items(conn, alex, now=NOW, rules=RULES, show="all"))
    hac = quiz(items.list_items(conn, alex, now=NOW, rules=RULES, show="all", prefs=HAC))
    assert (default.grade, default.outcome, default.actionable) == ("Missing", "not_done", True)
    assert (hac.grade, hac.outcome, hac.actionable) == ("28/30", "done_offline", False)


def test_a_rule_for_another_class_leaves_this_one_alone(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    p = sources.DEFAULT.with_rule("Alex", "Algebra I", "hac", None)
    assert quiz(items.list_items(conn, alex, now=NOW, rules=RULES, show="all", prefs=p)).grade == "Missing"


def test_dashboard_counts_follow_prefs(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    before = items.dashboard_counts(conn, alex, now=NOW, rules=RULES).actionable
    after = items.dashboard_counts(conn, alex, now=NOW, rules=RULES, prefs=HAC).actionable
    assert after == before - 1


def test_the_disagreement_is_still_listed_under_hac(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    qid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    kinds = [c.kind for c in reconcile.cases(conn, alex["id"], rules=RULES, now=NOW, prefs=HAC) if c.item_id == qid]
    assert "disagree" in kinds


def test_the_kid_page_reads_the_preference_from_config(tmp_path):
    seed(tmp_path).close()
    assert "28/30" not in client(tmp_path, "").get("/kids/Alex?show=all").text
    assert "28/30" in client(tmp_path, '[sources]\nassignments = "hac"\n').get("/kids/Alex?show=all").text
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_web_sources_threading.py -q`
Expected: FAIL with `TypeError: list_items() got an unexpected keyword argument 'prefs'` (the last test fails on its second assert).

- [ ] **Step 3: `items._views` and its callers**

In `stores/items.py` add `from ... import sources` to the imports. Change `_views` (line 185) to take `prefs=None` and use it:

```python
def _views(conn: sqlite3.Connection, student: sqlite3.Row, *, now: datetime, rules, days_ahead: int = DAYS_AHEAD,
           prefs=None) -> list[ItemView]:
    latest = db.latest_observations(conn, student["id"])
    kinds: dict[int, list[str]] = {}
    for case in reconcile.cases(conn, student["id"], rules=rules, now=now, prefs=prefs):
        kinds.setdefault(case.item_id, []).append(case.kind)
```

and inside the loop, right after `obs = latest.get(r["id"], {})`:

```python
        prefer = sources.assignments_for(prefs, r["kid"], r["course_name"])
```

then pass it on the five lines that decide a score:

```python
        grade, zero = grade_text(r, obs, prefer)
        open_in = reconcile.open_sources(r, obs, now, prefer=prefer)
        ...
            outcome=outcomes.classify(r, obs, now, prefer=prefer), late_until=late_until, credit=credit,
        ...
            actionable=reconcile.is_actionable(r, obs, r["flag"], rules, r["kid"], now, prefer=prefer),
        ...
            flag=r["flag"], flag_text=flag_text.get(r["id"], ""), status=status_text(r, obs, now, prefer),
```

Add `prefs=None` to the signatures of `list_items`, `one`, `with_cases`, `open_work` and `dashboard_counts`, and forward it to every `_views(...)` call in them (`prefs=prefs`). In `with_cases`, also pass it to its own `reconcile.cases(...)` call.

- [ ] **Step 4: `reconcile.cases` and `actionable_items`**

In `reconcile.py` add `from .. import sources` near the other imports (inside the function if a module-level import cycles; `sources` imports only `matching`, so it should not). Change:

```python
def actionable_items(conn: sqlite3.Connection, student_id: int, *, rules, now: datetime, prefs=None) -> list[sqlite3.Row]:
    latest = db.latest_observations(conn, student_id)
    out = [r for r in live_items(conn, student_id, now)
           if is_actionable(r, latest.get(r["id"], {}), r["flag"], rules, r["kid"], now,
                            prefer=sources.assignments_for(prefs, r["kid"], r["course_name"]))]
```

and in `cases` add `prefs=None` to the signature and replace `opened = open_sources(r, obs, now)` with:

```python
        opened = open_sources(r, obs, now, prefer=sources.assignments_for(prefs, r["kid"], r["course_name"]))
```

The `disagree` block below it stays exactly as it is.

- [ ] **Step 5: `trends.weekly_outcomes` and `open_days`**

Add `prefs=None` to both signatures and `from ... import sources` to the imports. In `weekly_outcomes` (line 173):

```python
            outcome = outcomes.classify(item, latest.get(item["id"], {}), now,
                                        prefer=sources.assignments_for(prefs, item["kid"], item["course_name"]))
```

In `open_days` (the `if not reconcile.open_sources(...)` line):

```python
            if not reconcile.open_sources(item, latest.get(item["id"], {}), now,
                                          prefer=sources.assignments_for(prefs, item["kid"], item["course_name"])):
```

- [ ] **Step 6: `views.build` and `_item_rows`**

`build(conn, d, *, now, rules, nicknames, prefs=None)`; forward `prefs=prefs` into `_item_rows(...)`; `_item_rows(conn, d, *, now, rules, nicknames, prefs=None)` passes `prefs=prefs` to `items_store.list_items(...)`.

- [ ] **Step 7: Routes**

Pass `prefs=state.sources()` at every call below. Where a route already binds `rules = state.rules()`, bind `prefs = state.sources()` beside it.

| file | calls to change |
|---|---|
| `routes/dashboard.py:22` | `items.dashboard_counts(...)` |
| `routes/kid.py:48, 60, 63, 81, 83` | `items.list_items`, `items.one`, `reconcile.cases`, both course-page `items.list_items` |
| `routes/trends.py:62, 72, 84` | `items.dashboard_counts`, `trends.weekly_outcomes`, `trends.open_days`; `_record` gains `prefs` and forwards it |
| `routes/trends.py` `weekly_json` | `trends.weekly_outcomes` |
| `routes/open.py:22` | `items.open_work` |
| `routes/checkin.py:71, 135` | `items.list_items`, `items.one` |
| `routes/flags.py:32, 33` | `items.one`, `reconcile.cases` |
| `routes/reports.py:102, 161` | `views.build` |
| `routes/reconcile.py:26, 32, 67` | `items.with_cases` |

Then confirm nothing was missed:

Run: `grep -rn "list_items(\|items.one(\|with_cases(\|open_work(\|dashboard_counts(\|reconcile.cases(\|weekly_outcomes(\|open_days(\|views.build(" fridgesheet/web/routes`
Expected: every line contains `prefs=`.

- [ ] **Step 8: Run the whole suite**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task4.log | tail -5`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add fridgesheet/web tests/test_web_sources_threading.py
git commit -m "web: every page classifies work by the family's assignments source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: The printed sheet and the MCP open-work tools

**Files:**
- Modify: `fridgesheet/open_items.py:125-192` (`open_items`)
- Modify: `fridgesheet/reports/open_work.py:38`
- Modify: `fridgesheet/server.py:109-113` (`_open_work`)
- Test: `tests/test_open_items.py` (append)

**Interfaces:**
- Consumes: `sources.assignments_for`, `Settings.sources`
- Produces: `open_items.open_items(entry, kid, now, days_ahead=14, overdue_days=14, rules=None, include_hac=True, flags=None, prefs=None) -> OpenWork`

Under `pick == "hac"`, a Canvas assignment whose HAC twin has a score is settled by that score:
zero (with points above zero) prints `ZERO`; anything above zero is not on the sheet.
Excused and unpublished Canvas items stay off the sheet as today. With no HAC score, nothing changes.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_open_items.py`)

```python
from fridgesheet import sources  # noqa: E402

HAC = sources.DEFAULT.with_default("hac", "hac")


def hac_class(rows, name="Honors Biology - 3"):
    return [{"name": name, "assignments": rows}]


def hac_row(name, score, points=10.0):
    return {"name": name, "due": "09/10/2026", "assigned": "09/01/2026", "category": "Homework", "points": points,
            "score": score, "score_raw": "" if score is None else f"{score:.2f}"}


def test_hac_preference_drops_canvas_missing_when_hac_graded_it(rules):
    e = entry([canvas_item(missing=True)], hac_classes=hac_class([hac_row("WS 1", 9.0)]))
    assert [i.status for i in run(e, rules).items] == ["MISSING"]     # today: Canvas's flag wins
    assert run(e, rules, prefs=HAC).items == []


def test_hac_zero_prints_zero_under_hac_preference(rules):
    """Review focus 5, on paper."""
    e = entry([canvas_item(state="graded", score=8.0, grade="8")], hac_classes=hac_class([hac_row("WS 1", 0.0)]))
    assert run(e, rules).items == []
    (it,) = run(e, rules, prefs=HAC).items
    assert it.status == "ZERO" and it.score == 0.0 and it.overdue


def test_hac_preference_without_a_hac_score_changes_nothing(rules):
    e = entry([canvas_item(missing=True)], hac_classes=hac_class([hac_row("WS 1", None)]))
    assert [i.status for i in run(e, rules, prefs=HAC).items] == ["MISSING"]


def test_rules_resolve_by_first_name_not_the_printed_nickname(rules):
    p = sources.DEFAULT.with_rule("Alex", "Honors Biology", "hac", None)
    e = entry([canvas_item(missing=True)], hac_classes=hac_class([hac_row("WS 1", 9.0)]))
    assert open_items.open_items(e, "Dougie", NOW, rules=rules, prefs=p).items == []
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_open_items.py -q -k "hac_preference or hac_zero or first_name"`
Expected: FAIL with `TypeError: open_items() got an unexpected keyword argument 'prefs'`.

- [ ] **Step 3: Implement**

In `open_items.py` add `from . import sources` to the imports and `prefs=None` as the last parameter of `open_items`. After `year_start = ...` (line 133):

```python
    # Rules name kids by first name; `kid` here is the printed label, which may be a nickname.
    first = ((entry.get("name") or kid).split() or [kid])[0]
```

Inside the Canvas course loop, right after `peer_rows = ...` (line 143):

```python
        pick = sources.assignments_for(prefs, first, c["name"])
```

Replace lines 150-153 and 160 (compute the HAC twin before the status, and let a preferred HAC score settle it):

```python
            hac_row = next((r for n, r in peer_rows.items() if same_item(a["name"], n)), None)
            hac_score = (hac_row or {}).get("score")
            if pick == "hac" and hac_score is not None and not a.get("excused") and a.get("published", True):
                # The family reads this class's scores from HAC: its grade settles the item.
                status = "ZERO" if hac_score == 0 and (a.get("points_possible") or 0) > 0 else None
            else:
                status = _status(a, due, now)
            if status is None:
                continue
```

Delete the old `hac_row = next(...)` line and the old `hac_score = (hac_row or {}).get("score")` line that followed the comment block; the suppression `if status in ("PAPER — CHECK", "MISSING") ...` block stays as it is.

In the `Item(...)` constructor change `score=a.get("score")` to:

```python
                points=a.get("points_possible"), score=hac_score if pick == "hac" and hac_score is not None else a.get("score"),
```

- [ ] **Step 4: Wire the callers**

`reports/open_work.py:38`: add `prefs=ctx.settings.sources` to the `open_items.open_items(...)` call.
`server.py` `_open_work`: add `prefs=_settings.sources` to the `open_items.open_items(...)` call.

- [ ] **Step 5: Run the whole suite**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task5.log | tail -5`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/open_items.py fridgesheet/reports/open_work.py fridgesheet/server.py tests/test_open_items.py
git commit -m "sheet: the printed sheet and MCP open work follow the assignments source

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 6: Class averages in the web app

The grades preference picks the headline average on the course page and marks the official
series and events everywhere else. Nothing is hidden: the other source's number stays on the
page, labelled.

**Files:**
- Modify: `fridgesheet/web/stores/students.py` (add `GradeLine`, `grade_lines`)
- Modify: `fridgesheet/web/routes/kid.py:68-89` (`course`), `fridgesheet/web/templates/course.html:7-12`
- Modify: `fridgesheet/web/stores/trends.py` (`GradeSeries`, `grade_series`), `fridgesheet/web/routes/trends.py` (both `grade_series` calls, `grades_json`)
- Modify: `fridgesheet/web/stores/changes.py` (`_course_grade_events`, `since`), `fridgesheet/web/routes/changes.py:29`
- Modify: `fridgesheet/web/views.py` (`COLUMNS["grades"]`, `DEFAULT_COLUMNS["grades"]`, `_grade_rows`, `_change_rows`, `build`)
- Test: `tests/test_web_official_grade.py` (create)

**Interfaces:**
- Consumes: `sources.DEFAULT`, `SourcePrefs.resolve`, `AppState.sources()`, `views.build(..., prefs=)` from Task 4
- Produces:
  - `students.GradeLine(source: str, value: float, label: str, extra: str)` (frozen dataclass)
  - `students.grade_lines(canvas_row, hac_row, pick: str) -> list[GradeLine]` (official first)
  - `trends.GradeSeries.official: bool = False`; `trends.grade_series(conn, *, student_id=None, since=None, prefs=None)`
  - `changes.since(..., prefs=None)`; `changes._course_grade_events(conn, student_id, prefs=None)`
  - `views._grade_rows(conn, d, *, now, nicknames, prefs=None)`; `views._change_rows(conn, d, *, now, nicknames, prefs=None)`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_official_grade.py`:

```python
"""The grades preference picks the headline average. Fixture: Alex's Honors English 9 is 91.2 in
Canvas and 88 in HAC; the history fixture moves HAC 85 -> 88 and Canvas 93 -> 91.2."""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from fridgesheet import config, sources
from fridgesheet.web import app as webapp, views
from fridgesheet.web.stores import changes, students
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, TZ, history, seed

CANVAS_GRADES = '[sources]\ngrades = "canvas"\n'


def client(home, toml: str) -> TestClient:
    (home / "config.toml").write_text(toml)
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.clock = lambda: NOW
    return TestClient(application, headers=LOCAL_HOST_HEADERS)


def english(conn) -> int:
    return conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]


def grade_card(body: str) -> str:
    return body.split("<h2>Grade</h2>", 1)[1].split("</div>", 1)[0]


def test_grade_lines_put_the_official_source_first():
    canvas = {"current": 91.2, "letter": "A-", "average": None, "last_updated": None}
    hac = {"current": None, "letter": None, "average": 88.0, "last_updated": "9/11/2026"}
    assert [g.source for g in students.grade_lines(canvas, hac, "hac")] == ["hac", "canvas"]
    assert [g.source for g in students.grade_lines(canvas, hac, "canvas")] == ["canvas", "hac"]
    assert [g.source for g in students.grade_lines(canvas, None, "hac")] == ["canvas"]      # the gap is filled
    assert students.grade_lines(None, None, "hac") == []


def test_course_page_headline_follows_the_grades_source(tmp_path):
    conn = seed(tmp_path)
    cid = english(conn)
    conn.close()
    default = grade_card(client(tmp_path, "").get(f"/kids/Alex/courses/{cid}").text)
    assert default.index("HAC average") < default.index("Canvas current")
    assert "A-" in default and "88" in default and "91.2" in default
    flipped = grade_card(client(tmp_path, CANVAS_GRADES).get(f"/kids/Alex/courses/{cid}").text)
    assert flipped.index("Canvas current") < flipped.index("HAC average")


def test_grades_json_marks_the_official_series(tmp_path):
    history(tmp_path).close()
    series = client(tmp_path, "").get("/trends/grades.json").json()["series"]
    official = {s["label"]: s["official"] for s in series}
    assert official["Honors English 9 (HAC average)"] is True
    assert official["Honors English 9 (Canvas current)"] is False
    series = client(tmp_path, CANVAS_GRADES).get("/trends/grades.json").json()["series"]
    assert {s["label"]: s["official"] for s in series}["Honors English 9 (Canvas current)"] is True


def test_grade_change_events_say_which_is_official(tmp_path):
    conn = history(tmp_path)
    since = datetime(2026, 9, 1, tzinfo=TZ)
    details = [e.detail for e in changes.since(conn, since=since, limit=None) if e.kind == "course_grade"]
    assert any(d.startswith("HAC average") and d.endswith("· official") for d in details)
    assert all(not d.endswith("· official") for d in details if d.startswith("Canvas current"))
    flipped = sources.DEFAULT.with_default("canvas", "canvas")
    details = [e.detail for e in changes.since(conn, since=since, limit=None, prefs=flipped) if e.kind == "course_grade"]
    assert any(d.startswith("Canvas current") and d.endswith("· official") for d in details)


def test_report_builder_grades_rows_carry_official(tmp_path):
    conn = history(tmp_path)
    rows = [r for r, _ in views._grade_rows(conn, views.Definition(source="grades"), now=NOW, nicknames={})]
    assert {r["source"]: r["official"] for r in rows if r["course"] == "Honors English 9"} == {"hac": "yes", "canvas": ""}
    assert "official" in views.DEFAULT_COLUMNS["grades"]
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_web_official_grade.py -q`
Expected: FAIL (`AttributeError: module ... has no attribute 'grade_lines'`, `KeyError: 'official'`, and so on).

- [ ] **Step 3: `students.grade_lines`**

Append to `stores/students.py` (add `from dataclasses import dataclass` to its imports):

```python
@dataclass(frozen=True)
class GradeLine:
    source: str          # canvas | hac
    value: float
    label: str           # "Canvas current" | "HAC average"
    extra: str           # the letter, or when HAC last updated it


def grade_lines(canvas_row, hac_row, pick: str) -> list[GradeLine]:
    """A class's averages, the family's official source first (sources.py). The other source's
    number stays, second: a parent choosing HAC still wants to see what Canvas says."""
    out: list[GradeLine] = []
    if canvas_row is not None and canvas_row["current"] is not None:
        out.append(GradeLine("canvas", canvas_row["current"], "Canvas current", canvas_row["letter"] or ""))
    if hac_row is not None and hac_row["average"] is not None:
        updated = f"updated {hac_row['last_updated']}" if hac_row["last_updated"] else ""
        out.append(GradeLine("hac", hac_row["average"], "HAC average", updated))
    return sorted(out, key=lambda g: g.source != pick)
```

- [ ] **Step 4: Course page**

In `routes/kid.py`, add `from ... import sources` to the imports. In `course()`, after `grades = students.latest_grades(conn, s["id"])` (line 78):

(`prefs = state.sources()` is already bound in this route by Task 4; reuse it, do not bind it twice.)

```python
    own, other = grades.get(course_id), (grades.get(peer["id"]) if peer else None)
    canvas_g, hac_g = (own, other) if c["source"] == "canvas" else (other, own)
    grade_lines = students.grade_lines(canvas_g, hac_g, prefs.resolve(s["key"], c["name"]).grades)
```

and add `grade_lines=grade_lines,` to the `render(...)` call (keep `grade` and `peer_grade`; nothing else reads them after this change, but removing them is not this task's job).

Replace `course.html` lines 7-12 (the Grade card) with:

```html
  <div class="card"><h2>Grade</h2>
    {% for g in grade_lines %}
    <p>{% if loop.first %}<span class="big">{{ g.value }}</span>{% else %}{{ g.value }}{% endif %} {{ g.label }}{% if g.extra %} <span class="muted">{{ g.extra }}</span>{% endif %}{% if loop.first and grade_lines | length > 1 %} <span class="muted">· official</span>{% endif %}</p>
    {% else %}<p class="muted">No grade observed yet.</p>{% endfor %}
  </div>
```

- [ ] **Step 5: Trends**

In `stores/trends.py` add `from ... import sources` to the imports; add `official: bool = False` to `GradeSeries` after `label`; give `grade_series` a `prefs=None` keyword; add `s.key AS student_key, c.name AS course_name` to its SELECT list; and where a new series is created:

```python
            if s is None:
                pick = (prefs or sources.DEFAULT).resolve(r["student_key"], r["course_name"]).grades
                s = out[key] = GradeSeries(r["course_id"], r["course_short"], source,
                                           f"{r['course_short']} ({word})", official=source == pick)
```

End with `return sorted((s for s in out.values() if s.points), key=lambda s: not s.official)` (stable, so the existing order holds within each group).

In `routes/trends.py` pass `prefs=state.sources()` to both `trends.grade_series(...)` calls, and add `"official": s.official` to each series dict in `grades_json`.

- [ ] **Step 6: Changes**

In `stores/changes.py` add `from ... import sources` to the imports. `_course_grade_events(conn, student_id, prefs=None)`: add `c.name AS course_name` to its SELECT, and replace the inner loop with:

```python
        pick = (prefs or sources.DEFAULT).resolve(row["student_key"], row["course_name"]).grades
        for field, word, src in (("average", "HAC average", "hac"), ("current", "Canvas current", "canvas")):
            a, b = before[field], row[field]
            if a is not None and b is not None and a != b:
                mark = " · official" if src == pick else ""
                out.append(Event("course_grade", _dt(row["at"]), row["student_key"], row["student_id"],
                                 course_short=row["course_short"], source=row["course_source"],
                                 detail=f"{word} {_num(a)} → {_num(b)}{mark}"))
```

`since(..., prefs=None)` forwards `prefs` to `_course_grade_events(conn, student_id, prefs)`. `routes/changes.py:29` passes `prefs=state.sources()`.

- [ ] **Step 7: Report builder**

In `views.py`: add `("official", "Official", "text")` to `COLUMNS["grades"]` after `("source", ...)`; `DEFAULT_COLUMNS["grades"] = ["kid", "course", "source", "official", "value", "at"]`. `_grade_rows(conn, d, *, now, nicknames, prefs=None)` passes `prefs=prefs` to `trends_store.grade_series(...)` and adds `"official": "yes" if series.official else ""` to each row. `_change_rows(..., prefs=None)` passes `prefs=prefs` to `changes_store.since(...)`. `build` forwards its `prefs` to both.

- [ ] **Step 8: Run the whole suite**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task6.log | tail -5`
Expected: all pass. If a report-builder test pins the grades default columns, update it to include `official`.

- [ ] **Step 9: Commit**

```bash
git add fridgesheet/web tests/test_web_official_grade.py
git commit -m "web: the family's grades source is the headline average

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: MCP `grades()` names the official average

**Files:**
- Modify: `fridgesheet/server.py:63-89` (`grades`)
- Test: `tests/test_server_tools.py` (append)

**Interfaces:**
- Consumes: `Settings.sources`, `sources.pick_value`
- Produces: each class dict in `grades()` gains `official` (float or None) and `official_source` (`"canvas"`, `"hac"` or None); existing keys unchanged.

- [ ] **Step 1: Write the failing test** (append to `tests/test_server_tools.py`)

```python
from fridgesheet import sources  # noqa: E402


@pytest.fixture
def graded(monkeypatch, tmp_path):
    snap = {
        "fetched_at": _iso(0), "fetched_at_epoch": 10**12, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {"Alex": {
            "name": "Alex Example",
            "canvas": {"courses": [{"id": 5, "name": "Honors Biology S1-2027-Nance", "assignments": [], "staff": [],
                                    "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False}}]},
            "hac": {"week_view": [], "classes": [
                {"name": "Honors Biology - 3", "marking_period_avg": 88.0, "last_updated": "9/11/2026", "categories": [], "assignments": []},
                {"name": "Hawk Time", "marking_period_avg": 100.0, "last_updated": None, "categories": [], "assignments": []},
            ]},
        }},
    }
    monkeypatch.setattr(collector, "load_snapshot", lambda s: snap)
    monkeypatch.setattr(collector, "snapshot_is_fresh", lambda s, snap: True)
    return snap


def test_grades_official_follows_the_grades_source(graded, monkeypatch):
    monkeypatch.setattr(server._settings, "sources", sources.DEFAULT)
    out = {c["course"]: c for c in server.grades("Alex")["classes"]}
    bio = out["Honors Biology S1-2027-Nance"]
    assert (bio["official"], bio["official_source"]) == (88.0, "hac")
    assert (bio["hac_official"], bio["canvas_current"]) == (88.0, 91.2)          # both still there
    monkeypatch.setattr(server._settings, "sources", sources.DEFAULT.with_default("canvas", "canvas"))
    out = {c["course"]: c for c in server.grades("Alex")["classes"]}
    assert (out["Honors Biology S1-2027-Nance"]["official"], out["Honors Biology S1-2027-Nance"]["official_source"]) == (91.2, "canvas")
    assert (out["Hawk Time"]["official"], out["Hawk Time"]["official_source"]) == (100.0, "hac")   # HAC-only fills the gap
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_server_tools.py -q -k official`
Expected: FAIL with `KeyError: 'official'`.

- [ ] **Step 3: Implement**

In `server.py` add `from .sources import pick_value`. In `grades`, after `e = _kid(_snap(), student)`:

```python
    first = (e["name"].split() or [student])[0]
```

In the Canvas loop, compute before appending:

```python
        hac_official = h.get("marking_period_avg", w.get("current_average"))
        pick = _settings.sources.resolve(first, c["name"]).grades
        official, official_source = pick_value(pick, c["grade"]["current_score"], hac_official)
```

use `"hac_official": hac_official,` in the dict and add `"official": official, "official_source": official_source,`. In the HAC-only loop:

```python
            pick = _settings.sources.resolve(first, name).grades
            official, official_source = pick_value(pick, None, h.get("marking_period_avg"))
```

and add the same two keys to that dict. Replace the docstring with:

```python
    """Class averages per class: HAC's marking-period average and Canvas's current/final score
    side by side, plus `official` -- the one the family has chosen as authoritative for this kid
    and class ([sources] in config.toml; HAC unless changed), falling back to the other source
    when that one has no average. Canvas can be hidden or partial."""
```

- [ ] **Step 4: Run to verify pass**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_server_tools.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/server.py tests/test_server_tools.py
git commit -m "mcp: grades() names the official average

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---
### Task 8: Settings page — household defaults and the rule list

**Files:**
- Modify: `fridgesheet/web/actions.py` (`FormValues`, `load_form`, `validate`, `save`; add `load_sources`, `set_source_rule`, `remove_source_rule`)
- Modify: `fridgesheet/web/routes/settings.py` (`_page`, `save`; add `remove_source`)
- Modify: `fridgesheet/web/templates/settings.html`
- Test: `tests/test_web_settings_page.py` (append)

**Interfaces:**
- Consumes: `sources.from_doc`, `SourcePrefs.with_default` / `with_rule`, `sources.SOURCES`, `sources.LABELS`
- Produces:
  - `FormValues.sources_assignments: str = "canvas"`, `FormValues.sources_grades: str = "hac"`
  - `actions.load_sources(home: Path) -> SourcePrefs`
  - `actions.set_source_rule(home: Path, kid: str, course: str, assignments: str | None, grades: str | None) -> None` (both None removes)
  - `actions.remove_source_rule(home: Path, kid: str, course: str) -> None`
  - Route `POST /settings/sources/remove` (form fields `kid`, `course`) → 303 to `/settings`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_settings_page.py`)

```python
RULE = '\n[[sources.rule]]\nkid = "Alex"\ncourse = "Band"\nassignments = "hac"\n'


def test_source_defaults_round_trip(tmp_path):
    c, app = _client(tmp_path)
    r = c.post("/settings", data={**FORM, "sources_assignments": "hac", "sources_grades": "canvas"})
    assert r.status_code == 200 and "Settings saved" in r.text
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert (doc["sources"]["assignments"], doc["sources"]["grades"]) == ("hac", "canvas")
    assert app.state.fridgesheet.settings.sources.default.assignments == "hac"     # reloaded
    body = c.get("/settings").text
    assert 'name="sources_assignments"' in body and '<option value="hac" selected>' in body


def test_saving_the_form_keeps_rules(tmp_path):
    """Review focus 4: the main form owns the defaults, never the rules."""
    c, _ = _client(tmp_path)
    with open(tmp_path / "config.toml", "a") as f:
        f.write(RULE)
    assert c.post("/settings", data=FORM).status_code == 200
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["sources"]["rule"] == [{"kid": "Alex", "course": "Band", "assignments": "hac"}]


def test_a_bad_source_value_is_refused_and_nothing_is_written(tmp_path):
    c, _ = _client(tmp_path)
    before = (tmp_path / "config.toml").read_text()
    r = c.post("/settings", data={**FORM, "sources_grades": "powerschool"})
    assert "Canvas or HAC" in r.text
    assert (tmp_path / "config.toml").read_text() == before


def test_rules_are_listed_and_removable(tmp_path):
    c, app = _client(tmp_path)
    with open(tmp_path / "config.toml", "a") as f:
        f.write(RULE)
    app.state.fridgesheet.reload()
    body = c.get("/settings").text
    assert "Band" in body and 'action="/settings/sources/remove"' in body
    r = c.post("/settings/sources/remove", data={"kid": "Alex", "course": "Band"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/settings"
    assert "rule" not in config.load_config_doc(tmp_path / "config.toml")["sources"]
    assert app.state.fridgesheet.settings.sources.rules == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_web_settings_page.py -q -k "source or rules"`
Expected: FAIL (`KeyError: 'sources'`, 404 on the remove route).

- [ ] **Step 3: `actions.py`**

Import: change `from .. import config, late_rules, runner` to `from .. import config, late_rules, runner, sources`.

Add to `FormValues` after `check_updates`:

```python
    sources_assignments: str = "canvas"   # [sources] assignments: household default
    sources_grades: str = "hac"           # [sources] grades: household default
```

In `load_form`, add to the `FormValues(...)` call:

```python
        sources_assignments=s.sources.default.assignments,
        sources_grades=s.sources.default.grades,
```

At the end of `validate`, before `return errors`:

```python
    for label, value in (("Assignment scores", form.sources_assignments), ("Class averages", form.sources_grades)):
        if value not in sources.SOURCES:
            errors.append(f"{label} must come from Canvas or HAC.")
```

In `save`, after `rep.update(...)` (line 168):

```python
    # Only the household defaults: the override rules belong to the course pages and the list below.
    doc["sources"] = sources.from_doc(doc).with_default(form.sources_assignments, form.sources_grades).to_doc()
```

Append after `save`:

```python
def load_sources(home: Path) -> sources.SourcePrefs:
    return _settings_for(home).sources


def set_source_rule(home: Path, kid: str, course: str, assignments: str | None, grades: str | None) -> None:
    """Add, replace or (both None) remove the one rule for exactly this kid and class."""
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    doc["sources"] = sources.from_doc(doc).with_rule(kid, course, assignments, grades).to_doc()
    config.save_config_doc(path, doc)


def remove_source_rule(home: Path, kid: str, course: str) -> None:
    set_source_rule(home, kid, course, None, None)
```

- [ ] **Step 4: `routes/settings.py`**

Add `from fastapi.responses import RedirectResponse` and `from ... import qr, sources` (replacing `from ... import qr`). In `_page`, add to the `render(...)` call:

```python
                  source_rules=actions.load_sources(state.home).rules, SOURCE_LABELS=sources.LABELS,
```

In `save`, add parameters `sources_assignments: str = Form("canvas"), sources_grades: str = Form("hac"),` and pass `sources_assignments=sources_assignments, sources_grades=sources_grades` into `actions.FormValues(...)`.

Append:

```python
@router.post("/settings/sources/remove")
def remove_source(kid: str = Form(""), course: str = Form(""), state=State):
    actions.remove_source_rule(state.home, kid, course)
    state.reload()
    return RedirectResponse("/settings", status_code=303)
```

- [ ] **Step 5: `settings.html`**

After the Archive folder paragraph (line 21), inside the form:

```html
  <p><label>Assignment scores come from <select name="sources_assignments">
     {% for v in ('canvas', 'hac') %}<option value="{{ v }}"{{ ' selected' if form.sources_assignments == v }}>{{ SOURCE_LABELS[v] }}</option>{% endfor %}</select></label>
     <label>Class averages come from <select name="sources_grades">
     {% for v in ('canvas', 'hac') %}<option value="{{ v }}"{{ ' selected' if form.sources_grades == v }}>{{ SOURCE_LABELS[v] }}</option>{% endfor %}</select></label><br>
     <span class="muted">Which gradebook wins when both have a number. The other still fills in what this one lacks.
       One class or one kid can differ: set it on the class's page.</span></p>
```

After `</form>` (line 39), outside it (forms cannot nest):

```html
{% if source_rules %}
<h3>Gradebook overrides</h3>
<table class="items"><tr><th>Kid</th><th>Class</th><th>Assignment scores</th><th>Class average</th><th></th></tr>
{% for r in source_rules %}<tr><td>{{ r.kid or 'Every kid' }}</td><td>{{ r.course or 'Every class' }}</td>
  <td>{{ SOURCE_LABELS[r.assignments] if r.assignments else 'Default' }}</td><td>{{ SOURCE_LABELS[r.grades] if r.grades else 'Default' }}</td>
  <td><form method="post" action="/settings/sources/remove"><input type="hidden" name="kid" value="{{ r.kid }}"><input type="hidden" name="course" value="{{ r.course }}"><button>Remove</button></form></td></tr>
{% endfor %}</table>
{% endif %}
```

- [ ] **Step 6: Run the whole suite**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task8.log | tail -5`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/actions.py fridgesheet/web/routes/settings.py fridgesheet/web/templates/settings.html tests/test_web_settings_page.py
git commit -m "settings: choose the household's gradebook for assignments and averages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Course page — "Sources for this class"

**Files:**
- Modify: `fridgesheet/web/routes/kid.py` (`course`; add `course_sources`)
- Modify: `fridgesheet/web/templates/course.html` (add a card inside `<div class="cards">`)
- Test: `tests/test_web_course_sources.py` (create)

**Interfaces:**
- Consumes: `actions.set_source_rule`, `SourcePrefs.rule_for` / `resolve` / `deciding_rule`, `sources.LABELS`, `sources.SOURCES`
- Produces: Route `POST /kids/{key}/courses/{course_id}/sources` (form fields `assignments`, `grades`; each `""`, `"canvas"` or `"hac"`; anything else counts as `""`) → 303 to the course page. The rule it writes is `kid = <student key>`, `course = <course short_name>`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_course_sources.py`:

```python
"""The course page writes the one rule for this kid and this class."""
from __future__ import annotations

from fastapi.testclient import TestClient

from fridgesheet import config
from fridgesheet.web import app as webapp
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, seed


def client(home, toml: str = "") -> tuple[TestClient, object]:
    (home / "config.toml").write_text(toml)
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=False)
    application.state.fridgesheet.clock = lambda: NOW
    return TestClient(application, headers=LOCAL_HOST_HEADERS), application


def course_id(home, short: str) -> int:
    conn = seed(home)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = ?", (short,)).fetchone()["id"]
    conn.close()
    return cid


def rules(home):
    return config.load_config_doc(home / "config.toml").get("sources", {}).get("rule")


def test_the_control_writes_a_short_name_rule_and_the_page_follows_it(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path)
    assert "Sources for this class" in c.get(f"/kids/Alex/courses/{cid}").text
    r = c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac", "grades": ""}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/kids/Alex/courses/{cid}"
    assert rules(tmp_path) == [{"kid": "Alex", "course": "Honors English 9", "assignments": "hac"}]
    assert "28/30" in c.get(f"/kids/Alex/courses/{cid}").text          # Quiz 1 now reads HAC's score


def test_saving_again_replaces_and_default_on_both_removes(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path)
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac", "grades": ""})
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "", "grades": "canvas"})
    assert rules(tmp_path) == [{"kid": "Alex", "course": "Honors English 9", "grades": "canvas"}]
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "", "grades": ""})
    assert rules(tmp_path) is None


def test_a_junk_value_counts_as_default(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path)
    c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "powerschool", "grades": ""})
    assert rules(tmp_path) is None


def test_the_control_names_a_broader_rule_in_force(tmp_path):
    cid = course_id(tmp_path, "Honors English 9")
    c, _ = client(tmp_path, '[[sources.rule]]\nkid = "Alex"\ngrades = "canvas"\n')
    assert "from a rule for Alex" in c.get(f"/kids/Alex/courses/{cid}").text


def test_another_kids_course_is_404(tmp_path):
    cid = course_id(tmp_path, "Science 7")
    c, _ = client(tmp_path)
    assert c.post(f"/kids/Alex/courses/{cid}/sources", data={"assignments": "hac"}).status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `env -u PYTHONPATH python3 -m pytest tests/test_web_course_sources.py -q`
Expected: FAIL (no "Sources for this class"; 405 on the POST).

- [ ] **Step 3: Route**

In `routes/kid.py`: change `from fastapi import APIRouter, HTTPException, Request` to `from fastapi import APIRouter, Form, HTTPException, Request`, add `from fastapi.responses import RedirectResponse`, and `from .. import actions` (the `sources` import was added in Task 6). In `course()`, after the `grade_lines = ...` line from Task 6:

```python
    source_ctx = {
        "own_rule": prefs.rule_for(s["key"], c["short_name"]),
        "household": prefs.default,
        "choice": prefs.resolve(s["key"], c["name"]),
        "deciding": {f: prefs.deciding_rule(s["key"], c["name"], f) for f in ("assignments", "grades")},
        "SOURCE_LABELS": sources.LABELS,
    }
```

and pass `**source_ctx` into `render(...)`. Append:

```python
@router.post("/kids/{key}/courses/{course_id}/sources")
def course_sources(key: str, course_id: int, assignments: str = Form(""), grades: str = Form(""),
                   conn: sqlite3.Connection = Db, state=State):
    """The rule for exactly this kid and this class, keyed by the class's short name: the full
    Canvas name is not contained in HAC's name for the same class, so a rule written from it
    would miss the HAC-only rows. "" (or anything unknown) means the household default."""
    s = student_or_404(conn, key)
    c = students.course(conn, course_id)
    if c is None or c["student_id"] != s["id"]:
        raise HTTPException(404, "no such course")

    def pick(v: str) -> str | None:
        return v if v in sources.SOURCES else None

    actions.set_source_rule(state.home, s["key"], c["short_name"], pick(assignments), pick(grades))
    state.reload()
    return RedirectResponse(f"/kids/{quote(key)}/courses/{course_id}", status_code=303)
```

- [ ] **Step 4: Template**

In `course.html`, add after the Teacher card, before the `</div>` that closes `cards`:

```html
  <div class="card"><h2>Sources for this class</h2>
    <form method="post" action="/kids/{{ student.key | urlencode }}/courses/{{ course.id }}/sources">
    {% for field, word in (('assignments', 'Assignment scores'), ('grades', 'Class average')) %}
      {% set mine = own_rule[field] if own_rule else none %}
      <p><label>{{ word }} <select name="{{ field }}">
        <option value=""{{ ' selected' if mine is none }}>Household default ({{ SOURCE_LABELS[household[field]] }})</option>
        {% for v in ('canvas', 'hac') %}<option value="{{ v }}"{{ ' selected' if mine == v }}>{{ SOURCE_LABELS[v] }}</option>{% endfor %}
      </select></label>
      {% set d = deciding[field] %}
      {% if d and mine is none %}<br><span class="muted">Now {{ SOURCE_LABELS[choice[field]] }}, from a rule for {{ d.kid or 'every kid' }}{{ ' in ' ~ d.course if d.course }}</span>{% endif %}</p>
    {% endfor %}
    <p><button>Save</button></p>
    </form>
  </div>
```

(Jinja's `x[field]` falls back to attribute lookup, so it reads the frozen dataclasses directly.)

- [ ] **Step 5: Run the whole suite**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task9.log | tail -5`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/routes/kid.py fridgesheet/web/templates/course.html tests/test_web_course_sources.py
git commit -m "course page: choose this class's gradebook for assignments and average

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Documentation

**Files:**
- Modify: `docs/outcomes.md:62-82` ("Which source is the source of truth")
- Modify: `README.md:152-179` (the `config.toml` example)

- [ ] **Step 1: `docs/outcomes.md`**

Replace the paragraph that begins "So the app pairs the two by course and then by assignment" (lines 77-82) with:

```markdown
So the app pairs the two by course and then by assignment, and reads both: submission and
marks from Canvas, and the score from the family's chosen source. Pairing is by title, with a
fallback for titles the two teachers typed differently — the same due date, the same points,
exactly one candidate, and every number in the two titles agreeing — because an assignment
that fails to pair shows up **twice**: once as *done on paper* from HAC and once as *unknown*
from Canvas.

### Choosing the source

By default assignment scores come from **Canvas** and class averages from **HAC**. Both can be
changed for the whole family on Settings, and for one kid or one class on the class's page
(`[sources]` in `config.toml`). The chosen source wins when both have a number; the other still
fills in what it lacks, so a class Canvas never lists still shows HAC's work and a kid whose
school uses one system still shows that system. Submitted, late and excused always come from
Canvas, because HAC does not record them. Under a HAC preference a HAC score settles the item:
a HAC 48/50 is *done on paper* even where Canvas says *missing*, and a HAC zero is *not done*
even where Canvas shows a score. The Reconcile page still lists every disagreement.

Paper work is not a reason on its own to prefer HAC. In this household's data on 2026-09-21,
20 of 27 past-due paper assignments were graded in Canvas. The real conflicts were one
teacher's online quizzes, auto-scored in Canvas and finalised in HAC — which is what a
per-class rule is for.
```

- [ ] **Step 2: `README.md`**

In the `config.toml` example block, after the `[kids]` table (line 161), insert:

```toml

# Which gradebook wins when both have a number (the other still fills gaps). These are the
# defaults; Settings changes them, and each class's page can override one class for one kid.
[sources]
assignments = "canvas"
grades = "hac"

[[sources.rule]]                      # first matching rule that sets a field wins
kid = "Alex"                          # optional; prefix match (Alex ~ Alexander)
course = "Honors Algebra II"          # optional; whole words of the class name
assignments = "hac"                   # this teacher finalises quiz scores in HAC
```

- [ ] **Step 3: Check the docs build nothing broken**

Run: `env -u PYTHONPATH python3 -m pytest -q 2>&1 | tee /tmp/sot-task10.log | tail -3`
Expected: all pass (some tests read `README.md`; keep the TOML valid).

- [ ] **Step 4: Commit**

```bash
git add docs/outcomes.md README.md
git commit -m "docs: choosing which gradebook is the source of truth

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

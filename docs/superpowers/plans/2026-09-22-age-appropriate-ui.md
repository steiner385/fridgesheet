# Age-Appropriate UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the pages a child reads in language, type, density and colour suited to that child's grade, without changing what information or controls they get.

**Architecture:** A `[kids].grades` setting maps each child to a grade; one pure function maps a grade to one of three tiers; the tier is written as a `data-tier` attribute on the element that owns a child's content; CSS custom properties and one phrase table do the rest. No template branches on tier.

**Tech Stack:** Python 3.11+, FastAPI, Jinja2, CSS custom properties, pytest.

**Spec:** `docs/superpowers/specs/2026-09-22-age-appropriate-ui-design.md`

## Global Constraints

- **Run tests with `.venv/bin/python -m pytest`** from the repo root.
- **One pre-existing failure is expected and is not yours:** `tests/test_host_credentials.py::test_settings_credentials_falls_back_to_store_username_then_errors` fails on a machine whose keyring holds real credentials, identically on clean `main`.
- **No grade set means today's interface, byte for byte.** An unset, unparseable or out-of-range grade yields the empty tier `""`, which renders exactly what ships today. Every task must preserve this.
- **Tiers are exactly:** `""` (unset), `early` (K–5), `middle` (6–8), `older` (9–12).
- **A phrase must never add a fact its adult equivalent does not carry.** No time, date or number may appear in a child phrase that is absent from the `older` phrase for the same concept. `due tomorrow morning` is allowed for 7:20am; `finish by bedtime` is not.
- **Colour never carries meaning alone.** Anything conveyed by colour at `older` is conveyed by colour *and* a word at `early`.
- **No template may branch on tier** (`{% if tier == 'early' %}`). Vocabulary lives in one table.
- **Config parsing falls back, it does not raise.** A value of the wrong shape keeps the default — a `TypeError` escaping config parsing tracebacks out of `schedule remove --all`, which the uninstaller runs hidden with its exit code discarded.
- **Commit after every task**, ending each message with:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`

### One correction to the spec, applied throughout

The spec's §5 says the CSS blocks are keyed `:root[data-tier="early"]`. Use **`[data-tier="early"]`** (no `:root`) instead. The spec's own scope includes the Open work page, which shows every child on one page and therefore needs a tier *per section* rather than one per document. An unanchored attribute selector works identically on `<body>` and on a `<section>`; `:root[...]` would only ever match `<html>`. Everything else in §5 is unchanged.

### A second correction, for the same reason

The spec's §6 resolves the tier in `web/app.py::page_context`. Use a **`tier_of` Jinja
filter** (student key → tier) instead. `page_context` takes only `request` and `conn`; the
student a page is about arrives later, in `render`'s `**ctx`, and the Open work page has no
single student at all. A filter reads a key wherever a template already holds one, which
covers both the one-child pages and the per-section case, and needs no change to
`page_context` or `render`. `tiers.for_student(settings, key)` is unchanged — the filter is
a one-line wrapper over it, registered beside `nickname`, which closes over `state` the same
way.

## File Structure

| File | Responsibility |
|---|---|
| `fridgesheet/config.py` | `Settings.grades`, parsed from `[kids].grades` |
| `fridgesheet/web/tiers.py` *(new)* | `tier(grade)` and `for_student(settings, key)`. Pure. |
| `fridgesheet/web/phrasing.py` *(new)* | The phrase table and `phrase(word, tier)`. Pure. |
| `fridgesheet/web/app.py` | Registers the `tier_of` and `phrase` Jinja filters |
| `fridgesheet/web/templates/base.html` | `data-tier` on `<body>` for single-child pages |
| `fridgesheet/web/templates/open.html` | `data-tier` per kid section |
| `fridgesheet/web/templates/plan_print.html` | `data-tier` on its own standalone `<body>` |
| `fridgesheet/web/static/app.css` | Three `[data-tier=…]` token blocks |
| `fridgesheet/web/templates/_item_rows.html`, `_case_group.html`, `_planning_evidence.html` | Read words through `| phrase(tier)` |

---

### Task 1: The `[kids].grades` setting

**Files:**
- Modify: `fridgesheet/config.py` (`Settings` field near line 203; parsing near line 308)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.Settings.grades: dict[str, int]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
# --- [kids].grades: which grade each child is in ---------------------------------------

def test_grades_default_to_empty():
    s = config.Settings()
    config.settings_from_doc({}, s)
    assert s.grades == {}


def test_grades_are_read_beside_the_nicknames():
    s = config.Settings()
    config.settings_from_doc({"kids": {"nicknames": {"Douglas": "Doug"},
                                       "grades": {"Douglas": 9, "Kayla": 5}}}, s)
    assert s.grades == {"Douglas": 9, "Kayla": 5}
    assert s.nicknames == {"Douglas": "Doug"}          # the neighbour still works


@pytest.mark.parametrize("bad", ["five", 5.5, None, [], True])
def test_a_grade_that_is_not_a_whole_number_is_dropped_not_raised(bad):
    """A child with an unreadable grade falls back to today's interface. Raising here would
    traceback out of `schedule remove --all`, which the uninstaller runs hidden."""
    s = config.Settings()
    config.settings_from_doc({"kids": {"grades": {"Douglas": bad, "Kayla": 5}}}, s)
    assert s.grades == {"Kayla": 5}


def test_a_grades_value_that_is_not_a_table_keeps_the_default():
    s = config.Settings()
    config.settings_from_doc({"kids": {"grades": "ninth"}}, s)
    assert s.grades == {}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_config.py -q -k grade`
Expected: FAIL, `AttributeError: 'Settings' object has no attribute 'grades'`

- [ ] **Step 3: Implement**

In `fridgesheet/config.py`, add the field beside `nicknames` (line 203):

```python
    #: Child key -> school grade (0 = kindergarten). Drives the age-appropriate presentation
    #: in `web/tiers.py`; a child not listed here reads exactly the interface that shipped
    #: before grades existed.
    grades: dict[str, int] = field(default_factory=dict)
```

And parse it beside the nicknames (after line 309):

```python
    raw_grades = kids.get("grades")
    # `bool` is an `int` subclass, so `grades = { Kayla = true }` would otherwise read as 1.
    s.grades = {str(k): v for k, v in raw_grades.items()
                if isinstance(v, int) and not isinstance(v, bool)} if isinstance(raw_grades, dict) else {}
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/config.py tests/test_config.py
git commit -m "config: [kids].grades, which grade each child is in

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Grade to tier

**Files:**
- Create: `fridgesheet/web/tiers.py`
- Test: `tests/test_tiers.py`

**Interfaces:**
- Consumes: `config.Settings.grades`
- Produces: `tiers.tier(grade: int | None) -> str`, `tiers.for_student(settings, key: str) -> str`, `tiers.TIERS: tuple[str, ...]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tiers.py`:

```python
"""Which presentation a child's grade earns.

Three tiers, not thirteen: school structure already clusters this way, and the difference
between 6th and 7th grade is not real. The empty tier is what shipped before grades existed,
and an unreadable grade must land there rather than guess.
"""
from __future__ import annotations

import pytest

from fridgesheet import config
from fridgesheet.web import tiers


@pytest.mark.parametrize("grade,expected", [
    (0, "early"), (1, "early"), (5, "early"),          # K-5
    (6, "middle"), (7, "middle"), (8, "middle"),       # 6-8
    (9, "older"), (11, "older"), (12, "older"),        # 9-12
])
def test_each_grade_lands_in_its_school(grade, expected):
    assert tiers.tier(grade) == expected


@pytest.mark.parametrize("boundary,expected", [(5, "early"), (6, "middle"), (8, "middle"), (9, "older")])
def test_the_boundaries_are_where_the_schools_are(boundary, expected):
    assert tiers.tier(boundary) == expected


@pytest.mark.parametrize("bad", [None, -1, 13, 99, "9", 9.5, True])
def test_anything_unreadable_is_the_interface_that_shipped(bad):
    """A typo must not silently pick a tier."""
    assert tiers.tier(bad) == ""


def test_for_student_reads_the_setting():
    s = config.Settings()
    s.grades = {"Douglas": 9, "Melanie": 7, "Kayla": 5}
    assert tiers.for_student(s, "Douglas") == "older"
    assert tiers.for_student(s, "Melanie") == "middle"
    assert tiers.for_student(s, "Kayla") == "early"


def test_a_child_with_no_grade_set_gets_the_shipped_interface():
    s = config.Settings()
    s.grades = {"Douglas": 9}
    assert tiers.for_student(s, "Kayla") == ""
    assert tiers.for_student(s, "") == ""
    assert tiers.for_student(s, None) == ""


def test_every_tier_name_is_in_TIERS():
    assert set(tiers.TIERS) == {"early", "middle", "older"}
    assert "" not in tiers.TIERS          # the absence of a tier is not a tier
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_tiers.py -q`
Expected: collection error, `ImportError: cannot import name 'tiers'`

- [ ] **Step 3: Implement**

Create `fridgesheet/web/tiers.py`:

```python
"""Which presentation a child's grade earns.

The pages a child reads -- the kid page, Open work, the check-in and the plan -- render the
same facts and offer the same actions whatever their age. What changes is type size,
density, colour and wording, and this is the one place a grade becomes that choice.

Three tiers rather than thirteen: school structure already clusters this way, the difference
between 6th and 7th grade is not real, and thirteen palettes is more than one person can
keep good. The empty tier is what shipped before grades existed; an unset or unreadable
grade lands there rather than guessing, so a household that never sets one sees no change.
"""
from __future__ import annotations

#: The tiers that have a presentation of their own. "" is not among them: it is the absence
#: of a grade, and it renders what shipped before this existed.
TIERS: tuple[str, ...] = ("early", "middle", "older")


def tier(grade) -> str:
    """"early" (K-5), "middle" (6-8), "older" (9-12), or "" for anything unreadable.

    `bool` is an `int` subclass, so it is excluded explicitly: `True` is not grade 1.
    """
    if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 12:
        return ""
    if grade <= 5:
        return "early"
    return "middle" if grade <= 8 else "older"


def for_student(settings, key) -> str:
    """The tier for one child, by their student key. Unknown child, no grade set, or no key
    at all -- all the same answer: the interface that shipped."""
    if not key:
        return ""
    return tier((getattr(settings, "grades", None) or {}).get(str(key)))
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tiers.py -q`
Expected: PASS, 26 passed

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/tiers.py tests/test_tiers.py
git commit -m "tiers: one grade-to-presentation mapping, and only one

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: The `tier_of` filter and the `data-tier` attribute

**Files:**
- Modify: `fridgesheet/web/app.py` (`_filters`, the return dict at line 143)
- Modify: `fridgesheet/web/templates/base.html:13`, `fridgesheet/web/templates/open.html:16`, `fridgesheet/web/templates/plan_print.html:13`
- Test: `tests/test_web_tier_markup.py` *(new)*

**Interfaces:**
- Consumes: `tiers.for_student`
- Produces: a `tier_of` Jinja filter (student key → tier string) and a `data-tier` attribute on every element that owns one child's content

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_tier_markup.py`:

```python
"""The tier reaches the page, on the element that owns one child's content.

`base.html` carries it for the pages about a single child. The Open work page shows every
child at once, so each kid section carries its own -- which is why the CSS keys on a bare
`[data-tier=...]` and not on `:root`.
"""
from __future__ import annotations

import re

import tomllib

from tests.web_fixtures import app_for, seed


def _grades(home, **by_key):
    """Write [kids].grades, the way a parent editing config.toml would."""
    p = home / "config.toml"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    rows = ", ".join(f"{k} = {v}" for k, v in by_key.items())
    p.write_text(text + f"\n[kids]\ngrades = {{ {rows} }}\n", encoding="utf-8")


def test_a_kid_page_carries_that_kids_tier(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=5)
    body = app_for(tmp_path).get("/kids/Alex").text
    assert re.search(r'<body[^>]*data-tier="early"', body)


def test_a_child_with_no_grade_set_gets_no_tier_attribute(tmp_path):
    """The shipped interface, byte for byte: no attribute at all, not data-tier=""."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert re.search(r"<body[^>]*>", body) and "data-tier" not in body


def test_two_children_on_one_page_each_carry_their_own_tier(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=9, Sam=5)
    body = app_for(tmp_path).get("/open").text
    assert re.search(r'<section class="kid"[^>]*id="Alex"[^>]*data-tier="older"', body) \
        or re.search(r'<section class="kid"[^>]*data-tier="older"[^>]*id="Alex"', body)
    assert 'data-tier="early"' in body and 'data-tier="older"' in body


def test_the_check_in_page_carries_the_tier(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=7)
    assert 'data-tier="middle"' in app_for(tmp_path).get("/kids/Alex/check-in").text


def test_the_printable_plan_carries_the_tier(tmp_path):
    """plan_print.html does not extend base.html -- it has a body of its own."""
    seed(tmp_path).close()
    _grades(tmp_path, Alex=5)
    body = app_for(tmp_path).get("/kids/Alex/plan/print").text
    assert re.search(r'<body[^>]*data-tier="early"', body)


def test_a_parent_tool_never_carries_a_tier(tmp_path):
    """Settings, Runs and the rest are read by an adult; tiering them would mean three
    presentations of pages no child opens."""
    seed(tmp_path).close()
    _grades(tmp_path, Alex=5)
    for path in ("/settings", "/runs", "/reports"):
        assert "data-tier" not in app_for(tmp_path).get(path).text, path
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_tier_markup.py -q`
Expected: FAIL — no `data-tier` anywhere

- [ ] **Step 3: Implement**

In `fridgesheet/web/app.py`, inside `_filters`, add beside `nickname`:

```python
    def tier_of(key: str) -> str:
        return tiers.for_student(state.settings, key)
```

and add it to the returned dict (line 143):

```python
    return {"wd_md_time": wd_md_time, "md": md, "time12": time12, "nickname": nickname,
            "wd_md": wd_md, "trigger_words": runs.trigger_label, "tier_of": tier_of}
```

Import it at the top of the file, beside the other `from . import` names:

```python
from . import db, staleness, tiers, updates
```

In `fridgesheet/web/templates/base.html`, replace line 13 (`<body>`):

```html
{# A page about one child carries that child's tier; the stylesheet keys on the attribute
   wherever it sits, so the Open work page can put it on each kid section instead. A child
   with no grade set gets no attribute at all -- the interface that shipped. #}
<body{% if student is defined and student %}{% set t = student.key | tier_of %}{% if t %} data-tier="{{ t }}"{% endif %}{% endif %}>
```

In `fridgesheet/web/templates/open.html`, replace line 16:

```html
<section class="kid" id="{{ s.key }}"{% set t = s.key | tier_of %}{% if t %} data-tier="{{ t }}"{% endif %}>
```

In `fridgesheet/web/templates/plan_print.html`, replace line 13:

```html
<body class="print-page"{% if student %}{% set t = student.key | tier_of %}{% if t %} data-tier="{{ t }}"{% endif %}{% endif %}>
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_tier_markup.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: only the documented `test_host_credentials` failure.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/app.py fridgesheet/web/templates/base.html \
        fridgesheet/web/templates/open.html fridgesheet/web/templates/plan_print.html \
        tests/test_web_tier_markup.py
git commit -m "web: carry each child's tier on the element that owns their content

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The three token blocks

**Files:**
- Modify: `fridgesheet/web/static/app.css` (the `:root` block at line 2)
- Test: `tests/test_web_tier_css.py` *(new)*

**Interfaces:**
- Consumes: the `data-tier` attribute from Task 3
- Produces: `[data-tier="early"|"middle"|"older"]` blocks redefining the existing palette tokens plus a new `--type-root`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_tier_css.py`:

```python
"""Each tier defines every token it overrides.

A half-defined tier is a page with inherited colours nobody designed -- worse than no tier
at all, because it looks deliberate. CSS is not executed here, so these pin the rules; the
look itself is a judgement made in a browser.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fridgesheet.web import tiers

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")

#: Every token a tier is allowed to move. `--type-root` is new; the rest already exist.
TOKENS = ("--ink", "--muted", "--rule", "--paper", "--wash", "--accent", "--warn", "--ok", "--type-root")


def _block(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S)
    assert m, f"no {selector} block"
    return m.group(1)


def test_the_default_root_defines_every_token():
    """A tier overrides; the root is what it overrides from."""
    root = _block(":root")
    for tok in TOKENS:
        assert f"{tok}:" in root, tok


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_every_tier_defines_every_token(tier):
    block = _block(f'[data-tier="{tier}"]')
    for tok in TOKENS:
        assert f"{tok}:" in block, f"{tier} leaves {tok} inherited"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_a_tier_keys_on_the_attribute_alone_not_on_root(tier):
    """The Open work page puts the attribute on a section, not on <html>."""
    assert f':root[data-tier="{tier}"]' not in CSS
    assert f'[data-tier="{tier}"]' in CSS


def test_the_root_font_size_comes_from_the_token():
    """Otherwise a tier can set --type-root and nothing reads it."""
    assert re.search(r"(html|body)\s*\{[^}]*font-size:\s*var\(--type-root\)", CSS)


def test_the_younger_tiers_set_larger_type():
    def px(tier):
        return int(re.search(r"--type-root:\s*(\d+)px", _block(f'[data-tier="{tier}"]')).group(1))
    assert px("early") > px("middle") > px("older")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_tier_css.py -q`
Expected: FAIL — no `--type-root`, no tier blocks

- [ ] **Step 3: Implement**

In `fridgesheet/web/static/app.css`, replace line 2 (the `:root` block) with:

```css
:root { --ink: #1c1c1c; --muted: #6b6b6b; --rule: #d9d9d9; --paper: #fff; --wash: #f4f4f2; --accent: #1f5fa8; --warn: #b3261e; --ok: #2e7d32; --type-root: 16px; }

/* The presentation a child's grade earns (web/tiers.py). The attribute is not anchored to
   :root on purpose: a page about one child carries it on <body>, and the Open work page --
   which shows every child at once -- carries it on each kid section instead.

   A tier redefines every token rather than some, so no page ever inherits a colour nobody
   designed. Nothing conveyed by colour alone: what is red here is red *and* a word, which
   is the accessibility requirement and the age requirement at the same time. */
[data-tier="early"]  { --ink: #10151b; --muted: #4a5568; --rule: #b9c6d4; --paper: #fff; --wash: #eef4fb; --accent: #0b5cab; --warn: #a3170f; --ok: #1d6b27; --type-root: 20px; }
[data-tier="middle"] { --ink: #161b22; --muted: #5a6474; --rule: #ccd5de; --paper: #fff; --wash: #f1f5f9; --accent: #14539b; --warn: #a81d14; --ok: #24702c; --type-root: 18px; }
[data-tier="older"]  { --ink: #1c1c1c; --muted: #6b6b6b; --rule: #d9d9d9; --paper: #fff; --wash: #f4f4f2; --accent: #1f5fa8; --warn: #b3261e; --ok: #2e7d32; --type-root: 16px; }

/* A tier sets its type scale here; everything sized in rem follows it. */
html { font-size: var(--type-root); }

/* Roomier rows for the younger readers -- the same rows, with space to land a finger and
   to tell one from the next. */
[data-tier="early"] table.items th, [data-tier="early"] table.items td { padding: 12px 10px; }
[data-tier="middle"] table.items th, [data-tier="middle"] table.items td { padding: 9px 9px; }
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_tier_css.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/static/app.css tests/test_web_tier_css.py
git commit -m "css: a token block per tier, every token defined

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: The phrase table

**Files:**
- Create: `fridgesheet/web/phrasing.py`
- Modify: `fridgesheet/web/app.py` (`_filters`)
- Test: `tests/test_phrasing.py` *(new)*

**Interfaces:**
- Consumes: `tiers.TIERS`
- Produces: `phrasing.phrase(word: str, tier: str) -> str`, `phrasing.PHRASES: dict[str, dict[str, str]]`, and a `phrase` Jinja filter used as `{{ word | phrase(tier) }}`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_phrasing.py`:

```python
"""The same fact in fewer words, and never a fact nobody gave us.

This app's discipline is not to say more than the sources support -- a fabricated due hour
was removed from the whole app for exactly that reason. Age-appropriate language is
therefore *simpler true statements*, never friendlier approximations: "due tomorrow morning"
is true of 7:20am; "finish by bedtime" is invented.
"""
from __future__ import annotations

import re

import pytest

from fridgesheet.web import phrasing, tiers


def test_the_adult_word_is_the_word_that_ships_today():
    assert phrasing.phrase("Missing", "older") == "Missing"
    assert phrasing.phrase("Zero", "older") == "Zero"


def test_a_younger_reader_gets_the_same_fact_in_plainer_words():
    assert phrasing.phrase("Missing", "early") == "Teacher hasn't got it"
    assert phrasing.phrase("Missing", "middle") == "Marked missing"


def test_no_tier_is_the_word_that_ships_today():
    """A household that set no grade sees no change."""
    for word in phrasing.PHRASES:
        assert phrasing.phrase(word, "") == word


def test_a_word_nobody_translated_is_shown_as_it_is():
    """Never a blank: an untranslated word is the current word."""
    assert phrasing.phrase("Excused", "early") == "Excused"
    assert phrasing.phrase("something new", "early") == "something new"


def test_a_concept_missing_one_tier_falls_back_to_the_adult_word():
    table = dict(phrasing.PHRASES, tester={"older": "widget"})
    assert phrasing.phrase("tester", "early", table=table) == "widget"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_no_phrase_invents_a_number_a_date_or_a_time(tier):
    """The guard that keeps "simpler" from becoming "made up". A phrase table is copy, and
    copy is where invented precision comes back."""
    for word, by_tier in phrasing.PHRASES.items():
        adult = by_tier.get("older", word)
        allowed = set(re.findall(r"\d+", adult))
        for found in re.findall(r"\d+", by_tier.get(tier, adult)):
            assert found in allowed, f"{word!r} at {tier!r} invents the number {found!r}"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_every_concept_has_a_phrase_for_every_tier(tier):
    for word, by_tier in phrasing.PHRASES.items():
        assert by_tier.get(tier), f"{word!r} has nothing for {tier!r}"


def test_the_table_covers_the_words_a_child_actually_meets():
    """The status words and reconcile kinds that render on a child's pages."""
    for word in ("Missing", "Zero", "Paper, check", "Late, ungraded", "Submitted, ungraded",
                 "disagree", "past_credit", "one_source", "paper_no_grade", "actionable"):
        assert word in phrasing.PHRASES, word
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_phrasing.py -q`
Expected: collection error, `ImportError: cannot import name 'phrasing'`

- [ ] **Step 3: Implement**

Create `fridgesheet/web/phrasing.py`:

```python
"""One table of words, three columns wide.

A child reads the same rows an adult does. What changes is how much vocabulary the row
assumes they already have -- `past credit` and `disagree` are accurate and useless to a
ten-year-old who has not been taught the model they belong to.

Every younger phrase is the same fact in fewer words. None adds a claim: "Teacher hasn't got
it" is what Canvas's `missing` flag means, and it is not a verdict on the child. A phrase
that states a time, a date or a number its adult equivalent does not is a bug, and a test
holds the whole table to that.

The table lives here rather than in the templates because a vocabulary expressed as
`{% if tier == 'early' %}` across fifteen files is the same vocabulary implemented fifteen
times, which is the pattern this codebase rejects everywhere else.
"""
from __future__ import annotations

#: concept -> tier -> the words. `older` is what ships today, so the empty tier and `older`
#: read identically; they are separate so a later change to `older` leaves the households
#: that set no grade alone.
PHRASES: dict[str, dict[str, str]] = {
    # --- the status word on a row -----------------------------------------------------
    "Missing":             {"early": "Teacher hasn't got it", "middle": "Marked missing", "older": "Missing"},
    "Zero":                {"early": "Marked 0 - ask about it", "middle": "Scored 0", "older": "Zero"},
    "Paper, check":        {"early": "On paper - hand it in", "middle": "Paper, no grade yet", "older": "Paper, check"},
    "Late, ungraded":      {"early": "Handed in late, no grade yet", "middle": "Late, not graded", "older": "Late, ungraded"},
    "Submitted, ungraded": {"early": "Handed in - waiting", "middle": "Submitted, not graded", "older": "Submitted, ungraded"},
    "Unpublished":         {"early": "Not open yet", "middle": "Not published", "older": "Unpublished"},
    # --- what the two sources disagree about ------------------------------------------
    "disagree":            {"early": "Ask your teacher", "middle": "Sources disagree", "older": "disagree"},
    "past_credit":         {"early": "Too late to fix", "middle": "Past the credit window", "older": "past credit"},
    "one_source":          {"early": "Only one system lists it", "middle": "Only one source lists it", "older": "one source"},
    "paper_no_grade":      {"early": "On paper - hand it in", "middle": "Paper, no grade yet", "older": "paper no grade"},
    "submitted_ungraded":  {"early": "Handed in - waiting", "middle": "Submitted, not graded", "older": "submitted ungraded"},
    # --- the badge that means "you can still do something about this" -----------------
    "actionable":          {"early": "Can still fix", "middle": "Still fixable", "older": "actionable"},
}


def phrase(word: str, tier: str, *, table: dict[str, dict[str, str]] | None = None) -> str:
    """`word` said for `tier`.

    Two fallbacks, both to the word that ships today rather than to a blank: a concept in the
    table with nothing for this tier yields its `older` entry, and a concept absent from the
    table yields `word` unchanged. A word nobody has translated is shown as it is; it is
    never dropped.
    """
    by_tier = (table if table is not None else PHRASES).get(word)
    if not by_tier or not tier:
        return word
    return by_tier.get(tier) or by_tier.get("older") or word
```

In `fridgesheet/web/app.py`, add to `_filters` beside `tier_of`:

```python
    def phrase(word, tier: str = "") -> str:
        return phrasing.phrase(str(word or ""), tier)
```

add `"phrase": phrase` to the returned dict, and add `phrasing` to the `from . import` line:

```python
from . import db, phrasing, staleness, tiers, updates
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_phrasing.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/phrasing.py fridgesheet/web/app.py tests/test_phrasing.py
git commit -m "phrasing: one table of words, three columns wide

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: The pages read through the table

**Files:**
- Modify: `fridgesheet/web/templates/_item_rows.html` (the status/grade cell and the case-kind badges), `fridgesheet/web/templates/_case_group.html`, `fridgesheet/web/templates/open.html`
- Test: `tests/test_web_tier_wording.py` *(new)*

**Interfaces:**
- Consumes: the `phrase` and `tier_of` filters
- Produces: child-facing pages whose words follow the reader's tier

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_tier_wording.py`:

```python
"""The words on the page follow the reader.

Same rows, same actions, plainer words. The fixture's Quiz 1 is Canvas-missing and HAC-graded
-- it carries both a status word and a `disagree` badge, so one row exercises both paths.
"""
from __future__ import annotations

from tests.web_fixtures import app_for, seed


def _grades(home, **by_key):
    p = home / "config.toml"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    rows = ", ".join(f"{k} = {v}" for k, v in by_key.items())
    p.write_text(text + f"\n[kids]\ngrades = {{ {rows} }}\n", encoding="utf-8")


def test_a_young_reader_sees_the_plain_words(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=5)
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "Teacher hasn't got it" in body
    assert ">Missing<" not in body


def test_a_middle_reader_sees_the_middle_words(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=7)
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "Marked missing" in body


def test_an_older_reader_sees_exactly_what_ships_today(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=9)
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_no_grade_set_renders_the_shipped_words(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "Missing" in body and "Teacher hasn't got it" not in body


def test_the_reconcile_kinds_follow_the_reader_too(tmp_path):
    seed(tmp_path).close()
    _grades(tmp_path, Alex=5)
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "Ask your teacher" in body          # `disagree` on Quiz 1
    assert ">disagree<" not in body
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_web_tier_wording.py -q`
Expected: FAIL — the pages still render the adult words

- [ ] **Step 3: Implement**

`_item_rows.html` and `_case_group.html` are included from pages that may or may not have a
tier, so each computes it once from the student it is already given.

In `fridgesheet/web/templates/_item_rows.html`, immediately after the opening `{#` comment
block (before `{% macro sortable`), add:

```jinja
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
```

Then in the row body, replace the grade cell's bare `{{ v.grade }}`:

```jinja
    <td class="grade {{ 'zero' if v.grade_zero }} {{ 'missing' if v.grade == 'Missing' }}">{{ v.grade | phrase(tier) }}</td>
```

and the two badge loops:

```jinja
        {% if v.actionable %}<span class="badge">{{ 'actionable' | phrase(tier) }}</span>{% endif %}
```

```jinja
        {% for k in v.case_kinds %}<span class="badge warn">{{ k | phrase(tier) }}</span>{% endfor %}
```

Note the case-kind loop no longer calls `.replace('_', ' ')`: the table's `older` column
already carries the spaced form (`"past credit"`), and an untranslated kind falls through
`phrase` unchanged.

In `fridgesheet/web/templates/_case_group.html`, add the same `{% set tier %}` line at the
top and read the two words through it:

```jinja
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
```

then replace `{{ item.status }}` with `{{ item.status | phrase(tier) }}` and
`{{ c.kind.replace('_', ' ') }}` with `{{ c.kind | phrase(tier) }}`.

In `fridgesheet/web/templates/open.html`, each kid section already has `s`; inside the
section, set `{% set tier = s.key | tier_of %}` before the tables so the included row
partial inherits it.

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_tier_wording.py -q`
Expected: PASS

- [ ] **Step 5: Run the whole suite and fix what the rewording broke**

Run: `.venv/bin/python -m pytest -q`
Expected: failures only in tests that assert on an adult word rendered for a child with a
grade set. There should be none, because no existing fixture sets a grade — if one fails,
read it before changing it: a test that breaks without a grade set means the empty tier is
no longer the shipped interface, which is a bug in this task, not in the test.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/templates/_item_rows.html fridgesheet/web/templates/_case_group.html \
        fridgesheet/web/templates/open.html tests/test_web_tier_wording.py
git commit -m "web: child-facing pages read their words through the phrase table

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: "Due tomorrow morning"

**Files:**
- Modify: `fridgesheet/dates.py` (beside `due_time`)
- Modify: `fridgesheet/web/stores/items.py` (`ItemView`, and its construction)
- Modify: `fridgesheet/web/templates/_item_rows.html` (the due cell)
- Test: `tests/test_due_times.py`

**Interfaces:**
- Consumes: `dates.due_time`
- Produces: `dates.day_part(d: datetime | None, *, from_canvas: bool) -> str` and `ItemView.due_part: str`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_due_times.py`:

```python
# --- the hour, for a reader who does not yet read a clock quickly ----------------------

@pytest.mark.parametrize("h,expected", [
    (7, "morning"), (11, "morning"),
    (12, "afternoon"), (16, "afternoon"),
    (17, "evening"), (23, "evening"),
])
def test_a_canvas_hour_has_a_part_of_the_day(h, expected):
    from fridgesheet.dates import day_part
    assert day_part(_at(h, 20), from_canvas=True) == expected


def test_a_hac_only_item_has_no_part_of_the_day():
    """Same rule as the hour itself: HAC never gave one, so the app does not offer one."""
    from fridgesheet.dates import day_part
    assert day_part(_at(23, 59), from_canvas=False) == ""
    assert day_part(None, from_canvas=True) == ""


def test_the_part_of_day_is_the_hour_it_already_shows(tmp_path):
    """Not a new fact -- the same timestamp, said in a word."""
    from fridgesheet.dates import day_part, due_time
    d = _at(7, 20)
    assert due_time(d, from_canvas=True) == "7:20am" and day_part(d, from_canvas=True) == "morning"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_due_times.py -q -k "day_part or part_of"`
Expected: FAIL, `ImportError: cannot import name 'day_part'`

- [ ] **Step 3: Implement**

In `fridgesheet/dates.py`, beside `due_time`:

```python
def day_part(d: datetime | None, *, from_canvas: bool) -> str:
    """"morning", "afternoon", "evening" -- or "" when nobody told us an hour.

    The same timestamp `due_time` formats, said in a word a reader who does not yet read a
    clock at a glance can act on. It adds nothing: 7:20am *is* the morning. A HAC-only item
    has no hour to name, for the same reason it has no time to show.
    """
    if d is None or not from_canvas:
        return ""
    if d.hour < 12:
        return "morning"
    return "afternoon" if d.hour < 17 else "evening"
```

In `fridgesheet/web/stores/items.py`, add the field beside `due_time`:

```python
    #: "morning" | "afternoon" | "evening" | "" -- `due_time`'s hour as a word, for the
    #: youngest readers (`dates.day_part`).
    due_part: str = ""
```

and set it where `due_time` is set:

```python
            due_time=due_time(due, from_canvas="canvas" in obs),
            due_part=day_part(due, from_canvas="canvas" in obs),
```

importing `day_part` alongside `due_time` at the top of that file.

In `fridgesheet/web/templates/_item_rows.html`, the due cell shows the part of day instead
of the clock time for the youngest tier only:

```jinja
    <td class="due">{{ v.due | md if v.due else '' }}{% if tier == 'early' %}{% if v.due_part %} <span class="at">{{ v.due_part }}</span>{% endif %}{% elif v.due_time %} <span class="at">{{ v.due_time }}</span>{% endif %}{% if v.due_relative %} <span class="rel">{{ v.due_relative }}</span>{% endif %}</td>
```

This is the one place a template reads the tier as a value rather than through a filter. It
is a presentation switch between two facts the row already holds, not a vocabulary — the
words themselves still come from `dates`.

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_due_times.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/dates.py fridgesheet/web/stores/items.py \
        fridgesheet/web/templates/_item_rows.html tests/test_due_times.py
git commit -m "dates: the due hour as a part of the day, for the youngest readers

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: The parity guard

**Files:**
- Test: `tests/test_web_tier_parity.py` *(new)*

**Interfaces:**
- Consumes: everything above. Adds no production code.

- [ ] **Step 1: Write the test**

This task is a guard, not a feature: it should pass the moment it is written. If it does
not, an earlier task hid something from a child and that is the bug to fix.

Create `tests/test_web_tier_parity.py`:

```python
"""Simplification must never become concealment.

This is the failure this feature is most exposed to, and the one a child would never report:
they would not know an assignment had been left off their page. So every tier renders the
same rows -- different words, same facts.
"""
from __future__ import annotations

import re

import pytest

from fridgesheet.web import tiers
from tests.web_fixtures import app_for, seed


def _grades(home, **by_key):
    p = home / "config.toml"
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    rows = ", ".join(f"{k} = {v}" for k, v in by_key.items())
    p.write_text(text + f"\n[kids]\ngrades = {{ {rows} }}\n", encoding="utf-8")


GRADE_OF = {"early": 5, "middle": 7, "older": 11, "": None}


def _row_ids(tmp_path_factory, tier: str, path: str) -> set[str]:
    home = tmp_path_factory.mktemp(f"parity-{tier or 'none'}")
    seed(home).close()
    if GRADE_OF[tier] is not None:
        _grades(home, Alex=GRADE_OF[tier])
    return set(re.findall(r'id="row-(\d+)"', app_for(home).get(path).text))


@pytest.mark.parametrize("tier", list(tiers.TIERS) + [""])
@pytest.mark.parametrize("path", ["/kids/Alex?show=all", "/kids/Alex?show=open", "/open"])
def test_every_tier_renders_every_row_the_oldest_gets(tmp_path_factory, tier, path):
    older = _row_ids(tmp_path_factory, "older", path)
    assert older, "the fixture must render rows for this to mean anything"
    assert _row_ids(tmp_path_factory, tier, path) == older


def test_no_tier_hides_a_badge_the_oldest_gets(tmp_path_factory):
    """The words differ; the number of things said about a row does not."""
    def badges(tier):
        home = tmp_path_factory.mktemp(f"badge-{tier or 'none'}")
        seed(home).close()
        if GRADE_OF[tier] is not None:
            _grades(home, Alex=GRADE_OF[tier])
        body = app_for(home).get("/kids/Alex?show=all").text
        return len(re.findall(r'<span class="badge', body))
    for tier in list(tiers.TIERS) + [""]:
        assert badges(tier) == badges("older"), tier
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_web_tier_parity.py -q`
Expected: PASS. A failure here means an earlier task dropped a row or a badge for younger
readers — fix that task, never this test.

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: only the documented `test_host_credentials` failure.

- [ ] **Step 4: Commit**

```bash
git add tests/test_web_tier_parity.py
git commit -m "tests: every tier renders every row the oldest gets

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Documentation

**Files:**
- Modify: `README.md` (the `config.toml` block), `docs/outcomes.md`
- Test: none new; the suite must stay green.

- [ ] **Step 1: Document the setting in README's config.toml block**

Add to the `[kids]` section of the example:

```toml
[kids]
nicknames = { Douglas = "Doug" }
# Each child's school grade (0 = kindergarten). The pages a child reads -- their own page,
# Open work, the check-in and the plan -- use it to pick type size, density, colour and
# wording. A child not listed here sees exactly the interface that shipped before this
# existed, so leaving it out changes nothing.
grades = { Douglas = 9, Melanie = 7, Kayla = 5 }
```

- [ ] **Step 2: Add a row to `docs/outcomes.md`**

In the table that lists where each outcome shows up, add:

```markdown
| **How it is worded** | Every child sees every row and every action. A `[kids].grades` entry changes type, density, colour and vocabulary only (`web/tiers.py`, `web/phrasing.py`) — never which rows appear, which `tests/test_web_tier_parity.py` holds. No child phrase states a time, date or number its adult equivalent does not. |
```

- [ ] **Step 3: Run the whole suite**

Run: `.venv/bin/python -m pytest -q`
Expected: unchanged — only the documented `test_host_credentials` failure. Note
`tests/test_rebrand.py` greps shipped docs; the words added here contain no old brand name.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/outcomes.md
git commit -m "docs: [kids].grades, and what it may and may not change

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## Verification

1. `.venv/bin/python -m pytest -q` — one documented failure, no others.
2. `git log --oneline main..HEAD` — nine commits, one per task.
3. **Look at it in a browser.** These tests pin structure and vocabulary; they cannot tell you whether the `early` palette is pleasant or the 20px scale is right on the kiosk. Set a grade for each child and open the kid page and Open work at kiosk width (864×1392) and phone width (390×844).
4. The PR must say what was not verified: no child has read these pages yet, and the three palettes are a judgement, not a measurement.

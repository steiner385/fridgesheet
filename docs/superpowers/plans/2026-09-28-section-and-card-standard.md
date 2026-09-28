# Section-and-card standard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every page's content column is a stack of one section block, and every assignment is drawn by one partial with five slots at three densities, so the app stops feeling noisy.

**Architecture:** New CSS blocks (`.sec`, `.item`, `.lines`, `.inset`, tokens) land beside the old rules first; one new Jinja partial `_item.html` replaces the six containers that draw an assignment; pages are converted in the spec's order (Assignments, Questions, Check-in/Plan, the rest); the old rules and classes are retired last, held out by a test. No route changes its contract; no row or action is added or removed (the parity rule).

**Tech Stack:** Python 3 / FastAPI, Jinja2 templates, htmx, one hand-written stylesheet (`fridgesheet/web/static/app.css`), pytest with `starlette.testclient`. No build step.

**Spec:** `docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md` (mockups beside it in `2026-09-28-sections-and-items-mockups/`; `mock.css` there is the CSS this plan lands).

## Global Constraints

- Run tests as `env -u PYTHONPATH $PYTEST ...` where `PYTEST=/home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/pytest` (this worktree has no venv; `PYTHONPATH` shadows the `tests` package). Run from the worktree root `/home/tony/GitHub/.ccswitch/worktrees/fridgesheet/bda39e1d`.
- The parity rule: every tier and kid mode render the same rows and actions (`tests/test_web_tier_parity.py` compares `row-`/`q-`/`qc-` ids and the counts of `<form` and `<button`). Never add or drop a form or button for one tier.
- Every phrase key has all three tiers (`early`, `middle`, `older`) with the same `{placeholders}`; no tier states a number, a day word or a span of days the older text lacks (`tests/test_phrasing.py`).
- The `?card=q-<id>` / `/items/{id}/question?slot=` round trip, the `qd-` slot prefix inside a detail, and the `qc-` slot on the check-in are unchanged (`tests/test_web_ui_flow.py`, `tests/test_web_checkin_verdicts.py`).
- Tokens: `--radius: 8px`; gap scale `--s1: 4px`, `--s2: 8px`, `--s3: 12px`, `--s4: 16px`, `--s5: 24px`, `--s6: 32px`.
- Fold names in an item's foot, in this order: Record, History (n), Notes (n), Plan a step / Plan another step, More.
- The glossary sentence (`copy.sources_hint`) appears at most once in any page's HTML and never inside a record.
- Commit after every task; commit messages in this repo are one sentence saying what changed and why, no conventional-commit prefix, ending with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Deviations from the spec text, in favour of the approved renderings

The mockups were approved before the spec was written and the two disagree in four places. The renderings win; Task 3 amends the spec's §4.1 to match.

1. **The head's right-hand word.** The spec says it is always the `standing` phrase. The renderings show the due date on a question card. Rule used here: the includer's `word` if given (Must finish passes the sheet's word); else "due {date} {time}" when the verdict is a question or the item is upcoming; else the `standing` phrase, with the due date moved into `.meta`.
2. **`.done-line` stays**, as the line density's standalone form (a `.line.ok` with its own box when it replaces a whole card, no box when it sits inside a Must-finish row). The spec listed it among retired classes.
3. **Notes and More on card density.** A card in a list has no notes or history loaded. On card density, "Notes (n)" is the link that fetches the detail into the card (today's "Add a note" link, the `?card=` mechanism); History, the Notes fold with `_notes.html`, and More (the flag menu) are detail density only. A Must-finish row (whose box id is `mf-<id>`, not a card id) has no Notes link; its name links to the row on Assignments.
4. **A family step is drawn with the item classes inline** in `_plan_panel.html`, not through `_item.html`: a step is a `plan_steps` row, not an `ItemView`, and the partial keys on the item's verdict.

## Review Focus

1. **An assignment name with no spaces or a very long one** must wrap inside its card, not push the page wide: `.item { overflow-wrap: anywhere }` (Task 1's CSS test).
2. **A note added to an item** must change the card's foot from "Notes (0)" to "Notes (1)" on the next load, since the count comes from `item.notes` (Task 3's test).
3. **A finished check-in** must show "Last check-in … · Next check-in …" and "What we agreed" in the state line under the tabs, and "time to check in" once the next date has passed (Task 6's test).
4. **Kid mode** (the `fridgesheet_who` cookie) draws no child tabs but must still draw the state line (Task 4's test).
5. **The flag menu under More on a detail with a card id** must still post back with the card id so Close returns to the card (`tests/test_web_ui_flow.py::test_a_flag_change_on_such_a_detail_keeps_the_way_back`, kept passing in Task 3).

---

### Task 1: Tokens and the new CSS blocks, beside the old rules

**Files:**
- Modify: `fridgesheet/web/static/app.css` (`:root` at line 7; append a new block at the end)
- Create: `tests/test_web_section_and_card.py`

**Interfaces:**
- Produces: the classes every later task's templates use: `.sec`, `.sec-head`, `.lead`, `.count`, `.controls`, `details.sec > summary`, `.sec.quiet`, `.item` (`.ask`/`.red`/`.ok`/`.grey`), `.item-head` (`.name`, `.meta`, `.when`, `.when.word`, `.close-detail`), `.facts`, `.ask-line`, `.answers`, `.ours`, `.item-foot` (`.stamp`), `.inset` (`.inset.warn`), `.sources` (`.src`, `.stamp`), `.lines`/`.line` (`.glyph`), `.done-line`, `.badge` (neutral), `.tab-hint`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_web_section_and_card.py`:

```python
"""One section, one card (docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md).

Holds the standard the way test_web_page_layout.py holds the page layout: the tokens, the
section head, the item's five slots at three densities, and, once every page is converted,
the absence of the classes it retired. CSS is not executed here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
TEMPLATES = WEB / "templates"


def _root() -> str:
    return re.search(r":root\s*\{([^}]*)\}", CSS).group(1)


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


# --- §6: tokens ---------------------------------------------------------------------------------

def test_the_root_defines_the_radius_and_the_gap_scale():
    root = _root()
    assert re.search(r"--radius:\s*8px", root)
    for tok, px in (("--s1", 4), ("--s2", 8), ("--s3", 12), ("--s4", 16), ("--s5", 24), ("--s6", 32)):
        assert re.search(rf"{tok}:\s*{px}px", root), f"{tok} is not {px}px"


# --- §3: the section ----------------------------------------------------------------------------

def test_a_section_head_is_one_wrapping_row_and_a_folded_section_draws_the_same_head():
    assert re.search(r"\.sec\s*\{[^}]*margin: 0 0 var\(--s6\)", CSS)
    head = _rule(".sec-head, details.sec > summary")
    assert "display: flex" in head and "flex-wrap: wrap" in head
    assert re.search(r"\.sec-head h3, details\.sec > summary h3\s*\{[^}]*font-size: 18px", CSS)
    assert re.search(r"\.sec\.quiet h3\s*\{[^}]*color: var\(--muted\)", CSS)
    assert re.search(r"\.sec-head \.lead\s*\{[^}]*flex-basis: 100%", CSS)
    assert re.search(r"\.sec-head \.controls\s*\{[^}]*margin-left: auto", CSS)


# --- §4: the item surface -----------------------------------------------------------------------

def test_the_item_is_one_box_with_a_left_rule_that_names_its_tone():
    item = _rule(".item")
    assert "border-radius: var(--radius)" in item and "border-left: 4px solid var(--rule)" in item
    assert "overflow-wrap: anywhere" in item                                   # a long name wraps
    for tone, colour in (("ask", "--accent"), ("red", "--warn"), ("ok", "--ok")):
        assert re.search(rf"\.item\.{tone}\s*\{{[^}}]*border-left-color: var\({colour}\)", CSS), tone
    assert re.search(r"\.item\.grey\s*\{[^}]*color: var\(--muted\)", CSS)
    assert re.search(r"\.item-head \.when\s*\{[^}]*margin-left: auto", CSS)
    assert re.search(r"\.item-head \.when\.word\s*\{[^}]*color: var\(--warn\)", CSS)
    assert re.search(r"\.item-foot\s*\{[^}]*font-size: var\(--type-small\)", CSS)
    assert re.search(r"\.item-foot \.stamp\s*\{[^}]*font-size: var\(--type-tiny\)", CSS)
    assert re.search(r"\.ours\s*\{[^}]*border-left: 3px solid var\(--accent\)", CSS)


def test_the_inset_the_record_and_the_lines_share_the_radius():
    for sel in (".inset", ".lines"):
        assert "border-radius: var(--radius)" in _rule(sel), sel
    assert re.search(r"\.sources\s*\{[^}]*grid-template-columns: max-content 1fr", CSS)
    assert re.search(r"\.sources \.stamp\s*\{[^}]*grid-column: 2", CSS)
    assert re.search(r"\.done-line\s*\{[^}]*border-left: 4px solid var\(--ok\)", CSS)
    assert re.search(r"\.item \.done-line\s*\{[^}]*border: 0", CSS)


def test_a_badge_is_one_neutral_style():
    badge = _rule(".badge, .badge.flag, .badge.plan")
    assert "background: var(--wash)" in badge and "color: var(--ink)" in badge


def test_the_new_targets_are_44px_under_a_finger():
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    for sel in (".item-foot summary", ".item-foot a", "details.sec > summary", ".lines .line > a"):
        assert re.search(re.escape(sel) + r"[^{]*\{[^}]*min-height: 44px", coarse), sel
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py -q`
Expected: 6 failed (no `--radius` at the root, no `.sec` rule, …).

- [ ] **Step 3: Add the tokens to `:root`**

In `fridgesheet/web/static/app.css` line 7, the `:root` declaration ends with `--pad: 24px; }`. Change it to end with:

```css
--pad: 24px; --radius: 8px; --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 32px; }
```

- [ ] **Step 4: Append the new blocks at the end of `app.css`**

```css

/* One section, one card (docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md).
   The content column below the page head is a stack of sections 32px apart; an assignment is one
   box with five slots; anything quoted inside it is one inset. The rules above that these
   replace (.q, .record, .mf-row, .plan-panel, .plan-card, .review-card, .done-line's old form,
   .section-head, .quiet-head, .workspace-heading, the check-in greens) are retired once every
   page is converted; tests/test_web_section_and_card.py holds the retirement. */

/* §3 The section: h3 + count + one lead sentence + the section's own controls at the right. A
   folded section draws the same head as its <summary>; a quiet one is the same head in muted ink. */
.sec { margin: 0 0 var(--s6); }
.sec-head, details.sec > summary { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--s1) var(--s3); margin: 0 0 var(--s3); }
.sec-head h3, details.sec > summary h3 { margin: 0; font-size: 18px; font-weight: 650; display: inline; }
.sec-head .count, details.sec > summary .count { font-size: var(--type-small); color: var(--muted); font-weight: 400; }
/* Full-width so the lead always wraps under the head; the measure is kept as right padding,
   because a max-width would let a short lead fit beside the controls instead. */
.sec-head .lead { flex-basis: 100%; margin: 0; color: var(--muted); padding-right: max(0px, calc(100% - var(--measure))); }
.sec-head .lead.inline { flex-basis: auto; padding-right: 0; }
.sec-head .controls { margin-left: auto; display: flex; flex-wrap: wrap; gap: var(--s2) var(--s4); align-items: center; }
.sec.quiet h3 { color: var(--muted); font-weight: 600; }
details.sec > summary { cursor: pointer; list-style-position: inside; }
details.sec > summary::marker { color: var(--muted); }
.sec h4 { font-size: 15px; margin: var(--s4) 0 var(--s2); }
/* The line under the child tabs is state, not instruction (§3): body type, ink. */
.tab-hint { margin: -12px 0 var(--s5); font-size: inherit; font-weight: 550; color: var(--ink); }
.tab-hint .muted { font-weight: 400; }

/* §4 The item: one box for one assignment. Emphasis is the left rule and a word, never a
   different shape: .ask needs an answer, .red the school says not in, .ok done, .grey nothing to do. */
.item { background: var(--paper); border: 1px solid var(--rule); border-left: 4px solid var(--rule); border-radius: var(--radius); padding: var(--s3) var(--s4); overflow-wrap: anywhere; }
.item + .item, .inset + .item { margin-top: var(--s2); }
.item.ask { border-left-color: var(--accent); }
.item.red { border-left-color: var(--warn); }
.item.ok { border-left-color: var(--ok); }
.item.grey { color: var(--muted); }
.item-head { display: flex; flex-wrap: wrap; gap: var(--s1) var(--s3); align-items: baseline; }
.item-head .name { font-weight: 650; }
.item-head .name a { color: inherit; text-decoration: none; }
.item-head .name a:hover { text-decoration: underline; }
.item-head .meta { font-size: var(--type-small); color: var(--muted); }
.item-head .when { margin-left: auto; font-size: var(--type-small); color: var(--muted); white-space: nowrap; }
.item-head .when.word { color: var(--warn); font-weight: 700; font-size: inherit; }
.item-head .close-detail { margin-left: var(--s3); }
.item .facts { margin: var(--s2) 0 0; }
.item .ask-line { margin: var(--s2) 0 0; font-weight: 600; }
.item .answers { margin-top: var(--s2); display: flex; flex-wrap: wrap; gap: var(--s2); align-items: center; }
.item .answers form { display: inline; margin: 0; }
/* Slot 4, the family's layer: one line each, with the family's rule. */
.ours { margin: var(--s2) 0 0; padding-left: 10px; border-left: 3px solid var(--accent); font-size: var(--type-small); }
/* Slot 5, the foot: the folds and links on one wrapping line, the stamp pushed right and tiny. */
.item-foot { margin: var(--s3) 0 0; display: flex; flex-wrap: wrap; gap: var(--s1) var(--s4); font-size: var(--type-small); align-items: baseline; }
.item-foot details { display: inline; }
.item-foot details[open] { display: block; flex-basis: 100%; }
.item-foot summary { display: inline; cursor: pointer; color: var(--accent); }
.item-foot summary::-webkit-details-marker { display: none; }
.item-foot summary::before { content: "▸ "; color: var(--muted); }
.item-foot details[open] > summary::before { content: "▾ "; }
.item-foot .stamp { margin-left: auto; color: var(--muted); font-size: var(--type-tiny); }

/* §5 One inset for anything quoted inside an item or a card: the record, a witness line, the
   class's pace, the "school evidence changed" notice. */
.inset { margin: var(--s2) 0 0; padding: var(--s2) var(--s3); background: var(--wash); border-radius: var(--radius); font-size: var(--type-small); }
.inset.warn { border-left: 3px solid var(--warn); color: var(--warn); }
.inset p { margin: var(--s1) 0; }
.inset a { color: var(--accent); }
/* The record: one block per source: the label, the facts, then the stamp on its own line under
   the facts, so a long stamp never wraps the label column four lines deep. */
.sources { display: grid; grid-template-columns: max-content 1fr; gap: var(--s1) var(--s3); }
.sources .src { color: var(--muted); font-weight: 600; font-size: var(--type-small); }
.sources .stamp { grid-column: 2; color: var(--muted); font-size: var(--type-tiny); margin: 0 0 var(--s1); }

/* §5 Lines: the compact density, the same box, one action per row at the right. */
.lines { background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 0 var(--s4); margin: 0; }
.lines .line { display: flex; gap: var(--s3); align-items: baseline; padding: var(--s2) 0; border-bottom: 1px solid var(--rule); }
.lines .line:last-child { border-bottom: none; }
.lines .line > a, .lines .line > form, .lines .line > button { margin-left: auto; font-size: var(--type-small); white-space: nowrap; }
.lines .glyph, .done-line .glyph { color: var(--muted); flex: none; }
.lines .line.ok .glyph, .done-line .glyph { color: var(--ok); }
/* The done-line after an answer: line density on its own. In a list it takes the card's place
   and wears the box; inside a Must-finish row it is a line in the row, no box. */
.done-line { display: flex; gap: var(--s3); align-items: baseline; background: var(--paper); border: 1px solid var(--rule); border-left: 4px solid var(--ok); border-radius: var(--radius); padding: var(--s2) var(--s4); margin-bottom: var(--s2); }
.done-line form { margin-left: auto; }
.item .done-line { border: 0; padding: var(--s2) 0; margin: 0; background: none; }

/* §4.2 A badge is one neutral style; the word carries the meaning. */
.badge, .badge.flag, .badge.plan { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: var(--type-small); background: var(--wash); border: 1px solid var(--rule); color: var(--ink); text-decoration: none; margin: 0; }
a.badge:hover { border-color: var(--accent); }

/* A table row that opens holds one item, no box inside a box. */
tr.detail td { padding: var(--s2) var(--s2) var(--s3); }

@media (max-width: 1023px) {
  .item-head .when { margin-left: 0; flex-basis: 100%; white-space: normal; }
  .sec-head .controls { margin-left: 0; flex-basis: 100%; }
}
@media (pointer: coarse) {
  .item-foot summary, .item-foot a, details.sec > summary, .lines .line > a, .lines .line > button, .lines .line > form button, .done-line form button { min-height: 44px; display: inline-flex; align-items: center; }
  .item-head .name a, .inset a { display: inline-block; padding-block: 8px; }
}
```

- [ ] **Step 5: Run the new tests and the CSS tests that already exist**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_page_layout.py tests/test_web_tier_css.py tests/test_web_tone_layout.py tests/test_web_a11y.py -q`
Expected: all pass. (`test_web_tier_css.py::test_secondary_text_on_a_childs_page_is_sized_by_a_token[.record]` still finds the old `.record` rule; `.badge` keeps its old rule too until Task 8.)

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/static/app.css tests/test_web_section_and_card.py
git commit -m "The section and item blocks land in the stylesheet beside the rules they will replace, with the radius and gap tokens (spec 2026-09-28 §3–§6)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Phrasing, the record's stamp layout, the record without the glossary

**Files:**
- Modify: `fridgesheet/web/phrasing.py` (lines 50–51 `facts.still_ungraded` / `facts.awaiting_grade`; lines 126–130 `copy.tab_*`; line 159 `copy.details`; add six keys)
- Modify: `fridgesheet/web/templates/_source_facts.html`
- Modify: `fridgesheet/web/templates/_record.html`
- Modify: `tests/test_phrasing.py:157` (`MUST_FINISH_KEYS`), `tests/test_web_words_nav.py:73-74`

**Interfaces:**
- Produces: phrase keys `copy.record`, `copy.history` (`{n}`), `copy.notes` (`{n}`), `copy.ours_step`, `copy.note_on` (`{when}`), `copy.not_counted_tonight`; `_record.html` rendering `<div class="inset">` from `item` and `tier`; `_source_facts.html` rendering `<span class="src">`, `<span>` facts, `<span class="stamp">` per source.
- Consumes: nothing new.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_phrasing.py` after `MUST_FINISH_KEYS`:

```python
CARD_KEYS = ("copy.record", "copy.history", "copy.notes", "copy.ours_step", "copy.note_on", "copy.not_counted_tonight")


def test_the_card_words_exist_in_every_tier_and_the_tab_hints_are_gone():
    for key in CARD_KEYS:
        assert key in phrasing.PHRASES, key
        assert set(phrasing.PHRASES[key]) == set(tiers.TIERS), key
    for key in ("copy.tab_checkin", "copy.tab_plan", "copy.tab_all", "copy.details"):
        assert key not in phrasing.PHRASES, key


def test_the_facts_sentences_do_not_restate_the_kind_or_the_due_date():
    """The head is the one place for them (spec 2026-09-28 §4.1)."""
    for key in ("facts.still_ungraded", "facts.awaiting_grade"):
        for tier in tiers.TIERS:
            words = phrasing.phrase(key, tier)
            assert "{kind}" not in words and "{due}" not in words, (key, tier, words)
```

In `tests/test_phrasing.py:157` remove `"copy.details", ` from `MUST_FINISH_KEYS`.

In `tests/test_web_words_nav.py` replace the last test (lines 73–74) with:

```python
def test_a_verdict_sentence_that_starts_with_a_value_is_capitalised():
    assert verdicts.say("facts.awaiting_grade", "", {"kind": "paper", "due": "Thu 9/10"}).startswith("No grade yet")
```

Add to `tests/test_web_section_and_card.py`:

```python
# --- §4.1 the Record ----------------------------------------------------------------------------

def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_the_record_puts_each_sources_stamp_under_its_facts_and_carries_no_glossary(tmp_path):
    qid = _id(tmp_path, "Quiz 1")
    body = app_for(tmp_path).get(f"/items/{qid}").text
    inset = re.search(r'<div class="inset">(.*?)</div>\s*</div>', body, re.S).group(1)
    assert re.search(r'<span class="src">Canvas</span><span>[^<]+</span><span class="stamp">checked [^<]+</span>', inset)
    assert re.search(r'<span class="src">HAC</span><span>[^<]+</span><span class="stamp">checked [^<]+</span>', inset)
    assert "Home Access Center" not in inset
    assert "Open in Canvas (opens a new tab)" in inset
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_phrasing.py tests/test_web_words_nav.py tests/test_web_section_and_card.py -q`
Expected: the three new tests fail; the rest pass.

- [ ] **Step 3: Change the phrases**

In `fridgesheet/web/phrasing.py`:

Replace lines 50–51 with:

```python
    "facts.still_ungraded":  {"early": "There's still no grade.", "middle": "Still no grade anywhere.", "older": "Still no grade anywhere, longer than grading usually takes."},
    "facts.awaiting_grade":  {"early": "No grade yet.", "middle": "No grade yet.", "older": "No grade yet; grading paper takes time."},
```

Delete the `copy.tab_checkin`, `copy.tab_plan` and `copy.tab_all` entries (lines 126–130) and the `copy.details` entry (line 159). Where `copy.details` was, add:

```python
    "copy.record":          {"early": "Record", "middle": "Record", "older": "Record"},
    "copy.history":         {"early": "History ({n})", "middle": "History ({n})", "older": "History ({n})"},
    "copy.notes":           {"early": "Notes ({n})", "middle": "Notes ({n})", "older": "Notes ({n})"},
    "copy.ours_step":       {"early": "Our step", "middle": "Our step", "older": "Our step"},
    "copy.note_on":         {"early": "Note, {when}", "middle": "Note, {when}", "older": "Note, {when}"},
    "copy.not_counted_tonight": {"early": "not counted tonight", "middle": "not counted tonight", "older": "not counted tonight"},
```

`verdicts.py` still passes `kind` and `due` in the facts dict; `str.format(**values)` ignores keys the template does not use, so nothing else changes.

- [ ] **Step 4: Rewrite `_source_facts.html`**

```jinja
{# What each gradebook holds about one item: one block per source, the label, the facts, and on
   the next line the stamp (checked when, changed when) in the reader's words (`record.*`). The
   Record fold (`_record.html`) is the one place this renders now (spec 2026-09-28 §4.1). Wants
   `item` (an ItemView) and reads `tier` when the page set one. #}
{% set t = tier | default('') %}
{% macro of(obs, points) %}{{ obs.score | num }}{% if points %} of {{ points | num }}{% endif %}{% endmacro %}
{% macro stamp(checked, as_of) %}{% if checked %}checked {{ checked | wd_md_time }}{% if as_of %} · changed {{ as_of | wd_md_time }}{% endif %}{% elif as_of %}as of {{ as_of | wd_md_time }}{% endif %}{% endmacro %}
<div class="sources">
  {% if item.canvas %}{% set c = item.canvas %}<span class="src">Canvas</span><span>{% if c.missing %}{{ 'record.missing' | words(t) }}{% if c.submitted_at %} · {% endif %}{% endif %}{% if c.submitted_at %}{{ ('record.handed_in_late' if c.late else 'record.handed_in') | words(t, {'when': c.submitted_at | wd_md_time}) }}{% elif not c.missing %}{{ ('record.offline' if item.kind in ('paper', 'in class') else 'record.nothing') | words(t) }}{% endif %} · {% if c.score is not none %}{{ of(c, item.points) }}{% elif c.grade %}{{ 'record.grade' | words(t, {'grade': c.grade}) }}{% else %}{{ 'record.no_grade' | words(t) }}{% endif %}</span><span class="stamp">{{ stamp(item.canvas_checked, item.canvas_as_of) }}</span>{% endif %}
  {% if item.hac %}<span class="src">HAC</span><span>{% if item.hac.score is not none %}{{ of(item.hac, item.points) }}{% else %}{{ 'record.no_grade' | words(t) }}{% endif %}</span><span class="stamp">{{ stamp(item.hac_checked, item.hac_as_of) }}</span>{% endif %}
</div>
```

- [ ] **Step 5: Rewrite `_record.html`**

```jinja
{# The Record: what each gradebook holds (`_source_facts.html`), the app's pace sentence when it
   has one, the zero note, and the teacher. The glossary sentence is not here: it is said once
   per page, under the Assignments table and at the foot of the check-in's queue (spec
   2026-09-28 §2). Wants `item`; reads `tier` when the page set one. #}
<div class="inset">
  {% include "_source_facts.html" %}
  {% set pk = item.verdict | pace_key %}{% if pk %}<p class="app-count">{{ pk | say(tier | default(''), item.verdict.pace) }}</p>{% endif %}
  {% if item.grade_zero %}<p>{{ 'copy.zero_note' | say(tier | default('')) }}</p>{% endif %}
  {% if item.teacher or item.teacher_email or item.canvas_path %}<p>{% if item.teacher or item.teacher_email %}Teacher: {{ item.teacher or 'the teacher' }}{% endif %}{% if item.teacher_email %} · <a href="mailto:{{ item.teacher_email }}?subject={{ ('About ' ~ item.name) | urlencode }}&amp;body={{ item | mailto_body | urlencode }}">Email with these facts</a>{% endif %}{% if item.canvas_path %}{% if item.teacher or item.teacher_email %} · {% endif %}<a href="{{ settings.canvas_base }}{{ item.canvas_path }}" target="_blank" rel="noopener">Open in Canvas (opens a new tab)</a>{% endif %}</p>{% endif %}
</div>
```

`_question.html` still wraps this in its "See the record" fold and adds the pace sentence itself; until Task 3 the pace sentence therefore renders twice on a question card. That is expected for one commit; Task 3 removes the duplicate.

- [ ] **Step 6: Run the tests**

Run: `env -u PYTHONPATH $PYTEST tests/test_phrasing.py tests/test_web_words_nav.py tests/test_web_section_and_card.py tests/test_web_checkin_verdicts.py tests/test_web_tier_wording.py -q`
Expected: the three new tests pass. Two existing ones now fail and stay red until Task 3 and Task 4: `test_web_words_nav.py::test_the_third_tab_is_assignments_and_every_tab_says_what_it_is_for` (the tab hints, Task 4) and `test_web_checkin_verdicts.py::test_canvas_and_hac_are_explained` (the glossary in the record, Task 3). `tests/test_web_tier_wording.py` passes (the glossary is still under the Assignments tabs).

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/phrasing.py fridgesheet/web/templates/_source_facts.html fridgesheet/web/templates/_record.html tests/test_phrasing.py tests/test_web_words_nav.py tests/test_web_section_and_card.py
git commit -m "The facts sentence stops restating kind and due date, the record puts each source's stamp under its facts and drops the glossary, and the card's fold words exist in three tiers (spec 2026-09-28 §4.1, §8)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: `_item.html`, the one partial, at card and detail density

**Files:**
- Create: `fridgesheet/web/templates/_item.html`
- Modify: `fridgesheet/web/templates/_question.html` (becomes a wrapper), `_item_detail.html` (becomes a wrapper), `_flag_menu.html:1` (`closest .card` → `closest .item`)
- Modify: `docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md` §4.1 slot 1 (the head's word rule)
- Modify tests: `tests/test_web_ui_flow.py:48,58,68`, `tests/test_reconcile_traps.py:67,77-78`, `tests/test_web_questions.py:82`, `tests/test_web_pages.py:281`, `tests/test_web_checkin_verdicts.py:95-101`, `tests/test_kids_ux_small_items.py:50-52`

**Interfaces:**
- Produces: `_item.html`, included with these context variables set by the includer (all optional except `item`):
  - `item` — an `ItemView`; `student` in scope (the page's kid)
  - `density` — `'card'` (default) or `'detail'` (`'line'` is Task 4)
  - `slot` — the id the answers swap (default `'q-<id>'`); `box_id` — the element's own id (default `slot`; `''` for none). When they differ the answers are wrapped in `<div id="{{ slot }}">`
  - `tone` — `'ask'|'red'|'ok'|'grey'|''` (default: `ask` for a question, `grey` for waiting)
  - `word` — the head's right-hand text, when the includer knows better; `badges` — a list of badge strings for the head's meta
  - `says` — the facts sentence override; `late_line` — `true` to append the late-credit sentence
  - `stamp` — foot provenance text; `linked` — the name links to the row on Assignments; `plan_state` — appended as `&state=` to the Plan-a-step link; `earlier` — completed steps on this item (a list)
  - `exclude`, `first` — passed through to `_answers.html`
  - detail only: `card`, `item_history`, `notes`, `message`
  - question only: `reopened`, `undone`
- Consumes: `_record.html` (Task 2), the CSS (Task 1), `copy.*` keys (Task 2).

- [ ] **Step 1: Update the existing tests to the new markup**

`tests/test_web_ui_flow.py`:
- line 48: `assert re.match(rf'\s*<div class="item[^"]*" id="q-{pid}" data-focus>', detail)`
- line 58: `assert f'<div class="item ask" id="q-{pid}"' in r.text and "Was it handed in?" in r.text and "Notes (0)" in r.text`
- line 68: `assert re.match(r'\s*<div class="item[^"]*" data-focus>', detail)`

`tests/test_reconcile_traps.py`:
- line 67, add after it: `    visible = re.sub(r"<details><summary>More</summary>.*?</details>", "", visible, flags=re.S)   # the flag menu quotes the note as the input's context`
- lines 77–78: `assert re.search(r'<b[^>]*tabindex="-1"[^>]*data-focus-target', body) or re.search(r'<b[^>]*data-focus-target[^>]*tabindex="-1"', body)`

`tests/test_web_questions.py` line 82: `assert "<summary>Record</summary>" in body and "Notes (0)" in body`

`tests/test_web_pages.py` line 281: `assert 'class="inset"' in body                         # the evidence`

`tests/test_web_checkin_verdicts.py` lines 95–101:

```python
def test_canvas_and_hac_are_explained_once_per_page_and_not_in_the_record(tmp_path):
    qid = _id(tmp_path, "Quiz 1")
    c = app_for(tmp_path)
    line = "HAC (Home Access Center) is the official gradebook"
    assert c.get("/kids/Alex").text.count(line) == 1 and c.get("/kids/Alex/check-in").text.count(line) == 1
    record = c.get(f"/items/{qid}").text
    assert line not in record and "Open in Canvas (opens a new tab)" in record
```

`tests/test_kids_ux_small_items.py` lines 50–52:

```python
    card = kid[kid.index('id="q-%d"' % pid):kid.index('id="items"')]
    assert "allows 7 days" in card
    assert card.index("<summary>Record</summary>") < card.index("allows 7 days")
```

Add to `tests/test_web_section_and_card.py`:

```python
# --- §4 the five slots, at card and detail density ------------------------------------------------

def test_a_question_card_has_head_says_ask_answers_and_foot_in_that_order(tmp_path):
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get("/kids/Alex").text
    card = body[body.index('<div class="item ask" id="q-%d"' % pid):body.index('id="items"')]
    order = [card.index(s) for s in ('class="item-head"', 'class="facts"', 'class="ask-line"', 'class="answers"', 'class="item-foot"')]
    assert order == sorted(order)
    assert 'class="ours"' not in card                                          # no step, no note, no answer yet
    head = re.search(r'<div class="item-head">(.*?)</div>', card, re.S).group(1)
    assert re.search(r'<span class="name"><b tabindex="-1" data-focus-target>Participation</b></span>', head)
    assert re.search(r'<span class="meta">Honors English 9</span>', head)
    assert re.search(r'<span class="when">due \w{3} 9/8[^<]*</span>', head)      # a question: the date, not the standing
    facts = re.search(r'<p class="facts">(.*?)</p>', card).group(1)
    assert "due" not in facts and "9/8" not in facts                              # said once, in the head
    foot = re.search(r'<div class="item-foot">(.*?)</div>\s*</div>', card, re.S).group(1)
    assert foot.index("<summary>Record</summary>") < foot.index("Notes (0)") < foot.index("Plan a step")
    assert "<summary>More</summary>" not in foot                                 # detail density only


def test_the_detail_is_the_same_card_with_close_and_the_record_open_and_nothing_twice(tmp_path):
    pid = _id(tmp_path, "Participation")
    body = app_for(tmp_path).get(f"/items/{pid}").text
    assert body.count("Participation</b>") == 1 and body.count("<h2") == 0
    head = re.search(r'<div class="item-head">(.*?)</div>', body, re.S).group(1)
    assert head.index("data-focus-target") < head.index("data-close-detail")
    assert body.index('class="answers"') < body.index('<div class="inset">') < body.index('class="item-foot"')
    assert body.count("<summary>Record</summary>") == 0                          # open in place, not folded
    foot = re.search(r'<div class="item-foot">(.*?)</div>\s*</div>', body, re.S).group(1)
    assert foot.index("Notes (0)") < foot.index("Plan a step") < foot.index("<summary>More</summary>")
    assert 'id="qd-%d"' % pid in body                                            # the detail's answers keep their own slot


def test_a_note_and_a_step_show_in_the_family_slot_and_count_in_the_foot(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import notes
    pid = _id(tmp_path, "Participation")
    conn = db.open_db(tmp_path)
    notes.add(conn, "item", pid, "Doug says he played it Friday", now="2026-09-14T19:00:00-04:00")
    conn.close()
    c = app_for(tmp_path)
    r = c.post(f"/items/{pid}/answer", data={"answer": "plan:today", "prev": "", "slot": f"q-{pid}"})
    assert r.status_code == 200
    body = c.get("/questions").text                       # the item is planned, so it left the question list;
    detail = c.get(f"/items/{pid}").text                  # the detail shows the family's layer
    ours = re.findall(r'<p class="ours">(.*?)</p>', detail)
    assert any(o.startswith("Our step: Work on it · Alex") for o in ours)
    assert any(o.startswith("Note, ") and "played it Friday" in o for o in ours)
    assert "Notes (1)" in detail and "Plan another step" in detail
    assert "played it Friday" not in body or 'class="ours"' in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_ui_flow.py tests/test_reconcile_traps.py tests/test_web_questions.py tests/test_web_pages.py tests/test_web_checkin_verdicts.py tests/test_kids_ux_small_items.py -q`
Expected: the three new tests and the updated ones fail (`class="item` not found).

- [ ] **Step 3: Create `_item.html`**

```jinja
{# One assignment, one surface, five slots (spec 2026-09-28 §4). The includer sets `item` and any of:
   density   'card' (default), 'detail', or 'line'
   slot      the id the answers swap ('q-<id>' by default; 'qd-<id>' in a detail; 'qc-<id>' on the check-in)
   box_id    the element's own id ('' for none). Must finish gives the row 'mf-<id>' and keeps the
             answers in a div with the slot id, so an answer swaps the answers, not the row.
   tone      'ask' | 'red' | 'ok' | 'grey' | ''      word     the head's right-hand words (the sheet's word)
   badges    a list for the head's meta               says     the facts sentence, when the includer knows better
   late_line true: append the late-credit sentence    stamp    provenance for the foot's right
   linked    the name links to the row on Assignments plan_state  appended to the Plan-a-step link
   earlier   completed steps on this item             exclude, first   for _answers.html
   detail: card, item_history, notes, message         question: reopened, undone #}
{% set tier = (student.key | tier_of) if student is defined and student else "" %}
{% set vd = item.verdict %}
{% set density = density if density is defined and density else 'card' %}
{% set qid = slot if slot is defined and slot else 'q-' ~ item.id %}
{% set box = box_id if box_id is defined else qid %}
{% set asked_again = reopened is defined and reopened %}
{% set is_q = vd.state == 'question' or (asked_again and ('ask.' ~ vd.kind) | has_phrase) %}
{% set tone = tone if tone is defined and tone else ('ask' if is_q else 'grey' if vd.state == 'waiting' else '') %}
{% set has_word = word is defined and word %}
{% set at = (item | due_at(tier)) if item.due else '' %}
{% set due_text = ('due ' ~ (item.due | wd_md) ~ (' ' ~ at if at else '')) if item.due else '' %}
{# The one word about time: the includer's word; else the date while the item is a question or
   still upcoming; else the standing phrase, with the date moved into the meta. #}
{% set date_at_right = (not has_word) and due_text and (is_q or (item.upcoming and not item.overdue)) %}
{% set when_text = word if has_word else (due_text if date_at_right else (item | standing(tier))) %}
{% set is_detail = density == 'detail' %}
{% if density == 'line' %}
<div class="line{{ ' ' ~ tone if tone }}"{% if box %} id="{{ box }}"{% endif %}><span class="glyph" aria-hidden="true">{{ '✓' if tone == 'ok' else '◷' }}</span><span><b>{{ item.name }}</b> <span class="muted">{% if says is defined and says %}{{ says }}{% elif ('facts.' ~ vd.kind) | has_phrase %}{{ ('facts.' ~ vd.kind) | say(tier, vd.facts) }}{% else %}{{ item | standing(tier) }}{% endif %}{% if vd.asks_on %} Asks you on {{ vd.asks_on | wd_md }}.{% endif %}</span>{% if vd.kind == 'asked' and item.teacher_email %} <a href="mailto:{{ item.teacher_email }}?subject={{ ('About ' ~ item.name) | urlencode }}&amp;body={{ item | mailto_body | urlencode }}">Email</a>{% endif %}</span>{{ line_action if line_action is defined else '' }}</div>
{% else %}
<div class="item{{ ' ' ~ tone if tone }}"{% if box %} id="{{ box }}"{% endif %} data-focus{% if undone is defined and undone %} data-announce="{{ item.name }}: answer undone, the question is back"{% elif asked_again %} data-announce="{{ item.name }}: say what's right below"{% endif %}>
  <div class="item-head"><span class="name">{% if linked is defined and linked %}<a href="/kids/{{ student.key | urlencode }}?show=all#row-{{ item.id }}" data-focus-target>{{ item.name }}</a>{% else %}<b tabindex="-1" data-focus-target>{{ item.name }}</b>{% endif %}</span><span class="meta">{{ item.course_short }}{% if item.kind in ('paper', 'in class') %} · {{ item.kind }}{% endif %}{% if item.points %} · {{ item.points | round(1) | string | replace('.0', '') }} pts{% endif %}{% if due_text and not date_at_right %} · {{ due_text }}{% endif %}{% if badges is defined %}{% for b in badges %} <span class="badge">{{ b }}</span>{% endfor %}{% endif %}</span><span class="when{{ ' word' if has_word }}">{{ when_text }}</span>{% if is_detail %}<button type="button" class="link close-detail" data-close-detail{% if card is defined and card %} hx-get="/items/{{ item.id }}/question?slot={{ card }}" hx-target="#{{ card }}" hx-swap="outerHTML"{% endif %} aria-label="Close {{ item.name }}">Close</button>{% endif %}</div>
  {% if message is defined and message %}<p data-announce="{{ message }}"><strong>{{ message }}</strong></p>{% endif %}
  {% set late = (late_line is defined and late_line and item.open_in and item.due and item.late_until) %}
  {% if says is defined and says %}<p class="facts">{{ says }}{% if late %} {{ 'copy.late_until' | say(tier, {'when': item.late_until | wd_md}) }}{% endif %}</p>
  {% elif ('facts.' ~ vd.kind) | has_phrase %}<p class="facts">{{ ('facts.' ~ vd.kind) | say(tier, vd.facts) }}{% if late %} {{ 'copy.late_until' | say(tier, {'when': item.late_until | wd_md}) }}{% endif %}</p>
  {% elif not has_word %}<p class="facts">{{ item | standing(tier) }}{% if late %} {{ 'copy.late_until' | say(tier, {'when': item.late_until | wd_md}) }}{% endif %}</p>
  {% elif late %}<p class="facts">{{ 'copy.late_until' | say(tier, {'when': item.late_until | wd_md}) }}</p>{% endif %}
  {% if is_q %}<p class="ask-line">{{ ('ask.' ~ vd.kind) | say(tier) }}</p>{% endif %}
  {% if vd.answers %}{% if box != qid %}<div id="{{ qid }}">{% endif %}{% include "_answers.html" %}{% if box != qid %}</div>{% endif %}{% endif %}
  {% if item.step %}<p class="ours">{{ 'copy.ours_step' | say(tier) }}: {{ item.step.next_step }} · {{ item.step.owner }} · {{ item.step.planned_for | wd_md }} <a href="/kids/{{ student.key | urlencode }}/check-in/step?step_id={{ item.step.id }}&amp;return_to={{ here | urlencode }}">Edit</a></p>{% endif %}
  {% if earlier is defined and earlier %}<p class="ours">{{ earlier | length }} completed step{{ 's' if earlier | length != 1 }} on this already{% if earlier[-1].family_account %} · last account: {{ earlier[-1].family_account }}{% endif %}</p>{% endif %}
  {% if item.flag and item.flag_text %}<p class="ours">{{ item.flag_text }}</p>{% endif %}
  {% if item.latest_note %}<p class="ours">{{ 'copy.note_on' | say(tier, {'when': item.latest_note.at | wd_md}) }}: {{ item.latest_note.body }}</p>{% endif %}
  {% if is_detail %}{% include "_record.html" %}{% endif %}
  <div class="item-foot">{% if not is_detail %}<details><summary>{{ 'copy.record' | say(tier) }}</summary>{% include "_record.html" %}</details>{% endif %}
    {% if is_detail %}{% if item_history is defined and item_history %}<details class="history"><summary>{{ 'copy.history' | say(tier, {'n': item_history | length}) }}</summary><ul>{% for e in item_history %}<li><span class="muted">{{ e.at | wd_md_time }}</span> · {{ e.label }}{% if e.source %} <span class="muted">({{ 'HAC' if e.source == 'hac' else 'Canvas' }})</span>{% endif %}{% if e.detail %}: {{ e.detail }}{% endif %}</li>{% endfor %}</ul></details>{% endif %}
    <details class="notes-fold"{{ ' open' if notes is defined and notes }}><summary>{{ 'copy.notes' | say(tier, {'n': (notes | length) if notes is defined else item.notes}) }}</summary>{% set target_type = "item" %}{% set target_id = item.id %}{% include "_notes.html" %}</details>
    {% elif box == qid %}<a href="#detail-{{ item.id }}" hx-get="/items/{{ item.id }}?card={{ box }}" hx-target="#{{ box }}" hx-swap="outerHTML">{{ 'copy.notes' | say(tier, {'n': item.notes}) }}</a>{% endif %}
    <a href="/kids/{{ student.key | urlencode }}/check-in/step?item_id={{ item.id }}{% if plan_state is defined and plan_state %}&amp;state={{ plan_state }}{% endif %}&amp;return_to={{ here | urlencode }}">{{ 'Plan another step' if item.step else 'Plan a step' }}</a>
    {% if is_detail %}<details><summary>More</summary>{% include "_flag_menu.html" %}</details>{% endif %}
    {% if stamp is defined and stamp %}<span class="stamp">{{ stamp }}</span>{% endif %}</div>
</div>
{% endif %}
```

- [ ] **Step 4: Make `_question.html` and `_item_detail.html` wrappers**

`_question.html`, whole file:

```jinja
{# One question (or decided/waiting) card: the item surface at card density (spec 2026-09-28 §4.2).
   `slot` names the element the answer buttons swap: "q-<id>" in a page's question list, "qd-<id>"
   inside the item detail, "qc-<id>" on the check-in. Routes render this after Not right?
   (`reopened`) and Undo (`undone`). #}
{% set density = 'card' %}
{% include "_item.html" %}
{% if undone is defined and undone %}{% include "_after_answer.html" %}{% endif %}
```

`_item_detail.html`, whole file:

```jinja
{# The item opened: the surface at detail density (spec 2026-09-28 §4.2). Opened from a question
   card (`card`, #126), the detail takes that card's id and Close fetches the card back into it; in a
   table row it has no id and app.js closes it by hiding the row. The detail's answers swap
   `qd-<id>`, their own slot, so a list's card with the same item is never reached for. #}
{% set card = card if card is defined and card else '' %}
{% set density = 'detail' %}{% set slot = 'qd-' ~ item.id %}{% set box_id = card %}
{% include "_item.html" %}
{# After a flag change, the row above the card and the question counts follow it (#3, as #72
   did for answers); htmx lifts these out-of-band pieces off before swapping the card in. #}
{% if refresh_row is defined and refresh_row %}{% include "_after_answer.html" %}{% endif %}
```

`_flag_menu.html` line 1: change `hx-target="closest .card"` to `hx-target="closest .item"`.

- [ ] **Step 5: Amend the spec's §4.1 slot 1**

In `docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md`, replace the sentence beginning "At the right, `.when`: **the one word about time**, which is the item's `standing` phrase" through "muted otherwise ("Waiting for a grade", "Following up since 9/23")." with:

```
At the right, `.when`: **the one word about time**. The includer's word when it has one
   (Must finish passes the sheet's word, `.word` in `--warn` at weight 700: DUE TONIGHT, DUE
   TOMORROW, MISSING, ZERO); else the due date, muted ("due Sun 9/20 11:59pm"), while the item
   is a question or still upcoming; else the item's `standing` phrase, the same words the
   table's "Where it stands" column shows ("Waiting for a grade", "Following up since 9/23"),
   with the due date moved into `.meta`. So the date is said once, and a card whose word is
   its standing agrees with its row by construction.
```

- [ ] **Step 6: Run the tests**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_ui_flow.py tests/test_reconcile_traps.py tests/test_web_questions.py tests/test_web_pages.py tests/test_web_checkin_verdicts.py tests/test_kids_ux_small_items.py tests/test_web_evidence_notes.py tests/test_web_a11y.py tests/test_web_tier_parity.py tests/test_web_answer_trail.py -q`
Expected: all pass except `test_web_checkin_verdicts.py::test_canvas_and_hac_are_explained_once_per_page_and_not_in_the_record` (the check-in still says the glossary once, the Assignments page still says it under the tabs *and* nowhere else now, so this passes) — check: if `test_kids_ux_small_items.py::test_the_apps_own_pace_reasoning_folds_away` fails on the check-in row (its second half looks for `mf-row`), leave it red: Task 6 owns it.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/web/templates/_item.html fridgesheet/web/templates/_question.html fridgesheet/web/templates/_item_detail.html fridgesheet/web/templates/_flag_menu.html docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md tests
git commit -m "One partial draws an assignment at card and detail density: head, says, ask, ours, foot; a row's detail is the card with Close and the record open, nothing drawn twice (spec 2026-09-28 §4)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The Assignments tab: sections, lines, the state line, filters in the table's head

**Files:**
- Modify: `fridgesheet/web/templates/_verdict_sections.html` (whole file), `kid.html` (whole file), `_child_nav.html` (whole file), `_answered.html:4-9`, `_sources_hint.html`
- Modify tests: `tests/test_web_page_layout.py:277-292`, `tests/test_web_words_nav.py:21-30`, `tests/test_web_who.py:144`, `tests/test_web_tier_wording.py:138-139`, `tests/test_web_tone_layout.py:79`

**Interfaces:**
- Consumes: `_item.html` at `line` and `card` density (Task 3); `copy.done_so_far`, `copy.checkin_first` (existing).
- Produces: the section markup every later page copies: `<section class="sec"><div class="sec-head"><h3>…</h3><span class="count">n</span>…</div>…</section>` and `<details class="sec quiet"><summary><h3>…</h3> <span class="count">n</span></summary>…</details>`; the state line `<p class="tab-hint">` drawn by `_child_nav.html` from `done_so_far` (Assignments) or `last_check`/`today` (Check-in, Plan); the legend `<p class="legend sources-hint">` under the table.

- [ ] **Step 1: Update the existing tests and add new ones**

`tests/test_web_page_layout.py` lines 277–292, replace the whole test with:

```python
def test_the_line_under_the_tabs_is_state_and_the_glossary_is_said_once_under_the_table(tmp_path):
    """#190 put one instruction sentence under the tabs; spec 2026-09-28 §3 replaces it with one
    line of state (Done so far; the last check-in) and says what Canvas and HAC are once, as the
    table's legend, never above the first section and never inside a record."""
    from fridgesheet.web import phrasing
    for key in ("copy.checkin_intro", "copy.tab_checkin", "copy.tab_plan", "copy.tab_all"):
        assert key not in phrasing.PHRASES, key
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for path in ("/kids/Alex/check-in", "/kids/Alex/plan"):
        body = c.get(path).text
        above = body.split('class="child-nav"')[1].split("<section", 1)[0]
        assert "sources-hint" not in above, path
        assert re.search(r'<p class="tab-hint">', above), path
    assignments = c.get("/kids/Alex").text
    assert assignments.count("official gradebook") == 1
    assert assignments.index('id="items"') < assignments.index('class="legend sources-hint"')
    assert re.search(r'<p class="tab-hint">Done so far: 2 of 5 due · 1 on time\.</p>', assignments)
```

`tests/test_web_words_nav.py` lines 21–30, replace the test with:

```python
def test_the_third_tab_is_assignments_and_the_line_under_the_tabs_is_state(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    pages = {"/kids/Alex/check-in": "Start with what", "/kids/Alex/plan": "Start with what",
             "/kids/Alex": "Done so far"}
    for path, state in pages.items():
        body = c.get(path).text
        nav = re.search(r'<nav class="child-nav".*?</nav>', body, re.S).group(0)
        assert ">Assignments<" in nav and ">All work<" not in nav, path
        assert re.search(r'<p class="tab-hint">[^<]*' + re.escape(state), body), path
```

`tests/test_web_who.py` line 144: `assert re.search(r'<p class="tab-hint">[^<]*Start with what', body)   # the state line stays without the tabs`

`tests/test_web_tier_wording.py` line 139: `return re.search(r'<p class="tab-hint">(.*?)</p>', body, re.S).group(1)`

`tests/test_web_tone_layout.py` line 79: `assert re.search(r"\.sec-head, details\.sec > summary\s*\{[^}]*flex-wrap:\s*wrap", CSS)`

Add to `tests/test_web_section_and_card.py`:

```python
# --- §3 the Assignments tab as sections -------------------------------------------------------------

def test_the_assignments_tab_is_four_sections_with_the_filters_in_the_tables_head(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    content = body.split('class="child-nav"', 1)[1]
    heads = re.findall(r'<(?:section|details) class="sec[^"]*"[^>]*>\s*(?:<div class="sec-head">|<summary>)<h3[^>]*>([^<]*)</h3>', content)
    assert heads == ["1 question about Alex's work", "Settled by the records", "Waiting, nothing to do yet", "All assignments"]
    assert re.search(r'<details class="sec quiet">\s*<summary><h3>Waiting, nothing to do yet</h3> <span class="count">2</span></summary>', content)
    table_head = re.search(r'<h3>All assignments</h3>(.*?)</div>\s*<div class="table-wrap">', content, re.S).group(1)
    assert 'class="filters controls"' in table_head and 'name="course"' in table_head and "More filters" in table_head
    assert re.search(r'<div class="lines">\s*<div class="line ok" id="q-\d+"><span class="glyph"', content)   # Settled, line density


def test_kid_mode_draws_the_state_line_without_the_tabs(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.cookies.set("fridgesheet_who", "Alex")
    body = c.get("/kids/Alex").text
    assert 'class="child-nav"' not in body
    assert re.search(r'<p class="tab-hint">Done so far', body)


def test_an_answer_collapses_a_card_to_the_line_density(tmp_path):
    pid = _id(tmp_path, "Participation")
    r = app_for(tmp_path).post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": f"q-{pid}"})
    assert re.match(rf'\s*<div class="line ok done-line" id="q-{pid}" data-focus', r.text)
    assert "Undo" in r.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_page_layout.py tests/test_web_words_nav.py tests/test_web_who.py tests/test_web_tier_wording.py tests/test_web_tone_layout.py -q`
Expected: the new and updated tests fail.

- [ ] **Step 3: Rewrite `_child_nav.html`**

```jinja
{% if not who_student %}
<nav class="child-nav" aria-label="Child workspace">
  <a href="/kids/{{ student.key | urlencode }}/check-in" {{ 'aria-current="page"' | safe if workspace == 'checkin' }}>Check-in</a>
  <a href="/kids/{{ student.key | urlencode }}/plan" {{ 'aria-current="page"' | safe if workspace == 'plan' }}>Plan</a>
  <a href="/kids/{{ student.key | urlencode }}" {{ 'aria-current="page"' | safe if workspace == 'all' }}>Assignments</a>
</nav>
{% endif %}
{# The one line under the tabs is state, not instruction (spec 2026-09-28 §3): what has been done
   on Assignments (kids' UX audit F8; only once something has), the last check-in and what was
   agreed on Check-in and Plan. The section heads do the old tab hint's job (F3, superseded). #}
{% set tier = student.key | tier_of %}
{% if workspace == 'all' %}
{% if done_so_far.done %}<p class="tab-hint">{{ 'copy.done_so_far' | say(tier, done_so_far) }}</p>{% endif %}
{% elif last_check %}
<p class="tab-hint">Last check-in {{ last_check.finished_at | wd_md_time }}{% if last_check.recorded_by %} (recorded by {{ last_check.recorded_by }}){% endif %} · Next check-in {{ last_check.next_check | wd_md }}{% if last_check.next_check <= today %} · <strong class="warn">time to check in</strong>{% endif %} · <span class="muted">What we agreed: {{ last_check.summary }}</span></p>
{% else %}
<p class="tab-hint">{{ 'copy.checkin_first' | say(tier) }}</p>
{% endif %}
```

- [ ] **Step 4: Rewrite `_verdict_sections.html`**

```jinja
{# The sections above a kid's work list (spec 2026-09-23 §6.1; drawn as spec 2026-09-28 §3 sections).
   Computed over all of the kid's work, whatever the table below is filtered to. #}
{% set tier = student.key | tier_of %}
{% if questions %}
<section class="sec questions" aria-labelledby="q-head">
  <div class="sec-head"><h3 id="q-head">{{ 'copy.questions_head' | say(tier, {'n': questions | length, 's': 's' if questions | length != 1 else ''}) }}</h3><span class="lead inline">{{ 'copy.answering_hint' | say(tier) }}</span></div>
  {% for item in questions %}{% include "_question.html" %}{% endfor %}
</section>
{% else %}
<div class="sec-head quiet"><h3 id="q-head" class="muted">{{ 'copy.no_questions' | say(tier) }}</h3></div>
{% endif %}
{% if decided or decided_earlier %}
<section class="sec quiet decided" aria-labelledby="d-head">
  <div class="sec-head"><h3 id="d-head">Settled by the records</h3></div>
  {# Not right? asks the family, with the item's own answers; it writes nothing and undoes nothing (#123). #}
  {% if decided %}<div class="lines">{% for item in decided %}{% set density = 'line' %}{% set tone = 'ok' %}{% set line_action %}<button type="button" class="link" hx-get="/items/{{ item.id }}/reopen" hx-target="#q-{{ item.id }}" hx-swap="outerHTML" aria-label="Not right? {{ item.name }}">Not right?</button>{% endset %}{% include "_item.html" %}{% endfor %}</div>{% endif %}
  {# Older settled items fold away so the list never pushes the work off the first screen (#76). #}
  {% if decided_earlier %}<details class="quiet"><summary>Earlier ({{ decided_earlier | length }})</summary>
    <div class="lines">{% for item in decided_earlier %}{% set density = 'line' %}{% set tone = 'ok' %}{% set line_action %}<button type="button" class="link" hx-get="/items/{{ item.id }}/reopen" hx-target="#q-{{ item.id }}" hx-swap="outerHTML" aria-label="Not right? {{ item.name }}">Not right?</button>{% endset %}{% include "_item.html" %}{% endfor %}</div></details>{% endif %}
</section>
{% endif %}
{% if waiting %}
<details class="sec quiet">
  <summary><h3>Waiting, nothing to do yet</h3> <span class="count">{{ waiting | length }}</span></summary>
  <div class="lines">{% for item in waiting %}{% set density = 'line' %}{% set tone = 'grey' %}{% set says = (('facts.' ~ item.verdict.kind) | say(tier, item.verdict.facts)) if item.verdict.state == 'waiting' else (item | standing(tier)) %}{% set line_action %}{% if item.verdict.answers %}<form hx-post="/items/{{ item.id }}/answer" hx-target="#q-{{ item.id }}" hx-swap="outerHTML"><input type="hidden" name="prev" value=""><button class="link" name="answer" value="ask_teacher" aria-label="Ask the teacher now about {{ item.name }}">Ask now</button></form>{% endif %}{% endset %}{% include "_item.html" %}{% endfor %}</div>
</details>
{% endif %}
```

The `{% set line_action %}…{% endset %}` block captures markup; `_item.html`'s line branch prints it after the text. `{% set says %}` inside the loop is visible to the include (Jinja passes loop-local variables to includes).

- [ ] **Step 5: Rewrite `kid.html`**

```jinja
{% extends "base.html" %}
{% block title %}{{ student.key | nickname }} · Fridge Sheet{% endblock %}
{% block content %}
{% set page_title = student.key | nickname %}{% include "_page_head.html" %}
{% include "_child_nav.html" %}
{% include "_verdict_sections.html" %}
<section class="sec all-work" aria-labelledby="all-head">
  <div class="sec-head"><h3 id="all-head">All assignments</h3><span class="count">{{ rows | length }} {{ 'shown' if f.show == 'all' else 'open' }}</span>
    {# The table's own controls live in its head (spec 2026-09-28 §3). The form re-asks for the whole
       table; the hidden sort inputs keep the sort a parent chose when they narrow to one course. #}
    <form class="filters controls" hx-get="/kids/{{ student.key | urlencode }}" hx-target="#items" hx-push-url="true" hx-trigger="change">
      <span class="seg" role="group" aria-label="Show">
        {# Open work's "Not shown" links open exactly the set they count (#125); the choice stays
           checked here so narrowing by class keeps it. #}
        {% set narrowed = {'past_window': 'Past the late-work window', 'handled': 'Handled'}.get(f.show) %}
        <label><input type="radio" name="show" value="open" {{ 'checked' if f.show not in ('all', 'past_window', 'handled') }}> Open</label>
        <label><input type="radio" name="show" value="all" {{ 'checked' if f.show == 'all' }}> Everything</label>
        {% if narrowed %}<label><input type="radio" name="show" value="{{ f.show }}" checked> {{ narrowed }}</label>{% endif %}
      </span>
      <label>Class <select name="course"><option value="">All classes</option>{% for cid, label in course_options %}<option value="{{ cid }}" {{ 'selected' if f.course_id == cid }}>{{ label }}</option>{% endfor %}</select></label>
      <details class="more-filters"{{ ' open' if f.source or f.kind or f.flagged or f.outcome or f.verdict }}><summary>More filters</summary>
        <label>Which gradebook <select name="source"><option value="">either</option><option value="canvas" {{ 'selected' if f.source == 'canvas' }}>in Canvas</option><option value="hac" {{ 'selected' if f.source == 'hac' }}>in HAC</option><option value="both" {{ 'selected' if f.source == 'both' }}>in both</option></select></label>
        <label>Kind of work <select name="kind"><option value="">any</option>{% for v in ("online", "paper", "in class") %}<option value="{{ v }}" {{ 'selected' if f.kind == v }}>{{ v }}</option>{% endfor %}</select></label>
        <label>Your answer <select name="flagged"><option value="">any</option><option value="any" {{ 'selected' if f.flagged == 'any' }}>answered or asked</option><option value="handled" {{ 'selected' if f.flagged == 'handled' }}>handled</option><option value="marked" {{ 'selected' if f.flagged == 'marked' }}>asked or following up</option><option value="none" {{ 'selected' if f.flagged == 'none' }}>not answered</option>
          {# Each answer, as it stands: the one label table's state column, in the menu's order (#129). #}
          {% for v, _ in FLAG_CHOICES %}<option value="{{ v }}" {{ 'selected' if f.flagged == v }}>{{ v | flag_label('state', student.key | tier_of) }}</option>{% endfor %}</select></label>
        <label>What the app says <select name="verdict"><option value="">anything</option>{% for v, label in (("question", "needs your answer"), ("decided", "decided for you"), ("waiting", "waiting")) %}<option value="{{ v }}" {{ 'selected' if f.verdict == v }}>{{ label }}</option>{% endfor %}</select></label>
        <label>Outcome <select name="outcome"><option value="">any</option>{% for v in OUTCOMES %}<option value="{{ v }}" {{ 'selected' if f.outcome == v }}>{{ OUTCOME_LABELS[v] }}</option>{% endfor %}</select></label>
      </details>
      <input type="hidden" name="sort" value="{{ f.sort }}">
      <input type="hidden" name="dir" value="{{ f.direction }}">
    </form>
    {% if widened %}<p class="lead" role="note">Showing everything that matches, not only open work.</p>{% endif %}
  </div>
  <div id="items">
  {% block partial %}
  {% include "_item_rows.html" %}
  {% endblock %}
  </div>
  {# What the two words in "Where it stands" mean, once, under the table (spec 2026-09-28 §2). #}
  {% include "_sources_hint.html" %}
</section>
{% endblock %}
```

Check `routes/kid.py` passes `rows` to the template (the `_item_rows.html` loop uses `rows`, so it does).

- [ ] **Step 6: Make the sources hint the legend, and the done-line the line density**

`_sources_hint.html`, whole file:

```jinja
{# What the two systems are, in the reader's words (kids' UX audit F3): once per page, as the
   Assignments table's legend and at the foot of the check-in's queue (spec 2026-09-28 §2). #}
<p class="legend sources-hint muted">{{ 'copy.sources_hint' | say((student.key | tier_of) if student is defined and student else '') }}</p>
```

`_answered.html` lines 4–9: change the opening tag to `<div class="line ok done-line" id="{{ qid }}" data-focus data-announce="{{ item.name }}: {{ said }}">` and line 5 to `<span class="glyph" aria-hidden="true">✓</span>`. Nothing else in the file changes.

- [ ] **Step 7: Run the tests**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_page_layout.py tests/test_web_words_nav.py tests/test_web_who.py tests/test_web_tier_wording.py tests/test_web_tone_layout.py tests/test_web_kid_questions.py tests/test_web_kid_table.py tests/test_web_tier_parity.py tests/test_web_tier_markup.py tests/test_web_questions.py tests/test_web_ui_flow.py tests/test_web_a11y.py -q`
Expected: all pass. If `test_web_kid_questions.py::test_alex_has_one_question_one_decided_and_two_waiting` fails on `body.index("Waiting")`, the word "Waiting" now first appears in a line's facts inside Settled; change line 18 to `body[body.index("Settled by the records"):body.index("Waiting, nothing to do yet")]` and line 20 to `body[body.index("Waiting, nothing to do yet"):body.index('id="items"')]`.

- [ ] **Step 8: Commit**

```bash
git add fridgesheet/web/templates tests
git commit -m "Assignments is four sections: the state line under the tabs, questions as cards, settled and waiting as lines, the table with its filters in its own head and the glossary as its legend (spec 2026-09-28 §3)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The Questions page as sections and lines

**Files:**
- Modify: `fridgesheet/web/templates/questions.html` (lines 9–36)

**Interfaces:**
- Consumes: `_item.html` line density; the section markup (Task 4).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web_section_and_card.py`:

```python
def test_the_questions_page_is_one_section_per_kid_with_lines_for_the_waiting(tmp_path):
    from fridgesheet.web import db
    from fridgesheet.web.stores import flags
    lab = _id(tmp_path, "Lab notebook")
    conn = db.open_db(tmp_path)
    flags.set_flag(conn, lab, "ask_teacher", now="2026-09-15T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/questions").text
    assert re.search(r'<section class="sec kid-questions"[^>]*>\s*<div class="sec-head"><h3>Alex</h3><span class="count">1</span>', body)
    assert re.search(r'<h4>Waiting on the teacher</h4>\s*<div class="lines">\s*<div class="line grey" id="q-%d">' % lab, body)
    assert body.count("<h2") == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py -q -k questions_page`
Expected: FAIL (`sec kid-questions` not found).

- [ ] **Step 3: Rewrite `questions.html` from line 7 to the end**

```jinja
{% for g in groups %}
{% set student = g.student %}{% set tier = student.key | tier_of %}
<section class="sec kid-questions"{% if tier %} data-tier="{{ tier }}"{% endif %}>
  <div class="sec-head"><h3>{{ student.key | nickname }}</h3><span class="count">{{ g.questions | length }}</span><span class="controls"><a href="/kids/{{ student.key | urlencode }}">Open {{ student.key | nickname }}'s work →</a></span></div>
  {# Past-credit work is a status, not a question, so it is not in the list below: the bar names
     every item it will mark, and its confirm names them again (#124). #}
  {% if g.past_credit | length >= 2 %}{% set names = g.past_credit | map(attribute='name') | join(', ') %}
  <form class="lines bulk" method="post" action="/questions/let-go" data-confirm="Let all {{ g.past_credit | length }} go: {{ names }}? They stop counting as open work on the sheet and Open work. Nothing is deleted, and Undo puts them back.">
    <input type="hidden" name="kid" value="{{ student.key }}">
    <span>{{ g.past_credit | length }} of {{ student.key | nickname }}'s assignments are too late for credit: {% for v in g.past_credit %}<b>{{ v.name }}</b> <span class="muted">({{ v.course_short }}{% if v.due %}, due {{ v.due | wd_md }}{% endif %})</span>{{ ', ' if not loop.last }}{% endfor %}.</span> <button>Let all {{ g.past_credit | length }} go</button>
  </form>
  {% endif %}
  {% if g.let_go %}
  <form class="lines bulk" method="post" action="/questions/let-go/undo" role="status">
    <input type="hidden" name="kid" value="{{ student.key }}"><input type="hidden" name="ids" value="{{ g.let_go | map(attribute='id') | join(',') }}">
    <span>Let go: {% for v in g.let_go %}<b>{{ v.name }}</b>{{ ', ' if not loop.last }}{% endfor %}.</span> <button class="link">Undo</button>
  </form>
  {% endif %}
  {% for item in g.questions %}{% include "_question.html" %}{% else %}<p class="muted">Nothing to ask about {{ student.key | nickname }}'s work.</p>{% endfor %}
  {% if g.asked %}
  <h4>Waiting on the teacher</h4>
  <div class="lines">{% for item in g.asked %}{% set density = 'line' %}{% set tone = 'grey' %}{% set says = item | standing(tier) %}{% set line_action %}{% if item.teacher_email %}<a href="mailto:{{ item.teacher_email }}?subject={{ ('About ' ~ item.name) | urlencode }}&amp;body={{ item | mailto_body | urlencode }}">Email</a>{% endif %}{% endset %}{% include "_item.html" %}{% endfor %}</div>
  {% endif %}
  {% if g.twins %}
  <details class="sec quiet"><summary><h3>Can't pair these</h3> <span class="count">{{ g.twins | length }}</span></summary>
    <p class="lead">These may be one assignment listed under two names. The app keeps them apart; nothing is asked of the family.</p>
    <ul>{% for c, h in g.twins %}<li>Canvas "{{ c.name }}" ({{ c.due | wd_md }}) and HAC "{{ h.name }}" ({{ h.due | wd_md }})</li>{% endfor %}</ul>
  </details>
  {% endif %}
</section>
{% endfor %}
{% endblock %}
```

The `.bulk` forms keep the `.lines` class: the box is the same box. The `.lines.bulk` rule (`form.lines.bulk`) needs no change.

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_questions.py tests/test_web_questions_page.py tests/test_web_tier_markup.py tests/test_web_tier_parity.py tests/test_web_page_layout.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates/questions.html tests/test_web_section_and_card.py
git commit -m "Questions is one section per kid, the waiting-on-the-teacher list in line density and the unpaired twins a folded section (spec 2026-09-28 §3)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Check-in and Plan: Must finish, the plan, the queue, the step form's evidence

**Files:**
- Modify: `fridgesheet/web/templates/_must_finish.html` (whole file), `_plan_panel.html` (whole file), `checkin.html` (lines 14–70), `plan_step.html:23`
- Delete: `fridgesheet/web/templates/_planning_evidence.html`
- Modify tests: `tests/test_web_checkin.py`, `tests/test_web_checkin_verdicts.py`, `tests/test_kids_ux_small_items.py:53-56`, `tests/test_web_tier_wording.py:186`, `tests/test_web_tone_layout.py:102-105`, `tests/test_web_page_layout.py:57`

**Interfaces:**
- Consumes: `_item.html` card density with `box_id`, `word`, `badges`, `late_line`, `stamp`, `linked`, `plan_state`, `earlier`, `exclude`, `first` (Task 3); `copy.not_counted_tonight` (Task 2).
- Produces: `<div class="item step">` for a family step (the item classes inline; see Deviations 4); `<details class="sec queue-group…">` with `<summary><h3>…</h3> <span class="count">…</span></summary>` for the queue groups.

- [ ] **Step 1: Update the existing tests with these literal replacements**

Apply with `sed -i` from the worktree root, then re-read the touched lines:

```bash
# the Must-finish row's box
sed -i 's|<div class="mf-row\[^"\]\*" id="mf-|<div class="item[^"]*" id="mf-|g; s|(?=<div class="mf-row|(?=<div class="item|g' tests/test_web_checkin.py tests/test_web_checkin_verdicts.py tests/test_kids_ux_small_items.py tests/test_web_tier_wording.py
# the review card and the plan step
sed -i "s|<article class=\"card review-card\" id=\"qc-%d\".*?</article>|<div class=\"item[^\"]*\" id=\"qc-%d\">.*?(?=<div class=\"item\|</details>)|; s|<article class=\"card review-card|<div class=\"item[^\"]*\" id=\"qc-|g" tests/test_web_checkin_verdicts.py tests/test_web_checkin.py
sed -i "s|<article class=\"card plan-card\">|<div class=\"item step\">|g" tests/test_web_checkin.py
# the queue groups' summary carries an h3
sed -i "s|re.split(r'<details class=\"queue-group\"', body)|re.split(r'<details class=\"sec queue-group', body)|; s|re.search(r\"<summary>(.\*?) <span\", g)|re.search(r\"<summary><h3>(.*?)</h3>\", g)|" tests/test_web_checkin_verdicts.py tests/test_web_checkin.py
sed -i "s|'<details class=\"queue-group\" open>'|'<details class=\"sec queue-group\" open>'|g; s|'<details class=\"queue-group\" open>\\\\n    <summary>Worth checking'|'<details class=\"sec queue-group\" open>\\\\n    <summary><h3>Worth checking</h3>'|; s|'<details class=\"queue-group\" >\\\\n    <summary>Waiting on the school'|'<details class=\"sec queue-group quiet\" >\\\\n    <summary><h3>Waiting on the school</h3>'|; s|'<details class=\"queue-group\" >\\\\n    <summary>Other open work'|'<details class=\"sec queue-group quiet\" >\\\\n    <summary><h3>Other open work</h3>'|" tests/test_web_checkin.py
# the ask line's class
sed -i "s|'<p class=\"ask\">'|'<p class=\"ask-line\">'|; s|'class=\"ask\"' not in card|'class=\"ask-line\"' not in card|" tests/test_web_checkin_verdicts.py
```

Then by hand:
- `tests/test_web_checkin_verdicts.py` line 57: `worth_asks = len(re.findall(r'<div class="item ask" id="qc-', _groups(body)["Worth checking"]))`
- `tests/test_kids_ux_small_items.py` line 56: `assert "allows 7 days" in row and row.index("<summary>Record</summary>") < row.index("allows 7 days")`
- `tests/test_web_tone_layout.py` lines 102–105: replace the test body with `assert re.search(r"\.item \.answers[^{]*\{[^}]*display:\s*flex", CSS)` and its docstring's last clause with "the row styling is the item's, on every page".
- `tests/test_web_page_layout.py` line 57: remove `r"\.checkin-intro", ` from the tuple.
- `tests/test_web_checkin.py`: the `"Completed steps"` split and the `"<h2>Add a task</h2>"` and `step-more` assertions stay as they are.

Add to `tests/test_web_section_and_card.py`:

```python
# --- §4.3 Check-in and Plan ---------------------------------------------------------------------------

def test_a_must_finish_row_is_the_item_with_the_sheets_word_at_the_right_and_no_ask(tmp_path):
    vid = _id(tmp_path, "Vocabulary")                                          # due today, nothing handed in
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    row = re.search(r'<div class="item red" id="mf-%d">.*?(?=<div class="item|</div><!-- /\w+ -->)' % vid, body, re.S).group(0)
    head = re.search(r'<div class="item-head">(.*?)</div>', row, re.S).group(1)
    assert re.search(r'<span class="name"><a href="/kids/Alex\?show=all#row-%d" data-focus-target>Vocabulary</a></span>' % vid, head)
    assert re.search(r'<span class="when word">DUE TONIGHT</span>', head)
    assert 'class="ask-line"' not in row and 'id="qc-%d"' % vid in row       # answers keep their own slot
    foot = re.search(r'<div class="item-foot">(.*?)</div>', row, re.S).group(1)
    assert "<summary>Record</summary>" in foot and "Plan a step" in foot and "Add details" not in foot and "Notes (" not in foot


def test_the_plan_is_sections_and_a_step_is_the_item_with_its_provenance_in_the_foot(tmp_path):
    from uuid import uuid4
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/kids/Alex/check-in/step", data=dict(title="Pick up the form", family_account="", next_step="Bring it home", owner="Alex",
               planned_for="2026-09-15", minutes="20", state="planned", position="", request_key=str(uuid4()), revision="0"), follow_redirects=False)
    assert r.status_code == 303
    body = c.get("/kids/Alex/plan").text
    heads = re.findall(r'<(?:section|details) class="sec[^"]*"[^>]*>\s*(?:<div class="sec-head">|<summary>)<h3[^>]*>([^<]*)</h3>', body)
    assert heads[:2] == ["Must finish", "Our next steps"] and "Worth checking" in heads and "Waiting on the school" in heads
    step = re.search(r'<div class="item step">.*?<div class="item-foot">(.*?)</div>\s*</div>', body, re.S)
    assert step and "Edit or complete step" in step.group(1) and re.search(r'<span class="stamp">Recorded \w{3} 9/15', step.group(1))
    assert re.search(r'<p class="ours">Alex · 20 min</p>', body)
    assert "checkin-intro" not in body and 'class="eyebrow"' not in body


def test_a_finished_check_in_shows_in_the_state_line(tmp_path):
    from uuid import uuid4
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/kids/Alex/check-in/finish", data={"available_minutes": "40", "next_check": "2026-09-14", "summary": "Biology first.",
                                                   "recorded_by": "Mom", "request_key": str(uuid4())}, follow_redirects=False)
    assert r.status_code == 303
    line = re.search(r'<p class="tab-hint">(.*?)</p>', c.get("/kids/Alex/check-in").text, re.S).group(1)
    assert "Last check-in" in line and "recorded by Mom" in line and "time to check in" in line and "What we agreed: Biology first." in line
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_checkin.py tests/test_web_checkin_verdicts.py -q`
Expected: the new tests and every updated regex fail.

- [ ] **Step 3: Rewrite `_must_finish.html`**

```jinja
{# Must finish (spec 2026-09-27 §4): Open work's rows, sectioned for tonight. Computed from the
   school record every time, never stored; a row leaves when the record says the work is in or
   the family answers "It's handed in". Its own section, outside #plan, so the out-of-band swap
   after an answer cannot replace the row a done-line and its Undo sit in (§12). Each row is the
   item surface (spec 2026-09-28 §4) with the row's own id `mf-<id>` and the answers in `qc-<id>`. #}
{% set tier = student.key | tier_of %}
<section id="must-finish" class="sec must-finish" aria-labelledby="mf-heading">
  <div class="sec-head"><h3 id="mf-heading">{{ 'copy.must_finish' | say(tier) }}</h3><span class="count">{{ must_finish | length }}</span>{% if jobs %}<span class="controls"><button type="button" hx-post="/jobs/refresh" hx-vals='{"reload_page": "1"}' hx-target="#job" hx-swap="outerHTML">{{ 'copy.check_again' | say(tier) }}</button></span>{% endif %}
    <p class="lead">{{ 'copy.must_finish_hint' | say(tier) }}{% if data_as_of %} {{ 'copy.list_as_of' | say(tier, {'when': data_as_of | wd_md_time}) }}{% endif %}</p></div>
  {# Only a refresh job's own card belongs here: a doctor or login job started elsewhere must
     not show as if it were this button's progress, and only a refresh reloads the page when it
     finishes (review finding 5). #}
  {% if job and job.kind == 'refresh' %}{% with busy=false, reload_page=true %}{% include "_job.html" %}{% endwith %}{% else %}<div id="job"></div>{% endif %}
  {# Each tuple: key, heading phrase, rows, red, grey, the action to put first (or none), and
     whether the section folds. #}
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
  {% if fold %}<details class="sec quiet mf-fold"><summary><h3>{{ label | say(tier) }}</h3> <span class="count">{{ rows | length }}</span></summary>{% endif %}
  <div class="mf-section" data-section="{{ key }}">{% if not fold %}<h4>{{ label | say(tier) }}</h4>{% endif %}
    {% for view in rows %}
    {% if key == 'paper' %}{% set pk = view.verdict | pace_key %}{% if pk and loop.changed(view.course_id) %}<p class="inset">{{ pk | say(tier, view.verdict.pace) }}</p>{% endif %}{% endif %}
    {% set item = view %}{% set density = 'card' %}{% set slot = 'qc-' ~ view.id %}{% set box_id = 'mf-' ~ view.id %}
    {% set tone = 'red' if red else 'grey' if grey else '' %}{% set word = view | sheet_word(tier) %}{% set linked = true %}{% set late_line = true %}
    {% set badges = [] %}
    {% if view.verdict.kind in ('submitted_hac_zero', 'excused_hac_zero', 'hac_lower') %}{% set badges = badges + [('badge.zero_to_check' | say(tier))] %}{% elif view.verdict.kind == 'stale_answer' %}{% set badges = badges + [('badge.changed_since_answer' | say(tier))] %}{% endif %}
    {% set stamp = (('badge.seen_at_checkin' if view.id in seen else 'badge.new_since_checkin') | say(tier, {'day': seen_day})) if seen_day else '' %}
    {% set earlier = completed_for.get(view.id) %}
    {% if grey %}{% set exclude = ['too_late', 'ignore', 'done', 'plan:today', 'plan:tomorrow', 'ask_teacher', 'follow_up', 'excused'] %}{% endif %}
    {% include "_item.html" %}
    {% if grey %}{% set exclude = ['too_late', 'ignore'] %}{% endif %}
    {% endfor %}
  </div><!-- /{{ key }} -->
  {% if fold %}</details>{% endif %}
  {% endfor %}
  {% if not must_finish | length %}<p class="muted">{{ 'copy.nothing_due' | say(tier) }}</p>{% endif %}
</section>
```

The grey group ("Handed in, waiting for a grade") drew no answers before (`{% if vd.answers and not grey %}`); excluding every action keeps that, and `_answers.html` then renders an empty `.answers` div with no forms, so the parity counts are unchanged. The `first` variable is already in scope from the loop tuple and `_answers.html` reads it.

- [ ] **Step 4: Rewrite `_plan_panel.html`**

```jinja
{# "Our next steps": the family's plan for this kid. Rendered on the check-in and the plan
   page, and swapped in out of band after a one-tap plan answer (spec 6.5). A step is drawn with
   the item's classes (spec 2026-09-28 §4.3): head = title, class, the Must-finish badge, when it is
   planned for; says = the step; ours = owner · minutes; foot = Record, Edit, the provenance stamp. #}
{% set tier = student.key | tier_of %}
<section id="plan" class="sec plan" aria-labelledby="plan-heading"{% if oob is defined and oob %} hx-swap-oob="true"{% endif %}>
  <div class="sec-head"><h3 id="plan-heading">Our next steps</h3><span class="controls"><a class="button-link" href="{{ base }}/step?return_to={{ here | urlencode }}">Add a task</a></span>
    <p class="lead"><strong>{{ 'copy.tonight_steps' | say(tier, {'steps': today_steps_n, 's': '' if today_steps_n == 1 else 's', 'minutes': total_minutes}) }}</strong>{% if unpicked %} · {{ 'copy.tonight_unpicked' | say(tier, {'n': unpicked}) }}{% endif %}{% if school_has_n %} · {{ 'copy.tonight_school_has' | say(tier, {'n': school_has_n}) }}{% endif %}</p>
    {% if last_check %}<p class="lead">Last agreed time budget: {{ last_check.available_minutes }} min{% if not budget_today %} (agreed {{ last_check.finished_at | wd_md }}, for that day){% endif %}{% if over > 0 %} · <strong class="warn">{{ total_minutes }} min planned today, {{ last_check.available_minutes }} min available: {{ over }} min over. Move a step to another day.</strong>{% endif %}</p>{% endif %}
  </div>
  {% for label in ('planned', 'blocked', 'waiting') %}
  <h4>{{ states[label] }}</h4>
  {% for step in steps if step.state == label and not step.witness %}
  <div class="item step">
    <div class="item-head"><span class="name">{{ step.title }}</span><span class="meta">{% if step.view %}{{ step.view.course_short }}{% if step.must_word %} <span class="badge">{{ 'badge.must_finish' | say(tier, {'word': step.must_word}) }}</span>{% endif %}{% elif step.item_id %}<span class="muted">no longer on the school list</span>{% else %}Family-added task{% endif %}</span><span class="when">{{ 'check again' if label in ('waiting', 'blocked') else 'planned for' }} {{ step.planned_for | wd_md }}{% if step.planned_for < today %} · <span class="warn">revisit this date</span>{% elif step.planned_for == today %} · today{% endif %}</span></div>
    <p class="facts">{{ step.next_step }}</p>
    <p class="ours">{{ step.owner }}{% if step.minutes %} · {{ step.minutes }} min{% endif %}</p>
    {% if step.family_account %}<p class="ours">{{ step.family_account }}</p>{% endif %}
    {% if step.changed %}<p class="inset warn">School evidence changed since this step was saved. Review it together; your agreement is still here.</p>{% endif %}
    <div class="item-foot">{% if step.view %}<details><summary>{{ 'copy.record' | say(tier) }}</summary>{% with item=step.view %}{% include "_record.html" %}{% endwith %}</details>{% endif %}
      <a href="{{ base }}/step?step_id={{ step.id }}&amp;return_to={{ here | urlencode }}">Edit or complete step</a>
      <span class="stamp">{% if step.since == 'agreed' %}Agreed at the {{ last_check.finished_at | wd_md }} check-in · {% elif step.since == 'edited' %}Edited since the {{ last_check.finished_at | wd_md }} check-in · {% elif step.since == 'added' %}Added since the {{ last_check.finished_at | wd_md }} check-in · {% endif %}Recorded {{ step.created_at | wd_md_time }}{% if step.created_by %} by {{ step.created_by }}{% endif %}{% if step.updated_at != step.created_at %} · edited {{ step.updated_at | wd_md_time }}{% if step.recorded_by %} by {{ step.recorded_by }}{% endif %}{% endif %}</span></div>
  </div>
  {% else %}<p class="muted">No steps here yet.</p>{% endfor %}
  {% endfor %}
  {% if school_has_n %}
  <h4>{{ 'copy.school_has_it' | say(tier) }}</h4>
  {% for step in steps if step.witness %}
  <div class="item step ok grey school-has-it">
    <div class="item-head"><span class="name">{{ step.title }}</span><span class="meta">{% if step.view %}{{ step.view.course_short }}{% endif %}</span><span class="when">{{ 'check again' if step.state in ('waiting', 'blocked') else 'planned for' }} {{ step.planned_for | wd_md }}</span></div>
    <p class="facts">{{ step.witness[0] | say(tier, step.witness[1]) }}</p>
    <form method="post" action="{{ base }}/step/{{ step.id }}/complete" class="answers"><input type="hidden" name="revision" value="{{ step.revision }}"><input type="hidden" name="return_to" value="{{ here }}"><button>{{ 'a.mark_step_complete' | say(tier) }}</button></form>
    <p class="ours">{{ step.owner }}{% if step.minutes %} · {{ step.minutes }} min{% endif %} · {{ 'copy.not_counted_tonight' | words(tier) }}</p>
    {% if step.family_account %}<p class="ours">{{ step.family_account }}</p>{% endif %}
    {% if step.changed %}<p class="inset warn">School evidence changed since this step was saved. Review it together; your agreement is still here.</p>{% endif %}
    <div class="item-foot">{% if step.view %}<details><summary>{{ 'copy.record' | say(tier) }}</summary>{% with item=step.view %}{% include "_record.html" %}{% endwith %}</details>{% endif %}
      <a href="{{ base }}/step?step_id={{ step.id }}&amp;return_to={{ here | urlencode }}">Edit</a>
      <span class="stamp">{% if step.since == 'agreed' %}Agreed at the {{ last_check.finished_at | wd_md }} check-in · {% endif %}Recorded {{ step.created_at | wd_md_time }}{% if step.created_by %} by {{ step.created_by }}{% endif %}</span></div>
  </div>
  {% endfor %}
  {% endif %}
  <details class="sec quiet queue-group"><summary><h3>Completed steps</h3> <span class="count">{{ completed | length }}</span></summary>
    <p class="lead">Finishing a step is our own record. The school decides what counts as submitted.</p>
    {% for step in completed %}<div class="item step grey"><div class="item-head"><span class="name">{{ step.title }}</span><span class="when">completed {{ step.updated_at | wd_md_time }}{% if step.recorded_by %} by {{ step.recorded_by }}{% endif %}</span></div><p class="facts">{{ step.next_step }} · {{ step.owner }}</p>{% if step.family_account %}<p class="ours">{{ step.family_account }}</p>{% endif %}<div class="item-foot"><a href="{{ base }}/step?step_id={{ step.id }}&amp;return_to={{ here | urlencode }}">Edit or reopen</a>{% if step.item_id %}<a href="{{ base }}/step?item_id={{ step.item_id }}&amp;return_to={{ here | urlencode }}">Add another step</a>{% endif %}</div></div>{% endfor %}
  </details>
</section>
```

The old "School evidence changed" `.review-note` becomes `.inset.warn` with the same words; the school-has-it card's `Mark step complete` form keeps its one button and the old "Edit" link moves to the foot, so the button and form counts are unchanged. `.plan-card.school-has-it` styling (opacity, strike-through) is dropped: the `.ok.grey` rules say the same thing.

- [ ] **Step 5: Rewrite `checkin.html` lines 14–70**

Replace from the comment "The one sentence of instruction is the tab's hint" through the closing `</section>` of the review queue with:

```jinja
{% set tier = student.key | tier_of %}
<div class="checkin-layout {{ 'plan-only' if plan_only }}">
<div class="checkin-main">
{% include "_must_finish.html" %}
{% include "_plan_panel.html" %}
{% if not plan_only %}
<section class="card finish-checkin sec">
  <h3>Agree and wrap up</h3><p>Check that the plan fits. Save what you agreed, including who will help and when you’ll meet again.</p>
  {% set fv = finish_values | default({}) %}
  <form method="post" action="{{ base }}/finish" class="plan-form">
    <input type="hidden" name="request_key" value="{{ finish_token }}">
    <div class="form-pair"><label>Time available today (minutes)<input type="number" name="available_minutes" min="1" max="1440" required value="{{ fv.get('available_minutes', last_check.available_minutes if last_check else 40) }}"></label>
    <label>Next check-in<input type="date" name="next_check" required value="{{ fv.get('next_check', next_default) }}"></label></div>
    <label>What we agreed<textarea name="summary" maxlength="4000" required placeholder="What will we do first? What help do we need?">{{ fv.get('summary', '') }}</textarea></label>
    <label>Recorded by <span class="muted">(a grown-up helping · optional)</span><input name="recorded_by" maxlength="100" value="{{ fv.get('recorded_by', last_check.recorded_by if last_check else '') }}" placeholder="Mom, Dad, Grandma…"></label>
    <button class="primary">Finish check-in</button>
  </form>
</section>
{% endif %}
{% if asked %}<p class="asked-line"><strong>{{ 'copy.asked_the_school' | say(tier) }}:</strong> {% for v, key, when in asked %}<a href="/kids/{{ student.key | urlencode }}?show=all#row-{{ v.id }}">{{ v.name }}</a>: {{ key | say(tier, {'when': when}) }}{{ ' · ' if not loop.last }}{% endfor %}</p>{% endif %}
<section class="review-queue" aria-labelledby="review-heading">
  <h3 id="review-heading" class="sr-only">Review</h3>
  {% for label, rows in queues.items() %}
  <details class="sec queue-group{{ ' quiet' if label != worth_group }}" {{ 'open' if (label == worth_group and worth_open) }}>
    <summary><h3>{{ queue_keys[label] | say(tier) }}</h3> <span class="count">{{ rows | length }}</span></summary>
    {% if label == worth_group %}<p class="lead">{{ 'copy.queue_hint' | say(tier) }}</p>{% endif %}
    {% for view in rows %}
    {% set item = view %}{% set density = 'card' %}{% set slot = 'qc-' ~ view.id %}{% set box_id = slot %}{% set linked = true %}{% set late_line = true %}
    {% set plan_state = 'waiting' if label == waiting_group else '' %}{% set earlier = completed_for.get(view.id) %}
    {% include "_item.html" %}
    {% else %}<p class="muted">Nothing in this group.</p>{% endfor %}
  </details>
  {% endfor %}
  <p><a href="/kids/{{ student.key | urlencode }}?show=all">{{ 'copy.browse_all_link' | say(tier) }}</a> {{ 'copy.browse_all_rest' | words(tier) }}</p>
  {# What the two systems the cards quote are: once, at the foot of the queue (#190). #}
  {% include "_sources_hint.html" %}
</section>
```

Keep everything after (the closing `</div></div>`, the `.halves` strip, Previous agreements) as it is, except the Previous agreements fold: change `<details class="queue-group"><summary>Previous agreements <span class="badge">{{ history | length }}</span></summary>` to `<details class="sec quiet queue-group"><summary><h3>Previous agreements</h3> <span class="count">{{ history | length }}</span></summary>` and each `<article class="card plan-card">` inside it to `<div class="item step grey">` with its matching `</article>` to `</div>`.

The review card's "Plan a step" was a `.button-link`; it is now the foot's link, the same words, one form and button fewer? No: it was an `<a>`, not a button, so the counts hold. The `.review-card`'s answers came after the evidence; they now come after the ask, before `.ours`.

- [ ] **Step 6: `plan_step.html` and delete `_planning_evidence.html`**

`plan_step.html` line 23: replace with

```jinja
{% if view %}<div class="item"><div class="item-head"><span class="name">{{ view.name }}</span><span class="meta">{{ view.course_short }}{% if view.due %} · due {{ view.due | wd_md }}{% set at = view | due_at(tier | default('')) %}{% if at %} {{ at }}{% endif %}{% endif %}</span></div>{% with item=view %}{% include "_record.html" %}{% endwith %}</div>{% endif %}
```

Then `git rm fridgesheet/web/templates/_planning_evidence.html`. Grep to confirm nothing includes it: `grep -rn planning_evidence fridgesheet tests` must print nothing (the `_source_facts.html` comment was rewritten in Task 2).

- [ ] **Step 7: Run the tests**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_checkin.py tests/test_web_checkin_verdicts.py tests/test_web_checkin_queue.py tests/test_must_finish.py tests/test_web_plan_steps_everywhere.py tests/test_kids_ux_small_items.py tests/test_web_tier_wording.py tests/test_web_tone_layout.py tests/test_web_page_layout.py tests/test_web_tier_parity.py tests/test_web_ui_flow.py tests/test_web_who.py -q`
Expected: all pass. A `test_web_tier_wording.py` failure on "evening" means the row's meta drew the due hour without `due_at`; the partial uses `due_at`, so check `word` was passed (a Must-finish row's `.when` is the word and the date goes to `.meta`).

- [ ] **Step 8: Commit**

```bash
git add -A fridgesheet/web/templates tests
git commit -m "Check-in and Plan take the section and the item: Must-finish rows with the sheet's word at the right, steps with their provenance in the foot, the queue as folded sections of cards, the evidence block gone into the Record (spec 2026-09-28 §4.3)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Today, Open work, the class page and the print page's screen view take the section head

**Files:**
- Modify: `fridgesheet/web/templates/dashboard.html:7,22`, `open.html:26-28`, `course.html:33,40,43`, `plan_print.html` (its screen-side headings only)
- Modify tests: `tests/test_web_outcomes.py:112`, `tests/test_web_page_layout.py:222`

**Interfaces:**
- Consumes: the section markup (Task 4).
- Produces: `p.outcome-line` on the Today card (was `p.record`).

- [ ] **Step 1: Update and add tests**

`tests/test_web_outcomes.py` line 112: `assert 'class="outcome-line"' in dash and "not done</a>" in dash and "due so far" in dash`

`tests/test_web_page_layout.py` line 222: `assert re.search(r'<div class="sec-head"><h3 class="kid-head"><a href="/kids/Alex">Alex</a></h3></div>', body)`

Add to `tests/test_web_section_and_card.py`:

```python
# --- §3 every other page ----------------------------------------------------------------------------

def test_today_open_work_and_a_class_page_head_their_sections_the_one_way(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    today = c.get("/").text
    assert re.search(r'<section class="sec kids"[^>]*>\s*<div class="cards">', today)
    assert 'class="outcome-line"' in today and 'class="record"' not in today
    open_work = c.get("/open").text
    assert open_work.count('<section class="sec kid"') == 2
    course = c.get("/kids/Alex").text
    cid = re.search(r'/kids/Alex/courses/(\d+)', course).group(1)
    page = c.get(f"/kids/Alex/courses/{cid}").text
    heads = re.findall(r'<section class="sec[^"]*"[^>]*>\s*<div class="sec-head"><h3>([^<]*)</h3>', page)
    assert heads == ["Grade history", "Notes", "Items"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py -k "today_open_work" tests/test_web_outcomes.py tests/test_web_page_layout.py -q`
Expected: the three fail.

- [ ] **Step 3: Edit the four templates**

`dashboard.html` line 7: `<div class="cards">` becomes `<section class="sec kids" aria-label="Kids"><div class="cards">`; line 58's `</div>` (closing `.cards`) becomes `</div></section>`. Line 22: `<p class="record">` becomes `<p class="outcome-line">`.

`open.html` lines 26–28:

```jinja
<section class="sec kid" id="{{ s.key }}"{% set t = s.key | tier_of %}{% if t %} data-tier="{{ t }}"{% endif %}>
  {# A kid is a section of the page (h3), its two lists parts of that (h4) -- #191. #}
  <div class="sec-head"><h3 class="kid-head"><a href="/kids/{{ s.key }}">{{ s.key | nickname }}</a></h3></div>
```

`course.html`: line 33 `<h3>Grade history</h3>` becomes `<section class="sec"><div class="sec-head"><h3>Grade history</h3></div>`, and after the chart block (line 39's `{% endif %}`) add `</section>`; line 40 `<h3>Notes</h3>` becomes `<section class="sec"><div class="sec-head"><h3>Notes</h3></div>` with `</section>` after the `_notes.html` include (line 42); line 43 `<h3>Items</h3>` becomes `<section class="sec"><div class="sec-head"><h3>Items</h3></div>` with `</section>` after the `#items` div's closing `</div>` (line 50). The `<div class="cards">` at line 7 becomes `<section class="sec"><div class="cards">` and its closing `</div>` (line 32) `</div></section>`.

`plan_print.html`: open it and wrap each `<h3>` heading and its block in `<section class="sec"><div class="sec-head"><h3>…</h3></div> … </section>`; the print stylesheet is unchanged and `.sec`'s margin prints as before (32 px, was 24 px on `main h3`). If `tests/test_web_plan_steps_everywhere.py` or the print test asserts a literal `<h3>Must finish</h3>` sequence, keep the `<h3>` text identical; only the wrapper changes.

`app.css`: add `.outcome-line { font-size: var(--type-small); line-height: 1.7; } .outcome-line a { text-decoration: none; } .outcome-line a.warn { font-weight: 600; }` beside the old `.record` rules (lines 108–110), and change the coarse-pointer selector `.record a` (line 478) to `.outcome-line a, .inset a`. Also add `.kid-head` to the `.sec-head h3` size exception: `.sec-head h3.kid-head { font-size: 22px; }` (the layout standard's type table keeps Open work's kid sections at 22 px).

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py tests/test_web_outcomes.py tests/test_web_page_layout.py tests/test_web_open_today.py tests/test_web_pages.py tests/test_web_a11y.py tests/test_web_plan_steps_everywhere.py tests/test_web_tier_markup.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates fridgesheet/web/static/app.css tests
git commit -m "Today, Open work, a class page and the printed plan's screen view head their sections the one way, and the Today card's outcome line stops sharing a class name with the record (spec 2026-09-28 §3, §9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Retire the old rules and classes, held out by a test

**Files:**
- Modify: `fridgesheet/web/static/app.css` (remove the listed rules)
- Modify: `tests/test_web_tier_css.py:27-29`, `tests/test_web_tone_layout.py:83`, `tests/test_web_a11y.py:161`, `tests/test_web_section_and_card.py`

**Interfaces:**
- Produces: a stylesheet with no rule for `.q`, `.record`, `.mf-row`, `.plan-panel`, `.plan-card`, `.review-card`, `.review-grid`, `.section-head`, `.quiet-head`, `.workspace-heading`, `.school-evidence`, `.review-note`, `.family-account`, `.mf-paper`, `.witness`, `.eyebrow`, `.qmark`, `.checkin-intro`, `.plan-total`, `.next-step`, `.mf-section`'s old paddings, and none of the six greens.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_web_section_and_card.py`:

```python
# --- §9 what this retired ---------------------------------------------------------------------------

RETIRED = (".q ", ".q.", ".q{", ".record", ".mf-row", ".plan-panel", ".plan-card", ".review-card", ".review-grid",
           ".section-head", ".quiet-head", ".workspace-heading", ".school-evidence", ".review-note", ".family-account",
           ".mf-paper", ".witness", ".eyebrow", ".qmark", ".checkin-intro", ".plan-total", ".next-step")
GREENS = ("#286454", "#214f43", "#edf5f1", "#45655e", "#eef3ef", "#aa7c32", "#b7cdc5", "#c9d8cd", "#a2bdb3", "#4f5754", "#6e8f85", "#725017", "#f4f6f4", "#edf6ee", "#eaf1fa")


@pytest.mark.parametrize("selector", RETIRED)
def test_the_stylesheet_has_no_rule_for_a_retired_class(selector):
    assert selector not in CSS, selector


@pytest.mark.parametrize("colour", GREENS)
def test_the_check_ins_own_palette_is_gone(colour):
    assert colour.lower() not in CSS.lower(), colour


@pytest.mark.parametrize("name", sorted(p.name for p in TEMPLATES.glob("*.html")))
def test_no_template_uses_a_retired_class(name):
    src = (TEMPLATES / name).read_text(encoding="utf-8")
    for cls in ("q card", "record\"", "mf-row", "plan-panel", "plan-card", "review-card", "review-grid", "section-head",
                "quiet-head", "workspace-heading", "school-evidence", "review-note", "family-account", "mf-paper",
                "witness", "eyebrow", "qmark", "checkin-intro", "plan-total", "next-step", "done-line\" "):
        assert f'class="{cls}' not in src and f' {cls}"' not in src, f"{name} uses {cls}"


def test_every_radius_and_gap_is_a_token():
    """The documented exceptions: the rail's links and buttons (6px), the chips (10px pill), the
    chooser's 12px buttons, the mark's 6px, the stale banner's 4px, the note's 2px swatch."""
    body = CSS.split(":root", 1)[1]
    for m in re.finditer(r"border-radius:\s*([^;]+);", body):
        v = m.group(1).strip()
        assert v in ("var(--radius)", "6px", "10px", "12px", "4px", "2px", "50%"), v
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH $PYTEST tests/test_web_section_and_card.py -q -k "retired or palette or radius"`
Expected: many fail.

- [ ] **Step 3: Remove the old rules from `app.css`**

Delete these rules (by their selectors; each is one or two lines in the file as of Task 7):
`.notice`'s literal colours (change to `background: var(--wash); border-left: 4px solid var(--accent);`), `.record`, `.record a`, `.record a.warn` (lines 108–110, now duplicated by `.outcome-line`), `.qmark`, `.section-head`, `.quiet-head`, `.done-so-far`, `.tab-hint`'s old rule (line 439; the new one from Task 1 stays), `.sources-hint`'s `margin: -8px 0 16px` (replace with `.sources-hint { margin: var(--s2) 0 0; }`), `.record .sources-hint`, `.workspace-heading`, `.eyebrow`, `.child-nav a[aria-current]`'s colours (change to `border-bottom: 3px solid var(--accent); color: var(--accent); font-weight: 650;`), `.button-link`'s colours (change to `border: 1px solid var(--control); background: var(--paper); color: var(--ink);`), `.checkin-intro`, `.review-grid`, `.review-card, .plan-card`, `.review-card h4, .plan-card h4`, `.school-evidence`, `.school-evidence p`, `.review-note`, `.plan-panel`, `.plan-total`, `.next-step`, `.family-account`, the second `.record` block (line 378), `.school-evidence .source`, `.source`, `.sources .src` (old), `.done-line`'s old three rules (lines 384–386; the new ones stay), `.q`, `.q .what`, `.q .what b`, `.q .facts`, `.q .ask, .review-card .ask`, `.q .answers, .review-card .answers`, `.q .answers form, .review-card .answers form`, `.q .more`, `.lines`/`.lines .line`/`.lines .line:last-child`/`.lines .line > a, .lines .line > form` (old, lines 410–413; the new ones stay), `.badge.plan`, `.must-finish h4`, `.mf-row` and its six rules, `.mf-paper`, `details.mf-fold > summary`, `.plan-card.school-has-it`, `.plan-card.school-has-it > h4`, `.witness`, `.plan-panel { padding: 12px }` inside the 1279px block, the `.review-card a`, `.plan-card a`, `.plan-card details > summary` entries in the coarse-pointer selector lists (lines 354–356), and `.q details.more > summary, .q .more a` in the coarse list at line 470 (keep `.lines .line > button, .lines .line > form button, .add-note > summary`).

Then change the first `.badge` rule (line 90) to read `.badge { display: inline-block; }` only, since the Task 1 rule carries the look; change `.badge.OK`/`.badge.FAIL` and `.badge.current` nothing. Keep `.badge.flag`'s selector out (it is in the Task 1 combined rule).

- [ ] **Step 4: Update the three tests that named old selectors**

`tests/test_web_tier_css.py` lines 27–29:

```python
SECONDARY = (".item-head .meta", ".item-foot", ".ours", ".inset", ".stamp", "p.legend", "td .rel", "td .at",
             "table.work td.item small", "table.work td.where small.thru", ".sources-hint", ".src", ".note .meta",
             ".sources .src", ".lines .line > form")
```

`tests/test_web_tone_layout.py` line 83: `for sel in (r"\.rail \.count",):` (the `.qmark` chip is a `.badge` now).

`tests/test_web_a11y.py` line 161: `for sel in ("table.work td.item small a", ".inset a", ".tally a"):`

- [ ] **Step 5: Run the whole suite**

Run: `env -u PYTHONPATH $PYTEST tests -q 2>&1 | tee /tmp/section-card-full.log | tail -20`
Expected: all pass. Anything that names a retired class is listed in `grep -n "retired\|SECONDARY\|\.q \|mf-row" /tmp/section-card-full.log`.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/web/static/app.css tests
git commit -m "The old containers leave the stylesheet: seven box styles become one item, one inset and one lines box, and the check-in's greens become the accent; a test keeps them out (spec 2026-09-28 §9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Docs, the browser measurements, the one-pager

**Files:**
- Create: `docs/product/features/section-and-card-standard.md`
- Modify: `docs/product/features/page-layout-standard.md` (links), `docs/user-guide.md` (the glossary sentence; one paragraph on a card's slots), `docs/product/2026-09-24-kids-ux-audit.md` (F3 note)
- Run: `scripts/layout_audit_seed.py` + `scripts/layout_audit_measure.py`, `scripts/kids_ui_measure.py`

- [ ] **Step 1: Write the one-pager**

`docs/product/features/section-and-card-standard.md`:

```markdown
---
slug: section-and-card-standard
title: Section and Card Standard
state: live
parent: browser-app
links:
  - kind: related
    project: fridgesheet
    feature: page-layout-standard
  - kind: related
    project: fridgesheet
    feature: all-work-table-ux
---

Below the page head, every page is a stack of one section block, and every assignment is one card with five slots, so a parent or a kid reads the same shape on every page and never reads the same fact twice.

## Problem

The page layout standard made the chrome identical and stopped at "sections of cards". Every spec after it invented its own section and its own card: seven box styles and four heading treatments on one page, one assignment drawn three times (a card at the top, a table row, and a card inside a card when the row opened), four lines of prose before the first thing to do, and a second green palette on Check-in and Plan. Inside the cards, six containers drew an assignment in six orders, the head said "in class · due 9/20" and the sentence under it said it again, and the school's record, the app's reading, the family's layer and the actions interleaved with no hierarchy.

## Target users

Everyone who reads a kid's page: the weeknight triager scanning for what needs an answer, the kid on their own plan, the second caregiver who opens a row to see the record.

## Desired outcome

One section: an h3, a count, one lead sentence, the section's own controls at the right; folded and quiet variants draw the same head. One card, five slots owned by one layer each: head (identity, once: name, class, kind, points, the one word about time at the right), says (the app's one sentence), ask (the question and its one-tap answers), ours (our step, our note), foot (Record, History, Notes, Plan a step, More, and the provenance stamp, tiny). Three densities from one partial: a line, a card, and the card opened as a detail with the record open and Close in the head. Emphasis is a left rule and a word: accent needs an answer, red the school says not in, green done, grey nothing to do. One inset for anything quoted. One radius, a named gap scale, the accent on every page. The line under a kid's tabs is state (Done so far; the last check-in), not instruction. The glossary sentence is said once per page, as the table's legend.

## Success metrics

- `tests/test_web_section_and_card.py` holds it: the tokens, the section head, each density's slots in order, the facts sentence never restating the due date, the glossary at most once per page, no retired class in any template or rule, and every radius a token.
- Doug's Assignments tab, which prompted this, draws MakeMusic #4 once as a card, once as a row, and the row opens flat.
- The parity rule still holds: the tier tests and kid mode render the same rows, forms and buttons.

## Non-goals

- Which rows a page shows and which answers a verdict offers (`docs/outcomes.md`, the verdict table).
- The printed PDF sheet and the paper side of the two print pages.
- The status bar's wording.

## Notes

- Designed in `docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md` from rendered mockups (`2026-09-28-sections-and-items-mockups/`); planned in `docs/superpowers/plans/2026-09-28-section-and-card-standard.md`.
- Supersedes the kids' UX audit's F3 tab hint: the section heads and their leads carry the orientation now.

## Evidence

- `fridgesheet/web/templates/_item.html` (the one partial), `_verdict_sections.html`, `kid.html`, `_child_nav.html`, `_must_finish.html`, `_plan_panel.html`, `checkin.html`, `questions.html`, `_record.html`, `_source_facts.html`
- `fridgesheet/web/static/app.css` (`--radius`, `--s1…--s6`, `.sec`, `.item`, `.inset`, `.lines`)
- `tests/test_web_section_and_card.py`
```

- [ ] **Step 2: Link it, note F3, update the user guide**

`docs/product/features/page-layout-standard.md`: add to `links:` a `- kind: related / project: fridgesheet / feature: section-and-card-standard` entry, and one sentence at the end of Notes: "The content column below the head has its own standard, [[section-and-card-standard]]."

`docs/product/2026-09-24-kids-ux-audit.md`: at finding F3, append: "*2026-09-28: the tab hint is superseded by the section-and-card standard (§3): the line under the tabs is state, and the section heads carry the orientation.*"

`docs/user-guide.md`: find the paragraph that describes a kid's Assignments tab (grep `Assignments`) and add after it:

```markdown
Every assignment is drawn the same way wherever you meet it: its name, class and due date on the first line, one sentence saying what the record means, the question and its answer buttons when there is one, the family's own step or note under a blue rule, and at the bottom the folds: **Record** (what Canvas and HAC hold, and as of when), **History**, **Notes**, **Plan a step** and **More**. A red rule at the left means the school says it is not in; a blue one means it needs your answer; green means done.
```

Make sure the guide still says what Canvas and HAC are (the glossary sentence) once, near where it first names them.

- [ ] **Step 3: Re-run the browser measurements by hand**

```bash
env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python scripts/layout_audit_seed.py 2>&1 | tee /tmp/layout-seed.log | tail -3
# start the app on the seeded home as the seed script's output says (port 8577), in its own Bash call, then:
VIEWPORTS=phone,desktop env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/0783798f/.venv/bin/python scripts/layout_audit_measure.py 2>&1 | tee /tmp/layout-measure.log | tail -30
```

Read the phone numbers for `/kids/Alex`, `/kids/Alex/check-in` and `/kids/Alex/plan`: the first content must land at or above 117 px (the standard's number) and no target under 44 px. Kill the server in its own Bash call (`pkill -f "fridgesheet web --port 8577"`). If a target is under 44 px, it is a new selector missing from the coarse-pointer block in Task 1; add it there and re-measure.

- [ ] **Step 4: Run the whole suite once more, then commit**

Run: `env -u PYTHONPATH $PYTEST tests -q 2>&1 | tail -5`
Expected: all pass.

```bash
git add docs
git commit -m "docs(product): the section-and-card standard's one-pager, the F3 note, the user guide's paragraph on a card (spec 2026-09-28 §9)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- **Spec coverage.** §3 the section: Tasks 1, 4–7. §4.1 slots, §4.2 densities, §4.3 the container map: Tasks 3–6 (the step card inline, Deviation 4). §5 `.card`, `.inset`, `.lines`: Tasks 1, 2, 5, 6. §6 tokens and the greens: Tasks 1, 8. §7 type: Task 1's sizes. §8 phrasing: Task 2 (the `a.add_details` swap on Must finish is Task 6's foot, which draws "Plan a step"). §9 mechanism: every file it names is in a task; `_section.html` is correctly not created. §10 tests: `test_web_section_and_card.py` grows across Tasks 1–8; the "`.when` equals Where it stands" check is narrowed to the cases where the head shows the standing (Deviation 1) and is not separately asserted, since the same `standing` filter feeds both. §11 order: the task order. §12/§13: nothing to build.
- **Placeholders.** None: every template and test step carries its text.
- **Type consistency.** `_item.html`'s variables are the same names in Tasks 3, 4, 5 and 6 (`density`, `slot`, `box_id`, `tone`, `word`, `badges`, `says`, `late_line`, `stamp`, `linked`, `plan_state`, `earlier`, `line_action`); the phrase keys added in Task 2 are the ones Tasks 3 and 6 read; the section markup Task 4 produces is what Tasks 5–7's tests match.
- **Review Focus.** 1 → Task 1's `overflow-wrap` assertion; 2 → Task 3's note test; 3 → Task 6's finished-check-in test; 4 → Task 4's kid-mode test; 5 → the kept `test_web_ui_flow.py` test in Task 3.

---
slug: reconcile-page-interaction
title: Flag & Evidence Card Interaction
state: live
parent: actionable-work-model
---

A parent can open an assignment's flag-and-evidence card, set or change what the family decided, and trust what the card shows — one render, one visible flag, no accidental submits — on whichever page hosts it.

## Problem

A five-persona UX review of the then-standalone Reconcile page (2026-09-23) found the flag/evidence card untrustworthy in five separate ways: pressing Enter in the "why" text box silently fired the form's first button, which was `done`, so typing a reason and hitting Enter marked the item done and dropped it off the page (#37); the flag's reason and date were nested inside a "just saved" message, so they vanished on any plain page load and were recoverable only via a hover-only tooltip invisible on touch (#38); the card rendered its title, case bullets and a five-button flag form twice — once in the outer row, once in the loaded detail — leaving 11 of 16 tab stops duplicate, an anchor pointing at a nonexistent id, and the two forms free to disagree (#39); the page's own tagline promised any flag removed the item, but `follow up` and `ask teacher` left it in place with no indication on the outer card of which flag was set (#41); and the evidence table used per-page vocabulary ("graded 18/25" vs. the check-in's "HAC: 18/25") that made the same item read as a different fact depending on which page showed it (#46).

## Target users

Parents/caregivers triaging open items and setting a flag or reading school evidence for one assignment; the teacher-contact parent persona specifically, for whom a wrong Enter-key submit or an invisible flag reason is a blocker, not an inconvenience.

## Desired outcome

The flag menu (`_flag_menu.html`) and detail card (`_item_detail.html`) render an item's state exactly once per view, with the current flag, its reason and its date shown as a first-class line on a plain load (not conditional on a "just saved" message), and a hidden first submit button that re-posts the current flag so Enter in the reason field can never fall through to a destructive default action. The card's evidence section reuses one partial everywhere an item's school-record facts are shown, so the same item reads identically on the Reconcile/Questions card, the check-in, and plan_step: the source lines themselves are `_source_facts.html`, included by both the detail card's record (`_record.html`) and the check-in's evidence (`_planning_evidence.html`), with their words in `phrasing.PHRASES` (`record.*`) so a younger reader gets the same facts in plainer words (#129 restored this after the two had drifted apart). This interaction contract holds regardless of which page hosts the card — it moved from the standalone Reconcile page onto the Questions page and each kid's work page (see Notes) without changing.

## Success metrics

- Pressing Enter in the flag-reason field never submits a destructive default flag; it either resaves the current flag or, with no flag set, submits nothing (`tests/test_reconcile_traps.py::test_enter_on_an_unflagged_item_submits_nothing`, `::test_enter_on_a_flagged_item_resaves_its_current_flag`).
- The current flag, its date and its reason are visible on a plain `GET` of the item, not only right after a save (`::test_the_flag_reason_shows_without_a_just_saved_message`).
- A card renders its title, cases and flag controls exactly once per view; no duplicate tab stops or dangling anchors.
- Evidence wording for one item is identical across every page that shows it, via one shared partial.

## Non-goals

- The underlying outcome/verdict classification (what counts as missing, late, decided, waiting) — that's [[actionable-work-model]].
- The bulk "let all N go" action and the Questions page's kind/answer filters — those are page-level Questions concerns, not the card's own interaction contract.
- Re-deciding which flags exist or what each one means.

## Notes

- **Naming caution:** the standalone "Reconcile" page these issues were filed against no longer exists under that name. `docs/superpowers/specs/2026-09-23-questions-not-cases-design.md` replaced it with **Questions** (`/questions`) plus a "Decided for you" / "Waiting" section on each kid's work page; `routes/reconcile.py` now only 308-redirects `/reconcile` to `/questions`, and `reconcile.html`/`_case_group.html` were deleted (spec §6.3, §7). The card-level interaction contract this doc describes (`_flag_menu.html`, `_item_detail.html`, `_planning_evidence.html`) survived that rename unchanged and is reused by the new pages — `_flag_menu.html` is explicitly kept "behind **More**" per the spec. This doc is filed under the triage-suggested slug `reconcile-page-interaction`; a maintainer may prefer to rename or fold it into a future Questions-page capability doc once one exists.
- #39 and #46 are also listed as closed by the Questions redesign itself (spec §9: "Closes #55, #39, #45, #46, ..."), which folded the duplicate-card problem into a one-card-per-item page structure and the evidence-table problem into `_planning_evidence.html` reuse — i.e., two of this cluster's issues were fixed by page redesign as much as by the card-level patches in #58.
- #58 ("Batch 2: Reconcile card interaction traps") is the PR that fixed #37, #38, #40 (focus-after-swap; not in this cluster) and #41 in one pass, with eight new regression tests, seven of which failed before the fix.

## Evidence

- Issues: #37 (Enter marks done), #38 (flag reason hidden on plain load), #39 (card renders twice, two flag forms, dangling anchor), #41 (follow up/ask teacher don't leave the page, no visible flag on the outer card), #46 (evidence table vocabulary diverges by page), #58 (batch PR fixing #37/#38/#40/#41)
- `fridgesheet/web/templates/_flag_menu.html`, `_item_detail.html`, `_planning_evidence.html`, `_record.html`, `_source_facts.html`, `_item_rows.html`; the answer vocabulary every one of them shows is `phrasing.FLAG_LABELS`
- `fridgesheet/web/routes/flags.py`, `fridgesheet/web/routes/kid.py`, `fridgesheet/web/routes/reconcile.py` (now a redirect only)
- `fridgesheet/web/stores/items.py`, `fridgesheet/web/stores/flags.py`
- `docs/superpowers/specs/2026-09-23-questions-not-cases-design.md` (§6.3 "The item detail", §7, §9 — the redesign that renamed the page and closed #39/#46)
- `tests/test_reconcile_traps.py` (the eight batch-2 regression tests)

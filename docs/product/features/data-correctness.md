---
slug: data-correctness
title: Data Correctness
state: live
parent: actionable-work-model
---

Every status, case and flag the app puts on screen is something Canvas or HAC actually recorded, never the app's own inference wearing the school's name.

## Problem

Fridge Sheet's whole promise is that a parent can trust one answer instead of reading two gradebooks. That promise breaks quietly: the classification is right in `outcomes.py` and wrong by the time it reaches a card, or two code paths look at the same item and disagree. A persona UX review on 2026-09-23 found four instances of exactly that failure, all in work the app had already classified correctly somewhere else. `status_text` returned "Missing" for any past-due unsubmitted item that was not `paper` — so in-class work got it — and never consulted HAC in the Canvas branch, while `_item_detail.html` printed that inference under a column headed **Says / Canvas**, attributing the app's guess to the school (#32). Reconcile's `paper_no_grade` case tested only Canvas's `state` and `score`, so a Concert Band item HAC had graded 18/25 read "In class work with no grade: ask" directly above a row reading `HAC · graded · 18/25`, and the same item was classified `DONE_OFFLINE` by `outcomes.classify` — opposite verdicts on one item, on one page (#33). `stale_flag` watched only Canvas, so a HAC grade posted after a parent flagged `ask teacher` never tripped it and the flag lingered until a human noticed; a flag already marked handled was filtered out of both Reconcile and the check-in queue even once the school's record had contradicted it, so the contradiction had nowhere to appear (#36). And `flag_set_at` was selected by the query but dropped by `ItemView`, so a flag could never say when it was set, while `set_flag`'s clear-and-reinsert meant re-saving a flag to fix a typo in its reason silently moved the "asked" date and the stale-flag baseline with it (#42). Each of these lets the app assert something neither source recorded — the one thing a parent cannot check without opening the gradebooks the app exists to replace.

## Target users

Everyone who reads a verdict rather than a raw source: the weeknight triager deciding what is genuinely open, the check-in pair working the Review-together queue, the student reading "Missing" next to work they handed to a teacher on paper, and the teacher-contact parent about to email a teacher on the strength of a flag date the app quietly reset.

## Desired outcome

A claim on screen is traceable to a source that made it. Where the app infers, it says so in its own voice; where it quotes, it quotes — "marked missing" only when Canvas set that flag, "no online submission (in-class)" when there is simply nothing to submit online, and a HAC score shown as the score it is rather than reduced to "Missing". Any code path that reaches a verdict consults both sources before speaking, so `cases()`, `actionable` and `outcomes.classify` cannot disagree about one item: a HAC score demotes `paper_no_grade` everywhere or nowhere. Contradiction is surfaced rather than filtered: a flag the school's record has since overtaken raises the stale-flag case whether the newer evidence came from Canvas or HAC, and reaches the parent on Reconcile *and* in the check-in's "Needs clarification" instead of being dropped by a `handled` filter on the way. The family's own annotations carry honest provenance — a flag's date survives an edit to its reason and is shown, so "asked the teacher" is a fact with a timestamp a parent can act on.

## Success metrics

- No two surfaces give opposite verdicts on the same item; the regression suite added with #57 (19 tests, each watched failing first) covers the crossings that produced these four bugs.
- No string attributed to a source ("Says: Canvas") reports something that source did not supply.
- Every case that fires consults both sources; none fires on a Canvas-only reading of an item HAC has settled.
- A flag the school's record has contradicted reaches the parent on both Reconcile and the check-in, not just one.
- Editing a flag's reason never moves its `set_at`.

## Non-goals

- Adding reconciliation cases or outcome categories — this capability keeps [[actionable-work-model]]'s existing decision table honest, it does not extend it.
- Guessing which source is right when Canvas and HAC genuinely disagree; the product surfaces the disagreement, as [[actionable-work-model]] already specifies.
- Wording, badge shape, filters and layout of the surfaces these verdicts appear on — [[all-work-table-ux]] owns how a verdict is *read*, this owns whether it is *true*.
- Writing anything back to Canvas or HAC.

## Notes

- The distinction against [[all-work-table-ux]] is worth holding onto, because the two clusters came out of the same review: that doc is about a true statement being unreadable, this one is about a readable statement being false. A fix that changes what the app concludes belongs here; a fix that changes how a conclusion is phrased or styled belongs there.
- #57's own description makes this a prerequisite rather than a peer: "Every later UI batch depends on the app stating only what the school's record supports." The four issues are closed and merged, so this doc records a standard already met, not work outstanding.
- The recurring shape is a derived or presentation-layer read of a *single* source in code that has two. Worth checking any new surface against, and worth watching as `ItemView` grows — #42's bug was a field the query already fetched and the view silently dropped.
- The code has moved since the four fixes landed: "Questions, not cases" (#59, #60) replaced `reconcile.cases()`/`with_cases` and the `_case_group.html` template with `fridgesheet/web/verdicts.py` and `_question.html`. The two-source rule survived the move intact — `verdicts._stale_change` still takes both the Canvas and HAC observations — which is the evidence that this standard held through a rewrite rather than being a one-off patch. Read the issue text below against the old names.
- Whether this deserves its own capability is a genuine open question: every file it touches belongs to [[actionable-work-model]], and this could reasonably be a section of that doc rather than a child of it. It is filed separately because the failure mode recurs across surfaces and earns its own metrics, but a maintainer folding it back in would not be wrong. `parent: actionable-work-model` is also a forward reference — that doc is not on `main` yet; it is pending in the initial-map PR #17, alongside another draft of this same capability. Reconciling the two is a maintainer's call, which is why this carries `hold:human`.

## Evidence

- Driving issues: #32 (`status_text` invents "Missing" for in-class work and the detail card attributes it to Canvas), #33 (`paper_no_grade` ignores the HAC score), #36 (`stale_flag` only watches Canvas; handled-but-stale flags never reach the check-in), #42 (`flag_set_at` never rendered, and re-saving a flag resets it) — all from the persona UX review of 2026-09-23.
- Landed on `main` as PR #57, "Batch 1: stop the app contradicting its own evidence (#32, #33, #36, #42)"; the check-in's skip-and-group decision moved into `queue_for()` in that PR so it could be tested without rendering a page.
- Current owners of the rule, on `main`: `fridgesheet/web/verdicts.py` (`verdict`, `_stale_change`, `_scores`, `_waiting_or_status`), `fridgesheet/web/outcomes.py` (`classify`), `fridgesheet/web/stores/items.py` (`status_text`, `ItemView`, `grade_text`, `grade_source`), `fridgesheet/web/stores/flags.py` (`set_flag`), `fridgesheet/web/routes/checkin.py` (`queue_for`), `fridgesheet/web/reconcile.py` (`open_sources`, `is_actionable`, `live_items`)
- `fridgesheet/web/templates/_item_detail.html`, `_item_rows.html`, `_flag_menu.html`, `_planning_evidence.html`, `_question.html`, `_verdict_sections.html`
- `docs/outcomes.md` — the canonical decision table these surfaces are measured against
- `tests/test_flag_set_at.py`, `tests/test_checkin_queue.py`, `tests/test_reconcile_traps.py`, `tests/test_verdicts.py`, `tests/test_web_outcomes.py`

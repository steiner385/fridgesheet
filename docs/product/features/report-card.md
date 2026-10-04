---
slug: report-card
title: Report Card & the Account of an Average
state: live
parent: actionable-work-model
---

A kid or a parent can read every class's grade the way the paper report card reads, and see in one sentence how the gradebook arrived at it, instead of taking a number on faith.

## Problem

HAC shows a marking-period average and Canvas shows a current score, and neither says what the number is made of. A family cannot tell whether a 70.88 is a weak test or three blank rows counted as zero, whether the two gradebooks are measuring the same thing, or whether the number the app shows is even consistent with the rows it lists. The next capability, guidance on what would move a grade, has nowhere to stand without that account.

## Target users

The kid reading their own grades (in their reading tier), and the parent checking a class or printing the page for the fridge.

## Desired outcome

**Report card** (`/kids/{key}/report-card`, a fourth tab beside Plan, Assignments and Check-in) lists every class on one line: the official average (the family's chosen gradebook, HAC unless changed), a letter from a configurable scale (`[grading]` in config.toml, ten-point by default), whose number it is and when it last changed, and one sentence on how it is figured. **How it's figured** on the class page shows HAC's category subtotals with each category's share of the grade, the total, and whether it adds up to HAC's number; Canvas's part says what its current score counts and what its final would be if missing work stays missing.

Underneath, one pure module (`fridgesheet/grading.py`) builds an *account* of each average from the gradebook's own subtotal rows and the class's assignment rows, rebuilds the total, and checks it against the reported number. The household's data showed HAC's average to be straight total points in every class whose subtotals it exposed (thirteen of thirteen on 2026-10-03), so the account checks that on every class rather than asserting it; where HAC shows no category table, or the rebuild disagrees, the page says so in plain words rather than inventing weights. HAC's subtotals are stored per refresh (`category_observations`, written when the set changes) and each gradebook's category for every item is kept (`item_categories`), so later features can say what a row is worth. The MCP `grades()` tool and the doctor's `averages` probe carry the same account.

**What moves it** (2026-10-04, spec `docs/superpowers/specs/2026-10-04-what-moves-the-grade-design.md`). One pure engine (`fridgesheet/guidance.py`) turns the account and the class's open rows into levers of three kinds (blank work HAC already counts as zero, overdue work still inside the late window that is not counted yet, posted work not yet due) with their worth in average points, the reach to the next letter and the slack under the current one, from posted work only and never extrapolated. The report card line gains a second sentence naming the best move and the reach; the class page gains a "What moves it" section listing the levers as planner lines with worth badges; every Must-finish row carries its worth as a badge, annotated only. Late credit follows the family's late rule (full unless it names a percentage); a row past its deadline or answered Too late or Let it go is not a lever. Nothing says an average point where the account does not read "exact": there it is points, not average points. The MCP `grades()` tool carries the same `guidance`.

## Success metrics

- Every class with HAC subtotal rows reads "Adds up" on the report card when HAC's number equals the straight-points rebuild to the hundredth; a class that does not reads the honest sentence, never a fabricated weight.
- The report card renders the same lines in every reading tier; only the words change.
- The doctor's `averages` line names any class whose breakdown is missing or off, so a scraper regression is visible before a family notices.

## Non-goals

- Guidance: what would move the number and by how much (the next suite; `share`, `zero_points`, `missing` and `final` are stored and exposed for it).
- Category weights entered by the family, past marking periods, a Settings field for the letter scale, and the scraper gap behind the classes that show no category table.

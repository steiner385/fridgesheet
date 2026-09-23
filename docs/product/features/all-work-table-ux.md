---
slug: all-work-table-ux
title: All-Work Table
state: live
parent: browser-app
links:
  - kind: powered_by
    feature: actionable-work-model
---

One kid's whole workload reads as a single scannable table, where every badge says whose verdict it is, every cell says what it means, and the filters ask their question in a parent's words — on a laptop, on a phone, and at 200% zoom.

## Problem

The Kid page's all-work table is where a parent actually triages on a weeknight and where a kid reads about their own work, and it was speaking the app's internal vocabulary rather than the family's. Four different kinds of badge — the app's `actionable` marker, the family's own flag, the note count, and reconcile case kinds — all rendered as near-identical grey pills, so a row reading "follow up / one source / stale flag / actionable" gave no way to tell your verdict from the app's, and `stale flag` sat next to the very flag it contradicted. `actionable` fired on every row under the default `show=open`, so it discriminated nothing, while `late_until` and `credit` — the real deadline it stood for — were computed and never rendered. A `—` under a "Handed in" header meant both "HAC-only, not tracked" and "nothing to submit online", which a kid reads as "no", and the Grade cell showed `0/20` without naming which gradebook said so. Six dropdowns printed raw enum values (`marked`, `handled`, `any flag`) explained nowhere in the UI, offered no way to ask for "everything I emailed about", and silently forced `show=all` when an Outcome was picked. At 200% zoom or on a phone the table scrolled sideways with no affordance and the only two signals a triager needs — Grade and Sources — went off-screen; sorting dropped keyboard focus to `<body>`; and an empty detail row after every item doubled screen-reader row counts.

## Target users

The weeknight triager scanning every open item for one kid; the kid reading their own row, for whom app jargon lands as an accusation; a second caregiver at 200% zoom or on a phone, for whom the sideways scroll was a blocker; the teacher-contact parent who wants "everything I emailed about" to be one move rather than a mental filter.

## Desired outcome

The table distinguishes, visually and in words, between what the school's records say, what the app concluded, and what the family decided — the same three-layer separation [[check-in-planning]] makes explicit, carried into a dense table. Badges are typed rather than uniformly grey, and the family's own flag is attributed to them with its date. Where the app had a jargon marker it now shows the fact behind it: the credit deadline instead of `actionable`, the kind of work ("on paper", "in class") or "not tracked" instead of a bare dash, and the gradebook name next to a grade. Filters read as questions a parent would ask — one primary Show control plus Class, with Which gradebook / Kind of work / Your answer / What the app says / Outcome folded behind **More filters** — every value carrying a human label, and any filter that widens the row set saying so rather than silently overriding it. The table survives a phone and 200% zoom: it wraps or reflows rather than hiding its most load-bearing columns, sortable headers carry `aria-sort` and stable ids so keyboard focus returns after an htmx swap, detail rows are `hidden` until opened and toggle `aria-expanded`, row-count changes are announced, and small text and interactive borders clear a readable contrast and size floor.

## Success metrics

- No badge in a row is ambiguous about who said it: the family's flag, the app's verdict, and the school's record are separable at a glance without opening the detail.
- No marker appears on essentially every row under the default filter; anything shown discriminates between rows or is replaced by the fact it stood for.
- Every filter value visible in the UI is a phrase a parent would say, not an enum member, and no filter changes the row set without saying so in the status line.
- The table is usable at 200% zoom and at phone width without Grade or Sources becoming unreachable.
- Sorting by keyboard returns focus to the header that was activated; screen-reader row counts match visible rows.
- This table and the check-in page describe the same item in the same words.

## Non-goals

- Changing what [[actionable-work-model]] decides — this capability governs how the outcome, flags and reconcile cases are *read*, never what they classify.
- A separate kid-facing view or login; the age-appropriate typography and contrast tiers already vary this surface by grade, within the single-user model [[credential-security]] describes.
- Restyling the rest of the app; the Reconcile card and Dashboard share vocabulary with this table but are covered by their own capabilities.

## Notes

- The driving cluster came out of a single persona UX review on 2026-09-23 that walked five personas (weeknight triager, check-in pair, student, secondary caregiver, teacher-contact parent) across the Reconcile card and this table — the same persona-driven verification bar [[check-in-planning]] records. All five issues are closed and the work is on `main`.
- The vocabulary fix is the load-bearing one: these issues are mostly not layout bugs, they are the app using internal names (`actionable`, `marked`, `handled`, case kinds) in front of a child. Future work on this table should be judged first on whether a twelve-year-old reading their own row would understand it.
- Accessibility here is not a separate track: the 200%-zoom overflow was a blocker for a real caregiver, so contrast, target size, focus management and reflow belong to this capability rather than to a generic audit.

## Evidence

- Driving issues: #49 (four badge types share one shape), #50 (`actionable` on every row; show the credit deadline), #51 (`—` means two things; Grade never names its source), #52 (six dropdowns with internal enum names; Outcome silently forces `show=all`), #53 (overflow, lost sort focus, empty detail rows, unlabeled arrows, low-contrast borders)
- `fridgesheet/web/templates/_item_rows.html` (sortable headers, badges, detail rows), `fridgesheet/web/templates/kid.html` (filter controls, **More filters**), `fridgesheet/web/templates/_item_detail.html`
- `fridgesheet/web/stores/items.py` (`ItemView`, `handed_in_text`, `grade_text`, `late_until`, `credit`, `FLAGGED`, `_keep`, `OUTCOME_LABELS`), `fridgesheet/web/routes/kid.py`, `fridgesheet/web/reconcile.py`
- `fridgesheet/web/static/app.css` (`--muted`, `--rule`, `.sr-only`, `.badge`, `.rel`, `.at`, overflow and tier variables), `fridgesheet/web/static/app.js` (htmx afterSwap focus and detail handling)
- Landed on `main` via "Accessibility: announcements, labelled controls, foldable detail rows, readable contrast" (#63), "Tabs say what they're for, filters for one answer or verdict, red only for the school's not-done" (#65), and "Evidence and notes: Canvas link and history, notes that reach the check-in, grades that name their gradebook" (#66); preceded by "Questions, not cases" (#59, #60) and "Stop the app contradicting its own evidence" (#57)
- `tests/test_web_kid_table.py`, `tests/test_web_kid_questions.py`, `tests/test_reconcile_traps.py`

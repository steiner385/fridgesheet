---
slug: actionable-work-model
title: Outcome Reconciliation & Actionable Work
state: live
links:
  - kind: powered_by
    feature: canvas-hac-ingestion
---

Every assignment either source has mentioned gets exactly one settled outcome, so a parent gets a single, trustworthy answer to "what did my kid actually miss" instead of two disagreeing gradebooks.

## Problem

Canvas's "Missing" flag is not a fact — it is only set when a teacher clicks it, or a course's late policy auto-applies it to past-due *online* work; it is never set for paper or in-class work, and many teachers just enter a 0. On one real measured day, Canvas's dashboard said 4 missing while the two gradebooks actually held 11 not-done (4 flagged, 6 zeros, 1 unflagged unsubmitted item) plus 8 unknown paper items with no grade anywhere. Reading either source alone, or naively, misleads a parent about what their kid actually needs to do.

## Target users

The parent household triaging what's open for each kid, every school day; downstream consumers ([[printed-reports]], [[check-in-planning]], the Dashboard/Kid/Reconcile pages) that all need one authoritative answer rather than re-deriving it.

## Desired outcome

One ordered table of outcomes (excused, unpublished, not done, late, on time, done on paper, unknown, not due yet) decides, deterministically and in one place (`fridgesheet/web/outcomes.py`), what happened to every assignment either source has mentioned — the same table whether it's read from the Dashboard, the Kid page, Trends, or the printed sheet. A teacher's 0 counts as not done on purpose; paper work with a grade is never counted as "missing" even though Canvas lists it as unsubmitted forever. Reconciliation surfaces the cases the two sources can't settle on their own (disagreement, one-source-only, ungraded-but-submitted, paper-with-no-grade, past the late-work credit window, or a stale parent flag) so a parent can act, annotate with a flag (`done`, `excused`, `ignore`, `follow_up`, `ask_teacher`) or note, and have that annotation flow into every report and the printed sheet.

## Success metrics

- Outcome classification matches `docs/outcomes.md`'s decision table exactly; if code and doc ever disagree, the doc says the code is wrong.
- The "unknown" bucket (paper work nobody has graded) is small and shrinks as parents flag/ask teachers, rather than silently growing.
- Flags set in the browser are reflected in the next scheduled/printed sheet without any extra step.
- Items that fail Canvas↔HAC pairing (double-counted) are rare (tracked via `matching.same_item`'s fallback heuristic).

## Non-goals

- Any write-back of a flag or note to Canvas or HAC — flags are Fridge Sheet's own record, layered next to the sources, never sent back to them.
- Automatically resolving "unknown" outcomes — the product's job is to surface them, not guess.

## Notes

- `late-rules.toml` (per kid/class `late_days`/`until`/`credit`, first match wins) decides whether "not done" or "unknown" work is still "actionable" (inside its credit window) versus merely a historical record.
- The Canvas-vs-HAC authority split is explicit and load-bearing: HAC is the gradebook of record (marking-period average, plus ~30+ assignments per kid Canvas never has); Canvas is the only source that knows submission timing, lateness, and explicit missing/excused marks.
- PR #13 ("web: an Open work page") brings this same actionable list to the browser (`/open`, sections "Still fixable" / "Coming due") using the shared `AppState.days_ahead` setting that the Dashboard, Kid page and printed sheet already use — not yet merged as of this writing.
- [[trends-and-changes]] and [[check-in-planning]] are both direct consumers of this outcome model, not independent sources of truth.

## Evidence

- `fridgesheet/web/outcomes.py`, `fridgesheet/web/reconcile.py`, `fridgesheet/late_rules.py`, `fridgesheet/open_items.py`
- `fridgesheet/web/stores/flags.py`, `fridgesheet/web/stores/notes.py`, `fridgesheet/web/routes/flags.py`, `fridgesheet/web/routes/notes.py`, `fridgesheet/web/routes/reconcile.py`, `fridgesheet/web/routes/kid.py`, `fridgesheet/web/routes/dashboard.py`
- DB tables `notes`, `flags` in `fridgesheet/web/db.py`
- `docs/outcomes.md` (the canonical decision table)
- MCP tool `missing_work()` in `fridgesheet/server.py`
- GitHub issue #2 ("Plan A follow-ups... data layer residuals"), PR #13 ("web: an Open work page")
- `tests/test_reconcile.py`, `tests/test_open_items.py`, `tests/test_late_rules.py`, `tests/test_web_outcomes.py`, `tests/test_web_reconcile_bulk.py`, `tests/test_web_open_sources.py`

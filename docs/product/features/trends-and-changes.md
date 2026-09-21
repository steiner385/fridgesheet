---
slug: trends-and-changes
title: Trends & Changes History
state: live
parent: actionable-work-model
---

A parent can see how a kid's grades and work habits are moving over the school year, and catch up on everything that changed since they last looked, instead of only ever seeing a snapshot of "right now."

## Problem

A point-in-time outcome list answers "what's open today" but not "is this getting better or worse," "what happened while I was traveling last week," or "how long has this one item been sitting open." Those questions need history, and the product only started keeping history once refreshes began being ingested into a database rather than overwriting one JSON file.

## Target users

A parent checking in periodically rather than daily; either parent catching up after being away; anyone deciding whether a pattern (a class sliding, a string of lates) is worth a conversation with the kid or the teacher.

## Desired outcome

**Changes** is a feed of everything that moved since a chosen moment — new items, grades posted, items cleared, flags set — "what happened while I wasn't looking." **Trends** plots grade lines per class (HAC average, Canvas current) and weekly missing/late/on-time counts, computed from the same settled-outcome numbers as the Dashboard card, spread over the calendar by due week (not refresh week, so the chart reads correctly from day one of the year); it also lists what has sat open longest. Both read from the append-only observation history ([[canvas-hac-ingestion]]'s `item_observations`/`grade_observations` tables), not from a live re-derivation.

## Success metrics

- Trends' "on-time hand-ins" rate and weekly counts reconcile exactly with the Dashboard's per-kid settled-outcome counts for the same period.
- The Changes feed never misses an actual change (a write to `item_observations`/`grade_observations`/`flags` that differs from the prior value) and never fabricates a change when nothing differed.
- Charts render correctly from the first day of the school year, not just from whenever ingestion happened to start.

## Non-goals

- Predictive analytics or grade forecasting — Trends shows what happened, not a projection.
- Editing history — Changes and Trends are read-only views over the observation log.

## Notes

- "Done on paper" outcomes are deliberately excluded from the on-time rate (timing is unknowable), and "unknown" outcomes are excluded too (nothing is known yet) — see [[actionable-work-model]] for why.
- GitHub issue #5 ("Plan C follow-ups (Changes and Trends)") tracks residual gaps from the initial delivery.

## Evidence

- `fridgesheet/web/routes/changes.py`, `fridgesheet/web/routes/trends.py`, `fridgesheet/web/stores/changes.py`, `fridgesheet/web/stores/trends.py`
- DB tables `item_observations`, `grade_observations` (append-on-change history)
- `docs/outcomes.md` §"Where each outcome shows up" (Trends rows)
- GitHub issue #5
- `tests/test_web_changes_page.py`, `tests/test_web_changes_store.py`, `tests/test_web_trends_page.py`, `tests/test_web_trends_store.py`

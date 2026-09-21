---
slug: check-in-planning
title: Parent–Child Check-In & Planning
state: delivering
links:
  - kind: powered_by
    feature: actionable-work-model
---

A parent and kid can turn the raw list of open school work into a short, recorded conversation that ends in a concrete, owned plan, without ever overwriting what the school actually reported.

## Problem

An outcome list (missing, late, unknown, actionable) tells a parent what happened, but not what the family decided to do about it. Today that conversation happens informally and leaves no record: no memory of what was agreed last time, no way to tell "still open because nobody looked" from "open because we agreed to tackle it Thursday," and no easy way to keep the school's facts, the family's account of what happened, and the agreed next step from getting tangled together.

## Target users

The parent and kid together, at a recurring check-in; a second caregiver who needs to see the same plan without re-litigating it; a household with more than one kid, where each kid's plan and evidence must stay isolated from the others.

## Desired outcome

A per-kid check-in workspace (`/kids/<kid>/check-in`) that separates three layers and never lets one silently overwrite another: read-only school evidence (Canvas/HAC facts via [[actionable-work-model]]), the family's own account of what happened, and an agreed next step (owner, day, effort, and when to look again). A review queue groups items into *Work to consider*, *Needs clarification*, and *Submitted — waiting for a grade*; finishing a check-in records a time budget, the next check-in date, and who recorded it, and snapshots the plan so later edits are visible as "edited since" / "added since" that check-in. A read-only plan view (`/kids/<kid>/plan`) and a standalone print view (`/plan/print`) let the plan be shared or posted without exposing the full work queue.

## Success metrics

- A check-in can be finished and later re-opened without ever silently discarding a step the family recorded.
- Concurrent edits (e.g., two devices, or a revision conflict) surface a 409 with what was saved meanwhile, rather than clobbering one caregiver's typed words.
- Steps survive a refresh, and "school evidence changed" is judged by comparing facts, not by refresh id, so an unrelated refresh doesn't spuriously mark a step stale.
- Sibling data (evidence, steps, plans) never leaks across kids, including for shared Canvas ids or replayed requests.

## Non-goals

- Writing observations or flags back into the outcome model — completing a step returns the assignment to the review queue; it does not alter [[actionable-work-model]]'s record.
- A kid-facing login or separate kid identity — this is still a single-user, parent-operated app per [[credential-security]]'s security model.

## Notes

- This finishes a work-in-progress checkpoint (`docs/handoffs/2026-09-19-persona-ui-redesign.md`, from a separate rebased branch) rather than starting from nothing.
- Verification included five synthetic "persona" agents (busy parent, teenager, overwhelmed 12-year-old, second caregiver, security-minded multi-child parent) driving the workspace with Playwright at desktop and mobile/touch viewports plus print media — an unusually heavy verification bar for a single PR, reflecting how easy this kind of feature is to get subtly wrong for the people who'll actually use it.
- Ships as a schema bump (`schema_version` 1 → 2, adding `plan_steps` and `checkins` tables) with tested migration of an already-populated database.
- Not yet merged as of this writing (PR #12) — the routes and tables described here do not exist on `main` yet.

## Evidence

- PR #12 ("Check-in: a parent–child conversation that ends in an owned plan"), branch `ccswitch/main-7d3e2ecc`
- Planned routes: `/kids/<kid>/check-in`, `/kids/<kid>/plan`, `/kids/<kid>/plan/print`, `/kids/<kid>/check-in/step`
- Planned DB tables: `plan_steps`, `checkins` (schema version 2)
- `docs/handoffs/2026-09-19-persona-ui-redesign.md` (status, verification record, deliberate omissions)
- Planned test file: `tests/test_web_checkin.py` (36 tests per the PR description)

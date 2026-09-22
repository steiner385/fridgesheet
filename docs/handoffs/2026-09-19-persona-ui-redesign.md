# Fridge Sheet persona-driven UI redesign — status and continuation

## Goal and authorization

The user asked to think through personas, use cases, missing features and UI organization,
especially a parent–child conversation that turns open/missing/late assignments into an
actionable plan, and explicitly requested persona agents. A first session delivered
recommendations; a second implemented a work-in-progress checkpoint (`5fd6360`, on top of
0.3.1) and wrote this handoff; a third (2026-09-19) rebased that checkpoint onto the
Fridge Sheet rename (0.4.1), reviewed and finished the slice, tested it, ran five persona
sessions against it, fixed what they found, and opened the PR. Nothing has been merged or
deployed.

Repository: `steiner385/fridgesheet`. Branch: `ccswitch/main-92a2bc39` (the earlier
`ccswitch/main-7d3e2ecc` is the pre-rebase checkpoint and can be deleted once the PR merges).

## Product direction

Make the primary job a short parent–child check-in that ends with a feasible, owned plan.
Persona agents represented a busy parent, an autonomy-seeking teenager, an overwhelmed
student, a second caregiver/tutor, and a parent managing multiple children. These are
simulated perspectives, not user research.

Three independent layers, never written by one another:

1. School evidence: Canvas/HAC submission, grade, missing flag, due date, uncertainty.
2. Family account: "I handed this in Tuesday", "wrong file uploaded", "need help starting".
3. Agreed next action: concrete step, owner, planned day, rough effort, follow-up date.

Critical persona cases and where they now live:

- A zero is not proof of no work: `_planning_evidence.html` keeps the submission and the zero
  together and says a zero can mean not graded yet, not handed in, or on paper. The outcome
  contract (`docs/outcomes.md`, zeros are `not_done` on Today and All work) is unchanged.
- Submitted but ungraded goes to *Submitted · waiting for a grade* and its form opens with
  Waiting preselected (`routes/checkin.py:_group`, `?state=waiting`).
- Paper hand-ins, HAC-only rows and disagreements land in *Needs clarification* with a
  sentence saying what there is to clarify.
- Completing a step never marks an assignment submitted; the assignment returns to review
  with a note of the completed steps already taken on it.
- Upcoming work and undated HAC rows are reviewable even when nothing is missing.
- A late-credit cutoff is shown as "usually accepted until … ask the teacher if you need
  longer"; work past it sorts after work that can still earn credit but stays visible.
- Family commitments survive refreshes and dropped source records (`tests/test_web_checkin.py`
  refresh tests); the "school evidence changed" notice compares facts, not refresh ids.
- Siblings are isolated server-side, including shared Canvas ids and replayed request keys.
- Caregiver handoff: steps and agreements carry a free-text "recorded by", created/edited
  timestamps, and an *agreed at / edited since / added since* badge against the last check-in.

## What is implemented (this PR)

- `web/db.py`: schema 2 adds `plan_steps` (with `created_by`, `recorded_by`) and `checkins`.
  Migration from a populated schema-1 file, and from a file still under the pre-rename file name, is tested.
- `web/stores/plans.py`: steps, request-key deduplication, revision conflicts, delete,
  immutable check-in snapshots, today's load and last check-in per child (for Today).
- `web/routes/checkin.py`: check-in, plan, standalone print page, step form (new / manual /
  edit), delete, finish. Plain validation messages that keep typed values; unparsable ids are
  404 pages; the 409 conflict page shows what was saved meanwhile and lets one more Save apply
  the reader's words.
- Templates: `checkin.html`, `plan_step.html`, `plan_print.html`, `_child_nav.html`,
  `_planning_evidence.html`; Today card shows next check-in / check-in due and today's load.
  CSS: responsive layout, 44px touch targets on the new pages, print rules. JS: explicit
  print, one confirm for delete.
- Tests: `tests/test_web_checkin.py` (36 tests) and three migration/schema tests in
  `tests/test_web_db.py`. Two old assertions updated (schema version; rail links).
- README: "Check-in" paragraph under *The browser app*.

## Validation state

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
env -u PYTHONPATH .venv/bin/python -m pytest -q      # 746 passed, 1 skipped
```

`PYTHONPATH` must be unset if the shell exports one that carries another `tests` package.

Browser checks (Playwright, Chrome, 1280×800 and 390×844 touch, print media) were run by the
five persona agents against the checkpoint and again by the session against the fixed code:
no horizontal overflow, focus visible, labelled controls, one-page print for a six-step plan,
sibling text absent from print, tampered ids 404. Physical printing and Firefox/Safari native
validation were not exercised.

## Known gaps and review questions (deliberately not in this PR)

- Today and All work still call a Canvas-missing item with a HAC score "not done" / "Handed
  in: No · Grade: Missing"; the Reconcile reason for past-credit work still says "No longer
  earns credit". Changing those means changing the outcome contract and its tests.
- No "since last check-in" delta of school changes; `/changes` has fixed windows.
- The step form's title can drift from the linked assignment; duplicate active steps for one
  item are allowed.
- Retrying a saved form with changed content answers "Saved" but keeps the first version
  (request-key deduplication). Request keys are client-chosen; the first writer owns one.
- No teacher-extension override, no per-source fetch timestamps, no separate Progress view,
  no reorganized administration, no remote caregiver sharing.
- The browser's native date widget accepts a wrong date typed day-first without complaint.
- The evidence-changed notice clears only when the step is re-saved.

## Continuation checklist

1. Review the PR; merging is the user's call. Delete `ccswitch/main-7d3e2ecc` afterwards.
2. If the outcome-contract wording is to change, do it in `outcomes.py` / `docs/outcomes.md`
   with its own tests, not in the check-in templates.
3. Consider a "since last check-in" summary above the plan: school changes since
   `checkins.finished_at`, plus steps added / edited / completed with their `recorded_by`.

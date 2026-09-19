# Fridgesheet persona-driven UI redesign — continuation handoff

## Goal and authorization

The user originally asked to think through personas, use cases, missing features, and UI organization, especially a parent–child conversation that turns open/missing/late assignments into an actionable plan. They explicitly requested persona agents. The first session delivered recommendations only and was automatically archived. The user restored it and said “keep going. dont stop”; implementation then began. They subsequently requested committing/pushing everything and a prompt to continue in a new session. This is a work-in-progress checkpoint, not a finished redesign. No PR has been opened in this session.

Repository: `steiner385/fridgesheet`
Branch: `ccswitch/main-7d3e2ecc`
Original base commit: `ac56d24` (`Fridge Sheet 0.3.1`).

## Product direction

Make the primary job a short parent–child check-in that ends with a feasible, owned plan. Persona agents represented a busy parent, autonomy-seeking teenager, overwhelmed student, second caregiver/tutor, and parent managing multiple children. These are simulated perspectives, not user research.

Keep three independent layers:

1. School evidence: Canvas/HAC submission, grade, missing flag, due date, and uncertainty.
2. Child/family account: “I handed this in Tuesday,” “wrong file uploaded,” “need help starting.”
3. Agreed next action: concrete step, owner, planned day, rough effort, and follow-up date.

Suggested flow: acknowledge progress → hear context → separate work/clarification/waiting → choose realistic steps → save and print agreement, including adult commitments and next check-in.

Critical persona cases:

- Zero recorded is not sufficient conversational evidence that a child did no work. Preserve submission and zero facts together. The existing outcome contract deliberately treats zeros as `not_done`; the new workspace uses factual language without globally changing that contract.
- Submitted but ungraded belongs in Waiting, not automatically redo-work.
- Paper hand-in, stale/conflicting sources, and a teacher extension need room for explanation.
- Finishing a small step does not establish submission or complete an assignment.
- Upcoming work and long projects matter even when no work is missing.
- A configured late-credit cutoff is not proof that an individual exception is impossible.
- Family commitments survive school refreshes and disappearing source records.
- Siblings must be isolated server-side, including shared source IDs.
- Caregiver handoff needs ownership, dates, and durable agreements; existing mutually exclusive flags and unauthored notes do not provide this alone.

Longer-term navigation proposal: Today, child workspaces (Check-in / Plan / All work / Progress), Progress, Print & reports; move administration out of daily workflow. Only part of this is implemented.

## Current implementation

- `web/db.py`: schema version 2 migration adds `plan_steps` and `checkins`.
- `web/stores/plans.py`: independent family commitments, optional school-item linkage, manual tasks, owner/date/effort/order, planned/waiting/blocked/done states, revision-based edit conflict detection, request-key deduplication, evidence fingerprint, immutable check-in plan snapshots.
- `web/routes/checkin.py`: child check-in, plan, browser-print view, create/edit step form, finish-check-in routes. Review queue includes upcoming/open work and submitted/ungraded work. Existing active commitments move out of the review queue. Completed steps return unfinished assignments to review.
- Templates: `checkin.html`, `plan_step.html`, `plan_print.html`, `_child_nav.html`, `_planning_evidence.html`.
- Dashboard now offers Start check-in / Open plan; historical school record is collapsed. Rail child links go to check-in. Existing `/kids/{key}` remains the original filtered assignment table with child navigation. Item details link to next-step creation.
- CSS adds responsive check-in/plan layout, form styles, explicit focus outlines, and print styles. JS adds explicit browser printing.

No live school data or credentials were needed. No production database was migrated by this session. No dependency specification changes were made.

## Validation state

Local `.venv` was created and dependencies installed with:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

The system `python3` initially could not collect the suite due to missing `segno` and `reportlab`; use `.venv/bin/python`. `.venv` is ignored and is not pushed.

Most recent full suite: **681 passed, 2 failed, 1 skipped** (37.09 seconds).

Failures:

1. `tests/test_doctor.py::test_database_probe_reports_counts` hardcodes `schema 1`; new schema is 2. Update expectation using `db.SCHEMA_VERSION` if consistent with intended migration.
2. `tests/test_web_app.py::test_header_shows_refresh_time_source_health_and_last_run` expects rail `href="/kids/Alex"`; new rail links to `/kids/Alex/check-in`. Update the intended navigation assertion while retaining coverage of existing All work URLs.

`git diff --check` passed before the checkpoint.

**No dedicated new-workflow tests or browser checks have been written/run.** The existing suite does not establish that the new pages/forms work. Do not report the feature as verified.

## Recommended continuation

1. Read the current diff and repository instructions. Review new code before expanding scope.
2. Add meaningful tests using `tests/web_fixtures.py` (`seed`, `snapshot`, `app_for`, frozen `NOW`):
   - Render each new route and test real form POSTs, reload, edit, and validation errors retaining input.
   - Create a waiting step on missing work, ingest a fresh snapshot, verify family account/commitment survive and school facts/flags are not overwritten.
   - Evidence-change indication should react to fact changes, not merely a new refresh ID.
   - Upcoming work, paper unknowns, submitted/ungraded work, zero plus submission, closed late window, missing due date, empty child, and removed school item.
   - Step completion must not mark an assignment submitted; adding a subsequent submission step remains possible.
   - Reject cross-child item IDs and step IDs; hidden/missing children are 404.
   - Repeated POST must not duplicate a step. Concurrent edits must not silently overwrite one another.
   - Migration from an actual populated schema-v1 database preserves notes, flags, items, and runs; migration is idempotent.
   - Print includes only the selected child's commitments/adult follow-ups, no unrelated inventory or editing controls.
   - Escape family text in screen, history, and print.
3. Fix the two old assertions where the new behavior is intended. Run relevant tests then full suite.
4. Launch with synthetic fixture data in a temporary app home and inspect desktop/mobile in Playwright. Exercise creating a task, editing Waiting/Blocked, finishing a check-in, reloading, and print media. Check keyboard labels, focus, clipping, navigation and HTTP errors.
5. Improve defects revealed by review/testing before adding more features.
6. Document the workflow in README and preserve explicit scope: this is a first implemented slice, not every earlier suggestion.
7. Commit/push fixes and prepare a reviewable PR when ready; do not merge or deploy as part of this checkpoint.

## Known rough edges / review questions

- Review queue sorting currently follows due dates; old past-credit work can dominate. Consider separating policy questions and prioritizing upcoming deadlines/credit cutoffs without hiding work.
- “Submitted · waiting for a grade” queue links to a form defaulting to planned work; consider a Waiting default for that context.
- The UI repeats header source-health warnings; it does not add reliable per-source fetch timestamps. Ingestion can carry older source data forward; never label the latest ingestion time as fresh source evidence.
- No “since last check-in” delta summary is implemented yet. Saved agreements/history exist.
- Time budget is captured on Finish check-in; current estimate compares against the last saved budget, not an interactive new budget. Review clarity for different dates.
- Print uses current active steps across planned dates plus the last agreement summary; consider whether users need a date selector and how to distinguish later edits from the saved agreement.
- `plan_steps` supports several steps per item but active-step cards only expose editing; adding another step is easiest via All work or after completing a step. Improve discoverability if appropriate.
- Family account is currently stored per step, not separately per assignment; assess consistency across multiple steps.
- Single-step edits have optimistic conflict detection; check-in finalization snapshots the server's current plan. Review simultaneous caregivers, token collision handling, and stale forms.
- Date/number validation may expose Python exception text. Make it understandable without losing entered values.
- Dedicated teacher-extension overrides, author identities, remote caregiver sharing, manual task matching, separate progress subview, and reorganized administration are not implemented.
- No automated contact with teachers or grade-impact predictions are implemented or intended for this slice.

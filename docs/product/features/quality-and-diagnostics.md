---
slug: quality-and-diagnostics
title: Quality, Diagnostics & CI
state: delivering
---

A parent (or the maintainer) can tell, in one place, whether Fridge Sheet is healthy right now, and every change to the product is checked against the same cross-platform test suite before it ships.

## Problem

This product's failure modes are unusually hard to see from the outside: a broken Chromium install, a locked keyring, a missing PDF engine, a printer that vanished, or a scheduler that silently stopped writing tasks would otherwise only be discovered by a missed sheet. Separately, the product is developed through large, plan-driven implementation passes that reliably leave small residual gaps (a wrong label, an untested edge case, a UI inconsistency) that need somewhere to be tracked and worked off systematically rather than forgotten.

## Target users

The end-user parent, via **Diagnostics**/`doctor` when something seems wrong; the maintainer, via CI on every push/PR and the standing backlog of audit and residual-cleanup issues.

## Desired outcome

`fridgesheet doctor` (and the browser's Diagnostics page, run on demand) checks Python, Chromium, the PDF engine, the credential store, printers, the scheduler and the web/database layer, and writes `<home>/doctor.txt`; any `FAIL` line is the actionable pointer. `.github/workflows/ci.yml` runs the full pytest suite on both `ubuntu-latest` and `windows-latest` on every push and PR, so an OS-specific assumption (a glibc-only `strftime` code, a POSIX-only path) cannot ship unnoticed — this is the gate `docs/release-checklist.md` explicitly tells a human not to re-verify by hand before a release. Beyond automated checks, the product runs periodic UI/UX audits (including multi-persona, real-browser passes) against the live app and tracks their findings, plus the residual follow-ups every large implementation plan leaves behind, as a standing, triaged issue backlog rather than letting them silently rot.

## Success metrics

- CI is green on both platforms before any tag is cut.
- Every `FAIL` line `doctor` can produce corresponds to a real, checkable condition (not a check that always passes or always fails).
- The audit/residual backlog (currently GitHub issues #2–#9, #11, #16) trends toward closed rather than growing indefinitely.

## Non-goals

- End-to-end monitoring or alerting of a live deployment — there is no live deployment; this is entirely local, on-demand or CI-triggered checking.
- Automatically fixing what diagnostics finds — `doctor` and the audits report; a human or a follow-up PR fixes.

## Notes

- This capability currently has the heaviest open-issue concentration in the backlog: nine of the eleven open issues (#2 through #9, plus #11) are plan-residual or audit findings, and PR #16 is mid-flight UI-audit work — reflecting a development process that ships in large plan-sized increments and then works off what each increment missed, rather than nine independent feature requests.
- `tests/test_packaging.py` is itself a quality gate for [[windows-packaging]] (pins the installer script's shape, the SumatraPDF version/hash, and that a temporary CI branch trigger never ships) — evidence that this capability's reach extends into the release pipeline, not just runtime health.

## Evidence

- `fridgesheet/doctor.py`, `fridgesheet/web/routes/diagnostics.py`
- CLI: `fridgesheet doctor`
- `.github/workflows/ci.yml`
- `docs/release-checklist.md` §0 ("What CI already proved — don't re-check these")
- GitHub issues #2, #3, #4, #5, #6, #7, #8, #9, #11; PR #16
- `tests/` (the suite as a whole), `tests/test_doctor.py`, `tests/test_web_diagnostics_page.py`, `tests/test_ui_audit_batch_a.py`, `tests/test_ui_audit_batch_b.py`, `tests/test_conftest_subprocess_guard.py`

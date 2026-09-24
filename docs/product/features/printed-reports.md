---
slug: printed-reports
title: Report Building, Printing & the Open-Work Sheet
state: live
links:
  - kind: powered_by
    feature: actionable-work-model
  - kind: powered_by
    feature: canvas-hac-ingestion
---

A parent gets a physical, letter-portrait, per-kid sheet of open school work on the fridge every school day, built and printed without anyone having to sit at a computer.

## Problem

Checking two web gradebooks every day is a chore nobody reliably does; a printed sheet on the fridge is what actually gets looked at by both parents and the kid, but building it by hand from two disagreeing sources, and remembering to print it, doesn't scale to a daily habit.

## Target users

The whole household — the sheet is explicitly designed to be read by parents and kids without needing to open a browser or log into anything.

## Desired outcome

`fridgesheet run <report-key>` (or its original alias `print-sheet`) refreshes if needed, builds one PDF (one letter-portrait section per kid, even a kid with nothing open), prints it two-sided via the OS's printer, and records the run — the same guard order every time: no-print-days, already-printed, print-window, stale-refresh fallback, build, archive copy, print, record. Each row shows what's new or changed since the previous sheet, due/assigned dates, course, assignment, points, source (Canvas/HAC/Both), how it's turned in, and a shouted status word (`MISSING`, `ZERO`, `LATE`, `PAPER — CHECK`, `HAC — NO GRADE`, `DUE TODAY/TOMORROW/<weekday>`). A report is a pluggable unit (the `Report` protocol) so a new report type is a module plus a registry entry, not a rewrite — the built-in `open-work` report and browser-built [[view-reports]] both flow through the same runner, archive, and run-history path.

## Success metrics

- A scheduled run prints (or correctly skips, with a stated reason) every school day without anyone touching a keyboard.
- A refresh failure never blocks printing if the last good snapshot is under 24 hours old — the sheet still prints, with a note.
- Preview/Print-now build from the last refresh by default (seconds, not minutes) rather than forcing a live pull every time a parent just wants to look.
- Run history (`fridgesheet reports`, the Runs page) accurately reflects what actually printed, was skipped, or failed, and why.

## Non-goals

- Any report that isn't built from the shared snapshot/database — no ad hoc data sources.
- Guaranteeing exact duplex output on a printer whose driver doesn't report duplex support (falls back to single-sided, by design).

## Notes

- "One pull, many tools": a scheduled print installed by the app itself runs with `--no-refresh`, deliberately not repeating a Canvas/HAC pull the refresh timer already did; a hand-typed `run`/`print-sheet` still refreshes first, since someone at a terminal is presumably fine waiting.
- PR #14 (merged 2026-09-20, "Print from the last refresh instead of pulling live every time") changed the browser app's Preview/Print-now default to reuse the last refresh instead of always pulling live, matching the CLI's "one pull, many tools" promise; a "Refresh data first" checkbox opts back into a live pull.
- Overdue rows beyond `--overdue-days` (14) or past the late-work credit window collapse into a one-line "Not shown" rather than growing the sheet forever.
- `sheet.py`'s table-rendering engine was generalized so the same PDF machinery serves both the bespoke open-work layout and [[view-reports]]' generic column/row reports.

## Evidence

- `fridgesheet/runner.py`, `fridgesheet/reports/base.py`, `fridgesheet/reports/__init__.py`, `fridgesheet/reports/open_work.py`, `fridgesheet/print_sheet.py`, `fridgesheet/sheet.py`, `fridgesheet/dates.py`
- CLI: `fridgesheet run`, `fridgesheet print-sheet`, `fridgesheet reports`
- Web: `fridgesheet/web/routes/runs.py`, `fridgesheet/web/stores/runs.py`, `fridgesheet/web/jobs.py`, DB table `runs`
- README.md §6 ("Printing a report on a schedule")
- PR #14 (merged), GitHub issue #9 ("Plan F residuals: ... a silent five-day schedule...")
- `tests/test_runner.py`, `tests/test_print_sheet.py`, `tests/test_sheet.py`, `tests/test_sheet_table.py`, `tests/test_reports.py`, `tests/test_web_jobs.py`

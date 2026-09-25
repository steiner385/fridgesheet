---
slug: report-scheduling
title: Report Scheduling (the server's own clock)
state: live
parent: printed-reports
---

Any report, code-defined or user-built, can be put on its own days-and-time schedule from either the CLI or the browser; it fires from inside the running server, once a minute, for as long as the server itself is up.

## Problem

A printed sheet is only useful if it prints itself. The OS scheduler this used to delegate to could not be trusted to do that: Task Scheduler only fires a task "when the user is logged on", and on the household's kiosk the app's own account never is — not one scheduled run ever happened. Scheduling has to work identically for the CLI-first Linux install and the GUI-first Windows install, survive a slot missed while the server was down without double-printing or silently losing it, and never let the app touch a schedule someone wrote by hand.

## Target users

A parent who wants "print itself every school day" set-and-forget, on either Linux or Windows; the household's own hand-written Linux timer, which the app never touches.

## Desired outcome

The server fires schedules itself, once a minute, from `config.toml` (`web/clock.py`, `schedule_plan.py`). A slot missed while the server was down is caught up once; a print caught up the next morning is refused by the runner's print window. Schedules run only while the server runs: on Windows the installer registers it; on Linux, `fridgesheet service install`.

The Schedules page (one row per report, built-in or saved) and `fridgesheet schedule show|remove <report>` only ever read or write `config.toml` — no systemd unit, no Task Scheduler task, so there is nothing for the app to clobber. The household's hand-written `fridgesheet-print-sheet.{service,timer}` and the always-on `fridgesheet-refresh.{service,timer}` stay safe by construction, not by a name check.

## Success metrics

- A schedule set on the Schedules page or in `config.toml` fires within a minute of its slot while the server is running, and is caught up once, not repeatedly, after the server was down.
- Saving a schedule, or `schedule remove`, never touches anything outside `config.toml`.
- Windows and Linux report identical outcomes for the same schedule definition — the clock that fires it is the same code on both platforms.

## Non-goals

- A schedule that fires while the server itself is not running — that is what the OS-native scheduler used to promise and could not deliver reliably; the always-on server ([[os-integration]]'s "service" concern) is what this now depends on instead.
- Detecting or reporting on a hand-written systemd unit from the Schedules page — the app no longer looks at the OS scheduler at all for a report's own schedule.

## Notes

- GitHub issue #7 ("D6 Schedules residuals: test-safety guard, delete refusals, key spellings") tracks known residual gaps that predate the in-app scheduler; some no longer apply now that the app never writes an OS unit for a report's schedule.
- The always-on server task/unit and the refresh-only pre-fetch timer (README §5) remain outside `config.toml` entirely — they are hand-written systemd units the app never reads, writes, or removes.
- `fridgesheet schedule remove --all` (what the Windows uninstaller runs) is the one place that still talks to the OS: it removes the Task Scheduler tasks and systemd timers an *earlier* version of this app registered, so upgrading from a release that used to write those leaves nothing behind.

## Evidence

- CLI: `fridgesheet schedule show|remove <report>`, `fridgesheet schedule remove --all`
- `fridgesheet/web/clock.py`, `fridgesheet/schedule_plan.py` (the clock and the plan it acts on)
- `fridgesheet/web/routes/schedules.py`, `fridgesheet/web/schedules.py` (the Schedules page, `config.toml` persistence only)
- `fridgesheet/web/db.py` `schedule_fires` table (schema 6, the last slot each schedule fired)
- `fridgesheet/host/scheduling.py`, `fridgesheet/host/scheduling_linux.py`, `fridgesheet/host/scheduling_windows.py` (leftover removal only)
- `systemd/fridgesheet-print-sheet.{service,timer}`, `systemd/fridgesheet-refresh.{service,timer}` (the hand-written units the app must never touch)
- README.md §6 ("Printing a report on a schedule")
- GitHub issue #7
- `tests/test_schedule_plan.py`, `tests/test_clock.py`, `tests/test_schedule_fires.py`, `tests/test_os_leftovers.py`, `tests/test_web_schedules.py`, `tests/test_web_schedules_page.py`

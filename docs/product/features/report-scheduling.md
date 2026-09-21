---
slug: report-scheduling
title: Report Scheduling (OS Timers & Tasks)
state: live
parent: printed-reports
---

Any report, code-defined or user-built, can be put on its own days-and-time schedule from either the CLI or the browser, and the schedule keeps running even if the browser app is closed.

## Problem

A printed sheet is only useful if it prints itself; scheduling has to survive the web server being down, work identically for the CLI-first Linux install and the GUI-first Windows install, and never let the app clobber a schedule someone wrote by hand.

## Target users

A parent who wants "print itself every school day" set-and-forget, on either Linux or Windows; the household's own hand-written Linux timer, which must never be touched by the app's own scheduling commands.

## Desired outcome

`fridgesheet schedule install|remove|show <report>` and the Schedules page (one row per report, built-in or saved) both write to `config.toml` and the platform's own scheduler: `~/.config/systemd/user/fridgesheet-<key>.{service,timer}` on Linux, a Task Scheduler task on Windows — the same underlying `host.scheduling.install/remove/describe` call either way. Every unit or task the app writes carries a `# Written by Fridge Sheet` marker; `install`/`remove` refuse outright, before touching anything, on a unit that lacks that marker — which is exactly how the household's hand-written `fridgesheet-print-sheet.{service,timer}` and the always-on `fridgesheet-refresh.{service,timer}` stay safe under any `schedule` command. For the built-in `open-work` report specifically, the app also recognizes the hand-written print timer by name and refuses to install or remove a conflicting schedule for it, to avoid ever printing the sheet twice or silently leaving nothing scheduled.

## Success metrics

- `schedule install`/`remove`/the Schedules page never modifies a unit/task it did not itself write.
- A report already scheduled by a hand-written unit shows up on the Schedules page (disabled, with the manual command to turn it off) rather than being silently duplicated.
- Windows and Linux report identical outcomes for the same schedule definition, modulo the underlying OS scheduler.

## Non-goals

- A cross-platform scheduling daemon of its own — scheduling always delegates to the OS's native scheduler (systemd user timers, Task Scheduler).
- Scheduling the always-on web server itself — that is [[os-integration]]'s "service" concern, not a report schedule.

## Notes

- GitHub issue #7 ("D6 Schedules residuals: test-safety guard, delete refusals, key spellings") tracks known residual gaps in the delete-refusal and key-naming logic.
- The always-on server task/unit and the refresh-only pre-fetch timer (README §5) are deliberately out of scope for `schedule` commands — they are refused by name, same as the hand-written print timer.

## Evidence

- CLI: `fridgesheet schedule install|remove|show`
- `fridgesheet/web/routes/schedules.py`, `fridgesheet/web/schedules.py`, `fridgesheet/web/stores/reports.py` (schedule persistence), DB table `schedules`
- `fridgesheet/host/scheduling.py`, `fridgesheet/host/scheduling_linux.py`, `fridgesheet/host/scheduling_windows.py`
- `systemd/fridgesheet-print-sheet.{service,timer}`, `systemd/fridgesheet-refresh.{service,timer}` (the hand-written units the app must never touch)
- README.md §6 ("Schedule it...")
- GitHub issue #7
- `tests/test_host_scheduling.py`, `tests/test_host_scheduling_linux.py`, `tests/test_web_schedules.py`, `tests/test_web_schedules_page.py`

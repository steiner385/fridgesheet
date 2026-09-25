---
slug: os-integration
title: Cross-Platform OS Integration (Printing, Scheduling, Notifications)
state: live
---

The same Fridge Sheet code prints, schedules itself, and notifies the parent correctly whether it's running on Tony's Linux desktop or a friend's Windows PC, without either platform's quirks leaking into the rest of the app.

## Problem

Printing, scheduling and desktop notification are fundamentally different APIs on Linux (CUPS/`lp`, systemd user timers, `notify-send`) and Windows (SumatraPDF, Task Scheduler, toast notifications), but the report/runner/reconciliation logic above them needs to be written once. Without a clean seam, OS-specific code would spread through the whole codebase instead of staying in one place.

## Target users

Both supported platforms' end users, indirectly; directly, every other capability ([[printed-reports]], [[report-scheduling]]) that needs to print, schedule, or notify without knowing which OS it's running on.

## Desired outcome

Every OS-facing concern is a small adapter module in `fridgesheet/host/`, selected by `sys.platform` at import time, with nothing outside `host/` ever checking the OS directly: `printing` (list printers, default printer, print a PDF — CUPS `lp`/`lpstat` on Linux, bundled `SumatraPDF.exe` on Windows), `scheduling` (remove the Task Scheduler tasks and systemd timers earlier versions registered), `notify` (a toast/desktop notification after a scheduled run — `notify-send` on Linux, a `Windows.UI.Notifications` toast attributed to the app's Start-menu shortcut on Windows), `credentials` (covered by [[credential-security]]), `opener` (open a built PDF — Evince/`xdg-open` on Linux, `os.startfile` on Windows), and `service` (the always-on web server itself — a systemd user unit with `Restart=on-failure` on Linux, a logon task on Windows). Every adapter takes its `subprocess.run` as an injectable argument specifically so tests can assert on the exact command line built, without ever running a real OS scheduler or printer in CI.

## Success metrics

- CI (`ci.yml`) runs the full suite on both `ubuntu-latest` and `windows-latest` for every push/PR, so a glibc-only format code or a POSIX-only path assumption cannot ship unnoticed.
- Adapter tests assert exact command lines (the `lp`/`lpstat` invocation, the `schtasks` XML, the SumatraPDF flags) against golden values, not just "did not raise."
- The startup cleanup and `schedule remove --all` only ever remove a leftover unit/task an earlier version of this app itself registered — a marked `fridgesheet-*.timer` on Linux, a task literally named `Fridge Sheet - *` (other than the web server's own) on Windows — and never a hand-written unit (see [[report-scheduling]]).

## Non-goals

- macOS support — the adapter shape is designed to accommodate it (`launchd` is named as the future Linux/Windows-equivalent), but no macOS packaging or adapter ships.
- Any OS-level capability not already needed by printing, scheduling, notification, the credential store, or the always-on service.

## Notes

- Desktop shortcuts (`desktop/fridgesheet-{pdf,print}.desktop`, driven by `scripts/fridgesheet-desktop.sh`) and the household's hand-written systemd units (`systemd/fridgesheet-{print-sheet,refresh}.{service,timer}`) are the Linux-specific, human-operated half of this capability; see [[windows-packaging]] for the equivalent Windows installer-driven half.
- The Windows toast is deliberately attributed to the Start-menu shortcut's `AppUserModelID` rather than a generic Python process identity, so it shows the app's own name and icon.
- GitHub issue #4 touches `jobs, service, installer` residuals that overlap this capability and [[windows-packaging]].

## Evidence

- `fridgesheet/host/__init__.py`, `printing.py`/`printing_linux.py`/`printing_windows.py`, `scheduling.py`/`scheduling_linux.py`/`scheduling_windows.py`, `notify.py`/`notify_linux.py`/`notify_windows.py`, `opener.py`, `service.py`/`service_linux.py`/`service_windows.py`
- `fridgesheet/host/logon-task.xml` (Task Scheduler template for the web server's own logon task)
- CLI: `fridgesheet printers`, `fridgesheet service install|remove|show`
- `desktop/fridgesheet-{pdf,print}.desktop`, `scripts/fridgesheet-desktop.sh`, `systemd/fridgesheet-{print-sheet,refresh}.{service,timer}`
- `.github/workflows/ci.yml` (Ubuntu + Windows matrix)
- GitHub issue #4
- `tests/test_host_printing.py`, `tests/test_host_notify.py`, `tests/test_host_service.py`, `tests/test_os_leftovers.py`

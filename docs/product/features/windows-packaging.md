---
slug: windows-packaging
title: Windows Packaging & Release Distribution
state: live
links:
  - kind: powered_by
    feature: os-integration
---

Anyone else running the same district's Canvas and HAC can install "Fridge Sheet" on their own Windows PC with one download and no terminal, and it keeps printing on its own after they walk away.

## Problem

Tony's own Linux setup (systemd timers, GNOME keyring, CUPS, a cloned repo) is not something a non-technical friend can or should replicate. Getting this to another parent requires a real installer, a bundled browser engine and PDF printer, an in-place upgrade path, and a clean uninstall — none of which a `pip install -e .` workflow provides.

## Target users

A parent at another district on the same Canvas/HAC/OneLogin stack, installing and running the app with no terminal, ever.

## Desired outcome

`packaging/windows/build.ps1`, run by `.github/workflows/release.yml` on a tagged `v*` push, bundles Chromium (via Playwright) and a pinned SumatraPDF, freezes the app with PyInstaller (`FridgeSheet.spec`), runs a smoke test against the frozen bundle (`doctor` passing, a `--dry-run` sheet from a fixture snapshot, `schedule install`/`remove --all` round-tripping through real `schtasks`, the web server answering `/health`/`/`/`/diagnostics`, `service install`/`remove` round-tripping the logon task), and wraps it with Inno Setup (`installer.iss`) into a per-user, unsigned, no-admin-prompt installer attached to the GitHub release. Installed copies check GitHub once a day for a newer release and say so in Settings and the header (sending nothing else). Upgrading over a running app is handled explicitly: `installer.iss`'s `PrepareToInstall` ends the logon task and force-kills the exe and its children (`taskkill /T`) before files are replaced, then re-registers and restarts the task — the same stop-before-replace step runs on uninstall.

## Success metrics

- The release workflow refuses to build for a tag that doesn't match `pyproject.toml`'s version.
- An upgrade over a running install completes with no "files in use" dialog and no reboot prompt, and leaves exactly one running process afterward.
- An uninstall removes the program and every task the app itself installed, while leaving `%LOCALAPPDATA%\fridgesheet` (sheets, `fridgesheet.db`, config, logs) and the Credential Manager entry intact.
- `docs/release-checklist.md`'s hardware-dependent checks (real paper, a real phone camera, a real reboot, a second PC) are worked through by a human before every tag — CI cannot prove these.

## Non-goals

- Code signing — explicitly out of scope; SmartScreen's warning is accepted and documented for the end user.
- Auto-update / in-place silent updates — the user re-downloads and re-runs the installer; Inno Setup handles the in-place replace.
- Packaging the MCP server into the Windows build (see [[mcp-server]]).

## Notes

- GitHub issue #10 is an open, confirmed defect: installing as a genuine standard (non-administrator) Windows user causes `service install`'s `schtasks /Create` to fail with Access Denied — but Inno Setup does not check a `[Run]` entry's exit code, so the installer still reports success while the app silently never starts itself. Ruled out as an artifact of the test method (SSH, a weak token); reproduced via three independent access paths including the raw `Schedule.Service` COM API.
- GitHub issue #15 tracks the five checklist items that structurally cannot be verified by CI or an agent — a real print, a real scheduled fire, a real phone camera scan, a cold boot, and the `taskkill /T` children case — and are treated as standing physical-world gaps rather than release blockers.
- A real Windows 11 pass on 2026-09-17 (documented in `docs/release-checklist.md` §0b) exercised install, the upgrade-over-running-app fix, Schedules writing a real task, and uninstall-with-a-running-server — and caught one real defect (a farewell message box that `/SUPPRESSMSGBOXES` didn't suppress), since fixed.
- Size is accepted at ~200 MB installed, almost all Chromium.

## Evidence

- `packaging/windows/build.ps1`, `installer.iss`, `FridgeSheet.spec`, `smoke.ps1`, `fixture-snapshot.json`, `sumatra.json`, `FridgeSheet.ico`
- `.github/workflows/release.yml`
- `docs/windows.md`, `docs/release-checklist.md`
- `docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md`
- README.md §"Releasing the Windows installer"
- GitHub issues #1 (closed), #9, #10, #15
- `tests/test_packaging.py`

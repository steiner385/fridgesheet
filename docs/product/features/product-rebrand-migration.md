---
slug: product-rebrand-migration
title: Product Rebrand & Data Migration
state: live
parent: windows-packaging
---

An existing Lakota Sheet install upgrades to Fridge Sheet automatically on first start, keeping every kid's history, credentials, notes and schedules intact under the new name.

## Problem

The product was built and shipped under a district-specific name ("Lakota Sheet" / `lakota-grades`) and then fully rebranded ("Fridge Sheet" / `fridgesheet`) so any district's parent could install it without a name that only means something to one family. That rename touches the package name, CLI command, data directory, keyring service, env-var prefix, scheduled-task names, and the installer's own identity (Inno AppId) — any one of which, done carelessly, loses a family's run history or stored password.

## Target users

Tony, migrating his own live install; any future parent who installed under the old name before the rebrand shipped.

## Desired outcome

`fridgesheet.migrate.run()` runs before anything opens the database, from both the CLI entry point and the web server start, and is safe to run every time: if the new home directory doesn't exist and the old one does, it moves it (same-filesystem `os.replace`) and, on Linux only, leaves a symlink at the old path (because hand-written systemd units and Drive paths still name it explicitly); if the new keyring service has no password for the configured username and the old service does, it copies it (leaving the old entry alone); every `LAKOTA_<X>` environment variable also sets `FRIDGESHEET_<X>` when the new name is unset, so old `.env` files keep working while code only ever reads the new names. On Windows, the installer's own `[Code]` finds an old-AppId install and silently uninstalls it first (keeping the data directory, which the app then moves) before installing under the new identity. A `lakota-grades` console-script shim prints a one-line notice and delegates to the same `main`, kept for exactly one release; `doctor` lists every shim still in use under "Old names still in use" so they're easy to retire later.

## Success metrics

- A machine with an old install ends up with the same run history, flags, notes, credentials and schedules under the new name, verified end to end on a real Windows box (graphy, 2026-09-18).
- `doctor`'s "old names" line reads `none` once migration and any admin-registered task rename are complete.
- No source or doc file outside the rebrand design spec and the (unavoidable) district defaults still contains the old name, case-insensitively, past an explicit allowlist.

## Non-goals

- Retiring the shims in this release — explicitly deferred to the release after.
- Renaming Tony's own hand-written systemd units, desktop shortcuts, or clone directory — they keep working through the shims and the symlink, by design.

## Notes

- The product mark (a sheet of paper under a fridge magnet) is part of this same rename effort: `fridgesheet/web/static/mark.svg` is the source of truth, rendered to the installer icon and favicons by `scripts/render_mark.py` on the maintainer's machine (CI does not render it).
- An admin-registered scheduled task under the old name cannot be removed by the old app's own uninstaller and must be re-registered by hand under the new name — a documented manual step in the release checklist, not something the migration code can reach.

## Evidence

- `fridgesheet/migrate.py`, `fridgesheet/web/static/mark.svg`, `scripts/render_mark.py`
- `packaging/windows/installer.iss` (`[Code]` old-AppId silent uninstall, `[InstallDelete]` for both old and new dist-info)
- `docs/superpowers/specs/2026-09-18-fridgesheet-rebrand-design.md`
- `docs/release-checklist.md` §7b ("The rename: upgrading a Lakota Sheet install")
- `tests/test_migrate.py`, `tests/test_rebrand.py`

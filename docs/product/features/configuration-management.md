---
slug: configuration-management
title: Configuration, Settings & Seed Files
state: live
---

A parent can adjust how Fridge Sheet behaves — printer, look-ahead window, nicknames, late-work rules, no-print days — from one place, with one clear rule for what wins when the same setting is set two ways.

## Problem

Settings need to work identically whether they're set from a config file (for the CLI/Linux power-user path), environment variables (for 1Password Environments or a script), or a form in the browser (for the Windows "friend" who never opens a text editor) — and a parent needs to trust that editing one doesn't silently get overridden by a stale value in another.

## Target users

Tony's own Linux/`.env`-based workflow; a Windows "friend" who only ever touches the Settings page; the app's own scheduled/unattended runs, which must resolve the same settings without a terminal.

## Desired outcome

`config.toml` in the home directory (`~/.fridgesheet` on Linux, `%LOCALAPPDATA%\fridgesheet` on Windows; `FRIDGESHEET_HOME` overrides both) holds most settings and is what the Settings page and `fridgesheet set-credentials` edit; environment variables (`FRIDGESHEET_*`, loaded from `~/.fridgesheet/.env` or a path named by `FRIDGESHEET_ENV_FILE`) always win over it, so Tony's `.env`-based Linux setup keeps working unchanged. Precedence overall, highest first: CLI flag, environment variable, `config.toml`, built-in default. Two seed files are created on first run and never overwritten by the app: `late-rules.toml` (per kid/class late-work credit rules) and `no-print-days.txt` (no-school days, `--force` overrides). Unknown keys in `config.toml` are ignored, so a newer config still loads under an older app version.

## Success metrics

- Setting the same value in an env var and `config.toml` always resolves to the env var's value, with no surprises.
- A hand-edited `late-rules.toml` or `no-print-days.txt` is never clobbered by an app write.
- A `config.toml` that fails to parse produces a clear, file-naming error rather than a silent fallback to defaults.

## Non-goals

- A feature-flag system — this is user-facing configuration, not internal rollout control.
- Multiple named configuration profiles — one install has exactly one active configuration.

## Notes

- `FRIDGESHEET_NICKNAMES` / the `[kids]` table map a snapshot first name to the name printed on the sheet (`fridgesheet/naming.py`); the old built-in `Alex=Al` default was deliberately removed during the Windows-packaging generalization (see [[windows-packaging]]) so nicknames come only from configuration, never a hardcoded family default.
- `print-sheet`'s `--days`/`--overdue-days` defaults (14) are hardcoded and intentionally do not read `config.toml`'s `days_ahead`/`overdue_days` — only the general-purpose `run open-work` form does; this asymmetry is a documented, deliberate compatibility choice, not a bug.
- The browser app's in-page editors for `late-rules.toml` and `no-print-days.txt` write the same files the CLI/Linux path reads, so the two are always describing one truth.

## Evidence

- `fridgesheet/config.py`, `fridgesheet/naming.py`
- `env.example`, seed content for `late-rules.toml` and `no-print-days.txt`
- `fridgesheet/web/routes/settings.py` (`/settings/files/{name}` in-page editors)
- README.md §"Settings file", §3 ("First check")
- `tests/test_config.py`, `tests/test_late_rules.py`

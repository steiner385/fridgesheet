---
slug: credential-security
title: Credential Handling & Network Security
state: live
---

A parent's OneLogin credentials, and everything they unlock, stay on their own machine and out of every log, config file, and AI tool call — even though the app has no login of its own.

## Problem

This app necessarily holds a real school-account password to do its job, and also hands data to an AI assistant ([[mcp-server]]) and, optionally, a phone on the home network. Each of those is a place a credential or a kid's data could leak if handled carelessly, and the product has explicit, stated opinions about which of those risks are acceptable and which are not.

## Target users

The parent who owns the credentials; every other capability that depends on this one holding the line — [[mcp-server]] most directly, but also [[browser-app]]'s Settings page and [[os-integration]]'s scheduled/unattended runs.

## Desired outcome

Credentials resolve, in order: environment variables (a 1Password Environments mount, `op run`, or a plain `.env`), the OS credential store (GNOME keyring on Linux via `secret-tool`, Windows Credential Manager via `keyring`) — the default — or `op read` secret references for interactive 1Password use. Nothing here ever prints or logs a credential; `Settings.credentials()` is the only reader. The web app has no login (the home network's own isolation is the accepted security boundary, by explicit owner decision), but the stored OneLogin password field is write-only end to end: never rendered into the settings form, never returned by any route, and a blank field on save keeps whatever is already stored — so the password can be *set* from any device on the network but never read back from one. The server talks to nothing but OneLogin, Canvas and HAC (plus, once a day, a version check against GitHub that sends nothing) — no telemetry, ever.

## Success metrics

- No credential ever appears in `print-sheet.log`, `app.log`, a toast notification, or an HTTP response body.
- The Settings password field, reloaded after being set from a second device, is always empty.
- A locked-but-not-logged-out desktop keeps the OS keyring available to unattended/scheduled runs; a keyring that is genuinely locked (nobody signed into the desktop) fails loudly rather than silently.

## Non-goals

- HTTPS or a login system for the browser app — explicitly rejected as unsatisfiable on a headless host and as protecting less than it appears to (any device that can reach the page can already read the kids' grades).
- Multi-factor-authenticated OneLogin accounts — the unattended refresh cannot work against them at all; this is a documented hard limit, not a bug to fix here.

## Notes

- The "Allow other devices on this network" toggle rebinds the server to `0.0.0.0` and shows a LAN URL with a QR code (`fridgesheet/qr.py`) for a phone; `FRIDGESHEET_WEB_HOST` can pin the bind address directly for headless/scripted use, with `127.0.0.1` as the one variant worth using by hand (keeps the app off the network without touching Settings).
- On Windows, the app refuses to answer at any address other than the ones it's configured for (its own loopback address, or the LAN address once the toggle is on) — reaching it via the machine's computer name is explicitly refused, whether that's an accident or someone probing it.
- `op://` 1Password references reject punctuation in an item title; addressing by UUID is the documented workaround.

## Evidence

- `fridgesheet/config.py` (`Settings.credentials()` precedence), `fridgesheet/host/credentials.py`, `credentials_linux.py`, `credentials_windows.py`
- `fridgesheet/web/routes/settings.py` (write-only password field), `fridgesheet/qr.py`
- CLI: `fridgesheet set-credentials`
- README.md §2 ("Credentials"), §"Security notes"; `docs/superpowers/specs/2026-09-15-fridgesheet-web-app-design.md` §8 ("Access and security")
- `docs/windows.md` §"To read the sheet on your phone", §"FRIDGESHEET_WEB_HOST"
- `tests/test_host_credentials.py`, `tests/test_web_settings_page.py`, `tests/test_qr.py`

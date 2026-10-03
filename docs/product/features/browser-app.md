---
slug: browser-app
title: Local Browser App
state: live
---

A parent gets one local web app — reachable from a laptop or, if they opt in, a phone — that becomes the single place to see, annotate and act on everything Fridge Sheet knows, instead of jumping between a terminal and a PDF.

## Problem

The CLI and printed sheet cover "what's open today," but a parent also wants to browse history, adjust settings, check on the last refresh, and see whether a scheduled print actually happened — all without a terminal, and (per the design goal) without anyone else on the family network having to know a password.

## Target users

Both parents in the household, from a laptop primarily and optionally a phone; a "friend" installing the Windows build, who never touches a terminal at all.

## Desired outcome

`fridgesheet web` (or the Windows exe with no arguments) runs a small local FastAPI/uvicorn server rendering server-side Jinja2 pages with htmx for in-page updates, and opens it in the browser. One responsive layout (left rail on desktop, single column on phone) shows the last refresh time and source health in the header on every page. Long-running actions (refresh, build, print) run on a single background worker sharing the CLI runner's lock, streaming progress to the page over server-sent events, so a button press and a scheduled CLI run never collide. The app is the delivery surface for [[actionable-work-model]] (Dashboard, Kid, Reconcile), [[trends-and-changes]], [[view-reports]] and [[report-scheduling]] — this capability covers the shell, navigation, job-progress infrastructure and general settings/diagnostics UI those pages sit inside.

A browser remembers who is looking (`/who`, one tap, no login): a kid's device opens on their plan with a rail naming only their pages; a grown-up's opens on Today. Spec: `docs/superpowers/specs/2026-09-27-plan-fills-itself-design.md` §13.

The app installs on a phone's home screen (a web app manifest and a small service worker, `routes/pwa.py`). Each kid's page, in the family's view, folds a QR code for `/who/<key>` at the machine's network address: the phone that scans it opens as that kid and remembers; installed from there, the kid's own app starts on that link, so the home-screen app's separate cookie jar learns who is looking on its first launch. The worker never caches a page — only the offline page a kid sees at school, away from the home Wi‑Fi.

## Success metrics

- Every page renders correctly with an empty database (first run) and with a populated one.
- A refresh/print triggered from the browser and one triggered by a scheduled CLI run never run concurrently or silently overwrite each other's output.
- Progress for a 1–3 minute refresh is visibly live on the page, not a blank wait.
- A second server start (port already in use) opens the browser at the existing instance rather than starting a duplicate.

## Non-goals

- Any login or account system — see [[credential-security]] for why, and what that implies about network exposure.
- Multiple households sharing one install.
- A JavaScript build step — htmx plus one vendored charting library (Chart.js, with its date adapter) is the entire client-side dependency.

## Notes

- Settings mirrors `config.toml` exactly (username, printer, archive folder, nicknames, hidden courses) plus in-browser editors for `late-rules.toml` and `no-print-days.txt`, a **Test login** button, and the network-access toggle — see [[configuration-management]] and [[credential-security]] for the parts of Settings that are really about those capabilities.
- Diagnostics runs the same doctor checks as `fridgesheet doctor` — see [[quality-and-diagnostics]].
- GitHub issues #3 and #4 ("Plan B part 1/2 follow-ups... server core residuals... jobs, service, installer") track residual gaps from the initial server delivery.

## Evidence

- `fridgesheet/web/app.py`, `fridgesheet/web/server.py`, `fridgesheet/web/__main__.py`, `fridgesheet/web/jobs.py`, `fridgesheet/web/routes/jobs.py`
- `fridgesheet/web/routes/dashboard.py`, `kid.py`, `reconcile.py`, `flags.py`, `notes.py`
- `fridgesheet/web/templates/*`, `fridgesheet/web/static/app.css`, `app.js`, vendored `htmx.min.js`, `chart.umd.min.js`, `chartjs-adapter-date-fns.bundle.min.js`
- CLI: `fridgesheet web`
- README.md §"The browser app"
- GitHub issues #3, #4
- `tests/test_web_app.py`, `tests/test_web_main.py`, `tests/test_web_server.py`, `tests/test_web_pages.py`, `tests/test_web_status_parts.py`

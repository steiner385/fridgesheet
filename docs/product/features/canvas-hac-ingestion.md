---
slug: canvas-hac-ingestion
title: Canvas & HAC Data Ingestion
state: live
---

Fridge Sheet pulls Canvas and Home Access Center into one durable local snapshot so every other tool and report reads the same facts without re-scraping the sites.

## Problem

Canvas and Home Access Center are two separate logins behind a district's OneLogin SSO, each with its own browser-hostile quirks (no public API token for parent/observer accounts, HAC has no login form of its own, an iframe-rendered classwork table, a student switcher with no visible "Change" button). Pulling both by hand, every time a parent wants to know what's outstanding, is slow and error-prone, and doing it live on every question would hammer both sites and log in constantly.

## Target users

The parent(s) running Fridge Sheet, and every other capability in the product ([[actionable-work-model]], [[printed-reports]], [[mcp-server]]) that reads the snapshot instead of talking to the sites directly.

## Desired outcome

One authenticated pull ("refresh") per cache window collects every kid's Canvas assignments/grades and HAC classwork/grades through a single persistent Chromium session, and writes an atomic, permission-locked JSON snapshot that every tool, report and page reads from — "one pull, many tools." A source that fails or is skipped on a given refresh never erases the last good data for that source; it is marked `stale` with the time it was actually fetched, and downstream reports say so.

## Success metrics

- A `fridgesheet check` / `refresh` reports `OK` for both sources under normal conditions.
- `status()` accurately reports snapshot age and per-source health, including `stale` reasons.
- No refresh writes a source's data out empty because that source failed or was skipped — the previous good pull is carried forward.
- Cache TTL (default 3h) keeps a normal day's worth of questions from re-hitting Canvas/HAC more than once.

## Non-goals

- Write-back to Canvas or HAC (read-only, always).
- ParentSquare or other OneLogin-portal apps as a data source (explicitly named as future scope, not built).
- A public Canvas API token flow (disabled for parent/observer accounts by Canvas itself; browser-session cookies against the REST API are used instead).

## Notes

- One persistent Chromium profile (`~/.fridgesheet/browser-profile`, `0700`) holds OneLogin/Canvas/HAC cookies so a login only happens when a site actually bounces the session to a login page — "log in rarely" is a named design goal.
- Extensive host-specific quirks are documented and coded around: `/api/v1/users/<kid>/courses` 403s for observers (use `include[]=observed_users`); `/api/v1/courses/<id>/users` also 403s, so teacher/TA contact falls back to the course object's `include[]=teachers`; HAC's login form is gone, so HAC is entered only via the OneLogin portal tile; the HAC student switcher is a POST form with no visible toggle; HAC Classwork renders inside iframe `sg-legacy-iframe` and must be polled, not scanned once after `domcontentloaded`; the browser reports an ordinary Chrome UA (not `HeadlessChrome/<v>`) so ParentSquare's sniffer doesn't misroute it.
- `matching.py` pairs a Canvas assignment with its HAC twin by title (with a fallback heuristic requiring an exact due date/points match and exactly one candidate) — pairing failures cause an assignment to double-count, once from each source, which is the seed of [[actionable-work-model]]'s reconciliation problem.
- Credentials for the pull itself are covered by [[credential-security]], not this capability.

## Evidence

- `fridgesheet/canvas.py`, `fridgesheet/hac.py`, `fridgesheet/session.py`, `fridgesheet/collector.py`, `fridgesheet/matching.py`
- `scripts/hac_key_spike.py` (HAC stable-key research spike)
- CLI: `fridgesheet check`, `fridgesheet refresh`, `fridgesheet status`, `fridgesheet login`
- MCP tools `refresh()` / `status()` in `fridgesheet/server.py`
- README.md §3 ("First check"), §"Notes and known quirks (Lakota, Sept 2026)"
- `tests/test_canvas.py`, `tests/test_collector.py`, `tests/test_matching.py`

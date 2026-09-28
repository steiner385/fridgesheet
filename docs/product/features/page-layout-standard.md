---
slug: page-layout-standard
title: Page Layout Standard
state: live
parent: browser-app
links:
  - kind: related
    project: fridgesheet
    feature: all-work-table-ux
  - kind: related
    project: fridgesheet
    feature: section-and-card-standard
---

Every page in the browser app opens, scrolls and folds to a phone the same way, so a layout fix made once (#184) does not have to be rediscovered page by page.

## Problem

The app grew nineteen-plus pages one at a time, and each inherited whatever layout its author reached for that day rather than a shared standard. A 2026-09-26 audit (`docs/product/2026-09-26-page-layout-audit.md`) measured all of them across seven viewports and found the drift was structural, not cosmetic: `main { max-width: 1100px }` left 32.5% of a 1920px screen and 49.4% of a 2560px screen blank while wide tables (Runs' seven columns, the kid table's three) had room to breathe but didn't get it; a phone's first 210–249px went to chrome before any content, because the quiet status-bar lines (clock, "Last run OK") never dropped; a phone held sideways still got the desktop layout; six different heading patterns existed across nineteen pages, so card titles and a page's own `<h2>` title competed at the same visual level; and three incompatible filter-control patterns (badge chips, radios plus selects, inline selects) forced a parent to relearn the UI on every page. #184 fixed the shared mechanics — one `--page-max: 1600px` ceiling, a shared `_page_head.html`, a one-line status bar, tables that scroll inside their own box — but that was the standard, not its application: seven more issues (#187, #188, #191, #192, #195, #196, #197) tracked carrying it into the pages and edge cases #184 didn't reach.

## Target users

Every user of the browser app, on every page: the weeknight triager who now gets a consistent heading and filter pattern regardless of which page they're on; the phone user (portrait or sideways) who needs chrome to yield to content; the wide-monitor household where the app used to strand a third of the screen as dead space.

## Desired outcome

One page layout, applied everywhere rather than negotiated per page: a shared `_page_head.html` sets the heading hierarchy (the page title is the single `<h2>`; cards, kid sections and job rows are `<h3>`/`<h4>`) so no card competes with the page for top billing; every `table.items` lives in a `.table-wrap` that scrolls sideways in its own box instead of pushing the whole page wide; the content column is capped at `--page-max: 1600px` everywhere, deliberately not wider, because a work list or card row is not improved by getting wider, only harder to scan (recorded and closed as a considered, not-taken option in #197); the status bar is one shell-level line that drops its quieter items below 1280px and shares its row with the phone strip when a sideways phone leaves under 500px of height; filter controls settle on one pattern (badge chips) instead of three; and every table identified as too wide for a phone (Runs, Changes) folds its lowest-value columns under the row it belongs to rather than forcing a sideways swipe. This capability owns *that every page follows the standard*; it does not own what any one page's table or filter actually does with its own data — that stays with the page's own feature (e.g. [[all-work-table-ux]] for the kid table's vocabulary).

## Success metrics

- Every page in `scripts/layout_audit_measure.py`'s 21-page sweep uses the shared `_page_head.html` heading pattern, one `--page-max`, and the one-line status bar, at all seven measured viewports.
- No `table.items` forces the page itself to scroll sideways on a 390px phone; the table scrolls inside `.table-wrap` instead.
- Blank space at the right of the content column is a recorded, deliberate trade-off (documented in #197) rather than an accident of a 1100px-era default.
- Filter controls across pages use one visual pattern (badge chips), not three.
- A phone held sideways with under 500px of height gets the strip and status bar sharing one row, not two full-height chrome bars ahead of any content.

## Non-goals

- What any individual page's table, filter, or card actually shows — the vocabulary and business logic of the kid table stays with [[all-work-table-ux]]; this capability only governs the shared shell those pages sit inside, the same split [[browser-app]] draws for navigation and job-progress infrastructure.
- Raising the 1600px ceiling or centering the content column on very wide (2560px+) screens: considered in #197 and deliberately left closed unless a household actually reads the app that wide.
- A route-level bug found during the audit's measurement pass (#183, a class page listing every row twice) — that is a data bug, not a layout one, and is tracked outside this capability.

## Notes

- The standard itself — `--page-max`, the shared `_page_head.html`, the one-line status bar, `.table-wrap` scrolling — was designed in `docs/superpowers/specs/2026-09-26-page-layout-standard-design.md` and landed in #184 (commit `25c4f99`); this capability is that standard's continued application across the rest of the app, tracked by its own follow-up issues.
- #197 is a closed "decision to revisit" rather than an open gap: the audit measured that 1600px still leaves 29.8% blank at 2560px, weighed centering the column vs. raising the ceiling, and recorded both as two-line CSS changes to reach for only if a household actually uses that wide a screen. Treat it as evidence the standard was applied deliberately, not incompletely.
- #188 is the audit's own bookkeeping issue (naming its follow-ups by number, `[skip release]`) rather than a layout change; it's included in the driving cluster because it's the thread that ties #187/#191/#192/#195/#196/#197 back to the audit that produced them.
- The content column below the head has its own standard, [[section-and-card-standard]].

## Evidence

- Driving issues: #187 (Runs/Changes phone columns), #188 (audit names its follow-ups), #191 (heading levels), #192 (three filter patterns settle on one), #195 (update badge wraps the phone status bar), #196 (sideways phone gives 31% of height to chrome), #197 (2560px blank-space decision, closed not-taken)
- Parent standard: #184 ("One page layout on every page"), designed in `docs/superpowers/specs/2026-09-26-page-layout-standard-design.md`, audited in `docs/product/2026-09-26-page-layout-audit.md`
- `fridgesheet/web/static/app.css` (`--page-max`, `.table-wrap`, status-bar breakpoints, `.badge.current`), `fridgesheet/web/templates/_page_head.html`, `_header.html`, `base.html`
- `fridgesheet/web/templates/runs.html`, `_change_rows.html` (#187's phone column folding), `dashboard.html`, `open.html`, `course.html`, `trends.html`, `changes.html` (#184/#191/#192 heading and chip rollout)
- `scripts/layout_audit_seed.py`, `scripts/layout_audit_measure.py` (the audit's own measurement harness, re-runnable to verify the standard still holds)
- Landed via "One page layout on every page" (#184, `25c4f99`), "Page chrome: the outline under the title is h3/h4, a filter chip in force is filled, the bar fits a phone with an update pending, and a phone on its side shares one row" (#191, #192, #195, #196; `485edee`/`a546862`), and "Runs and Changes fit a phone" (#187; `d54b573`/`caa53e9`); #188 tracked via `adc9db4`/`45c2336`
- `tests/test_web_page_layout.py`, `tests/test_ui_audit_batch_b.py`

---
slug: view-reports
title: Saved View Reports & Builder
state: live
parent: printed-reports
---

A parent can define their own report — pick a data source, columns, filters, sort and grouping — without writing code, and have it print, schedule and export exactly like the built-in sheet.

## Problem

The built-in open-work sheet answers one question well, but parents want other views of the same data (a weekly summary, a grade trend, a quarter recap) that no fixed, code-defined report can anticipate.

## Target users

A parent who wants a report shape the built-in sheet doesn't provide, without asking for a code change.

## Desired outcome

The Reports page lists both code reports and saved "view" reports (`view:<id>`); a builder lets a parent choose scope (which kids), source (`items`, `grades`, `changes`), columns, filters, group-by, sort, an optional chart, title and print options, with a live preview before saving. A saved view report satisfies the same `Report` protocol as the built-in sheet, so it flows through the identical runner, archiving, run-history and [[report-scheduling]] path — a scheduled view report prints, archives, records and toasts exactly like the open-work sheet. Seed templates (Open work, Weekly summary, Grade trend, Quarter recap) give a starting point. Export to CSV or JSON is available from the same definition.

## Success metrics

- A saved view report, once scheduled, behaves identically (guards, archiving, run history) to the built-in report.
- The preview shown while building matches what actually prints/exports.
- A report built from `changes` or `grades` sources reflects the same underlying facts as the Changes/Trends pages, not a divergent calculation.

## Non-goals

- A general-purpose query language or SQL access — filters and grouping are fixed, form-driven operations.
- Cross-household or shared report templates — reports are local to this single install.

## Notes

- GitHub issue #6 ("Plan D part 1 follow-ups (view reports)") tracks residual polish from the initial delivery.

## Evidence

- `fridgesheet/web/views.py`, `fridgesheet/reports/view.py`, `fridgesheet/web/stores/reports.py`, DB table `reports`
- `fridgesheet/web/routes/reports.py` (builder, preview, export CSV/JSON, seed templates)
- GitHub issue #6
- `tests/test_report_view.py`, `tests/test_web_reports_page.py`, `tests/test_web_reports_store.py`, `tests/test_web_views.py`

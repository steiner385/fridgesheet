# Trends on the shared chart stack

**Date:** 2026-09-25. **Status:** approved for implementation (the two choices below were put
to the household and the recommendations taken).

## The problem

The app draws charts two ways. Trends (and the course page's grade line) fetch JSON per
chart and build a uPlot in the browser: bucketing, colours, forward-filling and the
week-label time-zone workaround all live in `app.js`. Reports (#119) build a `ChartData` on
the server, `chart_config()` turns it into one Chart.js config, the config is inlined beside a
`<canvas>`, and the same config is drawn headlessly for the PDF. Two libraries are vendored,
two attach paths run in `app.js`, and the Trends page computes every series twice (once for
the caption and table, again when each chart fetches its JSON).

## What changes

Trends and the course page move to the reports model. Nothing about *what* Trends shows
changes except the two decided points below; the numbers come from the same store functions.

1. **One chart vocabulary, in one module.** `ChartSeries`, `ChartData`, `chart_config()`
   and `escape_for_script_tag()` move out of `web/views.py` (the report builder) into a new
   `web/charts.py` that reports and Trends both import. `views` keeps the names as
   re-exports so nothing that reads `views.ChartData` today has to change.
2. **The vocabulary grows just enough for Trends.** A series may carry its own colour
   (outcomes keep their meaning: not done is red, on time is green, as the tables' `warn`
   class agrees) and an `emphasis` flag (the official grade source is drawn thicker and its
   label ends "· official", the wording the Changes feed already uses). A chart may carry a
   title, a `time` x-scale, and `stepped` lines.
3. **Grade lines keep real timing.** *Decision 1.* Each grade observation is plotted at the
   moment it was seen, on a Chart.js `time` scale, stepped so a line holds its value until
   the next observation (that is what "only rows where something changed" means). A time
   scale needs a date adapter: `chartjs-adapter-date-fns.bundle.min.js` (3.0.0, MIT, ~50 KB)
   is vendored beside `chart.umd.min.js` with a SHA-256 in `VENDOR.md`, and every host that
   loads Chart.js loads it too, including the headless PDF renderer. Tick labels are
   formatted by the browser in its own zone; the previous uPlot chart did the same.
4. **The weekly outcomes chart is a stacked bar.** *Decision 2.* One bar per week, one
   segment per outcome, in the table's column order and colours. Labels are the same
   `md_year` strings the report charts use, computed on the server in the household's zone,
   so the `Date.parse` workaround in `app.js` goes.
5. **Config travels with the page.** Trends and the course page inline each chart's config
   through one partial, `_chart_canvas.html`, which the report preview also uses. The two
   JSON endpoints (`/trends/grades.json`, `/trends/weekly.json`) are removed: nothing else
   called them, and a page that already holds the rows should not ask for them again.
6. **uPlot goes.** `uplot.min.js`, `uplot.min.css`, `_chart.html`, the `.chart`/`.u-legend`
   styles and the ~140 lines of `app.js` that existed for it (the library wait loop, the
   width maths, the registry, the resize listener). Chart.js resizes on its own; the holder
   gives it a height. The one generic attach function keeps #181's destroy-on-swap rule.
7. **Static URLs carry the version.** After an upgrade a browser may keep the old `app.js`,
   which would look for markup this change renames and draw nothing until a hard refresh.
   Script and stylesheet URLs gain `?v=<version>` so a new build is a new URL.

## Non-goals

- Charts on the printed kids' sheet, or a printable Trends page.
- Changing which numbers Trends shows, its filters, or the On-time / Open-the-longest cards.
- Report charts on a time scale (report grade lines stay bucketed averages).

## Constraints

- No build step: vendored files are committed as downloaded, pinned by SHA-256 in
  `fridgesheet/web/static/VENDOR.md`, line endings declared in `.gitattributes`.
- A chart config is JSON: no functions. Anything both hosts need must be expressible as data.
- Chart.js 4.5.1 stays as vendored; the adapter is the only new file.
- Copy stays the app's: "No grades recorded yet.", "Work due that week", "On paper".
- Tests that pinned uPlot's sizing contract are replaced, not left asserting a dead file.

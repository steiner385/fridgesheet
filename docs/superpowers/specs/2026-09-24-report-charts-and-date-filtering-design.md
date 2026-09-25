# Report charts and date filtering: design

Date: 2026-09-24. Status: decisions taken in discussion, awaiting review of this document.
Closes the chart half of #6's "Features the plan deferred" (`Definition.chart` has stayed
`None` since Plan D part 1) and its "No date narrowing (feature)" item, both retriaged open
on 2026-09-23. Builds on `views.py`'s existing `Definition`/`WINDOWS` (#94, preset windows)
and reuses the app's existing bundled Chromium (`session.py`, `doctor.py`) rather than adding
a new dependency for chart rendering.

## 1. Goal

A parent building a view report can add a chart (line, bar, or stacked/grouped bar) plotted
against a real date axis, and can narrow any report — table or chart — to an arbitrary custom
date range, not just the five fixed presets that exist today. The chart must show in the
browser preview and in the printed/scheduled PDF, and the two must agree, the same way the
HTML table, the PDF and the CSV already agree on every value `views.py` produces.

## 2. Decisions taken in discussion

| Question | Decision |
|---|---|
| Where must charts render? | Web preview **and** PDF/scheduled print — not preview-only |
| Chart types at launch | Line, bar, stacked/grouped bar (pie and others deferred) |
| "See the date per data point" | Both: table columns (already true today) and chart axes/points (new) |
| Date filtering | Add a custom start/end range, on top of the existing presets — not a replacement |
| Chart rendering architecture | A modern JS chart library for the live preview; the same library, headless-captured, produces the image embedded in the PDF |
| Per-column date filter operators (before/after/between) | Deferred — the one custom range covers the request |
| Chart data in CSV/JSON export | Deferred — those exports stay row data only |

## 3. The chart data model

`fridgesheet/web/views.py` gains:

```python
CHART_TYPES = ("line", "bar", "stacked_bar")
BUCKETS = ("day", "week", "month")
MAX_CHART_POINTS = 60          # a chart is illustrative, not exhaustive -- see truncation below

@dataclass(frozen=True)
class ChartSpec:
    type: str
    x: str                      # a date column of the source
    y: str | None = None        # a number column, or None = count of rows
    series: str | None = None   # a column that splits the chart into lines/segments;
                                 # required when type == "stacked_bar"
    bucket: str = "week"
```

`Definition.chart: ChartSpec | None = None` replaces today's dead `chart: None = None` stub.
`to_json`/`from_json` round-trip it the same defensive way `filters`/`sort` already are:
`from_json` builds whatever shape is present and leaves `validate()` to name the problem,
rather than silently dropping a malformed chart.

`validate()` gains, only when `d.chart is not None`:
- `chart.type` must be one of `CHART_TYPES`; `chart.bucket` one of `BUCKETS`.
- `chart.x` must be a column of `d.source` whose `kind` is `"date"` — this is the concrete
  meaning of "date per data point": a chart can only be built against a real date column.
- `chart.y`, if set, must be a `"number"` column of `d.source`.
- `chart.series` is required when `type == "stacked_bar"`, and if set must be a real column
  of `d.source`.

### Building chart data

`build()` already produces `kept`, the filtered, windowed, scoped, sorted, `MAX_ROWS`-capped
`(row, keys)` pairs the table renders from. The chart is built from that exact same set, not
a separate query — a chart cannot show a point the table doesn't, for the same reason the
PDF cannot disagree with the HTML.

For each kept pair, `keys[chart.x]` is already an ISO-parseable timestamp (`_date_key`'s
output), `keys[chart.y]` is already a float when `chart.y` is set (`_num_key`'s output), and
`row.get(chart.series, "")` is the display value for the series split. Points bucket by
`chart.bucket` (day → the date itself; week → that week's Monday; month → the 1st), using two
new shared helpers in `fridgesheet/dates.py` — `week_start(d)` and `month_start(d)` — that
also replace `trends.py`'s private `_monday`, since both now need the same boundary.

Aggregation within a bucket: when `chart.y` is set, the bucket's value is the **average** of
that column's values in it (a grade trend shows where the grade sat, not a meaningless sum).
When `chart.y` is `None`, the bucket's value is a **count** of rows in it (an items-by-status
chart wants "how many", the same as `weekly_counts`/`weekly_outcomes` today).

Missing buckets: `bar`/`stacked_bar` charts zero-fill every bucket in the range so the x-axis
is even, exactly the convention `weekly_counts` and `weekly_outcomes` already use ("one row
per week even when nothing happened"). `line` charts do **not** zero-fill — `grade_series`
already established that "a flat stretch is simply the absence of points between two of
them", and a chart of a number column should keep that meaning rather than drawing a
misleading dip to zero.

A row whose `chart.x` value is blank cannot be plotted and is dropped from the chart only
(it still counts in the table) — the count of chart-dropped rows folds into a new
`Rendered.chart_note`, the same "say so, don't silently shrink" instinct behind
`Rendered.truncated`.

`MAX_CHART_POINTS` bounds bucket count: a daily bucket over a school year is unreadable as a
bar chart. When bucketing would produce more than `MAX_CHART_POINTS`, the chart keeps the
most recent `MAX_CHART_POINTS` buckets and `chart_note` says so ("Chart shows the most recent
N; choose a coarser bucket or a shorter range to see the rest.").

`Rendered` gains `chart: ChartData | None` and `chart_note: str`. `ChartData` is a small
dataclass: `type: str`, `x_label: str`, `y_label: str`, `series: list[ChartSeries]`, each
`ChartSeries(label: str, points: list[tuple[str, float]])` — `(bucket_label, value)`, already
formatted for display (`dates.md`-style, matching how every other value in `Rendered` is
formatted once and reused everywhere). `y_label` is the `y` column's own label when set, or
"Count" when `chart.y is None`. A kept row with a blank `y` value (the column is `None` for
that row) is excluded from its bucket's average, not treated as a zero — a missing grade
observation should not pull a trend line down.

## 4. Custom date range

`WINDOWS` gains one entry: `("custom", "Custom range", None)`. `Definition` gains
`date_from: str = ""` and `date_to: str = ""` (ISO `YYYY-MM-DD`, blank when unused — same
style as every other string field, no new `Optional[datetime]` shape to serialize).

`validate()`: when `d.window == "custom"`, both `date_from` and `date_to` must be present,
parse as dates, and satisfy `date_from <= date_to` — one sentence per problem, the existing
pattern.

`window_start` gains the `"custom"` case (midnight of `date_from`). A new `window_end(d, now)`
returns `None` for every window today ("through now" is what every existing window already
means) except `"custom"`, which returns the end of `date_to`'s day (inclusive). A new
`_on_or_before(v, end)` mirrors `_on_or_after`. `_item_rows`, `_grade_rows` and `_change_rows`
each gain the matching upper-bound filter, applied the same post-fetch way `_on_or_after`
already is (no store changes needed — `grade_series`/`changes_store.since` keep their
`since`-only signature; the end bound is applied to what they return, in the same loop that
already builds each row).

## 5. Rendering: one config, two hosts

The library: **Chart.js**, vendored as a single UMD file (`chart.umd.min.js`) into
`fridgesheet/web/static/`, next to the existing vendored `uplot.min.js` — same
no-build-step, no-framework pattern the codebase already uses. Chart.js has native line, bar
and stacked-bar support, matching the three approved types exactly, and draws to a `<canvas>`
element that both hosts below can use unmodified.

A new `views.chart_config(chart_data: ChartData) -> dict` builds the Chart.js
type/data/options object from a `ChartData` — one function, so both hosts draw from
byte-identical configuration:

- **Live web preview**: the existing `data-chart`/`data-kind` mechanism (`_chart.html`,
  `app.js`) gains a `report` kind. The reports preview/standalone view route serves
  `chart_config()` as JSON (a new `/reports/{id}/chart.json`, or a field added to the existing
  preview response); `app.js`'s `attachCharts` initializes a live, interactive Chart.js
  instance for it, alongside its existing uPlot path for Trends.
- **PDF embed**: a new `fridgesheet/chart_render.py` exposes
  `render_chart_png(chart_data: ChartData, *, width_px: int, height_px: int) -> bytes`. It
  builds a small standalone HTML document — the same vendored `chart.umd.min.js`, the same
  `chart_config()` output, animation disabled and a `window.__chartReady = true` flag set in
  Chart.js's `onComplete` — and loads it via Playwright's `page.set_content()`. This is a new,
  lighter helper alongside `session.browser()`, not a reuse of it: a chart capture wants a
  clean throwaway context, not `launch_persistent_context`'s cookie/profile persistence built
  for scraping sessions. `page.wait_for_function("window.__chartReady")`, then
  `page.locator("canvas").screenshot()` returns PNG bytes directly, at `device_scale_factor=2`
  for print sharpness. `sheet.build_table_pdf` gains `chart_png: bytes | None = None` and, when
  set, inserts a `reportlab.platypus.Image` sized to the page width, after the title and
  before the first group's table.

Playwright and its bundled Chromium are **already** a hard dependency
(`pyproject.toml`: `playwright>=1.45`), already shipped in the PyInstaller build, and already
health-checked by `doctor.py`'s `_chromium()` probe (used today for Canvas/HAC login
sessions). This is not a new dependency being introduced for charts — it's reusing capability
the app already provisions and already verifies.

## 6. Robustness: a chart never fails a report

`ViewReport.build()` (`fridgesheet/reports/view.py`) calls `render_chart_png` only when
`d.chart` is set, and catches its failure (missing/broken Chromium, a render timeout) rather
than letting it raise `ReportError`. On failure: log it, build the PDF with `chart_png=None`,
and append "Chart unavailable this run — see the log" to the report's existing `note`
mechanism. A scheduled report with a broken chart renderer still prints, archives and records
a run — exactly the guarantee `printed-reports.md` already makes for every other failure mode
in the runner.

The live web preview has an independent failure domain (client-side JS, not a headless
capture): if Chart.js fails to draw, `app.js` shows a small inline "chart failed to render"
message in that div; the table beside it is unaffected either way.

## 7. Builder UI

`report_builder.html` gains chart controls — type, x (filtered to the source's date columns),
y (the source's number columns, plus "Count of rows"), series (shown/required only for
stacked bar), bucket — and two date inputs for the custom range, shown only when
`window = custom`, mirroring how the window select already toggles visible controls.
`definition_from_form()` (`routes/reports.py`) reads all of these into the `Definition`.

While wiring the chart controls to reload when the source changes, this also fixes the
adjacent, already-known bug from issue #6: today, changing the source select does not reload
the column/filter/sort lists, so the first save after switching source always fails
validation. The chart controls need that same reload wiring to show the right columns per
source, so both get fixed by one piece of JS, not two.

## 8. What changes in code

- **`fridgesheet/web/views.py`**: `ChartSpec`, `ChartData`, `ChartSeries`, `CHART_TYPES`,
  `BUCKETS`, `MAX_CHART_POINTS`; `Definition.chart`, `.date_from`, `.date_to`; the `"custom"`
  `WINDOWS` entry; `validate()` additions; `window_end`, `_on_or_before`; the chart-building
  step in `build()`; `Rendered.chart`, `.chart_note`; `chart_config()`.
- **`fridgesheet/dates.py`**: `week_start()`, `month_start()` (the latter new, the former
  promoted out of `trends.py`'s private `_monday`).
- **`fridgesheet/web/stores/trends.py`**: `_monday` calls become `dates.week_start` — no
  behavior change, just the dedup `week_start`'s promotion makes possible.
- **`fridgesheet/chart_render.py`** (new): `render_chart_png()`.
- **`fridgesheet/sheet.py`**: `build_table_pdf(..., chart_png: bytes | None = None)`.
- **`fridgesheet/reports/view.py`**: calls `chart_render` when `d.chart` is set; catches and
  notes failure per section 6.
- **`fridgesheet/web/routes/reports.py`**: `definition_from_form()` reads the new fields; a
  chart-JSON endpoint (or field) for the live preview.
- **`fridgesheet/web/templates/report_builder.html`**: chart controls, custom-range inputs,
  the source-change reload fix.
- **`fridgesheet/web/templates/_report_preview.html`, `report_view.html`**: a chart container
  using the existing `data-chart`/`data-kind` mechanism.
- **`fridgesheet/web/static/`**: vendor `chart.umd.min.js`.
- **`fridgesheet/web/static/app.js`**: a `report` branch in `attachCharts`.

## 9. Testing

- `ChartSpec`/`Definition` validate() and JSON round-trip: every rule in section 3, including
  `stacked_bar` requiring `series`, and a chart's `x` rejected when it isn't a date column.
- Bucketing/aggregation, pure Python, no browser: day/week/month boundaries; average-per-bucket
  vs count-per-bucket; zero-fill for bar/stacked_bar vs sparse points for line;
  `MAX_CHART_POINTS` truncation and its note.
- Custom date range, extending `tests/test_report_window.py`: both ends inclusive; validate()
  errors for missing or reversed dates; each of items/grades/changes respects the end bound.
- `chart_render.render_chart_png`: a real-browser test (using the already-bundled Chromium,
  same as existing Playwright-backed tests) asserting the PNG decodes at the requested size; a
  fault-injection test asserting `ViewReport.build()` still succeeds with the fallback note
  when rendering fails.
- Builder page test: chart controls and the custom-range inputs appear/reset correctly when
  source or window change.
- A PDF-structure check (existing `pdf_text`/poppler tooling, or checking for an embedded
  image object) that a chart-bearing report's PDF actually contains the chart, and a
  table-only report's does not.

## 10. Delivery sequencing

Charts (sections 3, 5, 6, 7) and the custom date range (section 4) are independently useful
and independently shippable — a plan may split them into two PRs. Both touch `views.py`'s
`Definition`/`validate()`/`build()`, so if split, they must land sequentially (rebase the
second onto the first), not as two concurrently open PRs against the same functions.

## 11. Out of scope

Pie charts and any chart type beyond line/bar/stacked-bar. Per-column date filter operators
(before/after/between) beyond the one custom range. Chart data in CSV/JSON export — those
stay row data only. Chart appearance customization (colors, legend position, multi-axis)
beyond fixed, sensible defaults. Live-updating charts — the preview redraws on refresh, like
today, not by push.

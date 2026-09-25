# Trends on the Shared Chart Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trends and the course page draw their charts through the same server-built Chart.js config the report builder uses, and uPlot leaves the codebase.

**Architecture:** The chart vocabulary (`ChartData`, `ChartSeries`, `chart_config`, `escape_for_script_tag`) moves from the report builder module into `fridgesheet/web/charts.py` and grows a time x-scale, per-series colour/emphasis, a title and stepped lines. Trends' route builds `ChartData` from the store functions it already calls and inlines each config beside a canvas through one partial that the report preview also uses. `app.js` keeps one attach function; the uPlot path, its JSON endpoints and its vendored files are deleted.

**Tech Stack:** Python 3.12, FastAPI + Jinja2 + htmx (no build step), Chart.js 4.5.1 (vendored) plus chartjs-adapter-date-fns 3.0.0 (vendored, new), Playwright's bundled Chromium for the PDF capture and the browser tests, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-trends-on-the-shared-chart-stack-design.md`

## Global Constraints

- Vendored files are committed as downloaded, their SHA-256 pinned in `fridgesheet/web/static/VENDOR.md`, and named in `.gitattributes` with `-text`.
- A chart config is plain JSON: no functions, so both the browser and `chart_render.py` can draw it.
- Chart.js stays at 4.5.1. The adapter is the only new vendored file.
- Copy stays the app's: "No grades recorded yet.", "Work due that week", "On paper", "· official".
- Tests run with `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/2c151b67/.venv/bin/python -m pytest` (the worktree has no venv of its own; `PYTHONPATH` shadows the tests package).
- One commit per task, on the branch `viberpit/main-754567a0`, ending in `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. A course or assignment name containing `</script>` reaches a Trends chart label: the page must stay intact. Pinned in Task 5 (`test_a_grade_series_label_cannot_close_the_script_tag`).
2. A household with only one refresh, or a kid with no grade points in the window, opens Trends: the sentence "No grades recorded yet." appears and no empty canvas does. Pinned in Task 5 (`test_a_kid_with_no_grade_points_gets_the_sentence_not_a_canvas`).
3. The weekly chart and the table beside it must show the same numbers in the same order, including a week where every count is zero. Pinned in Task 4 (`test_the_weekly_chart_and_the_table_beside_it_show_the_same_numbers`).
4. Week labels must be the household's dates, the same strings the table prints, not UTC's. Pinned in Task 4 (same test: labels compared to the table's cells).
5. After an upgrade a browser keeps the old `app.js`, which looks for `data-report-chart` and draws nothing. Pinned in Task 7 (`test_static_script_and_style_urls_carry_the_version`).

---

### Task 1: Move the chart vocabulary into `web/charts.py`

**Files:**
- Create: `fridgesheet/web/charts.py`
- Modify: `fridgesheet/web/views.py` (remove `ChartSeries`, `ChartData`, `_CHART_JS_TYPE`, `_SERIES_COLORS`, `escape_for_script_tag`, `chart_config`; import them from `charts`)
- Modify: `fridgesheet/chart_render.py`, `fridgesheet/web/routes/reports.py`, `fridgesheet/reports/view.py` (import from `charts`)
- Test: `tests/test_web_charts.py` (new)

**Interfaces:**
- Produces: `fridgesheet.web.charts.ChartSeries(label, points, ...)`, `ChartData(type, x_label, y_label, series, labels)`, `chart_config(data) -> dict`, `escape_for_script_tag(json_text) -> str`, `SERIES_COLORS`. `views` re-exports the four names unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_charts.py
"""One chart vocabulary for every chart the app draws: `web/charts.py`."""
from __future__ import annotations

from fridgesheet.web import charts, views


def test_the_chart_vocabulary_lives_in_charts_and_views_re_exports_it():
    assert views.ChartData is charts.ChartData and views.ChartSeries is charts.ChartSeries
    assert views.chart_config is charts.chart_config
    assert views.escape_for_script_tag is charts.escape_for_script_tag
```

- [ ] **Step 2: Run it to verify it fails**

Run: `env -u PYTHONPATH /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/2c151b67/.venv/bin/python -m pytest tests/test_web_charts.py -q`
Expected: FAIL with `ImportError: cannot import name 'charts'`.

- [ ] **Step 3: Create `charts.py` with the moved code, verbatim**

```python
# fridgesheet/web/charts.py
"""One chart vocabulary for every chart the app draws.

A `ChartData` is what a page or a report has to say; `chart_config()` turns it into the one
Chart.js `type`/`data`/`options` object that the live page (`app.js`) and the headless PDF
capture (`chart_render.py`) both draw from, so neither can disagree with the other about what
a chart looks like. The report builder (`views.py`) builds one from a report's rows; the
Trends route builds one from its stores. Nothing here reads the database.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SERIES_COLORS = ("#1f5fa8", "#b3261e", "#2e7d32", "#6b3fa0", "#b8860b", "#00707f")
_CHART_JS_TYPE = {"line": "line", "bar": "bar", "stacked_bar": "bar"}


@dataclass
class ChartSeries:
    label: str
    points: list[tuple[str, float]] = field(default_factory=list)   # (bucket label, value)


@dataclass
class ChartData:
    type: str
    x_label: str
    y_label: str
    series: list[ChartSeries] = field(default_factory=list)
    labels: tuple[str, ...] = ()


def escape_for_script_tag(json_text: str) -> str:
    """(docstring moved verbatim from views.py)"""
    return (json_text.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
                     .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def chart_config(data: ChartData) -> dict:
    """(docstring moved verbatim from views.py)"""
    labels = list(data.labels)
    datasets = []
    for i, s in enumerate(data.series):
        by_label = dict(s.points)
        color = SERIES_COLORS[i % len(SERIES_COLORS)]
        datasets.append({"label": s.label, "data": [by_label.get(l) for l in labels],
                         "borderColor": color, "backgroundColor": color, "fill": False})
    stacked = data.type == "stacked_bar" and data.y_label == "Count"
    return {
        "type": _CHART_JS_TYPE[data.type],
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "animation": False,
            "scales": {
                "x": {"stacked": stacked, "title": {"display": True, "text": data.x_label}},
                "y": {"stacked": stacked, "title": {"display": True, "text": data.y_label}},
            },
        },
    }
```

In `views.py`: delete the `ChartSeries`/`ChartData` dataclasses, `_CHART_JS_TYPE`, `_SERIES_COLORS`, `escape_for_script_tag` and `chart_config`; add after the existing imports:

```python
from .charts import ChartData, ChartSeries, chart_config, escape_for_script_tag  # noqa: F401  re-exported: the builder's own tests read them here
```

In `chart_render.py`: `from .web import charts` and `charts.escape_for_script_tag(...)`; fix the two docstrings that say `views.chart_config` to say `charts.chart_config`. In `routes/reports.py` `_chart_json`: `charts.escape_for_script_tag(json.dumps(charts.chart_config(rendered.chart)))` with `from .. import charts`. In `reports/view.py`: `charts.chart_config(rendered.chart)` with `from ..web import charts`.

- [ ] **Step 4: Run the new test and the suites that touched the moved code**

Run: `... -m pytest tests/test_web_charts.py tests/test_report_chart.py tests/test_web_reports_page.py tests/test_chart_render.py tests/test_report_view.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/charts.py fridgesheet/web/views.py fridgesheet/chart_render.py fridgesheet/web/routes/reports.py fridgesheet/reports/view.py tests/test_web_charts.py
git commit -m "The chart vocabulary moves out of the report builder into web/charts.py; views re-exports it"
```

---

### Task 2: A time x-scale, series colour and emphasis, a title, stepped lines; vendor the date adapter

**Files:**
- Create: `fridgesheet/web/static/chartjs-adapter-date-fns.bundle.min.js` (downloaded), `fridgesheet/web/templates/_chart_scripts.html`
- Modify: `fridgesheet/web/charts.py`, `fridgesheet/chart_render.py`, `fridgesheet/web/static/VENDOR.md`, `.gitattributes`, `fridgesheet/web/templates/report_builder.html:4`, `fridgesheet/web/templates/report_view.html:9`
- Test: `tests/test_web_charts.py`, `tests/test_chart_render.py`, `tests/test_web_reports_page.py`

**Interfaces:**
- Produces: `ChartSeries(label, points, color: str | None = None, emphasis: bool = False)`; `ChartData(..., title: str = "", x_scale: str = "category", stepped: bool = False)`; `charts.COUNT_LABEL == "Count"`; `charts.OUTCOME_COLORS` keyed by outcome name; `_chart_scripts.html` (the two `<script defer>` tags every Chart.js page includes).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_web_charts.py
def test_a_time_scale_chart_carries_points_as_x_y_and_no_labels():
    data = charts.ChartData(type="line", x_label="Seen", y_label="Grade", x_scale="time", stepped=True,
                            title="Grade per class",
                            series=[charts.ChartSeries(label="Math (HAC average) · official", emphasis=True,
                                                       points=[(1757937600000, 88.0), (1758542400000, 91.0)])])
    cfg = charts.chart_config(data)
    assert "labels" not in cfg["data"]
    ds = cfg["data"]["datasets"][0]
    assert ds["data"] == [{"x": 1757937600000, "y": 88.0}, {"x": 1758542400000, "y": 91.0}]
    assert ds["stepped"] == "after" and ds["borderWidth"] == 3
    assert cfg["options"]["scales"]["x"]["type"] == "time"
    assert cfg["options"]["scales"]["x"]["time"]["minUnit"] == "day"
    assert cfg["options"]["plugins"]["title"] == {"display": True, "text": "Grade per class"}


def test_a_series_colour_is_its_own_when_given_and_positional_otherwise():
    data = charts.ChartData(type="stacked_bar", x_label="Week of", y_label=charts.COUNT_LABEL, labels=("9/8",),
                            series=[charts.ChartSeries(label="Not done", color=charts.OUTCOME_COLORS["not_done"], points=[("9/8", 2.0)]),
                                    charts.ChartSeries(label="Other", points=[("9/8", 1.0)])])
    cfg = charts.chart_config(data)
    assert cfg["data"]["datasets"][0]["borderColor"] == "#b3261e"
    assert cfg["data"]["datasets"][1]["borderColor"] == charts.SERIES_COLORS[1]
    assert cfg["options"]["scales"]["x"]["stacked"] is True


def test_a_category_chart_is_responsive_with_no_title_and_no_stepping():
    cfg = charts.chart_config(charts.ChartData(type="bar", x_label="Due", y_label="Count", labels=("9/8",),
                                               series=[charts.ChartSeries(label="Count", points=[("9/8", 1.0)])]))
    assert cfg["options"]["responsive"] is True and cfg["options"]["maintainAspectRatio"] is False
    assert cfg["options"]["plugins"]["title"]["display"] is False
    assert "stepped" not in cfg["data"]["datasets"][0] and "borderWidth" not in cfg["data"]["datasets"][0]
```

```python
# append to tests/test_chart_render.py
def test_render_chart_png_draws_a_time_scale_chart(tmp_path):
    """A `time` x-scale needs the vendored date adapter loaded beside Chart.js; without it
    Chart.js throws before drawing and the ready flag never sets."""
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    config = {"type": "line",
              "data": {"datasets": [{"label": "HAC", "data": [{"x": 1757937600000, "y": 88.0},
                                                               {"x": 1758542400000, "y": 91.0}]}]},
              "options": {"scales": {"x": {"type": "time", "time": {"minUnit": "day"}}}}}
    png = chart_render.render_chart_png(config, width_px=400, height_px=200, timeout_ms=4000)
    img = Image.open(io.BytesIO(png))
    assert img.convert("L").getextrema() != (255, 255)
```

```python
# append to tests/test_web_reports_page.py
def test_every_chart_page_loads_chart_js_and_its_date_adapter_through_one_partial():
    """Chart.js and the date adapter are one pair: a page that has one without the other
    draws category charts but throws on a time scale."""
    from pathlib import Path
    templates = Path(views.__file__).parent / "templates"
    partial = (templates / "_chart_scripts.html").read_text(encoding="utf-8")
    assert partial.index("chart.umd.min.js") < partial.index("chartjs-adapter-date-fns.bundle.min.js")
    for p in templates.glob("*.html"):
        if p.name != "_chart_scripts.html":
            assert "chart.umd.min.js" not in p.read_text(encoding="utf-8"), p.name
```

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_web_charts.py tests/test_chart_render.py tests/test_web_reports_page.py -q -k "time_scale or colour or responsive or adapter"`
Expected: the three `charts` tests FAIL with `TypeError: unexpected keyword argument` (`x_scale`, `color`) / `KeyError: 'responsive'`; the render test FAILS with a Playwright timeout; the template test FAILS with `FileNotFoundError` for `_chart_scripts.html`.

- [ ] **Step 3: Vendor the adapter and register it**

```bash
cd fridgesheet/web/static
curl -sSL -o chartjs-adapter-date-fns.bundle.min.js https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js
sha256sum chartjs-adapter-date-fns.bundle.min.js
```

Add to `VENDOR.md` (the hash is the one `sha256sum` printed):

```
| chartjs-adapter-date-fns.bundle.min.js | https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js | 3.0.0 | MIT | `<sha256>` |
```

Add to `.gitattributes`: `fridgesheet/web/static/chartjs-adapter-date-fns.bundle.min.js -text`

Create `_chart_scripts.html`:

```html
{# Chart.js and its date adapter, one pair: every page that draws a chart includes this once.
   `app.js` (base.html, deferred) runs first; both of these are deferred too, and deferred
   scripts run in document order, so a chart's first draw at DOMContentLoaded sees both. #}
<script src="/static/chart.umd.min.js" defer></script>
<script src="/static/chartjs-adapter-date-fns.bundle.min.js" defer></script>
```

Replace `report_builder.html` line 4 and `report_view.html` line 9 with `{% include "_chart_scripts.html" %}`.

In `chart_render.py`:

```python
_ADAPTER = "chartjs-adapter-date-fns.bundle.min.js"

def _chart_js() -> str:
    """Chart.js and its date adapter, in that order -- the same pair `_chart_scripts.html`
    gives the browser, so a `time` x-scale draws on paper exactly as it does on the page."""
    return "\n;".join((_STATIC / name).read_text(encoding="utf-8")
                      for name in ("chart.umd.min.js", _ADAPTER))
```

- [ ] **Step 4: Grow the vocabulary in `charts.py`**

```python
COUNT_LABEL = "Count"
#: Outcome colours, as the tables' `warn` class and docs/outcomes.md agree: the same strokes
#: the Trends chart has always used.
OUTCOME_COLORS = {"on_time": "#2e7d32", "late": "#b8860b", "not_done": "#b3261e",
                  "done_offline": "#1f5fa8", "unknown": "#8a6d3b"}


@dataclass
class ChartSeries:
    label: str
    #: (bucket label, value) on a category axis; (epoch milliseconds, value) on a time axis.
    points: list[tuple] = field(default_factory=list)
    color: str | None = None        # None: the next SERIES_COLORS entry, by position
    emphasis: bool = False          # drawn thicker -- the official grade source


@dataclass
class ChartData:
    type: str
    x_label: str
    y_label: str
    series: list[ChartSeries] = field(default_factory=list)
    labels: tuple[str, ...] = ()
    title: str = ""
    x_scale: str = "category"       # "time": each series carries its own (ms, value) points
    stepped: bool = False           # a line holds its value until the next point


def chart_config(data: ChartData) -> dict:
    time_axis = data.x_scale == "time"
    labels = list(data.labels)
    datasets = []
    for i, s in enumerate(data.series):
        color = s.color or SERIES_COLORS[i % len(SERIES_COLORS)]
        if time_axis:
            values = [{"x": t, "y": v} for t, v in s.points]
        else:
            by_label = dict(s.points)
            values = [by_label.get(l) for l in labels]
        ds = {"label": s.label, "data": values, "borderColor": color, "backgroundColor": color, "fill": False}
        if s.emphasis:
            ds["borderWidth"] = 3
        if data.stepped:
            ds["stepped"] = "after"     # hold the value until the next observation
        datasets.append(ds)
    stacked = data.type == "stacked_bar" and data.y_label == COUNT_LABEL
    x: dict = {"stacked": stacked, "title": {"display": True, "text": data.x_label}}
    if time_axis:
        # No `unit`: Chart.js picks day/week/month for the span; `minUnit` keeps it from
        # showing hours. Formats are date-fns tokens, applied in the browser's own zone.
        x.update({"type": "time", "time": {"minUnit": "day", "tooltipFormat": "M/d h:mm a",
                                             "displayFormats": {"day": "M/d", "week": "M/d", "month": "MMM yyyy"}}})
    chart_data = {"datasets": datasets} if time_axis else {"labels": labels, "datasets": datasets}
    return {
        "type": _CHART_JS_TYPE[data.type],
        "data": chart_data,
        "options": {
            "animation": False,
            "responsive": True, "maintainAspectRatio": False,     # the holder's height is the chart's
            "plugins": {"title": {"display": bool(data.title), "text": data.title}},
            "scales": {"x": x, "y": {"stacked": stacked, "title": {"display": True, "text": data.y_label}}},
        },
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `... -m pytest tests/test_web_charts.py tests/test_chart_render.py tests/test_report_chart.py tests/test_web_reports_page.py -q`
Expected: all PASS (the existing `chart_config` tests keep passing: category charts still carry `labels`).

- [ ] **Step 6: Commit**

```bash
git add -A fridgesheet/web/static fridgesheet/web/charts.py fridgesheet/chart_render.py fridgesheet/web/templates .gitattributes tests
git commit -m "A chart may have a time axis, a title, stepped lines and a series with its own colour or emphasis; the date adapter is vendored beside Chart.js"
```

---

### Task 3: One canvas partial, one attach function, one holder style

**Files:**
- Create: `fridgesheet/web/templates/_chart_canvas.html`
- Modify: `fridgesheet/web/templates/_report_preview.html:8-13`, `fridgesheet/web/static/app.js` (the `attachReportCharts` block), `fridgesheet/web/static/app.css` (add `.chart-holder`)
- Test: `tests/test_web_reports_page.py:319,328`, `tests/test_web_report_chart_lifecycle.py`

**Interfaces:**
- Produces: `{% with config = <escaped json>, height = <px>, label = <sentence> %}{% include "_chart_canvas.html" %}{% endwith %}`; the canvas carries `data-chart-canvas`; `app.js` draws every `[data-chart-canvas]` from the `[data-chart-config]` beside it.

- [ ] **Step 1: Write the failing tests**

Change the two existing assertions in `tests/test_web_reports_page.py`: `"data-report-chart" in body` becomes `"data-chart-canvas" in body` (line 319) and `"data-report-chart" not in body` becomes `"data-chart-canvas" not in body` (line 328). Add:

```python
def test_the_report_view_draws_its_chart_through_the_shared_canvas_partial(tmp_path):
    seed(tmp_path).close()
    c = _client(tmp_path)
    rid = _save(tmp_path, source="items", columns=["kid", "name", "due"],
               chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    body = c.get(f"/reports/{rid}/view").text
    assert '<div class="chart-holder" style="height: 260px">' in body
    assert '<canvas data-chart-canvas role="img" aria-label="Mine, as a chart"></canvas>' in body
```

In `tests/test_web_report_chart_lifecycle.py`, `_preview_partial()` becomes the partial's output:

```python
def _preview_partial() -> str:
    """What `_chart_canvas.html` renders."""
    return ('<div class="chart-holder" style="height: 260px">'
            '<canvas data-chart-canvas role="img" aria-label="probe, as a chart"></canvas>'
            f'<script type="application/json" data-chart-config>{charts.escape_for_script_tag(json.dumps(CONFIG))}</script>'
            '</div>')
```

and every `[data-report-chart]` selector in that file becomes `[data-chart-canvas]` (`from fridgesheet.web import charts` replaces the `views` import).

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_web_reports_page.py tests/test_web_report_chart_lifecycle.py -q`
Expected: the two changed assertions and the new test FAIL (`data-chart-canvas` absent); the lifecycle test FAILS on `dataset.drawn` (app.js still looks for `data-report-chart`).

- [ ] **Step 3: Write the partial, switch the preview to it, rename the attribute in app.js, style the holder**

```html
{# fridgesheet/web/templates/_chart_canvas.html
   One chart. `config` is charts.chart_config()'s JSON, already passed through
   charts.escape_for_script_tag(); app.js draws it into the canvas (attachCharts). `height` is
   the CSS pixels the holder gives the chart -- Chart.js sizes to its parent, so the height
   lives here, not on the canvas. `label` is the one sentence a screen reader gets. #}
<div class="chart-holder" style="height: {{ height|default(260) }}px"><canvas data-chart-canvas role="img" aria-label="{{ label }}"></canvas><script type="application/json" data-chart-config>{{ config | safe }}</script></div>
```

`_report_preview.html` lines 8-13 become:

```html
  {% if rendered.chart %}
  {% with config = chart_json, height = 260, label = rendered.title ~ ", as a chart" %}{% include "_chart_canvas.html" %}{% endwith %}
  {% endif %}
```

`app.js`: in the report-chart block, `root.querySelectorAll("[data-report-chart]")` becomes `root.querySelectorAll("[data-chart-canvas]")`; the comment "Report charts: ..." becomes "Config charts: `charts.chart_config()`'s output, inlined as JSON next to a `<canvas>` by `_chart_canvas.html`." (The function keeps its name until Task 6 frees `attachCharts`.)

`app.css`, next to the `.chart` rule:

```css
/* Chart.js sizes its canvas to this holder (`responsive`, no aspect ratio), so the holder's
   inline height from `_chart_canvas.html` is the chart's height; `position: relative` is
   what Chart.js's own resize detection asks of a chart's parent. */
.chart-holder { position: relative; background: var(--paper); border: 1px solid var(--rule); border-radius: 8px; padding: 8px; margin: 8px 0; }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `... -m pytest tests/test_web_reports_page.py tests/test_web_report_chart_lifecycle.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates/_chart_canvas.html fridgesheet/web/templates/_report_preview.html fridgesheet/web/static/app.js fridgesheet/web/static/app.css tests/test_web_reports_page.py tests/test_web_report_chart_lifecycle.py
git commit -m "One canvas partial for every inlined chart; the report preview uses it"
```

---

### Task 4: The weekly outcomes chart is a stacked bar built on the server

**Files:**
- Modify: `fridgesheet/web/routes/trends.py` (add `WEEKLY_SERIES`, `weekly_chart`, `chart_json`; remove `weekly_json`), `fridgesheet/web/templates/trends.html:49-53`
- Modify: `tests/web_fixtures.py` (add `chart_configs`)
- Test: `tests/test_web_trends_page.py` (rewrite `test_weekly_json_is_parallel_arrays`, `test_weeks_parameter_is_bounded`; add two)

**Interfaces:**
- Consumes: `charts.ChartData`, `charts.ChartSeries`, `charts.OUTCOME_COLORS`, `charts.COUNT_LABEL`, `_chart_canvas.html`.
- Produces: `routes.trends.weekly_chart(rows: list[trends.WeekOutcomes], now: datetime) -> charts.ChartData`; `routes.trends.chart_json(data: charts.ChartData) -> str`; `tests.web_fixtures.chart_configs(body: str) -> list[dict]`.

- [ ] **Step 1: Add the fixture helper and write the failing tests**

```python
# tests/web_fixtures.py, near the top
import json, re
CHART_CONFIG = re.compile(r'<script type="application/json" data-chart-config>(.*?)</script>', re.S)

def chart_configs(body: str) -> list[dict]:
    """Every inlined chart config on a page, in page order, decoded (the `\\u003c` escapes
    `charts.escape_for_script_tag` writes are plain JSON to `json.loads`)."""
    return [json.loads(m) for m in CHART_CONFIG.findall(body)]
```

Replace `test_weekly_json_is_parallel_arrays` and `test_weeks_parameter_is_bounded` in `tests/test_web_trends_page.py` with:

```python
WEEKLY_LABELS = ["On time", "Late", "Not done", "On paper", "Unknown"]      # the table's column order


def weekly_config(body: str) -> dict:
    return next(c for c in chart_configs(body) if c["options"]["plugins"]["title"]["text"] == "Work due that week")


def test_the_weekly_chart_is_a_stacked_bar_in_the_tables_column_order(tmp_path):
    history(tmp_path).close()
    cfg = weekly_config(app_for(tmp_path).get("/trends?weeks=4").text)
    assert cfg["type"] == "bar" and cfg["options"]["scales"]["x"]["stacked"] is True
    assert [d["label"] for d in cfg["data"]["datasets"]] == WEEKLY_LABELS
    assert len(cfg["data"]["labels"]) == 4
    colors = {d["label"]: d["borderColor"] for d in cfg["data"]["datasets"]}
    assert colors["Not done"] == charts.OUTCOME_COLORS["not_done"] and colors["On time"] == charts.OUTCOME_COLORS["on_time"]


def test_the_weekly_chart_and_the_table_beside_it_show_the_same_numbers(tmp_path):
    """One definition for every number (#150): the chart's labels are the table's "Week of"
    cells -- the household's dates, not UTC's -- and each dataset is one table column."""
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends?weeks=4").text
    cfg = weekly_config(body)
    rows = re.findall(r"<tr><td>([^<]*)</td><td>(\d+)</td><td>(\d+)</td><td[^>]*>(\d+)</td><td>(\d+)</td><td[^>]*>(\d+)</td></tr>", body)
    assert len(rows) == 4
    assert [r[0] for r in rows] == cfg["data"]["labels"]
    for i, _ in enumerate(WEEKLY_LABELS):
        assert cfg["data"]["datasets"][i]["data"] == [float(r[i + 1]) for r in rows]


def test_weeks_parameter_is_bounded(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    assert len(weekly_config(c.get("/trends?weeks=200").text)["data"]["labels"]) == 52     # clamped
    assert len(weekly_config(c.get("/trends?weeks=0").text)["data"]["labels"]) == 1
    assert len(weekly_config(c.get("/trends?weeks=nonsense").text)["data"]["labels"]) == 8  # the default


def test_the_weekly_json_endpoint_is_gone(tmp_path):
    history(tmp_path).close()
    assert app_for(tmp_path).get("/trends/weekly.json?weeks=4").status_code == 404
```

Add `from fridgesheet.web import charts` and `chart_configs` to the file's imports.

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_web_trends_page.py -q -k "weekly or weeks_parameter_is_bounded"`
Expected: FAIL with `StopIteration` (no inlined config on the page) and `assert 200 == 404`.

- [ ] **Step 3: Build the chart in the route and inline it**

```python
# fridgesheet/web/routes/trends.py -- add imports and helpers
import json
from ... import dates
from .. import charts, outcomes

#: The weekly chart's series, in the table's column order; the labels are the table's headers.
WEEKLY_SERIES = (("on_time", "On time"), ("late", "Late"), ("not_done", "Not done"),
                 ("done_offline", "On paper"), ("unknown", "Unknown"))


def weekly_chart(rows: list[trends.WeekOutcomes], now: datetime) -> charts.ChartData:
    """One bar per week, one segment per outcome -- the table beside it, drawn. Labels are
    the same `md_year` strings the report charts use, built here in the household's zone,
    so the chart cannot drift a day from the "Week of" column (the uPlot chart had to
    rebuild local midnight by hand in the browser to avoid exactly that)."""
    labels = tuple(dates.md_year(w.week_start, now) for w in rows)
    series = [charts.ChartSeries(label=label, color=charts.OUTCOME_COLORS[key],
                                 points=[(l, float(getattr(w, key))) for l, w in zip(labels, rows)])
              for key, label in WEEKLY_SERIES]
    return charts.ChartData(type="stacked_bar", x_label="Week of", y_label=charts.COUNT_LABEL,
                            series=series, labels=labels, title="Work due that week")


def chart_json(data: charts.ChartData) -> str:
    """`chart_config()`'s output, safe to inline inside `_chart_canvas.html`'s script tag."""
    return charts.escape_for_script_tag(json.dumps(charts.chart_config(data)))
```

In `page()`, pass `weekly_json=chart_json(weekly_chart(week_rows, now))` to `render`. Delete the `weekly_json` route and its `JSONResponse` import if nothing else uses it (the grades route still does until Task 5).

`trends.html` lines 49-53 become:

```html
<h3>How the work due each week came out</h3>
<p class="muted">By the week it was <em>due</em>, not the week a refresh noticed it — so the year so far is here from the first day. One definition for every number: <a href="https://github.com/steiner385/fridgesheet/blob/main/docs/outcomes.md">docs/outcomes.md</a>.</p>
{% with config = weekly_json, height = 220, label = "Work due each week, by how it came out; the table below has the numbers" %}{% include "_chart_canvas.html" %}{% endwith %}
```

Add `{% include "_chart_scripts.html" %}` under `<h2>Trends</h2>` (the uPlot lines stay until Task 6).

- [ ] **Step 4: Run the Trends tests to verify they pass**

Run: `... -m pytest tests/test_web_trends_page.py tests/test_changes_trends_residuals.py -q`
Expected: the four new/rewritten tests PASS; `test_the_weekly_chart_draws_every_series_the_table_beside_it_shows` now FAILS (it fetched `weekly.json`) -- delete it here, its replacement is `test_the_weekly_chart_and_the_table_beside_it_show_the_same_numbers`. Everything else PASSES.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/trends.py fridgesheet/web/templates/trends.html tests/web_fixtures.py tests/test_web_trends_page.py
git commit -m "The weekly outcomes chart is a stacked bar the server builds from the table's own rows; weekly.json goes"
```

---

### Task 5: Grade lines on a time axis, on Trends and the course page

**Files:**
- Modify: `fridgesheet/web/routes/trends.py` (add `grade_chart`; rewrite `page()`; remove `grades_json`, `_explicit_weeks`), `fridgesheet/web/routes/kid.py:95-127`, `fridgesheet/web/templates/trends.html:16,34-48`, `fridgesheet/web/templates/course.html:36-40`
- Test: `tests/test_web_trends_page.py`, `tests/test_web_official_grade.py`

**Interfaces:**
- Consumes: `trends.GradeSeries(course_id, course_short, source, label, points: list[(datetime, float)], official)`.
- Produces: `routes.trends.grade_chart(series: list[trends.GradeSeries], *, title: str) -> charts.ChartData | None` (None when `series` is empty); Trends context `grade_charts: list[tuple[str, str | None]]` of (kid key, config json or None) and `has_grades: bool`; course context `grade_chart_json: str | None`.

- [ ] **Step 1: Write the failing tests**

Replace `test_grades_json_has_one_series_per_course_and_source`, `test_kid_filter_applies_to_page_and_json`, `test_weeks_parameter_also_narrows_the_grade_chart`, `test_grades_json_with_no_weeks_returns_all_history`, `test_weeks_selector_url_carries_the_chosen_weeks_for_the_grade_chart_too`, `test_a_course_filter_that_is_not_a_course_matches_nothing` and `test_course_page_gains_a_grade_chart` in `tests/test_web_trends_page.py` with:

```python
def grade_configs(body: str) -> list[dict]:
    return [c for c in chart_configs(body) if c["options"]["scales"]["x"].get("type") == "time"]


def test_the_grade_chart_has_one_stepped_series_per_course_and_source_on_a_time_axis(tmp_path):
    history(tmp_path).close()
    cfgs = grade_configs(app_for(tmp_path).get("/trends?kid=Alex").text)
    assert len(cfgs) == 1 and cfgs[0]["type"] == "line"
    labels = {d["label"] for d in cfgs[0]["data"]["datasets"]}
    assert "Honors English 9 (HAC average) · official" in labels and "Honors English 9 (Canvas current)" in labels
    hac = next(d for d in cfgs[0]["data"]["datasets"] if d["label"].startswith("Honors English 9 (HAC"))
    assert [p["y"] for p in hac["data"]] == [85.0, 88.0]
    assert all(isinstance(p["x"], int) for p in hac["data"]) and hac["data"][0]["x"] < hac["data"][1]["x"]
    assert hac["stepped"] == "after" and hac["borderWidth"] == 3
    assert cfgs[0]["options"]["plugins"]["title"]["text"] == "Grade per class"


def test_the_all_kids_view_draws_one_titled_grade_chart_per_kid(tmp_path):
    """Three kids' classes in one legend was 28 series (#40 item 12)."""
    history(tmp_path).close()
    c = app_for(tmp_path)
    everyone = grade_configs(c.get("/trends").text)
    assert len(everyone) >= 2
    assert "Alex — grade per class" in {cfg["options"]["plugins"]["title"]["text"] for cfg in everyone}
    assert len(grade_configs(c.get("/trends?kid=Sam").text)) == 1


def test_kid_filter_applies_to_the_page_and_its_chart(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/trends?kid=Sam").text
    assert "Science 7" in body and "Honors English 9" not in body
    assert all("Science 7" in d["label"] for cfg in grade_configs(body) for d in cfg["data"]["datasets"])
    assert c.get("/trends?kid=Nobody").status_code == 404


def test_weeks_parameter_also_narrows_the_grade_chart(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)

    def total_points(weeks):
        return sum(len(d["data"]) for cfg in grade_configs(c.get(f"/trends?weeks={weeks}").text) for d in cfg["data"]["datasets"])

    assert total_points(1) < total_points(16)


def test_the_course_page_chart_shows_all_history_not_a_default_window(tmp_path):
    """`course.html`'s chart has no Weeks selector and must not silently drop old grades."""
    old_now = NOW - timedelta(weeks=20)                            # ~5 months back
    old_snap = snapshot()
    old_snap["students"]["Alex"]["hac"]["classes"][0]["marking_period_avg"] = 70.0
    old_snap["fetched_at"] = old_now.isoformat()
    seed(tmp_path, old_snap, now=old_now).close()                  # the one old observation
    conn = history(tmp_path)                                       # the standard 3-day fixture, layered on top
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    conn.close()
    cfgs = grade_configs(app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text)
    assert len(cfgs) == 1 and cfgs[0]["options"]["plugins"]["title"]["text"] == "This class"
    points = [p for d in cfgs[0]["data"]["datasets"] for p in d["data"]]
    eight_weeks_ago = (NOW - timedelta(weeks=8)).timestamp() * 1000
    assert any(p["x"] < eight_weeks_ago for p in points)
    assert all("Honors English 9" in d["label"] for d in cfgs[0]["data"]["datasets"])   # this course, not the house


def test_a_kid_with_no_grade_points_in_the_window_gets_the_sentence_not_a_canvas(tmp_path):
    """The first refresh records a grade point, so an empty window is the way to have none:
    one week, looked at three weeks after the only refresh."""
    seed(tmp_path).close()
    body = app_for(tmp_path, now=NOW + timedelta(weeks=3)).get("/trends?kid=Alex&weeks=1").text
    assert grade_configs(body) == [] and "No grades recorded yet." in body


def test_a_grade_series_label_cannot_close_the_script_tag():
    from fridgesheet.web.routes.trends import chart_json, grade_chart
    from fridgesheet.web.stores.trends import GradeSeries
    evil = GradeSeries(1, "</script><script>alert(1)</script>", "hac", "</script> (HAC average)",
                       points=[(NOW, 90.0)], official=True)
    text = chart_json(grade_chart([evil], title="Grade per class"))
    assert "</script>" not in text and "\\u003c/script" in text


def test_the_grades_json_endpoint_is_gone(tmp_path):
    history(tmp_path).close()
    assert app_for(tmp_path).get("/trends/grades.json").status_code == 404
```

In `tests/test_web_official_grade.py`, replace the two `grades.json` tests:

```python
def _grade_labels(body: str) -> set[str]:
    return {d["label"] for c in chart_configs(body) if c["options"]["scales"]["x"].get("type") == "time"
            for d in c["data"]["datasets"]}


def test_the_trends_grade_chart_marks_the_official_series(tmp_path):
    history(tmp_path).close()
    labels = _grade_labels(client(tmp_path, "").get("/trends").text)
    assert "Honors English 9 (HAC average) · official" in labels and "Honors English 9 (Canvas current)" in labels
    labels = _grade_labels(client(tmp_path, CANVAS_GRADES).get("/trends").text)
    assert "Honors English 9 (Canvas current) · official" in labels and "Honors English 9 (HAC average)" in labels


def test_only_one_twin_is_official_when_a_rule_names_one_twin(tmp_path):
    """Review finding: grade_series resolved each twin by its own name, so a rule matching only the
    Canvas name made both the Canvas and the HAC series official."""
    history(tmp_path).close()
    labels = _grade_labels(client(tmp_path, '[[sources.rule]]\ncourse = "Hoch"\ngrades = "canvas"\n').get("/trends").text)
    assert "Honors English 9 (Canvas current) · official" in labels and "Honors English 9 (HAC average)" in labels
```

(`from tests.web_fixtures import chart_configs` joins that file's imports.)

- [ ] **Step 2: Run them to verify they fail**

Run: `... -m pytest tests/test_web_trends_page.py tests/test_web_official_grade.py -q`
Expected: every new test FAILS (`grade_configs` empty, `ImportError: grade_chart`, `200 == 404`); the old uPlot-holder tests still pass for now.

- [ ] **Step 3: Build the grade charts in the routes and inline them**

```python
# fridgesheet/web/routes/trends.py
from ..stores import students as students_store, trends


def grade_chart(series: list[trends.GradeSeries], *, title: str) -> charts.ChartData | None:
    """One stepped line per course and source, each observation at the moment it was seen:
    `grade_observations` only holds rows where something changed, so a line holds its value
    until the next point. The official source (sources.py) is drawn thicker and says so in its
    label, the words the Changes feed uses. None when there is nothing to draw -- the page
    prints its sentence rather than an empty chart."""
    if not series:
        return None
    return charts.ChartData(
        type="line", x_label="Seen", y_label="Grade", x_scale="time", stepped=True, title=title,
        series=[charts.ChartSeries(label=s.label + (" · official" if s.official else ""), emphasis=s.official,
                                   points=[(int(t.timestamp() * 1000), v) for t, v in s.points])
                for s in series])
```

`page()` becomes:

```python
@router.get("/trends")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    student = _student(conn, request)
    sid = student["id"] if student else None
    weeks = _weeks(request)
    now, prefs = state.now(), state.sources()
    week_rows = trends.weekly_outcomes(conn, student_id=sid, weeks=weeks, now=now, prefs=prefs)
    # One grade chart per kid, not one for the house (#40 item 12); the caption's course list
    # covers the same window the charts show, so it is never broader than what is drawn.
    since = _since(weeks, now)
    kids = [student] if student else students_store.visible(conn)
    per_kid = [(s["key"], trends.grade_series(conn, student_id=s["id"], since=since, prefs=prefs)) for s in kids]

    def title(key: str) -> str:
        return "Grade per class" if student else f"{state.settings.nicknames.get(key, key)} — grade per class"

    return render(request, conn, "trends.html", current="trends",
                  kid=student["key"] if student else None, weeks=weeks,
                  course_names=sorted({gs.course_short for _, series in per_kid for gs in series}),
                  has_grades=any(series for _, series in per_kid),
                  grade_charts=[(key, chart_json(grade_chart(series, title=title(key))) if series else None)
                                for key, series in per_kid],
                  weekly_json=chart_json(weekly_chart(week_rows, now)),
                  week_rows=week_rows,
                  record=_record(conn, student, now=now, rules=state.rules(), prefs=prefs),
                  longest=trends.open_days(conn, student_id=sid, now=now, prefs=prefs))
```

Delete `grades_json`, `_explicit_weeks`, and the `JSONResponse` import; update the module docstring to "The page builds every chart's config itself (`charts.chart_config`) and inlines it."

`trends.html`: line 16 becomes `{% set empty = not has_grades and not longest and record.on_time_rate is none %}`; lines 34-48 become:

```html
<h3>Grades</h3>
<p class="muted">{{ course_names | join(", ") if course_names else "No grades recorded yet." }}</p>
{% for key, cfg in grade_charts %}
{% if cfg %}{% with config = cfg, height = 260, label = (key | nickname) ~ ": each class's grade over time, one line per class and source" %}{% include "_chart_canvas.html" %}{% endwith %}
{% elif kid or grade_charts | length > 1 %}<p class="muted">{{ key | nickname }}: no grades recorded yet.</p>{% endif %}
{% endfor %}
```

`kid.py` `course()`: add `from .trends import chart_json, grade_chart` and `from ..stores import trends`; before `render`:

```python
    # This course's own lines only (the twin has its own page): the old grades.json filter.
    mine = [gs for gs in trends.grade_series(conn, student_id=s["id"], prefs=prefs) if gs.course_id == course_id]
    chart = grade_chart(mine, title="This class")
```

and pass `grade_chart_json=chart_json(chart) if chart else None`. `course.html` lines 36-40 become:

```html
{% include "_chart_scripts.html" %}
{% if grade_chart_json %}{% with config = grade_chart_json, height = 220, label = "This class's grade over time" %}{% include "_chart_canvas.html" %}{% endwith %}
{% else %}<p class="muted">No grades recorded yet.</p>{% endif %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `... -m pytest tests/test_web_trends_page.py tests/test_web_official_grade.py tests/test_web_pages.py -q`
Expected: the new tests PASS. The remaining uPlot tests (`test_page_renders_chart_holders_and_the_summary`, `test_trends_page_asks_for_a_taller_grade_chart_than_the_weekly_one`, `test_course_page_chart_holder_also_carries_a_height`, `test_the_all_kids_view_draws_one_grade_chart_per_kid`) now FAIL: Task 6 removes them. Run Task 6 before committing if a green tree per commit is wanted; otherwise commit here and note it.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/routes/trends.py fridgesheet/web/routes/kid.py fridgesheet/web/templates/trends.html fridgesheet/web/templates/course.html tests/test_web_trends_page.py tests/test_web_official_grade.py
git commit -m "Grade lines keep real timing: one stepped line per class and source on a time axis, on Trends and the course page; grades.json goes"
```

---

### Task 6: uPlot leaves

**Files:**
- Delete: `fridgesheet/web/static/uplot.min.js`, `fridgesheet/web/static/uplot.min.css`, `fridgesheet/web/templates/_chart.html`
- Modify: `fridgesheet/web/static/app.js:109-248` (delete the uPlot block; rename `attachReportCharts` to `attachCharts`, `REPORT_CHARTS` to `CHARTS`, `pruneReportCharts` to `pruneCharts`), `fridgesheet/web/static/app.css` (delete `.chart`, `.chart .muted`, `.u-legend` and their comment; reword the `.shell` comment), `fridgesheet/web/static/VENDOR.md`, `.gitattributes`, `fridgesheet/web/templates/trends.html:4-5`, `docs/product/features/browser-app.md:32,44`
- Test: `tests/test_web_trends_page.py`

- [ ] **Step 1: Write the failing test and delete the dead ones**

Delete from `tests/test_web_trends_page.py`: `test_page_renders_chart_holders_and_the_summary`, `test_chart_holders_carry_their_plot_height_and_no_inline_height`, `test_trends_page_asks_for_a_taller_grade_chart_than_the_weekly_one`, `test_course_page_chart_holder_also_carries_a_height`, `test_the_all_kids_view_draws_one_grade_chart_per_kid` (Task 5's titled-per-kid test replaces it), `test_a_chart_swapped_away_during_its_fetch_is_not_drawn_or_kept`, and the block comment above the sizing tests. Keep `test_the_content_column_can_shrink_below_its_content` (reword its docstring's last two sentences: Chart.js's canvas is also fixed-width once drawn, so the track must still be able to shrink). Add:

```python
def test_page_renders_both_charts_and_the_summary(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    assert body.count("data-chart-canvas") == len(chart_configs(body)) >= 2
    assert "chart.umd.min.js" in body and "chartjs-adapter-date-fns.bundle.min.js" in body
    assert "On-time" in body and "%" in body
    assert "Open the longest" in body and "Quiz 1" in body


def test_uplot_is_gone():
    """Two charting libraries was one too many: everything draws through charts.chart_config."""
    assert not (STATIC / "uplot.min.js").exists() and not (STATIC / "uplot.min.css").exists()
    assert not (TEMPLATES / "_chart.html").exists()
    for p in [*TEMPLATES.glob("*.html"), STATIC / "app.js", STATIC / "app.css", STATIC / "VENDOR.md"]:
        assert "uplot" not in p.read_text(encoding="utf-8").lower(), p.name
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert js.count("function attachCharts") == 1 and "typeof uPlot" not in js
```

- [ ] **Step 2: Run it to verify it fails**

Run: `... -m pytest tests/test_web_trends_page.py -q -k "uplot_is_gone or both_charts"`
Expected: `test_uplot_is_gone` FAILS on the first `exists()`.

- [ ] **Step 3: Remove uPlot**

```bash
git rm -q fridgesheet/web/static/uplot.min.js fridgesheet/web/static/uplot.min.css fridgesheet/web/templates/_chart.html
```

`app.js`: delete from the comment `// Charts: a <div class="chart" data-chart=URL ...` through the two `attachCharts` listeners (the whole uPlot block, lines 109-248). In the remaining chart block rename `REPORT_CHARTS`→`CHARTS`, `pruneReportCharts`→`pruneCharts`, `attachReportCharts`→`attachCharts`, and reword its leading comment:

```js
// Charts: `charts.chart_config()`'s output, inlined as JSON next to a `<canvas>` by
// `_chart_canvas.html` (Trends, the course page, the report builder and view). The config
// travels with the page rather than being fetched: a builder preview is an unsaved definition
// with no URL to fetch by, and a page that already holds the rows should not ask for them
// twice. Every page that draws a chart includes `_chart_scripts.html` on its own initial load,
// before any htmx swap can bring in a chart-bearing partial, so there is no "library not
// loaded yet" race here.
//
// Chart.js keeps every instance in its own registry (and a ResizeObserver on the canvas's
// parent) until `destroy()`. An htmx swap replaces the canvas; the chart drawn on it must be
// destroyed, not kept, or each Preview click leaks one (tests/test_web_report_chart_lifecycle.py).
```

`app.css`: delete the `.chart`, `.chart .muted`, `.u-legend` rules and the "No fixed height: uPlot ..." comment; the `.shell` comment's sentences from "Once a chart has drawn" to "would never fire on the way down." become "Once a chart has drawn, the content is a `<canvas>` with a fixed pixel width, so the column would stay at its widest-ever size and Chart.js's own resize detection would never see it shrink."

`VENDOR.md`: delete the two uPlot rows. `.gitattributes`: delete the two uPlot lines. `trends.html`: delete lines 4-5 (`uplot.min.css`, `uplot.min.js`). `browser-app.md` line 32: "htmx plus one small vendored charting library (uPlot)" becomes "htmx plus one vendored charting library (Chart.js, with its date adapter)"; line 44: `uplot.min.js` becomes `chart.umd.min.js`, `chartjs-adapter-date-fns.bundle.min.js`.

- [ ] **Step 4: Run the whole suite**

Run: `... -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "uPlot leaves: one attach function, one holder style, one charting library"
```

---

### Task 7: Static script and stylesheet URLs carry the version

**Files:**
- Modify: `fridgesheet/web/templates/base.html:9-11`, `fridgesheet/web/templates/_chart_scripts.html`, `fridgesheet/web/templates/report_view.html:8-10`, `fridgesheet/web/templates/plan_print.html:8-9`
- Test: `tests/test_web_pages.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_web_pages.py (imports: re, Path; TEMPLATES = Path(webapp.__file__).parent / "templates")
def test_static_script_and_style_urls_carry_the_version():
    """An upgraded install serves new templates to a browser that may still hold last week's
    app.js (StaticFiles sends no Cache-Control). A new build is a new URL, so the two cannot
    disagree about what markup to draw."""
    for name in ("base.html", "report_view.html", "plan_print.html", "_chart_scripts.html"):
        tmpl = (TEMPLATES / name).read_text(encoding="utf-8")
        urls = re.findall(r'(?:src|href)="(/static/[^"]+\.(?:js|css)[^"]*)"', tmpl)
        assert urls, name
        assert all(u.endswith("?v={{ version }}") for u in urls), (name, urls)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `... -m pytest tests/test_web_pages.py -q -k version`
Expected: FAIL on `base.html`.

- [ ] **Step 3: Append `?v={{ version }}` to every `.js`/`.css` URL in those four templates**

`version` is in `page_context` for every page `render()` builds, including the two standalone print pages.

- [ ] **Step 4: Run the suite**

Run: `... -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add fridgesheet/web/templates tests/test_web_pages.py
git commit -m "Static script and stylesheet URLs carry the version, so an upgrade is a new URL"
```

---

### Task 8: See it draw, then open the PR

- [ ] **Step 1: Render Trends in headless Chromium and look at it**

A one-off script (not committed): build the fixture app, fetch `/trends` and one course page with the TestClient, serve `/static/*` from disk through `page.route`, `set_content` the HTML, wait for `Chart.getChart` on every canvas, screenshot to `/tmp/fs-trends.png` and `/tmp/fs-course.png`, then read the images. Both charts must show: the stacked weekly bars in five colours with the legend, and stepped grade lines with a day-formatted time axis and a thicker official line.

- [ ] **Step 2: Full suite, then push and open the PR**

Run: `... -m pytest -q` (all PASS), then:

```bash
git push -u origin viberpit/main-754567a0
gh pr create --base main --title "Trends draws through the shared chart stack: stacked weekly bars, stepped grade lines on a time axis, uPlot leaves" --body-file <body>
gh pr merge <n> --auto --squash
```

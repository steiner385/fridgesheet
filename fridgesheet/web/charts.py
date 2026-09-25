"""One chart vocabulary for every chart the app draws.

A `ChartData` is what a page or a report has to say; `chart_config()` turns it into the one
Chart.js `type`/`data`/`options` object that the live page (`app.js`) and the headless PDF
capture (`chart_render.py`) both draw from, so neither can disagree with the other about what
a chart looks like. The report builder (`views.py`) builds one from a report's rows; the
Trends route builds one from its stores. Nothing here reads the database.

A config is plain JSON -- no functions -- so the same object can be inlined in a page and
handed to a headless browser. Anything both hosts need is expressed as data here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SERIES_COLORS = ("#1f5fa8", "#b3261e", "#2e7d32", "#6b3fa0", "#b8860b", "#00707f")
#: Outcome colours, as the tables' `warn` class and docs/outcomes.md agree: the same strokes
#: the Trends chart has always used.
OUTCOME_COLORS = {"on_time": "#2e7d32", "late": "#b8860b", "not_done": "#b3261e",
                  "done_offline": "#1f5fa8", "unknown": "#8a6d3b"}
#: The y label of a chart that counts rows. Only such a chart may stack: summing averages
#: on top of each other would be meaningless, so a stacked_bar with any other y draws grouped.
COUNT_LABEL = "Count"
_CHART_JS_TYPE = {"line": "line", "bar": "bar", "stacked_bar": "bar"}


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


def escape_for_script_tag(json_text: str) -> str:
    """A JSON string, safe to inline verbatim inside an HTML <script> tag.

    A chart series/axis/bucket label can come from a course or assignment name -- untrusted
    the same way sheet.py's _esc() and the CSV formula-injection guard already treat those
    names -- so a label of literal `</script>` must not be able to close the element early.
    `json.dumps` alone does not guard against that; the escapes below live inside JSON string
    values, which `JSON.parse` unescapes transparently, so the value round-trips unchanged.
    Both the live web preview (`routes/reports.py`) and the headless PDF capture
    (`chart_render.py`) share this, so neither can drift out of sync about what's safe.
    """
    return (json_text.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
                     .replace('\u2028', '\\u2028').replace('\u2029', '\\u2029'))


def chart_config(data: ChartData) -> dict:
    """A Chart.js `type`/`data`/`options` object, built once -- the live web preview and the
    headless PDF capture (`chart_render.py`) both draw from this, so neither can disagree with
    the other about what a chart looks like."""
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

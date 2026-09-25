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

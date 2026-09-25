"""One chart vocabulary for every chart the app draws: `web/charts.py`."""
from __future__ import annotations

from fridgesheet.web import charts, views


def test_the_chart_vocabulary_lives_in_charts_and_views_re_exports_it():
    assert views.ChartData is charts.ChartData and views.ChartSeries is charts.ChartSeries
    assert views.chart_config is charts.chart_config
    assert views.escape_for_script_tag is charts.escape_for_script_tag


def test_a_time_scale_chart_carries_points_as_x_y_and_no_labels():
    data = charts.ChartData(type="line", x_label="Seen", y_label="Grade", x_scale="time", stepped=True,
                            title="Grade per class",
                            series=[charts.ChartSeries(label="Math (HAC average) · official", emphasis=True,
                                                       points=[(1757937600000, 88.0), (1758542400000, 91.0)])])
    cfg = charts.chart_config(data)
    assert "labels" not in cfg["data"]
    ds = cfg["data"]["datasets"][0]
    assert ds["data"] == [{"x": 1757937600000, "y": 88.0}, {"x": 1758542400000, "y": 91.0}]
    # Chart.js's "before" is the hold-until-the-next-point shape: the horizontal run carries the
    # *previous* value to the next x. "after" carries the next value back, which drew a grade as
    # if it had changed the moment it was first seen (caught in the Task 8 screenshot).
    assert ds["stepped"] == "before" and ds["borderWidth"] == 3
    assert cfg["options"]["scales"]["x"]["type"] == "time"
    assert cfg["options"]["scales"]["x"]["time"]["minUnit"] == "day"
    assert cfg["options"]["plugins"]["title"] == {"display": True, "text": "Grade per class"}


def test_a_time_scale_chart_holds_every_series_at_its_last_value_until_hold_until():
    """A stepped line only shapes the segments *between* points, so a class whose grade has
    not moved since 9/1 would stop on 9/1 while its siblings run to today -- reading as "this
    class stopped being tracked". The hold is data: one more point at `hold_until`, carrying
    the last value, drawn with no marker. A series already there is left alone."""
    data = charts.ChartData(type="line", x_label="Seen", y_label="Grade", x_scale="time", stepped=True,
                            hold_until=1758542400000,
                            series=[charts.ChartSeries(label="Math", points=[(1757937600000, 88.0)]),
                                    charts.ChartSeries(label="Art", points=[(1757937600000, 90.0), (1758542400000, 91.0)])])
    math, art = charts.chart_config(data)["data"]["datasets"]
    assert math["data"] == [{"x": 1757937600000, "y": 88.0}, {"x": 1758542400000, "y": 88.0}]
    assert math["pointRadius"] == [3, 0]
    assert art["data"] == [{"x": 1757937600000, "y": 90.0}, {"x": 1758542400000, "y": 91.0}]
    assert "pointRadius" not in art


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

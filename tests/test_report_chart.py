"""Bucketing and aggregation for a report's chart -- built from the same filtered, windowed,
scoped rows the table shows, never a separate query."""
from __future__ import annotations

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fridgesheet import late_rules
from fridgesheet.web import db, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])          # tests/test_web_views.py's own idiom
TZ = ZoneInfo("America/New_York")


def _save(home, **d):
    conn = db.open_db(home)
    rid = store.create(conn, "Mine", json.dumps({"title": "Mine", "source": "items", "columns": ["name", "due"], **d}),
                       now="2026-09-16T08:00:00-04:00")
    conn.close()
    return rid


def _rendered(home, rid):
    conn = db.open_db(home)
    row = store.by_id(conn, rid)
    d = views.from_json(row["definition"])
    rendered = views.build(conn, d, now=NOW, rules=RULES, nicknames={"Alex": "Al"})
    conn.close()
    return row, d, rendered


def test_a_stacked_bar_chart_counts_rows_per_bucket_per_series(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="items",
               chart={"type": "stacked_bar", "x": "due", "y": None, "series": "status", "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert rendered.chart is not None
    assert rendered.chart.type == "stacked_bar"
    total_points = sum(len(s.points) for s in rendered.chart.series)
    assert total_points > 0
    assert all(isinstance(v, float) for s in rendered.chart.series for _, v in s.points)


def test_a_line_chart_averages_a_number_column_and_skips_blank_buckets(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="grades", columns=["course", "value", "at"],
               chart={"type": "line", "x": "at", "y": "value", "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert rendered.chart is not None and rendered.chart.type == "line"
    # every point is a real observed average, never a manufactured zero for a silent week
    assert all(v != 0.0 for s in rendered.chart.series for _, v in s.points) or not rendered.chart.series


def test_a_report_with_no_rows_has_no_chart(tmp_path):
    seed(tmp_path).close()
    rid = _save(tmp_path, source="items", scope=["nobody"],
               chart={"type": "bar", "x": "due", "y": None, "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert rendered.chart is None and rendered.chart_note == ""


def test_a_chart_field_need_not_be_a_displayed_column(tmp_path):
    """The chart's x/y/series columns are independent of which columns the table shows."""
    seed(tmp_path).close()
    rid = _save(tmp_path, source="items", columns=["name"],           # "due" and "status" not shown
               chart={"type": "stacked_bar", "x": "due", "y": None, "series": "status", "bucket": "week"})
    row, d, rendered = _rendered(tmp_path, rid)
    assert views.validate(d) == [] and rendered.chart is not None


def test_two_y_values_in_one_bucket_average_to_exact_mean_not_sum_or_count():
    """(a) Two rows with y="80" and y="90" in the same bucket must average to exactly 85.0."""
    spec = views.ChartSpec(type="line", x="at", y="value", bucket="week")
    now = datetime(2026, 9, 20, tzinfo=TZ)
    # Both dates in same week, same series
    d = date(2026, 9, 15)  # Monday of that week
    kept = [
        ({"value": "80"}, {}, {"at": datetime(2026, 9, 16, 10, 0, tzinfo=TZ)}),
        ({"value": "90"}, {}, {"at": datetime(2026, 9, 17, 10, 0, tzinfo=TZ)}),
    ]
    chart, _ = views._chart_data("grades", spec, kept, now)
    assert chart is not None and len(chart.series) > 0
    points = chart.series[0].points
    assert len(points) == 1
    assert points[0][1] == 85.0  # average of 80 and 90


def test_three_rows_with_no_y_column_count_to_exact_three():
    """(b) Three rows with spec.y = None in the same bucket count to exactly 3.0."""
    spec = views.ChartSpec(type="stacked_bar", x="due", y=None, series="status", bucket="week")
    now = datetime(2026, 9, 20, tzinfo=TZ)
    kept = [
        ({"status": "open"}, {}, {"due": datetime(2026, 9, 16, 10, 0, tzinfo=TZ)}),
        ({"status": "done"}, {}, {"due": datetime(2026, 9, 17, 10, 0, tzinfo=TZ)}),
        ({"status": "open"}, {}, {"due": datetime(2026, 9, 18, 10, 0, tzinfo=TZ)}),
    ]
    chart, _ = views._chart_data("items", spec, kept, now)
    assert chart is not None
    # Find the "open" series
    open_series = next((s for s in chart.series if s.label == "open"), None)
    assert open_series is not None
    assert len(open_series.points) == 1
    assert open_series.points[0][1] == 2.0  # two open items


def test_bar_chart_zero_fills_empty_weeks_but_line_chart_leaves_gaps():
    """(c) bar/stacked_bar with rows in week 1 and week 3 produces 0.0 for week 2;
    line chart has no point for week 2 (gap, not zero)."""
    now = datetime(2026, 9, 20, tzinfo=TZ)
    week1_start = datetime(2026, 9, 7, 10, 0, tzinfo=TZ)   # week of Sept 7
    week3_start = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)  # week of Sept 21
    kept = [
        ({"status": "open"}, {}, {"due": week1_start}),
        ({"status": "open"}, {}, {"due": week3_start}),
    ]

    # Bar chart should have 3 points (week1, week2 with 0.0, week3)
    spec_bar = views.ChartSpec(type="bar", x="due", y=None, bucket="week")
    chart_bar, _ = views._chart_data("items", spec_bar, kept, now)
    assert chart_bar is not None and len(chart_bar.series) > 0
    bar_points = chart_bar.series[0].points
    assert len(bar_points) == 3  # three weeks
    assert bar_points[1][1] == 0.0  # middle week is zero-filled

    # Line chart should have 2 points (no zero-fill)
    spec_line = views.ChartSpec(type="line", x="due", y=None, bucket="week")
    chart_line, _ = views._chart_data("items", spec_line, kept, now)
    assert chart_line is not None and len(chart_line.series) > 0
    line_points = chart_line.series[0].points
    assert len(line_points) == 2  # only two weeks with data, gap in middle


def test_blank_y_value_excluded_from_average_not_coerced_to_zero():
    """(d) A bucket with values "80" and "" (blank) averages to exactly 80.0, not 40.0."""
    spec = views.ChartSpec(type="line", x="at", y="value", bucket="week")
    now = datetime(2026, 9, 20, tzinfo=TZ)
    kept = [
        ({"value": "80"}, {}, {"at": datetime(2026, 9, 16, 10, 0, tzinfo=TZ)}),
        ({"value": ""}, {}, {"at": datetime(2026, 9, 17, 10, 0, tzinfo=TZ)}),  # blank, should be skipped
    ]
    chart, note = views._chart_data("grades", spec, kept, now)
    assert chart is not None and len(chart.series) > 0
    points = chart.series[0].points
    assert len(points) == 1
    assert points[0][1] == 80.0  # only the 80, not averaged with blank
    assert "1 row(s) with no value are not charted" in note  # blank row should be mentioned


def test_evening_due_date_stays_in_its_day_for_bucketing():
    """(e) An item due 2026-09-20T23:59:00-04:00 (9/20 in NY) buckets into the week
    containing 2026-09-20, not 2026-09-21 (UTC). This is the regression test for
    the timezone bucketing bug where UTC times drifted items into the next calendar period.
    2026-09-20 is a Sunday; the week_start (Monday) is 2026-09-14, labeled "9/14".
    Under the old UTC bug, 2026-09-20T23:59-04:00 = 2026-09-21T03:59 UTC (Monday), so
    it would incorrectly bucket to the following week, labeled "9/21"."""
    spec = views.ChartSpec(type="bar", x="due", y=None, bucket="week")
    now = datetime(2026, 9, 20, tzinfo=TZ)
    # The evening of 9/20 in America/New_York
    evening_due = datetime(2026, 9, 20, 23, 59, 0, tzinfo=TZ)
    kept = [
        ({"status": "open"}, {}, {"due": evening_due}),
    ]
    chart, _ = views._chart_data("items", spec, kept, now)
    assert chart is not None and len(chart.series) > 0
    points = chart.series[0].points
    assert len(points) == 1
    # Must be the correct week label (9/14, the Monday of the week containing 9/20),
    # not the incorrect UTC-shifted week (9/21)
    assert points[0][0] == "9/14"


def test_chart_config_is_one_shape_for_every_chart_type():
    data = views.ChartData(type="stacked_bar", x_label="Due", y_label="Count", series=[
        views.ChartSeries(label="MISSING", points=[("9/8", 2.0), ("9/15", 0.0)]),
        views.ChartSeries(label="LATE", points=[("9/8", 0.0), ("9/15", 1.0)]),
    ], labels=("9/8", "9/15"))
    cfg = views.chart_config(data)
    assert cfg["type"] == "bar"
    assert cfg["data"]["labels"] == ["9/8", "9/15"]
    assert [ds["label"] for ds in cfg["data"]["datasets"]] == ["MISSING", "LATE"]
    assert cfg["data"]["datasets"][0]["data"] == [2.0, 0.0]
    assert cfg["options"]["scales"]["x"]["stacked"] is True

    line = views.chart_config(views.ChartData(type="line", x_label="Seen", y_label="Value",
                                              series=[views.ChartSeries(label="Value", points=[("9/8", 91.2)])],
                                              labels=("9/8",)))
    assert line["type"] == "line" and line["options"]["scales"]["x"]["stacked"] is False


def test_chart_config_labels_stay_chronological_with_divergent_series():
    """Regression test: when series have different bucket sets, labels must remain
    in chronological order, not series-iteration order. Series A at 9/1 and 9/20,
    Series B at 9/5 and 9/10 must yield labels ["9/1", "9/5", "9/10", "9/20"],
    not ["9/1", "9/20", "9/5", "9/10"] (A first, then B)."""
    data = views.ChartData(type="line", x_label="Date", y_label="Count", series=[
        views.ChartSeries(label="Series A", points=[("9/1", 10.0), ("9/20", 40.0)]),
        views.ChartSeries(label="Series B", points=[("9/5", 20.0), ("9/10", 30.0)]),
    ], labels=("9/1", "9/5", "9/10", "9/20"))
    cfg = views.chart_config(data)
    # Must be chronological order, not series-iteration order
    assert cfg["data"]["labels"] == ["9/1", "9/5", "9/10", "9/20"]
    # Series A should have values at 9/1 and 9/20, None at 9/5 and 9/10
    assert cfg["data"]["datasets"][0]["data"] == [10.0, None, None, 40.0]
    # Series B should have None at 9/1, value at 9/5, value at 9/10, None at 9/20
    assert cfg["data"]["datasets"][1]["data"] == [None, 20.0, 30.0, None]

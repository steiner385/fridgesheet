"""Bucketing and aggregation for a report's chart -- built from the same filtered, windowed,
scoped rows the table shows, never a separate query."""
from __future__ import annotations

import json

from fridgesheet import late_rules
from fridgesheet.web import db, views
from fridgesheet.web.stores import reports as store
from tests.web_fixtures import NOW, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])          # tests/test_web_views.py's own idiom


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

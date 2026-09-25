"""One chart vocabulary for every chart the app draws: `web/charts.py`."""
from __future__ import annotations

from fridgesheet.web import charts, views


def test_the_chart_vocabulary_lives_in_charts_and_views_re_exports_it():
    assert views.ChartData is charts.ChartData and views.ChartSeries is charts.ChartSeries
    assert views.chart_config is charts.chart_config
    assert views.escape_for_script_tag is charts.escape_for_script_tag

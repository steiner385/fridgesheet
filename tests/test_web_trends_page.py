"""The Trends page and the chart configs it inlines."""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from fridgesheet.web import charts
from tests.web_fixtures import NOW, app_for, chart_configs, history, seed, snapshot

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
TEMPLATES, STATIC = WEB / "templates", WEB / "static"
WEEKLY_LABELS = ["On time", "Late", "Not done", "On paper", "Unknown"]      # the table's column order


def weekly_config(body: str) -> dict:
    return next(c for c in chart_configs(body) if c["options"]["plugins"]["title"]["text"] == "Work due that week")


def test_empty_database_says_nothing_yet(tmp_path):
    r = app_for(tmp_path).get("/trends")
    assert r.status_code == 200 and "Not enough history yet" in r.text


def grade_configs(body: str) -> list[dict]:
    return [c for c in chart_configs(body) if c["options"]["scales"]["x"].get("type") == "time"]


def test_the_grade_chart_has_one_stepped_series_per_course_and_source_on_a_time_axis(tmp_path):
    history(tmp_path).close()
    cfgs = grade_configs(app_for(tmp_path).get("/trends?kid=Alex").text)
    assert len(cfgs) == 1 and cfgs[0]["type"] == "line"
    labels = {d["label"] for d in cfgs[0]["data"]["datasets"]}
    assert "Honors English 9 (HAC average) · official" in labels and "Honors English 9 (Canvas current)" in labels
    hac = next(d for d in cfgs[0]["data"]["datasets"] if d["label"].startswith("Honors English 9 (HAC"))
    assert [p["y"] for p in hac["data"]][:2] == [85.0, 88.0]          # the observations; then the hold to now
    assert all(isinstance(p["x"], int) for p in hac["data"]) and hac["data"][0]["x"] < hac["data"][1]["x"]
    assert hac["stepped"] == "before" and hac["borderWidth"] == 3      # hold until the next point
    assert cfgs[0]["options"]["plugins"]["title"]["text"] == "Grade per class"


def test_every_grade_line_runs_to_now_not_to_its_own_last_observation(tmp_path):
    """Alex's HAC average last moved on 9/14 and the Canvas current on 9/15; both lines must
    reach `now`, or the class that has not changed looks like it stopped being tracked."""
    history(tmp_path).close()
    cfg, = grade_configs(app_for(tmp_path).get("/trends?kid=Alex").text)
    now_ms = int(NOW.timestamp() * 1000)
    ends = {d["label"]: d["data"][-1]["x"] for d in cfg["data"]["datasets"]}
    assert set(ends.values()) == {now_ms}, ends
    hac = next(d for d in cfg["data"]["datasets"] if d["label"].startswith("Honors English 9 (HAC"))
    assert [p["y"] for p in hac["data"]] == [85.0, 88.0, 88.0] and hac["pointRadius"][-1] == 0


def test_the_all_kids_view_draws_one_titled_grade_chart_per_kid(tmp_path):
    """Three kids' classes in one legend was 28 series (#40 item 12)."""
    history(tmp_path).close()
    c = app_for(tmp_path)
    everyone = grade_configs(c.get("/trends").text)
    assert len(everyone) >= 2
    assert "Alex — grade per class" in {cfg["options"]["plugins"]["title"]["text"] for cfg in everyone}
    assert len(grade_configs(c.get("/trends?kid=Sam").text)) == 1


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
    text = chart_json(grade_chart([evil], title="Grade per class", now=NOW))
    assert "</script>" not in text and "\\u003c/script" in text


def test_the_grades_json_endpoint_is_gone(tmp_path):
    history(tmp_path).close()
    assert app_for(tmp_path).get("/trends/grades.json").status_code == 404


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


def test_the_weekly_json_endpoint_is_gone(tmp_path):
    history(tmp_path).close()
    assert app_for(tmp_path).get("/trends/weekly.json?weeks=4").status_code == 404


def test_kid_filter_applies_to_the_page_and_its_chart(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/trends?kid=Sam").text
    assert "Science 7" in body and "Honors English 9" not in body
    assert all("Science 7" in d["label"] for cfg in grade_configs(body) for d in cfg["data"]["datasets"])
    assert c.get("/trends?kid=Nobody").status_code == 404


def test_weeks_parameter_is_bounded(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    assert len(weekly_config(c.get("/trends?weeks=200").text)["data"]["labels"]) == 52     # clamped
    assert len(weekly_config(c.get("/trends?weeks=0").text)["data"]["labels"]) == 1
    assert len(weekly_config(c.get("/trends?weeks=nonsense").text)["data"]["labels"]) == 8  # the default


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


def test_one_refresh_only_still_renders(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/trends")
    assert r.status_code == 200 and "Trends" in r.text


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


def test_the_content_column_can_shrink_below_its_content():
    """A bare `1fr` track is `minmax(auto, 1fr)`: it never narrows past its content's
    min-content width. After the first draw a chart holder's content is a `<canvas>` with a
    fixed pixel width, so the column froze at its widest-ever size and narrowing the window
    left the page horizontally scrollable with the rail off-screen, permanently (a phone
    rotated to landscape and back needs a reload). Measured in Chromium at 1400 -> 900 ->
    700 -> 390: holders of 1050/630/674/364 with `scrollWidth == innerWidth` at every step;
    with a bare `1fr`, 1050 at all four and `scrollWidth` up to 1320 against a 900 viewport.
    Chart.js's own resize detection can only follow a track that is allowed to shrink. Both
    grid declarations need the explicit zero minimum -- the phone width uses the second."""
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    tracks = re.findall(r"\.shell\s*\{[^}]*grid-template-columns:\s*([^;}]+)", css)
    assert len(tracks) == 2, "expected the wide layout and the max-width:800px override"
    assert [t.strip() for t in tracks] == ["220px minmax(0, 1fr)", "minmax(0, 1fr)"]


def test_an_unknown_kid_on_trends_says_the_kid_is_not_known(tmp_path):
    """#150: the 404 blamed the address ("/trends is not a page here.") when it was the kid."""
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/trends?kid=nobody")
    assert r.status_code == 404
    assert "is not a page here" not in r.text
    assert "No kid called “nobody”" in r.text

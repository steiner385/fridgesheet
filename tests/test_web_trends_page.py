"""The Trends page and the JSON its charts read."""
from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path

from tests.web_fixtures import NOW, app_for, history, seed, snapshot

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
TEMPLATES, STATIC = WEB / "templates", WEB / "static"


def test_empty_database_says_nothing_yet(tmp_path):
    r = app_for(tmp_path).get("/trends")
    assert r.status_code == 200 and "Not enough history yet" in r.text


def test_page_renders_chart_holders_and_the_summary(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    assert 'data-chart="/trends/grades.json' in body and 'data-chart="/trends/weekly.json' in body
    assert "uplot.min.js" in body and "uplot.min.css" in body
    assert "On-time" in body and "%" in body
    assert "Open the longest" in body and "Quiz 1" in body


def test_grades_json_has_one_series_per_course_and_source(tmp_path):
    history(tmp_path).close()
    data = app_for(tmp_path).get("/trends/grades.json").json()
    labels = {s["label"] for s in data["series"]}
    assert "Honors English 9 (HAC average)" in labels and "Honors English 9 (Canvas current)" in labels
    hac = next(s for s in data["series"] if s["label"].endswith("(HAC average)") and s["label"].startswith("Honors"))
    assert [v for _, v in hac["points"]] == [85.0, 88.0]
    assert all(isinstance(t, (int, float)) for t, _ in hac["points"])       # epoch seconds for uPlot


def test_weekly_json_is_parallel_arrays(tmp_path):
    history(tmp_path).close()
    data = app_for(tmp_path).get("/trends/weekly.json?weeks=4").json()
    assert len(data["weeks"]) == 4
    for key in ("on_time", "late", "not_done", "done_offline", "unknown"):
        assert len(data[key]) == 4
    assert data["weeks"] == sorted(data["weeks"])


def test_kid_filter_applies_to_page_and_json(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/trends?kid=Sam").text
    assert "Science 7" in body and "Honors English 9" not in body
    data = c.get("/trends/grades.json?kid=Sam").json()
    assert all("Science 7" in s["label"] for s in data["series"])
    assert c.get("/trends?kid=Nobody").status_code == 404
    assert c.get("/trends/grades.json?kid=Nobody").status_code == 404


def test_weeks_parameter_is_bounded(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    assert len(c.get("/trends/weekly.json?weeks=200").json()["weeks"]) == 52     # clamped
    assert len(c.get("/trends/weekly.json?weeks=0").json()["weeks"]) == 1
    assert c.get("/trends/weekly.json?weeks=nonsense").status_code == 200        # falls back to the default


def test_weeks_parameter_also_narrows_the_grade_chart(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)

    def total_points(weeks):
        data = c.get(f"/trends/grades.json?weeks={weeks}").json()
        return sum(len(s["points"]) for s in data["series"])

    assert total_points(1) < total_points(16)


def test_grades_json_with_no_weeks_returns_all_history(tmp_path):
    """An absent `weeks` means all history, not the same default window a chart with a Weeks
    selector would use -- `course.html`'s embed has no selector and must not silently drop
    old grades."""
    old_now = NOW - timedelta(weeks=20)                            # ~5 months back
    old_snap = snapshot()
    old_snap["students"]["Alex"]["hac"]["classes"][0]["marking_period_avg"] = 70.0
    old_snap["fetched_at"] = old_now.isoformat()
    seed(tmp_path, old_snap, now=old_now).close()                  # the one old observation
    conn = history(tmp_path)                                       # the standard 3-day fixture, layered on top
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    conn.close()

    data = app_for(tmp_path).get(f"/trends/grades.json?course={cid}").json()
    points = [p for s in data["series"] for p in s["points"]]
    eight_weeks_ago = (NOW - timedelta(weeks=8)).timestamp()
    assert any(t < eight_weeks_ago for t, _ in points)


def test_weeks_selector_url_carries_the_chosen_weeks_for_the_grade_chart_too(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends?weeks=4").text
    assert 'data-chart="/trends/grades.json?weeks=4' in body


def test_a_course_filter_that_is_not_a_course_matches_nothing(tmp_path):
    """`?course=abc` names no course, so it answers with no series -- it must not fall through
    to "every class in the house", which is what a course-page chart would then draw."""
    history(tmp_path).close()
    c = app_for(tmp_path)
    assert c.get("/trends/grades.json?course=abc").json() == {"series": []}
    assert c.get("/trends/grades.json?course=999999").json() == {"series": []}
    assert c.get("/trends/grades.json").json()["series"]                  # the unfiltered call still answers


def test_course_page_gains_a_grade_chart(tmp_path):
    conn = history(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    assert 'data-chart="/trends/grades.json?course=' in body and "uplot.min.js" in body


def test_one_refresh_only_still_renders(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/trends")
    assert r.status_code == 200 and "Trends" in r.text


# The chart holder's *sizing* contract, pinned the way `test_packaging.py` pins the installer
# text: none of it can be exercised here (there is no browser in this suite), and all of it is
# load-bearing. Each assertion below stands for a defect that shipped once:
#
#   - an inline `style="height:NNNpx"` on `.chart` clipped the holder to the plot alone, so
#     uPlot's title and legend -- drawn as *siblings* of the sized plot -- printed 72px/42px
#     over whatever followed the chart. `.chart` must have no fixed height at all (app.css
#     says the same in prose); the holder grows to fit title + plot + legend.
#   - `data-height` is what app.js passes to uPlot as the plot height. Drop it from a holder
#     and `drawChart` silently falls back to 220, so the grade chart -- the one the page gives
#     260 to -- renders 40px shorter with nothing anywhere saying so.
def test_chart_holders_carry_their_plot_height_and_no_inline_height():
    """`_chart.html` is the only place a chart holder is emitted; `style="height` there is the
    exact overflow bug, and `data-height` is the only channel the per-chart height travels."""
    tmpl = (TEMPLATES / "_chart.html").read_text(encoding="utf-8")
    assert 'data-height="{{ height|default(220) }}"' in tmpl
    assert "style=" not in tmpl, "a chart holder sized in CSS overflows uPlot's title and legend"


def test_trends_page_asks_for_a_taller_grade_chart_than_the_weekly_one(tmp_path):
    """Rendered, not just templated: the grade chart is given 260 and the weekly chart takes
    the 220 default, and neither holder carries an inline height."""
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    holders = re.findall(r'<div class="chart"[^>]*>', body)
    grades = [h for h in holders if "grades.json" in h]          # one per kid in the "all" view
    weekly = [h for h in holders if "weekly.json" in h]
    assert len(grades) >= 1 and len(weekly) == 1 and len(holders) == len(grades) + 1
    assert all('data-height="260"' in h for h in grades) and 'data-height="220"' in weekly[0]
    assert 'style="height' not in body


def test_course_page_chart_holder_also_carries_a_height(tmp_path):
    conn = history(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").text
    holder, = re.findall(r'<div class="chart"[^>]*>', body)
    assert 'data-height="220"' in holder and 'style="height' not in body


def test_the_content_column_can_shrink_below_its_content():
    """A bare `1fr` track is `minmax(auto, 1fr)`: it never narrows past its content's
    min-content width. After the first draw a chart holder's content is a fixed-width
    `<canvas>`, so the column froze at its widest-ever size -- `chartWidth` kept reporting the
    old width, app.js's `w !== c.u.width` stayed false, `setSize` never fired, and narrowing
    the window left the page horizontally scrollable with the rail off-screen, permanently (a
    phone rotated to landscape and back needs a reload). Measured in Chromium at 1400 -> 900 ->
    700 -> 390: holders of 1050/630/674/364 with `scrollWidth == innerWidth` at every step;
    with a bare `1fr`, 1050 at all four and `scrollWidth` up to 1320 against a 900 viewport.
    Both grid declarations need the explicit zero minimum -- the phone width uses the second."""
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    tracks = re.findall(r"\.shell\s*\{[^}]*grid-template-columns:\s*([^;}]+)", css)
    assert len(tracks) == 2, "expected the wide layout and the max-width:800px override"
    assert [t.strip() for t in tracks] == ["220px minmax(0, 1fr)", "minmax(0, 1fr)"]


def test_the_all_kids_view_draws_one_grade_chart_per_kid(tmp_path):
    """Three kids' classes in one legend was 28 series (#40 item 12). "all" now shows the
    chart each kid's own view shows, one under the other; a kid's view still shows one."""
    history(tmp_path).close()
    c = app_for(tmp_path)
    everyone = c.get("/trends").text
    assert everyone.count('data-chart="/trends/grades.json') >= 2
    assert 'grades.json?weeks=8&amp;kid=Alex' in everyone or 'grades.json?weeks=8&kid=Alex' in everyone
    assert 'data-title="Alex — grade per class"' in everyone
    one = c.get("/trends?kid=Sam").text
    assert one.count('data-chart="/trends/grades.json') == 1


def test_a_chart_swapped_away_during_its_fetch_is_not_drawn_or_kept():
    """#9: `drawChart` marks the holder drawn at once but only registers the uPlot when its JSON
    arrives. An htmx swap in between removes the holder and prunes; the late continuation then
    drew into the detached node and pushed it into CHARTS. It now checks first."""
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    body = js[js.index("function drawChart"):js.index("// One shared resize listener")]
    then = body[body.index(".then(function (data)"):]
    guard = then.index("if (!document.contains(el)) return;")
    assert guard < then.index("el.innerHTML") and guard < then.index("CHARTS.push")

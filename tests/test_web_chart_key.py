"""A chart's key is HTML under the plot, not Chart.js's legend inside the canvas.

The canvas legend shares the holder's fixed height with the plot. At a phone's width a
class name and its "(HAC average)" fit one per row, so six classes were six rows: 180 of
the holder's 260px, the sixth clipped mid-name and the lines squeezed into the 70px left
(the Trends screenshot behind this). The key `app.js` builds beside the canvas takes no
height from the plot, wraps as text does, and gives each series a real button to tap (the
canvas legend's hit boxes are the size of its 13px text). Tapping hides and shows the
series, as the canvas legend did. The PDF path (`chart_render.py`) draws the same config
without `app.js` and keeps Chart.js's legend: paper has no HTML to put a key in.

Gated on the same bundled Chromium `doctor.py` health-checks, like tests/test_chart_render.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

import fridgesheet.web as webapp
from fridgesheet import doctor
from fridgesheet.config import Settings
from fridgesheet.web import charts

STATIC = Path(webapp.__file__).parent / "static"

CONFIG = charts.chart_config(charts.ChartData(
    type="line", x_label="Seen", y_label="Grade", x_scale="time", stepped=True, title="Grade per class",
    series=[charts.ChartSeries(label="Algebra I", points=[(1757937600000, 88.0), (1758542400000, 91.0)]),
            charts.ChartSeries(label="Art (Canvas current)", points=[(1757937600000, 95.0)])]))


def _chromium_available(tmp_path) -> bool:
    checks = doctor.checks(Settings(home=tmp_path), tmp_path)
    return next(c for c in checks if c.name == "chromium").ok


def _page_html() -> str:
    """The app's real scripts and stylesheet, inline, around what `_chart_canvas.html` renders."""
    scripts = "".join(f"<script>{(STATIC / name).read_text(encoding='utf-8')}</script>"
                      for name in ("chart.umd.min.js", "chartjs-adapter-date-fns.bundle.min.js", "app.js"))
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<style>{css}</style>{scripts}</head><body><main>"
            '<div class="chart-holder" style="height: 260px">'
            '<canvas data-chart-canvas role="img" aria-label="probe, as a chart"></canvas>'
            f'<script type="application/json" data-chart-config>{charts.escape_for_script_tag(json.dumps(CONFIG))}</script>'
            "</div></main></body></html>")


def test_the_key_is_html_beside_the_canvas_and_toggles_its_series(tmp_path):
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.set_content(_page_html())
            page.wait_for_selector(".chart-key")
            # One button per series, named as the series is, right after the holder.
            assert page.evaluate("document.querySelector('.chart-holder').nextElementSibling.className") == "chart-key"
            buttons = page.locator(".chart-key button")
            assert buttons.all_text_contents() == ["Algebra I", "Art (Canvas current)"]
            assert buttons.evaluate_all("bs => bs.map(b => b.getAttribute('aria-pressed'))") == ["true", "true"]
            # Each swatch wears its series' colour; the text wears the page's ink.
            swatches = page.locator(".chart-key .swatch")
            assert swatches.evaluate_all("ss => ss.map(s => getComputedStyle(s).backgroundColor)") == ["rgb(31, 95, 168)", "rgb(179, 38, 30)"]
            # The canvas legend is off: the plot has the whole holder.
            chart = "Chart.getChart(document.querySelector('[data-chart-canvas]'))"
            assert page.evaluate(f"{chart}.options.plugins.legend.display") is False
            assert page.evaluate(f"{chart}.chartArea.top") < 60
            # A tap hides the series and says so; another brings it back.
            buttons.first.click()
            assert page.evaluate(f"{chart}.isDatasetVisible(0)") is False
            assert buttons.first.get_attribute("aria-pressed") == "false"
            buttons.first.click()
            assert page.evaluate(f"{chart}.isDatasetVisible(0)") is True
            assert buttons.first.get_attribute("aria-pressed") == "true"
        finally:
            browser.close()


def test_the_key_buttons_are_finger_sized_on_a_touch_screen(tmp_path):
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True)
            page.set_content(_page_html())
            page.wait_for_selector(".chart-key")
            heights = page.locator(".chart-key button").evaluate_all("bs => bs.map(b => b.getBoundingClientRect().height)")
            assert all(h >= 44 for h in heights), heights
        finally:
            browser.close()

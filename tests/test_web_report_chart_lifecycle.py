"""A report chart that htmx swaps away must be destroyed, not kept.

Chart.js holds every live instance in `Chart.instances` (and, being responsive, a
ResizeObserver on the canvas's parent) until `destroy()` is called. The builder's Preview
button replaces `#preview` wholesale on every click, so each preview drew a new chart on a new
canvas and left the previous one behind: one leaked chart per click for the life of the page.
The uPlot path (`pruneCharts`) already destroys what a swap removed; this pins the same
guarantee for the Chart.js path, in a real browser, against Chart.js's own registry.

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
from fridgesheet.web import views

STATIC = Path(webapp.__file__).parent / "static"

CONFIG = {"type": "bar", "data": {"labels": ["9/8"], "datasets": [{"label": "Count", "data": [1]}]},
          "options": {"animation": False}}


def _chromium_available(tmp_path) -> bool:
    checks = doctor.checks(Settings(home=tmp_path), tmp_path)
    return next(c for c in checks if c.name == "chromium").ok


def _page_html() -> str:
    """The app's real scripts, inline, around an empty preview target -- what report_builder.html
    is after its own page load, minus htmx (the swap below is dispatched by hand)."""
    chart_js = (STATIC / "chart.umd.min.js").read_text(encoding="utf-8")
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    return ("<!doctype html><html><head><meta charset=\"utf-8\">"
            f"<script>{chart_js}</script><script>{app_js}</script></head>"
            "<body><div id=\"preview\"></div></body></html>")


def _preview_partial() -> str:
    """What `_report_preview.html` renders for a report with a chart."""
    return ('<div class="card"><div class="chart-holder">'
            '<canvas data-report-chart width="300" height="100"></canvas>'
            f'<script type="application/json" data-chart-config>{views.escape_for_script_tag(json.dumps(CONFIG))}</script>'
            '</div></div>')


SWAP = """(html) => {
  var target = document.getElementById("preview");
  target.innerHTML = html;
  document.dispatchEvent(new CustomEvent("htmx:afterSwap", {detail: {target: target}}));
}"""


def test_a_preview_swapped_three_times_leaves_one_live_chart(tmp_path):
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(_page_html())
            for _ in range(3):
                page.evaluate(SWAP, _preview_partial())
            # The chart on the page now is drawn, and it is the only one Chart.js still holds.
            assert page.evaluate("document.querySelector('[data-report-chart]').dataset.drawn") == "1"
            assert page.evaluate("Chart.getChart(document.querySelector('[data-report-chart]')) !== undefined")
            assert page.evaluate("Object.keys(Chart.instances).length") == 1
        finally:
            browser.close()

"""Headless-rendered chart images for the PDF path (`sheet.build_table_pdf`'s `chart_png`).

`charts.chart_config()` is the one Chart.js config the live web preview and this module both
draw from; this module's only job is getting that same drawing onto paper, via the app's
existing bundled Chromium (`session.py` uses the same Playwright install for Canvas/HAC
sessions; `doctor.py` already health-checks it). A fresh, non-persistent browser context is
used here -- unlike `session.browser()`, a chart capture has no cookies or login profile to
keep between runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

from .web import charts

_STATIC = Path(__file__).parent / "web" / "static"

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{{margin:0;padding:0}}</style>
<script>{chart_js}</script></head>
<body><canvas id="c" width="{width}" height="{height}"></canvas>
<script>
var cfg = {config};
cfg.options = cfg.options || {{}};
cfg.options.animation = {{duration: 0, onComplete: function () {{ window.__chartReady = true; }}}};
cfg.options.responsive = false;
new Chart(document.getElementById("c").getContext("2d"), cfg);
</script></body></html>"""


def _chart_js() -> str:
    """Chart.js and its date adapter, in that order -- the same pair `_chart_scripts.html`
    gives the browser, so a `time` x-scale draws on paper exactly as it does on the page."""
    return "\n;".join((_STATIC / name).read_text(encoding="utf-8")
                      for name in ("chart.umd.min.js", "chartjs-adapter-date-fns.bundle.min.js"))


def render_chart_png(config: dict, *, width_px: int = 1400, height_px: int = 500,
                     timeout_ms: int = 10000) -> bytes:
    """A Chart.js `config` (from `charts.chart_config`), drawn headlessly and returned as a PNG
    at 2x scale for print sharpness. Raises on anything that stops it -- a missing/broken
    Chromium, a page that never signals ready -- so the caller decides how to degrade
    (`reports/view.py` falls back to a chart-less PDF rather than failing the run)."""
    html = _HTML.format(chart_js=_chart_js(), width=width_px, height=height_px,
                        config=charts.escape_for_script_tag(json.dumps(config)))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": width_px, "height": height_px}, device_scale_factor=2)
            page.set_content(html)
            page.wait_for_function("window.__chartReady === true", timeout=timeout_ms)
            return page.locator("canvas").screenshot()
        finally:
            browser.close()

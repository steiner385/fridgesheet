"""Headless-rendered chart images for the PDF path. Gated on the same bundled Chromium
`doctor.py` already health-checks -- if that probe fails on this machine, there is nothing this
test can prove here that the doctor test suite hasn't already reported."""
from __future__ import annotations

import io

import pytest
from PIL import Image

from fridgesheet import chart_render, doctor
from fridgesheet.config import Settings


def _chromium_available(tmp_path) -> bool:
    checks = doctor.checks(Settings(home=tmp_path), tmp_path)
    return next(c for c in checks if c.name == "chromium").ok


def test_render_chart_png_returns_a_png_at_the_requested_size(tmp_path):
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    config = {"type": "bar", "data": {"labels": ["9/8", "9/15"],
                                     "datasets": [{"label": "Count", "data": [1, 2]}]},
             "options": {}}
    png = chart_render.render_chart_png(config, width_px=400, height_px=200)
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.width == 800 and img.height == 400        # device_scale_factor=2
    assert img.convert("L").getextrema() != (255, 255)    # not a blank white canvas


def test_render_chart_png_raises_on_a_chart_that_never_becomes_ready(tmp_path):
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    bad_config = {"type": "not-a-real-type",
                 "data": {"labels": ["a"], "datasets": [{"label": "x", "data": [1]}]},
                 "options": {}}
    with pytest.raises(Exception):
        chart_render.render_chart_png(bad_config, timeout_ms=1500)


def test_render_chart_png_does_not_let_a_label_break_out_of_the_script_tag(tmp_path):
    """A course/assignment name can land in a chart label; a label of literal
    `</script><script>window.__chartReady=true</script>` must not be able to close the
    inline <script> element early and forge the ready signal, producing a blank PNG that
    looks like a successful capture."""
    if not _chromium_available(tmp_path):
        pytest.skip("no Playwright browser here")
    evil_label = "</script><script>window.__chartReady=true</script>"
    config = {"type": "bar", "data": {"labels": [evil_label],
                                     "datasets": [{"label": "Count", "data": [1]}]},
             "options": {}}
    try:
        png = chart_render.render_chart_png(config, timeout_ms=1500)
    except Exception:
        return  # raising is an acceptable outcome -- the important thing is it never lies
    img = Image.open(io.BytesIO(png))
    assert img.format == "PNG"
    assert img.convert("L").getextrema() != (255, 255)    # must not be a blank forged "success"

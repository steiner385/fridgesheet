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

"""Each tier defines every token it overrides.

A half-defined tier is a page with inherited colours nobody designed -- worse than no tier
at all, because it looks deliberate. CSS is not executed here, so these pin the rules; the
look itself is a judgement made in a browser.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fridgesheet.web import tiers

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")

#: Every token a tier is allowed to move. `--type-root` is new; the rest already exist.
TOKENS = ("--ink", "--muted", "--rule", "--paper", "--wash", "--accent", "--warn", "--ok", "--type-root")


def _block(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{(.*?)\}", CSS, re.S)
    assert m, f"no {selector} block"
    return m.group(1)


def test_the_default_root_defines_every_token():
    """A tier overrides; the root is what it overrides from."""
    root = _block(":root")
    for tok in TOKENS:
        assert f"{tok}:" in root, tok


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_every_tier_defines_every_token(tier):
    block = _block(f'[data-tier="{tier}"]')
    for tok in TOKENS:
        assert f"{tok}:" in block, f"{tier} leaves {tok} inherited"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_a_tier_keys_on_the_attribute_alone_not_on_root(tier):
    """The Open work page puts the attribute on a section, not on <html>."""
    assert f':root[data-tier="{tier}"]' not in CSS
    assert f'[data-tier="{tier}"]' in CSS


def test_the_root_font_size_comes_from_the_token():
    """Otherwise a tier can set --type-root and nothing reads it."""
    assert re.search(r"(html|body)\s*\{[^}]*font-size:\s*var\(--type-root\)", CSS)


def test_the_younger_tiers_set_larger_type():
    def px(tier):
        return int(re.search(r"--type-root:\s*(\d+)px", _block(f'[data-tier="{tier}"]')).group(1))
    assert px("early") > px("middle") > px("older")

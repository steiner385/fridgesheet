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

#: Every token a tier is allowed to move. `--type-root` is the body size; `--type-small` and
#: `--type-tiny` are the two secondary sizes (13px and 12px at the root) that the school
#: evidence, dates, eyebrows and stamps on a child's page are set in.
TOKENS = ("--ink", "--muted", "--rule", "--paper", "--wash", "--accent", "--warn", "--ok",
          "--type-root", "--type-small", "--type-tiny")

#: The classes a child reads on the check-in, question card and work list that used to be
#: pinned at 12 or 13px whatever the tier (kids' UX audit F2). Each must size itself from a
#: token so the tier reaches it.
SECONDARY = (".school-evidence", ".q .what", ".q .more", ".eyebrow", ".stamp", "p.legend", "td .rel", "td .at",
             "table.work td.item small", "table.work td.where small.thru", ".sources-hint", ".src", ".note .meta",
             ".record", ".qmark", ".lines .line > form")


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


def test_each_tier_sets_its_own_font_size():
    """The tier selector (on <body> or <section>) sets its type scale directly.

    A custom property cannot reach its ancestor, so html {font-size: var(--type-root)}
    would not work: data-tier lives on <body> or <section>, never on <html>.
    Instead, each tier selector applies the token to itself. This selector has higher
    specificity than body { font: 15px/1.45 ... }, so tier size wins.
    """
    # Tier selectors must set font-size via the token
    tier_selector_rule = re.search(
        r"\[data-tier=[\"'](?:early|middle|older)[\"']\][^{]*\{[^}]*font-size:\s*var\(--type-root\)",
        CSS
    )
    assert tier_selector_rule, "tier selectors must set font-size: var(--type-root)"

    # There must NOT be an html rule setting this (that would not work)
    assert not re.search(r"^\s*html\s*\{[^}]*font-size:\s*var\(--type-root\)", CSS, re.M),\
        "html selector cannot set font-size for attributes on body/section"


def test_the_younger_tiers_set_larger_type():
    def px(tier):
        return int(re.search(r"--type-root:\s*(\d+)px", _block(f'[data-tier="{tier}"]')).group(1))
    assert px("early") > px("middle") > px("older")


def _token_px(block: str, token: str) -> float:
    return float(re.search(re.escape(token) + r":\s*([\d.]+)px", block).group(1))


def test_secondary_type_clears_the_childrens_floor_in_the_young_tiers():
    """NN/g's floor for 9-12-year-olds is 12pt (16px); the older tier keeps today's 13px, and the
    root (no grade set) is byte-for-byte what shipped."""
    early, middle, older, root = (_block(s) for s in ('[data-tier="early"]', '[data-tier="middle"]', '[data-tier="older"]', ":root"))
    assert _token_px(early, "--type-small") >= 16 and _token_px(early, "--type-tiny") >= 14
    assert _token_px(middle, "--type-small") >= 14.5 and _token_px(middle, "--type-tiny") >= 13
    assert _token_px(older, "--type-small") == _token_px(root, "--type-small") == 13
    assert _token_px(older, "--type-tiny") == _token_px(root, "--type-tiny") == 12


@pytest.mark.parametrize("selector", SECONDARY)
def test_secondary_text_on_a_childs_page_is_sized_by_a_token(selector):
    """A pixel literal here is a size the tier cannot reach: the 20px early page rendered its
    "School record" lines at 13px."""
    blocks = re.findall(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert blocks, f"no {selector} rule"
    sizes = [m for b in blocks for m in re.findall(r"font-size:\s*([^;]+);", b)]
    assert sizes, f"{selector} sets no font-size"
    for s in sizes:
        assert "var(--type-small)" in s or "var(--type-tiny)" in s, f"{selector} is pinned at {s}"

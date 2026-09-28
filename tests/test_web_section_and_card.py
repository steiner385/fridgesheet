"""One section, one card (docs/superpowers/specs/2026-09-28-section-and-card-standard-design.md).

Holds the standard the way test_web_page_layout.py holds the page layout: the tokens, the
section head, the item's five slots at three densities, and, once every page is converted,
the absence of the classes it retired. CSS is not executed here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
TEMPLATES = WEB / "templates"


def _root() -> str:
    return re.search(r":root\s*\{([^}]*)\}", CSS).group(1)


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


# --- §6: tokens ---------------------------------------------------------------------------------

def test_the_root_defines_the_radius_and_the_gap_scale():
    root = _root()
    assert re.search(r"--radius:\s*8px", root)
    for tok, px in (("--s1", 4), ("--s2", 8), ("--s3", 12), ("--s4", 16), ("--s5", 24), ("--s6", 32)):
        assert re.search(rf"{tok}:\s*{px}px", root), f"{tok} is not {px}px"


# --- §3: the section ----------------------------------------------------------------------------

def test_a_section_head_is_one_wrapping_row_and_a_folded_section_draws_the_same_head():
    assert re.search(r"\.sec\s*\{[^}]*margin: 0 0 var\(--s6\)", CSS)
    head = _rule(".sec-head, details.sec > summary")
    assert "display: flex" in head and "flex-wrap: wrap" in head
    assert re.search(r"\.sec-head h3, details\.sec > summary h3\s*\{[^}]*font-size: 18px", CSS)
    assert re.search(r"\.sec\.quiet h3\s*\{[^}]*color: var\(--muted\)", CSS)
    assert re.search(r"\.sec-head \.lead\s*\{[^}]*flex-basis: 100%", CSS)
    assert re.search(r"\.sec-head \.controls\s*\{[^}]*margin-left: auto", CSS)


# --- §4: the item surface -----------------------------------------------------------------------

def test_the_item_is_one_box_with_a_left_rule_that_names_its_tone():
    item = _rule(".item")
    assert "border-radius: var(--radius)" in item and "border-left: 4px solid var(--rule)" in item
    assert "overflow-wrap: anywhere" in item                                   # a long name wraps
    for tone, colour in (("ask", "--accent"), ("red", "--warn"), ("ok", "--ok")):
        assert re.search(rf"\.item\.{tone}\s*\{{[^}}]*border-left-color: var\({colour}\)", CSS), tone
    assert re.search(r"\.item\.grey\s*\{[^}]*color: var\(--muted\)", CSS)
    assert re.search(r"\.item-head \.when\s*\{[^}]*margin-left: auto", CSS)
    assert re.search(r"\.item-head \.when\.word\s*\{[^}]*color: var\(--warn\)", CSS)
    assert re.search(r"\.item-foot\s*\{[^}]*font-size: var\(--type-small\)", CSS)
    assert re.search(r"\.item-foot \.stamp\s*\{[^}]*font-size: var\(--type-tiny\)", CSS)
    assert re.search(r"\.ours\s*\{[^}]*border-left: 3px solid var\(--accent\)", CSS)


def test_the_inset_the_record_and_the_lines_share_the_radius():
    for sel in (".inset", ".lines"):
        assert "border-radius: var(--radius)" in _rule(sel), sel
    assert re.search(r"\.sources\s*\{[^}]*grid-template-columns: max-content 1fr", CSS)
    assert re.search(r"\.sources \.stamp\s*\{[^}]*grid-column: 2", CSS)
    assert re.search(r"\.done-line\s*\{[^}]*border-left: 4px solid var\(--ok\)", CSS)
    assert re.search(r"\.item \.done-line\s*\{[^}]*border: 0", CSS)


def test_a_badge_is_one_neutral_style():
    badge = _rule(".badge, .badge.flag, .badge.plan")
    assert "background: var(--wash)" in badge and "color: var(--ink)" in badge


def test_the_new_targets_are_44px_under_a_finger():
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    for sel in (".item-foot summary", ".item-foot a", "details.sec > summary", ".lines .line > a"):
        assert re.search(re.escape(sel) + r"[^{]*\{[^}]*min-height: 44px", coarse), sel

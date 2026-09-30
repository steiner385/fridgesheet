"""One token source for the screen and the paper (fridgesheet/tokens.py).

The stylesheet's token lines are generated from it, the printed sheet and the charts read it,
and DESIGN.md's palette names it. These hold the four in step: a colour changed in one place
and not the others is the drift the extract step (2026-09-30) removed.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from fridgesheet import sheet, tokens
from fridgesheet.web import charts, tiers

REPO = Path(__file__).resolve().parents[1]
CSS = (REPO / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")
DESIGN = (REPO / "DESIGN.md").read_text(encoding="utf-8")


def _css_line(key: str) -> str:
    pattern = r"^:root \{.*\}$" if key == ":root" else r'^\[data-tier="%s"\]\s*\{.*\}$' % key
    m = re.search(pattern, CSS, re.M)
    assert m, f"app.css has no {key} token line"
    return m.group(0)


# --- the stylesheet is generated from the source ---------------------------------------------

@pytest.mark.parametrize("key", [":root", *tokens.TIERS])
def test_the_stylesheets_token_lines_are_the_sources(key):
    assert _css_line(key) == tokens.css_lines()[key], f"run scripts/tokens_css.py ({key} differs)"


def test_the_generator_reports_the_stylesheet_in_step():
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "tokens_css.py"), "--check"], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_tier_redefines_every_tier_token():
    """The Whole-Tier Rule: a tier sets every token whether or not it changes it."""
    assert set(tokens.TIERS) == set(tiers.TIERS)
    for tier in tokens.TIERS:
        moved = tokens.tier_tokens(tier)
        assert tuple(moved) == tokens.TIER_TOKENS
        assert set(tokens.TIERS[tier]) <= set(tokens.TIER_TOKENS), f"{tier} moves a token no tier may move"
    assert tokens.tier_tokens("older") == {t: tokens.ROOT[t] for t in tokens.TIER_TOKENS}     # what ships at the root


def test_the_roles_wear_the_palette():
    for name, role in tokens.ROLE_OF.items():
        assert tokens.ROOT[role] == tokens.COLORS[name], (name, role)
    for role, value in tokens.ROOT.items():
        if value.startswith("#"):
            assert value in tokens.COLORS.values(), f"--{role} is a colour outside the palette"


# --- the paper and the charts read the same source ------------------------------------------

def test_the_printed_sheets_colours_are_the_pages():
    hexes = {name: getattr(sheet, name).hexval() for name in ("RED", "AMBER", "BLUE", "GREEN", "PURPLE", "GREY", "INK", "RULE")}
    want = {"RED": "warn", "AMBER": "late", "BLUE": "accent", "GREEN": "ok", "PURPLE": "check", "GREY": "muted", "INK": "ink", "RULE": "rule"}
    for name, role in want.items():
        assert hexes[name].lower() == "0x" + tokens.ROOT[role][1:].lower(), name
    source = (REPO / "fridgesheet" / "sheet.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9A-Fa-f]{6}\b", source), "sheet.py carries a literal colour"
    assert "colors.black" not in source


def test_the_charts_strokes_are_the_palettes():
    assert charts.SERIES_COLORS == tokens.CHART["series"] and charts.OUTCOME_COLORS == tokens.CHART["outcomes"]
    for value in (*charts.SERIES_COLORS, *charts.OUTCOME_COLORS.values()):
        assert value in tokens.COLORS.values(), value
    source = (REPO / "fridgesheet" / "web" / "charts.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9A-Fa-f]{6}\b", source), "charts.py carries a literal colour"


def test_the_print_ramp_is_the_sheets():
    assert (sheet.H1.fontSize, sheet.H1.leading) == tokens.PRINT["h1"]
    assert (sheet.CELL.fontSize, sheet.CELL.leading) == tokens.PRINT["cell"]
    assert (sheet.SM.fontSize, sheet.SM.leading) == tokens.PRINT["small"]
    assert (sheet.TINY.fontSize, sheet.TINY.leading) == tokens.PRINT["tiny"]
    assert (sheet.GROUP_HEAD.fontSize, sheet.GROUP_HEAD.leading) == tokens.PRINT["group"]


# --- DESIGN.md names the same values ---------------------------------------------------------

def _design_colors() -> dict[str, str]:
    front = DESIGN.split("---", 2)[1]
    block = re.search(r"^colors:\n((?:  [^\n]+\n)+)", front, re.M).group(1)
    return dict(re.findall(r'^  ([a-z0-9-]+): "(#[0-9a-f]{6})"', block, re.M))


def test_design_md_names_the_palette_and_the_tier_variants():
    listed = _design_colors()
    assert listed, "DESIGN.md has no colours in its frontmatter"
    for name, value in listed.items():
        m = re.fullmatch(r"(.+)-(early|middle)", name)
        if m and m.group(1) in tokens.ROLE_OF:
            assert tokens.tier_tokens(m.group(2))[tokens.ROLE_OF[m.group(1)]] == value, name
        else:
            assert tokens.COLORS.get(name) == value, name
    for name, value in tokens.COLORS.items():
        if name not in ("teal-pencil", "brown-pencil"):                 # chart-only strokes, listed under Charts
            assert listed.get(name) == value, f"DESIGN.md does not name {name}"

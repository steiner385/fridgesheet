"""Colour and type discipline from the 2026-09-29 critique (.impeccable/critique/), the first
polish pass against DESIGN.md ("The Teacher's Ledger").

Four rules, held here the way test_web_tier_css.py holds the tiers. CSS is not executed:

- The Red Pen Rule: red is for what the school recorded as not in. The sheet's word on a row
  wears the sheet's colour for that word (status_words.STATUS_TONE), so DUE TODAY is blue,
  LATE amber, PAPER — CHECK purple and only MISSING / ZERO red -- the same colours the
  printed sheet has always used (sheet.STATUS_COLOR).
- The Never-Smallest Rule: headings scale from the tier's root, so on the early tier's 20px
  page "Must finish" is not the smallest text above the fold.
- The One Voice Rule: the filled primary is the page's one main action; the first answer on a
  row is the default, drawn as a heavier stroke, not a fill.
- No literal colour in app.css outside the token blocks.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from fridgesheet import status_words
from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _coarse() -> str:
    return "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))


# --- the Red Pen Rule ------------------------------------------------------------------------

def test_the_status_tone_table_is_the_sheets_colour_table():
    """One table for paper and screen: the sheet's STATUS_COLOR and the page's word tone agree
    on every word, so a row cannot be red on screen and blue on the fridge."""
    from fridgesheet import sheet
    paper = {"RED": "red", "AMBER": "late", "PURPLE": "check", "BLUE": "due"}
    names = {sheet.RED: "RED", sheet.AMBER: "AMBER", sheet.PURPLE: "PURPLE", sheet.BLUE: "BLUE"}
    for word, colour in sheet.STATUS_COLOR.items():
        assert status_words.status_tone(word) == paper[names[colour]], word
    assert status_words.status_tone("DUE SUN") == "due"                     # any DUE <day>
    assert status_words.status_tone("Submitted, ungraded") == ""            # not a sheet word: no colour


def test_a_must_finish_row_wears_the_sheets_colour_not_red_for_being_due(tmp_path):
    conn = seed(tmp_path)
    ids = {n: conn.execute("SELECT id FROM items WHERE name = ?", (n,)).fetchone()["id"]
           for n in ("Vocabulary", "Worksheet 3", "Participation", "Homework 4")}
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text

    def row(name):
        return re.search(r'<div class="item([^"]*)" id="mf-%d"' % ids[name], body).group(1).strip()

    assert row("Vocabulary") == "due" and row("Worksheet 3") == "due"         # due tonight / tomorrow
    assert row("Participation") == "check"                                   # HAC — NO GRADE: paper
    assert re.search(r'<span class="when word check">HAC — NO GRADE</span>', body)
    assert 'class="item red"' not in body                                    # nothing on Alex's plan is not-in yet


def test_the_school_evidence_changed_note_is_the_apps_inference_and_not_red():
    panel = (WEB / "templates" / "_plan_panel.html").read_text(encoding="utf-8")
    assert 'class="inset warn"' not in panel and 'class="inset changed"' in panel
    assert re.search(r"\.inset\.changed\s*\{[^}]*border-left: 0", CSS)                    # no left rule (finish review 2026-09-29)
    assert re.search(r"\.inset\.changed strong\s*\{[^}]*color: var\(--accent\)", CSS)      # a ballpoint lead word instead
    assert not re.search(r"\.inset\.warn\s*\{", CSS)


# --- the Never-Smallest Rule -----------------------------------------------------------------

@pytest.mark.parametrize("selector, factor", [
    ("main h3", "1.125"), (".sec-head h3, details.sec > summary h3", "1.125"),
    (".page-head h2", "1.5"), (".sec-head h3.kid-head", "1.375"), (".card h3.report-title", "1.25"),
])
def test_a_heading_steps_up_from_the_tiers_root(selector, factor):
    assert re.search(r"font-size: calc\(var\(--type-root\) \* " + re.escape(factor) + r"\)", _rule(selector)), selector


@pytest.mark.parametrize("selector", ["main h4", ".sec h4", ".card h2, .card h3", ".update-action h3"])
def test_a_subheading_is_the_tiers_root_size(selector):
    assert "font-size: var(--type-root)" in _rule(selector), selector


def test_no_heading_is_pinned_in_pixels():
    for sel in ("main h3", "main h4", ".sec h4", ".page-head h2", ".card h3"):
        for m in re.finditer(r"(?m)^([^{}\n]+)\{([^{}]*)\}", CSS):
            if sel in [s.strip() for s in m.group(1).split(",")]:
                assert not re.search(r"font-size:\s*\d+px", m.group(2)), f"{sel} pinned: {m.group(2).strip()}"


def test_filter_labels_and_class_links_follow_the_body():
    assert "font-size" not in _rule(".filters label")                         # 14px was off every ramp
    links = _rule("table.items td > small a, table.work td.item small a")
    assert "text-decoration: none" in links                                    # seven identical underlines per table
    assert re.search(r"table\.items td > small a:hover, [^{]*:focus-visible[^{]*\{[^}]*text-decoration: underline", CSS)


# --- the One Voice Rule ----------------------------------------------------------------------

def test_the_default_answer_is_a_heavier_stroke_not_a_fill():
    default = _rule("button.default")
    assert "border: 2px solid var(--accent)" in default and "font-weight: 600" in default    # a ballpoint stroke, ink label
    assert "background: var(--accent)" not in default
    answers = (WEB / "templates" / "_answers.html").read_text(encoding="utf-8")
    assert "class=\"{{ 'default' if default }}\"" in answers and "'primary'" not in answers


@pytest.mark.parametrize("path", ["/", "/kids/Alex/plan", "/kids/Sam/plan", "/kids/Alex", "/kids/Alex/check-in", "/questions"])
def test_a_page_has_at_most_one_filled_primary(tmp_path, path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get(path).text
    assert len(re.findall(r'class="primary"', body)) <= 1, path


# --- tokens, not literals --------------------------------------------------------------------

def test_the_warn_wash_is_a_token_and_no_hex_literal_hides_in_a_rule():
    for sel in (".notice.warn", ".stale"):
        assert "var(--warn-wash)" in _rule(sel), sel
    blocks = re.findall(r"(?m)^([^{}\n]+)\{([^{}]*)\}", CSS)
    for selector, body in blocks:
        if selector.strip().startswith((":root", "[data-tier=")):
            continue
        if selector.strip() in ("pre.log",):                                  # the one black console, on purpose
            continue
        assert not re.search(r"#[0-9a-fA-F]{3,6}\b", body), f"{selector.strip()} carries a literal colour"


def test_the_late_and_check_colours_read_as_text():
    """Amber Pencil as chart stroke (#b8860b) is 3.3:1 on white; as a bold word beside a due
    date it needs 4.5:1, so the screen token is darker."""
    root = re.search(r":root\s*\{([^}]*)\}", CSS).group(1)
    late = re.search(r"--late:\s*(#[0-9a-f]{6})", root).group(1)
    check = re.search(r"--check:\s*(#[0-9a-f]{6})", root).group(1)

    def lum(h):
        def lin(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)

    for colour in (late, check):
        assert (1.05) / (lum(colour) + 0.05) >= 4.5, colour                  # on paper white


# --- touch and the strip ----------------------------------------------------------------------

def test_the_today_card_links_reach_a_finger():
    coarse = _coarse()
    for sel in (".tally a", ".card > h3 a"):
        assert re.search(re.escape(sel) + r"[^{]*\{[^}]*min-height: 44px", coarse), sel
    dash = (WEB / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert re.search(r'<label class="tick"><input type="checkbox" id="refresh-first"', dash)


def test_the_strip_keeps_a_space_before_a_question_count():
    """"Alex1" on the phone: inline-flex drops the text node's space between the name and the count."""
    strip = re.search(r"@media \(max-width: 1023px\)\s*\{(.*?)\n\}", CSS, re.S).group(1)
    assert re.search(r"\.rail nav a\s*\{[^}]*gap: \.3em", strip)
    assert re.search(r"\.rail nav a, \.rail nav \.rail-more > summary\s*\{[^}]*gap: \.3em", _coarse())

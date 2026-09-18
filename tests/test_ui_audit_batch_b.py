"""Batch B of the UI/UX audit (#40): the phone.

CSS is not executed here, so these pin the rules and the markup that carry the three fixes;
the numbers behind them (content start 1,450px -> ~100px, tap targets 21px -> 44px) were
measured in a real browser against the deployed app before and after.
"""
from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _block(media: str) -> str:
    m = re.search(r"@media \(" + re.escape(media) + r"\)\s*\{(.*?)\n\}", CSS, re.S)
    assert m, f"no @media ({media}) block"
    return m.group(1)


# --- item 1: the rail stacked above the content on a phone --------------------------------

def test_under_800px_the_rail_is_a_horizontal_strip_not_a_stack():
    narrow = _block("max-width: 800px")
    assert re.search(r"\.rail nav\s*\{[^}]*display: flex", narrow)
    assert re.search(r"\.rail nav\s*\{[^}]*overflow-x: auto", narrow)
    assert re.search(r"\.rail nav \.group\s*\{[^}]*display: none", narrow), "group labels take a row each"
    assert re.search(r"\.rail nav a\s*\{[^}]*white-space: nowrap", narrow), "a wrapped link breaks the strip"


def test_the_rail_still_marks_the_current_page():
    """The strip drops the group labels; it must not drop the one cue that says where you are."""
    html = (WEB / "templates" / "base.html").read_text(encoding="utf-8")
    assert "'current' if current ==" in html
    assert re.search(r"\.rail nav a\.current[^{]*\{[^}]*background", CSS)


# --- item 2: 21px tap targets --------------------------------------------------------------

def test_touch_targets_are_44px_on_a_coarse_pointer():
    coarse = _block("pointer: coarse")
    assert "min-height: 44px" in coarse
    for sel in ("button", "select", ".rail nav a", ".badge[href]"):
        assert sel in coarse.split("min-height: 44px")[0], f"{sel} is not in the 44px rule"


def test_desktop_keeps_the_compact_layout():
    """The 44px rule is scoped to a coarse pointer; a mouse must not get phone-sized controls."""
    head = CSS.split("@media")[0]
    assert "min-height: 44px" not in head


# --- item 15: every button looked the same, including the one that spends paper ------------

def test_buttons_have_one_look_and_the_paper_one_is_the_primary(tmp_path):
    assert re.search(r"(?m)^button\s*\{[^}]*border-radius", CSS), "a base button rule replaces the browser default"
    assert re.search(r"button\.primary\s*\{[^}]*background: var\(--accent\)", CSS)
    assert re.search(r"button\.danger\s*\{[^}]*var\(--warn\)", CSS)
    dash = (WEB / "templates" / "dashboard.html").read_text(encoding="utf-8")
    print_btn = re.search(r'<button[^>]*hx-post="/jobs/print"[^>]*>Print now</button>', dash).group(0)
    assert 'class="primary"' in print_btn
    assert "hx-confirm" in print_btn, "the paper still asks first"
    for other in ("/jobs/refresh", "/jobs/preview"):
        btn = re.search(r'<button[^>]*hx-post="' + other + '"[^>]*>', dash).group(0)
        assert "primary" not in btn, "only one primary per page"


def test_the_print_confirmation_names_the_printer(tmp_path):
    from web_fixtures import app_for
    c = app_for(tmp_path, worker=True)
    c.app.state.fridgesheet.settings.printer = "Brother MFC-J4335DW Printer"
    page = c.get("/", headers={"host": "127.0.0.1"}).text
    # The apostrophe is template text, not a variable, so autoescape leaves it alone.
    assert 'hx-confirm="Print today\'s sheet on Brother MFC-J4335DW Printer?"' in page


def test_delete_is_the_danger_button_and_saves_are_primary():
    t = WEB / "templates"
    assert 'class="danger">Delete' in (t / "reports.html").read_text(encoding="utf-8")
    for name in ("settings.html", "schedules.html", "report_builder.html", "_settings_files.html"):
        assert 'class="primary"' in (t / name).read_text(encoding="utf-8"), name


def test_the_items_table_scrolls_sideways_on_a_phone_instead_of_clipping():
    """Seen on the live app at 390px: Handed in, Grade, Sources and Flag fell off the right
    edge with nothing to scroll. A block-level table scrolls on its own."""
    narrow = _block("max-width: 800px")
    assert re.search(r"table\.items\s*\{[^}]*display: block", narrow)
    assert re.search(r"table\.items\s*\{[^}]*overflow-x: auto", narrow)

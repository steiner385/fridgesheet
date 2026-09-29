"""The Student Planner: the visual world chosen 2026-09-29 (direction contract in
.impeccable/surfaces/fridgesheet-web-templates-checkin-html.md, seed 5d8bc5ca). A child's Plan
is her planner spread: Tonight and Tomorrow as printed day boxes side by side, a checkbox on every
line, the sheet's word as a highlighter stroke, the family's steps in ballpoint beneath. CSS is
not executed here; the rendered markup is."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def test_the_spread_holds_tonight_and_tomorrow_side_by_side_and_the_rest_beneath(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    spread = re.search(r'<div class="mf-spread">(.*?)</div>\s*(?:<p class="muted">|</section>)', body, re.S).group(1)
    assert spread.index('data-section="tonight"') < spread.index('data-section="tomorrow"') < spread.index('data-section="paper"')
    grid = _rule(".mf-spread")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in grid
    assert re.search(r'\.mf-spread > \.mf-section\[data-section="tonight"\], \.mf-spread > \.mf-section\[data-section="tomorrow"\]\s*\{[^}]*grid-column: auto', CSS)
    strip = re.search(r"@media \(max-width: 1023px\)\s*\{\s*\.mf-spread(.*?)\n\}", CSS, re.S).group(1)
    assert "minmax(0, 1fr)" in strip                                          # stacked on a phone, Tonight first


def test_a_day_box_is_printed_with_its_label_along_the_top_edge():
    box = _rule(".mf-section")
    assert "border: 1.5px solid var(--box)" in box and "background: var(--paper)" in box
    label = _rule(".mf-section > h4")
    assert "text-transform: uppercase" in label and "font-size: var(--type-small)" in label and "border-bottom: 1.5px solid var(--box)" in label


def test_every_line_has_a_checkbox_and_an_answered_line_is_struck_through():
    assert "border: 2px solid var(--box)" in _rule("div.item::before")
    assert re.search(r"\.item:has\(> \.done-line\)::before[^{]*\{[^}]*background: var\(--ok\)", CSS)
    assert re.search(r"\.item:has\(> \.done-line\) \.item-head \.name[^{]*\{[^}]*text-decoration: line-through", CSS)
    assert "transition: background-color 180ms ease-out" in _rule("div.item::before")   # the one authored motion
    assert re.search(r"\.item\.ok::after[^{]*\{[^}]*transform: rotate\(45deg\)", CSS)  # the tick is drawn, not a glyph


def test_the_sheets_word_is_a_highlighter_stroke():
    word = _rule(".item-head .when.word")
    assert "padding: 0 .35em" in word and "box-decoration-break: clone" in word
    assert "background: var(--hl-due)" in _rule(".item-head .when.word.due")


def test_the_family_writes_in_pencil_the_default_answer_in_ballpoint_and_only_links_are_blue():
    assert "color: var(--muted)" in _rule(".ours")
    assert re.search(r"\.plan \.item\.step \.facts\s*\{[^}]*color: var\(--muted\)", CSS)
    assert "border: 2px solid var(--accent)" in _rule("button.default")
    assert re.search(r"\.plan > \.sec-head\s*\{[^}]*border-bottom: 1\.5px solid var\(--box\)", CSS)


def test_the_page_is_warm_planner_white_with_a_faint_ruling_and_no_spiral():
    root = re.search(r":root\s*\{([^}]*)\}", CSS).group(1)
    assert re.search(r"--wash:\s*#fffdf6", root) and re.search(r"--box:\s*#8fa3b8", root)
    for tier in ("early", "middle"):
        wash = re.search(rf'\[data-tier="{tier}"\][^{{]*\{{[^}}]*--wash:\s*(#[0-9a-f]{{6}})', CSS).group(1)
        r, g, b = (int(wash[i:i + 2], 16) for i in (1, 3, 5))
        assert r >= g >= b, (tier, wash)                                       # warm, never a cool blue-white
    ruling = _rule(".checkin-main")
    assert "repeating-linear-gradient" in ruling and "color-mix" in ruling     # faint, pitched to the line
    assert ".checkin-main::before" not in CSS and "radial-gradient" not in CSS  # the spiral was not approved
    narrow = re.search(r"@media \(max-width: 1023px\)\s*\{\s*\.mf-spread(.*?)\n\}", CSS, re.S).group(1)
    assert "width: max-content" in narrow                                      # the highlighter hugs its word on a phone


def test_tonight_and_tomorrow_are_printed_even_when_empty(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Sam/plan").text                        # Sam has nothing due tonight or tomorrow
    assert 'data-section="tonight"' in body and 'data-section="tomorrow"' in body
    assert "Nothing due tonight" in body and "Nothing due tomorrow" in body
    assert 'data-section="later"' not in body                                  # the other sections still need rows


def test_a_step_carries_the_sheets_word_as_a_highlight_not_a_badge(tmp_path):
    from uuid import uuid4
    from fridgesheet.web.stores import plans
    from tests.web_fixtures import NOW
    conn = seed(tmp_path)
    vocab = conn.execute("SELECT id FROM items WHERE name = 'Vocabulary'").fetchone()["id"]
    plans.save(conn, 1, dict(title="Vocabulary", family_account="", next_step="Ten words tonight", owner="Alex", planned_for="2026-09-15",
                             minutes=15, state="planned", position=10, evidence="{}", recorded_by=""),
               now=NOW.isoformat(), request_key=str(uuid4()), item_id=vocab)
    conn.close()
    panel = app_for(tmp_path).get("/kids/Alex/plan").text
    assert '<span class="word due">Must finish · DUE TODAY</span>' in panel
    assert 'class="badge">Must finish' not in panel
    assert "background: var(--hl-due)" in _rule(".item-head .meta .word.due")


def test_the_header_line_is_ruled_with_the_dates_bold(tmp_path):
    from uuid import uuid4
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.post("/kids/Alex/check-in/finish", data={"available_minutes": "40", "next_check": "2026-09-22", "summary": "Quiz first.",
                                               "recorded_by": "Mom", "request_key": str(uuid4())}, follow_redirects=False)
    hint = re.search(r'<p class="tab-hint">(.*?)</p>', c.get("/kids/Alex/plan").text, re.S).group(1)
    assert hint.count("<strong>") >= 2                                         # last and next check-in dates
    assert "font-weight: 400" in _rule(".tab-hint") and "border-bottom: 1.5px solid var(--box)" in _rule(".tab-hint")


def test_no_side_tab_is_left_on_the_item_or_the_family_line():
    for sel in (".item", ".ours"):
        assert "border-left: 4px" not in _rule(sel) and "border-left: 3px" not in _rule(sel), sel


def test_a_fold_with_nothing_in_it_is_one_quiet_line(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Sam/plan").text
    assert body.count('class="sec queue-group quiet empty"') >= 3            # the three review groups on an empty page
    assert 'class="sec queue-group quiet empty" open><summary><h3>Completed steps</h3>' in body
    assert "font-weight: 400" in _rule(".sec.empty > summary h3")

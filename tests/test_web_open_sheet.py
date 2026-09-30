"""The sheet on a screen (the Student Planner, Open work; the surface brief in
.impeccable/surfaces/, 2026-09-30): the kids as tabs on the ruled line, the chosen kid's sheet
beneath as one paper page in the sheet's order, every row a planner line with the sheet's word,
the trailers at the foot and the legend once. Every kid's page stays in the markup; the tabs
hide the others. Nothing is answered here."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, client_with_grades, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _section(body: str, key: str) -> str:
    start = body.index(f'id="{key}"')
    return body[start:body.index("</section>", start)]


def test_the_kids_are_tabs_and_the_first_kids_page_is_shown(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    tabs = re.search(r'<nav class="child-nav kid-tabs" aria-label="Whose sheet">(.*?)</nav>', body, re.S).group(1)
    assert re.search(r'<a href="/open\?kid=Alex" hx-get="/open\?kid=Alex" hx-target="#open-pages" hx-swap="outerHTML" hx-push-url="true" aria-current="page">Alex <span class="tally">· 5</span></a>', tabs)
    assert re.search(r'<a href="/open\?kid=Sam"[^>]*>Sam <span class="tally">· 2</span></a>', tabs) and 'aria-current="page">Sam' not in tabs
    assert re.search(r'<a href="/open\?kid=all" class="every"[^>]*>Every kid</a>', tabs)
    # Both pages are in the markup (parity of rows at every tier); Sam's is hidden behind the tab.
    assert re.search(r'<section class="sec kid" id="Alex" aria-labelledby="sheet-Alex">', body)
    assert re.search(r'<section class="sec kid" id="Sam" aria-labelledby="sheet-Sam" hidden>', body)


def test_a_tab_turns_the_page_and_every_kid_lays_them_all_out(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    sam = c.get("/open?kid=Sam").text
    assert 'aria-current="page">Sam' in sam and re.search(r'id="Alex" aria-labelledby="sheet-Alex" hidden>', sam)
    assert re.search(r'id="Sam" aria-labelledby="sheet-Sam">', sam)
    every = c.get("/open?kid=all").text
    assert "hidden>" not in every and 'class="every" hx-get="/open?kid=all" hx-target="#open-pages" hx-swap="outerHTML" hx-push-url="true" aria-current="page"' in every
    assert 'aria-current="page">Alex' not in c.get("/open?kid=Nobody").text or re.search(r'id="Alex" aria-labelledby="sheet-Alex">', c.get("/open?kid=Nobody").text)
    # htmx swaps the tabs and the pages together, nothing else.
    partial = c.get("/open?kid=Sam", headers={"HX-Request": "true"}).text
    assert partial.lstrip().startswith('<div id="open-pages">') and 'class="page-head"' not in partial and "<main" not in partial
    assert partial.count("<section") == 2 and 'aria-current="page">Sam' in partial


def test_a_kids_page_reads_like_the_sheet(tmp_path):
    seed(tmp_path).close()
    alex = _section(app_for(tmp_path).get("/open").text, "Alex")
    # The label along the top edge, the date line, the two halves as day rows with their counts.
    assert re.search(r'^[^>]*>\s*<h3 id="sheet-Alex"><a href="/kids/Alex">Alex</a> — open work <span class="tally">· 5 open</span></h3>', alex)
    assert re.search(r'<p class="as-of muted">Tue 9/15 · next 14 days plus overdue within 14</p>', alex)
    assert '<h4 class="day">Still fixable <span class="tally">· 2</span></h4>' in alex
    assert '<h4 class="day coming">Coming due <span class="tally">· 3</span></h4>' in alex
    # The sheet's order: soonest-closing window first, then by due date.
    assert alex.index("Participation") < alex.index("Lab notebook") < alex.index("Coming due") < alex.index("Vocabulary") < alex.index("Worksheet 3") < alex.index("Reading log")
    # The sheet's word on its highlighter; no ask line and no answers on this page.
    assert re.search(r'<span class="when word check">HAC — NO GRADE</span>', alex) and re.search(r'<span class="when word due">DUE ', alex)
    assert 'class="ask-line"' not in alex and 'class="answers"' not in alex and "<button" not in alex
    # Read-only: no foot (the name is the one way into the record), no Edit on the step, and the
    # sheet's own "until" sub-line in pencil where the working pages say the whole sentence.
    assert 'class="item-foot"' not in alex and ">Edit</a>" not in alex and "Plan a step" not in alex
    assert re.search(r'<p class="facts">[^<]+ <span class="until muted">Until Tue 9/22</span></p>', alex)
    assert "Late work is usually accepted" not in alex
    # A question is a link to the page that asks, in the line's meta (#85).
    assert re.search(r'<a class="badge" href="/questions\?kid=Alex#q-\d+" aria-label="Question about Participation">question</a>', alex)
    # The trailer at the foot, in pencil.
    assert re.search(r'<p class="muted trailer">Not shown:\s*<a href="/kids/Alex\?show=past_window">1 past the late-work window', alex)


def test_the_legend_is_printed_once_under_the_pages(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    assert body.count('<p class="legend sheet-legend muted">') == 1
    legend = re.search(r'<p class="legend sheet-legend muted">(.*?)</p>', body, re.S).group(1)
    for word, tone in (("MISSING / ZERO", "red"), ("LATE", "late"), ("PAPER — CHECK / IN CLASS — CHECK / HAC — NO GRADE", "check"), ("DUE TODAY / TOMORROW", "due")):
        assert f'<span class="word {tone}">{word}</span>' in legend, word
    assert body.index("sheet-legend") > body.index('id="Sam"')


def test_a_younger_kids_sheet_is_in_their_words_and_size(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=9, Sam=5).get("/open?kid=all").text
    sam = _section(body, "Sam")
    assert 'data-tier="early"' in body[body.index('id="Sam"') - 60:body.index('id="Sam"') + 80]
    assert re.search(r'<span class="when word red">(Marked zero|Teacher hasn|Not handed in)', sam)     # the sheet's word in a fifth-grader's words


def test_the_page_box_and_the_tabs_are_drawn_in_the_planners_rules():
    page = _rule(".open-sheets > .sec.kid")
    assert "background: var(--paper)" in page and "border: 1.5px solid var(--box)" in page and "border-radius: 2px" in page
    label = _rule(".open-sheets > .sec.kid > h3")
    assert "border-bottom: 1.5px solid var(--box)" in label and "text-transform: uppercase" in label and "letter-spacing: .08em" in label
    assert "border-top: 1.5px solid var(--box)" in _rule(".open-sheets > .sec.kid > h4.day.coming")      # the printed rule between the halves
    assert "max-width: 1100px" in _rule(".open-sheets")                                                   # the planner's measure
    assert "margin-left: auto" in _rule(".kid-tabs .every")
    assert "color: var(--muted)" in _rule(".kid-tabs .tally") and ".kid-tabs .count" not in CSS
    assert "open-list" not in CSS and "kid-head" not in CSS
    for tone in ("red", "late", "check", "due"):
        assert _rule(f".sheet-legend .word.{tone}")

"""The chooser as the planner's cover (the Student Planner; the surface brief in
.impeccable/surfaces/, 2026-10-01): the mark and the name, today's date as a day row in pencil
over the question, one tall stroke button per kid, the grown-up's quieter beneath, the
remembering sentence as the last pencil line, on the ruled paper."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def test_the_cover_is_dated_and_reads_top_to_bottom(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.cookies.clear()
    body = c.get("/who").text
    assert '<main class="planner-main">' in body and '<aside class="rail">' not in body and 'header class="status"' not in body
    assert re.search(r'<p class="day">[A-Z][a-z]{2} \d+/\d+</p>\s*<h2>Who&#39;s looking\?</h2>', body)   # the fixture's clock: Thu 9/17
    assert re.search(r'<h2>Who&#39;s looking\?</h2>\s*<form method="post" action="/who">\s*<button name="who" value="Alex"(?: data-tier="[a-z]+")?>Alex</button><button name="who" value="Sam"', body)
    assert re.search(r'<button name="who" value="family" class="grownup">A grown-up</button>\s*</form>\s*<p class="muted remember">This browser will remember\. You can change it any time\.</p>', body)
    assert "card" not in body.split("<body")[1]


def test_the_cover_is_drawn_in_the_planners_rules():
    button = _rule(".who button")
    assert "border-radius: 2px" in button and "border: 1px solid var(--control)" in button and "background: var(--paper)" in button
    assert "box-shadow" not in button and "12px" not in button
    day = _rule(".who .day")
    assert "text-transform: uppercase" in day and "color: var(--muted)" in day and "font-weight: 650" in day
    assert "color: var(--muted)" in _rule(".who button.grownup") and "background: var(--wash)" in _rule(".who button.grownup")
    assert "font-size: var(--type-small)" in _rule(".who .remember")
    assert "border-bottom: 1px solid var(--rule)" in day and "text-align: left" in day         # the page's own day row, not a label over the heading
    assert "min-height: 100dvh" in _rule("main.planner-main:has(> .who)")                        # the ruled paper is the page
    assert "background: var(--wash)" in _rule(".who button:hover") and ".who button:hover, .who button:focus-visible" not in CSS
    coarse = "\n".join(re.findall(r"@media \(pointer: coarse\)\s*\{(.*?)\n\}", CSS, re.S))
    assert re.search(r"\.who h1 \.brand\s*\{[^}]*min-height: 44px", coarse)
    assert "rounded.chooser" not in Path(__file__).resolve().parents[1].joinpath("DESIGN.md").read_text(encoding="utf-8")

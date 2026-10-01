"""Trends as the report card page (the Student Planner; the surface brief in .impeccable/surfaces/,
2026-10-01): the Kid and Weeks words in the sort line's grammar, then one paper page for the
year with its label along the top edge, the hand-in record as its first line, the charts as
figures on the page, the numbers behind a pencil fold, the longest open as pencil lines."""
from __future__ import annotations

import re
from pathlib import Path

from tests.web_fixtures import app_for, history, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def test_the_choices_are_words_in_the_sort_lines_grammar(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/trends").text
    line = re.search(r'<p class="sort trend-words" role="group" aria-label="Show">(.*?)</p>', body, re.S).group(1)
    assert re.search(r'<span class="muted">Kid</span> <a href="/trends\?weeks=8" aria-current="true">all</a> · <a href="/trends\?kid=Alex&weeks=8">Alex</a> · <a href="/trends\?kid=Sam&weeks=8">Sam</a>', line)
    assert re.search(r'<span class="muted">Weeks</span> <a href="/trends\?weeks=4">4</a> · <a href="/trends\?weeks=8" aria-current="true">8</a> · <a href="/trends\?weeks=16">16</a>', line)
    assert 'class="badge' not in body and 'class="filters"' not in body
    alex = c.get("/trends?kid=Alex&weeks=4").text
    assert 'href="/trends?kid=Alex&weeks=4" aria-current="true">Alex</a>' in alex and 'href="/trends?kid=Alex&weeks=4" aria-current="true">4</a>' in alex


def test_the_year_is_one_paper_page_with_its_parts_as_day_rows(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    assert re.search(r'<div class="planner-main trends-page">\s*<section class="sec report-card" aria-labelledby="year-head">\s*<h3 id="year-head">The year so far <span class="tally">· last 8 weeks</span></h3>', body)
    days = re.findall(r'<h4 class="day">([^<]*)</h4>', body)
    assert days == ["On-time hand-ins", "Grades", "Work due each week", "Open the longest"]
    assert re.search(r'<p class="record-line"><b>\d+% on time</b> so far · <span>\d+ on time</span> · <span>\d+ late</span> · <span class="[^"]*">\d+ not done</span>', body)
    assert body.count("data-chart-canvas") >= 2
    assert re.search(r'<details class="fold numbers"><summary>The numbers</summary>\s*<div class="table-wrap">\s*<table class="items">', body)
    assert re.search(r'<ul class="longest">(<li><span class="kid">(Alex|Sam)</span> · [^<]+ <span class="muted">· [^<]* · \d+ days</span></li>)+</ul>', body) and "Quiz 1 <span" in body
    assert re.search(r'<span>\d+ unknown</span>', body) and re.search(r'class="warn">\d+ not done</span>', body)   # Red Pen for the school's word alone
    assert 'class="cards"' not in body and 'class="card"' not in body[body.index("<main"):]
    assert body.index("record-line") < body.index("data-chart-canvas") < body.index('class="fold numbers"') < body.index('class="longest"')


def test_a_kids_page_names_the_kid_on_the_label_and_draws_one_chart(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/trends?kid=Sam").text
    assert "The year so far <span class=\"tally\">· last 8 weeks · Sam</span>" in body
    assert body.count("data-chart-canvas") == 2                                             # one kid: one grade chart and the weeks
    assert '<span class="kid">' not in body[body.index('class="longest"'):]                  # one kid: the label says whose


def test_an_empty_database_still_says_one_thing(tmp_path):
    body = app_for(tmp_path).get("/trends").text
    assert "Not enough history yet" in body and "report-card" not in body


def test_the_page_and_its_figures_are_drawn_in_the_planners_rules():
    page = _rule(".trends-page > .report-card")
    assert "background: var(--paper)" in page and "border: 1.5px solid var(--box)" in page and "border-radius: 2px" in page
    label = _rule(".trends-page > .report-card > h3")
    assert "text-transform: uppercase" in label and "border-bottom: 1.5px solid var(--box)" in label
    chart = _rule(".report-card .chart-holder")
    assert "border: 0" in chart and "background: none" in chart                                    # a figure on the page, not a box in a box
    assert "max-width: 1100px" in _rule(".trends-page")
    assert "border-bottom: 1px solid var(--rule)" in _rule(".report-card .longest li")

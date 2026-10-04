"""The report card (spec 2026-10-03 §7.1): every class one ruled line with the official number,
the scale's letter, whose number in pencil, and one sentence on how it is figured; a fourth
tab on the kid's rail and in the grown-up's child nav; prints as it stands."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web import app as webapp
from tests.web_fixtures import app_for, client_with_grades, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", CSS)
    assert m, f"no {selector} rule"
    return m.group(1)


def _lines(body: str) -> list[str]:
    return re.findall(r'<li class="report-line"[^>]*>(.*?)</li>', body, re.S)


def test_one_line_per_class_with_number_letter_whose_and_how(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source='canvas' AND short_name='Honors English 9'").fetchone()["id"]
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert '<h2>Report card <span class="subtitle">Alex' in body
    assert '<span class="count">2 classes</span>' in body
    lines = _lines(body)
    assert len(lines) == 2
    eng = next(l for l in lines if "Honors English 9" in l)
    assert re.search(r'<span class="big">88\.00</span>\s*<span class="letter">B</span>', eng)
    assert '<p class="whose">HAC average · as of 9/11</p>' in eng
    assert '<p class="how">Adds up: 44 of 50 points.</p>' in eng
    assert f'href="/kids/Alex/courses/{cid}"' in eng                      # a paired class links the Canvas page


def test_a_class_without_a_number_is_a_line_with_a_dash(tmp_path):
    conn = seed(tmp_path)
    with conn:
        conn.execute("UPDATE grade_observations SET average = NULL, current = NULL")
    conn.close()
    lines = _lines(app_for(tmp_path).get("/kids/Alex/report-card").text)
    assert len(lines) == 2 and all('<span class="big">—</span>' in l and "No average yet." in l for l in lines)


def test_every_line_has_a_row_id_so_tiers_can_be_compared(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert len(re.findall(r'<li class="report-line" id="row-\d+"', body)) == 2


def test_the_how_is_said_in_the_kids_tier(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex/report-card").text
    assert "Your points: 44 out of 50." in body


def test_the_fold_explains_how_averages_are_figured(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert re.search(r'<details class="sec quiet how-figured">\s*<summary><h3>How averages are figured</h3>', body)
    assert "total points" in body and "graded work only" in body


def test_report_card_is_the_fourth_tab_in_both_shells(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/kids/Alex/report-card").text
    nav = re.search(r'<nav class="child-nav".*?</nav>', body, re.S).group(0)
    assert nav.index(">Assignments<") < nav.index('aria-current="page">Report card<')
    kid = app_for(tmp_path)
    kid.cookies.set(webapp.WHO_COOKIE, "Alex")
    rail = re.search(r'<nav class="kid">.*?</nav>', kid.get("/kids/Alex/report-card").text, re.S).group(0)
    assert rail.index('href="/kids/Alex"') < rail.index('href="/kids/Alex/report-card" class="current">Report card</a>') < rail.index('<details class="rail-more"')


def test_the_page_prints_its_lines_and_the_print_button_is_the_pages_only_action(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert '<p class="page-actions"><button type="button" data-print>Print</button></p>' in body
    assert body.count("<h2>") == 1


def test_the_child_navs_state_line_belongs_to_the_other_pages_not_this_one(tmp_path):
    """`_child_nav.html` prints the last check-in (or the first-check-in nudge) under the tabs on
    Check-in, Plan and Assignments; the report card has no such state and must not borrow it."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/report-card").text
    assert 'class="tab-hint"' not in body and "Start with what" not in body


def test_an_unknown_kid_is_404(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).get("/kids/Nobody/report-card").status_code == 404


def test_the_lines_are_drawn_in_the_planners_rules():
    for sel in (".report-card-page .report-lines", ".report-card-page .report-line", ".report-card-page .report-line .big", ".report-card-page .report-line .whose"):
        _rule(sel)
    assert "border-bottom: 1px solid var(--rule)" in _rule(".report-card-page .report-line")


# --- what moves it (spec 2026-10-04 §7.1) --------------------------------------------------------

def test_the_line_says_what_would_move_it_when_the_account_is_sound(tmp_path):
    seed(tmp_path).close()
    lines = _lines(app_for(tmp_path).get("/kids/Alex/report-card").text)
    eng = next(l for l in lines if "Honors English 9" in l)
    assert '<p class="lever">Best move: Vocabulary (10 pts), worth up to +2.0. An A needs 10 of the next 50 points.</p>' in eng
    alg = next(l for l in lines if "Algebra I" in l)
    assert 'class="lever"' not in alg                                                  # no breakdown: no second sentence


def test_the_early_tier_says_it_without_cant(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex/report-card").text
    lever = body.split('class="lever">', 1)[1].split("</p>", 1)[0]
    assert lever.startswith("Best move: Vocabulary (10 pts), worth up to +2.0.") and "can" not in lever.lower()


def test_the_lever_line_is_drawn_in_ink_under_the_how():
    assert "var(--muted)" not in _rule(".report-card-page .report-line .lever")        # ink: it is the one thing to do
    assert "max-width: var(--measure)" in _rule(".report-card-page .report-line .lever")

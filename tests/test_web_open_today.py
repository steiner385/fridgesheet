"""Open work and Today on the verdicts (#85), and one reading of the sheet's day options (#20)."""
from __future__ import annotations

import re
from datetime import date

import pytest

from fridgesheet import config, late_rules, open_items
from fridgesheet.web.stores import items, students
from tests.web_fixtures import NOW, app_for, seed, snapshot

QUARTER = late_rules.LateRules(late_rules.Rule(late_days=None, until="quarter_end"), [], [date(2026, 10, 30)])


# --- #20: one accessor, and the page agreeing with the sheet -------------------------------

@pytest.mark.parametrize("raw, want", [(7, 7), ("7", 7), (" 21 ", 21), (None, 14), ("", 14), ("x", 14), (0, 14), (-3, 14)])
def test_a_day_option_is_a_positive_whole_number_or_the_default(raw, want):
    assert config.day_option({"days_ahead": raw}, "days_ahead") == want


def test_the_web_reads_both_day_options_through_the_accessor(tmp_path):
    seed(tmp_path).close()
    config.save_config_doc(tmp_path / "config.toml", {"reports": {"open-work": {"days_ahead": -3, "overdue_days": 10}}})
    c = app_for(tmp_path)
    c.app.state.fridgesheet.reload()
    assert c.app.state.fridgesheet.days_ahead() == 14         # a hand-edited -3, as the sheet now reads it
    assert c.app.state.fridgesheet.overdue_days() == 10


def test_still_fixable_is_what_the_sheet_prints_overdue(tmp_path):
    """The divergence #20 demonstrated: with the late-work window running to the quarter's end,
    Homework 4 (due 8/20) can still earn credit, but it is more than overdue_days past due, so
    the sheet drops it. The page must drop it too."""
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    web = items.open_work(conn, alex, now=NOW, rules=QUARTER, days_ahead=14, overdue_days=14)
    conn.close()
    sheet = open_items.open_items(snapshot()["students"]["Alex"], "Alex", NOW, days_ahead=14, overdue_days=14, rules=QUARTER)
    printed = sorted(i.name for i in sheet.items if i.overdue)
    assert "Homework 4" not in printed, "the fixture must still show the sheet's cut"
    assert sorted(v.name for v in web.fixable) == printed
    assert "Homework 4" in [v.name for v in web.past_window]  # counted in the trailer, as on paper


def test_the_open_page_and_today_follow_overdue_days(tmp_path):
    seed(tmp_path).close()
    (tmp_path / "late-rules.toml").write_text('[quarters]\nq1 = 2026-10-30\n\n[[rule]]\ncourse = "Algebra"\nuntil = "quarter_end"\n', encoding="utf-8")
    config.save_config_doc(tmp_path / "config.toml", {"reports": {"open-work": {"overdue_days": 14}}})
    c = app_for(tmp_path)
    c.app.state.fridgesheet.reload()
    body = c.get("/open").text
    alex, sam = body.index('id="Alex"'), body.index('id="Sam"')
    fixable = body[alex:body.index("Coming due", alex)]
    assert "Homework 4" not in fixable and "Participation" in fixable


def test_the_open_page_states_parity_with_the_sheet(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    assert "the same rows the printed sheet shows" in body
    assert "can appear here and not on paper" not in body


# --- #85: Open work on the three-column work list ------------------------------------------

def test_open_work_uses_the_three_column_work_list(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    assert body.count('class="items work open-list"') == 3              # Alex fixable + coming due, Sam fixable
    assert "Where it stands" in body
    for old in ("<th>Handed in</th>", "<th>Grade</th>", "<th>Credit thru</th>", "<th>Flag</th>", "<th>Pts</th>"):
        assert old not in body, old
    # Every row carries its detail row, closed until opened.
    assert re.search(r'<tr class="detail" hidden><td colspan="3" id="detail-\d+"></td></tr>', body)


def test_a_fixable_row_still_says_when_credit_ends(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    assert "Credit thru Tue 9/22" in body and "Credit thru Thu 9/24" in body


def test_a_question_on_open_work_links_to_its_card(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    w = items.open_work(conn, alex, now=NOW, rules=late_rules.LateRules(late_rules.Rule(), [], []), days_ahead=14)
    conn.close()
    asking = [v for v in w.fixable + w.upcoming if v.asks]
    assert asking, "the fixture must have a question on Open work for this to mean anything"
    body = app_for(tmp_path).get("/open").text
    for v in asking:
        assert f'href="/questions?kid=Alex#q-{v.id}"' in body


# --- #85: Today leads with questions and still fixable ------------------------------------

def test_today_counts_questions_and_still_fixable_not_actionable(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/").text
    assert "actionable" not in body
    rail = c.app.state.fridgesheet
    conn = seed(tmp_path)
    for key in ("Alex", "Sam"):
        s = students.by_key(conn, key)
        counts = items.dashboard_counts(conn, s, now=NOW, rules=rail.rules(), days_ahead=14, overdue_days=14)
        n = counts.questions
        words = f'<span class="big">{n}</span> question{"s" if n != 1 else ""} to answer' if n else "Nothing to answer"
        assert words in body
        assert f'href="/open#{key}"><span class="big">{counts.fixable}</span> still fixable</a>' in body
    conn.close()
    assert 'href="/questions?kid=Alex"' in body


def test_today_question_count_matches_the_rail(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    rail = re.search(r'id="qcount-Alex" class="count">(\d*)<', body).group(1) or "0"
    card = re.search(r'(\d+)</span> questions? to answer', body[body.index("<main"):])
    assert (card.group(1) if card else "0") == rail

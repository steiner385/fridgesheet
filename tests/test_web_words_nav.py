"""Words and navigation left over from the persona review: #54 tabs, #52 filters, #34 red on
the Open page, and sentences that start with a capital."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web import verdicts
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _table(body):
    return body.split('id="items"', 1)[1]


# --- #54: the tabs say what they are ---------------------------------------------------------

def test_the_third_tab_is_assignments_and_every_tab_says_what_it_is_for(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    pages = {"/kids/Alex/check-in": "Talk it through", "/kids/Alex/plan": "What you agreed to do",
             "/kids/Alex": "Everything the school lists"}
    for path, hint in pages.items():
        body = c.get(path).text
        nav = re.search(r'<nav class="child-nav".*?</nav>', body, re.S).group(0)
        assert ">Assignments<" in nav and ">All work<" not in nav, path
        assert hint in body, path


# --- #52: filters in family words, including the ones that were missing ----------------------

def test_you_can_filter_to_one_answer_such_as_asked_the_teacher(tmp_path):
    conn = seed(tmp_path)
    lab = conn.execute("SELECT id FROM items WHERE name = 'Lab notebook'").fetchone()["id"]
    flags.set_flag(conn, lab, "ask_teacher", now="2026-09-15T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex?flagged=ask_teacher").text
    assert '<option value="ask_teacher" selected>' in body
    table = _table(body)
    assert "Lab notebook" in table and "Vocabulary" not in table


def test_you_can_filter_by_what_the_app_says(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?verdict=waiting").text
    assert 'name="verdict"' in body and '<option value="waiting" selected>' in body
    table = _table(body)
    assert "Essay draft" in table and "Lab notebook" in table
    assert "Vocabulary" not in table and "Participation" not in table


def test_a_filter_that_widens_to_everything_says_so(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for q in ("?outcome=not_done", "?verdict=decided", "?flagged=done"):
        assert "Showing everything that matches" in c.get("/kids/Alex" + q).text, q
    assert "Showing everything that matches" not in c.get("/kids/Alex").text


# --- #34: on the Open page, red is only the school's not-done ---------------------------------

def test_a_no_in_handed_in_is_not_red():
    red = re.search(r"([^{}]*)\{\s*color:\s*var\(--warn\);\s*font-weight:\s*600;\s*\}", CSS)
    assert red and "td.handed.no" not in red.group(1)
    assert "td.grade.missing" in red.group(1) and "td.grade.zero" in red.group(1)


# --- sentences start with a capital ----------------------------------------------------------

def test_a_verdict_sentence_that_starts_with_a_value_is_capitalised():
    assert verdicts.say("facts.awaiting_grade", "", {"kind": "paper", "due": "Thu 9/10"}).startswith("Paper work")

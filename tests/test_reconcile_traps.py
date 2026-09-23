"""Batch 2 of the persona UX review: the flag menu's interaction traps (#37, #38, #40). The
Reconcile card #41 was about is gone; its flag now shows on the kid page's badge and asked line."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed

ASKED = "2026-09-12T08:00:00-04:00"
APP_JS = Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.js"


def _item_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _flag_forms(body: str) -> list[str]:
    return re.findall(r'<form class="[^"]*"[^>]*hx-post="/items/\d+/flag".*?</form>', body, re.S)


def _first_button(form: str) -> str:
    return re.search(r"<button[^>]*>", form).group(0)


def _setup(tmp_path, flag=None, text=""):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    if flag:
        flags.set_flag(conn, qid, flag, now=ASKED, text=text)
    conn.close()
    return app_for(tmp_path), qid


# -- #37: Enter in the reason box must not mark the item done ------------------------------

def test_enter_on_an_unflagged_item_submits_nothing(tmp_path):
    """Implicit submission uses a form's first submit button; a disabled one submits nothing."""
    c, qid = _setup(tmp_path)
    forms = _flag_forms(c.get(f"/items/{qid}").text)      # the raw flag menu, behind the detail card's More
    assert forms
    for form in forms:
        first = _first_button(form)
        assert "hidden" in first and "disabled" in first, first


def test_enter_on_a_flagged_item_resaves_its_current_flag(tmp_path):
    c, qid = _setup(tmp_path, "follow_up")
    for form in _flag_forms(c.get(f"/items/{qid}").text):
        first = _first_button(form)
        assert 'value="follow_up"' in first and "hidden" in first and "disabled" not in first, first


# -- #38: the flag's reason shows on a plain load ---------------------------------------------

def test_the_flag_reason_shows_without_a_just_saved_message(tmp_path):
    c, qid = _setup(tmp_path, "ask_teacher", text="emailed Mr Hoch")
    body = c.get(f"/items/{qid}").text
    assert re.search(r"Flag: ask teacher[^<]*emailed Mr Hoch", body), body


def test_the_reason_is_not_printed_twice_after_saving(tmp_path):
    c, qid = _setup(tmp_path)
    body = c.post(f"/items/{qid}/flag", data={"flag": "ask_teacher", "text": "emailed Mr Hoch"}).text
    visible = re.sub(r'value="[^"]*"', "", body)
    visible = re.sub(r'<details class="history">.*?</details>', "", visible, flags=re.S)   # History lists the flag too, by design           # the input keeps it for editing; that is not a display
    assert visible.count("emailed Mr Hoch") == 1


# -- #40: a swap focuses the card, not its first input ---------------------------------------

def test_the_detail_card_offers_its_heading_as_the_focus_target(tmp_path):
    c, qid = _setup(tmp_path)
    body = c.get(f"/items/{qid}").text
    assert re.search(r'<h2[^>]*tabindex="-1"[^>]*data-focus-target', body) or \
        re.search(r'<h2[^>]*data-focus-target[^>]*tabindex="-1"', body)


def test_app_js_focuses_the_named_target_not_the_first_input():
    js = APP_JS.read_text()
    assert "[data-focus-target]" in js
    assert 'querySelector("textarea, input")' not in js

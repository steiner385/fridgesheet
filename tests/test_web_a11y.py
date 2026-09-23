"""Accessibility for the secondary caregiver (#43) and the work table at zoom (#53)."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet.web.stores import flags, notes
from tests.web_fixtures import app_for, seed

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")
JS = (WEB / "static" / "app.js").read_text(encoding="utf-8")


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _hex_luminance(h):
    h = h.lstrip("#")
    def ch(c):
        c = int(c, 16) / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(h[i:i + 2]) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b="#ffffff"):
    la, lb = sorted((_hex_luminance(a), _hex_luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _root_var(name):
    return re.search(rf":root\s*\{{[^}}]*--{name}:\s*(#[0-9a-fA-F]{{6}})", CSS).group(1)


# --- #43: announcements, labels, the note editor, the pressed flag ----------------------------

def test_every_page_has_one_polite_live_region(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert len(re.findall(r'<div id="announce"[^>]*role="status"[^>]*aria-live="polite"', body)) == 1


def test_app_js_announces_what_a_swap_says():
    assert "[data-announce]" in JS and 'getElementById("announce")' in JS


def test_answering_and_note_changes_carry_an_announcement(tmp_path):
    conn = seed(tmp_path)
    pid = _id(conn, "Participation")
    conn.close()
    c = app_for(tmp_path)
    assert 'data-announce="' in c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""}).text
    added = c.post("/notes", data={"target_type": "item", "target_id": pid, "body": "Asked Mr Hoch"}).text
    assert 'data-announce="Note added"' in added


def test_the_items_table_announces_how_many_rows_it_shows(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?show=all", headers={"HX-Request": "true"}).text
    assert re.search(r'data-announce="\d+ assignments? shown"', body)


def test_the_flag_menu_is_a_labelled_group_with_the_current_flag_pressed(tmp_path):
    conn = seed(tmp_path)
    qid = _id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "follow_up", now="2026-09-15T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{qid}").text
    menu = re.search(r'<form class="flagmenu".*?</form>', body, re.S).group(0)
    assert "<fieldset" in menu and "<legend>Correct the school record</legend>" in menu
    assert re.search(r'<label[^>]*>\s*Why \(optional\)\s*<input name="text"', menu)
    assert re.search(r'<button[^>]*value="follow_up"[^>]*aria-pressed="true"', menu)
    assert re.search(r'<button[^>]*value="done"[^>]*aria-pressed="false"', menu)


def test_notes_have_a_label_and_edit_in_place_with_the_text_already_there(tmp_path):
    conn = seed(tmp_path)
    qid = _id(conn, "Quiz 1")
    notes.add(conn, "item", qid, "Asked Mr Hoch about the missing mark", now="2026-09-15T14:30:00-04:00")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{qid}").text
    assert "hx-prompt" not in body
    assert re.search(r'<textarea name="body"[^>]*>Asked Mr Hoch about the missing mark</textarea>', body)   # the edit form
    assert re.search(r'<label[^>]*>\s*<span[^>]*>Add a note</span>\s*<textarea name="body"[^>]*required', body)
    assert re.search(r'aria-label="Delete the note from [^"]+"', body)


# --- #53: the table at zoom, the sort headers, the detail rows ----------------------------------

def test_sort_links_keep_an_id_and_inactive_headers_say_so(tmp_path):
    seed(tmp_path).close()
    head = re.search(r"<thead>(.*?)</thead>", app_for(tmp_path).get("/kids/Alex?sort=due").text, re.S).group(1)
    assert 'id="sort-due"' in head and 'id="sort-name"' in head
    assert head.count('aria-sort="none"') == 2
    assert re.search(r'<span class="arrow" aria-hidden="true">', head)


def test_detail_rows_are_hidden_until_opened_and_links_say_so(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert re.search(r'<tr class="detail" hidden>', body)
    assert not re.search(r'<tr class="detail">', body)
    assert re.search(r'hx-target="#detail-\d+"[^>]*aria-expanded="false"', body) or \
        re.search(r'aria-expanded="false"[^>]*hx-target="#detail-\d+"', body)
    assert "tr.detail" in JS and "aria-expanded" in JS


def test_the_detail_card_can_be_closed(tmp_path):
    conn = seed(tmp_path)
    qid = _id(conn, "Quiz 1")
    conn.close()
    assert re.search(r'<button[^>]*data-close-detail[^>]*>Close</button>', app_for(tmp_path).get(f"/items/{qid}").text)
    assert "data-close-detail" in JS


def test_the_table_scrolls_inside_its_own_box_at_any_width(tmp_path):
    seed(tmp_path).close()
    assert '<div class="table-wrap">' in app_for(tmp_path).get("/kids/Alex").text
    assert re.search(r"\.table-wrap\s*\{[^}]*overflow-x:\s*auto", CSS)


def test_controls_and_small_text_are_readable():
    assert _contrast(_root_var("control")) >= 3.0                          # button, select and input borders
    assert _contrast(_root_var("muted")) >= 7.0                            # small muted text
    for sel in (r"td \.rel", r"td \.at", r"\.badge", r"\.note \.meta"):
        size = re.search(sel + r"\s*\{[^}]*font-size:\s*(\d+)px", CSS)
        assert size and int(size.group(1)) >= 13, sel
    assert re.search(r"button[^{]*\{[^}]*border:\s*1px solid var\(--control\)", CSS)


def test_a_detail_row_is_shown_before_focus_moves_into_it():
    """Found in Chrome: the focus handler ran first and focused inside a still-hidden row, so
    focus fell to <body>. htmx runs afterSwap listeners in the order app.js adds them."""
    unhide = JS.index("row.hidden = false")
    focus = JS.index('querySelector("[data-focus-target]")')
    assert unhide < focus

"""Evidence and notes left over from the persona review: #44 (Canvas link, history), #47
(notes that collapse, keep their lines, and reach the check-in), #51 (a grade names its source)."""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet import config
from fridgesheet.web.stores import flags, notes
from tests.web_fixtures import app_for, history, seed

CSS = (Path(__file__).resolve().parents[1] / "fridgesheet" / "web" / "static" / "app.css").read_text(encoding="utf-8")


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


# --- #44: the record links to Canvas and shows what changed ------------------------------------

def test_the_record_links_to_the_assignment_in_canvas(tmp_path):
    conn = seed(tmp_path)
    qid, pid = _id(conn, "Quiz 1"), _id(conn, "Participation")
    conn.close()
    c = app_for(tmp_path)
    base = config.Settings(home=tmp_path).canvas_base
    assert f'href="{base}/courses/5/assignments/77"' in c.get(f"/items/{qid}").text
    assert "/assignments/" not in c.get(f"/items/{pid}").text           # HAC-only: nothing in Canvas to open


def test_the_detail_shows_the_items_history(tmp_path):
    conn = history(tmp_path)
    qid = _id(conn, "Quiz 1")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{qid}").text
    hist = body[body.index("<summary>History"):]
    assert "Grade posted" in hist and "Now missing" in hist


# --- #47: notes -----------------------------------------------------------------------------

def test_an_empty_notes_block_is_a_single_add_a_note_disclosure(tmp_path):
    conn = seed(tmp_path)
    qid = _id(conn, "Quiz 1")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{qid}").text
    notes_html = body[body.index('<div class="notes"'):]
    assert "No notes yet." not in notes_html
    assert re.search(r'<details class="add-note"><summary>Add a note</summary>', notes_html)


def test_a_note_keeps_its_line_breaks():
    assert re.search(r"\.note \.body\s*\{[^}]*white-space:\s*pre-wrap", CSS)


def test_the_check_in_evidence_shows_the_latest_note_and_a_new_step_starts_from_it(tmp_path):
    conn = seed(tmp_path)
    lab = _id(conn, "Lab notebook")
    notes.add(conn, "item", lab, "Handed it in on paper Tuesday", now="2026-09-15T08:00:00-04:00")
    flags.set_flag(conn, lab, "follow_up", now="2026-09-15T08:05:00-04:00", text="check with Mr Hoch")
    conn.close()
    c = app_for(tmp_path)
    form = c.get(f"/kids/Alex/check-in/step?item_id={lab}").text
    assert "Handed it in on paper Tuesday" in form                                  # the evidence card
    family = re.search(r'<textarea name="family_account"[^>]*>(.*?)</textarea>', form, re.S).group(1)
    assert "Handed it in on paper Tuesday" in family and "check with Mr Hoch" in family


# --- #51: a grade says which gradebook it came from --------------------------------------------

def test_a_grade_in_the_table_names_its_gradebook(tmp_path):
    seed(tmp_path).close()
    table = app_for(tmp_path).get("/kids/Sam?show=all").text.split('id="items"', 1)[1]
    assert re.search(r"0/10\s*·\s*Canvas", table)


def test_a_grade_on_the_open_page_names_its_gradebook(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/open").text
    sam = body[body.index('id="Sam"'):]
    assert re.search(r'0/10 <span class="src">Canvas</span>', sam)

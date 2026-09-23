"""Answering a question card (spec 5 and 6.1)."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _setup(tmp_path, name="Participation"):
    conn = seed(tmp_path)
    iid = _id(conn, name)
    conn.close()
    return app_for(tmp_path), iid


def test_answering_sets_the_flag_and_collapses_to_one_line_with_undo(tmp_path):
    c, pid = _setup(tmp_path)
    r = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    assert r.status_code == 200
    assert f'id="q-{pid}"' in r.text and "Undo" in r.text and "Participation" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, pid)["flag"] == "done"


def test_undo_restores_the_previous_state_and_the_question(tmp_path):
    c, pid = _setup(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    r = c.post(f"/items/{pid}/undo", data={"prev": ""})
    assert "Was it handed in?" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, pid) is None


def test_a_double_submitted_answer_leaves_one_flag(tmp_path):
    """Review Focus 5."""
    c, pid = _setup(tmp_path)
    first = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    second = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    assert "Undo" in first and "Undo" in second
    conn = db.open_db(tmp_path)
    assert len([r for r in flags.history(conn, pid) if r["cleared_at"] is None]) == 1


def test_asking_the_teacher_offers_their_email(tmp_path):
    """Spec 5: the asked line carries a mailto when the course has a teacher email."""
    c, pid = _setup(tmp_path)
    body = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    assert "mailto:hoch@example.org" in body


def test_the_record_says_as_of_when(tmp_path):
    c, pid = _setup(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    assert "as of" in c.post(f"/items/{pid}/undo", data={"prev": ""}).text


def test_an_unknown_answer_is_refused(tmp_path):
    c, pid = _setup(tmp_path)
    assert c.post(f"/items/{pid}/answer", data={"answer": "bogus", "prev": ""}).status_code == 400


def test_the_question_card_offers_the_record_and_plan_links(tmp_path):
    c, pid = _setup(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    body = c.post(f"/items/{pid}/undo", data={"prev": ""}).text
    assert "See the record" in body and "Add a note" in body
    assert f"check-in/step?item_id={pid}" in body          # the "Not yet, plan it" answer


# --- final-review fixes ------------------------------------------------------------------

def _stale_homework(tmp_path):
    """Homework 4 flagged done on 9/1, before the seed's refresh recorded it missing: stale."""
    conn = seed(tmp_path)
    hid = _id(conn, "Homework 4")
    flags.set_flag(conn, hid, "done", now="2026-09-01T08:00:00-04:00", text="handed in")
    conn.close()
    return app_for(tmp_path), hid


def test_undo_after_answering_a_stale_question_brings_the_question_back(tmp_path):
    """Review 1: undo must restore the flag *and its date*, so the stale question returns."""
    c, hid = _stale_homework(tmp_path)
    card = c.get(f"/items/{hid}").text
    assert "Still done?" in card and 'name="prev_set_at" value="2026-09-01T08:00:00-04:00"' in card
    for answer in ("clear", "confirm"):
        c.post(f"/items/{hid}/answer", data={"answer": answer, "prev": "done", "prev_set_at": "2026-09-01T08:00:00-04:00"})
        body = c.post(f"/items/{hid}/undo", data={"prev": "done", "prev_set_at": "2026-09-01T08:00:00-04:00"}).text
        assert "Still done?" in body, answer
        assert "facts." not in body and "where." not in body
        conn = db.open_db(tmp_path)
        active = flags.active(conn, hid)
        assert (active["flag"], active["set_at"], active["text"]) == ("done", "2026-09-01T08:00:00-04:00", "handed in")
        conn.close()


def test_reopening_shows_where_it_stands_in_words(tmp_path):
    """Review 3: "No, reopen it" left a raw `where.not_done` on the answered line."""
    conn = seed(tmp_path)
    cid = _id(conn, "Cell diagram")                     # Sam's: missing in Canvas, still inside its window
    flags.set_flag(conn, cid, "done", now="2026-09-01T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).post(f"/items/{cid}/answer", data={"answer": "clear", "prev": "done"}).text
    assert "where." not in body and "Cell diagram" in body and "Missing" in body


def test_answering_from_the_tables_expanded_row_swaps_that_card(tmp_path):
    """Review 4: the detail's card must not share an id with the section card above it."""
    import re
    c, pid = _setup(tmp_path)
    page = c.get("/kids/Alex").text
    detail = c.get(f"/items/{pid}").text
    page_ids = set(re.findall(r'id="([^"]+)"', page))
    detail_ids = set(re.findall(r'id="([^"]+)"', detail))
    assert not (page_ids & detail_ids) - {"notes-item-%d" % pid}, page_ids & detail_ids
    target = re.search(r'hx-post="/items/%d/answer" hx-target="#([^"]+)"' % pid, detail).group(1)
    assert target in detail_ids
    slot = re.search(r'name="slot" value="([^"]+)"', detail).group(1)
    r = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": slot})
    assert f'id="{slot}"' in r.text

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

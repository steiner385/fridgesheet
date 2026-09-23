"""After an answer the page stays true (#71, #72); asking the teacher keeps its trail (#73);
missing work can be answered in one tap (#74)."""
from __future__ import annotations

import re
from urllib.parse import unquote

from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _setup(tmp_path, *names):
    conn = seed(tmp_path)
    ids = [_id(conn, n) for n in names]
    conn.close()
    return (app_for(tmp_path), *ids)


# --- #71 / #72 --------------------------------------------------------------------------------

def test_the_answered_line_names_the_answer(tmp_path):
    c, pid = _setup(tmp_path, "Participation")
    assert "Marked done on" in c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""}).text
    assert "Let go on" in c.post(f"/items/{pid}/answer", data={"answer": "ignore", "prev": "done"}).text


def test_answering_updates_the_row_the_heading_and_the_counts(tmp_path):
    c, pid = _setup(tmp_path, "Participation")
    body = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""}).text
    row = re.search(r'<template>\s*<tr id="row-%d"[^>]*hx-swap-oob="true">(.*?)</tr>\s*</template>' % pid, body, re.S)
    assert row and "Marked done on" in row.group(1) and "question" not in row.group(1)
    assert re.search(r'<span id="qcount-Alex" class="count" hx-swap-oob="true"></span>', body)
    assert re.search(r'<h3 id="q-head" hx-swap-oob="true">No more questions about', body)


def test_undo_is_announced_and_restores_the_counts(tmp_path):
    c, pid = _setup(tmp_path, "Participation")
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    body = c.post(f"/items/{pid}/undo", data={"prev": ""}).text
    assert "the question is back" in body
    assert re.search(r'<span id="qcount-Alex" class="count" hx-swap-oob="true">1</span>', body)


# --- #73 --------------------------------------------------------------------------------------

def test_an_asked_item_keeps_its_date_and_email_everywhere(tmp_path):
    conn = seed(tmp_path)
    pid = _id(conn, "Participation")
    flags.set_flag(conn, pid, "ask_teacher", now="2026-09-15T08:00:00-04:00")
    conn.close()
    c = app_for(tmp_path)
    kid = c.get("/kids/Alex").text
    waiting = kid[kid.index("Waiting"):kid.index('id="items"')]
    assert "Participation" in waiting and "Asked the teacher on 9/15" in waiting and "mailto:hoch@example.org" in waiting
    q = c.get("/questions").text
    assert "Waiting on the teacher" in q and "Participation" in q
    assert "You asked the teacher on 9/15" in c.get(f"/items/{pid}").text


def test_the_record_names_the_teacher_with_a_prefilled_email(tmp_path):
    c, qid = _setup(tmp_path, "Quiz 1")
    body = c.get(f"/items/{qid}").text
    assert "Michael Hoch" in body
    m = re.search(r'href="mailto:hoch@example\.org\?subject=([^"&]+)&amp;body=([^"]+)"', body)
    assert m and "Quiz 1" in unquote(m.group(1))
    text = unquote(m.group(2))
    assert "Due" in text and "Canvas:" in text and "HAC:" in text and "/assignments/77" in text


# --- #74 --------------------------------------------------------------------------------------

def test_a_missing_row_can_be_answered_in_one_tap(tmp_path):
    c, cell, hw = _setup(tmp_path, "Cell diagram", "Homework 4")
    body = c.get(f"/items/{cell}").text
    assert re.search(r'<button name="answer" value="done"[^>]*>It.{1,6}s handed in</button>', body)
    assert "Canvas marks it missing." in body
    assert re.search(r'<button name="answer" value="ignore"[^>]*>Let it go</button>', c.get(f"/items/{hw}").text)

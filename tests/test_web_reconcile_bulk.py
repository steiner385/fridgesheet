"""Reconcile's one bulk action: ignore every past-credit item for one kid (#40 item 10)."""
from __future__ import annotations

import re

from lakota_grades.web.stores import flags, students
from web_fixtures import app_for, history


def _past_credit_count(page: str, kid: str) -> int:
    m = re.search(r"Ignore all (\d+) past-credit item", page.split(f"<h3>{kid}</h3>")[1].split("<h3>")[0])
    return int(m.group(1)) if m else 0


def test_the_offer_names_the_count_and_takes_them_all_for_one_kid_only(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    before = c.get("/reconcile", headers={"host": "127.0.0.1"}).text
    n = _past_credit_count(before, "Alex")
    assert n >= 1, "the fixture's Homework 4 is past its credit window"
    assert 'name="case_kind" value="past_credit"' in before

    after = c.post("/reconcile/flag-all", data={"kid": "Alex", "case_kind": "past_credit"},
                   headers={"host": "127.0.0.1", "Origin": "http://127.0.0.1"}).text
    assert _past_credit_count(after, "Alex") == 0                       # the offer is gone
    assert "Homework 4" not in after                                        # and so is the card

    from lakota_grades.web import db
    conn = db.open_db(tmp_path)
    al = students.by_key(conn, "Alex")["id"]
    ignored = conn.execute("""SELECT i.name, f.text FROM flags f JOIN items i ON i.id = f.item_id
                              WHERE f.flag = 'ignore' AND f.cleared_at IS NULL AND i.student_id = ?""", (al,)).fetchall()
    assert any(r["name"] == "Homework 4" for r in ignored)
    assert all(r["text"] == "past the late-work window" for r in ignored)
    # nobody else's flags moved
    others = conn.execute("SELECT COUNT(*) FROM flags f JOIN items i ON i.id = f.item_id WHERE f.flag = 'ignore' AND i.student_id != ?", (al,)).fetchone()[0]
    assert others == 0
    conn.close()


def test_only_known_bulk_kinds_and_known_kids(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    h = {"host": "127.0.0.1", "Origin": "http://127.0.0.1"}
    assert c.post("/reconcile/flag-all", data={"kid": "Alex", "case_kind": "disagree"}, headers=h).status_code == 400
    assert c.post("/reconcile/flag-all", data={"kid": "Nobody", "case_kind": "past_credit"}, headers=h).status_code == 404

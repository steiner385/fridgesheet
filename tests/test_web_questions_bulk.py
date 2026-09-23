"""Letting a kid's past-credit work go in one step (was Reconcile's bulk ignore)."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed


def _flag(tmp_path, name):
    conn = db.open_db(tmp_path)
    row = flags.active(conn, conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"])
    conn.close()
    return row["flag"] if row else None


def test_letting_go_flags_only_that_kids_past_credit_work(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).post("/questions/let-go", data={"kid": "Alex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/questions?kid=Alex"
    assert _flag(tmp_path, "Homework 4") == "ignore"          # Alex's one past-credit item
    assert _flag(tmp_path, "Lab notebook") is None            # still inside its window
    assert _flag(tmp_path, "Cell diagram") is None            # Sam's work is never touched


def test_an_unknown_kid_is_refused(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).post("/questions/let-go", data={"kid": "Nobody"}).status_code == 404

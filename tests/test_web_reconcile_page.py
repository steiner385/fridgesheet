"""The Reconcile page: every case, grouped by item, per kid, with quick flags."""
from __future__ import annotations

from tests.web_fixtures import app_for, seed


def test_reconcile_lists_every_case_grouped_by_item(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/reconcile")
    assert r.status_code == 200
    body = r.text
    assert body.index("Alex") < body.index("Sam")
    assert "Quiz 1" in body and "Canvas says MISSING, HAC shows 28" in body
    assert "Essay draft" in body and "Turned in, not graded yet" in body
    assert "Lab notebook" in body and "Paper work with no grade" in body
    assert "Participation" in body and "Only HAC lists this" in body
    assert "Homework 4" in body and "No longer earns credit" in body
    assert body.count("Quiz 1") == 1                                # one group per item, however many reasons
    assert "disagree" in body and "past credit" in body            # kind labels
    assert 'hx-post="/items/' in body and 'value="done"' in body   # quick flags


def test_reconcile_filters_by_kid_and_kind(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.get("/reconcile?kid=Sam")
    assert "Sam" in r.text and "Quiz 1" not in r.text
    r = c.get("/reconcile?kind=past_credit")
    assert "Homework 4" in r.text and "Quiz 1" not in r.text
    assert "disagree 1" in r.text and "one source 5" in r.text      # counts ignore the kind filter
    assert "No longer earns credit" in r.text and "gradebook yet" in r.text  # a kind selects groups, not reasons
    assert c.get("/reconcile?kind=bogus").status_code == 200        # an unknown kind shows everything


def test_reconcile_summary_counts_and_empty_state(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/reconcile").text
    assert "disagree 1" in body and "past credit 1" in body and "submitted ungraded 1" in body and "paper no grade 1" in body
    assert "one source 5" in body     # Participation, Lab notebook, Homework 4, Cell diagram, Safety quiz: each has a HAC twin course with no row
    from fridgesheet.web import db
    from fridgesheet.web.stores import flags
    conn = db.open_db(tmp_path)
    for name in ("Quiz 1", "Essay draft", "Lab notebook", "Participation", "Homework 4"):
        iid = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
        flags.set_flag(conn, iid, "ignore", now="2026-09-15T14:30:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/reconcile?kid=Alex").text
    assert "Nothing to reconcile" in body

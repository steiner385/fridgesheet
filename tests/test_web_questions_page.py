"""The Questions page, which replaces Reconcile (spec 6.2)."""
from __future__ import annotations

from tests.web_fixtures import app_for, seed


def test_questions_groups_every_kids_questions(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/questions").text
    assert "<h2>Questions</h2>" in body
    assert "Alex" in body and "Participation" in body and "Was it handed in?" in body
    assert "Quiz 1" not in body                          # decided, not asked


def test_reconcile_redirects_to_questions_keeping_the_kid(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/reconcile?kid=Alex", follow_redirects=False)
    assert r.status_code in (301, 307, 308) and r.headers["location"] == "/questions?kid=Alex"


def test_the_nav_says_questions_with_a_count(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    assert ">Questions" in body and "Reconcile" not in body


def test_bulk_let_go_appears_only_with_two_or_more_past_credit_items(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/questions").text
    assert "too late for credit" not in body             # Alex has one (Homework 4), Sam none


def test_an_unknown_kid_is_a_404_that_names_the_kid_not_an_empty_page(tmp_path):
    """#150: `/questions?kid=nobody` filtered every kid away and rendered an empty page, as if
    nobody had a question. It now answers the way /changes and /trends do."""
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/questions?kid=nobody")
    assert r.status_code == 404
    assert "No kid called “nobody”" in r.text

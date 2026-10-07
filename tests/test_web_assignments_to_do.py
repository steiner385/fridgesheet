"""Assignments as a to-do list (spec 2026-10-06): every open item once, in deadline order, the
gradebook questions under it, waiting and missed work folded, finished work in a Done view."""
from __future__ import annotations

from datetime import timedelta

from tests.web_fixtures import NOW, app_for, seed, week_line


def _id(tmp_path, name):
    conn = seed(tmp_path)
    try:
        return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
    finally:
        conn.close()


def test_a_missed_row_says_the_window_in_the_past_tense(tmp_path):
    """Protist Lab on Doug's page read "the late-work window has closed. Late work is usually
    accepted until Mon 10/5." -- a date already gone, in the present tense."""
    safety = _id(tmp_path, "Safety quiz")
    body = app_for(tmp_path, now=NOW + timedelta(days=30)).get("/kids/Sam?show=all").text
    line = week_line(body, safety)
    assert "is usually accepted until" not in line
    assert "Late work was accepted until" in line

"""Assignment types on the pages (spec 2026-10-04 assignment types §6)."""
from __future__ import annotations

import re

from fridgesheet.web import app as webapp
from web_fixtures import app_for, seed, snapshot


def _quiz_snapshot():
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"]
    eng[0]["group"] = "Quizzes & Tests"             # Quiz 1 -> assessment
    eng[5]["group"] = "Labs"                        # Lab notebook -> lab_project
    return snap


def _item_ids(conn):
    return {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM items")}


def test_the_row_says_the_family_and_everyday_work_says_nothing(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    ids = _item_ids(conn)
    page = app_for(tmp_path).get("/kids/Alex?show=all").text
    def line(name):
        # The week's line for the item: its name, then its meta, up to the line's end.
        m = re.search(rf'<b>{re.escape(name)}</b>.*?</div>', page, re.S)
        assert m, name
        return m.group(0)
    assert "test/quiz" in line("Quiz 1")
    assert "lab/project" in line("Lab notebook")
    assert not re.search(r"test/quiz|lab/project|participation", line("Essay draft"))

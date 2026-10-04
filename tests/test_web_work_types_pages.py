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


# --- the type filter (assignment types §6.3) --------------------------------------------------
def _pages(page):
    """The weekly pages only: the kid page's decided and waiting sections below them list all
    of the child's work whatever the filters, by design."""
    return page.split('id="items"', 1)[1].split('<section class="sec quiet', 1)[0]


def _names_listed(page):
    return set(re.findall(r"<b>([^<]+)</b>", page)) | set(re.findall(r'data-focus-target>([^<]+)</a>', page))


def test_the_type_filter_shows_one_family_and_counts_each(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    page = app_for(tmp_path).get("/kids/Alex?show=all&type=assessment").text
    week = _pages(page)
    assert "Quiz 1" in week and "Essay draft" not in week
    links = re.search(r'<p class="type-links">(.*?)</p>', page, re.S).group(1)
    assert re.search(r"Tests &amp; quizzes 1<", links) and re.search(r"Labs &amp; projects 1<", links)
    assert re.search(r'aria-current="true"[^>]*>Tests &amp; quizzes', links)


def test_the_type_filter_combines_with_outcome(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    page = _pages(app_for(tmp_path).get("/kids/Alex?type=practice&outcome=not_done").text)
    assert "Homework 4" in page                               # not done, and everyday work
    assert "Quiz 1" not in page                               # a quiz
    tests_only = _pages(app_for(tmp_path).get("/kids/Alex?type=assessment&outcome=not_done").text)
    assert "Homework 4" not in tests_only                     # not done, but everyday work


def test_an_unknown_type_is_ignored(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    c = app_for(tmp_path)
    plain = _pages(c.get("/kids/Alex?show=all").text)
    bogus = _pages(c.get("/kids/Alex?show=all&type=bogus").text)
    assert _names_listed(bogus) == _names_listed(plain)


def test_the_class_page_filters_by_type_too(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND name LIKE '%English%'").fetchone()["id"]
    page = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}?type=lab_project").text.split('id="items"', 1)[1]
    assert "Lab notebook" in page and "Quiz 1" not in page

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


# --- correcting a type, and class rules (assignment types §6.4) -------------------------------
def _post_type(c, iid, **form):
    return c.post(f"/items/{iid}/type", data=form)


def test_a_grown_up_corrects_one_item(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    iid = _item_ids(conn)["Essay draft"]
    c = app_for(tmp_path)
    detail = c.get(f"/items/{iid}").text
    assert "Type:" in detail and 'name="family"' in detail
    r = _post_type(c, iid, family="lab_project")
    assert r.status_code == 200 and "lab/project" in r.text
    assert conn.execute("SELECT family FROM item_types WHERE item_id = ?", (iid,)).fetchone()["family"] == "lab_project"


def test_choosing_the_guess_again_clears_the_correction(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    iid = _item_ids(conn)["Essay draft"]
    c = app_for(tmp_path)
    _post_type(c, iid, family="lab_project")
    _post_type(c, iid, family="practice")                    # what the ladder says anyway
    assert conn.execute("SELECT COUNT(*) FROM item_types").fetchone()[0] == 0


def test_a_correction_can_become_a_class_rule(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    ids = _item_ids(conn)
    c = app_for(tmp_path)
    detail = c.get(f"/items/{ids['Essay draft']}").text
    assert "applies to 4 items" in detail                     # group "Homework": the 4 English items left in it
    _post_type(c, ids["Essay draft"], family="participation", also_group="1")
    page = _pages(c.get("/kids/Alex?show=all&type=participation").text)
    assert "Reading log" in page and "Worksheet 3" in page   # the rule reached the rest of the group
    assert conn.execute("SELECT COUNT(*) FROM item_types").fetchone()[0] == 0   # the rule covers it


def test_a_generic_group_rule_is_only_for_everyday_work(tmp_path):
    snap = _quiz_snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"][1]["group"] = "Assignments"
    conn = seed(tmp_path, snap)
    iid = _item_ids(conn)["Essay draft"]
    r = _post_type(app_for(tmp_path), iid, family="assessment", also_group="1")
    assert conn.execute("SELECT COUNT(*) FROM type_rules").fetchone()[0] == 0
    assert "only for everyday work" in r.text
    assert conn.execute("SELECT family FROM item_types WHERE item_id = ?", (iid,)).fetchone()["family"] == "assessment"


def test_the_class_page_lists_its_rules_and_removes_one(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    ids = _item_ids(conn)
    c = app_for(tmp_path)
    _post_type(c, ids["Essay draft"], family="participation", also_group="1")
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND name LIKE '%English%'").fetchone()["id"]
    page = c.get(f"/kids/Alex/courses/{cid}").text
    assert "Type rules" in page and "“homework”" in page
    rule = conn.execute("SELECT id FROM type_rules").fetchone()["id"]
    r = c.post(f"/kids/Alex/courses/{cid}/type-rules/{rule}/remove", follow_redirects=False)
    assert r.status_code == 303 and conn.execute("SELECT COUNT(*) FROM type_rules").fetchone()[0] == 0


def test_a_child_cannot_correct_a_type(tmp_path):
    conn = seed(tmp_path, _quiz_snapshot())
    iid = _item_ids(conn)["Essay draft"]
    c = app_for(tmp_path)
    c.cookies.set(webapp.WHO_COOKIE, "Alex")
    assert 'name="family"' not in c.get(f"/items/{iid}").text
    assert _post_type(c, iid, family="assessment").status_code == 403
    assert conn.execute("SELECT COUNT(*) FROM item_types").fetchone()[0] == 0


# --- Diagnostics (assignment types §6.5) ------------------------------------------------------
def test_diagnostics_shows_how_each_class_was_typed(tmp_path):
    seed(tmp_path, _quiz_snapshot()).close()
    page = app_for(tmp_path).get("/diagnostics").text
    m = re.search(r'<section class="sec type-coverage">(.*?)</section>', page, re.S)
    assert m, "a Types section"
    sec = m.group(1)
    assert "Types" in sec and "Everyday by default" in sec
    # Honors English 9: Quiz 1 and Lab notebook typed by their Canvas group, the rest too ("Homework").
    row = re.search(r"<tr><td>[^<]*</td><td>Honors English 9</td>(.*?)</tr>", sec, re.S)
    assert row, sec
    nums = [int(n) for n in re.findall(r'<td class="num">(\d+)</td>', row.group(1))]
    assert nums[0] == sum(nums[1:]) and nums[4] >= 6        # every item counted once; 6 by gradebook name

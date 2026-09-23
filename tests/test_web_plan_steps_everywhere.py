"""An agreed plan step shows wherever its assignment does (#35), and planning one returns the
family to where they started (#48)."""
from __future__ import annotations

import re
from uuid import uuid4

from tests.web_fixtures import app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _form(title, **over):
    base = dict(title=title, family_account="", next_step="Ask Mr. Hoch whether it was collected", owner="Alex",
                planned_for="2026-09-16", minutes="", state="planned", position="10", request_key=str(uuid4()), revision="1")
    base.update(over)
    return base


def _with_step(tmp_path, name="Participation"):
    conn = seed(tmp_path)
    iid = _id(conn, name)
    conn.close()
    c = app_for(tmp_path)
    r = c.post(f"/kids/Alex/check-in/step?item_id={iid}", data=_form(name), follow_redirects=False)
    assert r.status_code == 303
    return c, iid


# --- #35: the step shows beside its assignment ------------------------------------------------

def test_the_item_detail_shows_the_agreed_step(tmp_path):
    c, iid = _with_step(tmp_path)
    body = c.get(f"/items/{iid}").text
    assert "Our step:" in body and "Ask Mr. Hoch whether it was collected" in body and "Alex" in body
    assert re.search(r'href="/kids/Alex/check-in/step\?step_id=\d+[^"]*">Edit', body)


def test_the_table_marks_a_row_that_is_in_the_plan(tmp_path):
    c, iid = _with_step(tmp_path)
    table = c.get("/kids/Alex?show=all").text.split('id="items"', 1)[1]
    row = re.search(rf'id="row-{iid}">(.*?)</tr>', table, re.S).group(1)
    assert "in plan" in row


def test_an_item_with_an_agreed_step_is_not_asked_about_again(tmp_path):
    c, iid = _with_step(tmp_path)
    kid = c.get("/kids/Alex").text
    assert f'id="q-{iid}"' not in kid and "question about" not in kid
    assert "Participation" not in c.get("/questions").text


def test_a_completed_step_does_not_hide_the_question(tmp_path):
    c, iid = _with_step(tmp_path)
    conn_step = re.search(r"step\?step_id=(\d+)", c.get(f"/items/{iid}").text).group(1)
    r = c.post(f"/kids/Alex/check-in/step?step_id={conn_step}", data=_form("Participation", state="done", revision="1"),
               follow_redirects=False)
    assert r.status_code == 303
    assert f'id="q-{iid}"' in c.get("/kids/Alex").text


# --- #48: planning a step returns to where you were -------------------------------------------

def test_the_plan_link_carries_the_page_you_are_on(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    conn = seed(tmp_path)
    iid = _id(conn, "Lab notebook")
    conn.close()
    detail = c.get(f"/items/{iid}", headers={"HX-Request": "true", "HX-Current-URL": "http://127.0.0.1:8433/kids/Alex?show=all&course=5"}).text
    assert "return_to=/kids/Alex%3Fshow%3Dall%26course%3D5" in detail


def test_the_step_form_goes_back_and_saves_back_to_that_page(tmp_path):
    conn = seed(tmp_path)
    iid = _id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    back = "/kids/Alex?show=all&course=5"
    form = c.get(f"/kids/Alex/check-in/step?item_id={iid}&return_to=/kids/Alex%3Fshow%3Dall%26course%3D5").text
    assert 'href="/kids/Alex?show=all&amp;course=5">' in form                   # back link and Cancel
    assert 'name="return_to" value="/kids/Alex?show=all&amp;course=5"' in form
    r = c.post(f"/kids/Alex/check-in/step?item_id={iid}", data=_form("Lab notebook", return_to=back), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == back


def test_an_outside_return_address_is_ignored(tmp_path):
    conn = seed(tmp_path)
    iid = _id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    for bad in ("https://evil.example/x", "//evil.example/x", "javascript:alert(1)", "kids/Alex"):
        r = c.post(f"/kids/Alex/check-in/step?item_id={iid}", data=_form("Lab notebook", return_to=bad), follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/kids/Alex/check-in"), bad


def test_return_addresses_browsers_would_rewrite_to_another_host_are_refused():
    """A browser treats "\\" as "/" and drops tabs and newlines in a Location header, so each of
    these would become "//evil.example" and leave the site (security review of #62)."""
    from fridgesheet.web.app import safe_return
    for bad in ("/\\evil.example", "/\\/evil.example", "\\\\evil.example", "/\t/evil.example", "/\n/evil.example",
                "/ /evil.example", "/%09/evil.example"):
        assert safe_return(bad) is None, repr(bad)
    for good in ("/kids/Alex", "/kids/Alex?show=all&course=5", "/questions#q-4", "/kids/Al%20ex"):
        assert safe_return(good) == good, good

"""Kid mode (spec 2026-09-27 §13): a browser remembers who is looking."""
from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

from fridgesheet.web import app as webapp
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed, snapshot


def _bare(tmp_path) -> TestClient:
    """A client with no cookie at all: what a browser that has never chosen sends."""
    c = app_for(tmp_path)
    c.cookies.clear()
    return c


def test_the_root_with_no_cookie_is_the_chooser(tmp_path):
    seed(tmp_path).close()
    c = _bare(tmp_path)
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/who"
    body = c.get("/who").text
    assert "Who's looking?" in body
    assert body.index("Alex") < body.index("Sam") < body.index("A grown-up")
    assert 'name="who" value="Alex"' in body and 'name="who" value="family"' in body


def test_choosing_a_kid_sets_the_cookie_and_the_root_goes_to_their_plan(tmp_path):
    seed(tmp_path).close()
    c = _bare(tmp_path)
    r = c.post("/who", data={"who": "Alex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith("fridgesheet_who=alex") and "path=/" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age=31536000" in cookie and "secure" not in cookie
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/plan"


def test_choosing_a_grown_up_shows_today(tmp_path):
    seed(tmp_path).close()
    c = _bare(tmp_path)
    c.post("/who", data={"who": "family"}, follow_redirects=False)
    r = c.get("/")
    assert r.status_code == 200 and "What needs our attention?" in r.text


def test_an_unknown_choice_is_a_404(tmp_path):
    seed(tmp_path).close()
    assert _bare(tmp_path).post("/who", data={"who": "Nobody"}).status_code == 404


def test_a_cookie_naming_a_kid_who_is_gone_clears_and_shows_the_chooser(tmp_path):
    """Review Focus 1."""
    seed(tmp_path).close()
    c = _bare(tmp_path)
    c.cookies.set("fridgesheet_who", "Gone")
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/who"
    assert 'fridgesheet_who=""' in r.headers.get("set-cookie", "") or "Max-Age=0" in r.headers.get("set-cookie", "")


def test_a_kid_key_that_needs_encoding_round_trips(tmp_path):
    """Review Focus 5."""
    snap = snapshot()
    snap["students"]["Mary Ann"] = {"name": "Mary Ann Example", "canvas_id": 3, "hac_name": "Mary Ann Example",
                                    "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    seed(tmp_path, snap).close()
    c = _bare(tmp_path)
    assert 'value="Mary Ann"' in c.get("/who").text
    c.post("/who", data={"who": "Mary Ann"}, follow_redirects=False)
    r = c.get("/", follow_redirects=False)
    assert r.headers["location"] == "/kids/Mary%20Ann/plan"
    assert c.get(r.headers["location"]).status_code == 200


def test_every_existing_page_test_client_is_a_grown_up(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert c.cookies.get("fridgesheet_who") == "family"
    assert c.get("/").status_code == 200


def test_the_chooser_renders_with_an_empty_database(tmp_path):
    """Global constraint: every page renders with an empty database -- no seed, so no kids."""
    c = app_for(tmp_path)
    c.cookies.clear()
    r = c.get("/who")
    assert r.status_code == 200 and "A grown-up" in r.text
    assert re.search(r'<button name="who" value="(?!family")', r.text) is None


def _kid(tmp_path, key="Alex"):
    c = app_for(tmp_path)
    c.cookies.set("fridgesheet_who", key)
    return c


def _rail(body: str) -> str:
    return re.search(r'<aside class="rail">(.*?)</aside>', body, re.S).group(1)


def test_a_kids_rail_names_only_their_pages(tmp_path):
    seed(tmp_path).close()
    rail = _rail(_kid(tmp_path).get("/kids/Alex/plan").text)
    links = re.findall(r'<a href="([^"]+)"', rail)
    assert links == ["/", "/kids/Alex/plan", "/kids/Alex/plan", "/kids/Alex/check-in", "/kids/Alex", "/trends?kid=Alex", "/changes?kid=Alex", "/who"]
    assert "Sam" not in rail and "Settings" not in rail and "Today" not in rail and "Questions" not in rail
    assert "Not Alex?" in rail and 'id="qcount-Alex"' in rail and 'id="qcount-all"' not in rail


def test_the_grown_up_rail_is_unchanged_but_for_the_switch_link(tmp_path):
    seed(tmp_path).close()
    rail = html.unescape(_rail(app_for(tmp_path).get("/").text))       # "kid's" -> kid&#39;s (see test_web_tier_wording.py)
    for word in ("Today", "Alex", "Sam", "Open work", "Questions", "Settings", "Switch to a kid's view"):
        assert word in rail, word
    assert 'href="/who"' in rail


def test_kid_mode_trims_the_status_bar_and_the_child_nav(tmp_path):
    seed(tmp_path).close()
    body = _kid(tmp_path).get("/kids/Alex/plan").text
    header = re.search(r'<header class="status">(.*?)</header>', body, re.S).group(1)
    assert "Refreshed" in header and "Canvas OK" in header
    assert "Last run" not in header and "/settings" not in header
    assert 'class="child-nav"' not in body
    assert "What you agreed to do, day by day." in body                   # the tab hint stays


def test_an_answer_swap_on_a_kid_mode_page_does_not_error(tmp_path):
    """Review Focus 2: `_after_answer.html` targets ids the kid rail does not draw."""
    from uuid import uuid4
    conn = seed(tmp_path)
    vid = conn.execute("SELECT id FROM items WHERE name = 'Vocabulary'").fetchone()["id"]
    conn.close()
    c = _kid(tmp_path)
    r = c.post(f"/items/{vid}/answer", data={"answer": "plan:today", "prev": "", "request_key": str(uuid4()), "slot": f"qc-{vid}"})
    assert r.status_code == 200 and 'id="plan"' in r.text


def test_a_sibling_page_by_address_still_renders_with_the_readers_rail(tmp_path):
    """Review Focus 3."""
    seed(tmp_path).close()
    body = _kid(tmp_path, "Alex").get("/kids/Sam/plan").text
    assert "Not Alex?" in _rail(body) and "Sam" in body


def test_kid_rail_links_are_url_encoded(tmp_path):
    """Review Focus 5."""
    snap = snapshot()
    snap["students"]["Mary Ann"] = {"name": "Mary Ann Example", "canvas_id": 3, "hac_name": "Mary Ann Example",
                                    "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    seed(tmp_path, snap).close()
    rail = _rail(_kid(tmp_path, "Mary Ann").get("/kids/Mary%20Ann/plan").text)
    assert 'href="/kids/Mary%20Ann/check-in"' in rail and 'href="/trends?kid=Mary%20Ann"' in rail


def test_trends_and_changes_scope_to_the_reader_without_a_parameter(tmp_path):
    from tests.web_fixtures import history
    history(tmp_path).close()
    c = _kid(tmp_path, "Alex")
    trends = c.get("/trends").text
    assert "Kid:" not in trends and 'href="/trends?weeks=8"' not in trends            # no picker
    assert "Grade per class" in trends and "Sam — grade per class" not in trends       # one kid, one chart
    changes = c.get("/changes").text
    assert "Kid:" not in changes
    assert "Cell diagram" not in changes                                                # Sam's change stays off Alex's page
    grown = app_for(tmp_path).get("/trends").text
    assert "Kid:" in grown


def test_a_kid_parameter_still_wins_in_kid_mode(tmp_path):
    """Review Focus 4: the address is honoured; the picker stays hidden."""
    from tests.web_fixtures import history
    history(tmp_path).close()
    body = _kid(tmp_path, "Alex").get("/trends?kid=Sam").text
    assert "Kid:" not in body and "Grade per class" in body
    assert "Honors English" not in body                                                # Alex's class is not drawn


def test_trends_carries_the_readers_tier_in_kid_mode(tmp_path):
    from tests.web_fixtures import client_with_grades
    seed(tmp_path).close()
    c = client_with_grades(tmp_path, Alex=5)
    c.cookies.set("fridgesheet_who", "Alex")
    assert 'data-tier="early"' in c.get("/trends").text

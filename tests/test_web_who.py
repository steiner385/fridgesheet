"""Kid mode (spec 2026-09-27 §13): a browser remembers who is looking."""
from __future__ import annotations

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

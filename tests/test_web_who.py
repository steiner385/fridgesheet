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


def test_a_cookie_naming_a_kid_who_is_hidden_clears_and_shows_the_chooser(tmp_path):
    """Final review, finding 7: `hidden` is the other way a name in the cookie stops naming a
    kid the app will show -- not just deleted outright (see the "gone" test above)."""
    conn = seed(tmp_path)
    conn.execute("UPDATE students SET hidden = 1 WHERE key = 'Alex'")
    conn.commit()
    conn.close()
    c = _bare(tmp_path)
    c.cookies.set("fridgesheet_who", "Alex")
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
    # No name link: the name is the page's own heading; the question count rides on Plan. Plan and
    # Assignments first, the rest behind More (maintainer, 2026-09-30), nothing removed.
    assert links == ["/", "/kids/Alex/plan", "/kids/Alex", "/kids/Alex/check-in", "/trends?kid=Alex", "/changes?kid=Alex", "/who"]
    assert re.search(r'<details class="rail-more"[^>]*>\s*<summary>More</summary>', rail)
    assert rail.index('<summary>More</summary>') < rail.index('/kids/Alex/check-in') < rail.index('/changes?kid=Alex') < rail.index('</details>')
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
    assert re.search(r'<p class="tab-hint">[^<]*Start with what', body)   # the state line stays without the tabs


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
    assert 'class="current"' not in _rail(body)                                        # final review 4


def test_the_kids_own_plan_page_highlights_only_the_plan_link(tmp_path):
    """Final review, finding 4: the name link and the tabs used to highlight together on every
    kid page, and a sibling's tab highlighted by address (the test above). Alex's own tab is
    the one link that should carry `current`."""
    seed(tmp_path).close()
    rail = _rail(_kid(tmp_path, "Alex").get("/kids/Alex/plan").text)
    assert rail.count('class="current"') == 1
    assert re.search(r'<a href="/kids/Alex/plan" class="current">Plan <span id="qcount-Alex"', rail)


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
    assert ">Kid</span>" not in trends and 'href="/trends?weeks=8"' not in trends      # no picker (the Kid words, 2026-10-01)
    assert "Grade per class" in trends and "Sam — grade per class" not in trends       # one kid, one chart
    changes = c.get("/changes").text
    assert ">Kid</span>" not in changes
    assert "Cell diagram" not in changes                                                # Sam's change stays off Alex's page
    grown = app_for(tmp_path).get("/trends").text
    assert ">Kid</span>" in grown
    assert ">Kid</span>" in app_for(tmp_path).get("/changes").text                      # final review 8


def test_a_kid_key_that_needs_encoding_is_encoded_in_trends_and_changes_links(tmp_path):
    """Final review, finding 5: kid mode puts `kid` into the Window/Kind chips, the pager and
    the Weeks chips by default -- an unencoded key with a space (or `&`) breaks the query."""
    snap = snapshot()
    snap["students"]["Mary Ann"] = {"name": "Mary Ann Example", "canvas_id": 3, "hac_name": "Mary Ann Example",
                                    "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    seed(tmp_path, snap).close()
    c = _kid(tmp_path, "Mary Ann")
    for path in ("/changes", "/trends"):
        body = c.get(path).text
        assert "kid=Mary%20Ann" in body
        assert "kid=Mary Ann" not in body


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

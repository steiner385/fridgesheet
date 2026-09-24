"""The tier reaches the page, on the element that owns one child's content.

`base.html` carries it for the pages about a single child. The Open work page shows every
child at once, so each kid section carries its own -- which is why the CSS keys on a bare
`[data-tier=...]` and not on `:root`.
"""
from __future__ import annotations

import re

from tests.web_fixtures import client_with_grades, seed


def test_a_kid_page_carries_that_kids_tier(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex").text
    assert re.search(r'<body[^>]*data-tier="early"', body)


def test_a_child_with_no_grade_set_gets_no_tier_attribute(tmp_path):
    """The shipped interface, byte for byte: no attribute at all, not data-tier=""."""
    seed(tmp_path).close()
    body = client_with_grades(tmp_path).get("/kids/Alex").text
    assert re.search(r"<body[^>]*>", body) and "data-tier" not in body


def test_two_children_on_one_page_each_carry_their_own_tier(tmp_path):
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=9, Sam=5).get("/open").text
    assert re.search(r'<section class="kid"[^>]*id="Alex"[^>]*data-tier="older"', body) \
        or re.search(r'<section class="kid"[^>]*data-tier="older"[^>]*id="Alex"', body)
    assert 'data-tier="early"' in body and 'data-tier="older"' in body


def test_the_check_in_page_carries_the_tier(tmp_path):
    seed(tmp_path).close()
    assert 'data-tier=\"middle\"' in client_with_grades(tmp_path, Alex=7).get("/kids/Alex/check-in").text


def test_the_printable_plan_carries_the_tier(tmp_path):
    """plan_print.html does not extend base.html -- it has a body of its own."""
    seed(tmp_path).close()
    body = client_with_grades(tmp_path, Alex=5).get("/kids/Alex/plan/print").text
    assert re.search(r'<body[^>]*data-tier="early"', body)


def test_a_parent_tool_never_carries_a_tier(tmp_path):
    """Settings, Runs and the rest are read by an adult; tiering them would mean three
    presentations of pages no child opens."""
    seed(tmp_path).close()
    c = client_with_grades(tmp_path, Alex=5)
    for path in ("/settings", "/runs", "/reports"):
        assert "data-tier" not in c.get(path).text, path


# --- kids' UX audit F5: one navigation on a child's page ------------------------------------------

def _rail(body):
    return re.search(r'<aside class="rail">(.*?)</aside>', body, re.S).group(1)


def test_a_tiered_page_folds_the_parent_tools_behind_app(tmp_path):
    """Thirteen links, two of them a sibling's pages and three of them Settings, Runs and
    Diagnostics, sat one tap from the child, above the child's own three tabs. On a page that
    carries a tier the rail is Today, this child, and one "App" fold holding the rest. Nothing
    is removed: the sibling's question count keeps its id, which an answer swaps out of band."""
    seed(tmp_path).close()
    rail = _rail(client_with_grades(tmp_path, Alex=9, Sam=5).get("/kids/Alex").text)
    fold = rail.index('<details class="rail-more"')
    front = rail[:fold]
    assert 'href="/"' in front and 'href="/kids/Alex/check-in"' in front
    for parent_only in ('href="/kids/Sam/check-in"', 'href="/settings"', 'href="/diagnostics"', 'href="/open"'):
        assert parent_only not in front and parent_only in rail[fold:], parent_only
    assert re.search(r'<details class="rail-more"[^>]*>\s*<summary>App', rail)
    assert 'id="qcount-Sam"' in rail
    assert ">Kids<" not in rail


def test_a_page_with_no_grade_keeps_the_full_rail(tmp_path):
    seed(tmp_path).close()
    rail = _rail(client_with_grades(tmp_path).get("/kids/Alex").text)
    assert "rail-more" not in rail and 'href="/settings"' in rail


def test_a_parent_tool_keeps_the_full_rail_even_when_grades_are_set(tmp_path):
    seed(tmp_path).close()
    assert "rail-more" not in _rail(client_with_grades(tmp_path, Alex=9).get("/settings").text)

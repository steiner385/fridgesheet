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

"""The Kid table's own affordances (#11 item 9): the flag, the sort headers, the Sources cell.

The audit found three things wrong with the same table. The Flag column was empty on every
row -- a whole column spent on a fact that is usually absent, in a seven-column table that
already falls off a phone. The sort links said nothing about which column was sorting or
which way. And "canvas + hac" wrapped, so row heights were uneven down the page.
"""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet import late_rules
from fridgesheet.web.stores import flags, items, students
from tests.web_fixtures import NOW, app_for, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
ROWS = (WEB / "templates" / "_item_rows.html").read_text(encoding="utf-8")
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _header(body: str) -> str:
    m = re.search(r"<thead>(.*?)</thead>", body, re.S)
    assert m, "the item table has no header"
    return m.group(1)


def _row(body: str, item_id: int) -> str:
    m = re.search(rf'<tr[^>]*id="row-{item_id}">(.*?)</tr>', body, re.S)
    assert m, f"no row for item {item_id}"
    return m.group(1)


def _item_id(conn, name: str) -> int:
    """The row id, which is not the Canvas assignment id the fixture names items by."""
    r = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()
    assert r, f"no item named {name!r}"
    return r["id"]


def _course_id(conn, short_name: str) -> int:
    r = conn.execute("SELECT id FROM courses WHERE short_name = ? AND source = 'canvas'", (short_name,)).fetchone()
    assert r, f"no course {short_name!r}"
    return r["id"]


# --- the Flag column ----------------------------------------------------------------------

def test_the_table_has_no_flag_column(tmp_path):
    """Three columns (Due, Assignment, Where it stands). A Flag column was blank on every row
    of a real household."""
    seed(tmp_path).close()
    header = _header(app_for(tmp_path).get("/kids/Alex").text)
    assert ">Flag<" not in header
    assert header.count("<th") == 3


def test_a_flag_shows_as_a_badge_beside_the_item_it_is_on(tmp_path):
    """Dropping the column must not drop the fact. It moves in beside the notes and
    case-kind badges, which is where the row's other parent-supplied facts already are."""
    conn = seed(tmp_path)
    item = _item_id(conn, "Homework 4")
    flags.set_flag(conn, item, "ignore", now=NOW.isoformat(), text="past the late-work window")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert re.search(r'class="badge flag"[^>]*>ignore \d+/\d+<', _row(body, item))   # with the day it was set


def test_an_unflagged_row_spends_no_space_on_the_flag(tmp_path):
    conn = seed(tmp_path)
    item = _item_id(conn, "Quiz 1")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "badge flag" not in _row(body, item)


def test_the_detail_row_spans_every_column(tmp_path):
    """`colspan` must match the three-column table; a stale one leaves a ragged edge."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex").text
    assert 'colspan="3"' in body and 'colspan="6"' not in body and 'colspan="7"' not in body


# --- sort indicators and direction ---------------------------------------------------------

def test_the_sorting_column_is_marked_and_the_others_are_not(tmp_path):
    seed(tmp_path).close()
    header = _header(app_for(tmp_path).get("/kids/Alex?sort=name").text)
    assert 'aria-sort="ascending"' in header
    assert header.count("aria-sort") == 1, "exactly one column sorts at a time"
    name = re.search(r"<th[^>]*>(?:(?!</th>).)*?sort=name.*?</th>", header, re.S).group(0)
    assert 'aria-sort="ascending"' in name
    assert "▲" in name


def test_clicking_the_sorting_column_again_turns_it_around(tmp_path):
    """The one thing a parent expects of a sort header, and the only way to ask for the
    oldest work first. Every other column's link asks for ascending."""
    seed(tmp_path).close()
    header = _header(app_for(tmp_path).get("/kids/Alex?sort=due").text)
    due = re.search(r"<th[^>]*>(?:(?!</th>).)*?sort=due.*?</th>", header, re.S).group(0)
    assert "dir=desc" in due, "the active column offers the other direction"
    name = re.search(r"<th[^>]*>(?:(?!</th>).)*?sort=name.*?</th>", header, re.S).group(0)
    assert "dir=desc" not in name


def test_a_descending_header_says_so(tmp_path):
    seed(tmp_path).close()
    header = _header(app_for(tmp_path).get("/kids/Alex?sort=due&dir=desc").text)
    assert 'aria-sort="descending"' in header and "▼" in header
    due = re.search(r"<th[^>]*>(?:(?!</th>).)*?sort=due.*?</th>", header, re.S).group(0)
    assert "dir=desc" not in due, "it is already descending; the link goes back to ascending"


def test_descending_really_reverses_the_rows(tmp_path):
    """The header is a claim about the table; this is the table."""
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    up = [v.id for v in items.list_items(conn, s, now=NOW, rules=RULES, show="all", sort="due")]
    down = [v.id for v in items.list_items(conn, s, now=NOW, rules=RULES, show="all", sort="due", direction="desc")]
    conn.close()
    assert down == list(reversed(up))


def test_an_unknown_direction_sorts_ascending(tmp_path):
    """Query strings are typed by hand and pasted from elsewhere; `dir=sideways` is a page,
    not a 500."""
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/kids/Alex?sort=due&dir=sideways")
    assert r.status_code == 200
    assert 'aria-sort="ascending"' in _header(r.text)


def test_the_sort_and_its_direction_survive_a_filter_change(tmp_path):
    """The filter form posts the sort back as a hidden field; the direction has to travel
    with it, or narrowing to one course silently flips the table back over."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?sort=name&dir=desc").text
    form = re.search(r'<form class="filters".*?</form>', body, re.S).group(0)
    assert 'name="sort" value="name"' in form
    assert 'name="dir" value="desc"' in form


def test_the_course_page_sorts_the_same_way(tmp_path):
    """The course page merges a Canvas course with its HAC twin and sorts the whole; it
    reads the same header partial, so it needs the same direction or its links 404 the idea."""
    conn = seed(tmp_path)
    cid = _course_id(conn, "Honors English 9")
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}?sort=name&dir=desc").text
    assert 'aria-sort="descending"' in _header(body)


# --- the Sources cell ----------------------------------------------------------------------

def test_the_table_has_no_sources_column(tmp_path):
    """Which gradebooks list an item is evidence, not a column: it lives in the item's record
    (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md, 6.1)."""
    assert not re.search(r'class="[^"]*\bsources\b[^"]*"', ROWS)
    seed(tmp_path).close()
    assert ">Sources<" not in _header(app_for(tmp_path).get("/kids/Alex").text)

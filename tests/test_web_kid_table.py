"""The kid page's own affordances (#11 item 9), on the weekly pages: the flag as a badge on
its line, the sort line that says which key sorts and which way, and no Sources column.

The audit found three things wrong with the old table. The Flag column was empty on every
row -- a whole column spent on a fact that is usually absent, in a seven-column table that
already fell off a phone. The sort links said nothing about which column was sorting or
which way. And "canvas + hac" wrapped, so row heights were uneven down the page. The table
became the weekly pages (the Student Planner, 2026-09-30); the class page keeps the table.
"""
from __future__ import annotations

import re
from pathlib import Path

from fridgesheet import late_rules
from fridgesheet.web.stores import flags, items, students
from tests.web_fixtures import NOW, app_for, items_block, seed, week_line

RULES = late_rules.LateRules(late_rules.Rule(), [], [])

WEB = Path(__file__).resolve().parents[1] / "fridgesheet" / "web"
WEEKS = (WEB / "templates" / "_weeks.html").read_text(encoding="utf-8") + (WEB / "templates" / "_week_line.html").read_text(encoding="utf-8")
CSS = (WEB / "static" / "app.css").read_text(encoding="utf-8")


def _sort_line(body: str) -> str:
    m = re.search(r'<p class="sort"[^>]*>(.*?)</p>', body, re.S)
    assert m, "the kid page has no sort line"
    return m.group(1)


def _link(line: str, key: str) -> str:
    m = re.search(rf'<a id="sort-{key}"[^>]*>.*?</a>', line, re.S)
    assert m, f"no sort link for {key}"
    return m.group(0)


def _item_id(conn, name: str) -> int:
    """The row id, which is not the Canvas assignment id the fixture names items by."""
    r = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()
    assert r, f"no item named {name!r}"
    return r["id"]


def _course_id(conn, short_name: str) -> int:
    r = conn.execute("SELECT id FROM courses WHERE short_name = ? AND source = 'canvas'", (short_name,)).fetchone()
    assert r, f"no course {short_name!r}"
    return r["id"]


# --- the flag ----------------------------------------------------------------------------

def test_the_page_has_no_flag_column(tmp_path):
    """No table at all on the kid page: the flag is a badge on its own line."""
    seed(tmp_path).close()
    assert ">Flag<" not in items_block(app_for(tmp_path).get("/kids/Alex").text)


def test_a_flag_shows_as_a_badge_beside_the_item_it_is_on(tmp_path):
    """Dropping the column must not drop the fact. It moves in beside the line's class and
    due date, which is where the line's other facts already are."""
    conn = seed(tmp_path)
    item = _item_id(conn, "Homework 4")
    flags.set_flag(conn, item, "ignore", now=NOW.isoformat(), text="past the late-work window")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert re.search(r'class="badge flag"[^>]*>let go \d+/\d+<', week_line(body, item))   # with the day it was set; family words, never "ignore" (#129)


def test_an_unflagged_row_spends_no_space_on_the_flag(tmp_path):
    conn = seed(tmp_path)
    item = _item_id(conn, "Quiz 1")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex?show=all").text
    assert "badge flag" not in week_line(body, item)


def test_a_lines_name_opens_its_record_in_place(tmp_path):
    """The name fetches the item's record into the line's own place; Close puts the line
    back (#126, `routes/kid.py: card_for`)."""
    conn = seed(tmp_path)
    item = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    line = week_line(c.get("/kids/Alex?show=all").text, item)
    assert f'<a href="#row-{item}" hx-get="/items/{item}?card=row-{item}" hx-target="#row-{item}" hx-swap="outerHTML"' in line
    detail = c.get(f"/items/{item}?card=row-{item}").text
    assert f'id="row-{item}"' in detail
    assert f'hx-get="/items/{item}/question?slot=row-{item}" hx-target="#row-{item}"' in detail     # Close
    back = c.get(f"/items/{item}/question?slot=row-{item}").text
    assert f'id="row-{item}"' in back and 'class="when word' not in back or "Quiz 1" in back


# --- sort indicators and direction ---------------------------------------------------------

def test_the_sorting_key_is_marked_and_the_others_are_not(tmp_path):
    seed(tmp_path).close()
    line = _sort_line(app_for(tmp_path).get("/kids/Alex?sort=name").text)
    assert line.count('aria-current="true"') == 1, "exactly one key sorts at a time"
    name = _link(line, "name")
    assert 'aria-current="true"' in name and '<svg class="arrow up"' in name        # drawn, not a glyph


def test_clicking_the_sorting_key_again_turns_it_around(tmp_path):
    """The one thing a parent expects of a sort control, and the only way to ask for the
    oldest work first. Every other key's link asks for ascending."""
    seed(tmp_path).close()
    line = _sort_line(app_for(tmp_path).get("/kids/Alex?sort=due").text)
    assert "dir=desc" in _link(line, "due"), "the active key offers the other direction"
    assert "dir=desc" not in _link(line, "name")


def test_a_descending_key_says_so(tmp_path):
    seed(tmp_path).close()
    line = _sort_line(app_for(tmp_path).get("/kids/Alex?sort=due&dir=desc").text)
    due = _link(line, "due")
    assert 'aria-current="true"' in due and '<svg class="arrow down"' in due
    assert "dir=desc" not in due, "it is already descending; the link goes back to ascending"


def test_descending_really_reverses_the_rows(tmp_path):
    """The sort line is a claim about the list; this is the list."""
    conn = seed(tmp_path)
    s = students.by_key(conn, "Alex")
    up = [v.id for v in items.list_items(conn, s, now=NOW, rules=RULES, show="all", sort="due")]
    down = [v.id for v in items.list_items(conn, s, now=NOW, rules=RULES, show="all", sort="due", direction="desc")]
    conn.close()
    assert down == list(reversed(up))


def test_the_weeks_keep_their_order_and_the_lines_follow_the_sort(tmp_path):
    """The planner turns back a page at a time whatever the sort: the newest week first. Inside
    a week the lines follow the chosen key and direction."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for q in ("?show=all&sort=due", "?show=all&sort=due&dir=desc", "?show=all&sort=name"):
        weeks = re.findall(r'data-week="([0-9-]+)"', items_block(c.get(f"/kids/Alex{q}").text))
        assert weeks == sorted(weeks, reverse=True), q
    up = items_block(c.get("/kids/Alex?show=all&sort=due").text)
    down = items_block(c.get("/kids/Alex?show=all&sort=due&dir=desc").text)
    week = lambda body: re.findall(r'<a href="#row-\d+"[^>]*>([^<]+)</a>', body[body.index('data-week="2026-09-14"'):body.index("</section>", body.index('data-week="2026-09-14"'))])
    assert week(up) == list(reversed(week(down))) and len(week(up)) > 1


def test_an_unknown_direction_sorts_ascending(tmp_path):
    """Query strings are typed by hand and pasted from elsewhere; `dir=sideways` is a page,
    not a 500."""
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/kids/Alex?sort=due&dir=sideways")
    assert r.status_code == 200
    assert '<svg class="arrow up"' in _link(_sort_line(r.text), "due")


def test_the_sort_and_its_direction_survive_a_filter_change(tmp_path):
    """The filter form posts the sort back as a hidden field; the direction has to travel
    with it, or narrowing to one course silently flips the list back over."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex?sort=name&dir=desc").text
    form = re.search(r'<form class="filters controls".*?</form>', body, re.S).group(0)
    assert 'name="sort" value="name"' in form
    assert 'name="dir" value="desc"' in form


def test_the_course_page_sorts_the_same_way(tmp_path):
    """The course page merges a Canvas course with its HAC twin and sorts the whole on the same
    weekly pages as Assignments (the class's record, 2026-09-30), so its sort line marks the
    same key and direction."""
    conn = seed(tmp_path)
    cid = _course_id(conn, "Honors English 9")
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}?sort=name&dir=desc").text
    line = _sort_line(body)
    assert re.search(r'id="sort-name" href="[^"]*sort=name"[^>]*aria-current="true"', line) and 'class="arrow down"' in line


# --- the Sources cell ----------------------------------------------------------------------

def test_the_page_has_no_sources_column(tmp_path):
    """Which gradebooks list an item is evidence, not a column: it lives in the item's record
    (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md, 6.1)."""
    assert not re.search(r'class="[^"]*\bsources\b[^"]*"', WEEKS)
    seed(tmp_path).close()
    assert ">Sources<" not in items_block(app_for(tmp_path).get("/kids/Alex").text)

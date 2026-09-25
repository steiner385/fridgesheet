"""The Open work page: still fixable and coming due, per kid, and the store behind it."""
from __future__ import annotations

import re
from datetime import datetime

from fridgesheet import config, late_rules
from fridgesheet.web.stores import flags, items, students
from tests.web_fixtures import NOW, app_for, seed

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _names(views):
    return [v.name for v in views]


def test_open_work_splits_a_kid_into_still_fixable_and_coming_due(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    w = items.open_work(conn, alex, now=NOW, rules=RULES, days_ahead=14)
    # Still fixable, soonest-closing window first: the 14-day default puts Participation
    # (due 9/08) first. Homework 4 (due 8/20) closed on 9/03. Quiz 1 is settled: HAC's 28/30
    # beats Canvas's automatic missing (docs/outcomes.md).
    assert _names(w.fixable) == ["Participation", "Lab notebook"]
    assert [v.late_until.date().isoformat() for v in w.fixable] == ["2026-09-22", "2026-09-24"]
    assert all(v.credit == "" for v in w.fixable)          # the built-in default carries no credit text
    assert _names(w.past_window) == ["Homework 4"]
    assert _names(w.upcoming) == ["Vocabulary", "Worksheet 3", "Reading log"]
    assert w.handled == []
    conn.close()


def test_open_work_coming_due_stops_at_days_ahead(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    w = items.open_work(conn, alex, now=NOW, rules=RULES, days_ahead=3)
    assert _names(w.upcoming) == ["Vocabulary", "Worksheet 3"]       # Reading log (9/20) is 5 days out
    conn.close()


def test_open_work_moves_a_handled_item_out_of_both_lists(tmp_path):
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    qid = conn.execute("SELECT id FROM items WHERE name = 'Lab notebook'").fetchone()["id"]
    wid = conn.execute("SELECT id FROM items WHERE name = 'Worksheet 3'").fetchone()["id"]
    flags.set_flag(conn, qid, "done", now="2026-09-15T13:00:00-04:00")
    flags.set_flag(conn, wid, "ignore", now="2026-09-15T13:00:00-04:00")
    w = items.open_work(conn, alex, now=NOW, rules=RULES, days_ahead=14)
    assert "Lab notebook" not in _names(w.fixable) and "Worksheet 3" not in _names(w.upcoming)
    assert _names(w.handled) == ["Lab notebook", "Worksheet 3"]
    conn.close()


def test_open_page_shows_each_kid_in_two_sections(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/open")
    assert r.status_code == 200
    body = r.text
    assert 'href="/open"' in body and "Open work" in body            # in the rail, under Work
    alex, sam = body.index('id="Alex"'), body.index('id="Sam"')
    assert alex < sam
    assert body.count("Still fixable") == 2 and body.count("Coming due") == 2
    # Alex's still-fixable rows, soonest-closing window first, each saying when it closes.
    assert alex < body.index("Participation") < body.index("Lab notebook") < sam
    assert "Quiz 1" not in body[alex:sam]                              # settled by HAC's grade
    assert "thru Tue 9/22" in body and "thru Thu 9/24" in body
    # Coming due, by due date, inside Alex's section.
    assert alex < body.index("Vocabulary") < body.index("Worksheet 3") < body.index("Reading log") < sam
    assert "Essay draft" not in body                                  # submitted: nothing to do
    # The trailer counts what the tables leave out, the way the sheet does, and links to it.
    assert "Not shown:" in body
    assert 'href="/kids/Alex?show=past_window">1 past the late-work window or more than 14 days overdue (10 pts)</a>' in body
    # Sam has nothing coming due, and says so rather than showing an empty table.
    assert body.index("Cell diagram") > sam and body.index("Safety quiz") > sam
    assert "Nothing coming due" in body


def test_open_page_says_nice_work_when_a_kid_has_nothing_open(tmp_path):
    conn = seed(tmp_path)
    for name in ("Cell diagram", "Safety quiz"):
        iid = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
        flags.set_flag(conn, iid, "done", now="2026-09-15T13:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/open").text
    sam = body.index('id="Sam"')
    assert body.index("Nothing open. Nice work.") > sam
    assert "2 handled" in body and 'href="/kids/Sam?show=handled"' in body


def test_days_ahead_setting_governs_the_web_window(tmp_path):
    seed(tmp_path).close()
    config.save_config_doc(tmp_path / "config.toml", {"reports": {"open-work": {"days_ahead": 3}}})
    c = app_for(tmp_path)
    c.app.state.fridgesheet.reload()
    assert "Reading log" not in c.get("/open").text                   # 5 days out; the window is 3
    assert "Worksheet 3" in c.get("/open").text
    assert "Reading log" not in c.get("/kids/Alex").text              # the Kid page's "open" agrees
    assert "Reading log" in c.get("/kids/Alex?show=all").text


def test_dashboard_due_counts_link_to_the_kids_section_of_the_open_page(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/").text
    assert 'href="/open#Alex"' in body and "1 due today" in body


def test_the_credit_text_reaches_the_page_and_the_column(tmp_path):
    """`credit` is the parent's own words next to a late-work rule -- "50% after Friday" --
    and the Credit thru column exists to show them.

    The default `Rule()` carries no credit text, so every other test here asserts `credit ==
    ""` and would pass just as well if `credit` were never threaded into `ItemView` at all.
    This one uses a rule that has some, so deleting that wiring fails a test instead of
    quietly emptying a column nobody notices until a parent looks for their own note.
    """
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    rules = late_rules.LateRules(late_rules.Rule(credit="50% after the window"), [], [])
    w = items.open_work(conn, alex, now=NOW, rules=rules, days_ahead=14)
    conn.close()
    assert w.fixable, "the fixture must have fixable work for this to mean anything"
    assert all(v.credit == "50% after the window" for v in w.fixable)


def _not_shown_links(body, key):
    """The "Not shown" trailer's links for one kid, as (href, count)."""
    section = body[body.index(f'id="{key}"'):]
    section = section[:section.index("</section>")]
    trailer = section[section.index("Not shown:"):]
    return [(href.replace("&amp;", "&"), int(n)) for href, n in re.findall(r'<a href="([^"]+)">(\d+) ', trailer)]


def test_the_not_shown_links_open_exactly_the_set_they_count(tmp_path):
    """#125: "1 past the late-work window" opened every not-done item, fixable ones included,
    and "N handled" opened every handled item ever."""
    when = datetime(2026, 9, 26, 14, 0, tzinfo=NOW.tzinfo)
    conn = seed(tmp_path)
    ids = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM items")}
    flags.set_flag(conn, ids["Participation"], "done", now="2026-09-20T08:00:00-04:00")   # open, handled
    flags.set_flag(conn, ids["Essay draft"], "done", now="2026-09-20T08:00:00-04:00")     # handed in: not open work
    conn.close()
    c = app_for(tmp_path, now=when)
    body = c.get("/open").text
    checked = 0
    for key in ("Alex", "Sam"):
        for href, n in _not_shown_links(body, key):
            rows = set(re.findall(r'id="row-(\d+)"', c.get(href).text))
            assert len(rows) == n, (key, href, rows)
            checked += 1
    assert checked >= 3, "the fixture must give both links something to count"


def test_the_past_window_and_handled_filters_match_open_works_lists(tmp_path):
    when = datetime(2026, 9, 26, 14, 0, tzinfo=NOW.tzinfo)
    conn = seed(tmp_path)
    sam = students.by_key(conn, "Sam")
    flags.set_flag(conn, conn.execute("SELECT id FROM items WHERE name = 'Cell diagram'").fetchone()["id"], "excused",
                   now="2026-09-20T08:00:00-04:00")
    w = items.open_work(conn, sam, now=when, rules=RULES, days_ahead=14)
    for show, expected in (("past_window", w.past_window), ("handled", w.handled)):
        got = items.list_items(conn, sam, now=when, rules=RULES, show=show, days_ahead=14)
        assert [v.id for v in got] == [v.id for v in expected], show
    conn.close()

"""The Open work page: still fixable and coming due, per kid, and the store behind it."""
from __future__ import annotations

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
    # (due 9/08) first and Quiz 1 (due 9/12) last. Homework 4 (due 8/20) closed on 9/03.
    assert _names(w.fixable) == ["Participation", "Lab notebook", "Quiz 1"]
    assert [v.late_until.date().isoformat() for v in w.fixable] == ["2026-09-22", "2026-09-24", "2026-09-26"]
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
    qid = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    wid = conn.execute("SELECT id FROM items WHERE name = 'Worksheet 3'").fetchone()["id"]
    flags.set_flag(conn, qid, "done", now="2026-09-15T13:00:00-04:00")
    flags.set_flag(conn, wid, "ignore", now="2026-09-15T13:00:00-04:00")
    w = items.open_work(conn, alex, now=NOW, rules=RULES, days_ahead=14)
    assert "Quiz 1" not in _names(w.fixable) and "Worksheet 3" not in _names(w.upcoming)
    assert _names(w.handled) == ["Quiz 1", "Worksheet 3"]
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
    assert alex < body.index("Participation") < body.index("Lab notebook") < body.index("Quiz 1") < sam
    assert "thru Tue 9/22" in body and "thru Thu 9/24" in body and "thru Sat 9/26" in body
    # Coming due, by due date, inside Alex's section.
    assert alex < body.index("Vocabulary") < body.index("Worksheet 3") < body.index("Reading log") < sam
    assert "Essay draft" not in body                                  # submitted: nothing to do
    # The trailer counts what the tables leave out, the way the sheet does, and links to it.
    assert "Not shown:" in body
    assert 'href="/reconcile?kid=Alex&amp;kind=past_credit">1 past the late-work window (10 pts)</a>' in body
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
    assert "2 handled" in body and 'href="/kids/Sam?show=all&amp;flagged=handled"' in body


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

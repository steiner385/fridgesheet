"""Levers from the database's open work, and the report card's second sentence (spec 2026-10-04 §5-§6)."""
from __future__ import annotations

from fridgesheet import grading, guidance, late_rules, sources
from fridgesheet.web import phrasing
from fridgesheet.web.stores import grades, guidance as gstore, items, students
from tests.web_fixtures import NOW, seed


def _work(conn, key):
    s = students.by_key(conn, key)
    rules = late_rules.LateRules(late_rules.Rule(), [], [])
    return s, items.open_work(conn, s, now=NOW, rules=rules, prefs=sources.DEFAULT)


def _english(conn):
    return conn.execute("SELECT * FROM courses WHERE short_name = 'Honors English 9' AND source = 'hac'").fetchone()


def test_rows_are_deduplicated_across_fixable_and_upcoming(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    hac = _english(conn)
    rows = gstore.rows_for(conn, work, {hac["id"], hac["peer_course_id"]})
    names = [r["name"] for r in rows]
    assert len(names) == len(set(names))
    assert set(names) == {"Participation", "Lab notebook", "Vocabulary", "Worksheet 3", "Reading log"}


def test_englishs_levers_and_reach_from_the_fixture(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    hac = _english(conn)
    account = grades.account_for(conn, hac, students.latest_grades(conn, s["id"]).get(hac["id"]))
    g = gstore.for_class(conn, hac, account, work, grading.TEN_POINT)
    assert g.sound and g.letter == "B"
    assert {l.name: l.kind for l in g.levers} == {"Participation": "missing", "Lab notebook": "missing", "Vocabulary": "upcoming",
                                                  "Worksheet 3": "upcoming", "Reading log": "upcoming"}
    assert all(round(l.worth, 1) == 2.0 for l in g.levers)                          # 100*(44+10)/(50+10) - 88
    assert g.best.name == "Vocabulary"                                              # equal worth: soonest deadline first
    assert g.reach.letter == "A" and g.reach.needed == 10.0 and g.reach.posted == 50.0 and g.reach.reachable


def test_the_report_cards_second_sentence_for_english_and_for_an_unsound_class(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    hac = _english(conn)
    latest = students.latest_grades(conn, s["id"])
    g = gstore.for_class(conn, hac, grades.account_for(conn, hac, latest.get(hac["id"])), work, grading.TEN_POINT)
    assert gstore.sentence_for(g) == [("gd.best", {"name": "Vocabulary", "points": "10", "worth": "2.0"}),
                                      ("gd.reach", {"letter": "an A", "needed": "10", "posted": "50"})]
    alg = conn.execute("SELECT * FROM courses WHERE short_name = 'Algebra I' AND source = 'hac'").fetchone()
    g2 = gstore.for_class(conn, alg, grades.account_for(conn, alg, latest.get(alg["id"])), work, grading.TEN_POINT)
    assert not g2.sound and gstore.sentence_for(g2) == []


def test_sentence_order_zeros_reach_then_best_then_reach_or_slack():
    L = guidance.Lever(1, "Scale test", "zero", 25.0, 1.0, True, 8.2, None, "Playing")
    zeros = guidance.Guidance(True, "B", (L,), L, guidance.Reach("A", 90.0, -3.0, 0.0, True), None, 25.0)
    assert gstore.sentence_for(zeros) == [("gd.zeros_reach", {"zero_points": "25", "letter": "an A"})]
    far = guidance.Guidance(True, "C", (), None, guidance.Reach("B", 80.0, 237.5, 80.0, False), None, 0.0)
    assert gstore.sentence_for(far) == [("gd.reach_far", {"letter": "a B", "needed": "237.5", "posted": "80"})]
    top = guidance.Guidance(True, "A", (), None, None, guidance.Slack("A", 90.0, 115.0, 70.0), 0.0)
    assert gstore.sentence_for(top) == [("gd.keep", {"letter": "an A", "can_miss": "70", "posted": "115"})]
    hold = guidance.Guidance(True, "B", (), None, guidance.Reach("A", 90.0, 60.0, 10.0, False), guidance.Slack("B", 80.0, 10.0, -2.0), 0.0)
    assert gstore.sentence_for(hold) == [("gd.reach_far", {"letter": "an A", "needed": "60", "posted": "10"}), ("gd.hold", {"letter": "a B", "need": "2", "posted": "10"})]
    nothing = guidance.Guidance(True, "A", (), None, None, guidance.Slack("A", 90.0, 0.0, 10.0), 0.0)
    assert gstore.sentence_for(nothing) == [("gd.nothing_posted", {})]


def test_by_item_maps_every_open_row_of_a_sound_class_to_its_lever(tmp_path):
    conn = seed(tmp_path)
    s, work = _work(conn, "Alex")
    by = gstore.by_item(conn, s, work, sources.DEFAULT, grading.TEN_POINT)
    vocab = conn.execute("SELECT id FROM items WHERE name = 'Vocabulary'").fetchone()["id"]
    assert round(by[vocab].worth, 1) == 2.0
    homework4 = conn.execute("SELECT id FROM items WHERE name = 'Homework 4'").fetchone()["id"]
    assert homework4 not in by                                                      # past the window: not open at all


def test_an_undated_lever_note_has_no_until():
    L = guidance.Lever(1, "Reading", "missing", 5.0, 1.0, False, 0.9, None, "")
    key, values = gstore.lever_note(L, "older")
    assert key == "gd.lever_missing_undated" and "until" not in values and values["credit_note"] == " · late credit unknown, ask"


def test_every_gd_phrase_has_three_tiers():
    keys = [k for k in phrasing.PHRASES if k.startswith("gd.") or k.startswith("copy.gd_") or k == "badge.worth"]
    assert len(keys) >= 15
    for key in keys:
        assert set(phrasing.PHRASES[key]) == {"early", "middle", "older"}, key

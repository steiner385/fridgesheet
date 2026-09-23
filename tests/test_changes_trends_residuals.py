"""#5 residuals: Trends says one thing when there is nothing yet, the window chips stay plain
links, and a kid with no live work costs no observation query."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import trends
from tests.web_fixtures import NOW, app_for, seed


def test_an_empty_trends_page_says_one_thing(tmp_path):
    """Before any refresh the page said "Not enough history yet", then "Nothing has come due
    yet", "Nothing is open" and "No grades recorded yet" under it: four ways of saying one thing."""
    db.open_db(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    assert "Not enough history yet" in body
    for also in ("Nothing has come due yet", "Nothing is open.", "No grades recorded yet", 'class="chart"'):
        assert also not in body, also


def test_trends_with_data_still_shows_its_cards(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/trends").text
    assert "Not enough history yet" not in body and "On-time hand-ins" in body and "Open the longest" in body


def test_the_window_chips_are_plain_links(tmp_path):
    """The chips sit outside #changes; an hx-get swapping only the table would leave every
    other chip on the old window. Pinned so nobody "improves" them back."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/changes").text
    chips = body[body.index('<div class="filters">'):body.index('<div id="changes">')]
    assert "hx-get" not in chips and 'href="/changes?window=7d"' in chips


def test_a_kid_with_no_live_work_costs_no_observation_query(tmp_path, monkeypatch):
    conn = seed(tmp_path)
    # Last year's work is not live (`reconcile.live_items`' school-year floor).
    conn.execute("UPDATE items SET due = '2025-01-10T23:59:00-05:00' WHERE student_id = (SELECT id FROM students WHERE key = 'Sam')")
    asked = []
    real = trends._db.latest_observations
    monkeypatch.setattr(trends._db, "latest_observations", lambda conn, sid: asked.append(sid) or real(conn, sid))
    trends.open_days(conn, now=NOW)
    alex = conn.execute("SELECT id FROM students WHERE key = 'Alex'").fetchone()["id"]
    conn.close()
    assert asked == [alex]

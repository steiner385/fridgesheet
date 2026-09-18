"""The Changes page: what happened while I wasn't looking."""
from __future__ import annotations

from datetime import timedelta

from lakota_grades.web import db
from lakota_grades.web.stores import changes
from tests.web_fixtures import NOW, app_for, history, seed


def test_empty_database_says_nothing_yet(tmp_path):
    c = app_for(tmp_path)
    r = c.get("/changes")
    assert r.status_code == 200 and "Nothing has changed" in r.text
    assert "Since yesterday" in r.text                     # the window buttons render anyway


def test_the_default_window_is_since_yesterday(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes").text
    assert "Quiz 1" in body and "Now missing" in body      # today's Canvas change
    assert "Vocabulary" not in body                        # yesterday's new item is outside 1 day
    body = app_for(tmp_path).get("/changes?window=nonsense").text
    assert 'class="badge current" href="/changes?window=1d"' in body  # unknown window falls back, chip still lights up


def test_a_longer_window_reaches_further_back(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=7d").text
    assert "Vocabulary" in body and "New" in body
    assert "Grade posted" in body and "28/30" in body
    assert "Class average" in body and "→" in body


def test_filters_by_kid_and_kind(tmp_path):
    history(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/changes?window=7d&kid=Sam").text
    assert "Safety quiz" in body and "Quiz 1" not in body
    body = c.get("/changes?window=7d&kind=new_item", headers={"HX-Request": "true"}).text
    assert "Vocabulary" in body and "Now missing" not in body
    r = c.get("/changes?window=7d&kind=nonsense")
    assert r.status_code == 200                                              # unknown kind: no crash
    # ...and it falls back to no kind filter, with the "all" chip lit, exactly as an unknown
    # window falls back to 1d. A dead query string must not render an empty, unexplained feed.
    assert 'class="badge current" href="/changes?window=7d">all</a>' in r.text
    assert "Vocabulary" in r.text and "Now missing" in r.text
    assert c.get("/changes?window=7d&kid=Nobody").status_code == 404


def test_htmx_gets_the_table_only(tmp_path):
    history(tmp_path).close()
    r = app_for(tmp_path).get("/changes?window=7d", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "Quiz 1" in r.text


def test_rows_link_to_the_kid_and_the_item(tmp_path):
    history(tmp_path).close()
    body = app_for(tmp_path).get("/changes?window=7d").text
    assert 'href="/kids/Alex"' in body
    assert 'hx-get="/items/' in body                       # the row expands the same detail the Kid page uses


def test_a_flag_shows_as_the_parents_own_change(tmp_path):
    conn = history(tmp_path)
    from lakota_grades.web.stores import flags
    quiz = conn.execute("SELECT id FROM items WHERE name = 'Quiz 1'").fetchone()["id"]
    flags.set_flag(conn, quiz, "ask_teacher", now="2026-09-15T15:00:00-04:00", text="emailed")
    conn.close()
    body = app_for(tmp_path).get("/changes").text
    assert "You flagged" in body and "ask teacher" in body and "emailed" in body


def test_one_refresh_only_shows_state_not_a_wall_of_new(tmp_path):
    """The state every install starts in. The first refresh has no "before", so nothing is
    genuinely new -- but what the observations already say is real, and Trends counts it."""
    seed(tmp_path).close()                                  # the single-refresh fixture
    body = app_for(tmp_path).get("/changes?window=7d", headers={"HX-Request": "true"}).text
    assert "Quiz 1" in body and "Grade posted" in body and "28/30" in body
    assert "Cell diagram" in body and "Now missing" in body
    assert ">New<" not in body                              # no first-refresh "New" rows
    assert "Nothing has changed" not in body


def test_a_feed_longer_than_the_cap_says_how_many_more(tmp_path, monkeypatch):
    """The real case is a household's first refresh: a thousand events at one timestamp. The
    cap is what keeps that a page; the caption is what keeps it honest."""
    history(tmp_path).close()
    c = app_for(tmp_path)
    full = changes.since(db.open_db(tmp_path), since=NOW - timedelta(days=7), limit=None)
    assert len(full) > 2
    monkeypatch.setattr(changes, "DEFAULT_LIMIT", 2)
    body = c.get("/changes?window=7d").text
    assert f"Showing 1–2 of {len(full)} changes" in body
    assert "page=2" in body and "Older ›" in body and "Newer" not in body
    assert body.count('hx-get="/items/') <= 2                # only this page's rows rendered
    page2 = c.get("/changes?window=7d&page=2").text
    assert f"Showing 3–{min(4, len(full))} of {len(full)} changes" in page2
    assert "page=1" in page2 and "‹ Newer" in page2
    assert c.get("/changes?window=7d&page=0").status_code == 200   # clamps, never 500s
    assert c.get("/changes?window=7d&page=999").status_code == 200


def test_an_empty_first_refresh_is_not_the_baseline(tmp_path):
    """The real install: refresh 1 ran before the credentials were entered and recorded no
    items; refresh 2 was the first real look. Everything it found used to be "New" -- 199
    rows -- because the baseline was the earliest refresh, not the earliest refresh with items."""
    from datetime import datetime
    from lakota_grades.web import db, ingest
    from web_fixtures import TZ, snapshot
    conn = db.open_db(tmp_path)
    empty = snapshot()
    empty["students"] = {}
    empty["sources"] = {"canvas": "error: No credentials available", "hac": "error: No credentials available"}
    ingest.record(conn, empty, tz=TZ, now=datetime(2026, 9, 15, 12, 0, tzinfo=TZ))
    ingest.record(conn, snapshot(), tz=TZ, now=NOW)
    feed = changes.since(conn, since=NOW - timedelta(days=1), limit=None)
    assert not [e for e in feed if e.kind == "new_item"], "the first real look is a baseline, not news"
    assert any(e.kind == "grade_posted" for e in feed)           # the state it carried still shows
    conn.close()

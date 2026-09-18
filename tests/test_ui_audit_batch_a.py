"""Batch A of the UI/UX audit (#40): the six one-liners.

Each of these was observed on the deployed app, not read from the source, so each test
pins the observable rather than the implementation where it can.
"""
from __future__ import annotations

import re
from pathlib import Path

from lakota_grades.web import actions
from lakota_grades.web.stores import num

WEB = Path(__file__).resolve().parents[1] / "lakota_grades" / "web"


# --- item 6: a raw float in the Status column ---------------------------------------------

def test_a_score_is_rounded_to_what_a_gradebook_shows():
    assert num(12.5033) == "12.5"          # the value seen live: "12.5033/50"
    assert num(88.5) == "88.5"
    assert num(9.0) == "9"
    assert num(100) == "100"
    assert num(33.335) in ("33.33", "33.34")   # banker's vs half-up is not the point; 3 places is
    assert num(None) == ""


def test_the_kid_page_and_the_changes_feed_format_a_score_the_same_way():
    from lakota_grades.web.stores import changes, items
    assert changes._num(12.5033) == "12.5"
    assert items._score({"score": 12.5033, "grade": None}, 50) == "12.5/50"
    assert items._score({"score": 7.0, "grade": None}, None) == "7"


# --- item 3: Settings scrolled sideways because a <pre> would not wrap --------------------

def test_every_pre_wraps():
    css = (WEB / "static" / "app.css").read_text(encoding="utf-8")
    rule = re.search(r"(?m)^pre\s*\{([^}]*)\}", css)
    assert rule, "a bare `pre` rule is expected"
    assert "white-space: pre-wrap" in rule.group(1)
    assert "overflow-wrap: anywhere" in rule.group(1)     # a bare URL or a Windows path has no space to break at


# --- item 14: the job pane promised 1-3 minutes and took 8-10 -----------------------------

def test_the_time_estimate_no_longer_promises_three_minutes():
    src = (WEB / "actions.py").read_text(encoding="utf-8")
    # The old strings were literal "(1-3 minutes)..." inside log() calls. A comment may still
    # *mention* the old promise; no line a parent reads may make it.
    assert "(1-3 minutes)" not in src
    assert "ten" in actions.RUN_ESTIMATE          # the ceiling a parent should wait before worrying
    assert src.count("({RUN_ESTIMATE})...") == 3  # refresh, preview, print: the three long-running jobs


# --- item 17: no favicon -------------------------------------------------------------------

def test_the_favicon_is_declared_and_the_legacy_path_answers(tmp_path):
    from web_fixtures import app_for
    c = app_for(tmp_path)
    page = c.get("/", headers={"host": "127.0.0.1"}).text
    assert re.search(r'<link rel="icon" href="/static/favicon.svg" type="image/svg\+xml">', page)
    assert c.get("/static/favicon.svg", headers={"host": "127.0.0.1"}).status_code == 200
    legacy = c.get("/favicon.ico", headers={"host": "127.0.0.1"})
    assert legacy.status_code == 200 and legacy.headers["content-type"].startswith("image/svg+xml")


# --- item 18: the password field had no autocomplete attribute ----------------------------

def test_the_credential_fields_tell_the_browser_what_they_are():
    html = (WEB / "templates" / "settings.html").read_text(encoding="utf-8")
    assert re.search(r'name="username"[^>]*autocomplete="username"', html)
    assert re.search(r'name="password"[^>]*autocomplete="current-password"', html)


# --- item 19: trailing whitespace from Canvas was stored and rendered ---------------------

def test_an_item_name_is_stripped_at_ingest(tmp_path):
    import sqlite3
    from lakota_grades.web import db, ingest
    conn = db.open_db(tmp_path)
    try:
        sid = ingest._upsert_student(conn, "Kid", "Kid")
        cid = ingest._upsert_course(conn, sid, "canvas", 1, "Honors Biology", None, None)
        conn.execute("INSERT INTO refreshes(started_at, finished_at, sources, ok) VALUES ('2026-09-17T00:00:00', NULL, '{}', 1)")
        rid = conn.execute("SELECT MAX(id) FROM refreshes").fetchone()[0]
        item_id, _ = ingest._upsert_item(conn, sid, cid, "canvas:1", "Chapter 1.3 Reading Guide ", "online",
                                         10, None, None, False, rid)
        assert conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()[0] == "Chapter 1.3 Reading Guide"
    finally:
        conn.close()

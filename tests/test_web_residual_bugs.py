"""Residual server bugs from #3: a flag leaving its row stale, notes on a hidden kid, the moment
an item falls due, and "new since yesterday" across a clock change."""
from __future__ import annotations

from datetime import datetime, timedelta

from fridgesheet import late_rules
from fridgesheet.web import db, reconcile
from fridgesheet.web.stores import items, students
from tests.web_fixtures import NOW, TZ, app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_a_flag_set_from_the_detail_card_refreshes_the_row_and_the_counts(tmp_path):
    """The detail card re-rendered, but the row above it and the question counts in the rail
    kept the old state until a reload -- the same stale page answers fixed in #72."""
    conn = seed(tmp_path)
    iid = _id(conn, "Participation")
    conn.close()
    body = app_for(tmp_path).post(f"/items/{iid}/flag", data={"flag": "done"}).text
    assert f'<tr id="row-{iid}" hx-swap-oob="true">' in body
    assert 'id="qcount-Alex" class="count" hx-swap-oob="true"' in body
    assert "Marked done" in body                                  # the card itself still renders


def test_notes_cannot_be_hung_on_a_hidden_kid_or_their_class(tmp_path):
    conn = seed(tmp_path)
    sam = students.by_key(conn, "Sam")
    course = conn.execute("SELECT id FROM courses WHERE student_id = ? LIMIT 1", (sam["id"],)).fetchone()["id"]
    conn.execute("UPDATE students SET hidden = 1 WHERE id = ?", (sam["id"],))
    conn.close()
    c = app_for(tmp_path)
    assert c.post("/notes", data={"target_type": "student", "target_id": sam["id"], "body": "x"}).status_code == 404
    assert c.post("/notes", data={"target_type": "course", "target_id": course, "body": "x"}).status_code == 404


def test_an_item_due_this_very_minute_is_still_coming_due(tmp_path):
    """`upcoming` needed due > now and `outcomes` counts past only when due < now, so at exactly
    the due minute the item was neither and dropped off the open list."""
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    due = conn.execute("SELECT due FROM items WHERE name = 'Vocabulary'").fetchone()["due"]
    at_due = datetime.fromisoformat(due)
    rules = late_rules.LateRules(late_rules.Rule(), [], [])
    names = [v.name for v in items.list_items(conn, alex, now=at_due, rules=rules, show="open")]
    conn.close()
    assert "Vocabulary" in names


def test_new_since_yesterday_counts_by_time_not_by_text_across_a_clock_change(tmp_path):
    """`started_at >= since` compared ISO strings. The clocks went back at 2 AM on 11/1/2026, so
    1 AM came twice. From 1:30 AM on 11/2 the cut-off is 1:30 AM EDT (05:30 UTC) on 11/1; a
    refresh at 1:20 AM EST (06:20 UTC) came after it, but "01:20" sorts before "01:30" as text,
    so its new items were not counted."""
    now = datetime(2026, 11, 2, 1, 30, tzinfo=TZ)
    conn = seed(tmp_path)
    alex = students.by_key(conn, "Alex")
    stamp = "2026-11-01T01:20:00-05:00"
    assert datetime.fromisoformat(stamp) > now - timedelta(days=1) and stamp < (now - timedelta(days=1)).isoformat()
    rid = conn.execute("INSERT INTO refreshes(started_at, finished_at, sources, ok) VALUES (?, ?, '{}', 1)",
                       (stamp, stamp)).lastrowid
    conn.execute("UPDATE items SET first_seen = ? WHERE student_id = ?", (rid, alex["id"]))
    n = items.dashboard_counts(conn, alex, now=now, rules=late_rules.LateRules(late_rules.Rule(), [], [])).new_since_yesterday
    total = conn.execute("SELECT COUNT(*) FROM items WHERE student_id = ?", (alex["id"],)).fetchone()[0]
    conn.close()
    assert n == total


def test_a_refused_request_says_so_on_the_page():
    """#6: a reprint the server refused with a 400 left the page exactly as it was. One
    `htmx:responseError` handler puts the reason next to what was clicked, as an alert."""
    from pathlib import Path
    from fridgesheet.web import app as webapp
    js = (Path(webapp.__file__).parent / "static" / "app.js").read_text(encoding="utf-8")
    handler = js[js.index('addEventListener("htmx:responseError"'):]
    assert 'setAttribute("role", "alert")' in handler and "errorText(e.detail.xhr)" in handler
    assert "j.detail" in js                       # FastAPI's {"detail": "..."} is read, not shown raw

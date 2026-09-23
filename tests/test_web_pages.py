"""Dashboard and Kid pages: what a parent sees, and the notes and flags round trip."""
from __future__ import annotations

import re

from fridgesheet.web import db
from fridgesheet.web.stores import flags, notes
from tests.web_fixtures import NOW, app_for, seed


def _item_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_dashboard_cards_per_kid(tmp_path):
    conn = seed(tmp_path)
    conn.execute("INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path) VALUES (?,?,?,?,?,?,?)",
                 ("open-work", "2026-09-15T14:00:05-04:00", "2026-09-15T14:02:00-04:00", "schedule", "OK", "2p Al=3 Sam=2", "/x/sheet.pdf"))
    conn.close()
    r = app_for(tmp_path).get("/")
    assert r.status_code == 200
    body = r.text
    assert body.index("Alex") < body.index("Sam")
    assert body.count("2 actionable") == 2                           # Alex (Quiz 1 is settled by HAC's 28/30), Sam
    assert "1 due today" in body and "1 due tomorrow" in body and "8 new since yesterday" in body
    # The card reads the run's log line for the parent instead of echoing it (#40 item 4):
    # "Previewed · 2 pages · Al 3, Sam 2", never the file path or "Al=3".
    assert "Today's sheet" in body and "2 pages" in body and "Al 3, Sam 2" in body
    assert "Al=3" not in body and "sheet.pdf" not in body
    assert 'href="/kids/Alex?show=actionable"' in body


def test_dashboard_with_nothing_printed_says_so(tmp_path):
    seed(tmp_path).close()
    assert "No sheet built today yet" in app_for(tmp_path).get("/").text


def test_kid_page_lists_open_items_by_default_with_filters_and_sort_links(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Lab notebook")
    flags.set_flag(conn, qid, "follow_up", now="2026-09-15T14:30:00-04:00")
    conn.close()
    c = app_for(tmp_path)
    r = c.get("/kids/Alex")
    assert r.status_code == 200
    body = r.text
    table = body[body.index('id="items"'):]
    for name in ("Lab notebook", "Participation", "Vocabulary", "Worksheet 3", "Reading log", "Homework 4"):
        assert name in table, name
    assert "Quiz 1" not in table                                      # HAC's 28/30 settles it (docs/outcomes.md)
    assert "Essay draft" not in table                                 # submitted: not open
    # Three columns (Due, Assignment, Where it stands): Homework 4 is too late for credit (and
    # red: Canvas marked it missing), "today" hangs off the Due date, and the HAC-only
    # Participation says in words that a week has gone by with no grade.
    assert "Too late for credit" in table and 'class="where red"' in table and 'class="rel">today</small>' in table and "No grade after a week" in table
    assert 'name="show"' in body and 'value="all"' in body and 'name="course"' in body
    assert "Honors English 9" in body and "Algebra I" in body        # course filter options
    assert "&amp;sort=name" in body or "&sort=name" in body           # the column header sort links
    assert ">All classes<" in body                                    # the class picker's "no filter"
    assert ">answered or asked<" in body                              # FLAGGED's "any", in family words

    flagged_only = c.get("/kids/Alex?show=all&flagged=any").text
    flagged_table = flagged_only[flagged_only.index('id="items"'):]
    assert "Lab notebook" in flagged_table and "Reading log" not in flagged_table   # only the flagged item shows


def test_kid_page_filters_apply_and_htmx_gets_the_table_only(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.get("/kids/Alex?show=actionable")
    assert "Lab notebook" in r.text and "Reading log" not in r.text
    r = c.get("/kids/Alex?show=all&source=hac", headers={"HX-Request": "true"})
    assert "<html" not in r.text and "Participation" in r.text and "Essay draft" not in r.text
    r = c.get("/kids/Alex?show=all&flagged=marked")
    assert "Quiz 1" not in r.text[r.text.index('id="items"'):]


def test_unknown_kid_is_404(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).get("/kids/Nobody").status_code == 404


def test_item_detail_shows_both_sources_cases_notes_and_the_flag_menu(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    notes.add(conn, "item", qid, "Asked Mr Hoch about the missing mark", now="2026-09-15T14:30:00-04:00")
    conn.close()
    r = app_for(tmp_path).get(f"/items/{qid}")
    assert r.status_code == 200 and "<html" not in r.text
    body = r.text
    assert "Canvas" in body and "marked missing" in body and "HAC" in body and "28 of 30" in body   # the record
    assert "HAC has 28 of 30. Canvas still shows its automatic" in body   # the verdict: decided, with its reason
    assert "Asked Mr Hoch" in body
    for f in ("done", "excused", "ignore", "follow_up", "ask_teacher"):
        assert f'value="{f}"' in body, f
    assert f'hx-post="/items/{qid}/flag"' in body and f'hx-post="/notes"' in body


def test_flag_round_trip_updates_the_detail_and_the_list(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    r = c.post(f"/items/{qid}/flag", data={"flag": "done", "text": "HAC is right"})
    assert r.status_code == 200 and "Marked done" in r.text and "HAC is right" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, qid)["flag"] == "done"
    conn.close()
    assert "Lab notebook" not in c.get("/kids/Alex").text               # handled items leave the open list
    assert "Lab notebook" in c.get("/kids/Alex?show=all").text
    r = c.post(f"/items/{qid}/flag", data={"flag": "clear"})
    assert "No flag" in r.text
    assert "Lab notebook" in c.get("/kids/Alex").text
    assert c.post(f"/items/{qid}/flag", data={"flag": "bogus"}).status_code == 400


def test_notes_round_trip(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    r = c.post("/notes", data={"target_type": "item", "target_id": qid, "body": "first note"})
    assert r.status_code == 200 and "first note" in r.text
    conn = db.open_db(tmp_path)
    (n,) = notes.for_target(conn, "item", qid)
    conn.close()
    r = c.post(f"/notes/{n['id']}/edit", data={"body": "edited note"})
    assert "edited note" in r.text and "first note" not in r.text
    r = c.post(f"/notes/{n['id']}/delete")
    assert "edited note" not in r.text and '<details class="add-note"><summary>' in r.text   # empty: one "Add a note" line
    assert c.post("/notes", data={"target_type": "item", "target_id": qid, "body": "   "}).status_code == 400
    assert c.post("/notes", data={"target_type": "planet", "target_id": 1, "body": "x"}).status_code == 400


def test_a_cross_site_post_is_refused(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    data = {"target_type": "item", "target_id": qid, "body": "from somewhere else"}
    assert c.post("/notes", data=data, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/notes", data=data, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    conn = db.open_db(tmp_path)
    assert notes.for_target(conn, "item", qid) == []                 # nothing was written
    conn.close()
    # "testserver" (TestClient's default Host) is Origin==Host too, but is not an address
    # this app is ever served on -- accepting it would be exactly the evil.example bypass
    # above, just spelled differently. A real same-origin request needs a real Host.
    assert c.post("/notes", data=data, headers={"Origin": "http://testserver"}).status_code == 403
    assert c.post("/notes", data=data, headers={"Host": "127.0.0.1:8433", "Origin": "http://127.0.0.1:8433"}).status_code == 200
    assert c.post("/notes", data=data, headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert c.get("/kids/Alex", headers={"Origin": "http://evil.example"}).status_code == 200   # reads are fine


def test_an_item_of_a_hidden_kid_is_404(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    with conn:
        conn.execute("UPDATE students SET hidden = 1 WHERE key = 'Alex'")
    conn.close()
    c = app_for(tmp_path)
    assert c.get(f"/items/{qid}").status_code == 404                 # like /kids/Alex itself
    assert c.get("/kids/Alex").status_code == 404


def test_course_page_shows_grades_teacher_and_course_notes(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    notes.add(conn, "course", cid, "Syllabus says 7-day late window", now="2026-09-15T14:30:00-04:00")
    conn.close()
    r = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}")
    assert r.status_code == 200
    body = r.text
    assert "Honors English 9" in body and "Michael Hoch" in body and "hoch@example.org" in body
    assert "91.2" in body and "A-" in body and "88" in body          # Canvas current, letter, HAC average via the peer course
    assert "Syllabus says" in body and 'name="target_type" value="course"' in body
    assert "Quiz 1" in body                                          # the course's items
    assert 'id="items"' in body                                      # the sort headers' hx-target exists on this page too
    assert f'/kids/Alex/courses/{cid}?sort=name' in body.replace("&amp;", "&")   # they sort this page, not the Kid page


def test_course_page_sort_keeps_the_peer_courses_rows(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE source = 'canvas' AND short_name = 'Honors English 9'").fetchone()["id"]
    conn.close()
    r = app_for(tmp_path).get(f"/kids/Alex/courses/{cid}?sort=name", headers={"HX-Request": "true"})
    assert r.status_code == 200 and "<html" not in r.text
    body = r.text
    assert "Participation" in body                                   # the HAC-only row from the twin course
    assert body.index("Essay draft") < body.index("Lab notebook") < body.index("Participation")   # sorted by name


def test_a_note_on_something_that_does_not_exist_is_404(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for target in ("item", "course", "student"):
        r = c.post("/notes", data={"target_type": target, "target_id": 999999, "body": "x"})
        assert r.status_code == 404, target
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT COUNT(*) AS n FROM notes").fetchone()["n"] == 0
    conn.close()


def test_course_of_another_kid_is_404(tmp_path):
    conn = seed(tmp_path)
    cid = conn.execute("SELECT id FROM courses WHERE short_name = 'Science 7' AND source = 'canvas'").fetchone()["id"]
    conn.close()
    assert app_for(tmp_path).get(f"/kids/Alex/courses/{cid}").status_code == 404


def test_item_detail_is_the_verdict_the_record_notes_and_a_more_menu(tmp_path):
    conn = seed(tmp_path)
    pid = _item_id(conn, "Participation")
    conn.close()
    body = app_for(tmp_path).get(f"/items/{pid}").text
    assert "Was it handed in?" in body                     # the question card
    assert 'class="record"' in body                        # the evidence
    assert "<summary>More</summary>" in body and 'value="excused"' in body   # the raw flags, behind More
    assert "<th>Says</th>" not in body                     # the old Source/Says table is gone

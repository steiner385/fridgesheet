"""Answering a question card (spec 5 and 6.1)."""
from __future__ import annotations

from fridgesheet.web import db
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _setup(tmp_path, name="Participation"):
    conn = seed(tmp_path)
    iid = _id(conn, name)
    conn.close()
    return app_for(tmp_path), iid


def test_answering_sets_the_flag_and_collapses_to_one_line_with_undo(tmp_path):
    c, pid = _setup(tmp_path)
    r = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    assert r.status_code == 200
    assert f'id="q-{pid}"' in r.text and "Undo" in r.text and "Participation" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, pid)["flag"] == "done"


def test_undo_restores_the_previous_state_and_the_question(tmp_path):
    c, pid = _setup(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    r = c.post(f"/items/{pid}/undo", data={"prev": ""})
    assert "Was it handed in?" in r.text
    conn = db.open_db(tmp_path)
    assert flags.active(conn, pid) is None


def test_a_double_submitted_answer_leaves_one_flag(tmp_path):
    """Review Focus 5."""
    c, pid = _setup(tmp_path)
    first = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    second = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    assert "Undo" in first and "Undo" in second
    conn = db.open_db(tmp_path)
    assert len([r for r in flags.history(conn, pid) if r["cleared_at"] is None]) == 1


def test_asking_the_teacher_offers_their_email(tmp_path):
    """Spec 5: the asked line carries a mailto when the course has a teacher email."""
    c, pid = _setup(tmp_path)
    body = c.post(f"/items/{pid}/answer", data={"answer": "ask_teacher", "prev": ""}).text
    assert "mailto:hoch@example.org" in body


def test_the_record_says_as_of_when(tmp_path):
    c, pid = _setup(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    assert "checked" in c.post(f"/items/{pid}/undo", data={"prev": ""}).text          # last checked, and last changed (#75)


def test_an_unknown_answer_is_refused(tmp_path):
    c, pid = _setup(tmp_path)
    assert c.post(f"/items/{pid}/answer", data={"answer": "bogus", "prev": ""}).status_code == 400


def test_the_question_card_offers_the_record_and_plan_links(tmp_path):
    c, pid = _setup(tmp_path)
    c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": ""})
    body = c.post(f"/items/{pid}/undo", data={"prev": ""}).text
    assert "See the record" in body and "Add a note" in body
    assert f"check-in/step?item_id={pid}" in body          # the "Plan a step" link


# --- final-review fixes ------------------------------------------------------------------

def _stale_homework(tmp_path):
    """Homework 4 flagged done on 9/1, before the seed's refresh recorded it missing: stale."""
    conn = seed(tmp_path)
    hid = _id(conn, "Homework 4")
    flags.set_flag(conn, hid, "done", now="2026-09-01T08:00:00-04:00", text="handed in")
    conn.close()
    return app_for(tmp_path), hid


def test_undo_after_answering_a_stale_question_brings_the_question_back(tmp_path):
    """Review 1: undo must restore the flag *and its date*, so the stale question returns."""
    c, hid = _stale_homework(tmp_path)
    card = c.get(f"/items/{hid}").text
    assert "Still done?" in card and 'name="prev_set_at" value="2026-09-01T08:00:00-04:00"' in card
    for answer in ("clear", "confirm"):
        c.post(f"/items/{hid}/answer", data={"answer": answer, "prev": "done", "prev_set_at": "2026-09-01T08:00:00-04:00"})
        body = c.post(f"/items/{hid}/undo", data={"prev": "done", "prev_set_at": "2026-09-01T08:00:00-04:00"}).text
        assert "Still done?" in body, answer
        assert "facts." not in body and "where." not in body
        conn = db.open_db(tmp_path)
        active = flags.active(conn, hid)
        assert (active["flag"], active["set_at"], active["text"]) == ("done", "2026-09-01T08:00:00-04:00", "handed in")
        conn.close()


def test_reopening_shows_where_it_stands_in_words(tmp_path):
    """Review 3: "No, reopen it" left a raw `where.not_done` on the answered line."""
    conn = seed(tmp_path)
    cid = _id(conn, "Cell diagram")                     # Sam's: missing in Canvas, still inside its window
    flags.set_flag(conn, cid, "done", now="2026-09-01T08:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).post(f"/items/{cid}/answer", data={"answer": "clear", "prev": "done"}).text
    assert "where." not in body and "Cell diagram" in body and "Missing" in body


def test_answering_from_the_tables_expanded_row_swaps_that_card(tmp_path):
    """Review 4: the detail's card must not share an id with the section card above it."""
    import re
    c, pid = _setup(tmp_path)
    page = c.get("/kids/Alex").text
    detail = c.get(f"/items/{pid}").text
    page_ids = set(re.findall(r'id="([^"]+)"', page))
    detail_ids = set(re.findall(r'id="([^"]+)"', detail))
    assert not (page_ids & detail_ids) - {"notes-item-%d" % pid}, page_ids & detail_ids
    target = re.search(r'hx-post="/items/%d/answer" hx-target="#([^"]+)"' % pid, detail).group(1)
    assert target in detail_ids
    slot = re.search(r'name="slot" value="([^"]+)"', detail).group(1)
    r = c.post(f"/items/{pid}/answer", data={"answer": "done", "prev": "", "slot": slot})
    assert f'id="{slot}"' in r.text


def test_every_answer_form_carries_a_request_key(tmp_path):
    import re
    c, pid = _setup(tmp_path)
    forms = re.findall(r'<form hx-post="/items/%d/answer".*?</form>' % pid, c.get(f"/items/{pid}").text, re.S)
    assert forms
    keys = {re.search(r'name="request_key" value="([^"]+)"', f).group(1) for f in forms}
    assert len(keys) == 1 and len(next(iter(keys))) == 36       # one uuid per card, shared by its buttons


# --- plan answers (spec 6.3, 6.4, 6.5) ---------------------------------------------------------------

from uuid import uuid4

from fridgesheet.web.stores import plans


def _steps(home):
    conn = db.open_db(home)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM plan_steps ORDER BY id")]
    finally:
        conn.close()


def _plan(c, pid, when="plan:today", key=None, slot=""):
    return c.post(f"/items/{pid}/answer", data={"answer": when, "prev": "", "request_key": key or str(uuid4()), "slot": slot})


def test_today_creates_a_step_with_the_documented_defaults(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    r = _plan(c, vid, "plan:today", slot=f"qc-{vid}")
    assert r.status_code == 200
    (step,) = _steps(tmp_path)
    assert (step["title"], step["next_step"], step["owner"], step["planned_for"], step["minutes"], step["state"], step["position"]) == \
        ("Vocabulary", "Work on it", "Alex", "2026-09-15", None, "planned", 10)
    assert step["item_id"] == vid and step["family_account"] == "" and step["revision"] == 1
    assert "Planned for today" in r.text and "Undo" in r.text
    assert f'check-in/step?step_id={step["id"]}' in r.text and "Add details" in r.text


def test_tomorrow_plans_for_the_next_day(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid, "plan:tomorrow")
    assert _steps(tmp_path)[0]["planned_for"] == "2026-09-16"


def test_the_same_request_key_twice_is_one_step(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    key = str(uuid4())
    first, second = _plan(c, vid, key=key), _plan(c, vid, key=key)
    assert first.status_code == 200 and second.status_code == 200
    assert len(_steps(tmp_path)) == 1


def test_a_plan_answer_on_covered_work_is_refused(tmp_path):
    """Review Focus 3: one commitment per assignment from a tap."""
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    r = _plan(c, vid, "plan:tomorrow")
    assert r.status_code == 409 and len(_steps(tmp_path)) == 1


def test_a_plan_answer_without_a_request_key_is_refused(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    assert c.post(f"/items/{vid}/answer", data={"answer": "plan:today", "prev": ""}).status_code == 400


def test_the_response_carries_the_plan_panel_out_of_band(tmp_path):
    import re
    c, vid = _setup(tmp_path, "Vocabulary")
    body = _plan(c, vid).text
    section = re.search(r'<section id="plan"[^>]*hx-swap-oob="true"[^>]*>.*?</section>', body, re.S)
    assert section, body[:2000]
    assert "Vocabulary" in section.group(0)                                 # the step is in the panel
    assert "1 step without an estimate" in section.group(0)


def test_undo_deletes_an_unedited_step_and_brings_the_card_back(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    body = _plan(c, vid, slot=f"qc-{vid}").text
    sid = _steps(tmp_path)[0]["id"]
    assert f'name="step_id" value="{sid}"' in body
    r = c.post(f"/items/{vid}/undo", data={"prev": "", "step_id": str(sid), "slot": f"qc-{vid}"})
    assert r.status_code == 200 and _steps(tmp_path) == []
    assert 'value="plan:today"' in r.text and 'id="plan"' in r.text


def test_undo_leaves_an_edited_step_alone(tmp_path):
    """Review Focus 4."""
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    step = _steps(tmp_path)[0]
    conn = db.open_db(tmp_path)
    plans.save(conn, step["student_id"], {**{k: step[k] for k in plans.FIELDS}, "minutes": 20}, now="2026-09-15T15:00:00-04:00",
               request_key=str(uuid4()), item_id=vid, step_id=step["id"], revision=1)
    conn.close()
    r = c.post(f"/items/{vid}/undo", data={"prev": "", "step_id": str(step["id"])})
    assert r.status_code == 200 and _steps(tmp_path)[0]["minutes"] == 20


def test_undo_with_another_kids_step_is_refused(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    sid = _steps(tmp_path)[0]["id"]
    other = _id(db.open_db(tmp_path), "Cell diagram")                      # Sam's
    assert c.post(f"/items/{other}/undo", data={"prev": "", "step_id": str(sid)}).status_code == 404
    assert len(_steps(tmp_path)) == 1


def test_a_planned_item_leaves_the_check_in_queue(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    body = c.get("/kids/Alex/check-in").text
    assert f'id="qc-{vid}"' not in body and "Vocabulary" in body.split('<section id="plan"')[1]


# --- review: a refusal and a kept step are told to the family, not swallowed --------------------

def test_a_refused_plan_answer_says_why_in_words_the_page_can_show(tmp_path):
    """htmx does not swap a 409 body; app.js shows a short `detail` next to the button."""
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    r = _plan(c, vid, "plan:tomorrow")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "already" in detail.lower() and "9/15" in detail and len(detail) < 300


def test_planned_work_offers_no_second_one_tap_plan(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    body = c.get(f"/items/{vid}").text
    assert 'value="plan:today"' not in body and 'value="plan:tomorrow"' not in body
    assert "Plan another step" in body                                     # the form is still there


def test_undo_on_an_edited_step_says_the_step_stays(tmp_path):
    c, vid = _setup(tmp_path, "Vocabulary")
    _plan(c, vid)
    step = _steps(tmp_path)[0]
    conn = db.open_db(tmp_path)
    plans.save(conn, step["student_id"], {**{k: step[k] for k in plans.FIELDS}, "minutes": 20}, now="2026-09-15T15:00:00-04:00",
               request_key=str(uuid4()), item_id=vid, step_id=step["id"], revision=1)
    conn.close()
    r = c.post(f"/items/{vid}/undo", data={"prev": "", "step_id": str(step["id"]), "slot": f"qc-{vid}"})
    assert r.status_code == 200
    assert "answer undone" not in r.text and "edited" in r.text and "stays" in r.text
    assert f'check-in/step?step_id={step["id"]}' in r.text                 # a way to the step
    assert f'hx-post="/items/{vid}/undo"' not in r.text                    # no undo of an undo

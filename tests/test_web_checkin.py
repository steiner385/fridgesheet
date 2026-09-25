"""The check-in workspace: review queues, saved next steps, agreements, printing and isolation.

Three layers stay independent throughout: the school record (observations and flags), the
family's account of what happened, and the commitment they agreed on. A test that touches
one asserts the other two are untouched.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from uuid import uuid4

from fridgesheet.web import db, ingest
from fridgesheet.web.stores import flags, plans
from tests.web_fixtures import NOW, TZ, _h, app_for, seed, snapshot


def _item_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _step_rows(home):
    conn = db.open_db(home)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM plan_steps ORDER BY id")]
    finally:
        conn.close()


def _form(**over):
    base = dict(title="Quiz 1", family_account="", next_step="Ask Mr. Hoch to clear the missing flag", owner="Alex",
                planned_for="2026-09-16", minutes="", state="planned", position="10", request_key=str(uuid4()), revision="1")
    base.update(over)
    return base


def _finish(**over):
    base = dict(available_minutes="40", next_check="2026-09-17", summary="Quiz first, then vocabulary.", request_key=str(uuid4()))
    base.update(over)
    return base


def _queues(body: str) -> dict[str, str]:
    """The three review groups' HTML, by label, so a test can say which group a row is in."""
    groups = re.split(r'<details class="queue-group"', body)[1:]
    out = {}
    for g in groups:
        label = re.search(r"<summary>(.*?) <span", g)
        if label and label.group(1) in ("To do", "Questions", "Waiting on the school"):
            out[label.group(1)] = g
    return out


def _post_step(c, key, form, **query):
    q = "&".join(f"{k}={v}" for k, v in query.items())
    return c.post(f"/kids/{key}/check-in/step" + (f"?{q}" if q else ""), data=form, follow_redirects=False)


# --- the review queue ---------------------------------------------------------------------------

def test_check_in_sorts_the_school_record_into_three_review_groups(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/kids/Alex/check-in")
    assert r.status_code == 200
    q = _queues(r.text)
    assert set(q) == {"To do", "Questions", "Waiting on the school"}
    for name in ("Vocabulary", "Worksheet 3", "Reading log", "Homework 4"):     # open or upcoming, nothing to explain
        assert name in q["To do"], name
    assert "Participation" in q["Questions"]                                     # HAC-only, a week with no grade
    assert "Lab notebook" in q["Waiting on the school"]                          # paper, under a week: waiting, as on Assignments
    assert "Quiz 1" not in r.text.split('id="plan"')[0]                          # HAC's 28/30 settles it (docs/outcomes.md)
    assert "Essay draft" in q["Waiting on the school"]
    assert "Essay draft" not in q["To do"]                            # submitted work is never "redo it"


def test_review_evidence_states_facts_and_leaves_room_for_the_childs_account(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    alex = c.get("/kids/Alex/check-in").text
    assert "The sources disagree." not in alex        # Quiz 1 was the only disagreement; HAC's grade settles it
    assert "nothing to submit online" in alex                   # Lab notebook, in the record's one vocabulary (#129)
    assert "Late work is usually accepted until" in alex and "Ask the teacher if you need longer" in alex
    sam = c.get("/kids/Sam/check-in").text
    assert "Zero recorded. A zero can mean not graded yet, not handed in, or handed in on paper" in sam
    assert "did no work" not in sam and "didn't do" not in sam


def test_work_that_still_earns_credit_comes_before_closed_late_windows(tmp_path):
    """Homework 4 is a month old and past its 14-day window; sorting by due date alone would put
    it above tonight's Vocabulary. The queue keeps it visible but after the work that can still
    earn credit."""
    seed(tmp_path).close()
    consider = _queues(app_for(tmp_path).get("/kids/Alex/check-in").text)["To do"]
    assert consider.index("Vocabulary") < consider.index("Worksheet 3") < consider.index("Reading log") < consider.index("Homework 4")


def test_undated_work_is_reviewable_with_its_missing_date_named(tmp_path):
    snap = snapshot()
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"].append(_h("Reading project", "", None))
    seed(tmp_path, snap).close()
    q = _queues(app_for(tmp_path).get("/kids/Alex/check-in").text)
    assert "Reading project" in q["To do"]
    assert "no due date listed" in q["To do"]


def test_a_child_with_no_work_still_gets_a_working_check_in(tmp_path):
    snap = snapshot()
    snap["students"]["Kim"] = {"name": "Kim Example", "canvas_id": 3, "hac_name": "Kim Example",
                               "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    seed(tmp_path, snap).close()
    c = app_for(tmp_path)
    r = c.get("/kids/Kim/check-in")
    assert r.status_code == 200 and r.text.count("Nothing in this group.") == 3
    assert "No steps here yet." in r.text
    assert c.get("/kids/Kim/plan/print").status_code == 200


# --- saving next steps ----------------------------------------------------------------------------

def test_saving_a_step_moves_the_assignment_from_review_into_the_plan(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    form = c.get(f"/kids/Alex/check-in/step?item_id={qid}")
    assert form.status_code == 200 and 'value="Quiz 1"' in form.text and 'name="request_key"' in form.text
    r = _post_step(c, "Alex", _form(family_account="Took it in class Friday; HAC has 28/30."), item_id=qid)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"
    page = c.get("/kids/Alex/check-in?saved=1").text
    assert "Saved. Your family plan is separate from the school record." in page
    assert "Ask Mr. Hoch to clear the missing flag" in page and "Took it in class Friday" in page
    assert "Quiz 1" not in _queues(page)["Questions"]      # covered by an active step
    rows = _step_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["item_id"] == qid and rows[0]["state"] == "planned" and rows[0]["revision"] == 1


def test_a_manual_task_needs_no_school_assignment(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert "Assignment or task" in c.get("/kids/Alex/check-in/step").text
    r = _post_step(c, "Alex", _form(title="Bring PE uniform", next_step="Pack it Wednesday night", owner="Alex"))
    assert r.status_code == 303
    plan = c.get("/kids/Alex/plan").text
    assert "Bring PE uniform" in plan and "Family-added task" in plan
    assert _step_rows(tmp_path)[0]["item_id"] is None


def test_the_form_for_submitted_ungraded_work_defaults_to_waiting(tmp_path):
    conn = seed(tmp_path)
    eid = _item_id(conn, "Essay draft")
    conn.close()
    c = app_for(tmp_path)
    page = c.get("/kids/Alex/check-in").text
    assert f'href="/kids/Alex/check-in/step?item_id={eid}&amp;state=waiting"' in page
    form = c.get(f"/kids/Alex/check-in/step?item_id={eid}&state=waiting").text
    assert re.search(r'<option value="waiting"\s+selected', form)
    form = c.get(f"/kids/Alex/check-in/step?item_id={eid}&state=bogus").text
    assert re.search(r'<option value="planned"\s+selected', form)                 # unknown hint: the usual default


def test_validation_keeps_typed_values_and_explains_in_plain_words(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    story = "I handed the worksheet in on paper on Tuesday and Ms. Lee said she would look for it."
    cases = {
        "minutes": ("twenty", "minutes"),
        "planned_for": ("9/16", "YYYY-MM-DD"),
        "planned_for": ("2026-02-30", "YYYY-MM-DD"),
        "position": ("0", "order"),
        "position": ("x", "order"),
        "title": ("", "title"),
        "revision": ("abc", "Reload"),
    }
    for field, (bad, hint) in cases.items():
        r = _post_step(c, "Alex", _form(family_account=story, **{field: bad}))
        assert r.status_code == 422, field
        assert story in r.text, field                                           # nothing typed is lost
        assert hint.lower() in r.text.lower(), (field, hint)
        for leak in ("invalid literal", "Traceback", "ValueError", "isoformat"):
            assert leak not in r.text, (field, leak)
    assert _step_rows(tmp_path) == []
    # An oversized account is refused with its length rule, not silently cut.
    r = _post_step(c, "Alex", _form(family_account="x" * 4001))
    assert r.status_code == 422 and "4,000" in r.text


def test_family_text_is_escaped_on_screen_in_history_and_in_print(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    evil = "<script>alert(1)</script>"
    _post_step(c, "Alex", _form(title=f"T{evil}", family_account=f"A{evil}", next_step=f"N{evil}", owner=f"O{evil}"), item_id=qid)
    c.post("/kids/Alex/check-in/finish", data=_finish(summary=f"S{evil}"), follow_redirects=False)
    for path in ("/kids/Alex/check-in", "/kids/Alex/plan", "/kids/Alex/plan/print"):
        body = c.get(path).text
        assert evil not in body, path
        assert "&lt;script&gt;" in body, path
    step = _step_rows(tmp_path)[0]
    edit = c.get(f"/kids/Alex/check-in/step?step_id={step['id']}").text
    assert evil not in edit and "T&lt;script&gt;" in edit


def test_a_repeated_post_does_not_duplicate_a_step(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    form = _form(title="Read 10 pages")
    assert _post_step(c, "Alex", form).status_code == 303
    assert _post_step(c, "Alex", form).status_code == 303                         # back button, submit again
    assert len(_step_rows(tmp_path)) == 1


def test_concurrent_edits_do_not_overwrite_one_another(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Lab notebook", next_step="Ask Mr. Hoch to check the bin"))
    sid = _step_rows(tmp_path)[0]["id"]
    parent = c.get(f"/kids/Alex/check-in/step?step_id={sid}").text
    assert 'name="revision" value="1"' in parent
    first = _post_step(c, "Alex", _form(title="Lab notebook", next_step="Parent: emailed Mr. Hoch", revision="1"), step_id=sid)
    assert first.status_code == 303
    second = _post_step(c, "Alex", _form(title="Lab notebook", next_step="Grandma: saw the notebook", family_account="Showed me Wed", revision="1"), step_id=sid)
    assert second.status_code == 409
    assert "changed in another window" in second.text and "Showed me Wed" in second.text   # nothing typed is lost
    assert f'href="/kids/Alex/check-in/step?step_id={sid}"' in second.text          # and the latest is one click away
    row = _step_rows(tmp_path)[0]
    assert row["next_step"] == "Parent: emailed Mr. Hoch" and row["revision"] == 2
    # With the fresh revision the second person's save goes through.
    assert _post_step(c, "Alex", _form(title="Lab notebook", next_step="Grandma: saw the notebook", revision="2"), step_id=sid).status_code == 303
    assert _step_rows(tmp_path)[0]["revision"] == 3


def test_completing_a_step_does_not_mark_the_assignment_submitted(tmp_path):
    conn = seed(tmp_path)
    cid = _item_id(conn, "Cell diagram")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Sam", _form(title="Cell diagram", next_step="Label the 6 parts", owner="Sam", minutes="20", planned_for="2026-09-15"), item_id=cid)
    sid = _step_rows(tmp_path)[0]["id"]
    assert "20 min estimated for today" in c.get("/kids/Sam/plan").text
    r = _post_step(c, "Sam", _form(title="Cell diagram", next_step="Label the 6 parts", owner="Sam", minutes="20", planned_for="2026-09-15", state="done"), step_id=sid)
    assert r.status_code == 303
    page = c.get("/kids/Sam/check-in").text
    assert "Cell diagram" in _queues(page)["To do"]                  # back in review: still not handed in
    assert "0 min estimated for today" in page
    assert "The school decides what counts as submitted." in page
    assert f'href="/kids/Sam/check-in/step?item_id={cid}"' in page             # a second step for the same work
    all_work = c.get("/kids/Sam?show=all").text
    assert ">Missing · Canvas<" in all_work                                               # the school record is untouched
    conn = db.open_db(tmp_path)
    obs = db.latest_observations(conn, conn.execute("SELECT id FROM students WHERE key='Sam'").fetchone()[0])[cid]
    assert obs["canvas"]["submitted_at"] is None and obs["canvas"]["missing"] == 1
    assert flags.active(conn, cid) is None
    conn.close()


# --- the school record moves on; the family's words do not -----------------------------------

def _refresh(home, snap, when):
    conn = db.open_db(home)
    ingest.record(conn, snap, tz=TZ, now=when)
    conn.close()


def test_commitments_survive_a_refresh_and_never_write_school_facts(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "follow_up", now=NOW.isoformat(), text="ask on Monday")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(family_account="Took it in class; HAC shows 28/30.", state="waiting", planned_for="2026-09-17"), item_id=qid)
    later = NOW + timedelta(days=1)
    _refresh(tmp_path, snapshot(), later)
    page = app_for(tmp_path, now=later).get("/kids/Alex/plan").text
    assert "Took it in class; HAC shows 28/30." in page and "Check again Thu 9/17" in page
    assert "School evidence changed" not in page                                # same facts, new refresh id
    conn = db.open_db(tmp_path)
    obs = db.latest_observations(conn, conn.execute("SELECT id FROM students WHERE key='Alex'").fetchone()[0])[qid]
    assert obs["canvas"]["missing"] == 1 and obs["hac"]["score"] == 28.0       # the school's facts, as the school said them
    assert flags.active(conn, qid)["flag"] == "follow_up"                       # the old flag path is untouched
    assert conn.execute("SELECT COUNT(*) FROM refreshes").fetchone()[0] == 2
    conn.close()


def test_evidence_change_notice_follows_facts_not_refresh_ids(tmp_path):
    conn = seed(tmp_path)
    qid, lid = _item_id(conn, "Quiz 1"), _item_id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(state="waiting"), item_id=qid)
    _post_step(c, "Alex", _form(title="Lab notebook", state="waiting", family_account="On paper Tuesday"), item_id=lid)
    day2 = NOW + timedelta(days=1)
    _refresh(tmp_path, snapshot(), day2)
    assert "School evidence changed" not in app_for(tmp_path, now=day2).get("/kids/Alex/plan").text
    fixed = snapshot()
    for a in fixed["students"]["Alex"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"], a["state"], a["score"], a["grade"] = False, "graded", 28.0, "28"
    day3 = NOW + timedelta(days=2)
    _refresh(tmp_path, fixed, day3)
    page = app_for(tmp_path, now=day3).get("/kids/Alex/plan").text
    cards = page.split('<article class="card plan-card">')[1:]
    quiz = next(x for x in cards if "Quiz 1" in x)
    lab = next(x for x in cards if "Lab notebook" in x)
    assert "School evidence changed since this step was saved" in quiz
    assert "School evidence changed" not in lab and "On paper Tuesday" in lab


def test_a_step_on_work_the_school_dropped_is_kept_and_labelled(tmp_path):
    conn = seed(tmp_path)
    lid = _item_id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Lab notebook", family_account="Handed in on paper", state="waiting"), item_id=lid)
    dropped = snapshot()
    eng = dropped["students"]["Alex"]["canvas"]["courses"][0]
    eng["assignments"] = [a for a in eng["assignments"] if a["name"] != "Lab notebook"]
    later = NOW + timedelta(days=1)
    _refresh(tmp_path, dropped, later)
    page = app_for(tmp_path, now=later).get("/kids/Alex/plan").text
    assert "Handed in on paper" in page
    assert "This assignment is no longer in the current school list. Your step is still saved." in page


# --- siblings and strangers ----------------------------------------------------------------------

def test_another_childs_ids_are_refused_and_hidden_children_are_404(tmp_path):
    conn = seed(tmp_path)
    sam_item = _item_id(conn, "Cell diagram")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Sam", _form(title="Cell diagram", owner="Sam"), item_id=sam_item)
    sam_step = _step_rows(tmp_path)[0]["id"]
    assert c.get(f"/kids/Alex/check-in/step?item_id={sam_item}").status_code == 404
    assert c.get(f"/kids/Alex/check-in/step?step_id={sam_step}").status_code == 404
    assert _post_step(c, "Alex", _form(), item_id=sam_item).status_code == 404
    assert _post_step(c, "Alex", _form(), step_id=sam_step).status_code == 404
    assert c.get("/kids/Alex/check-in/step?step_id=999999").status_code == 404
    assert c.get("/kids/Alex/check-in/step?step_id=abc").status_code == 404
    assert c.get("/kids/Nobody/check-in").status_code == 404
    assert c.post("/kids/Nobody/check-in/finish", data=_finish()).status_code == 404
    # A request key already used for Sam's step cannot be replayed to plant a copy under Alex.
    sam_form = _form(title="Safety quiz", owner="Sam")
    assert _post_step(c, "Sam", sam_form).status_code == 303
    replay = _post_step(c, "Alex", sam_form)
    assert replay.status_code == 422 and "belongs to another child" in replay.text
    rows = _step_rows(tmp_path)
    assert len(rows) == 2 and {r["title"] for r in rows} == {"Cell diagram", "Safety quiz"}
    conn = db.open_db(tmp_path)
    conn.execute("UPDATE students SET hidden = 1 WHERE key = 'Sam'")
    conn.close()
    for path in ("/kids/Sam/check-in", "/kids/Sam/plan", "/kids/Sam/plan/print", f"/kids/Sam/check-in/step?step_id={sam_step}"):
        assert c.get(path).status_code == 404, path


def test_each_childs_pages_show_only_their_own_steps_even_with_shared_canvas_ids(tmp_path):
    """Siblings in one section share Canvas assignment ids: the item row, not the source id,
    decides ownership."""
    snap = snapshot()
    twin = snapshot()["students"]["Alex"]
    twin["name"], twin["canvas_id"], twin["hac_name"] = "Zoë Q Example", 3, "Zoë Q Example"
    snap["students"]["Zoë Q"] = twin
    conn = seed(tmp_path, snap)
    alex_quiz = conn.execute("SELECT i.id FROM items i JOIN students s ON s.id = i.student_id WHERE i.name='Quiz 1' AND s.key='Alex'").fetchone()[0]
    zoe_quiz = conn.execute("SELECT i.id FROM items i JOIN students s ON s.id = i.student_id WHERE i.name='Quiz 1' AND s.key='Zoë Q'").fetchone()[0]
    conn.close()
    assert alex_quiz != zoe_quiz
    c = app_for(tmp_path)
    assert _post_step(c, "Alex", _form(next_step="Alex asks Mr. Hoch"), item_id=alex_quiz).status_code == 303
    assert _post_step(c, "Zo%C3%AB%20Q", _form(next_step="Zoë asks Mr. Hoch", owner="Zoë"), item_id=zoe_quiz).status_code == 303
    alex = c.get("/kids/Alex/check-in").text
    zoe = c.get("/kids/Zo%C3%AB%20Q/check-in").text
    assert "Alex asks Mr. Hoch" in alex and "Zoë asks Mr. Hoch" not in alex
    assert "Zoë asks Mr. Hoch" in zoe and "Alex asks Mr. Hoch" not in zoe
    assert "Quiz 1" not in _queues(zoe)["Questions"]
    assert 'href="/kids/Zo%C3%ABQ' not in zoe and 'href="/kids/Zo%C3%AB%20Q/plan"' in zoe   # the key survives every link
    assert 'href="/kids/Zo%C3%AB%20Q/check-in"' in c.get("/").text


# --- agreements ------------------------------------------------------------------------------

def test_finishing_a_check_in_saves_an_agreement_that_later_edits_do_not_rewrite(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", next_step="Ten words tonight", minutes="15", planned_for="2026-09-15"), item_id=vid)
    _post_step(c, "Alex", _form(title="Old reading", next_step="Already done", state="done"))
    token = str(uuid4())
    r = c.post("/kids/Alex/check-in/finish", data=_finish(summary="Ten words, then Mom emails Ms. Lee.", request_key=token), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/plan?saved=1"
    plan = c.get("/kids/Alex/plan?saved=1").text
    assert "Previous agreements" in plan and "Ten words, then Mom emails Ms. Lee." in plan
    assert "Next check-in Thu 9/17 · 40 min available" in plan
    assert "Vocabulary · Alex: Ten words tonight — Tue 9/15 (Work to do)" in plan
    assert "Already done" not in plan.split("Previous agreements")[1]           # done steps are not part of the agreement
    assert c.post("/kids/Alex/check-in/finish", data=_finish(request_key=token), follow_redirects=False).status_code == 303
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM checkins").fetchone()[0] == 1     # resubmitting the same form once more
    conn.close()
    sid = next(s["id"] for s in _step_rows(tmp_path) if s["title"] == "Vocabulary")
    _post_step(c, "Alex", _form(title="Vocabulary", next_step="Twenty words tonight", revision="1"), step_id=sid)
    history = c.get("/kids/Alex/plan").text.split("Previous agreements")[1]
    assert "Ten words tonight" in history and "Twenty words tonight" not in history


def test_finish_validation_is_plain_and_keeps_what_was_typed(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for bad in (dict(available_minutes=""), dict(available_minutes="lots"), dict(available_minutes="0"),
                dict(next_check="tomorrow"), dict(next_check="2026-13-01"), dict(request_key="")):
        r = c.post("/kids/Alex/check-in/finish", data=_finish(summary="We agreed on ten words.", **bad), follow_redirects=False)
        assert r.status_code == 422, bad
        assert "We agreed on ten words." in r.text, bad
        for leak in ("invalid literal", "Traceback", "isoformat", "ValueError"):
            assert leak not in r.text, (bad, leak)
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM checkins").fetchone()[0] == 0
    conn.close()


def test_the_plan_compares_todays_estimate_with_the_agreed_budget_and_flags_a_due_check_in(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Sam", _form(title="Label the parts", owner="Sam", minutes="20", planned_for="2026-09-15"))
    _post_step(c, "Sam", _form(title="Upload the photo", owner="Sam", minutes="5", planned_for="2026-09-15"))
    _post_step(c, "Sam", _form(title="Ask Mr. Kim", owner="Sam", state="waiting", planned_for="2026-09-15"))
    c.post("/kids/Sam/check-in/finish", data=_finish(available_minutes="20", next_check="2026-09-14"), follow_redirects=False)
    page = c.get("/kids/Sam/plan").text
    assert "25 min estimated for today" in page                                 # waiting steps carry no minutes today
    assert "25 min planned today, 20 min available: 5 min over. Move a step to another day." in page
    assert "time to check in" in page                                           # next check-in was yesterday


# --- the printable plan -------------------------------------------------------------------------

def test_the_print_view_is_one_childs_agreement_and_nothing_else(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", next_step="Ten words tonight", minutes="15"))
    _post_step(c, "Alex", _form(title="Homework 4", next_step="Email Ms. Lee about an extension", owner="Mom", state="blocked"))
    _post_step(c, "Alex", _form(title="Old reading", next_step="Already finished", state="done"))
    _post_step(c, "Sam", _form(title="Cell diagram", next_step="Label the 6 parts", owner="Sam"))
    c.post("/kids/Alex/check-in/finish", data=_finish(summary="Mom emails; Alex does ten words."), follow_redirects=False)
    r = c.get("/kids/Alex/plan/print")
    assert r.status_code == 200
    body = r.text
    assert "Ten words tonight" in body and "Email Ms. Lee about an extension" in body and "<strong>Mom</strong>" in body
    assert "Mom emails; Alex does ten words." in body and "Next check-in: Thu 9/17" in body
    assert "Label the 6 parts" not in body and "Sam" not in body               # the sibling stays off this fridge
    assert "Already finished" not in body                                       # done steps are not commitments
    for control in ("Edit or complete", "<form", 'class="rail"', "<header", "Reconcile", "Settings", "hx-"):
        assert control not in body, control
    assert 'href="/kids/Alex/plan"' in body and "data-print-plan" in body       # back, and an explicit print button


def test_child_nav_joins_the_workspaces_and_all_work_keeps_its_filters(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for path, current in (("/kids/Alex/check-in", "Check-in"), ("/kids/Alex/plan", "Plan"), ("/kids/Alex", "Assignments")):
        body = c.get(path).text
        assert 'aria-label="Child workspace"' in body, path
        assert re.search(rf'aria-current="page"[^>]*>{current}<', body), (path, current)
    # On a phone the queue runs two screens before the plan: the check-in page offers a jump.
    checkin = c.get("/kids/Alex/check-in").text
    assert '<a class="button-link" href="#plan">Jump to our next steps</a>' in checkin
    assert 'href="#plan">Jump to our next steps' not in c.get("/kids/Alex/plan").text
    table = c.get("/kids/Alex?show=all&flagged=none&sort=name").text
    assert "Essay draft" in table and 'name="show"' in table
    detail_link = f'href="/kids/Alex/check-in/step?item_id='
    conn = db.open_db(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    assert detail_link + str(qid) in c.get(f"/items/{qid}", headers={"HX-Request": "true"}).text


# --- what the persona sessions asked for ------------------------------------------------------

def test_the_plan_page_cannot_finish_a_check_in_and_the_form_defaults_to_the_agreed_date(tmp_path):
    """A caregiver reading the plan pressed the one button on it and replaced the agreed next
    check-in with today's date and no summary. Finishing belongs to the check-in page, and its
    date starts from what was agreed while that is still ahead."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert 'action="/kids/Alex/check-in/finish"' in c.get("/kids/Alex/check-in").text
    assert 'action="/kids/Alex/check-in/finish"' not in c.get("/kids/Alex/plan").text
    c.post("/kids/Alex/check-in/finish", data=_finish(next_check="2026-09-17"), follow_redirects=False)
    assert 'name="next_check" required value="2026-09-17"' in c.get("/kids/Alex/check-in").text
    c.post("/kids/Alex/check-in/finish", data=_finish(next_check="2026-09-14"), follow_redirects=False)
    assert 'name="next_check" required value="2026-09-15"' in c.get("/kids/Alex/check-in").text   # agreed date passed: today


def test_finishing_needs_a_few_words_about_what_was_agreed(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    r = c.post("/kids/Alex/check-in/finish", data=_finish(summary="   "), follow_redirects=False)
    assert r.status_code == 422 and "What we agreed" in r.text
    conn = db.open_db(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM checkins").fetchone()[0] == 0
    conn.close()


def test_review_groups_with_something_in_them_start_open(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert c.get("/kids/Alex/check-in").text.count('<details class="queue-group" open>') == 3
    sam = c.get("/kids/Sam/check-in").text                        # no questions, nothing waiting: only To do
    assert sam.count('<details class="queue-group" open>') == 1


def test_steps_say_who_recorded_them_and_when(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Algebra help", next_step="Sit with Alex", owner="Grandma", recorded_by="Grandma"))
    page = c.get("/kids/Alex/plan").text
    assert "Recorded Tue 9/15 2:00 PM by Grandma" in page
    sid = _step_rows(tmp_path)[0]["id"]
    later = app_for(tmp_path, now=NOW + timedelta(days=1))
    edit = later.get(f"/kids/Alex/check-in/step?step_id={sid}").text
    assert 'name="recorded_by"' in edit and 'value="Grandma"' in edit
    _post_step(later, "Alex", _form(title="Algebra help", next_step="Sit with Alex Wed 7pm", owner="Grandma", recorded_by="Mom", revision="1"), step_id=sid)
    page = later.get("/kids/Alex/plan").text
    assert "Recorded Tue 9/15 2:00 PM by Grandma · edited Wed 9/16 2:00 PM by Mom" in page
    row = _step_rows(tmp_path)[0]
    assert row["recorded_by"] == "Mom" and row["created_by"] == "Grandma"


def test_the_plan_tells_the_agreed_steps_from_later_additions_and_edits(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", next_step="Ten words"))
    c.post("/kids/Alex/check-in/finish", data=_finish(recorded_by="Mom"), follow_redirects=False)
    page = c.get("/kids/Alex/plan").text
    assert "Agreed at the Tue 9/15 check-in" in page.split("Previous agreements")[0]
    later = app_for(tmp_path, now=NOW + timedelta(days=1))
    _post_step(later, "Alex", _form(title="Algebra help", next_step="Sit with Alex", owner="Grandma"))
    sid = next(s["id"] for s in _step_rows(tmp_path) if s["title"] == "Vocabulary")
    _post_step(later, "Alex", _form(title="Vocabulary", next_step="Twenty words", revision="1"), step_id=sid)
    cards = later.get("/kids/Alex/plan").text.split("Previous agreements")[0].split('<article class="card plan-card">')[1:]
    vocab = next(x for x in cards if "Vocabulary" in x)
    algebra = next(x for x in cards if "Algebra help" in x)
    assert "Edited since the Tue 9/15 check-in" in vocab
    assert "Added since the Tue 9/15 check-in" in algebra
    history = later.get("/kids/Alex/plan").text.split("Previous agreements")[1]
    assert "Recorded by Mom" in history and "Vocabulary · Alex: Ten words" in history


def test_a_conflict_shows_what_was_saved_meanwhile(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Lab notebook", next_step="Ask Mr. Hoch"))
    sid = _step_rows(tmp_path)[0]["id"]
    _post_step(c, "Alex", _form(title="Lab notebook", next_step="Mr. Hoch has it, grade next week", state="done", revision="1"), step_id=sid)
    r = _post_step(c, "Alex", _form(title="Lab notebook", next_step="Grandma saw it", family_account="Showed me Wed", revision="1"), step_id=sid)
    assert r.status_code == 409
    assert "Saved meanwhile" in r.text and "Mr. Hoch has it, grade next week" in r.text and "Step complete" in r.text
    assert "Showed me Wed" in r.text and 'name="revision" value="2"' in r.text       # mine kept, and one more Save applies it
    assert _step_rows(tmp_path)[0]["next_step"] == "Mr. Hoch has it, grade next week"


def test_today_shows_each_childs_next_check_in_and_todays_load(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", minutes="15", planned_for="2026-09-15"))
    _post_step(c, "Alex", _form(title="Worksheet 3", minutes="10", planned_for="2026-09-15"))
    _post_step(c, "Alex", _form(title="Reading log", planned_for="2026-09-16"))
    c.post("/kids/Alex/check-in/finish", data=_finish(next_check="2026-09-17"), follow_redirects=False)
    c.post("/kids/Sam/check-in/finish", data=_finish(next_check="2026-09-14"), follow_redirects=False)
    body = c.get("/").text
    alex, sam = body.split('<h2><a href="/kids/Sam/check-in">')
    assert "Next check-in Thu 9/17" in alex and "2 steps planned today · 25 min" in alex
    assert "Check-in due (planned for Mon 9/14)" in sam and "No steps planned today" in sam


def test_a_child_with_no_check_in_yet_is_invited_on_today(tmp_path):
    seed(tmp_path).close()
    assert "No check-in yet" in app_for(tmp_path).get("/").text


def test_completed_steps_keep_their_account_and_review_cards_count_earlier_steps(tmp_path):
    conn = seed(tmp_path)
    lid = _item_id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Lab notebook", next_step="Ask Mr. Hoch", family_account="Mr. Hoch emailed: he has it.", state="done"), item_id=lid)
    page = c.get("/kids/Alex/check-in").text
    completed = page.split("Completed steps")[1]
    assert "Mr. Hoch emailed: he has it." in completed
    card = _queues(page)["Waiting on the school"]
    lab = card.split('<article class="card review-card"')
    lab = next(x for x in lab if "Lab notebook" in x)
    assert "1 completed step" in lab and "Mr. Hoch emailed: he has it." in lab


def test_the_manual_task_form_says_what_it_is_for(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in/step").text
    assert "<h2>Add a task</h2>" in body and "not on the school list" in body


def test_the_print_view_carries_the_markers_a_reader_needs(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", next_step="Ten words", planned_for="2026-09-14", family_account="Private"))
    _post_step(c, "Alex", _form(state="waiting"), item_id=qid)
    fixed = snapshot()
    for a in fixed["students"]["Alex"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"] = False
    _refresh(tmp_path, fixed, NOW + timedelta(days=1))
    body = app_for(tmp_path, now=NOW + timedelta(days=1)).get("/kids/Alex/plan/print").text
    assert "Planned for Mon 9/14 · revisit this date" in body
    assert "school record changed since this step was saved" in body
    assert "Private" not in body and "Each step’s family account stays on screen" in body


def test_hac_scores_print_with_their_denominator(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    conn.close()
    body = app_for(tmp_path).get(f"/kids/Alex/check-in/step?item_id={qid}").text     # Quiz 1 is settled, so not in review
    # The record's words are the detail card's (`_source_facts.html`, #129): "28 of 30", as the
    # verdict sentence says it, on both.
    assert "28 of 30" in body and "score 28.0" not in body and "28/30" not in body
    assert re.search(r"Canvas.*?nothing submitted · 0 of 10", app_for(tmp_path).get("/kids/Sam/check-in").text, re.S)


def test_a_step_added_by_mistake_can_be_removed_but_only_by_its_own_child(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Oops", next_step="Made by mistake"))
    _post_step(c, "Sam", _form(title="Cell diagram", next_step="Label the parts", owner="Sam"))
    alex_step, sam_step = (r["id"] for r in _step_rows(tmp_path))
    edit = c.get(f"/kids/Alex/check-in/step?step_id={alex_step}").text
    assert f'action="/kids/Alex/check-in/step/{alex_step}/delete"' in edit and "data-confirm" in edit
    assert c.post(f"/kids/Alex/check-in/step/{sam_step}/delete", follow_redirects=False).status_code == 404
    assert c.post(f"/kids/Alex/check-in/step/abc/delete", follow_redirects=False).status_code == 404
    r = c.post(f"/kids/Alex/check-in/step/{alex_step}/delete", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"
    assert [s["title"] for s in _step_rows(tmp_path)] == ["Cell diagram"]
    assert "Made by mistake" not in c.get("/kids/Alex/plan").text
    assert c.post(f"/kids/Alex/check-in/step/{alex_step}/delete", follow_redirects=False).status_code == 404   # already gone


def test_the_same_token_with_different_words_is_refused_rather_than_silently_dropped(tmp_path):
    """A replayed POST must not be able to claim a save it did not make.

    `ON CONFLICT(request_key) DO NOTHING` is right for a double-click, where the words are
    identical. It is wrong for Back, edit, Save: the token is the same, the plan is not, the
    insert is dropped, and the page would answer "Saved." while the first version stood. On a
    kitchen kiosk that is a family reading a commitment nobody agreed to.
    """
    seed(tmp_path).close()
    c = app_for(tmp_path)
    token = str(uuid4())
    first = _post_step(c, "Alex", _form(request_key=token, next_step="Ask Mr. Hoch to clear the flag"))
    assert first.status_code == 303

    changed = _post_step(c, "Alex", _form(request_key=token, next_step="Email Mr. Hoch instead"))
    assert changed.status_code == 409, "a changed replay must not report success"
    assert "already saved" in changed.text

    rows = _step_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["next_step"] == "Ask Mr. Hoch to clear the flag"


def test_an_identical_replay_is_still_one_step(tmp_path):
    """The behaviour the token exists for: a double-click or a retry saves once and says so."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    form = _form(request_key=str(uuid4()))
    assert _post_step(c, "Alex", form).status_code == 303
    assert _post_step(c, "Alex", dict(form)).status_code == 303
    assert len(_step_rows(tmp_path)) == 1


def test_a_budget_agreed_on_an_earlier_day_does_not_warn_about_today(tmp_path):
    """#21: "Time available today" was agreed for that day. Measured against a later day's
    plan it told a child "80 min over" a budget nobody agreed to tonight."""
    seed(tmp_path).close()
    app_for(tmp_path, now=NOW - timedelta(days=1)).post(
        "/kids/Sam/check-in/finish", data=_finish(available_minutes="10", next_check="2026-09-16"), follow_redirects=False)
    c = app_for(tmp_path)
    _post_step(c, "Sam", _form(title="Label the parts", owner="Sam", minutes="90", planned_for="2026-09-15"))
    for page in (c.get("/kids/Sam/plan").text, c.get("/kids/Sam/plan/print").text):
        assert "min over" not in page
        assert "Last agreed time budget: 10 min" in page and "Mon 9/14" in page


def test_planning_evidence_rounds_scores_with_the_shared_helper(tmp_path):
    """#21: the evidence card had its own rounding macro; it now uses `stores.num`, the rule the
    work list and Changes use, through a `num` filter. The source lines moved into the shared
    `_source_facts.html` (#129); neither template rounds on its own."""
    from pathlib import Path
    from fridgesheet.web import app as webapp
    templates = Path(webapp.__file__).parent / "templates"
    assert "round(" not in (templates / "_planning_evidence.html").read_text(encoding="utf-8")
    src = (templates / "_source_facts.html").read_text(encoding="utf-8")
    assert "round(" not in src and "| num" in src
    seed(tmp_path).close()
    env = app_for(tmp_path).app.state.fridgesheet.extra["env"]
    assert env.from_string("{{ 12.5033 | num }}/{{ 30.0 | num }}").render() == "12.5/30"


# --- kids' UX audit F6: the step form asks three things first ---------------------------------------

def test_the_step_form_asks_three_things_first_and_folds_the_rest(tmp_path):
    """Nine fields to write down one step, including a required "Order within this day". Title,
    next step and day come first; State, Minutes, Order and Recorded-by fold under one "More",
    the same at every tier -- every field is still on the form."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in/step").text
    fold = body.index('<details class="step-more"')
    for name in ("title", "next_step", "planned_for"):
        assert body.index(f'name="{name}"') < fold, f"{name} should be above the fold"
    for name in ("state", "minutes", "position", "recorded_by"):
        assert body.index(f'name="{name}"') > fold, f"{name} should be under More"
    assert re.search(r'<details class="step-more"[^>]*>\s*<summary>More', body)


def test_order_is_optional_and_a_blank_one_goes_last(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert _post_step(c, "Alex", _form(position="", planned_for="2026-09-16")).status_code == 303
    assert _post_step(c, "Alex", _form(title="Vocabulary", position="", planned_for="2026-09-16")).status_code == 303
    assert _post_step(c, "Alex", _form(title="Reading log", position="", planned_for="2026-09-17")).status_code == 303
    rows = {(r["title"], r["planned_for"]): r["position"] for r in _step_rows(tmp_path)}
    assert rows[("Quiz 1", "2026-09-16")] < rows[("Vocabulary", "2026-09-16")]      # second that day sorts after the first
    assert rows[("Reading log", "2026-09-17")] == rows[("Quiz 1", "2026-09-16")]     # a new day starts over

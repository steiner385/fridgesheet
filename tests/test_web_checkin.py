"""The check-in workspace: review queues, saved next steps, agreements, printing and isolation.

Three layers stay independent throughout: the school record (observations and flags), the
family's account of what happened, and the commitment they agreed on. A test that touches
one asserts the other two are untouched.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from fridgesheet.web import db, ingest
from fridgesheet.web.stores import flags, plans
from tests.web_fixtures import NOW, TZ, _a, _h, app_for, seed, snapshot


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
    """The review groups' HTML, by label, so a test can say which group a row is in."""
    groups = re.split(r'<details class="sec queue-group', body)[1:]
    out = {}
    for g in groups:
        label = re.search(r"<summary><h3>(.*?)</h3>", g)
        if label and label.group(1) in ("Other open work", "Worth checking", "Waiting on the school"):
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
    assert set(q) == {"Other open work", "Worth checking", "Waiting on the school"}
    assert "Homework 4" in q["Other open work"]                     # past its window: open, not fixable
    for name in ("Vocabulary", "Worksheet 3", "Reading log", "Lab notebook", "Participation"):
        assert name not in q["Other open work"], name               # these are in Must finish now
    assert "Essay draft" in q["Waiting on the school"]
    assert "Quiz 1" not in r.text.split('id="plan"')[0]             # HAC's 28/30 settles it (docs/outcomes.md)


def _section(body: str, key: str) -> str:
    """The HTML of one Must-finish section, by its data-section key."""
    m = re.search(rf'<div class="mf-section" data-section="{key}">(.*?)</div><!-- /{key} -->', body, re.S)
    return m.group(1) if m else ""


def test_must_finish_opens_the_plan_with_the_school_list_in_sections(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    assert body.index('id="must-finish"') < body.index('id="plan"')
    assert "Vocabulary" in _section(body, "tonight") and "DUE TODAY" in _section(body, "tonight")
    assert "Worksheet 3" in _section(body, "tomorrow")
    assert "Reading log" in _section(body, "later")
    paper = _section(body, "paper")
    assert "Lab notebook" in paper and "Participation" in paper
    assert "The school&#39;s list as of" in body      # apostrophe escaped: `say` returns plain text, autoescaped


def test_a_must_finish_row_never_offers_too_late_or_let_it_go(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    body = c.get("/kids/Sam/plan").text
    overdue = _section(body, "overdue")
    assert "Cell diagram" in overdue and "Safety quiz" in overdue
    assert 'value="too_late"' not in overdue and 'value="ignore"' not in overdue
    assert 'value="done"' in overdue and 'value="plan:today"' in overdue
    # The verdict table itself still carries them: the row filtered, the answers did not change.
    from fridgesheet.web import verdicts as V
    assert any(a.action == "too_late" for a in V.ANSWERS["not_done"])


def test_a_paper_row_puts_handed_in_first(tmp_path):
    seed(tmp_path).close()
    paper = _section(app_for(tmp_path).get("/kids/Alex/plan").text, "paper")
    lab = paper[paper.index("Lab notebook"):]
    assert lab.index('value="done"') < lab.index('value="ask_teacher"')
    assert re.search(r'<button name="answer" value="done" class="primary"', lab)


def test_a_zero_on_handed_in_work_keeps_ask_the_teacher_first(tmp_path):
    """Review Focus 2: finishing first must not mean tapping away a wrong zero."""
    snap = snapshot()
    sci = snap["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci["assignments"]:
        if a["name"] == "Safety quiz":
            a.update(state="submitted", submitted_at="2026-09-10T20:00:00-04:00", score=None, grade=None)
    snap["students"]["Sam"]["hac"]["classes"][0]["assignments"] = [_h("Safety quiz", "09/11/2026", 0.0)]
    conn = seed(tmp_path, snap)
    qid = _item_id(conn, "Safety quiz")
    conn.close()
    overdue = _section(app_for(tmp_path).get("/kids/Sam/plan").text, "overdue")
    # Scoped to this row alone: Safety quiz sorts before Cell diagram in "overdue" (its due
    # date is earlier), and Cell diagram's own row legitimately has a primary "done" button --
    # slicing to end-of-section would fail this row's checks on that account.
    quiz = re.search(rf'<div class="item[^"]*" id="mf-{qid}".*?(?=<div class="item[ "]|</div><!-- /overdue -->)',
                     overdue, re.S).group(0)
    assert "Zero to check" in quiz
    assert re.search(r'<button name="answer" value="ask_teacher" class="primary"', quiz)
    assert 'value="ignore"' not in quiz and 'value="done" class="primary"' not in quiz


def test_a_must_finish_item_is_in_no_review_group(tmp_path):
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    q = _queues(body)
    for name in ("Lab notebook", "Participation"):                  # paper with no grade used to be a question or waiting
        assert name in _section(body, "paper")
        assert all(name not in g for g in q.values()), name


def test_the_must_finish_ids_are_open_works_rows_minus_the_plan(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Vocabulary", planned_for="2026-09-15"), item_id=vid)
    body = c.get("/kids/Alex/plan").text
    ids = set(re.findall(r'id="mf-(\d+)"', body))
    assert str(vid) not in ids and len(ids) == 4                    # Worksheet 3, Reading log, Lab notebook, Participation


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
    """Homework 4 is a month old and past its 14-day window; sorting by due date alone (or not
    at all) would not put it after work that is still open and not yet past its window. The
    queue keeps it visible but after that work -- undated, unfinished Reading project among it
    (`checkin._context`'s `rows.sort(key=lambda v: bool(v.open_in) and not v.actionable)`)."""
    snap = snapshot()
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"].append(_h("Reading project", "", None))
    seed(tmp_path, snap).close()
    other = _queues(app_for(tmp_path).get("/kids/Alex/check-in").text)["Other open work"]
    assert other.index("Reading project") < other.index("Homework 4")


def test_undated_work_is_reviewable_with_its_missing_date_named(tmp_path):
    """Task 6 (spec 2026-09-28 §4.3): the queue card is the item surface now, and its Record
    (`_record.html`) states only the sources, the pace and the teacher -- the old "no due date
    listed" line was `_planning_evidence.html`'s own summary sentence, gone with it. Undated work
    still sorts into "Other open work" and is still reviewable there; nothing states its date
    because it has none."""
    snap = snapshot()
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"].append(_h("Reading project", "", None))
    seed(tmp_path, snap).close()
    q = _queues(app_for(tmp_path).get("/kids/Alex/check-in").text)
    assert "Reading project" in q["Other open work"]


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
    # Quiz 1 is done_offline from the seed fixture itself (HAC's 28/30 beats Canvas's automatic
    # missing flag), so the step the family just saved is shown as "The school has it" (spec
    # 2026-09-27 §6) -- that card still carries the family account, same as a plain plan card.
    assert "Ask Mr. Hoch to clear the missing flag" in page and "Took it in class Friday" in page
    assert "The school has it" in page
    assert "Quiz 1" not in _queues(page)["Worth checking"]      # covered by an active step
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
    assert f'href="/kids/Alex/check-in/step?item_id={eid}&amp;state=waiting&amp;return_to=' in page
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
    assert "Tonight: 1 step, 20 min" in c.get("/kids/Sam/plan").text
    r = _post_step(c, "Sam", _form(title="Cell diagram", next_step="Label the 6 parts", owner="Sam", minutes="20", planned_for="2026-09-15", state="done"), step_id=sid)
    assert r.status_code == 303
    page = c.get("/kids/Sam/check-in").text
    assert "Cell diagram" in _section(page, "overdue")                # back in Must finish: still not handed in
    assert "Tonight: 0 steps, 0 min" in page
    assert "The school decides what counts as submitted." in page
    assert f'href="/kids/Sam/check-in/step?item_id={cid}&amp;return_to=' in page  # a second step for the same work
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
    # Quiz 1 is done_offline (HAC's 28/30 beats Canvas's automatic missing flag), so the step
    # shows as "The school has it" (spec 2026-09-27 §6) -- but that card still carries the
    # family's account and the step's own "Check again" wording, the same as a plain card.
    assert "The school has it" in page and "check again Thu 9/17" in page
    assert "Took it in class; HAC shows 28/30." in page
    conn = db.open_db(tmp_path)
    obs = db.latest_observations(conn, conn.execute("SELECT id FROM students WHERE key='Alex'").fetchone()[0])[qid]
    assert obs["canvas"]["missing"] == 1 and obs["hac"]["score"] == 28.0       # the school's facts, as the school said them
    assert flags.active(conn, qid)["flag"] == "follow_up"                       # the old flag path is untouched
    assert conn.execute("SELECT COUNT(*) FROM refreshes").fetchone()[0] == 2
    conn.close()
    # A witnessed step is still greyed, not silenced: a later refresh that actually changes
    # Canvas's mark must still tell the family -- the worst case is a witnessed step whose
    # school evidence moved and nobody is told.
    moved = snapshot()
    for a in moved["students"]["Alex"]["canvas"]["courses"][0]["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"] = False
    day3 = NOW + timedelta(days=2)
    _refresh(tmp_path, moved, day3)
    page = app_for(tmp_path, now=day3).get("/kids/Alex/plan").text
    assert "The school has it" in page                                          # still done_offline: still witnessed
    assert "School evidence changed since this step was saved" in page


def test_evidence_change_notice_follows_facts_not_refresh_ids(tmp_path):
    # Quiz 1 is done_offline from the seed fixture itself (HAC's 28/30 beats Canvas's automatic
    # missing flag), so any step on it is shown as "The school has it" (spec 2026-09-27 §6),
    # which never carries this notice -- Homework 4 (past its window, still open, no HAC row)
    # stands in for the item whose Canvas record changes but stays a plain plan card.
    conn = seed(tmp_path)
    hid, lid = _item_id(conn, "Homework 4"), _item_id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Homework 4", state="waiting"), item_id=hid)
    _post_step(c, "Alex", _form(title="Lab notebook", state="waiting", family_account="On paper Tuesday"), item_id=lid)
    day2 = NOW + timedelta(days=1)
    _refresh(tmp_path, snapshot(), day2)
    assert "School evidence changed" not in app_for(tmp_path, now=day2).get("/kids/Alex/plan").text
    fixed = snapshot()
    for a in fixed["students"]["Alex"]["canvas"]["courses"][1]["assignments"]:
        if a["name"] == "Homework 4":
            a["missing"] = False
    day3 = NOW + timedelta(days=2)
    _refresh(tmp_path, fixed, day3)
    page = app_for(tmp_path, now=day3).get("/kids/Alex/plan").text
    cards = page.split('<div class="item step">')[1:]
    homework = next(x for x in cards if "Homework 4" in x)
    lab = next(x for x in cards if "Lab notebook" in x)
    assert "School evidence changed since this step was saved" in homework
    assert "School evidence changed" not in lab and "On paper Tuesday" in lab


def test_a_step_on_work_the_school_dropped_is_kept_and_labelled(tmp_path):
    """Task 6 (spec 2026-09-28 §4.3): the step's card is the item surface now, and its own head
    meta says "no longer on the school list" -- the old full-sentence `.muted` line was
    `_plan_panel.html`'s own paragraph, folded into the head."""
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
    assert "no longer on the school list" in page


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
    assert "Quiz 1" not in _queues(zoe)["Worth checking"]
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
    assert "Tonight: 2 steps, 25 min" in page                                    # waiting steps carry no minutes today
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
    # On a phone the queue runs screens before the plan: the check-in page's strip at the bottom
    # of the screen names both halves (#189); the plan page is one half and has none.
    checkin = c.get("/kids/Alex/check-in").text
    assert '<nav class="halves" aria-label="Check-in sections"><a href="#must-finish">Must finish ' in checkin
    assert 'href="#plan">Next steps ' in checkin
    assert 'class="halves"' not in c.get("/kids/Alex/plan").text
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


def test_only_worth_checking_opens_itself_and_only_when_something_there_needs_a_look(tmp_path):
    """Spec 2026-09-27 §7: a review group used to start open whenever it held a row; now only
    "Worth checking" pries itself open, and only when one of its rows is a kind that opens it
    by itself (`checkin.OPENS_WORTH_CHECKING`). Neither kid's fixture has one, so nothing before
    Must finish grabs the family's attention on its own."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert c.get("/kids/Alex/check-in").text.count('<details class="sec queue-group" open>') == 0
    assert c.get("/kids/Sam/check-in").text.count('<details class="sec queue-group" open>') == 0


def test_worth_checking_opens_itself_when_a_row_there_is_the_kind_that_does(tmp_path):
    """The positive case: a `checkin.OPENS_WORTH_CHECKING` kind (here `hac_lower` -- Canvas
    graded higher than HAC on the same item) opens "Worth checking" by itself, and only that
    group."""
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    for a in eng["assignments"]:
        if a["name"] == "Quiz 1":
            a.update(missing=False, state="graded", score=30.0, grade="30")
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"] = [_h("Quiz 1", "09/12/2026", 20.0, points=30.0)]
    seed(tmp_path, snap).close()
    body = app_for(tmp_path).get("/kids/Alex/check-in").text
    assert body.count('<details class="sec queue-group" open>') == 1
    assert '<details class="sec queue-group" open>\n    <summary><h3>Worth checking</h3>' in body
    assert '<details class="sec queue-group quiet" >\n    <summary><h3>Waiting on the school</h3>' in body
    assert '<details class="sec queue-group quiet" >\n    <summary><h3>Other open work</h3>' in body


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
    cards = later.get("/kids/Alex/plan").text.split("Previous agreements")[0].split('<div class="item step">')[1:]
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
    alex, sam = body.split('<h3><a href="/kids/Sam/check-in">')
    assert "Next check-in Thu 9/17" in alex and "2 steps planned today · 25 min" in alex
    assert "Check-in due (planned for Mon 9/14)" in sam and "No steps planned today" in sam


def test_a_child_with_no_check_in_yet_is_invited_on_today(tmp_path):
    seed(tmp_path).close()
    assert "No check-in yet" in app_for(tmp_path).get("/").text


def test_completed_steps_keep_their_account_and_review_cards_count_earlier_steps(tmp_path):
    # Lab notebook is Must finish's now (paper, no grade), never a review card again -- but its
    # row still carries the same "N completed steps · last account" line (spec 2026-09-27 §4).
    conn = seed(tmp_path)
    lid = _item_id(conn, "Lab notebook")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Lab notebook", next_step="Ask Mr. Hoch", family_account="Mr. Hoch emailed: he has it.", state="done"), item_id=lid)
    page = c.get("/kids/Alex/check-in").text
    completed = page.split("Completed steps")[1]
    assert "Mr. Hoch emailed: he has it." in completed
    row = re.search(r'<div class="item[^"]*" id="mf-%d".*?(?=<div class="item[ "]|</div><!-- /\w+ -->)' % lid,
                    page, re.S).group(0)
    assert "1 completed step" in row and "Mr. Hoch emailed: he has it." in row


def test_a_review_card_still_counts_earlier_steps_too(tmp_path):
    """The same line, on a row that stays a review card (Essay draft, "waiting on the school",
    is not fixable or upcoming and so is never Must finish's)."""
    conn = seed(tmp_path)
    eid = _item_id(conn, "Essay draft")
    conn.close()
    c = app_for(tmp_path)
    _post_step(c, "Alex", _form(title="Essay draft", next_step="Ask Mr. Hoch", family_account="Mr. Hoch emailed: he has it.", state="done"), item_id=eid)
    page = c.get("/kids/Alex/check-in").text
    card = _queues(page)["Waiting on the school"]
    essay = card.split('<div class="item')
    essay = next(x for x in essay if "Essay draft" in x)
    assert "1 completed step" in essay and "Mr. Hoch emailed: he has it." in essay


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


def test_the_record_rounds_scores_with_the_shared_helper(tmp_path):
    """#21: the evidence card had its own rounding macro; it now uses `stores.num`, the rule the
    work list and Changes use, through a `num` filter. The source lines moved into the shared
    `_source_facts.html` (#129); neither template rounds on its own. The evidence card itself is
    now `_record.html` (spec 2026-09-28 §4.3)."""
    from pathlib import Path
    from fridgesheet.web import app as webapp
    templates = Path(webapp.__file__).parent / "templates"
    assert "round(" not in (templates / "_record.html").read_text(encoding="utf-8")
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


# --- spec 2026-09-27: seen ids, one-tap complete, excluded steps -----------------------------

def test_finishing_records_which_must_finish_ids_the_list_held(tmp_path):
    conn = seed(tmp_path)
    plans.finish(conn, 1, now=NOW.isoformat(), next_check="2026-09-20", available_minutes=30, summary="x",
                 request_key=str(uuid4()), seen=[81, 80])
    last = plans.last_checkin(conn, 1)
    assert last["seen"] == "[80, 81]"
    plans.finish(conn, 1, now=NOW.isoformat(), next_check="2026-09-21", available_minutes=30, summary="y", request_key=str(uuid4()))
    assert plans.last_checkin(conn, 1)["seen"] == "[]"
    conn.close()


def test_complete_marks_a_step_done_with_the_revision_check(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    values = {k: v for k, v in _form(title="Vocabulary").items() if k in plans.FIELDS}
    values.update(minutes=None, position=10, evidence="{}", recorded_by="")
    sid = plans.save(conn, 1, values, now=NOW.isoformat(), request_key=str(uuid4()), item_id=vid)
    plans.complete(conn, 1, sid, now=NOW.isoformat(), revision=1, recorded_by="Dad")
    step = plans.one(conn, 1, sid)
    assert (step["state"], step["revision"], step["recorded_by"]) == ("done", 2, "Dad")
    with pytest.raises(plans.Conflict):
        plans.complete(conn, 1, sid, now=NOW.isoformat(), revision=1)        # stale revision
    with pytest.raises(plans.Conflict):
        plans.complete(conn, 2, sid, now=NOW.isoformat(), revision=2)        # another child's id
    conn.close()


def test_today_load_leaves_out_steps_the_school_has(tmp_path):
    conn = seed(tmp_path)
    vid = _item_id(conn, "Vocabulary")
    base = {k: v for k, v in _form(planned_for="2026-09-15").items() if k in plans.FIELDS}
    base.update(position=10, evidence="{}", recorded_by="")
    plans.save(conn, 1, {**base, "minutes": 20}, now=NOW.isoformat(), request_key=str(uuid4()), item_id=vid)
    plans.save(conn, 1, {**base, "title": "Other", "minutes": 10}, now=NOW.isoformat(), request_key=str(uuid4()))
    assert plans.today_load(conn, 1, "2026-09-15") == (2, 30)
    assert plans.today_load(conn, 1, "2026-09-15", exclude={vid}) == (1, 10)
    conn.close()


def _plan_step_for(c, conn, key, name, **over):
    iid = _item_id(conn, name)
    _post_step(c, key, _form(title=name, planned_for="2026-09-15", **over), item_id=iid)
    return iid


def test_a_step_the_school_shows_as_in_is_greyed_with_canvas_as_the_witness(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Essay draft", minutes="20")          # submitted 9/14 8 pm
    _plan_step_for(c, conn, "Alex", "Vocabulary", minutes="15")           # not handed in
    conn.close()
    body = c.get("/kids/Alex/plan").text
    panel = body[body.index('id="plan"'):]
    assert "The school has it" in panel
    assert "Canvas: handed in Mon 9/14 8:00 PM" in panel
    assert "Mark step complete" in panel
    assert "Tonight: 1 step, 15 min" in panel and "1 the school has, not counted" in panel
    assert "3 must-finish not picked yet" in panel                         # Worksheet 3, Lab notebook, Participation; Vocabulary is covered


def test_a_hac_zero_keeps_a_step_off_the_school_has_it_list(tmp_path):
    """Review finding 2 (Review Focus 2): a HAC zero is not done whatever Canvas's submission
    says -- the school has not "got it", so a step on it must not grey out as though it had."""
    snap = snapshot()
    sci = snap["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci["assignments"]:
        if a["name"] == "Safety quiz":
            a.update(state="submitted", submitted_at="2026-09-10T20:00:00-04:00", score=None, grade=None)
    snap["students"]["Sam"]["hac"]["classes"][0]["assignments"] = [_h("Safety quiz", "09/11/2026", 0.0)]
    conn = seed(tmp_path, snap)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Sam", "Safety quiz", owner="Sam", minutes="10")
    conn.close()
    panel = c.get("/kids/Sam/plan").text.split('id="plan"')[1]
    assert "The school has it" not in panel
    assert "Canvas: handed in" not in panel
    assert "Tonight: 1 step, 10 min" in panel                              # the step counts; nothing greyed it out


def test_the_familys_own_done_answer_is_named_as_theirs(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    vid = _plan_step_for(c, conn, "Alex", "Vocabulary")
    flags.set_flag(conn, vid, "done", now="2026-09-15T13:00:00-04:00")
    conn.close()
    panel = c.get("/kids/Alex/plan").text.split('id="plan"')[1]
    assert "You answered It&#39;s handed in, Tue 9/15" in panel   # apostrophe escaped: say returns plain text, autoescaped
    assert "Canvas: handed in" not in panel and "school says" not in panel.lower()


def test_a_stale_answer_ungreys_the_step(tmp_path):
    """Review Focus 3: the school contradicted the family's `done`; the step is live again."""
    from tests.web_fixtures import history
    conn = history(tmp_path)                                                # Quiz 1: HAC 28/30 day 2, Canvas MISSING day 3
    c = app_for(tmp_path)
    qid = _plan_step_for(c, conn, "Alex", "Quiz 1", minutes="10")
    flags.set_flag(conn, qid, "done", now="2026-09-14T09:00:00-04:00")      # answered before day 3's mark
    conn.close()
    panel = c.get("/kids/Alex/plan").text.split('id="plan"')[1]
    assert "The school has it" not in panel
    assert "Tonight: 1 step, 10 min" in panel


def test_mark_step_complete_is_one_post_with_the_revision(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Essay draft")
    (step,) = _step_rows(tmp_path)
    conn.close()
    r = c.post(f"/kids/Alex/check-in/step/{step['id']}/complete", data={"revision": "1", "recorded_by": "Mom"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/check-in?saved=1#plan"
    (step,) = _step_rows(tmp_path)
    assert (step["state"], step["revision"], step["recorded_by"]) == ("done", 2, "Mom")
    r = c.post(f"/kids/Alex/check-in/step/{step['id']}/complete", data={"revision": "1"})
    assert r.status_code == 409 and "changed in another window" in r.text


def test_a_covered_step_carries_the_sheets_word(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Worksheet 3")
    conn.close()
    panel = c.get("/kids/Alex/plan").text.split('id="plan"')[1]
    assert "Must finish · DUE TOMORROW" in panel


def test_asked_the_school_lines_sit_above_worth_checking(tmp_path):
    conn = seed(tmp_path)
    lab = _item_id(conn, "Lab notebook")
    flags.set_flag(conn, lab, "ask_teacher", now="2026-09-13T09:00:00-04:00")
    conn.close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    assert "Asked the school" in body and "Lab notebook</a>: Asked the teacher on Sun 9/13" in body
    assert body.index("Asked the school") < body.index("Worth checking")


def test_finishing_a_check_in_snapshots_the_must_finish_ids_and_rows_badge_against_it(tmp_path):
    conn = seed(tmp_path)
    vid, wid = _item_id(conn, "Vocabulary"), _item_id(conn, "Worksheet 3")
    conn.close()
    c = app_for(tmp_path)
    assert "'s list" not in c.get("/kids/Alex/plan").text                       # no check-in yet: no badge
    r = c.post("/kids/Alex/check-in/finish", data=_finish(), follow_redirects=False)
    assert r.status_code == 303
    conn = db.open_db(tmp_path)
    seen = json.loads(plans.last_checkin(conn, 1)["seen"])
    conn.close()
    assert vid in seen and wid in seen
    body = c.get("/kids/Alex/plan").text
    assert body.count("On Tue 9/15&#39;s list") == 5                               # Vocabulary, Worksheet 3, Reading log, Lab notebook, Participation (apostrophe escaped)
    assert "New since Tue 9/15" not in body


def test_a_row_that_appears_after_the_check_in_is_new_since(tmp_path):
    """Review Focus 4: an empty list at finish means nothing is "on the list" later."""
    snap = snapshot()
    snap["students"]["Kim"] = {"name": "Kim Example", "canvas_id": 3, "hac_name": "Kim Example",
                               "canvas": {"courses": []}, "hac": {"week_view": [], "classes": []}}
    conn = seed(tmp_path, snap)
    conn.close()
    c = app_for(tmp_path)
    c.post("/kids/Kim/check-in/finish", data=_finish(), follow_redirects=False)
    conn = db.open_db(tmp_path)
    kim = conn.execute("SELECT id FROM students WHERE key = 'Kim'").fetchone()["id"]
    assert plans.last_checkin(conn, kim)["seen"] == "[]"
    conn.close()
    later = snapshot()
    later["students"]["Kim"] = {"name": "Kim Example", "canvas_id": 3, "hac_name": "Kim Example",
                                "canvas": {"courses": [{"id": 9, "name": "Art 6 S1-2027-Ng", "course_code": "ART6",
                                    "grade": {"current_score": None, "final_score": None, "current_grade": None, "hidden": False},
                                    "staff": [], "assignments": [_a(300, "Sketchbook", "09-16")]}]},
                                "hac": {"week_view": [], "classes": []}}
    conn = db.open_db(tmp_path)
    ingest.record(conn, later, tz=TZ, now=NOW + timedelta(hours=1))
    conn.close()
    body = c.get("/kids/Kim/plan").text
    assert "Sketchbook" in body and "New since Tue 9/15" in body and "'s list" not in body


def test_the_printed_plan_leads_with_must_finish_as_boxes_and_names_people(tmp_path):
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Essay draft", recorded_by="Mom")
    conn.close()
    c.post("/kids/Alex/check-in/finish", data=_finish(recorded_by="Dad"), follow_redirects=False)
    body = c.get("/kids/Alex/plan/print").text
    assert body.index("Must finish") < body.index("Our next steps")
    assert "□ Vocabulary" in body and "□ Worksheet 3" in body
    assert "□ Lab notebook" not in body and "Reading log" not in body                # paper and later stay off paper
    assert "The school&#39;s list as of Tue 9/15" in body and "It changes daily" in body
    assert "On Tue 9/15&#39;s list" in body
    assert "Recorded by Dad" in body and "by Mom" in body
    assert "The school has it" in body and "Canvas: handed in" in body and "□ Essay draft" not in body
    assert "Worth checking" not in body


def test_a_covered_red_step_still_shows_as_due_on_the_printed_plan(tmp_path):
    """Review finding 1: a step on Vocabulary covers it in Must finish's own list, but it is
    still not done -- the printed plan must not say "Nothing due by tomorrow", and the step
    itself must still carry the Must finish badge."""
    conn = seed(tmp_path)
    c = app_for(tmp_path)
    _plan_step_for(c, conn, "Alex", "Vocabulary", minutes="15")
    conn.close()
    body = c.get("/kids/Alex/plan/print").text
    assert "Nothing due by tomorrow" not in body
    assert "Must finish · DUE TODAY" in body


def test_the_plan_page_offers_check_canvas_again_only_with_a_worker(tmp_path):
    from fastapi.testclient import TestClient
    from fridgesheet import config
    from fridgesheet.web import app as webapp, jobs
    from tests.web_fixtures import LOCAL_HOST_HEADERS
    seed(tmp_path).close()
    without = app_for(tmp_path).get("/kids/Alex/plan").text
    assert "Check Canvas again" not in without
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    application.state.fridgesheet.jobs = jobs.Worker(application.state.fridgesheet, actions=None)
    with_worker = TestClient(application, headers=LOCAL_HOST_HEADERS).get("/kids/Alex/plan").text
    assert "Check Canvas again" in with_worker and 'hx-post="/jobs/refresh"' in with_worker and '"reload_page": "1"' in with_worker


def test_a_running_non_refresh_job_does_not_appear_under_must_finish(tmp_path):
    """Review finding 5: a doctor (or any non-refresh) job in progress is not this button's own
    progress card, and it would never reload the page when it finished, so it must not show."""
    from fastapi.testclient import TestClient
    from fridgesheet import config
    from fridgesheet.web import app as webapp, jobs
    from tests.web_fixtures import LOCAL_HOST_HEADERS
    seed(tmp_path).close()
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    w = jobs.Worker(application.state.fridgesheet, actions=None)
    application.state.fridgesheet.jobs = w
    job = w.submit("doctor")
    assert job is not None and not job.done                        # queued, never run: still "current"
    body = TestClient(application, headers=LOCAL_HOST_HEADERS).get("/kids/Alex/plan").text
    section = body[body.index('id="must-finish"'):body.index('id="plan"')]
    assert '<div id="job"></div>' in section
    assert "Running diagnostics" not in section and "data-sse" not in section


def test_a_running_refresh_job_still_shows_and_still_reloads_the_plan(tmp_path):
    """The refresh button's own progress card is unaffected by finding 5's fix."""
    from fastapi.testclient import TestClient
    from fridgesheet import config
    from fridgesheet.web import app as webapp, jobs
    from tests.web_fixtures import LOCAL_HOST_HEADERS
    seed(tmp_path).close()
    application = webapp.create_app(config.Settings(home=tmp_path), worker=False)
    w = jobs.Worker(application.state.fridgesheet, actions=None)
    application.state.fridgesheet.jobs = w
    job = w.submit("refresh")
    assert job is not None and not job.done
    body = TestClient(application, headers=LOCAL_HOST_HEADERS).get("/kids/Alex/plan").text
    assert 'data-reload-page="1"' in body

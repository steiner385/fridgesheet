"""Reset (2026-10-04): a triage tap made the wrong way is taken back in one tap, and a kid's
whole plan can be sent back to Needs you now. A reset deletes the open steps and clears the
family's answers on the work it covers, and keeps a copy of both so its one Undo puts them back
exactly as they were. Completed steps and check-in agreements are history and stay."""
from __future__ import annotations

import re
from uuid import uuid4

from fridgesheet.web import db
from fridgesheet.web.stores import flags, plans, resets
from tests.web_fixtures import NOW, app_for, seed

STAMP = NOW.isoformat()
BASE = dict(family_account="", next_step="Work on it", owner="Alex", minutes=None, state="planned",
            position=10, evidence="{}", recorded_by="")


def _id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def _kid(conn, key):
    return conn.execute("SELECT id FROM students WHERE key = ?", (key,)).fetchone()["id"]


def _step(conn, kid, item_id, title, day="2026-09-16", **kw):
    return plans.save(conn, kid, {**BASE, "title": title, "planned_for": day, **kw}, now=STAMP,
                      request_key=str(uuid4()), item_id=item_id)


def _open_steps(conn, item_id):
    return [dict(r) for r in conn.execute("SELECT * FROM plan_steps WHERE item_id = ? AND state != 'done'", (item_id,))]


def _needs_now(body: str) -> list[int]:
    start = body.index('id="needs-now"')
    section = body[start:body.index("</section>", start)]
    return [int(i) for i in re.findall(r'<div class="item[^"]*" id="nn-(\d+)"', section)]


# --- the store -----------------------------------------------------------------------------

def test_a_reset_clears_the_answer_and_the_open_step_and_keeps_completed_steps(tmp_path):
    conn = seed(tmp_path)
    alex, vocab = _kid(conn, "Alex"), _id(conn, "Vocabulary")
    flags.set_flag(conn, vocab, "ask_teacher", now="2026-09-14T09:00:00-04:00", text="emailed Ms. K")
    done = _step(conn, alex, vocab, "Vocabulary", day="2026-09-14")
    plans.complete(conn, alex, done, now=STAMP, revision=1)
    _step(conn, alex, vocab, "Vocabulary")
    reset_id = resets.reset_items(conn, alex, [vocab], now=STAMP)
    assert reset_id is not None
    assert flags.active(conn, vocab) is None and _open_steps(conn, vocab) == []
    assert plans.one(conn, alex, done)["state"] == "done"


def test_undo_puts_the_step_and_the_answer_back_as_they_were(tmp_path):
    conn = seed(tmp_path)
    alex, vocab = _kid(conn, "Alex"), _id(conn, "Vocabulary")
    flags.set_flag(conn, vocab, "ask_teacher", now="2026-09-14T09:00:00-04:00", text="emailed Ms. K")
    step = plans.one(conn, alex, _step(conn, alex, vocab, "Vocabulary", minutes=20))
    reset_id = resets.reset_items(conn, alex, [vocab], now=STAMP)
    assert resets.undo(conn, alex, reset_id, now=STAMP) is True
    row = flags.active(conn, vocab)
    assert (row["flag"], row["set_at"], row["text"]) == ("ask_teacher", "2026-09-14T09:00:00-04:00", "emailed Ms. K")
    assert plans.one(conn, alex, step["id"]) == step


def test_undo_leaves_an_item_the_family_answered_since(tmp_path):
    conn = seed(tmp_path)
    alex, vocab = _kid(conn, "Alex"), _id(conn, "Vocabulary")
    _step(conn, alex, vocab, "Vocabulary")
    reset_id = resets.reset_items(conn, alex, [vocab], now=STAMP)
    flags.set_flag(conn, vocab, "done", now=STAMP)
    assert resets.undo(conn, alex, reset_id, now=STAMP) is True
    assert flags.active(conn, vocab)["flag"] == "done" and _open_steps(conn, vocab) == []


def test_an_undo_happens_once_and_only_for_its_own_kid(tmp_path):
    conn = seed(tmp_path)
    alex, sam, vocab = _kid(conn, "Alex"), _kid(conn, "Sam"), _id(conn, "Vocabulary")
    _step(conn, alex, vocab, "Vocabulary")
    reset_id = resets.reset_items(conn, alex, [vocab], now=STAMP)
    assert resets.undo(conn, sam, reset_id, now=STAMP) is False
    assert resets.undo(conn, alex, reset_id, now=STAMP) is True
    assert resets.undo(conn, alex, reset_id, now=STAMP) is False
    assert len(_open_steps(conn, vocab)) == 1


def test_nothing_to_reset_records_nothing(tmp_path):
    conn = seed(tmp_path)
    assert resets.reset_items(conn, _kid(conn, "Alex"), [_id(conn, "Vocabulary")], now=STAMP) is None
    assert conn.execute("SELECT COUNT(*) FROM plan_resets").fetchone()[0] == 0


# --- one assignment ------------------------------------------------------------------------

def test_reset_on_a_planned_row_puts_it_back_on_needs_you_now_with_an_undo(tmp_path):
    conn = seed(tmp_path)
    alex, worksheet = _kid(conn, "Alex"), _id(conn, "Worksheet 3")
    _step(conn, alex, worksheet, "Worksheet 3")                 # tomorrow: in hand, off the triage
    conn.close()
    client = app_for(tmp_path)
    body = client.get("/kids/Alex").text
    assert worksheet not in _needs_now(body)
    assert f'action="/items/{worksheet}/reset"' in body
    r = client.post(f"/items/{worksheet}/reset", data={"return_to": "/kids/Alex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/kids/Alex?reset=")
    body = client.get(r.headers["location"]).text
    assert worksheet in _needs_now(body)
    reset_id = int(r.headers["location"].rsplit("=", 1)[1])
    assert "Worksheet 3 is back on Needs you now." in body and f'action="/resets/{reset_id}/undo"' in body
    r = client.post(f"/resets/{reset_id}/undo", data={"return_to": "/kids/Alex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex"
    assert worksheet not in _needs_now(client.get("/kids/Alex").text)


def test_an_answer_alone_is_reset_from_the_records_more_menu(tmp_path):
    conn = seed(tmp_path)
    participation = _id(conn, "Participation")
    flags.set_flag(conn, participation, "ask_teacher", now=STAMP)
    conn.close()
    client = app_for(tmp_path)
    assert participation not in _needs_now(client.get("/kids/Alex").text)
    assert f'action="/items/{participation}/reset"' in client.get(f"/items/{participation}").text
    r = client.post(f"/items/{participation}/reset", data={"return_to": "/kids/Alex"})
    assert participation in _needs_now(r.text)


def test_untriaged_work_offers_no_reset(tmp_path):
    conn = seed(tmp_path)
    vocab = _id(conn, "Vocabulary")
    conn.close()
    client = app_for(tmp_path)
    assert "/reset" not in client.get("/kids/Alex").text
    # A stale page's tap on work with nothing to take back goes home with no notice and no record.
    r = client.post(f"/items/{vocab}/reset", data={"return_to": "/kids/Alex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex"
    assert client.post("/items/99999/reset", data={"return_to": "/kids/Alex"}).status_code == 404


# --- a kid's whole plan --------------------------------------------------------------------

def test_reset_plan_sends_every_triaged_row_in_the_window_back_and_undo_restores_them(tmp_path):
    conn = seed(tmp_path)
    alex = _kid(conn, "Alex")
    vocab, worksheet, participation, essay = (_id(conn, n) for n in ("Vocabulary", "Worksheet 3", "Participation", "Essay draft"))
    _step(conn, alex, vocab, "Vocabulary")
    _step(conn, alex, worksheet, "Worksheet 3")
    flags.set_flag(conn, participation, "done", now=STAMP)
    flags.set_flag(conn, essay, "done", now=STAMP)              # handed in: not on the triage, left alone
    finished = _step(conn, alex, vocab, "Vocabulary", day="2026-09-14")
    plans.complete(conn, alex, finished, now=STAMP, revision=1)
    own = _step(conn, alex, None, "Practise scales")            # the family's own step, no school work
    conn.close()
    client = app_for(tmp_path)
    page = client.get("/kids/Alex/plan").text
    assert 'action="/kids/Alex/plan/reset"' in page and "Send 3 items back to Needs you now?" in page
    r = client.post("/kids/Alex/plan/reset", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/kids/Alex/plan?reset=")
    reset_id = int(r.headers["location"].rsplit("=", 1)[1])
    conn = db.connect(tmp_path / db.DB_NAME)
    assert _open_steps(conn, vocab) == _open_steps(conn, worksheet) == [] and flags.active(conn, participation) is None
    assert flags.active(conn, essay)["flag"] == "done"
    assert plans.one(conn, alex, finished)["state"] == "done" and plans.one(conn, alex, own) is not None
    conn.close()
    assert "3 items are back on Needs you now." in client.get(r.headers["location"]).text
    client.post(f"/resets/{reset_id}/undo", data={"return_to": "/kids/Alex/plan"})
    conn = db.connect(tmp_path / db.DB_NAME)
    assert len(_open_steps(conn, vocab)) == len(_open_steps(conn, worksheet)) == 1
    assert flags.active(conn, participation)["flag"] == "done"


def test_a_plan_with_nothing_triaged_offers_no_reset(tmp_path):
    seed(tmp_path).close()
    assert "/plan/reset" not in app_for(tmp_path).get("/kids/Alex/plan").text


def test_an_unknown_reset_is_a_404(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).post("/resets/999/undo", data={"return_to": "/kids/Alex"}).status_code == 404

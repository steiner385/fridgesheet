"""Letting a kid's past-credit work go in one step (was Reconcile's bulk ignore)."""
from __future__ import annotations

import re
from datetime import datetime

from fridgesheet.web import db
from fridgesheet.web.stores import flags, items, students
from tests.web_fixtures import TZ, app_for, seed, snapshot


def _flag(tmp_path, name):
    conn = db.open_db(tmp_path)
    row = flags.active(conn, conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"])
    conn.close()
    return row["flag"] if row else None


def test_letting_go_flags_only_that_kids_past_credit_work(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).post("/questions/let-go", data={"kid": "Alex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/questions?kid=Alex")
    assert _flag(tmp_path, "Homework 4") == "ignore"          # Alex's one past-credit item
    assert _flag(tmp_path, "Lab notebook") is None            # still inside its window
    assert _flag(tmp_path, "Cell diagram") is None            # Sam's work is never touched


def test_an_unknown_kid_is_refused(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).post("/questions/let-go", data={"kid": "Nobody"}).status_code == 404


def test_the_redirect_back_encodes_the_kid(tmp_path):
    """#150: the redirect was `f"/questions?kid={kid}"`, so a key with `&` or a space in it
    came back as a different (or broken) query."""
    snap = snapshot()
    snap["students"]["Al & Ex"] = snap["students"].pop("Alex")
    seed(tmp_path, snap).close()
    r = app_for(tmp_path).post("/questions/let-go", data={"kid": "Al & Ex"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/questions?kid=Al+%26+Ex")


LATER = datetime(2026, 9, 30, 14, 0, tzinfo=TZ)     # two of Alex's items are past their window by now


def _past_credit(tmp_path, kid="Alex"):
    conn = db.open_db(tmp_path)
    s = students.by_key(conn, kid)
    st = app_for(tmp_path, now=LATER).app.state.fridgesheet
    views = items.list_items(conn, s, now=LATER, rules=st.rules(), show="all", prefs=st.sources())
    conn.close()
    return [v for v in views if v.verdict.kind == "past_credit"]


def _bar(body):
    return re.search(r'<form class="lines bulk".*?</form>', body, re.S).group(0)


def test_the_bar_names_every_item_it_will_let_go_and_does_not_say_this_page(tmp_path):
    """#124: past-credit work is not on the Questions page, so the bar must say which it is."""
    seed(tmp_path).close()
    due = _past_credit(tmp_path)
    assert len(due) >= 2
    bar = _bar(app_for(tmp_path, now=LATER).get("/questions?kid=Alex").text)
    for v in due:
        assert v.name in bar, v.name
    confirm = re.search(r'data-confirm="([^"]*)"', bar).group(1)
    assert "this page" not in confirm
    assert all(v.name in confirm for v in due)


def _undo_form(page):
    form = re.search(r'<form[^>]*action="(/questions/let-go/undo)"[^>]*>(.*?)</form>', page, re.S)
    assert form, "the page after letting go offers one Undo"
    return form.group(1), dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form.group(2))), form.group(2)


def test_letting_go_can_be_undone_in_one_step_for_exactly_those_items(tmp_path):
    conn = seed(tmp_path)
    part = conn.execute("SELECT id FROM items WHERE name = 'Participation'").fetchone()["id"]
    flags.set_flag(conn, part, "done", now="2026-09-20T08:00:00-04:00", text="on paper")
    conn.close()
    due = _past_credit(tmp_path)
    c = app_for(tmp_path, now=LATER)
    page = c.post("/questions/let-go", data={"kid": "Alex"}).text
    assert all(_flag(tmp_path, v.name) == "ignore" for v in due)
    url, fields, said = _undo_form(page)
    assert all(v.name in said for v in due)                   # the page says which went
    r = c.post(url, data=fields, follow_redirects=False)
    assert r.status_code == 303
    assert all(_flag(tmp_path, v.name) is None for v in due)
    assert _flag(tmp_path, "Participation") == "done"         # an answer the bar never touched stays


def test_undo_leaves_an_item_answered_since_alone(tmp_path):
    """Only a let-go that is still in place is undone: an answer given after it is the family's."""
    seed(tmp_path).close()
    due = _past_credit(tmp_path)
    c = app_for(tmp_path, now=LATER)
    c.post("/questions/let-go", data={"kid": "Alex"})
    conn = db.open_db(tmp_path)
    flags.set_flag(conn, due[0].id, "done", now="2026-09-30T15:00:00-04:00")
    conn.close()
    ids = ",".join(str(v.id) for v in due)
    assert c.post("/questions/let-go/undo", data={"kid": "Alex", "ids": ids}, follow_redirects=False).status_code == 303
    assert _flag(tmp_path, due[0].name) == "done"
    assert all(_flag(tmp_path, v.name) is None for v in due[1:])


def test_undo_never_touches_another_kids_items(tmp_path):
    conn = seed(tmp_path)
    cell = conn.execute("SELECT id FROM items WHERE name = 'Cell diagram'").fetchone()["id"]
    flags.set_flag(conn, cell, "ignore", now="2026-09-20T08:00:00-04:00", text="past the late-work window")
    conn.close()
    c = app_for(tmp_path, now=LATER)
    c.post("/questions/let-go/undo", data={"kid": "Alex", "ids": str(cell)}, follow_redirects=False)
    assert _flag(tmp_path, "Cell diagram") == "ignore"

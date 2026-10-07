"""Assignments' one partition (spec 2026-10-06): every one of a kid's rows lands in exactly one
group, so the page's sections cannot disagree. Doug's page on 2026-10-06 showed due-tonight
work under This week that Needs you now left out; the groups below are the cure."""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fridgesheet.web import db
from fridgesheet.web.stores import flags, items, plans, students
from tests.web_fixtures import NOW, _a, _h, app_for, seed, snapshot


def _groups(tmp_path, key, now=NOW, snap=None, before=None):
    conn = seed(tmp_path, snap) if snap is not None or not (tmp_path / "fridgesheet.db").exists() else db.open_db(tmp_path)
    if before:
        before(conn)
    s = students.by_key(conn, key)
    st = app_for(tmp_path, now=now).app.state.fridgesheet
    views = items.list_items(conn, s, now=now, rules=st.rules(), show="all", prefs=st.sources(), **st.window())
    conn.close()
    return views, items.assignments(views, now.date())


def _names(rows):
    return [v.name for v in rows]


def _where(a: items.Assignments, name: str) -> list[str]:
    fields = ("overdue", "tonight", "tomorrow", "this_week", "later", "question", "waiting", "missed", "done")
    return [f for f in fields if name in _names(getattr(a, f))]


def test_every_row_lands_in_exactly_one_group(tmp_path):
    for key in ("Alex", "Sam"):
        views, a = _groups(tmp_path, key)
        placed = [v.id for g in a.groups.values() for v in g]
        assert sorted(placed) == sorted(v.id for v in views), key
        assert len(placed) == len(set(placed)), key


def test_alex_tonight_tomorrow_question_waiting_missed_done(tmp_path):
    _, a = _groups(tmp_path, "Alex")
    assert _names(a.tonight) == ["Vocabulary"]
    assert _names(a.tomorrow) == ["Worksheet 3"]
    assert _where(a, "Reading log") == ["this_week"]          # Sun 9/20, the week's last day
    assert _where(a, "Participation") == ["question"]
    assert _where(a, "Lab notebook") == ["waiting"]           # on paper, no grade yet
    assert _where(a, "Essay draft") == ["waiting"]            # handed in, the teacher is grading
    assert _where(a, "Homework 4") == ["missed"]              # 8/20: the late-work window has closed
    assert _where(a, "Quiz 1") == ["done"]                    # graded in HAC


def test_overdue_is_closest_to_losing_credit_first(tmp_path):
    _, a = _groups(tmp_path, "Sam")
    assert _names(a.overdue) == ["Safety quiz", "Cell diagram"]
    assert a.to_do == a.overdue + a.tonight + a.tomorrow + a.this_week + a.later


def test_a_step_never_takes_a_row_off_the_list(tmp_path):
    def step(conn):
        row = conn.execute("SELECT id, student_id FROM items WHERE name = 'Safety quiz'").fetchone()
        plans.save(conn, row["student_id"], dict(title="Safety quiz", planned_for="2026-09-16", family_account="",
                   next_step="Work on it", owner="Sam", minutes=None, state="planned", position=10, evidence="{}",
                   recorded_by=""), now=NOW.isoformat(), request_key=str(uuid4()), item_id=row["id"])
    seed(tmp_path).close()
    _, a = _groups(tmp_path, "Sam", before=step)
    assert _where(a, "Safety quiz") == ["overdue"]
    assert next(v for v in a.overdue if v.name == "Safety quiz").step is not None


def test_far_future_work_is_to_do_not_done(tmp_path):
    """Past the "coming due" window is still not due: it is on the list, under Later."""
    snap = snapshot()
    snap["students"]["Alex"]["canvas"]["courses"][0]["assignments"].append(_a(83, "Term paper", "11-20"))
    _, a = _groups(tmp_path, "Alex", snap=snap)
    assert _where(a, "Term paper") == ["later"]


def test_a_hac_only_row_not_yet_due_is_not_to_do(tmp_path):
    """HAC's dates are the app's invention (23:59), and its weekly participation rows are not
    work a child hands in: as everywhere else in the app, they are not coming due."""
    snap = snapshot()
    snap["students"]["Alex"]["hac"]["classes"][0]["assignments"].append(_h("Week 3", "09/18/2026", None))
    _, a = _groups(tmp_path, "Alex", snap=snap)
    assert "Week 3" not in _names(a.to_do)


def test_handled_upcoming_row_is_done(tmp_path):
    def done(conn):
        row = conn.execute("SELECT id FROM items WHERE name = 'Worksheet 3'").fetchone()
        flags.set_flag(conn, row["id"], "done", now=NOW.isoformat())
    seed(tmp_path).close()
    _, a = _groups(tmp_path, "Alex", before=done)
    assert _where(a, "Worksheet 3") == ["done"]


def test_a_to_do_row_that_asks_stays_in_to_do(tmp_path):
    """Overdue and asked about at once: listed once, in To do, where its row asks."""
    later = NOW + timedelta(days=1)
    views, a = _groups(tmp_path, "Alex", now=later)
    asking = [v for v in a.to_do if v.asks]
    for v in asking:
        assert v not in a.question
    assert not any(v.asks for v in a.waiting + a.missed + a.done)

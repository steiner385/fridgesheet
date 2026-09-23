"""Issue #42: when a flag was set is part of the record ("asked the teacher on Sat 9/12"),
and editing the flag's reason must not move that date."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet import dates
from fridgesheet.web.stores import flags
from tests.web_fixtures import app_for, seed

TZ = ZoneInfo("America/New_York")
ASKED = "2026-09-12T08:00:00-04:00"


def _item_id(conn, name):
    return conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]


def test_resetting_the_same_flag_keeps_its_date_and_updates_its_reason(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "ask_teacher", now=ASKED)
    flags.set_flag(conn, qid, "ask_teacher", now="2026-09-14T20:00:00-04:00", text="emailed Mr Hoch")
    active = flags.active(conn, qid)
    assert active["set_at"] == ASKED and active["text"] == "emailed Mr Hoch"
    assert len(flags.history(conn, qid)) == 1


def test_a_different_flag_starts_a_new_date(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "ask_teacher", now=ASKED)
    flags.set_flag(conn, qid, "done", now="2026-09-14T20:00:00-04:00")
    assert flags.active(conn, qid)["set_at"] == "2026-09-14T20:00:00-04:00"
    assert len(flags.history(conn, qid)) == 2


def test_the_detail_card_says_when_the_flag_was_set(tmp_path):
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "ask_teacher", now=ASKED)
    conn.close()
    body = app_for(tmp_path).get(f"/items/{qid}").text
    assert "set " + dates.wd_md_time(datetime.fromisoformat(ASKED).astimezone(TZ)) in body


def test_confirming_an_answer_restarts_its_date(tmp_path):
    """Spec 5.1: "Yes, still done" must stop the stale question returning on the next refresh."""
    conn = seed(tmp_path)
    qid = _item_id(conn, "Quiz 1")
    flags.set_flag(conn, qid, "done", now=ASKED, text="handed in on paper")
    assert flags.confirm(conn, qid, now="2026-09-16T08:00:00-04:00") is not None
    active = flags.active(conn, qid)
    assert (active["flag"], active["set_at"], active["text"]) == ("done", "2026-09-16T08:00:00-04:00", "handed in on paper")
    assert len(flags.history(conn, qid)) == 2


def test_confirming_with_no_flag_does_nothing(tmp_path):
    conn = seed(tmp_path)
    assert flags.confirm(conn, _item_id(conn, "Quiz 1"), now=ASKED) is None

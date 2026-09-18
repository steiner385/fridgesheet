"""Notes and flags: the parent's own knowledge next to the data."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fridgesheet import open_items
from fridgesheet.web import db, ingest
from fridgesheet.web.stores import flags, notes

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)
KEY = "hac:Honors Biology:lab safety contract"


@pytest.fixture
def conn(tmp_path):
    c = db.open_db(tmp_path)
    with c:
        c.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        c.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex S')")
        c.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Honors Biology S1', 'Honors Biology')")
        c.executemany("INSERT INTO items(id, student_id, course_id, key, name, first_seen, last_seen) VALUES (?, 1, 1, ?, ?, 1, 1)",
                      [(1, "canvas:1", "WS 1"), (2, "canvas:2", "WS 2")])
    return c


def test_notes_round_trip_and_student_view(conn):
    n1 = notes.add(conn, "item", 1, "emailed Mr. Nance", now="2026-09-14T10:00:00")
    n2 = notes.add(conn, "course", 1, "late work 50% for a week", now="2026-09-14T11:00:00")
    n3 = notes.add(conn, "student", 1, "check planner Fridays", now="2026-09-14T12:00:00")
    assert [r["body"] for r in notes.for_target(conn, "item", 1)] == ["emailed Mr. Nance"]
    notes.edit(conn, n1, "emailed Mr. Nance; he replied", now="2026-09-14T13:00:00")
    row = notes.for_target(conn, "item", 1)[0]
    assert row["body"].endswith("replied") and row["updated_at"] == "2026-09-14T13:00:00" and row["created_at"] == "2026-09-14T10:00:00"
    all_rows = notes.for_student(conn, 1)
    assert [(r["target_type"], r["target_name"]) for r in all_rows] == [("student", "Alex S"), ("course", "Honors Biology"), ("item", "WS 1")]
    notes.delete(conn, n2)
    assert len(notes.for_student(conn, 1)) == 2 and n3


def test_flags_one_active_replace_clear_and_history(conn):
    assert flags.active(conn, 1) is None
    flags.set_flag(conn, 1, "follow_up", now="2026-09-14T10:00:00", text="ask about retake")
    assert flags.active(conn, 1)["flag"] == "follow_up"
    flags.set_flag(conn, 1, "done", now="2026-09-15T10:00:00")          # replaces: old one gets cleared_at
    assert flags.active(conn, 1)["flag"] == "done"
    hist = flags.history(conn, 1)
    assert [(h["flag"], h["cleared_at"] is None) for h in hist] == [("done", True), ("follow_up", False)]
    assert flags.clear(conn, 1, now="2026-09-16T10:00:00") is True
    assert flags.active(conn, 1) is None and flags.clear(conn, 1, now="x") is False
    with pytest.raises(ValueError):
        flags.set_flag(conn, 1, "bogus", now="t")


def test_active_by_student_for_the_runner(conn):
    flags.set_flag(conn, 1, "done", now="t")
    flags.set_flag(conn, 2, "ask_teacher", now="t")
    assert flags.active_by_student(conn) == {"Alex": {"canvas:1": "done", "canvas:2": "ask_teacher"}}
    flags.clear(conn, 1, now="t2")
    assert flags.active_by_student(conn) == {"Alex": {"canvas:2": "ask_teacher"}}
    assert flags.HANDLED == ("done", "excused", "ignore")


def _hac_only_snapshot() -> dict:
    """Two kids in like-named classes, each with the same ungraded HAC-only row, so both
    carry the item key `hac:Honors Biology:lab safety contract`."""
    def kid(first: str) -> dict:
        return {"name": f"{first} Stein", "canvas": {"courses": []},
                "hac": {"week_view": [], "classes": [{
                    "code": "22001 - 3", "name": "Honors Biology - 3", "marking_period_avg": 88.0,
                    "last_updated": "9/14/2026", "categories": [],
                    "assignments": [{"due": "09/10/2026", "assigned": "09/08/2026", "name": "Lab Safety Contract",
                                     "category": "Labs", "score": None, "score_raw": "", "points": 5.0, "percent": ""}],
                }]}}
    return {"fetched_at": NOW.isoformat(), "fetched_at_epoch": NOW.timestamp(),
            "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
            "students": {"Alex": kid("Alex"), "Sam": kid("Sam")}}


def test_a_flag_on_a_hac_only_item_reaches_the_sheet_and_only_that_kids(tmp_path):
    """End to end for the case the sheet used to miss entirely: ingest a HAC-only row, flag
    it done, and the row leaves the open list for that kid -- and only that kid. The key the
    database stores and the key open_items looks up are one function now
    (`matching.hac_item_key`); they used to differ in whether the name was normalised."""
    conn = db.open_db(tmp_path)
    snap = _hac_only_snapshot()
    ingest.record(conn, snap, tz=TZ, now=NOW)
    rows = conn.execute("""SELECT i.id, i.key, s.key AS kid FROM items i JOIN students s ON s.id = i.student_id
                           ORDER BY s.key""").fetchall()
    assert [(r["kid"], r["key"]) for r in rows] == [("Alex", KEY), ("Sam", KEY)]
    flags.set_flag(conn, rows[0]["id"], "done", now=NOW.isoformat())

    by_student = flags.active_by_student(conn)
    assert by_student == {"Alex": {KEY: "done"}}
    al = open_items.open_items(snap["students"]["Alex"], "Al", NOW, flags=by_student.get("Alex", {}))
    assert [i.key for i in al.items] == [] and [i.key for i in al.handled] == [KEY]
    sam = open_items.open_items(snap["students"]["Sam"], "Sam", NOW, flags=by_student.get("Sam", {}))
    assert [i.key for i in sam.items] == [KEY] and sam.handled == []

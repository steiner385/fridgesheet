"""Canvas's "No Submission" work is "outside Canvas", not "in class".

Teachers pick "No Submission" for work done in the room, in another app (MakeMusic Cloud's
playing assignments, on prod 2026-10-04) or kept only in the gradebook, and Canvas does not say
which. "In class" was a guess that read wrong on every MakeMusic row.
"""
from __future__ import annotations

from types import SimpleNamespace

from fridgesheet import open_items
from fridgesheet.web import db


def test_no_submission_work_is_outside_canvas_and_on_paper_stays_paper():
    assert open_items.kind_of(["none"]) == "outside Canvas"
    assert open_items.kind_of([]) == open_items.kind_of(None) == "outside Canvas"
    assert open_items.kind_of(["on_paper"]) == "paper"
    assert open_items.kind_of(["online_upload"]) == "online"


def test_the_upgrade_renames_the_kind_already_stored(tmp_path):
    conn = db.open_db(tmp_path)
    with conn:
        conn.execute("INSERT INTO refreshes(id, started_at, sources, ok) VALUES (1, 't', '{}', 1)")
        conn.execute("INSERT INTO students(id, key, name) VALUES (1, 'Alex', 'Alex Example')")
        conn.execute("INSERT INTO courses(id, student_id, source, name, short_name) VALUES (1, 1, 'canvas', 'Concert Band', 'Concert Band')")
        conn.executemany("INSERT INTO items(id, student_id, course_id, key, name, kind, first_seen, last_seen) VALUES (?, 1, 1, ?, ?, ?, 1, 1)",
                         [(1, "canvas:1", "MakeMusic Cloud Assignment #5", "in class"), (2, "canvas:2", "Worksheet", "paper")])
        conn.execute("UPDATE schema_version SET version = 10")
    assert db.migrate(conn) == db.SCHEMA_VERSION
    assert dict(conn.execute("SELECT id, kind FROM items").fetchall()) == {1: "outside Canvas", 2: "paper"}


def test_a_sheet_printed_before_the_rename_does_not_mark_the_row_changed():
    item = SimpleNamespace(key="canvas:1", status="OUTSIDE CANVAS — CHECK")
    diff = open_items.compare([{"key": "canvas:1", "status": "IN CLASS — CHECK"}], [item])
    assert diff.changed == {} and diff.new == set() and diff.cleared == []

"""Saved view reports: the rows behind the Reports list."""
from __future__ import annotations

import json

from lakota_grades.web import db
from lakota_grades.web.stores import reports


def test_empty_table(tmp_path):
    conn = db.open_db(tmp_path)
    assert reports.all(conn) == [] and reports.by_id(conn, 1) is None
    conn.close()


def test_create_read_update_delete(tmp_path):
    conn = db.open_db(tmp_path)
    rid = reports.create(conn, "Weekly summary", '{"source": "items"}', now="2026-09-16T08:00:00-04:00")
    row = reports.by_id(conn, rid)
    assert row["name"] == "Weekly summary" and json.loads(row["definition"])["source"] == "items"
    assert row["created_at"] == row["updated_at"] == "2026-09-16T08:00:00-04:00"
    assert reports.update(conn, rid, "Renamed", '{"source": "grades"}', now="2026-09-16T09:00:00-04:00") is True
    row = reports.by_id(conn, rid)
    assert row["name"] == "Renamed" and row["created_at"] < row["updated_at"]
    assert reports.update(conn, 999, "x", "{}", now="2026-09-16T09:00:00-04:00") is False
    assert reports.delete(conn, rid) is True and reports.by_id(conn, rid) is None
    assert reports.delete(conn, rid) is False
    conn.close()


def test_all_is_by_name(tmp_path):
    conn = db.open_db(tmp_path)
    for name in ("Zebra", "Apple", "Mango"):
        reports.create(conn, name, "{}", now="2026-09-16T08:00:00-04:00")
    assert [r["name"] for r in reports.all(conn)] == ["Apple", "Mango", "Zebra"]
    conn.close()


def test_seed_templates_only_fills_an_empty_table(tmp_path):
    conn = db.open_db(tmp_path)
    assert reports.seed_templates(conn, now="2026-09-16T08:00:00-04:00") == 4
    names = [r["name"] for r in reports.all(conn)]
    assert names == ["Grade trend", "Open work", "Quarter recap", "Recent changes"]
    assert reports.seed_templates(conn, now="2026-09-16T08:00:00-04:00") == 0
    assert len(reports.all(conn)) == 4
    conn.close()


def test_seeded_definitions_are_valid(tmp_path):
    from lakota_grades.web import views
    conn = db.open_db(tmp_path)
    reports.seed_templates(conn, now="2026-09-16T08:00:00-04:00")
    for r in reports.all(conn):
        d = views.from_json(r["definition"])
        assert views.validate(d) == [], f"{r['name']}: {views.validate(d)}"
    conn.close()

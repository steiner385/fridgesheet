"""The last slot each schedule fired: what stops a restart firing it twice."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fridgesheet.web import db
from fridgesheet.web.stores import fires

TZ = ZoneInfo("America/New_York")


def test_a_new_database_has_the_table_and_no_rows(tmp_path):
    conn = db.open_db(tmp_path)
    assert db.SCHEMA_VERSION == 10
    assert fires.all(conn) == {}


def test_record_then_read_back_keeps_the_instant(tmp_path):
    conn = db.open_db(tmp_path)
    slot = datetime(2026, 9, 25, 14, 0, tzinfo=TZ)
    fires.record(conn, "open-work", slot)
    got = fires.all(conn)["open-work"]
    assert got == slot and got.utcoffset() == slot.utcoffset()


def test_recording_again_replaces_the_slot(tmp_path):
    conn = db.open_db(tmp_path)
    fires.record(conn, "data-refresh", datetime(2026, 9, 25, 5, 0, tzinfo=TZ))
    fires.record(conn, "data-refresh", datetime(2026, 9, 25, 7, 0, tzinfo=TZ))
    assert fires.all(conn) == {"data-refresh": datetime(2026, 9, 25, 7, 0, tzinfo=TZ)}


def test_a_version_7_file_migrates_to_current(tmp_path):
    conn = db.open_db(tmp_path)
    conn.execute("DROP TABLE category_observations")               # back to the v9 shape
    conn.execute("DROP TABLE item_categories")
    conn.execute("DROP TABLE schedule_fires")
    conn.execute("ALTER TABLE checkins DROP COLUMN seen")          # back to the v8 shape
    conn.execute("UPDATE schema_version SET version = 7")
    assert db.migrate(conn) == db.SCHEMA_VERSION == 10
    assert fires.all(conn) == {}

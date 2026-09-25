"""`schedule_fires`: the last slot each schedule fired. Written by the clock, read by it and
by nothing else -- the Runs page, not this table, is what a parent reads."""
from __future__ import annotations

import sqlite3
from datetime import datetime


def all(conn: sqlite3.Connection) -> dict[str, datetime]:
    return {r["key"]: datetime.fromisoformat(r["slot"]) for r in conn.execute("SELECT key, slot FROM schedule_fires")}


def record(conn: sqlite3.Connection, key: str, slot: datetime) -> None:
    conn.execute("INSERT INTO schedule_fires(key, slot) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET slot = excluded.slot", (key, slot.isoformat()))

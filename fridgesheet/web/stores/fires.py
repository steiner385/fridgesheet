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


def forget_all_but(conn: sqlite3.Connection, keys) -> None:
    """Drop every row whose key is not in `keys` (the schedules switched on right now). A row
    outliving its schedule would make the next schedule under that key -- the same one turned
    back on, or a new report reissued an old `view:<id>` -- skip the first-sight rule and fire
    a slot that passed before it was on."""
    keys = list(keys)
    if not keys:
        conn.execute("DELETE FROM schedule_fires")
        return
    marks = ", ".join("?" for _ in keys)
    conn.execute(f"DELETE FROM schedule_fires WHERE key NOT IN ({marks})", keys)

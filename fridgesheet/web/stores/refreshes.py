"""What the header says about the last refresh."""
from __future__ import annotations

import sqlite3


def latest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM refreshes ORDER BY id DESC LIMIT 1").fetchone()

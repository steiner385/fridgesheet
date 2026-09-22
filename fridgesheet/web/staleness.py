"""How old the data is, and whether that is old enough to say so on every page.

The ceiling is the runner's own, imported rather than re-spelled: past it a `--no-refresh`
run refuses to print ("snapshot is stale ... nothing printed"). A banner with a threshold of
its own could show a kiosk claiming the data is fine while the afternoon print fails as
stale -- the app disagreeing with itself about one fact.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ..runner import MAX_DATA_AGE_HOURS
from ..dates import parse_iso                 # moved out of web/app.py in this task

CEILING_HOURS = MAX_DATA_AGE_HOURS


@dataclass(frozen=True)
class Staleness:
    hours: int                  # whole hours since the last refresh that actually succeeded
    last_good: str | None       # its ISO timestamp, or None when there has never been one
    reason: str                 # why the most recent attempt did not help, or ""


def _latest_good(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM refreshes WHERE ok = 1 ORDER BY id DESC LIMIT 1").fetchone()


def _why(conn: sqlite3.Connection) -> str:
    """The failing sources of the most recent attempt, if it failed."""
    row = conn.execute("SELECT * FROM refreshes ORDER BY id DESC LIMIT 1").fetchone()
    if row is None or row["ok"]:
        return ""
    try:
        bad = {k: v for k, v in json.loads(row["sources"]).items() if v != "ok"}
    except (ValueError, TypeError):
        return ""
    return "; ".join(f"{k.upper() if k == 'hac' else k.capitalize()}: {v}" for k, v in sorted(bad.items()))


def check(conn: sqlite3.Connection, now: datetime, ceiling_hours: int = CEILING_HOURS) -> Staleness | None:
    """None when the data is fresh enough to print from; a `Staleness` when it is not."""
    good = _latest_good(conn)
    if good is None:
        return Staleness(hours=ceiling_hours + 1, last_good=None, reason=_why(conn))
    started = parse_iso(good["started_at"])
    hours = int((now - started.astimezone(now.tzinfo)).total_seconds() // 3600)
    if hours < ceiling_hours:
        return None
    return Staleness(hours=hours, last_good=good["started_at"], reason=_why(conn))

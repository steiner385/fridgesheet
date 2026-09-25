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
from ..dates import parse_iso, wd_md_time     # parse_iso moved out of web/app.py in this task
from .ingest import course_label, n_classes   # the header names a carried class the way the log line does

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


def canvas_note(refresh: sqlite3.Row | None, tz) -> str:
    """What the header adds beside "Canvas OK" when one class did not answer (#140):
    "1 class carried from Tue 9/15 6:05 AM: Alex's Algebra I (403 Forbidden)", and/or
    "1 class not fetched: Alex's course 6 (403 Forbidden)". "" when every class answered,
    for a row from before the column existed, and for no refresh at all. Not a staleness:
    the refresh was good, so this never trips the banner -- it is named, not alarmed about.
    """
    if refresh is None or "carried" not in refresh.keys() or not refresh["carried"]:
        return ""
    try:
        faults = json.loads(refresh["carried"])
    except (ValueError, TypeError):
        return ""

    def label(f: dict) -> str:
        return f"{course_label(f)} ({(f.get('reason') or '')[:80]})"

    def when(iso: str) -> str:
        d = parse_iso(iso)
        return wd_md_time(d.astimezone(tz)) if d else "an older pull"

    parts = []
    carried = faults.get("carried") or []
    if carried:
        times = sorted({c.get("fetched_at") or "" for c in carried})
        if len(times) == 1:
            parts.append(f"{n_classes(len(carried))} carried from {when(times[0])}: " + "; ".join(label(c) for c in carried))
        else:
            parts.append(f"{n_classes(len(carried))} carried from older pulls: "
                         + "; ".join(f"{label(c)} from {when(c.get('fetched_at') or '')}" for c in carried))
    missing = faults.get("missing") or []
    if missing:
        parts.append(f"{n_classes(len(missing))} not fetched: " + "; ".join(label(m) for m in missing))
    return "; ".join(parts)


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

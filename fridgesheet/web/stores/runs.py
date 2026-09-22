"""Run history: the CLI runner and (part 2) the jobs worker write it; the header badge,
the Dashboard and the Runs page read it."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date


#: What started a run, in words (#11 item 20). `runs.trigger` is `RunOptions.trigger` --
#: "web", "cli", "schedule" -- which named the code path that called the runner rather than
#: anything a parent did. A trigger with no label here is shown as it was written, because a
#: row from a newer version is still a row somebody has to be able to read.
TRIGGER_LABELS = {"web": "In the app", "cli": "At a terminal", "schedule": "On a schedule"}


def trigger_label(trigger: str) -> str:
    return TRIGGER_LABELS.get(trigger, trigger)


def latest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT 1").fetchone()


def latest_for(conn: sqlite3.Connection, report_key: str) -> sqlite3.Row | None:
    """The newest run recorded for one report key -- how `preview` finds the PDF a run just
    built, without guessing a filename or globbing a directory that might hold a stale one."""
    return conn.execute(
        "SELECT * FROM runs WHERE report_key = ? ORDER BY started_at DESC, id DESC LIMIT 1",
        (report_key,)).fetchone()


def recent(conn: sqlite3.Connection, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)).fetchall()


def printed_on(conn: sqlite3.Connection, day: date) -> list[sqlite3.Row]:
    """OK runs that produced a PDF on `day` (local date prefix of started_at)."""
    return conn.execute(
        "SELECT * FROM runs WHERE outcome = 'OK' AND pdf_path IS NOT NULL AND substr(started_at, 1, 10) = ? ORDER BY id",
        (day.isoformat(),)).fetchall()


def record(conn: sqlite3.Connection, report_key: str, started: str, finished: str, trigger: str, outcome: str,
           message: str, pdf_path: str | None = None, job_ref: str | None = None) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path, job_ref) VALUES (?,?,?,?,?,?,?,?)",
            (report_key, started, finished, trigger, outcome, message[:500], pdf_path, job_ref))
        return cur.lastrowid


def by_id(conn: sqlite3.Connection, run_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


@dataclass(frozen=True)
class RunSummary:
    """A run's message, read for a parent rather than echoed.

    `runs.message` is the runner's log line -- "dry-run built C:\\Users\\...\\sheet.pdf 2p
    Kid1=23 Kid2=4 data=9/17 18:06" -- and the Dashboard card, the header and Settings all
    printed it verbatim, file path and all, under a heading that said "Printed today" when
    nothing had been printed (#40 items 4 and 16). This is the same line with the facts
    picked out; anything the pattern does not recognise keeps the raw text as `detail`.
    """
    kind: str                       # printed | previewed | pdf only | refreshed | skipped | failed
    pages: int | None = None
    per_kid: list[tuple[str, int]] = field(default_factory=list)   # (student key, items on the sheet)
    detail: str = ""                # the raw message, for the kinds nothing else describes

    @property
    def label(self) -> str:
        return {"printed": "Printed", "previewed": "Previewed", "pdf only": "PDF only, not printed",
                "refreshed": "Refreshed", "skipped": "Skipped", "failed": "Failed"}.get(self.kind, self.kind)

    @property
    def short(self) -> str:
        """What happened, for the header: two words for a good run, the reason for a bad one.
        A failure's message is the one line a parent must see ("printer offline"), so it is
        kept -- but cut, since a traceback-shaped message would push the clock off the bar."""
        if self.kind in ("failed", "skipped") and self.detail:
            return f"{self.label.lower()}: {self.detail[:80]}"
        if self.pages:
            return f"{self.label.lower()} · {self.pages} page{'s' if self.pages != 1 else ''}"
        return self.label.lower()


_PAGES = re.compile(r"\b(\d+)p\b")
_PER_KID = re.compile(r"\b([A-Za-z][\w-]*)=(\d+)\b")
_NOT_KIDS = {"data", "saved"}


def describe(row: sqlite3.Row) -> RunSummary:
    msg = row["message"] or ""
    if row["outcome"] == "FAIL":
        kind = "failed"
    elif row["outcome"] == "SKIP":
        kind = "skipped"
    elif row["report_key"] == "refresh":
        kind = "refreshed"
    elif msg.startswith("dry-run"):
        kind = "previewed"
    elif msg.startswith("PDF only"):
        kind = "pdf only"
    else:
        kind = "printed"
    m = _PAGES.search(msg)
    pages = int(m.group(1)) if m else None
    per_kid = [(k, int(n)) for k, n in _PER_KID.findall(msg) if k not in _NOT_KIDS]
    return RunSummary(kind, pages, per_kid, detail=msg if kind in ("failed", "skipped", "refreshed") else "")

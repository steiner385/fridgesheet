"""`lakota-grades print-sheet`: refresh, build the open-work sheet, send it to CUPS, record it.

Files under the lakota-grades home (~/.lakota-grades):

    no-print-days.txt        one YYYY-MM-DD (or YYYY-MM-DD..YYYY-MM-DD) per line, optional comment
    late-rules.toml          the late-work register (see late_rules)
    sheets/YYYY-MM-DD/       sheet.pdf, rows.json (what was on it), printed.txt (the CUPS job)
    print-sheet.log          one line per run; the same line goes to stderr for journalctl

Guards, in order: skip list (--force overrides), already printed today (nothing overrides;
delete printed.txt to reprint), the 2 PM-to-midnight window so a Persistent= catch-up after
a wake does not print yesterday's sheet at 9 AM (--force, --dry-run and --date override).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import collector, late_rules, open_items, sheet
from .config import Settings

WINDOW_START_HOUR = 14
MAX_DATA_AGE_HOURS = 24
DEFAULT_PRINTER = "Brother_MFC_J4335DW"

SKIP_SEED = """# Days the sheet is not printed. One date per line, optional note after it.
# Ranges: 2026-12-21..2027-01-01 . Weekends never print anyway.
# Source: Lakota Local Schools board-approved 2026-27 calendar (amended 5/4/26).
2026-08-10..2026-08-12  Teacher PD
2026-09-07  Labor Day
2026-09-08  Safety/Security PD day
2026-10-16  Teacher PD
2026-11-03  Election Day / Teacher PD
2026-11-25  Compensatory day
2026-11-26..2026-11-27  Thanksgiving
2026-12-21..2027-01-01  Holiday break
2027-01-04  Teacher PD
2027-01-18  MLK Day
2027-02-12  Compensatory day
2027-02-15  Presidents' Day
2027-03-12  Teacher PD
2027-03-26..2027-04-02  Spring break
2027-05-04  Election Day / Teacher PD
2027-05-21  Teacher PD
2027-05-24..2027-08-13  Summer -- update when the 27-28 calendar posts
"""

_DATE = r"(\d{4}-\d{2}-\d{2})"
_LINE = re.compile(rf"^\s*{_DATE}(?:\s*\.\.\s*{_DATE})?\s*(.*?)\s*$")


@dataclass
class Options:
    dry_run: bool = False
    kid: str | None = None
    date: str | None = None
    days: int = 14
    overdue_days: int = 14
    force: bool = False
    printer: str = DEFAULT_PRINTER
    no_refresh: bool = False


def parse_skip_days(text: str) -> dict[date, str]:
    out: dict[date, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        try:
            start = date.fromisoformat(m.group(1))
            end = date.fromisoformat(m.group(2)) if m.group(2) else start
        except ValueError:
            continue
        note = m.group(3).lstrip("#").strip()
        d = start
        while d <= end:
            out[d] = note
            d += timedelta(days=1)
    return out


def nicknames() -> dict[str, str]:
    """Snapshot key -> name printed on the sheet. LAKOTA_NICKNAMES="Douglas=Doug,Katherine=Kate"."""
    out = {"Douglas": "Doug"}
    for pair in os.environ.get("LAKOTA_NICKNAMES", "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _wanted(key: str, kid: str | None) -> bool:
    if not kid:
        return True
    a, b = key.lower(), kid.lower()
    return a.startswith(b) or b.startswith(a) or nicknames().get(key, "").lower().startswith(b)


def data_as_of(snap: dict) -> datetime:
    """When the oldest data in the snapshot was really fetched: the file's own time, or an
    earlier one for any source carried forward from a previous pull."""
    epochs = [snap.get("fetched_at_epoch") or 0] + [m.get("fetched_at_epoch") or 0 for m in (snap.get("stale") or {}).values()]
    return datetime.fromtimestamp(min(e for e in epochs if e) if any(epochs) else 0).astimezone()


def _previous_rows(sheets_dir: Path, day: date) -> tuple[dict | None, str | None]:
    """The rows.json from the most recent earlier sheet, and a label for it."""
    if not sheets_dir.is_dir():
        return None, None
    for p in sorted(sheets_dir.iterdir(), reverse=True):
        try:
            d = date.fromisoformat(p.name)
        except ValueError:
            continue
        if d < day and (p / "rows.json").is_file():
            return json.loads((p / "rows.json").read_text()), d.strftime("%a %-m/%-d")
    return None, None


class _Log:
    def __init__(self, path: Path, now: datetime):
        self.path, self.now = path, now

    def __call__(self, level: str, msg: str) -> None:
        line = f"{self.now:%Y-%m-%d %H:%M:%S} {level:<5} {msg}"
        print(line, file=sys.stderr, flush=True)
        with self.path.open("a") as f:
            f.write(line + "\n")


def run(opts: Options, settings: Settings, *, now: datetime | None = None, refresh=collector.collect, lp=subprocess.run) -> int:
    tz = ZoneInfo(settings.timezone)
    now = now or datetime.now(tz)
    day = date.fromisoformat(opts.date) if opts.date else now.date()
    home = settings.home
    home.mkdir(parents=True, exist_ok=True)
    log = _Log(home / "print-sheet.log", now)
    day_dir = home / "sheets" / day.isoformat()
    mode = "dry-run" if opts.dry_run else "print"

    # First run seeds the two editable files; later runs never touch them.
    skip_path = home / "no-print-days.txt"
    if not skip_path.exists():
        skip_path.write_text(SKIP_SEED)
    late_rules.ensure_seed(home / "late-rules.toml")

    # --- guards ---------------------------------------------------------------
    skips = parse_skip_days(skip_path.read_text())
    if day in skips and not opts.force:
        log("SKIP", f"{day} is in no-print-days.txt ({skips[day] or 'no note'}); nothing printed")
        return 0
    if not opts.dry_run and (day_dir / "printed.txt").is_file():
        log("SKIP", f"{day} already printed ({(day_dir / 'printed.txt').read_text().strip()}); delete printed.txt to reprint")
        return 0
    if not (opts.force or opts.dry_run or opts.date) and now.hour < WINDOW_START_HOUR:
        log("SKIP", f"outside print window (before {WINDOW_START_HOUR}:00); this is a catch-up run, not printing")
        return 0

    # --- data -----------------------------------------------------------------
    refresh_error: str | None = None
    if not opts.no_refresh:
        try:
            snap = refresh(settings)
            bad = {k: v for k, v in (snap.get("sources") or {}).items() if v != "ok"}
            if bad:
                refresh_error = "; ".join(f"{k}: {v}" for k, v in bad.items())
        except Exception as e:  # a failed pull must never stop a fresh-enough sheet
            refresh_error = str(e)[:200]
    snap = collector.load_snapshot(settings)
    if not snap:
        log("FAIL", "no snapshot on disk and refresh failed" + (f": {refresh_error}" if refresh_error else ""))
        return 1
    as_of = data_as_of(snap).astimezone(tz)
    age_h = (now - as_of).total_seconds() / 3600
    stale_note = None
    if refresh_error:
        if age_h > MAX_DATA_AGE_HOURS:
            log("FAIL", f"refresh failed ({refresh_error}) and snapshot is stale ({age_h:.0f} h old, data from {as_of:%Y-%m-%d %H:%M}); nothing printed")
            return 1
        stale_note = f"refresh failed at {now:%-I:%M %p}; data from {as_of:%a %-m/%-d %-I:%M %p}"

    # --- build ------------------------------------------------------------------
    rules = late_rules.load(home / "late-rules.toml")
    names = nicknames()
    prev_rows, prev_label = _previous_rows(home / "sheets", day)
    at = now if not opts.date else datetime.combine(day, now.timetz())
    sheets: list[sheet.KidSheet] = []
    rows_out: dict[str, list[dict]] = {}
    counts = []
    for key, entry in snap["students"].items():
        if not _wanted(key, opts.kid):
            continue
        label = names.get(key, key)
        work = open_items.open_items(entry, label, at, days_ahead=opts.days, overdue_days=opts.overdue_days, rules=rules)
        diff = open_items.compare(prev_rows.get(key, []), work.items) if prev_rows is not None else None
        sheets.append(sheet.KidSheet(label, work, diff, prev_label))
        rows_out[key] = [i.to_dict() for i in work.items]
        counts.append(f"{label}={len(work.items)}")
    if not sheets:
        log("FAIL", f"no student matches --kid {opts.kid!r}; known: {', '.join(snap['students'])}")
        return 1
    day_dir.mkdir(parents=True, exist_ok=True)
    pdf = day_dir / "sheet.pdf"
    pages = sheet.build_pdf(sheets, pdf, data_as_of=as_of, days_ahead=opts.days, overdue_days=opts.overdue_days, stale_note=stale_note, printed_at=at)
    (day_dir / "rows.json").write_text(json.dumps(rows_out, indent=1))
    summary = f"{pages}p {' '.join(counts)} data={as_of:%-m/%-d %H:%M}" + (f" NOTE refresh failed: {refresh_error}" if refresh_error else "")

    if opts.dry_run:
        log("OK", f"dry-run built {pdf} {summary}")
        return 0

    # --- print ------------------------------------------------------------------
    cmd = ["lp", "-d", opts.printer, "-o", "sides=two-sided-long-edge", "-o", "media=Letter", "-t", f"lakota open work {day}", str(pdf)]
    r = lp(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log("FAIL", f"lp failed ({r.returncode}): {(r.stderr or r.stdout).strip()[:200]}; PDF kept at {pdf}")
        return 1
    m = re.search(r"request id is (\S+)", r.stdout or "")
    job = m.group(1) if m else (r.stdout or "").strip()
    (day_dir / "printed.txt").write_text(f"{now.isoformat()} {job}\n")
    log("OK", f"printed job={job} {summary}")
    return 0

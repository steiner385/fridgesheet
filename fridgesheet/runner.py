# fridgesheet/runner.py
"""Run one report for one day: guards, refresh, build, archive, print, record, notify.

Files under the app home:
    no-print-days.txt        one YYYY-MM-DD (or YYYY-MM-DD..YYYY-MM-DD) per line, optional comment
    late-rules.toml          the late-work register (see late_rules)
    <output_dir>/<day>/      sheet.pdf, rows.json, printed.txt   (open-work: sheets/<day>/)
    print-sheet.log          every report's runs: the outcome line, plus an INFO line for an
                             ingested refresh; also stderr when the process has one
    fridgesheet.db                the app's database (see web/db.py), with its -wal/-shm sidecars
    run.lock                 held while a run is in progress

Guards, in order: skip list (--force overrides), already printed today (only --reprint
overrides), and the print window (the report's configured time to midnight, so a
Persistent/StartWhenAvailable catch-up the next morning logs and exits; --force,
--dry-run and --date override).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path, PureWindowsPath
from zoneinfo import ZoneInfo

from . import collector, late_rules, reports
from .config import Settings
from .dates import md, time12, wd_md, wd_md_time
from .reports.base import BuildContext, ReportError

MAX_DATA_AGE_HOURS = 24
LOG_NAME = "print-sheet.log"
LOCK_NAME = "run.lock"
LOCK_STALE_SECONDS = 45 * 60
# Must exceed the scheduler's ExecutionTimeLimit (PT30M in host/task.xml) so a slow-but-alive
# run is never declared abandoned.

SKIP_HEADER = """# Days the sheet is not printed. One date per line, optional note after it.
# Ranges: 2026-12-21..2027-01-01 . Weekends never print anyway.
"""

SKIP_SEED = SKIP_HEADER + """# Source: Lakota Local Schools board-approved 2026-27 calendar (amended 5/4/26).
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
class RunOptions:
    dry_run: bool = False
    force: bool = False
    reprint: bool = False            # a deliberate second print of a day; --force never implies it
    force_print: bool = False        # print even a report configured PDF-only: an interactive
                                     # "Print now", never a scheduled run
    date: str | None = None
    kid: str | None = None
    no_refresh: bool = False
    printer: str | None = None       # None -> settings.printer -> system default
    options: dict = field(default_factory=dict)   # report-specific CLI overrides; None values are ignored
    notify: bool = True
    trigger: str = "cli"             # cli | schedule | web


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


@dataclass(frozen=True)
class SkipEntry:
    """One row of the graphical editor: a single day, or a range (`end` set), with a note.
    Unlike `parse_skip_days`'s dict-per-day, a range survives as one entry so editing it
    doesn't explode it into hundreds of single-day rows."""
    start: date
    end: date | None = None
    note: str = ""


def parse_skip_entries(text: str) -> list[SkipEntry]:
    out: list[SkipEntry] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        try:
            start = date.fromisoformat(m.group(1))
            end = date.fromisoformat(m.group(2)) if m.group(2) else None
        except ValueError:
            continue
        out.append(SkipEntry(start, end, m.group(3).lstrip("#").strip()))
    return out


def format_skip_entries(entries: list[SkipEntry]) -> str:
    lines = [SKIP_HEADER.rstrip("\n")]
    for e in entries:
        line = e.start.isoformat()
        if e.end and e.end != e.start:
            line += f"..{e.end.isoformat()}"
        if e.note:
            line += f"  {e.note}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def school_year(d: date) -> str:
    """'2026-27' for any date from Aug 1 2026 through Jul 31 2027."""
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def archive_copy(pdf: Path, archive_root: str, day: date, name: str) -> Path | None:
    """Copy the PDF where people look for it: <archive>/<school year>/<name>.

    `name` comes from a report's `archive_name()`, and a view report's is built from the
    user-editable `reports.name` column -- never trusted whole. Only the final path
    component survives; a name that is empty or `.`/`..` after that gets no copy at all
    rather than a path outside the archive root.

    The reduction goes through `PureWindowsPath` on every platform, because it is the
    stricter of the two rulesets: it treats `\\` as a separator (where POSIX would keep it
    as an ordinary character) and strips a drive, so `C:evil.pdf` cannot reset the anchor of
    the join below on Windows. Same input, same answer, whichever OS is running.
    """
    safe = PureWindowsPath(name).name
    if not safe or safe in (".", ".."):
        return None
    dest = Path(archive_root).expanduser() / school_year(day) / safe
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, dest)
    return dest


def data_as_of(snap: dict) -> datetime:
    """When the oldest data in the snapshot was really fetched: the file's own time, or an
    earlier one for any source carried forward from a previous pull."""
    epochs = [snap.get("fetched_at_epoch") or 0] + [m.get("fetched_at_epoch") or 0 for m in (snap.get("stale") or {}).values()]
    return datetime.fromtimestamp(min(e for e in epochs if e) if any(epochs) else 0).astimezone()


def _previous_rows(out_root: Path, day: date) -> tuple[dict | None, str | None]:
    """The rows.json from the most recent earlier sheet, and a label for it."""
    if not out_root.is_dir():
        return None, None
    for p in sorted(out_root.iterdir(), reverse=True):
        try:
            d = date.fromisoformat(p.name)
        except ValueError:
            continue
        if d < day and (p / "rows.json").is_file():
            return json.loads((p / "rows.json").read_text()), wd_md(d)
    return None, None


def _window_open(now: datetime, hhmm: str) -> bool:
    h, m = (int(x) for x in hhmm.split(":", 1))
    return now.time() >= dtime(h, m)


def _open_db(home: Path, log):
    """One connection for the whole run, reused by the flags load, ingest and the run record;
    None (with a WARN) when the database cannot be opened -- the sheet must print either way."""
    try:
        from .web import db as webdb
        return webdb.open_db(home)
    except Exception as e:
        log("WARN", f"could not open the database: {type(e).__name__}: {str(e)[:120]}")
        return None


def _load_flags(conn, log) -> dict[str, dict[str, str]]:
    """Active flags per kid (student key -> item key -> flag), or nothing (with a WARN) if
    they cannot be read. Per kid because item keys only identify an item within a student."""
    if conn is None:
        return {}
    try:
        from .web.stores import flags as flagstore
        return flagstore.active_by_student(conn)
    except Exception as e:  # the sheet must print even if the database is broken
        log("WARN", f"could not read flags from the database: {type(e).__name__}: {str(e)[:120]}")
        return {}


def _ingest(conn, snap: dict, tz, log) -> None:
    """Record the fresh snapshot in the database. The database is a passenger: it must never
    stop the sheet from printing."""
    if conn is None:
        return
    try:
        from .web import ingest
        r = ingest.record(conn, snap, tz=tz)
        log("INFO", f"ingested refresh {r.refresh_id}: {r.items} new items, {r.observations} changes, {r.grades} grade changes")
    except Exception as e:
        log("WARN", f"could not ingest the snapshot into the database: {type(e).__name__}: {str(e)[:120]}")


def _record_run(conn, report_key: str, started: datetime, finished: datetime, trigger: str, outcome: str,
                message: str, pdf_path, job_ref, log) -> None:
    if conn is None:
        return
    try:
        with conn:
            conn.execute(
                "INSERT INTO runs(report_key, started_at, finished_at, trigger, outcome, message, pdf_path, job_ref) VALUES (?,?,?,?,?,?,?,?)",
                (report_key, started.isoformat(), finished.isoformat(), trigger, outcome, message[:500],
                 str(pdf_path) if pdf_path else None, job_ref))
    except Exception as e:
        log("WARN", f"could not record the run in the database: {type(e).__name__}: {str(e)[:120]}")


class _Log:
    """The run's outcome line -- plus an `INFO ingested ...` line when the run refreshed --
    always to the log file, and to `echo` when given (the app's log pane) or else to stderr
    when the process has one (a windowed exe has sys.stderr = None)."""

    def __init__(self, path: Path, now: datetime, key: str, echo=None):
        self.path, self.now, self.key, self.echo = path, now, key, echo

    def __call__(self, level: str, msg: str) -> None:
        line = f"{self.now:%Y-%m-%d %H:%M:%S} {level:<5} {self.key} {msg}"
        if self.echo is not None:
            self.echo(line)
        elif sys.stderr is not None:
            print(line, file=sys.stderr, flush=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class Lock:
    """Create-exclusive lock file; a lock older than LOCK_STALE_SECONDS is treated as abandoned
    and a new holder may take it over. That does not mean the displaced holder ever learns of
    the takeover -- it is typically still running, just slow -- so `release()` must not trust
    "I once held this" enough to delete whatever is at `path` by the time it gets there: it may
    by then be someone else's lock.

    Each `acquire` therefore mints a fresh random token and writes it (with the pid, for a human
    reading the file) into the lock; `release()` deletes the file only if that token is still
    the one written there. The token is *not* the pid: a pid identifies an OS process, but the
    two holders on either side of a takeover can be the very same process -- `web.jobs.Worker`
    starts a fresh thread for the replacement job while the displaced job's thread is left
    running, and both share one pid. A pid comparison would let the displaced thread's release
    delete the replacement thread's lock, which is exactly the bug this guards against. (Reusing
    a pid across two unrelated *processes*, the classic reason a bare pid is an unsafe lock
    token, would have the same failure mode.) A lock with no token at all -- missing, truncated,
    or left by a version that wrote nothing -- never matches and is simply left alone.
    """

    def __init__(self, path: Path):
        self.path, self.held, self.token = path, False, None

    def acquire(self) -> bool:
        try:
            if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                self.path.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        self.token = uuid.uuid4().hex
        os.write(fd, f"{os.getpid()} {self.token}".encode("ascii"))
        os.close(fd)
        self.held = True
        return True

    def release(self) -> None:
        """Delete the lock file, but only if it still carries the token this `acquire` wrote --
        never true after a stale takeover, since the new holder's own `acquire` wrote a fresh
        one. `self.held` always goes back to False either way: whether or not the file gets
        touched, this object no longer represents a held lock."""
        if self.held:
            try:
                current = self.path.read_text(encoding="ascii")
            except (OSError, UnicodeDecodeError):
                current = ""
            if current.split()[-1:] == [self.token]:
                self.path.unlink(missing_ok=True)
            self.held = False


_Lock = Lock   # one release of compatibility; nothing else in the tree uses this name


def _toast_body(level: str, msg: str, day: date, printed: bool = True) -> str:
    if level == "OK":
        return f"Printed {wd_md(day)}: {msg}" if printed else f"Built (not printed) {wd_md(day)}: {msg}"
    if level == "SKIP":
        return f"Skipped: {msg}"
    body = f"Not printed: {msg}"
    if "login" in msg.lower():
        body += ". Open Fridge Sheet to check your password."
    return body


def run(report_key: str, opts: RunOptions, settings: Settings, *, now: datetime | None = None,
        refresh=collector.collect, print_pdf=None, toast=None, echo=None) -> int:
    tz = ZoneInfo(settings.timezone)
    now = now or datetime.now(tz)
    started = datetime.now(tz)   # the real clock for run bookkeeping, even when `now` is injected
    home = settings.home
    home.mkdir(parents=True, exist_ok=True)
    log = _Log(home / LOG_NAME, now, report_key, echo)
    try:
        report = reports.resolve(report_key, settings.home)
    except ReportError as e:
        log("FAIL", str(e))
        return 2
    if print_pdf is None:
        from .host import printing
        print_pdf = printing.print_pdf
    if toast is None:
        from .host import notify
        toast = notify.toast
    from .host.printing import PrintError

    db_conn = _open_db(home, log)   # one connection for the whole run: flags, ingest, run record
    recorded = False                # a run gets exactly one `runs` row, whatever goes wrong
    try:
        def finish(level: str, msg: str, rc: int, toast_msg: str | None = None, pdf_path=None,
                   job_ref=None, printed: bool = True, quiet: bool = False) -> int:
            """Log the line, record the run, and toast a shorter form of it (the OK toast
            carries the summary, not the job id).

            `printed` only changes the OK toast's wording (see `_toast_body`) -- the log
            level and the `runs` row stay "OK" either way, since a PDF-only run that built
            and archived exactly as configured is not a failure or a skip.

            An exception raised inside finish -- a toast backend that dies, say -- lands in
            the catch-all below, which calls finish again to report it. The line is logged
            both times, but the run is recorded once.

            `quiet` records and logs without a toast: another run holds the lock, and that run
            will say how it went.
            """
            nonlocal recorded
            log(level, msg)
            if not recorded:
                recorded = True
                _record_run(db_conn, report_key, started, datetime.now(tz), opts.trigger, level, msg, pdf_path, job_ref, log)
            if opts.notify and not opts.dry_run and not quiet:
                toast(report.title, _toast_body(level, toast_msg or msg, day, printed))
            return rc

        day = date.fromisoformat(opts.date) if opts.date else now.date()
        rc_cfg = settings.report_config(report.key, report.default_time)
        out_root = home / report.output_dir
        day_dir = out_root / day.isoformat()

        skip_path = home / "no-print-days.txt"
        if not skip_path.exists():
            skip_path.write_text(SKIP_SEED)
        late_rules.ensure_seed(home / "late-rules.toml")

        # --- guards ---------------------------------------------------------------
        skips = parse_skip_days(skip_path.read_text())
        if day in skips and not opts.force:
            return finish("SKIP", f"{day} is in no-print-days.txt ({skips[day] or 'no note'}); nothing printed", 0)
        if not opts.dry_run and not opts.reprint and (day_dir / "printed.txt").is_file():
            last = (day_dir / "printed.txt").read_text().strip().splitlines()[-1]
            return finish("SKIP", f"{day} already printed ({last}); use --reprint to print again", 0)
        if not (opts.force or opts.dry_run or opts.date) and not _window_open(now, rc_cfg.time):
            return finish("SKIP", f"outside print window (before {rc_cfg.time}); this is a catch-up run, not printing", 0)

        lock = Lock(home / LOCK_NAME)
        if not lock.acquire():
            # Through `finish` like every other outcome (#2), so the one-row-per-run rule has
            # one owner; `quiet`, because the run holding the lock toasts its own result.
            return finish("SKIP", "already running (run.lock present); nothing done", 0, quiet=True)
        try:
            # --- data -----------------------------------------------------------------
            refresh_error: str | None = None
            if not opts.no_refresh:
                try:
                    snap = refresh(settings)
                    bad = {k: v for k, v in (snap.get("sources") or {}).items() if v != "ok"}
                    if bad:
                        refresh_error = "; ".join(f"{k}: {v}" for k, v in bad.items())
                    _ingest(db_conn, snap, tz, log)
                except Exception as e:  # a failed pull must never stop a fresh-enough sheet
                    refresh_error = str(e)[:200]
            snap = collector.load_snapshot(settings)
            if not snap:
                return finish("FAIL", "no snapshot on disk and refresh failed" + (f": {refresh_error}" if refresh_error else ""), 1)
            as_of = data_as_of(snap).astimezone(tz)
            age_h = (now - as_of).total_seconds() / 3600
            stale_note = None
            if refresh_error:
                if age_h > MAX_DATA_AGE_HOURS:
                    return finish("FAIL", f"refresh failed ({refresh_error}) and snapshot is stale ({age_h:.0f} h old, data from {as_of:%Y-%m-%d %H:%M}); nothing printed", 1)
                stale_note = f"refresh failed at {time12(now)}; data from {wd_md_time(as_of)}"
            elif opts.no_refresh and age_h > MAX_DATA_AGE_HOURS:
                # No refresh was even attempted -- the caller asked to use the snapshot as is,
                # trusting the independent refresh schedule (or a manual "Refresh now") to have
                # kept it warm. The same ceiling as a failed refresh still applies: past this
                # age the snapshot is not "as is", it is abandoned, and nothing should print or
                # build as though it were current.
                return finish("FAIL", f"snapshot is stale ({age_h:.0f} h old, data from {as_of:%Y-%m-%d %H:%M}) and no refresh was requested; nothing printed", 1)

            # --- build ------------------------------------------------------------------
            prev_rows, prev_label = _previous_rows(out_root, day)
            at = now if not opts.date else datetime.combine(day, now.timetz())
            options = {**rc_cfg.options, **{k: v for k, v in opts.options.items() if v is not None}}
            day_dir.mkdir(parents=True, exist_ok=True)
            ctx = BuildContext(settings=settings, home=home, day=day, now=at, out_dir=day_dir, kid=opts.kid, nicknames=settings.nicknames,
                               prev_rows=prev_rows, prev_label=prev_label, stale_note=stale_note, options=options, data_as_of=as_of,
                               flags=_load_flags(db_conn, log))
            try:
                built = report.build(snap, ctx)
            except ReportError as e:
                return finish("FAIL", str(e), 1)
            (day_dir / "rows.json").write_text(json.dumps(built.rows, indent=1))
            summary = f"{built.summary} data={md(as_of)} {as_of:%H:%M}" + (f" NOTE refresh failed: {refresh_error}" if refresh_error else "")
            if settings.sheets_archive:
                archive_name = report.archive_name(day)
                try:
                    dest = archive_copy(built.pdf, settings.sheets_archive, day, archive_name)
                # OSError is the missing Drive mount; ValueError is what the filesystem call
                # itself raises on a name it cannot even attempt (a raw NUL byte, say). Either
                # way the archive copy is a courtesy: it is a warning, never a failed run.
                except (OSError, ValueError) as e:
                    log("WARN", f"could not copy the sheet to the archive {settings.sheets_archive}: {e}")
                else:
                    if dest is None:
                        log("WARN", f"could not copy the sheet to the archive: {archive_name!r} is not a safe file name")
                    else:
                        summary += f" saved={dest}"
            if opts.dry_run:
                return finish("OK", f"dry-run built {built.pdf} {summary}", 0, toast_msg=None, pdf_path=built.pdf)
            if not rc_cfg.prints and not opts.force_print:
                # PDF only, by this report's own configuration -- the point of the setting, and
                # a scheduled run never gets past here. `force_print` is the escape hatch every
                # other guard in this function already has (the skip list yields to --force,
                # already-printed to --reprint, the window to --force/--date): a parent who
                # presses "Print now" is asking for paper, and answering OK without printing
                # would be the run claiming something it did not do.
                # Nothing is written to printed.txt: nothing was printed, and that file is the
                # record of prints.
                return finish("OK", f"PDF only (not printed) {built.pdf} {summary}", 0,
                              toast_msg=summary, pdf_path=built.pdf, printed=False)

            # --- print ------------------------------------------------------------------
            printer = opts.printer or rc_cfg.printer or settings.printer or None
            try:
                job = print_pdf(built.pdf, printer, f"fridgesheet {report.title.lower()} {day}")
            except PrintError as e:
                return finish("FAIL", f"{e}; PDF kept at {built.pdf}", 1, pdf_path=built.pdf)
            with (day_dir / "printed.txt").open("a") as f:   # append: a --reprint keeps the earlier job on record
                f.write(f"{now.isoformat()} {job}\n")
            return finish("OK", f"printed job={job} {summary}", 0, toast_msg=summary, pdf_path=built.pdf, job_ref=job)
        except Exception as e:  # anything not already handled above must still be logged and toasted, not crash the scheduler
            return finish("FAIL", f"unexpected error: {type(e).__name__}: {str(e)[:200]}", 1)
        finally:
            lock.release()
    finally:
        if db_conn is not None:
            db_conn.close()

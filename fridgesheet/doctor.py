"""`fridgesheet doctor`: ten quick probes that tell a user (or the build's smoke test)
whether this installation can do its job. Every probe is isolated; a probe that raises
becomes a FAIL line rather than a crash. Nothing here reads or prints a credential."""
from __future__ import annotations

import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import host
from .config import Settings

REPORT_NAME = "doctor.txt"


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _python(s: Settings, home: Path) -> str:
    return f"{sys.version.split()[0]} {'frozen' if getattr(sys, 'frozen', False) else 'source'} at {sys.executable}"


def _home(s: Settings, home: Path) -> str:
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=home, prefix=".doctor-", delete=True):
        pass
    return f"{home} is writable"


def _database(s: Settings, home: Path) -> str:
    """Open the database the way the app does. That runs any pending migration, on purpose:
    a doctor run on a machine that has not started the app since an upgrade reports the
    schema the app will actually use, and a migration that fails shows up here, where it can
    be read, rather than as a 500 on the first page (#2)."""
    from .web import db as webdb
    conn = webdb.open_db(home)
    try:
        v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
        n = conn.execute("SELECT count(*) FROM refreshes").fetchone()[0]
        m = conn.execute("SELECT count(*) FROM items").fetchone()[0]
        k = conn.execute("SELECT count(*) FROM flags WHERE cleared_at IS NULL").fetchone()[0]
    finally:
        conn.close()
    return f"{webdb.db_path(home)} schema {v}: {n} refreshes, {m} items, {k} active flags"


def _timezone(s: Settings, home: Path) -> str:
    ZoneInfo(s.timezone)
    # Worth a word when the household's zone is not the computer's (#122): schedules fire from
    # the server in the household's zone, but the log files' timestamps are the PC's clock.
    pc_zone = host.local_timezone()
    if pc_zone and pc_zone != s.timezone:
        return f"{s.timezone} (this computer's clock is {pc_zone})"
    return s.timezone


def _pdf(s: Settings, home: Path) -> str:
    from reportlab.pdfgen import canvas
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "doctor.pdf"
        c = canvas.Canvas(str(p))
        c.drawString(72, 720, "doctor")
        c.save()
        size = p.stat().st_size
    return f"reportlab wrote a {size}-byte PDF"


def _chromium(s: Settings, home: Path) -> str:
    """Actually start the bundled browser: the one thing the PyInstaller build could get wrong."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            version, path = browser.version, p.chromium.executable_path
        finally:
            browser.close()
    return f"Chromium {version} at {path}"


def _no_print_days(s: Settings, home: Path) -> str:
    """Does no-print-days.txt read the way the parent meant it? A reversed range or a date that
    does not exist is left out by `runner.parse_skip_days` -- a day the parent thinks is
    covered and is not (#147) -- and a hand-edited file is exactly the one nobody re-reads, so
    every such line is a FAIL here. Never writes: the first run seeds the file, not this."""
    from . import runner
    path = home / runner.SKIP_NAME
    if not path.is_file():
        return f"{runner.SKIP_NAME} not created yet (the first run seeds it)"
    problems: list[str] = []
    entries = runner.parse_skip_entries(path.read_text(encoding="utf-8"), problems=problems)
    if problems:
        raise RuntimeError(f"{runner.SKIP_NAME}: " + "; ".join(problems))
    days = runner.parse_skip_days(path.read_text(encoding="utf-8"))
    return f"{len(entries)} entries covering {len(days)} days"


def _credential_store(s: Settings, home: Path) -> str:
    if host.IS_WINDOWS:
        import keyring
        name = type(keyring.get_keyring()).__name__
        token = secrets.token_hex(8)
        service = host.keyring_service()
        keyring.set_password(service, "doctor-probe", token)
        try:
            got = keyring.get_password(service, "doctor-probe")
        finally:
            keyring.delete_password(service, "doctor-probe")
        if got != token:
            raise RuntimeError(f"keyring backend {name} did not round-trip a probe value")
        return f"keyring backend {name}: round trip OK"
    tool = shutil.which("secret-tool")
    if not tool:
        raise FileNotFoundError("secret-tool (libsecret) is not installed")
    return tool


def _printers(s: Settings, home: Path) -> str:
    from .host import printing
    names = printing.list_printers()
    if not names:
        raise RuntimeError("no printers are installed")
    if s.printer and s.printer not in names:
        raise RuntimeError(f"configured printer {s.printer!r} is not installed; installed: {', '.join(names)}")
    default = printing.default_printer()
    if not s.printer and default is None:
        raise RuntimeError("no printer is configured and this computer has no default printer")
    return f"{len(names)} printer(s), default {default or 'none'}, configured {s.printer or 'system default'}"


def _print_engine(s: Settings, home: Path) -> str:
    if host.IS_WINDOWS:
        from .host.printing_windows import sumatra_path
        p = sumatra_path()
        if not p.is_file():
            raise FileNotFoundError(f"SumatraPDF not found at {p}")
        return str(p)
    lp = shutil.which("lp")
    if not lp:
        raise FileNotFoundError("lp (CUPS) is not installed")
    return lp


def _scheduler(s: Settings, home: Path) -> str:
    """The server's own clock fires schedules (web/clock.py). From a terminal there is no clock
    to ask, so this names what is next and says schedules need the server; inside the server a
    clock that has stopped ticking is a FAIL, and so is a schedule that is on but cannot run, or a
    report scheduled while the data refresh is off."""
    from datetime import datetime
    from . import schedule_plan
    from .web import clock
    schedules, problems = clock.configured(home, settings=s)
    if problems:
        raise RuntimeError("; ".join(f"{k}: {v}" for k, v in sorted(problems.items())))
    # A scheduled report with the refresh off prints once and then fails every day (#120): it
    # runs with no refresh of its own and refuses a snapshot older than MAX_DATA_AGE_HOURS.
    reports_on = [x.key for x in schedules if x.key != host.DATA_REFRESH_KEY]
    if reports_on and not s.refresh.enabled:
        from .runner import MAX_DATA_AGE_HOURS
        raise RuntimeError(
            f"{', '.join(reports_on)} {'is' if len(reports_on) == 1 else 'are'} scheduled but the data refresh "
            f"is off; a scheduled report prints from the last refresh and refuses one older than "
            f"{MAX_DATA_AGE_HOURS} h. Tick Refresh on a schedule on the Schedules page and Save")
    if not schedules:
        return "no schedules are on"
    now = datetime.now(ZoneInfo(s.timezone))
    nxt = min(((schedule_plan.next_run(x, now), x.key) for x in schedules if schedule_plan.next_run(x, now)),
              default=(None, ""))
    detail = f"{len(schedules)} on; next: {nxt[1]} {nxt[0]:%a %H:%M}" if nxt[0] else f"{len(schedules)} on"
    running = clock.current()
    if running is None:
        return detail + "; schedules run only while the web server is running"
    if running.stale(now):
        raise RuntimeError(running.paused())
    return "scheduler running; " + detail


def _describe_service():
    from .host import service
    return service.describe_service()


def _port_answers(host: str, port: int) -> bool:
    from .web.server import port_answers
    return port_answers(host, port, timeout=2.0)


def _web_server(s: Settings, home: Path) -> str:
    """Is the browser app reachable, and is the always-on service the reason?"""
    url = f"http://127.0.0.1:{s.web_port}/"
    try:
        info = _describe_service()
        state = f"{info.managed_by}: {info.detail}"
        installed = info.installed
    except Exception as e:  # noqa: BLE001  no systemctl / schtasks here
        state, installed = f"service state unknown ({type(e).__name__})", False
    if _port_answers("127.0.0.1", s.web_port):
        return f"answering at {url} ({state})"
    if installed:
        raise RuntimeError(f"the service is installed ({state}) but {url} does not answer; check app.log")
    return f"not running ({state}); start it with `fridgesheet web` or install the service"


def _old_names(s: Settings, home: Path) -> str:
    """What on this machine still goes by the old name (lakota-grades / Lakota Sheet). Never a
    FAIL: everything listed still works through migrate.py's shims; the line is the to-do."""
    from . import migrate
    old = migrate.legacy_home(is_windows=host.IS_WINDOWS)
    lines = migrate.legacy_in_use(home=home, legacy_home_path=old)
    return "none" if not lines else "; ".join(lines)


PROBES: list[tuple[str, Callable[[Settings, Path], str]]] = [
    ("python", _python), ("home", _home), ("database", _database), ("timezone", _timezone), ("no-print days", _no_print_days),
    ("pdf", _pdf), ("chromium", _chromium),
    ("credential store", _credential_store), ("printers", _printers), ("print engine", _print_engine), ("scheduler", _scheduler),
    ("web server", _web_server), ("old names", _old_names),
]


def checks(settings: Settings, home: Path, *, probes=None) -> list[Check]:
    out: list[Check] = []
    for name, probe in (PROBES if probes is None else probes):
        try:
            out.append(Check(name, True, probe(settings, home)))
        except Exception as e:  # a probe must never take the report down with it
            out.append(Check(name, False, f"{type(e).__name__}: {str(e)[:300]}"))
    return out


def format_report(results: list[Check]) -> str:
    lines = [f"{'OK   ' if c.ok else 'FAIL '} {c.name}: {c.detail}" for c in results]
    failed = sum(1 for c in results if not c.ok)
    lines.append("All checks passed" if failed == 0 else f"{failed} check(s) failed")
    return "\n".join(lines)


def run(settings: Settings, home: Path, *, probes=None) -> tuple[str, bool]:
    """Run the probes, write <home>/doctor.txt (the windowed exe has no stdout), return (report, all_ok).
    A home that cannot be written is itself a FAIL line, never an exception."""
    results = checks(settings, home, probes=probes)
    ok = all(c.ok for c in results)
    report = format_report(results)
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / REPORT_NAME).write_text(report, encoding="utf-8")
    except OSError as e:
        report += f"\nFAIL  report: could not write {home / REPORT_NAME}: {type(e).__name__}: {str(e)[:200]}"
        ok = False
    return report, ok

"""What the pages' buttons do. Plain functions, no web framework, every side effect behind an
injectable parameter so the whole module is tested with fakes.

Actions that do work take `home` (the app home directory) explicitly and a `log` callable that
receives one line at a time for the page's log pane; the form helpers in this file take only what they need.
Nothing here prints, and nothing here ever writes a password anywhere but the OS credential store.
"""
from __future__ import annotations

import contextlib
import ipaddress
import logging
from dataclasses import dataclass
from datetime import date, datetime
from importlib import metadata
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from .. import config, late_rules, runner, sources

REPORT_KEY = "open-work"
LOGIN_STAMP = "login-ok.txt"
APP_LOG = "app.log"
CONFIG_NAME = "config.toml"
MAX_DAYS = 60

#: What the job pane promises next to the spinner. It said "1-3 minutes", which was true on
#: the maintainer's Linux box and reads as *hung* on the family PC it actually runs on, where
#: a full refresh-and-build measured 8-10 minutes (#40 item 14). Three kids, two sites, a
#: headless Chromium on a shared desktop: honest is "a few", and the ceiling is the number a
#: parent should wait before worrying.
RUN_ESTIMATE = "usually a few minutes, up to ten on a busy PC"


def printer_names(extra: dict) -> list[str]:
    """The printers to offer. `extra["printers"]` is the tests' seam; a host that cannot list
    them offers none, which is a shorter menu and never a failed page."""
    if "printers" in extra:
        return extra["printers"]
    try:
        from ..host import printing
        return printing.list_printers()
    except Exception:  # noqa: BLE001  a printer list is a convenience, never a failure
        return []


def _whole_number(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


@dataclass
class FormValues:
    username: str = ""
    password: str = ""          # blank = keep the stored one
    printer: str = ""           # blank = system default
    days_ahead: int = 14
    overdue_days: int = 14
    nicknames: str = ""         # one "First=Nick" per line
    archive: str = ""
    port: int = 8433
    allow_lan: bool = False
    check_updates: bool = True
    sources_assignments: str = "canvas"   # [sources] assignments: household default
    sources_grades: str = "hac"           # [sources] grades: household default


def _settings_for(home: Path) -> config.Settings:
    s = config.Settings(home=home)
    try:
        config.settings_from_doc(config.load_config_doc(home / CONFIG_NAME), s)
    except config.ConfigError as e:
        raise config.ConfigError(f"{home / CONFIG_NAME}: {e}") from e
    return s


def stored_username(home: Path) -> str:
    return _settings_for(home).username


def load_form(home: Path) -> FormValues:
    s = _settings_for(home)
    rc = s.report_config(REPORT_KEY, "14:00")
    return FormValues(
        username=s.username,
        printer=s.printer,
        days_ahead=_whole_number(rc.options.get("days_ahead")) or 14,
        overdue_days=_whole_number(rc.options.get("overdue_days")) or 14,
        nicknames=format_nicknames(s.nicknames),
        archive=s.sheets_archive,
        port=s.web_port,
        allow_lan=s.web_allow_lan,
        check_updates=s.web_check_updates,
        sources_assignments=s.sources.default.assignments,
        sources_grades=s.sources.default.grades,
    )


def parse_nickname_lines(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for n, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        first, sep, nick = line.partition("=")
        if not sep or not first.strip() or not nick.strip():
            raise ValueError(f"nicknames line {n}: expected First=Nick, got {line!r}")
        out[first.strip()] = nick.strip()
    return out


def format_nicknames(d: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in d.items())


def validate(form: FormValues, stored: str) -> list[str]:
    """Every problem with the form, as one sentence each. Empty means save is allowed."""
    errors: list[str] = []
    user = form.username.strip()
    if not user:
        errors.append("OneLogin username is required.")
    if not form.password and (not stored or user != stored):
        errors.append("Enter the OneLogin password (it is stored in the OS credential store, never in a file).")
    for label, value in (("Days ahead", form.days_ahead), ("Overdue days", form.overdue_days)):
        n = _whole_number(value)
        if n is None or not 1 <= n <= MAX_DAYS:
            errors.append(f"{label} must be a whole number between 1 and {MAX_DAYS}.")
    try:
        parse_nickname_lines(form.nicknames)
    except ValueError as e:
        errors.append(str(e))
    n = _whole_number(form.port)
    if n is None or not 1024 <= n <= 65535:
        errors.append("Port must be a whole number between 1024 and 65535.")
    for label, value in (("Assignment scores", form.sources_assignments), ("Class averages", form.sources_grades)):
        if value not in sources.SOURCES:
            errors.append(f"{label} must come from Canvas or HAC.")
    return errors


@dataclass
class SaveResult:
    ok: bool
    messages: list[str]
    restart_needed: bool = False        # True when [web] port/allow_lan changed against the previous file


def _table(doc: dict, key: str) -> dict:
    """doc[key] as a table, replacing a scalar left by a hand edit."""
    if not isinstance(doc.get(key), dict):
        doc[key] = {}
    return doc[key]


def save(form: FormValues, *, home: Path, log: Callable[[str], None], credstore=None) -> SaveResult:
    """Validate, write config.toml, and store the password if one was typed. The schedule
    itself -- enabled, time, days -- is the Schedules page's alone; this never touches it."""
    if credstore is None:
        from ..host import credentials as credstore
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    errors = validate(form, stored=str(_table(doc, "account").get("username", "")))
    if errors:
        return SaveResult(False, errors)

    user = form.username.strip()
    _table(doc, "account")["username"] = user
    prn = _table(doc, "print")
    prn["printer"], prn["archive"] = form.printer.strip(), form.archive.strip()
    _table(doc, "kids")["nicknames"] = parse_nickname_lines(form.nicknames)
    rep = _table(_table(doc, "reports"), REPORT_KEY)
    rep.update(days_ahead=int(form.days_ahead), overdue_days=int(form.overdue_days))
    # Only the household defaults: the override rules belong to the course pages and the list below.
    doc["sources"] = sources.from_doc(doc).with_default(form.sources_assignments, form.sources_grades).to_doc()

    prev = dict(_table(doc, "web"))
    web = _table(doc, "web")
    web["port"], web["allow_lan"] = int(form.port), bool(form.allow_lan)
    web["check_updates"] = bool(form.check_updates)
    restart_needed = prev.get("port", 8433) != web["port"] or bool(prev.get("allow_lan", False)) != web["allow_lan"]

    messages: list[str] = []
    config.save_config_doc(path, doc)
    log(f"Settings saved to {path}")
    messages.append(f"Settings saved to {path}.")
    if restart_needed:
        msg = "The server address changed; restart Fridge Sheet (or the service) for it to take effect."
        log(msg)
        messages.append(msg)

    if form.password:
        try:
            credstore.write(user, form.password)
        except Exception as e:      # keyring / secret-tool failure; never includes the password
            msg = f"Settings saved, but the password could not be stored: {str(e)[:200]}. Fix that and Save again."
            log(msg)
            messages.append(msg)
            return SaveResult(False, messages)
        log("Password stored in the OS credential store.")
        messages.append("Password stored.")

    return SaveResult(True, messages, restart_needed)


def load_sources(home: Path) -> sources.SourcePrefs:
    return _settings_for(home).sources


def set_source_rule(home: Path, kid: str, course: str, assignments: str | None, grades: str | None) -> None:
    """Add, replace or (both None) remove the one rule for exactly this kid and class."""
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    doc["sources"] = sources.from_doc(doc).with_rule(kid, course, assignments, grades).to_doc()
    config.save_config_doc(path, doc)


def remove_source_rule(home: Path, kid: str, course: str) -> None:
    set_source_rule(home, kid, course, None, None)


@dataclass
class LoginResult:
    ok: bool
    results: dict[str, str | None]       # site -> None (OK) or the error text
    message: str


def check_sites(settings: config.Settings, log: Callable[[str], None]) -> dict[str, str | None]:
    """Sign in headless to Canvas and HAC the way `fridgesheet check` does; the error
    text is site copy or our own message, never a credential."""
    from ..session import browser, ensure_canvas, ensure_hac
    out: dict[str, str | None] = {}
    with browser(settings) as ctx:
        for name, fn in (("Canvas", ensure_canvas), ("HAC", ensure_hac)):
            try:
                fn(ctx, settings)
                out[name] = None
            except Exception as e:  # any failure is a result, not a crash
                out[name] = str(e)[:300]
    return out


def test_login(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
               check=check_sites, now: datetime | None = None) -> LoginResult:
    settings = settings or config.load_settings()
    now = now or datetime.now(ZoneInfo(settings.timezone))
    log("Testing the login to Canvas and Home Access Center (up to a minute)...")
    try:
        with forward_logs(log):
            results = check(settings, log)
    except Exception as e:
        results = {"Login": str(e)[:300]}
    for site, err in results.items():
        log(f"  {site}: {'OK' if err is None else 'FAILED - ' + err}")
    stamp = home / LOGIN_STAMP
    if all(v is None for v in results.values()):
        stamp.write_text(now.isoformat())
        return LoginResult(True, results, "Login OK for " + " and ".join(results) + ".")
    stamp.unlink(missing_ok=True)
    bad = "; ".join(f"{k}: {v}" for k, v in results.items() if v is not None)
    return LoginResult(False, results, f"Login failed ({bad}). Check the username and password, then try again.")


def preview(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
            run=None, opener=None, today: date | None = None, report_key: str = REPORT_KEY,
            refresh: bool = False) -> Path | None:
    """Build today's sheet from the current snapshot -- fast, no live pull -- unless `refresh`
    asks to pull Canvas + HAC first (the "Refresh data first" checkbox next to the button)."""
    from . import db
    from .stores import runs as runstore
    settings = settings or config.load_settings()
    run = run or runner.run
    opener = opener or (lambda p: None)   # the browser links the PDF; nothing opens a viewer on the server
    if refresh:
        log(f"Refreshing Canvas + HAC and building today's sheet ({RUN_ESTIMATE})...")
    else:
        log("Building today's sheet from the last refresh...")
    with forward_logs(log):
        rc = run(report_key, runner.RunOptions(dry_run=True, force=True, notify=False, trigger="web",
                                               no_refresh=not refresh), settings, echo=log)
    # The run itself recorded the exact PDF it built in the `runs` row (runner._record_run,
    # on the dry-run branch too) -- read that back instead of guessing a filename or globbing
    # the day's directory, which sorts by filename and can silently pick up a stale PDF left
    # over from an earlier run instead of the one this run just built.
    pdf = None
    try:
        conn = db.open_db(home)
        try:
            row = runstore.latest_for(conn, report_key)
        finally:
            conn.close()
    except Exception:
        row = None
    if row is not None and row["pdf_path"]:
        candidate = Path(row["pdf_path"])
        if candidate.is_file():
            pdf = candidate
    if rc != 0 or pdf is None:
        if rc == 0:
            log("No sheet was built (see the line above); nothing to open.")
        return None
    opener(pdf)
    return pdf


def print_now(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None, run=None,
              date: str | None = None, report_key: str = REPORT_KEY, refresh: bool = False) -> int:
    """The Reports page's "Print now": paper, now, whatever the schedule says.

    Prints from the current snapshot -- fast, no live pull -- unless `refresh` asks to pull
    Canvas + HAC first (the "Refresh data first" checkbox next to the button).

    `force_print` is why this beats a report whose *schedule* is PDF-only. Without it the run
    built the PDF, printed nothing and recorded the job OK -- a button that says it printed
    and did not.
    """
    settings = settings or config.load_settings()
    run = run or runner.run
    if refresh:
        log(f"Refreshing Canvas + HAC, building and printing today's sheet ({RUN_ESTIMATE})...")
    else:
        log("Building and printing today's sheet from the last refresh...")
    with forward_logs(log):
        return run(report_key, runner.RunOptions(force=True, reprint=True, force_print=True, date=date,
                                                 trigger="web", no_refresh=not refresh), settings, echo=log)


def status_line(home: Path, describe=None) -> str:
    if describe is None:
        from ..host.scheduling import describe
    log_path = home / runner.LOG_NAME
    last = "No runs yet"
    if log_path.is_file():
        lines = [l for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            last = lines[-1]
    try:
        info = describe(REPORT_KEY)
    except Exception:
        return f"{last} · schedule unknown"
    if not info.installed:
        return f"{last} · not scheduled"
    if not info.next_run:
        return f"{last} · scheduled (next run unknown)"
    suffix = "" if info.managed_by == "task-scheduler" else f" ({info.managed_by})"
    return f"{last} · next run {info.next_run}{suffix}"


def late_rules_settings(home: Path) -> late_rules.LateRules:
    """The parsed register for the graphical editor, seeding the file first if this is its
    first touch (never overwriting an existing one)."""
    path = home / "late-rules.toml"
    late_rules.ensure_seed(path)
    return late_rules.load(path)


def late_rules_view(rules: late_rules.LateRules) -> dict:
    """A register as the plain strings the editor's inputs hold -- the same shape a rejected
    submission is redisplayed in, so an invalid Save shows what was typed, not the file on disk."""
    return {
        "default_late_days": str(rules.default.late_days),
        "default_credit": rules.default.credit,
        "quarters": [str(q) for q in rules.quarters],
        "rules": [{
            "kid": r.kid, "course": r.course,
            "mode": "quarter_end" if r.until == "quarter_end" else "days",
            "late_days": "" if r.late_days is None else str(r.late_days),
            "credit": r.credit, "source": r.source,
        } for r in rules.rules],
    }


def no_print_days_view(entries: list[runner.SkipEntry]) -> list[dict]:
    """Entries as the plain strings the editor's inputs hold, for the same reason as `late_rules_view`."""
    return [{"start": e.start.isoformat(), "end": e.end.isoformat() if e.end else "", "note": e.note} for e in entries]


def _parsed_int(label: str, text: str, errors: list[str]) -> int | None:
    try:
        return int(text)
    except (TypeError, ValueError):
        errors.append(f"{label}: enter a whole number of days, not {text!r}.")
        return None


def save_late_rules(home: Path, *, default_late_days: str, default_credit: str, quarter_dates: list[str],
                     rule_kid: list[str], rule_course: list[str], rule_mode: list[str],
                     rule_late_days: list[str], rule_credit: list[str], rule_source: list[str]) -> list[str]:
    """Build a register from the graphical editor's rows, validate it the same way a hand-typed
    file would be, then write. Errors mean nothing was written."""
    import tempfile
    errors: list[str] = []
    default_days = _parsed_int("Default", default_late_days, errors)
    quarters: list[date] = []
    for i, text in enumerate(quarter_dates, start=1):
        if not text:
            continue
        try:
            quarters.append(date.fromisoformat(text))
        except ValueError:
            errors.append(f"Quarter {i}: {text!r} is not a date (yyyy-mm-dd).")
    rules: list[late_rules.Rule] = []
    for i, (kid, course, mode, days_text, credit, source) in enumerate(
            zip(rule_kid, rule_course, rule_mode, rule_late_days, rule_credit, rule_source), start=1):
        if mode == "quarter_end":
            rules.append(late_rules.Rule(kid=kid, course=course, until="quarter_end", late_days=None,
                                         credit=credit, source=source))
        else:
            days = _parsed_int(f"Rule {i}", days_text, errors)
            if days is not None:
                rules.append(late_rules.Rule(kid=kid, course=course, late_days=days, credit=credit, source=source))
    if errors:
        return errors
    text = late_rules.to_toml(late_rules.LateRules(late_rules.Rule(late_days=default_days, credit=default_credit),
                                                    rules, quarters))
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False, encoding="utf-8") as tmp:
        tmp.write(text)
    try:
        late_rules.load(Path(tmp.name))
    except late_rules.LateRulesError as e:
        return [str(e)]
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    path = home / "late-rules.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return []


def no_print_days_settings(home: Path) -> list[runner.SkipEntry]:
    """The parsed skip list for the graphical editor, seeding the file first if this is its
    first touch (never overwriting an existing one)."""
    path = home / "no-print-days.txt"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(runner.SKIP_SEED)
    return runner.parse_skip_entries(path.read_text(encoding="utf-8"))


def save_no_print_days(home: Path, entries: list[runner.SkipEntry]) -> list[str]:
    """Validate, then write. Errors mean nothing was written."""
    errors = [f"Row {i}: the end date is before the start date." for i, e in enumerate(entries, start=1)
              if e.end is not None and e.end < e.start]
    if errors:
        return errors
    path = home / "no-print-days.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(runner.format_skip_entries(entries), encoding="utf-8")
    return []


def _lan_probe() -> str:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))      # no packet is sent; the OS picks the outbound address
        return s.getsockname()[0]


def lan_url(port: int, *, probe=None) -> str | None:
    try:
        ip = (probe or _lan_probe)()
    except OSError:
        return None
    return f"http://{ip}:{port}/" if ip and not ip.startswith("127.") else None


#: Tailscale's own MagicDNS resolver. Connecting a UDP socket to it sends nothing, but makes
#: the OS choose a source address on the tailnet interface -- the same trick `_lan_probe` uses
#: for the house network, pointed somewhere only a tailnet can route to.
_TAILSCALE_RESOLVER = "100.100.100.100"

#: 100.64.0.0/10, the shared-address (CGNAT) range Tailscale assigns from. The probe's answer
#: is only believed when it lands in here: with Tailscale down, the connect either fails or the
#: OS falls back to the default route and hands back the ordinary LAN address, which would
#: otherwise be reported as a tailnet address.
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _tailnet_probe() -> str:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((_TAILSCALE_RESOLVER, 1))
        return s.getsockname()[0]


def tailnet_url(port: int, *, probe=None) -> str | None:
    """This machine's tailnet address, or None when it is not on one.

    Separate from `lan_url` because a machine can be on both at once and `_lan_probe` can only
    ever name one of them -- whichever the default route uses. That single-address assumption
    is what made a tailnet client get a bare 403 with the app running and reachable. #38."""
    try:
        ip = (probe or _tailnet_probe)()
    except OSError:
        return None
    try:
        in_cgnat = ipaddress.ip_address(ip) in _CGNAT
    except ValueError:
        return None
    return f"http://{ip}:{port}/" if in_cgnat else None


def about_text() -> str:
    try:
        version = metadata.version("fridgesheet")
    except metadata.PackageNotFoundError:
        version = "dev"
    return (
        f"Fridge Sheet {version}\n"
        "Prints the kids' open-work sheet from Canvas and Home Access Center.\n"
        "https://github.com/steiner385/fridgesheet (MIT)\n\n"
        "Bundled components: Chromium via Playwright (BSD-3-Clause), SumatraPDF 3.5.2 for printing (GPL-3.0; source at "
        "https://github.com/sumatrapdfreader/sumatrapdf/tree/3.5.2rel), segno for the LAN QR code (BSD-3-Clause), "
        "Python (PSF licence).\n"
        "Everything runs on this computer; the app talks only to OneLogin, Canvas and HAC -- and, once a day, "
        "asks GitHub whether a newer Fridge Sheet exists (nothing is sent; turn it off on this page)."
    )


def run_doctor(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None, run=None) -> bool:
    """The Diagnostics page's Run diagnostics: stream the doctor report into the log pane. A broken config.toml
    must not stop the report from running; it becomes a log line and the default settings are used."""
    from .. import doctor
    if settings is None:
        try:
            settings = config.load_settings()
        except config.ConfigError as e:
            log(f"Settings could not be loaded ({e}); running diagnostics with default settings.")
            settings = config.Settings(home=home)
    run = run or doctor.run
    report, ok = run(settings, home)
    for line in report.splitlines():
        log(line)
    return ok


class _Forward(logging.Handler):
    def __init__(self, log: Callable[[str], None]):
        super().__init__(level=logging.INFO)
        self._log = log

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._log(record.getMessage())
        except Exception:
            pass


@contextlib.contextmanager
def forward_logs(log: Callable[[str], None]):
    """While active, every INFO+ record from the `fridgesheet` loggers also reaches `log`.
    The logger is lowered to INFO for the duration if it was quieter, and restored after."""
    handler = _Forward(log)
    root = logging.getLogger("fridgesheet")
    previous = root.level
    if root.getEffectiveLevel() > logging.INFO:
        root.setLevel(logging.INFO)
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
        handler.close()


@dataclass
class RefreshResult:
    ok: bool
    message: str
    refresh_id: int | None


def refresh(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
            collect=None, now: datetime | None = None, trigger: str = "web") -> RefreshResult:
    """Refresh now: pull Canvas and HAC, ingest the snapshot, record the run. Holds the runner's
    lock so a scheduled print in progress is never pulled out from under. Every failure is a
    result, never an exception -- the page shows it.

    `trigger` is what the run is recorded as: "web" for the Refresh now button, "schedule"
    for the app's own data-refresh task. It is the only thing that differs between them --
    a scheduled refresh is this same collect / ingest / record, under the same lock.
    """
    from .. import collector
    from . import db, ingest
    from .stores import runs as runstore
    settings = settings or config.load_settings()
    collect = collect or collector.collect
    tz = ZoneInfo(settings.timezone)
    started = now or datetime.now(tz)
    lock = runner.Lock(home / runner.LOCK_NAME)
    if not lock.acquire():
        message = "already running (run.lock present); nothing done"
        log("A run is already in progress (run.lock present); try again in a minute.")
        now2 = datetime.now(tz).isoformat()
        try:
            conn = db.open_db(home)
            try:
                runstore.record(conn, "refresh", started.isoformat(), now2, trigger, "FAIL", message)
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001  the database is a passenger here too
            log(f"WARN could not record the run: {e}")
        return RefreshResult(False, message, None)
    outcome, message, refresh_id = "FAIL", "", None
    try:
        log(f"Refreshing Canvas + HAC ({RUN_ESTIMATE})...")
        with forward_logs(log):
            snap = collect(settings)
        bad = {k: v for k, v in (snap.get("sources") or {}).items() if v != "ok"}
        conn = db.open_db(home)
        try:
            r = ingest.record(conn, snap, tz=tz, now=now)
            refresh_id = r.refresh_id
            message = f"refresh {r.refresh_id}: {r.items} new items, {r.observations} changes, {r.grades} grade changes"
            if bad:
                message += "; " + "; ".join(f"{k}: {v}" for k, v in bad.items())
            outcome = "OK" if not bad else "FAIL"
            log(f"ingested {message}")
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001  a failed pull is a result
        message = f"refresh failed: {str(e)[:200]}"
        log(message)
    finally:
        lock.release()
        try:
            conn2 = db.open_db(home)
            try:
                runstore.record(conn2, "refresh", started.isoformat(), datetime.now(tz).isoformat(), trigger, outcome, message)
            finally:
                conn2.close()
        except Exception as e:  # noqa: BLE001  the database is a passenger here too
            log(f"WARN could not record the run: {e}")
    return RefreshResult(outcome == "OK", message, refresh_id)

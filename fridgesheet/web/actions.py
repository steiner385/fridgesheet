"""What the pages' buttons do. Plain functions, no web framework, every side effect behind an
injectable parameter so the whole module is tested with fakes.

Actions that do work take `home` (the app home directory) explicitly and a `log` callable that
receives one line at a time for the page's log pane; the form helpers in this file take only what they need.
Nothing here prints, and nothing here ever writes a password anywhere but the OS credential store.
"""
from __future__ import annotations

import contextlib
import ipaddress
import json
import logging
import socket
import threading
from dataclasses import dataclass
from datetime import date, datetime
from importlib import metadata
from pathlib import Path
from typing import Callable
from urllib.error import URLError
from zoneinfo import ZoneInfo

from .. import config, late_rules, runner, sources
from . import updatepin

REPORT_KEY = "open-work"
LOGIN_STAMP = "login-ok.txt"
APP_LOG = "app.log"
CONFIG_NAME = "config.toml"
MAX_DAYS = 60
#: A shorter PIN is guessable inside the five tries the lockout allows (#145).
MIN_PIN_LENGTH = 4

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
    days_ahead: int = config.DEFAULT_DAYS
    overdue_days: int = config.DEFAULT_DAYS
    nicknames: str = ""         # one "First=Nick" per line
    archive: str = ""
    port: int = 8433
    allow_lan: bool = False
    check_updates: bool = True
    update_pin: str = ""        # write-only, like `password`: blank = keep the stored hash
    clear_update_pin: bool = False        # the "Remove the update PIN" box: drop the stored hash
    has_update_pin: bool = False          # read-only, for the page: whether a hash is stored
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
        days_ahead=config.day_option(rc.options, "days_ahead"),
        overdue_days=config.day_option(rc.options, "overdue_days"),
        nicknames=format_nicknames(s.nicknames),
        archive=s.sheets_archive,
        port=s.web_port,
        allow_lan=s.web_allow_lan,
        check_updates=s.web_check_updates,
        has_update_pin=bool(s.web_update_pin_hash),
        sources_assignments=s.sources.default.assignments,
        sources_grades=s.sources.default.grades,
    )


#: Settings fields the process environment (or the .env `load_settings` reads into it) wins
#: over, and the variable that does it -- the same list `config.load_settings` applies.
ENV_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("printer", "FRIDGESHEET_PRINTER"),
    ("archive", "FRIDGESHEET_SHEETS_ARCHIVE"),
    ("port", "FRIDGESHEET_WEB_PORT"),
    ("nicknames", "FRIDGESHEET_NICKNAMES"),
    ("allow_lan", "FRIDGESHEET_WEB_HOST"),
)


#: The variable pairs that supply the OneLogin login without the credential store, in the
#: order `config.Settings.credentials` tries them: the pair itself, then 1Password references
#: to it. Either pair, complete, means the store is never read -- and so never written here.
CREDENTIAL_ENV: tuple[tuple[str, str], ...] = (
    ("FRIDGESHEET_ONELOGIN_USERNAME", "FRIDGESHEET_ONELOGIN_PASSWORD"),
    ("FRIDGESHEET_OP_USERNAME_REF", "FRIDGESHEET_OP_PASSWORD_REF"),
)


def credentials_from_env(environ: dict | None = None) -> str | None:
    """The username variable of the pair that supplies the login from the environment (or the
    `.env` `load_settings` reads into it), or None when the credential store is the source.

    Half a pair earns nothing: `Settings.credentials` fills the missing half from config.toml
    and the store, so the boxes on the Settings page still matter then (#154)."""
    import os
    env = os.environ if environ is None else environ
    for user_var, pw_var in CREDENTIAL_ENV:
        if env.get(user_var) and env.get(pw_var):
            return user_var
    return None


def env_overrides(environ: dict | None = None) -> dict[str, str]:
    """One sentence per form field the environment overrides, keyed by field name, for the
    Settings page to print beside the box (#148). `load_form` shows config.toml, which is what
    the form edits -- but `config.load_settings` lets these variables win over it, so a parent
    who changed the printer here saw nothing happen and had no way to know why.

    Only a variable that actually changes something earns a note, by the same rules
    `load_settings` applies: a `FRIDGESHEET_WEB_PORT` that is not a number is ignored there,
    an empty `FRIDGESHEET_NICKNAMES` parses to nothing, an empty `FRIDGESHEET_WEB_HOST` is not
    a pin -- while an empty `FRIDGESHEET_PRINTER` *does* override (it means "system default").

    The `password` key is the School login card's note (#154): a login the environment
    supplies never reaches the store, so both boxes are ignored and Save asks for neither.
    The note names the variable, never its value -- that is the password's own."""
    import os
    env = os.environ if environ is None else environ
    out: dict[str, str] = {}
    login_var = credentials_from_env(env)
    if login_var:
        out["password"] = (f"Username and password are supplied by the environment ({login_var}); "
                           "the boxes here are ignored.")
    for field_name, var in ENV_OVERRIDES:
        if var not in env:
            continue
        value = env[var]
        if field_name == "port" and _whole_number(value) is None:
            continue
        if field_name == "nicknames":
            if not config.parse_nicknames(value):
                continue
            out[field_name] = (f"{var}={value} in the environment (.env) is added on top of these, "
                               "and wins where they disagree.")
            continue
        if field_name == "allow_lan" and not value:
            continue
        out[field_name] = f"Set by {var}={value} in the environment (.env); this box is ignored while that is set."
    return out


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


def validate(form: FormValues, stored: str, *, environ: dict | None = None) -> list[str]:
    """Every problem with the form, as one sentence each. Empty means save is allowed.

    The login boxes are only required when the credential store is where the login comes
    from. With `FRIDGESHEET_ONELOGIN_*` (or the 1Password references) in the environment --
    the headless setup, where the keyring is locked -- the store is never read, so demanding
    a password here only to fail storing it kept a parent from saving a printer (#154). A
    password typed anyway still needs a username to be stored under."""
    errors: list[str] = []
    user = form.username.strip()
    if credentials_from_env(environ) is not None:
        if form.password and not user:
            errors.append("OneLogin username is required to store the password under.")
    else:
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
    pin = form.update_pin.strip()
    if pin and len(pin) < MIN_PIN_LENGTH:
        errors.append(f"The update PIN must be at least {MIN_PIN_LENGTH} characters.")
    if pin and form.clear_update_pin:
        errors.append("Type a new update PIN or tick Remove the update PIN, not both.")
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


def save(form: FormValues, *, home: Path, log: Callable[[str], None], credstore=None,
         environ: dict | None = None) -> SaveResult:
    """Validate, write config.toml, and store the password if one was typed. The schedule
    itself -- enabled, time, days -- is the Schedules page's alone; this never touches it.

    The store is only written when a password was typed: with the login supplied by the
    environment (`validate`, #154) both boxes may be blank, and then nothing here goes near
    a keyring that, on the box this matters on, is locked."""
    if credstore is None:
        from ..host import credentials as credstore
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    errors = validate(form, stored=str(_table(doc, "account").get("username", "")), environ=environ)
    if errors:
        return SaveResult(False, errors)

    user = form.username.strip()
    if user:                     # blank only when the environment supplies the login: leave the file's alone
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
    # Write-only, like the password below: a typed PIN is hashed and only the hash is ever
    # written to config.toml; a blank field leaves whatever hash is already stored alone, so
    # saving any other setting can never silently erase the household's update PIN.
    if form.update_pin.strip():
        web["update_pin_hash"] = updatepin.hash_pin(form.update_pin.strip())
    elif form.clear_update_pin:
        # The one way to unset it from the page (#145); the update button goes with it.
        web.pop("update_pin_hash", None)
    restart_needed = prev.get("port", 8433) != web["port"] or bool(prev.get("allow_lan", False)) != web["allow_lan"]

    messages: list[str] = []
    config.save_config_doc(path, doc)
    log(f"Settings saved to {path}")
    messages.append(f"Settings saved to {path}.")
    if restart_needed:
        msg = "The server address changed; restart Fridge Sheet (or the service) for it to take effect."
        log(msg)
        messages.append(msg)
    if form.update_pin.strip():
        log("Update PIN stored.")
        messages.append("Update PIN stored.")
    elif form.clear_update_pin:
        log("Update PIN removed.")
        messages.append("Update PIN removed.")

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
    ok = all(v is None for v in results.values())
    record_login(home, ok, now=now)
    if ok:
        return LoginResult(True, results, "Login OK for " + " and ".join(results) + ".")
    bad = "; ".join(f"{k}: {v}" for k, v in results.items() if v is not None)
    return LoginResult(False, results, f"Login failed ({bad}). Check the username and password, then try again.")


def record_login(home: Path, ok: bool, *, now: datetime | None = None) -> None:
    """Leave `login-ok.txt` after a passing login check, and take it away after a failing
    one. The one place the stamp is written or removed, for both callers that check the
    login -- the web Test login above and `fridgesheet check` (#154): the Schedules page and
    `schedule install` gate on it (`login_passed`), and a terminal-only setup could never
    satisfy that gate while only the button wrote it."""
    stamp = home / LOGIN_STAMP
    if ok:
        stamp.write_text((now or datetime.now().astimezone()).isoformat())
    else:
        stamp.unlink(missing_ok=True)


def login_passed(home: Path) -> bool:
    """Whether a login check has passed since it last failed -- the gate on installing any
    schedule, on the page and at the command line alike."""
    return (home / LOGIN_STAMP).exists()


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


def reprint(*, home: Path, log: Callable[[str], None], settings: config.Settings, run_id: int, pdf: str,
            report_key: str, print_pdf=None, now: datetime | None = None) -> int:
    """The Runs page's Reprint: the PDF that run stored, to the printer, as it is.

    Not a rebuild (#143). Rebuilding "from 9/22" from today's snapshot printed a different
    sheet under 9/22's name, overwrote the file every earlier row linked, and failed outright
    once the snapshot was a day old. The caller (`routes/jobs.py`) has already checked that
    `pdf` is a file under the app's own folders; this prints it, records a `runs` row of its
    own for the report so Runs shows the reprint, and touches nothing under `sheets/`.
    """
    from . import db
    from .stores import runs as runstore
    from .. import reports as registry
    if print_pdf is None:
        from ..host import printing
        print_pdf = printing.print_pdf
    from ..host.printing import PrintError
    tz = ZoneInfo(settings.timezone)
    started = now or datetime.now(tz)
    try:
        title = registry.resolve(report_key, home).title
    except registry.ReportError:
        title = report_key          # a saved report deleted since; the PDF is still the PDF
    # The same resolution the runner prints with and the Runs confirm names (#127).
    printer = settings.printer_for(report_key) or None
    path = Path(pdf)
    day = path.parent.name
    log(f"Printing {path.name} from {day} again on {printer or 'the default printer'}...")
    try:
        job = print_pdf(path, printer, f"fridgesheet {title.lower()} {day} (reprint)")
    except PrintError as e:
        outcome, message, job = "FAIL", f"{e}; PDF kept at {path}", None
    else:
        outcome, message = "OK", f"reprinted run {run_id} job={job} {path}"
    log(message)
    try:
        conn = db.open_db(home)
        try:
            runstore.record(conn, report_key, started.isoformat(), datetime.now(tz).isoformat(), "web", outcome, message,
                            str(path), job)
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001  the database is a passenger here too
        log(f"WARN could not record the run: {e}")
    return 0 if outcome == "OK" else 1


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


def no_print_days_settings(home: Path, problems: list[str] | None = None) -> list[runner.SkipEntry]:
    """The parsed skip list for the graphical editor, seeding the file first if this is its
    first touch (never overwriting an existing one). `problems` collects the lines the editor
    cannot show (`runner.parse_skip_entries`), so the page can say so instead of the next Save
    quietly dropping them (#147)."""
    path = home / runner.SKIP_NAME
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(runner.SKIP_SEED)
    return runner.parse_skip_entries(path.read_text(encoding="utf-8"), problems=problems)


def no_print_days_problems(home: Path) -> list[str]:
    """The lines of no-print-days.txt the app has to ignore, each prefixed with the file name
    so it reads on its own in the page header -- beside a broken late-rules.toml, which
    `AppState.rules` carries there the same way. Nothing when there is no file yet, or when
    it reads clean."""
    path = home / runner.SKIP_NAME
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    return [f"{runner.SKIP_NAME} {p}" for p in runner.skip_day_problems(text)]


def save_no_print_days(home: Path, entries: list[runner.SkipEntry]) -> list[str]:
    """Validate, then write. Errors mean nothing was written."""
    errors = [f"Row {i}: the end date is before the start date." for i, e in enumerate(entries, start=1)
              if e.end is not None and e.end < e.start]
    if errors:
        return errors
    path = home / runner.SKIP_NAME
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
    """Forwards the records logged on the thread that created it -- the job's -- and no other:
    a stalled job still running beside the next one must not write into its transcript (#4)."""
    def __init__(self, log: Callable[[str], None]):
        super().__init__(level=logging.INFO)
        self._log = log
        self._thread = threading.get_ident()

    def emit(self, record: logging.LogRecord) -> None:
        if record.thread != self._thread:
            return
        try:
            self._log(record.getMessage())
        except Exception:
            pass


_FORWARD_LOCK = threading.Lock()
_forwarding = {"depth": 0, "level": logging.NOTSET}


@contextlib.contextmanager
def forward_logs(log: Callable[[str], None]):
    """While active, every INFO+ record this thread logs to the `fridgesheet` loggers also
    reaches `log`. The logger is lowered to INFO while any job forwards, and restored when the
    last one ends -- not when the first does, which silenced a job still running (#4)."""
    handler = _Forward(log)
    root = logging.getLogger("fridgesheet")
    with _FORWARD_LOCK:
        if _forwarding["depth"] == 0:
            _forwarding["level"] = root.level
            if root.getEffectiveLevel() > logging.INFO:
                root.setLevel(logging.INFO)
        _forwarding["depth"] += 1
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
        with _FORWARD_LOCK:
            _forwarding["depth"] -= 1
            if _forwarding["depth"] == 0:
                root.setLevel(_forwarding["level"])
        handler.close()


@dataclass
class RefreshResult:
    ok: bool
    message: str
    refresh_id: int | None


def refresh(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None,
            collect=None, now: datetime | None = None, trigger: str = "web", sleep=None) -> RefreshResult:
    """Refresh now: pull Canvas and HAC, ingest the snapshot, record the run. Holds the runner's
    lock so a scheduled print in progress is never pulled out from under. Every failure is a
    result, never an exception -- the page shows it.

    `trigger` is what the run is recorded as: "web" for the Refresh now button, "schedule"
    for the app's own data-refresh task. A scheduled refresh is this same collect / ingest /
    record under the same lock, with one difference: nobody is watching it, so when a
    scheduled print holds the lock on the same minute it waits (up to
    `runner.LOCK_WAIT_SECONDS`, with `sleep`) rather than recording a FAIL and pulling
    nothing (#121). The button is told at once, as before.
    """
    from .. import collector
    from . import db, ingest
    from .stores import runs as runstore
    settings = settings or config.load_settings()
    collect = collect or collector.collect
    tz = ZoneInfo(settings.timezone)
    started = now or datetime.now(tz)
    lock = runner.Lock(home / runner.LOCK_NAME)
    if trigger == "schedule":
        got = lock.acquire_wait(runner.LOCK_WAIT_SECONDS, sleep=sleep, label=runner.REFRESH_LABEL)
        who = runner.holder_phrase(lock.waited_for)
        if got and lock.waited:
            log(f"waited {lock.waited} s for {who} to finish")
    else:
        got = lock.acquire(label=runner.REFRESH_LABEL)
    if not got:
        if trigger == "schedule":
            message = f"waited {lock.waited} s for {who} to finish and it is still running (run.lock present); nothing pulled"
            log(message)
        else:
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
            if r.note():
                message += "; " + r.note()      # a class carried from an older pull, or not fetched (#140)
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


def self_update(*, home: Path, log: Callable[[str], None], settings, state) -> bool:
    """Download the newest release's installer, prove it against GitHub's own sha256, and hand
    off to it. Returns False having already explained itself on `log`; raising would only reach
    the job worker's generic handler (jobs.Worker._run), which logs the exception type and loses
    the parent-facing sentence `UpdateError` was written to carry.

    Only ever called from the "update" branch of `jobs.Worker._run`, which is only ever reached
    by a job the PIN-gated `POST /settings/update` route started (see `jobs.GATED`) -- there is
    no other way into this function from the web.
    """
    import fridgesheet.host as host
    from ..host import selfupdate, selfupdate_linux
    from . import updates as updatemod
    # Refused before any network call or breadcrumb write -- not left for
    # `selfupdate.spawn_installer`'s dispatcher to discover last, after a 286 MB download
    # has already happened and a `update-pending.json` has already been left behind for
    # `resolve_pending` to find on the next (Linux) start, where no running version will
    # ever match `to_version` and the "did not finish" card can never clear.
    if not host.IS_WINDOWS:
        log(selfupdate_linux.NOT_WINDOWS)
        return False
    try:
        current = updatemod.current_version()
        latest, url, digest, size = updatemod.latest_release(state.extra.get("update_fetch"))
        if not updatemod.newer(latest, current):
            log(f"Already on {current}; nothing to do.")
            return False
        log(f"Downloading Fridge Sheet {latest} ({size // 10**6} MB)...")
        folder = home / "updates"
        # `size` is not decoration: without it `download_verified`'s free-space check is
        # dead code, because it has nothing to compare the free space against.
        installer = selfupdate.download_verified(url, digest, folder / f"FridgeSheet-Setup-{latest}.exe",
                                                 log=log, size=size)
        log_path = folder / f"install-{latest}.log"
        selfupdate.write_pending(home, selfupdate.Pending(
            from_version=current, to_version=latest, started_at=state.now().isoformat(),
            installer=str(installer), log=str(log_path)))
        log("Starting the installer. Fridge Sheet will close and come back on its own.")
        selfupdate.spawn_installer(installer, log_path)
        return True
    except selfupdate.UpdateError as e:
        log(str(e))
        return False
    except (URLError, socket.timeout, json.JSONDecodeError) as e:
        # `updatemod.latest_release` only wraps its own `download_verified`-equivalent
        # failures in `UpdateError`; a network problem reaching GitHub in the first place
        # (no internet -- the single most likely failure in a household this feature is
        # for) or a malformed release JSON escapes as the raw exception instead. Left
        # uncaught, that reaches `jobs.py`'s generic handler as e.g. `URLError: <urlopen
        # error [Errno -2] Name or service not known>` -- exactly the raw traceback string
        # the "one sentence a parent can act on" contract above exists to prevent.
        log(f"Could not reach GitHub to check for an update ({type(e).__name__}). "
            "Check the internet connection and try again later.")
        return False

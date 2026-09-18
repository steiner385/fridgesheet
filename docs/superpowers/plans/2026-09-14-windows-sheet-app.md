# Windows Sheet App, Plan 2 of 3: The Settings App

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the Windows user one window, "Lakota Sheet", to enter their OneLogin account, pick a printer and print time, test the login, preview or print today's sheet, and turn the scheduled run on or off, without a terminal.

**Architecture:** Every button is a plain function in `lakota_grades/app/actions.py` that takes a `log` callable and returns a small result dataclass; those functions are fully tested with fakes for the host adapters and the runner. `lakota_grades/app/gui.py` is a thin tkinter layer that builds widgets, runs each action on a worker thread, and marshals log lines back to the main loop through a queue; it is not unit-tested. `lakota_grades/app/__main__.py` is the PyInstaller entry point: no arguments opens the window, anything else is the normal CLI, and logging goes to `<home>/app.log` because a windowed exe has no stderr.

**Tech Stack:** Python 3.12, tkinter/ttk (ships with CPython; **not installed on the dev box**, so `gui.py` cannot be run here), `logging.handlers.RotatingFileHandler`, the Plan 1 modules `config`, `runner`, `reports`, `session`, `late_rules`, `host.*`.

**Spec:** `docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md`, section 8 (the app), plus the `login-ok.txt` and `app.log` lines in sections 6 and 7 and the error-handling rules in section 11.

## Global Constraints

- `actions.py` must not import tkinter. `gui.py` must contain no business logic: no file writes, no config edits, no subprocesses, only widget code, threads and the queue.
- Every action takes `log: Callable[[str], None]` and never prints; every action takes `home: Path` explicitly (the GUI passes `config.DEFAULT_HOME`) so tests use `tmp_path`.
- No credential is ever written to `config.toml`, `app.log`, `print-sheet.log`, a log pane line, a toast, or an exception message. The password field is cleared after a successful Save.
- `<home>/login-ok.txt` is written only by a passing Test login (ISO timestamp), removed by a failing one, and is what gates installing the scheduled task.
- `<home>/app.log` is a rotating file (1 MB, 3 backups) that receives every `logging` record from the `lakota` loggers; stderr also gets them only when `sys.stderr is not None`.
- The report key the app manages is `"open-work"`; days are the weekdays `["Mon", "Tue", "Wed", "Thu", "Fri"]` unless `config.toml` already lists days, which the app preserves.
- Existing behaviour must survive: the full suite (`env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`, 131 passed at the start of this plan) stays green on Linux and in CI on both runners.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Interfaces this plan builds on (all exist after Plan 1)

| Name | Signature |
|---|---|
| `config.DEFAULT_HOME` | `Path` |
| `config.load_config_doc(path) -> dict`, `config.save_config_doc(path, doc)` | raw TOML round trip; `save` is atomic, 0600 |
| `config.settings_from_doc(doc, s)`, `config.Settings(home=...)`, `Settings.report_config(key, default_time) -> ReportConfig(enabled, time, days, options)` | |
| `config._validate_report_time(key, value)` | raises `ConfigError` unless `HH:MM` |
| `config.WEEKDAYS` | `["Mon", "Tue", "Wed", "Thu", "Fri"]` |
| `config.load_settings() -> Settings` | reads `config.toml` then env |
| `runner.run(report_key, opts: RunOptions, settings, *, now=None, refresh=..., print_pdf=None, toast=None) -> int` | Task 1 adds `echo=None` |
| `runner.RunOptions(dry_run, force, reprint, date, kid, no_refresh, printer, options, notify)` | |
| `runner.LOG_NAME = "print-sheet.log"`, `runner.SKIP_SEED` | |
| `late_rules.ensure_seed(path) -> bool` | |
| `session.browser(settings) -> ctx`, `session.ensure_canvas(ctx, s)`, `session.ensure_hac(ctx, s)` | raise on failure |
| `host.credentials.write(username, password)` | |
| `host.printing.list_printers() -> list[str]`, `default_printer() -> str \| None` | |
| `host.scheduling.install(key, time, days, exe, args, workdir)`, `remove(key)`, `describe(key) -> ScheduleInfo(managed_by, installed, next_run, last_result)`, `command_for(key) -> (exe, args, workdir)` | `install`/`remove` raise `host.NotSupported` on Linux, `host.SchedulingError` on schtasks failure |
| `host.opener.open_file(path)` | Task 4 adds `open_text(path)` |
| `host.IS_WINDOWS`, `host.NotSupported`, `host.SchedulingError` | |

## File map

| Path | Responsibility |
|---|---|
| `lakota_grades/runner.py` (modify) | `_Log` gains an `echo` callback; `run()` gains `echo=None` |
| `lakota_grades/app/__init__.py` (new) | package docstring only |
| `lakota_grades/app/actions.py` (new) | `FormValues`, `load_form`, `validate`, `save`, `test_login`, `preview`, `print_now`, `status_line`, `open_editable`, `about_text`, `forward_logs` |
| `lakota_grades/app/gui.py` (new) | the tkinter window; `run_app() -> int` |
| `lakota_grades/app/__main__.py` (new) | `setup_logging(home)`, `main(argv=None) -> int`; frozen-exe environment |
| `lakota_grades/host/opener.py` (modify) | `open_text(path)` for the two editable files |
| `lakota_grades/cli.py` (modify) | `app` command |
| `README.md` (modify) | one short "The settings window" paragraph |
| `tests/test_runner.py` (modify), `tests/test_app_actions.py` (new), `tests/test_app_main.py` (new), `tests/test_host_notify.py` (modify, opener tests live there) | |

---

### Task 1: Runner log echo

The GUI's log pane must show the runner's own `OK`/`SKIP`/`FAIL` lines as they happen. Today `_Log` prints to stderr when it exists; this adds an optional callback and routes to it instead.

**Files:**
- Modify: `lakota_grades/runner.py` (`_Log`, `run` signature, the `_Log(...)` construction inside `run`)
- Test: `tests/test_runner.py` (append)

**Interfaces:**
- Produces: `runner.run(..., echo: Callable[[str], None] | None = None)`. When `echo` is given, every log line goes to the file and to `echo(line)`, and **not** to stderr. When `echo` is None, behaviour is unchanged (file always; stderr when present).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_runner.py`:

```python
def test_echo_receives_every_log_line_and_stderr_is_quiet(env, capsys):
    s, calls, refresh, print_pdf, toast = env
    lines = []
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast, echo=lines.append) == 0
    assert len(lines) == 1 and " OK " in lines[0] and "dry-run" in lines[0]
    assert lines[0] + "\n" == (s.home / runner.LOG_NAME).read_text()
    assert capsys.readouterr().err == ""
```

- [ ] **Step 2: Run to verify it fails**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_runner.py -q -k echo`
Expected: FAIL with `TypeError: run() got an unexpected keyword argument 'echo'`.

- [ ] **Step 3: Implement**

In `lakota_grades/runner.py`, change `_Log`:

```python
class _Log:
    """One line per run, always to the log file, and to `echo` when given (the app's log
    pane) or else to stderr when the process has one (a windowed exe has sys.stderr = None)."""

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
```

Change the `run` signature to end `..., print_pdf=None, toast=None, echo=None) -> int:` and the construction to `log = _Log(home / LOG_NAME, now, report_key, echo)`. Update the docstring's one-line mention if there is one.

- [ ] **Step 4: Run the suite**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q`
Expected: 132 passed.

- [ ] **Step 5: Commit**

```bash
git add lakota_grades/runner.py tests/test_runner.py
git commit -m "runner: optional echo callback for log lines (the app's log pane)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `actions.py` part 1: the form, loading it, validating it

**Files:**
- Create: `lakota_grades/app/__init__.py`, `lakota_grades/app/actions.py`
- Test: `tests/test_app_actions.py`

**Interfaces:**
- Produces, in `lakota_grades.app.actions`:
  - `REPORT_KEY = "open-work"`, `LOGIN_STAMP = "login-ok.txt"`, `APP_LOG = "app.log"`, `CONFIG_NAME = "config.toml"`
  - `FormValues(username="", password="", printer="", time="14:00", days_ahead=14, overdue_days=14, nicknames="", archive="", scheduled=False)` — `nicknames` is the multi-line text, one `First=Nick` per line; `printer=""` means system default; `password=""` means keep the stored one.
  - `load_form(home: Path) -> FormValues` (raises `config.ConfigError` on a broken file)
  - `stored_username(home: Path) -> str`
  - `parse_nickname_lines(text: str) -> dict[str, str]` (raises `ValueError` naming the bad line)
  - `format_nicknames(d: dict[str, str]) -> str`
  - `validate(form: FormValues, stored: str) -> list[str]` (empty list = valid)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app_actions.py
"""The settings app's actions, with every host adapter and the runner faked."""
from __future__ import annotations

from pathlib import Path

import pytest

from lakota_grades import config
from lakota_grades.app import actions


def test_load_form_defaults_when_no_config(tmp_path):
    f = actions.load_form(tmp_path)
    assert f == actions.FormValues()
    assert actions.stored_username(tmp_path) == ""


def test_load_form_reads_every_field(tmp_path):
    config.save_config_doc(tmp_path / "config.toml", {
        "account": {"username": "p@x.com"},
        "print": {"printer": "Office", "archive": "D:/Drive/Sheets"},
        "kids": {"nicknames": {"Alex": "Al", "Katherine": "Kate"}},
        "reports": {"open-work": {"enabled": True, "time": "15:30", "days": ["Mon", "Wed"], "days_ahead": 7, "overdue_days": 21}},
    })
    f = actions.load_form(tmp_path)
    assert f == actions.FormValues(username="p@x.com", password="", printer="Office", time="15:30", days_ahead=7, overdue_days=21,
                                   nicknames="Alex=Al\nKatherine=Kate", archive="D:/Drive/Sheets", scheduled=True)
    assert actions.stored_username(tmp_path) == "p@x.com"


def test_load_form_surfaces_a_broken_config(tmp_path):
    (tmp_path / "config.toml").write_text("[print\n")
    with pytest.raises(config.ConfigError, match="config.toml"):
        actions.load_form(tmp_path)


def test_nickname_lines_round_trip_and_reject_garbage():
    assert actions.parse_nickname_lines(" Alex = Al \n\nKatherine=Kate\n") == {"Alex": "Al", "Katherine": "Kate"}
    assert actions.format_nicknames({"Alex": "Al", "Katherine": "Kate"}) == "Alex=Al\nKatherine=Kate"
    with pytest.raises(ValueError, match="line 2"):
        actions.parse_nickname_lines("Alex=Al\nnot a pair\n")
    with pytest.raises(ValueError, match="line 1"):
        actions.parse_nickname_lines("=Al")


def _form(**over) -> actions.FormValues:
    d = dict(username="p@x.com", password="hunter2", printer="", time="14:00", days_ahead=14, overdue_days=14, nicknames="", archive="", scheduled=True)
    d.update(over)
    return actions.FormValues(**d)


def test_validate_accepts_a_good_form():
    assert actions.validate(_form(), stored="") == []
    assert actions.validate(_form(password=""), stored="p@x.com") == []      # keep stored password


def test_validate_requires_username_and_a_password_for_a_new_username():
    assert any("username" in e.lower() for e in actions.validate(_form(username="  "), stored=""))
    assert any("password" in e.lower() for e in actions.validate(_form(password=""), stored=""))
    assert any("password" in e.lower() for e in actions.validate(_form(username="new@x.com", password=""), stored="old@x.com"))


def test_validate_checks_time_ranges_and_nicknames():
    assert any("HH:MM" in e for e in actions.validate(_form(time="2 PM"), stored=""))
    assert any("HH:MM" in e for e in actions.validate(_form(time="9:00"), stored=""))
    assert any("days ahead" in e.lower() for e in actions.validate(_form(days_ahead=0), stored=""))
    assert any("overdue" in e.lower() for e in actions.validate(_form(overdue_days=61), stored=""))
    assert any("line 1" in e for e in actions.validate(_form(nicknames="bad"), stored=""))
    errs = actions.validate(_form(username="", time="x", days_ahead=99), stored="")
    assert len(errs) == 3            # one message per problem, none swallowed
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_actions.py -q`
Expected: FAIL at import (`No module named 'lakota_grades.app'`).

- [ ] **Step 3: Create the package and the first half of `actions.py`**

```python
# lakota_grades/app/__init__.py
"""The settings window (Plan 2). `actions` holds every button's logic, tested without a
display; `gui` is the tkinter layer; `__main__` is the frozen exe's entry point."""
```

```python
# lakota_grades/app/actions.py
"""What the buttons do. Plain functions, no tkinter, every side effect behind an
injectable parameter so the whole module is tested with fakes.

Every action takes `home` (the app home directory) explicitly and a `log` callable that
receives one line at a time for the window's log pane. Nothing here prints, and nothing
here ever writes a password anywhere but the OS credential store.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .. import config

REPORT_KEY = "open-work"
LOGIN_STAMP = "login-ok.txt"
APP_LOG = "app.log"
CONFIG_NAME = "config.toml"
MAX_DAYS = 60


@dataclass
class FormValues:
    username: str = ""
    password: str = ""          # blank = keep the stored one
    printer: str = ""           # blank = system default
    time: str = "14:00"
    days_ahead: int = 14
    overdue_days: int = 14
    nicknames: str = ""         # one "First=Nick" per line
    archive: str = ""
    scheduled: bool = False


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
        time=rc.time or "14:00",
        days_ahead=int(rc.options.get("days_ahead") or 14),
        overdue_days=int(rc.options.get("overdue_days") or 14),
        nicknames=format_nicknames(s.nicknames),
        archive=s.sheets_archive,
        scheduled=rc.enabled,
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
    try:
        config._validate_report_time(REPORT_KEY, form.time)
    except config.ConfigError:
        errors.append(f"Print time must be HH:MM in 24-hour form, got {form.time!r}.")
    if not 1 <= int(form.days_ahead) <= MAX_DAYS:
        errors.append(f"Days ahead must be between 1 and {MAX_DAYS}.")
    if not 1 <= int(form.overdue_days) <= MAX_DAYS:
        errors.append(f"Overdue days must be between 1 and {MAX_DAYS}.")
    try:
        parse_nickname_lines(form.nicknames)
    except ValueError as e:
        errors.append(str(e))
    return errors
```

- [ ] **Step 4: Run the tests**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_actions.py -q`
Expected: 7 passed. Then the full suite: 139 passed.

- [ ] **Step 5: Commit**

```bash
git add lakota_grades/app tests/test_app_actions.py
git commit -m "app.actions: form values, load_form, validate

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: `actions.save`: write config, store the password, sync the schedule

**Files:**
- Modify: `lakota_grades/app/actions.py` (append)
- Test: `tests/test_app_actions.py` (append)

**Interfaces:**
- Consumes: Task 2's `FormValues`, `validate`, `parse_nickname_lines`, `stored_username`; `config.load_config_doc/save_config_doc/WEEKDAYS`; `host.credentials.write`; `host.scheduling.install/remove/command_for`; `host.NotSupported`, `host.SchedulingError`.
- Produces: `SaveResult(ok: bool, messages: list[str], schedule_installed: bool | None)` and
  `save(form, *, home: Path, log, credstore=None, scheduling=None) -> SaveResult`. `credstore` needs `.write(username, password)`; `scheduling` needs `.install(key, time, days, exe, args, workdir)`, `.remove(key)`, `.command_for(key)`. `schedule_installed` is `True` after a successful install, `False` when removed, not installed for lack of a login stamp, or install failed, and `None` when the host does not manage schedules (Linux).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_actions.py`:

```python
class _Cred:
    def __init__(self):
        self.written = []

    def write(self, username, password):
        self.written.append((username, password))


class _Sched:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def command_for(self, key):
        return ("C:/x.exe", f"run {key}", "C:/")

    def install(self, key, time, days, exe, args, workdir):
        if self.fail:
            raise self.fail
        self.calls.append(("install", key, time, list(days), exe, args, workdir))

    def remove(self, key):
        if self.fail:
            raise self.fail
        self.calls.append(("remove", key))


def _save(tmp_path, form, **kw):
    lines = []
    cred, sched = kw.pop("cred", _Cred()), kw.pop("sched", _Sched())
    r = actions.save(form, home=tmp_path, log=lines.append, credstore=cred, scheduling=sched, **kw)
    return r, lines, cred, sched


def test_save_rejects_an_invalid_form_and_writes_nothing(tmp_path):
    r, lines, cred, sched = _save(tmp_path, _form(username=""))
    assert not r.ok and any("username" in m.lower() for m in r.messages)
    assert not (tmp_path / "config.toml").exists() and cred.written == [] and sched.calls == []


def test_save_writes_config_stores_password_and_defers_schedule_until_login_ok(tmp_path):
    r, lines, cred, sched = _save(tmp_path, _form(printer="Office", nicknames="Alex=Al", archive="D:/S", days_ahead=7))
    assert r.ok and r.schedule_installed is False
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["account"] == {"username": "p@x.com"}
    assert doc["print"] == {"printer": "Office", "archive": "D:/S"}
    assert doc["kids"] == {"nicknames": {"Alex": "Al"}}
    assert doc["reports"]["open-work"] == {"enabled": True, "time": "14:00", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "days_ahead": 7, "overdue_days": 14}
    assert cred.written == [("p@x.com", "hunter2")]
    assert sched.calls == []
    assert any("Test login" in m for m in r.messages)
    assert "hunter2" not in " ".join(lines + r.messages) and "hunter2" not in (tmp_path / "config.toml").read_text()


def test_save_installs_the_schedule_once_login_ok_exists_and_preserves_unknown_keys(tmp_path):
    (tmp_path / actions.LOGIN_STAMP).write_text("2026-09-14T12:00:00")
    config.save_config_doc(tmp_path / "config.toml", {"account": {"username": "p@x.com"}, "extra": {"keep": 1},
                                                      "reports": {"open-work": {"days": ["Mon", "Wed"], "custom": "yes"}}})
    r, lines, cred, sched = _save(tmp_path, _form(password="", time="15:30"))
    assert r.ok and r.schedule_installed is True
    assert sched.calls == [("install", "open-work", "15:30", ["Mon", "Wed"], "C:/x.exe", "run open-work", "C:/")]
    assert cred.written == []                                   # blank password = keep the stored one
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["extra"] == {"keep": 1} and doc["reports"]["open-work"]["custom"] == "yes"
    assert any("15:30" in m for m in r.messages)


def test_save_with_schedule_off_removes_the_task(tmp_path):
    (tmp_path / actions.LOGIN_STAMP).write_text("x")
    r, lines, cred, sched = _save(tmp_path, _form(scheduled=False))
    assert r.ok and r.schedule_installed is False and sched.calls == [("remove", "open-work")]
    assert config.load_config_doc(tmp_path / "config.toml")["reports"]["open-work"]["enabled"] is False


def test_save_reports_scheduler_failures_but_keeps_the_config(tmp_path):
    from lakota_grades.host import NotSupported, SchedulingError
    (tmp_path / actions.LOGIN_STAMP).write_text("x")
    r, *_ = _save(tmp_path, _form(), sched=_Sched(fail=SchedulingError("Access is denied")))
    assert r.ok and r.schedule_installed is False and any("Access is denied" in m for m in r.messages)
    assert (tmp_path / "config.toml").exists()
    r, *_ = _save(tmp_path, _form(password=""), sched=_Sched(fail=NotSupported("managed by systemd")))
    assert r.ok and r.schedule_installed is None and any("systemd" in m for m in r.messages)


def test_save_tolerates_scalar_sections_in_an_existing_config(tmp_path):
    (tmp_path / "config.toml").write_text('print = "oops"\naccount = 5\n')
    r, *_ = _save(tmp_path, _form())
    assert r.ok
    doc = config.load_config_doc(tmp_path / "config.toml")
    assert doc["print"]["printer"] == "" and doc["account"]["username"] == "p@x.com"
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_actions.py -q -k save`
Expected: FAIL with `AttributeError: module ... has no attribute 'save'`.

- [ ] **Step 3: Implement `save`**

Append to `lakota_grades/app/actions.py` (add `from typing import Callable` and `from .. import host` to the imports):

```python
@dataclass
class SaveResult:
    ok: bool
    messages: list[str]
    schedule_installed: bool | None     # None = this host does not manage schedules


def _table(doc: dict, key: str) -> dict:
    """doc[key] as a table, replacing a scalar left by a hand edit."""
    if not isinstance(doc.get(key), dict):
        doc[key] = {}
    return doc[key]


def save(form: FormValues, *, home: Path, log: Callable[[str], None], credstore=None, scheduling=None) -> SaveResult:
    """Validate, write config.toml, store the password if one was typed, then make the
    scheduled task match the checkbox. A scheduler failure never loses the saved settings."""
    if credstore is None:
        from ..host import credentials as credstore
    if scheduling is None:
        from ..host import scheduling
    path = home / CONFIG_NAME
    doc = config.load_config_doc(path)
    errors = validate(form, stored=str(_table(doc, "account").get("username", "")))
    if errors:
        return SaveResult(False, errors, None)

    user = form.username.strip()
    _table(doc, "account")["username"] = user
    prn = _table(doc, "print")
    prn["printer"], prn["archive"] = form.printer.strip(), form.archive.strip()
    _table(doc, "kids")["nicknames"] = parse_nickname_lines(form.nicknames)
    rep = _table(_table(doc, "reports"), REPORT_KEY)
    rep.update(enabled=bool(form.scheduled), time=form.time, days_ahead=int(form.days_ahead), overdue_days=int(form.overdue_days))
    days = rep.get("days") if isinstance(rep.get("days"), list) and rep.get("days") else list(config.WEEKDAYS)
    rep["days"] = [str(d) for d in days]

    messages: list[str] = []
    if form.password:
        credstore.write(user, form.password)
        log("Password stored in the OS credential store.")
        messages.append("Password stored.")
    config.save_config_doc(path, doc)
    log(f"Settings saved to {path}")
    messages.append(f"Settings saved to {path}.")

    installed: bool | None = False
    try:
        if form.scheduled:
            if not (home / LOGIN_STAMP).exists():
                messages.append("Scheduled printing is on, but run Test login first; the schedule is installed on the next Save after a passing test.")
            else:
                exe, args, workdir = scheduling.command_for(REPORT_KEY)
                scheduling.install(REPORT_KEY, form.time, rep["days"], exe, args, workdir)
                installed = True
                messages.append(f"Scheduled: {', '.join(rep['days'])} at {form.time}.")
        else:
            scheduling.remove(REPORT_KEY)
            messages.append("Scheduled printing is off.")
    except host.NotSupported as e:
        installed = None
        messages.append(str(e))
    except host.SchedulingError as e:
        installed = False
        messages.append(f"Settings saved, but the schedule could not be changed: {e}")
    for m in messages[-1:]:
        log(m)
    return SaveResult(True, messages, installed)
```

- [ ] **Step 4: Run the tests and the suite**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_actions.py -q` then the full suite.
Expected: 13 passed in the file; 145 passed overall.

- [ ] **Step 5: Commit**

```bash
git add lakota_grades/app/actions.py tests/test_app_actions.py
git commit -m "app.actions.save: write config.toml, store the password, sync the scheduled task

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The Run-tab actions: Test login, Preview, Print now, status line, editable files, About

**Files:**
- Modify: `lakota_grades/app/actions.py` (append)
- Modify: `lakota_grades/host/opener.py` (add `open_text`)
- Test: `tests/test_app_actions.py` (append), `tests/test_host_notify.py` (append; the opener tests live there)

**Interfaces:**
- Consumes: `runner.run(..., echo=)` (Task 1), `runner.RunOptions`, `runner.LOG_NAME`, `runner.SKIP_SEED`, `late_rules.ensure_seed`, `session.browser/ensure_canvas/ensure_hac`, `host.scheduling.describe`, `host.opener.open_file`.
- Produces:
  - `host.opener.open_text(path: Path, popen=subprocess.Popen) -> None` — Windows: `notepad.exe <path>`; Linux: same viewer rule as `open_file` (`xdg-open`), detached.
  - `actions.check_sites(settings, log) -> dict[str, str | None]` — `{"Canvas": None, "HAC": "error text"}`; `None` means OK. Real implementation; tests inject a fake.
  - `actions.LoginResult(ok: bool, results: dict[str, str | None], message: str)`
  - `actions.test_login(*, home, log, settings=None, check=check_sites, now=None) -> LoginResult` — writes `<home>/login-ok.txt` (ISO timestamp) on success, deletes it on failure.
  - `actions.preview(*, home, log, settings=None, run=None, opener=None, today=None) -> Path | None` — dry run with `force`, `notify=False`; returns the PDF path and opens it, or `None` on failure.
  - `actions.print_now(*, home, log, settings=None, run=None) -> int` — `force=True, reprint=True`.
  - `actions.status_line(home, describe=None) -> str`
  - `actions.open_editable(home, name: str, opener=None) -> Path` — `name` is `"late-rules.toml"` or `"no-print-days.txt"`; seeds the file if missing, then opens it in a text editor.
  - `actions.about_text() -> str`
  - `actions.forward_logs(log)` — context manager that attaches a `logging.Handler` to the `"lakota"` logger and forwards `record.getMessage()` to `log` for the duration.

- [ ] **Step 1: Write the failing opener test**

Append to `tests/test_host_notify.py`:

```python
def test_open_text_uses_notepad_on_windows_and_a_viewer_on_linux(monkeypatch):
    seen = []
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    opener.open_text(Path("C:/h/late-rules.toml"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    assert seen[0][0] == ["notepad.exe", str(Path("C:/h/late-rules.toml"))]
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    monkeypatch.setattr(opener.shutil, "which", lambda n: "/usr/bin/xdg-open" if n == "xdg-open" else None)
    opener.open_text(Path("/h/late-rules.toml"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    assert seen[1][0] == ["/usr/bin/xdg-open", "/h/late-rules.toml"] and seen[1][1]["start_new_session"] is True
```

- [ ] **Step 2: Write the failing action tests**

Append to `tests/test_app_actions.py`:

```python
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from lakota_grades import runner
from lakota_grades.config import Settings
from lakota_grades.host import ScheduleInfo

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 14, 14, 5, tzinfo=TZ)


def test_test_login_writes_the_stamp_on_success_and_removes_it_on_failure(tmp_path):
    lines = []
    ok = actions.test_login(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path),
                            check=lambda s, log: {"Canvas": None, "HAC": None}, now=NOW)
    assert ok.ok and ok.results == {"Canvas": None, "HAC": None} and "OK" in ok.message
    assert (tmp_path / actions.LOGIN_STAMP).read_text() == NOW.isoformat()
    assert any("Canvas: OK" in l for l in lines) and any("HAC: OK" in l for l in lines)
    bad = actions.test_login(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path),
                             check=lambda s, log: {"Canvas": None, "HAC": "LoginRequired: OneLogin did not redirect"}, now=NOW)
    assert not bad.ok and "HAC" in bad.message and "did not redirect" in bad.message
    assert not (tmp_path / actions.LOGIN_STAMP).exists()


def test_test_login_treats_an_exception_from_the_checker_as_failure(tmp_path):
    def boom(s, log):
        raise RuntimeError("No credentials available. Run set-credentials")
    r = actions.test_login(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), check=boom, now=NOW)
    assert not r.ok and "No credentials" in r.message and not (tmp_path / actions.LOGIN_STAMP).exists()


def test_preview_runs_a_forced_dry_run_and_opens_the_pdf(tmp_path):
    seen, opened, lines = {}, [], []

    def fake_run(key, opts, settings, **kw):
        seen["key"], seen["opts"], seen["echo"] = key, opts, kw.get("echo")
        kw["echo"]("2026-09-14 14:05:00 OK    open-work dry-run built x")
        return 0

    log = lines.append          # one bound method, so the identity check below is meaningful
    pdf = actions.preview(home=tmp_path, log=log, settings=Settings(home=tmp_path), run=fake_run, opener=opened.append, today=NOW.date())
    assert pdf == tmp_path / "sheets" / "2026-09-14" / "sheet.pdf" and opened == [pdf]
    assert seen["key"] == "open-work" and seen["opts"] == runner.RunOptions(dry_run=True, force=True, notify=False)
    assert seen["echo"] is log and any("dry-run built" in l for l in lines)
    assert actions.preview(home=tmp_path, log=log, settings=Settings(home=tmp_path), run=lambda *a, **k: 1, opener=opened.append, today=NOW.date()) is None
    assert len(opened) == 1


def test_print_now_forces_a_reprint(tmp_path):
    seen = {}

    def fake_run(key, opts, settings, **kw):
        seen["opts"] = opts
        return 0

    assert actions.print_now(home=tmp_path, log=lambda l: None, settings=Settings(home=tmp_path), run=fake_run) == 0
    assert seen["opts"] == runner.RunOptions(force=True, reprint=True)


def test_status_line_reports_last_run_and_next_run(tmp_path):
    assert actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("task-scheduler", False, None, None)) == "No runs yet · not scheduled"
    (tmp_path / runner.LOG_NAME).write_text("old line\n2026-09-14 14:05:00 OK    open-work printed job=1\n")
    s = actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("task-scheduler", True, "9/15/2026 2:00:00 PM", "0"))
    assert s == "2026-09-14 14:05:00 OK    open-work printed job=1 · next run 9/15/2026 2:00:00 PM"
    s = actions.status_line(tmp_path, describe=lambda k: ScheduleInfo("systemd", True, "Tue 2026-09-15 14:00:00 EDT", None))
    assert s.endswith("· next run Tue 2026-09-15 14:00:00 EDT (systemd)")


def test_open_editable_seeds_then_opens(tmp_path):
    opened = []
    p = actions.open_editable(tmp_path, "late-rules.toml", opener=opened.append)
    assert p == tmp_path / "late-rules.toml" and p.read_text().startswith("# Late-work rules") and opened == [p]
    p2 = actions.open_editable(tmp_path, "no-print-days.txt", opener=opened.append)
    assert p2.read_text() == runner.SKIP_SEED and opened == [p, p2]
    p.write_text("edited")
    actions.open_editable(tmp_path, "late-rules.toml", opener=opened.append)
    assert p.read_text() == "edited"                      # never overwritten
    with pytest.raises(ValueError):
        actions.open_editable(tmp_path, "config.toml", opener=opened.append)


def test_about_text_names_version_repo_and_licences():
    t = actions.about_text()
    assert "Lakota Sheet" in t and "github.com/steiner385/fridgesheet" in t
    assert "SumatraPDF" in t and "Chromium" in t and ("0.2" in t or "dev" in t)


def test_forward_logs_streams_lakota_records_only_while_active():
    lines = []
    lg = logging.getLogger("lakota.session")
    lg.setLevel(logging.INFO)
    with actions.forward_logs(lines.append):
        lg.info("OneLogin login page detected; signing in")
        logging.getLogger("other").info("not ours")
    lg.info("after")
    assert lines == ["OneLogin login page detected; signing in"]
```

- [ ] **Step 3: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_actions.py tests/test_host_notify.py -q`
Expected: the new tests FAIL with `AttributeError` (`open_text`, `test_login`, ...).

- [ ] **Step 4: Add `open_text` to the opener**

Append to `lakota_grades/host/opener.py`:

```python
def open_text(path: Path, popen=subprocess.Popen) -> None:
    """Open a plain-text settings file in an editor. Windows has no association for .toml,
    so Notepad is named explicitly; Linux goes through the desktop's opener."""
    if host.IS_WINDOWS:
        popen(["notepad.exe", str(path)], creationflags=host.CREATE_NO_WINDOW)
        return
    viewer = shutil.which("xdg-open")
    if not viewer:
        raise RuntimeError("no text editor found (xdg-open)")
    popen([viewer, path.as_posix()], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
```

- [ ] **Step 5: Implement the Run-tab actions**

Append to `lakota_grades/app/actions.py` (imports to add at the top: `import contextlib`, `import logging`, `from datetime import date, datetime`, `from importlib import metadata`, `from zoneinfo import ZoneInfo`, `from .. import late_rules, runner`):

```python
@dataclass
class LoginResult:
    ok: bool
    results: dict[str, str | None]       # site -> None (OK) or the error text
    message: str


def check_sites(settings: config.Settings, log: Callable[[str], None]) -> dict[str, str | None]:
    """Sign in headless to Canvas and HAC the way `lakota-grades check` does; the error
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
            run=None, opener=None, today: date | None = None) -> Path | None:
    settings = settings or config.load_settings()
    run = run or runner.run
    if opener is None:
        from ..host.opener import open_file as opener
    today = today or datetime.now(ZoneInfo(settings.timezone)).date()
    log("Refreshing Canvas + HAC and building today's sheet (1-3 minutes)...")
    with forward_logs(log):
        rc = run(REPORT_KEY, runner.RunOptions(dry_run=True, force=True, notify=False), settings, echo=log)
    if rc != 0:
        return None
    pdf = home / "sheets" / today.isoformat() / "sheet.pdf"
    opener(pdf)
    return pdf


def print_now(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None, run=None) -> int:
    settings = settings or config.load_settings()
    run = run or runner.run
    log("Refreshing Canvas + HAC, building and printing today's sheet (1-3 minutes)...")
    with forward_logs(log):
        return run(REPORT_KEY, runner.RunOptions(force=True, reprint=True), settings, echo=log)


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
    suffix = "" if info.managed_by == "task-scheduler" else f" ({info.managed_by})"
    return f"{last} · next run {info.next_run}{suffix}"


EDITABLE = {"late-rules.toml", "no-print-days.txt"}


def open_editable(home: Path, name: str, opener=None) -> Path:
    """Seed the file if it does not exist (never overwrite), then open it in a text editor."""
    if name not in EDITABLE:
        raise ValueError(f"not an editable settings file: {name}")
    if opener is None:
        from ..host.opener import open_text as opener
    path = home / name
    if name == "late-rules.toml":
        late_rules.ensure_seed(path)
    elif not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(runner.SKIP_SEED)
    opener(path)
    return path


def about_text() -> str:
    try:
        version = metadata.version("lakota-grades-mcp")
    except metadata.PackageNotFoundError:
        version = "dev"
    return (
        f"Lakota Sheet {version}\n"
        "Prints the kids' open-work sheet from Canvas and Home Access Center.\n"
        "https://github.com/steiner385/fridgesheet (MIT)\n\n"
        "Bundled components: Chromium via Playwright (BSD-3-Clause), SumatraPDF for printing (GPL-3.0; source at "
        "https://www.sumatrapdfreader.org), Python and Tk (PSF / Tcl-Tk licences).\n"
        "Everything runs on this computer; the app talks only to OneLogin, Canvas and HAC."
    )


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
    """While active, every INFO+ record from the `lakota` loggers also reaches `log`."""
    handler = _Forward(log)
    root = logging.getLogger("lakota")
    root.addHandler(handler)
    try:
        yield
    finally:
        root.removeHandler(handler)
```

- [ ] **Step 6: Run the tests and the suite**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_actions.py tests/test_host_notify.py -q` then the full suite.
Expected: all pass; 154 passed overall.

- [ ] **Step 7: Commit**

```bash
git add lakota_grades/app/actions.py lakota_grades/host/opener.py tests/test_app_actions.py tests/test_host_notify.py
git commit -m "app.actions: test login (login-ok.txt), preview, print now, status line, editable files, about

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 5: The entry point: `app/__main__.py`, `app.log`, and the `app` command

**Files:**
- Create: `lakota_grades/app/__main__.py`
- Modify: `lakota_grades/cli.py` (add `cmd_app` and the `app` parser)
- Test: `tests/test_app_main.py`

**Interfaces:**
- Consumes: `config.DEFAULT_HOME`, `actions.APP_LOG`, `cli.main(argv)` (which calls `sys.exit`), and `gui.run_app() -> int` (Task 6; faked here).
- Produces:
  - `app.__main__.frozen_environment(environ=os.environ, executable=None) -> None` — when `sys.frozen` is true, sets `PLAYWRIGHT_BROWSERS_PATH` to `<exe folder>/ms-playwright` unless already set.
  - `app.__main__.setup_logging(home: Path, stderr=sys.stderr) -> None` — root logger at INFO; `RotatingFileHandler(home/app.log, maxBytes=1_000_000, backupCount=3, encoding="utf-8")`; a `StreamHandler(stderr)` only when `stderr is not None`; idempotent (calling twice does not double the handlers).
  - `app.__main__.main(argv=None) -> int` — no args → `gui.run_app()`; else → `cli.main(argv)`, translating its `SystemExit` into the return code.
  - `cli app` → `cmd_app`: imports `gui.run_app` lazily; a missing tkinter prints one line to stderr and returns 2.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_app_main.py
"""The frozen-exe entry point: environment, app.log, and dispatch to the GUI or the CLI."""
from __future__ import annotations

import logging
import logging.handlers
import sys
import types

import pytest

from lakota_grades import cli
from lakota_grades.app import __main__ as appmain
from lakota_grades.app import actions


@pytest.fixture(autouse=True)
def _clean_root_logger():
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()


def test_frozen_environment_points_playwright_at_the_bundle(monkeypatch, tmp_path):
    env = {}
    monkeypatch.delattr(sys, "frozen", raising=False)
    appmain.frozen_environment(environ=env, executable=str(tmp_path / "LakotaSheet.exe"))
    assert env == {}
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    appmain.frozen_environment(environ=env, executable=str(tmp_path / "LakotaSheet.exe"))
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(tmp_path / "ms-playwright")
    env["PLAYWRIGHT_BROWSERS_PATH"] = "custom"
    appmain.frozen_environment(environ=env, executable=str(tmp_path / "LakotaSheet.exe"))
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == "custom"


def test_setup_logging_writes_app_log_and_skips_stderr_when_absent(tmp_path):
    appmain.setup_logging(tmp_path, stderr=None)
    appmain.setup_logging(tmp_path, stderr=None)          # idempotent
    root = logging.getLogger()
    files = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(files) == 1 and files[0].baseFilename == str(tmp_path / actions.APP_LOG)
    assert not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in root.handlers)
    logging.getLogger("lakota.test").info("hello app.log")
    for h in files:
        h.flush()
    assert "hello app.log" in (tmp_path / actions.APP_LOG).read_text(encoding="utf-8")


def test_main_without_args_opens_the_gui(monkeypatch, tmp_path):
    monkeypatch.setattr(appmain, "DEFAULT_HOME", tmp_path)
    monkeypatch.setitem(sys.modules, "lakota_grades.app.gui", types.SimpleNamespace(run_app=lambda: 7))
    assert appmain.main([]) == 7


def test_main_with_args_runs_the_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(appmain, "DEFAULT_HOME", tmp_path)
    seen = {}

    def fake_cli_main(argv):
        seen["argv"] = argv
        raise SystemExit(3)

    monkeypatch.setattr(cli, "main", fake_cli_main)
    assert appmain.main(["run", "open-work", "--dry-run"]) == 3
    assert seen["argv"] == ["run", "open-work", "--dry-run"]


def test_cli_app_command_opens_the_gui_or_explains_missing_tkinter(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "lakota_grades.app.gui", types.SimpleNamespace(run_app=lambda: 0))
    with pytest.raises(SystemExit) as e:
        cli.main(["app"])
    assert e.value.code == 0
    monkeypatch.setitem(sys.modules, "lakota_grades.app.gui", None)      # makes `import` raise ImportError
    with pytest.raises(SystemExit) as e:
        cli.main(["app"])
    assert e.value.code == 2 and "tkinter" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_main.py -q`
Expected: FAIL at import (`No module named 'lakota_grades.app.__main__'`).

- [ ] **Step 3: Write `app/__main__.py`**

```python
# lakota_grades/app/__main__.py
"""Entry point of the frozen Windows executable, and of `python -m lakota_grades.app`.

No arguments opens the settings window. Anything else is the ordinary CLI, so the
scheduled task's `LakotaSheet.exe run open-work` and the uninstaller's
`LakotaSheet.exe schedule remove` come from the same binary. A windowed exe has no
stdout or stderr, so logging goes to <home>/app.log; stderr gets a copy only when it exists.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from ..config import DEFAULT_HOME
from .actions import APP_LOG

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def frozen_environment(environ=os.environ, executable: str | None = None) -> None:
    """Point Playwright at the Chromium the installer puts next to the exe (Plan 3)."""
    if getattr(sys, "frozen", False):
        exe = Path(executable or sys.executable)
        environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(exe.parent / "ms-playwright"))


def setup_logging(home: Path, stderr=sys.stderr) -> None:
    home.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    target = str(home / APP_LOG)
    if any(isinstance(h, logging.handlers.RotatingFileHandler) and h.baseFilename == target for h in root.handlers):
        return
    fmt = logging.Formatter(_FORMAT)
    fh = logging.handlers.RotatingFileHandler(target, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if stderr is not None:
        sh = logging.StreamHandler(stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    frozen_environment()
    setup_logging(DEFAULT_HOME)
    if not argv:
        from .gui import run_app
        return run_app()
    from .. import cli
    try:
        cli.main(argv)
    except SystemExit as e:
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note `cli.main` calls `logging.basicConfig(...)`, which is a no-op once the root logger has handlers, so `setup_logging` must run first (it does).

- [ ] **Step 4: Add the `app` command to `cli.py`**

```python
def cmd_app(args) -> int:
    try:
        from .app.gui import run_app
    except ImportError as e:  # tkinter is not part of every Linux python
        print(f"The settings window needs tkinter, which is not installed here: {e}", file=sys.stderr)
        return 2
    return run_app()
```

and in `main()` after the `schedule` parser: `sub.add_parser("app", help="open the Lakota Sheet settings window").set_defaults(fn=cmd_app)`. Update the module docstring's command list to include `app`.

- [ ] **Step 5: Run the tests and the suite, commit**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_main.py -q` then the full suite. Expected: 5 passed; 159 passed overall.

```bash
git add lakota_grades/app/__main__.py lakota_grades/cli.py tests/test_app_main.py
git commit -m "app entry point: app.log, frozen-exe environment, GUI-or-CLI dispatch, cli app command

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: The window: `app/gui.py`, a display-gated smoke test, and the README note

`gui.py` is the one file this plan does not unit-test. It must stay thin: every decision is a call into `actions`. The smoke test constructs the window when tkinter and a display exist, which on CI means the Windows runner.

**Files:**
- Create: `lakota_grades/app/gui.py`
- Test: `tests/test_app_gui.py`
- Modify: `README.md` (after the "### Settings file" block)

**Interfaces:**
- Consumes: everything in `actions`, `config.DEFAULT_HOME`, `config.ConfigError`, `host.printing.list_printers/default_printer`, `host.PrintError`.
- Produces: `gui.run_app(home: Path | None = None) -> int` and the `App` class (`App(root, home)`), with `App.form() -> FormValues` and `App.set_form(FormValues)` as the two seams the smoke test touches.

- [ ] **Step 1: Write the smoke test**

```python
# tests/test_app_gui.py
"""Constructs the window when a display exists (the Windows CI runner; a dev box with
python3-tk and DISPLAY). Everywhere else it skips. Business logic is tested in
test_app_actions.py; this only proves the widgets build and round-trip a form."""
from __future__ import annotations

import os
import sys

import pytest

tk = pytest.importorskip("tkinter")
if sys.platform != "win32" and not os.environ.get("DISPLAY"):
    pytest.skip("no display", allow_module_level=True)

from lakota_grades.app import actions, gui  # noqa: E402


def test_window_builds_and_round_trips_the_form(tmp_path, monkeypatch):
    monkeypatch.setattr(gui, "_printer_names", lambda: ["Office", "Microsoft Print to PDF"])
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"no usable display: {e}")
    try:
        root.withdraw()
        app = gui.App(root, tmp_path)
        assert app.form() == actions.FormValues()
        want = actions.FormValues(username="p@x.com", password="pw", printer="Office", time="15:30", days_ahead=7,
                                  overdue_days=21, nicknames="Alex=Al", archive="D:/S", scheduled=True)
        app.set_form(want)
        assert app.form() == want
        app.set_form(actions.FormValues(printer=""))
        assert app.printer_var.get() == gui.SYSTEM_DEFAULT and app.form().printer == ""
    finally:
        root.destroy()
```

- [ ] **Step 2: Run it to see it skip here**

Run: `env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest tests/test_app_gui.py -q`
Expected: `1 skipped` (no tkinter on this box). It will run on the Windows CI leg after the push.

- [ ] **Step 3: Write `gui.py`**

```python
# lakota_grades/app/gui.py
"""The Lakota Sheet window. Widgets, a worker thread and a queue; nothing else.

Every button calls one function in `actions`. Long actions run on a daemon thread and
report through `self._q`; `_poll` drains it on the Tk main loop every 100 ms, so widget
updates never happen off-thread.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .. import config
from ..host import PrintError
from . import actions

SYSTEM_DEFAULT = "System default"
POLL_MS = 100


def _printer_names() -> list[str]:
    from ..host import printing
    try:
        return printing.list_printers()
    except PrintError:
        return []


class App:
    def __init__(self, root: tk.Tk, home: Path):
        self.root, self.home = root, home
        self._q: queue.Queue = queue.Queue()
        self._busy = False
        root.title("Lakota Sheet")
        root.minsize(640, 520)
        self._build_menu()
        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.settings_tab, self.run_tab = ttk.Frame(nb), ttk.Frame(nb)
        nb.add(self.settings_tab, text="Settings")
        nb.add(self.run_tab, text="Run")
        self._build_settings(self.settings_tab)
        self._build_run(self.run_tab)
        self._load()
        self._refresh_status()
        root.after(POLL_MS, self._poll)

    # ----- building -------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        helpm = tk.Menu(menu, tearoff=0)
        helpm.add_command(label="About Lakota Sheet", command=lambda: messagebox.showinfo("About Lakota Sheet", actions.about_text()))
        menu.add_cascade(label="Help", menu=helpm)
        self.root.config(menu=menu)

    def _build_settings(self, f: ttk.Frame) -> None:
        f.columnconfigure(1, weight=1)
        self.username_var, self.password_var = tk.StringVar(), tk.StringVar()
        self.printer_var, self.time_var = tk.StringVar(value=SYSTEM_DEFAULT), tk.StringVar(value="14:00")
        self.days_ahead_var, self.overdue_var = tk.IntVar(value=14), tk.IntVar(value=14)
        self.archive_var, self.scheduled_var = tk.StringVar(), tk.BooleanVar(value=False)
        row = 0

        def label(text):
            nonlocal row
            ttk.Label(f, text=text).grid(row=row, column=0, sticky="w", padx=6, pady=4)

        label("OneLogin username")
        ttk.Entry(f, textvariable=self.username_var, width=40).grid(row=row, column=1, sticky="ew", padx=6)
        row += 1
        label("OneLogin password")
        ttk.Entry(f, textvariable=self.password_var, show="•", width=40).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Label(f, text="blank = keep the stored one").grid(row=row, column=2, sticky="w")
        row += 1
        label("Printer")
        self.printer_box = ttk.Combobox(f, textvariable=self.printer_var, state="readonly")
        self.printer_box.grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="Refresh", command=self._refresh_printers).grid(row=row, column=2, padx=4)
        row += 1
        label("Print time (24-hour HH:MM)")
        ttk.Entry(f, textvariable=self.time_var, width=8).grid(row=row, column=1, sticky="w", padx=6)
        row += 1
        label("Days ahead")
        ttk.Spinbox(f, from_=1, to=actions.MAX_DAYS, textvariable=self.days_ahead_var, width=5).grid(row=row, column=1, sticky="w", padx=6)
        row += 1
        label("Overdue days")
        ttk.Spinbox(f, from_=1, to=actions.MAX_DAYS, textvariable=self.overdue_var, width=5).grid(row=row, column=1, sticky="w", padx=6)
        row += 1
        label("Kid nicknames (First=Nick, one per line)")
        self.nick_text = tk.Text(f, height=4, width=40)
        self.nick_text.grid(row=row, column=1, sticky="ew", padx=6)
        row += 1
        label("Also save each PDF to folder")
        ttk.Entry(f, textvariable=self.archive_var, width=40).grid(row=row, column=1, sticky="ew", padx=6)
        ttk.Button(f, text="Browse...", command=self._browse).grid(row=row, column=2, padx=4)
        row += 1
        ttk.Checkbutton(f, text="Print the sheet automatically on school days", variable=self.scheduled_var).grid(row=row, column=1, sticky="w", padx=6, pady=6)
        row += 1
        bar = ttk.Frame(f)
        bar.grid(row=row, column=0, columnspan=3, sticky="w", padx=6, pady=8)
        self.save_btn = ttk.Button(bar, text="Save", command=self._save)
        self.save_btn.pack(side="left")
        ttk.Button(bar, text="Open late-work rules", command=lambda: self._open_editable("late-rules.toml")).pack(side="left", padx=6)
        ttk.Button(bar, text="Open no-print days", command=lambda: self._open_editable("no-print-days.txt")).pack(side="left")
        self._refresh_printers()

    def _build_run(self, f: ttk.Frame) -> None:
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=6, pady=6)
        self.login_btn = ttk.Button(bar, text="Test login", command=lambda: self._start("Test login", self._do_test_login))
        self.preview_btn = ttk.Button(bar, text="Preview today's sheet", command=lambda: self._start("Preview", self._do_preview))
        self.print_btn = ttk.Button(bar, text="Print now", command=lambda: self._start("Print now", self._do_print))
        for b in (self.login_btn, self.preview_btn, self.print_btn):
            b.pack(side="left", padx=4)
        self.log_pane = scrolledtext.ScrolledText(f, height=18, state="disabled", wrap="word")
        self.log_pane.pack(fill="both", expand=True, padx=6)
        self.status_var = tk.StringVar()
        ttk.Label(f, textvariable=self.status_var, anchor="w").pack(fill="x", padx=6, pady=4)

    # ----- form <-> widgets ---------------------------------------------------------
    def form(self) -> actions.FormValues:
        printer = self.printer_var.get()
        return actions.FormValues(
            username=self.username_var.get(), password=self.password_var.get(),
            printer="" if printer == SYSTEM_DEFAULT else printer, time=self.time_var.get().strip(),
            days_ahead=int(self.days_ahead_var.get()), overdue_days=int(self.overdue_var.get()),
            nicknames=self.nick_text.get("1.0", "end").strip(), archive=self.archive_var.get(),
            scheduled=bool(self.scheduled_var.get()),
        )

    def set_form(self, v: actions.FormValues) -> None:
        self.username_var.set(v.username)
        self.password_var.set(v.password)
        self.printer_var.set(v.printer or SYSTEM_DEFAULT)
        self.time_var.set(v.time)
        self.days_ahead_var.set(v.days_ahead)
        self.overdue_var.set(v.overdue_days)
        self.nick_text.delete("1.0", "end")
        self.nick_text.insert("1.0", v.nicknames)
        self.archive_var.set(v.archive)
        self.scheduled_var.set(v.scheduled)

    def _load(self) -> None:
        try:
            self.set_form(actions.load_form(self.home))
        except config.ConfigError as e:
            # Spec section 11: a config.toml that does not parse names the file and offers to open it.
            if messagebox.askyesno("Settings file problem", f"{e}\n\nOpen the file in an editor to fix it?"):
                try:
                    from ..host.opener import open_text
                    open_text(self.home / actions.CONFIG_NAME)
                except Exception as e2:
                    messagebox.showerror("Could not open", str(e2))

    def _refresh_printers(self) -> None:
        names = _printer_names()
        self.printer_box["values"] = [SYSTEM_DEFAULT] + names
        if self.printer_var.get() not in self.printer_box["values"]:
            self.printer_var.set(SYSTEM_DEFAULT)

    def _browse(self) -> None:
        d = filedialog.askdirectory(title="Folder for a second copy of each sheet")
        if d:
            self.archive_var.set(d)

    def _open_editable(self, name: str) -> None:
        try:
            actions.open_editable(self.home, name)
        except Exception as e:
            messagebox.showerror("Could not open", str(e))

    # ----- actions on the worker thread --------------------------------------------
    def _log(self, line: str) -> None:
        self._q.put(("log", line))

    def _start(self, name: str, fn) -> None:
        if self._busy:
            return
        self._busy = True
        for b in (self.login_btn, self.preview_btn, self.print_btn, self.save_btn):
            b.state(["disabled"])
        self._append(f"--- {name} ---")

        def work():
            try:
                result = fn()
            except Exception as e:  # never let a thread die silently
                result = ("error", f"{type(e).__name__}: {e}")
            self._q.put(("done", name, result))

        threading.Thread(target=work, daemon=True).start()

    def _do_test_login(self):
        return ("login", actions.test_login(home=self.home, log=self._log))

    def _do_preview(self):
        return ("preview", actions.preview(home=self.home, log=self._log))

    def _do_print(self):
        return ("print", actions.print_now(home=self.home, log=self._log))

    def _save(self) -> None:
        form = self.form()
        self._start("Save", lambda: ("save", actions.save(form, home=self.home, log=self._log)))

    def _poll(self) -> None:
        try:
            while True:
                item = self._q.get_nowait()
                if item[0] == "log":
                    self._append(item[1])
                else:
                    self._finish(item[1], item[2])
        except queue.Empty:
            pass
        self.root.after(POLL_MS, self._poll)

    def _finish(self, name: str, result) -> None:
        self._busy = False
        for b in (self.login_btn, self.preview_btn, self.print_btn, self.save_btn):
            b.state(["!disabled"])
        kind, value = result
        if kind == "error":
            messagebox.showerror(name, value)
        elif kind == "save":
            (messagebox.showinfo if value.ok else messagebox.showerror)("Save", "\n".join(value.messages))
            if value.ok:
                self.password_var.set("")
        elif kind == "login":
            (messagebox.showinfo if value.ok else messagebox.showerror)("Test login", value.message)
        elif kind == "preview" and value is None:
            messagebox.showerror("Preview", "The sheet could not be built; see the log above.")
        elif kind == "print" and value != 0:
            messagebox.showerror("Print now", "The sheet was not printed; see the log above.")
        self._refresh_status()

    def _append(self, line: str) -> None:
        self.log_pane.configure(state="normal")
        self.log_pane.insert("end", line + "\n")
        self.log_pane.see("end")
        self.log_pane.configure(state="disabled")

    def _refresh_status(self) -> None:
        try:
            self.status_var.set(actions.status_line(self.home))
        except Exception as e:
            self.status_var.set(f"status unavailable: {e}")


def run_app(home: Path | None = None) -> int:
    root = tk.Tk()
    App(root, home or config.DEFAULT_HOME)
    root.mainloop()
    return 0
```

- [ ] **Step 4: README note**

In `README.md`, after the "### Settings file" block's last paragraph (the one starting "**Upgrading from 0.1:**"), add:

```markdown
### The settings window

`lakota-grades app` opens a small window (tkinter; on Debian/Ubuntu `sudo apt install python3-tk`) with the same settings as `config.toml`, a **Test login** button that records a passing login in `~/.lakota-grades/login-ok.txt`, **Preview today's sheet** and **Print now** buttons with a live log, and the last run's status. On Windows this is the "Lakota Sheet" app; the scheduled task is installed from the window's Save button once a login has passed. The window itself writes `app.log` in the same folder.
```

- [ ] **Step 5: Run the full suite, commit, push, and watch CI**

```bash
env -u PYTHONPATH ~/lakota-grades-mcp/.venv/bin/python -m pytest -q      # expect 159 passed, 1 skipped (the GUI smoke test)
git add lakota_grades/app/gui.py tests/test_app_gui.py README.md
git commit -m "app.gui: the Lakota Sheet window (tkinter), display-gated smoke test, README note

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
gh run watch "$(gh run list --workflow ci.yml --branch "$(git rev-parse --abbrev-ref HEAD)" --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status 2>&1 | tee /tmp/ci-plan2.log | tail -5
```

Expected: both legs green. The Windows leg should show the GUI smoke test **passing** (not skipped); quote its line from `gh run view <id> --log | grep test_app_gui`. If the Windows leg fails inside `test_app_gui.py` with a Tcl/Tk display error, mark the test `pytest.skip` on that error message (the test already skips on `TclError` at `tk.Tk()`; extend the same guard to `App(...)` construction) and note it in the report; a failure anywhere else is a real bug to fix in `gui.py`.

---

## Done when

- `python -m lakota_grades.app` on a machine with tkinter opens the window; every button calls into `actions` and nothing in `gui.py` touches a file or a subprocess (`grep -n "open(\|subprocess\|save_config_doc\|write_text" lakota_grades/app/gui.py` is empty).
- `tests/test_app_actions.py` covers `load_form`, `validate`, `save` (all three schedule outcomes), `test_login` (stamp written and removed), `preview`, `print_now`, `status_line`, `open_editable`, `about_text`, `forward_logs`.
- CI green on both runners; the Windows leg runs the GUI smoke test.
- `LakotaSheet.exe`-style dispatch proven by `tests/test_app_main.py`: no args → GUI, args → CLI, `app.log` written, no stderr handler when stderr is `None`.
- Plan 3 can build the bundle: entry point `lakota_grades/app/__main__.py`, `PLAYWRIGHT_BROWSERS_PATH` handling in `frozen_environment`, and the uninstaller's `schedule remove` all exist.

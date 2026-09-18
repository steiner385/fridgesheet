# Windows Sheet App, Plan 1 of 3: Portable Core and Host Adapters

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing package run on Windows and Linux from one codebase, with the printed sheet behind a report plugin layer and every OS-specific action behind a small adapter, so Plan 2 (the tkinter app) and Plan 3 (PyInstaller + Inno Setup + release workflow) can be built on stable interfaces.

**Architecture:** `print_sheet.run` is split into a generic `runner` (guards, refresh, archive, print, record, toast) and a `reports.open_work` report (build the PDF). A `host/` package holds `printing`, `credentials`, `scheduling`, `notify`, `opener`, each with a `_linux` and a `_windows` module and a selector that picks one by `sys.platform`; every adapter takes `run=subprocess.run` so tests assert on command lines without an OS. Settings gain a `config.toml` under the app home with env vars still overriding it.

**Tech Stack:** Python 3.12, tomllib + tomli-w, keyring (Windows Credential Manager), pywin32 (printer enumeration), SumatraPDF (bundled in Plan 3; invoked here), Windows Task Scheduler via `schtasks`, PowerShell toasts, pytest on ubuntu-latest and windows-latest.

**Spec:** `docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md`

**Plans 2 and 3** (`app/actions.py` + `app/gui.py`; `packaging/windows/*` + `release.yml` + `docs/windows.md`) are written after this plan lands, against the interfaces this plan produces.

## Global Constraints

- `requires-python = ">=3.11"` (tomllib); the Windows bundle ships 3.12.
- Nothing outside `fridgesheet/host/` may check `sys.platform` or `os.name`.
- No `%-m`, `%-d`, `%-I` (or any `%-x`) strftime code anywhere in `fridgesheet/`; a test enforces this.
- No credential is ever written to `config.toml`, a log line, a toast, or stdout.
- Existing behaviour that must survive unchanged: `fridgesheet print-sheet` and all its flags; `secret-tool` credential reads on Linux; `~/.fridgesheet/.env` overriding everything in `config.toml`; `sheets/<date>/` as the open-work output folder; the three guards in their current order; the 24-hour stale fallback.
- The `Alex=Al` default nickname and the family-specific late-rules seed leave the code.
- Commit after every task with the attribution trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run the full suite (`python3 -m pytest -q`) before every commit; it must stay green (45 passed, 2 skipped at the start of this plan).

## File map

| Path | Responsibility |
|---|---|
| `fridgesheet/dates.py` (new) | Four date formatters replacing glibc-only strftime codes |
| `fridgesheet/config.py` (modify) | Home dir per OS, `config.toml` load/save, `ReportConfig`, nicknames, printer, username; credentials via `host.credentials` |
| `fridgesheet/host/__init__.py` (new) | `IS_WINDOWS`, `CREATE_NO_WINDOW`, `NotSupported` |
| `fridgesheet/host/credentials.py`, `credentials_linux.py`, `credentials_windows.py` (new) | Password store |
| `fridgesheet/host/printing.py`, `printing_linux.py`, `printing_windows.py` (new) | List / default / print PDF |
| `fridgesheet/host/notify.py`, `notify_linux.py`, `notify_windows.py` (new) | Toast |
| `fridgesheet/host/opener.py` (new) | Open a file in the desktop viewer |
| `fridgesheet/host/scheduling.py`, `scheduling_linux.py`, `scheduling_windows.py`, `task.xml` (new) | Scheduled run |
| `fridgesheet/reports/__init__.py`, `base.py`, `open_work.py` (new) | Report protocol, registry, the sheet |
| `fridgesheet/runner.py` (new) | Generic guards / refresh / build / archive / print / record / toast |
| `fridgesheet/print_sheet.py` (rewrite) | Thin alias: `Options` -> `runner.run("open-work", ...)` |
| `fridgesheet/sheet.py` (modify) | Use `dates` helpers |
| `fridgesheet/late_rules.py` (modify) | Generic seed |
| `fridgesheet/cli.py` (modify) | `run`, `reports`, `printers`, `schedule`; `print-sheet` alias; `--printer` default None |
| `pyproject.toml` (modify) | Version 0.2.0, python floor, `tomli-w`, `tzdata` on Windows, `windows` extra, package data |
| `.github/workflows/spike-pyinstaller.yml`, `packaging/windows/spike_entry.py` (new) | Throwaway feasibility check (Task 1) |
| `.github/workflows/ci.yml` (new) | pytest on both OSes |
| `README.md`, `env.example`, `desktop/*.desktop`, `systemd/fridgesheet-print-sheet.service` (modify) | De-Tony and document |
| `tests/test_dates.py`, `test_config.py`, `test_host_credentials.py`, `test_host_printing.py`, `test_host_notify.py`, `test_host_scheduling.py`, `test_reports.py`, `test_runner.py` (new/modify) | |

---

### Task 1: Feasibility spike, Playwright inside a PyInstaller bundle on Windows (throwaway)

The spec's first risk (section 15.1). This is a spike: the deliverable is a green or red CI run, not code we keep. The workflow stays in the repo as `workflow_dispatch`-only until Plan 3 replaces it with `release.yml`.

**Files:**
- Create: `packaging/windows/spike_entry.py`
- Create: `.github/workflows/spike-pyinstaller.yml`

**Interfaces:**
- Produces: a recorded answer in this plan (see Step 5), plus the working PyInstaller recipe Plan 3 copies.

- [ ] **Step 1: Write the spike entry point**

```python
# packaging/windows/spike_entry.py
"""Throwaway: prove Chromium launches from inside a PyInstaller one-folder bundle.

Prints CHROMIUM_OK <title> and exits 0, or a traceback and exits 1. Not shipped.
"""
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(sys.executable).parent / "ms-playwright"))

from playwright.sync_api import sync_playwright  # noqa: E402

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    page = b.new_page()
    page.goto("data:text/html,<title>spike-ok</title>")
    print("CHROMIUM_OK", page.title(), flush=True)
    b.close()
```

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/spike-pyinstaller.yml
name: spike-pyinstaller
on:
  workflow_dispatch:
  push:
    paths: [".github/workflows/spike-pyinstaller.yml", "packaging/windows/spike_entry.py"]
jobs:
  spike:
    runs-on: windows-latest
    env:
      PLAYWRIGHT_BROWSERS_PATH: ${{ github.workspace }}\build\ms-playwright
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install "playwright>=1.45" pyinstaller
      - run: python -m playwright install chromium
      - run: pyinstaller --noconfirm --onedir --name spike packaging/windows/spike_entry.py
      - run: Copy-Item -Recurse build\ms-playwright dist\spike\ms-playwright
        shell: pwsh
      - run: |
          $env:PLAYWRIGHT_BROWSERS_PATH = ""
          $out = & dist\spike\spike.exe
          Write-Host $out
          if ($out -notmatch "CHROMIUM_OK spike-ok") { exit 1 }
        shell: pwsh
```

- [ ] **Step 3: Commit and push, then watch the run**

```bash
git add packaging/windows/spike_entry.py .github/workflows/spike-pyinstaller.yml
git commit -m "Spike: prove Chromium launches from a PyInstaller bundle on Windows

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push -u origin HEAD
gh run list --workflow spike-pyinstaller.yml --limit 1
gh run watch "$(gh run list --workflow spike-pyinstaller.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status 2>&1 | tee /tmp/spike-pyinstaller.log
```

Expected: the final step prints `CHROMIUM_OK spike-ok` and the run is green.

- [ ] **Step 4: If red, diagnose before continuing**

Known failure modes and the fix to try, one at a time, each as its own push:
1. `Executable doesn't exist at ...ms-playwright...`: the browser folder name inside `ms-playwright` must match what the bundled driver expects; print `os.environ["PLAYWRIGHT_BROWSERS_PATH"]` and `Get-ChildItem dist\spike\ms-playwright` in the workflow and compare.
2. `playwright driver not found`: add `--collect-all playwright` to the `pyinstaller` line.
3. Anything else: stop, record the error text in Step 5, and hand the plan back. This is the spec's stated ratchet point.

- [ ] **Step 5: Record the outcome here**

Green: https://github.com/steiner385/fridgesheet/actions/runs/34852463828 — Chromium launched from inside the PyInstaller one-folder bundle on windows-latest (`CHROMIUM_OK spike-ok`); `--collect-all playwright` was not needed, but `$env:PLAYWRIGHT_BROWSERS_PATH = ""` had to be changed to `Remove-Item Env:\PLAYWRIGHT_BROWSERS_PATH` since PowerShell's empty-string assignment leaves the key set and defeats `os.environ.setdefault()` in the frozen entry point.

---

### Task 2: Date helpers and removal of glibc-only strftime codes

**Files:**
- Create: `fridgesheet/dates.py`
- Modify: `fridgesheet/sheet.py:55-58, 77, 110, 165, 176, 188`
- Modify: `fridgesheet/print_sheet.py:146, 210, 236`
- Test: `tests/test_dates.py`

**Interfaces:**
- Produces: `dates.md(d) -> str` ("9/14"), `dates.wd_md(d) -> str` ("Mon 9/14"), `dates.time12(d) -> str` ("2:05 PM"), `dates.wd_md_time(d) -> str` ("Mon 9/14 2:05 PM"), `dates.long_date(d) -> str` ("Monday, September 14, 2026"). All accept `date` or `datetime` except `time12` and `wd_md_time`, which need a `datetime`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dates.py
"""Date text without glibc-only strftime codes (%-m, %-d, %-I raise on Windows)."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from fridgesheet import dates

D = datetime(2026, 9, 14, 14, 5)


def test_month_day_has_no_leading_zeros():
    assert dates.md(D) == "9/14"
    assert dates.md(date(2026, 1, 2)) == "1/2"


def test_weekday_month_day():
    assert dates.wd_md(D) == "Mon 9/14"


def test_twelve_hour_time_covers_noon_midnight_and_afternoon():
    assert dates.time12(D) == "2:05 PM"
    assert dates.time12(datetime(2026, 9, 14, 0, 0)) == "12:00 AM"
    assert dates.time12(datetime(2026, 9, 14, 12, 0)) == "12:00 PM"
    assert dates.time12(datetime(2026, 9, 14, 23, 59)) == "11:59 PM"


def test_combined_and_long_forms():
    assert dates.wd_md_time(D) == "Mon 9/14 2:05 PM"
    assert dates.long_date(D) == "Monday, September 14, 2026"


def test_no_glibc_only_strftime_codes_remain_in_the_package():
    pkg = Path(dates.__file__).parent
    offenders = [p.name for p in pkg.rglob("*.py") if re.search(r"%-[a-zA-Z]", p.read_text(encoding="utf-8"))]
    assert offenders == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest tests/test_dates.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fridgesheet.dates'`

- [ ] **Step 3: Write `dates.py`**

```python
# fridgesheet/dates.py
"""Short date text for the sheet and the log, built from fields rather than strftime.

The 'no leading zero' strftime codes (percent-dash-m and friends) are a glibc extension;
Python on Windows raises ValueError on them. %a %A %B %p are portable and stay.
"""
from __future__ import annotations

from datetime import date, datetime


def md(d: date) -> str:
    return f"{d.month}/{d.day}"


def wd_md(d: date) -> str:
    return f"{d:%a} {d.month}/{d.day}"


def time12(d: datetime) -> str:
    return f"{d.hour % 12 or 12}:{d.minute:02d} {d:%p}"


def wd_md_time(d: datetime) -> str:
    return f"{wd_md(d)} {time12(d)}"


def long_date(d: date) -> str:
    return f"{d:%A}, {d:%B} {d.day}, {d.year}"
```

- [ ] **Step 4: Replace every `%-` code in `sheet.py`**

Add `from .dates import long_date, md, time12, wd_md, wd_md_time` to the imports, then:

```python
# sheet.py fmt_due (was lines 55-59)
def fmt_due(d: datetime) -> str:
    s = wd_md(d)
    if not (d.hour == 23 and d.minute == 59):
        s += " " + time12(d).replace(" ", "").lower().replace(":00", "")
    return s
```

Line 77: `thru {it.late_until.strftime("%a %-m/%-d")}` becomes `thru {wd_md(it.late_until)}`.
Line 110: `it.assigned.strftime("%a %-m/%-d")` becomes `wd_md(it.assigned)`.
Line 165: `{data_as_of.strftime('%a %-m/%-d %-I:%M %p')}` becomes `{wd_md_time(data_as_of)}`.
Line 176: `printed_at.strftime("%A, %B %-d, %Y")` becomes `long_date(printed_at)`.
Line 188: `{printed_at.strftime('%-m/%-d %-I:%M %p')}` becomes `{md(printed_at)} {time12(printed_at)}`.

- [ ] **Step 5: Replace every `%-` code in `print_sheet.py`**

Add `from .dates import md, time12, wd_md, wd_md_time`, then:

Line 146: `d.strftime("%a %-m/%-d")` becomes `wd_md(d)`.
Line 210: `f"refresh failed at {now:%-I:%M %p}; data from {as_of:%a %-m/%-d %-I:%M %p}"` becomes `f"refresh failed at {time12(now)}; data from {wd_md_time(as_of)}"`.
Line 236: `data={as_of:%-m/%-d %H:%M}` becomes `data={md(as_of)} {as_of:%H:%M}`.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: all pass, including `test_no_glibc_only_strftime_codes_remain_in_the_package`.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/dates.py fridgesheet/sheet.py fridgesheet/print_sheet.py tests/test_dates.py
git commit -m "Format sheet dates without glibc-only strftime codes (they raise on Windows)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 3: `config.toml`, per-OS home directory, and removing the family-specific defaults

**Files:**
- Create: `fridgesheet/host/__init__.py`
- Modify: `fridgesheet/config.py` (whole file)
- Modify: `fridgesheet/print_sheet.py:36, 72, 98-112, 214, 248` (nicknames, printer default)
- Modify: `fridgesheet/cli.py:164` (`--printer` default)
- Modify: `fridgesheet/late_rules.py:32-74` (SEED)
- Modify: `pyproject.toml`, `env.example`, `desktop/fridgesheet-pdf.desktop`, `desktop/fridgesheet-print.desktop`, `systemd/fridgesheet-print-sheet.service`
- Test: `tests/test_config.py` (append), `tests/test_print_sheet.py:45-70` (fixture)

**Interfaces:**
- Produces:
  - `host.IS_WINDOWS: bool`, `host.CREATE_NO_WINDOW: int`, `host.NotSupported(RuntimeError)`
  - `config.ConfigError(RuntimeError)`
  - `config.ReportConfig(enabled: bool = False, time: str = "14:00", days: list[str] = [Mon..Fri], options: dict = {})`
  - `config.Settings` new fields: `username: str = ""`, `printer: str = ""`, `nicknames: dict[str, str] = {}`, `reports: dict[str, ReportConfig] = {}`; new method `report_config(key: str, default_time: str = "14:00") -> ReportConfig`
  - `config.config_file() -> Path` (`<home>/config.toml`)
  - `config.load_config_doc(path: Path) -> dict` (missing file -> `{}`; parse error -> `ConfigError`)
  - `config.save_config_doc(path: Path, doc: dict) -> None` (atomic write, mode 0600)
  - `config.parse_nicknames(text: str) -> dict[str, str]`
  - `config.settings_from_doc(doc: dict, s: Settings) -> None` (applies the file; env applied afterwards by `load_settings`)
  - `config.KEYRING_SERVICE` is **removed** from `config` (moves to `host.credentials` in Task 4). `cli.py` still imports it until Task 4; keep a re-export `KEYRING_SERVICE = "fridgesheet"` in `config.py` for this task only.

- [ ] **Step 1: Write the failing config tests**

Append to `tests/test_config.py`:

```python
def test_default_home_is_localappdata_on_windows(monkeypatch, tmp_path):
    from fridgesheet import host
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("FRIDGESHEET_HOME", raising=False)
    assert config._default_home() == tmp_path / "fridgesheet"
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    assert config._default_home() == Path.home() / ".fridgesheet"


def test_config_doc_round_trip(tmp_path):
    p = tmp_path / "config.toml"
    doc = {"account": {"username": "p@x.com"}, "print": {"printer": 'Brother "MFC"', "archive": "C:\\Users\\p\\Drive"},
           "kids": {"nicknames": {"Alex": "Al"}},
           "reports": {"open-work": {"enabled": True, "time": "15:30", "days": ["Mon", "Wed"], "days_ahead": 7, "overdue_days": 21}}}
    config.save_config_doc(p, doc)
    assert config.load_config_doc(p) == doc
    assert config.load_config_doc(tmp_path / "missing.toml") == {}


def test_broken_config_names_the_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[print\n")
    with pytest.raises(config.ConfigError) as e:
        config.load_config_doc(p)
    assert str(p) in str(e.value)


def test_settings_from_doc_and_env_precedence(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    for k in ("FRIDGESHEET_PRINTER", "FRIDGESHEET_NICKNAMES", "FRIDGESHEET_SHEETS_ARCHIVE"):
        monkeypatch.delenv(k, raising=False)
    config.save_config_doc(tmp_path / "config.toml", {
        "account": {"username": "p@x.com"}, "print": {"printer": "Office", "archive": "/mnt/d"},
        "kids": {"nicknames": {"Alex": "Al", "Katherine": "Kate"}},
        "reports": {"open-work": {"enabled": True, "time": "15:30", "days_ahead": 7}, "unknown-key": 1},
        "not_a_section": {"x": 1},
    })
    s = config.load_settings()
    assert s.username == "p@x.com" and s.printer == "Office" and s.sheets_archive == "/mnt/d"
    assert s.nicknames == {"Alex": "Al", "Katherine": "Kate"}
    rc = s.report_config("open-work")
    assert rc.enabled and rc.time == "15:30" and rc.days == ["Mon", "Tue", "Wed", "Thu", "Fri"] and rc.options == {"days_ahead": 7}
    assert s.report_config("nope").enabled is False and s.report_config("nope", default_time="18:00").time == "18:00"
    monkeypatch.setenv("FRIDGESHEET_PRINTER", "Env")
    monkeypatch.setenv("FRIDGESHEET_NICKNAMES", "Alex=D,Jo=Mel")
    monkeypatch.setenv("FRIDGESHEET_SHEETS_ARCHIVE", "/env")
    s = config.load_settings()
    assert s.printer == "Env" and s.sheets_archive == "/env"
    assert s.nicknames == {"Alex": "D", "Katherine": "Kate", "Jo": "Mel"}   # env wins per key


def test_parse_nicknames():
    assert config.parse_nicknames(" Alex = Al ,Katherine=Kate,,bad") == {"Alex": "Al", "Katherine": "Kate"}
    assert config.parse_nicknames("") == {}


def test_no_nickname_is_built_in(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.delenv("FRIDGESHEET_ENV_FILE", raising=False)
    monkeypatch.delenv("FRIDGESHEET_NICKNAMES", raising=False)
    assert config.load_settings().nicknames == {}
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_config.py -q`
Expected: the six new tests FAIL (`AttributeError: module 'fridgesheet.config' has no attribute '_default_home'` and similar).

- [ ] **Step 3: Create `host/__init__.py`**

```python
# fridgesheet/host/__init__.py
"""OS adapters. This package is the only place that may look at the platform.

Each adapter module (`printing`, `credentials`, `scheduling`, `notify`, `opener`) picks a
`_linux` or `_windows` implementation at import time. Every implementation takes its
`run=subprocess.run` as an argument so tests assert on command lines on any OS.
"""
from __future__ import annotations

import subprocess
import sys

IS_WINDOWS: bool = sys.platform == "win32"

#: subprocess creationflags that keep a console window from flashing under a windowed exe.
CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class NotSupported(RuntimeError):
    """The host has no implementation of this action (e.g. scheduling on Linux)."""
```

- [ ] **Step 4: Add dependencies and metadata to `pyproject.toml`**

```toml
[project]
name = "fridgesheet"
version = "0.2.0"
description = "Lakota Local Schools parent tools: a printed open-work sheet from Canvas + Home Access Center, and a local MCP server for Claude."
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE"]
readme = "README.md"
dependencies = [
    "mcp>=1.2,<3",
    "playwright>=1.45",
    "python-dotenv>=1.0",
    "reportlab>=4",
    "tomli-w>=1.0",
    "tzdata>=2024.1; sys_platform == 'win32'",
]

[project.optional-dependencies]
dev = ["pytest>=8"]
windows = ["keyring>=25", "pywin32>=306"]

[project.scripts]
fridgesheet = "fridgesheet.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["fridgesheet*"]

[tool.setuptools.package-data]
fridgesheet = ["host/*.xml"]
```

Then `pip install tomli-w` into whatever environment runs the tests (`python3 -m pip install --user tomli-w` if there is no venv). `tzdata` is only pulled on Windows: Python there has no system zoneinfo database, and `ZoneInfo("America/New_York")` raises without it.

- [ ] **Step 5: Rewrite `config.py`**

Keep the module docstring's credential paragraphs. Replace the body from `DEFAULT_HOME` down with:

```python
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import tomllib
import tomli_w
from dotenv import load_dotenv

from . import host

log = logging.getLogger("fridgesheet.config")

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

#: Temporary: cli.py imports this until Task 4 moves it to host.credentials.
KEYRING_SERVICE = os.environ.get("FRIDGESHEET_KEYRING_SERVICE", "fridgesheet")
KEYRING_LABEL = "Fridge Sheet OneLogin"


class ConfigError(RuntimeError):
    pass


def _default_home() -> Path:
    """~/.fridgesheet on Linux, %LOCALAPPDATA%\\fridgesheet on Windows; FRIDGESHEET_HOME wins."""
    if os.environ.get("FRIDGESHEET_HOME"):
        return Path(os.environ["FRIDGESHEET_HOME"])
    if host.IS_WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "fridgesheet"
    return Path.home() / ".fridgesheet"


DEFAULT_HOME = _default_home()


def env_file() -> Path:
    """The .env to load: FRIDGESHEET_ENV_FILE if set, else <home>/.env."""
    return Path(os.environ.get("FRIDGESHEET_ENV_FILE") or DEFAULT_HOME / ".env")


def config_file() -> Path:
    return DEFAULT_HOME / "config.toml"


def _load_env_files() -> None:
    for c in (env_file(), Path.cwd() / ".env"):
        if c.is_file():
            load_dotenv(c, override=False)


def load_config_doc(path: Path) -> dict:
    """The raw config.toml as a dict. Missing file -> {}. Unparseable -> ConfigError naming the file."""
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"cannot parse {path}: {e}") from e


def save_config_doc(path: Path, doc: dict) -> None:
    """Write config.toml atomically. Never receives a password: callers keep it out of `doc`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config-", suffix=".toml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(tomli_w.dumps(doc).encode("utf-8"))
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def parse_nicknames(text: str) -> dict[str, str]:
    """'Alex=Al,Katherine=Kate' -> {'Alex': 'Al', 'Katherine': 'Kate'}."""
    out: dict[str, str] = {}
    for pair in (text or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
    return out


def _op_read(ref: str) -> str:
    # unchanged from today
    ...


def _keyring_read(key: str) -> str | None:
    # unchanged from today (moves to host.credentials_linux in Task 4)
    ...


def keyring_write(key: str, value: str) -> None:
    # unchanged from today (moves to host.credentials_linux in Task 4)
    ...


@dataclass
class ReportConfig:
    enabled: bool = False
    time: str = "14:00"
    days: list[str] = field(default_factory=lambda: list(WEEKDAYS))
    options: dict = field(default_factory=dict)      # report-specific, e.g. days_ahead, overdue_days


@dataclass
class Settings:
    home: Path = DEFAULT_HOME
    canvas_base: str = "https://lakota.instructure.com"
    hac_base: str = "https://hac.lakotainline.com/HomeAccess"
    onelogin_host: str = "lakota.onelogin.com"
    timezone: str = "America/New_York"
    headless: bool = True
    user_agent: str = ""
    cache_ttl_minutes: int = 180
    sheets_archive: str = ""
    username: str = ""                 # OneLogin username from config.toml; the password is in the OS store
    printer: str = ""                  # blank = the system default printer
    nicknames: dict[str, str] = field(default_factory=dict)
    reports: dict[str, ReportConfig] = field(default_factory=dict)
    onelogin_user_selector: str = "input#username, input[name='username'], input[type='email']"
    onelogin_pass_selector: str = "input#password, input[name='password'], input[type='password']"
    onelogin_submit_selector: str = "button[type='submit'], input[type='submit']"
    onelogin_portal_path: str = "/portal/"
    hac_app_url: str = ""
    hac_app_pattern: str = r"home ?access|\bhac\b"
    _username: str | None = field(default=None, repr=False)
    _password: str | None = field(default=None, repr=False)

    @property
    def profile_dir(self) -> Path:
        return self.home / "browser-profile"

    @property
    def cache_dir(self) -> Path:
        return self.home / "cache"

    def report_config(self, key: str, default_time: str = "14:00") -> ReportConfig:
        return self.reports.get(key) or ReportConfig(time=default_time)

    def credentials(self) -> tuple[str, str]:
        # unchanged from today in this task; Task 4 routes it through host.credentials
        ...


def settings_from_doc(doc: dict, s: Settings) -> None:
    """Apply config.toml. Unknown sections and keys are ignored so a newer file works with an older app."""
    acct, prn, kids = doc.get("account") or {}, doc.get("print") or {}, doc.get("kids") or {}
    s.username = str(acct.get("username", s.username))
    s.printer = str(prn.get("printer", s.printer))
    s.sheets_archive = str(prn.get("archive", s.sheets_archive))
    nick = kids.get("nicknames") or {}
    s.nicknames = {str(k): str(v) for k, v in nick.items()} if isinstance(nick, dict) else {}
    for key, sect in (doc.get("reports") or {}).items():
        if not isinstance(sect, dict):
            continue
        known = {"enabled", "time", "days"}
        s.reports[key] = ReportConfig(
            enabled=bool(sect.get("enabled", False)),
            time=str(sect.get("time", "14:00")),
            days=[str(d) for d in sect.get("days", WEEKDAYS)],
            options={k: v for k, v in sect.items() if k not in known},
        )


def load_settings() -> Settings:
    _load_env_files()
    s = Settings()
    settings_from_doc(load_config_doc(config_file()), s)
    s.canvas_base = os.environ.get("FRIDGESHEET_CANVAS_BASE", s.canvas_base).rstrip("/")
    s.hac_base = os.environ.get("FRIDGESHEET_HAC_BASE", s.hac_base).rstrip("/")
    s.onelogin_host = os.environ.get("FRIDGESHEET_ONELOGIN_HOST", s.onelogin_host)
    s.headless = os.environ.get("FRIDGESHEET_HEADLESS", "1") not in ("0", "false", "no")
    s.user_agent = os.environ.get("FRIDGESHEET_USER_AGENT", s.user_agent)
    s.cache_ttl_minutes = int(os.environ.get("FRIDGESHEET_CACHE_TTL_MINUTES", s.cache_ttl_minutes))
    s.sheets_archive = os.environ.get("FRIDGESHEET_SHEETS_ARCHIVE", s.sheets_archive).strip()
    s.printer = os.environ.get("FRIDGESHEET_PRINTER", s.printer).strip()
    s.nicknames = {**s.nicknames, **parse_nicknames(os.environ.get("FRIDGESHEET_NICKNAMES", ""))}
    s.hac_app_url = os.environ.get("FRIDGESHEET_HAC_ONELOGIN_APP_URL", s.hac_app_url)
    s.hac_app_pattern = os.environ.get("FRIDGESHEET_HAC_APP_PATTERN", s.hac_app_pattern)
    for k in ("onelogin_user_selector", "onelogin_pass_selector", "onelogin_submit_selector"):
        v = os.environ.get("FRIDGESHEET_" + k.upper())
        if v:
            setattr(s, k, v)
    for d in (s.home, s.profile_dir, s.cache_dir):
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        d.chmod(0o700)
    return s
```

The three `...` bodies are the current code, copied verbatim; they are not placeholders for new code.

- [ ] **Step 6: Take nicknames and the printer default out of `print_sheet.py` and `cli.py`**

In `print_sheet.py`: delete `DEFAULT_PRINTER` (line 36) and the `nicknames()` function (lines 98-105); change `Options.printer` to `printer: str | None = None`; change `_wanted` and its two uses:

```python
def _wanted(key: str, kid: str | None, names: dict[str, str]) -> bool:
    if not kid:
        return True
    a, b = key.lower(), kid.lower()
    return a.startswith(b) or b.startswith(a) or names.get(key, "").lower().startswith(b)
```

Line 214 `names = nicknames()` becomes `names = settings.nicknames`; line 221 `_wanted(key, opts.kid)` becomes `_wanted(key, opts.kid, names)`. Line 248 becomes:

```python
    printer = opts.printer or settings.printer or None
    cmd = ["lp", *(["-d", printer] if printer else []), "-o", "sides=two-sided-long-edge", "-o", "media=Letter", "-t", f"fridgesheet open work {day}", str(pdf)]
```

In `cli.py` line 164: `ps.add_argument("--printer", default=os.environ.get("FRIDGESHEET_PRINTER") or None, help="printer name (default: config.toml, then the system default)")`.

- [ ] **Step 7: Fix the print-sheet test fixture, which relied on the built-in nickname**

In `tests/test_print_sheet.py`, the `env` fixture: after `s = Settings(home=tmp_path)` add `s.nicknames = {"Alex": "Al"}`. Nothing else in that file changes.

- [ ] **Step 8: Genericise the late-rules seed, the examples, and the unit file**

`late_rules.py` `SEED` becomes:

```python
SEED = '''# Late-work rules for the printed sheet. Edit freely; re-read on every run.
#
# An overdue item is shown only while it can still earn credit. First matching
# [[rule]] wins; "kid" and "course" are optional (course = case-insensitive
# substring of the class name). "late_days" = days after the due date the teacher
# still accepts work (0 = no late work). Or "until = \\"quarter_end\\"" for a teacher
# who accepts late work through the grading period. "credit" is printed on the
# sheet next to the deadline; "source" is just for you.

[default]
late_days = 14
credit = "?"

[quarters]                     # Lakota board-approved 2026-27 calendar
q1 = 2026-10-15
q2 = 2026-12-18
q3 = 2027-03-11
q4 = 2027-05-20

# Example: one class that closes late work after a week at half credit.
# [[rule]]
# course = "Honors English 9"
# late_days = 7
# credit = "50%"
# source = "class syllabus, 2026-27"
'''
```

`env.example` line 31 becomes `# FRIDGESHEET_SHEETS_ARCHIVE=/path/to/a/folder/people/look/in/Open Work Sheets` and add after line 28:

```
# FRIDGESHEET_PRINTER=            # printer name; blank = system default (lpstat -a lists them)
# FRIDGESHEET_NICKNAMES=Alex=Al,Katherine=Kate   # snapshot first name = name printed on the sheet
# Most settings can also live in ~/.fridgesheet/config.toml; the environment wins.
```

Both `desktop/*.desktop`: `Exec=/home/tony/fridgesheet/scripts/fridgesheet-desktop.sh pdf` becomes `Exec=bash -c '"$HOME/fridgesheet/scripts/fridgesheet-desktop.sh" pdf'` (and `print` in the other). `.desktop` files do not expand `$HOME` themselves, hence the explicit `bash -c`.

`systemd/fridgesheet-print-sheet.service` line 9-10 become:

```
# The printer is set explicitly; the CUPS default is not used. `lpstat -a` lists names.
Environment=FRIDGESHEET_PRINTER=Brother_MFC_J4335DW
```

(Only the comment changes; the example value stays a real name so a copied unit works.)

- [ ] **Step 9: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 10: Commit**

```bash
git add -A fridgesheet tests pyproject.toml env.example desktop systemd
git commit -m "Read settings from config.toml with env overriding; drop the family-specific defaults

Adds ReportConfig, per-OS home dir, parse_nicknames, and the tomli-w / tzdata deps.
The Alex=Al default and the Stein-specific late-rules seed leave the code.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 4: `host.credentials` (secret-tool on Linux, Credential Manager on Windows)

**Files:**
- Create: `fridgesheet/host/credentials.py`, `credentials_linux.py`, `credentials_windows.py`
- Modify: `fridgesheet/config.py` (remove `_keyring_read`, `keyring_write`, `KEYRING_SERVICE`, `KEYRING_LABEL`; reroute `Settings.credentials`)
- Modify: `fridgesheet/cli.py:13, 72-96, 146-148` (`set-credentials`)
- Test: `tests/test_host_credentials.py`

**Interfaces:**
- Consumes: `config.Settings.username`, `config.load_config_doc`, `config.save_config_doc`, `config.config_file` (Task 3)
- Produces, in `host.credentials`:
  - `SERVICE: str` (`FRIDGESHEET_KEYRING_SERVICE` env or `"fridgesheet"`)
  - `read_username(run=subprocess.run) -> str | None`
  - `read_password(username: str, run=subprocess.run) -> str | None`
  - `write(username: str, password: str, run=subprocess.run) -> None`
  - The same three names on `credentials_linux` and `credentials_windows`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_host_credentials.py
"""The OS password store. Linux = secret-tool (unchanged from the original config.py);
Windows = the keyring library's Credential Manager backend. Neither is touched here:
`run` and the keyring module are faked."""
from __future__ import annotations

import subprocess
import types

import pytest

from fridgesheet import config
from fridgesheet.host import credentials, credentials_linux, credentials_windows


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_linux_reads_with_secret_tool_lookup():
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return _R(0, "hunter2\n")

    assert credentials_linux.read_password("ignored", run=run) == "hunter2"
    cmd, kw = seen[0]
    assert cmd == ["secret-tool", "lookup", "service", credentials.SERVICE, "key", "password"]
    assert kw.get("timeout") == 20


def test_linux_read_returns_none_when_secret_tool_is_missing_or_fails():
    def missing(cmd, **kw):
        raise FileNotFoundError
    assert credentials_linux.read_password("x", run=missing) is None
    assert credentials_linux.read_username(run=lambda c, **k: _R(1)) is None

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 20)
    assert credentials_linux.read_password("x", run=slow) is None


def test_linux_write_passes_the_secret_on_stdin_not_argv():
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return _R(0)

    credentials_linux.write("p@x.com", "hunter2", run=run)
    assert [c[0][:2] for c in seen] == [["secret-tool", "store"], ["secret-tool", "store"]]
    for cmd, kw in seen:
        assert "hunter2" not in " ".join(cmd) and kw["input"] in ("p@x.com", "hunter2")
    assert seen[0][0][-2:] == ["key", "username"] and seen[1][0][-2:] == ["key", "password"]


def test_linux_write_failure_raises_without_the_secret():
    with pytest.raises(RuntimeError) as e:
        credentials_linux.write("u", "hunter2", run=lambda c, **k: _R(1, "", "locked"))
    assert "locked" in str(e.value) and "hunter2" not in str(e.value)


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}
    mod = types.SimpleNamespace(
        get_password=lambda svc, user: store.get((svc, user)),
        set_password=lambda svc, user, pw: store.__setitem__((svc, user), pw),
    )
    monkeypatch.setattr(credentials_windows, "_keyring", lambda: mod)
    return store


def test_windows_round_trip_through_keyring(fake_keyring):
    credentials_windows.write("p@x.com", "hunter2")
    assert fake_keyring == {(credentials.SERVICE, "p@x.com"): "hunter2"}
    assert credentials_windows.read_password("p@x.com") == "hunter2"
    assert credentials_windows.read_password("nobody") is None
    assert credentials_windows.read_username() is None     # the username lives in config.toml


def test_settings_credentials_prefers_env_then_store(monkeypatch):
    monkeypatch.delenv("FRIDGESHEET_ONELOGIN_USERNAME", raising=False)
    monkeypatch.delenv("FRIDGESHEET_ONELOGIN_PASSWORD", raising=False)
    monkeypatch.delenv("FRIDGESHEET_OP_USERNAME_REF", raising=False)
    monkeypatch.delenv("FRIDGESHEET_OP_PASSWORD_REF", raising=False)
    monkeypatch.setattr(credentials, "read_username", lambda run=None: None)
    monkeypatch.setattr(credentials, "read_password", lambda user, run=None: "stored" if user == "cfg@x.com" else None)
    s = config.Settings(username="cfg@x.com")
    assert s.credentials() == ("cfg@x.com", "stored")
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_USERNAME", "env@x.com")
    monkeypatch.setenv("FRIDGESHEET_ONELOGIN_PASSWORD", "envpw")
    assert config.Settings(username="cfg@x.com").credentials() == ("env@x.com", "envpw")


def test_settings_credentials_falls_back_to_store_username_then_errors(monkeypatch):
    for k in ("FRIDGESHEET_ONELOGIN_USERNAME", "FRIDGESHEET_ONELOGIN_PASSWORD", "FRIDGESHEET_OP_USERNAME_REF", "FRIDGESHEET_OP_PASSWORD_REF"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(credentials, "read_username", lambda run=None: "ring@x.com")
    monkeypatch.setattr(credentials, "read_password", lambda user, run=None: "ringpw")
    assert config.Settings().credentials() == ("ring@x.com", "ringpw")
    monkeypatch.setattr(credentials, "read_username", lambda run=None: None)
    with pytest.raises(RuntimeError) as e:
        config.Settings().credentials()
    assert "set-credentials" in str(e.value)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_host_credentials.py -q`
Expected: FAIL at import (`cannot import name 'credentials' from 'fridgesheet.host'`).

- [ ] **Step 3: Write the three credential modules**

```python
# fridgesheet/host/credentials.py
"""The OS password store: where `set-credentials` puts the OneLogin password.

Linux: freedesktop Secret Service through `secret-tool` (GNOME keyring), exactly as the
original config.py did, so an existing entry keeps working. Windows: Credential Manager
through the `keyring` library. Nothing here logs or prints a secret.
"""
from __future__ import annotations

import os

from . import IS_WINDOWS

SERVICE: str = os.environ.get("FRIDGESHEET_KEYRING_SERVICE", "fridgesheet")

if IS_WINDOWS:
    from . import credentials_windows as _impl
else:
    from . import credentials_linux as _impl

read_username = _impl.read_username
read_password = _impl.read_password
write = _impl.write
```

```python
# fridgesheet/host/credentials_linux.py
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger("fridgesheet.host.credentials")
LABEL = "Fridge Sheet OneLogin"


def _service() -> str:
    from .credentials import SERVICE
    return SERVICE


def _lookup(key: str, run) -> str | None:
    """None when unavailable so the caller falls through. A locked keyring makes secret-tool
    block on a GUI prompt, which would hang a timer forever -- hence the timeout."""
    try:
        p = run(["secret-tool", "lookup", "service", _service(), "key", key], capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        log.warning("secret-tool timed out reading %r; is the login keyring locked?", key)
        return None
    if p.returncode != 0 or not p.stdout:
        return None
    return p.stdout.rstrip("\n")


def read_username(run=subprocess.run) -> str | None:
    return _lookup("username", run)


def read_password(username: str, run=subprocess.run) -> str | None:
    return _lookup("password", run)      # the Secret Service entry is keyed by attribute, not by user


def _store(key: str, value: str, run) -> None:
    """`value` goes on stdin, never argv, so it cannot leak through the process table."""
    p = run(["secret-tool", "store", "--label", LABEL, "service", _service(), "key", key],
            input=value, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError(f"`secret-tool store` failed for {key!r}: {(p.stderr or '').strip()[:200]}")


def write(username: str, password: str, run=subprocess.run) -> None:
    _store("username", username, run)
    _store("password", password, run)
```

```python
# fridgesheet/host/credentials_windows.py
"""Windows Credential Manager via the `keyring` library (Windows extra). Imported lazily so
the module loads, and tests can fake it, on any OS."""
from __future__ import annotations

import subprocess


def _keyring():
    import keyring
    return keyring


def _service() -> str:
    from .credentials import SERVICE
    return SERVICE


def read_username(run=subprocess.run) -> str | None:
    return None      # config.toml [account].username is the username on Windows


def read_password(username: str, run=subprocess.run) -> str | None:
    if not username:
        return None
    return _keyring().get_password(_service(), username)


def write(username: str, password: str, run=subprocess.run) -> None:
    _keyring().set_password(_service(), username, password)
```

- [ ] **Step 4: Reroute `Settings.credentials()` and delete the old keyring code from `config.py`**

Delete `KEYRING_SERVICE`, `KEYRING_LABEL`, `_keyring_read`, `keyring_write` from `config.py`. Replace the body of `Settings.credentials`:

```python
    def credentials(self) -> tuple[str, str]:
        """Return (username, password). Resolved lazily and never logged.
        Order: environment; config.toml username (or the store's) + the OS store; 1Password refs."""
        if self._username and self._password:
            return self._username, self._password
        from .host import credentials as store
        user = os.environ.get("FRIDGESHEET_ONELOGIN_USERNAME")
        pw = os.environ.get("FRIDGESHEET_ONELOGIN_PASSWORD")
        if not (user and pw):
            user = user or self.username or store.read_username()
            pw = pw or (store.read_password(user) if user else None)
        if not (user and pw):
            uref = os.environ.get("FRIDGESHEET_OP_USERNAME_REF")
            pref = os.environ.get("FRIDGESHEET_OP_PASSWORD_REF")
            if uref and pref:
                user, pw = user or _op_read(uref), pw or _op_read(pref)
        if not (user and pw):
            raise RuntimeError(
                "No credentials available. Run `fridgesheet set-credentials` to store them in "
                "the OS credential store, or provide FRIDGESHEET_ONELOGIN_USERNAME/PASSWORD in the "
                "environment, or set FRIDGESHEET_OP_USERNAME_REF/FRIDGESHEET_OP_PASSWORD_REF for the 1Password CLI."
            )
        self._username, self._password = user, pw
        return user, pw
```

- [ ] **Step 5: Point `set-credentials` at the store and record the username in `config.toml`**

In `cli.py` replace line 13 with `from .config import Settings, config_file, load_config_doc, load_settings, save_config_doc` and add `from .host import credentials as credstore`. Replace `cmd_set_credentials`:

```python
def cmd_set_credentials(args) -> int:
    """Store the OneLogin username/password in the OS credential store (GNOME keyring on
    Linux, Credential Manager on Windows) and remember the username in config.toml."""
    load_settings()
    if not sys.stdin.isatty():
        print("set-credentials needs a terminal so the password is never echoed or logged.", file=sys.stderr)
        print("Run it yourself in a shell, or (Linux) pipe a value from your password manager", file=sys.stderr)
        print("into secret-tool, e.g.:", file=sys.stderr)
        print("  op read --no-newline 'op://Vault/<uuid>/password' | \\", file=sys.stderr)
        print(f"    secret-tool store --label 'Fridge Sheet OneLogin' service {credstore.SERVICE} key password", file=sys.stderr)
        return 2
    user = args.username or input("OneLogin username: ").strip()
    if not user:
        print("No username given.", file=sys.stderr)
        return 2
    pw = getpass.getpass("OneLogin password (not echoed): ")
    if not pw:
        print("No password given.", file=sys.stderr)
        return 2
    credstore.write(user, pw)
    del pw
    doc = load_config_doc(config_file())
    doc.setdefault("account", {})["username"] = user
    save_config_doc(config_file(), doc)
    print(f"Stored under service={credstore.SERVICE!r}; username recorded in {config_file()}.")
    print("Verify with:  fridgesheet check")
    return 0
```

Line 146's help text becomes `"store OneLogin credentials in the OS credential store"`.

- [ ] **Step 6: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add fridgesheet/host fridgesheet/config.py fridgesheet/cli.py tests/test_host_credentials.py
git commit -m "Move the password store behind host.credentials; Credential Manager on Windows

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: `host.printing` (CUPS on Linux, SumatraPDF on Windows) and the `printers` command

**Files:**
- Create: `fridgesheet/host/printing.py`, `printing_linux.py`, `printing_windows.py`
- Modify: `fridgesheet/cli.py` (add `printers`)
- Test: `tests/test_host_printing.py`

**Interfaces:**
- Consumes: `host.CREATE_NO_WINDOW`, `host.IS_WINDOWS` (Task 3)
- Produces, on `host.printing` and on each `printing_*` module:
  - `PrintError(RuntimeError)` (defined once in `host/printing.py`; the `_linux`/`_windows` modules import it from there via a late import to avoid a cycle, see code)
  - `list_printers(run=subprocess.run) -> list[str]`
  - `default_printer(run=subprocess.run) -> str | None`
  - `print_pdf(pdf: Path, printer: str | None, title: str, run=subprocess.run, now: datetime | None = None) -> str` returning a job reference; `printer=None` means the system default.
  - `printing_windows.sumatra_path() -> Path`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_host_printing.py
"""Printing adapters. Only command lines are asserted; nothing is printed."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from fridgesheet.host import printing, printing_linux, printing_windows


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _recorder(result=_R()):
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return result
    return seen, run


def test_linux_lists_and_defaults_from_lpstat():
    seen, run = _recorder(_R(0, "Brother_MFC accepting requests since Mon\nCanon_LBP accepting requests since Tue\n"))
    assert printing_linux.list_printers(run=run) == ["Brother_MFC", "Canon_LBP"]
    assert seen[0][0] == ["lpstat", "-a"]
    assert printing_linux.default_printer(run=lambda c, **k: _R(0, "system default destination: Canon_LBP\n")) == "Canon_LBP"
    assert printing_linux.default_printer(run=lambda c, **k: _R(0, "no system default destination\n")) is None
    assert printing_linux.list_printers(run=lambda c, **k: (_ for _ in ()).throw(FileNotFoundError())) == []


def test_linux_print_builds_lp_command_and_returns_the_request_id():
    seen, run = _recorder(_R(0, "request id is Brother_MFC-42 (1 file(s))\n"))
    job = printing_linux.print_pdf(Path("/tmp/s.pdf"), "Brother_MFC", "fridgesheet open work 2026-09-14", run=run)
    assert job == "Brother_MFC-42"
    cmd = seen[0][0]
    assert cmd[:3] == ["lp", "-d", "Brother_MFC"]
    assert "sides=two-sided-long-edge" in cmd and "media=Letter" in cmd and cmd[-1] == "/tmp/s.pdf"
    assert cmd[cmd.index("-t") + 1] == "fridgesheet open work 2026-09-14"


def test_linux_print_default_printer_omits_dash_d_and_failure_raises():
    seen, run = _recorder(_R(0, "request id is Canon-7 (1 file(s))\n"))
    printing_linux.print_pdf(Path("/tmp/s.pdf"), None, "t", run=run)
    assert "-d" not in seen[0][0]
    with pytest.raises(printing.PrintError) as e:
        printing_linux.print_pdf(Path("/tmp/s.pdf"), "X", "t", run=lambda c, **k: _R(1, "", "lp: The printer or class does not exist."))
    assert "does not exist" in str(e.value)


@pytest.fixture
def win(monkeypatch, tmp_path):
    exe = tmp_path / "SumatraPDF.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(printing_windows, "sumatra_path", lambda: exe)
    monkeypatch.setattr(printing_windows, "list_printers", lambda run=None: ["Brother MFC-J4335DW", "Microsoft Print to PDF"])
    monkeypatch.setattr(printing_windows, "default_printer", lambda run=None: "Microsoft Print to PDF")
    return exe


def test_windows_print_runs_sumatra_silently_with_duplex(win):
    seen, run = _recorder(_R(0))
    at = datetime(2026, 9, 14, 14, 2)
    job = printing_windows.print_pdf(Path(r"C:\s\sheet.pdf"), "Brother MFC-J4335DW", "t", run=run, now=at)
    cmd, kw = seen[0]
    assert cmd == [str(win), "-print-to", "Brother MFC-J4335DW", "-print-settings", "duplexlong,paper=letter",
                   "-silent", "-exit-when-done", r"C:\s\sheet.pdf"]
    assert kw["creationflags"] == printing_windows.CREATE_NO_WINDOW
    assert job == "Brother MFC-J4335DW @ 14:02"


def test_windows_default_printer_and_errors(win):
    seen, run = _recorder(_R(0))
    job = printing_windows.print_pdf(Path("s.pdf"), None, "t", run=run, now=datetime(2026, 9, 14, 14, 2))
    assert "-print-to-default" in seen[0][0] and job == "Microsoft Print to PDF @ 14:02"
    with pytest.raises(printing.PrintError, match="not installed"):
        printing_windows.print_pdf(Path("s.pdf"), "Gone", "t", run=run)
    with pytest.raises(printing.PrintError, match="exit 1"):
        printing_windows.print_pdf(Path("s.pdf"), None, "t", run=lambda c, **k: _R(1))
    win.unlink()
    with pytest.raises(printing.PrintError, match="SumatraPDF"):
        printing_windows.print_pdf(Path("s.pdf"), None, "t", run=run)


def test_selector_exposes_the_same_names():
    for name in ("list_printers", "default_printer", "print_pdf", "PrintError"):
        assert hasattr(printing, name)


def test_printers_command_marks_the_default(monkeypatch, capsys):
    from fridgesheet import cli
    monkeypatch.setattr(printing, "list_printers", lambda: ["A", "B"])
    monkeypatch.setattr(printing, "default_printer", lambda: "B")
    with pytest.raises(SystemExit) as e:
        cli.main(["printers"])
    assert e.value.code == 0
    assert capsys.readouterr().out == "  A\n* B\n"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_host_printing.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Write the printing modules**

```python
# fridgesheet/host/printing.py
"""Print a PDF duplex on letter paper, and list printers.

Linux: CUPS (`lp`, `lpstat`). Windows: SumatraPDF (bundled by the installer; FRIDGESHEET_SUMATRA
overrides its path) because it is the one PDF printer on Windows that is silent, honours
duplex, and returns an exit code. `printer=None` means the system default on both.
"""
from __future__ import annotations

from . import IS_WINDOWS


class PrintError(RuntimeError):
    """The print could not be handed to the spooler. The PDF is left on disk."""


if IS_WINDOWS:
    from . import printing_windows as _impl
else:
    from . import printing_linux as _impl

list_printers = _impl.list_printers
default_printer = _impl.default_printer
print_pdf = _impl.print_pdf
```

```python
# fridgesheet/host/printing_linux.py
from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path


def _err():
    from .printing import PrintError
    return PrintError


def list_printers(run=subprocess.run) -> list[str]:
    try:
        p = run(["lpstat", "-a"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    return [line.split()[0] for line in (p.stdout or "").splitlines() if line.strip()]


def default_printer(run=subprocess.run) -> str | None:
    try:
        p = run(["lpstat", "-d"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"system default destination:\s*(\S+)", p.stdout or "")
    return m.group(1) if m else None


def print_pdf(pdf: Path, printer: str | None, title: str, run=subprocess.run, now: datetime | None = None) -> str:
    cmd = ["lp", *(["-d", printer] if printer else []), "-o", "sides=two-sided-long-edge", "-o", "media=Letter", "-t", title, str(pdf)]
    r = run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise _err()(f"lp failed ({r.returncode}): {((r.stderr or r.stdout) or '').strip()[:200]}")
    m = re.search(r"request id is (\S+)", r.stdout or "")
    return m.group(1) if m else (r.stdout or "").strip()
```

```python
# fridgesheet/host/printing_windows.py
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from . import CREATE_NO_WINDOW


def _err():
    from .printing import PrintError
    return PrintError


def sumatra_path() -> Path:
    """FRIDGESHEET_SUMATRA, else SumatraPDF.exe next to the frozen executable (Plan 3 puts it there)."""
    if os.environ.get("FRIDGESHEET_SUMATRA"):
        return Path(os.environ["FRIDGESHEET_SUMATRA"])
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path.cwd()
    return base / "SumatraPDF.exe"


def list_printers(run=subprocess.run) -> list[str]:
    import win32print
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    return [p["pPrinterName"] for p in win32print.EnumPrinters(flags, None, 2)]


def default_printer(run=subprocess.run) -> str | None:
    import win32print
    try:
        return win32print.GetDefaultPrinter()
    except Exception:
        return None


def print_pdf(pdf: Path, printer: str | None, title: str, run=subprocess.run, now: datetime | None = None) -> str:
    exe = sumatra_path()
    if not exe.is_file():
        raise _err()(f"SumatraPDF not found at {exe}; reinstall Fridge Sheet")
    if printer and printer not in list_printers():
        raise _err()(f"printer {printer!r} is not installed (renamed or removed?)")
    target = ["-print-to", printer] if printer else ["-print-to-default"]
    cmd = [str(exe), *target, "-print-settings", "duplexlong,paper=letter", "-silent", "-exit-when-done", str(pdf)]
    r = run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=300)
    if r.returncode != 0:
        raise _err()(f"SumatraPDF exit {r.returncode}: {((r.stderr or r.stdout) or '').strip()[:200]}")
    name = printer or default_printer() or "default printer"
    return f"{name} @ {(now or datetime.now()):%H:%M}"
```

SumatraPDF has no job id to return, so the reference is printer plus time; `title` is unused on Windows and kept for signature parity.

- [ ] **Step 4: Add the `printers` command**

In `cli.py`:

```python
def cmd_printers(args) -> int:
    from .host import printing
    default = printing.default_printer()
    for name in printing.list_printers():
        print(f"{'*' if name == default else ' '} {name}")
    return 0
```

and in `main()` after the `status` parser: `sub.add_parser("printers", help="list printers; * marks the system default").set_defaults(fn=cmd_printers)`.

- [ ] **Step 5: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add fridgesheet/host fridgesheet/cli.py tests/test_host_printing.py
git commit -m "Add host.printing: CUPS on Linux, SumatraPDF on Windows, plus a printers command

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 6: `host.notify` and `host.opener`

**Files:**
- Create: `fridgesheet/host/notify.py`, `notify_linux.py`, `notify_windows.py`, `opener.py`
- Test: `tests/test_host_notify.py`

**Interfaces:**
- Produces:
  - `host.notify.toast(title: str, body: str, run=subprocess.run) -> None` (never raises; logs a warning on failure). Same on `notify_linux` / `notify_windows`.
  - `host.notify_windows.APP_ID = "Cairnea.FridgeSheet"` (Plan 3's Inno Setup script sets the same `AppUserModelID` on the Start menu shortcut).
  - `host.opener.open_file(path: Path, popen=subprocess.Popen) -> None`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_host_notify.py
from __future__ import annotations

import base64
import subprocess
from pathlib import Path

from fridgesheet import host
from fridgesheet.host import notify, notify_linux, notify_windows, opener


def _rec():
    seen = []

    def run(cmd, **kw):
        seen.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return seen, run


def test_linux_uses_notify_send_when_present(monkeypatch):
    seen, run = _rec()
    monkeypatch.setattr(notify_linux.shutil, "which", lambda n: "/usr/bin/notify-send")
    notify_linux.toast("Open Work Sheet", "Printed 2 pages", run=run)
    assert seen[0][0] == ["notify-send", "-a", "Fridge Sheet", "Open Work Sheet", "Printed 2 pages"]
    monkeypatch.setattr(notify_linux.shutil, "which", lambda n: None)
    notify_linux.toast("x", "y", run=run)
    assert len(seen) == 1


def test_windows_runs_an_encoded_powershell_toast_with_no_window():
    seen, run = _rec()
    notify_windows.toast("Open Work Sheet", 'Printed <2> pages & "more"', run=run)
    cmd, kw = seen[0]
    assert cmd[0] == "powershell" and "-NoProfile" in cmd and "-NonInteractive" in cmd
    script = base64.b64decode(cmd[cmd.index("-EncodedCommand") + 1]).decode("utf-16-le")
    assert notify_windows.APP_ID in script
    assert "Open Work Sheet" in script and "Printed &lt;2&gt; pages &amp; &quot;more&quot;" in script
    assert kw["creationflags"] == host.CREATE_NO_WINDOW and kw["timeout"] == 20


def test_toast_never_raises(monkeypatch):
    def boom(cmd, **kw):
        raise OSError("no powershell")
    notify_windows.toast("a", "b", run=boom)
    notify_linux.toast("a", "b", run=boom)
    assert hasattr(notify, "toast")


def test_opener_linux_prefers_evince_and_detaches(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    seen = []
    monkeypatch.setattr(opener.shutil, "which", lambda n: "/usr/bin/evince" if n == "evince" else None)
    opener.open_file(Path("/tmp/s.pdf"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    cmd, kw = seen[0]
    assert cmd == ["/usr/bin/evince", "/tmp/s.pdf"] and kw["start_new_session"] is True
    monkeypatch.setattr(opener.shutil, "which", lambda n: "/usr/bin/xdg-open" if n == "xdg-open" else None)
    opener.open_file(Path("/tmp/s.pdf"), popen=lambda cmd, **kw: seen.append((cmd, kw)))
    assert seen[1][0][0] == "/usr/bin/xdg-open"


def test_opener_windows_uses_startfile(monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seen = []
    monkeypatch.setattr(opener, "_startfile", lambda p: seen.append(p))
    opener.open_file(Path("C:/s.pdf"), popen=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no popen on Windows")))
    assert seen == [str(Path("C:/s.pdf"))]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_host_notify.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Write the modules**

```python
# fridgesheet/host/notify.py
"""A desktop notification at the end of a scheduled run. Best effort: never raises."""
from __future__ import annotations

from . import IS_WINDOWS

if IS_WINDOWS:
    from . import notify_windows as _impl
else:
    from . import notify_linux as _impl

toast = _impl.toast
```

```python
# fridgesheet/host/notify_linux.py
from __future__ import annotations

import logging
import shutil
import subprocess

log = logging.getLogger("fridgesheet.host.notify")


def toast(title: str, body: str, run=subprocess.run) -> None:
    if not shutil.which("notify-send"):
        return
    try:
        run(["notify-send", "-a", "Fridge Sheet", title, body], capture_output=True, text=True, timeout=20)
    except Exception as e:
        log.warning("notify-send failed: %s", e)
```

```python
# fridgesheet/host/notify_windows.py
"""Windows toast via PowerShell and the WinRT ToastNotificationManager. No third-party
toast library. The script is passed base64 UTF-16LE (-EncodedCommand) so titles and
bodies never touch shell quoting; inside the XML they are entity-escaped."""
from __future__ import annotations

import base64
import logging
import subprocess
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW

log = logging.getLogger("fridgesheet.host.notify")

#: Must match the AppUserModelID Inno Setup puts on the Start menu shortcut (Plan 3).
APP_ID = "Cairnea.FridgeSheet"

_SCRIPT = """
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>{title}</text><text>{body}</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show($toast)
"""


def _xml_text(s: str) -> str:
    # escape() handles & < >; quotes are escaped too because the XML sits inside a PS single-quoted string
    return escape(s, {'"': "&quot;", "'": "&apos;"})


def toast(title: str, body: str, run=subprocess.run) -> None:
    script = _SCRIPT.format(title=_xml_text(title), body=_xml_text(body), app_id=APP_ID)
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-EncodedCommand", encoded]
    try:
        run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=20)
    except Exception as e:
        log.warning("toast failed: %s", e)
```

```python
# fridgesheet/host/opener.py
"""Open a file in the desktop's viewer, detached from us so it outlives a terminal window."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import fridgesheet.host as host   # attribute lookup at call time, so tests can flip IS_WINDOWS


def _startfile(path: str) -> None:
    os.startfile(path)  # type: ignore[attr-defined]  # Windows only


def open_file(path: Path, popen=subprocess.Popen) -> None:
    if host.IS_WINDOWS:
        _startfile(str(path))
        return
    viewer = shutil.which("evince") or shutil.which("xdg-open")
    if not viewer:
        raise RuntimeError("no PDF viewer found (evince or xdg-open)")
    popen([viewer, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
```

- [ ] **Step 4: Run the whole suite, commit**

Run: `python3 -m pytest -q` — all pass.

```bash
git add fridgesheet/host tests/test_host_notify.py
git commit -m "Add host.notify (notify-send / PowerShell toast) and host.opener

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Report plugin layer and the generic runner; `print-sheet` becomes an alias

This is the structural split. `print_sheet.py` keeps its public names (`Options`, `run`, `parse_skip_days`, `school_year`) so `tests/test_print_sheet.py` runs unchanged and proves nothing regressed.

**Files:**
- Create: `fridgesheet/reports/__init__.py`, `base.py`, `open_work.py`
- Create: `fridgesheet/runner.py`
- Rewrite: `fridgesheet/print_sheet.py`
- Modify: `fridgesheet/cli.py` (add `run`, `reports`; `print-sheet` unchanged)
- Test: `tests/test_reports.py`, `tests/test_runner.py`

**Interfaces:**
- Consumes: `config.Settings.nicknames/printer/report_config` (Task 3); `host.printing.print_pdf`, `PrintError` (Task 5); `host.notify.toast` (Task 6); `dates.*` (Task 2)
- Produces:
  - `reports.base.BuildContext(settings, home, day, now, out_dir, kid, nicknames, prev_rows, prev_label, stale_note, options, data_as_of)`
  - `reports.base.Built(pdf: Path, rows: dict, summary: str)`
  - `reports.base.ReportError(RuntimeError)`
  - `reports.base.Report` protocol: `key`, `title`, `output_dir`, `default_time`, `archive_name(day) -> str`, `build(snap, ctx) -> Built`
  - `reports.REPORTS: dict[str, Report]`, `reports.get(key) -> Report` (raises `ReportError` listing known keys)
  - `runner.RunOptions(dry_run=False, force=False, reprint=False, date=None, kid=None, no_refresh=False, printer=None, options={}, notify=True)`
  - `runner.run(report_key: str, opts: RunOptions, settings: Settings, *, now=None, refresh=collector.collect, print_pdf=None, toast=None) -> int`
  - `runner.parse_skip_days`, `runner.school_year`, `runner.archive_copy(pdf, archive_root, day, name)`, `runner.data_as_of`, `runner.SKIP_SEED`, `runner.LOG_NAME = "print-sheet.log"`, `runner.LOCK_NAME = "run.lock"`
  - `print_sheet.Options` (fields as today, `printer: str | None = None`) and `print_sheet.run(opts, settings, *, now=None, refresh=..., lp=None)`; when `lp` is given it is the injected CUPS `run` and notifications are off.

- [ ] **Step 1: Write the failing report tests**

```python
# tests/test_reports.py
"""The report registry and the open-work report's build(), isolated from the runner."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from fridgesheet import reports  # noqa: E402
from fridgesheet.config import Settings  # noqa: E402
from fridgesheet.reports.base import BuildContext, ReportError  # noqa: E402

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 11, 14, 5, tzinfo=TZ)


def _snapshot() -> dict:
    a = {"id": 1, "name": "WS 1", "due_at": (NOW + timedelta(days=2)).isoformat(), "unlock_at": None, "created_at": None,
         "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "published": True, "score": None,
         "grade": None, "state": "unsubmitted", "late": False, "missing": False, "excused": False}
    return {"fetched_at": NOW.isoformat(), "fetched_at_epoch": NOW.timestamp(), "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
            "students": {"Alex": {"name": "Alex S", "canvas": {"courses": [{"id": 5, "name": "Honors Biology", "assignments": [a]}]}, "hac": {"classes": []}},
                         "Sam": {"name": "Sam S", "canvas": {"courses": []}, "hac": {"classes": []}}}}


def _ctx(tmp_path, **over) -> BuildContext:
    d = dict(settings=Settings(home=tmp_path), home=tmp_path, day=NOW.date(), now=NOW, out_dir=tmp_path / "out", kid=None,
             nicknames={"Alex": "Al"}, prev_rows=None, prev_label=None, stale_note=None, options={}, data_as_of=NOW)
    d.update(over)
    (d["out_dir"]).mkdir(parents=True, exist_ok=True)
    return BuildContext(**d)


def test_registry_has_open_work_with_its_metadata():
    r = reports.get("open-work")
    assert r.key == "open-work" and r.title == "Open Work Sheet" and r.output_dir == "sheets" and r.default_time == "14:00"
    assert r.archive_name(NOW.date()) == "2026-09-11 Open Work.pdf"
    with pytest.raises(ReportError, match="open-work"):
        reports.get("nope")


def test_open_work_builds_pdf_rows_and_summary(tmp_path):
    built = reports.get("open-work").build(_snapshot(), _ctx(tmp_path))
    assert built.pdf == tmp_path / "out" / "sheet.pdf" and built.pdf.read_bytes()[:4] == b"%PDF"
    assert set(built.rows) == {"Alex", "Sam"} and len(built.rows["Alex"]) == 1
    assert built.summary.startswith("1p Al=1 Sam=0")


def test_open_work_honours_kid_filter_options_and_previous_rows(tmp_path):
    r = reports.get("open-work")
    first = r.build(_snapshot(), _ctx(tmp_path, kid="al", options={"days_ahead": 1, "overdue_days": 3}))
    assert set(first.rows) == {"Alex"} and first.rows["Alex"] == []      # due in 2 days, window is 1
    second = r.build(_snapshot(), _ctx(tmp_path, prev_rows=first.rows, prev_label="Thu 9/10"))
    from fridgesheet import sheet
    assert "since last sheet" in sheet.pdf_text(second.pdf)
    with pytest.raises(ReportError, match="no student matches"):
        r.build(_snapshot(), _ctx(tmp_path, kid="zed"))
```

- [ ] **Step 2: Write the failing runner tests**

```python
# tests/test_runner.py
"""The generic runner, with the open-work report but fake refresh, printer and notifier.
The behavioural guards are covered by tests/test_print_sheet.py through the alias; this
file covers what is new: the lock, the configured window time, PrintError, toasts, and a
windowed process with no stderr."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("reportlab")

from fridgesheet import runner  # noqa: E402
from fridgesheet.config import ReportConfig, Settings  # noqa: E402
from fridgesheet.host.printing import PrintError  # noqa: E402
from tests.test_reports import _snapshot  # noqa: E402

TZ = ZoneInfo("America/New_York")
FRI_2PM = datetime(2026, 9, 11, 14, 5, tzinfo=TZ)


@pytest.fixture
def env(tmp_path):
    s = Settings(home=tmp_path, nicknames={"Alex": "Al"})
    s.cache_dir.mkdir(parents=True)
    (s.cache_dir / "snapshot.json").write_text(json.dumps(_snapshot()))
    calls = {"print": [], "toast": []}

    def print_pdf(pdf, printer, title):
        calls["print"].append((pdf, printer, title))
        return "job-1"

    def toast(title, body):
        calls["toast"].append((title, body))

    def refresh(settings, **kw):
        return _snapshot()

    return s, calls, refresh, print_pdf, toast


def _run(s, opts, **kw):
    return runner.run("open-work", opts, s, now=kw.pop("now", FRI_2PM), **kw)


def test_prints_toasts_and_records(env):
    s, calls, refresh, print_pdf, toast = env
    assert _run(s, runner.RunOptions(printer="Office"), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    (pdf, printer, title) = calls["print"][0]
    assert printer == "Office" and pdf == s.home / "sheets" / "2026-09-11" / "sheet.pdf" and "2026-09-11" in title
    assert "job-1" in (s.home / "sheets" / "2026-09-11" / "printed.txt").read_text()
    assert calls["toast"] == [("Open Work Sheet", "Printed Fri 9/11: 1p Al=1 Sam=0 data=9/11 14:05")]
    log = (s.home / runner.LOG_NAME).read_text()
    assert " OK " in log and "open-work" in log


def test_printer_falls_back_to_settings_then_none(env):
    s, calls, refresh, print_pdf, toast = env
    s.printer = "FromConfig"
    _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][0][1] == "FromConfig"
    s.printer = ""
    _run(s, runner.RunOptions(reprint=True), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["print"][1][1] is None


def test_print_error_is_a_fail_with_toast_and_pdf_kept(env):
    s, calls, refresh, _, toast = env

    def bad(pdf, printer, title):
        raise PrintError("printer 'Gone' is not installed")

    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=bad, toast=toast) == 1
    assert (s.home / "sheets" / "2026-09-11" / "sheet.pdf").is_file()
    assert not (s.home / "sheets" / "2026-09-11" / "printed.txt").exists()
    assert calls["toast"][0][1].startswith("Not printed: printer 'Gone'")
    assert "FAIL" in (s.home / runner.LOG_NAME).read_text()


def test_login_failure_toast_tells_them_where_to_look(env):
    s, calls, _, print_pdf, toast = env
    old = FRI_2PM - timedelta(hours=30)
    snap = _snapshot()
    snap["fetched_at_epoch"] = old.timestamp()
    (s.cache_dir / "snapshot.json").write_text(json.dumps(snap))

    def refresh(settings, **kw):
        raise RuntimeError("LoginRequired: OneLogin did not redirect")

    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 1
    assert "check your password" in calls["toast"][0][1]


def test_dry_run_and_notify_off_never_toast(env):
    s, calls, refresh, print_pdf, toast = env
    _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast)
    _run(s, runner.RunOptions(notify=False), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["toast"] == [] and len(calls["print"]) == 1


def test_skip_reasons_are_toasted(env):
    s, calls, refresh, print_pdf, toast = env
    _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=9), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert calls["toast"][0][1].startswith("Skipped: outside print window")


def test_window_uses_the_configured_report_time(env):
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(enabled=True, time="18:00")
    _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast)      # 14:05 < 18:00
    assert calls["print"] == [] and "before 18:00" in (s.home / runner.LOG_NAME).read_text()
    _run(s, runner.RunOptions(), now=FRI_2PM.replace(hour=18, minute=1), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert len(calls["print"]) == 1


def test_config_options_feed_the_report_and_cli_overrides_win(env):
    s, calls, refresh, print_pdf, toast = env
    s.reports["open-work"] = ReportConfig(options={"days_ahead": 1})
    _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert json.loads((s.home / "sheets" / "2026-09-11" / "rows.json").read_text())["Alex"] == []
    _run(s, runner.RunOptions(dry_run=True, options={"days_ahead": 14, "overdue_days": None}), refresh=refresh, print_pdf=print_pdf, toast=toast)
    assert len(json.loads((s.home / "sheets" / "2026-09-11" / "rows.json").read_text())["Alex"]) == 1


def test_lock_file_prevents_overlap_and_a_stale_lock_is_ignored(env):
    s, calls, refresh, print_pdf, toast = env
    lock = s.home / runner.LOCK_NAME
    lock.write_text(str(os.getpid()))
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert calls["print"] == [] and "already running" in (s.home / runner.LOG_NAME).read_text()
    os.utime(lock, (time.time() - 3600, time.time() - 3600))
    assert _run(s, runner.RunOptions(), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert len(calls["print"]) == 1 and not lock.exists()


def test_log_survives_a_windowed_process_with_no_stderr(env, monkeypatch):
    s, calls, refresh, print_pdf, toast = env
    monkeypatch.setattr(sys, "stderr", None)
    assert _run(s, runner.RunOptions(dry_run=True), refresh=refresh, print_pdf=print_pdf, toast=toast) == 0
    assert "dry-run" in (s.home / runner.LOG_NAME).read_text()


def test_unknown_report_is_a_logged_failure(env):
    s, calls, refresh, print_pdf, toast = env
    assert runner.run("nope", runner.RunOptions(), s, now=FRI_2PM, refresh=refresh, print_pdf=print_pdf, toast=toast) == 2
    assert "unknown report" in (s.home / runner.LOG_NAME).read_text()
```

- [ ] **Step 3: Run both files to verify they fail**

Run: `python3 -m pytest tests/test_reports.py tests/test_runner.py -q`
Expected: FAIL at import (`No module named 'fridgesheet.reports'`).

- [ ] **Step 4: Write `reports/base.py` and `reports/__init__.py`**

```python
# fridgesheet/reports/base.py
"""What a report is: one PDF for one day, built from the snapshot. The runner does
everything around it (guards, refresh, archive, print, record, notify)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from ..config import Settings


class ReportError(RuntimeError):
    """The report could not be built; the runner logs it as FAIL."""


@dataclass
class BuildContext:
    settings: Settings
    home: Path
    day: date
    now: datetime                    # tz-aware; the moment printed on the page
    out_dir: Path                    # <home>/<report.output_dir>/<day>/, already created
    kid: str | None                  # --kid filter, or None for everyone
    nicknames: dict[str, str]        # snapshot first name -> printed name
    prev_rows: dict | None           # rows.json from the most recent earlier day, if any
    prev_label: str | None           # e.g. "Thu 9/10"
    stale_note: str | None           # footer note when the refresh failed but data is fresh enough
    options: dict                    # report-specific: config.toml [reports.<key>] merged with CLI overrides
    data_as_of: datetime             # oldest fetch time in the snapshot


@dataclass
class Built:
    pdf: Path
    rows: dict                       # written to rows.json; the next run gets it as prev_rows
    summary: str                     # for the log line and the toast, e.g. "2p Al=5 Kate=2"


class Report(Protocol):
    key: str                         # "open-work": CLI, config section, task name
    title: str                       # "Open Work Sheet": app and toasts
    output_dir: str                  # "sheets" for open-work (existing paths); "reports/<key>" for new ones
    default_time: str                # "14:00"

    def archive_name(self, day: date) -> str: ...
    def build(self, snap: dict, ctx: BuildContext) -> Built: ...
```

```python
# fridgesheet/reports/__init__.py
"""Registry. Adding a report = a new module here plus one entry in REPORTS."""
from __future__ import annotations

from .base import Built, BuildContext, Report, ReportError
from .open_work import OpenWorkReport

REPORTS: dict[str, Report] = {
    "open-work": OpenWorkReport(),
}


def get(key: str) -> Report:
    try:
        return REPORTS[key]
    except KeyError:
        raise ReportError(f"unknown report {key!r}; known: {', '.join(REPORTS)}") from None


__all__ = ["REPORTS", "get", "Built", "BuildContext", "Report", "ReportError"]
```

- [ ] **Step 5: Write `reports/open_work.py` (moved from `print_sheet.run`, lines 213-236)**

```python
# fridgesheet/reports/open_work.py
"""The open-work sheet: one section per kid, the rows open_items says are still actionable."""
from __future__ import annotations

from datetime import date

from .. import late_rules, open_items, sheet
from .base import Built, BuildContext, ReportError


def _wanted(key: str, kid: str | None, names: dict[str, str]) -> bool:
    if not kid:
        return True
    a, b = key.lower(), kid.lower()
    return a.startswith(b) or b.startswith(a) or names.get(key, "").lower().startswith(b)


class OpenWorkReport:
    key = "open-work"
    title = "Open Work Sheet"
    output_dir = "sheets"
    default_time = "14:00"

    def archive_name(self, day: date) -> str:
        return f"{day.isoformat()} Open Work.pdf"

    def build(self, snap: dict, ctx: BuildContext) -> Built:
        days_ahead = int(ctx.options.get("days_ahead") or 14)
        overdue_days = int(ctx.options.get("overdue_days") or 14)
        rules = late_rules.load(ctx.home / "late-rules.toml")
        sheets: list[sheet.KidSheet] = []
        rows: dict[str, list[dict]] = {}
        counts = []
        for key, entry in snap["students"].items():
            if not _wanted(key, ctx.kid, ctx.nicknames):
                continue
            label = ctx.nicknames.get(key, key)
            work = open_items.open_items(entry, label, ctx.now, days_ahead=days_ahead, overdue_days=overdue_days, rules=rules)
            diff = open_items.compare(ctx.prev_rows.get(key, []), work.items) if ctx.prev_rows is not None else None
            sheets.append(sheet.KidSheet(label, work, diff, ctx.prev_label))
            rows[key] = [i.to_dict() for i in work.items]
            counts.append(f"{label}={len(work.items)}")
        if not sheets:
            raise ReportError(f"no student matches --kid {ctx.kid!r}; known: {', '.join(snap['students'])}")
        pdf = ctx.out_dir / "sheet.pdf"
        pages = sheet.build_pdf(sheets, pdf, data_as_of=ctx.data_as_of, days_ahead=days_ahead, overdue_days=overdue_days,
                                stale_note=ctx.stale_note, printed_at=ctx.now)
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {' '.join(counts)}")
```

- [ ] **Step 6: Write `runner.py`**

```python
# fridgesheet/runner.py
"""Run one report for one day: guards, refresh, build, archive, print, record, notify.

Files under the app home:
    no-print-days.txt        one YYYY-MM-DD (or YYYY-MM-DD..YYYY-MM-DD) per line, optional comment
    late-rules.toml          the late-work register (see late_rules)
    <output_dir>/<day>/      sheet.pdf, rows.json, printed.txt   (open-work: sheets/<day>/)
    print-sheet.log          one line per run for every report; also stderr when there is one
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
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import collector, late_rules, reports
from .config import Settings
from .dates import md, time12, wd_md, wd_md_time
from .reports.base import BuildContext, ReportError

MAX_DATA_AGE_HOURS = 24
LOG_NAME = "print-sheet.log"
LOCK_NAME = "run.lock"
LOCK_STALE_SECONDS = 30 * 60

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
class RunOptions:
    dry_run: bool = False
    force: bool = False
    reprint: bool = False            # a deliberate second print of a day; --force never implies it
    date: str | None = None
    kid: str | None = None
    no_refresh: bool = False
    printer: str | None = None       # None -> settings.printer -> system default
    options: dict = field(default_factory=dict)   # report-specific CLI overrides; None values are ignored
    notify: bool = True


def parse_skip_days(text: str) -> dict[date, str]:
    # unchanged from print_sheet.parse_skip_days
    ...


def school_year(d: date) -> str:
    """'2026-27' for any date from Aug 1 2026 through Jul 31 2027."""
    start = d.year if d.month >= 8 else d.year - 1
    return f"{start}-{(start + 1) % 100:02d}"


def archive_copy(pdf: Path, archive_root: str, day: date, name: str) -> Path:
    """Copy the PDF where people look for it: <archive>/<school year>/<name>."""
    dest = Path(archive_root).expanduser() / school_year(day) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, dest)
    return dest


def data_as_of(snap: dict) -> datetime:
    # unchanged from print_sheet.data_as_of
    ...


def _previous_rows(out_root: Path, day: date) -> tuple[dict | None, str | None]:
    # unchanged from print_sheet._previous_rows except the label uses wd_md(d)
    ...


def _window_open(now: datetime, hhmm: str) -> bool:
    h, m = (int(x) for x in hhmm.split(":", 1))
    return now.time() >= dtime(h, m)


class _Log:
    """One line per run, always to the log file, and to stderr when the process has one
    (a windowed exe has sys.stderr = None)."""

    def __init__(self, path: Path, now: datetime, key: str):
        self.path, self.now, self.key = path, now, key

    def __call__(self, level: str, msg: str) -> None:
        line = f"{self.now:%Y-%m-%d %H:%M:%S} {level:<5} {self.key} {msg}"
        if sys.stderr is not None:
            print(line, file=sys.stderr, flush=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


class _Lock:
    """Create-exclusive lock file; a lock older than LOCK_STALE_SECONDS is treated as abandoned."""

    def __init__(self, path: Path):
        self.path, self.held = path, False

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
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        self.held = True
        return True

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False


def _toast_body(level: str, msg: str, day: date) -> str:
    if level == "OK":
        return f"Printed {wd_md(day)}: {msg}"
    if level == "SKIP":
        return f"Skipped: {msg}"
    body = f"Not printed: {msg}"
    if "login" in msg.lower():
        body += ". Open Fridge Sheet to check your password."
    return body


def run(report_key: str, opts: RunOptions, settings: Settings, *, now: datetime | None = None,
        refresh=collector.collect, print_pdf=None, toast=None) -> int:
    tz = ZoneInfo(settings.timezone)
    now = now or datetime.now(tz)
    home = settings.home
    home.mkdir(parents=True, exist_ok=True)
    log = _Log(home / LOG_NAME, now, report_key)
    try:
        report = reports.get(report_key)
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

    def finish(level: str, msg: str, rc: int, toast_msg: str | None = None) -> int:
        """Log the line; toast a shorter form of it (the OK toast carries the summary, not the job id)."""
        log(level, msg)
        if opts.notify and not opts.dry_run:
            toast(report.title, _toast_body(level, toast_msg or msg, day))
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

    lock = _Lock(home / LOCK_NAME)
    if not lock.acquire():
        log("SKIP", "already running (run.lock present); nothing done")
        return 0
    try:
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
            return finish("FAIL", "no snapshot on disk and refresh failed" + (f": {refresh_error}" if refresh_error else ""), 1)
        as_of = data_as_of(snap).astimezone(tz)
        age_h = (now - as_of).total_seconds() / 3600
        stale_note = None
        if refresh_error:
            if age_h > MAX_DATA_AGE_HOURS:
                return finish("FAIL", f"refresh failed ({refresh_error}) and snapshot is stale ({age_h:.0f} h old, data from {as_of:%Y-%m-%d %H:%M}); nothing printed", 1)
            stale_note = f"refresh failed at {time12(now)}; data from {wd_md_time(as_of)}"

        # --- build ------------------------------------------------------------------
        prev_rows, prev_label = _previous_rows(out_root, day)
        at = now if not opts.date else datetime.combine(day, now.timetz())
        options = {**rc_cfg.options, **{k: v for k, v in opts.options.items() if v is not None}}
        day_dir.mkdir(parents=True, exist_ok=True)
        ctx = BuildContext(settings=settings, home=home, day=day, now=at, out_dir=day_dir, kid=opts.kid, nicknames=settings.nicknames,
                           prev_rows=prev_rows, prev_label=prev_label, stale_note=stale_note, options=options, data_as_of=as_of)
        try:
            built = report.build(snap, ctx)
        except ReportError as e:
            return finish("FAIL", str(e), 1)
        (day_dir / "rows.json").write_text(json.dumps(built.rows, indent=1))
        summary = f"{built.summary} data={md(as_of)} {as_of:%H:%M}" + (f" NOTE refresh failed: {refresh_error}" if refresh_error else "")
        if settings.sheets_archive:
            try:
                summary += f" saved={archive_copy(built.pdf, settings.sheets_archive, day, report.archive_name(day))}"
            except OSError as e:  # a missing Drive mount must not stop the print
                log("WARN", f"could not copy the sheet to the archive {settings.sheets_archive}: {e}")
        if opts.dry_run:
            log("OK", f"dry-run built {built.pdf} {summary}")
            return 0

        # --- print ------------------------------------------------------------------
        printer = opts.printer or settings.printer or None
        try:
            job = print_pdf(built.pdf, printer, f"fridgesheet {report.title.lower()} {day}")
        except PrintError as e:
            return finish("FAIL", f"{e}; PDF kept at {built.pdf}", 1)
        with (day_dir / "printed.txt").open("a") as f:   # append: a --reprint keeps the earlier job on record
            f.write(f"{now.isoformat()} {job}\n")
        return finish("OK", f"printed job={job} {summary}", 0, toast_msg=summary)
    finally:
        lock.release()
```

The two `...` bodies are moved verbatim from `print_sheet.py` (lines 77-95 and 129-133); `_previous_rows` is lines 136-147 with `d.strftime("%a %-m/%-d")` already replaced by `wd_md(d)` in Task 2.

Note the stale-snapshot FAIL message keeps the words "stale" and the refresh error text: `test_failed_refresh_with_stale_snapshot_prints_nothing_and_exits_nonzero` greps for both.

- [ ] **Step 7: Rewrite `print_sheet.py` as the alias**

```python
# fridgesheet/print_sheet.py
"""`fridgesheet print-sheet`: the original command, now an alias for `run open-work`.

Kept so the systemd unit, the desktop shortcuts and the tests keep working unchanged.
The behaviour lives in runner.py and reports/open_work.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import collector
from .config import Settings
from .runner import SKIP_SEED, RunOptions, archive_copy, data_as_of, parse_skip_days, school_year  # noqa: F401  (re-exports)
from .runner import run as _run


@dataclass
class Options:
    dry_run: bool = False
    kid: str | None = None
    date: str | None = None
    days: int = 14
    overdue_days: int = 14
    force: bool = False
    printer: str | None = None
    no_refresh: bool = False
    reprint: bool = False


def run(opts: Options, settings: Settings, *, now=None, refresh=collector.collect, lp=None) -> int:
    """`lp` is the injected CUPS `subprocess.run` used by the tests; when given, printing goes
    through the Linux adapter with it and desktop notifications are off."""
    print_pdf = None
    if lp is not None:
        from .host import printing_linux
        print_pdf = lambda pdf, printer, title: printing_linux.print_pdf(pdf, printer, title, run=lp)  # noqa: E731
    ro = RunOptions(dry_run=opts.dry_run, force=opts.force, reprint=opts.reprint, date=opts.date, kid=opts.kid,
                    no_refresh=opts.no_refresh, printer=opts.printer,
                    options={"days_ahead": opts.days, "overdue_days": opts.overdue_days}, notify=lp is None)
    return _run("open-work", ro, settings, now=now, refresh=refresh, print_pdf=print_pdf)
```

- [ ] **Step 8: Add `run` and `reports` to the CLI**

In `cli.py`:

```python
def cmd_run(args) -> int:
    from . import runner
    opts = runner.RunOptions(dry_run=args.dry_run, force=args.force, reprint=args.reprint, date=args.date, kid=args.kid,
                             no_refresh=args.no_refresh, printer=args.printer,
                             options={"days_ahead": args.days, "overdue_days": args.overdue_days})
    return runner.run(args.report, opts, load_settings())


def cmd_reports(args) -> int:
    from . import reports
    s = load_settings()
    for key, r in reports.REPORTS.items():
        rc = s.report_config(key, r.default_time)
        print(f"{key:<12} {r.title:<20} {'enabled' if rc.enabled else 'disabled':<9} {rc.time} {','.join(rc.days)}")
    return 0
```

and in `main()`, before the `print-sheet` parser:

```python
    rn = sub.add_parser("run", help="refresh, build one report, print it, record it")
    rn.add_argument("report", help="report key; see `fridgesheet reports`")
    rn.add_argument("--dry-run", action="store_true", help="build the PDF but do not print, record or notify")
    rn.add_argument("--kid", help="one student only (first name or nickname prefix)")
    rn.add_argument("--date", help="YYYY-MM-DD to build for (testing); bypasses the print window")
    rn.add_argument("--days", type=int, default=None, help="days ahead (default: config.toml, then 14)")
    rn.add_argument("--overdue-days", type=int, default=None, help="how far back an overdue item may be (default: config.toml, then 14)")
    rn.add_argument("--force", action="store_true", help="ignore no-print-days.txt and the print window (never reprints a day)")
    rn.add_argument("--printer", default=os.environ.get("FRIDGESHEET_PRINTER") or None, help="printer name (default: config.toml, then the system default)")
    rn.add_argument("--no-refresh", action="store_true", help="use the snapshot as is")
    rn.add_argument("--reprint", action="store_true", help="print again even if this date already has a printed sheet")
    rn.set_defaults(fn=cmd_run)
    sub.add_parser("reports", help="list report types and their schedules").set_defaults(fn=cmd_reports)
```

The `print-sheet` parser stays exactly as it is (its `--printer` default was changed in Task 3).

- [ ] **Step 9: Run the whole suite**

Run: `python3 -m pytest -q`
Expected: all pass, including every test in `tests/test_print_sheet.py` unchanged.

- [ ] **Step 10: Commit**

```bash
git add fridgesheet/reports fridgesheet/runner.py fridgesheet/print_sheet.py fridgesheet/cli.py tests/test_reports.py tests/test_runner.py
git commit -m "Split print-sheet into a generic runner and an open-work report plugin

Adds \`fridgesheet run <report>\` and \`reports\`; print-sheet is now an alias.
The runner gains a lock file, toasts, a per-report window time, and survives a
windowed process with no stderr.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 8: `host.scheduling` (Task Scheduler on Windows, read-only on Linux) and the `schedule` command

**Files:**
- Create: `fridgesheet/host/scheduling.py`, `scheduling_linux.py`, `scheduling_windows.py`, `task.xml`
- Modify: `fridgesheet/cli.py` (add `schedule`)
- Test: `tests/test_host_scheduling.py`

**Interfaces:**
- Consumes: `config.ReportConfig.time/days`, `reports.get(key).default_time`, `host.NotSupported`, `host.CREATE_NO_WINDOW`
- Produces, on `host.scheduling` and each `scheduling_*`:
  - `ScheduleInfo(managed_by: str, installed: bool, next_run: str | None, last_result: str | None)`
  - `task_name(key: str) -> str` (`"Fridge Sheet - open-work"`)
  - `command_for(key: str) -> tuple[str, str, str]` = (exe, args, workdir): frozen -> (`sys.executable`, `"run <key>"`, exe's folder); source -> (`sys.executable`, `"-m fridgesheet.cli run <key>"`, cwd)
  - `install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run) -> None`
  - `remove(key: str, run=subprocess.run) -> None`
  - `describe(key: str, run=subprocess.run) -> ScheduleInfo`
  - `scheduling_windows.render_task_xml(name, time, days, exe, args, workdir) -> str`
  - `SchedulingError(RuntimeError)` for `schtasks` failures (stderr included)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_host_scheduling.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from fridgesheet.host import NotSupported, scheduling, scheduling_linux, scheduling_windows


class _R:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def test_task_xml_has_the_trigger_settings_and_action():
    xml = scheduling_windows.render_task_xml("Fridge Sheet - open-work", "14:00", ["Mon", "Tue", "Wed", "Thu", "Fri"],
                                             r"C:\Apps\FridgeSheet.exe", "run open-work", r"C:\Apps")
    assert "<StartBoundary>2026-01-01T14:00:00</StartBoundary>" in xml
    assert "<Monday />" in xml and "<Friday />" in xml and "<Saturday />" not in xml
    assert "<StartWhenAvailable>true</StartWhenAvailable>" in xml
    assert "<ExecutionTimeLimit>PT30M</ExecutionTimeLimit>" in xml
    assert "<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>" in xml
    assert "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>" in xml
    assert "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>" in xml
    assert "<WakeToRun>false</WakeToRun>" in xml
    assert "<LogonType>InteractiveToken</LogonType>" in xml and "<RunLevel>LeastPrivilege</RunLevel>" in xml
    assert r"<Command>C:\Apps\FridgeSheet.exe</Command>" in xml and "<Arguments>run open-work</Arguments>" in xml
    assert r"<WorkingDirectory>C:\Apps</WorkingDirectory>" in xml
    assert "<Description>Fridge Sheet: open-work</Description>" in xml


def test_task_xml_escapes_paths_with_ampersands():
    xml = scheduling_windows.render_task_xml("n", "08:05", ["Sat"], r"C:\A & B\x.exe", "run k", r"C:\A & B")
    assert r"<Command>C:\A &amp; B\x.exe</Command>" in xml and "<Saturday />" in xml and "T08:05:00" in xml


def test_windows_install_writes_utf16_xml_and_calls_schtasks():
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        seen["xml"] = Path(cmd[cmd.index("/XML") + 1]).read_bytes()
        return _R(0, "SUCCESS: The scheduled task has been created.")

    scheduling_windows.install("open-work", "14:00", ["Mon"], r"C:\x.exe", "run open-work", r"C:\", run=run)
    assert seen["cmd"][:4] == ["schtasks", "/Create", "/TN", "Fridge Sheet - open-work"] and seen["cmd"][-1] == "/F"
    assert seen["xml"].startswith(b"\xff\xfe") and seen["xml"].decode("utf-16").startswith('<?xml version="1.0" encoding="UTF-16"?>')
    assert seen["kw"]["creationflags"] == scheduling_windows.CREATE_NO_WINDOW
    assert not Path(seen["cmd"][seen["cmd"].index("/XML") + 1]).exists()      # temp file cleaned up


def test_windows_install_failure_surfaces_stderr():
    with pytest.raises(scheduling.SchedulingError, match="Access is denied"):
        scheduling_windows.install("k", "14:00", ["Mon"], "x", "run k", ".", run=lambda c, **k: _R(1, "", "ERROR: Access is denied."))


def test_windows_remove_and_describe():
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        if cmd[1] == "/Delete":
            return _R(0)
        return _R(0, "Folder: \\\nHostName:      PC\nTaskName:      \\Fridge Sheet - open-work\nNext Run Time: 9/15/2026 2:00:00 PM\n"
                     "Status:        Ready\nLast Run Time: 9/14/2026 2:00:03 PM\nLast Result:   0\n")

    scheduling_windows.remove("open-work", run=run)
    assert seen[0] == ["schtasks", "/Delete", "/TN", "Fridge Sheet - open-work", "/F"]
    info = scheduling_windows.describe("open-work", run=run)
    assert seen[1] == ["schtasks", "/Query", "/TN", "Fridge Sheet - open-work", "/FO", "LIST", "/V"]
    assert info == scheduling.ScheduleInfo("task-scheduler", True, "9/15/2026 2:00:00 PM", "0")
    missing = scheduling_windows.describe("open-work", run=lambda c, **k: _R(1, "", "ERROR: The system cannot find the file specified."))
    assert missing == scheduling.ScheduleInfo("task-scheduler", False, None, None)
    scheduling_windows.remove("gone", run=lambda c, **k: _R(1, "", "ERROR: The system cannot find the file specified."))  # not an error


def test_linux_is_read_only_and_reads_systemd():
    with pytest.raises(NotSupported, match="systemd"):
        scheduling_linux.install("open-work", "14:00", ["Mon"], "x", "run open-work", ".")
    with pytest.raises(NotSupported):
        scheduling_linux.remove("open-work")
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return _R(0, "Tue 2026-09-15 14:00:00 EDT\n")

    info = scheduling_linux.describe("open-work", run=run)
    assert seen[0] == ["systemctl", "--user", "show", "fridgesheet-print-sheet.timer", "-p", "NextElapseUSecRealtime", "--value"]
    assert info == scheduling.ScheduleInfo("systemd", True, "Tue 2026-09-15 14:00:00 EDT", None)
    assert scheduling_linux.describe("weekly", run=lambda c, **k: _R(0, "\n")) == scheduling.ScheduleInfo("systemd", False, None, None)


def test_command_for_source_and_frozen(monkeypatch, tmp_path):
    import sys
    monkeypatch.delattr(sys, "frozen", raising=False)
    exe, args, wd = scheduling.command_for("open-work")
    assert exe == sys.executable and args == "-m fridgesheet.cli run open-work" and wd == str(Path.cwd())
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "FridgeSheet.exe"))
    exe, args, wd = scheduling.command_for("open-work")
    assert exe.endswith("FridgeSheet.exe") and args == "run open-work" and wd == str(tmp_path)


def test_schedule_cli_show_and_not_supported(monkeypatch, capsys):
    from fridgesheet import cli
    from fridgesheet.config import Settings
    monkeypatch.setattr(cli, "load_settings", lambda: Settings())
    monkeypatch.setattr(scheduling, "describe", lambda key, run=None: scheduling.ScheduleInfo("systemd", True, "Tue 14:00", None))
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "show"])
    assert e.value.code == 0 and "systemd" in capsys.readouterr().out

    def unsupported(*a, **k):
        raise NotSupported("managed by systemd; see README section 6")
    monkeypatch.setattr(scheduling, "install", unsupported)
    with pytest.raises(SystemExit) as e:
        cli.main(["schedule", "install"])
    assert e.value.code == 2 and "systemd" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest tests/test_host_scheduling.py -q`
Expected: FAIL at import.

- [ ] **Step 3: Write `task.xml`**

```xml
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{description}</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
{days}
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT30M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{exe}</Command>
      <Arguments>{args}</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
```

Save as `fridgesheet/host/task.xml` (UTF-8 on disk; the writer re-encodes to UTF-16 for `schtasks`). `pyproject.toml` already lists `host/*.xml` as package data (Task 3).

- [ ] **Step 4: Write the scheduling modules**

```python
# fridgesheet/host/scheduling.py
"""The scheduled run of a report.

Windows: one Task Scheduler task per report, "Fridge Sheet - <key>", running only while
the user is logged in (InteractiveToken: Credential Manager and the printer need the
session) and catching up a missed start (the runner's window guard then decides).
Linux: scheduling stays with systemd user timers; this adapter only reports on them.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import IS_WINDOWS


class SchedulingError(RuntimeError):
    """schtasks refused; its stderr is in the message."""


@dataclass(frozen=True)
class ScheduleInfo:
    managed_by: str                 # "task-scheduler" | "systemd"
    installed: bool
    next_run: str | None
    last_result: str | None


def task_name(key: str) -> str:
    return f"Fridge Sheet - {key}"


def command_for(key: str) -> tuple[str, str, str]:
    """(exe, args, workdir) that runs the report from this installation."""
    if getattr(sys, "frozen", False):
        return sys.executable, f"run {key}", str(Path(sys.executable).parent)
    return sys.executable, f"-m fridgesheet.cli run {key}", str(Path.cwd())


if IS_WINDOWS:
    from . import scheduling_windows as _impl
else:
    from . import scheduling_linux as _impl

install = _impl.install
remove = _impl.remove
describe = _impl.describe
```

```python
# fridgesheet/host/scheduling_linux.py
from __future__ import annotations

import subprocess

from . import NotSupported

_MSG = "scheduling on Linux is managed by systemd; see README section 6"


def _unit(key: str) -> str:
    return "fridgesheet-print-sheet.timer" if key == "open-work" else f"fridgesheet-{key}.timer"


def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run) -> None:
    raise NotSupported(_MSG)


def remove(key: str, run=subprocess.run) -> None:
    raise NotSupported(_MSG)


def describe(key: str, run=subprocess.run):
    from .scheduling import ScheduleInfo
    try:
        p = run(["systemctl", "--user", "show", _unit(key), "-p", "NextElapseUSecRealtime", "--value"], capture_output=True, text=True, timeout=20)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ScheduleInfo("systemd", False, None, None)
    nxt = (p.stdout or "").strip()
    return ScheduleInfo("systemd", bool(nxt), nxt or None, None)
```

```python
# fridgesheet/host/scheduling_windows.py
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from importlib import resources
from xml.sax.saxutils import escape

from . import CREATE_NO_WINDOW

_DAY_TAGS = {"Mon": "Monday", "Tue": "Tuesday", "Wed": "Wednesday", "Thu": "Thursday", "Fri": "Friday", "Sat": "Saturday", "Sun": "Sunday"}
_NOT_FOUND = "cannot find the file"


def _name(key: str) -> str:
    from .scheduling import task_name
    return task_name(key)


def _err(msg: str):
    from .scheduling import SchedulingError
    return SchedulingError(msg)


def render_task_xml(name: str, time: str, days: list[str], exe: str, args: str, workdir: str) -> str:
    template = resources.files("fridgesheet.host").joinpath("task.xml").read_text(encoding="utf-8")
    day_xml = "\n".join(f"          <{_DAY_TAGS[d]} />" for d in days if d in _DAY_TAGS)
    key = name.split(" - ", 1)[-1]
    return (template.replace("{description}", escape(f"Fridge Sheet: {key}"))
                    .replace("{start}", f"2026-01-01T{time}:00")
                    .replace("{days}", day_xml)
                    .replace("{exe}", escape(exe)).replace("{args}", escape(args)).replace("{workdir}", escape(workdir)))


def _schtasks(cmd: list[str], run) -> subprocess.CompletedProcess:
    return run(["schtasks", *cmd], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=60)


def install(key: str, time: str, days: list[str], exe: str, args: str, workdir: str, run=subprocess.run) -> None:
    xml = render_task_xml(_name(key), time, days, exe, args, workdir)
    fd, path = tempfile.mkstemp(prefix="fridgesheet-task-", suffix=".xml")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(xml.encode("utf-16"))          # BOM + UTF-16LE, what schtasks /XML expects
        p = _schtasks(["/Create", "/TN", _name(key), "/XML", path, "/F"], run)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if p.returncode != 0:
        raise _err(f"schtasks /Create failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def remove(key: str, run=subprocess.run) -> None:
    p = _schtasks(["/Delete", "/TN", _name(key), "/F"], run)
    if p.returncode != 0 and _NOT_FOUND not in (p.stderr or ""):
        raise _err(f"schtasks /Delete failed: {(p.stderr or p.stdout or '').strip()[:300]}")


def describe(key: str, run=subprocess.run):
    from .scheduling import ScheduleInfo
    p = _schtasks(["/Query", "/TN", _name(key), "/FO", "LIST", "/V"], run)
    if p.returncode != 0:
        return ScheduleInfo("task-scheduler", False, None, None)
    fields = {}
    for line in (p.stdout or "").splitlines():
        m = re.match(r"^([A-Za-z ]+):\s*(.*?)\s*$", line)
        if m:
            fields.setdefault(m.group(1).strip(), m.group(2))
    return ScheduleInfo("task-scheduler", True, fields.get("Next Run Time") or None, fields.get("Last Result") or None)
```

The `StartBoundary` date is fixed at 2026-01-01: Task Scheduler only needs it to be in the past for a weekly trigger; the time part is what matters.

- [ ] **Step 5: Add the `schedule` command**

In `cli.py`:

```python
def cmd_schedule(args) -> int:
    from . import reports
    from .host import NotSupported, scheduling
    s = load_settings()
    key = args.report
    try:
        if args.action == "install":
            r = reports.get(key)
            rc = s.report_config(key, r.default_time)
            exe, a, wd = scheduling.command_for(key)
            scheduling.install(key, rc.time, rc.days, exe, a, wd)
            print(f"Installed {scheduling.task_name(key)}: {','.join(rc.days)} at {rc.time}")
        elif args.action == "remove":
            scheduling.remove(key)
            print(f"Removed {scheduling.task_name(key)}")
        info = scheduling.describe(key)
        state = f"next run {info.next_run}" if info.installed else "not scheduled"
        print(f"{key}: {state} (managed by {info.managed_by}" + (f", last result {info.last_result}" if info.last_result else "") + ")")
        return 0
    except NotSupported as e:
        print(str(e), file=sys.stderr)
        return 2
    except scheduling.SchedulingError as e:
        print(str(e), file=sys.stderr)
        return 1
```

and in `main()` after `reports`:

```python
    sc2 = sub.add_parser("schedule", help="install, remove or show the scheduled run (Windows Task Scheduler; read-only on Linux)")
    sc2.add_argument("action", choices=["install", "remove", "show"])
    sc2.add_argument("report", nargs="?", default="open-work")
    sc2.set_defaults(fn=cmd_schedule)
```

- [ ] **Step 6: Run the whole suite, commit**

Run: `python3 -m pytest -q` — all pass.

```bash
git add fridgesheet/host fridgesheet/cli.py tests/test_host_scheduling.py
git commit -m "Add host.scheduling: Task Scheduler XML + schtasks on Windows, systemd read-only on Linux

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: CI on Linux and Windows

**Files:**
- Create: `.github/workflows/ci.yml`, `tests/conftest.py`
- Modify: `tests/test_sheet.py`, `tests/test_print_sheet.py`, `tests/test_reports.py` (mark the tests that need `pdftotext`)
- Modify: `.github/workflows/spike-pyinstaller.yml` (manual trigger only)

**Interfaces:**
- Produces: `tests/conftest.py::needs_pdftotext` marker.

- [ ] **Step 1: Add the marker and apply it**

```python
# tests/conftest.py
"""Shared markers. pdftotext (poppler-utils) is how tests read a built PDF back; it is
installed on the Linux CI leg and usually absent on Windows, where those tests skip."""
from __future__ import annotations

import shutil

import pytest

needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext (poppler-utils) not installed")
```

Decorate with `@needs_pdftotext` (importing it with `from tests.conftest import needs_pdftotext`):
- `tests/test_sheet.py`: both tests.
- `tests/test_print_sheet.py`: `test_failed_refresh_with_fresh_snapshot_prints_with_a_footer_note`, `test_second_run_diffs_against_the_previous_sheet`.
- `tests/test_reports.py`: `test_open_work_honours_kid_filter_options_and_previous_rows`.

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: ci
on:
  push:
  pull_request:
jobs:
  test:
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, windows-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - if: runner.os == 'Linux'
        run: sudo apt-get update && sudo apt-get install -y poppler-utils
      - if: runner.os == 'Linux'
        run: pip install -e ".[dev]"
      - if: runner.os == 'Windows'
        run: pip install -e ".[dev,windows]"
      - run: python -m pytest -q 2>&1 | tee pytest.log
        shell: bash
      - uses: actions/upload-artifact@v4
        if: failure()
        with: { name: "pytest-${{ matrix.os }}", path: pytest.log }
```

In `.github/workflows/spike-pyinstaller.yml` delete the `push:` block under `on:` so only `workflow_dispatch` remains.

- [ ] **Step 3: Run locally, push, watch both legs**

```bash
python3 -m pytest -q
git add .github tests
git commit -m "CI: pytest on ubuntu and windows; skip pdftotext-dependent tests where poppler is absent

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
gh run watch "$(gh run list --workflow ci.yml --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status 2>&1 | tee /tmp/ci-first-run.log
```

Expected: both legs green. If the Windows leg fails on a path or encoding assumption, fix it in the module (not the test) as its own commit; that is the point of the leg.

---

### Task 10: README, examples, and spec touch-ups

**Files:**
- Modify: `README.md`, `docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md`

- [ ] **Step 1: README**

1. Under "## 6. The printed sheet", after the file table, add:

```markdown
### Settings file

Most settings can live in `~/.fridgesheet/config.toml` instead of `.env`; the environment still wins when both set the same thing. `fridgesheet set-credentials` records the username there (the password goes in the OS credential store).

```toml
[account]
username = "parent@example.com"

[print]
printer = ""                          # blank = system default (fridgesheet printers)
archive = ""                          # optional folder for a second copy of every PDF

[kids]
nicknames = { Alex = "Al" }      # snapshot first name -> name printed on the sheet

[reports.open-work]
enabled = true
time = "14:00"
days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
days_ahead = 14
overdue_days = 14
```

`fridgesheet run open-work` is the general form of `print-sheet` (same flags); `fridgesheet reports` lists report types and their schedules; `fridgesheet schedule show` prints the next run. On Windows `schedule install` writes the Task Scheduler task; on Linux the systemd units above stay in charge.

**Upgrading from 0.1:** the built-in `Alex=Al` nickname is gone. Add `FRIDGESHEET_NICKNAMES=Alex=Al` to `.env` or the `[kids]` table above, or the sheet prints the full first name.
```

2. In section 2, change "GNOME keyring" in the first sentence to "OS credential store (GNOME keyring on Linux, Credential Manager on Windows)".
3. Under "## 1. Install (Linux)" add one line: `Python 3.11 or newer.`
4. Add to the "Tests" section: `CI runs the suite on Ubuntu and Windows.`

- [ ] **Step 2: Spec touch-ups (two lines)**

In the spec, section 4, replace `ctx.settings.report_options(key)` with `ctx.options` (the runner merges config and CLI). In section 3's tree and section 7, `packaging/windows/task.xml` becomes `fridgesheet/host/task.xml` (package data, so the frozen app can read it).

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md
git commit -m "Document config.toml, the run/reports/schedule commands, and the nickname migration

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Done when

- `python3 -m pytest -q` is green locally and `ci.yml` is green on both runners.
- `fridgesheet print-sheet --dry-run --force` on Tony's box builds today's sheet exactly as before (compare page count and the log line format).
- `fridgesheet printers`, `reports`, `schedule show` each print something sensible on Linux.
- Task 1's Step 5 records the spike outcome for Plan 3.

Plan 2 (app) and Plan 3 (packaging and release) are written next, against the interfaces above.

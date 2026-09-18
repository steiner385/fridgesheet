# Windows Sheet App, Plan 3 of 3: Bundle, Installer, Release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the code from Plans 1 and 2 into `FridgeSheet-Setup-<version>.exe`, built by GitHub Actions from a version tag, that another Lakota parent installs per-user on Windows, plus the page that tells him how.

**Architecture:** A PyInstaller one-folder bundle of `fridgesheet/app/__main__.py` (windowed) with Chromium and SumatraPDF copied in beside it, wrapped by an Inno Setup per-user installer whose uninstaller removes the scheduled task. A `build.ps1` does every step and runs a smoke test on the built exe (a `doctor` self-check, a dry-run sheet from a fixture snapshot, and a no-arguments launch), so the release job fails before it publishes a broken bundle. A new `fridgesheet doctor` command doubles as the friend's first troubleshooting step.

**Tech Stack:** PyInstaller 6 (one-folder, `console=False`), Playwright Chromium, SumatraPDF 3.5.2 portable (GPL-3.0, pinned by SHA-256), Inno Setup 6 (preinstalled on `windows-latest`), GitHub Actions (`softprops/action-gh-release@v2`), PowerShell 7.

**Spec:** `docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md`, sections 9 (build and distribution), 12 (the one test on the built artefact), 13 (limitations told to the friend), plus the Plan 2 carry-overs recorded in its ledger: a close-window prompt while a job runs, terminal-only commands under a windowed exe, and a no-arguments launch check of the built exe.

## Global Constraints

- The Windows executable is `FridgeSheet.exe`, windowed (`console=False`), built from `fridgesheet/app/__main__.py`; no arguments opens the window, anything else is the CLI (Plan 2 built this; Plan 3 only packages it).
- Chromium lives in `<install dir>\ms-playwright\`; `frozen_environment()` already points `PLAYWRIGHT_BROWSERS_PATH` there. SumatraPDF lives at `<install dir>\SumatraPDF.exe` next to `SumatraPDF-LICENSE.txt`; `host.printing_windows.sumatra_path()` already looks there.
- The installer is per-user: `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\Fridge Sheet`, Start menu shortcut with `AppUserModelID` `Cairnea.FridgeSheet` (must equal `host.notify_windows.APP_ID`), optional desktop shortcut, "Launch Fridge Sheet" on finish, `[UninstallRun]` `FridgeSheet.exe schedule remove`, data under `%LOCALAPPDATA%\fridgesheet` kept on uninstall and the uninstaller says so.
- Version has one source, `pyproject.toml`; `build.ps1` reads it and passes it to Inno Setup; on a tag build the tag must equal `v<version>` or the job fails.
- SumatraPDF is pinned: version 3.5.2, `https://www.sumatrapdfreader.org/dl/rel/3.5.2/SumatraPDF-3.5.2-64.zip`, SHA-256 `66ccb395c9184dce6822dfbb9970c877383b3ead6d9417b5106a844aac512989`, containing `SumatraPDF-3.5.2-64.exe`; licence `https://raw.githubusercontent.com/sumatrapdfreader/sumatrapdf/master/COPYING`, SHA-256 `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`. A checksum mismatch fails the build.
- No credential is ever written by any smoke step; the smoke test uses `FRIDGESHEET_HOME` pointed at a temp folder and `--no-refresh`.
- Nothing in this plan tags a release. Task 4 runs the release workflow by `workflow_dispatch` (artifact only). Creating the `v0.2.0` tag is the user's action, documented in the README.
- Suite command on this box: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q` (167 passed, 1 skipped at the start of this plan). Windows-only artefacts (`.spec`, `.ps1`, `.iss`) are verified by the workflow run in Task 4, not locally.
- Commit after every task with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Pushing this branch is approved; tagging is not.

## File map

| Path | Responsibility |
|---|---|
| `fridgesheet/doctor.py` (new) | `checks(settings, home)` and `run(settings, home)`: the self-check behind `fridgesheet doctor`, the window's Help menu, and the build smoke test |
| `fridgesheet/cli.py` (modify) | `doctor` command |
| `fridgesheet/app/actions.py` (modify) | `run_doctor(home, log, settings=None, run=None)` |
| `fridgesheet/app/__main__.py` (modify) | refuse `login`/`set-credentials` when there is no stdin; GUI import inside the crash guard |
| `fridgesheet/app/gui.py` (modify) | close-window prompt while a job runs; Help → Run diagnostics |
| `packaging/windows/sumatra.json` (new) | the pin above |
| `packaging/windows/fixture-snapshot.json` (new) | one-student, no-assignments snapshot for the smoke dry run |
| `packaging/windows/FridgeSheet.spec` (new) | PyInstaller spec |
| `packaging/windows/build.ps1` (new) | the whole build; calls `smoke.ps1` |
| `packaging/windows/smoke.ps1` (new) | doctor + dry run + no-args launch against `dist\FridgeSheet\FridgeSheet.exe` |
| `packaging/windows/installer.iss` (new) | Inno Setup script |
| `.github/workflows/release.yml` (new) | tag `v*` or manual dispatch → build → artifact → release on tags |
| `.github/workflows/spike-pyinstaller.yml`, `packaging/windows/spike_entry.py` (delete) | superseded |
| `docs/windows.md` (new) | the friend's page |
| `README.md` (modify) | "Releasing" section and a pointer to `docs/windows.md` |
| `tests/test_doctor.py`, `tests/test_packaging.py` (new); `tests/test_app_main.py`, `tests/test_app_actions.py` (modify) | |

---

### Task 1: `doctor`, and the frozen-exe hardening carried over from Plan 2

**Files:**
- Create: `fridgesheet/doctor.py`
- Modify: `fridgesheet/cli.py` (add `doctor`), `fridgesheet/app/actions.py` (add `run_doctor`), `fridgesheet/app/__main__.py` (stdin guard; import inside try), `fridgesheet/app/gui.py` (close prompt; Help menu item)
- Test: `tests/test_doctor.py`, `tests/test_app_main.py` (append), `tests/test_app_actions.py` (append)

**Interfaces:**
- Produces:
  - `doctor.Check(name: str, ok: bool, detail: str)` (frozen dataclass)
  - `doctor.checks(settings, home: Path, *, probes=None) -> list[Check]` — runs each probe in `PROBES` (or the injected list) inside `try/except`, so a raising probe becomes `Check(name, False, "<ExcType>: <msg>")`.
  - `doctor.PROBES: list[tuple[str, Callable[[Settings, Path], str]]]` — `("python", ...)`, `("home", ...)`, `("timezone", ...)`, `("pdf", ...)`, `("chromium", ...)`, `("credential store", ...)`, `("printers", ...)`, `("print engine", ...)`, `("scheduler", ...)`; each returns a one-line detail or raises.
  - `doctor.format_report(checks) -> str` — one line per check: `"OK    name: detail"` / `"FAIL  name: detail"`, then `"All checks passed"` or `"<n> check(s) failed"`.
  - `doctor.run(settings, home, *, probes=None) -> tuple[str, bool]` — writes the report to `<home>/doctor.txt` and returns `(report, all_ok)`.
  - `cli doctor` → prints the report, exit 0 when all OK else 1.
  - `actions.run_doctor(*, home, log, settings=None, run=None) -> bool` — streams each report line to `log`, returns `all_ok`.
  - `app.__main__.TERMINAL_ONLY = ("login", "set-credentials")`; `main([...])` returns 2 and logs `"<cmd> needs a terminal; use the Fridge Sheet window instead"` when `sys.stdin is None` and `argv[0]` is in that tuple.

- [ ] **Step 1: Write the failing doctor tests**

```python
# tests/test_doctor.py
"""The self-check: every probe is isolated, a raising probe is a FAIL line, the report is
written to <home>/doctor.txt, and the CLI exit code follows the verdict."""
from __future__ import annotations

from pathlib import Path

import pytest

from fridgesheet import cli, doctor
from fridgesheet.config import Settings


def _probes():
    return [
        ("python", lambda s, h: "3.12"),
        ("boom", lambda s, h: (_ for _ in ()).throw(RuntimeError("no such thing"))),
        ("printers", lambda s, h: "2 printers, default Office"),
    ]


def test_checks_isolate_each_probe(tmp_path):
    out = doctor.checks(Settings(home=tmp_path), tmp_path, probes=_probes())
    assert [(c.name, c.ok) for c in out] == [("python", True), ("boom", False), ("printers", True)]
    assert out[1].detail == "RuntimeError: no such thing"


def test_format_report_and_run_write_doctor_txt(tmp_path):
    report, ok = doctor.run(Settings(home=tmp_path), tmp_path, probes=_probes())
    assert not ok
    assert report.splitlines()[0] == "OK    python: 3.12"
    assert "FAIL  boom: RuntimeError: no such thing" in report
    assert report.splitlines()[-1] == "1 check(s) failed"
    assert (tmp_path / "doctor.txt").read_text(encoding="utf-8") == report
    report2, ok2 = doctor.run(Settings(home=tmp_path), tmp_path, probes=_probes()[:1])
    assert ok2 and report2.splitlines()[-1] == "All checks passed"


def test_real_probes_run_on_this_machine(tmp_path):
    """The default probe list must not crash; individual probes may FAIL here (no printer,
    no keyring) but each must produce a Check."""
    out = doctor.checks(Settings(home=tmp_path), tmp_path)
    names = [c.name for c in out]
    assert names == ["python", "home", "timezone", "pdf", "chromium", "credential store", "printers", "print engine", "scheduler"]
    assert all(isinstance(c.detail, str) and c.detail for c in out)
    by = {c.name: c for c in out}
    assert by["python"].ok and by["home"].ok and by["timezone"].ok and by["pdf"].ok


def test_cli_doctor_exit_code_follows_verdict(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "load_settings", lambda: Settings(home=tmp_path))
    monkeypatch.setattr(doctor, "PROBES", _probes())
    with pytest.raises(SystemExit) as e:
        cli.main(["doctor"])
    assert e.value.code == 1 and "FAIL  boom" in capsys.readouterr().out
    monkeypatch.setattr(doctor, "PROBES", _probes()[:1])
    with pytest.raises(SystemExit) as e:
        cli.main(["doctor"])
    assert e.value.code == 0
```

Append to `tests/test_app_actions.py`:

```python
def test_run_doctor_streams_lines_and_returns_verdict(tmp_path):
    lines = []
    fake = lambda settings, home, probes=None: ("OK    python: 3.12\nFAIL  boom: x\n1 check(s) failed", False)  # noqa: E731
    assert actions.run_doctor(home=tmp_path, log=lines.append, settings=Settings(home=tmp_path), run=fake) is False
    assert lines == ["OK    python: 3.12", "FAIL  boom: x", "1 check(s) failed"]
```

Append to `tests/test_app_main.py`:

```python
@pytest.mark.parametrize("cmd", ["login", "set-credentials"])
def test_terminal_only_commands_are_refused_without_stdin(monkeypatch, tmp_path, cmd):
    monkeypatch.setattr(appmain, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(sys, "stdin", None)
    called = []
    monkeypatch.setattr(cli, "main", lambda argv: called.append(argv))
    assert appmain.main([cmd]) == 2 and called == []
    for h in logging.getLogger().handlers:
        h.flush()
    assert "needs a terminal" in (tmp_path / actions.APP_LOG).read_text(encoding="utf-8")


def test_gui_import_failure_is_logged_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(appmain, "DEFAULT_HOME", tmp_path)
    monkeypatch.setitem(sys.modules, "fridgesheet.app.gui", None)      # import raises ImportError
    assert appmain.main([]) == 1
    for h in logging.getLogger().handlers:
        h.flush()
    assert "the window could not start" in (tmp_path / actions.APP_LOG).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_doctor.py tests/test_app_actions.py tests/test_app_main.py -q`
Expected: `test_doctor.py` fails at import; the three appended tests fail with `AttributeError`/assertion errors.

- [ ] **Step 3: Write `doctor.py`**

```python
# fridgesheet/doctor.py
"""`fridgesheet doctor`: nine quick probes that tell a user (or the build's smoke test)
whether this installation can do its job. Every probe is isolated; a probe that raises
becomes a FAIL line rather than a crash. Nothing here reads or prints a credential."""
from __future__ import annotations

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
REPORT_KEY = "open-work"


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


def _timezone(s: Settings, home: Path) -> str:
    ZoneInfo(s.timezone)
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
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        exe = Path(p.chromium.executable_path)
    if not exe.is_file():
        raise FileNotFoundError(f"Chromium not found at {exe}")
    return str(exe)


def _credential_store(s: Settings, home: Path) -> str:
    if host.IS_WINDOWS:
        import keyring
        return f"keyring backend {type(keyring.get_keyring()).__name__}"
    tool = shutil.which("secret-tool")
    if not tool:
        raise FileNotFoundError("secret-tool (libsecret) is not installed")
    return tool


def _printers(s: Settings, home: Path) -> str:
    from .host import printing
    names = printing.list_printers()
    return f"{len(names)} printer(s), default {printing.default_printer() or 'none'}, configured {s.printer or 'system default'}"


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
    from .host import scheduling
    info = scheduling.describe(REPORT_KEY)
    state = f"next run {info.next_run}" if info.installed else "not scheduled"
    return f"{info.managed_by}: {state}"


PROBES: list[tuple[str, Callable[[Settings, Path], str]]] = [
    ("python", _python), ("home", _home), ("timezone", _timezone), ("pdf", _pdf), ("chromium", _chromium),
    ("credential store", _credential_store), ("printers", _printers), ("print engine", _print_engine), ("scheduler", _scheduler),
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
    """Run the probes, write <home>/doctor.txt (the windowed exe has no stdout), return (report, all_ok)."""
    results = checks(settings, home, probes=probes)
    report = format_report(results)
    home.mkdir(parents=True, exist_ok=True)
    (home / REPORT_NAME).write_text(report, encoding="utf-8")
    return report, all(c.ok for c in results)
```

- [ ] **Step 4: Wire the CLI, the action, the entry-point guard, and the window**

`cli.py`:

```python
def cmd_doctor(args) -> int:
    from . import doctor
    s = load_settings()
    report, ok = doctor.run(s, s.home)
    print(report)
    return 0 if ok else 1
```

and in `main()` after the `app` parser: `sub.add_parser("doctor", help="check Python, Chromium, the PDF engine, the credential store, printers and the scheduler; writes <home>/doctor.txt").set_defaults(fn=cmd_doctor)`. Add `doctor` to the module docstring's command list.

`app/actions.py` (append):

```python
def run_doctor(*, home: Path, log: Callable[[str], None], settings: config.Settings | None = None, run=None) -> bool:
    """Help → Run diagnostics: stream the doctor report into the log pane."""
    from .. import doctor
    settings = settings or config.load_settings()
    run = run or doctor.run
    report, ok = run(settings, home)
    for line in report.splitlines():
        log(line)
    return ok
```

`app/__main__.py`: add `TERMINAL_ONLY = ("login", "set-credentials")` at module level and change `main`:

```python
def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    frozen_environment()
    setup_logging(DEFAULT_HOME)
    log = logging.getLogger("fridgesheet.app")
    if not argv:
        try:
            from fridgesheet.app.gui import run_app
            return run_app()
        except Exception:
            log.exception("the window could not start")
            return 1
    if argv[0] in TERMINAL_ONLY and sys.stdin is None:
        log.error("%s needs a terminal; use the Fridge Sheet window instead", argv[0])
        return 2
    from fridgesheet import cli
    try:
        cli.main(argv)
    except SystemExit as e:
        code = e.code
        if code is None:
            return 0
        if isinstance(code, int):
            return code
        if sys.stderr is not None:
            print(code, file=sys.stderr)
        return 1
    return 0
```

`app/gui.py`: in `App.__init__` after building the tabs add `root.protocol("WM_DELETE_WINDOW", self._on_close)`; in `_build_menu` add `helpm.add_command(label="Run diagnostics", command=lambda: self._start("Diagnostics", self._do_doctor))` before the About entry; add:

```python
    def _do_doctor(self):
        return ("doctor", actions.run_doctor(home=self.home, log=self._log))

    def _on_close(self) -> None:
        if self._busy and not messagebox.askyesno("Fridge Sheet", "A job is still running. Close anyway?"):
            return
        self.root.destroy()
```

and in `_finish` add a branch: `elif kind == "doctor" and not value: messagebox.showwarning("Diagnostics", "Some checks failed; see the log above and doctor.txt.")`.

- [ ] **Step 5: Run the suite, commit**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q` — expect 175 passed, 1 skipped (the `chromium` probe launches Playwright's driver once; it is fine if that probe reports FAIL locally, the test only requires a `Check`). Also `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m py_compile fridgesheet/app/gui.py`.

```bash
git add fridgesheet/doctor.py fridgesheet/cli.py fridgesheet/app tests/test_doctor.py tests/test_app_actions.py tests/test_app_main.py
git commit -m "doctor self-check; refuse terminal-only commands without stdin; close-window prompt; Help → Run diagnostics

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 2: The bundle: pin, fixture, PyInstaller spec, `build.ps1`, `smoke.ps1`

Nothing in this task can be executed on the Linux dev box. The tests check that the packaging files say what the spec says; Task 4 runs them for real on a Windows runner.

**Files:**
- Create: `packaging/windows/sumatra.json`, `packaging/windows/fixture-snapshot.json`, `packaging/windows/FridgeSheet.spec`, `packaging/windows/build.ps1`, `packaging/windows/smoke.ps1`
- Delete: `packaging/windows/spike_entry.py`, `.github/workflows/spike-pyinstaller.yml`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: `fridgesheet/app/__main__.py` (entry script), `fridgesheet/host/task.xml` (package data), `fridgesheet doctor` (Task 1), `run open-work --dry-run --no-refresh --force`, `FRIDGESHEET_HOME`.
- Produces: `dist\FridgeSheet\` containing `FridgeSheet.exe`, `_internal\`, `ms-playwright\`, `SumatraPDF.exe`, `SumatraPDF-LICENSE.txt`; `build.ps1 [-SkipSmoke] [-SkipInstaller]` and `smoke.ps1` (both runnable by hand from any cwd); `$env:FRIDGESHEET_APP_VERSION` is not used, the version is read from `pyproject.toml`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_packaging.py
"""The Windows packaging files cannot run here; these tests pin what they must say so a
drift from the spec (a renamed exe, a dropped uninstall step, an unpinned download) fails
on Linux before it costs a Windows build."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIN = ROOT / "packaging" / "windows"


def test_sumatra_pin_is_complete_and_hashes_look_like_sha256():
    pin = json.loads((WIN / "sumatra.json").read_text(encoding="utf-8"))
    assert pin["version"] == "3.5.2"
    assert pin["url"].startswith("https://www.sumatrapdfreader.org/dl/rel/3.5.2/") and pin["url"].endswith(".zip")
    assert pin["exe_in_zip"] == "SumatraPDF-3.5.2-64.exe"
    assert pin["license_url"].startswith("https://raw.githubusercontent.com/sumatrapdfreader/sumatrapdf/")
    assert re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) and re.fullmatch(r"[0-9a-f]{64}", pin["license_sha256"])


def test_fixture_snapshot_loads_and_has_one_student_with_nothing_open():
    snap = json.loads((WIN / "fixture-snapshot.json").read_text(encoding="utf-8"))
    assert snap["sources"] == {"canvas": "ok", "hac": "ok"} and snap["stale"] == {}
    (name, entry), = snap["students"].items()
    assert entry["canvas"]["courses"] == [] and entry["hac"]["classes"] == []
    assert isinstance(snap["fetched_at_epoch"], (int, float))


def test_pyinstaller_spec_names_the_entry_point_and_the_package_data():
    spec = (WIN / "FridgeSheet.spec").read_text(encoding="utf-8")
    assert 'name="FridgeSheet"' in spec and "console=False" in spec
    assert "fridgesheet/app/__main__.py" in spec.replace("\\", "/")
    assert "task.xml" in spec and "tzdata" in spec and 'copy_metadata("fridgesheet")' in spec and 'copy_metadata("keyring")' in spec
    assert "keyring.backends.Windows" in spec


def test_build_script_does_every_spec_step_in_order():
    ps = (WIN / "build.ps1").read_text(encoding="utf-8")
    order = ["pyproject.toml", "[windows]", "playwright install chromium", "sumatra.json", "Get-FileHash", "FridgeSheet.spec",
             "dist\\FridgeSheet\\ms-playwright", "SumatraPDF.exe", "SumatraPDF-LICENSE.txt", "smoke.ps1", "ISCC.exe", "installer.iss"]
    positions = [ps.index(k) for k in order]
    assert positions == sorted(positions), "build.ps1 steps are out of the spec's order"
    assert "$ErrorActionPreference" in ps and '"Stop"' in ps


def test_smoke_script_runs_doctor_dry_run_and_a_no_args_launch():
    ps = (WIN / "smoke.ps1").read_text(encoding="utf-8")
    assert "FRIDGESHEET_HOME" in ps and "fixture-snapshot.json" in ps
    assert '"doctor"' in ps and "doctor.txt" in ps
    assert '"run"' in ps and '"--dry-run"' in ps and '"--no-refresh"' in ps and "sheet.pdf" in ps
    assert "HasExited" in ps and "app.log" in ps
    assert "$home" not in ps.replace("$smokeHome", ""), "never shadow PowerShell's automatic $HOME"


def test_spike_files_are_gone():
    assert not (WIN / "spike_entry.py").exists()
    assert not (ROOT / ".github" / "workflows" / "spike-pyinstaller.yml").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_packaging.py -q`
Expected: five FAIL with `FileNotFoundError`, one FAIL (`test_spike_files_are_gone`) on the assertion.

- [ ] **Step 3: Write the pin and the fixture**

```json
{
  "version": "3.5.2",
  "url": "https://www.sumatrapdfreader.org/dl/rel/3.5.2/SumatraPDF-3.5.2-64.zip",
  "sha256": "66ccb395c9184dce6822dfbb9970c877383b3ead6d9417b5106a844aac512989",
  "exe_in_zip": "SumatraPDF-3.5.2-64.exe",
  "license_url": "https://raw.githubusercontent.com/sumatrapdfreader/sumatrapdf/master/COPYING",
  "license_sha256": "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
}
```
(`packaging/windows/sumatra.json`; the hashes were computed from the downloaded files on 2026-09-14.)

```json
{
  "fetched_at": "2026-09-14T12:00:00+00:00",
  "fetched_at_epoch": 1789387200,
  "sources": {"canvas": "ok", "hac": "ok"},
  "stale": {},
  "students": {
    "Sample": {"name": "Sample Student", "canvas_id": 1, "canvas": {"courses": []}, "hac": {"classes": []}}
  }
}
```
(`packaging/windows/fixture-snapshot.json`; the dry run prints "Nothing open. Nice work." for one kid, which is all the smoke test needs.)

- [ ] **Step 4: Write the PyInstaller spec**

```python
# packaging/windows/FridgeSheet.spec
# -*- mode: python ; coding: utf-8 -*-
"""One-folder, windowed bundle of fridgesheet/app/__main__.py.

Run from the repo root: pyinstaller --noconfirm --clean packaging/windows/FridgeSheet.spec
Chromium (ms-playwright/) and SumatraPDF.exe are copied in afterwards by build.ps1; the
code finds them next to the exe (frozen_environment, sumatra_path).
"""
import os
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

datas = [(os.path.join(ROOT, "fridgesheet", "host", "task.xml"), os.path.join("fridgesheet", "host"))]
datas += collect_data_files("tzdata")                 # Windows has no system zoneinfo
datas += copy_metadata("fridgesheet")          # importlib.metadata.version() for the About box
datas += copy_metadata("keyring")                    # keyring discovers backends through entry points

hiddenimports = [
    "keyring.backends.Windows",
    "win32ctypes.core", "win32ctypes.pywin32",       # keyring's Windows backend
    "win32timezone",                                 # pywin32 needs it at runtime
]

a = Analysis(
    [os.path.join(ROOT, "fridgesheet", "app", "__main__.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["mcp"],                                # the MCP server is not part of the Windows product
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FridgeSheet",
    debug=False,
    strip=False,
    upx=False,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="FridgeSheet")
```

- [ ] **Step 5: Write `build.ps1`**

```powershell
# packaging/windows/build.ps1
# Builds dist\FridgeSheet\ and dist\FridgeSheet-Setup-<version>.exe. Runnable by hand on
# any Windows box with Python 3.12 and Inno Setup 6; this is exactly what release.yml runs.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$SkipSmoke,        # skip smoke.ps1 (faster local iteration)
    [switch]$SkipInstaller     # stop after dist\FridgeSheet\ (no Inno Setup needed)
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot "..\.."))

$version = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
if (-not $version) { throw "could not read version from pyproject.toml" }
Write-Host "== Fridge Sheet $version"

Write-Host "== Python packages"
python -m pip install --upgrade pip
python -m pip install ".[windows]" "pyinstaller>=6.6"

Write-Host "== Chromium"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $PWD "build\ms-playwright"
python -m playwright install chromium

Write-Host "== SumatraPDF (pinned)"
$pin = Get-Content packaging\windows\sumatra.json | ConvertFrom-Json
New-Item -ItemType Directory -Force build\sumatra | Out-Null
Invoke-WebRequest -Uri $pin.url -OutFile build\sumatra\sumatra.zip
$hash = (Get-FileHash build\sumatra\sumatra.zip -Algorithm SHA256).Hash.ToLower()
if ($hash -ne $pin.sha256) { throw "SumatraPDF checksum mismatch: got $hash, pinned $($pin.sha256)" }
Expand-Archive -Force build\sumatra\sumatra.zip build\sumatra
Invoke-WebRequest -Uri $pin.license_url -OutFile build\sumatra\COPYING
$lhash = (Get-FileHash build\sumatra\COPYING -Algorithm SHA256).Hash.ToLower()
if ($lhash -ne $pin.license_sha256) { throw "SumatraPDF licence checksum mismatch: got $lhash" }

Write-Host "== PyInstaller"
Remove-Item -Recurse -Force dist\FridgeSheet -ErrorAction SilentlyContinue
pyinstaller --noconfirm --clean packaging\windows\FridgeSheet.spec
Copy-Item -Recurse build\ms-playwright dist\FridgeSheet\ms-playwright
Copy-Item (Join-Path build\sumatra $pin.exe_in_zip) dist\FridgeSheet\SumatraPDF.exe
Copy-Item build\sumatra\COPYING dist\FridgeSheet\SumatraPDF-LICENSE.txt
Remove-Item Env:\PLAYWRIGHT_BROWSERS_PATH -ErrorAction SilentlyContinue   # the exe must find Chromium by itself

if (-not $SkipSmoke) {
    Write-Host "== Smoke test"
    & (Join-Path $PSScriptRoot "smoke.ps1")
}

if ($SkipInstaller) { Write-Host "== done (no installer)"; exit 0 }

Write-Host "== Inno Setup"
$iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found at $iscc" }
& $iscc "/DAppVersion=$version" "/DSourceDir=$PWD\dist\FridgeSheet" "/O$PWD\dist" packaging\windows\installer.iss
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
Get-ChildItem dist\FridgeSheet-Setup-*.exe | ForEach-Object { Write-Host "== built $($_.FullName) ($([math]::Round($_.Length / 1MB)) MB)" }
```

- [ ] **Step 6: Write `smoke.ps1`**

```powershell
# packaging/windows/smoke.ps1
# Three checks on the built exe, all against a throwaway FRIDGESHEET_HOME so nothing
# touches the builder's real settings and no credential is involved:
#   1. doctor           every probe must pass inside the bundle (Chromium, SumatraPDF, keyring, tzdata...)
#   2. dry-run sheet    run open-work --dry-run --no-refresh --force from a fixture snapshot -> a PDF exists
#   3. no-args launch   the window stays up for 8 s and app.log is written (a crash here is the
#                       one failure the friend would otherwise be first to see)
$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$exe = Join-Path $root "dist\FridgeSheet\FridgeSheet.exe"
if (-not (Test-Path $exe)) { throw "no built exe at $exe" }
$smokeHome = Join-Path $env:TEMP ("fridgesheet-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force (Join-Path $smokeHome "cache") | Out-Null
Copy-Item (Join-Path $root "packaging\windows\fixture-snapshot.json") (Join-Path $smokeHome "cache\snapshot.json")
$env:FRIDGESHEET_HOME = $smokeHome
Write-Host "smoke home: $smokeHome"

# 1. doctor (a windowed exe has no stdout; the report is in doctor.txt)
$p = Start-Process -FilePath $exe -ArgumentList "doctor" -Wait -PassThru -WindowStyle Hidden
Get-Content (Join-Path $smokeHome "doctor.txt") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
if ($p.ExitCode -ne 0) { throw "doctor reported failures (exit $($p.ExitCode))" }

# 2. dry-run sheet from the fixture
$p = Start-Process -FilePath $exe -ArgumentList "run","open-work","--dry-run","--no-refresh","--force" -Wait -PassThru -WindowStyle Hidden
Get-Content (Join-Path $smokeHome "print-sheet.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
if ($p.ExitCode -ne 0) { throw "dry run failed (exit $($p.ExitCode))" }
$pdf = Get-ChildItem (Join-Path $smokeHome "sheets\*\sheet.pdf") -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pdf) { throw "no sheet.pdf under $smokeHome\sheets" }
Write-Host "  built $($pdf.FullName) ($($pdf.Length) bytes)"

# 3. no-args launch: the window must still be alive after 8 s and must have written app.log
$w = Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 8
if ($w.HasExited) {
    Get-Content (Join-Path $smokeHome "app.log") -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    throw "the window exited within 8 s (exit $($w.ExitCode))"
}
Stop-Process -Id $w.Id -Force
if (-not (Test-Path (Join-Path $smokeHome "app.log"))) { throw "app.log was not written" }
Remove-Item Env:\FRIDGESHEET_HOME
Write-Host "smoke OK"
```

- [ ] **Step 7: Delete the spike files, run the tests, commit**

```bash
git rm -q packaging/windows/spike_entry.py .github/workflows/spike-pyinstaller.yml
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q          # expect 181 passed, 1 skipped
git add packaging/windows tests/test_packaging.py
git commit -m "Windows bundle: pinned SumatraPDF, PyInstaller spec, build.ps1 and smoke.ps1; drop the spike

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: The installer and the release workflow

**Files:**
- Create: `packaging/windows/installer.iss`, `.github/workflows/release.yml`
- Modify: `README.md` (add a "## Releasing" section before "## License"), `tests/test_packaging.py` (append)

**Interfaces:**
- Consumes: `dist\FridgeSheet\` and `build.ps1` (Task 2); `FridgeSheet.exe schedule remove` (Plan 1); `APP_ID = "Cairnea.FridgeSheet"` (Plan 1, `host/notify_windows.py`).
- Produces: `dist\FridgeSheet-Setup-<version>.exe`; the `release` workflow (`workflow_dispatch` builds and uploads an artifact; a `v*` tag additionally creates a GitHub release with the installer attached, after checking the tag equals `v<pyproject version>`).

- [ ] **Step 1: Append the failing tests**

```python
def test_installer_script_matches_the_spec():
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    assert "PrivilegesRequired=lowest" in iss
    assert "DefaultDirName={localappdata}\\Programs\\Fridge Sheet" in iss
    assert 'AppUserModelID: "Cairnea.FridgeSheet"' in iss
    assert 'Parameters: "schedule remove"' in iss and "[UninstallRun]" in iss
    assert "postinstall" in iss and "desktopicon" in iss
    assert "fridgesheet" in iss and "usPostUninstall" in iss          # the "your data was kept" message
    assert "OutputBaseFilename=FridgeSheet-Setup-{#AppVersion}" in iss


def test_app_user_model_id_matches_the_toast_code():
    from fridgesheet.host.notify_windows import APP_ID
    iss = (WIN / "installer.iss").read_text(encoding="utf-8")
    assert f'AppUserModelID: "{APP_ID}"' in iss


def test_release_workflow_triggers_and_gates():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in wf and '"v*"' in wf
    assert "windows-latest" in wf and "build.ps1" in wf
    assert "upload-artifact" in wf and "action-gh-release" in wf
    assert "startsWith(github.ref, 'refs/tags/v')" in wf
    assert "pyproject.toml" in wf and "github.ref_name" in wf              # tag == v<version> gate
```

- [ ] **Step 2: Run to verify they fail**

Run: `env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest tests/test_packaging.py -q`
Expected: the three new tests FAIL with `FileNotFoundError`.

- [ ] **Step 3: Write `installer.iss`**

```iss
; packaging/windows/installer.iss
; Per-user installer for Fridge Sheet. Built by build.ps1:
;   ISCC.exe /DAppVersion=<version> /DSourceDir=<repo>\dist\FridgeSheet /O<repo>\dist installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\FridgeSheet"
#endif

[Setup]
AppId={{B7E1C0E2-5C1D-4E8B-9C2A-7D3F0A1B2C3D}
AppName=Fridge Sheet
AppVersion={#AppVersion}
AppVerName=Fridge Sheet {#AppVersion}
AppPublisher=Tony Stein
AppPublisherURL=https://github.com/steiner385/fridgesheet
AppSupportURL=https://github.com/steiner385/fridgesheet/blob/main/docs/windows.md
DefaultDirName={localappdata}\Programs\Fridge Sheet
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
OutputBaseFilename=FridgeSheet-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Fridge Sheet
UninstallDisplayIcon={app}\FridgeSheet.exe

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Fridge Sheet"; Filename: "{app}\FridgeSheet.exe"; AppUserModelID: "Cairnea.FridgeSheet"
Name: "{autodesktop}\Fridge Sheet"; Filename: "{app}\FridgeSheet.exe"; AppUserModelID: "Cairnea.FridgeSheet"; Tasks: desktopicon

[Run]
Filename: "{app}\FridgeSheet.exe"; Description: "Launch Fridge Sheet"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove the scheduled task while the exe still exists. RunOnceId keeps Inno from running it twice.
Filename: "{app}\FridgeSheet.exe"; Parameters: "schedule remove"; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSchedule"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox('Fridge Sheet has been removed.' + #13#10 + #13#10 +
           'Your settings, printed sheets and logs were kept in' + #13#10 +
           ExpandConstant('{localappdata}\fridgesheet') + #13#10 + #13#10 +
           'Delete that folder yourself if you no longer want them. Your OneLogin password stays in Windows Credential Manager under "fridgesheet".',
           mbInformation, MB_OK);
end;
```

- [ ] **Step 4: Write `release.yml`**

```yaml
# .github/workflows/release.yml
name: release
on:
  push:
    tags: ["v*"]
  workflow_dispatch:
jobs:
  build:
    runs-on: windows-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Tag must match pyproject version
        if: startsWith(github.ref, 'refs/tags/v')
        shell: pwsh
        run: |
          $v = (Select-String -Path pyproject.toml -Pattern '^version = "(.+)"').Matches[0].Groups[1].Value
          if ("${{ github.ref_name }}" -ne "v$v") { throw "tag ${{ github.ref_name }} does not match pyproject version $v" }
      - name: Build, smoke-test and package
        shell: pwsh
        run: .\packaging\windows\build.ps1
      - uses: actions/upload-artifact@v4
        with:
          name: FridgeSheet-Setup
          path: dist/FridgeSheet-Setup-*.exe
          if-no-files-found: error
      - name: Publish the GitHub release
        if: startsWith(github.ref, 'refs/tags/v')
        uses: softprops/action-gh-release@v2
        with:
          files: dist/FridgeSheet-Setup-*.exe
          generate_release_notes: true
```

- [ ] **Step 5: README "Releasing" section**

Insert before `## License`:

```markdown
## Releasing the Windows installer

The Windows app ("Fridge Sheet") is built by `.github/workflows/release.yml` on a Windows runner, from `packaging/windows/build.ps1`, which bundles Chromium and a pinned SumatraPDF, smoke-tests the built exe, and wraps it with Inno Setup.

1. Bump `version` in `pyproject.toml` and merge to `main`.
2. Optionally run the workflow by hand first (Actions → release → Run workflow) and download the `FridgeSheet-Setup` artifact to try it.
3. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`. The job refuses a tag that does not match `pyproject.toml`, and on success attaches `FridgeSheet-Setup-0.2.0.exe` to a GitHub release.

The page to send along with it is [docs/windows.md](docs/windows.md).
```

- [ ] **Step 6: Run the tests, commit**

```bash
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q          # expect 184 passed, 1 skipped
git add packaging/windows/installer.iss .github/workflows/release.yml README.md tests/test_packaging.py
git commit -m "Inno Setup installer and the release workflow (manual dispatch builds an artifact; a v* tag publishes)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

### Task 4: Run the release workflow for real (manual dispatch, no tag)

This is where Tasks 2 and 3 are actually exercised. Expect iteration: PyInstaller hidden imports, a PowerShell quoting slip, an Inno Setup directive rejected by the installed version. Each fix is its own commit and push.

**Files:**
- Modify (only as fixes require): `packaging/windows/*`, `.github/workflows/release.yml`, `fridgesheet/**` if the built exe fails a smoke step for a code reason.
- Modify: `docs/superpowers/plans/2026-09-14-windows-sheet-release.md` (Step 6 records the outcome).

**Interfaces:**
- Consumes: everything from Tasks 1 to 3.
- Produces: a green `release` run on this branch with the `FridgeSheet-Setup` artifact, and the recorded run URL.

- [ ] **Step 1: Push and dispatch**

```bash
git push
gh workflow run release.yml --ref "$(git rev-parse --abbrev-ref HEAD)"
sleep 30
RUN=$(gh run list --workflow release.yml --branch "$(git rev-parse --abbrev-ref HEAD)" --limit 1 --json databaseId -q '.[0].databaseId')
echo "run=$RUN"
gh run watch "$RUN" --exit-status 2>&1 | tee /tmp/release-run.log | tail -20
```

Expected: the job is green after roughly 10 to 15 minutes (Chromium download, PyInstaller, three smoke steps, Inno Setup). Note the run id.

- [ ] **Step 2: If red, read the failing step and fix the cause**

```bash
gh run view "$RUN" --log-failed 2>&1 | tail -80
```

Known failure classes and the fix for each; apply one per commit, push, re-dispatch, re-watch:
1. `ModuleNotFoundError` inside the exe (seen in `doctor.txt` or `app.log` echoed by `smoke.ps1`): add the module to `hiddenimports` in `FridgeSheet.spec`.
2. `doctor` FAIL on `chromium`: `ms-playwright` was not copied where the driver expects; compare `Get-ChildItem dist\FridgeSheet\ms-playwright` with what `playwright install` printed, and fix the `Copy-Item` in `build.ps1`.
3. `doctor` FAIL on `credential store`: keyring backend not found in the bundle; confirm `copy_metadata("keyring")` landed in `_internal` and add `keyring.backends.Windows` (already there) or `win32ctypes` submodules to `hiddenimports`.
4. `doctor` FAIL on `timezone`: `tzdata` data files missing; confirm `collect_data_files("tzdata")` produced files (add `print(datas)` temporarily in the spec if needed).
5. The no-args launch exits early: read `app.log` (echoed by `smoke.ps1`); a `tkinter`/`_tkinter` import error means Python on the runner lacks Tk, which `actions/setup-python` does include, so the more likely cause is a code path; fix in `gui.py`/`__main__.py`.
6. `ISCC` rejects a directive (`ArchitecturesAllowed`, `AppUserModelID`): adjust `installer.iss` to the installed Inno Setup 6 syntax; the error names the line.
7. PowerShell: `Start-Process -WindowStyle Hidden` is not accepted for a GUI-subsystem exe on some hosts; drop `-WindowStyle Hidden` from the two `-Wait` invocations in `smoke.ps1`.

Allow up to five fix commits. If still red, stop and report BLOCKED with the last failing output.

- [ ] **Step 3: Verify the artifact and the smoke output**

```bash
gh run view "$RUN" --json conclusion,jobs --jq '{conclusion, jobs: [.jobs[] | {name, conclusion}]}'
gh api "repos/steiner385/fridgesheet/actions/runs/$RUN/artifacts" --jq '.artifacts[] | {name, size_in_bytes}'
gh run view "$RUN" --log 2>/dev/null | grep -E "smoke OK|built .*sheet.pdf|== built|OK    |FAIL  " | head -30
```

Expected: `conclusion: success`; one artifact `FridgeSheet-Setup` of roughly 150 to 250 MB; the log shows nine `OK` doctor lines, `built ...sheet.pdf`, `smoke OK`, and `== built ...FridgeSheet-Setup-0.2.0.exe (<n> MB)`.

- [ ] **Step 4: Confirm nothing was tagged or released**

```bash
git tag --list 'v*'
gh release list --limit 3
```

Expected: no `v0.2.0` tag, no release. (The manual dispatch only uploads an artifact.)

- [ ] **Step 5: Commit any fixes made in Step 2** (each was already committed and pushed; confirm `git status -sb` shows the branch level with origin).

- [ ] **Step 6: Record the outcome here**

**Fix-wave build (after the final review):** run https://github.com/steiner385/fridgesheet/actions/runs/34889884757 green on commit `6fac3d0`, artifact `FridgeSheet-Setup` 279,411,365 bytes; installed tree 863 MB, installer 267 MB. Two runner-side fixes were needed: SumatraPDF's GitHub tag for 3.5.2 is `3.5.2rel` (`efa310d`), and the now-honest `printers` probe fails without a configured printer, so `smoke.ps1` exports `FRIDGESHEET_PRINTER` from the first printer `Get-Printer` reports ("Microsoft Print to PDF" on the runner) for the duration of the smoke run (`6fac3d0`). The nine doctor lines on the runner: python, home, timezone, pdf, chromium (151.0.7922.34 from `ms-playwright`), credential store (`WinVaultKeyring: round trip OK`), printers, print engine, scheduler — all OK; then `scheduled task installed and removed` and `smoke OK`. Temporary branch trigger removed afterwards.

**First build (Task 4):** `gh workflow run release.yml --ref ccswitch/main-418b5ee1` (and a direct `gh api
.../dispatches`) 404'd: GitHub only registers `workflow_dispatch` workflows from files
present on the repository's *default* branch, and `release.yml` existed only on this
branch. The controller ruled out merging to `main` and instead approved a temporary
push trigger scoped to this branch (`branches: ["ccswitch/main-418b5ee1"]`), added in
commit `fd0bddb` and removed again in `6952138` once the build was green; the publish
step stayed gated on `startsWith(github.ref, 'refs/tags/v')` throughout, so neither run
tagged or released anything.

Two runs on this branch:
- Run [34884568097](https://github.com/steiner385/fridgesheet/actions/runs/34884568097) — **failed** after 2m1s. All nine `doctor` probes and the dry-run PDF
  passed; the no-args launch step then threw `"app.log did not grow during the window
  launch"` even though the process had not exited within the 8 s wait. Cause:
  `run_app()` (`fridgesheet/app/gui.py`) only logs on an unhandled exception, so a
  clean startup never grows `app.log` — the smoke-script assertion was vacuous by
  construction, not a sign of a broken launch (this is the brief's failure class 9,
  presenting as a log-growth false negative rather than an early `HasExited`).
- Run [34884940633](https://github.com/steiner385/fridgesheet/actions/runs/34884940633) — **green**, build job succeeded in 7m22s. Artifact `FridgeSheet-Setup`,
  279,402,045 bytes (~267 MB), within the expected 150-300 MB range.

One fix commit (`bce9e4a`, `smoke.ps1: check the no-args launch by window handle, not
app.log growth`): replaced the `app.log` growth assertion with a check that the
launched process has a live `MainWindowHandle` after the 8 s wait — the real evidence a
GUI window came up — and updated the matching pinned string in
`tests/test_packaging.py` (`"did not grow"` → `"MainWindowHandle"`) in the same commit.

The nine `doctor` lines from the green run (`34884940633`):
```
OK    python: 3.12.10 frozen at D:\a\fridgesheet\fridgesheet\dist\FridgeSheet\FridgeSheet.exe
OK    home: C:\Users\RUNNER~1\AppData\Local\Temp\fridgesheet-smoke-677fbb492fe54150bea7b6193a10e10e is writable
OK    timezone: America/New_York
OK    pdf: reportlab wrote a 1344-byte PDF
OK    chromium: Chromium 151.0.7922.34 at D:\a\fridgesheet\fridgesheet\dist\FridgeSheet\ms-playwright\chromium-1234\chrome-win64\chrome.exe
OK    credential store: keyring backend WinVaultKeyring
OK    printers: 1 printer(s), default none, configured system default
OK    print engine: D:\a\fridgesheet\fridgesheet\dist\FridgeSheet\SumatraPDF.exe
OK    scheduler: task-scheduler: not scheduled
```
followed by the dry-run build (`open-work dry-run built ...sheet.pdf 1p Sample=0
data=9/14 08:00`), `smoke OK`, and `== built
D:\a\fridgesheet\fridgesheet\dist\FridgeSheet-Setup-0.2.0.exe (267 MB)`.

`git tag --list 'v*'` and `gh release list --limit 3` were both empty after the green
run.

---

### Task 5: The friend's page, and the README pointer

**Files:**
- Create: `docs/windows.md`
- Modify: `README.md` (one sentence in the intro pointing to `docs/windows.md`), `docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md` (section 9 touch-ups for anything Task 4 changed, plus `smoke.ps1` and `doctor` which the spec did not name)
- Test: `tests/test_packaging.py` (append one test that the page exists and names the limitations)

**Interfaces:**
- Consumes: the installed layout and behaviour from Tasks 1 to 4.

- [ ] **Step 1: Append the failing test**

```python
def test_windows_page_exists_and_names_the_limitations():
    page = (ROOT / "docs" / "windows.md").read_text(encoding="utf-8")
    for phrase in ("SmartScreen", "More info", "Run anyway", "multi-factor", "logged in", "%LOCALAPPDATA%\\fridgesheet",
                   "Test login", "Print now", "no-print-days.txt", "late-rules.toml", "doctor.txt", "Task Scheduler", "Uninstall"):
        assert phrase in page, phrase
```

- [ ] **Step 2: Write `docs/windows.md`**

```markdown
# Fridge Sheet for Windows

Fridge Sheet prints a one-page-per-kid list of open schoolwork every school day at a time you choose, pulled from Canvas and Home Access Center with your own Lakota OneLogin parent login. Everything runs on your PC. The app talks only to OneLogin, Canvas and Home Access Center, and nothing about your kids leaves your computer.

## Before you start

- Windows 10 or 11, 64-bit, and a printer Windows can already print to.
- Your Lakota OneLogin parent username and password. If the district has turned on **multi-factor** sign-in for your account (a code on your phone every time), the automatic refresh cannot work; Test login will tell you so.
- About 300 MB of disk space (a copy of Chromium is included so the app can sign in the way a browser does).

## Install

1. Download `FridgeSheet-Setup-<version>.exe` from the Releases page.
2. Run it. Windows **SmartScreen** will say "Windows protected your PC" because the installer is not code-signed. Click **More info**, then **Run anyway**.
3. The installer needs no administrator password; it installs for your Windows user only and offers a desktop shortcut. It opens Fridge Sheet when it finishes.

## First run

1. **Settings tab.** Enter your OneLogin username and password. The password goes into Windows Credential Manager, never into a file. Pick your printer (or leave "System default"), the print time, and how many days ahead to look. If your kids go by nicknames, put one `First=Nick` per line. Tick **Print the sheet automatically on school days**.
2. **Run tab → Test login.** Takes up to a minute. Both lines must say OK. If not, check the username and password on the Settings tab and try again.
3. **Settings tab → Save.** Once a login has passed, Save installs the scheduled task. The Run tab's status line shows the next run time.
4. **Run tab → Preview today's sheet** to see what will print, or **Print now** to print it right away.

## What happens every day

At the time you chose, on school days, Windows Task Scheduler runs Fridge Sheet in the background while you are **logged in** (a locked screen is fine; a signed-out or powered-off PC skips that day, and the next day's run does not print the old sheet). It refreshes Canvas and Home Access Center, builds the sheet, prints it two-sided, and shows a small notification saying it printed, or why it did not. If the refresh fails, it prints from the last good data if that is under a day old and says so on the sheet.

## Your files

Everything lives in `%LOCALAPPDATA%\fridgesheet` (paste that into File Explorer's address bar):

| File | What it is |
|---|---|
| `sheets\<date>\sheet.pdf` | every sheet, one folder per day |
| `no-print-days.txt` | days not to print (seeded with the district calendar); edit it from the Settings tab |
| `late-rules.toml` | how long each class still takes late work; edit it from the Settings tab |
| `print-sheet.log` | one line per run: printed, skipped, or why it failed |
| `app.log` | the app's own log |
| `doctor.txt` | the last diagnostics report |
| `config.toml` | your settings (no password in it) |

## If something goes wrong

- **Help → Run diagnostics** in the app checks Chromium, the PDF engine, the credential store, printers and the scheduler, and writes `doctor.txt`. Any `FAIL` line is the place to look.
- **"Login failed"**: the username or password is wrong, or OneLogin wants multi-factor sign-in. Fix the Settings tab, Save, and Test login again.
- **Nothing printed at the scheduled time**: open the Run tab; the status line shows the last result. Common causes: the PC was off or you were signed out; the printer was off (the sheet is kept as a PDF in `sheets\<date>`); it was a no-print day. You can also open Windows **Task Scheduler** and look for "Fridge Sheet - open-work".
- **Wrong printer**: pick another on the Settings tab and Save; the app never uses the Windows default unless you leave the choice at "System default".

## Uninstall

Settings → Apps → Fridge Sheet → **Uninstall**. The uninstaller removes the scheduled task and the program, and leaves your sheets, settings and logs in `%LOCALAPPDATA%\fridgesheet` for you to delete if you wish. Your password stays in Credential Manager under "fridgesheet" until you remove it there.

## Credits and licences

Fridge Sheet is MIT-licensed: https://github.com/steiner385/fridgesheet. It bundles Chromium via Playwright (BSD-3-Clause) and SumatraPDF for printing (GPL-3.0; source at https://www.sumatrapdfreader.org; the licence text is installed as `SumatraPDF-LICENSE.txt`).
```

- [ ] **Step 3: README pointer and spec touch-ups**

In `README.md`'s intro list of design goals, add a final bullet: `- **Other parents can install it.** A Windows build ("Fridge Sheet") with a settings window and a per-user installer: see [docs/windows.md](docs/windows.md) and "Releasing" below.`

In the spec, section 9: after the six-step list add `7. The build runs \`packaging/windows/smoke.ps1\` on the bundle before packaging: \`FridgeSheet.exe doctor\` (all probes must pass), a dry-run sheet from a fixture snapshot, and a no-arguments launch that must survive eight seconds.` and mention `fridgesheet doctor` in section 5's command list. Apply any further deviation Task 4 forced (a changed directive, a renamed file).

- [ ] **Step 4: Run the tests, commit, push, and watch CI**

```bash
env -u PYTHONPATH ~/fridgesheet/.venv/bin/python -m pytest -q          # expect 185 passed, 1 skipped
git add docs/windows.md README.md docs/superpowers/specs/2026-09-14-windows-sheet-app-design.md tests/test_packaging.py
git commit -m "docs: the Windows page for other parents; README pointer; spec records the smoke test and doctor

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
gh run watch "$(gh run list --workflow ci.yml --branch "$(git rev-parse --abbrev-ref HEAD)" --limit 1 --json databaseId -q '.[0].databaseId')" --exit-status 2>&1 | tail -3
```

---

## Done when

- The `release` workflow has one green manual run on this branch with a `FridgeSheet-Setup` artifact, and Task 4 Step 6 records it.
- `fridgesheet doctor` runs on Linux and inside the bundle; the smoke test proves the bundle can build a sheet and open its window.
- No tag and no GitHub release exist; the README tells Tony how to create them.
- `docs/windows.md` covers install, first run, the daily run, files, troubleshooting, limitations and uninstall.
- CI green on both runners.

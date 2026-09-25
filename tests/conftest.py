# tests/conftest.py
"""Shared markers and fixtures.

pdftotext (poppler-utils) is how tests read a built PDF back; it is installed on the
Linux CI leg and usually absent on Windows, where those tests skip.

`server.py` calls `load_settings()` at import, so collecting `test_server_tools.py`
loads the developer's real `~/.fridgesheet/.env` into `os.environ` before any test
runs. The autouse fixture below strips every `FRIDGESHEET_*` variable for the duration of
each test, so a test that asserts on a default never sees the machine's own settings.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pytest

# Before anything from the package is imported: point the home at a throwaway directory.
# `server.py` calls `load_settings()` at import, and `load_settings` moves the *real* old data
# directory to the real new one on first sight (fridgesheet/migrate.py). Collected once with
# no override, the suite migrated the developer's own ~/.lakota-grades (2026-09-18). With an
# override in force `migrate.legacy_home` answers None and nothing outside tmp is touched.
TEST_HOME = os.environ["FRIDGESHEET_HOME"] = tempfile.mkdtemp(prefix="fridgesheet-tests-")

from fridgesheet import config, migrate

#: The unpatched lookup, for the one test that checks what it computes (paths only; it
#: never touches the filesystem). Every other test sees the None from `_no_real_migration`.
REAL_LEGACY_HOME = migrate.legacy_home

#: Executable names (case-folded, `.exe`-stripped) that must never actually launch during a
#: test run. `systemctl --user` reaches this machine's live units --
#: `fridgesheet-print-sheet.{service,timer}` (enabled, prints a real household's schoolwork every
#: weekday at 2 PM) and `fridgesheet-refresh.{service,timer}` -- and `schtasks` is its
#: Windows equivalent. Neither belongs anywhere near a test process.
_FORBIDDEN_PROGRAMS = {"systemctl", "schtasks"}


def _argv0(args) -> str:
    """The program name `Popen` would exec, normalized for comparison: `Popen`'s `args` is
    either a single command (str/bytes/`os.PathLike`, the `shell=True` shape, or a bare
    `executable=` override) or a sequence whose first element is the program (itself possibly
    `os.PathLike`, e.g. `[Path("/usr/bin/systemctl"), "start"]`). Strip any directory
    component (`/usr/bin/systemctl`, `C:\\Windows\\System32\\schtasks.exe`) and any Windows
    `.exe` suffix, then lowercase, so `systemctl`, `SYSTEMCTL`, `/usr/bin/systemctl` and
    `schtasks.EXE` all compare equal to the bare names in `_FORBIDDEN_PROGRAMS`."""
    if isinstance(args, os.PathLike):
        # `Popen`'s `executable=` accepts a `Path` directly (and `args` itself can be one in
        # the `shell=True`-less single-command shape) -- normalize it to `str` here, the same
        # as the `bytes` case just below, rather than letting it reach the `elif args:`
        # branch, where a bare `Path` is truthy but not subscriptable and raises `TypeError`
        # instead of being matched (or safely passed through).
        args = os.fspath(args)
    if isinstance(args, bytes):
        args = args.decode()
    if isinstance(args, str):
        # The `shell=True` shape: `args` is the whole command line ("systemctl --user
        # daemon-reload"), not just the program, so take its first whitespace-delimited
        # token rather than treating the entire string as one (nonexistent) filename.
        first = args.split()[0] if args.split() else ""
    elif args:
        first = args[0]
        if isinstance(first, os.PathLike):
            first = os.fspath(first)
    else:
        first = ""
    # `os.path.basename` only splits on the *current* OS's separator, but a Windows-style
    # absolute path (`C:\Windows\System32\schtasks.exe`) can appear in argv even when this
    # guard itself runs on Linux (e.g. a test exercising Windows-only code with a literal
    # path), so split on both `/` and `\` rather than trusting `os.path.basename` alone.
    name = os.path.basename(str(first).replace("\\", "/"))
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()


def _blocked_program(args, executable=None) -> str | None:
    """The forbidden program name a `Popen(args, ..., executable=executable)` call would
    exec, or `None` if nothing here is blocked. `executable=` overrides which binary actually
    runs regardless of what `args[0]` merely *says* -- `Popen(["placeholder"],
    executable="/usr/bin/systemctl")` really execs systemctl even though argv[0] claims to be
    something else -- so it wins over `args` whenever it is given. Split out of
    `guarded_popen` below so this decision (including the `executable=` override) can be
    unit-tested directly against plain strings, with no `Popen`, real or guarded, ever
    constructed."""
    program = _argv0(executable) if executable else _argv0(args)
    return program if program in _FORBIDDEN_PROGRAMS else None


needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext (poppler-utils) not installed")


@pytest.fixture(autouse=True)
def _no_real_migration(monkeypatch):
    """No test may move a real data directory. The env override above covers import time;
    this covers every test, including one that clears FRIDGESHEET_HOME to assert a default."""
    monkeypatch.setattr(migrate, "legacy_home", lambda **kw: None)


@pytest.fixture
def real_legacy_home():
    return REAL_LEGACY_HOME


@pytest.fixture(autouse=True)
def _no_app_env(monkeypatch):
    for name in [k for k in os.environ if k.startswith(("FRIDGESHEET_", "LAKOTA_"))]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_app_home(monkeypatch, tmp_path):
    """Patches the one place `DEFAULT_HOME` lives: `config.DEFAULT_HOME`. That reaches every
    *live* read of it -- `Settings.home`'s default factory (`field(default_factory=lambda:
    DEFAULT_HOME)` closes over the name, so it looks it up on the `config` module each time a
    bare `Settings()` is built) and any code that writes `config.DEFAULT_HOME` at the point of
    use, e.g. `entry.main()` -> `setup_logging(config.DEFAULT_HOME)`.

    It does NOT reach a name some other module imported *by value* (`from fridgesheet.config
    import DEFAULT_HOME`) before this fixture ran -- that binds a private copy into the
    importing module's own namespace, and there would be nothing here to patch. That was a real
    bug once (`fridgesheet/web/__main__.py` did exactly this; fixed in #35 fix round 2) and
    would be again if a new import-by-value of `DEFAULT_HOME` ever appears; grep for
    `from fridgesheet.config import DEFAULT_HOME` (or `config import.*DEFAULT_HOME`) if this
    guard is ever suspected of a leak.

    Without this fixture, a test that forgets `home=tmp_path` (or a command path that starts
    touching the database or the filesystem where it never used to) reaches the owner's real
    `~/.fridgesheet`: it has happened three times in this plan already -- the systemd unit
    directory, the database opened by `reports.available`, and `entry.main()`'s log directory.
    Tests that pass `home=` explicitly, or patch `config.DEFAULT_HOME` themselves, are
    unaffected; this only changes what a bare `Settings()` or a live `config.DEFAULT_HOME`
    read resolves to.
    """
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path / ".fridgesheet")


@pytest.fixture(autouse=True)
def _no_real_scheduler(monkeypatch):
    """Makes it impossible for any test to launch a real `systemctl` or `schtasks`, however
    it gets there.

    The obvious fixture is `monkeypatch.setattr(subprocess, "run", guard)`. **That does not
    work in this codebase and would give a guard that looks right and catches nothing.** All
    31 `fridgesheet/host/*` functions take their process launcher as a default argument --
    `def install(key, ..., run=subprocess.run)` -- and a default argument is evaluated once,
    at `def` time, i.e. at import. Every one of those functions already holds a direct
    reference to the *original* `subprocess.run` function object before this fixture, or any
    test, ever runs. Patching the `subprocess.run` name afterwards changes what a fresh
    `subprocess.run` lookup returns; it does nothing for a name that already closed over the
    old object. A test that calls `service_linux.describe()` without passing `run=` would
    sail straight past that patch into a real `systemctl --user is-enabled ...`.

    `subprocess.run` internally does `with Popen(*popenargs, **kwargs) as process`, and
    resolves `Popen` as a module global *at call time* -- not at def time, because `run`
    never takes `Popen` as a default argument. So patching `subprocess.Popen` is what
    actually reaches a `run=subprocess.run` default captured at import: every path, direct
    call or captured default, ends up constructing a `Popen`, and that is the one place this
    fixture needs to sit. (Verified empirically before writing this: patching
    `subprocess.run` left a captured default unintercepted; patching `subprocess.Popen`
    caught it.)

    The check matches the program name however the argv is spelled -- bare (`systemctl`),
    absolute (`/usr/bin/systemctl`, `C:\\Windows\\System32\\schtasks.exe`), `.exe`-suffixed,
    any case, `args` given as a single string (the `shell=True` shape) rather than a list, or
    `Popen`'s `executable=` override (which wins over `args[0]` when both are given, since
    `executable` is what actually runs) -- via `_blocked_program`/`_argv0` above. Anything
    else is handed straight to the real `Popen`, because
    real, legitimate subprocess use exists in this codebase and must keep working:
    `pdftotext` (`sheet.py`, see `needs_pdftotext` above), `op read` (`config.py`), a
    Chromium `--version` probe (`session.py`), and `web/__main__.py`'s own `Popen` call for
    detaching the server process. This fixture only ever blocks `systemctl` and `schtasks`;
    it does not fake, redirect, or record any other command.

    `systemctl --user` and `schtasks` are what would reach this machine's live units --
    `fridgesheet-print-sheet.{service,timer}` (enabled; prints a real household's schoolwork every
    weekday at 2 PM) and `fridgesheet-refresh.{service,timer}` -- if a test ever forgot to
    inject a fake `run=`. That is not hypothetical: it happened once already, when the
    report-delete route grew a call into the scheduler and a delete test written without the
    injected fake would have run a real `systemctl --user disable --now
    fridgesheet-view-N.timer`. A test that needs to make an assertion about a command line must
    inject its own fake `run=` (see `tests/test_os_leftovers.py` etc. for the
    pattern); this fixture never allows the real thing through for `systemctl`/`schtasks`,
    convention or no convention.
    """
    real_popen = subprocess.Popen

    def guarded_popen(args, *popen_args, **kwargs):
        # `Popen(args, bufsize=-1, executable=None, ...)`: `executable` is the *third*
        # parameter and can be passed positionally, so reading it from `kwargs` alone let
        # `Popen(["placeholder"], -1, "/usr/bin/systemctl")` through unchecked -- the same
        # class of hole as the keyword form this guard already closes, and the one that
        # actually decides which binary runs. `popen_args` here is everything after `args`,
        # so index 1 is `executable`.
        executable = popen_args[1] if len(popen_args) > 1 else kwargs.get("executable")
        program = _blocked_program(args, executable)
        if program:
            raise RuntimeError(
                f"blocked: a test tried to launch a real {program!r}. This machine has live "
                "systemd units (fridgesheet-print-sheet.{service,timer}, "
                "fridgesheet-refresh.{service,timer}) that a real systemctl/schtasks call "
                "could enable, disable or delete. Inject a fake `run=` into whatever "
                f"host function is calling {program!r} instead of letting it fall through "
                "to its `run=subprocess.run` default."
            )
        return real_popen(args, *popen_args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", guarded_popen)


@pytest.fixture(autouse=True)
def _no_background_clock(monkeypatch):
    """No test may start a real background clock. `server.run` now starts one beside the jobs
    worker (`web/clock.py`); `tests/test_web_server.py` (and maybe others) call the real
    `server.run` with a fake `serve`, so without this they would get a live ticking thread no
    test asked for -- and, once a later task adds it, the OS-cleanup thread beside it."""
    from fridgesheet.web import clock
    monkeypatch.setattr(clock, "start_background", lambda state: None)


@pytest.fixture(autouse=True)
def _no_github(monkeypatch):
    """`web.updates` asks GitHub for the latest release once a day. No test may make that call:
    it is slow, it is flaky, and a suite that passes only with a network is not a suite. The
    default fetch is replaced with one that fails the way a machine with no network fails; a
    test that wants an answer injects its own through `state.extra["update_fetch"]`."""
    from fridgesheet.web import updates

    def offline(url):
        raise OSError("no network in tests")
    monkeypatch.setattr(updates, "DEFAULT_FETCH", offline)

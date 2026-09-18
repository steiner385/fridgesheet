"""Proves the autouse `_no_real_scheduler` fixture in `conftest.py` actually closes the hole
it claims to close.

The hole is specific: the 31 host functions take their process launcher as a *default
argument* (`def install(key, ..., run=subprocess.run)`), which is evaluated once at `def`
time and holds a direct reference to the original `subprocess.run` function object.
Patching the `subprocess.run` *attribute* after that point changes what a fresh lookup of
`subprocess.run` returns, but does nothing for a name that already closed over the old
object -- so a naive `monkeypatch.setattr(subprocess, "run", guard)` fixture would report
green while a real `systemctl --user disable --now fridgesheet-view-7.timer` runs underneath it.

`subprocess.run` internally builds `Popen(*popenargs, **kwargs)`, and resolves `Popen` as a
module global at *call* time -- so patching `subprocess.Popen` is what actually reaches a
captured `run=subprocess.run` default. These tests check both the easy case (calling
`subprocess.run` directly) and the case that matters (a function that captured the default
at import, long before this test file existed).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from fridgesheet import host
from fridgesheet.host import opener, service_linux

# A bare `import conftest`, not `from tests.conftest import ...` or `from tests import
# conftest`: `tests/` has no `__init__.py`, so pytest loads `conftest.py` as the top-level
# module named `conftest` (its "prepend" import mode walks up from a package-less directory
# and stops there). `from tests.conftest import ...` instead imports it a *second* time as
# the namespace-package module `tests.conftest` -- a distinct object in `sys.modules` with
# its own independent copy of every module-level name. Patching `_FORBIDDEN_PROGRAMS` on
# that second copy would have zero effect on the `guarded_popen` closure pytest actually
# runs, which reads globals from the first. `import conftest` here hits the same
# already-imported top-level module pytest's fixture machinery uses (confirmed via
# `sys.modules["conftest"] is <this import>`), so patching it here reaches the real thing.
import conftest as conftest_module

assert conftest_module is sys.modules["conftest"]


def test_direct_systemctl_call_is_blocked():
    with pytest.raises(RuntimeError, match="systemctl"):
        subprocess.run(["systemctl", "--user", "daemon-reload"])


def test_direct_schtasks_call_is_blocked():
    with pytest.raises(RuntimeError, match="schtasks"):
        subprocess.run(["schtasks", "/Query"])


def test_a_default_argument_captured_at_import_is_still_blocked():
    """The case a `subprocess.run` attribute patch misses: `service_linux.describe`'s
    `run=subprocess.run` default was bound to the original function object when
    `service_linux.py` was imported, long before this test (or any fixture) ran. If the
    guard only patched the `subprocess.run` attribute, this call would reach a real
    `systemctl --user is-enabled ...` on the machine that owns this repo."""
    with pytest.raises(RuntimeError, match="systemctl"):
        service_linux.describe()


def test_absolute_path_to_systemctl_is_blocked():
    with pytest.raises(RuntimeError, match="systemctl"):
        subprocess.run(["/usr/bin/systemctl", "--user", "daemon-reload"])


def test_schtasks_exe_suffix_is_blocked():
    with pytest.raises(RuntimeError, match="schtasks"):
        subprocess.run(["schtasks.exe", "/Query"])


def test_absolute_windows_path_with_exe_suffix_is_blocked():
    with pytest.raises(RuntimeError, match="schtasks"):
        subprocess.run([r"C:\Windows\System32\schtasks.exe", "/Query"])


def test_argv_given_as_a_bare_string_is_blocked():
    """`Popen`/`run` accept a single string as `args` (only sensible with `shell=True`, but
    the guard should not assume the caller got that right)."""
    with pytest.raises(RuntimeError, match="systemctl"):
        subprocess.run("systemctl --user daemon-reload", shell=True)


def test_case_insensitive_windows_spelling_is_blocked():
    with pytest.raises(RuntimeError, match="schtasks"):
        subprocess.run(["SCHTASKS.EXE", "/Query"])


def test_non_blocked_command_runs_normally_through_the_wrapper():
    result = subprocess.run(["echo", "hello-from-guard-test"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "hello-from-guard-test" in result.stdout


def test_error_message_names_the_reason_and_the_fix():
    with pytest.raises(RuntimeError) as exc_info:
        subprocess.run(["systemctl", "--user", "start", "fridgesheet-view-7.timer"])
    message = str(exc_info.value)
    assert "run=" in message           # tells the reader how to fix their test
    assert "systemctl" in message


# --- Fix round 1, finding 1: host/opener.py had the identical default-argument trap one
# level up (`popen=subprocess.Popen` captured at import), which this guard's `Popen` patch
# could never reach. Fixed by resolving `subprocess.Popen` inside the function body
# (`popen = popen or subprocess.Popen`) instead of binding it in the signature. This proves
# the fix routes through whatever `subprocess.Popen` currently is, using a sentinel name --
# never `systemctl`/`schtasks` -- injected into the forbidden set for the duration of the
# test, so the real binaries are never named and a bypass (if the fix regressed) would only
# ever attempt to exec a nonexistent program, not a real one.

def test_open_file_default_popen_is_resolved_at_call_time_not_import_time(monkeypatch, tmp_path):
    """`open_file`'s `popen=None` default must resolve `subprocess.Popen` at the point of
    use, so a call that injects no `popen=` of its own still goes through whatever this
    fixture has currently patched `subprocess.Popen` to be. Uses a harmless sentinel program
    name, added to the forbidden set only for this test, instead of `systemctl`/`schtasks` --
    the point is to prove the *routing*, not to re-test name matching, and a regression here
    (the old `popen=subprocess.Popen` capture) would otherwise try to exec a nonexistent
    program rather than a real one."""
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    monkeypatch.setattr(conftest_module, "_FORBIDDEN_PROGRAMS", {"fridgesheet-guard-test-sentinel"})
    monkeypatch.setattr(opener.shutil, "which", lambda n: "fridgesheet-guard-test-sentinel" if n == "evince" else None)
    with pytest.raises(RuntimeError, match="fridgesheet-guard-test-sentinel"):
        opener.open_file(tmp_path / "s.pdf")


def test_open_text_default_popen_is_resolved_at_call_time_not_import_time(monkeypatch, tmp_path):
    """Same as above for `open_text`, and for the Windows branch, which calls `popen`
    directly with `notepad.exe` rather than going through `shutil.which` first."""
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    monkeypatch.setattr(conftest_module, "_FORBIDDEN_PROGRAMS", {"notepad"})   # _argv0 strips ".exe"
    with pytest.raises(RuntimeError, match="notepad"):
        opener.open_text(tmp_path / "settings.toml")


# --- Fix round 1, finding 2: `guarded_popen` only inspected `args`, so `Popen`'s
# `executable=` override -- which is what actually runs, regardless of what argv[0] merely
# says -- slipped past unchecked. Fixed by extracting `_blocked_program(args, executable)`,
# which `executable` wins when given. These are pure unit tests against that helper: no
# `Popen`, real or guarded, is ever constructed, so there is no way for them to reach a real
# binary even if the logic under test were wrong.

def test_blocked_program_prefers_executable_over_a_harmless_argv0():
    assert conftest_module._blocked_program(["totally-not-systemctl"], executable="systemctl") == "systemctl"


def test_blocked_program_matches_executable_by_absolute_path_and_case():
    assert conftest_module._blocked_program(["placeholder"], executable="/usr/bin/SYSTEMCTL") == "systemctl"


def test_blocked_program_falls_back_to_argv0_when_no_executable_given():
    assert conftest_module._blocked_program(["systemctl", "--user"], executable=None) == "systemctl"
    assert conftest_module._blocked_program(["echo", "hi"], executable=None) is None


def test_blocked_program_allows_a_harmless_executable_override():
    assert conftest_module._blocked_program(["systemctl"], executable="/usr/bin/echo") is None


# --- Fix round 2: `_argv0` branched only on `bytes`/`str`, so a `pathlib.Path` -- a shape
# `Popen`'s `executable=` genuinely accepts -- fell through to `elif args: first = args[0]`,
# and a bare `Path` is truthy but not subscriptable: `TypeError`, not a block. It failed
# closed (the exception aborts before `real_popen` is reached), but it would also crash on a
# legitimate `executable=Path(...)` call that names nothing forbidden. Both are plain
# `_blocked_program` calls with no `Popen` involved, so nothing here can reach a real binary.

# --- Fix round 3, minor 13: `guarded_popen` read `executable` out of `kwargs` only, but
# `Popen(args, bufsize, executable, ...)` takes it positionally too, so
# `Popen(["placeholder"], -1, "/usr/bin/systemctl")` reached the real binary. This one does
# construct a guarded `Popen` (that is the point -- `_blocked_program` was always right; the
# call into it was not), and it names a sentinel program rather than `systemctl`, so a
# regression fails by trying to exec something that does not exist rather than the real thing.

def test_a_positionally_passed_executable_is_blocked(monkeypatch):
    monkeypatch.setattr(conftest_module, "_FORBIDDEN_PROGRAMS", {"fridgesheet-guard-test-sentinel"})
    with pytest.raises(RuntimeError, match="fridgesheet-guard-test-sentinel"):
        subprocess.Popen(["placeholder"], -1, "/usr/bin/fridgesheet-guard-test-sentinel")


def test_a_positionally_passed_harmless_executable_still_runs(monkeypatch):
    monkeypatch.setattr(conftest_module, "_FORBIDDEN_PROGRAMS", {"fridgesheet-guard-test-sentinel"})
    # `sys.executable` rather than a fixed path: the Windows CI leg has no `/bin/echo`, and this
    # test is about the guard reading `executable` from the third *positional* slot, not about
    # which program happens to sit there.
    p = subprocess.Popen(["placeholder-argv0", "-c", "print('hi-from-positional')"], -1, sys.executable,
                         stdout=subprocess.PIPE, text=True)
    out, _ = p.communicate()
    assert "hi-from-positional" in out          # argv[0] is only a label; sys.executable is what ran


def test_blocked_program_matches_a_path_typed_executable():
    assert conftest_module._blocked_program(["placeholder"], executable=Path("/usr/bin/systemctl")) == "systemctl"


def test_blocked_program_allows_a_harmless_path_typed_executable():
    assert conftest_module._blocked_program(["systemctl"], executable=Path("/usr/bin/echo")) is None


def test_the_suite_never_sees_a_real_legacy_home(monkeypatch):
    """`load_settings` moves the old data directory on first sight. The suite must never do that
    to the developer's own home: the override set before the package is imported keeps the
    default home in tmp, and the autouse fixture makes the legacy lookup answer None even when
    a test clears the override to assert on a default."""
    import conftest as c
    from pathlib import Path
    from fridgesheet import config, migrate
    assert Path(c.TEST_HOME).name.startswith("fridgesheet-tests-")     # set before the package imported
    assert config.DEFAULT_HOME != Path.home() / ".fridgesheet"           # and every test's home is tmp
    assert migrate.legacy_home(is_windows=False) is None and migrate.legacy_home(is_windows=True) is None
    monkeypatch.delenv("FRIDGESHEET_HOME", raising=False)
    assert migrate.legacy_home(is_windows=False) is None       # the fixture, not just the env

"""The frozen-exe entry point: environment, app.log, the browser launch, and CLI dispatch.

Ported from the deleted `tests/test_app_main.py` when the tkinter window was retired: the
environment, logging and dispatch tests are unchanged in substance; the window tests are
replaced by the launch tests (make sure the server runs, then open the browser).
"""
from __future__ import annotations

import importlib
import logging
import logging.handlers
import os
import pathlib
import sys
from pathlib import Path

import pytest

from fridgesheet import cli, config
from fridgesheet.web import __main__ as entry

APP_LOG = entry.APP_LOG


@pytest.fixture(autouse=True)
def _clean_root_logger():
    root = logging.getLogger()
    before = list(root.handlers)
    before_level = root.level
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(before_level)


def test_frozen_environment_points_playwright_at_the_bundle(monkeypatch, tmp_path):
    env = {}
    monkeypatch.delattr(sys, "frozen", raising=False)
    entry.frozen_environment(environ=env, executable=str(tmp_path / "FridgeSheet.exe"))
    assert env == {}
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    entry.frozen_environment(environ=env, executable=str(tmp_path / "FridgeSheet.exe"))
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(tmp_path / "ms-playwright")
    env["PLAYWRIGHT_BROWSERS_PATH"] = "custom"
    entry.frozen_environment(environ=env, executable=str(tmp_path / "FridgeSheet.exe"))
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == "custom"


def test_setup_logging_writes_app_log_and_skips_stderr_when_absent(tmp_path):
    entry.setup_logging(tmp_path, stderr=None)
    entry.setup_logging(tmp_path, stderr=None)          # idempotent
    root = logging.getLogger()
    files = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(files) == 1 and files[0].baseFilename == str(tmp_path / APP_LOG)
    # `type(h) is StreamHandler` (not isinstance) so pytest's own root-logger instrumentation
    # (LogCaptureHandler etc., all StreamHandler subclasses) doesn't trip this assertion.
    assert not any(type(h) is logging.StreamHandler for h in root.handlers)
    logging.getLogger("fridgesheet.test").info("hello app.log")
    for h in files:
        h.flush()
    assert "hello app.log" in (tmp_path / APP_LOG).read_text(encoding="utf-8")


def test_setup_logging_is_idempotent_across_path_spellings(tmp_path):
    entry.setup_logging(tmp_path, stderr=None)
    entry.setup_logging(tmp_path / ".", stderr=None)
    if os.name != "nt":
        entry.setup_logging(Path(str(tmp_path) + "/"), stderr=None)
    root = logging.getLogger()
    files = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(files) == 1


def _opens(url, opener, **kw):
    """A stand-in for server._wait_and_open that finds the server: open, and say so."""
    opener(url)
    return True


def test_launch_opens_the_browser_when_the_server_answers(tmp_path):
    s = config.Settings(home=tmp_path)
    opened, spawned = [], []
    rc = entry.launch(s, answers=lambda h, p: True, spawn=lambda argv: spawned.append(argv),
                      opener=opened.append, wait=_opens)
    assert rc == 0 and spawned == [] and opened == ["http://127.0.0.1:8433/"]


def test_launch_starts_a_detached_server_then_opens(tmp_path, monkeypatch):
    s = config.Settings(home=tmp_path)
    opened, spawned = [], []
    rc = entry.launch(s, answers=lambda h, p: False, spawn=lambda argv: spawned.append(argv),
                      opener=opened.append, wait=_opens)
    assert rc == 0 and spawned == [[sys.executable, "-m", "fridgesheet.cli", "web", "--no-browser"]]
    assert opened == ["http://127.0.0.1:8433/"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\App\FridgeSheet.exe")
    spawned.clear()
    entry.launch(s, answers=lambda h, p: False, spawn=lambda argv: spawned.append(argv),
                 opener=opened.append, wait=_opens)
    assert spawned == [[r"C:\App\FridgeSheet.exe", "web", "--no-browser"]]


def test_launch_respects_no_browser_env(tmp_path, monkeypatch):
    """The smoke test's no-args launch: still wait for the server, open nothing."""
    monkeypatch.setenv("FRIDGESHEET_WEB_NO_BROWSER", "1")
    opened, waited = [], []

    def wait(url, opener, **kw):
        waited.append(opener(url))
        return True

    rc = entry.launch(config.Settings(home=tmp_path), answers=lambda h, p: True, spawn=lambda argv: None,
                      opener=opened.append, wait=wait)
    assert rc == 0 and opened == [] and waited == [None]


def test_launch_returns_1_and_says_so_when_the_server_never_answers(tmp_path, caplog):
    """The shortcut's commonest failure -- the spawned server dies on a stale lock -- used to
    write not one line anywhere, while docs/windows.md sends the parent to app.log."""
    spawned = []
    with caplog.at_level(logging.ERROR, logger="fridgesheet.web"):
        rc = entry.launch(config.Settings(home=tmp_path), answers=lambda h, p: False,
                          spawn=lambda argv: spawned.append(argv), opener=lambda u: None,
                          wait=lambda url, opener, **kw: False)
    assert rc == 1 and spawned != []
    assert "did not answer at http://127.0.0.1:8433/" in caplog.text and "30 seconds" in caplog.text


def test_launch_returns_1_with_no_browser_too(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("FRIDGESHEET_WEB_NO_BROWSER", "1")
    with caplog.at_level(logging.ERROR, logger="fridgesheet.web"):
        rc = entry.launch(config.Settings(home=tmp_path), answers=lambda h, p: False, spawn=lambda argv: None,
                          opener=lambda u: None, wait=lambda url, opener, **kw: False)
    assert rc == 1 and "did not answer" in caplog.text


def test_main_without_args_launches(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    called = {}
    monkeypatch.setattr(entry, "launch", lambda s, **kw: called.setdefault("ok", 0))
    monkeypatch.setattr(entry, "load_settings", lambda: object())
    assert entry.main([]) == 0 and called == {"ok": 0}


def test_main_stays_off_the_owners_real_home_with_no_local_patch(monkeypatch, tmp_path):
    """No `monkeypatch.setattr(..., "DEFAULT_HOME", ...)` anywhere in this test -- that is the
    point. `setup_logging` used to read a `DEFAULT_HOME` bound into `entry`'s own namespace at
    import time, which the conftest.py autouse fixture (it patches `config.DEFAULT_HOME`) could
    never reach; a test that forgot the local patch would `mkdir` the owner's real
    ~/.fridgesheet. Now `main()` reads `config.DEFAULT_HOME` live, so the autouse fixture alone
    is enough (#35 fix round 2)."""
    real_home = Path.home() / ".fridgesheet"
    before = real_home.stat() if real_home.exists() else None

    monkeypatch.setattr(entry, "launch", lambda s, **kw: 0)
    monkeypatch.setattr(entry, "load_settings", lambda: object())
    assert entry.main([]) == 0

    # The autouse fixture points config.DEFAULT_HOME at this test's own tmp_path, not the real
    # home, and setup_logging's mkdir landed there instead.
    assert config.DEFAULT_HOME != real_home
    assert config.DEFAULT_HOME.is_relative_to(tmp_path)
    assert (config.DEFAULT_HOME / APP_LOG).exists()

    after = real_home.stat() if real_home.exists() else None
    assert (before is None) == (after is None)          # not newly created
    if before is not None:
        assert before.st_mtime == after.st_mtime         # and not touched either


def test_main_logs_and_returns_1_when_the_launch_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(entry, "load_settings", lambda: object())

    def boom(settings, **kw):
        raise RuntimeError("port in use")

    monkeypatch.setattr(entry, "launch", boom)
    assert entry.main([]) == 1
    for h in logging.getLogger().handlers:
        h.flush()
    text = (tmp_path / APP_LOG).read_text(encoding="utf-8")
    assert "the app could not start" in text and "port in use" in text


def test_main_with_args_runs_the_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    seen = {}

    def fake_cli_main(argv):
        seen["argv"] = argv
        raise SystemExit(3)

    monkeypatch.setattr(cli, "main", fake_cli_main)
    assert entry.main(["run", "open-work", "--dry-run"]) == 3
    assert seen["argv"] == ["run", "open-work", "--dry-run"]


def test_main_translates_a_string_exit_into_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)

    def fake_cli_main(argv):
        raise SystemExit("bad flag")

    monkeypatch.setattr(cli, "main", fake_cli_main)
    assert entry.main(["x"]) == 1
    assert "bad flag" in capsys.readouterr().err


@pytest.mark.parametrize("cmd", ["login", "set-credentials"])
def test_terminal_only_commands_are_refused_without_stdin(monkeypatch, tmp_path, cmd):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)
    monkeypatch.setattr(sys, "stdin", None)
    called = []
    monkeypatch.setattr(cli, "main", lambda argv: called.append(argv))
    assert entry.main([cmd]) == 2 and called == []
    for h in logging.getLogger().handlers:
        h.flush()
    assert "needs a terminal" in (tmp_path / APP_LOG).read_text(encoding="utf-8")


def test_cli_exception_is_logged_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DEFAULT_HOME", tmp_path)

    def fake_cli_main(argv):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "main", fake_cli_main)
    assert entry.main(["run", "open-work"]) == 1
    for h in logging.getLogger().handlers:
        h.flush()
    text = (tmp_path / APP_LOG).read_text(encoding="utf-8")
    assert "run failed" in text and "boom" in text


def test_entry_file_runs_as_a_script(tmp_path):
    """PyInstaller executes __main__.py as a top-level script, not as a package module."""
    import subprocess
    repo = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(repo), "FRIDGESHEET_HOME": str(tmp_path)}
    r = subprocess.run([sys.executable, str(repo / "fridgesheet" / "web" / "__main__.py"), "reports"],
                       capture_output=True, text=True, env=env, cwd=str(tmp_path), timeout=120)
    assert r.returncode == 0, r.stderr
    assert "open-work" in r.stdout


def test_app_command_and_package_are_gone():
    with pytest.raises(SystemExit):
        cli.main(["app"])
    # No source left in it; a stale __pycache__ an upgrade left behind is not the package (#4).
    assert not list((pathlib.Path(cli.__file__).parent / "app").glob("*.py"))
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fridgesheet.app")

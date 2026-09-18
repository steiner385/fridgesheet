"""Entry point of the frozen Windows executable, and of `python -m fridgesheet.web`.

No arguments makes sure the server is running and opens the browser (spec section 10): if the
port already answers as this app, just open it; otherwise start `web --no-browser` detached
and open once it answers. Anything else is the ordinary CLI, so the scheduled task's
`FridgeSheet.exe run open-work`, the logon task's `FridgeSheet.exe web --no-browser` and the
uninstaller's `schedule remove` / `service remove` all come from the same binary. A windowed
exe has no stdout or stderr, so logging goes to <home>/app.log; stderr gets a copy only when
it exists.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from fridgesheet import config
from fridgesheet.config import Settings, load_settings
from fridgesheet.web import server

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
TERMINAL_ONLY = ("login", "set-credentials")
# Spelled out rather than imported from web.actions: setup_logging runs before anything else,
# and actions pulls in the runner, Playwright and the host adapters.
APP_LOG = "app.log"


def frozen_environment(environ=os.environ, executable: str | None = None) -> None:
    """Point Playwright at the Chromium the installer puts next to the exe."""
    if getattr(sys, "frozen", False):
        exe = Path(executable or sys.executable)
        environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(exe.parent / "ms-playwright"))


def setup_logging(home: Path, stderr=sys.stderr) -> None:
    home.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    path = os.path.abspath(str(home / APP_LOG))
    target = os.path.normcase(path)
    if any(isinstance(h, logging.handlers.RotatingFileHandler) and os.path.normcase(os.path.abspath(h.baseFilename)) == target
           for h in root.handlers):
        return
    fmt = logging.Formatter(_FORMAT)
    fh = logging.handlers.RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if stderr is not None:
        sh = logging.StreamHandler(stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)


def _server_argv() -> list[str]:
    """The command that runs the server. Frozen, `sys.executable` is FridgeSheet.exe itself."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "web", "--no-browser"]
    return [sys.executable, "-m", "fridgesheet.cli", "web", "--no-browser"]


def _spawn_detached(argv: list[str]) -> None:
    """Start the server so it outlives this process and shows no console window."""
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if sys.platform == "win32":                     # pragma: no cover - exercised on the Windows leg
        kw["creationflags"] = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                               | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        kw["start_new_session"] = True
    subprocess.Popen(argv, **kw)


TRIES, INTERVAL = 150, 0.2


def launch(settings: Settings, *, answers=None, spawn=None, opener=None, wait=None) -> int:
    """Make sure the server answers, then open the browser at it.

    Non-zero when the server never answered: the spawned server writes its own reason to
    app.log (it has no stderr -- `_spawn_detached` gives it DEVNULL), and this adds the line
    that says the shortcut gave up. Silence here is what made the commonest first-run failure,
    a server that dies on a stale lock, leave no trace at all."""
    answers = answers or server.port_answers
    spawn = spawn or _spawn_detached
    opener = opener or webbrowser.open
    wait = wait or server._wait_and_open
    url = f"http://127.0.0.1:{settings.web_port}/"
    quiet = os.environ.get("FRIDGESHEET_WEB_NO_BROWSER") == "1"   # the smoke test: wait for the server, open nothing
    if not answers("127.0.0.1", settings.web_port):
        spawn(_server_argv())
    if not wait(url, (lambda u: None) if quiet else opener, answers=answers, tries=TRIES, interval=INTERVAL):
        logging.getLogger("fridgesheet.web").error(
            "the server did not answer at %s after %.0f seconds; see the lines above", url, TRIES * INTERVAL)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    frozen_environment()
    # The move from the old data directory comes first: setup_logging creates the new home
    # for app.log, and a home that already exists is one the move leaves alone -- on the
    # first real upgrade (graphy, 2026-09-18) that ordering left every note, flag and run
    # behind in the old data directory while the app started over in an empty folder.
    config.migrate_home_once()
    # `config.DEFAULT_HOME` read here, not imported by value: a value import binds a copy into
    # this module's own namespace at import time, so a test (or anything else) that redirects
    # `config.DEFAULT_HOME` afterwards would have no way to reach it (#35 fix round 2).
    setup_logging(config.DEFAULT_HOME)
    log = logging.getLogger("fridgesheet.web")
    if not argv:
        try:
            return launch(load_settings())
        except Exception:
            log.exception("the app could not start")
            return 1
    if argv[0] in TERMINAL_ONLY and sys.stdin is None:
        log.error("%s needs a terminal; use the Settings page instead", argv[0])
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
    except Exception:
        log.exception("%s failed", argv[0])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

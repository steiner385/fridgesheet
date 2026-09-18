"""`fridgesheet web`: run the server in the foreground, or hand off to the one already running.

One instance per home (spec section 15, risk 4): an exclusive kernel lock on a file beside
the database. If the port already answers /health as this app, the second start opens the
browser there and exits 0 -- that is what the desktop shortcut and `FridgeSheet.exe` with no
arguments do.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.request
import webbrowser
from dataclasses import replace
from pathlib import Path

if sys.platform == "win32":                       # pragma: no cover - exercised on the Windows leg
    import msvcrt
else:
    import fcntl

from ..config import Settings
from . import db
from .app import APP_NAME, create_app

LOCK_NAME = "web.lock"
#: Every refusal goes here as well as to stderr: the frozen exe has no stderr (the shortcut
#: spawns it with DEVNULL), and app.log is where docs/windows.md sends the parent to look.
log = logging.getLogger("fridgesheet.web")
# Windows locks a byte range and refuses every other handle's read of it, so lock a byte far
# past the pid text rather than byte 0: the pid stays readable while the server runs, as it is
# on Linux, where flock never blocks a reader. Locking beyond end-of-file is legal on Windows.
LOCK_BYTE = 1 << 20


def port_answers(host: str, port: int, timeout: float = 1.0) -> bool:
    """True when something on host:port is this app (GET /health says so)."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_NAME
    except Exception:
        return False


def _try_lock(fd: int) -> bool:
    """Take the kernel's exclusive lock on an open file, without waiting."""
    try:
        if sys.platform == "win32":               # pragma: no cover - exercised on the Windows leg
            os.lseek(fd, LOCK_BYTE, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    if sys.platform == "win32":                   # pragma: no cover - exercised on the Windows leg
        os.lseek(fd, LOCK_BYTE, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class WebLock:
    """An exclusive kernel lock on <home>/web.lock, held for the life of the process.

    The pid written inside is for a human reading the file; it is never trusted, because a
    pid tells you nothing after it has been reused. The kernel drops the lock however the
    process dies -- clean exit, SIGTERM, SIGKILL, power cut -- so a leftover file never
    keeps the next server out. A second lock on the same path fails even inside this
    process: the lock belongs to the open file description, and each `acquire` opens its own.
    """

    def __init__(self, path: Path):
        self.path, self.fd = path, None

    @property
    def held(self) -> bool:
        return self.fd is not None

    def acquire(self) -> bool:
        """True when we now hold the lock, False when anyone else does. Raises OSError when
        the file cannot be opened at all (an unwritable home)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        if not _try_lock(fd):
            os.close(fd)
            return False
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(os.getpid()).encode("ascii"))     # diagnostics only
        self.fd = fd
        return True

    def release(self) -> None:
        if self.fd is None:
            return
        fd, self.fd = self.fd, None
        try:
            _unlock(fd)
        finally:
            os.close(fd)
            self.path.unlink(missing_ok=True)


def _wait_and_open(url: str, opener, *, answers=port_answers, tries: int = 100, interval: float = 0.2) -> bool:
    """Open the browser once the server answers (called on a helper thread while uvicorn runs).

    True when it opened, False when the tries ran out -- the caller says so; giving up in
    silence is how a failed launch used to leave no trace anywhere."""
    host, port = url.split("//")[1].split("/")[0].split(":")
    for _ in range(tries):
        if answers(host, int(port)):
            opener(url)
            return True
        time.sleep(interval)
    return False


def _serve(app, host: str, port: int) -> None:
    import uvicorn
    # log_config=None leaves the root logger alone, so uvicorn's records propagate to
    # whatever the process already set up: app.log in the frozen exe, stderr from the CLI.
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False, log_config=None)


def run(settings: Settings, *, host: str | None = None, port: int | None = None, open_browser: bool = True,
        serve=None, opener=None, answers=None, wait_and_open=None) -> int:
    if host is not None or port is not None:
        # A `--host`/`--port` flag has to change what this process *answers to*, not just what
        # it binds: `same_origin_only`'s Host allowlist (app.py) reads `settings.bind_host` and
        # `settings.web_port` off the very Settings object handed to `create_app` below. Fold
        # the override into a copy of `settings` before that call -- the same way
        # FRIDGESHEET_WEB_HOST/FRIDGESHEET_WEB_PORT already do it via `web_host_explicit` -- so the
        # middleware's idea of "the addresses this app is actually served on" cannot fall out
        # of sync with the address uvicorn is actually given below.
        settings = replace(settings, web_host=host if host is not None else settings.bind_host,
                            web_host_explicit=True, web_port=port if port is not None else settings.web_port)
    host = host or settings.bind_host
    port = port or settings.web_port
    serve = serve or _serve
    opener = opener or webbrowser.open
    answers = answers or port_answers
    wait_and_open = wait_and_open or _wait_and_open
    local = f"http://127.0.0.1:{port}/"
    if answers("127.0.0.1", port):
        if open_browser:
            opener(local)
        print(f"Fridge Sheet is already running at {local}", file=sys.stderr)
        return 0
    lock = WebLock(settings.home / LOCK_NAME)
    try:
        got_lock = lock.acquire()
    except OSError as e:
        msg = f"cannot open the lock file {settings.home / LOCK_NAME}: {e}"
        log.error("%s", msg)
        print(msg, file=sys.stderr)
        return 1
    if not got_lock:
        msg = (f"another server holds {settings.home / LOCK_NAME} but {local} does not answer; "
               f"stop it or delete the lock file")
        log.error("%s", msg)
        print(msg, file=sys.stderr)
        return 1
    try:
        db.open_db(settings.home).close()             # create and migrate before the first request
        app = create_app(settings, worker=True)
        if open_browser:
            threading.Thread(target=wait_and_open, args=(local, opener), kwargs={"answers": answers}, daemon=True).start()
        serve(app, host, port)
        return 0
    finally:
        # Tidiness, not correctness: uvicorn re-raises SIGTERM/SIGINT after its own shutdown,
        # so on a real stop the process dies inside serve() and never gets here. The kernel
        # releases the lock either way; only the leftover file needs this.
        lock.release()

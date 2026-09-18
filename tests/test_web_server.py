"""Starting the server: one instance per home, open the browser at the running one, the lock file."""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from fridgesheet import config
from fridgesheet.web import server

REPO = str(Path(__file__).resolve().parents[1])


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_port_answers_is_false_on_a_closed_port():
    assert server.port_answers("127.0.0.1", _free_port(), timeout=0.2) is False


def test_lock_is_exclusive_while_held_and_free_after_release(tmp_path):
    lock = server.WebLock(tmp_path / "web.lock")
    assert lock.acquire() is True
    assert (tmp_path / "web.lock").read_text() == str(os.getpid())        # the pid, for a human
    assert server.WebLock(tmp_path / "web.lock").acquire() is False       # held: nobody else gets in
    lock.release()
    second = server.WebLock(tmp_path / "web.lock")
    assert second.acquire() is True                                       # released: free again
    second.release()
    (tmp_path / "web.lock").write_text("999999999")                       # a leftover file, no kernel lock
    third = server.WebLock(tmp_path / "web.lock")
    assert third.acquire() is True                                        # a dead pid inside stops nobody
    third.release()


def test_a_killed_holder_frees_the_lock(tmp_path):
    """The kernel lock, not the pid inside, is what keeps a second server out -- so a server
    killed outright (uvicorn re-raises SIGTERM; a reboot is worse) leaves the lock takeable."""
    path = tmp_path / "web.lock"
    code = ("import sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "from pathlib import Path\n"
            "from fridgesheet.web import server\n"
            "assert server.WebLock(Path(sys.argv[2])).acquire() is True\n"
            "time.sleep(60)\n")
    child = subprocess.Popen([sys.executable, "-c", code, REPO, str(path)],
                             env={**os.environ, "PYTHONPATH": REPO})
    try:
        for _ in range(200):                                              # wait for the child to hold it
            if path.exists() and path.read_text().strip():
                break
            time.sleep(0.05)
        assert path.read_text().strip() == str(child.pid)
        assert server.WebLock(path).acquire() is False                    # another process holds it
    finally:
        child.kill()
        child.wait(timeout=10)
    lock = server.WebLock(path)
    assert lock.acquire() is True                                         # killed: the kernel let go
    lock.release()


def test_run_opens_the_browser_at_a_running_instance_instead_of_serving(tmp_path):
    s = config.Settings(home=tmp_path)
    opened, served = [], []
    rc = server.run(s, open_browser=True, serve=lambda *a, **k: served.append(a), opener=opened.append, answers=lambda h, p: True)
    assert rc == 0 and served == [] and opened == ["http://127.0.0.1:8433/"]


def test_run_serves_and_hands_the_browser_to_the_waiter(tmp_path):
    s = config.Settings(home=tmp_path)
    s.web_port = 8500
    opened, served, waited = [], [], []

    def wait_and_open(url, opener, **kw):
        waited.append(url)
        opener(url)

    rc = server.run(s, serve=lambda app, host, port: served.append((host, port)), opener=opened.append,
                    answers=lambda h, p: False, wait_and_open=wait_and_open)
    assert rc == 0 and served == [("127.0.0.1", 8500)] and waited == opened == ["http://127.0.0.1:8500/"]
    assert not (tmp_path / "web.lock").exists()                           # released on exit
    assert (tmp_path / "fridgesheet.db").exists()                              # created and migrated before serving


def test_wait_and_open_opens_once_the_port_answers():
    calls = iter([False, False, True, True])
    opened = []
    assert server._wait_and_open("http://127.0.0.1:8500/", opened.append, answers=lambda h, p: next(calls), interval=0) is True
    assert opened == ["http://127.0.0.1:8500/"]
    opened.clear()
    # False, not None: the caller (web.__main__.launch) is what turns giving up into an
    # app.log line and a non-zero exit, instead of the silence this used to be.
    assert server._wait_and_open("http://127.0.0.1:8500/", opened.append, answers=lambda h, p: False, tries=3, interval=0) is False
    assert opened == []


def test_run_refuses_when_another_instance_holds_the_lock_and_the_port_is_silent(tmp_path, capsys, caplog):
    """Also logged, not only printed: spawned by the shortcut this process has no stderr, and
    app.log is where docs/windows.md sends the parent to read why nothing opened."""
    s = config.Settings(home=tmp_path)
    lock = server.WebLock(tmp_path / "web.lock")
    lock.acquire()
    try:
        with caplog.at_level(logging.ERROR, logger="fridgesheet.web"):
            rc = server.run(s, serve=lambda *a, **k: None, opener=lambda u: None, answers=lambda h, p: False)
    finally:
        lock.release()
    assert rc == 1 and "web.lock" in capsys.readouterr().err
    assert "web.lock" in caplog.text and "does not answer" in caplog.text


def test_run_reports_an_unopenable_lock_file_instead_of_a_traceback(tmp_path, capsys, caplog):
    s = config.Settings(home=tmp_path)
    (tmp_path / "web.lock").mkdir()                   # stands in for a permission problem
    with caplog.at_level(logging.ERROR, logger="fridgesheet.web"):
        rc = server.run(s, serve=lambda *a, **k: None, opener=lambda u: None, answers=lambda h, p: False)
    assert rc == 1
    err = capsys.readouterr().err
    assert "web.lock" in err and len(err.strip().splitlines()) == 1
    assert "cannot open the lock file" in caplog.text


def test_no_browser_flag(tmp_path):
    s = config.Settings(home=tmp_path)
    opened = []
    rc = server.run(s, open_browser=False, serve=lambda *a, **k: None, opener=opened.append, answers=lambda h, p: False)
    assert rc == 0 and opened == []


def test_lan_binding_uses_the_machine_address_in_the_browser_url(tmp_path):
    s = config.Settings(home=tmp_path)
    s.web_allow_lan = True
    opened = []
    server.run(s, serve=lambda *a, **k: None, opener=opened.append, answers=lambda h, p: True)
    assert opened == ["http://127.0.0.1:8433/"]      # the browser on this machine still uses loopback


def test_a_port_flag_reaches_the_middleware_not_just_uvicorn(tmp_path):
    """`fridgesheet web --port 9000` used to leave `settings.web_port` at its default (8433)
    while uvicorn bound 9000, so `same_origin_only`'s Host allowlist (app.py) still expected
    8433 and refused every request -- reads and writes alike -- from the user's own browser,
    the exact lockout a reviewer proved against a live server. Prove the `app` object `run`
    hands to `serve` is the one that actually answers to the overridden port, not the one
    `settings` started with."""
    s = config.Settings(home=tmp_path)
    apps = []
    rc = server.run(s, port=9000, serve=lambda app, host, port: apps.append(app),
                     opener=lambda u: None, answers=lambda h, p: False)
    assert rc == 0
    (app,) = apps
    assert app.state.fridgesheet.settings.web_port == 9000
    c = TestClient(app, headers={"host": "127.0.0.1:9000"})
    assert c.get("/").status_code == 200
    assert c.post("/notes", data={"target_type": "item", "target_id": 1, "body": "x"}).status_code != 403


def test_a_host_flag_reaches_the_middleware_too(tmp_path):
    """Same bug, the other flag: `--host` must also land in `settings` before `create_app`,
    the same way `FRIDGESHEET_WEB_HOST` already does (`web_host_explicit`)."""
    s = config.Settings(home=tmp_path)
    apps = []
    rc = server.run(s, host="192.168.1.50", serve=lambda app, host, port: apps.append(app),
                     opener=lambda u: None, answers=lambda h, p: False)
    assert rc == 0
    (app,) = apps
    assert (app.state.fridgesheet.settings.web_host, app.state.fridgesheet.settings.web_host_explicit) == ("192.168.1.50", True)
    c = TestClient(app, headers={"host": "192.168.1.50:8433"})
    assert c.get("/").status_code == 200

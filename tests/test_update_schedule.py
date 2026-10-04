"""Checking for, and installing, a new Fridge Sheet on a schedule (2026-10-04): the clock asks
GitHub every `[web] update_check_hours` (default 1), and `[web] update_mode` says what a new
release does -- a badge in the header (notify), a bar asking a grown-up to install it (prompt),
or an install at once (install, Windows only, turned on with the update PIN)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from fridgesheet import config, host
from fridgesheet.host import selfupdate
from fridgesheet.web import clock as clockmod, db, updatepin, updates
from tests.web_fixtures import LOCAL_HOST_HEADERS, NOW, app_for, seed

TZ = ZoneInfo("America/New_York")
T0 = datetime(2026, 10, 4, 14, 0, tzinfo=TZ)
DIGEST = "sha256:" + "a" * 64


@pytest.fixture(autouse=True)
def _installed_version(monkeypatch):
    monkeypatch.setattr(updates, "current_version", lambda: "0.3.1")


def release(tag="v0.9.0"):
    body = {"tag_name": tag, "html_url": f"https://github.com/x/releases/tag/{tag}",
            "assets": [{"name": f"FridgeSheet-Setup-{tag[1:]}.exe", "digest": DIGEST, "size": 1000,
                        "browser_download_url": f"https://github.com/x/releases/download/{tag}/FridgeSheet-Setup-{tag[1:]}.exe"}]}
    return lambda url: json.dumps(body).encode()


# --- config -------------------------------------------------------------------------------

def _settings(web: dict) -> config.Settings:
    s = config.Settings()
    config.settings_from_doc({"web": web}, s)
    return s


def test_the_defaults_are_hourly_and_a_badge():
    s = config.Settings()
    assert s.web_update_check_hours == 1 and s.web_update_mode == "notify"


def test_the_interval_and_the_mode_read_from_config():
    s = _settings({"update_check_hours": 6, "update_mode": "install"})
    assert s.web_update_check_hours == 6 and s.web_update_mode == "install"


@pytest.mark.parametrize("web", [{"update_check_hours": 0}, {"update_check_hours": 25}, {"update_check_hours": "x"},
                                 {"update_check_hours": True}, {"update_mode": "sometimes"}])
def test_a_bad_interval_or_mode_keeps_the_default(web):
    """As `[web] check_updates` does (`config._as_bool`): a hand edit gone wrong is a warning,
    never an app that will not start."""
    s = _settings(web)
    assert s.web_update_check_hours == 1 and s.web_update_mode == "notify"


# --- the check's own interval ---------------------------------------------------------------

def test_a_good_answer_is_kept_for_the_interval(tmp_path):
    seed(tmp_path).close()
    state = app_for(tmp_path).app.state.fridgesheet
    calls = []
    def fetch(url):
        calls.append(url); return release()(url)
    first = updates.check(state, now=NOW, fetch=fetch)
    assert updates.check(state, now=NOW + timedelta(minutes=59), fetch=fetch) is first
    assert updates.check(state, now=NOW + timedelta(minutes=61), fetch=fetch) is not first
    state.settings.web_update_check_hours = 6
    assert len(calls) == 2
    kept = updates.check(state, now=NOW + timedelta(hours=3), fetch=fetch)
    assert len(calls) == 2 and kept.available


# --- the clock ------------------------------------------------------------------------------

class FakeWorker:
    def __init__(self, busy=False):
        self.busy, self.submitted = busy, []

    def submit(self, kind, **params):
        if self.busy:
            return None
        self.submitted.append(kind)
        return object()


def _clock(home, web: dict, fetch, worker):
    config.save_config_doc(home / "config.toml", {"web": web})
    db.open_db(home).close()
    state = SimpleNamespace(home=home, extra={"update_fetch": fetch})
    return clockmod.Clock(state, submit=worker.submit), state


def test_the_clock_checks_on_the_interval_and_only_tells_in_notify_mode(tmp_path):
    calls = []
    def fetch(url):
        calls.append(url); return release()(url)
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": "notify"}, fetch, w)
    c.tick(T0)
    assert len(calls) == 1 and state.extra[updates.CACHE_KEY].available     # the header's badge has its answer
    c.tick(T0 + timedelta(minutes=1))
    assert len(calls) == 1                                                  # not every minute
    c.tick(T0 + timedelta(minutes=61))
    assert len(calls) == 2 and w.submitted == []


def test_checks_turned_off_ask_nothing(tmp_path):
    calls = []
    w = FakeWorker()
    c, state = _clock(tmp_path, {"check_updates": False, "update_mode": "install"}, lambda u: calls.append(u) or b"{}", w)
    c.tick(T0)
    assert calls == [] and w.submitted == []


def test_install_mode_starts_the_update_once_per_version(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    fetch = {"f": release("v0.9.0")}
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": "install"}, lambda url: fetch["f"](url), w)
    c.tick(T0)
    assert w.submitted == ["update"]
    c.tick(T0 + timedelta(minutes=61))            # still 0.3.1 running: the install did not take
    assert w.submitted == ["update"]              # tried once, not every hour
    fetch["f"] = release("v0.9.1")
    c.tick(T0 + timedelta(minutes=122))
    assert w.submitted == ["update", "update"]    # a newer release gets its own try


def test_a_busy_worker_is_tried_again_at_the_next_tick(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    w = FakeWorker(busy=True)
    c, state = _clock(tmp_path, {"update_mode": "install"}, release(), w)
    c.tick(T0)
    assert w.submitted == []
    w.busy = False
    c.tick(T0 + timedelta(minutes=1))             # the cached answer, no new request
    assert w.submitted == ["update"]


def test_an_update_already_tried_before_a_restart_is_not_tried_again(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    selfupdate.write_pending(tmp_path, selfupdate.Pending("0.3.1", "0.9.0", T0.isoformat(), "x.exe", "x.log"))
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": "install"}, release(), w)
    c.tick(T0)
    assert w.submitted == []


@pytest.mark.parametrize("mode", ["notify", "prompt"])
def test_only_install_mode_installs(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": mode}, release(), w)
    c.tick(T0)
    assert w.submitted == []


def test_install_mode_never_installs_off_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": "install"}, release(), w)
    c.tick(T0)
    assert w.submitted == []


def test_a_release_with_no_installer_is_not_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    body = {"tag_name": "v0.9.0", "html_url": "https://github.com/x/releases/tag/v0.9.0", "assets": []}
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": "install"}, lambda url: json.dumps(body).encode(), w)
    c.tick(T0)
    assert w.submitted == []


def test_a_scheduled_job_in_the_same_minute_goes_first(tmp_path, monkeypatch):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    w = FakeWorker()
    c, state = _clock(tmp_path, {"update_mode": "install"}, release(), w)
    monkeypatch.setattr(clockmod.Clock, "_tick_schedules", lambda self, now: "data-refresh")
    c.tick(T0)
    assert w.submitted == []


# --- the header -----------------------------------------------------------------------------

def _app(tmp_path, mode):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    state = c.app.state.fridgesheet
    state.settings.web_update_mode = mode
    updates.check(state, now=NOW, fetch=release())
    return c


def test_notify_mode_is_the_badge_alone(tmp_path):
    body = _app(tmp_path, "notify").get("/kids/Alex").text
    assert "Fridge Sheet 0.9.0 is available" in body and 'class="update-prompt"' not in body


def test_prompt_mode_asks_a_grown_up_to_install(tmp_path):
    body = _app(tmp_path, "prompt").get("/kids/Alex").text
    assert '<p class="update-prompt">' in body
    bar = body[body.index('<p class="update-prompt">'):]
    bar = bar[:bar.index("</p>")]
    assert "Fridge Sheet 0.9.0 is available" in bar and 'href="/settings#update-action"' in bar and ">Install it</a>" in bar
    assert body.count("is available") == 1                     # the bar, not the badge beside it as well


def test_a_kids_own_phone_sees_neither(tmp_path):
    c = _app(tmp_path, "prompt")
    c.post("/who", data={"who": "Alex"})
    body = c.get("/kids/Alex/plan").text
    assert "is available" not in body and "update-prompt" not in body


# --- turning it on in Settings --------------------------------------------------------------

FORM = {"username": "parent@example.org", "password": "hunter2", "printer": "", "days_ahead": "14",
        "overdue_days": "14", "nicknames": "", "archive": "", "port": "8433", "check_updates": "on"}
HEADERS = {**LOCAL_HOST_HEADERS, "Origin": "http://127.0.0.1"}


def _settings_client(tmp_path, monkeypatch, pin: str | None = "4321"):
    monkeypatch.setattr(host, "IS_WINDOWS", True)
    seed(tmp_path).close()
    if pin:
        config.save_config_doc(tmp_path / "config.toml", {"web": {"update_pin_hash": updatepin.hash_pin(pin)}})
    c = app_for(tmp_path)
    state = c.app.state.fridgesheet
    state.reload()

    class Cred:
        def write(self, username, password): pass
    state.extra["credstore"] = Cred()
    return c


def _web(tmp_path):
    return config.load_config_doc(tmp_path / "config.toml").get("web", {})


def test_the_interval_and_a_quiet_mode_save_without_a_pin(tmp_path, monkeypatch):
    c = _settings_client(tmp_path, monkeypatch)
    r = c.post("/settings", data={**FORM, "update_check_hours": "6", "update_mode": "prompt"}, headers=HEADERS)
    assert r.status_code == 200
    assert _web(tmp_path)["update_check_hours"] == 6 and _web(tmp_path)["update_mode"] == "prompt"


def test_automatic_install_needs_the_update_pin(tmp_path, monkeypatch):
    c = _settings_client(tmp_path, monkeypatch)
    r = c.post("/settings", data={**FORM, "update_check_hours": "1", "update_mode": "install"}, headers=HEADERS)
    assert "Enter the update PIN to turn on automatic install." in r.text and _web(tmp_path).get("update_mode") != "install"
    r = c.post("/settings", data={**FORM, "update_check_hours": "1", "update_mode": "install", "install_pin": "0000"}, headers=HEADERS)
    assert "That PIN is not right." in r.text and _web(tmp_path).get("update_mode") != "install"
    r = c.post("/settings", data={**FORM, "update_check_hours": "1", "update_mode": "install", "install_pin": "4321"}, headers=HEADERS)
    assert _web(tmp_path)["update_mode"] == "install"
    # Once on, saving anything else does not ask again.
    r = c.post("/settings", data={**FORM, "update_check_hours": "2", "update_mode": "install"}, headers=HEADERS)
    assert _web(tmp_path)["update_mode"] == "install" and _web(tmp_path)["update_check_hours"] == 2


def test_with_no_pin_stored_the_new_one_typed_with_it_will_do(tmp_path, monkeypatch):
    c = _settings_client(tmp_path, monkeypatch, pin=None)
    r = c.post("/settings", data={**FORM, "update_check_hours": "1", "update_mode": "install"}, headers=HEADERS)
    assert "Set an update PIN to turn on automatic install." in r.text and _web(tmp_path).get("update_mode") != "install"
    c.post("/settings", data={**FORM, "update_check_hours": "1", "update_mode": "install", "update_pin": "2468"}, headers=HEADERS)
    assert _web(tmp_path)["update_mode"] == "install"


def test_automatic_install_is_not_offered_off_windows(tmp_path, monkeypatch):
    c = _settings_client(tmp_path, monkeypatch)
    monkeypatch.setattr(host, "IS_WINDOWS", False)
    r = c.post("/settings", data={**FORM, "update_check_hours": "1", "update_mode": "install", "install_pin": "4321"}, headers=HEADERS)
    assert "Automatic install is only for the Windows install." in r.text and _web(tmp_path).get("update_mode") != "install"
    page = c.get("/settings", headers=LOCAL_HOST_HEADERS).text
    assert 'name="update_mode" value="install"' in page and "disabled" in page[page.index('value="install"') - 80:page.index('value="install"') + 80]


def test_the_bar_waits_while_an_automatic_install_is_running(tmp_path):
    """Between the clock starting the install and the installer closing the app, the try is
    not a failure: the header says nothing more than the job's own badge."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    state = c.app.state.fridgesheet
    state.settings.web_update_mode = "install"
    u = updates.check(state, now=NOW, fetch=release())
    state.extra[updates.TRIED_KEY] = u.latest
    running = SimpleNamespace(kind="update", done=False)
    assert not updates.auto_install_failed(state, state.settings, u, current_job=running)
    finished = SimpleNamespace(kind="update", done=True)
    assert updates.auto_install_failed(state, state.settings, u, current_job=finished)
    assert updates.auto_install_failed(state, state.settings, u, current_job=None)

"""`web.updates`: notice a newer release, once a day, and only ever say so (never fetch it)."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from fridgesheet.web import updates
from web_fixtures import NOW, app_for, seed


@pytest.fixture(autouse=True)
def _installed_version(monkeypatch):
    """What these tests exercise is the comparison, the cache and the page -- not whether the
    venv running them has this distribution installed under its current name (a venv that
    still carries the pre-rename metadata answers "dev", which is never newer than
    anything)."""
    monkeypatch.setattr(updates, "current_version", lambda: "0.3.1")


def release(tag="v0.9.0", asset=True):
    body = {"tag_name": tag, "html_url": f"https://github.com/x/releases/tag/{tag}",
            "assets": [{"name": f"FridgeSheet-Setup-{tag[1:]}.exe",
                        "browser_download_url": f"https://github.com/x/releases/download/{tag}/FridgeSheet-Setup-{tag[1:]}.exe"}] if asset else []}
    return lambda url: json.dumps(body).encode()


def test_versions_compare_as_numbers_and_dev_is_never_newer():
    assert updates.parse_version("v0.3.1") == (0, 3, 1) and updates.parse_version("0.10") == (0, 10)
    assert updates.newer("0.10.0", "0.9.9") and not updates.newer("0.9.9", "0.10.0")
    assert not updates.newer("dev", "0.1.0") and not updates.newer("0.1.0", "dev")
    assert not updates.newer("v0.3.0", "0.3.0")


def test_latest_release_prefers_the_installer_asset_and_falls_back_to_the_page():
    assert updates.latest_release(release()) == ("0.9.0", "https://github.com/x/releases/download/v0.9.0/FridgeSheet-Setup-0.9.0.exe")
    assert updates.latest_release(release(asset=False)) == ("0.9.0", "https://github.com/x/releases/tag/v0.9.0")
    with pytest.raises(ValueError):
        updates.latest_release(lambda url: b'{"tag_name": "nightly"}')


def _state(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    return c, c.app.state.fridgesheet


def test_check_caches_for_a_day_and_a_failure_for_an_hour(tmp_path):
    c, state = _state(tmp_path)
    calls = []
    def fetch(url):
        calls.append(url); return release()(url)
    u = updates.check(state, now=NOW, fetch=fetch)
    assert u.available and u.latest == "0.9.0" and u.url.endswith(".exe") and calls == [updates.LATEST_URL]
    assert updates.check(state, now=NOW + timedelta(hours=23), fetch=fetch) is u          # cached
    assert updates.check(state, now=NOW + timedelta(hours=25), fetch=fetch) is not u      # a day later: asked again
    assert len(calls) == 2

    def down(url):
        raise OSError("connection refused")
    state.extra.pop(updates.CACHE_KEY)
    bad = updates.check(state, now=NOW, fetch=down)
    assert not bad.available and "connection refused" in bad.error
    assert updates.check(state, now=NOW + timedelta(minutes=30), fetch=down) is bad
    assert updates.check(state, now=NOW + timedelta(minutes=61), fetch=fetch).available    # retried after an hour


def test_the_checkbox_turns_it_off_entirely(tmp_path):
    c, state = _state(tmp_path)
    state.settings.web_check_updates = False
    called = []
    assert updates.check(state, now=NOW, fetch=lambda u: called.append(u) or b"{}") is None
    assert called == [] and updates.cached(state) is None


def test_no_test_can_reach_github_by_accident(tmp_path):
    c, state = _state(tmp_path)
    u = updates.check(state, now=NOW)                 # no fetch injected: the conftest guard answers
    assert not u.available and "no network in tests" in u.error


def test_settings_says_what_it_found_and_the_header_carries_the_badge(tmp_path):
    c, state = _state(tmp_path)
    state.extra["update_fetch"] = release("v0.9.0")
    page = c.get("/settings", headers={"host": "127.0.0.1"}).text
    assert "Fridge Sheet 0.9.0 is available" in page and 'href="https://github.com/x/releases/download/v0.9.0/FridgeSheet-Setup-0.9.0.exe"' in page
    assert 'name="check_updates" checked' in page
    dash = c.get("/", headers={"host": "127.0.0.1"}).text       # other pages read the cache, no call
    assert "Fridge Sheet 0.9.0 is available" in dash and 'href="/settings"' in dash

    state.extra.pop(updates.CACHE_KEY)
    state.extra["update_fetch"] = release("v0.0.1")           # older than anything running
    page = c.get("/settings", headers={"host": "127.0.0.1"}).text
    assert "up to date" in page and "is available" not in page


def test_saving_settings_round_trips_the_checkbox(tmp_path):
    from fridgesheet import config
    c, state = _state(tmp_path)

    class Cred:                                   # a new username needs a password; keep it out of any file
        def write(self, username, password): pass
    state.extra["credstore"] = Cred()
    form = {"username": "parent@example.org", "password": "hunter2", "printer": "", "days_ahead": "14",
            "overdue_days": "14", "nicknames": "", "archive": "", "port": "8433", "allow_lan": "on"}   # check_updates absent = off
    r = c.post("/settings", data=form, headers={"host": "127.0.0.1", "Origin": "http://127.0.0.1"})
    assert r.status_code == 200 and "update checks are off" in r.text
    assert config.load_config_doc(tmp_path / "config.toml")["web"]["check_updates"] is False
    r = c.post("/settings", data={**form, "check_updates": "on"}, headers={"host": "127.0.0.1", "Origin": "http://127.0.0.1"})
    assert config.load_config_doc(tmp_path / "config.toml")["web"]["check_updates"] is True

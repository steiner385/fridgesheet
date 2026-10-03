"""The app on a kid's own phone: installable, opened by a QR code, remembered by the device.

Three pieces, one idea (kid mode, spec 2026-09-27 §13, carried onto a phone): a web app
manifest so a browser offers "Add to Home Screen"; a per-kid manifest whose start URL names
the kid, because a home-screen app on iOS gets a cookie jar of its own and the chooser's
cookie does not follow it there; and a QR code on each kid's page, in the family's view,
that encodes the link which sets that cookie on the phone that scans it.
"""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient

from fridgesheet import qr
from fridgesheet.web import actions, app as webapp
from tests.web_fixtures import LOCAL_HOST_HEADERS, app_for, seed


def _bare(tmp_path) -> TestClient:
    c = app_for(tmp_path)
    c.cookies.clear()
    return c


def _lan(monkeypatch, tmp_path, allow: bool = True) -> TestClient:
    """A client whose app knows one LAN address and (by default) allows the LAN."""
    monkeypatch.setattr(actions, "_lan_probe", lambda: "192.168.1.42")
    if allow:
        (tmp_path / "config.toml").write_text('[web]\nallow_lan = true\n', encoding="utf-8")
    seed(tmp_path).close()
    return app_for(tmp_path)


# --- the manifest ------------------------------------------------------------------------

def test_the_household_manifest_installs_the_app_at_the_root(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    m = r.json()
    assert m["name"] == "Fridge Sheet" and m["start_url"] == "/" and m["display"] == "standalone"
    sizes = {i["sizes"] for i in m["icons"]}
    assert {"192x192", "512x512"} <= sizes, "Chrome's install prompt needs both"
    assert all(i["src"].startswith("/static/") for i in m["icons"])


def test_a_kids_manifest_is_named_for_them_and_starts_on_their_link(tmp_path):
    """The installed app's first launch goes through `/who/<key>` -- not `/` -- so the
    home-screen app's own cookie jar learns who is looking before the plan is shown."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.app.state.fridgesheet.settings.nicknames["Alex"] = "Al"
    m = c.get("/kids/Alex/manifest.webmanifest").json()
    assert m["name"] == "Al · Fridge Sheet" and m["short_name"] == "Al"
    assert m["start_url"] == "/who/Alex" and m["id"] == "/kids/Alex"
    assert m["scope"] == "/"


def test_a_manifest_for_an_unknown_kid_is_a_404(tmp_path):
    seed(tmp_path).close()
    assert app_for(tmp_path).get("/kids/Nobody/manifest.webmanifest").status_code == 404


def test_the_manifests_icons_exist(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    for icon in c.get("/manifest.webmanifest").json()["icons"]:
        assert c.get(icon["src"]).status_code == 200, icon["src"]


def test_every_page_links_a_manifest_and_a_kids_page_links_the_kids(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert '<link rel="manifest" href="/manifest.webmanifest">' in c.get("/").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in c.get("/settings").text
    assert '<link rel="manifest" href="/kids/Alex/manifest.webmanifest">' in c.get("/kids/Alex/plan").text
    assert '<link rel="manifest" href="/kids/Alex/manifest.webmanifest">' in c.get("/kids/Alex").text
    assert '<link rel="manifest" href="/manifest.webmanifest">' in c.get("/who").text


def test_in_kid_mode_every_page_links_that_kids_manifest(tmp_path):
    """Trends in kid mode has no student in context but is still the kid's page: installing
    from there must still install the kid's app."""
    seed(tmp_path).close()
    c = _bare(tmp_path)
    c.cookies.set(webapp.WHO_COOKIE, "Sam")
    assert '<link rel="manifest" href="/kids/Sam/manifest.webmanifest">' in c.get("/trends").text


def test_the_pages_carry_a_theme_colour(tmp_path):
    seed(tmp_path).close()
    assert re.search(r'<meta name="theme-color" content="#[0-9a-f]{6}">', app_for(tmp_path).get("/").text)


# --- the link that chooses --------------------------------------------------------------

def test_the_kids_link_sets_the_cookie_and_goes_to_their_plan(tmp_path):
    seed(tmp_path).close()
    c = _bare(tmp_path)
    r = c.get("/who/Alex", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/plan"
    cookie = r.headers["set-cookie"].lower()
    assert cookie.startswith("fridgesheet_who=alex") and "max-age=31536000" in cookie and "httponly" in cookie


def test_the_grown_ups_link_works_the_same_way(tmp_path):
    seed(tmp_path).close()
    r = _bare(tmp_path).get("/who/family", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert r.headers["set-cookie"].lower().startswith("fridgesheet_who=family")


def test_a_link_naming_nobody_is_a_404_and_sets_nothing(tmp_path):
    seed(tmp_path).close()
    r = _bare(tmp_path).get("/who/Nobody", follow_redirects=False)
    assert r.status_code == 404 and "set-cookie" not in r.headers


def test_each_launch_renews_the_memory(tmp_path):
    """A kid who opens the app every day for a year should not land on the chooser on day
    366: `/` -- the installed app's start URL once the cookie is set -- re-sets it."""
    seed(tmp_path).close()
    c = _bare(tmp_path)
    c.cookies.set(webapp.WHO_COOKIE, "Alex")
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/kids/Alex/plan"
    assert r.headers["set-cookie"].lower().startswith("fridgesheet_who=alex") and "max-age=31536000" in r.headers["set-cookie"].lower()


# --- the service worker and the offline page -----------------------------------------------

def test_the_service_worker_is_served_from_the_root_as_script(tmp_path):
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/sw.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith(("application/javascript", "text/javascript"))
    assert "no-cache" in r.headers.get("cache-control", ""), "a browser must re-check the worker on every load"
    assert "/offline" in r.text


def test_the_service_worker_is_stamped_with_the_build(tmp_path):
    """A new build is a new worker (the byte-compare browsers do), so the old offline page is
    dropped at the next start rather than kept for ever."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/sw.js").text
    assert webapp.version() in body and "__VERSION__" not in body


def test_the_service_worker_never_caches_a_page(tmp_path):
    """Everything on these pages is a live answer about tonight's work. The worker caches the
    offline page and the mark, and nothing a route renders."""
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/sw.js").text
    assert "cache.put" not in body and "caches.open" in body
    assert re.search(r"mode\s*[!=]==\s*['\"]navigate['\"]", body), "only navigations are answered for"


def test_the_pages_register_the_worker(tmp_path):
    seed(tmp_path).close()
    c = app_for(tmp_path)
    assert "serviceWorker.register('/sw.js')" in c.get("/").text
    assert "serviceWorker.register('/sw.js')" in c.get("/who").text


def test_the_offline_page_stands_on_its_own(tmp_path):
    """Shown when the home computer cannot be reached, so nothing on it may come from the
    server: no stylesheet link, no script file, no rail, and no data."""
    seed(tmp_path).close()
    r = app_for(tmp_path).get("/offline")
    assert r.status_code == 200
    body = r.text
    assert "home Wi" in body and "Try again" in body
    assert '<link rel="stylesheet"' not in body and "<script src=" not in body
    assert 'class="rail"' not in body and "Alex" not in body


# --- the QR code on each kid's page --------------------------------------------------------

def test_a_kids_page_shows_the_qr_for_their_link_in_the_family_view(monkeypatch, tmp_path):
    c = _lan(monkeypatch, tmp_path)
    for path in ("/kids/Alex", "/kids/Alex/plan", "/kids/Alex/check-in"):
        body = c.get(path).text
        assert "Put this on Alex" in body, path
        assert "http://192.168.1.42:8433/who/Alex" in body, path
        assert qr.svg("http://192.168.1.42:8433/who/Alex", size_px=200) in body, path


def test_the_qr_names_the_kid_by_nickname(monkeypatch, tmp_path):
    c = _lan(monkeypatch, tmp_path)
    c.app.state.fridgesheet.settings.nicknames["Alex"] = "Al"
    body = c.get("/kids/Alex/plan").text
    assert "Put this on Al" in body and "Put this on Alex" not in body
    assert "/who/Alex" in body                               # the link carries the key, not the name


def test_the_qr_is_the_siblings_own_on_their_page(monkeypatch, tmp_path):
    body = _lan(monkeypatch, tmp_path).get("/kids/Sam/plan").text
    assert "/who/Sam" in body and "/who/Alex" not in body


def test_no_qr_in_kid_mode(monkeypatch, tmp_path):
    """The kid is already on their phone; a code to scan with it means nothing there."""
    c = _lan(monkeypatch, tmp_path)
    c.cookies.set(webapp.WHO_COOKIE, "Alex")
    body = c.get("/kids/Alex/plan").text
    assert "Put this on" not in body and "<svg" not in body


def test_with_the_lan_off_the_fold_points_at_settings_instead(monkeypatch, tmp_path):
    c = _lan(monkeypatch, tmp_path, allow=False)
    body = c.get("/kids/Alex/plan").text
    assert "Put this on Alex" in body
    assert "<svg" not in body and "192.168.1.42" not in body
    assert "Allow other devices" in body and 'href="/settings"' in body


def test_the_fold_is_closed_by_default(monkeypatch, tmp_path):
    """The QR is a one-time setup; it must not take 200px of every kid page every day."""
    body = _lan(monkeypatch, tmp_path).get("/kids/Alex/plan").text
    m = re.search(r'<details class="[^"]*phone-link[^"]*"([^>]*)>', body)
    assert m and "open" not in m.group(1)


def test_the_qr_is_not_drawn_on_a_phone_that_cannot_be_named(monkeypatch, tmp_path):
    """The probe fails on a box with no routable address: the fold still renders, says the
    address is not known, and the page is not taken down with it."""
    def boom():
        raise OSError("no route")
    monkeypatch.setattr(actions, "_lan_probe", boom)
    (tmp_path / "config.toml").write_text('[web]\nallow_lan = true\n', encoding="utf-8")
    seed(tmp_path).close()
    body = app_for(tmp_path).get("/kids/Alex/plan").text
    assert "Put this on Alex" in body and "<svg" not in body


def test_the_phone_link_json_is_safe_in_the_manifest(tmp_path):
    """A nickname is the parent's own text; the manifest is JSON, so a quote in it must be
    escaped rather than break the document."""
    seed(tmp_path).close()
    c = app_for(tmp_path)
    c.app.state.fridgesheet.settings.nicknames["Alex"] = 'A "J" <b>'
    r = c.get("/kids/Alex/manifest.webmanifest")
    assert json.loads(r.text)["short_name"] == 'A "J" <b>'

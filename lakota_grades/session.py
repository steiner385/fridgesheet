"""Browser session management.

One persistent Chromium profile holds the OneLogin, Canvas and HAC cookies, so a login is
only performed when a site actually bounces us to a login page. Credentials are pulled from
Settings.credentials() at the moment they are typed and are not kept anywhere else.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import BrowserContext, Page, TimeoutError as PWTimeout, sync_playwright

from .config import Settings

log = logging.getLogger("lakota.session")


class LoginRequired(RuntimeError):
    """Raised when a site needs a login and automatic login failed."""


@contextmanager
def browser(settings: Settings, headless: bool | None = None) -> Iterator[BrowserContext]:
    hl = settings.headless if headless is None else headless
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(settings.profile_dir),
            headless=hl,
            viewport={"width": 1400, "height": 900},
            timezone_id=settings.timezone,
        )
        try:
            yield ctx
        finally:
            ctx.close()


def _is_onelogin(page: Page, settings: Settings) -> bool:
    return settings.onelogin_host in page.url


def _fill_first(page: Page, selector_list: str, value: str, timeout: int = 8000) -> bool:
    for sel in [s.strip() for s in selector_list.split(",")]:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.fill(value)
            return True
        except PWTimeout:
            continue
    return False


def onelogin_login(page: Page, settings: Settings) -> None:
    """Complete the OneLogin username/password form currently on `page`."""
    user, pw = settings.credentials()
    log.info("OneLogin login page detected; signing in")
    if not _fill_first(page, settings.onelogin_user_selector, user):
        raise LoginRequired("Could not find the OneLogin username field (override LAKOTA_ONELOGIN_USER_SELECTOR)")
    # OneLogin often shows username first, then password on the next step.
    page.keyboard.press("Enter")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass
    if not _fill_first(page, settings.onelogin_pass_selector, pw):
        raise LoginRequired("Could not find the OneLogin password field (override LAKOTA_ONELOGIN_PASS_SELECTOR)")
    page.keyboard.press("Enter")
    try:
        page.wait_for_url(lambda u: settings.onelogin_host not in u or "/portal" in u, timeout=30000)
    except PWTimeout:
        raise LoginRequired("OneLogin did not redirect after submitting credentials (MFA prompt, or wrong password?)")
    del user, pw


def ensure_canvas(ctx: BrowserContext, settings: Settings) -> Page:
    """Return a page that is signed in to Canvas."""
    page = ctx.new_page()
    page.goto(settings.canvas_base + "/", wait_until="domcontentloaded")
    for _ in range(3):
        if _is_onelogin(page, settings):
            onelogin_login(page, settings)
            page.goto(settings.canvas_base + "/", wait_until="domcontentloaded")
            continue
        if "/login" in page.url:
            # Canvas' own login form (non-SSO). Use the same credentials.
            user, pw = settings.credentials()
            if _fill_first(page, "#pseudonym_session_unique_id", user) and _fill_first(page, "#pseudonym_session_password", pw):
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded")
                page.goto(settings.canvas_base + "/", wait_until="domcontentloaded")
                continue
            raise LoginRequired("Canvas login page shown but form not recognised")
        break
    r = ctx.request.get(settings.canvas_base + "/api/v1/users/self", headers={"Accept": "application/json"})
    if r.status != 200:
        raise LoginRequired(f"Canvas API not authenticated (HTTP {r.status})")
    return page


def ensure_hac(ctx: BrowserContext, settings: Settings) -> Page:
    """Return a page that is signed in to Home Access Center (on the Home/WeekView page)."""
    page = ctx.new_page()
    page.goto(settings.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
    for _ in range(3):
        if _is_onelogin(page, settings):
            onelogin_login(page, settings)
            page.goto(settings.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
            continue
        if "/Account/LogOn" in page.url:
            # HAC's own form (if SSO is bypassed). Same credentials.
            user, pw = settings.credentials()
            if _fill_first(page, "#LogOnDetails_UserName", user) and _fill_first(page, "#LogOnDetails_Password", pw):
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded")
                page.goto(settings.hac_base + "/Home/WeekView", wait_until="domcontentloaded")
                continue
            raise LoginRequired("HAC login page shown but form not recognised")
        break
    if "/Home/WeekView" not in page.url:
        raise LoginRequired(f"HAC did not land on WeekView (at {page.url})")
    return page

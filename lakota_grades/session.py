"""Browser session management.

One persistent Chromium profile holds the OneLogin, Canvas and HAC cookies, so a login is
only performed when a site actually bounces us to a login page. Credentials are pulled from
Settings.credentials() at the moment they are typed and are not kept anywhere else.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator

from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PWTimeout, sync_playwright

from .config import Settings

log = logging.getLogger("lakota.session")

# Text of a visible login error is site copy, never a credential, so it is safe to surface.
_ERROR_SELECTORS = "[role='alert'], .error, .alert-error, .login-error, #error_message"


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


def _goto(page: Page, url: str) -> None:
    """Navigate and let client-side SSO redirects settle before the caller inspects page.url.

    goto() follows server-side redirects, but Canvas and HAC both hand off to OneLogin with a
    JS redirect from an interstitial. Without this settle, page.url is still the interstitial
    (e.g. '/login/canvas') and we mistake an SSO hand-off for a native login form.
    """
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except PWTimeout:
        pass


def _first_visible(page: Page, selector_list: str, timeout: int = 5000) -> Locator | None:
    """First *visible* match among a comma-separated selector list, preferring earlier entries.

    The list is raced as a single CSS selector so the timeout is spent once rather than once
    per alternative (the original spent up to 8s x 3 selectors just to decide a field was absent).
    """
    sels = [s.strip() for s in selector_list.split(",") if s.strip()]
    if not sels:
        return None
    try:
        page.locator(", ".join(sels)).first.wait_for(state="visible", timeout=timeout)
    except PWTimeout:
        return None
    for sel in sels:
        loc = page.locator(sel).first
        try:
            if loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _fill_first(page: Page, selector_list: str, value: str, timeout: int = 8000) -> bool:
    loc = _first_visible(page, selector_list, timeout)
    if loc is None:
        return False
    loc.fill(value)
    return True


def _submit(page: Page, field: Locator, settings: Settings) -> None:
    """Advance a login form via its submit control, falling back to Enter in the field."""
    btn = _first_visible(page, settings.onelogin_submit_selector, timeout=2000)
    if btn is not None:
        btn.click()
    else:
        field.press("Enter")


def _login_error(page: Page) -> str | None:
    try:
        loc = page.locator(_ERROR_SELECTORS).first
        if loc.is_visible(timeout=1000):
            return " ".join(loc.inner_text().split())[:200]
    except Exception:
        pass
    return None


def onelogin_login(page: Page, settings: Settings) -> None:
    """Complete the OneLogin form on `page`, for both single-step and two-step layouts."""
    user, pw = settings.credentials()
    log.info("OneLogin login page detected; signing in")
    user_field = _first_visible(page, settings.onelogin_user_selector, timeout=10000)
    if user_field is None:
        raise LoginRequired(
            "Could not find the OneLogin username field (override LAKOTA_ONELOGIN_USER_SELECTOR). "
            f"At {page.url}"
        )
    user_field.fill(user)

    # Some OneLogin tenants put username and password on one page; others gate the password
    # behind a Continue step. Probe for a visible password field BEFORE advancing -- blindly
    # pressing Enter on a single-page form submits it with an empty password and fails the login.
    pw_field = _first_visible(page, settings.onelogin_pass_selector, timeout=1500)
    if pw_field is None:
        _submit(page, user_field, settings)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PWTimeout:
            pass
        pw_field = _first_visible(page, settings.onelogin_pass_selector, timeout=10000)
    if pw_field is None:
        raise LoginRequired(
            "Could not find the OneLogin password field (override LAKOTA_ONELOGIN_PASS_SELECTOR). "
            f"At {page.url}: {_login_error(page) or 'no error shown'}"
        )
    pw_field.fill(pw)
    _submit(page, pw_field, settings)
    try:
        page.wait_for_url(lambda u: settings.onelogin_host not in u or "/portal" in u, timeout=30000)
    except PWTimeout:
        raise LoginRequired(
            "OneLogin did not redirect after submitting credentials "
            f"({_login_error(page) or 'MFA prompt, or wrong password?'})"
        )
    del user, pw


def ensure_canvas(ctx: BrowserContext, settings: Settings) -> Page:
    """Return a page that is signed in to Canvas."""
    page = ctx.new_page()
    _goto(page, settings.canvas_base + "/")
    for _ in range(3):
        if _is_onelogin(page, settings):
            onelogin_login(page, settings)
            _goto(page, settings.canvas_base + "/")
            continue
        if "/login" in page.url:
            # Canvas' own login form (non-SSO). Use the same credentials.
            user, pw = settings.credentials()
            if _fill_first(page, "#pseudonym_session_unique_id", user) and _fill_first(page, "#pseudonym_session_password", pw):
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded")
                _goto(page, settings.canvas_base + "/")
                continue
            raise LoginRequired(f"Canvas login page shown but form not recognised (at {page.url})")
        break
    r = ctx.request.get(settings.canvas_base + "/api/v1/users/self", headers={"Accept": "application/json"})
    if r.status != 200:
        raise LoginRequired(f"Canvas API not authenticated (HTTP {r.status})")
    return page


def ensure_hac(ctx: BrowserContext, settings: Settings) -> Page:
    """Return a page that is signed in to Home Access Center (on the Home/WeekView page)."""
    page = ctx.new_page()
    _goto(page, settings.hac_base + "/Home/WeekView")
    for _ in range(3):
        if _is_onelogin(page, settings):
            onelogin_login(page, settings)
            _goto(page, settings.hac_base + "/Home/WeekView")
            continue
        if "/Account/LogOn" in page.url:
            # HAC's own form (if SSO is bypassed). Same credentials.
            user, pw = settings.credentials()
            if _fill_first(page, "#LogOnDetails_UserName", user) and _fill_first(page, "#LogOnDetails_Password", pw):
                page.keyboard.press("Enter")
                page.wait_for_load_state("domcontentloaded")
                _goto(page, settings.hac_base + "/Home/WeekView")
                continue
            raise LoginRequired(f"HAC login page shown but form not recognised (at {page.url})")
        break
    if "/Home/WeekView" not in page.url:
        raise LoginRequired(f"HAC did not land on WeekView (at {page.url})")
    return page

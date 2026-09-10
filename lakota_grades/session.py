"""Browser session management.

One persistent Chromium profile holds the OneLogin, Canvas and HAC cookies, so a login is
only performed when a site actually bounces us to a login page. Credentials are pulled from
Settings.credentials() at the moment they are typed and are not kept anywhere else.
"""
from __future__ import annotations

import logging
import re
import subprocess
from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PWTimeout, sync_playwright

from .config import Settings

log = logging.getLogger("lakota.session")

# Text of a visible login error is site copy, never a credential, so it is safe to surface.
_ERROR_SELECTORS = "[role='alert'], .error, .alert-error, .login-error, #error_message"


_UA_TEMPLATE = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v} Safari/537.36"
_FALLBACK_CHROME_VERSION = "151.0.0.0"


class LoginRequired(RuntimeError):
    """Raised when a site needs a login and automatic login failed."""


@lru_cache(maxsize=4)
def _default_user_agent(executable_path: str) -> str:
    """Present as ordinary Chrome rather than HeadlessChrome.

    Chromium's default UA carries a "HeadlessChrome/<v>" token. Vendor sniffers that do not
    know it fall through to the trailing "Safari/537.36" and mis-detect the browser --
    ParentSquare serves /browser_unsupported?browser=Safari&version= on exactly this. Report
    the real version of the binary we are running, without the Headless marker.
    """
    version = _FALLBACK_CHROME_VERSION
    try:
        out = subprocess.run([executable_path, "--version"], capture_output=True, text=True, timeout=10).stdout
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out or "")
        if m:
            version = m.group(1)
    except Exception:
        log.debug("could not read Chromium version; using fallback UA")
    return _UA_TEMPLATE.format(v=version)


@contextmanager
def browser(settings: Settings, headless: bool | None = None) -> Iterator[BrowserContext]:
    hl = settings.headless if headless is None else headless
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(settings.profile_dir),
            headless=hl,
            viewport={"width": 1400, "height": 900},
            timezone_id=settings.timezone,
            user_agent=settings.user_agent or _default_user_agent(p.chromium.executable_path),
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


_APP_TILE_SELECTOR = "a[href*='/client/apps/select/']"


def onelogin_app_url(page: Page, settings: Settings, pattern: str) -> str | None:
    """Find an app's launch URL on the OneLogin portal by matching its tile text.

    App ids are tenant-specific and change when an admin re-creates the app, so the tile is
    located by name rather than pinned. Set LAKOTA_HAC_ONELOGIN_APP_URL to skip this.
    """
    portal = "https://" + settings.onelogin_host + settings.onelogin_portal_path
    _goto(page, portal)
    if _is_onelogin(page, settings) and "/portal" not in page.url:
        onelogin_login(page, settings)
        _goto(page, portal)
    try:
        page.wait_for_selector(_APP_TILE_SELECTOR, timeout=25000)
    except PWTimeout:
        return None
    rx = re.compile(pattern, re.I)
    for a in page.locator(_APP_TILE_SELECTOR).all():
        try:
            txt = " ".join(a.inner_text().split())
        except Exception:
            continue
        if rx.search(txt):
            log.info("Found OneLogin app tile %r", txt)
            return a.get_attribute("href")
    return None


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
            user_field = _first_visible(page, "#LogOnDetails_UserName, input[name='LogOnDetails.UserName']", timeout=3000)
            if user_field is not None:
                # HAC's own eSchoolPlus form, where a district still allows direct login.
                user, pw = settings.credentials()
                user_field.fill(user)
                if _fill_first(page, "#LogOnDetails_Password, input[name='LogOnDetails.Password']", pw):
                    page.keyboard.press("Enter")
                    page.wait_for_load_state("domcontentloaded")
                    _goto(page, settings.hac_base + "/Home/WeekView")
                    continue
                raise LoginRequired(f"HAC login form found but no password field (at {page.url})")
            # Lakota's /Account/LogOn has no form at all -- it is now just a notice pointing
            # at the OneLogin portal. HAC must be entered by launching its portal tile, which
            # performs the SSO hand-off; navigating straight to /Home/WeekView never can.
            app_url = settings.hac_app_url or onelogin_app_url(page, settings, settings.hac_app_pattern)
            if not app_url:
                raise LoginRequired(
                    "HAC has no login form and no matching OneLogin app tile was found. "
                    "Set LAKOTA_HAC_ONELOGIN_APP_URL to the tile's launch URL, or adjust "
                    f"LAKOTA_HAC_APP_PATTERN (currently {settings.hac_app_pattern!r})."
                )
            settings.hac_app_url = app_url  # reuse within this run
            log.info("Launching HAC through the OneLogin portal")
            _goto(page, app_url)
            if _is_onelogin(page, settings):
                onelogin_login(page, settings)
            _goto(page, settings.hac_base + "/Home/WeekView")
            continue
        break
    if "/Home/WeekView" not in page.url:
        raise LoginRequired(f"HAC did not land on WeekView (at {page.url})")
    return page

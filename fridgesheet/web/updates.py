"""Is there a newer Fridge Sheet? Asked of GitHub's releases, at most once a day, and only
ever *told* to the parent -- nothing here downloads or installs anything.

The installer already knows how to upgrade over a running copy (`packaging/windows/
installer.iss`, `PrepareToInstall`). What was missing was the noticing: a parent who
installed once had no way to learn a fix existed short of being told by hand. This is the
minimum that closes that gap honestly. A one-click upgrade -- the app fetching and running
an installer on itself -- is a different level of trust and is deliberately not here yet.

This is the one place the app talks to anything other than OneLogin, Canvas and HAC. It
sends nothing but the request; it is off in one checkbox on Settings (`[web]
check_updates = false`); and the About text says so.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import metadata
from typing import Callable

REPO = "steiner385/fridgesheet"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CACHE_KEY = "updates"
#: A good answer is worth a day; a failed one is worth an hour, so a GitHub blip does not
#: pin "could not check" to the page until tomorrow.
TTL_OK = timedelta(hours=24)
TTL_ERROR = timedelta(hours=1)
TIMEOUT = 4          # seconds; the Settings page waits on this once a day, no more


@dataclass(frozen=True)
class Update:
    current: str                 # the version this process is running
    latest: str = ""             # the newest release's version, or "" when unknown
    url: str = ""                # where to get it: the installer asset, else the release page
    checked_at: datetime | None = None
    error: str = ""              # why `latest` is unknown, in one line

    @property
    def available(self) -> bool:
        return bool(self.latest) and newer(self.latest, self.current)


def current_version() -> str:
    try:
        return metadata.version("fridgesheet")
    except metadata.PackageNotFoundError:
        return "dev"


def parse_version(s: str) -> tuple[int, ...]:
    """'v0.3.1' -> (0, 3, 1). Anything that is not dotted digits after an optional 'v' is
    treated as the lowest version there is, so "dev" is never newer than a release and a
    malformed tag never announces itself."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (s or "").strip())
    return tuple(int(p) for p in m.group(1).split(".")) if m else ()


def newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    return bool(a) and bool(b) and a > b


def _default_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": f"fridgesheet/{current_version()}"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:     # noqa: S310  a fixed https URL
        return r.read()


#: Tests replace this (conftest) so no test ever reaches GitHub; the Settings route can also
#: inject one per app through `state.extra["update_fetch"]`.
DEFAULT_FETCH: Callable[[str], bytes] = _default_fetch


def latest_release(fetch: Callable[[str], bytes] | None = None) -> tuple[str, str]:
    """(version, url) for the newest published release. The URL is the Windows installer
    asset when the release has one, else the release page."""
    data = json.loads((fetch or DEFAULT_FETCH)(LATEST_URL))
    tag = str(data.get("tag_name") or "")
    if not parse_version(tag):
        raise ValueError(f"release tag {tag!r} is not a version")
    url = next((a.get("browser_download_url") for a in data.get("assets") or []
                if str(a.get("name", "")).lower().endswith(".exe")), None) or data.get("html_url") or RELEASES_PAGE
    return tag.lstrip("v"), str(url)


def check(state, *, now: datetime, fetch: Callable[[str], bytes] | None = None) -> Update | None:
    """The cached answer if it is fresh, else a new one. None when the parent turned it off."""
    if not state.settings.web_check_updates:
        return None
    cached: Update | None = state.extra.get(CACHE_KEY)
    if cached is not None and cached.checked_at is not None:
        age = now - cached.checked_at
        if age < (TTL_ERROR if cached.error else TTL_OK):
            return cached
    current = current_version()
    try:
        latest, url = latest_release(fetch or state.extra.get("update_fetch"))
        result = Update(current, latest, url, now)
    except Exception as e:  # noqa: BLE001  no network, a 404 before the first release, odd JSON: one line on the page, never a 500
        result = Update(current, "", "", now, error=f"{type(e).__name__}: {str(e)[:100]}")
    state.extra[CACHE_KEY] = result
    return result


def cached(state) -> Update | None:
    """What the last check said, for pages that must not wait on the network (every page's
    header). None until Settings has been visited once, or when the check is off."""
    if not state.settings.web_check_updates:
        return None
    return state.extra.get(CACHE_KEY)

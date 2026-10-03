"""The app on a phone's home screen: the manifests, the service worker, the offline page.

Kid mode (spec 2026-09-27 §13) carried onto the kid's own device. A browser installs what the
manifest describes; a page about a kid links *that kid's* manifest, whose start URL is
`/who/<key>` rather than `/`: a home-screen app on iOS has a cookie jar of its own, so the
chooser's cookie set in Safari does not follow the kid into the installed app -- the start
URL has to carry who they are, and `/who/<key>` sets the cookie in the new jar on first
launch. The grown-up's manifest starts at `/`, which goes by the cookie as always.

The service worker is deliberately small: it caches the offline page and the mark, and never
a page -- every page here is a live answer about tonight's work, and a cached one would be a
wrong one. Its one job is that a kid who opens the app at school sees "this phone needs the
home Wi-Fi" instead of the browser's own error.
"""
from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from ..app import HERE, Db, State, student_or_404, version, _env

router = APIRouter()

#: The planner's paper (`--wash` in app.css): the colour the phone paints around the app.
THEME_COLOUR = "#fffdf6"

MANIFEST_TYPE = "application/manifest+json"

_ICONS = [
    {"src": "/static/mark-192.png", "sizes": "192x192", "type": "image/png"},
    {"src": "/static/mark-512.png", "sizes": "512x512", "type": "image/png"},
    {"src": "/static/mark.svg", "sizes": "any", "type": "image/svg+xml"},
]


def _manifest(name: str, short_name: str, start_url: str, ident: str) -> JSONResponse:
    return JSONResponse({
        "id": ident, "name": name, "short_name": short_name, "start_url": start_url, "scope": "/",
        "display": "standalone", "background_color": THEME_COLOUR, "theme_color": THEME_COLOUR,
        "icons": _ICONS,
    }, media_type=MANIFEST_TYPE)


@router.get("/manifest.webmanifest", include_in_schema=False)
def household_manifest():
    return _manifest("Fridge Sheet", "Fridge Sheet", "/", "/")


@router.get("/kids/{key}/manifest.webmanifest", include_in_schema=False)
def kid_manifest(key: str, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    nick = state.settings.nicknames.get(s["key"], s["key"])
    path = quote(s["key"], safe="")
    return _manifest(f"{nick} · Fridge Sheet", nick, f"/who/{path}", f"/kids/{path}")


@router.get("/sw.js", include_in_schema=False)
def service_worker():
    # Served from the root so its scope is the whole app (a worker under /static/ could only
    # govern /static/). Stamped with the build: a browser byte-compares the worker on each
    # visit, so a new version is a new worker, and the old cache goes with it.
    body = (HERE / "static" / "sw.js").read_text(encoding="utf-8").replace("__VERSION__", version())
    return Response(body, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})   # re-check every load; never a stale worker


@router.get("/offline", include_in_schema=False)
def offline(request: Request):
    # No database, no page context: this is what the worker shows when the home computer
    # cannot be reached, so the page must need nothing from it (its styles are inline).
    return HTMLResponse(_env(request).get_template("offline.html").render(version=version()))

"""The FastAPI application: state, the per-request database connection, page rendering.

`create_app(settings)` is the only constructor; the server (`server.py`), the tests
(`TestClient`) and part 2's jobs worker all go through it. Routes live in `routes/`, SQL in
`stores/`; this module owns what every page shares -- the header data and the rail.
"""
from __future__ import annotations

import ipaddress
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from importlib import metadata
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import jinja2
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import dates, late_rules
from ..config import Settings
from . import db, updates
from .stores import refreshes, runs, students

HERE = Path(__file__).parent
APP_NAME = "fridgesheet"


def version() -> str:
    try:
        return metadata.version("fridgesheet")
    except metadata.PackageNotFoundError:
        return "dev"


@dataclass
class AppState:
    home: Path
    settings: Settings
    tz: ZoneInfo
    started_at: datetime
    clock: Callable[[], datetime] | None = None   # None -> the wall clock in `tz`; tests freeze it
    extra: dict = field(default_factory=dict)     # part 2 hangs the jobs worker here
    jobs: "Worker | None" = None

    def __post_init__(self) -> None:
        if self.clock is None:
            self.clock = lambda: datetime.now(self.tz)

    def reload(self) -> None:
        """Re-read config.toml after Settings saved it (env overrides stay in force when the
        server started from load_settings, because the process environment has not changed)."""
        from .. import config
        if self.home == config.DEFAULT_HOME:
            self.settings = config.load_settings()
        else:
            s = config.Settings(home=self.home)
            config.settings_from_doc(config.load_config_doc(self.home / "config.toml"), s)
            self.settings = s
        self.extra["env"].filters.update(_filters(self))

    def rules(self) -> late_rules.LateRules:
        """Re-read each call: the parent edits late-rules.toml (part 2's Settings page).

        A file the parent has just broken must not take every page down with it: fall back to
        the built-in default and carry the message into the header, where it is visible and
        fixable, and drop the warning again as soon as a later load parses.
        """
        try:
            rules = late_rules.load(self.home / "late-rules.toml")
        except late_rules.LateRulesError as e:
            self.extra["warnings"] = [str(e)]
            return late_rules.LateRules(late_rules.Rule(), [], [])
        self.extra["warnings"] = []
        return rules

    def now(self) -> datetime:
        return self.clock()


def _parse(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def _filters(state: AppState) -> dict:
    def wd_md_time(v):
        d = _parse(v) if isinstance(v, str) else v
        return dates.wd_md_time(d.astimezone(state.tz)) if d else ""

    def md(v):
        # A plain `date` (e.g. a week-table row's `week_start`) needs no zone conversion --
        # `dates.md` only reads `.month`/`.day` -- and `date` has no `astimezone` to call.
        # Only a `datetime` (a `date` subclass) is converted; the isoformat-string case above
        # always produces one.
        d = _parse(v) if isinstance(v, str) else v
        if isinstance(d, datetime):
            d = d.astimezone(state.tz)
        return dates.md(d) if d else ""

    def time12(v):
        d = _parse(v) if isinstance(v, str) else v
        return dates.time12(d.astimezone(state.tz)) if d else ""

    def nickname(key: str) -> str:
        return state.settings.nicknames.get(key, key)

    return {"wd_md_time": wd_md_time, "md": md, "time12": time12, "nickname": nickname}


#: The shared loader. Each app renders through one overlay of it, built in `create_app`, so
#: an app's filters (nicknames, time zone) stay its own even when tests build many apps in one
#: process -- and so the template cache survives between requests (an overlay per request
#: recompiles every template on every page).
ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(HERE / "templates")), autoescape=True)


def _env(request: Request) -> jinja2.Environment:
    return get_state(request).extra["env"]


def get_state(request: Request) -> AppState:
    return request.app.state.fridgesheet


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    conn = db.open_db(get_state(request).home)
    try:
        yield conn
    finally:
        conn.close()


def page_context(request: Request, conn: sqlite3.Connection) -> dict:
    state = get_state(request)
    r = refreshes.latest(conn)
    sources = sorted(json.loads(r["sources"]).items()) if r else []
    return {
        "request": request, "settings": state.settings, "now": state.now(), "refresh": r,
        "sources": [(k.upper() if k == "hac" else k.capitalize(), v) for k, v in sources],
        "last_run": (last_run := runs.latest(conn)), "last_run_what": runs.describe(last_run) if last_run else None,
        "students": students.visible(conn), "version": version(),
        "warnings": state.extra.get("warnings") or [],
        "job": state.jobs.current if state.jobs and state.jobs.current else None,
        "jobs": state.jobs is not None,
        "update": updates.cached(state),              # never a network call here: the last answer, or None
    }


def safe_pdf(state: AppState, path: str | None) -> Path | None:
    """The PDF a run or job produced, only if it is really ours: an existing file under the
    home folder or under the archive folder. Anything else is not served, whatever the row says."""
    if not path:
        return None
    p = Path(path)
    try:
        resolved = p.resolve(strict=True)
    except OSError:
        return None
    roots = [state.home.resolve()]
    if state.settings.sheets_archive:
        roots.append(Path(state.settings.sheets_archive).resolve())
    # is_file(), not just "it exists": a directory named sheet.pdf would otherwise reach
    # FileResponse and become a 500 instead of the 404 a path that is not our PDF deserves.
    if not (resolved.is_file() and resolved.suffix.lower() == ".pdf"):
        return None
    return resolved if any(resolved.is_relative_to(r) for r in roots) else None


def student_or_404(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    s = students.by_key(conn, key)
    if s is None or s["hidden"]:
        raise HTTPException(404, f"no student {key!r}")
    return s


def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


LOOPBACK = ("127.0.0.1", "::1")


def loopback(request: Request) -> bool:
    """This request came from a browser on this computer, not the LAN -- the OneLogin
    password field (and a posted password) is gated on this, never on `testclient`."""
    return bool(request.client) and request.client.host in LOOPBACK


_WILDCARD_HOSTS = ("0.0.0.0", "::")


def served_url(settings: Settings) -> str:
    """A URL this app is actually listening on, for the Host refusal to point the parent at.

    Loopback for the default bind and for a wildcard one (which answers there as well as
    everywhere else); otherwise the concrete address `Settings.bind_host` resolved to -- under
    `FRIDGESHEET_WEB_HOST=192.168.1.42` uvicorn binds *that instead of* loopback, so advertising
    127.0.0.1 there would hand the parent a dead link at the moment they are most lost. An IPv6
    literal is bracketed, or the port reads as one more group of the address."""
    bind = settings.bind_host
    host = "127.0.0.1" if not bind or bind in _WILDCARD_HOSTS else bind
    if ":" in host:
        host = f"[{host}]"
    return f"http://{escape(host, quote=True)}:{settings.web_port}/"


def _allowed_hosts(settings: Settings) -> set[str]:
    """The `Host` *names* a legitimate request may carry: loopback, always; plus
    `settings.bind_host` -- the address this app is actually bound to, which already accounts
    for `allow_lan` *and* an explicit `FRIDGESHEET_WEB_HOST` pin winning over it (see
    `Settings.bind_host`). A concrete bind (including a `FRIDGESHEET_WEB_HOST` pin to one specific
    address) is admitted outright: it is precisely the address this app is served on, the same
    reasoning that admits loopback in the first place.

    Under a wildcard bind this carries loopback plus whatever the parent listed in
    `[web] extra_hosts`, and nothing else -- addresses are admitted by rule in `_host_allowed`
    rather than by membership here. This set is the name-based half, which is the half that has
    to stay a closed list, because a name is what a rebinding attacker controls.

    This used to probe and memoise the machine's LAN address so it could be admitted by name.
    That is gone: the probe could only ever return one address (whichever the default route
    used), which is what left a tailnet client refused while the app was listening on the
    tailnet interface the whole time, and the memo it needed to avoid probing per-request could
    never invalidate. `actions.lan_url` still exists for the Settings page's QR code, where
    naming one convenient address is exactly the right thing. #38."""
    hosts = {"127.0.0.1", "localhost", "::1"}
    bind = settings.bind_host
    if bind in _WILDCARD_HOSTS:
        hosts.update(settings.web_extra_hosts)
    else:
        hosts.add(bind.lower())    # `urlsplit` lowercases the incoming Host; match it here too
    return hosts


def _is_ip_literal(hostname: str) -> bool:
    """Whether `hostname` is a bare IP address rather than a name.

    `urlsplit` has already unbracketed an IPv6 literal by the time this sees it. A scoped
    literal (`fe80::1%eth0`) is rejected: `ip_address` will not parse one, and there is no
    reason a browser should ever put a zone ID in a `Host` header."""
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _host_allowed(host_header: str | None, settings: Settings) -> bool:
    """Whether `host_header` (the request's raw `Host` header) is an address this app is
    actually served on. A `Host` may or may not carry a port; when it does, it must be the
    configured one. The hostname is compared case-insensitively (`urlsplit` lowercases it),
    and IPv6 literals arrive bracketed (`[::1]:8433`), which `urlsplit` also unpacks. A `Host`
    is an authority with no userinfo component -- `urlsplit` will still parse one out of
    `evil.example@127.0.0.1` and hand back the hostname after the `@`, so one is rejected
    outright rather than trusted to mean nothing.

    Under a **wildcard bind**, any IP literal is admitted. That reads alarming and is not: the
    attack this check exists to stop is DNS rebinding, and rebinding is an attack on *names*.
    It works by pointing a name the attacker owns at an address they do not, so that the
    browser's same-origin policy -- which compares the *name* -- lets their page read our
    responses. A request whose `Host` is a bare address cannot be that: the attacker's page
    would have to be served from that same address to have an origin that matches, and if it
    were, they are already inside. `evil.example` is still refused; so is every other name that
    is not loopback, the bound address, or one the parent listed in `[web] extra_hosts`.

    This replaces admitting only the single probed LAN address, which could not work on a
    machine with more than one -- a desktop on both a house network and a tailnet answers on
    both, and `actions.lan_url`'s probe can only ever name whichever one the default route
    happens to use. #38."""
    if not host_header:
        return False
    try:
        parsed = urlsplit(f"//{host_header}")
        port = parsed.port
    except ValueError:                     # a port that is not a port ("evil.example:x")
        return False
    if parsed.username is not None:        # "evil.example@127.0.0.1" is not this app's address
        return False
    if parsed.hostname is None:
        return False
    if port is not None and port != settings.web_port:
        return False
    if parsed.hostname in _allowed_hosts(settings):
        return True
    return settings.bind_host in _WILDCARD_HOSTS and _is_ip_literal(parsed.hostname)


def render(request: Request, conn: sqlite3.Connection, name: str, /, status_code: int = 200, **ctx) -> HTMLResponse:
    """Render a page; for an htmx request render only the template's `partial` block.

    The template name is positional-only, so a page may pass a context key called `name`
    (as one settings partial wanted to) without it landing on this parameter instead."""
    context = {**page_context(request, conn), **ctx}
    tmpl = _env(request).get_template(name)
    if is_htmx(request):
        block = tmpl.blocks.get("partial")
        if block is not None:
            return HTMLResponse("".join(block(tmpl.new_context(context))), status_code=status_code)
    return HTMLResponse(tmpl.render(context), status_code=status_code)


def render_partial(request: Request, conn: sqlite3.Connection, name: str, /, **ctx) -> HTMLResponse:
    """A standalone partial template (no page around it), for htmx swaps. The template name is
    positional-only: `**ctx` may carry a key called `name` and it goes to the template."""
    context = {**page_context(request, conn), **ctx}
    return HTMLResponse(_env(request).get_template(name).render(context))


def create_app(settings: Settings, *, home: Path | None = None, worker: bool = False) -> FastAPI:
    home = home or settings.home
    tz = ZoneInfo(settings.timezone)
    app = FastAPI(title="Fridge Sheet", docs_url=None, redoc_url=None, openapi_url=None)
    state = AppState(home=home, settings=settings, tz=tz, started_at=datetime.now(tz),
                     clock=lambda: datetime.now(tz))
    app.state.fridgesheet = state
    env = ENV.overlay()
    # `overlay()` copies the environment's __dict__ and replaces only `cache` and
    # `extensions`, so the overlay's `filters` IS the shared one: updating it in place would
    # write this app's nicknames and time zone into every other app in the process. Give the
    # overlay a dict of its own.
    env.filters = {**ENV.filters, **_filters(state)}
    state.extra["env"] = env
    if worker:
        from .jobs import Worker
        state.jobs = Worker(state)
        state.jobs.start()
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        # `base.html` declares the SVG icon, which every current browser prefers. This answers
        # the legacy path anyway: a 404 for it sat in the console of every page (#40 item 17),
        # and a kiosk that pins the tab asks here before it has parsed a single <link>.
        return FileResponse(HERE / "static" / "favicon.svg", media_type="image/svg+xml")

    # No login (spec section 8). Two checks, for two different attacks:
    #
    # 1. The Host check runs for *every* request, GET included. A DNS name that resolves to
    #    127.0.0.1 makes an attacker's page same-origin with this app once it's in the address
    #    bar, so a GET from it would otherwise come back with the whole page -- the parent's
    #    OneLogin username, the kids' names and grades, the LAN address. "Answer only to the
    #    addresses this app is actually served on" is method-agnostic; so is this check.
    # 2. The Origin-vs-Host comparison only matters on a write: a page on another site must
    #    not be able to POST to us from the parent's own browser. Our forms and htmx send
    #    nothing or same-origin; a request with neither header (a CLI, a test client) passes.
    #
    # The two refusals below deliberately say different things. An attacker never reads either
    # one; the only person who ever will is the parent who typed `http://dobby:8433/`, came in
    # over an SSH port-forward, or is on a multi-homed or VPN box where the LAN probe follows
    # the default route and names an address this machine is not reached at. Telling them
    # "cross-site" blames them for an attack they did not make and points nowhere, so the Host
    # refusal names the address that does work instead. Neither body echoes the header it
    # refused: that is attacker-controlled text on a page this app itself serves.
    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        host = request.headers.get("host")
        if not _host_allowed(host, settings):
            url = served_url(settings)
            return HTMLResponse(
                f"<p>Fridge Sheet only answers at <a href=\"{url}\">{url}</a> on this computer.</p>"
                "<p>Open that address on the computer running Fridge Sheet. To read it on a phone "
                "or tablet, tick <b>Allow other devices on this network</b> on the Settings page, "
                "restart Fridge Sheet, and use the address (or the QR code) shown there.</p>",
                status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            # Origin == Host is not enough on its own: an attacker domain whose DNS resolves
            # to 127.0.0.1 can make both headers say the same untrusted name -- but the Host
            # check above already caught that case, so this is purely the write-specific check.
            if (request.headers.get("sec-fetch-site") == "cross-site"
                    or (origin and urlsplit(origin).netloc != host)):
                return HTMLResponse("<p>Cross-site request refused.</p>", status_code=403)
        return await call_next(request)

    @app.get("/health")
    def health() -> JSONResponse:
        # No home path here: /health answers the LAN when allow_lan is on.
        return JSONResponse({"app": APP_NAME, "version": version(), "started_at": state.started_at.isoformat()})

    def not_found(request: Request) -> HTMLResponse:
        conn = db.open_db(home)
        try:
            return render(request, conn, "404.html", status_code=404, path=request.url.path)
        finally:
            conn.close()

    # Registered on Starlette's base HTTPException, not FastAPI's subclass: the exception
    # handler lookup walks the raised exception's own MRO, and a route with no matching path
    # raises the base class directly, so a handler keyed on the subclass would miss it.
    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException):
        if exc.status_code != 404:
            return await http_exception_handler(request, exc)
        return not_found(request)

    # A path that cannot be a row id (/items/abc) is a wrong address, not an API error:
    # the parent gets the 404 page, not FastAPI's 422 JSON. A bad form body is a different
    # mistake (ours, not the address bar's) and keeps the default answer.
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if all((e.get("loc") or ("",))[0] == "path" for e in exc.errors()):
            return not_found(request)
        return await request_validation_exception_handler(request, exc)

    from .routes import checkin, changes as change_routes, dashboard, diagnostics as diagnostics_routes, flags as flag_routes, jobs as job_routes, kid, notes as note_routes, reconcile as reconcile_routes, reports as report_routes, runs as run_routes, schedules as schedule_routes, settings as settings_routes, trends as trend_routes
    for r in (dashboard.router, checkin.router, kid.router, note_routes.router, flag_routes.router, reconcile_routes.router, change_routes.router, trend_routes.router, job_routes.router, run_routes.router, settings_routes.router, diagnostics_routes.router, report_routes.router, schedule_routes.router):
        app.include_router(r)
    return app


Db = Depends(get_db)
State = Depends(get_state)

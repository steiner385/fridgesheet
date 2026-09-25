"""The FastAPI application: state, the per-request database connection, page rendering.

`create_app(settings)` is the only constructor; the server (`server.py`), the tests
(`TestClient`) and part 2's jobs worker all go through it. Routes live in `routes/`, SQL in
`stores/`; this module owns what every page shares -- the header data and the rail.
"""
from __future__ import annotations

import ipaddress
import json
import re
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from html import escape
from importlib import metadata
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import unquote, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import jinja2
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import config, dates, late_rules
from ..config import Settings
from ..sources import SourcePrefs
from ..dates import parse_iso as _parse
from ..host import selfupdate
from . import actions, db, phrasing, staleness, tiers, updates, verdicts
from .actions import REPORT_KEY
from .stores import flags as flagstore, num, refreshes, runs, students

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
        server started from load_settings, because the process environment has not changed).

        The address this process is bound to is kept: a new port or LAN setting takes effect at
        the next start, and until then the Host check and the Settings QR code must describe
        the socket uvicorn actually holds -- including a `--host`/`--port` flag, which
        config.toml knows nothing about (#9)."""
        bound = self.settings
        if self.home == config.DEFAULT_HOME:
            s = config.load_settings()
        else:
            s = config.Settings(home=self.home)
            config.settings_from_doc(config.load_config_doc(self.home / "config.toml"), s)
        self.settings = replace(s, web_host=bound.bind_host, web_host_explicit=True, web_port=bound.web_port)
        # A changed time zone applies now, not at the next start (#4); a name that is not a
        # zone keeps the one in force rather than breaking every page.
        try:
            self.tz = ZoneInfo(self.settings.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            pass
        self.extra["env"].filters.update(_filters(self))

    def rules(self) -> late_rules.LateRules:
        """Re-read each call: the parent edits late-rules.toml (part 2's Settings page).

        A file the parent has just broken must not take every page down with it: fall back to
        the built-in default and carry the message into the header, where it is visible and
        fixable, and drop the warning again as soon as a later load parses.
        """
        try:
            rules = late_rules.load(self.home / "late-rules.toml", household=db.household(self.home))
        except late_rules.LateRulesError as e:
            self.extra["warnings"] = [str(e)]
            return late_rules.LateRules(late_rules.Rule(), [], [])
        self.extra["warnings"] = []
        return rules

    def warnings(self) -> list[str]:
        """What the header says is wrong with a hand-edited file: the late-rules.toml message
        `rules()` left in `extra["warnings"]`, plus every line of no-print-days.txt the sheet
        has to ignore (#147) -- re-read each page, like the rules, so the warning goes away
        the moment the file is fixed."""
        return list(self.extra.get("warnings") or []) + actions.no_print_days_problems(self.home)

    def sources(self) -> SourcePrefs:
        """Which gradebook is authoritative per kid and class. Read from settings, which
        Settings and the course-page control reload after they write config.toml."""
        return self.settings.sources

    def now(self) -> datetime:
        return self.clock()

    def days_ahead(self) -> int:
        """How far ahead "coming due" looks: the printed sheet's Days ahead setting (the
        open-work report's `days_ahead` option in config.toml), so the browser and the sheet
        draw the same line. The web pages used to hard-code 14 and silently disagree with a
        sheet the parent had set to 7."""
        return config.day_option(self.settings.report_config(REPORT_KEY).options, "days_ahead")

    def overdue_days(self) -> int:
        """How far past due a row can be and still count as fixable: the sheet's Overdue days,
        so "still fixable" on the web is what the sheet prints (#20)."""
        return config.day_option(self.settings.report_config(REPORT_KEY).options, "overdue_days")

    def window(self) -> dict:
        """Both, as keyword arguments for the item store: every page that says "still
        fixable" or "coming due" passes these, so none of them falls back to a default."""
        return {"days_ahead": self.days_ahead(), "overdue_days": self.overdue_days()}


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

    def tier_of(key: str) -> str:
        return tiers.for_student(state.settings, key)

    def phrase(word, tier: str = "") -> str:
        # Stays a plain `str` -- autoescaped like everything else. `phrasing.phrase` echoes
        # an untranslated `word` straight back, and `v.grade` can be Canvas's own grade
        # string (`stores/items.py::_score`, `o["grade"]`) when there is no numeric score:
        # external text, not vocabulary. Marking this safe would let that text carry markup
        # into the page unescaped. `tests/test_web_tier_wording.py` pins the escaped output.
        return phrasing.phrase(str(word or ""), tier)

    def wd_md(v):
        """"Thu 9/17". A plain date ("2026-09-17" or a `date`) has no time of day, so nothing
        is converted between zones; a timestamp is moved into the app's zone first."""
        if isinstance(v, str):
            v = datetime.fromisoformat(v) if "T" in v else date.fromisoformat(v)
        if isinstance(v, datetime):
            v = v.astimezone(state.tz)
        return dates.wd_md(v) if v else ""

    def due_at(item, tier: str = "") -> str:
        """The hour an item is due, as this reader meets it: "morning" / "evening" for the
        early tier, "7:20am" / "11:59pm" otherwise, "" when nobody gave an hour. One choice
        for the work list, the check-in card, the question card and the step form, so the
        same item cannot say "evening" on one and "11:59pm" on the next (kids' UX audit F10).
        Both are facts the item already holds (`stores/items.py`); this only picks."""
        return (item.due_part if tier == "early" else item.due_time) or ""

    def mailto_body(item) -> str:
        """The facts a parent cites when writing to a teacher, as plain text (#73), in the
        record's own words (`record.*`, the adult tier: the teacher is the reader)."""
        def score(o):
            if o["score"] is None:
                return ""
            return f"{num(o['score'])} of {num(item.points)}" if item.points else num(o["score"])
        c, h = item.canvas, item.hac
        lines = [f"Assignment: {item.name} ({item.course_short})"]
        if item.due:
            lines.append("Due: " + wd_md(item.due) + (f" {item.due_time}" if item.due_time else ""))
        if c is not None:
            if c["missing"]:
                said = verdicts.words("record.missing", "")
            elif c["submitted_at"]:
                said = verdicts.words("record.handed_in_late" if c["late"] else "record.handed_in", "", {"when": wd_md_time(c["submitted_at"])})
            else:
                said = verdicts.words("record.offline" if item.kind in ("paper", "in class") else "record.nothing", "")
            lines.append("Canvas: " + ", ".join(x for x in (said, score(c)) if x))
        if h is not None:
            lines.append("HAC: " + (score(h) or verdicts.words("record.no_grade", "")))
        if item.canvas_path:
            lines.append(state.settings.canvas_base + item.canvas_path)
        return "\n".join(lines)

    @jinja2.pass_context
    def printer_name(_ctx, report_key: str) -> str:
        """The printer a Print of this report will use, for its confirmation (#127). The same
        `Settings.printer_for` the runner prints with -- never `settings.printer` alone, which a
        report's own printer overrides. `pass_context` is only there to stop Jinja folding
        `'open-work' | printer_name` into a constant when the template compiles: the answer
        changes whenever Settings or Schedules is saved."""
        return state.settings.printer_for(report_key) or "the default printer"

    return {"wd_md_time": wd_md_time, "md": md, "time12": time12, "nickname": nickname, "printer_name": printer_name,
            "wd_md": wd_md, "trigger_words": runs.trigger_label, "tier_of": tier_of, "phrase": phrase,
            "say": lambda key, tier, values=None: verdicts.say(key, tier, values),
            "words": lambda key, tier, values=None: verdicts.words(key, tier, values),
            # A flag in family words (`phrasing.FLAG_LABELS`, #129): `'ignore' | flag_label('state', tier)`.
            "flag_label": lambda flag, form="state", tier="": phrasing.flag_label(flag or "", form, tier),
            "standing": lambda item, tier: verdicts.standing(item, tier),
            "has_phrase": verdicts.has_phrase, "mailto_body": mailto_body, "num": num, "due_at": due_at,
            "pace_key": verdicts.pace_key}


#: The shared loader. Each app renders through one overlay of it, built in `create_app`, so
#: an app's filters (nicknames, time zone) stay its own even when tests build many apps in one
#: process -- and so the template cache survives between requests (an overlay per request
#: recompiles every template on every page).
ENV = jinja2.Environment(loader=jinja2.FileSystemLoader(str(HERE / "templates")), autoescape=True)
ENV.globals["FLAG_CHOICES"] = flagstore.CHOICES          # the detail card's flag menu (#3)
ENV.globals["request_key"] = lambda: str(uuid4())      # one token per rendered card (spec 6.3)


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


def question_counts(conn: sqlite3.Connection, state) -> dict[str, int]:
    """How many questions each kid has, for the rail. This runs every verdict for every kid on
    every page render: fine at household scale (tens of items per kid). If it ever shows up in
    a profile, cache it per refresh id."""
    from .stores import items as items_store
    out = {}
    for s in students.visible(conn):
        views = items_store.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", prefs=state.sources())
        out[s["key"]] = sum(1 for v in views if v.asks)
    return out


def here(request: Request) -> str:
    """The page the person is looking at, as a same-site path: for an htmx partial, the page
    htmx says it was requested from; otherwise this request's own path. Links that leave for a
    form (planning a step) carry it as `return_to`, so saving comes back here."""
    current = request.headers.get("HX-Current-URL")
    if current:
        u = urlsplit(current)
        return u.path + (f"?{u.query}" if u.query else "")
    return request.url.path + (f"?{request.url.query}" if request.url.query else "")


_SNEAKY = re.compile(r"[\s\x00-\x1f\x7f\\]")


def safe_return(raw: str | None) -> str | None:
    """`raw` if it is a path on this site, else None: never another host, a scheme, or a
    protocol-relative `//host`. Browsers read "\\" as "/" and drop tabs and newlines from a
    Location header, so "/\\evil" or "/<tab>/evil" would become "//evil" and leave the site:
    raw whitespace, control characters and backslashes are refused outright, and so is
    anything that turns into "//" once percent-decoded and normalised the way a browser would."""
    if not raw or _SNEAKY.search(raw):
        return None
    u = urlsplit(raw)
    if u.scheme or u.netloc or not u.path.startswith("/") or u.path.startswith("//"):
        return None
    normalised = _SNEAKY.sub(lambda m: "/" if m.group(0) == "\\" else "", unquote(raw))
    if normalised.startswith("//"):
        return None
    return raw


def page_context(request: Request, conn: sqlite3.Connection) -> dict:
    state = get_state(request)
    r = refreshes.latest(conn)
    sources = sorted(json.loads(r["sources"]).items()) if r else []
    return {
        "request": request, "settings": state.settings, "now": state.now(), "refresh": r,
        "sources": [(k.upper() if k == "hac" else k.capitalize(), v) for k, v in sources],
        "last_run": (last_run := runs.latest(conn)), "last_run_what": runs.describe(last_run) if last_run else None,
        "students": students.visible(conn), "version": version(),
        "warnings": state.warnings(),
        "job": state.jobs.current if state.jobs else None,
        "jobs": state.jobs is not None,
        "update": updates.cached(state),              # never a network call here: the last answer, or None
        "staleness": staleness.check(conn, state.now()),
        "question_counts": question_counts(conn, state),
        "here": here(request),
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


class UnknownKid(HTTPException):
    """A 404 whose page names the kid: `/changes?kid=nobody` is a real page asked about a kid
    it doesn't know, and "/changes is not a page here." blamed the address instead (#150)."""

    def __init__(self, key: str):
        super().__init__(404, f"no student {key!r}")
        self.message = f"No kid called “{key}” is known here."


def student_or_404(conn: sqlite3.Connection, key: str) -> sqlite3.Row:
    s = students.by_key(conn, key)
    if s is None or s["hidden"]:
        raise UnknownKid(key)
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


#: A DNS-style name and nothing else: labels of letters, digits, hyphens (and the underscore
#: Windows computer names allow), joined by dots. This is what a refused `Host` must match
#: before `host_refusal` will show it back -- see there for why that is safe.
_PLAIN_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?)*$")


def _refused_name(host_header: str | None, settings: Settings) -> str | None:
    """The plain name a refused `Host` carried, when that name is the whole reason it was
    refused: a wildcard bind (other devices already allowed), the right port, and a hostname
    that is a name rather than an address. Anything else -- LAN off, wrong port, an IP literal
    (which a wildcard bind admits anyway), a string with any character a name cannot have --
    is `None`, and the refusal says nothing about the header."""
    if not host_header or settings.bind_host not in _WILDCARD_HOSTS:
        return None
    if any(c in host_header for c in "/?#"):
        return None
    try:
        parsed = urlsplit(f"//{host_header}")
        port = parsed.port
    except ValueError:
        return None
    name = (parsed.hostname or "").lower()
    if parsed.username is not None or port not in (None, settings.web_port):
        return None
    if not name or len(name) > 253 or _is_ip_literal(name) or not _PLAIN_NAME.match(name):
        return None
    return name


def host_refusal(settings: Settings, host_header: str | None) -> str:
    """The body of the Host-check 403. Nobody hostile ever reads it; the person who does is the
    parent who typed `http://dobby:8433/`, so it has to say what actually gets them in (#149).

    With other devices *not* allowed, that is the Settings tick. With it already on, a name is
    still refused (a name is what a DNS-rebinding attacker controls, so names are a closed
    list), and telling the parent to tick the box they just ticked sends them in a circle: the
    way in is `[web] extra_hosts`, and the page shows the exact line.

    That line is the one place a refused `Host` is shown back, and only through
    `_refused_name`: a string of letters, digits, dots and hyphens on the right port under a
    wildcard bind. Such a string cannot carry markup, a URL or a sentence -- it is exactly the
    TOML value the parent has to type, and the only person who will ever read it is the one who
    typed that name into their own address bar. It is escaped anyway. Everything else about the
    header is still never echoed; see `test_the_two_refusals_say_two_different_things`."""
    url = served_url(settings)
    lead = f"<p>Fridge Sheet only answers at <a href=\"{url}\">{url}</a> on this computer.</p>"
    if settings.bind_host not in _WILDCARD_HOSTS:
        return lead + (
            "<p>Open that address on the computer running Fridge Sheet. To read it on a phone "
            "or tablet, tick <b>Allow other devices on this network</b> on the Settings page, "
            "restart Fridge Sheet, and use the address (or the QR code) shown there.</p>")
    name = _refused_name(host_header, settings)
    config_path = escape(str(settings.home / "config.toml"))
    if name is None:
        return lead + (
            "<p>Other devices on this network are already allowed: use the address (or the QR code) "
            f"shown on the Settings page, with port {settings.web_port}. A computer name is only "
            f"accepted once it is listed under <code>[web] extra_hosts</code> in <code>{config_path}</code>.</p>")
    return lead + (
        "<p>Other devices on this network are already allowed, but a computer name is only accepted "
        f"once it is listed. To use <code>{escape(name)}</code>, add it to <code>extra_hosts</code> under "
        f"<code>[web]</code> in <code>{config_path}</code>, then restart Fridge Sheet:</p>"
        f"<pre>[web]\nextra_hosts = [\"{escape(name)}\"]</pre>"
        "<p>If a <code>[web]</code> heading is already there (it is, once other devices are allowed), "
        "put the <code>extra_hosts</code> line under it rather than adding a second heading. "
        "Or use the address (or the QR code) shown on the Settings page instead of a name.</p>")


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
    if any(c in host_header for c in "/?#"):   # `urlsplit` would end the authority there (#9)
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
    # Resolved once, here, at startup -- not from the /diagnostics route. `resolve_pending`
    # archives the breadcrumb on success (renames update-pending.json to update-last.json),
    # so calling it from a GET would make the page mutate state and hand the one-time verdict
    # to whoever loads /diagnostics first, leaving a second visitor (or a refresh) with
    # nothing to see. The spec asks the *next start* to read it, which is exactly this line;
    # the route below only reads what is stashed here.
    state.extra["last_update"] = selfupdate.resolve_pending(home, updates.current_version())
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
    # refusal names the address that does work instead (`host_refusal`). Neither body echoes
    # the header it refused -- attacker-controlled text on a page this app itself serves --
    # with the one narrow exception `host_refusal` documents: a plain name under a wildcard
    # bind, shown as the `extra_hosts` line that admits it (#149).
    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        host = request.headers.get("host")
        if not _host_allowed(host, settings):
            return HTMLResponse(host_refusal(settings, host), status_code=403)
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
    def health(request: Request) -> JSONResponse:
        # No home path here: /health answers the LAN when allow_lan is on. The version is for
        # this machine only (the launcher and the updater ask from loopback): on the network
        # it would say which known bugs this copy has (#3).
        body = {"app": APP_NAME, "started_at": state.started_at.isoformat()}
        if loopback(request):
            body["version"] = version()
        return JSONResponse(body)

    def not_found(request: Request, message: str | None = None) -> HTMLResponse:
        conn = db.open_db(home)
        try:
            return render(request, conn, "404.html", status_code=404, path=request.url.path, message=message)
        finally:
            conn.close()

    # Registered on Starlette's base HTTPException, not FastAPI's subclass: the exception
    # handler lookup walks the raised exception's own MRO, and a route with no matching path
    # raises the base class directly, so a handler keyed on the subclass would miss it.
    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException):
        if exc.status_code != 404:
            return await http_exception_handler(request, exc)
        return not_found(request, getattr(exc, "message", None))

    # A path that cannot be a row id (/items/abc) is a wrong address, not an API error:
    # the parent gets the 404 page, not FastAPI's 422 JSON. A bad form body is a different
    # mistake (ours, not the address bar's) and keeps the default answer.
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if all((e.get("loc") or ("",))[0] == "path" for e in exc.errors()):
            return not_found(request)
        return await request_validation_exception_handler(request, exc)

    from .routes import checkin, changes as change_routes, dashboard, diagnostics as diagnostics_routes, flags as flag_routes, jobs as job_routes, kid, notes as note_routes, open as open_routes, questions as question_routes, reconcile as reconcile_routes, reports as report_routes, runs as run_routes, schedules as schedule_routes, settings as settings_routes, trends as trend_routes
    for r in (dashboard.router, checkin.router, kid.router, open_routes.router, note_routes.router, flag_routes.router, question_routes.router, reconcile_routes.router, change_routes.router, trend_routes.router, job_routes.router, run_routes.router, settings_routes.router, diagnostics_routes.router, report_routes.router, schedule_routes.router):
        app.include_router(r)
    return app


Db = Depends(get_db)
State = Depends(get_state)

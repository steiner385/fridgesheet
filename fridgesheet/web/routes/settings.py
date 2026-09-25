"""Settings: everything config.toml holds, the two editable files, the network toggle."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..app import Db, State, loopback, render, render_partial
from .. import actions, updatepin, updates
from .jobs import _worker
from ... import config, host, qr, runner, sources
from ...host import selfupdate_linux

router = APIRouter()
log = logging.getLogger("fridgesheet.web.settings")

#: What the Updates card says instead of a button off Windows (#145): a Linux install is a
#: source checkout, and `selfupdate_linux.NOT_WINDOWS` is what the route would answer anyway.
LINUX_UPDATE_HOW = ("Updating from this page is only for the Windows install. Here, update the checkout with "
                    "`git pull && pip install -e .` and restart the service.")


def _lan_qr(lan_url: str | None) -> str | None:
    """The QR beside the LAN URL. A drawing failure is a lost convenience, never a reason to
    take the whole Settings page down -- the page is where a parent fixes everything else."""
    if lan_url is None:
        return None
    try:
        return qr.svg(lan_url)
    except Exception:  # noqa: BLE001  same posture as printer_names: degrade, don't fail the page
        log.exception("could not draw the LAN QR code")
        return None


def _tailnet_url(port: int) -> str | None:
    """The tailnet address, shown only when there is one. A machine on both a house network
    and a tailnet answers on both, but `lan_url`'s probe can only name whichever the default
    route uses -- so without this the other address is served and never mentioned. #38.

    Swallows everything for the same reason `_lan_qr` does: a network probe is a convenience,
    and Settings is the page a parent goes to when nothing else works."""
    try:
        return actions.tailnet_url(port)
    except Exception:  # noqa: BLE001
        log.exception("could not probe the tailnet address")
        return None


def config_problem(state, e: config.ConfigError) -> str:
    """The line a page shows for a config.toml that does not read (#144). `e` already names
    the file and the setting (`[reports.open-work] time must be HH:MM ...`); this adds what to do."""
    return (f"config.toml could not be read: {e}. Fix that setting in {state.home / 'config.toml'} "
            "with a text editor, then reload this page.")


def _update_gate(state, update) -> tuple[bool, str]:
    """Whether the update button may be offered, and if not, the line that says why.

    The refusals that keep the button from starting something it can already predict will
    go wrong -- see `_update_button.html`. Shared by the page and by the "check now" swap,
    so a check that finds a release offers (or declines) the button under the same rules
    a fresh page load would. The platform comes right after the checkbox (#145): `POST
    /settings/update` answers 409 off Windows whatever else is set, so on Linux no PIN would
    help and the card says how a checkout updates instead. `info.installed` is only asked
    for once the earlier guards pass: on most machines and most page loads (checks off,
    Linux, or no PIN set yet) that avoids a real `systemctl --user`/`schtasks` shell-out for
    a question the page was not going to act on anyway."""
    reason = ""
    if not state.settings.web_check_updates:
        reason = "Update checks are turned off."
    elif not host.IS_WINDOWS:
        reason = LINUX_UPDATE_HOW
    elif not state.settings.web_update_pin_hash:
        reason = "Set an update PIN below to update from this page."
    else:
        describe_service = state.extra.get("describe_service")
        if describe_service is None:
            from ...host.service import describe_service
        if not describe_service().installed:
            reason = ("Fridge Sheet is not set up to start on its own on this computer, so an "
                      "update could leave it closed. Install it again from the desktop shortcut "
                      "first (issue #39).")
    return bool(update and update.available and not reason), reason


def _page(request, conn, state, form, messages=(), errors=()):
    # The port this process answers on, not the one config.toml holds for the next start (#9).
    port = state.settings.web_port
    # `form` is None when config.toml does not read (#144): the page still renders, with the
    # error, and without a form whose placeholders a Save would write over the parent's file.
    allow_lan = form.allow_lan if form is not None else state.settings.web_allow_lan
    lan_url = actions.lan_url(port) if allow_lan else None
    # The one network call the page makes that is not to a school system: once a day, cached
    # on the app, off with the checkbox. Other pages only ever read the cache (app.page_context).
    update = updates.check(state, now=state.now())
    tailnet_url = _tailnet_url(port) if allow_lan else None
    update_ready, reason = _update_gate(state, update)
    try:
        source_rules = actions.load_sources(state.home).rules
    except config.ConfigError:
        source_rules = []                   # the same error is already on the page, from `form`
    skip_problems: list[str] = []
    entries = actions.no_print_days_view(actions.no_print_days_settings(state.home, skip_problems))
    return render(request, conn, "settings.html", current="settings", form=form, messages=list(messages), errors=list(errors),
                  printers=actions.printer_names(state.extra), loopback=loopback(request),
                  status=actions.status_line(state.home, now=state.now()),
                  lan_url=lan_url, lan_qr=_lan_qr(lan_url), tailnet_url=tailnet_url, about=actions.about_text(), update=update,
                  update_ready=update_ready, update_blocked_reason=reason, is_windows=host.IS_WINDOWS,
                  releases_page=updates.RELEASES_PAGE, linux_update_how=LINUX_UPDATE_HOW,
                  late_rules=actions.late_rules_view(actions.late_rules_settings(state.home)),
                  entries=entries, skip_problems=skip_problems, env_notes=actions.env_overrides(),
                  source_rules=source_rules, SOURCE_LABELS=sources.LABELS,
                  # "Where you are" (#122): a blank Time zone box means this computer's zone,
                  # so the page names it -- or says it could not be read and what is assumed.
                  local_tz=host.local_timezone(), fallback_tz=host.FALLBACK_TIMEZONE, zones=actions.US_ZONES)


@router.get("/settings")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    try:
        form = actions.load_form(state.home)
    except config.ConfigError as e:
        return _page(request, conn, state, None, errors=[config_problem(state, e)])
    return _page(request, conn, state, form)


@router.post("/settings")
def save(request: Request, username: str = Form(""), password: str = Form(""), printer: str = Form(""),
         days_ahead: str = Form("14"), overdue_days: str = Form("14"), nicknames: str = Form(""), archive: str = Form(""),
         port: str = Form("8433"), allow_lan: str | None = Form(None), check_updates: str | None = Form(None),
         update_pin: str = Form(""), clear_update_pin: str | None = Form(None),
         sources_assignments: str = Form("canvas"), sources_grades: str = Form("hac"),
         timezone: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    # The password used to be refusable unless the request came from loopback. That was
    # defensible when the app ran on the parent's own desktop and merely inconvenient over the
    # LAN -- but it is unsatisfiable on a headless host, where the account running the server
    # has no desktop session and so no browser that could ever be loopback. "Open Fridge Sheet
    # on the PC itself" was then an instruction nobody could follow, and the app could not be
    # set up at all.
    #
    # It also protected less than it looked. This app has no login by design (spec section 8):
    # every device the Host check admits can already read the kids' names, grades and the
    # OneLogin *username*, and start a refresh or a print. Refusing only the password field
    # stopped a parent configuring their own app; it did not stop anything an attacker on the
    # same network wanted, since setting a password grants them nothing they did not have.
    #
    # What is genuinely given up is confidentiality in transit: there is no HTTPS, so over the
    # LAN the password crosses the wire in the clear (over a tailnet it does not -- WireGuard
    # encrypts it). The page says so plainly rather than deciding for the parent. What does
    # *not* change is that the stored password is write-only: it is never rendered into the
    # form, never returned by any route, and a blank field keeps whatever is stored.
    form = actions.FormValues(username=username, password=password, printer=printer, days_ahead=days_ahead,
                              overdue_days=overdue_days, nicknames=nicknames, archive=archive,
                              port=port, allow_lan=bool(allow_lan), check_updates=bool(check_updates),
                              update_pin=update_pin, clear_update_pin=bool(clear_update_pin),
                              has_update_pin=bool(state.settings.web_update_pin_hash),
                              sources_assignments=sources_assignments, sources_grades=sources_grades,
                              timezone=timezone)
    lines: list[str] = []
    try:
        result = actions.save(form, home=state.home, log=lines.append, credstore=state.extra.get("credstore"))
    except config.ConfigError as e:         # a file that does not parse is not written over (#144)
        return _page(request, conn, state, None, errors=[config_problem(state, e)])
    if result.ok:
        try:
            state.reload()
            form = actions.load_form(state.home)
        except config.ConfigError as e:
            # Written, but config.toml has something the form does not own that no longer
            # reads (#4): say so on the page rather than a 500.
            return _page(request, conn, state, form, errors=[f"Saved, but the settings could not be re-read: {e}"])
        return _page(request, conn, state, form, messages=result.messages)
    return _page(request, conn, state, form, errors=result.messages)


@router.post("/settings/late-rules")
async def save_late_rules(request: Request, conn: sqlite3.Connection = Db, state=State):
    """The whole file is one form; row order in each array is the row order on the page, which
    is also the file's first-match-wins rule order -- so reordering rows before Save is enough,
    with no separate move/reorder endpoint needed."""
    actions.late_rules_settings(state.home)  # seed it first if this is its first touch; never overwrites
    form = await request.form()
    default_late_days = form.get("default_late_days", "")
    default_credit = form.get("default_credit", "")
    quarter_dates = [d for d in form.getlist("quarter_date") if d]
    rule_kid, rule_course = form.getlist("rule_kid"), form.getlist("rule_course")
    rule_mode, rule_late_days = form.getlist("rule_mode"), form.getlist("rule_late_days")
    rule_credit, rule_source = form.getlist("rule_credit"), form.getlist("rule_source")
    errors = actions.save_late_rules(
        state.home, default_late_days=default_late_days, default_credit=default_credit,
        quarter_dates=quarter_dates, rule_kid=rule_kid, rule_course=rule_course, rule_mode=rule_mode,
        rule_late_days=rule_late_days, rule_credit=rule_credit, rule_source=rule_source)
    if errors:
        rows = {"default_late_days": default_late_days, "default_credit": default_credit, "quarters": quarter_dates,
                "rules": [{"kid": k, "course": c, "mode": m, "late_days": d, "credit": cr, "source": s}
                          for k, c, m, d, cr, s in zip(rule_kid, rule_course, rule_mode, rule_late_days, rule_credit, rule_source)]}
    else:
        rows = actions.late_rules_view(actions.late_rules_settings(state.home))
    return render_partial(request, conn, "_late_rules_editor.html", late_rules=rows, errors=errors, saved=not errors)


@router.post("/settings/no-print-days")
async def save_no_print_days(request: Request, conn: sqlite3.Connection = Db, state=State):
    actions.no_print_days_settings(state.home)  # seed it first if this is its first touch; never overwrites
    form = await request.form()
    starts, ends, notes = form.getlist("start"), form.getlist("end"), form.getlist("note")
    entries: list[runner.SkipEntry] = []
    errors: list[str] = []
    left_out: list[str] = []
    for i, (s, e, note) in enumerate(zip(starts, ends, notes), start=1):
        if not s:
            # A row with no start date used to vanish on Save, note and all (#147). One that
            # says something is refused; one that says nothing (an "Add date" click never
            # filled in) is left out, and the page says so.
            if e or note.strip():
                errors.append(f"Row {i}: needs a start date.")
            else:
                left_out.append(f"Row {i} was empty and was left out.")
            continue
        try:
            entries.append(runner.SkipEntry(date.fromisoformat(s), date.fromisoformat(e) if e else None, note))
        except ValueError:
            errors.append(f"Row {i}: not a date (yyyy-mm-dd).")
    errors = errors or actions.save_no_print_days(state.home, entries)
    # After a Save the file is what the rows say, so it has no unreadable lines left; on an
    # error every typed row comes back, start date or not, so nothing typed is lost.
    rows = actions.no_print_days_view(actions.no_print_days_settings(state.home)) if not errors else \
        [{"start": s, "end": e, "note": n} for s, e, n in zip(starts, ends, notes)]
    return render_partial(request, conn, "_no_print_days_editor.html", entries=rows, errors=errors, saved=not errors,
                          notes=left_out if not errors else [], problems=[])


@router.post("/settings/update/check")
def check_for_updates_now(request: Request, conn: sqlite3.Connection = Db, state=State):
    """A parent's own "check now" click -- skips the once-a-day cache, but still honours the
    checkbox: refused, not a fetch, when the parent turned checks off (see `updates.check`)."""
    if not state.settings.web_check_updates:
        raise HTTPException(409, "Update checks are turned off in Settings.")
    update = updates.check(state, now=state.now(), force=True)
    # The status line, plus the update button block swapped out of band: a check that finds
    # a release used to leave the parent reloading the page to get the form it had just
    # earned. Same guards as the page (`_update_gate`), not a shortcut around them.
    update_ready, reason = _update_gate(state, update)
    return render_partial(request, conn, "_update_check.html", update=update,
                          update_ready=update_ready, update_blocked_reason=reason, is_windows=host.IS_WINDOWS,
                          releases_page=updates.RELEASES_PAGE, linux_update_how=LINUX_UPDATE_HOW)


@router.post("/settings/update")
def start_update(request: Request, pin: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """The only way to start an "update" job -- see `jobs.GATED`. `POST /jobs/update` (the
    generic, unauthenticated route) is refused a kind ahead of ever reaching a worker; this
    route is the PIN-gated door for it, and every check below runs before `_worker` is even
    asked for, so none of them can be skipped by a caller that races the worker into existing.
    """
    if not state.settings.web_check_updates:
        # The parent turned off this app's one outbound call (Settings' check_updates box).
        # A button here must not quietly put it back regardless of what it is gating.
        raise HTTPException(409, "Update checks are turned off in Settings.")
    if not host.IS_WINDOWS:
        # Refused here, before the PIN is even checked or a job is submitted -- not left for
        # `actions.self_update` (which also refuses, belt-and-braces) to discover after a
        # download. A Linux install is a git checkout; no button here can improve on that.
        raise HTTPException(409, selfupdate_linux.NOT_WINDOWS)
    stored = state.settings.web_update_pin_hash
    if not stored:
        raise HTTPException(403, "Set an update PIN in Settings before updating from here.")
    attempts = state.extra.setdefault("update_attempts", updatepin.Attempts())
    until = attempts.locked_until(state.now())
    if until is not None:
        raise HTTPException(429, "Too many wrong PINs. Try again in 15 minutes.")
    # Trimmed, as `actions.save` trimmed it before hashing (#145): a phone keyboard's trailing
    # space must not fail the check and count towards the lockout.
    if not updatepin.verify(pin.strip(), stored):
        attempts.record_failure(state.now())
        raise HTTPException(403, "That PIN is not right.")
    attempts.clear()
    w = _worker(state)
    job = w.submit("update")
    if job is None:
        r = render_partial(request, conn, "_job.html", job=w.current, busy=True, pdf=None)
        r.status_code = 409
        return r
    return render_partial(request, conn, "_job.html", job=job, busy=False, pdf=None)


@router.post("/settings/sources/remove")
def remove_source(kid: str = Form(""), course: str = Form(""), state=State):
    actions.remove_source_rule(state.home, kid, course)
    state.reload()
    return RedirectResponse("/settings", status_code=303)

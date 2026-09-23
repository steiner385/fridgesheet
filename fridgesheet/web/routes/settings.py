"""Settings: everything config.toml holds, the two editable files, the network toggle."""
from __future__ import annotations

import logging
import sqlite3
from datetime import date

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, loopback, render, render_partial
from .. import actions, updatepin, updates
from .jobs import _worker
from ... import host, qr, runner
from ...host import selfupdate_linux

router = APIRouter()
log = logging.getLogger("fridgesheet.web.settings")


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


def _page(request, conn, state, form, messages=(), errors=()):
    # The status line's `describe` comes from `state.extra["scheduling"]` when one is there --
    # the same seam `schedules.rows` uses. Without it every /settings render shells out to the
    # real `systemctl --user`, and a page test asserts on whatever this machine's own systemd
    # says rather than on its fake.
    lan_url = actions.lan_url(form.port) if form.allow_lan else None
    # The one network call the page makes that is not to a school system: once a day, cached
    # on the app, off with the checkbox. Other pages only ever read the cache (app.page_context).
    update = updates.check(state, now=state.now())
    tailnet_url = _tailnet_url(form.port) if form.allow_lan else None
    # The two refusals that keep the update button from starting something it can already
    # predict will go wrong -- see `_update_button.html`. `info.installed` is only asked for
    # once the first two guards pass: on most machines and most page loads (checks off, or no
    # PIN set yet) that avoids a real `systemctl --user`/`schtasks` shell-out for a question
    # the page was not going to act on anyway.
    reason = ""
    if not state.settings.web_check_updates:
        reason = "Update checks are turned off."
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
    update_ready = bool(update and update.available and not reason)
    return render(request, conn, "settings.html", current="settings", form=form, messages=list(messages), errors=list(errors),
                  printers=actions.printer_names(state.extra), loopback=loopback(request),
                  status=actions.status_line(state.home, describe=getattr(state.extra.get("scheduling"), "describe", None)),
                  lan_url=lan_url, lan_qr=_lan_qr(lan_url), tailnet_url=tailnet_url, about=actions.about_text(), update=update,
                  update_ready=update_ready, update_blocked_reason=reason,
                  late_rules=actions.late_rules_view(actions.late_rules_settings(state.home)),
                  entries=actions.no_print_days_view(actions.no_print_days_settings(state.home)))


@router.get("/settings")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _page(request, conn, state, actions.load_form(state.home))


@router.post("/settings")
def save(request: Request, username: str = Form(""), password: str = Form(""), printer: str = Form(""),
         days_ahead: str = Form("14"), overdue_days: str = Form("14"), nicknames: str = Form(""), archive: str = Form(""),
         port: str = Form("8433"), allow_lan: str | None = Form(None), check_updates: str | None = Form(None),
         update_pin: str = Form(""), conn: sqlite3.Connection = Db, state=State):
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
                              update_pin=update_pin)
    lines: list[str] = []
    result = actions.save(form, home=state.home, log=lines.append, credstore=state.extra.get("credstore"))
    if result.ok:
        state.reload()
        form = actions.load_form(state.home)
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
    for i, (s, e, note) in enumerate(zip(starts, ends, notes), start=1):
        if not s:
            continue
        try:
            entries.append(runner.SkipEntry(date.fromisoformat(s), date.fromisoformat(e) if e else None, note))
        except ValueError:
            errors.append(f"Row {i}: not a date (yyyy-mm-dd).")
    errors = errors or actions.save_no_print_days(state.home, entries)
    rows = actions.no_print_days_view(actions.no_print_days_settings(state.home)) if not errors else \
        [{"start": s, "end": e, "note": n} for s, e, n in zip(starts, ends, notes) if s]
    return render_partial(request, conn, "_no_print_days_editor.html", entries=rows, errors=errors, saved=not errors)


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
    if not updatepin.verify(pin, stored):
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

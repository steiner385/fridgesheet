"""Schedules: one row per report, days and a time, a printer or PDF only."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ... import host
from .. import actions, schedules
from ..app import Db, State, render

router = APIRouter()

DAYS = host.DAY_NAMES


def _printer_options(printers: list[str], current: str) -> list[tuple[str, str, bool]]:
    """(value, label, selected) for one row's printer `<select>`.

    If the row's stored printer is not in the offered list -- removed from CUPS, or the list
    could not be read at all -- it is still offered, selected, and labelled as missing. Without
    this, the browser falls back to selecting "(the printer on the Settings page)" and an
    unrelated Save on that row silently blanks the printer the parent chose.
    """
    options = [(p, p, p == current) for p in printers]
    if current and current not in printers:
        options.append((current, f"{current} (not currently listed)", True))
    return options


def _page(request, conn, state, *, messages=(), errors=()):
    rows = schedules.rows(state.home, scheduling=state.extra.get("scheduling"))
    printers = actions.printer_names(state.extra)
    return render(request, conn, "schedules.html", current="schedules",
                  rows=rows, days=DAYS,
                  refresh=schedules.refresh_row(state.home, scheduling=state.extra.get("scheduling")),
                  printer_options={r.key: _printer_options(printers, r.printer) for r in rows},
                  messages=list(messages), errors=list(errors))


@router.get("/schedules")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _page(request, conn, state)


@router.post("/schedules")
async def save(request: Request, conn: sqlite3.Connection = Db, state=State):
    """One row's form. `days` is a checkbox group, so it is read from the raw form rather than
    declared as a parameter -- FastAPI would give back only the last one."""
    form = await request.form()
    lines: list[str] = []
    out = schedules.save(
        form.get("key", ""),
        enabled=bool(form.get("enabled")),
        time=form.get("time", ""),
        days=[d for d in form.getlist("days") if d],
        printer=form.get("printer", ""),
        prints=bool(form.get("prints")),
        home=state.home, log=lines.append, scheduling=state.extra.get("scheduling"))
    if out.ok:
        state.reload()
    return _page(request, conn, state, messages=out.messages, errors=out.errors)


def _int_or(value, default: int) -> int:
    """A form field coerced the way every neighbouring field already is: a bad value falls
    back to the default rather than raising -- `int("")`/`int("junk")` would otherwise be a
    500 on a POST, where `start`/`end`/`days` all degrade instead of failing outright."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.post("/schedules/refresh")
async def save_refresh(request: Request, conn: sqlite3.Connection = Db, state=State):
    form = await request.form()
    out = schedules.save_refresh(
        enabled=bool(form.get("enabled")),
        every_hours=_int_or(form.get("every_hours"), 3),
        start=str(form.get("start") or "06:00"),
        end=str(form.get("end") or "21:00"),
        days=[str(d) for d in form.getlist("days")],
        home=state.home, log=lambda _m: None,
        scheduling=state.extra.get("scheduling"))
    state.reload()
    return _page(request, conn, state, messages=out.messages, errors=out.errors)

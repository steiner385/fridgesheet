"""Reset (2026-10-04): send one assignment, or a kid's whole plan, back to Needs you now, and
Undo it. Plain form POSTs that come back to the page they were made on with `?reset=<id>`, where
the notice with the one Undo is drawn (`app.page_context`, `_reset_notice.html`)."""
from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse

from ..app import Db, State, safe_return, student_or_404, with_reset
from ..stores import items, resets, students
from .. import db

router = APIRouter()


def _back(raw: str, fallback: str, reset_id: int | None = None) -> RedirectResponse:
    return RedirectResponse(with_reset(safe_return(raw) or fallback, reset_id), status_code=303)


@router.post("/items/{item_id}/reset")
def reset_item(item_id: int, return_to: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """One assignment triaged the wrong way: its open step and its answer go, and it asks again.
    A stale page's tap on work with nothing to take back records nothing and says nothing."""
    s = students.owner_of_item(conn, item_id)
    if s is None:
        raise HTTPException(404, "no such item")
    reset_id = resets.reset_items(conn, s["id"], [item_id], now=db.now_iso(state.tz))
    return _back(return_to, f"/kids/{quote(s['key'])}", reset_id)


@router.post("/kids/{key}/plan/reset")
def reset_plan(key: str, return_to: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """The kid's whole plan, after the page's confirm: every triaged row in the window."""
    s = student_or_404(conn, key)
    views = items.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", prefs=state.sources(), **state.window())
    reset_id = resets.reset_items(conn, s["id"], [v.id for v in resets.triaged(views)], now=db.now_iso(state.tz))
    return _back(return_to, f"/kids/{quote(key)}/plan", reset_id)


@router.post("/resets/{reset_id}/undo")
def undo(reset_id: int, return_to: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """Put a reset back. A second tap (a double-click, Back) finds it undone and changes nothing."""
    r = resets.one(conn, reset_id)
    if r is None:
        raise HTTPException(404, "no such reset")
    resets.undo(conn, r["student_id"], reset_id, now=db.now_iso(state.tz))
    s = conn.execute("SELECT key FROM students WHERE id = ?", (r["student_id"],)).fetchone()
    return _back(return_to, f"/kids/{quote(s['key'])}")

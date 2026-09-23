"""Questions: answer one, undo an answer (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md)."""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..app import Db, State, render, render_partial
from ..stores import flags, items, students
from .. import db

router = APIRouter()
ANSWERS = set(flags.FLAGS) | {"confirm", "clear"}
_SLOT = re.compile(r"q[cd]?-\d+")      # q- list card, qd- item detail, qc- check-in card


def _slot(raw: str, item_id: int) -> str:
    """The element id the card swaps into: the caller's, if it is one of ours, else the list's."""
    return raw if _SLOT.fullmatch(raw or "") else f"q-{item_id}"


def _view(conn, state, item_id):
    s = students.owner_of_item(conn, item_id)
    v = items.one(conn, s, item_id, now=state.now(), rules=state.rules(), prefs=state.sources()) if s is not None else None
    if v is None:
        raise HTTPException(404, "no such item")
    return s, v


def _apply(conn, item_id, answer, now):
    if answer in ("clear", ""):
        flags.clear(conn, item_id, now=now)
    elif answer == "confirm":
        flags.confirm(conn, item_id, now=now)
    else:
        flags.set_flag(conn, item_id, answer, now=now)


@router.post("/items/{item_id}/answer")
def answer(item_id: int, request: Request, answer: str = Form(...), prev: str = Form(""), prev_set_at: str = Form(""),
           slot: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    if answer not in ANSWERS:
        raise HTTPException(400, f"unknown answer {answer!r}")
    _view(conn, state, item_id)
    _apply(conn, item_id, answer, db.now_iso(state.tz))
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_answered.html", student=s, item=v, prev=prev, prev_set_at=prev_set_at,
                          slot=_slot(slot, item_id))


@router.post("/items/{item_id}/undo")
def undo(item_id: int, request: Request, prev: str = Form(""), prev_set_at: str = Form(""), slot: str = Form(""),
         conn: sqlite3.Connection = Db, state=State):
    """Put the item back as it was before the answer: the earlier flag with its original date
    (so a question the school raised comes back), or no flag at all."""
    if prev and prev not in flags.FLAGS:
        raise HTTPException(400, f"unknown flag {prev!r}")
    _view(conn, state, item_id)
    now = db.now_iso(state.tz)
    if prev and prev_set_at:
        flags.restore(conn, item_id, prev, set_at=prev_set_at, now=now)
    else:
        _apply(conn, item_id, prev or "clear", now)
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_question.html", student=s, item=v, slot=_slot(slot, item_id), undone=True)


@router.get("/questions")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    kid = request.query_params.get("kid") or None
    now, rules, prefs = state.now(), state.rules(), state.sources()
    groups = []
    for s in students.visible(conn):
        if kid and s["key"] != kid:
            continue
        views = items.list_items(conn, s, now=now, rules=rules, show="all", prefs=prefs)
        groups.append({
            "student": s,
            "questions": [v for v in views if v.asks],
            "asked": [v for v in views if v.verdict.kind == "asked"],
            "past_credit": [v for v in views if v.verdict.kind == "past_credit"],
            "twins": items.near_twins(conn, views),
        })
    return render(request, conn, "questions.html", current="questions", groups=groups, kid=kid)


@router.post("/questions/let-go")
def let_go(request: Request, kid: str = Form(...), conn: sqlite3.Connection = Db, state=State):
    """Ignore every one of one kid's past-credit items, after the page's confirm. One kid at a
    time: a button that hides a whole household's work in one click hides a problem."""
    s = next((s for s in students.visible(conn) if s["key"] == kid), None)
    if s is None:
        raise HTTPException(404, f"no student {kid!r}")
    now = db.now_iso(state.tz)
    for v in items.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", prefs=state.sources()):
        if v.verdict.kind == "past_credit":
            flags.set_flag(conn, v.id, "ignore", now=now, text="past the late-work window")
    return RedirectResponse(f"/questions?kid={kid}", status_code=303)

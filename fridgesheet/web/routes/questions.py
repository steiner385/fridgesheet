"""Questions: answer one, undo an answer (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md)."""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..app import Db, State, render, render_partial
from ..stores import flags, items, plans, students
from .. import db, phrasing, tiers, verdicts
from . import checkin

router = APIRouter()
ANSWERS = set(verdicts.ACTIONS)
_SLOT = re.compile(r"q[cd]?-\d+")      # q- list card, qd- item detail, qc- check-in card


def _slot(raw: str, item_id: int) -> str:
    """The element id the card swaps into: the caller's, if it is one of ours, else the list's."""
    return raw if _SLOT.fullmatch(raw or "") else f"q-{item_id}"


def _view(conn, state, item_id):
    s = students.owner_of_item(conn, item_id)
    v = items.one(conn, s, item_id, now=state.now(), rules=state.rules(), prefs=state.sources(), **state.window()) if s is not None else None
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


def _plan_step(conn, state, student, view, action: str, request_key: str) -> int:
    """A step from one tap, with the defaults the step form would have offered (spec 6.3)."""
    day = state.now().date() + (timedelta(days=1) if action == "plan:tomorrow" else timedelta(0))
    tier = tiers.for_student(state.settings, student["key"])
    said = [t for t in (view.flag_text, view.latest_note["body"] if view.latest_note else "") if t]
    values = dict(title=view.name, family_account="\n".join(said), next_step=phrasing.phrase("step.work_on_it", tier),
                  owner=state.settings.nicknames.get(student["key"], student["key"]), planned_for=day.isoformat(),
                  minutes=None, state="planned", position=10, evidence=plans.evidence(view), recorded_by="")
    return plans.save(conn, student["id"], values, now=db.now_iso(state.tz), request_key=request_key, item_id=view.id)


def _card(request, conn, state, item_id, slot, status_code=200, **extra) -> HTMLResponse:
    s, v = _view(conn, state, item_id)
    r = render_partial(request, conn, "_question.html", student=s, item=v, slot=_slot(slot, item_id), **extra)
    r.status_code = status_code
    return r


@router.post("/items/{item_id}/answer")
def answer(item_id: int, request: Request, answer: str = Form(...), prev: str = Form(""), prev_set_at: str = Form(""),
           slot: str = Form(""), request_key: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    if answer not in ANSWERS:
        raise HTTPException(400, f"unknown answer {answer!r}")
    s, v = _view(conn, state, item_id)
    if answer in verdicts.PLAN_ACTIONS:
        if not 1 <= len(request_key) <= 100:
            raise HTTPException(400, "a plan answer needs its request key")
        # A retried POST (double-click, flaky network) carries the key of the step it already
        # made: answer with that step again rather than refusing it as "already covered".
        earlier = plans.by_request_key(conn, s["id"], request_key)
        if earlier is not None and earlier["item_id"] == item_id:
            step_id = earlier["id"]
        elif v.step is not None:
            return _card(request, conn, state, item_id, slot, status_code=409)
        else:
            try:
                step_id = _plan_step(conn, state, s, v, answer, request_key)
            except plans.Conflict:
                return _card(request, conn, state, item_id, slot, status_code=409)
        s, v = _view(conn, state, item_id)
        ctx = checkin._context(conn, s, state)
        ctx.update(item=v, prev=prev, prev_set_at=prev_set_at, slot=_slot(slot, item_id),
                   step_id=step_id, planned=answer[len("plan:"):], plan_panel=True)
        return render_partial(request, conn, "_answered.html", **ctx)
    _apply(conn, item_id, answer, db.now_iso(state.tz))
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_answered.html", student=s, item=v, prev=prev, prev_set_at=prev_set_at,
                          slot=_slot(slot, item_id))


@router.post("/items/{item_id}/undo")
def undo(item_id: int, request: Request, prev: str = Form(""), prev_set_at: str = Form(""), slot: str = Form(""),
         step_id: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """Put the item back as it was before the answer: the earlier flag with its original date
    (so a question the school raised comes back), or no flag at all. For a plan answer, the
    step it created is deleted if nobody has edited it since (spec 6.4)."""
    if prev and prev not in flags.FLAGS:
        raise HTTPException(400, f"unknown flag {prev!r}")
    s, v = _view(conn, state, item_id)
    if step_id:
        if not step_id.isdigit():
            raise HTTPException(404, "no such step")
        step = plans.one(conn, s["id"], int(step_id))
        if step is None or step["item_id"] != item_id:
            raise HTTPException(404, "no such step")
        if step["revision"] == 1:
            plans.delete(conn, s["id"], step["id"])
        s, v = _view(conn, state, item_id)
        ctx = checkin._context(conn, s, state)
        ctx.update(item=v, slot=_slot(slot, item_id), undone=True, plan_panel=True)
        return render_partial(request, conn, "_question.html", **ctx)
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

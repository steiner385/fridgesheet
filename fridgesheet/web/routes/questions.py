"""Questions: answer one, undo an answer (docs/superpowers/specs/2026-09-23-questions-not-cases-design.md)."""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ... import dates
from ..app import Db, State, render, render_partial, student_or_404
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


def _already_planned(step) -> HTTPException:
    """htmx does not swap a 4xx body, so a refused tap is told in a short `detail` that the
    page shows next to the button (static/app.js), not in a re-rendered card nobody sees."""
    day = dates.wd_md(date.fromisoformat(step["planned_for"]))
    return HTTPException(409, f"Already in the plan for {day}. Open the plan to change it.")


def _planned_line(request, conn, state, s, v, *, slot, step_id, planned, **extra) -> HTMLResponse:
    """The done-line for a plan answer or its undo, with the plan panel out of band."""
    ctx = checkin._context(conn, s, state)
    ctx.update(item=v, slot=_slot(slot, v.id), step_id=step_id, planned=planned, plan_panel=True, **extra)
    return render_partial(request, conn, "_answered.html", **ctx)


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
            raise _already_planned(v.step)
        else:
            try:
                step_id = _plan_step(conn, state, s, v, answer, request_key)
            except plans.Conflict:
                raise HTTPException(409, "This card was already answered from this form. Reload the page.")
        s, v = _view(conn, state, item_id)
        return _planned_line(request, conn, state, s, v, slot=slot, step_id=step_id, planned=answer[len("plan:"):],
                             prev=prev, prev_set_at=prev_set_at)
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
        if step["revision"] != 1:
            # Somebody edited the step since the tap: it is theirs now, and saying "undone"
            # while it stays would be a lie. Say it stays, with the way to it.
            return _planned_line(request, conn, state, s, v, slot=slot, step_id=step["id"], planned="kept", kept=True)
        plans.delete(conn, s["id"], step["id"])
        s, v = _view(conn, state, item_id)
        ctx = checkin._context(conn, s, state)
        ctx.update(item=v, slot=_slot(slot, item_id), undone=True, plan_panel=True)
        return render_partial(request, conn, "_question.html", **ctx)
    now = db.now_iso(state.tz)
    before = _answer_of(conn, item_id)
    if prev and prev_set_at:
        flags.restore(conn, item_id, prev, set_at=prev_set_at, now=now)
    elif not (before and before[0] == prev):
        # With no date to restore, the flag already in place is left exactly as it is: setting
        # it again would say "undone" over a reason it had just erased (#123).
        _apply(conn, item_id, prev or "clear", now)
    s, v = _view(conn, state, item_id)
    # "Answer undone" only when an answer was: nothing is announced that did not happen.
    return render_partial(request, conn, "_question.html", student=s, item=v, slot=_slot(slot, item_id),
                          undone=_answer_of(conn, item_id) != before)


def _answer_of(conn, item_id) -> tuple | None:
    """The family's standing answer on an item, as the page would show it: flag, date, reason."""
    row = flags.active(conn, item_id)
    return (row["flag"], row["set_at"], row["text"]) if row else None


@router.get("/items/{item_id}/reopen")
def reopen(item_id: int, request: Request, slot: str = "", conn: sqlite3.Connection = Db, state=State):
    """"Not right?" on a line the records settled: the item's question card, with the answers
    its verdict carries, in place of the line. Nothing is written until the family answers, so
    nothing is announced as undone; the answer they give is recorded, and undone, the usual way."""
    s, v = _view(conn, state, item_id)
    return render_partial(request, conn, "_question.html", student=s, item=v, slot=_slot(slot, item_id), reopened=True)


@router.get("/questions")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    kid = request.query_params.get("kid") or None
    let_go_ids = _ids(request.query_params.get("let_go", ""))
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
            # Just let go by the bar, and still let go: what its one Undo would put back (#124).
            "let_go": [v for v in views if v.id in let_go_ids and _let_go_by_bar(conn, v.id)] if kid == s["key"] else [],
        })
    return render(request, conn, "questions.html", current="questions", groups=groups, kid=kid)


#: The reason the bar writes, which is also how its Undo knows a let-go is still the bar's.
LET_GO_TEXT = "past the late-work window"


def _ids(raw: str) -> set[int]:
    return {int(x) for x in (raw or "").split(",") if x.strip().isdigit()}


def _let_go_by_bar(conn, item_id: int) -> sqlite3.Row | None:
    row = flags.active(conn, item_id)
    return row if row is not None and row["flag"] == "ignore" and row["text"] == LET_GO_TEXT else None


@router.post("/questions/let-go")
def let_go(request: Request, kid: str = Form(...), conn: sqlite3.Connection = Db, state=State):
    """Ignore every one of one kid's past-credit items, after the page's confirm. One kid at a
    time: a button that hides a whole household's work in one click hides a problem. The page
    it lands on names what went and offers one Undo for exactly those items."""
    s = student_or_404(conn, kid)
    now = db.now_iso(state.tz)
    done = []
    for v in items.list_items(conn, s, now=state.now(), rules=state.rules(), show="all", prefs=state.sources()):
        if v.verdict.kind == "past_credit":
            flags.set_flag(conn, v.id, "ignore", now=now, text=LET_GO_TEXT)
            done.append(str(v.id))
    return RedirectResponse(f"/questions?{urlencode({'kid': kid, 'let_go': ','.join(done)})}", status_code=303)


@router.post("/questions/let-go/undo")
def let_go_undo(request: Request, kid: str = Form(...), ids: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    """Put back what the bar let go: each of these items of this kid's that is still let go by
    the bar returns to the answer it had before (none, for past-credit work), and an item the
    family has answered since keeps that answer."""
    s = student_or_404(conn, kid)
    now = db.now_iso(state.tz)
    for item_id in _ids(ids):
        owner = students.owner_of_item(conn, item_id)
        row = _let_go_by_bar(conn, item_id) if owner is not None and owner["id"] == s["id"] else None
        if row is None:
            continue
        before = conn.execute("SELECT flag, set_at FROM flags WHERE item_id = ? AND cleared_at = ? AND id < ? ORDER BY id DESC LIMIT 1",
                              (item_id, row["set_at"], row["id"])).fetchone()
        if before is not None:
            flags.restore(conn, item_id, before["flag"], set_at=before["set_at"], now=now)
        else:
            flags.clear(conn, item_id, now=now)
    return RedirectResponse(f"/questions?{urlencode({'kid': kid})}", status_code=303)

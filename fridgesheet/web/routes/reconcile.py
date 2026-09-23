"""The Reconcile page: what the sources and the parent's flags do not agree on, per kid."""
from __future__ import annotations

import sqlite3
from collections import Counter

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, render
from ..stores import flags, items, students
from .. import db, reconcile

router = APIRouter()


#: The one bulk action the page offers, and the flag it applies. "past credit" cases all say
#: the same thing -- "No longer earns credit; flag ignore to hide" -- and on a real gradebook
#: there were twenty of them per kid, each with its own five buttons (#40 item 10). A page
#: that tells a parent to click the same button twenty times should offer to do it once.
BULK = {"past_credit": ("ignore", "past the late-work window")}


def _page(request: Request, conn: sqlite3.Connection, state, kid: str | None, kind: str | None):
    now, rules = state.now(), state.rules()
    kids = [s for s in students.visible(conn) if kid is None or s["key"] == kid]
    groups = [(s, items.with_cases(conn, s, now=now, rules=rules, kind=kind, prefs=state.sources())) for s in kids]
    # Counts drive the kind badges, which must stay navigable while one is selected: an
    # unfiltered-by-kind pass over the same kid(s), not the kind-filtered `groups` above.
    counts: Counter = Counter()
    bulk: dict[str, int] = {}                       # kid key -> how many past-credit items a bulk ignore would take
    for s in kids:
        for _, cases in items.with_cases(conn, s, now=now, rules=rules, prefs=state.sources()):
            counts.update(c.kind for c in cases)
            if any(c.kind == "past_credit" for c in cases):
                bulk[s["key"]] = bulk.get(s["key"], 0) + 1
    return render(request, conn, "reconcile.html", current="reconcile", groups=groups, kid=kid, kind=kind,
                  counts=[(k, counts.get(k, 0)) for k in reconcile.KINDS], KINDS=reconcile.KINDS, bulk=bulk)


def _args(request: Request) -> tuple[str | None, str | None]:
    q = request.query_params
    kid, kind = q.get("kid") or None, q.get("kind") or None
    return kid, (kind if kind in reconcile.KINDS else None)


@router.get("/reconcile")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    kid, kind = _args(request)
    return _page(request, conn, state, kid, kind)


@router.post("/reconcile/flag-all")
def flag_all(request: Request, kid: str = Form(...), case_kind: str = Form(...),
             conn: sqlite3.Connection = Db, state=State):
    """Apply the bulk flag for `case_kind` to every one of `kid`'s items that carries it and
    is not already handled, then show the page again. Only the kinds in BULK, only one kid
    at a time: a button that ignores a whole household's cases in one click is not a
    convenience, it is a way to hide a problem."""
    if case_kind not in BULK:
        raise HTTPException(400, f"no bulk action for {case_kind!r}")
    s = next((s for s in students.visible(conn) if s["key"] == kid), None)
    if s is None:
        raise HTTPException(404, f"no student {kid!r}")
    flag, text = BULK[case_kind]
    now, rules = state.now(), state.rules()
    when = db.now_iso(state.tz)
    for view, cases in items.with_cases(conn, s, now=now, rules=rules, kind=case_kind, prefs=state.sources()):
        if not view.handled:
            flags.set_flag(conn, view.id, flag, now=when, text=text)
    view_kid, view_kind = _args(request)
    return _page(request, conn, state, view_kid, view_kind)

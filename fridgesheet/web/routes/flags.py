"""Set or clear the one active flag on an item; answer with the refreshed detail partial."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, render_partial
from ..stores import changes, flags, items, notes, students
from .. import db

router = APIRouter()

LABELS = {"done": "Marked done", "excused": "Marked excused", "ignore": "Ignored", "follow_up": "Marked follow up",
          "ask_teacher": "Marked ask teacher", "clear": "No flag"}


@router.post("/items/{item_id}/flag")
def set_item_flag(item_id: int, request: Request, flag: str = Form(...), text: str = Form(""),
                  conn: sqlite3.Connection = Db, state=State):
    s = students.owner_of_item(conn, item_id)
    if s is None:
        raise HTTPException(404, "no such item")
    if flag not in flags.FLAGS and flag != "clear":
        raise HTTPException(400, f"unknown flag {flag!r}")
    when, rules = state.now(), state.rules()
    now = db.now_iso(state.tz)
    if flag == "clear":
        flags.clear(conn, item_id, now=now)
    else:
        flags.set_flag(conn, item_id, flag, now=now, text=text.strip())
    v = items.one(conn, s, item_id, now=when, rules=rules, prefs=state.sources(), **state.window())
    return render_partial(request, conn, "_item_detail.html", student=s, item=v,
                          item_history=changes.for_item(conn, s["id"], item_id, now=state.now(), prefs=state.sources()), message=LABELS[flag],
                          notes=notes.for_target(conn, "item", item_id))

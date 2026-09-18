"""Notes on an item, a course or a student; every action answers with the target's note list."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request

from ..app import Db, State, render_partial
from ..stores import notes, students
from .. import db

router = APIRouter()


def _partial(request, conn, target_type, target_id):
    return render_partial(request, conn, "_notes.html", target_type=target_type, target_id=target_id,
                          notes=notes.for_target(conn, target_type, target_id))


def _target_exists(conn: sqlite3.Connection, target_type: str, target_id: int) -> bool:
    """A note has to hang on something: `notes` carries a loose (type, id), not a foreign key."""
    if target_type == "item":
        return students.owner_of_item(conn, target_id) is not None
    if target_type == "course":
        return students.course(conn, target_id) is not None
    return students.by_id(conn, target_id) is not None


@router.post("/notes")
def add_note(request: Request, target_type: str = Form(...), target_id: int = Form(...), body: str = Form(""),
             conn: sqlite3.Connection = Db, state=State):
    if target_type not in notes.TARGETS:
        raise HTTPException(400, f"unknown target {target_type!r}")
    if not _target_exists(conn, target_type, target_id):
        raise HTTPException(404, f"no {target_type} {target_id}")
    if not body.strip():
        raise HTTPException(400, "an empty note")
    notes.add(conn, target_type, target_id, body.strip(), now=db.now_iso(state.tz))
    return _partial(request, conn, target_type, target_id)


@router.post("/notes/{note_id}/edit")
def edit_note(note_id: int, request: Request, body: str = Form(""), conn: sqlite3.Connection = Db, state=State):
    n = notes.get(conn, note_id)
    if n is None:
        raise HTTPException(404, "no such note")
    body = body or request.headers.get("HX-Prompt", "")     # htmx's hx-prompt sends the answer as a header
    if not body.strip():
        raise HTTPException(400, "an empty note")
    notes.edit(conn, note_id, body.strip(), now=db.now_iso(state.tz))
    return _partial(request, conn, n["target_type"], n["target_id"])


@router.post("/notes/{note_id}/delete")
def delete_note(note_id: int, request: Request, conn: sqlite3.Connection = Db):
    n = notes.get(conn, note_id)
    if n is None:
        raise HTTPException(404, "no such note")
    notes.delete(conn, note_id)
    return _partial(request, conn, n["target_type"], n["target_id"])

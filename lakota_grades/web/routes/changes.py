"""The Changes feed: everything that moved since a chosen moment."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Request

from ..app import Db, State, render, student_or_404
from ..stores import changes

router = APIRouter()


@router.get("/changes")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    q = request.query_params
    window = q.get("window") or changes.DEFAULT_WINDOW
    if window not in {key for key, _, _ in changes.WINDOWS}:
        window = changes.DEFAULT_WINDOW           # an unknown key still highlights a real chip
    kid = q.get("kid") or None
    kind = q.get("kind") or None
    if kind not in changes.KINDS:
        kind = None                               # an unknown kind means no kind filter, and the
                                                  # "all" chip still lights up (as for `window`)
    student = student_or_404(conn, kid) if kid else None
    now = state.now()
    page_no = q.get("page", "1")
    page_no = int(page_no) if page_no.isdigit() and int(page_no) >= 1 else 1
    events = changes.since(conn, since=changes.window_start(window, now),
                           student_id=student["id"] if student else None,
                           kinds=(kind,) if kind else None,
                           limit=changes.DEFAULT_LIMIT, offset=(page_no - 1) * changes.DEFAULT_LIMIT)
    # The page links keep every filter; the partial cannot see the template's own `base`.
    base = "/changes?" + "".join(f"{k}={v}&" for k, v in (("window", window), ("kid", kid), ("kind", kind)) if v)
    return render(request, conn, "changes.html", current="changes", events=events, window=window, page_no=page_no,
                  page_base=base, kid=kid, kind=kind, WINDOWS=changes.WINDOWS, KINDS=changes.KINDS, LABELS=changes.LABELS)

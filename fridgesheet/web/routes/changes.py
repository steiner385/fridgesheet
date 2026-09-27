"""The Changes feed: everything that moved since a chosen moment."""
from __future__ import annotations

import sqlite3
from urllib.parse import quote

from fastapi import APIRouter, Request

from ..app import Db, State, render, student_or_404, who_of
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
    # No `kid` parameter and a kid cookie: the reader scopes the feed to themself
    # (spec 2026-09-27 §13.3), same as Trends.
    student = student_or_404(conn, kid) if kid else who_of(request, conn)[1]
    kid = student["key"] if student else None
    now = state.now()
    page_no = q.get("page", "1")
    page_no = int(page_no) if page_no.isdigit() and int(page_no) >= 1 else 1
    events = changes.since(conn, since=changes.window_start(window, now),
                           student_id=student["id"] if student else None,
                           kinds=(kind,) if kind else None,
                           limit=changes.DEFAULT_LIMIT, offset=(page_no - 1) * changes.DEFAULT_LIMIT,
                           prefs=state.sources())
    # The page links keep every filter; the partial cannot see the template's own `base`. A
    # kid key can carry `&` or a space, so it is quoted like every other kid= in the querystring
    # (changes.html, trends.html) -- an unencoded key would break the pager's own link.
    base = "/changes?" + "".join(f"{k}={quote(v, safe='') if k == 'kid' else v}&"
                                  for k, v in (("window", window), ("kid", kid), ("kind", kind)) if v)
    return render(request, conn, "changes.html", current="changes", events=events, window=window, page_no=page_no,
                  page_base=base, kid=kid, kind=kind, WINDOWS=changes.WINDOWS, KINDS=changes.KINDS, LABELS=changes.LABELS)

"""Run history: what ran, how it went, the PDF, print it again."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ... import reports as registry
from ..app import Db, State, render, safe_pdf
from ..stores import runs

router = APIRouter()


@router.get("/runs")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    rows = runs.recent(conn, 100)
    # Reprint prints the row's own PDF (`/jobs/reprint`, #143), so the button is offered on
    # exactly the rows whose "open" link would work: `pdfs` decides both.
    pdfs = {r["id"]: safe_pdf(state, r["pdf_path"]) for r in rows}
    # A saved report's key is `view:<id>`; the parent named it, so say that name (#6).
    titles = {r.key: r.title for r in registry.available(state.home)}
    return render(request, conn, "runs.html", current="runs", rows=rows, pdfs=pdfs, titles=titles)


@router.get("/runs/{run_id}/pdf")
def pdf(run_id: int, conn: sqlite3.Connection = Db, state=State):
    r = runs.by_id(conn, run_id)
    p = safe_pdf(state, r["pdf_path"]) if r else None
    if p is None:
        raise HTTPException(404, "no PDF for that run")
    return FileResponse(p, media_type="application/pdf", filename=p.name)

"""Run history: what ran, how it went, the PDF, print it again."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ..app import Db, State, render, safe_pdf
from ..stores import runs

router = APIRouter()


@router.get("/runs")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    rows = runs.recent(conn, 100)
    pdfs = {r["id"]: safe_pdf(state, r["pdf_path"]) for r in rows}
    # The day the reprint button asks for, cut from the stored ISO timestamp here rather than
    # sliced in the template: the template says what it shows, this says what it means.
    dates = {r["id"]: (r["started_at"] or "")[:10] for r in rows}
    return render(request, conn, "runs.html", current="runs", rows=rows, pdfs=pdfs, dates=dates)


@router.get("/runs/{run_id}/pdf")
def pdf(run_id: int, conn: sqlite3.Connection = Db, state=State):
    r = runs.by_id(conn, run_id)
    p = safe_pdf(state, r["pdf_path"]) if r else None
    if p is None:
        raise HTTPException(404, "no PDF for that run")
    return FileResponse(p, media_type="application/pdf", filename=p.name)

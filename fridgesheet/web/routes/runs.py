"""Run history: what ran, how it went, the PDF, print it again."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from ... import reports as registry
from ..app import Db, State, render, safe_pdf
from ..stores import runs

router = APIRouter()


def days_of(rows, tz):
    """The runs grouped by the day they started (the household's day), newest first, each day
    with its tally (the sheet's own log, 2026-10-01). `started_at` is an isoformat string with
    its offset; one written without an offset is read as it is."""
    groups: list[dict] = []
    for r in rows:
        at = datetime.fromisoformat(r["started_at"])
        day = (at.astimezone(tz) if at.tzinfo else at).date()
        if not groups or groups[-1]["date"] != day:
            groups.append({"date": day, "rows": [], "counts": {}})
        groups[-1]["rows"].append(r)
        groups[-1]["counts"][r["outcome"]] = groups[-1]["counts"].get(r["outcome"], 0) + 1
    for g in groups:
        g["tally"] = runs.tally(g["counts"])
    return groups


@router.get("/runs")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    rows = runs.recent(conn, 100)
    # Reprint prints the row's own PDF (`/jobs/reprint`, #143), so the button is offered on
    # exactly the rows whose "open" link would work: `pdfs` decides both.
    pdfs = {r["id"]: safe_pdf(state, r["pdf_path"]) for r in rows}
    # A saved report's key is `view:<id>`; the parent named it, so say that name (#6).
    titles = {r.key: r.title for r in registry.available(state.home)}
    titles.setdefault("refresh", "Refresh")   # the runner's key for a refresh, said as a word on its line
    return render(request, conn, "runs.html", current="runs", days=days_of(rows, state.tz), pdfs=pdfs, titles=titles)


@router.get("/runs/{run_id}/pdf")
def pdf(run_id: int, conn: sqlite3.Connection = Db, state=State):
    r = runs.by_id(conn, run_id)
    p = safe_pdf(state, r["pdf_path"]) if r else None
    if p is None:
        raise HTTPException(404, "no PDF for that run")
    return FileResponse(p, media_type="application/pdf", filename=p.name)

"""Start a job, show it, stream it."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import StreamingResponse

from ... import reports as registry
from ..app import Db, State, render_partial, safe_pdf
from .. import jobs as jobmod

router = APIRouter()


def _pdf(state, job):
    """The job's PDF only if `/jobs/{id}/pdf` would really serve it -- the same check the Runs
    page makes for its rows, so the link is never offered for a file that has since gone."""
    return safe_pdf(state, str(job.pdf) if job and job.pdf else None)


def _worker(state) -> jobmod.Worker:
    if state.jobs is None:
        raise HTTPException(404, "no jobs worker in this server")
    return state.jobs


@router.post("/jobs/{kind}")
def start(kind: str, request: Request, date: str | None = Form(None), report: str = Form("open-work"),
          conn: sqlite3.Connection = Db, state=State):
    if kind not in jobmod.KINDS:
        raise HTTPException(404, f"no job kind {kind!r}")
    w = _worker(state)
    params = {"date": date} if date else {}
    if kind in ("preview", "print"):
        try:
            registry.resolve(report, state.home)
        except registry.ReportError as e:
            raise HTTPException(400, str(e)) from None
        params["report"] = report
    job = w.submit(kind, **params)
    if job is None:
        r = render_partial(request, conn, "_job.html", job=w.current, busy=True, pdf=_pdf(state, w.current))
        r.status_code = 409
        return r
    return render_partial(request, conn, "_job.html", job=job, busy=False, pdf=_pdf(state, job))


@router.get("/jobs/{job_id}")
def show(job_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    job = _worker(state).get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    return render_partial(request, conn, "_job.html", job=job, busy=False, pdf=_pdf(state, job))


@router.get("/jobs/{job_id}/events")
def events(job_id: int, state=State):
    w = _worker(state)
    return StreamingResponse(w.events(job_id), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/jobs/{job_id}/pdf")
def job_pdf(job_id: int, state=State):
    from fastapi.responses import FileResponse
    p = _pdf(state, _worker(state).get(job_id))
    if p is None:
        raise HTTPException(404, "no PDF for that job")
    return FileResponse(p, media_type="application/pdf", filename=p.name)

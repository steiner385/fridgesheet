"""Start a job, show it, stream it."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from ... import reports as registry
from ..app import Db, State, is_htmx, render_partial, safe_pdf
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
          refresh_first: bool = Form(False), conn: sqlite3.Connection = Db, state=State):
    if kind not in jobmod.OPEN_KINDS:
        raise HTTPException(404, f"no job kind {kind!r}")
    w = _worker(state)
    params = {"date": date} if date else {}
    if kind in ("preview", "print"):
        try:
            registry.resolve(report, state.home)
        except registry.ReportError as e:
            raise HTTPException(400, str(e)) from None
        params["report"] = report
        params["refresh_first"] = refresh_first
    job = w.submit(kind, **params)
    if job is None:
        # The job that refused this one can finish between `submit` and here (#4); then the
        # slot is free, so try once more rather than render a card for no job.
        blocker = w.current
        if blocker is None:
            job = w.submit(kind, **params)
        if job is None:
            blocker = blocker or w.current or w.last
            r = render_partial(request, conn, "_job.html", job=blocker, busy=True, pdf=_pdf(state, blocker))
            r.status_code = 409
            return r
    return render_partial(request, conn, "_job.html", job=job, busy=False, pdf=_pdf(state, job))


@router.get("/jobs/{job_id}")
def show(job_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    job = _worker(state).get(job_id)
    if job is None:
        if is_htmx(request):
            # The live log's `done` event fetches this to replace the card; after eviction a
            # 404 page landed in it (#4). Runs still has the outcome.
            return HTMLResponse('<div class="card job" id="job"><p class="muted">That job is no longer kept here; '
                                'its result is on the <a href="/runs">Runs</a> page.</p></div>')
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

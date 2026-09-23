"""`/reconcile` was the page of cases; it is now Questions
(docs/superpowers/specs/2026-09-23-questions-not-cases-design.md)."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/reconcile")
def page(request: Request):
    kid = request.query_params.get("kid")
    return RedirectResponse("/questions" + (f"?{urlencode({'kid': kid})}" if kid else ""), status_code=308)

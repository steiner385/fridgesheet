"""A child-scoped conversation, durable next steps, and a browser-printable plan."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..app import Db, State, render, student_or_404
from ..stores import items, plans

router = APIRouter()


def root(key):
    return f"/kids/{quote(key, safe='')}/check-in"


def _context(conn, student, state):
    now, rules = state.now(), state.rules()
    views = items.list_items(conn, student, now=now, rules=rules, show="all")
    by_id = {v.id: v for v in views}
    steps = plans.for_student(conn, student["id"])
    for step in steps:
        view = by_id.get(step["item_id"])
        step["view"] = view
        step["changed"] = view is not None and step["evidence"] != plans.evidence(view)
    # Finishing a small step does not complete its assignment: it returns to review.
    covered = {s["item_id"] for s in steps if s["state"] != "done"}
    queues = {"Work to consider": [], "Needs clarification": [], "Submitted · waiting for a grade": []}
    for v in views:
        if v.handled or v.id in covered or v.outcome in ("excused", "unpublished"):
            continue
        submitted = v.canvas is not None and v.canvas["submitted_at"]
        ungraded = submitted and v.canvas["score"] is None and (v.hac is None or v.hac["score"] is None)
        uncertain = v.grade_zero or v.outcome == "unknown" or "disagree" in v.case_kinds
        if not (v.open_in or v.upcoming or ungraded):
            continue
        group = "Needs clarification" if uncertain else "Submitted · waiting for a grade" if ungraded else "Work to consider"
        queues[group].append(v)
    history = plans.history(conn, student["id"])
    active = [s for s in steps if s["state"] != "done"]
    today_steps = [s for s in active if s["state"] == "planned" and s["planned_for"] == now.date().isoformat()]
    return dict(student=student, current=f"kid:{student['key']}", base=root(student["key"]), queues=queues,
                steps=active, completed=[s for s in steps if s["state"] == "done"], history=history,
                last_check=history[0] if history else None, today=now.date().isoformat(),
                total_minutes=sum(s["minutes"] or 0 for s in today_steps),
                unestimated=sum(s["minutes"] is None for s in today_steps), states=plans.STATES,
                finish_token=str(uuid4()), rules=rules, saved=False, error=None)


@router.get("/kids/{key}/check-in")
@router.get("/kids/{key}/plan")
def page(key: str, request: Request, conn=Db, state=State):
    student = student_or_404(conn, key)
    ctx = _context(conn, student, state)
    ctx.update(plan_only=request.url.path.endswith("/plan"), saved=request.query_params.get("saved") == "1")
    return render(request, conn, "checkin.html", **ctx)


@router.get("/kids/{key}/plan/print")
def print_plan(key: str, request: Request, conn=Db, state=State):
    return render(request, conn, "plan_print.html", **_context(conn, student_or_404(conn, key), state))


def _form_context(conn, student, state, item_id=None, step_id=None):
    values = plans.one(conn, student["id"], step_id) if step_id is not None else None
    if step_id is not None and values is None:
        raise HTTPException(404, "No such plan step")
    item_id = values["item_id"] if values else item_id
    if item_id is not None and not conn.execute(
            "SELECT 1 FROM items WHERE id = ? AND student_id = ?", (item_id, student["id"])).fetchone():
        raise HTTPException(404, "No such assignment")
    view = items.one(conn, student, item_id, now=state.now(), rules=state.rules()) if item_id else None
    if values is None:
        values = dict(title=view.name if view else "", family_account="", next_step="", owner=state.settings.nicknames.get(student["key"], student["key"]),
                      planned_for=state.now().date().isoformat(), minutes="", state="planned", position=10,
                      revision=0, request_key=str(uuid4()))
    return dict(student=student, current=f"kid:{student['key']}", base=root(student["key"]),
                values=values, view=view, item_id=item_id, step_id=step_id, states=plans.STATES, error=None)


@router.get("/kids/{key}/check-in/step")
def step_form(key: str, request: Request, item_id: int | None = None, step_id: int | None = None, conn=Db, state=State):
    return render(request, conn, "plan_step.html", **_form_context(conn, student_or_404(conn, key), state, item_id, step_id))


def _date(value):
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("Use a date in YYYY-MM-DD format.")
    return value


@router.post("/kids/{key}/check-in/step")
async def save_step(key: str, request: Request, item_id: int | None = None, step_id: int | None = None, conn=Db, state=State):
    student = student_or_404(conn, key)
    ctx = _form_context(conn, student, state, item_id, step_id)
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in (*plans.FIELDS, "request_key", "revision")}
    try:
        for k in ("title", "next_step", "owner"):
            if not values[k] or len(values[k]) > 500:
                raise ValueError("Add a title, next step, and owner (each up to 500 characters).")
        if len(values["family_account"]) > 4000:
            raise ValueError("Keep the family account under 4,000 characters.")
        values["planned_for"] = _date(values["planned_for"])
        values["minutes"] = int(values["minutes"]) if values["minutes"] else None
        if values["minutes"] is not None and not 1 <= values["minutes"] <= 1440:
            raise ValueError("Choose an estimate between 1 and 1,440 minutes, or leave it blank.")
        values["position"] = int(values["position"])
        if not 1 <= values["position"] <= 999 or values["state"] not in plans.STATES:
            raise ValueError("Choose a valid state and an order between 1 and 999.")
        if not 1 <= len(values["request_key"]) <= 100:
            raise ValueError("Reload this form before saving.")
        values["evidence"] = plans.evidence(ctx["view"])
        plans.save(conn, student["id"], values, now=state.now().isoformat(), request_key=values["request_key"],
                   item_id=ctx["item_id"], step_id=step_id, revision=int(values["revision"]))
    except (ValueError, TypeError) as exc:
        ctx.update(values=values, error=str(exc))
        return render(request, conn, "plan_step.html", status_code=409 if isinstance(exc, plans.Conflict) else 422, **ctx)
    return RedirectResponse(root(key) + "?saved=1#plan", status_code=303)


@router.post("/kids/{key}/check-in/finish")
async def finish(key: str, request: Request, conn=Db, state=State):
    student = student_or_404(conn, key)
    form = await request.form()
    try:
        next_check = _date(str(form.get("next_check", "")))
        available = int(str(form.get("available_minutes", "")))
        summary = str(form.get("summary", "")).strip()
        token = str(form.get("request_key", ""))
        if not 1 <= available <= 1440 or len(summary) > 4000 or not 1 <= len(token) <= 100:
            raise ValueError("Choose 1–1,440 available minutes and a summary under 4,000 characters.")
        plans.finish(conn, student["id"], now=state.now().isoformat(), next_check=next_check,
                     available_minutes=available, summary=summary, request_key=token)
    except ValueError as exc:
        ctx = _context(conn, student, state)
        ctx.update(error=str(exc), finish_values=dict(form), plan_only=False)
        return render(request, conn, "checkin.html", status_code=422, **ctx)
    return RedirectResponse(f"/kids/{quote(key, safe='')}/plan?saved=1", status_code=303)

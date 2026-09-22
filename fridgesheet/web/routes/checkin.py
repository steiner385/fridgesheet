"""A child-scoped conversation, durable next steps, and a browser-printable plan.

Three layers, kept apart on purpose: the school record (observations and flags, never
written here), the family's account of what happened, and the step they agreed on. The
review queue is built from the first; everything saved is the second and third.
"""
from __future__ import annotations

from datetime import date
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import outcomes
from ..app import Db, State, render, student_or_404
from ..stores import items, plans

router = APIRouter()

QUEUES = ("Work to consider", "Needs clarification", "Submitted · waiting for a grade")


def root(key):
    return f"/kids/{quote(key, safe='')}/check-in"


def _id(value: str | None) -> int | None:
    """A row id from the query string, or 404: `?step_id=abc` is a wrong address, not a form
    error (FastAPI would answer a typed `int` parameter with 422 JSON)."""
    if value is None or value == "":
        return None
    if not value.isdigit():
        raise HTTPException(404, "no such row")
    return int(value)


def _group(v) -> str | None:
    """Which review group a live item belongs in, or None when there is nothing to talk about.

    Handled work and existing commitments are skipped by the caller. Anything the sources
    cannot settle -- a zero, a disagreement, paper work with no grade -- is a question before it
    is a task. Submitted but ungraded work is waiting on the teacher, not on the child."""
    if v.outcome in (outcomes.EXCUSED, outcomes.UNPUBLISHED):
        return None
    submitted = v.canvas is not None and v.canvas["submitted_at"]
    ungraded = submitted and v.canvas["score"] is None and (v.hac is None or v.hac["score"] is None)
    uncertain = v.grade_zero or v.outcome == outcomes.UNKNOWN or "disagree" in v.case_kinds
    # Undated work (HAC lists some) is never "open" or "upcoming" by date; unfinished, it still
    # deserves a look rather than silence.
    undated = v.due is None and v.outcome == outcomes.NOT_DUE
    if not (v.open_in or v.upcoming or ungraded or undated):
        return None
    return QUEUES[1] if uncertain else QUEUES[2] if ungraded else QUEUES[0]


def _since(step, last_check) -> str:
    """How this step relates to the last saved agreement: part of it, edited after it, or added
    after it. Empty before the first check-in."""
    if not last_check:
        return ""
    if step["id"] in {s["id"] for s in last_check["steps"]}:
        return "agreed" if step["updated_at"] <= last_check["finished_at"] else "edited"
    return "added"


def _context(conn, student, state):
    now, rules = state.now(), state.rules()
    today = now.date().isoformat()
    views = items.list_items(conn, student, now=now, rules=rules, show="all")
    by_id = {v.id: v for v in views}
    steps = plans.for_student(conn, student["id"])
    history = plans.history(conn, student["id"])
    last_check = history[0] if history else None
    for step in steps:
        view = by_id.get(step["item_id"])
        step["view"] = view
        step["changed"] = view is not None and step["evidence"] != plans.evidence(view)
        step["since"] = _since(step, last_check)
    # Finishing a small step does not complete its assignment: it returns to review, with the
    # family's earlier steps on it in view so the conversation does not start from zero.
    covered = {s["item_id"] for s in steps if s["state"] != "done"}
    completed_for: dict[int, list] = {}
    for s in steps:
        if s["state"] == "done" and s["item_id"] is not None:
            completed_for.setdefault(s["item_id"], []).append(s)
    queues = {label: [] for label in QUEUES}
    for v in views:
        if v.handled or v.id in covered:
            continue
        group = _group(v)
        if group:
            queues[group].append(v)
    # Due date order, except that work past its late-credit window goes after work that can
    # still earn credit: a month-old zero must not sit above tonight's deadline. It stays
    # visible -- a cutoff in the rules is not the teacher's last word.
    for rows in queues.values():
        rows.sort(key=lambda v: bool(v.open_in) and not v.actionable)
    active = [s for s in steps if s["state"] != "done"]
    today_steps = [s for s in active if s["state"] in ("planned", "blocked") and s["planned_for"] == today]
    total = sum(s["minutes"] or 0 for s in today_steps)
    # The next check-in starts from what was agreed while that date is still ahead.
    next_default = last_check["next_check"] if last_check and last_check["next_check"] >= today else today
    return dict(student=student, current=f"kid:{student['key']}", base=root(student["key"]), queues=queues,
                steps=active, completed=[s for s in steps if s["state"] == "done"], completed_for=completed_for,
                history=history, last_check=last_check, today=today, next_default=next_default,
                total_minutes=total, over=(total - last_check["available_minutes"]) if last_check else 0,
                unestimated=sum(s["minutes"] is None for s in today_steps), states=plans.STATES,
                finish_token=str(uuid4()), rules=rules, saved=False, error=None, waiting_group=QUEUES[2])


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


def _form_context(conn, student, state, item_id=None, step_id=None, default_state="planned"):
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
                      planned_for=state.now().date().isoformat(), minutes="",
                      state=default_state if default_state in plans.STATES else "planned", position=10,
                      recorded_by="", revision=0, request_key=str(uuid4()))
    return dict(student=student, current=f"kid:{student['key']}", base=root(student["key"]),
                values=values, view=view, item_id=item_id, step_id=step_id, states=plans.STATES, error=None, latest=None)


@router.get("/kids/{key}/check-in/step")
def step_form(key: str, request: Request, item_id: str | None = None, step_id: str | None = None, conn=Db, state=State):
    ctx = _form_context(conn, student_or_404(conn, key), state, _id(item_id), _id(step_id),
                        default_state=request.query_params.get("state", "planned"))
    return render(request, conn, "plan_step.html", **ctx)


def _date(value, label):
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise ValueError(f"{label}: use a date in YYYY-MM-DD format, like {date.today().isoformat()}.")
    return value


def _number(value, label, lo, hi, *, blank=None):
    """A whole number between `lo` and `hi`, explained in the parent's words when it is not."""
    if value == "" and blank is not None:
        return blank
    try:
        n = int(value)
    except ValueError:
        n = None
    if n is None or not lo <= n <= hi:
        raise ValueError(f"{label}: use a whole number from {lo:,} to {hi:,}" + (", or leave it blank." if blank is not None else "."))
    return n


@router.post("/kids/{key}/check-in/step")
async def save_step(key: str, request: Request, item_id: str | None = None, step_id: str | None = None, conn=Db, state=State):
    student = student_or_404(conn, key)
    item_id, step_id = _id(item_id), _id(step_id)
    ctx = _form_context(conn, student, state, item_id, step_id)
    form = await request.form()
    values = {k: str(form.get(k, "")).strip() for k in (*plans.FIELDS, "request_key", "revision")}
    try:
        for k, label in (("title", "Assignment or task"), ("next_step", "Agreed next step"), ("owner", "Who will do this")):
            if not values[k] or len(values[k]) > 500:
                raise ValueError(f"{label}: add a few words (up to 500 characters).")
        if len(values["family_account"]) > 4000:
            raise ValueError("Family account: keep it under 4,000 characters.")
        if len(values["recorded_by"]) > 100:
            raise ValueError("Recorded by: a name, up to 100 characters.")
        values["planned_for"] = _date(values["planned_for"], "Planned date")
        values["minutes"] = _number(values["minutes"], "Estimated minutes", 1, 1440, blank=None) if values["minutes"] else None
        values["position"] = _number(values["position"], "Order within this day", 1, 999)
        if values["state"] not in plans.STATES:
            raise ValueError("State: choose one of the listed states.")
        if not 1 <= len(values["request_key"]) <= 100 or not values["revision"].isdigit():
            raise ValueError("Reload this form before saving.")
        values["evidence"] = plans.evidence(ctx["view"])
        plans.save(conn, student["id"], values, now=state.now().isoformat(), request_key=values["request_key"],
                   item_id=ctx["item_id"], step_id=step_id, revision=int(values["revision"]))
    except plans.Conflict as exc:
        # Show what the other person saved, and carry their revision so that one more Save --
        # after reading it -- applies these words on top.
        # `step_id` is None when the conflict came from a create, and `one` returns None when
        # the step was deleted between the form load and this save -- neither has a revision
        # to carry, and neither should be a 500.
        latest = plans.one(conn, student["id"], step_id) if step_id is not None else None
        if latest is not None:
            values["revision"] = latest["revision"]
        ctx.update(values=values, error=str(exc), latest=latest)
        return render(request, conn, "plan_step.html", status_code=409, **ctx)
    except ValueError as exc:
        ctx.update(values=values, error=str(exc))
        return render(request, conn, "plan_step.html", status_code=422, **ctx)
    return RedirectResponse(root(key) + "?saved=1#plan", status_code=303)


@router.post("/kids/{key}/check-in/step/{step_id}/delete")
def delete_step(key: str, step_id: int, conn=Db):
    student = student_or_404(conn, key)
    if not plans.delete(conn, student["id"], step_id):
        raise HTTPException(404, "No such plan step")
    return RedirectResponse(root(key) + "?saved=1#plan", status_code=303)


@router.post("/kids/{key}/check-in/finish")
async def finish(key: str, request: Request, conn=Db, state=State):
    student = student_or_404(conn, key)
    form = await request.form()
    try:
        next_check = _date(str(form.get("next_check", "")), "Next check-in")
        available = _number(str(form.get("available_minutes", "")).strip(), "Time available today", 1, 1440)
        summary = str(form.get("summary", "")).strip()
        recorded_by = str(form.get("recorded_by", "")).strip()
        token = str(form.get("request_key", ""))
        if not summary or len(summary) > 4000:
            raise ValueError("What we agreed: write a few words, up to 4,000 characters.")
        if len(recorded_by) > 100:
            raise ValueError("Recorded by: a name, up to 100 characters.")
        if not 1 <= len(token) <= 100:
            raise ValueError("Reload this page before finishing the check-in.")
        plans.finish(conn, student["id"], now=state.now().isoformat(), next_check=next_check,
                     available_minutes=available, summary=summary, request_key=token, recorded_by=recorded_by)
    except ValueError as exc:
        ctx = _context(conn, student, state)
        ctx.update(error=str(exc), finish_values=dict(form), plan_only=False)
        return render(request, conn, "checkin.html", status_code=422, **ctx)
    return RedirectResponse(f"/kids/{quote(key, safe='')}/plan?saved=1", status_code=303)

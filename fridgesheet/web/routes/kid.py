"""The Kid page: the item list with filters, the expanded row, and the course page."""
from __future__ import annotations

import sqlite3
from datetime import timedelta
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import sources
from .. import actions, outcomes
from ..app import Db, State, render, render_partial, student_or_404
from ..stores import changes, items, notes, students, trends
from .trends import chart_json, grade_chart

router = APIRouter()


def _filters(request: Request) -> dict:
    q = request.query_params
    course = q.get("course")
    return {
        "show": q.get("show", "open"), "source": q.get("source") or None,
        "course_id": int(course) if course and course.isdigit() else None,
        "kind": q.get("kind") or None, "flagged": q.get("flagged") or None, "outcome": q.get("outcome") or None, "verdict": q.get("verdict") or None, "sort": q.get("sort", "due"),
        "direction": _direction(q.get("dir")),
    }


def _direction(raw: str | None) -> str:
    """Ascending unless the query string clearly asks otherwise -- `items.sorted_views` makes
    the same choice about the same value, and the header arrow has to agree with the rows."""
    return "desc" if raw == "desc" else "asc"


def _sort_base(key: str, f: dict) -> str:
    """The URL the column headers sort: this page with its filters, ready for `sort=<x>`."""
    q = [("show", f["show"])]
    q += [(name, v) for name, v in (("source", f["source"]), ("course", f["course_id"]),
                                    ("kind", f["kind"]), ("flagged", f["flagged"]),
                                    ("outcome", f["outcome"]), ("verdict", f["verdict"])) if v]
    return f"/kids/{quote(key)}?{urlencode(q)}&"


@router.get("/kids/{key}")
def kid(key: str, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    now, rules = state.now(), state.rules()
    f = _filters(request)
    rows = items.list_items(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window(), **f)
    # The sections above the table cover all of the kid's work, whatever the table shows.
    everything = items.list_items(conn, s, now=now, rules=rules, prefs=state.sources(), show="all", **state.window())
    by_state = {st: [v for v in everything if v.verdict.state == st] for st in ("decided", "waiting")}
    # Settled in the last week stays in view; older settled work folds under "Earlier" (#76).
    week_ago = now - timedelta(days=7)
    recent = [v for v in by_state["decided"] if items.changed_since(v, week_ago)]
    by_state["decided_earlier"] = [v for v in by_state["decided"] if v not in recent]
    by_state["decided"] = recent
    # Asked the teacher, or following up: waiting too, with the date and the email (#73).
    by_state["waiting"] += [v for v in everything if v.verdict.kind in ("asked", "following_up")]
    by_state["question"] = [v for v in everything if v.asks]          # an agreed step already covers the rest
    # What got done, in the dashboard's five outcomes (docs/outcomes.md): on time, late and done
    # on paper are done; not done and unknown are not, or not yet. One line above the questions.
    record = items.record_for(everything)
    return render(request, conn, "kid.html", current=f"kid:{key}", student=s, rows=rows, f=f,
                  done_so_far={"done": record.on_time + record.late + record.done_offline, "total": record.total, "on_time": record.on_time},
                  widened=items.widens_to_all(f["outcome"], f["flagged"], f["verdict"]),
                  questions=by_state["question"], decided=by_state["decided"], decided_earlier=by_state["decided_earlier"], waiting=by_state["waiting"],
                  sort=f["sort"], direction=f["direction"],
                  sort_base=_sort_base(key, f), course_options=students.course_options(conn, s["id"]),
                  SHOW=items.SHOW, FLAGGED=items.FLAGGED, SORTS=items.SORTS,
                  OUTCOMES=outcomes.ORDER, OUTCOME_LABELS=outcomes.LABELS)


def card_for(raw: str | None, item_id: int) -> str | None:
    """The question card an item detail replaced (#126): "q-<id>" from a question list or
    "qc-<id>" from a check-in, for this item only. The detail takes over that card's id, and
    its Close fetches the card back into it; anything else is a detail in a table row, which
    app.js closes by hiding the row."""
    return raw if raw in (f"q-{item_id}", f"qc-{item_id}") else None


@router.get("/items/{item_id}")
def item_detail(item_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    s = students.owner_of_item(conn, item_id)
    v = items.one(conn, s, item_id, now=now, rules=rules, prefs=state.sources(), **state.window()) if s is not None else None
    if v is None:
        raise HTTPException(404, "no such item")
    return render_partial(request, conn, "_item_detail.html", student=s, item=v,
                          item_history=changes.for_item(conn, s["id"], item_id, now=state.now(), prefs=state.sources()), message=None,
                          notes=notes.for_target(conn, "item", item_id), card=card_for(request.query_params.get("card"), item_id))


@router.get("/kids/{key}/courses/{course_id}")
def course(key: str, course_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    c = students.course(conn, course_id)
    if c is None or c["student_id"] != s["id"]:
        raise HTTPException(404, "no such course")
    now, rules, prefs = state.now(), state.rules(), state.sources()
    sort = request.query_params.get("sort", "due")
    direction = _direction(request.query_params.get("dir"))
    peer = students.course(conn, c["peer_course_id"]) if c["peer_course_id"] else None
    grades = students.latest_grades(conn, s["id"])
    own, other = grades.get(course_id), (grades.get(peer["id"]) if peer else None)
    canvas_g, hac_g = (own, other) if c["source"] == "canvas" else (other, own)
    peer_name = peer["name"] if peer else None
    grade_lines = students.grade_lines(canvas_g, hac_g, prefs.resolve(s["key"], c["name"], peer_name).grades)
    source_ctx = {
        "own_rule": prefs.rule_for(s["key"], c["short_name"]),
        "household": prefs.default,
        "choice": prefs.resolve(s["key"], c["name"], peer_name),
        "deciding": {f: prefs.deciding_rule(s["key"], c["name"], f, peer_name) for f in ("assignments", "grades")},
        "SOURCE_LABELS": sources.LABELS,
    }
    # This course and its twin in the other source are one list to a parent, so the peer's
    # rows join it -- and the headers sort the merged list, not each half.
    rows = items.list_items(conn, s, now=now, rules=rules, show="all", course_id=course_id, sort=sort, direction=direction, prefs=prefs)
    if peer is not None:
        rows += items.list_items(conn, s, now=now, rules=rules, show="all", course_id=peer["id"], sort=sort, direction=direction, prefs=prefs)
        rows = items.sorted_views(rows, sort, direction)
    # This course's own lines, all history (no Weeks selector here); the twin has its own page.
    mine = [gs for gs in trends.grade_series(conn, student_id=s["id"], prefs=prefs) if gs.course_id == course_id]
    chart = grade_chart(mine, title="This class")
    return render(request, conn, "course.html", current=f"kid:{key}", student=s, course=c, peer=peer,
                  grade=grades.get(course_id), peer_grade=grades.get(peer["id"]) if peer else None, grade_lines=grade_lines,
                  history=students.grade_history(conn, course_id), rows=rows, sort=sort, direction=direction,
                  sort_base=f"/kids/{quote(key)}/courses/{course_id}?",
                  grade_chart_json=chart_json(chart) if chart else None,
                  notes=notes.for_target(conn, "course", course_id), **source_ctx)


@router.post("/kids/{key}/courses/{course_id}/sources")
def course_sources(key: str, course_id: int, assignments: str = Form(""), grades: str = Form(""),
                   conn: sqlite3.Connection = Db, state=State):
    """The rule for exactly this kid and this class, keyed by the class's short name: the full
    Canvas name is not contained in HAC's name for the same class, so a rule written from it
    would miss the HAC-only rows. "" (or anything unknown) means the household default."""
    s = student_or_404(conn, key)
    c = students.course(conn, course_id)
    if c is None or c["student_id"] != s["id"]:
        raise HTTPException(404, "no such course")

    def pick(v: str) -> str | None:
        return v if v in sources.SOURCES else None

    actions.set_source_rule(state.home, s["key"], c["short_name"], pick(assignments), pick(grades))
    state.reload()
    return RedirectResponse(f"/kids/{quote(key)}/courses/{course_id}", status_code=303)

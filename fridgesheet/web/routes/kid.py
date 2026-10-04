"""The Kid page: the item list with filters, the expanded row, and the course page."""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from ... import grading, guidance, sources
from ...dates import deadline_date, wd_md, week_start
from .. import actions, outcomes
from ..app import Db, State, render, render_partial, student_or_404
from ..stores import changes, grades as grade_accounts, guidance as guidance_store, items, notes, students, trends
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


def _is_open(v) -> bool:
    """`items._keep`'s "open": still fixable or coming due, and not answered away."""
    return bool((v.open_in or v.upcoming) and not v.handled)


def _tally(views) -> list[tuple[str, int]]:
    """How a settled week came out: the five outcomes (docs/outcomes.md) as phrase keys with
    their counts, for the template to say in the child's tier."""
    t = items.record_for(views)
    parts = [("copy.tally_on_time", t.on_time), ("copy.tally_late", t.late), ("copy.tally_not_done", t.not_done),
             ("copy.tally_outside_canvas", t.done_offline), ("copy.tally_unknown", t.unknown)]
    return [(key, n) for key, n in parts if n] or [("copy.tally_listed", len(views))]


def weeks_of(shown, everything, now, *, by_day: bool = False) -> list[dict]:
    """The planner turned back a page at a time (the weekly pages, Assignments): every row the
    other filters allow, grouped by the week it was due, the newest week first, the list's own
    order kept inside each week; rows with no due date on a last page. A week with a row in
    the shown set (`shown`: the Open / Everything choice) is printed open with those rows; a
    week with none folds to its label and tally, its settled rows behind the fold. This week's
    page is printed whether or not anything is written on it. `by_day` marks the first row of
    each day, so a week sorted by due date reads as day rows."""
    this_week = week_start(now.date())
    shown_ids = {v.id for v in shown}
    groups: dict = {this_week: []}
    for v in everything:
        groups.setdefault(week_start(deadline_date(v.due)) if v.due else None, []).append(v)
    order = sorted((k for k in groups if k is not None), reverse=True) + ([None] if None in groups else [])
    out = []
    for k in order:
        vs = groups[k]
        mine = [v for v in vs if v.id in shown_ids]
        printed = bool(mine) or k == this_week
        lines, last_day = [], None
        for v in (mine if printed else vs):
            day = wd_md(deadline_date(v.due)) if (by_day and v.due) else ""
            lines.append((v, day if day != last_day else ""))
            last_day = day or last_day
        if k is None:
            word, when = "copy.no_due_date", ""
        else:
            word = {0: "copy.this_week", 1: "copy.next_week", -1: "copy.last_week"}.get((k - this_week).days // 7, "copy.week_of")
            when = wd_md(k)
        out.append(dict(key=k.isoformat() if k else "none", word=word, date=when, rows=lines, printed=printed,
                        tally=_tally(vs), current=k == this_week))
    return out


@router.get("/kids/{key}")
def kid(key: str, request: Request, conn: sqlite3.Connection = Db, state=State):
    s = student_or_404(conn, key)
    now, rules = state.now(), state.rules()
    f = _filters(request)
    rows = items.list_items(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window(), **f)
    # A question is open to the family whatever the record says, and on this page it is asked
    # on its own line (the weekly pages): Open shows every asked row the other filters allow.
    if f["show"] == "open":
        shown = {v.id for v in rows}
        asked = [v for v in items.list_items(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window(), **{**f, "show": "all"})
                 if v.asks and v.id not in shown]
        if asked:
            rows = items.sorted_views(rows + asked, f["sort"], f["direction"])
    # The weeks are turned back through every row the other filters allow: a week with nothing
    # in the shown set still prints, folded, with its tally.
    listed = rows if f["show"] == "all" else items.list_items(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window(), **{**f, "show": "all"})
    # The sections under the pages cover all of the kid's work, whatever the pages show.
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
    # Needs you now: the triage above the pages, the Plan's red rows and then the questions,
    # answered in place; a line on the pages that is up there offers nothing a second time.
    work = items.open_work(conn, s, now=now, rules=rules, prefs=state.sources(), **state.window())
    needs_now = items.needs_you_now(work, by_state["question"], now.date())
    # What got done, in the dashboard's five outcomes (docs/outcomes.md): on time, late and done
    # outside Canvas are done; not done and unknown are not, or not yet. One line above the questions.
    record = items.record_for(everything)
    return render(request, conn, "kid.html", current=f"kid:{key}", student=s, rows=rows, f=f, workspace="all",
                  weeks=weeks_of(rows, listed, now, by_day=f["sort"] == "due"), by_day=f["sort"] == "due", here=f"/kids/{quote(key)}",
                  done_so_far={"done": record.on_time + record.late + record.done_offline, "total": record.total, "on_time": record.on_time},
                  widened=items.widens_to_all(f["outcome"], f["flagged"], f["verdict"]),
                  needs_now=needs_now, up_top={v.id for v in needs_now},
                  questions=by_state["question"], decided=by_state["decided"], decided_earlier=by_state["decided_earlier"], waiting=by_state["waiting"],
                  sort=f["sort"], direction=f["direction"],
                  sort_base=_sort_base(key, f), course_options=students.course_options(conn, s["id"]),
                  SHOW=items.SHOW, FLAGGED=items.FLAGGED, SORTS=items.SORTS,
                  OUTCOMES=outcomes.ORDER, OUTCOME_LABELS=outcomes.LABELS)


def card_for(raw: str | None, item_id: int) -> str | None:
    """The question card an item detail replaced (#126): "q-<id>" from a question list,
    "qc-<id>" from a check-in or "row-<id>" from a week's page on Assignments, for this item
    only. The detail takes over that card's id, and its Close fetches the card back into it;
    anything else is a detail in a table row, which app.js closes by hiding the row."""
    return raw if raw in (f"q-{item_id}", f"qc-{item_id}", f"row-{item_id}") else None


@router.get("/items/{item_id}")
def item_detail(item_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    now, rules = state.now(), state.rules()
    s = students.owner_of_item(conn, item_id)
    v = items.one(conn, s, item_id, now=now, rules=rules, prefs=state.sources(), **state.window()) if s is not None else None
    if v is None:
        raise HTTPException(404, "no such item")
    return render_partial(request, conn, "_item_detail.html", student=s, item=v,
                          item_history=changes.for_item(conn, s["id"], item_id, now=state.now(), prefs=state.sources()), message=None,
                          notes=notes.for_target(conn, "item", item_id), card=card_for(request.query_params.get("card"), item_id),
                          # `?tone=line`: a record opened under a log line (Changes) keeps the sheet's word at its
                          # head like one opened from a week's line, without a card for Close to put back.
                          with_tone=request.query_params.get("tone") == "line")


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
    # This course and its twin in the other source are one list to a parent: `list_items`
    # widens a course id to its pair itself and sorts the merged list, so it is asked once.
    # Asking again for the peer doubled every row of a paired class (#183).
    rows = items.list_items(conn, s, now=now, rules=rules, show="all", course_id=course_id, sort=sort, direction=direction, prefs=prefs)
    # The class's assignments as the weekly pages (the class's record, 2026-09-30): every row
    # from both gradebooks printed on the week it was due, settled ones checked off in place;
    # a record hides nothing behind a fold.
    # This course's own lines, all history (no Weeks selector here); the twin has its own page.
    mine = [gs for gs in trends.grade_series(conn, student_id=s["id"], prefs=prefs) if gs.course_id == course_id]
    chart = grade_chart(mine, title="This class", now=now)
    # The grade strip: this course's own observations, one cell per refresh that moved the
    # grade (Canvas' current score, or HAC's average), and the other source's number from the
    # twin, first when it is the official one and last in pencil when it is not.
    own_field = "current" if c["source"] == "canvas" else "average"
    history = students.grade_history(conn, course_id)
    history_cells = [(g, g[own_field] if g[own_field] is not None else g["final"]) for g in history]
    history_cells = [(g, v) for g, v in history_cells if v is not None]
    pick = source_ctx["choice"].grades
    other_grade = next((g for g in grade_lines if g.source != c["source"]), None)
    # The twin's number in its cell: Canvas' letter beside the value; HAC's "as of" date (the
    # gradebook's own date, not a refresh) named for what it is, without the year, so the pencil
    # line is short on a phone (finish review 2026-09-30).
    other_letter = other_grade.extra if other_grade and other_grade.source == "canvas" else ""
    other_asof = re.sub(r"/\d{4}$", "", other_grade.extra.replace("updated ", "")) if other_grade and other_grade.source == "hac" and other_grade.extra else ""
    # How the average is figured (spec 2026-10-03 §7.2): this course's own account and the
    # twin's, the official source's first whichever page this is.
    account = grade_accounts.account_for(conn, c, grades.get(course_id))
    other_account = grade_accounts.account_for(conn, peer, grades.get(peer["id"])) if peer else None
    accounts = sorted([a for a in (account, other_account) if a is not None], key=lambda a: a.source != pick)
    # What moves it (spec 2026-10-04 §7.2): the official source's levers from the kid's open
    # work; the rows are the same views the Plan lists, so the two never disagree.
    work = items.open_work(conn, s, now=now, rules=rules, prefs=prefs, **state.window())
    official_course = c if c["source"] == pick else (peer or c)
    moves = guidance_store.for_class(conn, official_course, accounts[0], work, state.settings.grading) if accounts else None
    moves_said = guidance_store.sentence_for(moves) if moves else []
    lever_views = {v.id: v for v in list(work.fixable) + list(work.upcoming)}
    return render(request, conn, "course.html", current=f"kid:{key}", student=s, course=c, peer=peer,
                  accounts=accounts, how_for=grade_accounts.how_for, fmt_points=grading.fmt_points, fmt_avg=grading.fmt_avg,
                  moves=moves, moves_said=moves_said, lever_views=lever_views, lever_note=guidance_store.lever_note, fmt_worth=guidance.fmt_worth,
                  grade=grades.get(course_id), peer_grade=grades.get(peer["id"]) if peer else None, grade_lines=grade_lines,
                  history=history, history_cells=history_cells, other_grade=other_grade, other_letter=other_letter, other_asof=other_asof,
                  own_label="Canvas current" if c["source"] == "canvas" else "HAC average", own_official=pick == c["source"],
                  rows=rows, sort=sort, direction=direction, by_day=sort == "due",
                  weeks=weeks_of(rows, rows, now, by_day=sort == "due"), here=f"/kids/{quote(key)}/courses/{course_id}",
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

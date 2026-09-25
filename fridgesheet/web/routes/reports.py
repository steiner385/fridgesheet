"""Reports: the list of code and saved reports, the builder, and its live preview."""
from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from datetime import date as _date

from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from ... import reports as registry
from ...naming import safe_name
from .. import db, schedules, views
from ..app import Db, State, render, render_partial
from ..stores import reports as store, students

router = APIRouter()


def definition_from_form(form) -> views.Definition:
    """The builder's flat form fields as a definition. Unknown values fail `validate`, not here."""
    sort = [{"column": c, "dir": d} for c, d in
            zip(form.getlist("sort_column"), form.getlist("sort_dir")) if c]
    filters = [{"field": f, "op": o, "value": v} for f, o, v in
               zip(form.getlist("filter_field"), form.getlist("filter_op"), form.getlist("filter_value")) if f]
    group_by = form.get("group_by") or None
    return views.from_json(views.Definition(
        title=form.get("title", ""), source=form.get("source", "items"),
        scope=tuple(form.getlist("scope")), columns=tuple(form.getlist("columns")),
        filters=tuple(filters), group_by=group_by, sort=tuple(sort),
        orientation=form.get("orientation", "portrait"),
        per_kid_sections=bool(form.get("per_kid_sections")),
        window=form.get("window", "all"),
        date_from=form.get("date_from", ""), date_to=form.get("date_to", ""),
    ).to_json())


def _page(request, conn, state, *, messages=(), errors=()):
    return render(request, conn, "reports.html", current="reports",
                  saved=store.all(conn), code=list(registry.REPORTS.values()),
                  TEMPLATES=store.TEMPLATES,
                  messages=list(messages), errors=list(errors))


@router.get("/reports")
def page(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _page(request, conn, state)


@router.post("/reports/seed")
def seed(request: Request, conn: sqlite3.Connection = Db, state=State):
    n = store.seed_templates(conn, now=db.now_iso(state.tz))
    msg = f"Added {n} starter reports." if n else "This app already has reports; the starters were not added."
    return _page(request, conn, state, messages=[msg])


def _builder(request, conn, state, *, report=None, d=None, problems=(), messages=()):
    """The builder over `d`, which may well be a definition that does not validate -- that is
    what a parent comes here to repair. The column dict is chosen here rather than in the
    template, so an unknown source is a problem shown on the page, not an `UndefinedError`."""
    d = d or views.defaults()
    cols = views.COLUMNS.get(d.source) or views.COLUMNS["items"]
    return render(request, conn, "report_builder.html", current="reports", report=report,
                  d=d, cols=cols, SOURCES=views.SOURCES, OPS=views.OPS,
                  ORIENTATIONS=views.ORIENTATIONS, WINDOWS=views.WINDOWS, problems=list(problems), messages=list(messages),
                  kids=students.visible(conn))


@router.get("/reports/new")
def new(request: Request, conn: sqlite3.Connection = Db, state=State):
    return _builder(request, conn, state)


async def _save(request, conn, state, report_id: int | None):
    form = await request.form()
    d = definition_from_form(form)
    problems = views.validate(d)
    name = (form.get("name") or d.title).strip() or "Untitled report"
    if problems:
        return _builder(request, conn, state, report=store.by_id(conn, report_id) if report_id else None,
                        d=d, problems=problems)
    now = db.now_iso(state.tz)
    if report_id is None:
        report_id = store.create(conn, name, d.to_json(), now=now)
    elif not store.update(conn, report_id, name, d.to_json(), now=now):
        raise HTTPException(404, "no such report")
    return _builder(request, conn, state, report=store.by_id(conn, report_id), d=d, messages=["Saved."])


@router.post("/reports/new")
async def create(request: Request, conn: sqlite3.Connection = Db, state=State):
    return await _save(request, conn, state, None)


@router.post("/reports/builder")
async def rebuild(request: Request, conn: sqlite3.Connection = Db, state=State):
    """The builder redrawn for the source just picked (#6): the column, group, sort and filter
    lists are that source's, and whatever the old choice had that this source lacks is
    dropped rather than carried as a problem. Nothing is saved."""
    form = await request.form()
    d = definition_from_form(form)
    known = views.COLUMNS.get(d.source) or {}
    d = views.Definition(
        title=d.title, source=d.source, scope=d.scope,
        columns=tuple(c for c in d.columns if c in known) or tuple(views.DEFAULT_COLUMNS.get(d.source, ())),
        filters=tuple(f for f in d.filters if f.get("field") in known),
        group_by=d.group_by if d.group_by in known else None,
        sort=tuple(s for s in d.sort if s.get("column") in known),
        orientation=d.orientation, per_kid_sections=d.per_kid_sections, window=d.window,
        date_from=d.date_from, date_to=d.date_to)
    rid = form.get("report_id")
    report = store.by_id(conn, int(rid)) if rid and str(rid).isdigit() else None
    return _builder(request, conn, state, report=report, d=d)


def _chart_json(rendered) -> str | None:
    """`chart_config()`'s output, safe to inline verbatim inside a `<script>` tag.

    A series/axis/bucket label can come from a course or assignment name -- untrusted the same
    way `sheet.py`'s `_esc()` and the CSV formula-injection guard already treat those names --
    so a label of literal `</script>` must not be able to close the element early and either
    break the JSON or splice in markup of its own. `json.dumps` alone does not guard against
    that; the escapes below live inside JSON string values, which `JSON.parse` unescapes
    transparently, so the value round-trips unchanged.
    """
    if not (rendered and rendered.chart):
        return None
    return (json.dumps(views.chart_config(rendered.chart))
            .replace('<', '\\u003c')
            .replace('>', '\\u003e')
            .replace('&', '\\u0026')
            .replace(' ', '\\u2028')
            .replace(' ', '\\u2029'))


@router.post("/reports/preview")
async def preview(request: Request, conn: sqlite3.Connection = Db, state=State):
    form = await request.form()
    d = definition_from_form(form)
    problems = views.validate(d)
    rendered = None
    if not problems:
        try:
            rendered = views.build(conn, d, now=state.now(), rules=state.rules(), nicknames=state.settings.nicknames, prefs=state.sources(), window=state.window())
        except views.ViewError as e:
            problems = [str(e)]
    return render_partial(request, conn, "_report_preview.html", rendered=rendered, problems=problems,
                          chart_json=_chart_json(rendered))


@router.get("/reports/{report_id}/view")
def view(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    """A standalone, browser-printable rendering of the report -- what a parent clicking its
    name from the list wants to read, not the builder that produced it."""
    row, d, rendered = _rendered_or_400(conn, state, report_id)
    return render(request, conn, "report_view.html", report=row, rendered=rendered, now=state.now(),
                  chart_json=_chart_json(rendered))


@router.get("/reports/{report_id}")
def edit(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    row = store.by_id(conn, report_id)
    if row is None:
        raise HTTPException(404, "no such report")
    try:
        d = views.from_json(row["definition"])
        problems = views.validate(d)       # a stored source this version does not know (#6)
    except views.ViewError as e:
        # A definition a hand edit or an older version left unreadable: the builder is exactly
        # where it gets repaired, so open it on a fresh one and say what was wrong.
        d, problems = views.defaults(), [f"This report's definition could not be read ({e}); "
                                         "the builder below starts from a fresh one."]
    return _builder(request, conn, state, report=row, d=d, problems=problems)


@router.post("/reports/{report_id}")
async def save(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    if store.by_id(conn, report_id) is None:
        raise HTTPException(404, "no such report")
    return await _save(request, conn, state, report_id)


@router.post("/reports/{report_id}/delete")
def remove(report_id: int, request: Request, conn: sqlite3.Connection = Db, state=State):
    """Delete the report -- but only once its schedule is gone.

    The schedule goes first, and a removal that fails stops the delete. A saved report is
    schedulable (`view:<id>`), and `reports.id` is an `INTEGER PRIMARY KEY` with no
    `AUTOINCREMENT`, so sqlite reissues the id of a deleted row: a timer left behind would
    have no row on the Schedules page to turn it off with, and would print the *next* report
    on the deleted one's days, time and printer.
    """
    row = store.by_id(conn, report_id)
    if row is None:
        raise HTTPException(404, "no such report")
    lines: list[str] = []
    out = schedules.forget(f"view:{report_id}", home=state.home, log=lines.append,
                           title=row["name"], scheduling=state.extra.get("scheduling"))
    if not out.ok:
        return _page(request, conn, state,
                     errors=[f"{row['name']} was not deleted: its schedule is still installed."] + out.errors)
    if not store.delete(conn, report_id):
        raise HTTPException(404, "no such report")
    state.reload()
    return _page(request, conn, state, messages=["Deleted."] + out.messages)


def _rendered_or_400(conn, state, report_id: int):
    row = store.by_id(conn, report_id)
    if row is None:
        raise HTTPException(404, "no such report")
    try:
        d = views.from_json(row["definition"])
        return row, d, views.build(conn, d, now=state.now(), rules=state.rules(), nicknames=state.settings.nicknames, prefs=state.sources(), window=state.window())
    except views.ViewError as e:
        raise HTTPException(400, str(e)) from None


def _filename(title: str, day: _date, ext: str) -> str:
    """Same sanitising as a view report's `archive_name` (`naming.safe_name`), so a title that
    is safe for one is safe for the other."""
    return f"{safe_name(title)} {day.isoformat()}.{ext}"


def _disposition(name: str) -> str:
    """An attachment header for `name`. Headers are Latin-1, so a Cyrillic or emoji title raised
    on export (#6): send an ASCII fallback in `filename` and the real name as RFC 5987
    `filename*`, which every current browser prefers."""
    ascii_name = name.encode("ascii", "ignore").decode().strip() or "report"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"-?\d+(\.\d+)?")


def _cell(value) -> str:
    """A CSV cell a spreadsheet will not run. Assignment names come from Canvas and HAC; one
    starting with `=`, `+`, `-` or `@` opens as a formula, so it gets a leading apostrophe
    (OWASP's advice). A plain number, negative or not, is left as it is."""
    text = str(value)
    if text.startswith(_FORMULA_START) and not _NUMBER.fullmatch(text):
        return "'" + text
    return text


def _group_label(d, rendered) -> str | None:
    """The heading of the grouping column when it is not already one of the report's columns.

    A grouped report shows its group as a heading, which a flat export throws away; the export
    carries it as a column instead. `None` means the group value is already in every row.
    """
    if not d.group_by or d.group_by in [c.id for c in rendered.columns]:
        return None
    col = views.COLUMNS.get(d.source, {}).get(d.group_by)
    return col.label if col else d.group_by


@router.get("/reports/{report_id}/export.csv")
def export_csv(report_id: int, conn: sqlite3.Connection = Db, state=State):
    """The rendered rows as CSV. A grouped report keeps its grouping: the group column comes
    first in the header and in every row, unless the report already prints that column."""
    row, d, rendered = _rendered_or_400(conn, state, report_id)
    group_label = _group_label(d, rendered)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([_cell(v) for v in ([group_label] if group_label else []) + [c.label for c in rendered.columns]])
    for g in rendered.groups:
        for r in g.rows:
            w.writerow([_cell(v) for v in ([g.label] if group_label else []) + [r.get(c.id, "") for c in rendered.columns]])
    name = _filename(d.title or row["name"], state.now().date(), "csv")
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": _disposition(name)})


@router.get("/reports/{report_id}/export.json")
def export_json(report_id: int, conn: sqlite3.Connection = Db, state=State):
    """The rendered rows as JSON.

    `columns` and `labels` are the report's columns, by id and by heading; `rows` is every row
    in the printed order. `groups` is those same rows split the way the PDF prints them --
    one object per group with the heading in `label` -- so a grouped report does not lose its
    grouping on the way out. A report with no `group_by` has one group whose label is "" --
    or none at all when no row matched, so `groups: []` means an empty report.
    """
    row, d, rendered = _rendered_or_400(conn, state, report_id)
    name = _filename(d.title or row["name"], state.now().date(), "json")
    return JSONResponse({"title": rendered.title, "columns": [c.id for c in rendered.columns],
                         "labels": [c.label for c in rendered.columns],
                         "group_by": d.group_by,
                         "rows": [r for g in rendered.groups for r in g.rows],
                         "groups": [{"label": g.label, "rows": g.rows} for g in rendered.groups],
                         "truncated": rendered.truncated},
                        headers={"Content-Disposition": _disposition(name)})

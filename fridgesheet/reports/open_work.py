# fridgesheet/reports/open_work.py
"""The open-work sheet: one section per kid, the rows the Open work page shows.

The rows come from the database whenever it holds the snapshot being built: the same decided
items the page lists (`web/stores/items.open_work` -- outcomes, verdicts, late-work windows,
flags), turned into the sheet's rows by `from_views`, so the paper says exactly what the
screen says (#137). The screens and `open_items` used to decide "open" separately and
disagreed four ways. A household that has never recorded a refresh, or a snapshot the
database has not caught up with (a bare `refresh` with no `--record`), gets
`open_items.open_items` over the snapshot alone, which follows the same rules.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

from .. import config, late_rules, open_items, sheet
from ..web import reconcile, tiers
from ..web.stores import items as items_store, students
from .base import Built, BuildContext, ReportError


def wanted(key: str, kid: str | None, names: dict[str, str], keys=()) -> bool:
    """`--kid`: the student's first name or printed name, or else the start of one ("al" is Alex),
    or else a longer form of the first name ("alexander" is Alex).

    Each step applies only when the one before it selects nobody: `--kid Sam` is Sam, not also
    his sister Samantha, whose key it merely begins, and `--kid samant` is Samantha, not Sam
    (#134). `keys` is every student's key. The MCP server finds a kid by the same steps
    (`server._kid`), so "Mimi" means the same child everywhere (#151)."""
    if not kid:
        return True
    b = kid.strip().lower()

    def names_of(k: str) -> list[str]:
        return [n for n in (k.lower(), names.get(k, "").lower()) if n]

    tests = (lambda k: b in names_of(k),
             lambda k: any(n.startswith(b) for n in names_of(k)),
             lambda k: b.startswith(k.lower()))
    for test in tests:
        if any(test(k) for k in (keys or (key,))):
            return test(key)
    return False


def sheet_status(v: items_store.ItemView) -> str:
    """The sheet's word for a page row: DUE TODAY / DUE SUN for what is coming due, else the
    capitals of its status phrase (`sheet.STATUS_WORD`), else ZERO for a gradebook's zero."""
    if v.upcoming and not v.overdue:
        return v.status.upper()
    if v.status in sheet.STATUS_WORD:
        return sheet.STATUS_WORD[v.status]
    if v.grade_zero:
        return "ZERO"
    return v.status.upper()


def from_views(work: items_store.OpenWork, kid: str, now: datetime) -> open_items.OpenWork:
    """The page's four lists as the sheet's three: still fixable and coming due are its rows,
    past the window is its "Not shown" count, handled its "Handled" count. Rows take the
    sheet's own order (`OpenWork.sort`), so a day's sheet reads like the last one."""
    def row(v: items_store.ItemView) -> open_items.Item:
        scored = v.hac if v.grade_source == "hac" else (v.canvas if v.canvas is not None else v.hac)
        return open_items.Item(
            key=v.key, kid=kid, course=v.course_short, name=v.name, due=v.due, status=sheet_status(v), overdue=v.overdue,
            source="both" if len(v.sources) == 2 else (v.sources[0] if v.sources else "canvas"), kind=v.kind,
            points=v.points, score=scored["score"] if scored is not None else None, assigned=v.assigned,
            late_until=v.late_until, credit=v.credit, is_assessment=v.is_assessment, flag=v.flag or "",
        )
    return open_items.OpenWork(kid=kid, as_of=now, items=[row(v) for v in work.fixable + work.upcoming],
                               dropped=[row(v) for v in work.past_window], handled=[row(v) for v in work.handled]).sort()


def decided_work(conn, snap: dict, now: datetime, *, days_ahead: int, overdue_days: int, rules, prefs=None) -> dict[str, items_store.OpenWork] | None:
    """Each snapshot student's open work as the page decides it, or None when the database
    cannot stand in for this snapshot: no connection, a snapshot it has not recorded (its
    newest refresh is older than the snapshot's `fetched_at`), or a student it has never seen."""
    if conn is None:
        return None
    try:
        latest = conn.execute("SELECT MAX(started_at) AS at FROM refreshes").fetchone()["at"]
        recorded, fetched = reconcile.comparable(datetime.fromisoformat(latest or ""), datetime.fromisoformat(snap.get("fetched_at") or ""))
    except (sqlite3.Error, TypeError, ValueError):
        return None
    if recorded < fetched:
        return None
    out: dict[str, items_store.OpenWork] = {}
    for key in snap.get("students") or {}:
        student = students.by_key(conn, key)
        if student is None:
            return None
        out[key] = items_store.open_work(conn, student, now=now, rules=rules, days_ahead=days_ahead, overdue_days=overdue_days, prefs=prefs)
    return out


class OpenWorkReport:
    key = "open-work"
    title = "Open Work Sheet"
    output_dir = "sheets"
    default_time = "14:00"

    def archive_name(self, day: date) -> str:
        return f"{day.isoformat()} Open Work.pdf"

    def build(self, snap: dict, ctx: BuildContext) -> Built:
        days_ahead = config.day_option(ctx.options, "days_ahead")
        overdue_days = config.day_option(ctx.options, "overdue_days")
        rules = late_rules.load(ctx.home / "late-rules.toml", household=snap["students"])
        decided = decided_work(ctx.conn, snap, ctx.now, days_ahead=days_ahead, overdue_days=overdue_days, rules=rules, prefs=ctx.settings.sources)
        sheets: list[sheet.KidSheet] = []
        rows: dict[str, list[dict]] = {}
        counts = []
        for key, entry in snap["students"].items():
            if not wanted(key, ctx.kid, ctx.nicknames, snap["students"]):
                continue
            label = ctx.nicknames.get(key, key)
            if decided is not None:
                work = from_views(decided[key], label, ctx.now)
            else:
                # Late rules and source rules resolve by the key, as the web does; the label is only printed (#133).
                work = open_items.open_items(entry, label, ctx.now, days_ahead=days_ahead, overdue_days=overdue_days, rules=rules,
                                             flags=ctx.flags.get(key, {}), prefs=ctx.settings.sources, student_key=key)
            diff = open_items.compare(ctx.prev_rows.get(key, []), work.items, work.handled) if ctx.prev_rows is not None else None
            # Each kid's section speaks in that kid's tier, as their pages do (kids' UX audit F11).
            sheets.append(sheet.KidSheet(label, work, diff, ctx.prev_label, tier=tiers.for_student(ctx.settings, key)))
            rows[key] = [i.to_dict() for i in work.items]
            counts.append(f"{label}={len(work.items)}")
        if not sheets:
            raise ReportError(f"no student matches --kid {ctx.kid!r}; known: {', '.join(snap['students'])}" if ctx.kid
                              else "the snapshot has no students yet; run a refresh first")
        pdf = ctx.pdf_path("sheet")
        pages = sheet.build_pdf(sheets, pdf, data_as_of=ctx.data_as_of, days_ahead=days_ahead, overdue_days=overdue_days,
                                stale_note=ctx.stale_note, printed_at=ctx.now)
        return Built(pdf=pdf, rows=rows, summary=f"{pages}p {' '.join(counts)}")

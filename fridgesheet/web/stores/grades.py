"""The account of each class's average, and the report card's lines, read from the database
(spec 2026-10-03 §6). The arithmetic is `fridgesheet.grading`; this module only gathers rows."""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from ... import dates, grading
from ...sources import pick_value
from . import students


def latest_subtotals(conn: sqlite3.Connection, course_id: int) -> list[sqlite3.Row]:
    """The newest set of HAC category subtotal rows for a course, in HAC's order. Empty when the
    newest set is the cleared-table sentinel ingest writes (a row with no category)."""
    return conn.execute(
        """SELECT * FROM category_observations WHERE course_id = ? AND category <> ''
           AND refresh_id = (SELECT MAX(refresh_id) FROM category_observations WHERE course_id = ?) ORDER BY id""",
        (course_id, course_id)).fetchall()


def subtotal_history(conn: sqlite3.Connection, course_id: int) -> list[list[sqlite3.Row]]:
    """Every set, oldest first: one list per refresh that changed the breakdown; a cleared table
    is an empty list."""
    out: dict[int, list[sqlite3.Row]] = {}
    for r in conn.execute("SELECT * FROM category_observations WHERE course_id = ? ORDER BY refresh_id, id", (course_id,)):
        rows = out.setdefault(r["refresh_id"], [])
        if r["category"]:
            rows.append(r)
    return list(out.values())


_ROWS = """SELECT i.id, i.name, i.points, o.score, o.excused, o.missing, o.state, ic.category
           FROM items i
           JOIN item_observations o ON o.item_id = i.id AND o.source = :src
             AND o.id = (SELECT o2.id FROM item_observations o2 WHERE o2.item_id = i.id AND o2.source = :src
                         ORDER BY o2.refresh_id DESC, o2.id DESC LIMIT 1)
           LEFT JOIN item_categories ic ON ic.item_id = i.id AND ic.source = :src
           WHERE i.course_id IN (:own, :peer)"""


def hac_rows(conn: sqlite3.Connection, course: sqlite3.Row) -> list[dict]:
    """A HAC course's rows: its own HAC-only items plus the HAC observations hanging on its
    Canvas twin's items (ingest attaches a paired HAC row to the Canvas item)."""
    peer = course["peer_course_id"] if course["peer_course_id"] is not None else -1
    return [{"name": r["name"], "category": r["category"] or "", "score": r["score"], "points": r["points"], "excused": bool(r["excused"])}
            for r in conn.execute(_ROWS, {"src": "hac", "own": course["id"], "peer": peer})]


def canvas_rows(conn: sqlite3.Connection, course: sqlite3.Row) -> list[dict]:
    return [{"name": r["name"], "group": r["category"] or "", "score": r["score"], "points": r["points"],
             "excused": bool(r["excused"]), "missing": bool(r["missing"]), "state": r["state"]}
            for r in conn.execute(_ROWS, {"src": "canvas", "own": course["id"], "peer": -1})]


def account_for(conn: sqlite3.Connection, course: sqlite3.Row, grade_row: sqlite3.Row | None) -> grading.Account:
    """This course's own account: HAC's from its subtotals and rows, Canvas's from its rows."""
    if course["source"] == "hac":
        subs = [{"category": s["category"], "earned": s["earned"], "possible": s["possible"], "percent": s["percent"], "weight": s["weight"]}
                for s in latest_subtotals(conn, course["id"])]
        return grading.account_hac(grade_row["average"] if grade_row else None, subs, hac_rows(conn, course))
    current = grade_row["current"] if grade_row else None
    final = grade_row["final"] if grade_row else None
    return grading.account_canvas(current, final, grade_row is not None and current is None and final is None, canvas_rows(conn, course))


def how_for(account: grading.Account | None) -> tuple[str, dict]:
    """The one-line "how" for a report-card line: the phrasing key and its values, chosen in
    the spec's order (§6). Numbers are formatted here, so phrases carry none of their own."""
    if account is None or account.reported is None:
        if account is not None and account.source == "canvas" and account.hidden:
            return "rc.canvas_hidden", {}
        return "rc.no_grade", {}
    a = account
    if a.source == "canvas":
        if a.hidden:
            return "rc.canvas_hidden", {}
        if a.final is not None and a.final < a.reported:
            if a.missing:
                return "rc.canvas_partial", {"current": grading.fmt_avg(a.reported), "final": grading.fmt_avg(a.final), "missing": str(a.missing)}
            # Canvas's final zeroes unsubmitted work whether or not a row is flagged missing.
            return "rc.canvas_partial_unsubmitted", {"current": grading.fmt_avg(a.reported), "final": grading.fmt_avg(a.final)}
        # Canvas's how is always what it counts; the match against its groups is the class page's.
        return "rc.canvas_current", {"current": grading.fmt_avg(a.reported)}
    if a.basis == "none":
        return "rc.no_breakdown", {"reported": grading.fmt_avg(a.reported)}
    if a.match == "exact":
        if a.basis == "weighted":
            return "rc.adds_up_weighted", {"n": str(sum(1 for l in a.lines if l.share > 0))}
        if a.source == "hac" and a.basis == "subtotals" and a.zero_points > 0:
            return "rc.adds_up_zeros", {"earned": grading.fmt_points(a.earned), "possible": grading.fmt_points(a.possible),
                                        "zero_points": grading.fmt_points(a.zero_points)}
        return "rc.adds_up", {"earned": grading.fmt_points(a.earned), "possible": grading.fmt_points(a.possible)}
    if a.match == "off":
        if a.source == "hac" and a.basis == "rows":
            return "rc.rows_dont_add_up", {"rebuilt": grading.fmt_avg(a.rebuilt), "reported": grading.fmt_avg(a.reported),
                                           "rows": str(sum(l.rows for l in a.lines))}
        return "rc.dont_add_up", {"rebuilt": grading.fmt_avg(a.rebuilt), "reported": grading.fmt_avg(a.reported)}
    return "rc.no_breakdown", {"reported": grading.fmt_avg(a.reported)}


@dataclass(frozen=True)
class ReportLine:
    course_id: int            # the page to link: the Canvas course when paired, else the lone course
    short_name: str
    name: str
    official: float | None
    official_source: str      # "hac" | "canvas" | ""
    letter: str
    as_of: str                # HAC's last_updated without the year, or the refresh day for Canvas
    account: grading.Account | None     # the official source's account
    other: grading.Account | None       # the other source's, when it has a number
    how: tuple[str, dict]


def _as_of(grade_row: sqlite3.Row | None, source: str, conn, tz) -> str:
    if grade_row is None:
        return ""
    if source == "hac":
        return re.sub(r"/\d{4}$", "", grade_row["last_updated"] or "")
    r = conn.execute("SELECT started_at FROM refreshes WHERE id = ?", (grade_row["refresh_id"],)).fetchone()
    return dates.md(datetime.fromisoformat(r["started_at"]).astimezone(tz)) if r else ""   # "9/15", like HAC's own date


def report_card(conn: sqlite3.Connection, student: sqlite3.Row, prefs, scale: grading.GradeScale, tz) -> list[ReportLine]:
    """One line per class (a Canvas course and its HAC peer are one class), the sheet's order."""
    rows = students.courses(conn, student["id"])
    by_id = {r["id"]: r for r in rows}
    grade_rows = students.latest_grades(conn, student["id"])
    out: list[ReportLine] = []
    seen: set[int] = set()
    for r in rows:
        if r["id"] in seen:
            continue
        peer = by_id.get(r["peer_course_id"]) if r["peer_course_id"] else None
        seen.add(r["id"])
        if peer is not None:
            seen.add(peer["id"])
        canvas = r if r["source"] == "canvas" else peer
        hac = r if r["source"] == "hac" else peer
        canvas_g = grade_rows.get(canvas["id"]) if canvas is not None else None
        hac_g = grade_rows.get(hac["id"]) if hac is not None else None
        pick = prefs.resolve(student["key"], r["name"], peer["name"] if peer else None).grades
        official, src = pick_value(pick, canvas_g["current"] if canvas_g else None, hac_g["average"] if hac_g else None)
        accounts: dict[str, grading.Account] = {}
        if canvas is not None:
            accounts["canvas"] = account_for(conn, canvas, canvas_g)
        if hac is not None:
            accounts["hac"] = account_for(conn, hac, hac_g)
        lead_src = src or (pick if pick in accounts else next(iter(accounts), ""))
        account = accounts.get(lead_src)
        other = next((a for s, a in accounts.items() if s != lead_src and a.reported is not None), None)
        link = canvas if canvas is not None else hac
        out.append(ReportLine(link["id"], link["short_name"], link["name"], official, src or "", scale.letter(official),
                              _as_of(hac_g if lead_src == "hac" else canvas_g, lead_src, conn, tz), account, other, how_for(account)))
    return sorted(out, key=lambda l: l.short_name.lower())

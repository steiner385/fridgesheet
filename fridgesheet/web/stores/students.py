"""Students, their courses and the latest grade per course."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


def visible(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM students WHERE hidden = 0 ORDER BY key").fetchall()


def by_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM students WHERE key = ?", (key,)).fetchone()


def by_id(conn: sqlite3.Connection, student_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()


def courses(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM courses WHERE student_id = ? AND hidden = 0 ORDER BY short_name, source", (student_id,)).fetchall()


def course_options(conn: sqlite3.Connection, student_id: int) -> list[tuple[int, str]]:
    """(id, label) for a course filter: one entry per *class*, not per source.

    `courses` holds a row per source, so a kid in seven classes had fourteen options --
    "Honors Biology (canvas)" and "Honors Biology (hac)" -- and a parent thinks of one class
    (#40 item 8). A Canvas course and its paired HAC course collapse to the Canvas id; the
    filter expands that id back to both (`items.list_items`). A class only one source knows
    keeps its own id and says which source, since that is the whole reason it is separate."""
    rows = courses(conn, student_id)
    by_id = {r["id"]: r for r in rows}
    out: list[tuple[int, str]] = []
    seen: set[int] = set()
    for r in rows:
        if r["id"] in seen:
            continue
        peer = by_id.get(r["peer_course_id"]) if r["peer_course_id"] else None
        if peer is not None:
            canvas = r if r["source"] == "canvas" else peer
            seen.update((r["id"], peer["id"]))
            out.append((canvas["id"], canvas["short_name"]))
        else:
            seen.add(r["id"])
            out.append((r["id"], f"{r['short_name']} ({'HAC' if r['source'] == 'hac' else 'Canvas'} only)"))
    return sorted(out, key=lambda o: o[1].lower())


def course(conn: sqlite3.Connection, course_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()


def latest_grades(conn: sqlite3.Connection, student_id: int) -> dict[int, sqlite3.Row]:
    """course_id -> the newest grade_observations row for that course."""
    out: dict[int, sqlite3.Row] = {}
    for r in conn.execute(
            """SELECT g.* FROM grade_observations g JOIN courses c ON c.id = g.course_id
               WHERE c.student_id = ? ORDER BY g.refresh_id DESC, g.id DESC""", (student_id,)):
        out.setdefault(r["course_id"], r)
    return out


def owner_of_item(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    """The student an item belongs to, or None -- including when that student is hidden, so
    an item URL is as dead as `/kids/<key>` is for a kid the parent has put away."""
    return conn.execute(
        "SELECT s.* FROM students s JOIN items i ON i.student_id = s.id WHERE i.id = ? AND s.hidden = 0",
        (item_id,)).fetchone()


def grade_history(conn: sqlite3.Connection, course_id: int) -> list[sqlite3.Row]:
    """Every grade observation for one course, oldest first, with the refresh time."""
    return conn.execute(
        """SELECT g.*, r.started_at FROM grade_observations g JOIN refreshes r ON r.id = g.refresh_id
           WHERE g.course_id = ? ORDER BY g.refresh_id""", (course_id,)).fetchall()


@dataclass(frozen=True)
class GradeLine:
    source: str          # canvas | hac
    value: float
    label: str           # "Canvas current" | "HAC average"
    extra: str           # the letter, or when HAC last updated it


def grade_lines(canvas_row, hac_row, pick: str) -> list[GradeLine]:
    """A class's averages, the family's official source first (sources.py). The other source's
    number stays, second: a parent choosing HAC still wants to see what Canvas says."""
    out: list[GradeLine] = []
    if canvas_row is not None and canvas_row["current"] is not None:
        out.append(GradeLine("canvas", canvas_row["current"], "Canvas current", canvas_row["letter"] or ""))
    if hac_row is not None and hac_row["average"] is not None:
        updated = f"updated {hac_row['last_updated']}" if hac_row["last_updated"] else ""
        out.append(GradeLine("hac", hac_row["average"], "HAC average", updated))
    return sorted(out, key=lambda g: g.source != pick)

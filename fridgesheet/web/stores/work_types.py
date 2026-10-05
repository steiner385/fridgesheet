"""Corrections and class rules for assignment types (spec 2026-10-04 assignment types §5, §6).

`work_types.family_of` decides; this module only reads what it needs and writes what a
grown-up chose. A class is a Canvas course and its paired HAC course, so a rule made on
either applies to both, as a class filter does (`items.list_items`)."""
from __future__ import annotations

import sqlite3
from datetime import datetime

from ... import work_types
from .. import reconcile
from ...work_types import Facts, Rule, Typed


def pair(conn: sqlite3.Connection, course_id: int) -> set[int]:
    row = conn.execute("SELECT peer_course_id FROM courses WHERE id = ?", (course_id,)).fetchone()
    return {course_id} | ({row["peer_course_id"]} if row and row["peer_course_id"] else set())


def rules_for(conn: sqlite3.Connection, course_ids: set[int]) -> list[sqlite3.Row]:
    if not course_ids:
        return []
    marks = ",".join("?" * len(course_ids))
    return conn.execute(f"SELECT * FROM type_rules WHERE course_id IN ({marks}) ORDER BY created_at DESC, id DESC",
                        tuple(course_ids)).fetchall()


def _rule(r: sqlite3.Row) -> Rule:
    return Rule(r["id"], r["field"], r["value"], r["family"], r["created_at"])


def _categories(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    for i in range(0, len(item_ids), 500):                 # SQLite's bound-parameter limit
        chunk = item_ids[i:i + 500]
        for r in conn.execute(f"SELECT item_id, source, category FROM item_categories WHERE item_id IN ({','.join('?' * len(chunk))})", chunk):
            out.setdefault(r["item_id"], {})[r["source"]] = r["category"]
    return out


def _facts(row, cats: dict[str, str]) -> Facts:
    return Facts(row["name"], canvas_group=cats.get("canvas"), hac_category=cats.get("hac"),
                 online_quiz=bool(row["online_quiz"]) if "online_quiz" in row.keys() else False)


def facts_for(conn: sqlite3.Connection, item_id: int) -> Facts:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return _facts(row, _categories(conn, [item_id]).get(item_id, {}))


def classify(conn: sqlite3.Connection, student_id: int, rows: list) -> dict[int, Typed]:
    """Each row's family. One read each of categories, corrections and the student's rules."""
    cats = _categories(conn, [r["id"] for r in rows])
    corrections = {r["item_id"]: r["family"] for r in conn.execute(
        "SELECT t.item_id, t.family FROM item_types t JOIN items i ON i.id = t.item_id WHERE i.student_id = ?", (student_id,))}
    by_course: dict[int, list[Rule]] = {}
    for r in conn.execute("""SELECT t.*, c.peer_course_id FROM type_rules t JOIN courses c ON c.id = t.course_id
                             WHERE c.student_id = ?""", (student_id,)):
        for cid in (r["course_id"], r["peer_course_id"]):
            if cid:
                by_course.setdefault(cid, []).append(_rule(r))
    return {r["id"]: work_types.family_of(_facts(r, cats.get(r["id"], {})), by_course.get(r["course_id"], ()),
                                          corrections.get(r["id"])) for r in rows}


def set_correction(conn: sqlite3.Connection, item_id: int, family: str, now: str) -> None:
    if family not in work_types.FAMILIES:
        raise ValueError(f"unknown family {family!r}")
    conn.execute("INSERT OR REPLACE INTO item_types(item_id, family, set_at) VALUES (?, ?, ?)", (item_id, family, now))


def clear_correction(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM item_types WHERE item_id = ?", (item_id,))


def add_rule(conn: sqlite3.Connection, course_id: int, field: str, value: str, family: str, now: str) -> None:
    if field not in ("group", "name_prefix") or family not in work_types.FAMILIES or not work_types.fold(value):
        raise ValueError("a rule needs a field, a value and a family")
    conn.execute("""INSERT INTO type_rules(course_id, field, value, family, created_at) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(course_id, field, value) DO UPDATE SET family = excluded.family, created_at = excluded.created_at""",
                 (course_id, field, work_types.fold(value), family, now))


def remove_rule(conn: sqlite3.Connection, rule_id: int) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM type_rules WHERE id = ?", (rule_id,)).fetchone()
    if row is not None:
        conn.execute("DELETE FROM type_rules WHERE id = ?", (rule_id,))
    return row


def rule_reach(conn: sqlite3.Connection, student_id: int, course_id: int, field: str, value: str, now: datetime) -> int:
    """How many of the student's live items in this class (both courses of the pair) the rule
    would match: the "applies to N items" a grown-up sees before saving it. Live as the pages
    count it (`reconcile.live_items`): dropped work and last year's copies stay in `items` for
    the history, but no page lists them, so the count does not either."""
    ids = pair(conn, course_id)
    rows = [r for r in reconcile.live_items(conn, student_id, now) if r["course_id"] in ids]
    cats = _categories(conn, [r["id"] for r in rows])
    probe = Rule(0, field, work_types.fold(value), "practice", "")
    return sum(1 for r in rows if work_types.matches(probe, _facts(r, cats.get(r["id"], {}))))

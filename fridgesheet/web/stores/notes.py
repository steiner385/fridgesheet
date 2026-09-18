"""Notes: a parent's thought alongside an item, course or student."""
from __future__ import annotations

import sqlite3

TARGETS = ("item", "course", "student")


def add(conn: sqlite3.Connection, target_type: str, target_id: int, body: str, *, now: str) -> int:
    if target_type not in TARGETS:
        raise ValueError(f"unknown note target {target_type!r}")
    with conn:
        cur = conn.execute("INSERT INTO notes(target_type, target_id, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                           (target_type, target_id, body, now, now))
        return cur.lastrowid


def edit(conn: sqlite3.Connection, note_id: int, body: str, *, now: str) -> None:
    with conn:
        conn.execute("UPDATE notes SET body = ?, updated_at = ? WHERE id = ?", (body, now, note_id))


def delete(conn: sqlite3.Connection, note_id: int) -> None:
    with conn:
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))


def for_target(conn: sqlite3.Connection, target_type: str, target_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM notes WHERE target_type = ? AND target_id = ? ORDER BY created_at DESC, id DESC",
                        (target_type, target_id)).fetchall()


def get(conn: sqlite3.Connection, note_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()


def for_student(conn: sqlite3.Connection, student_id: int) -> list[sqlite3.Row]:
    """Every note that belongs to a student: on the student, on their courses, on their items."""
    return conn.execute(
        """SELECT n.*, CASE n.target_type
                 WHEN 'student' THEN s.name WHEN 'course' THEN c.short_name ELSE i.name END AS target_name
           FROM notes n
           LEFT JOIN students s ON n.target_type = 'student' AND s.id = n.target_id
           LEFT JOIN courses c ON n.target_type = 'course' AND c.id = n.target_id
           LEFT JOIN items i ON n.target_type = 'item' AND i.id = n.target_id
           WHERE COALESCE(s.id, c.student_id, i.student_id) = ?
           ORDER BY n.created_at DESC, n.id DESC""",
        (student_id,)).fetchall()

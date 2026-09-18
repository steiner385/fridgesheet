"""Saved view reports. The definition is opaque JSON here; `web/views.py` owns its meaning."""
from __future__ import annotations

import json
import sqlite3

#: Seeded on request into an empty table (spec section 7). Each is a valid `views.Definition`.
TEMPLATES: tuple[tuple[str, dict], ...] = (
    ("Open work", {"title": "Open work", "source": "items",
                   "columns": ["kid", "course", "name", "status", "due", "points"],
                   "filters": [{"field": "open", "op": "is", "value": "yes"}],
                   "group_by": "kid", "sort": [{"column": "due", "dir": "asc"}], "per_kid_sections": True}),
    # Named for what it shows: `views` reads the changes source a year back and nothing in the
    # builder can narrow a report by date yet, so "Weekly summary" promised a week it never kept.
    ("Recent changes", {"title": "Recent changes", "source": "changes",
                        "columns": ["at", "kid", "what", "item", "course", "detail"],
                        "sort": [{"column": "at", "dir": "desc"}]}),
    ("Grade trend", {"title": "Grade trend", "source": "grades",
                     "columns": ["kid", "course", "source", "value", "at"],
                     "group_by": "kid", "sort": [{"column": "at", "dir": "asc"}]}),
    ("Quarter recap", {"title": "Quarter recap", "source": "items",
                       "columns": ["kid", "course", "name", "status", "points", "flag"],
                       "group_by": "course", "sort": [{"column": "course", "dir": "asc"}, {"column": "name", "dir": "asc"}],
                       "orientation": "landscape"}),
)


def all(conn: sqlite3.Connection) -> list[sqlite3.Row]:   # noqa: A001  the store's vocabulary
    return conn.execute("SELECT * FROM reports ORDER BY name").fetchall()


def by_id(conn: sqlite3.Connection, report_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()


def create(conn: sqlite3.Connection, name: str, definition_json: str, *, now: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO reports(name, definition, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (name, definition_json, now, now))
        return cur.lastrowid


def update(conn: sqlite3.Connection, report_id: int, name: str, definition_json: str, *, now: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE reports SET name = ?, definition = ?, updated_at = ? WHERE id = ?",
                           (name, definition_json, now, report_id))
        return cur.rowcount > 0


def delete(conn: sqlite3.Connection, report_id: int) -> bool:
    with conn:
        cur = conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
        return cur.rowcount > 0


def seed_templates(conn: sqlite3.Connection, *, now: str) -> int:
    """Write the starter reports, but only into an empty table -- never over the parent's own."""
    if conn.execute("SELECT 1 FROM reports LIMIT 1").fetchone():
        return 0
    for name, definition in TEMPLATES:
        create(conn, name, json.dumps(definition), now=now)
    return len(TEMPLATES)

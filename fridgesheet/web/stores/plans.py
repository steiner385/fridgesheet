"""Family commitments are independent of school observations and handled flags.

A step is the family's own row: what they agreed, who owns it, when, and their account of what
happened. It points at an item when there is one, but the item's observations are never
written here, and a step outlives the item the school stops listing.
"""
from __future__ import annotations

import json
import sqlite3

STATES = {"planned": "Work to do", "waiting": "Waiting", "blocked": "Need help", "done": "Step complete"}
FIELDS = ("title", "family_account", "next_step", "owner", "planned_for", "minutes", "state", "position", "evidence", "recorded_by")


class Conflict(ValueError):
    pass


def for_student(conn, student_id):
    return [dict(r) for r in conn.execute(
        "SELECT * FROM plan_steps WHERE student_id = ? ORDER BY planned_for, position, id", (student_id,))]


def one(conn, student_id, step_id):
    row = conn.execute("SELECT * FROM plan_steps WHERE student_id = ? AND id = ?", (student_id, step_id)).fetchone()
    return dict(row) if row else None


def by_request_key(conn, student_id, request_key):
    """The step a form token already created, or None: how a retried POST finds its own step."""
    row = conn.execute("SELECT * FROM plan_steps WHERE student_id = ? AND request_key = ?", (student_id, request_key)).fetchone()
    return dict(row) if row else None


def save(conn, student_id, values, *, now, request_key, item_id=None, step_id=None, revision=0):
    if item_id is not None and not conn.execute(
            "SELECT 1 FROM items WHERE id = ? AND student_id = ?", (item_id, student_id)).fetchone():
        raise ValueError("That assignment does not belong to this child.")
    data = [values[k] for k in FIELDS]
    if step_id is not None:
        cur = conn.execute(
            f"UPDATE plan_steps SET {', '.join(k + ' = ?' for k in FIELDS)}, updated_at = ?, revision = revision + 1 "
            "WHERE student_id = ? AND id = ? AND revision = ?",
            (*data, now, student_id, step_id, revision))
        if not cur.rowcount:
            raise Conflict("This step changed in another window. Your changes have not been saved.")
        return step_id
    # A double-click or POST retry must not create two identical commitments.
    conn.execute(
        f"INSERT INTO plan_steps(student_id, item_id, {', '.join(FIELDS)}, created_by, request_key, created_at, updated_at) "
        f"VALUES ({', '.join('?' for _ in range(len(FIELDS) + 6))}) ON CONFLICT(request_key) DO NOTHING",
        (student_id, item_id, *data, values["recorded_by"], request_key, now, now))
    row = conn.execute("SELECT * FROM plan_steps WHERE request_key = ?", (request_key,)).fetchone()
    if row["student_id"] != student_id:
        raise ValueError("This form belongs to another child. Reload the page.")
    # `DO NOTHING` is right for a double-click or a POST retry, where the words are identical.
    # It is wrong for Back, edit, Save: the token is the same, the plan is not, and the insert
    # is silently dropped while the page answers "Saved." The family would read a commitment
    # that is not the one stored. Same token with different words is a conflict to show, not a
    # duplicate to swallow.
    if any(row[k] != values[k] for k in FIELDS):
        raise Conflict("This step was already saved from this form. Open it again to change it.")
    return row["id"]


def delete(conn, student_id, step_id) -> bool:
    """Remove a step the family added by mistake. Agreements already saved keep their snapshot."""
    return conn.execute("DELETE FROM plan_steps WHERE student_id = ? AND id = ?", (student_id, step_id)).rowcount > 0


def history(conn, student_id):
    result = []
    for row in conn.execute("SELECT * FROM checkins WHERE student_id = ? ORDER BY id DESC LIMIT 10", (student_id,)):
        result.append({**dict(row), "steps": json.loads(row["plan"])})
    return result


def finish(conn, student_id, *, now, next_check, available_minutes, summary, request_key, recorded_by=""):
    # Keep a snapshot of the agreement, so subsequent edits do not rewrite the conversation.
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        plan = [s for s in for_student(conn, student_id) if s["state"] != "done"]
        conn.execute(
            "INSERT INTO checkins(student_id, finished_at, next_check, available_minutes, summary, plan, recorded_by, request_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(request_key) DO NOTHING",
            (student_id, now, next_check, available_minutes, summary, json.dumps(plan), recorded_by, request_key))


def today_load(conn, student_id, today: str) -> tuple[int, int]:
    """(steps, minutes) the family planned for `today`: work to do and help-needed steps dated
    today. Waiting steps are on the teacher, and their date is when to look again."""
    row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(minutes), 0) AS m FROM plan_steps "
        "WHERE student_id = ? AND planned_for = ? AND state IN ('planned', 'blocked')", (student_id, today)).fetchone()
    return row["n"], row["m"]


def last_checkin(conn, student_id):
    row = conn.execute("SELECT * FROM checkins WHERE student_id = ? ORDER BY id DESC LIMIT 1", (student_id,)).fetchone()
    return dict(row) if row else None


def evidence(view):
    """Compare facts, not refresh IDs: unchanged missing flags are not new problems."""
    if view is None:
        return "{}"
    fields = ("state", "score", "grade", "submitted_at", "late", "missing", "excused", "published")
    return json.dumps({"due": view.due.isoformat() if view.due else None,
                       **{name: {k: obs[k] for k in fields} for name, obs in
                          (("canvas", view.canvas), ("hac", view.hac)) if obs is not None}}, sort_keys=True)

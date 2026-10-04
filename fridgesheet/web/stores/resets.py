"""Reset (2026-10-04): take a triage back. A reset deletes the open plan steps on the work it
covers and clears the family's answers there, so each row asks again as it did before anyone
answered; a copy of what it took is kept in `plan_resets`, and its one Undo puts that back
exactly -- the steps with their own ids and revisions, the answers with their own dates.
Completed steps and check-in agreements are the family's history and are never touched."""
from __future__ import annotations

import json
import sqlite3


def triaged(views) -> list:
    """What a whole-plan reset takes back: work the triage covers (overdue or coming due) that
    the family has answered or planned. Settled work and the family's own steps stay."""
    return [v for v in views if (v.overdue or v.upcoming) and (v.flag or v.step)]


def reset_items(conn: sqlite3.Connection, student_id: int, item_ids, *, now: str) -> int | None:
    """Take back the open steps and answers on these items of this kid's. The reset's id, or
    None when none of them had anything to take back (then nothing is recorded)."""
    ids = sorted(set(item_ids))
    if not ids:
        return None
    marks = ", ".join("?" for _ in ids)
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        steps = [dict(r) for r in conn.execute(
            f"SELECT * FROM plan_steps WHERE student_id = ? AND state != 'done' AND item_id IN ({marks}) ORDER BY id",
            (student_id, *ids))]
        answers = [dict(r) for r in conn.execute(
            f"""SELECT f.item_id, f.flag, f.set_at, f.text FROM flags f JOIN items i ON i.id = f.item_id
                WHERE i.student_id = ? AND f.cleared_at IS NULL AND f.item_id IN ({marks}) ORDER BY f.item_id""",
            (student_id, *ids))]
        if not steps and not answers:
            return None
        conn.executemany("DELETE FROM plan_steps WHERE id = ?", [(s["id"],) for s in steps])
        conn.executemany("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL",
                         [(now, a["item_id"]) for a in answers])
        return conn.execute("INSERT INTO plan_resets(student_id, made_at, taken) VALUES (?, ?, ?)",
                            (student_id, now, json.dumps({"steps": steps, "flags": answers}))).lastrowid


def one(conn: sqlite3.Connection, reset_id: int) -> dict | None:
    """A reset with what it took (`steps`, `flags`) and the items it covered (`item_ids`)."""
    row = conn.execute("SELECT * FROM plan_resets WHERE id = ?", (reset_id,)).fetchone()
    if row is None:
        return None
    taken = json.loads(row["taken"])
    item_ids = sorted({s["item_id"] for s in taken["steps"]} | {a["item_id"] for a in taken["flags"]})
    return {**dict(row), **taken, "item_ids": item_ids}


def undo(conn: sqlite3.Connection, student_id: int, reset_id: int, *, now: str) -> bool:
    """Put back what this kid's reset took, once. An item the family has answered or planned
    since keeps that: its newer answer is the one that stands, as the let-go bar's Undo does."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        claimed = conn.execute("UPDATE plan_resets SET undone_at = ? WHERE id = ? AND student_id = ? AND undone_at IS NULL",
                               (now, reset_id, student_id)).rowcount
        if not claimed:
            return False
        taken = json.loads(conn.execute("SELECT taken FROM plan_resets WHERE id = ?", (reset_id,)).fetchone()["taken"])
        moved_on = {r[0] for r in conn.execute("SELECT item_id FROM flags WHERE cleared_at IS NULL")}
        moved_on |= {r[0] for r in conn.execute("SELECT item_id FROM plan_steps WHERE state != 'done' AND item_id IS NOT NULL")}
        for s in taken["steps"]:
            if s["item_id"] in moved_on:
                continue
            cols = list(s)
            conn.execute(f"INSERT INTO plan_steps({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", [s[c] for c in cols])
        for a in taken["flags"]:
            if a["item_id"] in moved_on:
                continue
            conn.execute("INSERT INTO flags(item_id, flag, text, set_at) VALUES (?, ?, ?, ?)",
                         (a["item_id"], a["flag"], a["text"], a["set_at"]))
        return True

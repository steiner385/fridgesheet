"""The parent's verdict on an item, which the sources cannot know. One active flag per
item (a partial unique index enforces it); setting a new one clears the old."""
from __future__ import annotations

import sqlite3

from ...open_items import HANDLED_FLAGS as HANDLED, MARKED_FLAGS as MARKED

FLAGS = HANDLED + MARKED
#: Every flag with the words the detail card's menu shows, in the store's order; the menu is
#: drawn from this, so a flag added here appears there (#3).
CHOICES = (("done", "It's done"), ("excused", "Excused"), ("ignore", "Let it go"), ("too_late", "Too late to submit"),
           ("follow_up", "Follow up"), ("ask_teacher", "Ask the teacher"))


def active(conn: sqlite3.Connection, item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM flags WHERE item_id = ? AND cleared_at IS NULL", (item_id,)).fetchone()


def set_flag(conn: sqlite3.Connection, item_id: int, flag: str, *, now: str, text: str | None = None) -> int:
    """`text=None` is a one-tap answer, which carries no reason: the same flag again keeps the
    reason the family already gave, rather than erasing it (#123). The flag menu passes its
    text box, so an emptied box there still empties the reason."""
    if flag not in FLAGS:
        raise ValueError(f"unknown flag {flag!r}; one of {', '.join(FLAGS)}")
    with conn:
        conn.execute("BEGIN IMMEDIATE")   # clear-then-insert must not lose the write lock in between
        # The same flag again is an edit of its reason, not a new verdict: `set_at` is when the
        # parent decided ("asked the teacher on Sat"), and the stale-flag check measures from it.
        same = conn.execute("SELECT id FROM flags WHERE item_id = ? AND cleared_at IS NULL AND flag = ?",
                            (item_id, flag)).fetchone()
        if same is not None:
            if text is not None:
                conn.execute("UPDATE flags SET text = ? WHERE id = ?", (text, same["id"]))
            return same["id"]
        conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        cur = conn.execute("INSERT INTO flags(item_id, flag, text, set_at) VALUES (?, ?, ?, ?)", (item_id, flag, text or "", now))
        return cur.lastrowid


def confirm(conn: sqlite3.Connection, item_id: int, *, now: str) -> int | None:
    """Re-affirm the active flag as of `now`. Setting the same flag keeps its date (an edit of
    its reason); confirming is the family saying "still true, as of today" after the school
    contradicted it, so the stale check must measure from today."""
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("SELECT flag, text FROM flags WHERE item_id = ? AND cleared_at IS NULL", (item_id,)).fetchone()
        if cur is None:
            return None
        conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        return conn.execute("INSERT INTO flags(item_id, flag, text, set_at) VALUES (?, ?, ?, ?)",
                            (item_id, cur["flag"], cur["text"], now)).lastrowid


def restore(conn: sqlite3.Connection, item_id: int, flag: str, *, set_at: str, now: str) -> int:
    """Put back an earlier answer exactly as it was: the same flag, its original date and its
    reason. Undo uses this, so undoing an answer to a question the school raised brings the
    question back rather than a freshly dated answer the school has not contradicted yet."""
    if flag not in FLAGS:
        raise ValueError(f"unknown flag {flag!r}; one of {', '.join(FLAGS)}")
    with conn:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute("SELECT text FROM flags WHERE item_id = ? AND flag = ? AND set_at = ? ORDER BY id DESC LIMIT 1",
                             (item_id, flag, set_at)).fetchone()
        conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        return conn.execute("INSERT INTO flags(item_id, flag, text, set_at) VALUES (?, ?, ?, ?)",
                            (item_id, flag, prior["text"] if prior else "", set_at)).lastrowid


def clear(conn: sqlite3.Connection, item_id: int, *, now: str) -> bool:
    with conn:
        cur = conn.execute("UPDATE flags SET cleared_at = ? WHERE item_id = ? AND cleared_at IS NULL", (now, item_id))
        return cur.rowcount > 0


def history(conn: sqlite3.Connection, item_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM flags WHERE item_id = ? ORDER BY set_at DESC, id DESC", (item_id,)).fetchall()


def active_by_student(conn: sqlite3.Connection) -> dict[str, dict[tuple[str, str], str]]:
    """student key -> {(course name, item key) -> active flag}; what the runner hands to
    open_items, one dict per kid.

    Item keys are only unique within a student *and course*: two kids in like-named classes
    share `hac:<short course>:<norm name>`, siblings in one section share `canvas:<id>`, and
    one kid in two sections of a class ("Algebra I - 2" and "- 3") shares a HAC key between
    them. Keyed by less, one `done` struck the other kid's, or the other section's, work off
    the sheet (#97). The course is its full name as the gradebook gives it, which is what
    `open_items` has in hand.
    """
    out: dict[str, dict[tuple[str, str], str]] = {}
    for r in conn.execute(
            """SELECT s.key AS student, c.name AS course, i.key AS item, f.flag AS flag
               FROM flags f JOIN items i ON i.id = f.item_id JOIN students s ON s.id = i.student_id
               JOIN courses c ON c.id = i.course_id
               WHERE f.cleared_at IS NULL"""):
        out.setdefault(r["student"], {})[(r["course"], r["item"])] = r["flag"]
    return out

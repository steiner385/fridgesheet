"""The pace samples, read from the observation history (spec 4.1).

Ingest writes an observation only when a field changed, so the first row per (item, source)
that carries a score above zero is when the app first saw that grade. Its refresh's
`started_at` is `seen`; the anchor is the Canvas submission when there is one, else the
due date. One sample per item and source; an item the app met already graded is not one.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .. import pace as P


def _date(s: str):
    return datetime.fromisoformat(s).date()


def load(conn: sqlite3.Connection) -> P.Pace:
    """The whole household's pace: teacher pooling crosses kids."""
    classes: dict[int, int] = {}
    teachers: dict[int, str] = {}
    for c in conn.execute("SELECT c.id, c.peer_course_id, COALESCE(c.teacher, pc.teacher) AS teacher "
                          "FROM courses c LEFT JOIN courses pc ON pc.id = c.peer_course_id"):
        cid = min(c["id"], c["peer_course_id"]) if c["peer_course_id"] else c["id"]
        classes[c["id"]] = cid
        if P.teacher_key(c["teacher"]):
            teachers[cid] = P.teacher_key(c["teacher"])

    refresh_times = {r["id"]: r["started_at"] for r in conn.execute("SELECT id, started_at FROM refreshes")}
    first: dict[tuple[int, str], sqlite3.Row] = {}
    for o in conn.execute(
            """SELECT o.item_id, o.source, o.refresh_id, o.submitted_at,
                      i.first_seen, i.due, i.kind, i.course_id
               FROM item_observations o JOIN items i ON i.id = o.item_id
               WHERE o.score IS NOT NULL AND o.score > 0
               ORDER BY o.item_id, o.source, o.refresh_id, o.id"""):
        first.setdefault((o["item_id"], o["source"]), o)

    grade: dict[tuple[int, str], list[int]] = {}
    seen_at: dict[tuple[int, str], tuple] = {}
    for (iid, source), o in first.items():
        if o["refresh_id"] == o["first_seen"]:            # met already graded: says nothing about pace
            continue
        seen = _date(refresh_times[o["refresh_id"]])
        seen_at[(iid, source)] = (seen, o)
        anchor = _date(o["submitted_at"]) if source == "canvas" and o["submitted_at"] else (_date(o["due"]) if o["due"] else None)
        if anchor is None:
            continue
        key = (classes.get(o["course_id"], o["course_id"]), P.kind_group(o["kind"] or ""))
        grade.setdefault(key, []).append(max(0, (seen - anchor).days))

    hac: dict[tuple[int, str], list[int]] = {}
    for (iid, source), (seen, o) in seen_at.items():
        if source != "canvas" or (iid, "hac") not in seen_at:
            continue
        hac_seen, _ = seen_at[(iid, "hac")]
        key = (classes.get(o["course_id"], o["course_id"]), P.kind_group(o["kind"] or ""))
        hac.setdefault(key, []).append(max(0, (hac_seen - seen).days))
    return P.Pace(grade=grade, hac=hac, classes=classes, teachers=teachers)

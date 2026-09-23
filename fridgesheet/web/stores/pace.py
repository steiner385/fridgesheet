"""The pace samples, read from the observation history (spec 4.1).

Ingest writes an observation only when a field changed, so the first row per (item, source)
that carries a score above zero is when the app first saw that grade. Its refresh's
`started_at` is `seen`.

Grade lag is one sample per item: from the anchor (the Canvas hand-in when there is one,
else the due date) to the first refresh that showed a grade in either source. An item the
app met already graded, in either source, is not a sample: its HAC twin catching up a week
later says how HAC lags, not how long the teacher took. HAC lag is per item too: from the
refresh that first showed the Canvas grade to the one that first showed HAC's.
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
    # The hand-in Canvas recorded for each item, whichever refresh first carried it.
    handed_in = {r["item_id"]: r["submitted_at"] for r in conn.execute(
        "SELECT item_id, MIN(submitted_at) AS submitted_at FROM item_observations "
        "WHERE source = 'canvas' AND submitted_at IS NOT NULL GROUP BY item_id")}
    first_any: dict[int, sqlite3.Row] = {}                 # per item: earliest grade in any source
    first: dict[tuple[int, str], sqlite3.Row] = {}          # per item and source
    for o in conn.execute(
            """SELECT o.item_id, o.source, o.refresh_id,
                      i.first_seen, i.due, i.kind, i.course_id
               FROM item_observations o JOIN items i ON i.id = o.item_id
               WHERE o.score IS NOT NULL AND o.score > 0
               ORDER BY o.item_id, o.refresh_id, o.id"""):
        first_any.setdefault(o["item_id"], o)
        first.setdefault((o["item_id"], o["source"]), o)

    def key_of(o):
        return (classes.get(o["course_id"], o["course_id"]), P.kind_group(o["kind"] or ""))

    grade: dict[tuple[int, str], list[int]] = {}
    for iid, o in first_any.items():
        if o["refresh_id"] == o["first_seen"]:            # met already graded: says nothing about pace
            continue
        seen = _date(refresh_times[o["refresh_id"]])
        anchor = _date(handed_in[iid]) if iid in handed_in else (_date(o["due"]) if o["due"] else None)
        if anchor is None:
            continue
        grade.setdefault(key_of(o), []).append(max(0, (seen - anchor).days))

    hac: dict[tuple[int, str], list[int]] = {}
    for (iid, source), o in first.items():
        if source != "canvas" or o["refresh_id"] == o["first_seen"] or (iid, "hac") not in first:
            continue
        canvas_seen, hac_seen = _date(refresh_times[o["refresh_id"]]), _date(refresh_times[first[(iid, "hac")]["refresh_id"]])
        hac.setdefault(key_of(o), []).append(max(0, (hac_seen - canvas_seen).days))
    return P.Pace(grade=grade, hac=hac, classes=classes, teachers=teachers)

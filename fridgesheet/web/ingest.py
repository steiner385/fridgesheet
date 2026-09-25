# fridgesheet/web/ingest.py
"""Snapshot -> database rows. Called after every refresh (CLI runner, later the web worker).

One transaction per snapshot. Students, courses and items are upserted by stable keys;
an observation is appended only when the source's view of an item (or a course's grade)
differs from the last one recorded, so the observation tables are change logs.
A HAC row that names the same work as a Canvas assignment in the matched course becomes
that assignment's second source rather than its own item.

Real HAC data collides: one student's course can list the same normalised assignment name
twice with different due dates -- genuinely different assignments (Task 1's spike over live
data found this in a participation category). `matching.hac_item_key` gives the plain
`hac:<short course>:<norm name>` key (the same one the sheet uses, so a flag set in the app
finds the row it was set on); `record` detects, per HAC-only course, when two or more
rows share that base key within one snapshot and disambiguates every one of them (not just the
second, so the key never depends on row order) by appending the row's own due date. Two
colliding rows that also share a due date are the same row scraped twice, not two assignments:
the first is kept and the rest are skipped entirely -- no item, no observation, not counted.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .. import collector
from ..matching import hac_item_key, match_course, norm_name, same_item, short_course
from ..open_items import ASSESSMENT_WORDS, hac_excused, hac_only_keys as _hac_only_rows, kind_of, parse_hac_date
from . import db


@dataclass(frozen=True)
class IngestResult:
    refresh_id: int
    students: int
    courses: int
    items: int                       # items this snapshot created, not items it saw
    observations: int
    grades: int
    carried: tuple[str, ...] = ()    # Canvas classes served from an older pull, "Alex's Algebra I" (#140)
    missing: tuple[str, ...] = ()    # Canvas classes that failed with nothing older to serve

    def note(self) -> str:
        """What the log line and the run message add when a class did not answer, or ""."""
        parts = []
        if self.carried:
            parts.append(f"{n_classes(len(self.carried))} carried from an older pull: {', '.join(self.carried)}")
        if self.missing:
            parts.append(f"{n_classes(len(self.missing))} not fetched: {', '.join(self.missing)}")
        return "; ".join(parts)


def n_classes(n: int) -> str:
    return f"{n} class" if n == 1 else f"{n} classes"


def course_label(fault: dict) -> str:
    """"Alex's Algebra I" -- the kid and the class, short, the way the header names them."""
    name = fault.get("name")
    return f"{fault['kid']}'s {short_course(name) if name else 'course ' + str(fault['course_id'])}"


def item_key_canvas(assignment_id) -> str:
    return f"canvas:{assignment_id}"


def _upsert_student(conn, key: str, name: str) -> int:
    conn.execute("INSERT INTO students(key, name) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET name = excluded.name", (key, name))
    return conn.execute("SELECT id FROM students WHERE key = ?", (key,)).fetchone()[0]


def _upsert_course(conn, student_id: int, source: str, external_id, name: str, teacher: str | None,
                   teacher_email: str | None = None) -> int:
    conn.execute(
        """INSERT INTO courses(student_id, source, external_id, name, short_name, teacher, teacher_email)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(student_id, source, name) DO UPDATE SET external_id = excluded.external_id,
               teacher = COALESCE(excluded.teacher, courses.teacher),
               teacher_email = COALESCE(excluded.teacher_email, courses.teacher_email)""",
        (student_id, source, str(external_id) if external_id is not None else None, name, short_course(name),
         teacher, teacher_email),
    )
    return conn.execute("SELECT id FROM courses WHERE student_id = ? AND source = ? AND name = ?", (student_id, source, name)).fetchone()[0]


def _twin_by_date_and_points(row: dict, name: str, twins: list, attached: set[int], tz) -> int | None:
    """The Canvas twin of a HAC row whose *title* the word matcher could not pair.

    On a real gradebook three pairs slipped past `same_item`: "Concert Contract" / "Concert
    Contract Due", "Community Health" / "Ch. 1 - Community Health", "WK #1 HW" / "Week 1 Skill
    of the Week: Summary". Each was then a HAC-only item *and* a Canvas-only item, so the
    kid's record counted the work twice -- once as done (HAC had the grade) and once as
    unknown (Canvas had no submission). A teacher who enters the same assignment in both
    systems gives it the same due date and the same points, so when exactly one unclaimed
    Canvas item in the paired course matches on both, and the two titles agree on every
    number they contain (`Quiz 1` must still never pair with `Quiz 2`), that is the twin.
    Exactly one: two same-day ten-point worksheets with unrelated titles stay apart.
    """
    due = parse_hac_date(row.get("due"), tz)
    points = row.get("points")
    if due is None or points is None:
        return None
    digits = {w for w in norm_name(name).split() if w.isdigit()}

    def numbers_agree(other: str) -> bool:
        # Only two titles that *both* carry numbers have to agree on them. "Ch. 1 - Community
        # Health" against "Community Health" is one assignment; a title with no number imposes
        # no constraint. "Week 1" against "Week 2" stays two.
        theirs = {w for w in norm_name(other).split() if w.isdigit()}
        return not digits or not theirs or digits == theirs

    found = [iid for iid, n, d, p in twins
             if iid not in attached and d == due.date().isoformat() and p == points and numbers_agree(n)]
    return found[0] if len(found) == 1 else None


def _upsert_item(conn, student_id: int, course_id: int, key: str, name: str, kind: str, points, due: str | None,
                 assigned: str | None, is_assessment: bool, refresh_id: int,
                 present: frozenset[str] = frozenset(), *, unlock_at: str | None = None, lock_at: str | None = None) -> tuple[int, bool]:
    """Find or create one item; returns its id and whether this call created it.

    An item is identified by student, course and key together, never by key alone: two kids
    in like-named classes, and one kid in two sections of one course, share
    `hac:<short course>:<norm name>`, and siblings in one section share `canvas:<id>`.

    When the school renames a class mid-year it becomes a second `courses` row, so an item
    this student already carries under that key -- and that no row in this refresh has
    claimed yet -- moves to the new course rather than starting a second history. An item
    already seen in this refresh belongs to another row (the two-sections case above) and is
    never moved, so the outcome does not depend on the order rows arrive in.

    Nor is an item moved out of a class this refresh still lists (`present`, the student's
    course names in this snapshot): that is not a rename but a new section beside the old one,
    and taking the old section's item handed its flags, notes and history to the new section
    while the old one started again from nothing (#97). A renamed class is gone under its old
    name, so its items still move.
    """
    # Canvas assignment titles arrive with a teacher's stray trailing space ("Chapter 1.3
    # Reading Guide ") and that space was stored and rendered everywhere the name shows (#40
    # item 19). The key is derived before this point and is untouched, so identity is stable.
    name = name.strip()
    row = conn.execute("SELECT id FROM items WHERE student_id = ? AND course_id = ? AND key = ?",
                       (student_id, course_id, key)).fetchone()
    if row is None:
        row = next((r for r in conn.execute(
            """SELECT i.id, c.name AS course FROM items i JOIN courses c ON c.id = i.course_id
               WHERE i.student_id = ? AND i.key = ? AND i.last_seen < ? ORDER BY i.last_seen DESC, i.id DESC""",
            (student_id, key, refresh_id)) if r["course"] not in present), None)
    if row:
        conn.execute("UPDATE items SET course_id = ?, name = ?, kind = ?, points = ?, due = ?, assigned = COALESCE(?, assigned), is_assessment = ?, "
                     "unlock_at = ?, lock_at = ?, last_seen = ? WHERE id = ?",
                     (course_id, name, kind, points, due, assigned, int(is_assessment), unlock_at, lock_at, refresh_id, row[0]))
        return row[0], False
    cur = conn.execute(
        "INSERT INTO items(student_id, course_id, key, name, kind, points, due, assigned, is_assessment, unlock_at, lock_at, first_seen, last_seen) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (student_id, course_id, key, name, kind, points, due, assigned, int(is_assessment), unlock_at, lock_at, refresh_id, refresh_id))
    return cur.lastrowid, True


_OBS_FIELDS = ("state", "score", "grade", "submitted_at", "late", "missing", "excused", "published", "locked", "lock_reason")


def _observe(conn, refresh_id: int, item_id: int, source: str, values: dict) -> bool:
    """Append an observation if it differs from the last one for (item, source). Returns True when written."""
    last = conn.execute("SELECT * FROM item_observations WHERE item_id = ? AND source = ? ORDER BY refresh_id DESC, id DESC LIMIT 1",
                        (item_id, source)).fetchone()
    if last is not None and all(last[f] == values.get(f) for f in _OBS_FIELDS):
        return False
    # A rewrite for one field (the lock flipping) is not the teacher marking it missing again,
    # so the refresh in which the mark and the score first appeared travel with the row (#131).
    missing_since, scored_since = db.since_fields(last, refresh_id, values.get("missing"), values.get("score"))
    conn.execute(
        "INSERT INTO item_observations(refresh_id, item_id, source, state, score, grade, submitted_at, late, missing, excused, published, locked, lock_reason, "
        "missing_since, scored_since) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (refresh_id, item_id, source, *(values.get(f) for f in _OBS_FIELDS), missing_since, scored_since))
    return True


def _observe_grade(conn, refresh_id: int, course_id: int, average, letter, current, final, last_updated) -> bool:
    last = conn.execute("SELECT * FROM grade_observations WHERE course_id = ? ORDER BY refresh_id DESC, id DESC LIMIT 1", (course_id,)).fetchone()
    new = (average, letter, current, final, last_updated)
    if last is not None and (last["average"], last["letter"], last["current"], last["final"], last["last_updated"]) == new:
        return False
    conn.execute("INSERT INTO grade_observations(refresh_id, course_id, average, letter, current, final, last_updated) VALUES (?,?,?,?,?,?,?)",
                 (refresh_id, course_id, *new))
    return True


def _flag(v) -> int | None:
    return None if v is None else int(bool(v))


def _canvas_values(a: dict) -> dict:
    # An unpublished assignment is not work the kid can do; `published` is carried so the
    # database can say so too (open_items already drops it from the sheet). A snapshot taken
    # before the field existed says nothing, which means published.
    published = a.get("published")
    return {"state": a.get("state"), "score": a.get("score"), "grade": a.get("grade"), "submitted_at": a.get("submitted_at"),
            "late": _flag(a.get("late")), "missing": _flag(a.get("missing")), "excused": _flag(a.get("excused")),
            "published": 1 if published is None else _flag(published),
            "locked": _flag(a.get("locked")), "lock_reason": a.get("lock_reason") if a.get("locked") else None}


def _hac_values(row: dict) -> dict:
    graded = row.get("score") is not None
    # HAC's "EXC" in the score column is the teacher excusing the work; the scraper reads it as
    # no score, so the mark is kept here (#135). None rather than 0 when it is absent: an
    # observation stored before this field was read says None, and a changed value would
    # rewrite every HAC row on the first refresh after the upgrade.
    return {"state": "graded" if graded else "ungraded", "score": row.get("score"), "grade": (row.get("percent") or None) if graded else None,
            "submitted_at": None, "late": None, "missing": None, "excused": 1 if hac_excused(row) else None, "published": None,
            "locked": None, "lock_reason": None}


def record(conn: sqlite3.Connection, snapshot: dict, *, tz, now: datetime | None = None) -> IngestResult:
    now = now or datetime.now(tz)
    sources = snapshot.get("sources") or {}
    carried, missing = collector.course_faults(snapshot)
    n_students = n_courses = n_items = n_obs = n_grades = 0
    with conn:
        # IMMEDIATE takes the write lock up front: a deferred transaction that reads first and
        # writes later can only fail with SQLITE_BUSY when the web worker got there in between,
        # and a whole snapshot is too much work to throw away.
        conn.execute("BEGIN IMMEDIATE")
        # `ok` reads the sources alone: a refresh in which one Canvas class was carried from an
        # older pull is still a good refresh for the 24-hour rule (#140) -- the household's
        # data is complete, one class of it is just older, and the header says which. The
        # carried class's record is in the snapshot, so its items are seen in this refresh below.
        cur = conn.execute("INSERT INTO refreshes(started_at, finished_at, sources, ok, carried) VALUES (?, ?, ?, ?, ?)",
                           (snapshot.get("fetched_at") or now.isoformat(), now.isoformat(), json.dumps(sources),
                            int(all(v == "ok" for v in sources.values())),
                            json.dumps({"carried": carried, "missing": missing}) if carried or missing else None))
        refresh_id = cur.lastrowid
        for key, entry in (snapshot.get("students") or {}).items():
            student_id = _upsert_student(conn, key, entry.get("name") or key)
            n_students += 1
            canvas_courses = (entry.get("canvas") or {}).get("courses") or []
            hac_classes = (entry.get("hac") or {}).get("classes") or []
            # Every class this refresh lists for the student, both sources: an item is only
            # carried over from a class that is gone (a rename), never one still here (#97).
            present = frozenset([c["name"] for c in canvas_courses] + [h["name"] for h in hac_classes])

            # Canvas courses, grades and assignments
            canvas_course_ids: dict[str, int] = {}
            canvas_items_by_course: dict[int, list[tuple[int, str]]] = {}
            for c in canvas_courses:
                # One staff entry answers both questions: the teacher of record if the roles
                # name one, else whoever is listed first. Taking the name from one entry and
                # the address from another put a TA's mailto: under the teacher's name.
                staff = c.get("staff") or []
                who = next((s for s in staff if "TeacherEnrollment" in (s.get("roles") or [])), None) or (staff[0] if staff else {})
                teacher, teacher_email = who.get("name"), who.get("email")
                cid = _upsert_course(conn, student_id, "canvas", c.get("id"), c["name"], teacher, teacher_email)
                canvas_course_ids[c["name"]] = cid
                n_courses += 1
                g = c.get("grade") or {}
                n_grades += _observe_grade(conn, refresh_id, cid, None, g.get("current_grade"), g.get("current_score"), g.get("final_score"), None)
                for a in c.get("assignments") or []:
                    if a.get("id") is None:
                        continue
                    assigned = a.get("unlock_at") or a.get("created_at")
                    item_id, created = _upsert_item(conn, student_id, cid, item_key_canvas(a["id"]), a.get("name") or "", kind_of(a.get("submission_types")),
                                                    a.get("points_possible"), a.get("due_at"), assigned,
                                                    bool(a.get("group") and any(w in a["group"].lower() for w in ASSESSMENT_WORDS)), refresh_id,
                                                    present, unlock_at=a.get("unlock_at"), lock_at=a.get("lock_at"))
                    n_items += created
                    n_obs += _observe(conn, refresh_id, item_id, "canvas", _canvas_values(a))
                    canvas_items_by_course.setdefault(cid, []).append(
                        (item_id, a.get("name") or "", (a.get("due_at") or "")[:10], a.get("points_possible")))

            # HAC classes: pair with a Canvas course, attach rows to Canvas twins, else HAC-only items
            for h in hac_classes:
                hid = _upsert_course(conn, student_id, "hac", h.get("code"), h["name"], None)
                n_courses += 1
                peer_cid = match_course(h["name"], canvas_course_ids) if canvas_course_ids else None
                if peer_cid is not None:
                    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (peer_cid, hid))
                    conn.execute("UPDATE courses SET peer_course_id = ? WHERE id = ?", (hid, peer_cid))
                n_grades += _observe_grade(conn, refresh_id, hid, h.get("marking_period_avg"), None, None, None, h.get("last_updated"))
                twins = canvas_items_by_course.get(peer_cid, []) if peer_cid is not None else []
                attached_twins: set[int] = set()
                unmatched = []
                for row in h.get("assignments") or []:
                    name = row.get("name") or ""
                    twin = next((iid for iid, n, _d, _p in twins if same_item(name, n)), None)
                    if twin is None:
                        twin = _twin_by_date_and_points(row, name, twins, attached_twins, tz)
                    if twin is not None and twin not in attached_twins:
                        # Attach the first row that names the same work as a Canvas twin. A
                        # Canvas item takes at most one HAC observation per refresh (mirroring
                        # open_items, which does the same with `next(...)`), so a later row
                        # matching an already-attached twin is dropped, not made a HAC-only item
                        # -- otherwise two same-named HAC rows both matching one Canvas
                        # assignment would collide on item_observations' (refresh_id, item_id,
                        # source) uniqueness and roll back the whole snapshot.
                        attached_twins.add(twin)
                        n_obs += _observe(conn, refresh_id, twin, "hac", _hac_values(row))
                    elif twin is None:
                        unmatched.append(row)
                # The rest become HAC-only items, keyed per the collision rule above.
                for row, item_key in _hac_only_rows(unmatched, h["name"], tz):
                    name = row.get("name") or ""
                    due = parse_hac_date(row.get("due"), tz)
                    assigned = parse_hac_date(row.get("assigned"), tz)
                    item_id, created = _upsert_item(conn, student_id, hid, item_key, name, "", row.get("points"),
                                                    due.replace(hour=23, minute=59).isoformat() if due else None,
                                                    assigned.isoformat() if assigned else None,
                                                    any(w in (row.get("category") or "").lower() for w in ("quiz", "assess")), refresh_id,
                                                    present)
                    n_items += created
                    n_obs += _observe(conn, refresh_id, item_id, "hac", _hac_values(row))
    return IngestResult(refresh_id, n_students, n_courses, n_items, n_obs, n_grades,
                        tuple(course_label(c) for c in carried), tuple(course_label(m) for m in missing))

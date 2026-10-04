"""Levers from the database (spec 2026-10-04 §6): rows from `items.open_work` (the one
definition of what is still to do), the class's account from `grades.account_for`, and the
report card's second sentence. The arithmetic is `fridgesheet.guidance`."""
from __future__ import annotations

import sqlite3

from ... import dates, grading, guidance
from . import grades, students


def _hac_categories(conn: sqlite3.Connection, item_ids: list[int]) -> dict[int, str]:
    if not item_ids:
        return {}
    marks = ",".join("?" * len(item_ids))
    return {r["item_id"]: r["category"] for r in conn.execute(
        f"SELECT item_id, category FROM item_categories WHERE source = 'hac' AND item_id IN ({marks})", item_ids)}


def _row(v, cats: dict[int, str], counted_only: bool) -> dict:
    hac_score = v.hac["score"] if v.hac is not None else None
    canvas_score = v.canvas["score"] if v.canvas is not None else None
    # An explicit zero (HAC's, or Canvas's where HAC has no row) is already inside `possible`.
    zero = hac_score == 0 or (v.hac is None and canvas_score == 0)
    return {"item_id": v.id, "name": v.name, "category": cats.get(v.id, ""), "points": v.points, "due": v.due,
            "late_until": v.late_until, "credit_text": v.credit, "overdue": v.overdue, "upcoming": v.upcoming,
            "hac_blank": v.hac is not None and hac_score is None,
            "hac_scored": hac_score is not None, "hac_zero": zero, "counted_only": counted_only}


def rows_for(conn: sqlite3.Connection, work, course_ids: set[int]) -> list[dict]:
    """The class's open rows as the engine wants them, each item once; then the class's blank
    past-due rows that are no longer open (past their window, or answered) as `counted_only`,
    so the zero budget they used in HAC is not handed to a newer row (final review, 2026-10-04)."""
    seen: set[int] = set()
    live, gone = [], []
    for v in list(work.fixable) + list(work.upcoming):
        if v.course_id in course_ids and v.id not in seen:
            seen.add(v.id)
            live.append(v)
    for v in list(work.past_window) + list(work.handled):
        if v.course_id in course_ids and v.id not in seen and v.overdue:
            seen.add(v.id)
            gone.append(v)
    cats = _hac_categories(conn, [v.id for v in live + gone])
    return [_row(v, cats, False) for v in live] + [_row(v, cats, True) for v in gone]


def _class_ids(course: sqlite3.Row) -> set[int]:
    ids = {course["id"]}
    if course["peer_course_id"]:
        ids.add(course["peer_course_id"])
    return ids


def for_class(conn: sqlite3.Connection, course: sqlite3.Row, account: grading.Account, work, scale: grading.GradeScale) -> guidance.Guidance:
    return guidance.guide(account, rows_for(conn, work, _class_ids(course)), scale)


def by_item(conn: sqlite3.Connection, student: sqlite3.Row, work, prefs, scale: grading.GradeScale) -> dict[int, guidance.Lever]:
    """item id -> its lever, for the Plan's badges: one guide per class a kid has open work in,
    on the family's official source for that class."""
    out: dict[int, guidance.Lever] = {}
    latest = students.latest_grades(conn, student["id"])
    done: set[int] = set()
    for v in list(work.fixable) + list(work.upcoming):
        if v.course_id in done:
            continue
        course = students.course(conn, v.course_id)
        if course is None:
            continue
        peer = students.course(conn, course["peer_course_id"]) if course["peer_course_id"] else None
        ids = _class_ids(course)
        done |= ids
        pick = prefs.resolve(student["key"], course["name"], peer["name"] if peer else None).grades
        official = course if course["source"] == pick else (peer if peer is not None and peer["source"] == pick else course)
        account = grades.account_for(conn, official, latest.get(official["id"]))
        g = guidance.guide(account, rows_for(conn, work, ids), scale)
        for lever in g.levers:
            if lever.item_id is not None:
                out[lever.item_id] = lever
    return out


def lever_note(lever: guidance.Lever, tier: str) -> tuple[str, dict]:
    """The lever's one-line note under its item line (spec 2026-10-04 §5). `credit_note` is
    said here, in the kid's tier, so the outer phrase's values are plain strings."""
    from ..verdicts import words
    credit_note = ""
    if lever.kind != "upcoming":
        if lever.credit_known and lever.credit < 1.0:
            credit_note = words("copy.gd_credit_at", tier, {"credit": f"{round(lever.credit * 100)}%"})
        elif not lever.credit_known:
            credit_note = words("copy.gd_credit_unknown", tier)
        if lever.cost is not None and lever.cost >= 0.05:
            credit_note += words("copy.gd_cost", tier, {"cost": guidance.fmt_worth(lever.cost)})
    if lever.kind == "upcoming":
        return "gd.lever_upcoming", {"due": dates.wd_md(lever.deadline) if lever.deadline else ""}
    if lever.deadline is None:
        return "gd.lever_missing_undated", {"credit_note": credit_note}
    key = "gd.lever_zero" if lever.kind == "zero" else "gd.lever_missing"
    return key, {"until": dates.md(lever.deadline), "credit_note": credit_note}


def sentence_for(g: guidance.Guidance) -> list[tuple[str, dict]]:
    """The report card line's second sentence(s), in the spec's order; [] when not sound."""
    if not g.sound:
        return []
    out: list[tuple[str, dict]] = []
    art = guidance.with_article
    if g.reach is not None and g.reach.needed <= 0 and g.zero_points > 0:
        return [("gd.zeros_reach", {"zero_points": grading.fmt_points(g.zero_points), "letter": art(g.reach.letter)})]
    best = g.best if g.best is not None and g.best.stake >= 0.05 else None   # "+0.0" is no best move
    if best is not None:
        common = {"name": best.name, "points": grading.fmt_points(best.points), "worth": guidance.fmt_worth(best.worth)}
        if best.cost is not None and best.cost >= 0.05 and (best.worth or 0.0) < 0.05:
            # It cannot raise the number, only keep a zero off it: say that, not "+0.0".
            out.append(("gd.protect", {"name": best.name, "points": common["points"], "cost": guidance.fmt_worth(best.cost)}))
        elif best.cost is not None and best.cost >= 0.05:
            out.append(("gd.best_missing", {**common, "cost": guidance.fmt_worth(best.cost)}))
        else:
            out.append(("gd.best", common))
    # Then the honest reach, or at the top letter the slack: every sentence the engine can stand behind.
    if g.reach is not None and g.reach.posted > 0:
        key = "gd.reach" if g.reach.reachable else "gd.reach_far"
        out.append((key, {"letter": art(g.reach.letter), "needed": grading.fmt_points(g.reach.needed), "posted": grading.fmt_points(g.reach.posted)}))
    if g.slack is not None and g.slack.posted > 0:
        if g.slack.can_miss < 0:          # the current letter is at risk: always worth saying
            out.append(("gd.hold", {"letter": art(g.slack.letter), "need": grading.fmt_points(-g.slack.can_miss), "posted": grading.fmt_points(g.slack.posted)}))
        elif g.reach is None:             # at the top letter, the slack is the line
            out.append(("gd.keep", {"letter": art(g.slack.letter), "can_miss": grading.fmt_points(g.slack.can_miss), "posted": grading.fmt_points(g.slack.posted)}))
    if not out:
        out.append(("gd.nothing_posted", {}))
    return out

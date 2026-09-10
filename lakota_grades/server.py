"""MCP server. Run with `lakota-grades serve` (stdio transport).

Tools return plain JSON. The agent never sees credentials: logins happen inside this process.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from mcp.server.fastmcp import FastMCP

from . import collector
from .config import load_settings

log = logging.getLogger("lakota.server")

mcp = FastMCP("lakota-grades")
_settings = load_settings()


def _snap(refresh: bool = False) -> dict:
    snap = collector.load_snapshot(_settings)
    if refresh or not collector.snapshot_is_fresh(_settings, snap):
        snap = collector.collect(_settings)
    return snap


def _kid(snap: dict, student: str) -> dict:
    for name, entry in snap["students"].items():
        if name.lower() == student.lower() or entry["name"].lower().startswith(student.lower()):
            return entry
    raise ValueError(f"Unknown student '{student}'. Known: {', '.join(snap['students'])}")


@mcp.tool()
def refresh(kids: list[str] | None = None, hac: bool = True, canvas: bool = True) -> dict:
    """Re-pull Canvas and/or HAC now (logs in if a session expired) and return the source status.
    Use before building a report so numbers are current. Takes ~1-3 minutes."""
    snap = collector.collect(_settings, include_hac=hac, include_canvas=canvas, kids_filter=kids)
    return {"fetched_at": snap["fetched_at"], "sources": snap["sources"], "students": list(snap["students"])}


@mcp.tool()
def status() -> dict:
    """Snapshot age and whether each source (Canvas, HAC) was reachable on the last pull."""
    snap = collector.load_snapshot(_settings)
    if not snap:
        return {"snapshot": None, "fresh": False}
    return {"fetched_at": snap["fetched_at"], "fresh": collector.snapshot_is_fresh(_settings, snap), "sources": snap["sources"], "students": list(snap["students"])}


@mcp.tool()
def list_students() -> list[dict]:
    """The kids visible to this parent account, with Canvas IDs and which sources have data."""
    snap = _snap()
    return [{"student": k, "name": v["name"], "canvas_id": v.get("canvas_id"), "has_canvas": bool(v.get("canvas")), "has_hac": bool(v.get("hac"))} for k, v in snap["students"].items()]


@mcp.tool()
def grades(student: str) -> dict:
    """Official HAC marking-period averages side by side with Canvas current/final scores, per class.
    HAC is the gradebook of record; Canvas can be hidden or partial."""
    e = _kid(_snap(), student)
    out = {"student": e["name"], "classes": []}
    hac_classes = {c["name"]: c for c in (e.get("hac") or {}).get("classes", [])}
    hac_week = {w["class"]: w for w in (e.get("hac") or {}).get("week_view", [])}
    seen = set()
    for c in ((e.get("canvas") or {}).get("courses") or []):
        base = c["name"].split(" S1")[0].split("-20")[0].strip()
        h = _match(base, hac_classes) or {}
        w = _match(base, hac_week) or {}
        seen.add(h.get("name"))
        out["classes"].append({
            "course": c["name"],
            "hac_official": h.get("marking_period_avg", w.get("current_average")),
            "hac_last_updated": h.get("last_updated"),
            "hac_categories": h.get("categories"),
            "canvas_current": c["grade"]["current_score"],
            "canvas_final_if_unsubmitted_zero": c["grade"]["final_score"],
            "canvas_hidden": c["grade"]["hidden"],
            "staff": c.get("staff"),
        })
    for name, h in hac_classes.items():  # HAC-only classes (e.g. Hawk Time)
        if name not in seen:
            out["classes"].append({"course": name, "hac_official": h.get("marking_period_avg"), "hac_last_updated": h.get("last_updated"), "hac_categories": h.get("categories"), "canvas_current": None, "canvas_final_if_unsubmitted_zero": None, "canvas_hidden": None})
    return out


@mcp.tool()
def assignments(student: str, course: str | None = None, include_graded: bool = True) -> dict:
    """Every Canvas assignment for a student (optionally one course, matched by substring) with due date
    (America/New_York ISO), points, score, and late/missing/excused flags."""
    e = _kid(_snap(), student)
    courses = ((e.get("canvas") or {}).get("courses") or [])
    if course:
        courses = [c for c in courses if course.lower() in c["name"].lower()]
    out = []
    for c in courses:
        for a in c["assignments"]:
            if not include_graded and a["state"] == "graded" and not (a["missing"] or a["late"] or a["score"] == 0):
                continue
            out.append({"course": c["name"], **a})
    return {"student": e["name"], "count": len(out), "assignments": out}


@mcp.tool()
def missing_work(student: str) -> dict:
    """Canvas items that are missing, late, scored 0, or past due and unsubmitted, plus HAC rows with a blank
    score whose due date has passed. Sorted with assessments first, then by points."""
    e = _kid(_snap(), student)
    now = datetime.now(ZoneInfo(_settings.timezone))
    rows = []
    for c in ((e.get("canvas") or {}).get("courses") or []):
        for a in c["assignments"]:
            due = datetime.fromisoformat(a["due_at"]) if a["due_at"] else None
            past = bool(due and due < now)
            flag = None
            if a["excused"]:
                continue
            if a["missing"]:
                flag = "missing"
            elif a["late"]:
                flag = "late"
            elif a["score"] == 0 and a["state"] == "graded":
                flag = "scored_zero"
            elif past and a["state"] in ("unsubmitted", None) and a["score"] is None and a["published"]:
                flag = "past_due_unsubmitted"
            if flag:
                is_assessment = bool(a["group"] and any(k in a["group"].lower() for k in ("quiz", "test", "assess", "exam")))
                rows.append({"source": "canvas", "course": c["name"], "assignment": a["name"], "due": a["due_at"], "points": a["points_possible"], "score": a["score"], "flag": flag, "is_assessment": is_assessment, "submission_types": a["submission_types"]})
    already = {r["assignment"].strip().lower() for r in rows}
    for h in ((e.get("hac") or {}).get("classes") or []):
        for a in h["assignments"]:
            if a["name"].strip().lower() in already:
                continue  # same item already reported from Canvas
            try:
                due = datetime.strptime(a["due"], "%m/%d/%Y").replace(tzinfo=ZoneInfo(_settings.timezone))
            except ValueError:
                continue
            if a["score"] is None and a["score_raw"] == "" and due < now - timedelta(days=1):
                rows.append({"source": "hac", "course": h["name"], "assignment": a["name"], "due": due.date().isoformat(), "points": a["points"], "score": None, "flag": "no_grade_in_hac", "is_assessment": "quiz" in (a["category"] or "").lower() or "assess" in (a["category"] or "").lower(), "category": a["category"]})
    rows.sort(key=lambda r: (not r["is_assessment"], -(r["points"] or 0)))
    return {"student": e["name"], "as_of": now.isoformat(), "count": len(rows), "points_at_stake": sum((r["points"] or 0) for r in rows), "items": rows}


@mcp.tool()
def upcoming(student: str, days: int = 7) -> dict:
    """Canvas assignments due from now through the next N days, Eastern time, not yet submitted."""
    e = _kid(_snap(), student)
    now = datetime.now(ZoneInfo(_settings.timezone))
    end = now + timedelta(days=days)
    rows = []
    for c in ((e.get("canvas") or {}).get("courses") or []):
        for a in c["assignments"]:
            if not a["due_at"]:
                continue
            due = datetime.fromisoformat(a["due_at"])
            if now - timedelta(hours=12) <= due <= end and a["state"] in ("unsubmitted", None) and a["score"] is None:
                rows.append({"course": c["name"], "assignment": a["name"], "due": a["due_at"], "weekday": due.strftime("%a"), "points": a["points_possible"], "submission_types": a["submission_types"]})
    rows.sort(key=lambda r: r["due"])
    return {"student": e["name"], "window_days": days, "items": rows}


@mcp.tool()
def hac_classwork(student: str, course: str | None = None) -> dict:
    """Raw HAC classwork rows (score, points, category) and category subtotals — the official gradebook detail."""
    e = _kid(_snap(), student)
    classes = (e.get("hac") or {}).get("classes") or []
    if course:
        classes = [c for c in classes if course.lower() in c["name"].lower()]
    return {"student": e["name"], "classes": classes}


def _match(base: str, table: dict):
    b = base.lower()
    for k, v in table.items():
        kl = k.lower()
        if b in kl or kl in b or b.split()[0] in kl and b.split()[-1] in kl:
            return v
    return None


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mcp.run(transport="stdio")

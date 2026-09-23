"""MCP server. Run with `fridgesheet serve` (stdio transport).

Tools return plain JSON. The agent never sees credentials: logins happen inside this process.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

try:  # mcp >= 2.0 renamed FastMCP to MCPServer; the tool/run API is otherwise identical
    from mcp.server.mcpserver import MCPServer as _McpServer
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _McpServer

from . import collector, late_rules, open_items
from .config import load_settings
from .matching import match_course as _match
from .sources import pick_value

log = logging.getLogger("fridgesheet.server")

mcp = _McpServer("fridgesheet")
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
    Use before building a report so numbers are current. Takes ~1-3 minutes. A source that
    fails keeps its data from the last good pull; `stale` says which and how old."""
    snap = collector.collect(_settings, include_hac=hac, include_canvas=canvas, kids_filter=kids)
    return collector.summary(_settings, snap)


@mcp.tool()
def status() -> dict:
    """Snapshot age, whether each source (Canvas, HAC) was reachable on the last pull, and
    which sources are being served from an older pull (`stale`, with that pull's time)."""
    return collector.summary(_settings, collector.load_snapshot(_settings))


@mcp.tool()
def list_students() -> list[dict]:
    """The kids visible to this parent account, with Canvas IDs and which sources have data."""
    snap = _snap()
    return [{"student": k, "name": v["name"], "canvas_id": v.get("canvas_id"), "has_canvas": bool(v.get("canvas")), "has_hac": bool(v.get("hac"))} for k, v in snap["students"].items()]


@mcp.tool()
def grades(student: str) -> dict:
    """Class averages per class: HAC's marking-period average and Canvas's current/final score
    side by side, plus `official` -- the one the family has chosen as authoritative for this kid
    and class ([sources] in config.toml; HAC unless changed), falling back to the other source
    when that one has no average. Canvas can be hidden or partial."""
    e = _kid(_snap(), student)
    first = (e["name"].split() or [student])[0]
    out = {"student": e["name"], "classes": []}
    hac_classes = {c["name"]: c for c in (e.get("hac") or {}).get("classes", [])}
    hac_week = {w["class"]: w for w in (e.get("hac") or {}).get("week_view", [])}
    seen = set()
    for c in ((e.get("canvas") or {}).get("courses") or []):
        h = _match(c["name"], hac_classes) or {}
        w = _match(c["name"], hac_week) or {}
        seen.add(h.get("name"))
        hac_official = h.get("marking_period_avg", w.get("current_average"))
        pick = _settings.sources.resolve(first, c["name"]).grades
        official, official_source = pick_value(pick, c["grade"]["current_score"], hac_official)
        out["classes"].append({
            "course": c["name"],
            "official": official, "official_source": official_source,
            "hac_official": hac_official,
            "hac_last_updated": h.get("last_updated"),
            "hac_categories": h.get("categories"),
            "canvas_current": c["grade"]["current_score"],
            "canvas_final_if_unsubmitted_zero": c["grade"]["final_score"],
            "canvas_hidden": c["grade"]["hidden"],
            "staff": c.get("staff"),
        })
    for name, h in hac_classes.items():  # HAC-only classes (e.g. Hawk Time)
        if name not in seen:
            pick = _settings.sources.resolve(first, name).grades
            official, official_source = pick_value(pick, None, h.get("marking_period_avg"))
            out["classes"].append({"course": name, "official": official, "official_source": official_source, "hac_official": h.get("marking_period_avg"), "hac_last_updated": h.get("last_updated"), "hac_categories": h.get("categories"), "canvas_current": None, "canvas_final_if_unsubmitted_zero": None, "canvas_hidden": None})
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


def _open_work(student: str, days_ahead: int, include_hac: bool = True):
    e = _kid(_snap(), student)
    now = datetime.now(ZoneInfo(_settings.timezone))
    rules = late_rules.load(_settings.home / "late-rules.toml")
    return e, open_items.open_items(e, e["name"].split()[0], now, days_ahead=days_ahead, rules=rules, include_hac=include_hac, prefs=_settings.sources)


@mcp.tool()
def missing_work(student: str) -> dict:
    """Overdue work the student can still act on: Canvas items missing, scored 0, turned in
    late but ungraded, or past due and unsubmitted (on-paper ones as PAPER — CHECK), plus HAC
    rows with a blank score after the due date, deduped. Each row carries `late_until` and
    `credit` from ~/.fridgesheet/late-rules.toml; items past that deadline or more than two
    weeks overdue are only counted under `not_shown`. The same rules as the printed sheet,
    except that flags set in the app (done, excused, ignore) are not applied here, so an item
    the sheet drops as handled still appears. Sorted with assessments first, then by points."""
    e, work = _open_work(student, days_ahead=0)
    rows = [i.to_dict() for i in work.items if i.overdue]
    rows.sort(key=lambda r: (not r["is_assessment"], -(r["points"] or 0)))
    return {
        "student": e["name"], "as_of": work.as_of.isoformat(), "count": len(rows),
        "points_at_stake": sum((r["points"] or 0) for r in rows), "items": rows,
        "not_shown": {"count": len(work.dropped), "points": sum((i.points or 0) for i in work.dropped)},
    }


@mcp.tool()
def upcoming(student: str, days: int = 14) -> dict:
    """Canvas assignments due from now through the next N days, Eastern time, not yet
    submitted, with the same status words as the printed sheet (DUE TODAY / DUE TOMORROW /
    DUE <weekday>)."""
    e, work = _open_work(student, days_ahead=days, include_hac=False)
    rows = [i.to_dict() for i in work.items if not i.overdue]
    return {"student": e["name"], "window_days": days, "items": rows}


@mcp.tool()
def hac_classwork(student: str, course: str | None = None) -> dict:
    """Raw HAC classwork rows (score, points, category) and category subtotals — the official gradebook detail."""
    e = _kid(_snap(), student)
    classes = (e.get("hac") or {}).get("classes") or []
    if course:
        classes = [c for c in classes if course.lower() in c["name"].lower()]
    return {"student": e["name"], "classes": classes}


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mcp.run(transport="stdio")

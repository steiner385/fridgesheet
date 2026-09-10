"""MCP server. Run with `lakota-grades serve` (stdio transport).

Tools return plain JSON. The agent never sees credentials: logins happen inside this process.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:  # mcp >= 2.0 renamed FastMCP to MCPServer; the tool/run API is otherwise identical
    from mcp.server.mcpserver import MCPServer as _McpServer
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _McpServer

from . import collector
from .config import load_settings

log = logging.getLogger("lakota.server")

mcp = _McpServer("lakota-grades")
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
        h = _match(c["name"], hac_classes) or {}
        w = _match(c["name"], hac_week) or {}
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
    flagged_by_course: dict[str, list[str]] = {}
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
                flagged_by_course.setdefault(c["name"], []).append(a["name"])
    all_flagged = [n for names in flagged_by_course.values() for n in names]
    for h in ((e.get("hac") or {}).get("classes") or []):
        # Dedupe within the matching Canvas course when we can pair them up; two different
        # courses legitimately both have a "Quiz 1", and the old global name set dropped the
        # second one. Fall back to the global set for HAC-only classes.
        peer = _match(h.get("name") or "", flagged_by_course)
        already = peer if peer is not None else all_flagged
        for a in h["assignments"]:
            if any(_same_item(a["name"], seen) for seen in already):
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


def _norm_name(s: str) -> str:
    """Compare assignment titles across systems ignoring case, punctuation and spacing."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _same_item(a: str, b: str) -> bool:
    """Whether two titles from Canvas and HAC name the same piece of work.

    Teachers rarely type the title identically in both gradebooks -- Canvas' "MakeMusic Cloud
    Assignment #1" is HAC's "MakeMusic Assignment #1" -- so exact matching let real duplicates
    through. Compare word sets instead, but treat numbers as decisive: "Quiz 1" must never
    merge with "Quiz 2", nor "Chapter 1.3" with "Chapter 1.4", however similar the words.
    """
    ta, tb = set(_norm_name(a).split()), set(_norm_name(b).split())
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if {x for x in ta if x.isdigit()} != {x for x in tb if x.isdigit()}:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.7


# HAC labels a class "Algebra II - 3" (section); Canvas labels it "Algebra II S1" (term).
# Trim both tails so the two systems' names for one class compare equal.
_COURSE_TAIL_RE = re.compile(r"\s*(?:-\s*\d+|\bS[12]\b|\bSem\s*[12]\b|-\s*20\d\d.*)$", re.I)

# The two systems abbreviate differently -- Canvas' "ENGLISH LANGUAGE ARTS" is HAC's
# "ELA Plus 5th Gr", which share no words at all. Expand both sides to a common long form.
_ABBREV = {
    "soc std": "social studies",
    "soc studies": "social studies",
    "lang arts": "language arts",
    "ela": "english language arts",
    "adv": "advanced",
    "hnrs": "honors",
    "hon": "honors",
    "gr": "grade",
    "alg": "algebra",
    "bio": "biology",
    "lit": "literature",
}

#: Escape hatch for pairs no rule can infer, e.g.
#: LAKOTA_COURSE_ALIASES='{"ENGLISH LANGUAGE ARTS": "ELA Plus 5th Gr"}'
#: Both sides are rewritten to the alias target before matching.
try:
    _ALIASES = {k.strip().lower(): v for k, v in json.loads(os.environ.get("LAKOTA_COURSE_ALIASES", "{}")).items()}
except (ValueError, AttributeError):
    log.warning("LAKOTA_COURSE_ALIASES is not a JSON object; ignoring it")
    _ALIASES = {}


def _expand(s: str) -> str:
    for abbr in sorted(_ABBREV, key=len, reverse=True):   # multi-word entries first
        s = re.sub(rf"\b{re.escape(abbr)}\b", _ABBREV[abbr], s)
    return " ".join(s.split())


def _course_base(name: str) -> str:
    b = " ".join((name or "").split())
    b = _ALIASES.get(b.strip().lower(), b)
    prev = None
    while prev != b:
        prev, b = b, _COURSE_TAIL_RE.sub("", b).strip()
    return _expand(b.lower())


def _match(base: str, table: dict):
    """Pair a course name against the other system's differently-formatted name.

    Scores every candidate and takes the best, rather than returning the first that clears a
    loose test. The original fell back to "first word and last word both appear", which for a
    7th-grade schedule means "adv" and "7" -- true of Adv Math 7, Adv Science 7, Adv Social
    Studies 7 and Adv Language Arts 7 alike, so all four paired with whichever came first in
    the dict and the rest were reported a second time as HAC-only classes.
    """
    b = _course_base(base)
    if len(b) < 3:  # base.split()[0] raised IndexError on an empty name
        return None
    tb = set(b.split())
    best, best_score = None, 0.0
    for k, v in table.items():
        kl = _course_base(k)
        if len(kl) < 3:
            continue
        if b == kl:
            return v
        tk = set(kl.split())
        if not tk:
            continue
        # Course numbers distinguish siblings ("Adv Math 7" vs "Adv Math 8"), so a
        # disagreement on digits disqualifies the pair however alike the words are.
        if {x for x in tb if x.isdigit()} != {x for x in tk if x.isdigit()}:
            continue
        if (b in kl and len(tb) >= 2) or (kl in b and len(tk) >= 2):
            # One name is the other plus qualifiers: "english language arts" inside
            # "english language arts plus 5th grade". The >=2 word floor stops a bare
            # "Math" from swallowing "Math Plus".
            score = 0.95
        else:
            score = len(tb & tk) / len(tb | tk)
        if score > best_score:
            best, best_score = v, score
    return best if best_score >= 0.7 else None


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mcp.run(transport="stdio")

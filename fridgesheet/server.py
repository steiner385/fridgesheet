"""MCP server. Run with `fridgesheet serve` (stdio transport).

Tools return plain JSON. The agent never sees credentials: logins happen inside this process.
"""
from __future__ import annotations

import functools
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:  # mcp >= 2.0 renamed FastMCP to MCPServer; the tool/run API is otherwise identical
    from mcp.server.mcpserver import MCPServer as _McpServer
except ModuleNotFoundError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _McpServer

from dataclasses import asdict

from . import collector, config, grading, guidance, late_rules, open_items, work_types
from .config import load_settings
from .matching import match_course as _match, pair_titles
from .reports.open_work import OpenWorkReport, wanted as _wanted
from .sources import pick_value

log = logging.getLogger("fridgesheet.server")

mcp = _McpServer("fridgesheet")
@functools.lru_cache(maxsize=1)
def _settings():
    """Read on the first tool call, not at import (#3): a broken config.toml then fails that
    call with its message, instead of the MCP server failing to start with a traceback."""
    return load_settings()


def _snap() -> dict:
    """The snapshot every read answers from, pulled afresh first when it is stale -- under
    run.lock, as `run` and `refresh --record` pull, so a read never puts a second Chromium
    over the browser profile a scheduled print is using (#151). While another run holds the
    lock a read is answered from the snapshot on disk, and `status()` says so
    (`run_in_progress`): an older number with a reason beats minutes of silence inside a tool
    call. With no snapshot at all there is nothing to answer from, and the call says that."""
    s = _settings()
    snap = collector.load_snapshot(s)
    if not collector.snapshot_is_fresh(s, snap):
        try:
            snap = collector.collect_locked(s, wait_seconds=0)
        except collector.RunInProgress as e:
            if snap is None:
                raise RuntimeError(f"No snapshot to answer from yet: {e}") from None
    return snap


def _kid(snap: dict, student: str) -> tuple[str, dict]:
    """The student's key and entry. Found the way `--kid` finds a kid for the printed sheet
    (`reports.open_work.wanted`): the key or the nickname, then a start of either, then a
    longer form of the key. The key is what late rules and source rules resolve by everywhere
    else (#161); the first word of the entry's name, which this used to match on and pass to
    the rules, is "RIVERA," for a kid only HAC knows (#151)."""
    for key, entry in snap["students"].items():
        if _wanted(key, student, _settings().nicknames, snap["students"]):
            return key, entry
    raise ValueError(f"Unknown student '{student}'. Known: {', '.join(snap['students'])}")


@mcp.tool()
def refresh(kids: list[str] | None = None, hac: bool = True, canvas: bool = True) -> dict:
    """Re-pull Canvas and/or HAC now (logs in if a session expired) and return the source status.
    Use before building a report so numbers are current. Takes ~1-3 minutes. A source that
    fails keeps its data from the last good pull; `stale` says which and how old. So does a
    single Canvas class that fails: `carried` names it and the pull it comes from. A scheduled
    print or refresh already in progress is waited for a few minutes; if it is still running,
    the status of the snapshot on disk comes back with `refresh` saying nothing was pulled."""
    s = _settings()
    try:
        snap = collector.collect_locked(s, include_hac=hac, include_canvas=canvas, kids_filter=kids)
    except collector.RunInProgress as e:
        return {**collector.summary(s, collector.load_snapshot(s)), "refresh": f"not run: {e}"}
    return collector.summary(s, snap)


@mcp.tool()
def status() -> dict:
    """Snapshot age, whether each source (Canvas, HAC) was reachable on the last pull, which
    sources are being served from an older pull (`stale`, with that pull's time), which
    Canvas classes are (`carried`, with that pull's time and why) or could not be pulled at
    all (`missing`), and whether a run holds run.lock right now (`run_in_progress`: reads
    answer from this snapshot)."""
    return collector.summary(_settings(), collector.load_snapshot(_settings()))


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
    when that one has no average. Canvas can be hidden or partial.

    `account` is how HAC's number is built (grading.Account): its category lines (earned,
    possible, share of the grade), the rebuilt total, and `match`: "exact" when the rebuild
    equals HAC's number, "off" when it does not (HAC may weight categories, or count work the
    scraper cannot see), "unknown" when there is no number to check. Never present an "off"
    rebuild as the grade. `canvas_account` is the same for Canvas (graded work only; `final`
    counts missing work as zero; `hidden` when the teacher hides it)."""
    key, e = _kid(_snap(), student)
    out = {"student": e["name"], "classes": []}
    now = datetime.now(ZoneInfo(_settings().timezone))
    rules = late_rules.load(_settings().home / "late-rules.toml", household=_snap()["students"])
    hac_classes = {c["name"]: c for c in (e.get("hac") or {}).get("classes", [])}
    hac_week = {w["class"]: w for w in (e.get("hac") or {}).get("week_view", [])}
    seen = set()
    for c in ((e.get("canvas") or {}).get("courses") or []):
        h = _match(c["name"], hac_classes) or {}
        w = _match(c["name"], hac_week) or {}
        seen.add(h.get("name"))
        hac_official = h.get("marking_period_avg", w.get("current_average"))
        pick = _settings().sources.resolve(key, c["name"], h.get("name")).grades
        official, official_source = pick_value(pick, c["grade"]["current_score"], hac_official)
        canvas_rows = [{"group": a.get("group"), "score": a.get("score"), "points": a.get("points_possible"), "excused": a.get("excused"),
                        "missing": a.get("missing"), "state": a.get("state")} for a in (c.get("assignments") or [])]
        out["classes"].append({
            "course": c["name"],
            "official": official, "official_source": official_source,
            "hac_official": hac_official,
            "hac_last_updated": h.get("last_updated"),
            "hac_categories": h.get("categories"),
            "account": _hac_account(h) if h else None,
            "guidance": _guidance(h or None, c, now, rules, key, c["name"], h.get("name"), pick),
            "canvas_current": c["grade"]["current_score"],
            "canvas_final_if_unsubmitted_zero": c["grade"]["final_score"],
            "canvas_hidden": c["grade"]["hidden"],
            "canvas_account": asdict(grading.account_canvas(c["grade"]["current_score"], c["grade"]["final_score"], c["grade"]["hidden"], canvas_rows)),
            "staff": c.get("staff"),
        })
    for name, h in hac_classes.items():  # HAC-only classes (e.g. Hawk Time)
        if name not in seen:
            pick = _settings().sources.resolve(key, name).grades
            official, official_source = pick_value(pick, None, h.get("marking_period_avg"))
            out["classes"].append({"course": name, "official": official, "official_source": official_source, "hac_official": h.get("marking_period_avg"), "hac_last_updated": h.get("last_updated"), "hac_categories": h.get("categories"), "account": _hac_account(h), "guidance": _guidance(h, None, now, rules, key, name, None, pick), "canvas_current": None, "canvas_final_if_unsubmitted_zero": None, "canvas_hidden": None, "canvas_account": None})
    return out


def _hac_account(h: dict) -> dict:
    """grading.account_hac over one HAC class as the snapshot holds it, as a plain dict."""
    rows = [{"category": r.get("category"), "score": r.get("score"), "points": r.get("points"), "excused": open_items.hac_excused(r)}
            for r in (h.get("assignments") or [])]
    return _account_dict(grading.account_hac(h.get("marking_period_avg"), h.get("categories") or [], rows))


def _account_dict(account: grading.Account) -> dict:
    """asdict, plus each line's percent (a property `asdict` leaves out) as HAC prints it."""
    out = asdict(account)
    for line, d in zip(account.lines, out["lines"]):
        d["percent"] = round(line.percent, 2) if line.percent is not None else None
    return out


def _guidance(h: dict | None, c: dict | None, now: datetime, rules, kid: str, course_name: str, peer: str | None,
              pick: str = "hac") -> dict | None:
    """guidance.guide over the snapshot (spec 2026-10-04 §7.4), on the family's official
    gradebook for the class (`pick`), with upcoming work inside the sheet's days-ahead window as
    the web reads it, handed-in work never a lever, and a Canvas assignment paired to its HAC row
    by `matching.pair_titles` (the rule ingest uses) counted once. Flags set in the app are not
    applied here (as `missing_work`), so a row the family answered may still be a lever."""
    if h is None and c is None:
        return None
    hac_rows_ = (h or {}).get("assignments") or []
    canvas_rows_ = (c or {}).get("assignments") or []
    if pick == "canvas" and c is not None:
        g = c.get("grade") or {}
        account = grading.account_canvas(g.get("current_score"), g.get("final_score"), g.get("hidden"),
                                         [{"group": a.get("group"), "score": a.get("score"), "points": a.get("points_possible"), "excused": a.get("excused"),
                                           "missing": a.get("missing"), "state": a.get("state")} for a in canvas_rows_])
    elif h is not None:
        account = grading.account_hac(h.get("marking_period_avg"), h.get("categories") or [],
                                      [{"category": r.get("category"), "score": r.get("score"), "points": r.get("points"), "excused": open_items.hac_excused(r)}
                                       for r in hac_rows_])
    else:
        return None
    credit = rules.resolve(kid, course_name, peer).credit
    horizon = now + timedelta(days=config.day_option(_settings().report_config(OpenWorkReport.key).options, "days_ahead"))
    rows = []
    for r in hac_rows_:
        due = open_items.parse_hac_date(r.get("due"), now.tzinfo)
        score = r.get("score")
        if (score is not None and score != 0) or open_items.hac_excused(r) or due is None:
            continue
        due = due.replace(hour=23, minute=59)
        if due > horizon:
            continue
        late_until = rules.deadline(kid, course_name, due, peer)
        # Past its window it is no lever, but a blank one still used HAC's zero budget (final review, 2026-10-04).
        gone = due < now and now > late_until
        rows.append({"item_id": None, "name": r.get("name"), "category": r.get("category"), "points": r.get("points"), "due": due,
                     "late_until": late_until, "credit_text": credit, "overdue": due < now, "upcoming": due >= now,
                     "hac_blank": score is None, "hac_scored": score is not None, "hac_zero": score == 0, "counted_only": gone})
    twins = set(pair_titles([a.get("name") or "" for a in canvas_rows_], [r.get("name") or "" for r in hac_rows_]))
    for i, a in enumerate(canvas_rows_):
        if i in twins or (a.get("score") is not None and a.get("score") != 0) or a.get("excused") or not a.get("due_at"):
            continue
        if a.get("state") in ("submitted", "pending_review", "graded"):
            continue                                    # handed in: waiting for a grade, not a lever
        due = datetime.fromisoformat(a["due_at"])
        if due > horizon:
            continue
        late_until = rules.deadline(kid, course_name, due, peer)
        if due < now and now > late_until:
            continue
        zero = a.get("score") == 0
        rows.append({"item_id": a.get("id"), "name": a.get("name"), "category": a.get("group"), "points": a.get("points_possible"), "due": due,
                     "late_until": late_until, "credit_text": credit, "overdue": due < now, "upcoming": due >= now,
                     "hac_blank": False, "hac_scored": zero, "hac_zero": zero and pick == "canvas"})
    return asdict(guidance.guide(account, rows, _settings().grading))


@mcp.tool()
def assignments(student: str, course: str | None = None, include_graded: bool = True) -> dict:
    """Every Canvas assignment for a student (optionally one course, matched by substring) with due date
    (America/New_York ISO), points, score, and late/missing/excused flags."""
    _, e = _kid(_snap(), student)
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
    snap = _snap()
    key, e = _kid(snap, student)
    now = datetime.now(ZoneInfo(_settings().timezone))
    rules = late_rules.load(_settings().home / "late-rules.toml", household=snap["students"])
    # Late rules and source rules resolve by the key, as the sheet and the web do (#161); the
    # label is the nickname the sheet would print, and is only printed.
    return e, open_items.open_items(e, _settings().nicknames.get(key, key), now, days_ahead=days_ahead, rules=rules,
                                    include_hac=include_hac, prefs=_settings().sources, student_key=key)


@mcp.tool()
def missing_work(student: str) -> dict:
    """Overdue work the student can still act on: Canvas items missing, scored 0, turned in
    late but ungraded, or past due and unsubmitted (on-paper ones as PAPER — CHECK), plus HAC
    rows with a blank score after the due date, deduped. Each row carries `late_until` and
    `credit` from ~/.fridgesheet/late-rules.toml; items past that deadline or more than two
    weeks overdue are only counted under `not_shown`. The same rules as the printed sheet,
    except that flags set in the app (done, excused, ignore) are not applied here, so an item
    the sheet drops as handled still appears. Sorted tests and quizzes first, then labs and projects,
    everyday work and participation (`family`, from the gradebooks' names); then by points."""
    e, work = _open_work(student, days_ahead=0)
    rows = [i.to_dict() for i in work.items if i.overdue]
    rows.sort(key=lambda r: (work_types.RANK.get(r["family"], len(work_types.RANK)), -(r["points"] or 0)))
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
    _, e = _kid(_snap(), student)
    classes = (e.get("hac") or {}).get("classes") or []
    if course:
        classes = [c for c in classes if course.lower() in c["name"].lower()]
    return {"student": e["name"], "classes": classes}


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    mcp.run(transport="stdio")

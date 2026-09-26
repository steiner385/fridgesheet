"""One snapshot for every page test: two kids, and every row situation the pages must show.

Alex, Honors English 9 (Canvas course 5 <-> HAC "Honors English 9 S1"):
  77 Quiz 1        due 9/12  Canvas MISSING, HAC 28/30           -> done on paper (HAC's grade beats the automatic flag)
  78 Essay draft   due 9/14  submitted, ungraded                 -> submitted_ungraded, not open
  79 Reading log   due 9/20  unsubmitted, in the future          -> upcoming, not open
  80 Worksheet 3   due 9/16  unsubmitted (tomorrow)              -> upcoming, due tomorrow
  81 Vocabulary    due 9/15  unsubmitted (today)                 -> upcoming, due today
  82 Lab notebook  due 9/10  on paper, unsubmitted, no grade     -> open (canvas), paper_no_grade
  HAC-only "Participation" due 9/08, blank score                 -> open (hac), one_source
Alex, Algebra I (Canvas course 6 <-> HAC "Algebra I - 2"):
  90 Homework 4    due 8/20  MISSING                             -> open, past_credit (14-day default window)
Sam, Science 7 (Canvas course 7 <-> HAC "Science 7 - 1"):
  100 Cell diagram due 9/13  MISSING                             -> open, actionable
  101 Safety quiz  due 9/11  graded 0                            -> open (ZERO), actionable
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from fridgesheet import config, host
from fridgesheet.web import app as webapp, db, ingest

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)

CHART_CONFIG = re.compile(r'<script type="application/json" data-chart-config>(.*?)</script>', re.S)


def chart_configs(body: str) -> list[dict]:
    """Every inlined chart config on a page, in page order, decoded (the `\\u003c` escapes
    `charts.escape_for_script_tag` writes are plain JSON to `json.loads`)."""
    return [json.loads(m) for m in CHART_CONFIG.findall(body)]


def _a(id, name, due, **kw):
    base = {"id": id, "name": name, "due_at": f"2026-{due}T23:59:00-04:00", "unlock_at": None, "created_at": "2026-08-20T08:00:00-04:00",
            "points_possible": 10.0, "submission_types": ["online_upload"], "group": "Homework", "group_weight": None,
            "published": True, "score": None, "grade": None, "state": "unsubmitted", "late": False, "missing": False,
            "excused": False, "submitted_at": None, "seconds_late": 0}
    base.update(kw)
    return base


def _h(name, due, score, points=10.0, assigned="09/01/2026"):
    return {"due": due, "assigned": assigned, "name": name, "category": "Assignments", "score": score,
            "score_raw": "" if score is None else f"{score:.2f}", "points": points, "percent": "" if score is None else "93.33%"}


def snapshot() -> dict:
    return {
        "fetched_at": "2026-09-15T13:50:00-04:00", "fetched_at_epoch": 1789494600, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {
            "Alex": {"name": "Alex Example", "canvas_id": 1, "hac_name": "Alex Example",
                "canvas": {"courses": [
                    {"id": 5, "name": "Honors English 9 S1-2027-Hoch", "course_code": "ENG9",
                     "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False},
                     "staff": [{"name": "Michael Hoch", "email": "hoch@example.org", "roles": ["TeacherEnrollment"]}],
                     "assignments": [
                         _a(77, "Quiz 1", "09-12", missing=True, points_possible=30.0),
                         _a(78, "Essay draft", "09-14", state="submitted", submitted_at="2026-09-14T20:00:00-04:00"),
                         _a(79, "Reading log", "09-20"),
                         _a(80, "Worksheet 3", "09-16"),
                         _a(81, "Vocabulary", "09-15"),
                         _a(82, "Lab notebook", "09-10", submission_types=["on_paper"]),
                     ]},
                    {"id": 6, "name": "Algebra I S1-2027-Lee", "course_code": "ALG1",
                     "grade": {"current_score": 78.0, "final_score": None, "current_grade": "C+", "hidden": False},
                     "staff": [{"name": "Dana Lee", "email": None, "roles": ["TeacherEnrollment"]}],
                     "assignments": [_a(90, "Homework 4", "08-20", missing=True)]},
                ]},
                "hac": {"week_view": [], "classes": [
                    {"code": "13001 - 5", "name": "Honors English 9 S1", "marking_period_avg": 88.0, "last_updated": "9/11/2026",
                     "assignments": [_h("Quiz 1", "09/12/2026", 28.0, points=30.0), _h("Participation", "09/08/2026", None)], "categories": []},
                    {"code": "20010 - 2", "name": "Algebra I - 2", "marking_period_avg": 79.5, "last_updated": "9/12/2026",
                     "assignments": [], "categories": []},
                ]}},
            "Sam": {"name": "Sam Example", "canvas_id": 2, "hac_name": "Sam Example",
                "canvas": {"courses": [
                    {"id": 7, "name": "Science 7 S1-2027-Kim", "course_code": "SCI7",
                     "grade": {"current_score": 85.0, "final_score": None, "current_grade": "B", "hidden": False},
                     "staff": [{"name": "Pat Kim", "email": None, "roles": ["TeacherEnrollment"]}],
                     "assignments": [_a(100, "Cell diagram", "09-13", missing=True),
                                     _a(101, "Safety quiz", "09-11", state="graded", score=0.0, grade="0")]},
                ]},
                "hac": {"week_view": [], "classes": [
                    {"code": "30001 - 1", "name": "Science 7 - 1", "marking_period_avg": 84.0, "last_updated": "9/12/2026",
                     "assignments": [], "categories": []},
                ]}},
        },
    }


#: `seed`'s sentinel for "the caller didn't pass this" -- distinct from any real value
#: (including "", the default a blank update PIN and an untouched config.toml agree on) so
#: `seed(tmp_path)` alone still leaves config.toml untouched, the way every other test that
#: asserts on its absence (e.g. test_web_schedules_page.py) already expects.
_UNSET = object()


def seed(home: Path, snap: dict | None = None, now: datetime = NOW, *,
         update_pin_hash: str = _UNSET, check_updates: bool = _UNSET) -> sqlite3.Connection:
    conn = db.open_db(home)
    ingest.record(conn, snap or snapshot(), tz=TZ, now=now)
    if update_pin_hash is not _UNSET or check_updates is not _UNSET:
        doc = config.load_config_doc(home / "config.toml")
        web = dict(doc.get("web") or {})
        if update_pin_hash is not _UNSET:
            web["update_pin_hash"] = update_pin_hash
        if check_updates is not _UNSET:
            web["check_updates"] = check_updates
        config.save_config_doc(home / "config.toml", {**doc, "web": web})
    return conn


#: `TestClient`'s own default Host ("testserver") is not an address this app is ever served
#: on, and `same_origin_only` now checks Host on every request, GET included -- so every
#: client built for these tests needs a Host it actually answers to. "127.0.0.1" is always in
#: that set regardless of a test's `allow_lan`/`FRIDGESHEET_WEB_HOST`, since a bare hostname with no
#: port skips the port check.
LOCAL_HOST_HEADERS = {"host": "127.0.0.1"}


def app_for(home: Path, now: datetime = NOW, worker: bool = False, *, service_installed: bool = True) -> TestClient:
    """A client whose app clock is frozen at `now` (pages compare due dates against it).

    Reads `home/config.toml` if `seed(..., update_pin_hash=..., check_updates=...)` (or a
    test writing it directly) left one -- the same load `AppState.reload()` does for a
    non-default home, so a test that seeds a PIN before building its client sees it without
    a separate reload() call.

    `service_installed` stubs `describe_service()` through `state.extra["describe_service"]`,
    so a page test never shells out to the real `systemctl --user`/`schtasks` on whatever machine runs
    the suite. Defaults to True (a healthy install); pass False for the issue #39 case, where
    the logon task never got registered.
    """
    s = config.Settings(home=home)
    config.settings_from_doc(config.load_config_doc(home / "config.toml"), s)
    application = webapp.create_app(s, worker=worker)
    application.state.fridgesheet.clock = lambda: now
    application.state.fridgesheet.extra["describe_service"] = lambda: host.ServiceInfo(
        "task-scheduler", installed=service_installed, active=service_installed, detail="stub")
    return TestClient(application, headers=LOCAL_HOST_HEADERS)


def client_with_grades(home: Path, **grades) -> TestClient:
    """A client whose config.toml carries these grades.

    `app_for` builds `config.Settings(home=home)` and never reads config.toml --
    only `AppState.reload()` does that (app.py:62-72). So the file is written first and the
    state reloaded once, which is also what the Settings page does after a save.
    """
    if grades:
        p = home / "config.toml"
        text = p.read_text(encoding="utf-8") if p.exists() else ""
        rows = ", ".join(f"{k} = {v}" for k, v in grades.items())
        p.write_text(text + f"""
[kids]
grades = {{ {rows} }}
""", encoding="utf-8")
    c = app_for(home)
    c.app.state.fridgesheet.reload()
    return c


REFRESH_TIMES = ("2026-09-13T06:00:00-04:00", "2026-09-14T06:00:00-04:00", "2026-09-15T13:50:00-04:00")


def _history_snapshots() -> list[dict]:
    """Three days of one household, so the change log has something to say.

    Day 1 (9/13): Quiz 1 is ungraded everywhere; Homework 4 is not missing yet; no Vocabulary.
    Day 2 (9/14): HAC posts Quiz 1 at 28/30 and the English average rises; Homework 4 goes
                  MISSING in Canvas; Vocabulary appears for the first time.
    Day 3 (9/15): Canvas marks Quiz 1 MISSING (it disagrees with HAC -- the reconcile case),
                  Essay draft is submitted, Safety quiz is graded 0, English average slips.
    """
    day1 = snapshot()
    eng = day1["students"]["Alex"]["canvas"]["courses"][0]
    eng["grade"]["current_score"] = 93.0
    eng["assignments"] = [a for a in eng["assignments"] if a["name"] != "Vocabulary"]
    for a in eng["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"] = False
        if a["name"] == "Essay draft":
            a["state"], a["submitted_at"] = "unsubmitted", None
    day1["students"]["Alex"]["canvas"]["courses"][1]["assignments"][0]["missing"] = False
    hac_eng = day1["students"]["Alex"]["hac"]["classes"][0]
    hac_eng["marking_period_avg"] = 85.0
    hac_eng["assignments"] = [_h("Quiz 1", "09/12/2026", None, points=30.0), _h("Participation", "09/08/2026", None)]
    sci = day1["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci["assignments"]:
        if a["name"] == "Safety quiz":
            a["state"], a["score"], a["grade"] = "unsubmitted", None, None
    day1["fetched_at"] = REFRESH_TIMES[0]

    day2 = snapshot()
    eng2 = day2["students"]["Alex"]["canvas"]["courses"][0]
    eng2["grade"]["current_score"] = 93.0
    for a in eng2["assignments"]:
        if a["name"] == "Quiz 1":
            a["missing"] = False
        if a["name"] == "Essay draft":
            a["state"], a["submitted_at"] = "unsubmitted", None
    sci2 = day2["students"]["Sam"]["canvas"]["courses"][0]
    for a in sci2["assignments"]:
        if a["name"] == "Safety quiz":
            a["state"], a["score"], a["grade"] = "unsubmitted", None, None
    day2["fetched_at"] = REFRESH_TIMES[1]

    day3 = snapshot()                                  # the fixture every other test already knows
    day3["fetched_at"] = REFRESH_TIMES[2]
    return [day1, day2, day3]


def history(home: Path, now: datetime = NOW) -> sqlite3.Connection:
    """Three refreshes of the standard household, oldest first. Returns the open connection."""
    conn = db.open_db(home)
    for snap in _history_snapshots():
        ingest.record(conn, snap, tz=TZ, now=datetime.fromisoformat(snap["fetched_at"]))
    return conn


def canvas_grades_later(conn: sqlite3.Connection, name: str, score: float) -> None:
    """Record a Canvas grade for `name` in a refresh after the seed's, as a teacher who later
    scored it in Canvas would. Quiz 1 then has a Canvas score (not MISSING) *and* HAC's 28/30,
    which is the case where the family's source preference decides which score shows."""
    with conn:
        rid = conn.execute("INSERT INTO refreshes(started_at, sources, ok) VALUES ('2026-09-15T13:55:00-04:00', '{}', 1)").lastrowid
        iid = conn.execute("SELECT id FROM items WHERE name = ?", (name,)).fetchone()["id"]
        conn.execute("""INSERT INTO item_observations(refresh_id, item_id, source, state, score, grade, submitted_at, late, missing, excused, published)
                        VALUES (?, ?, 'canvas', 'graded', ?, ?, NULL, 0, 0, 0, 1)""", (rid, iid, score, str(score)))

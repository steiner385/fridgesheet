"""One snapshot for every page test: two kids, and every row situation the pages must show.

Alex, Honors English 9 (Canvas course 5 <-> HAC "Honors English 9 S1"):
  77 Quiz 1        due 9/12  Canvas MISSING, HAC 28/30           -> open (canvas), disagree
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

import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from fridgesheet import config, host
from fridgesheet.web import app as webapp, db, ingest

TZ = ZoneInfo("America/New_York")
NOW = datetime(2026, 9, 15, 14, 0, tzinfo=TZ)


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

    `service_installed` stubs `describe_service()` through `state.extra["describe_service"]`
    -- the same seam `extra["scheduling"]` is for `host.scheduling.describe` -- so a page
    test never shells out to the real `systemctl --user`/`schtasks` on whatever machine runs
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


class FakeScheduling:
    """A scheduler that records every call and answers `describe` from a dict.

    Stands in for `host.scheduling` wherever a test would otherwise reach systemctl or
    schtasks. `info` maps a report key to the `ScheduleInfo` `describe` should return;
    `fail` makes `install`/`remove` raise `SchedulingError` with that message, and
    `not_supported` makes them raise `NotSupported` instead -- whichever of the two the
    caller's `save()` actually reaches (only one of `install`/`remove` runs per call).
    `describe_error`, if given, is an exception instance `describe()` raises instead of
    answering from `info` -- the fake never failed `describe` before this, which meant
    `web/schedules.py`'s two exception-handling branches around a `describe()` call
    (`_installed_or_unknown`'s `NotSupported`/`Exception` split) had nothing to exercise them.
    """
    SchedulingError = host.SchedulingError
    NotSupported = host.NotSupported

    def __init__(self, info=None, fail=None, not_supported=None, describe_error=None):
        self.installed, self.removed = [], []
        self._info, self._fail, self._not_supported = info or {}, fail, not_supported
        self._describe_error = describe_error

    def _maybe_fail(self):
        if self._not_supported:
            raise host.NotSupported(self._not_supported)
        if self._fail:
            raise host.SchedulingError(self._fail)

    def command_for(self, key):
        return ("/py", f"run {key}", "/wd")

    def install(self, key, times, days, exe, args, workdir, **kw):
        self._maybe_fail()
        self.installed.append({"key": key, "times": list(times), "days": list(days), **kw})

    def remove(self, key, **kw):
        self._maybe_fail()
        self.removed.append(key)

    def describe(self, key):
        if self._describe_error is not None:
            raise self._describe_error
        return self._info.get(key, host.ScheduleInfo("systemd", False, None, None))

    def task_name(self, key):
        return f"Fridge Sheet - {key}"

    def blocking_name(self, key):
        """The Linux unit name a real `scheduling_linux` would name in an unmanageable-row
        refusal: `LEGACY_TIMERS[key]` for the one key that has a hand-written unit under a
        different name, `fridgesheet-<safe_key(key)>.timer` for everything else."""
        from fridgesheet.host import scheduling_linux
        return scheduling_linux.blocking_name(key)

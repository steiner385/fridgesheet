"""Pull everything for every kid into one JSON snapshot, with a small on-disk cache."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from .canvas import Canvas
from .config import Settings
from .hac import HAC
from .session import LoginRequired, browser, ensure_canvas, ensure_hac

log = logging.getLogger("fridgesheet.collector")

#: How long `collect_locked` waits for another run to let go of run.lock before giving up: a
#: refresh is one to three minutes, so this outlasts one that started just before us without
#: holding a terminal (or the hand-written refresh timer) for as long as a stuck run would.
LOCK_WAIT_SECONDS = 5 * 60
LOCK_POLL_SECONDS = 5


class RunInProgress(RuntimeError):
    """Another run holds run.lock and `collect_locked` gave up waiting. One line, for a
    terminal or a tool result."""


def run_in_progress(s: Settings) -> bool:
    """Whether a run (a scheduled print, `refresh --record`, the Refresh now button) holds
    run.lock right now -- the reason a read is being answered from an older snapshot."""
    from . import runner                                    # runner imports this module
    return runner.Lock(s.home / runner.LOCK_NAME).is_held()


def collect_locked(s: Settings, *, wait_seconds: int | None = None, sleep=None, **kw) -> dict:
    """`collect` under the runner's run.lock, the lock `run` and `web.actions.refresh` already
    hold around their own pull: one Chromium at a time over the one browser profile. Bare
    `refresh` (and so the hand-written refresh timer) and the MCP server used to call
    `collect` with no lock and could overlap a scheduled print (#151).

    Waits up to `wait_seconds` (`LOCK_WAIT_SECONDS`; 0 for "now or not at all") for the other
    run to finish, polling every `LOCK_POLL_SECONDS`, then raises `RunInProgress`. Counted by
    the naps taken, not the clock, so a test's fake `sleep` sees the same bound. `kw` is
    `collect`'s own keywords."""
    from . import runner
    wait = LOCK_WAIT_SECONDS if wait_seconds is None else wait_seconds
    sleep = sleep or time.sleep
    lock = runner.Lock(s.home / runner.LOCK_NAME)
    waited = 0
    while not lock.acquire():
        if waited >= wait:
            raise RunInProgress(f"another run holds {lock.path} (a scheduled print or refresh in progress); "
                                f"waited {waited} s and gave up -- try again in a few minutes")
        nap = min(LOCK_POLL_SECONDS, wait - waited)
        sleep(nap)
        waited += nap
    try:
        return collect(s, **kw)
    finally:
        lock.release()


def _snapshot_path(s: Settings) -> Path:
    return s.cache_dir / "snapshot.json"


def load_snapshot(s: Settings) -> dict | None:
    p = _snapshot_path(s)
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def snapshot_is_fresh(s: Settings, snap: dict | None) -> bool:
    return bool(snap) and (time.time() - snap.get("fetched_at_epoch", 0)) < s.cache_ttl_minutes * 60


def summary(s: Settings, snap: dict | None) -> dict:
    """What `status`, `refresh` and the CLI report: age, per-source health, which sources
    are being served from an older pull (and how old), the kids in the snapshot, and whether
    a run holds run.lock right now (`run_in_progress`: a read is answered from this snapshot
    rather than pulling a fresh one over that run's Chromium)."""
    if not snap:
        return {"snapshot": None, "fresh": False, "run_in_progress": run_in_progress(s)}
    carried, missing = course_faults(snap)
    return {
        "fetched_at": snap["fetched_at"],
        "fresh": snapshot_is_fresh(s, snap),
        "sources": snap["sources"],
        "stale": {src: {"fetched_at": m["fetched_at"], "reason": m["reason"]} for src, m in (snap.get("stale") or {}).items()},
        "carried": carried,
        "missing": missing,
        "students": list(snap["students"]),
        "run_in_progress": run_in_progress(s),
    }


def course_faults(snap: dict | None) -> tuple[list[dict], list[dict]]:
    """The Canvas classes this snapshot could not pull, in two lists: `carried` (served from
    an older pull -- which one, and why this one failed) and `missing` (nothing older to
    serve; the class is absent). Both are empty for a snapshot with no per-course errors."""
    carried, missing = [], []
    for kid, entry in ((snap or {}).get("students") or {}).items():
        cv = entry.get("canvas") or {}
        kept = cv.get("carried") or {}
        for err in cv.get("errors") or []:
            cid = str(err["course_id"])
            if cid in kept:
                carried.append({"kid": kid, "course_id": cid, "name": kept[cid]["name"], "reason": kept[cid]["reason"],
                                "fetched_at": kept[cid]["fetched_at"]})
            else:
                missing.append({"kid": kid, "course_id": cid, "reason": err["error"]})
    return carried, missing


def _first_name(full: str) -> str:
    """First name from either 'Maya Rivera' (Canvas) or 'RIVERA, MAYA' (HAC).

    HAC renders names last-first, so the original full.split()[0] keyed HAC data under
    'Rivera,' while Canvas keyed the same kid under 'Maya' -- every student ended up
    split across two snapshot entries, each missing half its data.
    """
    s = " ".join((full or "").split())
    if not s:
        return ""
    if "," in s:
        given = s.split(",", 1)[1].strip()
        s = given or s.split(",", 1)[0].strip()
    tok = s.split()[0].strip(".,")
    return tok.capitalize() if (tok.isupper() or tok.islower()) else tok


def _entry_key(students: dict, first: str) -> str:
    """Reuse an existing snapshot key when one form of the name extends the other.

    Keeps Canvas' 'Alexander' and a HAC banner reading 'Alex' on a single entry.
    """
    fl = first.lower()
    for k in students:
        kl = k.lower()
        if kl == fl or kl.startswith(fl) or fl.startswith(kl):
            return k
    return first


def _wanted(first: str, kids_filter: list[str] | None) -> bool:
    """--kids Alex should select Alexander; match on either name being a prefix of the other."""
    if not kids_filter:
        return True
    fl = first.lower()
    return any(fl.startswith(k.lower()) or k.lower().startswith(fl) for k in kids_filter if k)


def _write_snapshot(s: Settings, snap: dict) -> None:
    """Write 0600 and atomically -- the snapshot holds the kids' grades, and a crash
    mid-write would otherwise leave every tool reading truncated JSON."""
    p = _snapshot_path(s)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(snap, indent=1))
    tmp.chmod(0o600)
    tmp.replace(p)


#: Per source, the keys of a student entry that come from it and travel with it.
_SOURCE_FIELDS = {"canvas": ("canvas", "canvas_id"), "hac": ("hac", "hac_name")}


def _carry_forward(snap: dict, prev: dict | None, kids_filter: list[str] | None) -> None:
    """Fill in, from the previous snapshot, whatever this run did not pull.

    A source that failed (or was skipped) leaves its half of every kid's entry as None, and
    writing that out as the new snapshot meant one HAC outage or lapsed login wiped the
    official grades from every tool until the next successful pull. Keep the last good data
    instead and record under "stale" when it was pulled and why it was not refreshed, so
    status() can say so. Kids excluded by the filter are kept whole for the same reason.
    """
    if not prev:
        return
    for name, pe in prev["students"].items():
        if not _wanted(name, kids_filter) and _entry_key(snap["students"], name) not in snap["students"]:
            snap["students"][name] = pe
    prev_stale = prev.get("stale") or {}
    for src, status in snap["sources"].items():
        if status == "ok":
            continue
        origin = prev_stale.get(src) or (prev if prev.get("sources", {}).get(src) == "ok" else None)
        if origin is None:
            continue  # the previous run had nothing for this source either
        for name, pe in prev["students"].items():
            if pe.get(src) is None:
                continue
            entry = snap["students"].setdefault(_entry_key(snap["students"], name), {"name": pe["name"], "canvas_id": None, "canvas": None, "hac": None})
            if entry.get(src) is not None:
                continue
            for k in _SOURCE_FIELDS[src]:
                if pe.get(k) is not None:
                    entry[k] = pe[k]
        snap["stale"][src] = {"fetched_at": origin["fetched_at"], "fetched_at_epoch": origin["fetched_at_epoch"], "reason": status or "skipped"}
    _carry_courses(snap, prev)


def _carry_courses(snap: dict, prev: dict) -> None:
    """The per-course half of the same rule (#140): Canvas refuses observers on some endpoints
    for some courses, and a 403 on one class left the source "ok" with that class simply gone
    -- its open work vanished from every page until the next good pull, with no warning.
    A class that failed keeps its record from the previous snapshot (grade, assignments,
    staff), noted under the entry's `carried` with the pull it really comes from -- the
    previous snapshot's, or older still if that one was itself carried (per course, or the
    whole source). The source stays "ok" and nothing goes under `stale`: the household's data
    is complete, one class of it is just a pull older, so a refresh with a carried class is
    still a good refresh for the runner's 24-hour rule and `data_as_of` (which reads only
    `stale`). A class with nothing to carry stays under `errors` alone, and is reported as
    missing.
    """
    src_stale = (prev.get("stale") or {}).get("canvas")
    for key, entry in snap["students"].items():
        cv = entry.get("canvas")
        if not cv or not cv.get("errors"):
            continue
        pe = prev["students"].get(_entry_key(prev["students"], key)) or {}
        pcv = pe.get("canvas") or {}
        old = {str(c.get("id")): c for c in pcv.get("courses") or []}
        for err in cv["errors"]:
            cid = str(err["course_id"])
            course = old.get(cid)
            if course is None:
                continue
            origin = (pcv.get("carried") or {}).get(cid) or src_stale or prev
            cv["courses"].append(course)
            cv.setdefault("carried", {})[cid] = {"name": course.get("name") or f"course {cid}", "reason": err["error"],
                                                 "fetched_at": origin["fetched_at"], "fetched_at_epoch": origin["fetched_at_epoch"]}


def collect(s: Settings, include_hac: bool = True, include_canvas: bool = True, kids_filter: list[str] | None = None) -> dict:
    prev = load_snapshot(s)
    snap: dict = {
        "fetched_at": datetime.now().astimezone().isoformat(),
        "fetched_at_epoch": time.time(),
        "sources": {"canvas": None, "hac": None},
        "stale": {},
        "students": {},
    }
    with browser(s) as ctx:
        if include_canvas:
            try:
                ensure_canvas(ctx, s)
                cv = Canvas(ctx, s)
                for kid in cv.observed_students():
                    fn = _first_name(kid["name"])
                    if not _wanted(fn, kids_filter):
                        continue
                    entry = snap["students"].setdefault(_entry_key(snap["students"], fn), {"name": kid["name"], "canvas_id": kid["id"], "canvas": {"courses": []}, "hac": None})
                    for cid in kid["courses"]:
                        # Isolate per-course failures. Canvas refuses observers on some
                        # endpoints for some courses; without this, one 403 discarded every
                        # course for every kid and the whole Canvas source reported "error".
                        try:
                            course = cv.course(cid)
                            course["grade"] = cv.course_grade(cid, kid["id"])
                            course["assignments"] = cv.assignments(cid, kid["id"])
                            course["staff"] = cv.people(cid)
                            entry["canvas"]["courses"].append(course)
                        except Exception as ce:
                            log.warning("Canvas course %s for %s failed: %s", cid, fn, ce)
                            entry["canvas"].setdefault("errors", []).append({"course_id": cid, "error": str(ce)[:200]})
                snap["sources"]["canvas"] = "ok"
            except LoginRequired as e:
                snap["sources"]["canvas"] = f"login_required: {e}"
                log.warning("Canvas: %s", e)
            except Exception as e:  # keep going with HAC
                snap["sources"]["canvas"] = f"error: {e}"
                log.exception("Canvas failed")

        if include_hac:
            try:
                page = ensure_hac(ctx, s)
                hac = HAC(page, s)
                for name in hac.students():
                    fn = _first_name(name)
                    if not _wanted(fn, kids_filter):
                        continue
                    hac.select_student(name)
                    entry = snap["students"].setdefault(_entry_key(snap["students"], fn), {"name": name, "canvas_id": None, "canvas": None, "hac": None})
                    entry["hac_name"] = name
                    entry["hac"] = {"week_view": hac.week_view(), "classes": hac.classwork()}
                snap["sources"]["hac"] = "ok"
            except LoginRequired as e:
                snap["sources"]["hac"] = f"login_required: {e}"
                log.warning("HAC: %s", e)
            except Exception as e:
                snap["sources"]["hac"] = f"error: {e}"
                log.exception("HAC failed")

    _carry_forward(snap, prev, kids_filter)
    for src, m in snap["stale"].items():
        log.warning("%s not refreshed (%s); serving data from %s", src, m["reason"], m["fetched_at"])
    for c in course_faults(snap)[0]:
        log.warning("Canvas course %s (%s) for %s not refreshed (%s); serving data from %s", c["course_id"], c["name"], c["kid"], c["reason"], c["fetched_at"])
    _write_snapshot(s, snap)
    return snap

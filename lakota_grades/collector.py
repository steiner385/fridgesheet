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

log = logging.getLogger("lakota.collector")


def _snapshot_path(s: Settings) -> Path:
    return s.cache_dir / "snapshot.json"


def load_snapshot(s: Settings) -> dict | None:
    p = _snapshot_path(s)
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def snapshot_is_fresh(s: Settings, snap: dict | None) -> bool:
    return bool(snap) and (time.time() - snap.get("fetched_at_epoch", 0)) < s.cache_ttl_minutes * 60


def _first_name(full: str) -> str:
    return full.split()[0]


def collect(s: Settings, include_hac: bool = True, include_canvas: bool = True, kids_filter: list[str] | None = None) -> dict:
    snap: dict = {
        "fetched_at": datetime.now().astimezone().isoformat(),
        "fetched_at_epoch": time.time(),
        "sources": {"canvas": None, "hac": None},
        "students": {},
    }
    with browser(s) as ctx:
        if include_canvas:
            try:
                ensure_canvas(ctx, s)
                cv = Canvas(ctx, s)
                for kid in cv.observed_students():
                    fn = _first_name(kid["name"])
                    if kids_filter and fn.lower() not in [k.lower() for k in kids_filter]:
                        continue
                    entry = snap["students"].setdefault(fn, {"name": kid["name"], "canvas_id": kid["id"], "canvas": {"courses": []}, "hac": None})
                    for cid in kid["courses"]:
                        course = cv.course(cid)
                        course["grade"] = cv.course_grade(cid, kid["id"])
                        course["assignments"] = cv.assignments(cid, kid["id"])
                        course["staff"] = cv.people(cid)
                        entry["canvas"]["courses"].append(course)
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
                    if kids_filter and fn.lower() not in [k.lower() for k in kids_filter]:
                        continue
                    hac.select_student(name)
                    entry = snap["students"].setdefault(fn, {"name": name, "canvas_id": None, "canvas": None, "hac": None})
                    entry["hac"] = {"week_view": hac.week_view(), "classes": hac.classwork()}
                snap["sources"]["hac"] = "ok"
            except LoginRequired as e:
                snap["sources"]["hac"] = f"login_required: {e}"
                log.warning("HAC: %s", e)
            except Exception as e:
                snap["sources"]["hac"] = f"error: {e}"
                log.exception("HAC failed")

    _snapshot_path(s).write_text(json.dumps(snap, indent=1))
    return snap

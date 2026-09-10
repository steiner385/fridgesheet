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
    """First name from either 'Douglas Stein' (Canvas) or 'STEIN, DOUGLAS' (HAC).

    HAC renders names last-first, so the original full.split()[0] keyed HAC data under
    'Stein,' while Canvas keyed the same kid under 'Douglas' -- every student ended up
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

    Keeps Canvas' 'Douglas' and a HAC banner reading 'Doug' on a single entry.
    """
    fl = first.lower()
    for k in students:
        kl = k.lower()
        if kl == fl or kl.startswith(fl) or fl.startswith(kl):
            return k
    return first


def _wanted(first: str, kids_filter: list[str] | None) -> bool:
    """--kids Doug should select Douglas; match on either name being a prefix of the other."""
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
                    if not _wanted(fn, kids_filter):
                        continue
                    entry = snap["students"].setdefault(_entry_key(snap["students"], fn), {"name": kid["name"], "canvas_id": kid["id"], "canvas": {"courses": []}, "hac": None})
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

    _write_snapshot(s, snap)
    return snap

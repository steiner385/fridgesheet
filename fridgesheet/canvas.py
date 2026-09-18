"""Canvas REST API access using the browser session's cookies (observer account)."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from playwright.sync_api import BrowserContext

from .config import Settings

log = logging.getLogger("fridgesheet.canvas")


_NEXT_LINK_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


def _strip(text: str):
    return json.loads(text[len("while(1);"):] if text.startswith("while(1);") else text)


def _qs(params: dict) -> str | None:
    """Encode params, expanding list values into repeated keys.

    Canvas array params look like include[]=a&include[]=b. Playwright's `params` only accepts
    str/float/bool values, so a list silently produced a broken query; we hand it a query
    string instead.
    """
    pairs = []
    for k, v in params.items():
        if v is None:
            continue
        for item in (v if isinstance(v, (list, tuple)) else [v]):
            pairs.append((k, item if isinstance(item, str) else json.dumps(item) if isinstance(item, bool) else str(item)))
    return urlencode(pairs) if pairs else None


def _next_link(link_header: str | None) -> str | None:
    m = _NEXT_LINK_RE.search(link_header or "")
    return m.group(1) if m else None


class Canvas:
    def __init__(self, ctx: BrowserContext, settings: Settings):
        self.ctx = ctx
        self.s = settings
        self.tz = ZoneInfo(settings.timezone)

    def _request(self, url: str, query: str | None):
        r = self.ctx.request.get(url, params=query, headers={"Accept": "application/json"})
        if r.status != 200:
            raise RuntimeError(f"Canvas GET {url} -> HTTP {r.status}: {r.text()[:200]}")
        return r

    def get(self, path: str, **params):
        return _strip(self._request(self.s.canvas_base + path, _qs(params)).text())

    def get_all(self, path: str, **params):
        """Follow Canvas' Link-header pagination (rel="next") rather than guessing page numbers."""
        url, query, out = self.s.canvas_base + path, _qs({**params, "per_page": 100}), []
        for _ in range(100):  # backstop against a server that always advertises a next page
            r = self._request(url, query)
            chunk = _strip(r.text())
            if not isinstance(chunk, list):
                raise RuntimeError(f"Canvas GET {path} returned {type(chunk).__name__}, expected a list")
            out.extend(chunk)
            nxt = _next_link(r.headers.get("link"))
            if not nxt or nxt == url:
                return out
            url, query = nxt, None  # the next link already carries the query
        return out

    def local(self, iso: str | None) -> str | None:
        if not iso:
            return None
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(self.tz).isoformat()

    # ---- discovery -------------------------------------------------------
    def observed_students(self) -> list[dict]:
        """Kids this observer account can see, with their active course enrollments."""
        enr = self.get_all("/api/v1/users/self/enrollments", **{"include[]": "observed_users", "state[]": "active"})
        kids: dict[int, dict] = {}
        for e in enr:
            if e.get("type") != "ObserverEnrollment" or not e.get("observed_user"):
                continue
            ou = e["observed_user"]
            k = kids.setdefault(ou["id"], {"id": ou["id"], "name": ou["name"], "short_name": ou.get("short_name"), "courses": []})
            k["courses"].append(e["course_id"])
        for k in kids.values():
            k["courses"] = sorted(set(k["courses"]))
        return sorted(kids.values(), key=lambda k: k["name"])

    def course(self, cid: int) -> dict:
        c = self.get(f"/api/v1/courses/{cid}")
        return {"id": c["id"], "name": c["name"], "course_code": c.get("course_code")}

    # ---- per-course data -------------------------------------------------
    def course_grade(self, cid: int, student_id: int) -> dict:
        enr = self.get_all(f"/api/v1/courses/{cid}/enrollments", user_id=student_id, **{"type[]": "StudentEnrollment"})
        active = [e for e in enr if e.get("enrollment_state") == "active"] or enr
        g = (active[0].get("grades") if active else None) or {}
        return {
            "current_score": g.get("current_score"),
            "final_score": g.get("final_score"),
            "current_grade": g.get("current_grade"),
            "hidden": g.get("current_score") is None and g.get("final_score") is None,
        }

    def assignment_groups(self, cid: int) -> dict[int, dict]:
        return {g["id"]: {"name": g["name"], "weight": g.get("group_weight")} for g in self.get_all(f"/api/v1/courses/{cid}/assignment_groups")}

    def assignments(self, cid: int, student_id: int) -> list[dict]:
        groups = self.assignment_groups(cid)
        subs = {s["assignment_id"]: s for s in self.get_all(f"/api/v1/courses/{cid}/students/submissions", **{"student_ids[]": student_id})}
        rows = []
        for a in self.get_all(f"/api/v1/courses/{cid}/assignments"):
            s = subs.get(a["id"], {})
            rows.append({
                "id": a["id"],
                "name": a["name"],
                "due_at": self.local(a.get("due_at")),
                # Canvas has no "assigned on" field. unlock_at ("Available from") is the
                # closest when a teacher sets it; created_at is when the item appeared
                # (which for a course copied from last year is the copy date).
                "unlock_at": self.local(a.get("unlock_at")),
                "created_at": self.local(a.get("created_at")),
                "points_possible": a.get("points_possible"),
                "submission_types": a.get("submission_types") or [],
                "group": groups.get(a.get("assignment_group_id"), {}).get("name"),
                "group_weight": groups.get(a.get("assignment_group_id"), {}).get("weight"),
                "published": a.get("published"),
                "score": s.get("score"),
                "grade": s.get("grade"),
                "state": s.get("workflow_state"),
                "late": bool(s.get("late")),
                "missing": bool(s.get("missing")),
                "excused": bool(s.get("excused")),
                "submitted_at": self.local(s.get("submitted_at")),
                "seconds_late": s.get("seconds_late"),
            })
        rows.sort(key=lambda r: (r["due_at"] or "9999", r["name"]))
        return rows

    def people(self, cid: int) -> list[dict]:
        """Teachers and TAs for a course (for the contacts table).

        Observer accounts are refused /courses/:id/users with a 403 (same restriction the
        README notes for /users/:id/courses), so fall back to the course object's `teachers`
        include, which observers may read. Never raises: staff contacts are a nicety and must
        not cost us the entire Canvas pull.
        """
        try:
            out = []
            for u in self.get_all(f"/api/v1/courses/{cid}/users", **{"enrollment_type[]": ["teacher", "ta"], "include[]": ["enrollments", "email"]}):
                roles = sorted({e.get("type", "") for e in u.get("enrollments", [])})
                out.append({"name": u.get("name"), "email": u.get("email"), "roles": roles})
            return out
        except RuntimeError as e:
            log.info("course %s: /users unavailable (%s); using the course teachers include", cid, str(e)[-60:])
        try:
            c = self.get(f"/api/v1/courses/{cid}", **{"include[]": "teachers"})
            return [
                {"name": t.get("display_name") or t.get("name"), "email": None, "roles": ["TeacherEnrollment"]}
                for t in (c.get("teachers") or [])
            ]
        except RuntimeError as e:
            log.warning("course %s: no staff list available (%s)", cid, str(e)[-60:])
            return []

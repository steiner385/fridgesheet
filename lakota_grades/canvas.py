"""Canvas REST API access using the browser session's cookies (observer account)."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.sync_api import BrowserContext

from .config import Settings


def _strip(text: str):
    return json.loads(text[len("while(1);"):] if text.startswith("while(1);") else text)


class Canvas:
    def __init__(self, ctx: BrowserContext, settings: Settings):
        self.ctx = ctx
        self.s = settings
        self.tz = ZoneInfo(settings.timezone)

    def get(self, path: str, **params):
        url = self.s.canvas_base + path
        r = self.ctx.request.get(url, params=params or None, headers={"Accept": "application/json"})
        if r.status != 200:
            raise RuntimeError(f"Canvas GET {path} -> HTTP {r.status}: {r.text()[:200]}")
        return _strip(r.text())

    def get_all(self, path: str, **params):
        out, page = [], 1
        while True:
            chunk = self.get(path, per_page=100, page=page, **params)
            out.extend(chunk)
            if len(chunk) < 100:
                return out
            page += 1

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
        enr = self.get(f"/api/v1/courses/{cid}/enrollments", user_id=student_id, **{"type[]": "StudentEnrollment"})
        g = (enr[0].get("grades") if enr else None) or {}
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
        """Teachers and TAs for a course (for the contacts table)."""
        out = []
        for u in self.get_all(f"/api/v1/courses/{cid}/users", **{"enrollment_type[]": ["teacher", "ta"], "include[]": "enrollments"}):
            roles = sorted({e.get("type", "") for e in u.get("enrollments", [])})
            out.append({"name": u.get("name"), "email": u.get("email"), "roles": roles})
        return out

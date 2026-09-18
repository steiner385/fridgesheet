"""Canvas assignment rows carry the dates a sheet needs to say when work was assigned.
Canvas has no "assigned on" field: `unlock_at` ("Available from") is the closest when a
teacher sets it, and `created_at` is the fallback."""
from __future__ import annotations

import json

from fridgesheet.canvas import Canvas
from fridgesheet.config import Settings


class _Resp:
    def __init__(self, payload):
        self.status = 200
        self.headers = {}
        self._payload = payload

    def text(self):
        return "while(1);" + json.dumps(self._payload)


class _Request:
    """Answers the three endpoints assignments() hits, by URL substring."""

    def __init__(self):
        self.routes = {
            "/assignment_groups": [{"id": 7, "name": "Homework", "group_weight": 10}],
            "/students/submissions": [{"assignment_id": 1, "score": None, "workflow_state": "unsubmitted"}],
            "/assignments": [{
                "id": 1, "name": "WS 1", "due_at": "2026-09-10T03:59:00Z", "unlock_at": "2026-09-03T13:00:00Z",
                "created_at": "2026-08-18T15:22:00Z", "points_possible": 5, "submission_types": ["online_upload"],
                "assignment_group_id": 7, "published": True,
            }],
        }

    def get(self, url, params=None, headers=None):
        for key, payload in self.routes.items():
            if url.endswith(key):
                return _Resp(payload)
        raise AssertionError(f"unexpected URL {url}")


class _Ctx:
    request = _Request()


def test_assignment_rows_include_unlock_and_created_in_local_time():
    cv = Canvas(_Ctx(), Settings())
    (row,) = cv.assignments(1, 99)
    assert row["unlock_at"] == "2026-09-03T09:00:00-04:00"
    assert row["created_at"] == "2026-08-18T11:22:00-04:00"
    assert row["due_at"] == "2026-09-09T23:59:00-04:00"

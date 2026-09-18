"""missing_work and upcoming must report exactly what the printed sheet shows: both are
views over open_items(), so a status on paper is what Claude would say if asked."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

pytest.importorskip("mcp")

from fridgesheet import collector, server  # noqa: E402


def _iso(days: float) -> str:
    return (datetime.now().astimezone() + timedelta(days=days)).replace(hour=23, minute=59, second=0, microsecond=0).isoformat()


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    snap = {
        "fetched_at": _iso(0), "fetched_at_epoch": 10**12, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {"Alex": {
            "name": "Alex Example",
            "canvas": {"courses": [{"id": 5, "name": "Honors Biology S1-2027-Nance", "assignments": [
                {"id": 1, "name": "WS 1", "due_at": _iso(-2), "unlock_at": None, "created_at": _iso(-9), "points_possible": 10.0,
                 "submission_types": ["online_upload"], "group": "Homework", "published": True, "score": None, "grade": None,
                 "state": "unsubmitted", "late": False, "missing": True, "excused": False},
                {"id": 2, "name": "Lab 2", "due_at": _iso(3), "unlock_at": None, "created_at": _iso(-1), "points_possible": 20.0,
                 "submission_types": ["online_upload"], "group": "Labs", "published": True, "score": None, "grade": None,
                 "state": "unsubmitted", "late": False, "missing": False, "excused": False},
            ]}]},
            "hac": {"classes": []},
        }},
    }
    monkeypatch.setattr(collector, "load_snapshot", lambda s: snap)
    monkeypatch.setattr(collector, "snapshot_is_fresh", lambda s, snap: True)
    monkeypatch.setattr(server._settings, "home", tmp_path)
    return snap


def test_missing_work_uses_shared_statuses(snapshot):
    out = server.missing_work("Al")
    assert [i["status"] for i in out["items"]] == ["MISSING"]
    assert out["items"][0]["late_until"] and out["items"][0]["course"] == "Honors Biology"
    assert out["points_at_stake"] == 10.0
    assert out["not_shown"] == {"count": 0, "points": 0}


def test_upcoming_uses_shared_statuses(snapshot):
    out = server.upcoming("Al", days=7)
    assert [(i["name"], i["status"]) for i in out["items"]] == [("Lab 2", "DUE " + (datetime.now() + timedelta(days=3)).strftime("%a").upper())]

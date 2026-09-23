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


from fridgesheet import sources  # noqa: E402


@pytest.fixture
def graded(monkeypatch, tmp_path):
    snap = {
        "fetched_at": _iso(0), "fetched_at_epoch": 10**12, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {"Alex": {
            "name": "Alex Example",
            "canvas": {"courses": [{"id": 5, "name": "Honors Biology S1-2027-Nance", "assignments": [], "staff": [],
                                    "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False}}]},
            "hac": {"week_view": [], "classes": [
                {"name": "Honors Biology - 3", "marking_period_avg": 88.0, "last_updated": "9/11/2026", "categories": [], "assignments": []},
                {"name": "Hawk Time", "marking_period_avg": 100.0, "last_updated": None, "categories": [], "assignments": []},
            ]},
        }},
    }
    monkeypatch.setattr(collector, "load_snapshot", lambda s: snap)
    monkeypatch.setattr(collector, "snapshot_is_fresh", lambda s, snap: True)
    return snap


def test_grades_official_follows_the_grades_source(graded, monkeypatch):
    monkeypatch.setattr(server._settings, "sources", sources.DEFAULT)
    out = {c["course"]: c for c in server.grades("Alex")["classes"]}
    bio = out["Honors Biology S1-2027-Nance"]
    assert (bio["official"], bio["official_source"]) == (88.0, "hac")
    assert (bio["hac_official"], bio["canvas_current"]) == (88.0, 91.2)          # both still there
    monkeypatch.setattr(server._settings, "sources", sources.DEFAULT.with_default("canvas", "canvas"))
    out = {c["course"]: c for c in server.grades("Alex")["classes"]}
    assert (out["Honors Biology S1-2027-Nance"]["official"], out["Honors Biology S1-2027-Nance"]["official_source"]) == (91.2, "canvas")
    assert (out["Hawk Time"]["official"], out["Hawk Time"]["official_source"]) == (100.0, "hac")   # HAC-only fills the gap

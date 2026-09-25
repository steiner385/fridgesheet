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
    monkeypatch.setattr(server._settings(), "home", tmp_path)
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
    monkeypatch.setattr(server._settings(), "sources", sources.DEFAULT)
    out = {c["course"]: c for c in server.grades("Alex")["classes"]}
    bio = out["Honors Biology S1-2027-Nance"]
    assert (bio["official"], bio["official_source"]) == (88.0, "hac")
    assert (bio["hac_official"], bio["canvas_current"]) == (88.0, 91.2)          # both still there
    monkeypatch.setattr(server._settings(), "sources", sources.DEFAULT.with_default("canvas", "canvas"))
    out = {c["course"]: c for c in server.grades("Alex")["classes"]}
    assert (out["Honors Biology S1-2027-Nance"]["official"], out["Honors Biology S1-2027-Nance"]["official_source"]) == (91.2, "canvas")
    assert (out["Hawk Time"]["official"], out["Hawk Time"]["official_source"]) == (100.0, "hac")   # HAC-only fills the gap


from fridgesheet import runner  # noqa: E402


@pytest.fixture
def stale(snapshot, monkeypatch):
    monkeypatch.setattr(collector, "snapshot_is_fresh", lambda s, snap: False)
    return snapshot


def test_a_read_serves_the_snapshot_while_a_run_holds_the_lock(stale, monkeypatch, tmp_path):
    """A stale snapshot used to mean `collector.collect` from inside a read, with no lock: a
    second Chromium over the profile a scheduled print was using (#151). While a run holds
    run.lock, a read answers from what is on disk and `status` says why it is older."""
    (tmp_path / runner.LOCK_NAME).write_text("1 deadbeef")
    monkeypatch.setattr(collector, "collect", lambda *a, **k: pytest.fail("no Chromium while a run holds the lock"))
    assert [s["student"] for s in server.list_students()] == ["Alex"]
    assert server.status()["run_in_progress"] is True


def test_an_automatic_refresh_takes_the_lock(stale, monkeypatch, tmp_path):
    seen = {}

    def collect(s, **kw):
        seen["locked"] = (tmp_path / runner.LOCK_NAME).is_file()
        return stale

    monkeypatch.setattr(collector, "collect", collect)
    server.list_students()
    assert seen["locked"] is True and not (tmp_path / runner.LOCK_NAME).exists()
    assert server.status()["run_in_progress"] is False


def test_a_read_with_no_snapshot_and_a_run_in_progress_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(collector, "load_snapshot", lambda s: None)
    monkeypatch.setattr(server._settings(), "home", tmp_path)
    (tmp_path / runner.LOCK_NAME).write_text("1 deadbeef")
    monkeypatch.setattr(collector, "collect", lambda *a, **k: pytest.fail("no Chromium while a run holds the lock"))
    with pytest.raises(RuntimeError, match="run.lock"):
        server.list_students()


def test_refresh_reports_a_run_in_progress_instead_of_a_second_chromium(snapshot, monkeypatch, tmp_path):
    (tmp_path / runner.LOCK_NAME).write_text("1 deadbeef")
    monkeypatch.setattr(collector, "LOCK_WAIT_SECONDS", 0)
    monkeypatch.setattr(collector, "collect", lambda *a, **k: pytest.fail("no Chromium while a run holds the lock"))
    out = server.refresh()
    assert out["run_in_progress"] is True and "run.lock" in out["refresh"]
    assert out["students"] == ["Alex"]                              # status()-style, from the snapshot on disk


def test_refresh_takes_the_lock(snapshot, monkeypatch, tmp_path):
    seen = {}

    def collect(s, **kw):
        seen["locked"] = (tmp_path / runner.LOCK_NAME).is_file()
        return snapshot

    monkeypatch.setattr(collector, "collect", collect)
    out = server.refresh(hac=False)
    assert seen["locked"] is True and "refresh" not in out and not (tmp_path / runner.LOCK_NAME).exists()


def _days_ago(n: int) -> str:
    return (datetime.now() - timedelta(days=n)).strftime("%m/%d/%Y")


@pytest.fixture
def hac_only(monkeypatch, tmp_path):
    """A kid HAC knows and Canvas does not: her name is HAC's "RIVERA, MAYA", her key the
    first name the collector derives from it."""
    snap = {
        "fetched_at": _iso(0), "fetched_at_epoch": 10**12, "sources": {"canvas": "ok", "hac": "ok"}, "stale": {},
        "students": {"Maya": {
            "name": "RIVERA, MAYA", "hac_name": "RIVERA, MAYA", "canvas_id": None,
            "canvas": {"courses": [{"id": 9, "name": "Honors Biology S1-2027-Nance", "assignments": [], "staff": [],
                                    "grade": {"current_score": 91.2, "final_score": None, "current_grade": "A-", "hidden": False}}]},
            "hac": {"week_view": [], "classes": [
                {"name": "Honors Biology - 3", "marking_period_avg": 88.0, "last_updated": None, "categories": [], "assignments": [
                    {"name": "Lab Safety Contract", "assigned": _days_ago(8), "due": _days_ago(5), "score": None, "score_raw": "",
                     "points": 5.0, "category": "Labs"}]}]},
        }},
    }
    monkeypatch.setattr(collector, "load_snapshot", lambda s: snap)
    monkeypatch.setattr(collector, "snapshot_is_fresh", lambda s, snap: True)
    monkeypatch.setattr(server._settings(), "home", tmp_path)
    monkeypatch.setattr(server._settings(), "sources", sources.DEFAULT)
    monkeypatch.setattr(server._settings(), "nicknames", {})
    return snap


def test_late_rules_resolve_by_the_students_key_not_the_first_word_of_her_name(hac_only, tmp_path):
    """HAC writes "RIVERA, MAYA"; `name.split()[0]` is "RIVERA," and a rule for Maya never
    matched here, while the sheet and the web resolve by her key (#151, after #161)."""
    (tmp_path / "late-rules.toml").write_text('[[rule]]\nkid = "Maya"\nlate_days = 0\n', encoding="utf-8")
    out = server.missing_work("Maya")
    assert (out["count"], out["not_shown"]["count"]) == (0, 1)      # her rule: no late work, so past its deadline
    (tmp_path / "late-rules.toml").write_text('[[rule]]\nkid = "Maya"\nlate_days = 30\n', encoding="utf-8")
    assert server.missing_work("Maya")["count"] == 1


def test_source_rules_resolve_by_the_students_key(hac_only, monkeypatch):
    prefs = sources.DEFAULT.with_default("canvas", "canvas").with_rule("Maya", "Honors Biology", None, "hac")
    monkeypatch.setattr(server._settings(), "sources", prefs)
    bio = {c["course"]: c for c in server.grades("Maya")["classes"]}["Honors Biology S1-2027-Nance"]
    assert (bio["official"], bio["official_source"]) == (88.0, "hac")


def test_a_student_is_found_by_key_nickname_or_a_start_of_either(hac_only, monkeypatch):
    monkeypatch.setattr(server._settings(), "nicknames", {"Maya": "Mimi"})
    for asked in ("Maya", "maya", "Ma", "Mimi", "mi"):
        assert server.hac_classwork(asked)["student"] == "RIVERA, MAYA", asked
    with pytest.raises(ValueError, match="Maya"):
        server.hac_classwork("Rivera")

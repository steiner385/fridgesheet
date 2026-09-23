"""A refresh in which one source fails must not throw away the last good data for that
source. Before this, a HAC outage (or a lapsed login) produced a snapshot with every
kid's `hac` set to None, and every tool then reported no official grades until the
next successful pull."""
from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from fridgesheet import collector
from fridgesheet.config import Settings
from fridgesheet.session import LoginRequired


class FakeCanvas:
    def __init__(self, ctx, s):
        pass

    def observed_students(self):
        return [
            {"name": "Alex Example", "id": 1, "courses": [10]},
            {"name": "Sam Example", "id": 2, "courses": [20]},
        ]

    def course(self, cid):
        return {"id": cid, "name": f"Course {cid}"}

    def course_grade(self, cid, uid):
        return {"current_score": 90, "final_score": 88, "hidden": False}

    def assignments(self, cid, uid):
        return []

    def people(self, cid):
        return []


class FakeHAC:
    def __init__(self, page, s):
        pass

    def students(self):
        return ["RIVERA, ALEX", "RIVERA, SAM"]

    def select_student(self, name):
        pass

    def week_view(self):
        return [{"class": "Course 10 - 3", "current_average": 91}]

    def classwork(self):
        return [{"name": "Course 10 - 3", "assignments": [], "marking_period_avg": 91}]


@pytest.fixture
def settings(tmp_path):
    s = Settings(home=tmp_path)
    s.cache_dir.mkdir(parents=True)
    return s


@pytest.fixture
def fake_sites(monkeypatch):
    """Stub the browser boundary. Each source's `fail` can be set to an exception to raise."""
    state = {"canvas_fail": None, "hac_fail": None}

    @contextmanager
    def fake_browser(s, **kw):
        yield object()

    def ensure_canvas(ctx, s):
        if state["canvas_fail"]:
            raise state["canvas_fail"]

    def ensure_hac(ctx, s):
        if state["hac_fail"]:
            raise state["hac_fail"]
        return object()

    monkeypatch.setattr(collector, "browser", fake_browser)
    monkeypatch.setattr(collector, "ensure_canvas", ensure_canvas)
    monkeypatch.setattr(collector, "ensure_hac", ensure_hac)
    monkeypatch.setattr(collector, "Canvas", FakeCanvas)
    monkeypatch.setattr(collector, "HAC", FakeHAC)
    return state


def _seed(settings, fake_sites) -> dict:
    """A previous, fully successful snapshot on disk."""
    first = collector.collect(settings)
    assert first["sources"] == {"canvas": "ok", "hac": "ok"}
    assert first["students"]["Alex"]["hac"]["classes"][0]["marking_period_avg"] == 91
    return first


def test_successful_pull_has_no_stale_sources(settings, fake_sites):
    snap = _seed(settings, fake_sites)
    assert snap["stale"] == {}


def test_failed_source_keeps_previous_data(settings, fake_sites):
    prev = _seed(settings, fake_sites)
    fake_sites["hac_fail"] = RuntimeError("HAC is down")

    snap = collector.collect(settings)

    assert snap["sources"]["canvas"] == "ok"
    assert snap["sources"]["hac"] == "error: HAC is down"
    for kid in ("Alex", "Sam"):
        assert snap["students"][kid]["hac"] == prev["students"][kid]["hac"]
        assert snap["students"][kid]["hac_name"] == prev["students"][kid]["hac_name"]
    assert snap["students"]["Alex"]["canvas"]["courses"]  # the good source was still refreshed


def test_failed_source_is_marked_stale_with_its_last_good_time(settings, fake_sites):
    prev = _seed(settings, fake_sites)
    fake_sites["hac_fail"] = LoginRequired("session expired")

    snap = collector.collect(settings)

    assert snap["stale"] == {
        "hac": {
            "fetched_at": prev["fetched_at"],
            "fetched_at_epoch": prev["fetched_at_epoch"],
            "reason": "login_required: session expired",
        }
    }
    assert "canvas" not in snap["stale"]


def test_carried_data_is_what_gets_written_to_disk(settings, fake_sites):
    prev = _seed(settings, fake_sites)
    fake_sites["hac_fail"] = RuntimeError("HAC is down")

    collector.collect(settings)

    on_disk = json.loads((settings.cache_dir / "snapshot.json").read_text())
    assert on_disk["students"]["Alex"]["hac"] == prev["students"]["Alex"]["hac"]
    assert on_disk["stale"]["hac"]["fetched_at"] == prev["fetched_at"]


def test_repeated_failure_keeps_the_original_good_time(settings, fake_sites):
    prev = _seed(settings, fake_sites)
    fake_sites["hac_fail"] = RuntimeError("still down")
    collector.collect(settings)

    snap = collector.collect(settings)  # second consecutive failure

    assert snap["stale"]["hac"]["fetched_at"] == prev["fetched_at"]
    assert snap["students"]["Alex"]["hac"] == prev["students"]["Alex"]["hac"]


def test_failure_with_no_previous_snapshot_leaves_source_empty(settings, fake_sites):
    fake_sites["hac_fail"] = RuntimeError("HAC is down")

    snap = collector.collect(settings)

    assert snap["students"]["Alex"]["hac"] is None
    assert snap["stale"] == {}
    assert snap["sources"]["hac"] == "error: HAC is down"


def test_failure_after_a_previous_failure_with_nothing_to_carry(settings, fake_sites):
    fake_sites["hac_fail"] = RuntimeError("HAC is down")
    collector.collect(settings)

    snap = collector.collect(settings)

    assert snap["students"]["Alex"]["hac"] is None
    assert snap["stale"] == {}


def test_recovery_replaces_stale_data_and_clears_the_marker(settings, fake_sites):
    _seed(settings, fake_sites)
    fake_sites["hac_fail"] = RuntimeError("HAC is down")
    collector.collect(settings)
    fake_sites["hac_fail"] = None

    snap = collector.collect(settings)

    assert snap["sources"]["hac"] == "ok"
    assert snap["stale"] == {}
    assert snap["students"]["Alex"]["hac"]["classes"][0]["marking_period_avg"] == 91


def test_skipped_source_keeps_previous_data_and_is_marked_stale(settings, fake_sites):
    prev = _seed(settings, fake_sites)

    snap = collector.collect(settings, include_hac=False)

    assert snap["sources"]["hac"] is None
    assert snap["students"]["Alex"]["hac"] == prev["students"]["Alex"]["hac"]
    assert snap["stale"]["hac"] == {
        "fetched_at": prev["fetched_at"],
        "fetched_at_epoch": prev["fetched_at_epoch"],
        "reason": "skipped",
    }


def test_kid_filter_keeps_the_other_kids(settings, fake_sites):
    prev = _seed(settings, fake_sites)

    snap = collector.collect(settings, kids_filter=["Al"])

    assert set(snap["students"]) == {"Alex", "Sam"}
    assert snap["students"]["Sam"] == prev["students"]["Sam"]


def test_both_sources_failing_keeps_every_kid(settings, fake_sites):
    prev = _seed(settings, fake_sites)
    fake_sites["canvas_fail"] = RuntimeError("canvas down")
    fake_sites["hac_fail"] = RuntimeError("hac down")

    snap = collector.collect(settings)

    assert snap["students"] == prev["students"]
    assert set(snap["stale"]) == {"canvas", "hac"}


def test_summary_reports_stale_sources(settings, fake_sites):
    prev = _seed(settings, fake_sites)
    fake_sites["hac_fail"] = RuntimeError("HAC is down")
    snap = collector.collect(settings)

    out = collector.summary(settings, snap)

    assert out["sources"] == {"canvas": "ok", "hac": "error: HAC is down"}
    assert out["stale"] == {"hac": {"fetched_at": prev["fetched_at"], "reason": "error: HAC is down"}}
    assert out["students"] == ["Alex", "Sam"]
    assert out["fresh"] is True


def test_summary_of_an_old_snapshot_without_stale_key(settings):
    legacy = {"fetched_at": "2026-09-01T06:00:00-04:00", "fetched_at_epoch": 0, "sources": {"canvas": "ok", "hac": "ok"}, "students": {"Alex": {}}}
    out = collector.summary(settings, legacy)
    assert out["stale"] == {}
    assert out["fresh"] is False

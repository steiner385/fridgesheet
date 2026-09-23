"""packaging/windows/restamp_snapshot.py re-stamps the smoke fixture to "now" on its way into
the throwaway smoke home, so its committed timestamp never goes stale (runner.py's
MAX_DATA_AGE_HOURS ceiling on --no-refresh -- see restamp_snapshot.py's own docstring for why
refreshing the committed value instead would just reintroduce the same 24-hour bomb).

These tests prove the thing runner.py actually checks (`data_as_of`), not just that the
fields we wrote look right -- re-reading the fields we just set would prove nothing about
whether runner.py agrees.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("reportlab")

from fridgesheet import runner  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WIN = ROOT / "packaging" / "windows"
FIXTURE = WIN / "fixture-snapshot.json"

# restamp_snapshot.py lives in packaging/windows, not the fridgesheet package, so load it
# directly by path rather than trying to make packaging/windows importable as a package.
_spec = importlib.util.spec_from_file_location("restamp_snapshot", WIN / "restamp_snapshot.py")
restamp_snapshot = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = restamp_snapshot
_spec.loader.exec_module(restamp_snapshot)


def _minutes_from_now(dt: datetime) -> float:
    return abs((datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()) / 60


def test_restamp_produces_a_snapshot_current_by_runners_own_check():
    snap = restamp_snapshot.restamp(json.loads(FIXTURE.read_text(encoding="utf-8")))
    # Proven through runner.data_as_of itself -- the function runner.py actually calls to
    # decide staleness -- not by re-reading fetched_at_epoch, which would only prove the
    # helper wrote back what it was told to, not that the app agrees the data is fresh.
    assert _minutes_from_now(runner.data_as_of(snap)) < 1


def test_restamp_moves_stale_entries_too_not_just_the_top_level():
    # runner.data_as_of takes the *minimum* of the top-level fetched_at_epoch and every
    # stale[*].fetched_at_epoch (runner.py:176-181). A helper that only bumped the top level
    # would leave data_as_of computing an old timestamp from a carried-forward source and
    # silently fail to fix anything for a snapshot like this one.
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    snap = {
        "fetched_at": old.isoformat(),
        "fetched_at_epoch": old.timestamp(),
        "sources": {"canvas": "ok", "hac": "stale"},
        "stale": {"hac": {"fetched_at": old.isoformat(), "fetched_at_epoch": old.timestamp(), "reason": "skipped"}},
        "students": {},
    }
    out = restamp_snapshot.restamp(snap)
    assert _minutes_from_now(runner.data_as_of(out)) < 1
    # the reason -- everything but the timestamps -- must survive untouched
    assert out["stale"]["hac"]["reason"] == "skipped"


def test_restamp_leaves_students_and_sources_untouched():
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out = restamp_snapshot.restamp(original)
    assert out["students"] == original["students"]
    assert out["sources"] == original["sources"]


def test_restamp_file_round_trips_the_committed_fixture(tmp_path):
    # Guards against the fixture's shape drifting away from what the helper expects -- e.g. a
    # future edit renaming "stale" or "fetched_at_epoch" would break restamping silently
    # unless something here actually runs it against the real committed file.
    dst = tmp_path / "snapshot.json"
    restamp_snapshot.restamp_file(FIXTURE, dst)
    out = json.loads(dst.read_text(encoding="utf-8"))
    assert _minutes_from_now(runner.data_as_of(out)) < 1
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert out["students"] == original["students"]
    # the committed file itself must never be modified by a restamp
    assert original["fetched_at_epoch"] == 1789387200

"""Must finish: the Open work rows, sectioned for tonight (spec 2026-09-27 §4)."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fridgesheet import late_rules
from fridgesheet.web.stores import items, students
from tests.web_fixtures import NOW, TZ, _a, _h, seed, snapshot

RULES = late_rules.LateRules(late_rules.Rule(), [], [])


def _work(tmp_path, key="Alex", snap=None, now=NOW):
    conn = seed(tmp_path, snap)
    s = students.by_key(conn, key)
    w = items.open_work(conn, s, now=now, rules=RULES, days_ahead=14, overdue_days=14)
    conn.close()
    return w


def _names(views):
    return [v.name for v in views]


def test_the_fixture_lands_in_the_documented_sections(tmp_path):
    mf = items.must_finish(_work(tmp_path), NOW.date())
    assert _names(mf.tonight) == ["Vocabulary"]                 # due 9/15 23:59, read at 9/15 14:00
    assert _names(mf.tomorrow) == ["Worksheet 3"]               # due 9/16
    assert _names(mf.later) == ["Reading log"]                  # due 9/20, within 14 days
    assert _names(mf.overdue) == []                             # Homework 4 is past its window: not fixable
    assert set(_names(mf.paper)) == {"Lab notebook", "Participation"}   # paper, no grade; HAC-only, no grade
    assert mf.waiting == []
    assert "Essay draft" not in _names(mf.red + mf.paper + mf.waiting + mf.later)   # submitted on time: not open
    assert "Quiz 1" not in [v.name for v in mf.red]                                # HAC's 28/30 settles it


def test_sam_has_two_overdue_rows_a_missing_and_a_zero(tmp_path):
    mf = items.must_finish(_work(tmp_path, "Sam"), NOW.date())
    assert set(_names(mf.overdue)) == {"Cell diagram", "Safety quiz"}
    assert mf.red == mf.overdue and mf.paper == [] and len(mf) == 2


def test_the_sections_partition_fixable_and_upcoming(tmp_path):
    for key in ("Alex", "Sam"):
        w = _work(tmp_path, key)
        mf = items.must_finish(w, NOW.date())
        assert mf.ids == {v.id for v in w.fixable + w.upcoming}
        sections = [mf.tonight, mf.tomorrow, mf.overdue, mf.paper, mf.waiting, mf.later]
        assert sum(len(s) for s in sections) == len(mf.ids)


def test_a_covered_item_is_left_out_of_every_section(tmp_path):
    w = _work(tmp_path)
    vocab = next(v for v in w.upcoming if v.name == "Vocabulary")
    mf = items.must_finish(w, NOW.date(), covered={vocab.id})
    assert "Vocabulary" not in _names(mf.tonight) and vocab.id not in mf.ids


def test_a_deadline_in_the_first_hour_belongs_to_the_evening_before(tmp_path):
    """Review Focus 1: due 9/16 00:30, read 9/15 at 2 pm, is tonight (#139)."""
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    eng["assignments"].append(_a(83, "Midnight quiz", "09-16", due_at="2026-09-16T00:30:00-04:00"))
    mf = items.must_finish(_work(tmp_path, snap=snap), NOW.date())
    assert "Midnight quiz" in _names(mf.tonight) and "Midnight quiz" not in _names(mf.tomorrow)


def test_a_late_hand_in_with_no_grade_is_waiting(tmp_path):
    snap = snapshot()
    eng = snap["students"]["Alex"]["canvas"]["courses"][0]
    for a in eng["assignments"]:
        if a["name"] == "Lab notebook":
            a.update(submission_types=["online_upload"], state="submitted", late=True,
                     submitted_at="2026-09-12T20:00:00-04:00", seconds_late=100000)
    mf = items.must_finish(_work(tmp_path, snap=snap), NOW.date())
    assert _names(mf.waiting) == ["Lab notebook"] and "Lab notebook" not in _names(mf.paper)


def test_unpicked_is_the_open_groups_not_the_folded_ones(tmp_path):
    mf = items.must_finish(_work(tmp_path), NOW.date())
    assert set(_names(mf.unpicked)) == {"Vocabulary", "Worksheet 3", "Lab notebook", "Participation"}


def test_sheet_status_never_pulls_in_reportlab():
    """`items.sheet_status` reads `status_words`, not `sheet.py` (which imports reportlab at
    module scope) -- so a plan page can render without reportlab installed, the way
    `tests/test_open_work_parity.py` already treats it as optional (`importorskip`). A fresh
    interpreter is the only way to prove nothing already sitting in `sys.modules` from an
    earlier import masks the regression (#137 follow-up)."""
    code = ("import sys, fridgesheet.web.stores.items as i\n"
            "assert 'reportlab' not in sys.modules, sorted(m for m in sys.modules if 'reportlab' in m)\n"
            "assert 'fridgesheet.sheet' not in sys.modules\n")
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    result = subprocess.run([sys.executable, "-c", code], cwd=str(Path(__file__).resolve().parent.parent),
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_sheet_status_is_the_sheets_word(tmp_path):
    w = _work(tmp_path, "Sam")
    words = {v.name: items.sheet_status(v) for v in w.fixable}
    assert words == {"Cell diagram": "MISSING", "Safety quiz": "ZERO"}
    w = _work(tmp_path)
    assert {v.name: items.sheet_status(v) for v in w.upcoming}["Vocabulary"] == "DUE TODAY"

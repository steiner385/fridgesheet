"""The late-work register decides how long past its due date an item can still earn
credit. The sheet drops anything past that point, because a row nobody can act on
is noise, and prints the deadline on the rest."""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from fridgesheet import late_rules

TZ = ZoneInfo("America/New_York")
DUE = datetime(2026, 9, 4, 15, 0, tzinfo=TZ)


def test_missing_file_gives_fourteen_day_default(tmp_path):
    rules = late_rules.load(tmp_path / "none.toml")
    r = rules.resolve("Al", "Latin I S1-2027-Elifrits")
    assert r.late_days == 14
    assert rules.deadline("Al", "Latin I", DUE) == datetime(2026, 9, 18, 15, 0, tzinfo=TZ)


def test_first_matching_rule_wins_on_course_substring_and_kid_prefix(tmp_path):
    p = tmp_path / "late-rules.toml"
    p.write_text(
        '[default]\nlate_days = 14\n\n'
        '[[rule]]\ncourse = "Honors English 9"\nlate_days = 7\ncredit = "50%"\n\n'
        '[[rule]]\nkid = "Al"\nlate_days = 10\ncredit = "50%"\n'
    )
    rules = late_rules.load(p)
    assert rules.resolve("Alex", "Honors English 9 S1-2027-Hoch").late_days == 7
    assert rules.resolve("Alex", "Honors Biology S1-2027-Nance").late_days == 10
    assert rules.resolve("Sam", "Science 5th Gr-2027-Penewit").late_days == 14
    assert rules.resolve("Alex", "Honors English 9").credit == "50%"


def test_zero_days_means_deadline_is_the_due_date(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text('[[rule]]\ncourse = "Algebra"\nlate_days = 0\n')
    assert late_rules.load(p).deadline("Al", "Honors Algebra II", DUE) == DUE


def test_until_quarter_end_uses_the_next_quarter_boundary(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text(
        '[quarters]\nq1 = 2026-10-15\nq2 = 2026-12-18\n\n'
        '[[rule]]\ncourse = "Band"\nuntil = "quarter_end"\n'
    )
    rules = late_rules.load(p)
    assert rules.deadline("Jo", "Band 7-2027-Whaley", DUE) == datetime(2026, 10, 15, 23, 59, tzinfo=TZ)
    late_q1 = datetime(2026, 10, 16, 8, 0, tzinfo=TZ)
    assert rules.deadline("Jo", "Band 7", late_q1) == datetime(2026, 12, 18, 23, 59, tzinfo=TZ)


def test_until_quarter_end_past_last_quarter_falls_back_to_default_days(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text('[quarters]\nq1 = 2026-10-15\n\n[[rule]]\ncourse = "Band"\nuntil = "quarter_end"\n')
    due = datetime(2026, 11, 1, tzinfo=TZ)
    assert late_rules.load(p).deadline("Jo", "Band 7", due) == datetime(2026, 11, 15, tzinfo=TZ)


def test_seed_file_is_written_once_and_parses(tmp_path):
    p = tmp_path / "late-rules.toml"
    late_rules.ensure_seed(p)
    assert p.is_file()
    rules = late_rules.load(p)
    assert rules.resolve("Al", "Anything 101").late_days == 14
    assert rules.resolve("Al", "Anything 101").credit == "?"
    p.write_text("[default]\nlate_days = 3\n")
    late_rules.ensure_seed(p)  # must not overwrite an edited file
    assert late_rules.load(p).resolve("Al", "anything").late_days == 3


def test_bad_toml_raises_a_readable_error(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text("this is = not [ toml\n")
    with pytest.raises(late_rules.LateRulesError):
        late_rules.load(p)

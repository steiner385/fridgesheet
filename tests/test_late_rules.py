"""The late-work register decides how long past its due date an item can still earn
credit. The sheet drops anything past that point, because a row nobody can act on
is noise, and prints the deadline on the rest."""
from __future__ import annotations

from datetime import date, datetime
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


def test_first_matching_rule_wins_on_course_words_and_kid_short_form(tmp_path):
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


def test_to_toml_round_trips_default_quarters_and_rules(tmp_path):
    rules = late_rules.LateRules(
        default=late_rules.Rule(late_days=14, credit="?"),
        rules=[late_rules.Rule(course="Honors English 9", late_days=7, credit="50%", source="syllabus")],
        quarters=[date(2026, 10, 15), date(2026, 12, 18)],
    )
    p = tmp_path / "r.toml"
    p.write_text(late_rules.to_toml(rules))
    loaded = late_rules.load(p)
    assert loaded.default.late_days == 14 and loaded.default.credit == "?"
    assert loaded.quarters == [date(2026, 10, 15), date(2026, 12, 18)]
    assert len(loaded.rules) == 1
    r = loaded.rules[0]
    assert (r.course, r.late_days, r.credit, r.source) == ("Honors English 9", 7, "50%", "syllabus")


def test_to_toml_writes_until_quarter_end_for_a_rule(tmp_path):
    rules = late_rules.LateRules(
        default=late_rules.Rule(),
        rules=[late_rules.Rule(course="Band", until="quarter_end", late_days=None)],
        quarters=[date(2026, 10, 15)],
    )
    p = tmp_path / "r.toml"
    p.write_text(late_rules.to_toml(rules))
    loaded = late_rules.load(p)
    assert loaded.rules[0].until == "quarter_end"
    assert loaded.rules[0].late_days is None


def test_to_toml_with_no_rules_or_quarters_parses_back_to_bare_default(tmp_path):
    rules = late_rules.LateRules(default=late_rules.Rule(late_days=10, credit="?"), rules=[], quarters=[])
    p = tmp_path / "r.toml"
    p.write_text(late_rules.to_toml(rules))
    loaded = late_rules.load(p)
    assert loaded.default.late_days == 10 and loaded.rules == [] and loaded.quarters == []


def test_to_toml_preserves_a_zero_day_deadline():
    """0 late_days is a real value ("no late work"), not an absent one -- must not be dropped
    the way an empty string field is."""
    rules = late_rules.LateRules(default=late_rules.Rule(late_days=0), rules=[], quarters=[])
    assert "late_days = 0" in late_rules.to_toml(rules)


# --- #134: late rules match the way source rules do ------------------------------------------

def _one_rule(tmp_path, body: str, **load_kw):
    p = tmp_path / "r.toml"
    p.write_text('[default]\nlate_days = 14\n\n[[rule]]\n' + body + 'late_days = 2\n')
    return late_rules.load(p, **load_kw)


def test_course_is_matched_on_whole_words_so_algebra_i_is_not_algebra_ii(tmp_path):
    rules = _one_rule(tmp_path, 'course = "Algebra I"\n')
    assert rules.resolve("Alex", "Algebra I - 2").late_days == 2
    assert rules.resolve("Alex", "Algebra II S1-2027-Hoch").late_days == 14


def test_a_rule_written_against_either_name_of_a_paired_class_applies(tmp_path):
    """Canvas' ENGLISH LANGUAGE ARTS is HAC's ELA Plus 5th Gr; a rule is about the class."""
    rules = _one_rule(tmp_path, 'course = "ELA Plus"\n')
    assert rules.resolve("Alex", "ENGLISH LANGUAGE ARTS").late_days == 14
    assert rules.resolve("Alex", "ENGLISH LANGUAGE ARTS", "ELA Plus 5th Gr").late_days == 2
    assert rules.deadline("Alex", "ENGLISH LANGUAGE ARTS", DUE, "ELA Plus 5th Gr") == datetime(2026, 9, 6, 15, 0, tzinfo=TZ)


def test_a_rule_for_one_sibling_does_not_reach_a_sibling_whose_name_it_prefixes(tmp_path):
    rules = _one_rule(tmp_path, 'kid = "Max"\n', household=["Max", "Maxine"])
    assert rules.resolve("Max", "Band").late_days == 2
    assert rules.resolve("Maxine", "Band").late_days == 14


def test_a_short_form_of_the_name_still_reaches_the_kid(tmp_path):
    """README: kid = "Alex" matches Alexander. Only that direction: a longer name is not the kid."""
    rules = _one_rule(tmp_path, 'kid = "Alex"\n', household=["Alexander", "Sam"])
    assert rules.resolve("Alexander", "Band").late_days == 2
    assert rules.resolve("Al", "Band").late_days == 14
    assert rules.resolve("Sam", "Band").late_days == 14


def test_default_until_quarter_end_is_rejected_not_silently_replaced(tmp_path):
    p = tmp_path / "r.toml"
    p.write_text('[default]\nuntil = "quarter_end"\n\n[quarters]\nq1 = 2026-10-15\n')
    with pytest.raises(late_rules.LateRulesError, match="default"):
        late_rules.load(p)

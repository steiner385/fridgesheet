"""Which source is authoritative, per family, kid and class (docs/superpowers/specs/2026-09-22-source-of-truth-design.md)."""
from __future__ import annotations

import logging
import tomllib

import tomli_w

from fridgesheet import sources
from fridgesheet.matching import course_matches, kid_matches


def prefs(text: str) -> sources.SourcePrefs:
    return sources.from_doc(tomllib.loads(text))


def test_no_table_means_canvas_assignments_hac_grades():
    p = sources.from_doc({})
    assert p.resolve("Alex", "Honors Biology S1-2027-Nance") == sources.Choice("canvas", "hac")
    assert p == sources.DEFAULT


def test_household_default_applies_everywhere():
    p = prefs('[sources]\nassignments = "hac"\ngrades = "canvas"\n')
    assert p.resolve("Sam", "Science 7 - 1") == sources.Choice("hac", "canvas")


def test_fields_resolve_independently():
    p = prefs('[sources]\n'
              '[[sources.rule]]\nkid = "Douglas"\ngrades = "canvas"\n\n'
              '[[sources.rule]]\ncourse = "Band"\nassignments = "hac"\n')
    assert p.resolve("Douglas", "Concert Band S1-2027-Desmond") == sources.Choice("hac", "canvas")
    assert p.resolve("Douglas", "Honors English 9") == sources.Choice("canvas", "canvas")
    assert p.resolve("Melanie", "Concert Band") == sources.Choice("hac", "hac")


def test_first_matching_rule_that_sets_the_field_wins():
    p = prefs('[sources]\n'
              '[[sources.rule]]\nkid = "Douglas"\ncourse = "Honors Algebra II"\nassignments = "hac"\n\n'
              '[[sources.rule]]\ncourse = "Honors Algebra II"\nassignments = "canvas"\ngrades = "canvas"\n')
    assert p.resolve("Douglas", "Honors Algebra II S1-2027-Ho") == sources.Choice("hac", "canvas")
    assert p.resolve("Kayla", "Honors Algebra II - 2") == sources.Choice("canvas", "canvas")


def test_kid_is_a_prefix_match_either_way():
    p = prefs('[[sources.rule]]\nkid = "Alex"\ngrades = "canvas"\n')
    assert p.resolve("Alexander", "X").grades == "canvas"
    assert p.resolve("Al", "X").grades == "canvas"
    assert p.resolve("Sam", "X").grades == "hac"


def test_course_pattern_matches_whole_words_only():
    """Review focus 1: a rule for Algebra I must never flip Algebra II's grades."""
    p = prefs('[[sources.rule]]\ncourse = "Algebra I"\ngrades = "canvas"\n')
    assert p.resolve("Alex", "Algebra I S1-2027-Lee").grades == "canvas"
    assert p.resolve("Alex", "Algebra I - 2").grades == "canvas"
    assert p.resolve("Alex", "Algebra II S1-2027-Hoch").grades == "hac"
    assert p.resolve("Alex", "Honors Algebra II - 3").grades == "hac"


def test_short_name_rule_matches_both_sources_names():
    """Review focus 2: the course-page control writes the short name; HAC-only rows carry HAC's name."""
    p = sources.DEFAULT.with_rule("Douglas", "Honors Algebra II", "hac", None)
    assert p.resolve("Douglas", "Honors Algebra II S1-2027-Hoch").assignments == "hac"
    assert p.resolve("Douglas", "Honors Algebra II - 3").assignments == "hac"


def test_bad_values_warn_and_fall_through(caplog):
    """Review focus 3: a typo in a preference must not take the app down."""
    caplog.set_level(logging.WARNING, logger="fridgesheet.sources")
    p = prefs('[sources]\nassignments = "powerschool"\ngrades = " HAC "\n'
              '[[sources.rule]]\ncourse = "Band"\ngrades = 7\n')
    assert p.default == sources.Choice("canvas", "hac")            # "HAC " is tolerated, powerschool is not
    assert p.resolve("Alex", "Band").grades == "hac"               # the rule's bad value is unset, not fatal
    assert "powerschool" in caplog.text and "7" in caplog.text


def test_wrong_shapes_are_ignored(caplog):
    caplog.set_level(logging.WARNING, logger="fridgesheet.sources")
    assert sources.from_doc({"sources": "hac"}) == sources.DEFAULT
    assert sources.from_doc({"sources": {"rule": 3}}) == sources.DEFAULT
    assert sources.from_doc({"sources": {"rule": [3, {"course": "Band", "grades": "canvas"}]}}).resolve("A", "Band").grades == "canvas"


def test_with_rule_replaces_rather_than_duplicates_and_all_default_removes():
    p = sources.DEFAULT.with_rule("Alex", "Band", "hac", None)
    p = p.with_rule("alex", "band", None, "canvas")
    assert len(p.rules) == 1 and p.rules[0].grades == "canvas" and p.rules[0].assignments is None
    assert p.with_rule("Alex", "Band", None, None).rules == ()
    assert p.without_rule("ALEX", "Band").rules == ()


def test_deciding_rule_names_what_is_in_force():
    p = prefs('[[sources.rule]]\nkid = "Alex"\ngrades = "canvas"\n')
    assert p.deciding_rule("Alex", "Band", "grades").kid == "Alex"
    assert p.deciding_rule("Alex", "Band", "assignments") is None
    assert p.rule_for("Alex", "Band") is None                     # only an exact kid+course rule


def test_to_doc_round_trips_through_toml():
    p = sources.DEFAULT.with_default("hac", "canvas").with_rule("Alex", "Band", "hac", None)
    doc = {"sources": p.to_doc()}
    assert sources.from_doc(tomllib.loads(tomli_w.dumps(doc))) == p
    assert "rule" not in sources.DEFAULT.to_doc()


def test_pick_value_prefers_then_fills_the_gap():
    assert sources.pick_value("hac", 91.2, 88.0) == (88.0, "hac")
    assert sources.pick_value("canvas", 91.2, 88.0) == (91.2, "canvas")
    assert sources.pick_value("hac", 91.2, None) == (91.2, "canvas")
    assert sources.pick_value("canvas", None, None) == (None, None)


def test_assignments_for_defaults_to_canvas_without_prefs():
    assert sources.assignments_for(None, "Alex", "Band") == "canvas"


def test_shared_matchers_keep_late_rules_semantics():
    assert kid_matches("", "anyone") and kid_matches("Alex", "Al") and not kid_matches("Alex", "Sam")
    assert course_matches("Algebra I", "Algebra II")                          # late rules: plain substring, unchanged
    assert not course_matches("Algebra I", "Algebra II", whole_words=True)
    assert course_matches("English 9", "Honors English 9 S1-2027-Hoch", whole_words=True)


def test_a_course_page_rule_beats_a_broader_rule_earlier_in_the_file():
    """Review finding: with_rule appended, so a hand-written class-wide rule above it still won."""
    p = prefs('[[sources.rule]]\ncourse = "Honors English 9"\ngrades = "hac"\n')
    p = p.with_rule("Alex", "Honors English 9", None, "canvas")
    assert p.resolve("Alex", "Honors English 9 S1-2027-Hoch").grades == "canvas"
    assert p.resolve("Sam", "Honors English 9 S1-2027-Hoch").grades == "hac"        # the broad rule still holds for others
    p = p.with_rule("Alex", "Honors English 9", None, "hac").with_rule("Alex", "Honors English 9", None, "canvas")
    assert p.resolve("Alex", "Honors English 9").grades == "canvas" and len(p.rules) == 2


def test_a_rule_reaches_the_twin_whose_name_it_does_not_contain():
    """Review finding: pairs like ENGLISH LANGUAGE ARTS <-> ELA Plus 5th Gr share no words, so a rule
    written from one twin's page missed the other. Rules match either name of the class."""
    p = sources.DEFAULT.with_rule("Alex", "ENGLISH LANGUAGE ARTS", "hac", "canvas")
    assert p.resolve("Alex", "ELA Plus 5th Gr").assignments == "canvas"                           # no peer given: no match
    assert p.resolve("Alex", "ELA Plus 5th Gr", peer="ENGLISH LANGUAGE ARTS S1-2027-X") == sources.Choice("hac", "canvas")
    assert p.deciding_rule("Alex", "ELA Plus 5th Gr", "grades", peer="ENGLISH LANGUAGE ARTS").course == "ENGLISH LANGUAGE ARTS"
    assert sources.assignments_for(p, "Alex", "ELA Plus 5th Gr", peer="ENGLISH LANGUAGE ARTS") == "hac"

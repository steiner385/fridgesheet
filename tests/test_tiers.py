"""Which presentation a child's grade earns.

Three tiers, not thirteen: school structure already clusters this way, and the difference
between 6th and 7th grade is not real. The empty tier is what shipped before grades existed,
and an unreadable grade must land there rather than guess.
"""
from __future__ import annotations

import pytest

from fridgesheet import config
from fridgesheet.web import tiers


@pytest.mark.parametrize("grade,expected", [
    (0, "early"), (1, "early"), (5, "early"),          # K-5
    (6, "middle"), (7, "middle"), (8, "middle"),       # 6-8
    (9, "older"), (11, "older"), (12, "older"),        # 9-12
])
def test_each_grade_lands_in_its_school(grade, expected):
    assert tiers.tier(grade) == expected


@pytest.mark.parametrize("boundary,expected", [(5, "early"), (6, "middle"), (8, "middle"), (9, "older")])
def test_the_boundaries_are_where_the_schools_are(boundary, expected):
    assert tiers.tier(boundary) == expected


@pytest.mark.parametrize("bad", [None, -1, 13, 99, "9", 9.5, True])
def test_anything_unreadable_is_the_interface_that_shipped(bad):
    """A typo must not silently pick a tier."""
    assert tiers.tier(bad) == ""


def test_for_student_reads_the_setting():
    s = config.Settings()
    s.grades = {"Douglas": 9, "Melanie": 7, "Kayla": 5}
    assert tiers.for_student(s, "Douglas") == "older"
    assert tiers.for_student(s, "Melanie") == "middle"
    assert tiers.for_student(s, "Kayla") == "early"


def test_a_child_with_no_grade_set_gets_the_shipped_interface():
    s = config.Settings()
    s.grades = {"Douglas": 9}
    assert tiers.for_student(s, "Kayla") == ""
    assert tiers.for_student(s, "") == ""
    assert tiers.for_student(s, None) == ""


def test_every_tier_name_is_in_TIERS():
    assert set(tiers.TIERS) == {"early", "middle", "older"}
    assert "" not in tiers.TIERS          # the absence of a tier is not a tier

"""The same fact in fewer words, and never a fact nobody gave us.

This app's discipline is not to say more than the sources support -- a fabricated due hour
was removed from the whole app for exactly that reason. Age-appropriate language is
therefore *simpler true statements*, never friendlier approximations: "due tomorrow morning"
is true of 7:20am; "finish by bedtime" is invented.
"""
from __future__ import annotations

import re

import pytest

from fridgesheet.web import phrasing, reconcile, tiers


def test_the_adult_word_is_the_word_that_ships_today():
    assert phrasing.phrase("Missing", "older") == "Missing"
    assert phrasing.phrase("Zero", "older") == "Zero"


def test_a_younger_reader_gets_the_same_fact_in_plainer_words():
    assert phrasing.phrase("Missing", "early") == "Teacher hasn't got it"
    assert phrasing.phrase("Missing", "middle") == "Marked missing"


def test_no_tier_is_the_word_that_ships_today():
    """A household that set no grade sees no change."""
    for word in phrasing.PHRASES:
        assert phrasing.phrase(word, "") == word


def test_a_word_nobody_translated_is_shown_as_it_is():
    """Never a blank: an untranslated word is the current word."""
    assert phrasing.phrase("Excused", "early") == "Excused"
    assert phrasing.phrase("something new", "early") == "something new"


def test_a_concept_missing_one_tier_falls_back_to_the_adult_word():
    table = dict(phrasing.PHRASES, tester={"older": "widget"})
    assert phrasing.phrase("tester", "early", table=table) == "widget"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_no_phrase_invents_a_number_a_date_or_a_time(tier):
    """The guard that keeps "simpler" from becoming "made up". A phrase table is copy, and
    copy is where invented precision comes back."""
    for word, by_tier in phrasing.PHRASES.items():
        adult = by_tier.get("older", word)
        allowed = set(re.findall(r"\d+", adult))
        for found in re.findall(r"\d+", by_tier.get(tier, adult)):
            assert found in allowed, f"{word!r} at {tier!r} invents the number {found!r}"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_every_concept_has_a_phrase_for_every_tier(tier):
    for word, by_tier in phrasing.PHRASES.items():
        assert by_tier.get(tier), f"{word!r} has nothing for {tier!r}"


def test_the_table_covers_the_words_a_child_actually_meets():
    """The status words and reconcile kinds that render on a child's pages."""
    # Status words
    for word in ("Missing", "Zero", "Paper, check", "Late, ungraded", "Submitted, ungraded", "Unpublished"):
        assert word in phrasing.PHRASES, word
    # Reconcile kinds - every kind must have a phrase
    for kind in reconcile.KINDS:
        assert kind in phrasing.PHRASES, f"Missing phrase for reconcile kind {kind!r}"
    # Action badge
    assert "actionable" in phrasing.PHRASES
    # The two "Handed in" cells that are not yes or no. A child meets these on every paper
    # assignment, so they are copy like any other status word.
    for word in ("On paper", "Unknown"):
        assert word in phrasing.PHRASES, word


def test_the_two_non_answers_stay_distinguishable_at_every_tier():
    """Splitting one dash into two words is pointless if a tier collapses them again."""
    for tier in tiers.TIERS:
        assert phrasing.phrase("On paper", tier) != phrasing.phrase("Unknown", tier)

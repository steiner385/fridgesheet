"""The same fact in fewer words, and never a fact nobody gave us.

This app's discipline is not to say more than the sources support -- a fabricated due hour
was removed from the whole app for exactly that reason. Age-appropriate language is
therefore *simpler true statements*, never friendlier approximations: "due tomorrow morning"
is true of 7:20am; "finish by bedtime" is invented.
"""
from __future__ import annotations

import re

import pytest

from fridgesheet.web import phrasing, tiers


def test_the_adult_word_is_the_word_that_ships_today():
    assert phrasing.phrase("Missing", "older") == "Missing"
    assert phrasing.phrase("Zero", "older") == "Zero"


def test_a_younger_reader_gets_the_same_fact_in_plainer_words():
    assert phrasing.phrase("Missing", "early") == "Teacher hasn't got it"
    assert phrasing.phrase("Missing", "middle") == "Marked missing"


def test_no_tier_is_the_word_that_ships_today():
    """A household that set no grade sees no change -- and what shipped today is the `older`
    entry, not the raw table key. `one_source` is not a word; `one source` is."""
    for word, by_tier in phrasing.PHRASES.items():
        assert phrasing.phrase(word, "") == by_tier["older"]


def test_a_word_nobody_translated_is_shown_as_it_is():
    """Never a blank: an untranslated word is the current word."""
    assert phrasing.phrase("Excused", "early") == "Excused"
    assert phrasing.phrase("something new", "early") == "something new"


def test_a_concept_missing_one_tier_falls_back_to_the_adult_word():
    table = dict(phrasing.PHRASES, tester={"older": "widget"})
    assert phrasing.phrase("tester", "early", table=table) == "widget"


#: Date/time vocabulary a child phrase may not invent -- "No child phrase states a time, date
#: or number its adult equivalent does not" (docs/outcomes.md). Case-insensitive; matched as
#: whole words so "noon" does not also flag "afternoon" twice or "am" flag "camera".
_TIME_WORDS = (
    "tonight", "tomorrow", "yesterday", "today", "bedtime", "midnight", "noon",
    "morning", "afternoon", "evening", "o'clock", "am", "pm",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
)
_TIME_WORD_RE = re.compile(r"\b(" + "|".join(re.escape(w) for w in _TIME_WORDS) + r")\b", re.IGNORECASE)


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_no_phrase_invents_a_number_a_date_or_a_time(tier):
    """The guard that keeps "simpler" from becoming "made up". A phrase table is copy, and
    copy is where invented precision comes back. Numbers and date/time vocabulary are held to
    the same rule: a token may appear in a child phrase only if the concept's `older` phrase
    already has it."""
    for word, by_tier in phrasing.PHRASES.items():
        adult = by_tier.get("older", word)
        allowed_numbers = set(re.findall(r"\d+", adult))
        allowed_time_words = {w.lower() for w in _TIME_WORD_RE.findall(adult)}
        child = by_tier.get(tier, adult)
        for found in re.findall(r"\d+", child):
            assert found in allowed_numbers, f"{word!r} at {tier!r} invents the number {found!r}"
        for found in _TIME_WORD_RE.findall(child):
            assert found.lower() in allowed_time_words, \
                f"{word!r} at {tier!r} invents the date/time word {found!r}"


@pytest.mark.parametrize("tier", tiers.TIERS)
def test_every_concept_has_a_phrase_for_every_tier(tier):
    for word, by_tier in phrasing.PHRASES.items():
        assert by_tier.get(tier), f"{word!r} has nothing for {tier!r}"


def test_the_table_covers_the_words_a_child_actually_meets():
    """The status words and verdict sentences that render on a child's pages."""
    from fridgesheet.web import verdicts
    # Status words
    for word in ("Missing", "Zero", "Paper, check", "In class, check", "Late, ungraded", "Submitted, ungraded", "Unpublished"):
        assert word in phrasing.PHRASES, word
    # Every verdict kind that says something has its facts sentence, and every answer its label
    for kind, answers in verdicts.ANSWERS.items():
        assert "facts." + kind in phrasing.PHRASES, f"Missing facts sentence for verdict {kind!r}"
        for a in answers:
            assert a.key in phrasing.PHRASES, a.key
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


import string  # noqa: E402


def _placeholders(s):
    return {f for _, f, _, _ in string.Formatter().parse(s) if f}


def test_every_tier_of_a_sentence_uses_the_same_placeholders():
    for key, by_tier in phrasing.PHRASES.items():
        sets = {tier: _placeholders(words) for tier, words in by_tier.items()}
        assert len({frozenset(s) for s in sets.values()}) == 1, (key, sets)


def test_the_pace_sentences_exist_and_name_fridge_sheet_not_the_teacher():
    for key in ("pace.expect", "pace.passed", "pace.default", "pace.hac_expect", "pace.hac_passed", "pace.hac_default"):
        assert key in phrasing.PHRASES, key
        for tier in tiers.TIERS:
            words = phrasing.phrase(key, tier)
            assert "Fridge Sheet" in words, (key, tier)
            assert "teacher will" not in words.lower() and "school will" not in words.lower(), (key, tier)

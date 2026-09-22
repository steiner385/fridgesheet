"""One table of words, three columns wide.

A child reads the same rows an adult does. What changes is how much vocabulary the row
assumes they already have -- `past credit` and `disagree` are accurate and useless to a
ten-year-old who has not been taught the model they belong to.

Every younger phrase is the same fact in fewer words. None adds a claim: "Teacher hasn't got
it" is what Canvas's `missing` flag means, and it is not a verdict on the child. A phrase
that states a time, a date or a number its adult equivalent does not is a bug, and a test
holds the whole table to that.

The table lives here rather than in the templates because a vocabulary expressed as
`{% if tier == 'early' %}` across fifteen files is the same vocabulary implemented fifteen
times, which is the pattern this codebase rejects everywhere else.
"""
from __future__ import annotations

#: concept -> tier -> the words. `older` is what ships today, so the empty tier and `older`
#: read identically; they are separate so a later change to `older` leaves the households
#: that set no grade alone.
PHRASES: dict[str, dict[str, str]] = {
    # --- the status word on a row -----------------------------------------------------
    "Missing":             {"early": "Teacher hasn't got it", "middle": "Marked missing", "older": "Missing"},
    "Zero":                {"early": "Marked zero - ask about it", "middle": "Scored zero", "older": "Zero"},
    "Paper, check":        {"early": "On paper - hand it in", "middle": "Paper, no grade yet", "older": "Paper, check"},
    "Late, ungraded":      {"early": "Handed in late, no grade yet", "middle": "Late, not graded", "older": "Late, ungraded"},
    "Submitted, ungraded": {"early": "Handed in - waiting", "middle": "Submitted, not graded", "older": "Submitted, ungraded"},
    "Unpublished":         {"early": "Not open yet", "middle": "Not published", "older": "Unpublished"},
    # --- what the two sources disagree about ------------------------------------------
    "disagree":            {"early": "Ask your teacher", "middle": "Sources disagree", "older": "disagree"},
    "past_credit":         {"early": "Too late to fix", "middle": "Past the credit window", "older": "past credit"},
    "one_source":          {"early": "Only one system lists it", "middle": "Only one source lists it", "older": "one source"},
    "paper_no_grade":      {"early": "On paper - hand it in", "middle": "Paper, no grade yet", "older": "paper no grade"},
    "submitted_ungraded":  {"early": "Handed in - waiting", "middle": "Submitted, not graded", "older": "submitted ungraded"},
    # --- the badge that means "you can still do something about this" -----------------
    "actionable":          {"early": "Can still fix", "middle": "Still fixable", "older": "actionable"},
}


def phrase(word: str, tier: str, *, table: dict[str, dict[str, str]] | None = None) -> str:
    """`word` said for `tier`.

    Two fallbacks, both to the word that ships today rather than to a blank: a concept in the
    table with nothing for this tier yields its `older` entry, and a concept absent from the
    table yields `word` unchanged. A word nobody has translated is shown as it is; it is
    never dropped.
    """
    by_tier = (table if table is not None else PHRASES).get(word)
    if not by_tier or not tier:
        return word
    return by_tier.get(tier) or by_tier.get("older") or word

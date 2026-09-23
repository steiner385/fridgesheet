"""Which presentation a child's grade earns.

The pages a child reads -- the kid page, Open work, the check-in and the plan -- render the
same facts and offer the same actions whatever their age. What changes is type size,
density, colour and wording, and this is the one place a grade becomes that choice.

Three tiers rather than thirteen: school structure already clusters this way, the difference
between 6th and 7th grade is not real, and thirteen palettes is more than one person can
keep good. The empty tier is what shipped before grades existed; an unset or unreadable
grade lands there rather than guessing, so a household that never sets one sees no change.
"""
from __future__ import annotations

#: The tiers that have a presentation of their own. "" is not among them: it is the absence
#: of a grade, and it renders what shipped before this existed.
TIERS: tuple[str, ...] = ("early", "middle", "older")


def tier(grade) -> str:
    """"early" (K-5), "middle" (6-8), "older" (9-12), or "" for anything unreadable.

    `bool` is an `int` subclass, so it is excluded explicitly: `True` is not grade 1.
    """
    if isinstance(grade, bool) or not isinstance(grade, int) or not 0 <= grade <= 12:
        return ""
    if grade <= 5:
        return "early"
    return "middle" if grade <= 8 else "older"


def for_student(settings, key) -> str:
    """The tier for one child, by their student key. Unknown child, no grade set, or no key
    at all -- all the same answer: the interface that shipped."""
    if not key:
        return ""
    return tier((getattr(settings, "grades", None) or {}).get(str(key)))

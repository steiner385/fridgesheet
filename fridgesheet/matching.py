"""Pairing courses and assignments across Canvas and HAC, whose names never quite agree.

Shared by the MCP tools and the printed sheet, so it must not import the server.
"""
from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("fridgesheet.matching")


def norm_name(s: str) -> str:
    """Compare assignment titles across systems ignoring case, punctuation and spacing."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def same_item(a: str, b: str) -> bool:
    """Whether two titles from Canvas and HAC name the same piece of work.

    Teachers rarely type the title identically in both gradebooks -- Canvas' "MakeMusic Cloud
    Assignment #1" is HAC's "MakeMusic Assignment #1" -- so exact matching let real duplicates
    through. Compare word sets instead, but treat numbers as decisive: "Quiz 1" must never
    merge with "Quiz 2", nor "Chapter 1.3" with "Chapter 1.4", however similar the words.
    """
    ta, tb = set(norm_name(a).split()), set(norm_name(b).split())
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if {x for x in ta if x.isdigit()} != {x for x in tb if x.isdigit()}:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.7


# HAC labels a class "Algebra II - 3" (section); Canvas labels it "Algebra II S1-2027-Hoch"
# (term, year, teacher). Trim both tails so the two systems' names for one class compare equal.
_COURSE_TAIL_RE = re.compile(r"\s*(?:-\s*\d+|\bS[12]\b|\bSem\s*[12]\b|-\s*20\d\d.*)$", re.I)

# The two systems abbreviate differently -- Canvas' "ENGLISH LANGUAGE ARTS" is HAC's
# "ELA Plus 5th Gr", which share no words at all. Expand both sides to a common long form.
_ABBREV = {
    "soc std": "social studies",
    "soc studies": "social studies",
    "lang arts": "language arts",
    "ela": "english language arts",
    "adv": "advanced",
    "hnrs": "honors",
    "hon": "honors",
    "gr": "grade",
    "alg": "algebra",
    "bio": "biology",
    "lit": "literature",
}

#: Escape hatch for pairs no rule can infer, e.g.
#: FRIDGESHEET_COURSE_ALIASES='{"ENGLISH LANGUAGE ARTS": "ELA Plus 5th Gr"}'
#: Both sides are rewritten to the alias target before matching.
try:
    _ALIASES = {k.strip().lower(): v for k, v in json.loads(os.environ.get("FRIDGESHEET_COURSE_ALIASES", "{}")).items()}
except (ValueError, AttributeError):
    log.warning("FRIDGESHEET_COURSE_ALIASES is not a JSON object; ignoring it")
    _ALIASES = {}


def short_course(name: str) -> str:
    """The class name as a person says it: tails for term, year, teacher and section removed."""
    b, prev = " ".join((name or "").split()), None
    while prev != b:
        prev, b = b, _COURSE_TAIL_RE.sub("", b).strip()
    return b


def kid_matches(pattern: str, kid: str) -> bool:
    """A rule's kid against a student's first name: empty matches everyone; otherwise a prefix
    match either way, so "Alex" and "Alexander" (and a nickname "Al") are one kid."""
    if not pattern:
        return True
    a, b = pattern.lower(), (kid or "").lower()
    return a.startswith(b) or b.startswith(a)


def course_matches(pattern: str, course: str, *, whole_words: bool = False) -> bool:
    """A rule's course against a class name, or that name with its term/teacher tail removed.

    Empty matches every class. Late rules use a plain case-insensitive substring. Source rules
    ask for `whole_words`, so "Algebra I" does not also mean "Algebra II": a rule that flips
    which gradebook a class's grades come from must not reach a second class by accident."""
    if not pattern:
        return True
    p = pattern.lower().strip()
    names = ((course or "").lower(), short_course(course).lower())
    if not whole_words:
        return any(p in n for n in names)
    rx = re.compile(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])")
    return any(rx.search(n) for n in names)


def hac_item_key(course: str, name: str) -> str:
    """The stable key for a HAC row with no Canvas twin: `hac:<short course>:<norm name>`.

    One definition for the sheet (`open_items`) and the database (`web.ingest`). They had
    their own, differing in whether the assignment name was normalised, so a flag set on a
    HAC-only item in the app never matched the row it was set on and never reached the paper.
    """
    return f"hac:{short_course(course)}:{norm_name(name)}"


def _expand(s: str) -> str:
    for abbr in sorted(_ABBREV, key=len, reverse=True):   # multi-word entries first
        s = re.sub(rf"\b{re.escape(abbr)}\b", _ABBREV[abbr], s)
    return " ".join(s.split())


def course_base(name: str) -> str:
    b = " ".join((name or "").split())
    b = _ALIASES.get(b.strip().lower(), b)
    return _expand(short_course(b).lower())


def match_course(base: str, table: dict):
    """Pair a course name against the other system's differently-formatted name.

    Scores every candidate and takes the best, rather than returning the first that clears a
    loose test. The original fell back to "first word and last word both appear", which for a
    7th-grade schedule means "adv" and "7" -- true of Adv Math 7, Adv Science 7, Adv Social
    Studies 7 and Adv Language Arts 7 alike, so all four paired with whichever came first in
    the dict and the rest were reported a second time as HAC-only classes.
    """
    b = course_base(base)
    if len(b) < 3:  # base.split()[0] raised IndexError on an empty name
        return None
    tb = set(b.split())
    best, best_score = None, 0.0
    for k, v in table.items():
        kl = course_base(k)
        if len(kl) < 3:
            continue
        if b == kl:
            return v
        tk = set(kl.split())
        if not tk:
            continue
        # Course numbers distinguish siblings ("Adv Math 7" vs "Adv Math 8"), so a
        # disagreement on digits disqualifies the pair however alike the words are.
        if {x for x in tb if x.isdigit()} != {x for x in tk if x.isdigit()}:
            continue
        if (b in kl and len(tb) >= 2) or (kl in b and len(tk) >= 2):
            # One name is the other plus qualifiers: "english language arts" inside
            # "english language arts plus 5th grade". The >=2 word floor stops a bare
            # "Math" from swallowing "Math Plus".
            score = 0.95
        else:
            score = len(tb & tk) / len(tb | tk)
        if score > best_score:
            best, best_score = v, score
    return best if best_score >= 0.7 else None

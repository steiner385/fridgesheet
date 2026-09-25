"""Pairing courses and assignments across Canvas and HAC, whose names never quite agree.

Shared by the MCP tools and the printed sheet, so it must not import the server.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date
from typing import Sequence

log = logging.getLogger("fridgesheet.matching")


def norm_name(s: str) -> str:
    """Compare assignment titles across systems ignoring case, punctuation and spacing."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def title_score(a: str, b: str) -> float | None:
    """How well two titles from Canvas and HAC name the same piece of work: None when they do
    not, 1.0 for the same title, else the share of words they have in common.

    Teachers rarely type the title identically in both gradebooks -- Canvas' "MakeMusic Cloud
    Assignment #1" is HAC's "MakeMusic Assignment #1" -- so exact matching let real duplicates
    through. Compare word sets instead, but treat numbers as decisive: "Quiz 1" must never
    merge with "Quiz 2", nor "Chapter 1.3" with "Chapter 1.4", however similar the words.
    """
    ta, tb = set(norm_name(a).split()), set(norm_name(b).split())
    if not ta or not tb:
        return None
    if ta == tb:
        return 1.0
    if {x for x in ta if x.isdigit()} != {x for x in tb if x.isdigit()}:
        return None
    score = len(ta & tb) / len(ta | tb)
    return score if score >= 0.7 else None


def same_item(a: str, b: str) -> bool:
    """Whether two titles from Canvas and HAC could name the same piece of work (`title_score`)."""
    return title_score(a, b) is not None


def pair_titles(canvas: Sequence[str], hac: Sequence[str]) -> dict[int, int]:
    """Which HAC row each Canvas assignment pairs with, as {canvas index: hac index}, one to one.

    "Unit 3 Test Retake" shares three words of four with "Unit 3 Test", enough for `same_item`,
    and taking the first row over the bar paired the retake with the test's HAC row and left
    the retake's own grade with nowhere to go (#132). So: the same title wins outright (a score
    of 1.0), otherwise the closest wording, and a row on either side is paired at most once --
    the pairs are taken best first, so the answer does not depend on the order either gradebook
    lists its rows in. A HAC row left over is the caller's to keep as a HAC-only item, never to
    drop. One rule for the database (`web.ingest`) and the printed sheet (`open_items`), so a
    flag set on the screen is set on the row the paper prints. A dead tie between two
    candidates goes to the one listed first.
    """
    scored = []
    for i, a in enumerate(canvas):
        for j, b in enumerate(hac):
            s = title_score(a, b)
            if s is not None:
                scored.append((-s, i, j))
    pairs: dict[int, int] = {}
    taken: set[int] = set()
    for _, i, j in sorted(scored):
        if i in pairs or j in taken:
            continue
        pairs[i] = j
        taken.add(j)
    return pairs


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

#: The last `FRIDGESHEET_COURSE_ALIASES` text parsed, and what it parsed to. `course_base`
#: runs once per course per refresh, so the JSON is not re-parsed on every call -- but it is
#: re-read whenever the variable's text changes, which is what makes a `.env` loaded after
#: import count.
_alias_cache: tuple[str | None, dict[str, str]] = (None, {})


def course_aliases() -> dict[str, str]:
    """Escape hatch for pairs no rule can infer, e.g.
    FRIDGESHEET_COURSE_ALIASES='{"ENGLISH LANGUAGE ARTS": "ELA Plus 5th Gr"}'
    Both sides are rewritten to the alias target before matching.

    Read when asked, not at import (#148): `config.load_settings` is what reads `.env` into
    the environment, and this module is imported long before that, so a value set only in
    `.env` used to do nothing. Text that is not a JSON object is logged and ignored, never
    fatal, as before."""
    global _alias_cache
    raw = os.environ.get("FRIDGESHEET_COURSE_ALIASES")
    if raw != _alias_cache[0]:
        try:
            parsed = {str(k).strip().lower(): v for k, v in json.loads(raw or "{}").items()}
        except (ValueError, AttributeError):
            log.warning("FRIDGESHEET_COURSE_ALIASES is not a JSON object; ignoring it")
            parsed = {}
        _alias_cache = (raw, parsed)
    return _alias_cache[1]


def short_course(name: str) -> str:
    """The class name as a person says it: tails for term, year, teacher and section removed."""
    b, prev = " ".join((name or "").split()), None
    while prev != b:
        prev, b = b, _COURSE_TAIL_RE.sub("", b).strip()
    return b


def kid_matches(pattern: str, kid: str, household=()) -> bool:
    """A rule's kid against a student's key (their first name): empty matches everyone; the
    name itself matches, and so does a short form of it, so a rule for "Alex" reaches
    Alexander (README).

    Only that direction (#134): a rule for "Alexander" is not a student keyed "Alex". And a
    short form that is some other student's whole name is that student's rule -- given the
    `household` (every student's key), a rule for "Max" does not reach his sister Maxine."""
    if not pattern:
        return True
    a, b = pattern.strip().lower(), (kid or "").strip().lower()
    if a == b:
        return True
    if any(a == (k or "").strip().lower() for k in household):
        return False
    return b.startswith(a)


def course_matches(pattern: str, course: str) -> bool:
    """A rule's course against a class name, or that name with its term/teacher tail removed.

    Empty matches every class. Otherwise whole words, case-insensitive, so "Algebra I" does not
    also mean "Algebra II": a rule must not reach a second class by accident. One matcher for
    late rules and source rules alike -- the late rules used a plain substring until #134."""
    if not pattern:
        return True
    p = pattern.lower().strip()
    names = ((course or "").lower(), short_course(course).lower())
    rx = re.compile(rf"(?<![a-z0-9]){re.escape(p)}(?![a-z0-9])")
    return any(rx.search(n) for n in names)


def rule_course_matches(pattern: str, course: str, peer: str | None = None) -> bool:
    """`course_matches` against a class under either of its names. `peer` is the same class's
    name in the other source; the two can share no words at all (ENGLISH LANGUAGE ARTS <-> ELA
    Plus 5th Gr), and a rule is about the class, so a rule that fits either name applies to both
    halves of it."""
    return course_matches(pattern, course) or (bool(peer) and course_matches(pattern, peer))


def hac_item_key(course: str, name: str) -> str:
    """The title half of a HAC-only item's key: `hac:<short course>:<norm name>`. The key
    itself is `hac_only_key`, which adds the due date.

    One definition for the sheet (`open_items`) and the database (`web.ingest`). They had
    their own, differing in whether the assignment name was normalised, so a flag set on a
    HAC-only item in the app never matched the row it was set on and never reached the paper.
    """
    return f"hac:{short_course(course)}:{norm_name(name)}"


def hac_only_key(course: str, name: str, due: date | None) -> str:
    """The stable key for a HAC row with no Canvas twin:
    `hac:<short course>:<norm name>:<YYYY-MM-DD>`, or `:unknown` for a row with no due date.

    The date is always there, not only when two rows share a title. A lone row used to take
    the bare `hac_item_key`, and the day a second same-titled row appeared -- a weekly
    "Participation" -- every row with that title was re-keyed to the dated form, so the first
    became a new item and its flag, notes and history stayed behind on the old one (#136).
    Two rows with one title and one due date are the same row scraped twice (`open_items.
    hac_only_keys`). A title the teacher edits still re-keys the row: nothing in HAC identifies
    an assignment but its title and its date.
    """
    return f"{hac_item_key(course, name)}:{due.isoformat() if due else 'unknown'}"


def _expand(s: str) -> str:
    for abbr in sorted(_ABBREV, key=len, reverse=True):   # multi-word entries first
        s = re.sub(rf"\b{re.escape(abbr)}\b", _ABBREV[abbr], s)
    return " ".join(s.split())


def course_base(name: str) -> str:
    b = " ".join((name or "").split())
    b = course_aliases().get(b.strip().lower(), b)
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

"""What kind of work an item is (spec 2026-10-04 assignment types §4).

Canvas has no assignment type. Teachers name assignment groups (Canvas) and categories (HAC)
to weight the grade, and the names say what the work is only when the teacher happens to
weight by kind. So the type is inferred, in four families a parent would talk about
differently, by the first rung of a ladder that answers:

  1. a grown-up's correction on this item
  2. a class rule ("filed under X", "name starts with Y")
  3. Canvas's own `online_quiz`
  4. the gradebook's name for the item, HAC's category before Canvas's group, generic
     buckets ("Assignments", "Total Points") skipped
  5. a keyword in the item's name
  6. everyday work: on the household's data every unlabelled item was a worksheet, notes or
     a tracker, never a hidden test (spec §1), so nothing named is evidence, not a gap

Pure: no database, no clock. The family is computed on every read, never stored, so a better
keyword list or a new rule relabels every item, past ones included.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Sequence

FAMILIES: tuple[str, ...] = ("assessment", "practice", "lab_project", "participation")
#: The order the MCP server and (PR 2) Must-finish break ties in: tests first.
RANK: dict[str, int] = {"assessment": 0, "lab_project": 1, "practice": 2, "participation": 3}
FAMILIES_BY_RANK: tuple[str, ...] = tuple(sorted(FAMILIES, key=RANK.__getitem__))
GENERIC: frozenset[str] = frozenset({"assignments", "imported assignments", "total points", ""})

#: (family, word patterns), tried in this order, first match wins: "Lab Quiz" is a quiz.
#: Each pattern must stand alone: no letter on either side ("lab" is not in "label").
KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # Not "final": "Final Draft" and "Final Submission" are essays (2026-10-04); a final exam
    # says "exam" or "test" as well.
    ("assessment", ("tests?", "exams?", "midterms?", "quiz", "quizzes", "pre-?tests?",
                    "assessments?", "check ?points?", "summative")),
    ("lab_project", ("labs?", "projects?", "presentations?", "research", "essays?")),
    ("participation", ("participation", "attendance", "concerts?", "performances?", "playing", "seminars?")),
    ("practice", ("homework", "hmwk", "hw", "class ?work", "daily", "warm-?ups?", "bell ?ringers?",
                  "exit tickets?", "worksheets?", "ws")),
)
_PATTERNS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (fam, re.compile(r"(?<![a-z])(?:" + "|".join(words) + r")(?![a-z])")) for fam, words in KEYWORDS)


@dataclass(frozen=True)
class Facts:
    name: str
    canvas_group: str | None = None
    hac_category: str | None = None
    online_quiz: bool = False


@dataclass(frozen=True)
class Rule:
    id: int
    field: str          # "group" | "name_prefix"
    value: str          # case-folded, stripped
    family: str
    created_at: str


@dataclass(frozen=True)
class Typed:
    family: str
    rung: int           # 1..6, the ladder step that answered
    why: str            # a phrasing key, type.why.*
    values: dict = field(default_factory=dict)


def fold(text: str | None) -> str:
    return (text or "").casefold().strip()


def is_generic(name: str | None) -> bool:
    return fold(name) in GENERIC


def keyword_family(text: str | None) -> str | None:
    t = fold(text)
    return next((fam for fam, rx in _PATTERNS if rx.search(t)), None)


def gradebook_name(facts: Facts) -> str | None:
    """The name a group rule offers to pin: the first that names something, HAC's category
    before Canvas's group, as the ladder reads them; a generic bucket only when it is all there
    is (a rule on it is for everyday work)."""
    names = [n.strip() for n in (facts.hac_category, facts.canvas_group) if n and n.strip()]
    return next((n for n in names if not is_generic(n)), names[0] if names else None)


def _rule_order(r: Rule) -> tuple:
    # Group rules first; then longer prefixes; then newest (created_at, id). Sorted descending.
    return (r.field == "group", len(r.value) if r.field == "name_prefix" else 0, r.created_at, r.id)


def matches(rule: Rule, facts: Facts) -> bool:
    if not rule.value:
        return False
    if rule.field == "group":
        return rule.value in (fold(facts.canvas_group), fold(facts.hac_category))
    return fold(facts.name).startswith(rule.value)


def family_of(facts: Facts, rules: Sequence[Rule] = (), correction: str | None = None) -> Typed:
    if correction in FAMILIES:
        return Typed(correction, 1, "type.why.correction")
    for rule in sorted(rules, key=_rule_order, reverse=True):
        if matches(rule, facts):
            why = "type.why.rule_group" if rule.field == "group" else "type.why.rule_prefix"
            return Typed(rule.family, 2, why, {"value": rule.value})
    if facts.online_quiz:
        return Typed("assessment", 3, "type.why.online_quiz")
    for name, why in ((facts.hac_category, "type.why.hac"), (facts.canvas_group, "type.why.canvas")):
        if not is_generic(name):
            fam = keyword_family(name)
            if fam:
                return Typed(fam, 4, why, {"name": name.strip()})
    fam = keyword_family(facts.name)
    if fam:
        return Typed(fam, 5, "type.why.name")
    return Typed("practice", 6, "type.why.default")


def prefix_suggestion(name: str) -> str | None:
    """The text before the name's first digit, as a name-prefix rule would pin it ("WS #2-4 A"
    is "WS #"); None when that is shorter than two characters."""
    head = re.match(r"[^\d]*", name or "").group(0).strip()
    return head if len(head) >= 2 else None


def coverage(typed: Iterable[Typed]) -> dict[int, int]:
    out = {r: 0 for r in range(1, 7)}
    for t in typed:
        out[t.rung] += 1
    return out

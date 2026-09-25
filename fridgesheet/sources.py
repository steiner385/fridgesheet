"""Which source is authoritative: Canvas or HAC, for assignment scores and for class averages.

Both sources are always read and stored; this only decides which value is the headline when
both have one, and the other still fills gaps. Configured in config.toml:

    [sources]
    assignments = "canvas"        # household defaults (these are the built-in values)
    grades = "hac"

    [[sources.rule]]              # kid and course optional; first rule that sets a field wins
    kid = "Douglas"               #   the student's first name, or a short form (Alex ~ Alexander)
    course = "Honors Algebra II"  #   whole words of the class name or its short name
    assignments = "hac"

A bad value warns and is ignored: a typo in a preference must not take the app down.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from .matching import kid_matches, rule_course_matches

log = logging.getLogger("fridgesheet.sources")

SOURCES = ("canvas", "hac")
LABELS = {"canvas": "Canvas", "hac": "HAC"}
FIELDS = ("assignments", "grades")


@dataclass(frozen=True)
class Choice:
    assignments: str = "canvas"
    grades: str = "hac"


@dataclass(frozen=True)
class SourceRule:
    kid: str = ""
    course: str = ""
    assignments: str | None = None
    grades: str | None = None

    def matches(self, kid: str, course: str, peer: str | None = None) -> bool:
        """`peer` is the same class's name in the other source. The two can share no words at
        all (ENGLISH LANGUAGE ARTS <-> ELA Plus 5th Gr), and a rule is about the class, so a
        rule that fits either name applies to both halves of it."""
        return kid_matches(self.kid, kid) and rule_course_matches(self.course, course, peer)

    def targets(self, kid: str, course: str) -> bool:
        """Exactly this kid and this class, as the course-page control writes it."""
        return self.kid.lower() == (kid or "").lower() and self.course.lower() == (course or "").lower()


@dataclass(frozen=True)
class SourcePrefs:
    default: Choice = Choice()
    rules: tuple[SourceRule, ...] = ()

    def deciding_rule(self, kid: str, course: str, field: str, peer: str | None = None) -> SourceRule | None:
        for r in self.rules:
            if getattr(r, field) is not None and r.matches(kid, course, peer):
                return r
        return None

    def resolve(self, kid: str, course: str, peer: str | None = None) -> Choice:
        out = {}
        for f in FIELDS:
            r = self.deciding_rule(kid, course, f, peer)
            out[f] = getattr(r, f) if r is not None else getattr(self.default, f)
        return Choice(**out)

    def rule_for(self, kid: str, course: str) -> SourceRule | None:
        return next((r for r in self.rules if r.targets(kid, course)), None)

    def without_rule(self, kid: str, course: str) -> "SourcePrefs":
        return replace(self, rules=tuple(r for r in self.rules if not r.targets(kid, course)))

    def with_rule(self, kid: str, course: str, assignments: str | None, grades: str | None) -> "SourcePrefs":
        """Add or replace the exact kid+class rule; both fields None removes it.

        The rule goes first: it is the most specific thing a parent can say, and rules are
        first-match, so appending it behind a hand-written class-wide or kid-wide rule would
        leave the control showing a choice that never takes effect."""
        rest = self.without_rule(kid, course)
        if assignments is None and grades is None:
            return rest
        new = SourceRule(kid=kid, course=course, assignments=assignments, grades=grades)
        return replace(rest, rules=(new, *rest.rules))

    def with_default(self, assignments: str, grades: str) -> "SourcePrefs":
        return replace(self, default=Choice(assignments, grades))

    def to_doc(self) -> dict:
        doc: dict = {"assignments": self.default.assignments, "grades": self.default.grades}
        rules = []
        for r in self.rules:
            rules.append({k: v for k, v in (("kid", r.kid), ("course", r.course),
                                            ("assignments", r.assignments), ("grades", r.grades)) if v})
        if rules:
            doc["rule"] = rules
        return doc


DEFAULT = SourcePrefs()


def _value(raw, where: str) -> str | None:
    if raw is None:
        return None
    v = str(raw).strip().lower()
    if v in SOURCES:
        return v
    log.warning("config.toml [sources] %s: %r is not \"canvas\" or \"hac\"; ignoring it", where, raw)
    return None


def from_doc(doc: dict) -> SourcePrefs:
    raw = doc.get("sources")
    if raw is None:
        return DEFAULT
    if not isinstance(raw, dict):
        log.warning("config.toml [sources] is not a table; using the defaults")
        return DEFAULT
    base = Choice()
    default = Choice(assignments=_value(raw.get("assignments"), "assignments") or base.assignments,
                     grades=_value(raw.get("grades"), "grades") or base.grades)
    raw_rules = raw.get("rule")
    if raw_rules is not None and not isinstance(raw_rules, list):
        log.warning("config.toml [sources] rule is not a list of tables; ignoring it")
        raw_rules = []
    rules = []
    for n, d in enumerate(raw_rules or [], start=1):
        if not isinstance(d, dict):
            log.warning("config.toml [sources] rule %d is not a table; ignoring it", n)
            continue
        rules.append(SourceRule(kid=str(d.get("kid", "")).strip(), course=str(d.get("course", "")).strip(),
                                assignments=_value(d.get("assignments"), f"rule {n} assignments"),
                                grades=_value(d.get("grades"), f"rule {n} grades")))
    return SourcePrefs(default, tuple(rules))


def assignments_for(prefs: SourcePrefs | None, kid: str, course: str, peer: str | None = None) -> str:
    return (prefs or DEFAULT).resolve(kid, course, peer).assignments


def pick_value(pick: str, canvas_value, hac_value):
    """(value, source) from the preferred source, or the other when it has nothing."""
    order = (("hac", hac_value), ("canvas", canvas_value)) if pick == "hac" else (("canvas", canvas_value), ("hac", hac_value))
    for src, v in order:
        if v is not None:
            return v, src
    return None, None

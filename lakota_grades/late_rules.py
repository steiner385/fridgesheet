"""The late-work register: how long past its due date an item can still earn credit.

A plain TOML file the parent owns (default ~/.lakota-grades/late-rules.toml), re-read on
every run. The printed sheet drops items past their deadline -- a row nobody can act on
is noise -- and prints the deadline and credit on the rest, which is what turns a list
into a to-do.

    [default]
    late_days = 14

    [quarters]              # grading-period ends, for `until = "quarter_end"`
    q1 = 2026-10-15

    [[rule]]                # first matching rule wins
    kid = "Alex"            # optional; prefix match either way (Alex ~ Alexander)
    course = "English 9"    # optional; case-insensitive substring of the class name
    late_days = 7           # or: until = "quarter_end"
    credit = "50%"          # free text, printed on the sheet
    source = "..."          # where the rule came from; never printed
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from .matching import short_course

DEFAULT_LATE_DAYS = 14

SEED = '''# Late-work rules for the printed sheet. Edit freely; re-read on every run.
#
# An overdue item is shown only while it can still earn credit. First matching
# [[rule]] wins; "kid" and "course" are optional (course = case-insensitive
# substring of the class name). "late_days" = days after the due date the teacher
# still accepts work (0 = no late work). Or "until = \\"quarter_end\\"" for a teacher
# who accepts late work through the grading period. "credit" is printed on the
# sheet next to the deadline; "source" is just for you.

[default]
late_days = 14
credit = "?"

[quarters]                     # Lakota board-approved 2026-27 calendar
q1 = 2026-10-15
q2 = 2026-12-18
q3 = 2027-03-11
q4 = 2027-05-20

# Example: one class that closes late work after a week at half credit.
# [[rule]]
# course = "Honors English 9"
# late_days = 7
# credit = "50%"
# source = "class syllabus, 2026-27"
'''


class LateRulesError(RuntimeError):
    pass


@dataclass(frozen=True)
class Rule:
    late_days: int | None = DEFAULT_LATE_DAYS
    until: str | None = None
    credit: str = ""
    source: str = ""
    kid: str = ""
    course: str = ""

    def matches(self, kid: str, course: str) -> bool:
        if self.kid:
            a, b = self.kid.lower(), (kid or "").lower()
            if not (a.startswith(b) or b.startswith(a)):
                return False
        if self.course and self.course.lower() not in (course or "").lower() and self.course.lower() not in short_course(course).lower():
            return False
        return True


class LateRules:
    def __init__(self, default: Rule, rules: list[Rule], quarters: list[date]):
        self.default, self.rules, self.quarters = default, rules, sorted(quarters)

    def resolve(self, kid: str, course: str) -> Rule:
        for r in self.rules:
            if r.matches(kid, course):
                return r
        return self.default

    def deadline(self, kid: str, course: str, due: datetime) -> datetime:
        """The last moment the item can earn credit."""
        r = self.resolve(kid, course)
        if r.until == "quarter_end":
            for q in self.quarters:
                if q >= due.date():
                    return datetime(q.year, q.month, q.day, 23, 59, tzinfo=due.tzinfo)
        days = r.late_days if r.late_days is not None else (self.default.late_days or DEFAULT_LATE_DAYS)
        return due + timedelta(days=days)


def _rule(d: dict, fallback: Rule) -> Rule:
    if "until" in d and d["until"] != "quarter_end":
        raise LateRulesError(f"late-rules: unsupported until={d['until']!r} (only \"quarter_end\")")
    late_days = fallback.late_days
    if "late_days" in d:
        try:
            late_days = int(d["late_days"])
        except (TypeError, ValueError):
            raise LateRulesError(f"late-rules: late_days must be a whole number, got {d['late_days']!r}") from None
    elif "until" in d:
        late_days = None
    return Rule(
        late_days=late_days,
        until=d.get("until"),
        credit=str(d.get("credit", fallback.credit)),
        source=str(d.get("source", "")),
        kid=str(d.get("kid", "")),
        course=str(d.get("course", "")),
    )


def load(path: Path) -> LateRules:
    """Parse the register. A missing file means the built-in default; a broken one is an error,
    not a silent fallback, because a sheet printed under the wrong rules looks right."""
    if not path.is_file():
        return LateRules(Rule(), [], [])
    try:
        doc = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise LateRulesError(f"late-rules: cannot parse {path}: {e}") from e
    default = _rule(doc.get("default") or {}, Rule())
    if default.late_days is None:
        default = Rule(credit=default.credit)
    quarters = [v for v in (doc.get("quarters") or {}).values() if isinstance(v, date)]
    rules = [_rule(d, default) for d in doc.get("rule") or []]
    return LateRules(default, rules, quarters)


def ensure_seed(path: Path) -> bool:
    """Write the starter register if none exists. Never touches an existing file."""
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(SEED)
    return True

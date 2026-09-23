"""How long a class usually takes: the app's own count, from its own history.

Every grace period used to be one global seven days. Grading pace is a property of a course
and a teacher, and of the kind of work: a stack of paper reading guides is graded in a batch
a week or two on, an online quiz the same evening. The observation table already holds when
the app first saw each grade, so the pace can be learned at render time with no new table
(docs/superpowers/specs/2026-09-23-learned-pace-and-one-tap-answers-design.md, section 4).

`estimate` is the one tunable: its four numbers are policy, and nothing else in the app
knows them. It returns a high percentile rather than a mean so one slow week does not make
the app nag and one fast week does not make it ask early, and it is capped so a teacher who
grades once a quarter cannot silence a real problem for a quarter.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_DAYS = 7      # what the chain bottoms out on: the grace period the app always had
MIN_SAMPLES = 3       # fewer, and a group does not get its own number
PERCENTILE = 0.8      # nearest-rank
FLOOR_DAYS = 1
CAP_DAYS = 21

COURSE_KIND, COURSE, TEACHER, DEFAULT_SCOPE = "course_kind", "course", "teacher", "default"


@dataclass(frozen=True)
class Estimate:
    days: int
    n: int          # samples behind the number; 0 for the default
    scope: str      # course_kind | course | teacher | default


def estimate(samples: list[int]) -> int | None:
    """Days to allow, or None when the samples are too few to say."""
    if len(samples) < MIN_SAMPLES:
        return None
    ordered = sorted(samples)
    rank = max(1, math.ceil(PERCENTILE * len(ordered)))
    return min(CAP_DAYS, max(FLOOR_DAYS, ordered[rank - 1]))


def kind_group(kind: str) -> str:
    """Online work is graded on a different rhythm from paper; that split is most of what
    there is to learn. HAC-only items carry an empty kind and are offline."""
    return "online" if kind == "online" else "offline"


def teacher_key(name: str | None) -> str:
    return " ".join((name or "").split()).lower()


@dataclass(frozen=True)
class Pace:
    """Samples per (class id, kind group), for grade lag and for HAC lag, plus the two maps
    that let an item find its class: `classes` (course id -> class id, so a HAC twin shares
    its Canvas course's history) and `teachers` (class id -> normalised teacher name)."""
    grade: dict[tuple[int, str], list[int]]
    hac: dict[tuple[int, str], list[int]]
    classes: dict[int, int]
    teachers: dict[int, str]

    def grade_days(self, item) -> Estimate:
        # Pooling across kinds is for online work only. A class's auto-graded quizzes would
        # otherwise teach the app that its paper is graded the same day, and it would ask
        # about a reading guide the morning after it was due; paper waits for paper history.
        return self._lookup(self.grade, item, pool_offline=False)

    def hac_days(self, item) -> Estimate:
        # How long HAC takes to catch up is the teacher's gradebook habit, not the kind of work.
        return self._lookup(self.hac, item, pool_offline=True)

    def _lookup(self, table, item, *, pool_offline: bool) -> Estimate:
        if not table:                       # nothing learned at all: the default, without reading the item
            return Estimate(DEFAULT_DAYS, 0, DEFAULT_SCOPE)
        cid = self.classes.get(item["course_id"], item["course_id"])
        group = kind_group(item["kind"] or "")
        own = table.get((cid, group), [])
        if (days := estimate(own)) is not None:
            return Estimate(days, len(own), COURSE_KIND)
        if pool_offline or group == "online":
            pooled = [s for (c, _), ss in table.items() if c == cid for s in ss]
            if (days := estimate(pooled)) is not None:
                return Estimate(days, len(pooled), COURSE)
        teacher = teacher_key(item["teacher"])
        if teacher:
            same = {c for c, t in self.teachers.items() if t == teacher}
            by_teacher = [s for (c, g), ss in table.items() if c in same and g == group for s in ss]
            if (days := estimate(by_teacher)) is not None:
                return Estimate(days, len(by_teacher), TEACHER)
        return Estimate(DEFAULT_DAYS, 0, DEFAULT_SCOPE)


DEFAULT = Pace({}, {}, {}, {})

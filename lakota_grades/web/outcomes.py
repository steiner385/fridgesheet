"""What happened to one assignment, in one word, defined once.

Four places used to answer "did the kid do this?" with four private definitions: the Kid
page's Status column, Reconcile's case kinds, Trends' "on-time" rate and the printed
sheet's status words. They disagreed in exactly the way that surprised the maintainer on
2026-09-17: Canvas's dashboard said his son had 4 missing assignments, the truth was 11
not done and 8 unknown, and the app could not say which number it believed.

The disagreement has a single root: Canvas's `missing` is a *flag*, not a fact. Canvas
sets it when a teacher clicks "missing" or when a course's late policy auto-marks past-due
**online** work; it never sets it for paper or in-class work, and many teachers enter a 0
instead of clicking it. So "missing" undercounts, "past due and not submitted" overcounts
(paper work handed in and graded looks unsubmitted forever), and neither is what a parent
means by "missed".

`classify` reads every signal both sources give -- the flag, the score, the submission,
the kind of work, the due date -- and returns one of the outcomes below. Everything that
counts, filters, colours or prints an outcome goes through it. `docs/outcomes.md` is the
same table in prose, for the parent.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from . import reconcile

#: Handed in by the deadline.
ON_TIME = "on_time"
#: Handed in after the deadline (Canvas's `late`), whatever it was then graded.
LATE = "late"
#: Not done. Any one of: Canvas flagged it missing; a score of zero was entered (with or
#: without a submission -- a blank hand-in scored 0 is not done); or it is online work,
#: past due, with no submission and no grade. A teacher's 0 counts here precisely because
#: many enter one instead of clicking "missing".
NOT_DONE = "not_done"
#: Done, but not through Canvas: a grade above zero with no online submission. Paper and
#: in-class work handed in and marked by hand, or online work the teacher graded from a
#: physical copy. Timing is unknowable, so it is neither on time nor late.
DONE_OFFLINE = "done_offline"
#: Past due, nothing handed in online, and no grade anywhere yet -- paper or in-class work
#: whose fate only the teacher knows. This is the list to ask about.
UNKNOWN = "unknown"
#: Not due yet (or no due date) and not handed in. Nothing has happened.
NOT_DUE = "not_due_yet"
#: The teacher excused it. Counted nowhere.
EXCUSED = "excused"
#: The teacher unpublished it. Not work the kid can do; counted nowhere.
UNPUBLISHED = "unpublished"
#: Neither source has said anything about it.
NO_DATA = ""

#: Order for filters and legends: what a parent scans for first, first.
ORDER = (NOT_DONE, UNKNOWN, LATE, ON_TIME, DONE_OFFLINE, NOT_DUE, EXCUSED, UNPUBLISHED)

LABELS = {
    ON_TIME: "on time", LATE: "late", NOT_DONE: "not done", DONE_OFFLINE: "done on paper",
    UNKNOWN: "unknown", NOT_DUE: "not due yet", EXCUSED: "excused", UNPUBLISHED: "unpublished", NO_DATA: "",
}

#: The outcomes that are settled and count toward a kid's record: the work was due and
#: something is known about it. `NOT_DUE`, `EXCUSED`, `UNPUBLISHED` and `NO_DATA` are not
#: on the record; `UNKNOWN` is on it as the open question it is.
PAST_DUE = (ON_TIME, LATE, NOT_DONE, DONE_OFFLINE, UNKNOWN)

_NOTHING_TO_SUBMIT = ("paper", "in class")


def _is_past(item: sqlite3.Row, now: datetime) -> bool:
    due = reconcile.due_of(item)
    if due is None:
        return False
    a, b = reconcile.comparable(due, now)
    return a < b


def classify(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime) -> str:
    """One outcome for one item, from the latest observation of each source.

    Canvas is read first because it carries the teacher's marks and the submission; HAC
    carries only a grade. A grade in either source is a grade. The order of the checks is
    the order of certainty: a mark or a zero settles it; a submission settles it; a grade
    with no submission means done by hand; then it is either not due, not done, or -- for
    work that could never be submitted online -- not known."""
    c, h = obs.get("canvas"), obs.get("hac")
    if c is None and h is None:
        return NO_DATA
    if c is not None:
        if c["excused"]:
            return EXCUSED
        if c["published"] == 0:
            return UNPUBLISHED
    score = c["score"] if c is not None and c["score"] is not None else (h["score"] if h is not None else None)
    points = item["points"] or 0
    zero = score == 0 and points > 0
    if c is not None:
        if c["missing"] or zero:
            return NOT_DONE
        if c["submitted_at"]:
            return LATE if c["late"] else ON_TIME
        if score is not None:
            return DONE_OFFLINE
        if not _is_past(item, now):
            return NOT_DUE
        return UNKNOWN if item["kind"] in _NOTHING_TO_SUBMIT else NOT_DONE
    # HAC only: a grade or nothing.
    if zero:
        return NOT_DONE
    if score is not None:
        return DONE_OFFLINE
    return UNKNOWN if _is_past(item, now) else NOT_DUE


@dataclass(frozen=True)
class Tally:
    """How a kid's past-due work came out. Five numbers, one per settled outcome."""
    on_time: int = 0
    late: int = 0
    not_done: int = 0
    done_offline: int = 0
    unknown: int = 0

    @property
    def total(self) -> int:
        return self.on_time + self.late + self.not_done + self.done_offline + self.unknown

    @property
    def on_time_rate(self) -> float | None:
        """On time, as a share of the work whose timing is known: on time, late, or not done
        at all. Work done on paper has no timing and is left out; the unknowns are still
        unknown. `None` when nothing is settled yet."""
        timed = self.on_time + self.late + self.not_done
        return self.on_time / timed if timed else None


def tally(outcomes) -> Tally:
    counts = {k: 0 for k in PAST_DUE}
    for o in outcomes:
        if o in counts:
            counts[o] += 1
    return Tally(**counts)

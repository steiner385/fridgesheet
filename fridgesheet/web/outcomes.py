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


def _refresh_id(o) -> int | None:
    return o["refresh_id"] if o is not None and "refresh_id" in o.keys() else None


def newer(a, b) -> bool:
    """Whether observation `a` was recorded in a later refresh than `b`. Refresh ids only
    grow, and ingest writes an observation only when something changed, so this is "did
    `a`'s source change after `b`'s did". An unknown id is never newer."""
    ra, rb = _refresh_id(a), _refresh_id(b)
    return ra is not None and rb is not None and ra > rb


def since_refresh(o, field: str) -> int | None:
    """The refresh in which the observation's `field` run began (ingest's `missing_since` /
    `scored_since`), or the observation's own refresh for a row that does not carry it."""
    if o is not None and field in o.keys() and o[field] is not None:
        return o[field]
    return _refresh_id(o)


def marked_after(c, h) -> bool:
    """Whether Canvas's mark against the work -- its missing flag, or a zero -- was recorded in
    a later refresh than HAC's grade. This is the teacher saying something new, and the one
    thing that outranks a HAC grade (docs/outcomes.md).

    It compares when the *mark* appeared, not when Canvas's observation was last written: an
    observation is rewritten whenever any field changes, and the availability window closing
    a week after the grade used to read as "Canvas marked it missing after that" (#131)."""
    rh = _refresh_id(h)
    if c is None or rh is None:
        return False
    anchors = []
    if c["missing"]:
        anchors.append(since_refresh(c, "missing_since"))
    if c["score"] == 0:
        anchors.append(since_refresh(c, "scored_since"))
    return any(a is not None and a > rh for a in anchors)


def _is_past(item: sqlite3.Row, now: datetime) -> bool:
    due = reconcile.due_of(item)
    if due is None:
        return False
    a, b = reconcile.comparable(due, now)
    return a < b


def on_record(outcome: str, due: datetime | None, now: datetime) -> bool:
    """Whether an outcome counts toward "of N due so far": settled (`PAST_DUE`), and the work
    is past due. Work handed in early is *on time* the moment it is handed in, but it is not
    on the record until its due date passes -- "due so far" is work that is due (#138). Work
    with no due date can never become past due, so it is on the record as soon as anything
    has happened to it: a grade, a hand-in or a mark, which is every settled outcome, since
    `classify` calls undated work with nothing at all *not due yet*."""
    if outcome not in PAST_DUE:
        return False
    if due is None:
        return True
    a, b = reconcile.comparable(due, now)
    return a < b


def classify(item: sqlite3.Row, obs: dict[str, sqlite3.Row], now: datetime, prefer: str = "canvas") -> str:
    """One outcome for one item, from the latest observation of each source.

    Canvas carries the teacher's marks and the submission; HAC carries only a grade. `prefer`
    is the family's assignments source (sources.py). Under "canvas" a Canvas score wins and HAC
    fills the gap, and a HAC grade above zero also overrides Canvas's `missing` flag unless
    Canvas marked it later (`marked_after`, docs/outcomes.md). Under "hac" a HAC score, when there is one, decides done-or-not -- it
    overrides Canvas's `missing` flag and Canvas's own score -- while excused, unpublished and
    the submission's timing still come from Canvas, which is the only source that knows them.
    The order of the checks is the order of certainty: a mark or a zero settles it; a
    submission settles it; a grade with no submission means done by hand; then it is either
    not due, not done, or -- for work that could never be submitted online -- not known."""
    c, h = obs.get("canvas"), obs.get("hac")
    if c is None and h is None:
        return NO_DATA
    if c is not None:
        if c["excused"]:
            return EXCUSED
        if c["published"] == 0:
            return UNPUBLISHED
    # HAC's "EXC" is the teacher excusing it in the gradebook of record, whatever Canvas's
    # automatic mark says (#135).
    if h is not None and h["excused"]:
        return EXCUSED
    c_score = c["score"] if c is not None else None
    h_score = h["score"] if h is not None else None
    # A real HAC grade is the teacher's assessment, and Canvas's `missing` is often its late
    # policy's automatic mark, so HAC decides whenever it has a grade above zero -- unless
    # Canvas marked it after HAC graded it, which is the teacher saying something new. Under
    # the HAC preference HAC decides whenever it has any score, as before.
    hac_graded = h_score is not None and h_score > 0
    hac_decides = h_score is not None and (prefer == "hac" or (hac_graded and not marked_after(c, h)))
    score = h_score if hac_decides else (c_score if c_score is not None else h_score)
    points = item["points"] or 0
    zero = score == 0 and points > 0
    if c is not None:
        if (c["missing"] and not hac_decides) or zero:
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

"""One verdict per item: what the app concluded, and whether the family has anything to do.

The Reconcile page used to raise a "case" for every way Canvas and HAC differed, and asked
about all of them. Most needed nobody: a grade that has not flowed to HAC yet will flow, and
a teacher who graded only in HAC graded it. A verdict has one of four states. `decided`
means the records settle it and the app says why. `waiting` means time will settle it.
`question` means the family can do something. `status` is a plain fact. The rules below
run in order; the first that matches wins (docs/superpowers/specs/
2026-09-23-questions-not-cases-design.md, section 4.1).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..open_items import HANDLED_FLAGS, MARKED_FLAGS
from . import outcomes, reconcile

QUESTION, DECIDED, WAITING, STATUS = "question", "decided", "waiting", "status"
GRACE_DAYS = 7
TOLERANCE = 0.5


@dataclass(frozen=True)
class Answer:
    key: str                # phrase key for the button label
    flag: str | None        # a flag, "confirm", "clear", or None: open the plan-step form


@dataclass(frozen=True)
class Verdict:
    state: str
    kind: str
    facts: dict = field(default_factory=dict)      # values for the "facts.<kind>" phrase
    answers: tuple[Answer, ...] = ()
    asks_on: date | None = None                    # waiting only: the day it becomes a question


ASK = Answer("a.ask_teacher", "ask_teacher")
ANSWERS = {
    "missing_after_grade": (Answer("a.hac_right_done", "done"), ASK),
    "graded_in_hac": (Answer("a.hac_right_done", "done"), ASK),
    "hac_lower": (ASK, Answer("a.hac_right", "ignore")),
    "scores_explained": (ASK, Answer("a.hac_right", "ignore")),
    "submitted_hac_zero": (ASK, Answer("a.zero_right", "ignore")),
    "excused_hac_zero": (ASK, Answer("a.leave_it", "ignore")),
    "hac_still_blank": (ASK, Answer("a.its_fine", "ignore")),
    "hac_lag": (ASK,),
    "still_ungraded": (Answer("a.handed_in", "done"), Answer("a.plan_it", None), ASK),
    "awaiting_grade": (ASK,),
    "stale_answer": (Answer("a.still_done", "confirm"), Answer("a.reopen", "clear"), ASK),
}


def _n(x: float) -> str:
    return f"{x:g}"


def _of(score: float, points) -> str:
    return f"{_n(score)} of {_n(points)}" if points else _n(score)


def _md(ts: str) -> str:
    d = reconcile._parse_ts(ts)
    return f"{d.month}/{d.day}"


def _md_time(ts: str) -> str:
    d = reconcile._parse_ts(ts)
    hour = d.hour % 12 or 12
    return f"{d:%a} {d.month}/{d.day}, {hour}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def _credit_fraction(credit: str) -> float | None:
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*%", credit or "")
    return float(m.group(1)) / 100 if m else None


def _observed_at(o, refresh_times: dict[int, str]) -> datetime | None:
    started = refresh_times.get(o["refresh_id"]) if o is not None and "refresh_id" in o.keys() else None
    return reconcile._parse_ts(started) if started else None


def _after(o, set_at: str, refresh_times) -> bool:
    seen = _observed_at(o, refresh_times)
    if seen is None or not set_at:
        return False
    a, b = reconcile._comparable(seen, reconcile._parse_ts(set_at))
    return a > b


def _stale_change(flag, set_at, c, h, refresh_times) -> str | None:
    """What the school recorded after the family's answer that contradicts it, or None."""
    if flag in HANDLED_FLAGS:
        if c is not None and _after(c, set_at, refresh_times) and (c["missing"] or (c["state"] == "graded" and c["score"] == 0)):
            return "Canvas now says missing" if c["missing"] else "Canvas now shows a zero"
        if h is not None and _after(h, set_at, refresh_times) and h["score"] == 0:
            return "HAC now shows a zero"
    if flag in MARKED_FLAGS:
        if c is not None and _after(c, set_at, refresh_times) and c["score"] is not None:
            return f"Canvas has graded it: {_n(c['score'])}"
        if h is not None and _after(h, set_at, refresh_times) and h["score"] is not None:
            return f"HAC has graded it: {_n(h['score'])}"
    return None


def _scores(c, h, points, late_credit: float | None) -> Verdict | None:
    cs, hs = (c["score"] if c is not None else None), (h["score"] if h is not None else None)
    if cs is None or hs is None or not points:
        return None
    if cs - hs <= TOLERANCE:                           # HAC equal or higher: nothing to fix
        return None
    if abs(hs - cs / points * 100) <= TOLERANCE:
        return Verdict(DECIDED, "scores_explained", {"why": "scale"}, ANSWERS["scores_explained"])
    if c["late"] and late_credit is not None and abs(hs - cs * late_credit) <= TOLERANCE:
        return Verdict(DECIDED, "scores_explained", {"why": "late"}, ANSWERS["scores_explained"])
    return Verdict(QUESTION, "hac_lower", {"canvas": _of(cs, points), "hac": _of(hs, points)}, ANSWERS["hac_lower"])


def verdict(item, obs, *, flag, flag_set_at, now, rules, refresh_times, prefer="canvas") -> Verdict:
    c, h = obs.get("canvas"), obs.get("hac")
    points = item["points"]
    hs = h["score"] if h is not None else None

    # 1-2b: the family's own answer, unless the school has since contradicted it.
    if flag:
        change = _stale_change(flag, flag_set_at, c, h, refresh_times)
        if change:
            return Verdict(QUESTION, "stale_answer",
                           {"flag": flag.replace("_", " "), "when": _md(flag_set_at), "change": change},
                           ANSWERS["stale_answer"])
        if flag in HANDLED_FLAGS:
            return Verdict(STATUS, "answered")
        return Verdict(STATUS, "asked", {"when": _md(flag_set_at)} if flag_set_at else {})

    # 3-4: HAC counts a zero that Canvas says should not be there.
    if c is not None and h is not None and hs == 0 and (points or 0) > 0:
        if c["excused"]:
            return Verdict(QUESTION, "excused_hac_zero", {}, ANSWERS["excused_hac_zero"])
        if c["submitted_at"]:
            return Verdict(QUESTION, "submitted_hac_zero", {"when": _md_time(c["submitted_at"])}, ANSWERS["submitted_hac_zero"])

    # 5-6: a real HAC grade against Canvas's missing flag.
    if hs is not None and hs > 0 and c is not None and c["missing"]:
        kind = "missing_after_grade" if outcomes.newer(c, h) else "graded_in_hac"
        return Verdict(QUESTION if kind == "missing_after_grade" else DECIDED, kind, {"hac": _of(hs, points)}, ANSWERS[kind])

    # 7-8: both have a score and HAC is lower.
    credit = _credit_fraction(rules.resolve(item["kid"], item["course_name"]).credit)
    scored = _scores(c, h, points, credit)
    if scored is not None:
        return scored

    return _waiting_or_status(item, c, h, now=now, rules=rules, refresh_times=refresh_times, prefer=prefer, obs=obs)


def _waiting_or_status(item, c, h, *, now, rules, refresh_times, prefer, obs) -> Verdict:
    """Rules 9-15. Replaced in Task 4; until then everything left is a status."""
    return Verdict(STATUS, outcomes.classify(item, obs, now, prefer=prefer))

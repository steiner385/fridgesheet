"""One verdict per item: what the app concluded, and whether the family has anything to do.

The Reconcile page used to raise a "case" for every way Canvas and HAC differed, and asked
about all of them. Most needed nobody: a grade that has not flowed to HAC yet will flow, and
a teacher who graded only in HAC graded it. A verdict has one of four states. `decided`
means the records settle it and the app says why. `waiting` means time will settle it.
`question` means the family can do something. `status` is a plain fact. The rules below
run in order; the first that matches wins (docs/superpowers/specs/
2026-09-23-questions-not-cases-design.md, section 4.1).
The two grace periods (HAC catching up; paper work with no grade) are not a fixed week: they are
what this class's history says it usually takes (web/pace.py), and the card says so.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..open_items import HANDLED_FLAGS, MARKED_FLAGS
from . import outcomes, pace as _pace, phrasing, reconcile

QUESTION, DECIDED, WAITING, STATUS = "question", "decided", "waiting", "status"
TOLERANCE = 0.5


@dataclass(frozen=True)
class Answer:
    key: str                # phrase key for the button label
    action: str             # a flag, "confirm", "clear", or a plan action ("plan:today", "plan:tomorrow")


PLAN_ACTIONS = ("plan:today", "plan:tomorrow")
ACTIONS = HANDLED_FLAGS + MARKED_FLAGS + ("confirm", "clear") + PLAN_ACTIONS


@dataclass(frozen=True)
class Verdict:
    state: str
    kind: str
    facts: dict = field(default_factory=dict)      # values for the "facts.<kind>" phrase
    answers: tuple[Answer, ...] = ()
    asks_on: date | None = None                    # waiting only: the day it becomes a question
    #: The learned pace behind a grace period, for the "pace.*" sentence (spec 4.6); None when
    #: no grace period governs this verdict. Keys: which, days, n, scope, what, by, elapsed, passed.
    pace: dict | None = None


ASK = Answer("a.ask_teacher", "ask_teacher")
TODAY, TOMORROW = Answer("a.today", "plan:today"), Answer("a.tomorrow", "plan:tomorrow")

#: A family answer said back in family words, never the stored flag name ("ignore").
FLAG_WORDS = {"done": "it's done", "excused": "excused", "ignore": "let it go",
              "follow_up": "follow up", "ask_teacher": "ask the teacher", "too_late": "too late to submit"}
TOO_LATE = Answer("a.too_late", "too_late")
ANSWERS = {
    "missing_after_grade": (Answer("a.hac_right_done", "done"), ASK),
    "graded_in_hac": (Answer("a.hac_right_done", "done"), ASK),
    "hac_lower": (ASK, Answer("a.hac_right", "ignore")),
    "scores_explained": (ASK, Answer("a.hac_right", "ignore")),
    "submitted_hac_zero": (ASK, Answer("a.zero_right", "ignore")),
    "excused_hac_zero": (ASK, Answer("a.leave_it", "ignore")),
    "hac_still_blank": (ASK, Answer("a.its_fine", "ignore")),
    "hac_lag": (ASK,),
    "teacher_grading": (ASK,),
    "still_ungraded": (Answer("a.handed_in", "done"), TODAY, TOMORROW, ASK),
    "awaiting_grade": (ASK,),
    "stale_answer": (Answer("a.still_done", "confirm"), Answer("a.reopen", "clear"), ASK),
    # The family asked the teacher (or chose to follow up) and a grade has since appeared:
    # "still done?" would be the wrong question, and "ask the teacher" would change nothing.
    "asked_then_graded": (Answer("a.its_done", "done"), Answer("a.keep_asking", "confirm")),
    "followed_up_then_graded": (Answer("a.keep_following", "confirm"), Answer("a.its_done", "done")),
    # Statuses that still offer a one-tap answer (#74): these are not questions and are not
    # counted, but a red row must not leave "it's handed in" behind the raw flag menu.
    "not_done": (Answer("a.handed_in_behind", "done"), TODAY, TOMORROW, TOO_LATE),
    "past_credit": (Answer("a.let_go", "ignore"), Answer("a.handed_in_behind", "done"), TODAY, TOO_LATE),
    # Upcoming or undated work with nothing handed in: the plan is the answer (spec 6.2).
    "not_due_yet": (TODAY, TOMORROW, Answer("a.handed_in_behind", "done"), TOO_LATE),
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


def _stale_change(flag, set_at, c, h, refresh_times, prev=None, points=None) -> tuple[str, bool] | None:
    """What the school recorded after the family's answer that contradicts it, as (text, good),
    or None. `good` is a grade above zero or Canvas dropping its missing mark: for a follow-up,
    that answers the reminder (spec 5).

    For an ask or a follow-up, `prev` (each source's observation before its latest) tells a real
    change from a quiet one: Canvas dropping its missing mark closes the loop, and so does a grade
    that moved -- but a record that changed some other field while keeping the same score does
    not, and says nothing (#73)."""
    prev = prev or {}
    if flag in HANDLED_FLAGS:
        if c is not None and _after(c, set_at, refresh_times) and (c["missing"] or (c["state"] == "graded" and c["score"] == 0)):
            return ("Canvas now says missing" if c["missing"] else "Canvas now shows a zero"), False
        if h is not None and _after(h, set_at, refresh_times) and h["score"] == 0:
            return "HAC now shows a zero", False
    if flag in MARKED_FLAGS:
        for label, o in (("Canvas", c), ("HAC", h)):
            if o is None or not _after(o, set_at, refresh_times):
                continue
            before = prev.get(label.lower())
            if label == "Canvas" and before is not None and before["missing"] and not o["missing"]:
                # Missing replaced by a graded 0 is not good news; missing simply lifted is.
                return "Canvas no longer marks it missing", o["score"] is None or o["score"] > 0
            if o["score"] is not None:
                if before is None or before["score"] is None:
                    return f"{label} has graded it: {_of(o['score'], points)}", o["score"] > 0
                if abs(before["score"] - o["score"]) > TOLERANCE:
                    return f"{label} changed the grade: {_n(before['score'])} → {_of(o['score'], points)}", o["score"] > 0
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


def verdict(item, obs, *, flag, flag_set_at, now, rules, refresh_times, prefer="canvas", prev_obs=None, pace=None) -> Verdict:
    pace = pace or _pace.DEFAULT
    c, h = obs.get("canvas"), obs.get("hac")
    points = item["points"]
    hs = h["score"] if h is not None else None

    # 1-2b: the family's own answer, unless the school has since contradicted it.
    if flag:
        change = _stale_change(flag, flag_set_at, c, h, refresh_times, prev_obs, points)
        if change:
            text, good = change
            kind = {"ask_teacher": "asked_then_graded", "follow_up": "followed_up_then_graded"}.get(flag, "stale_answer")
            # A follow-up is the family's own reminder; good news answers it. The flag stays:
            # the app never records a family answer on the family's behalf.
            state = DECIDED if (flag == "follow_up" and good) else QUESTION
            return Verdict(state, kind,
                           {"flag": FLAG_WORDS.get(flag, flag.replace("_", " ")), "when": _md(flag_set_at), "change": text},
                           ANSWERS[kind])
        if flag in HANDLED_FLAGS:
            return Verdict(STATUS, "answered", {"when": _md(flag_set_at)} if flag_set_at else {})
        # "follow up" is the family's own reminder; only "ask teacher" means someone asked.
        return Verdict(STATUS, "asked" if flag == "ask_teacher" else "following_up",
                       {"when": _md(flag_set_at)} if flag_set_at else {})

    # 3-4: HAC counts a zero that Canvas says should not be there.
    if c is not None and h is not None and hs == 0 and (points or 0) > 0:
        if c["excused"]:
            return Verdict(QUESTION, "excused_hac_zero", {}, ANSWERS["excused_hac_zero"])
        # A submission Canvas itself scored 0 is a zero both gradebooks agree on: no question.
        if c["submitted_at"] and c["score"] != 0:
            return Verdict(QUESTION, "submitted_hac_zero", {"when": _md_time(c["submitted_at"])}, ANSWERS["submitted_hac_zero"])

    # 5-6: a real HAC grade against Canvas's missing flag.
    if hs is not None and hs > 0 and c is not None and c["missing"]:
        # Under the HAC preference the family already told us HAC decides this class, so a later
        # Canvas mark is not a question for them (and `classify` counts it done).
        kind = "missing_after_grade" if outcomes.newer(c, h) and prefer != "hac" else "graded_in_hac"
        return Verdict(QUESTION if kind == "missing_after_grade" else DECIDED, kind, {"hac": _of(hs, points)}, ANSWERS[kind])

    # 7-8: both have a score and HAC is lower.
    credit = _credit_fraction(rules.resolve(item["kid"], item["course_name"]).credit)
    scored = _scores(c, h, points, credit)
    if scored is not None:
        return scored

    return _waiting_or_status(item, c, h, now=now, rules=rules, refresh_times=refresh_times, prefer=prefer, obs=obs, pace=pace)


#: What the count is attributed to, by scope. The subject is always Fridge Sheet's count.
WHAT = {_pace.COURSE_KIND: "assignments in this class", _pace.COURSE: "assignments in this class",
        _pace.TEACHER: "assignments from this teacher", _pace.DEFAULT_SCOPE: "assignments in this class"}


def _pace_facts(est: _pace.Estimate, which: str, anchor: date, now: datetime) -> dict:
    by = anchor + timedelta(days=est.days)
    elapsed = (now.date() - anchor).days
    return {"which": which, "days": est.days, "n": est.n, "scope": est.scope, "what": WHAT[est.scope],
            "by": f"{by:%a} {by.month}/{by.day}", "elapsed": f"{elapsed} day{'' if elapsed == 1 else 's'}",
            "passed": elapsed >= est.days}


def pace_key(v: Verdict) -> str | None:
    """Which "pace.*" sentence a verdict's pace calls for, or None."""
    p = v.pace
    if not p:
        return None
    prefix = "pace.hac_" if p["which"] == "hac" else "pace."
    if p["scope"] == _pace.DEFAULT_SCOPE:
        return prefix + "default"
    return prefix + ("passed" if p["passed"] else "expect")


def _waiting_or_status(item, c, h, *, now, rules, refresh_times, prefer, obs, pace) -> Verdict:
    """Rules 9-15: what time will settle, and the plain facts left over."""
    outcome = outcomes.classify(item, obs, now, prefer=prefer)
    points = item["points"]
    due = reconcile.due_of(item)
    cs = c["score"] if c is not None else None
    hs = h["score"] if h is not None else None

    # The outcome is the one definition (docs/outcomes.md): excused or unpublished work is never
    # waited on, and neither is work the teacher marked missing or scored zero.
    if outcome in (outcomes.EXCUSED, outcomes.UNPUBLISHED):
        return Verdict(STATUS, outcome)
    settled_not_done = outcome == outcomes.NOT_DONE

    # 9-10: Canvas graded it and HAC, which this class has, still has nothing. How long to
    # allow is what this class's history says HAC usually takes (spec 4.5).
    if not settled_not_done and cs is not None and cs > 0 and hs is None and item["peer_course_id"] is not None:
        seen = _observed_at(c, refresh_times)
        if seen is not None:
            est = pace.hac_days(item)
            asks_on = seen.date() + timedelta(days=est.days)
            facts_p = _pace_facts(est, "hac", seen.date(), now)
            if now.date() >= asks_on:
                return Verdict(QUESTION, "hac_still_blank", {"canvas": _of(cs, points), "when": f"{seen.month}/{seen.day}"},
                               ANSWERS["hac_still_blank"], pace=facts_p)
            return Verdict(WAITING, "hac_lag", {"canvas": _of(cs, points)}, ANSWERS["hac_lag"], asks_on=asks_on, pace=facts_p)

    # 11: handed in online, no grade anywhere. Still waits without asking; the pace sentence
    # shows so the family sees the count before the app acts on it (spec section 8).
    if not settled_not_done and c is not None and c["submitted_at"] and cs is None and hs is None:
        submitted = reconcile._parse_ts(c["submitted_at"]).date()
        return Verdict(WAITING, "teacher_grading", {"when": _md(c["submitted_at"])}, ANSWERS["teacher_grading"],
                       pace=_pace_facts(pace.grade_days(item), "grade", submitted, now))

    # 12-13: nothing to submit online, past due, no grade anywhere.
    if outcome == outcomes.UNKNOWN and due is not None:
        est = pace.grade_days(item)
        asks_on = due.date() + timedelta(days=est.days)
        facts = {"kind": item["kind"] or "HAC-only", "due": f"{due:%a} {due.month}/{due.day}"}
        facts_p = _pace_facts(est, "grade", due.date(), now)
        if now.date() >= asks_on:
            return Verdict(QUESTION, "still_ungraded", facts, ANSWERS["still_ungraded"], pace=facts_p)
        return Verdict(WAITING, "awaiting_grade", facts, ANSWERS["awaiting_grade"], asks_on=asks_on, pace=facts_p)

    # 14: not done and past the late-work window.
    if outcome == outcomes.NOT_DONE and due is not None:
        late, deadline = reconcile._comparable(now, rules.deadline(item["kid"], item["course_name"], due))
        if late > deadline:
            return Verdict(STATUS, "past_credit", {"school": _school_says(c, h, points)}, ANSWERS["past_credit"])

    # 15: a plain outcome. Work the school recorded as not done still offers a one-tap answer,
    # and so does work not yet due: `classify` only says NOT_DUE when nothing is handed in.
    if outcome == outcomes.NOT_DONE:
        return Verdict(STATUS, outcome, {"school": _school_says(c, h, points)}, ANSWERS["not_done"])
    if outcome == outcomes.NOT_DUE:
        return Verdict(STATUS, outcome, {}, ANSWERS["not_due_yet"])
    return Verdict(STATUS, outcome)


def _school_says(c, h, points) -> str:
    """The school's own record of not-done work, attributed: never the app's inference."""
    if c is not None and c["missing"]:
        return "Canvas marks it missing"
    if c is not None and c["score"] == 0:
        return f"Canvas shows {_of(0, points)}"
    if h is not None and h["score"] == 0:
        return f"HAC shows {_of(0, points)}"
    return "Nothing is handed in on Canvas"


def say(key: str, tier: str, values: dict | None = None) -> str:
    """The words for `key` at `tier`, with the verdict's facts filled in. The template's
    autoescaping applies to the result, so a value is never markup."""
    text = phrasing.phrase(key, tier).format(**(values or {}))
    return text[:1].upper() + text[1:]      # a sentence may open with a value ("paper work, ...")


def standing(item, tier: str) -> str:
    """Where an item stands, in words: the verdict's own phrase when it has one, else the
    grade, else the status word. Never a raw phrase key."""
    kind = item.verdict.kind
    if kind == "answered" and item.verdict.facts.get("when"):
        kind = {"done": "done", "excused": "excused", "ignore": "let_go", "too_late": "too_late"}.get(getattr(item, "flag", None) or "", kind)
    key = "where." + kind
    if key in phrasing.PHRASES and ("{when}" not in phrasing.phrase(key, tier) or item.verdict.facts.get("when")):
        return say(key, tier, item.verdict.facts)
    if item.grade:
        where = {"canvas": "Canvas", "hac": "HAC"}.get(getattr(item, "grade_source", ""), "")
        return phrasing.phrase(item.grade, tier) + (f" · {where}" if where else "")
    return phrasing.phrase(item.status, tier)


def has_phrase(key: str) -> bool:
    return key in phrasing.PHRASES


def family_facts(v: Verdict) -> dict:
    """A verdict's facts with any stored flag name turned into family words."""
    facts = dict(v.facts)
    if "flag" in facts:
        facts["flag"] = FLAG_WORDS.get(facts["flag"], facts["flag"])
    return facts

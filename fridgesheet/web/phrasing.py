"""One table of words, three columns wide.

A child reads the same rows an adult does. What changes is how much vocabulary the row
assumes they already have -- `past credit` and `disagree` are accurate and useless to a
ten-year-old who has not been taught the model they belong to.

Every younger phrase is the same fact in fewer words. None adds a claim: "Teacher hasn't got
it" is what Canvas's `missing` flag means, and it is not a verdict on the child. A phrase
that states a time, a date or a number its adult equivalent does not is a bug, and a test
holds the whole table to that.

The table lives here rather than in the templates because a vocabulary expressed as
`{% if tier == 'early' %}` across fifteen files is the same vocabulary implemented fifteen
times, which is the pattern this codebase rejects everywhere else.
"""
from __future__ import annotations

#: concept -> tier -> the words. `older` is what ships today, so the empty tier and `older`
#: read identically; they are separate so a later change to `older` leaves the households
#: that set no grade alone.
PHRASES: dict[str, dict[str, str]] = {
    # --- the status word on a row -----------------------------------------------------
    "Missing":             {"early": "Teacher hasn't got it", "middle": "Marked missing", "older": "Missing"},
    "Zero":                {"early": "Marked zero - ask about it", "middle": "Scored zero", "older": "Zero"},
    "Paper, check":        {"early": "On paper - check if it's handed in", "middle": "Paper - check whether it was handed in", "older": "Paper, check"},
    "In class, check":     {"early": "In class - check if it's handed in", "middle": "In class - check whether it was handed in", "older": "In class, check"},
    "Late, ungraded":      {"early": "Handed in late, no grade yet", "middle": "Late, not graded", "older": "Late, ungraded"},
    "Submitted, ungraded": {"early": "Handed in - waiting", "middle": "Submitted, not graded", "older": "Submitted, ungraded"},
    "Unpublished":         {"early": "Not open yet", "middle": "Not published", "older": "Unpublished"},
    # --- the two "Handed in" cells that are neither yes nor no -------------------------
    # Neither may imply the work was done. "On paper" says only that the assignment is not
    # an online one; "Done on paper" would assert a fact no source gave us.
    "On paper":            {"early": "This one is on paper", "middle": "On paper, not online", "older": "On paper"},
    "Unknown":             {"early": "We can't tell", "middle": "Not recorded", "older": "Unknown"},
    # --- the badge that means "you can still do something about this" -----------------
    "actionable":          {"early": "Can still fix", "middle": "Still fixable", "older": "actionable"},
    # --- verdicts: what the records show (facts), what we ask, the answers, where it stands --
    "facts.missing_after_grade": {"early": "HAC has {hac}, but Canvas marked it missing after that.", "middle": "HAC has {hac}, but Canvas marked it missing after that.", "older": "HAC has {hac}, but Canvas marked it missing after that."},
    "facts.graded_in_hac":   {"early": "HAC has {hac}. Canvas still says missing, but HAC has the teacher's grade.", "middle": "HAC has {hac}. Canvas still says missing; HAC has the teacher's grade.", "older": "HAC has {hac}. Canvas still says missing; HAC has the teacher's grade."},
    "facts.hac_lower":       {"early": "Canvas has {canvas}. HAC has {hac}.", "middle": "Canvas has {canvas}. HAC has {hac}.", "older": "Canvas has {canvas}. HAC has {hac}."},
    "facts.scores_explained": {"early": "The scores differ ({why}), and that's expected.", "middle": "The scores differ because of the {why} rule.", "older": "Canvas and HAC differ, explained by the {why} rule."},
    "facts.submitted_hac_zero": {"early": "You handed it in on {when}. HAC shows a zero.", "middle": "Handed in on Canvas {when}. HAC counts a zero.", "older": "Handed in on Canvas {when}. HAC counts a zero."},
    "facts.excused_hac_zero": {"early": "Your teacher excused it, but HAC shows a zero.", "middle": "Excused in Canvas, but HAC counts a zero.", "older": "Excused in Canvas. HAC counts a zero."},
    "facts.hac_still_blank": {"early": "Canvas has {canvas} since {when}. HAC doesn't have it yet.", "middle": "Canvas has {canvas} since {when}. HAC still has nothing.", "older": "Canvas graded it {canvas} on {when}. HAC still has nothing."},
    "facts.hac_lag":         {"early": "Canvas has {canvas}. HAC will catch up.", "middle": "Canvas has {canvas}; waiting for HAC.", "older": "Canvas has {canvas}; waiting for HAC to catch up."},
    "facts.teacher_grading": {"early": "Handed in {when}, waiting for a grade.", "middle": "Handed in {when}, not graded yet.", "older": "Handed in {when}, waiting for the teacher to grade it."},
    "facts.still_ungraded":  {"early": "This was {kind} work, due {due}. There's still no grade.", "middle": "{kind} work, due {due}. Still no grade anywhere.", "older": "{kind} work, due {due}. A week on, no grade anywhere."},
    "facts.awaiting_grade":  {"early": "This was {kind} work, due {due}. No grade yet.", "middle": "{kind} work, due {due}. No grade yet.", "older": "{kind} work, due {due}. No grade yet; grading paper takes time."},
    "facts.stale_answer":    {"early": "On {when} you said “{flag}”. {change}.", "middle": "On {when} you said “{flag}”. {change}.", "older": "On {when} your answer was “{flag}”. {change}."},
    "ask.missing_after_grade": {"early": "Which one is right?", "middle": "Which is right?", "older": "Which is right?"},
    "ask.hac_lower":         {"early": "Should we ask your teacher?", "middle": "Ask the teacher to fix HAC?", "older": "Ask the teacher to fix HAC?"},
    "ask.submitted_hac_zero": {"early": "Should we tell your teacher?", "middle": "Tell the teacher?", "older": "Tell the teacher?"},
    "ask.excused_hac_zero":  {"early": "Should we ask your teacher?", "middle": "Ask to have it excused in HAC?", "older": "Ask to have it excused in HAC?"},
    "ask.hac_still_blank":   {"early": "Should we ask your teacher?", "middle": "Ask the teacher to enter it?", "older": "Ask the teacher to enter it?"},
    "ask.still_ungraded":    {"early": "Did you hand it in?", "middle": "Was it handed in?", "older": "Was it handed in?"},
    "ask.stale_answer":      {"early": "Is it still done?", "middle": "Still done?", "older": "Still done?"},
    "facts.asked_then_graded": {"early": "You asked the teacher on {when}. {change}.", "middle": "You asked the teacher on {when}. {change}.", "older": "You asked the teacher on {when}. {change}."},
    "ask.asked_then_graded": {"early": "Is it all sorted now?", "middle": "Is it settled?", "older": "Is it settled?"},
    "a.its_done":            {"early": "Yes, it's done", "middle": "Yes, it's done", "older": "Yes, it's done"},
    "a.keep_asking":         {"early": "No, keep asking", "middle": "Not settled, keep asking", "older": "Not settled, keep asking"},
    "where.asked_then_graded": {"early": "Graded since you asked", "middle": "Graded since you asked", "older": "Graded since you asked"},
    "facts.followed_up_then_graded": {"early": "You were following up on this since {when}. {change}.", "middle": "You were following up since {when}. {change}.", "older": "You were following up since {when}. {change}."},
    "ask.followed_up_then_graded": {"early": "Is it all sorted now?", "middle": "Is it settled?", "older": "Is it settled?"},
    "a.keep_following":      {"early": "No, keep checking", "middle": "Not settled, keep following up", "older": "Not settled, keep following up"},
    "where.followed_up_then_graded": {"early": "Graded since you checked", "middle": "Graded since you started following up", "older": "Graded since you started following up"},
    "where.following_up":    {"early": "Checking on it since {when}", "middle": "Following up since {when}", "older": "Following up since {when}"},
    "a.ask_teacher":         {"early": "Ask the teacher", "middle": "Ask the teacher", "older": "Ask the teacher"},
    "a.hac_right_done":      {"early": "HAC is right, it's done", "middle": "HAC is right, it's done", "older": "HAC is right, it's done"},
    "a.hac_right":           {"early": "HAC is right", "middle": "HAC is right", "older": "HAC is right"},
    "a.zero_right":          {"early": "The zero is right", "middle": "The zero is right", "older": "The zero is right"},
    "a.leave_it":            {"early": "Leave it", "middle": "Leave it", "older": "Leave it"},
    "a.its_fine":            {"early": "It's fine", "middle": "It's fine", "older": "It's fine"},
    "a.handed_in":           {"early": "Yes, I handed it in", "middle": "Yes, handed in", "older": "Yes, handed in"},
    # --- one-tap answers: plan it, and what the done-line then says (spec 6) --------------
    "a.today":               {"early": "Today", "middle": "Today", "older": "Today"},
    "a.tomorrow":            {"early": "Tomorrow", "middle": "Tomorrow", "older": "Tomorrow"},
    "a.add_details":         {"early": "Add details", "middle": "Add details", "older": "Add details"},
    "step.work_on_it":       {"early": "Work on it", "middle": "Work on it", "older": "Work on it"},
    "where.planned_today":   {"early": "You'll work on it today", "middle": "Planned for today", "older": "Planned for today"},
    "where.planned_tomorrow": {"early": "You'll work on it tomorrow", "middle": "Planned for tomorrow", "older": "Planned for tomorrow"},
    "where.planned_kept":    {"early": "Your step was edited since, so it stays", "middle": "The step was edited since, so it stays", "older": "The step was edited since, so it stays"},
    "facts.not_due_yet":     {"early": "Nothing handed in yet.", "middle": "Nothing handed in yet.", "older": "Nothing handed in yet."},
    "a.still_done":          {"early": "Yes, still done", "middle": "Yes, still done", "older": "Yes, still done"},
    "a.reopen":              {"early": "No, open it again", "middle": "No, reopen it", "older": "No, reopen it"},
    "where.answered":        {"early": "You answered this", "middle": "Answered", "older": "Answered"},
    "where.asked":           {"early": "Asked the teacher on {when}", "middle": "Asked the teacher on {when}", "older": "Asked the teacher on {when}"},
    "where.done":            {"early": "You said it's done, {when}", "middle": "Marked done on {when}", "older": "Marked done on {when}"},
    "where.excused":         {"early": "Excused, {when}", "middle": "Marked excused on {when}", "older": "Marked excused on {when}"},
    "where.let_go":          {"early": "Let go, {when}", "middle": "Let go on {when}", "older": "Let go on {when}"},
    "facts.asked":           {"early": "You asked the teacher on {when}.", "middle": "You asked the teacher on {when}.", "older": "You asked the teacher on {when}."},
    "facts.following_up":    {"early": "You've been checking on this since {when}.", "middle": "You're following up since {when}.", "older": "You're following up since {when}."},
    "facts.not_done":        {"early": "{school}.", "middle": "{school}.", "older": "{school}."},
    "facts.past_credit":     {"early": "{school}, and the late date has passed.", "middle": "{school}, and the late-work window has closed.", "older": "{school}, and the late-work window has closed."},
    "a.handed_in_behind":    {"early": "I handed it in", "middle": "It's handed in", "older": "It's handed in"},
    "a.let_go":              {"early": "Let it go", "middle": "Let it go", "older": "Let it go"},
    "where.past_credit":     {"early": "{school} · late date passed", "middle": "{school} · past the late-work window", "older": "{school} · past the late-work window"},
    "where.teacher_grading": {"early": "Handed in, waiting", "middle": "Handed in, not graded", "older": "Handed in, not graded"},
    "where.awaiting_grade":  {"early": "Waiting for a grade", "middle": "Waiting for a grade", "older": "Waiting for a grade"},
    "where.hac_lag":         {"early": "Waiting for HAC", "middle": "Waiting for HAC", "older": "Graded in Canvas, not yet in HAC"},
    "where.graded_in_hac":   {"early": "Done: {hac} in HAC", "middle": "Done: {hac} in HAC", "older": "Done · {hac} in HAC"},
    "where.scores_explained": {"early": "Scores differ ({why}), that's expected", "middle": "Scores differ ({why})", "older": "Scores differ ({why} rule)"},
    "where.missing_after_grade": {"early": "Canvas says missing, HAC {hac}", "middle": "Canvas says missing, HAC {hac}", "older": "Missing in Canvas · {hac} in HAC"},
    "where.hac_lower":       {"early": "HAC {hac}, Canvas {canvas}", "middle": "HAC {hac}, Canvas {canvas}", "older": "HAC {hac}, Canvas {canvas}"},
    "where.submitted_hac_zero": {"early": "Handed in, HAC shows zero", "middle": "Handed in · HAC shows zero", "older": "Handed in · HAC shows zero"},
    "where.excused_hac_zero": {"early": "Excused, HAC shows zero", "middle": "Excused · HAC shows zero", "older": "Excused · HAC shows zero"},
    "where.hac_still_blank": {"early": "Canvas {canvas}, not in HAC yet", "middle": "Canvas {canvas}, not in HAC yet", "older": "Canvas {canvas} · not in HAC"},
    "where.still_ungraded":  {"early": "No grade yet", "middle": "No grade, longer than usual", "older": "No grade, longer than usual"},
    "where.stale_answer":    {"early": "This changed after you answered", "middle": "Changed since you answered", "older": "Changed since your answer"},
    # --- the learned pace: Fridge Sheet's own count, never the school's word (spec 4.6) ----
    "pace.expect":      {"early": "Fridge Sheet counted {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}."},
    "pace.passed":      {"early": "Fridge Sheet counted {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}."},
    "pace.default":     {"early": "Fridge Sheet has no earlier grades from this class to go on, so it allows {days} days.",
                         "middle": "Fridge Sheet has no earlier grades from this class to go on, so it allows {days} days.",
                         "older": "Fridge Sheet has no earlier grades from this class to go on, so it allows {days} days."},
    "pace.hac_expect":  {"early": "Fridge Sheet counted {n} earlier {what}: HAC usually catches up within about {days} days, so look for it by {by}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days, so look for it by {by}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days, so look for it by {by}."},
    "pace.hac_passed":  {"early": "Fridge Sheet counted {n} earlier {what}: HAC usually catches up within about {days} days. It has been {elapsed}.",
                         "middle": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days. It has been {elapsed}.",
                         "older": "Fridge Sheet's count from {n} earlier {what}: HAC usually catches up within about {days} days. It has been {elapsed}."},
    "pace.hac_default": {"early": "Fridge Sheet has no earlier HAC grades from this class to go on, so it allows {days} days.",
                         "middle": "Fridge Sheet has no earlier HAC grades from this class to go on, so it allows {days} days.",
                         "older": "Fridge Sheet has no earlier HAC grades from this class to go on, so it allows {days} days."},
}


def phrase(word: str, tier: str, *, table: dict[str, dict[str, str]] | None = None) -> str:
    """`word` said for `tier`.

    Two fallbacks, both to the word that ships today rather than to a blank: a concept in the
    table with nothing for this tier -- including the empty tier, which is not a key any entry
    defines -- yields its `older` entry, and a concept absent from the table yields `word`
    unchanged. A word nobody has translated is shown as it is; it is never dropped. This is
    also why a household with no grade set (`tier == ""`) sees the same words as one on the
    `older` tier: `by_tier.get("")` is `None` for every entry, so it falls through to `older`.
    """
    by_tier = (table if table is not None else PHRASES).get(word)
    if not by_tier:
        return word
    return by_tier.get(tier) or by_tier.get("older") or word

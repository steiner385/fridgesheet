# Learned pace and one-tap answers: the check-in knows the teacher and asks for one tap: design

Date: 2026-09-23. Status: design approved in discussion; awaiting review of this document.
Builds on "Questions, not cases" (`2026-09-23-questions-not-cases-design.md`), whose verdict
rules this amends, and on PRs #80, #81 and #83, which put answers on the cards. Respects the
data-correctness capability (`docs/product/features/data-correctness.md`): nothing here
puts the app's own guess in the school's mouth.

## 1. Goal

Doug opens his check-in and sees twenty-one cards. He already knows which ones he handed
in. He also knows that his AP Human Geography teacher grades reading guides in a batch a
week or two after they are due, and that Concert Band never records a Canvas submission
for anything. The app knows none of this, so it waits the same seven days on every class
and then asks "was it handed in?" about work that is simply on the teacher's desk. And when
Doug wants to say "I'll do that tonight", the only way is a link to a form on another page.

After this change:

1. **The app learns each class's pace from its own history.** For every course and kind of
   work, it measures how long a grade usually takes to appear, and how long Canvas grades
   take to reach Home Access Center (HAC). Cards wait for that long, not a fixed week, and
   they say so: "This class usually has a grade within about 5 days, so look for it by Fri
   9/26." The estimate is always labelled as Fridge Sheet's own count.
2. **Every disposition is one tap on the card.** "Today", "Tomorrow", "It's handed in" and
   "Ask the teacher" each record the answer where Doug is standing, on every card that can
   take one, not only the ones the app has a question about.

The kid is the primary reader. Everything on the card is said in the reading tier the
household set (`phrasing.py`), and the page is meant to be usable by Doug alone as well as
in a parent-and-kid check-in.

## 2. Decisions taken in discussion

| Question | Decision |
|---|---|
| How far does inference go? | **Delay and explain.** The learned pace changes *when* a card becomes a question, and the card says what the app expects and why. The app never pre-picks a disposition for the family |
| Where is the pace computed? | At render time, from the observation history. No schema change, no ingest change, no stored model |
| Manual per-course pace settings? | Not in this design. Could later sit above the learned number as an override |
| A follow-up overtaken by a grade above zero | Becomes *decided*, not a question. An "ask the teacher" overtaken by a grade stays a question |
| The wrap-up's "What we agreed" box | Unchanged; still typed |
| Pooling history across kids | By exact teacher name only, and only as a fallback |

## 3. What Doug sees today

The live check-in (`/kids/Douglas/check-in`) sorts work into Questions, Waiting on the
school and To do. Questions and the school's own not-done rows carry answer buttons
(`_answers.html`). Every other card, including all twelve upcoming ones, ends in a single
link to the plan-step form. Five of Doug's eight questions are paper work from classes whose
teachers post grades late, asked after a fixed seven days. One card shows 5 of 5 with Doug
still "following up since 9/20" and asks him whether it is settled.

## 4. The learned pace

### 4.1 Samples

Every refresh writes an observation row per item and source only when a field changed
(`ingest.py`), so the first row that carries a score is when the app first saw a grade. The
pace module reads those rows for one kid and turns them into samples:

**Grade lag.** For each item, take the earliest observation in either source with a score
above zero. Its refresh's `started_at` is *seen*. The *anchor* is the Canvas `submitted_at`
when the item has one, otherwise the item's due date. The sample is
`max(0, seen.date() - anchor.date())` in days. An item contributes at most one grade-lag
sample, so the count on the card is a count of assignments. (Review of the first build: one
sample per source let an item Canvas had graded before the app existed re-enter through its
HAC twin as a due-anchored sample, and inflated the count.)

**HAC lag.** For an item with a first-scored observation in both sources, the sample is
`max(0, hac_seen.date() - canvas_seen.date())`.

**Censoring.** Work the app started watching after it was already graded tells nothing
about pace: if the first-scored observation belongs to the same refresh as the item's
`first_seen`, the item is not a sample, in either source. Items with no anchor (no due date
and no submission) are not samples. Items that have not been graded yet are not samples;
they are what the estimate is for.

A score of exactly zero is not a grade for this purpose. HAC writes placeholder zeros the
moment work is missing, and learning from them would teach the app that every teacher
grades instantly.

### 4.2 Grouping

Samples are keyed by `(course_id, kind_group)`, where `kind_group` is `online` when the
item's kind is `online` and `offline` for `paper`, `in class` and the empty kind that
HAC-only items carry. Online work is graded on a different rhythm from a stack of paper,
and that difference is most of what the app is meant to learn.

### 4.3 The estimate

`pace.estimate(samples) -> int | None` is one small function and the only tunable in the
module. It returns the number of days to allow, or `None` when the samples are too few.
Defaults:

- **Minimum samples:** 3. Fewer, and the group does not get its own number.
- **Statistic:** the 80th percentile by nearest rank. A high percentile, not the mean, so
  one slow week does not make the app nag, and one fast week does not make it ask early.
- **Floor and cap:** at least 1 day, at most 21. A teacher who grades once a quarter does
  not get to silence a real problem for a quarter.

The household can change these three numbers in that one function; nothing else in the
app knows them.

### 4.4 Fallback chain

`Pace.grade_days(item)` and `Pace.hac_days(item)` each return a `Estimate(days, n, scope)`:

1. this course and kind group, when `estimate` returns a number;
2. else this course with all kinds pooled; for grade lag, online work only (a class's auto-graded
   quizzes must not teach the app that its paper is graded the same day);
3. else every course in the household whose `courses.teacher` matches this course's
   teacher name (trimmed, case-insensitive), same kind group;
4. else the default: 7 days, `n = 0`, scope `default`.

`scope` is one of `course_kind`, `course`, `teacher`, `default`, and is what the card
attributes the number to.

### 4.5 Where verdicts change

`verdicts.verdict` gains a `pace` argument, passed from the items store the way `rules` is.
Two rules that use `GRACE_DAYS` today use the learned number instead:

| Rule | Today | After |
|---|---|---|
| 9–10 `hac_lag` → `hac_still_blank` | Canvas grade seen + 7 days | Canvas grade seen + `pace.hac_days(item)` |
| 12–13 `awaiting_grade` → `still_ungraded` | due + 7 days | due + `pace.grade_days(item)` |

`GRACE_DAYS` stays as the default the chain bottoms out on. No other rule moves. In
particular rule 11, `teacher_grading` (handed in online, no grade anywhere), still waits
without ever becoming a question; that is a separate change (section 8).

### 4.6 What the card says

Every waiting verdict that a pace governs, and every question that a pace turned into a
question, carries a `pace` fact on the `Verdict`: `days`, `n`, `scope`, `expect_by` (the
`asks_on` date) and `elapsed` (days since the anchor). `teacher_grading` also carries it,
for the sentence only, since its state does not change.

The card shows one sentence after the facts line, chosen by state:

| Key | Older tier | When |
|---|---|---|
| `pace.expect` | "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days, so look for it by {by}." | waiting, pace not yet passed |
| `pace.passed` | "Fridge Sheet's count from {n} earlier {what}: a grade usually shows up within about {days} days. It has been {elapsed}." | waiting or question, pace passed |
| `pace.default` | "Fridge Sheet has no earlier grades from this class to go on, so it allows a week." | scope is `default` |

`{what}` is "assignments in this class" for course scopes and "assignments from this
teacher" for the teacher scope. Every tier says the same numbers and dates; the early and
middle tiers shorten the words. The existing phrasing test, which forbids a younger tier
from stating a number its adult equivalent does not, holds these rows too.

The subject of every sentence is Fridge Sheet. The sentence never says the teacher will do
anything, and the school-record lines above it are untouched. That is what keeps this
within the data-correctness capability: the school's lines say what the school recorded,
and the app's line says what the app counted.

## 5. A follow-up overtaken by a grade

Today `_stale_change` reports any later record that contradicts a marked flag, and the
verdict becomes the question `followed_up_then_graded` or `asked_then_graded`, "Is it
settled?"

After this change, `_stale_change` also says whether the change is *good news*: a score
above zero, or Canvas dropping its missing mark. For a `follow_up` flag with good news the
verdict is **decided**, kind `followed_up_then_graded`, facts unchanged, and its answers are
`(a.keep_following → confirm, a.its_done → done)` so "not settled" is still one tap
wherever answers render. The flag is not cleared: the app never records a family answer on
the family's behalf. The card simply stops being a question and leaves the review queue.

A `follow_up` overtaken by bad news (a zero, or a new missing mark) stays a question, as
does any `ask_teacher` flag: a person is waiting on a reply, and only they know whether it
came.

## 6. One-tap answers on every card

### 6.1 The answer model

`Answer(key, action)` replaces `Answer(key, flag)`. `action` is a flag name, `confirm`,
`clear`, `plan:today` or `plan:tomorrow`. The `None` action, which today renders a link to
the step form, is gone; the form stays reachable through an "Add details" link on every
card (section 6.4).

### 6.2 Which cards offer what

| Verdict kind | Answers, in order |
|---|---|
| `not_done` | It's handed in → `done` · Today · Tomorrow |
| `past_credit` | Let it go → `ignore` · It's handed in → `done` · Today |
| `still_ungraded` | Yes, handed in → `done` · Today · Tomorrow · Ask the teacher |
| `not_due_yet` (status: upcoming or undated, nothing handed in) | Today · Tomorrow · It's handed in → `done` |
| `teacher_grading`, `awaiting_grade`, `hac_lag` (waiting) | Ask the teacher |
| `followed_up_then_graded` (decided, section 5) | Not settled, keep following up → `confirm` · Yes, it's done → `done` |
| all other kinds | unchanged |

`not_due_yet` gets answers only when neither source shows a submission; work already handed
in before its due date has nothing to plan.

The check-in card renders `_answers.html` whenever the verdict has answers and no active
plan step covers the item, not only when `view.asks`. The "ask" prompt line above the
buttons stays a question-only element. The Questions page and the item detail keep their
current rule (questions only) so those pages do not fill with plan buttons for upcoming
work.

### 6.3 The plan answers

`POST /items/{id}/answer` with `answer=plan:today` or `plan:tomorrow` creates a plan step
through `plans.save` with these values:

| Field | Value |
|---|---|
| `title` | the item's name |
| `family_account` | the flag's reason and the newest note, as the step form pre-fills today |
| `next_step` | the phrase `step.work_on_it` for the kid's tier ("Work on it") |
| `owner` | the kid's nickname |
| `planned_for` | today or tomorrow in the household's time zone |
| `minutes` | none |
| `state` | `planned` |
| `position` | 10 |
| `evidence` | `plans.evidence(view)` |
| `recorded_by` | empty |
| `request_key` | a hidden field rendered once per card |

The hidden `request_key` is what makes a double-click or a retried POST land on one step:
`plans.save` already answers a repeated key with the existing row. Because the card is
replaced by the done-line on the first success, the second button of a pair is never
pressed with the same key and different words; if it somehow is, `plans.save` raises
`Conflict` and the route answers 409 with the card re-rendered and the message shown.

The route rejects a plan answer for an item that already has an active step (409, the card
re-rendered) rather than creating a second commitment.

### 6.4 The done-line and undo

The response is the same `_answered.html` done-line the flags use: "{name}: planned for
today" (`where.planned_today` / `where.planned_tomorrow`), an **Undo** button and an **Add
details** link to the step form for the new step. For flag answers the done-line is as it
is today.

`POST /items/{id}/undo` gains an optional `step_id`. When present, and the step belongs to
this kid and this item and its `revision` is still 1 (never edited), the step is deleted and
the card is re-rendered. An edited step is left alone and the card is re-rendered with the
step in place, which the queue then hides as covered.

### 6.5 The plan panel updates in place

The right-hand "Our next steps" panel moves from `checkin.html` into a `_plan_panel.html`
partial with an `id="plan"`. `_after_answer.html` includes it out of band whenever the
answer was a plan answer or an undo of one, so the step appears in the plan, the minute
total changes, and the card leaves the review queue without a reload. On pages without a
`#plan` element htmx drops the swap, as it does today for the question heading. The panel's
context comes from `checkin._context`, which the answer route calls only for plan answers.

Every card keeps a small "Add details" link to the step form (`/check-in/step?item_id=`),
replacing today's "Plan a step" button. It is the one place minutes, a different owner, a
different date or a family account can be typed.

## 7. Not in this design

- The wrap-up's "What we agreed" box still requires typed text.
- No manual per-course pace override; no settings page changes.
- No pooling across kids by teacher email; by teacher name only, as a fallback.
- No change to ingest, refresh or the schema.
- No new answers on the Questions page or the item detail beyond what their verdict kinds
  already carry from section 6.2.
- Rule 11 (`teacher_grading`) keeps waiting indefinitely (section 8).

## 8. Follow-ups this enables

- **Submitted, still ungraded.** With a learned online-work pace, `teacher_grading` could
  become a question ("handed in 9/18, this class usually grades online work within 4 days,
  it has been 12") with "Ask the teacher" and "It's fine". Left out to keep this change to
  the two rules already governed by a grace period; the sentence from section 4.6 already
  shows on these cards, so the family sees the pace before the app acts on it.
- **A pace override.** A per-course "this teacher grades in batches, wait N days" rule in
  the late-work register's style, consulted before the learned chain.
- **A default for "What we agreed."** The wrap-up could pre-fill its summary from the day's
  plan steps.

## 9. Files

| File | Change |
|---|---|
| `fridgesheet/web/pace.py` (new) | `Estimate`, `Pace`, `estimate()`, the fallback chain |
| `fridgesheet/web/stores/pace.py` (new) | the sample query: first-scored observations per item and source, joined to refresh times, item anchors, course teacher; builds a `Pace` for one kid |
| `fridgesheet/web/verdicts.py` | `pace` argument; rules 9–10 and 12–13 use it; `pace` facts; good-news follow-ups decided; `Answer.action`; new `ANSWERS` rows |
| `fridgesheet/web/phrasing.py` | `pace.*`, `step.work_on_it`, `where.planned_today`, `where.planned_tomorrow`, `a.today`, `a.tomorrow`, `a.add_details` in three tiers |
| `fridgesheet/web/stores/items.py` | builds the kid's `Pace` once per `_views` and passes it to `verdict` |
| `fridgesheet/web/routes/questions.py` | plan answers create a step; undo with `step_id`; 409 paths |
| `fridgesheet/web/routes/checkin.py` | `_context` reused by the answer route for the panel |
| `templates/_answers.html` | `action` instead of `flag`; hidden `request_key`; no form-link branch |
| `templates/_answered.html` | plan wording; Add details link; `step_id` on the undo form |
| `templates/_after_answer.html` | out-of-band `_plan_panel.html` |
| `templates/_plan_panel.html` (new) | extracted from `checkin.html` |
| `templates/checkin.html` | answers on every card with answers; Add details link; includes the panel partial |
| `templates/_planning_evidence.html` | the pace sentence |
| `docs/outcomes.md` | note that the grace period is learned per course |

## 10. Testing

**Pace statistics** (`tests/test_pace.py`): the 80th percentile by nearest rank on small
lists; fewer than three samples yields `None`; floor and cap; kind grouping; the fallback
chain in order; teacher pooling matches trimmed, case-insensitive names and never crosses
different teachers; censoring drops items first seen already graded and items with no
anchor; zeros are not samples; a Canvas sample anchors on `submitted_at` when present.

**Verdicts** (`tests/test_verdicts.py`, extended): with an injected `Pace` returning 12 days,
an ungraded paper item 9 days past due is `awaiting_grade` with `asks_on` at due + 12 and a
`pace` fact; at 12 days it is `still_ungraded`; the same for `hac_lag` at Canvas seen + N;
the default scope yields the seven-day behaviour of today; a follow-up overtaken by 5 of 5
is decided with the two answers; overtaken by a zero it is still a question; an
`ask_teacher` overtaken by 5 of 5 is still a question.

**Phrasing** (`tests/test_phrasing.py`): the new keys exist in all three tiers and the
number-parity rule holds.

**Routes** (`tests/test_web_questions.py`, extended): `plan:today` creates a step with
the documented defaults and returns the done-line; the same `request_key` twice yields one
step; an item with an active step answers 409; undo with `step_id` deletes an unedited step
and re-renders the card; undo leaves an edited step alone; the response for a plan answer
contains the out-of-band plan panel.

**Check-in** (`tests/test_checkin_queue.py` and `tests/test_web_checkin_verdicts.py`, extended): an upcoming card renders
Today, Tomorrow and It's handed in; a waiting card renders Ask the teacher and the pace
sentence; after a plan answer the item is covered and leaves the queue.

## 11. Risks

- **Lag is bounded by refresh cadence.** The app sees a grade at the next refresh after
  the teacher posts it, so every sample is late by up to one refresh interval. With a
  morning-and-afternoon schedule that is half a day, and it errs in the safe direction
  (the app waits slightly longer).
- **Early in a term there is no history.** The chain bottoms out on the seven-day default
  and the card says so. Nothing regresses from today's behaviour.
- **A teacher who changes habits.** The 80th percentile of the whole history is slow to
  notice. The sample window is the household's whole database; a later change could limit
  it to the current school year.

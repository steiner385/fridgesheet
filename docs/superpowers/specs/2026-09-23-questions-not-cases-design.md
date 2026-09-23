# Questions, not cases: the app decides what the records settle: design

Date: 2026-09-23. Status: decisions taken in discussion, awaiting review of this document.
Replaces the Reconcile page and its six "case" kinds. Amends `docs/outcomes.md` (one
precedence change, section 4.2). Closes #55 and #39; covers most of #34, #44–#47 and
#49–#52 (section 9). Builds on PR #27 (age-appropriate UI), which lands first.

## 1. Goal

Stop asking parents questions the records already answer. Today the Reconcile page raises
a "case" for every difference between Canvas and Home Access Center (HAC). Each case offers
the same five flag buttons, and the page shows each item twice. Most of those cases need
nobody to do anything. A grade that hasn't flowed to HAC yet will flow. A teacher who graded
only in HAC graded it.

After this change the app sorts every item into one of four states. It settles what the
evidence settles and says so. It waits quietly on what time will settle. It asks a question
only when a kid or parent actually has something to do. It shows plain facts, such as "too
late for credit", as statuses. The questions sit at the top of each kid's All work page, and
the Reconcile page becomes **Questions**, the same cards for every kid.

## 2. Decisions taken in discussion

| Question | Decision |
|---|---|
| Fold Reconcile into the kid's work page? | Yes (#55) |
| HAC score above zero vs Canvas's automatic "missing" | HAC wins, except when Canvas's missing mark is newer than HAC's grade: then ask |
| Grace before asking about ungraded paper, in-class or HAC-only work | 7 days past due |
| A "Not now" answer | Dropped. An unanswered question already means "not now" |
| When the kid or parent must act | Only the four cases in section 3 |
| PR #27 | Land it first; this work uses its tier-aware phrasing |
| Grading-period end dates | Not available: the HAC scraper reads marking-period averages, not dates. Not used |

## 3. Why the records disagree, and who acts

| # | Cause | Signal in the data | Who acts |
|---|---|---|---|
| 1 | Canvas grade not yet in HAC | Canvas score, HAC blank | Nobody for 7 days after the Canvas grade appeared, then ask |
| 2 | Teacher graded only in HAC | HAC score, Canvas blank or auto-missing | Nobody |
| 3a | Different scale | Same percentage, different raw scores | Nobody |
| 3b | Late penalty in one system only | Canvas `late`; the gap matches the late-work rule's penalty | Nobody |
| 3c/d | Regrade in one system, or an entry error | Any other percentage gap | Ask only when HAC is lower |
| 4 | Handed in online, HAC has a zero | Canvas `submitted_at`, HAC score 0 | Ask: the kid has a timestamp as proof |
| 5 | Excused in Canvas, zero in HAC | Canvas `excused`, HAC score 0 | Ask |
| 6 | Canvas zero as a placeholder | Canvas 0, nothing submitted | The kid owes the work. Not a question: it is "not done" |
| 7 | The app paired the wrong items, or failed to pair | One-source items with a same-course near-twin | Nobody in the family; listed for the maintainer (section 6) |
| 8 | Removed in one system | Canvas unpublished, or HAC dropped it | Nobody: follow HAC |

## 4. The verdict

### 4.1 One function, four states

A new module `fridgesheet/web/verdicts.py` exposes one function:

```python
def verdict(item, obs, flag, *, now, rules, refresh_times) -> Verdict
```

`Verdict` holds a `state` (`question`, `decided`, `waiting` or `status`), a `kind` naming the
rule that fired, a plain-English `facts` sentence, and, for questions only, the `ask`
sentence and its `answers`. It is built on `outcomes.classify`, so the Questions page can
never ask about something the counts, Trends and the printed sheet already treat as settled.
One definition, as `outcomes.py` already insists.

The rules, in the order they are checked. The first that matches wins.

| Order | Rule | State | Kind |
|---|---|---|---|
| 1 | The family's flag is contradicted by an observation newer than the flag | question | `stale_answer` |
| 2 | Family flag is done / excused / ignore | status | `answered` |
| 2b | Family flag is follow up / ask teacher | status | `asked` (the "Asked Wed 9/23" line, section 5) |
| 3 | Canvas excused, HAC score 0 | question | `excused_hac_zero` |
| 4 | Canvas submitted, HAC score 0 | question | `submitted_hac_zero` |
| 5 | HAC score > 0, Canvas `missing` observed after the HAC score | question | `missing_after_grade` |
| 6 | HAC score > 0, Canvas `missing` observed no later than it | decided | `graded_in_hac` |
| 7 | Both scored; HAC percentage lower than Canvas's, not explained by 3b | question | `hac_lower` |
| 8 | Both scored; percentages differ but explained by scale or late penalty | decided | `scores_explained` |
| 9 | Canvas scored, HAC blank, Canvas grade observed ≥ 7 days ago | question | `hac_still_blank` |
| 10 | Canvas scored, HAC blank, younger than that | waiting | `hac_lag` |
| 11 | Submitted on Canvas, no grade anywhere | waiting | `teacher_grading` |
| 12 | Nothing to submit online (paper, in class, HAC-only), no grade, ≥ 7 days past due | question | `still_ungraded` |
| 13 | The same, less than 7 days past due | waiting | `awaiting_grade` |
| 14 | Open, past the late-work credit window | status | `past_credit` |
| 15 | Anything else | status | the outcome |

"Observed after" uses the refresh time of the latest observation of each source. Ingest
writes an observation only when something changes, so the latest observation's refresh time
is when that source last changed.

Percentages compare `score / points` for each source, where each uses its own points
possible. They differ when the gap is greater than half a point on the item's scale. The
late-penalty explanation applies when Canvas marks the work `late` and Canvas's percentage
equals HAC's minus the late-work rule's credit reduction for that class, within the same
tolerance.

### 4.2 Change to the outcome definition

`outcomes.classify` changes in one place. Under the default Canvas preference, a HAC score
above zero now beats Canvas's `missing` flag and yields `DONE_OFFLINE`. The exception is
when the Canvas observation carrying `missing` is newer than the HAC observation carrying
the score. Today only the per-class HAC preference does this. `docs/outcomes.md` gains a
paragraph explaining it, with the Quiz 1 example. This moves counts on the Today page, in
Trends and on the printed sheet. That is intended: those counts were wrong about exactly
these items.

## 5. What each question asks

Every answer maps onto a flag that exists today (`done`, `excused`, `ignore`, `follow_up`,
`ask_teacher`), or onto the plan-step form. No schema change.

| Kind | Facts line | Question | Answers → effect |
|---|---|---|---|
| `missing_after_grade` | HAC has 28 of 30, but Canvas marked it missing after that. | Which is right? | HAC is right, it's done → `done` · Ask the teacher → `ask_teacher` |
| `hac_lower` | Canvas has 20 of 25 (80%). HAC has 15 of 25 (60%). | Ask the teacher to fix HAC? | Ask the teacher → `ask_teacher` · HAC is right → `ignore` |
| `submitted_hac_zero` | Handed in on Canvas Mon 9/14, 8:02 PM. HAC counts a 0. | Tell the teacher? | Ask the teacher → `ask_teacher` · The zero is right → `ignore` |
| `excused_hac_zero` | Excused in Canvas. HAC counts a 0. | Ask to have it excused in HAC? | Ask the teacher → `ask_teacher` · Leave it → `ignore` |
| `hac_still_blank` | Canvas graded it 18 of 20 on 9/8. HAC still has nothing. | Ask the teacher to enter it? | Ask the teacher → `ask_teacher` · It's fine → `ignore` |
| `still_ungraded` | Paper work, due Thu 9/10. A week on, no grade anywhere. | Was it handed in? | Yes, handed in → `done` · Not yet, plan it → plan-step form · Ask the teacher → `ask_teacher` |
| `stale_answer` | You said done on 9/12. Canvas now says missing. | Still done? | Yes, still done → re-confirm (section 5.1) · No, reopen it → clear flag · Ask the teacher → `ask_teacher` |

The first answer is the primary button. On kid-tier pages (PR #27) every facts, question and
answer string passes through the tier phrase table. The fabrication guard applies to the new
entries too.

`ask_teacher` keeps the item visible as an **asked** line: "Asked Wed 9/23 · waiting on
Mr. Hoch". The line has an optional note and a mailto link when the course has a teacher
email (`courses.teacher_email`). It leaves the question list and returns as `stale_answer`
if the record later changes. (#44 in part, #42's date.)

### 5.1 Re-confirming an answer

"Yes, still done" must stop the stale question from coming back on the next refresh. Setting
the same flag keeps `set_at` (batch 1, #42), so re-confirming writes a new flag row instead:
it clears the old one and inserts `done` with a fresh `set_at`. `stores/flags.py` gains
`confirm(conn, item_id, now)` for this. It is the one deliberate exception to "same flag keeps
its date".

## 6. The pages

### 6.1 A kid's All work page (`/kids/<key>`)

Top to bottom, as in mockup v4:

1. **"N questions about Alex's work"**, the question cards. Hidden when N is 0.
2. **Decided for you**: one line per `decided` verdict whose source still shows something
   contrary, such as Canvas's stale "missing". Each line gives the reason and a **Not right?**
   link. The link opens that item's answers as a question card, and the answer becomes the
   family's flag. Items decided with nothing contrary on show get no line.
3. **Waiting, nothing to do yet (N)**, collapsed. One line each, saying what it is waiting for
   and when it would ask. `awaiting_grade` lines offer **Ask now**.
4. **The work list.** Three columns: Due, Assignment with the class and kind underneath, and
   "Where it stands", one phrase from the verdict. Controls: an Open / Everything toggle, a
   class picker, and **More filters**, a disclosure holding today's Source, Kind, Flagged and
   Outcome selects under plain labels (#52). A row with a question carries a small "question"
   tag that scrolls to its card. The Sources column and the "actionable" pill go (#50). Red
   appears only for school-recorded not-done: missing, or a zero (#34).

Answered questions collapse in place to a green line with **Undo** until the page reloads.
Undo restores the previous flag, or clears it if there was none.

**See the record** on any card or row opens the evidence: one line per source with what it
says and "as of" its latest observation's refresh time (#44, #46). Notes are a link that
opens the notes form (#47).

### 6.2 Questions (`/questions`, was `/reconcile`)

Every kid's question cards, grouped by kid, each group linking to that kid's page. The nav
item "Reconcile" becomes "Questions", with a count. The rail shows each kid's question count.
`/reconcile` redirects here, keeping `kid`. The kind filter goes: there are few enough
questions to read.

When a kid has two or more `past_credit` statuses, the group opens with one line: "N of
Sam's assignments are too late for credit. [Let all N go]". It applies `ignore` after a
confirm, as today's bulk action does.

A final collapsed section, **Can't pair these (N)**, lists one-source items with a
same-course item in the other source within three days of the same due date and with no
pair. It is for the maintainer, never a question (cause 7). Manual pairing is out of scope.

### 6.3 The item detail

The detail card (`_item_detail.html`) becomes the expanded question card, or for items with
no question, the evidence plus notes. `_case_group.html` is deleted. The raw five-flag menu
(`_flag_menu.html`, with batch 2's Enter-key guard) stays reachable under the card's **More**
link for families who want to set a flag the questions don't offer. Keyboard focus from batch 2 carries over.

## 7. What changes in code

- **New:** `web/verdicts.py` (rules and sentences); `templates/_question.html`,
  `_decided.html`, `_waiting.html`, `_record.html`; `routes/questions.py`.
- **`outcomes.classify`:** the precedence change in 4.2; it needs `refresh_times`, passed the
  way `reconcile.cases` already gets them.
- **`stores/items.py`:** `ItemView` gains `verdict`. `case_kinds` and `with_cases` go;
  `list_items` feeds all three page sections.
- **Consumers of `case_kinds` move to `verdict`:** `routes/checkin.py` (queues: a `question`
  goes to "Needs clarification", `waiting` to "Waiting for a grade"),
  `_planning_evidence.html`, `open.html`, `views.py` (the report column becomes the verdict
  kind's label), `routes/kid.py` and `routes/flags.py`.
- **`reconcile.cases`:** deleted, with its tests rewritten against `verdicts`. `KINDS` goes.
  `reconcile.py` keeps `open_sources`, `is_actionable`, `live_items` and the date helpers.
- **Removed:** `routes/reconcile.py` (kept only as the redirect), `reconcile.html`,
  `_case_group.html`. `_flag_menu.html` and `_flag_default.html` stay, behind **More**.

## 8. Testing

- `tests/test_verdicts.py`: one test per rule row in 4.1, at the boundary (6 vs 7 days;
  observation newer vs older; percentage gap at the tolerance), plus the explained-gap cases.
- `tests/test_outcomes*.py`: the 4.2 precedence change and its exception.
- Page tests: the three sections on the kid page; Questions groups and the bulk line;
  `/reconcile` redirects; answering collapses the card, and Undo restores; Not right? turns a
  decided line into a question; the tier parity test from PR #27 extended to the new sections.
- A browser check in Chrome against the seeded household, as in batch 2. The seeded Alex
  must show exactly one question (Participation), one decided line (Quiz 1), and two waiting
  lines (Essay draft, Lab notebook).

## 9. Issues

Closes #55, #39, #45, #46, #49, #50. Covers #34 (red rule), #44 (as of, teacher email; the
Canvas link stays open), #47 (notes as a link; notes into the check-in stay open), #51
(already partly fixed by PR #27) and #52 (filters; the flagged-kind filter values).
Untouched: #35 and #48 (plan steps), #43 and #53 (accessibility audit), #54 (nav names).

## 10. Out of scope

Manual pairing of items. Grading-period dates. A snooze. Changing ingest, the database
schema, or the source-of-truth settings.

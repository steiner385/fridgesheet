# The plan fills itself: what must be finished is on the plan before anyone taps: design

Date: 2026-09-27. Status: design approved in discussion, reviewed by five persona agents;
awaiting review of this document. Static mockups (throwaway HTML over the real stylesheet,
with desktop and phone renderings) are in `2026-09-27-plan-fills-itself-mockups/`. Builds on "Learned pace and one-tap answers"
(`2026-09-23-learned-pace-and-one-tap-answers-design.md`) and on the check-in's three-layer
rule (`docs/product/features/check-in-planning.md`): the school record, the family's account
and the agreed step are never written by one another. Respects `docs/outcomes.md` and the
data-correctness capability: nothing here puts the app's word in the school's mouth or the
school's word in the family's.

## 1. Goal

The owner's ask, in their words: "If there are things due and not yet turned in, that is the
focus and should be added to the plan. Period. Likewise if there are things on the plan that
we know have already been turned in, we can remove those from the plan. First priority is
always finishing and submitting the work. Checking up on scores, following up with teachers on
mismatches, and so on are secondary and much lower priority."

Today the plan (`/kids/<kid>/plan`, and the right half of `/kids/<kid>/check-in`) holds only
what a person put there: a one-tap "Today" or "Tomorrow" on a card, or the step form. Work due
tomorrow that nobody tapped is not on the plan. A step whose assignment Canvas has since
recorded as handed in stays on the plan, counted in tonight's minutes, until someone opens it
and marks it complete. And on a phone the Questions group sits above the plan, so a score
mismatch competes with tonight's deadline for the first screen.

After this change:

1. **The plan opens with "Must finish"**, a list the app computes from the school record
   every time the page is drawn, from the same rows the Open work page and the printed sheet
   already use. Nobody puts a row there and nobody can take one off; it leaves when the school
   record says the work is in, or the family answers "It's handed in."
2. **A family step the school now shows as handed in is greyed**, dropped from tonight's
   minutes, with the witness quoted ("Canvas: handed in Mon 9/28") and one tap to complete it.
3. **Questions and mismatches move below the plan**, collapsed, and open themselves only when
   they hold a zero to check or an answer the school has since contradicted.
4. **The kid can ask Canvas again from the plan page**, so "I just submitted it" does not end
   with marking it done by hand.
5. **The app opens on one kid.** A browser remembers who is looking, from one tap on a
   chooser, and a kid's device then opens on their plan with a rail that names only their
   pages: no siblings, no Settings, no household Today. The grown-up view is the app as it is
   today, one tap away, and no longer the only layout (section 13).

The app writes no family row on the family's behalf. "Must finish" is the school record,
sectioned and ordered; the plan beneath it is still only what the family agreed.

## 2. Decisions taken in discussion

| Question | Decision |
|---|---|
| Stored rows or a derived list? | **Derived.** No `plan_steps` row is ever inserted or completed by the app. The check-in snapshot stays a record of agreements only |
| What is "turned in"? | Whatever `outcomes.classify` and `reconcile.open_sources` already say. The spec adds no second definition |
| Paper work nobody has graded | In the list, since the school record cannot say it is in, but in its own un-red group with "It's handed in" first and the class's learned pace sentence |
| An item with a family step | Appears **once**, in the family's steps, badged with the sheet's word. Four of five personas over the one who wanted it to stay in Must finish |
| Escape hatches | "Too late" and "Let it go" come off Must-finish rows. They stay on the Questions page and behind **More** for a parent |
| "School says this is in" | Never a heading. A line naming the witness: Canvas, HAC, or the family's own answer |
| Order in Must finish | Due tonight, due tomorrow, then overdue and still fixable. The printed sheet keeps its overdue-first order; it is the quarter's record, the plan is tonight |
| "Check Canvas again" | In scope: the existing refresh job, started from the kid's plan page |
| Per-kid variation | Through settings that already exist (days ahead, overdue days, late-work rules, learned pace). No new setting |
| How does the app know which kid is looking? | **A remembered choice per browser** (a cookie), set by one tap on a chooser and changed by one tap. No login, no password: the credential-security model is unchanged, and every page stays reachable by its address |
| What does a kid's rail hold? | This kid's pages only: Plan, Check-in, Assignments, Trends, Changes, and "Not {name}?". The "App" fold on a child's page (kids' UX audit F5) is superseded in kid mode; it stays in the grown-up view |

## 3. What the page shows today

`checkin._context` builds the review queue from `items.list_items(show="all")` and
`queue_for` sorts each item into Questions, Waiting on the school, or To do, skipping items an
active step covers. The plan panel (`_plan_panel.html`, `id="plan"`) lists steps by state and
shows "N min estimated for today". A step whose school evidence changed shows "School evidence
changed since this step was saved. Review it together" and still counts in the total.

The Open work page and the sheet read `items.open_work`, whose `fixable` list is
`(overdue or upcoming) and not handled and actionable`: not-done and unknown work inside its
late-work window, no older than the overdue-days setting, plus a late hand-in with no grade
(`reconcile.open_sources`, `late_ungraded`). Its `upcoming` list is unsubmitted Canvas work due
within the days-ahead setting. HAC-only work is never upcoming (it needs a Canvas observation)
and enters `fixable` only once past due, as PAPER — CHECK or HAC — NO GRADE.

The persona reviews found that the first draft of this design, which reused those rows with a
fixed set of buttons, would have listed a paper lab the kid handed in last week as "Must
finish" and, on the same page, as "Waiting for a grade"; would have let "Too late" dismiss a
row the list promised nobody could dismiss; and would have offered "It's handed in" as the
first button on a HAC zero the family should be asking the teacher about. Sections 4 and 5
are the answer to those three findings.

## 4. Must finish

### 4.1 The rows

`items.open_work(...)` for the kid, `fixable + upcoming`, minus items an active family step
covers (section 5). No other source, no re-filter: `tests/test_open_work_parity.py` gains a
case that the plan's Must-finish ids equal Open work's `fixable + upcoming` ids minus the
covered set. The data-as-of line (the last refresh's `started_at`) is shown under the heading,
as Open work shows it.

### 4.2 Sections, in order

| Section | Rows | Colour | Open by default |
|---|---|---|---|
| **Due tonight** | `upcoming`, `deadline_date(due) == today` | red | yes |
| **Due tomorrow** | `upcoming`, `deadline_date(due) == today + 1` | red | yes |
| **Overdue, still fixable** | `fixable` with outcome `not_done`: a missing mark, a zero (with or without a submission; a zero on handed-in work is the `submitted_hac_zero` question, 4.4), or online work past due with nothing handed in. By `late_until` then due, as `open_work` already sorts | red | yes |
| **On paper, no grade yet** | `fixable` with outcome `unknown`: paper, in-class or HAC-only work past due with no grade | not red | yes, as one line per row, under one sentence |
| **Handed in, waiting for a grade** | `fixable` with outcome `late`: a Canvas hand-in after the deadline with no grade yet (`late_ungraded`) | grey | no |
| **Coming due later** | `upcoming` due after tomorrow, by due | plain | no, heading carries the count |

The three `fixable` sections partition it by `outcome`, which `open_sources` allows to be
only `not_done`, `unknown` or `late` for an open row; no row can fall in two, and none in
none.

A due date in the first hour of a day belongs to the evening before (`dates.deadline_date`),
as the sheet and Today's count already say.

The "On paper" group carries the class's pace sentence (`pace.expect` / `pace.passed` /
`pace.default`, spec 2026-09-23 §4.6) once per course, so it reads as waiting, not failing.
The two collapsed sections carry their count in the heading.

Undated work that HAC lists with a missing mark or a zero is in `fixable` and prints on the
sheet; it goes in **Overdue** with no deadline phrase. Undated work nothing has happened to is
not open, not upcoming, and stays out, as it is out of the sheet; it remains reachable from
the check-in's queue (section 7) as today.

### 4.3 What a row shows

The course eyebrow, the name (linking to the row on the Assignments tab), the deadline phrase
in the kid's tier (`sheet.status_word` of `view.status`: DUE TONIGHT, DUE TOMORROW, MISSING,
ZERO, PAPER — CHECK, or the phrase-table word for a younger reader), the late-credit line
the check-in card already shows for open rows ("Late work is usually accepted until…"), and
the answers (4.4). The evidence lines (`_planning_evidence.html`) are behind a **Details**
disclosure, as on the plan card, not open: this list is for tonight, not for reading the
record.

A row also says whether the last check-in saw it (section 8): "On Sunday's list" or "New
since Sunday", in the kid's tier.

### 4.4 Answers on a row

A row renders `_answers.html` with **its own verdict's answers**, filtered:

- `too_late` and `ignore` actions are dropped on this page. They are `HANDLED_FLAGS`, which
  remove a row from the open list; the list's promise is that nothing here can be waved
  away. They remain on the Questions page, the Assignments tab and behind **More**.
- The first remaining answer is the filled default, except on the "On paper" group, where
  `done` ("It's handed in") is moved first and filled. On an online `not_done` row the order
  stays `done`, Today, Tomorrow; on `not_due_yet` it stays Today, Tomorrow, `done`.
- A row whose verdict is a **question** (`submitted_hac_zero`, `hac_lower`,
  `missing_after_grade`, `stale_answer`, `still_ungraded`, …) keeps the question's ask line
  and its answers unfiltered except for the two above, and carries a badge in the kid's tier:
  `badge.zero_to_check` for a zero the school may have wrong, `badge.changed_since_answer` for
  a stale answer. Finishing first must not mean tapping away a wrong zero; on those rows
  "Ask the teacher" stays first.

Plan answers work as today (spec 2026-09-23 §6.3): one request key per row, the done-line
with Undo and "Add details" swaps into the row's slot, and the plan panel swaps out of band.
The Must-finish section is **not** swapped out of band after an answer (section 12), so the
Undo stays where the kid can see it.

### 4.5 How a row leaves

A row leaves Must finish when, and only when, it leaves `open_work`'s `fixable + upcoming`:

- Canvas records a submission (outcome becomes on time or late; a late hand-in with no grade
  moves to the grey "Handed in, waiting for a grade" group and leaves once graded);
- a grade above zero appears in either source (done on paper);
- the family answers `done` or `excused` ("It's handed in", the flag menu's excused);
- the teacher excuses or unpublishes it;
- it ages past the overdue-days setting or its late-work window (it moves to Open work's
  "past the window" count, as today, and to the check-in's queue);
- or an active family step now covers it (section 5).

The document does not restate `outcomes.classify`; that table is the definition.

## 5. One item, one place

An item is in at most one of: Must finish, Our next steps, Worth checking, Waiting.

- **A family step covers its item.** The `covered` set `checkin._context` already builds
  (steps not `done`) removes the item from Must finish, from Worth checking and from Waiting.
  The step's card in Our next steps carries a badge with the sheet's word for the item
  (`badge.must_finish`: "Must finish · DUE TOMORROW"), placed where the eyebrow is, so the
  deadline is not lost under the recorded-by stamps. When the step is completed or deleted
  the item returns to whichever section its record puts it in.
- **A Must-finish row is not a question or a waiting card.** `queue_for` returns None for
  any id in the Must-finish set, so a paper lab is never "Must finish" and "Waiting for a
  grade" on one page.
- **A second one-tap plan on a covered item** is refused with 409 as today
  (`questions._already_planned`); "Add details" and the item detail's "Plan another step"
  remain the way to a second step.

## 6. Family steps the school shows as in

For each active step with an item, `checkin._context` sets `step["school_has_it"]` to a
witness line, or None:

| Condition (from the item's view, in this order) | Line (older tier; `record.*` keys, three tiers) |
|---|---|
| `verdict.kind == "stale_answer"` | None: the school contradicted the family's answer; the step stays live |
| outcome `not_done` | None: a zero in either source is not done, whatever Canvas's submission says (review finding 2) |
| Canvas `submitted_at` set | "Canvas: handed in {when}" (`handed_in_at`, `wd_md_time`) |
| outcome `done_offline` | "HAC: graded {score}" or "Canvas: graded {score}", whichever source holds the grade above zero |
| flag `done` | "You answered It's handed in, {when}" (`flag_set_at`) |
| flag `excused` | "You answered excused, {when}" |
| Canvas `excused` | "Canvas: excused" |
| otherwise | None |

A step with a witness line is shown in its state group, greyed (`class="school-has-it"`),
under a small heading `copy.school_has_it` ("The school has it" on the early tier), with the
witness line in place of the "school evidence changed" notice, and one button, **Mark step
complete** (`POST /kids/<kid>/check-in/step/<id>/complete`, a new route that sets `state =
done` with the step's current revision and `recorded_by` from the form's optional name, then
303s back as `_after_save` does). It is excluded from `today_steps` and so from the minute
total, and the total line says so (section 8). The step is never completed by the app.

The existing "School evidence changed since this step was saved" notice stays for changes
that are not a hand-in.

`plans.today_load`, which the dashboard reads, gains the same exclusion: it takes the set of
item ids the school shows as in, computed once per kid by the caller, so the dashboard's
"N steps planned today · M min" agrees with the plan page.

## 7. Worth checking, and Waiting

On the check-in page the order becomes: **Must finish**, **Our next steps**, **Agree and wrap
up**, **Worth checking**, **Waiting on the school**. On the plan-only page: Must finish, Our
next steps, Worth checking, Waiting. (The plan page today shows only the panel; the two
collapsed groups are added so the kid alone sees the same page structure.)

- **Worth checking** is today's Questions group, minus the ids in Must finish. Collapsed by
  default; the heading carries the count. It renders **open** when it holds any item whose
  verdict kind is `submitted_hac_zero`, `excused_hac_zero`, `hac_lower`, `stale_answer`,
  `asked_then_graded` or `followed_up_then_graded`: a zero the school may have wrong, an
  answer the school contradicted, or a question that was asked and has since been graded. A
  second caregiver's one question, "did the teacher answer?", is above the fold.
- **Asked the school.** Above Worth checking, one open line per item with an active
  `ask_teacher` or `follow_up` flag: "{name}: asked the teacher on {when}" (`where.asked`,
  `where.following_up`), each linking to its row. This is the family's own record, shown
  where the family reads the plan; the `flags` table has no "who", so the line says when.
- **Waiting on the school** is unchanged in content, minus Must-finish ids, collapsed.
- **Other open work** is what today's To do group holds once Must finish has taken its
  rows: open work past its late-work window or older than the overdue-days setting (the
  sheet's "not shown" count), undated work nothing has happened to, and upcoming work with
  no Canvas observation. Collapsed, last, count in the heading, the same cards and answers as
  today. Nothing that is open today becomes unreachable.
- The one instruction sentence above the cards (`copy.queue_hint`, "These are options, not
  tonight's must-dos") moves under the Worth checking heading, where it is true again, and
  Must finish gets its own one sentence (`copy.must_finish_hint`: "The school says these are
  not in yet. They leave when it says they are, or when you say so.").
- The bottom strip on a phone (`.halves`, #189) names **Must finish** and **Next steps**, with
  their counts.

## 8. The total line, the snapshot, the dashboard

### 8.1 The total line

`_plan_panel.html`'s "N min estimated for today" becomes one sentence, three phrase keys
joined with " · ": `copy.tonight_steps` (`{steps}`, `{minutes}`), `copy.tonight_unpicked`
(`{unpicked}`) and `copy.tonight_school_has` (`{school_has}`):

> Tonight: 2 steps, 25 min · 10 must-finish not picked yet · 1 the school has, not counted

Each clause is omitted when its number is zero. "Without an estimate" goes: a step with no
minutes is counted as a step, and the kid's number is the number of things. The over-budget
warning against the last check-in's time budget stays as it is.

### 8.2 The check-in snapshot records what the list held

`checkins` gains a column `seen TEXT NOT NULL DEFAULT '[]'`: the JSON list of item ids in Must
finish at the moment the check-in was finished (schema v9; migration adds the column; every
existing row reads `[]`). `plans.finish` takes `seen` from the route, which computes it with
the same function the page uses.

Each Must-finish row then reads, from the last check-in: `badge.seen_at_checkin` ("On
Sunday's list") when its id is in `seen`, else `badge.new_since_checkin` ("New since Sunday"),
where the day is `last_check.finished_at` in `wd_md`. Before the first check-in the badge is
omitted. The badge prints (section 10). Nothing else about the snapshot changes: `plan` still
holds only family steps, and Must finish is still not an agreement.

### 8.3 The dashboard

Today's card shows "N still fixable" and "N due today · N due tomorrow" (`dashboard_counts`).
The card **replaces** those two lines with one headline per kid:

> **N** not done, due by tomorrow → `/kids/<kid>/plan`

where N is the count of Must-finish rows in the Due tonight, Due tomorrow and Overdue
sections, with no covered set removed: work with an agreed family step is still not done, so
covering every red row must not read as "Nothing due by tomorrow" (review finding 1). `Counts`
does not gain a field for this; the dashboard route computes it with `items.must_finish(work,
today)` (no `covered` argument) and passes it on the card as `must_finish`. `fixable`,
`due_today` and `due_tomorrow` stay on `Counts` for the Open work page and tests but leave the
card. A zero reads "Nothing due by tomorrow" so the parent can close the phone. The family line
("N steps planned today · M min") uses `today_load` with the section 6 exclusion.

## 9. Check Canvas again

The plan page and the check-in page get one button beside the Must finish heading: **Check
Canvas again** (`copy.check_again`, three tiers), an htmx POST to the existing `/jobs/refresh`, with
`hx-target="#job"` on a `<div id="job">` placed under the Must-finish heading, so the job card
(`_job.html`) shows there with its log, and a 409 "Busy" card when a job is already running,
as on Today. When the job finishes the page's data-as-of line is stale. `static/app.js`'s `attachSse`
listens on the job's event stream and, on the server's `done` event, fetches the finished
job card into `#job`. The `<pre>` gains an optional `data-reload-page` attribute, which
`_job.html` sets when the includer asks for it (the plan and check-in pages do); on `done`
with that attribute present, `attachSse` reloads the page instead of the card, so the list
and the as-of line are current. The lost-connection path is unchanged.

The button is hidden when the server has no jobs worker (`state.jobs is None`), as Today
hides "Refresh now". It refreshes every kid, as the job does today; the label does not claim
otherwise, and the log names each kid as it goes.

## 10. Print

`plan_print.html`, in order:

1. The head as today, plus the last check-in's `recorded_by` after "Agreed …".
2. **Must finish**, as the sheet's rows on paper: the Due tonight, Due tomorrow and Overdue
   sections only, each row `□ {name} · {course} · {deadline phrase}` with the seen/new badge
   as plain text, under one line: "The school's list as of {data_as_of}. It changes daily;
   the plan page is current." No paper group, no grey group, no Coming due later, no buttons.
3. **Our next steps** as today, with `created_by` / `recorded_by` on each step (the screen
   shows them; the paper did not), and greyed steps printed under "The school has it" with
   their witness line and no box.
4. Nothing from Worth checking or Waiting. The closing sentence stays.

The printed sheet (`reports/open_work.py`) is unchanged. The two papers list the same rows
in different orders and say so in their headings; that difference is deliberate and
documented in `docs/outcomes.md`'s "Where each outcome shows up" table with a new row for the
plan page.

## 11. Phrasing

New keys in `phrasing.PHRASES`, each in three tiers, under the parity rule (no younger tier
states a number, date or time its adult equivalent does not):

`copy.must_finish`, `copy.must_finish_hint`, `copy.due_tonight`, `copy.due_tomorrow`,
`copy.overdue_fixable`, `copy.on_paper_no_grade`, `copy.handed_in_waiting`,
`copy.coming_due_later`, `copy.worth_checking`, `copy.school_has_it`, `copy.tonight_total`,
`copy.check_again`, `copy.asked_the_school`, `copy.nothing_due` (dashboard zero),
`copy.not_done_due_by_tomorrow` (dashboard headline), `badge.must_finish`,
`badge.zero_to_check`, `badge.changed_since_answer`, `badge.seen_at_checkin`,
`badge.new_since_checkin`, `record.canvas_handed_in`, `record.graded_in` (with `{source}` and
`{score}`), `record.you_said_handed_in`, `record.you_said_excused`, `record.canvas_excused`,
`a.mark_step_complete`, and for kid mode `copy.who_looking` ("Who's looking?"),
`copy.a_grownup` ("A grown-up"), `copy.not_name` ("Not {name}?"), `copy.switch_to_kid`
("Switch to a kid's view", grown-up rail only, one tier). `copy.queue_hint` is reworded for
its new place under Worth checking.

Early-tier wording, for the two the reviewers called out: `copy.school_has_it` is "The school
has it"; `copy.tonight_total`'s unpicked clause is "{unpicked} not picked yet".

## 12. Mechanics

- **Sections.** Must finish is `<section id="must-finish">` in a new partial
  `_must_finish.html`, rendered above `_plan_panel.html` on both pages. It is not inside
  `#plan`, so `_after_answer.html`'s out-of-band swap of the panel cannot replace the slot the
  done-line and its Undo occupy. After a plan answer the panel's total line and the covered
  set change; the row already shows its done-line, and the next full load moves it.
- **Context.** `checkin._context` gains `must_finish` (the sectioned rows, from
  `items.open_work` filtered by `covered`), `red_total` (the same red rows with no `covered`
  argument, so the print page's empty state is judged against every red row, not just the
  uncovered ones — review finding 1), `school_has` (item id → witness line), `asked`
  (the open "asked the school" lines), and `worth_checking_open` (the boolean from section 7).
  The review queue is built with Must-finish ids excluded. The function stays the one place
  the answer route calls for the panel.
- **Answers.** `_answers.html`'s `first` (an action) moves one answer to the front and fills
  it as the primary button even on a waiting card, whose own default is otherwise never the
  filled one (kids' UX audit F9) — the zero-on-handed-in-work row (section 7) relies on this.
- **Routes.** New: `POST /kids/{key}/check-in/step/{step_id}/complete`. Changed: `finish`
  passes `seen`. No change to `/items/{id}/answer` beyond the answers a row offers, which the
  template filters.
- **Stores.** `plans.finish(..., seen)`, `plans.today_load(..., exclude=set())`,
  `plans.complete(conn, student_id, step_id, *, now, revision, recorded_by)` (a state-only
  update with the revision check `save` uses). `items.Counts.must_finish`.
- **Schema.** v9: `ALTER TABLE checkins ADD COLUMN seen TEXT NOT NULL DEFAULT '[]'`.

## 13. Kid mode: the app opens on one kid

### 13.1 Who is looking

Today `/` is the household's Today page and the rail names every child on every page; a
child's page folds the rest under **App** (kids' UX audit F5), but Doug is still one tap from
Settings and from his sister's plan, and typing the app's address on his phone lands him on
his parents' dashboard.

A browser remembers who is looking. `GET /who` is a chooser: one large button per visible
student, in that kid's nickname, and **A grown-up** last. `POST /who` (form field `who`: a
student key or `family`) sets a cookie `fridgesheet_who` for a year (`path=/`,
`SameSite=Lax`, no `Secure`: the app is plain http on the LAN) and 303s to `/`. The chooser
is reachable from every rail: **Not {name}?** at the foot of a kid's rail, **Switch to a
kid's view** under the grown-up rail's App group.

`/` then goes by the cookie: no cookie, the chooser; `family`, Today as it is now; a student
key, 303 to `/kids/<key>/plan`. A key that names no visible student (a renamed or hidden
kid) clears the cookie and shows the chooser.

There is no login. A kid can tap **A grown-up**; a parent can bookmark a sibling's page on a
kid's phone. This is the security model the app already has (`credential-security`: the
household network is the boundary), and the chooser removes distraction, not access.

### 13.2 The kid's rail

When the cookie names a student, `base.html` draws the kid rail instead of the household
rail, on every page:

- the brand, linking to `/` (which is this kid's plan);
- **{nickname}** with the question count `qcount-<key>`, linking to the plan;
- **Plan**, **Check-in**, **Assignments** (the child nav's three, so the same three words
  appear once, in the rail; `_child_nav.html` draws only its one-line tab hint in kid mode,
  not the tabs);
- **Trends** (`/trends?kid=<key>`) and **Changes** (`/changes?kid=<key>`);
- **Not {nickname}?** (`/who`).

No Today, no siblings, no Work, Time or App groups, no `qcount-all`. Out-of-band swaps that
target a missing id are dropped, as they are today for pages without a `#plan`. The rail
draws for the cookie's kid whatever page is showing; a page about a sibling reached by
address renders as it does today, with the rail still the reader's own.

The status bar keeps the refresh time and source health, and drops the last-run line and the
update badge (both link to grown-up pages). The stale banner's **Refresh now** links to
`#must-finish` on this kid's plan, where **Check Canvas again** (section 9) is, instead of to
Today.

### 13.3 Pages in kid mode

- **Home** is the plan, with Must finish first (section 4).
- **Trends** and **Changes** with no `kid` parameter scope to the cookie's kid, and their
  kid picker badges (`all`, each sibling) are not drawn. `?kid=` for another kid still works
  by address. Trends' one-chart-per-kid rule already gives a single kid a single chart.
- **Grades** are the Assignments tab's class filter and each class's page
  (`/kids/<key>/courses/<id>`), as today; the rail's Assignments entry is the way in.
- **Questions** and **Open work** are not in the kid rail: Worth checking on the plan is the
  kid's questions, and Must finish is the kid's open work. Both pages still answer by address.
- **Print** pages are unchanged; they already carry no rail.
- **Tier.** A page about a student carries that student's tier, as today. Trends and Changes,
  which have no student in context, carry the cookie kid's tier in kid mode, so type size and
  vocabulary follow the reader on every page of theirs. The parity rule holds: rows and
  actions are the same on every tier and in both modes.

### 13.4 The grown-up view

The app as it is today, plus **Switch to a kid's view** under App. The child-page fold
(`kid_page` in `base.html`) stays for a parent reading a kid's page in family mode.

### 13.5 Mechanics

`page_context` reads the cookie into `who` (`"family"`, a student key, or `None`) and
`who_student` (the row, or `None`); `base.html` branches on `who_student`. Routes: `GET /who`,
`POST /who`; the dashboard route checks `who` first. `trends._student` and the changes
route's kid lookup fall back to `who_student` when the parameter is absent. `_header.html`
and `_child_nav.html` read `who_student`. `docs/product/features/browser-app.md` drops "a
kid-facing view" from its non-goals and names this section.

## 14. Not in this design

- Any write of a `plan_steps` row by the app, including auto-completing a step.
- A login, a PIN on the grown-up view, or hiding any page from a kid who types its address.
  The chooser is for focus; access is the network's boundary, as today.
- A per-kid or per-class setting for what enters Must finish. Days ahead, overdue days, the
  late-work register and the learned pace are the knobs, as today.
- Changing which rows the printed sheet prints, or its order.
- A "who" on flags. The "Asked the school" line says when, not who.
- Pre-filling the wrap-up's "What we agreed" box from the plan (still the 2026-09-23 spec's
  follow-up).
- A per-kid refresh. "Check Canvas again" runs the household refresh.

## 15. Files

| File | Change |
|---|---|
| `fridgesheet/web/routes/checkin.py` | `_context`: Must-finish sections, `school_has`, `asked`, `worth_checking_open`; queue excludes Must-finish ids; `complete` route; `finish` passes `seen` |
| `fridgesheet/web/stores/plans.py` | `finish(seen)`, `today_load(exclude)`, `complete` |
| `fridgesheet/web/stores/items.py` | `Counts.must_finish`; a `must_finish_sections(open_work, today, covered)` helper the page, the dashboard and the parity test share |
| `fridgesheet/web/db.py` | schema v9, migration |
| `fridgesheet/web/routes/dashboard.py`, `templates/dashboard.html` | one headline per kid; family line excludes school-has-it steps |
| `templates/_must_finish.html` (new) | the six sections, the as-of line, the seen/new badge, the job slot |
| `templates/_plan_panel.html` | total sentence; greyed steps with witness line and Mark step complete; must-finish badge on covered steps |
| `templates/checkin.html` | new order; Worth checking, Waiting and Other open work on the plan page too; Asked the school; Check Canvas again; strip labels |
| `templates/_job.html` | optional `data-reload-page` on the live `<pre>` |
| `templates/_answers.html` | an `exclude` set of actions and a `first` action the includer may pass |
| `templates/plan_print.html` | Must finish block; names on steps; greyed steps |
| `fridgesheet/web/phrasing.py` | the keys in section 11 |
| `fridgesheet/web/static/app.js` | `data-reload-page` on a finished job |
| `fridgesheet/web/app.py` | `page_context`: `who`, `who_student` from the cookie |
| `fridgesheet/web/routes/who.py` (new) | `GET /who`, `POST /who`; `templates/who.html` (new) |
| `fridgesheet/web/routes/dashboard.py` | `/` goes by the cookie |
| `fridgesheet/web/routes/trends.py`, `routes/changes.py` | fall back to the cookie's kid; hide the picker in kid mode |
| `templates/base.html`, `_header.html`, `_child_nav.html`, `trends.html`, `changes.html` | the kid rail, the trimmed status bar, no child nav or kid picker in kid mode |
| `docs/product/features/browser-app.md` | "a kid-facing view" leaves the non-goals |
| `docs/outcomes.md` | a "Plan page" row in "Where each outcome shows up" |
| `docs/product/features/check-in-planning.md` | desired outcome and notes updated |
| `docs/user-guide.md` | the plan page section |

## 16. Testing

**Sections** (`tests/test_must_finish.py`, new): from a seeded kid with one item of each
kind (due tonight, due tomorrow, due in 5 days, overdue online missing, overdue zero with a
submission, overdue paper unknown, late ungraded, HAC-only past due, undated HAC zero,
undated untouched, past the overdue-days setting, handled `done`, handled `too_late`), each
lands in exactly the section the table in 4.2 names or in none; a 00:30 deadline is "tonight"
the evening before; the zero-with-submission is in Overdue with `badge.zero_to_check` and
"Ask the teacher" first; the paper row's first button is "It's handed in".

**Parity** (`tests/test_open_work_parity.py`, extended): Must-finish ids equal Open work's
`fixable + upcoming` minus the covered set, for a seeded household and for the empty case.

**One place** (`tests/test_checkin_queue.py`, extended): an item in Must finish is in neither
Questions nor Waiting; a plan answer moves it to the family steps with the must-finish badge
and out of Must finish; completing the step returns it; a second plan answer answers 409.

**Answers** (`tests/test_web_checkin_verdicts.py`, extended): no Must-finish row renders
`too_late` or `ignore`; the same item on the Questions page still does.

**School has it** (`tests/test_web_checkin.py`, extended): a step whose item gains a Canvas
submission shows the Canvas witness line, is out of the total, and is completed by the new
route with the revision check; a `done` flag shows the family witness line, not the school's;
a `stale_answer` un-greys; `today_load` with the exclusion matches the page's total.

**Snapshot** (`tests/test_web_checkin.py`, `tests/test_migrate.py`): finishing records
`seen`; rows badge seen/new against it; a v8 database migrates with `seen = '[]'` on existing
rows; before any check-in no badge renders.

**Worth checking** (`tests/test_web_checkin_verdicts.py`): collapsed with only an `hac_lag`
item; open with a `submitted_hac_zero` or `asked_then_graded` item; the "Asked the school"
line lists an `ask_teacher` flag with its date.

**Dashboard** (`tests/test_web_open_today.py`, extended): the headline count equals the
three red sections; zero reads "Nothing due by tomorrow"; the family line excludes a
school-has-it step.

**Print** (`tests/test_web_plan_steps_everywhere.py` or a new print test): the plan print
carries the three sections with boxes, the as-of line, the badges, names on steps, and
nothing from Worth checking.

**Check again** (`tests/test_web_jobs.py`, extended): the button is present with a worker
and absent without; the POST starts a refresh job and renders `_job.html` into `#job` with
`data-reload-page` set.

**Phrasing** (`tests/test_phrasing.py`, `tests/test_web_tier_parity.py`): every new key in
three tiers; parity holds; the same rows render on every tier.

**Kid mode** (`tests/test_web_who.py`, new): `/` with no cookie is the chooser; choosing a
kid sets the cookie and `/` 303s to that kid's plan; choosing a grown-up shows Today; a
cookie naming an unknown key clears and shows the chooser; in kid mode the rail holds the
kid's five links and the switch link, and no sibling, Settings or Today link; Trends and
Changes with no parameter scope to the cookie's kid and draw no picker; Trends in kid mode
carries the kid's tier; an out-of-band answer swap on a kid-mode page does not error on the
missing `qcount-all`; the parity test passes with a kid cookie set.

## 17. Risks

- **A long red list for a kid with many overdue items.** The overdue-days setting bounds
  it, as it bounds the sheet; Due tonight and Due tomorrow come first, and Coming due later
  folds. If the list is still long, that is the school record, and the one-tap answers are
  on every row.
- **"It's handed in" on paper work is one tap away from hiding a real gap.** It is the
  family's own answer, recorded as such, and a later zero from the teacher re-surfaces the
  item as `stale_answer`, which opens Worth checking (section 7). The witness line names the
  family, never the school.
- **The refresh is household-wide.** A kid tapping Check Canvas again refreshes siblings
  too; the log says so. A per-kid refresh is a separate change.
- **Two orders on two papers.** The sheet is overdue-first; the plan is tonight-first. Both
  headings say which they are.
- **The chooser is not a lock.** A kid is one tap from the grown-up view and one address
  from a sibling's page. That is the app's existing model; the chooser removes distraction.
  A household that wants more has the PIN the self-update already uses as a pattern to
  extend later; it is out of scope here.
- **A shared family tablet.** Whoever last chose is who the tablet opens as. "Not {name}?"
  is at the foot of every rail, and the grown-up view is one tap.

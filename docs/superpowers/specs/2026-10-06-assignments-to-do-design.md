# Assignments as a to-do list

Date: 2026-10-06. Status: approved in conversation, awaiting spec review.

## Why

On 2026-10-06 the maintainer checked Doug's Assignments page and found rows in "This week" that
"Needs you now" did not have. Checked against a copy of prod's database (Tue 10/6, 8:18pm),
every row followed a rule, but the rules were not visible on the page:

| Row | Shown in | Left out of Needs you now because |
|---|---|---|
| Ch 3.2 Reading Guide, due tonight | This week | a Plan step for today covers it |
| WS #2-7, ATP Explore and Explain, Smartbook L1 (Fri) | This week | due after tomorrow |
| Two Literary Analysis papers, PAPER — CHECK | Last week | waiting on a grade, and covered by steps |
| Protist Lab, ZERO 0/20 | Week of 9/21 | past its late-work window; open, but nothing lists it |

Other problems on the same page:
- Next week's page is printed above this week's.
- Questions appear twice: in Needs you now and on their week.
- Protist Lab reads "the late-work window has closed. Late work is usually accepted until Mon 10/5."
- Six summaries and control rows come before the first assignment.

The cause is structural. `routes/kid.py` builds the page from five separately filtered queries:
the shown rows, `listed` for the weeks, `everything` for the verdict sections, `open_work` and
`needs_you_now`. Each filters differently, so the sections overlap and leave gaps.

## Decisions (maintainer, 2026-10-06)

1. **Assignments answers "what's left to do".** Every open item appears exactly once, in deadline
   order. Triage stays with Check-in and the Plan; this page lists the work.
2. **Gradebook questions get their own short section** below the to-do list: "Check with the
   teacher".
3. **Everything else either folds or moves to a Done view.** "Waiting on a grade" and "Missed —
   too late for credit" are folded groups under the list. Finished work moves to a Done view,
   which keeps the weekly pages.
4. **The only filter on the to-do view is Class.** The Done view keeps Class, type and Outcome and
   the sort. The other filters are no longer on the page, but their query parameters still work.

This replaces the Assignments surface brief's thesis
(`.impeccable/surfaces/fridgesheet-web-templates-kid-html.md`, "the weekly pages, this week's
page first"). The weekly pages survive as the Done view; the brief is updated to match.

## The partition

A new `items.assignments(views, today) -> Assignments` sorts each of the kid's items into exactly
one group. The first rule that matches wins:

1. **to_do**: open and the child can still act on it. This is every row that is coming due
   (`reconcile.upcoming`'s rule, a Canvas deadline with nothing handed in, *without* its
   days-ahead cap, so a test three weeks out sits folded under Later), plus every `_fixable` row
   whose outcome is `not_done`. A Plan step does not remove a row; the step is shown under it.
2. **question**: `v.asks`, and not in to_do. A to-do row that asks keeps its question on its own
   row, as Needs you now does today.
3. **waiting**: nothing to do but wait on the school. This is `_fixable` rows with outcome
   `unknown` (paper, outside Canvas) or `late` (handed in late, not yet graded), plus verdict state
   `waiting` and the flags `asked` / `following_up`.
4. **missed**: `_past_window`, meaning overdue, not handled and past the late-work window.
5. **not_yet**: not due and not handled, but with no Canvas deadline (HAC's placeholder rows
   such as "Week 9", whose dates the app invents, and undated Canvas work). Neither view lists
   these, as the old Open list did not; `?show=all` still does. (Added during the build: on
   Doug's data they were landing in Done.)
6. **done**: everything else, including rows the family handled (done, let go, excused, too late).

`Assignments` exposes `to_do` already split into bands: overdue (closest to losing credit
first), tonight, tomorrow, later this week, and later. These are the
`must_finish` boundaries without the step filter. It also has `question`, `waiting`, `missed`
and `done`.

**Invariant, tested:** the six groups are disjoint, and together they hold every row of
`list_items(show="all")`. A second test reruns Doug's case from the table above as a fixture:
each of those rows lands where this spec says.

The Class filter is applied to the views before the partition, so the counts match what is shown.

## The page

```
Doug                                   Check-in · Plan · Assignments · Report card
Done so far: 168 of 191 due · 85 on time.

[ To do ]  ·  Done                                         Class [All classes ▾]

TO DO  6
 Overdue           rows with the Plan's one-tap answers
 Tonight           step, if any, as a pencil line under the row
 Tomorrow
 Later this week   plain lines, no answers
 Later             folded to one line: "8 due Mon 10/12 – Fri 10/16"

CHECK WITH THE TEACHER  2      answered in place (_needs_now_row / _question as today)

▸ Waiting on a grade  2         folded <details>
▸ Missed — too late for credit  1   folded <details>
```

- The view toggle is two words in the sort line's grammar (ballpoint link, the current one in
  ink), not tabs or a filled button. `?view=done` selects Done, and the default is To do.
- An empty band is not printed. When To do is empty it is one quiet line in the child's tier
  (`copy.nothing_to_do`). Questions, waiting and missed are not printed when they are empty.
- Rows reuse `_item.html` at `line` density, with the answers from `_needs_now_row.html` for the
  overdue, tonight and tomorrow bands. No new card shape (section-and-card standard).
- The step line is the existing "Our step: … Edit" partial already used on the weekly pages.
- **Missed** rows say "Late work was accepted until Mon 10/5." in place of the contradictory
  present-tense "Late work is usually accepted until …". That fix is in
  `guidance`/`phrasing`, so it applies on every page.
- **Done view:** the current `_weeks.html` over the done group, newest week first (it is a
  record, so newest-first is correct here). It keeps the Class picker, the type links, Outcome
  and the sort, plus "Settled by the records" with its "Not right?" link.

Everything the child sees goes through `phrasing.PHRASES` (`copy.*`) at all three tiers: "To do",
"Done", "Check with the teacher", "Waiting on a grade", "Missed — too late for credit", the band
labels, and the empty line. Parity: every tier gets the same rows and actions.

## What goes

From `kid.html` / `routes/kid.py`: the Needs you now section (`_needs_now.html` is deleted;
`_needs_now_row.html` stays as the answer row), the Open · Everything toggle, More filters and
Rarely needed, the `q-lead` questions line, the type links on the to-do view, and "Waiting,
nothing to do yet". `needs_you_now()` is removed if nothing else calls it (only kid.py does today).

Kept as they are: `course.html` and its `_weeks.html` use, Check-in's `_must_finish.html`,
`open_work`, `must_finish`, and the printed sheet.

## Old URLs

`/kids/{key}?show=all|past_window|handled`, `outcome=`, `flagged=`, `verdict=`, `source=`,
`kind=`, `type=` and `sort=` keep working. Any of them except `course` opens the Done view with
that filter applied, through the existing `list_items`. A one-line note offers "Back to To do".
Links from Open work's "Not shown" counts (#125) and from the dashboard keep landing on a list
that shows what they counted.

## Testing

- Unit: the partition invariant; band boundaries at midnight (`deadline_date`, #139); a step
  never removes a row; the question rule for a to-do row; each row of Doug's table.
- Web: To do is the default, `?view=done` shows the weekly pages, old filter URLs open Done, an
  answer in place still swaps the row (`hx-target="#q-{id}"`), tier parity, and the
  page-layout and section-and-card guard tests.
- Existing tests that assert Needs you now or the filter form on `/kids/{key}` are rewritten to
  check the new behaviour, not deleted. `test_web_kid_questions`, `test_web_kid_table`,
  `test_web_tier_parity` and `test_web_section_and_card` are the main ones.
- A browser check on prod's copied database with venv Playwright: the first viewport on a phone
  and on a desk shows To do, and Doug's four "missing" rows are where the table says.

## Out of scope

The class page, Check-in, the Plan, the printed sheet, and any change to how outcomes or the
late-work window are computed.

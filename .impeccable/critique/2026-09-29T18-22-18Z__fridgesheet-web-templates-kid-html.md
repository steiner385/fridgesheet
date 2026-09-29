---
target: Assignments (the child's page), re-run
total_score: 25
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 1
target_identity: "file:/home/tony/GitHub/.ccswitch/worktrees/fridgesheet/6ab5c602/fridgesheet/web/templates/kid.html"
target_fingerprint: "sha256:00b2d854f03ce5db640da8382e01dd69fcad1f61d88b09c174e6d77c96fd8e5a"
target_path: /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/6ab5c602/fridgesheet/web/templates/kid.html
timestamp: 2026-09-29T18-22-18Z
slug: fridgesheet-web-templates-kid-html
---
Method: dual-agent (A: isolated design-review subagent · B: isolated detector-and-browser subagent), re-run after polish passes #219–#222. Browser evidence headless; no user-visible overlay.

## Design Health Score

### Today (fridgesheet/web/templates/dashboard.html) — 27/40, Acceptable (was 25)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "No sheet built today yet." beside a status bar saying this morning printed (the seed's run has no PDF file; the card only counts runs whose PDF exists) |
| 2 | Match system / real world | 3 | "3 to finish by tomorrow, 1 planned · 2 more on the list" asks the parent to do arithmetic |
| 3 | User control and freedom | 3 | Print two-step has Cancel |
| 4 | Consistency and standards | 2 | Today says 3, the Plan says Must finish 4, the plan panel says 3 not picked |
| 5 | Error prevention | 3 | "Refresh data first" sits beside Refresh now, not the buttons it modifies |
| 6 | Recognition rather than recall | 3 | Tally and question lines self-describing |
| 7 | Flexibility and efficiency | 3 | Every child page one tap away; the nightly path is a text link beside the boxed weekly one |
| 8 | Aesthetic and minimalist design | 3 | Tally is a 12-word underlined link; the h3 link leaves a 40px void on the phone |
| 9 | Error recovery | 2 | Nothing says what to do when Canvas fails |
| 10 | Help and documentation | 2 | "planned" unexplained |

### Plan (fridgesheet/web/templates/checkin.html + _must_finish.html + _plan_panel.html) — 26/40, Acceptable (was 26)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "The school's list as of …", counts, "New since" stamp |
| 2 | Match system / real world | 3 | Early tier: "When will you do it?" answered by the bold "I handed it in"; "Marked zero - ask about it" with no ask offered |
| 3 | User control and freedom | 3 | One-tap answers with Undo; Check Canvas again reloads |
| 4 | Consistency and standards | 2 | Three counts for one list; group h4 and item name the same 650 weight and size |
| 5 | Error prevention | 3 | Request keys per card; dismissals off Must finish |
| 6 | Recognition rather than recall | 3 | The sheet's word on the row; the pace inset |
| 7 | Flexibility and efficiency | 2 | First tappable answer at y=834 (Sam kid mode) on an 844px phone |
| 8 | Aesthetic and minimalist design | 2 | Four zero-count folds end Sam's page; 87px bold tab-hint; full-size Check Canvas again above the first row |
| 9 | Error recovery | 2 | No error state for a failed refresh from this page |
| 10 | Help and documentation | 3 | Late-until sentence, pace inset, sources hint (2,300px down) |

### Assignments (fridgesheet/web/templates/kid.html + _item_rows.html + _item.html) — 25/40, Acceptable (was 27)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "7 open", aria-sort, live region |
| 2 | Match system / real world | 2 | "Nothing to answer." (22.5px muted h3) over a child's page whose two rows are both red |
| 3 | User control and freedom | 3 | Close, Not right?, Open/Everything |
| 4 | Consistency and standards | 2 | `question` badge 44px beside `in plan` at 23px; the same row has a prompt on the Plan and none in its detail |
| 5 | Error prevention | 2 | Past-window row's default stroke is "Let it go" on the child's "you" page |
| 6 | Recognition rather than recall | 3 | Filters in plain words; rarely-needed ones folded |
| 7 | Flexibility and efficiency | 3 | Sort, class filter, Everything, sort state kept |
| 8 | Aesthetic and minimalist design | 2 | Phone sort-link header 140px tall (Sam); each row 189px plus a 41px phantom row (regression from #221, fixed in #222); an opened detail exposes 13 controls |
| 9 | Error recovery | 2 | Inline request-error; "Nothing matches these filters." |
| 10 | Help and documentation | 3 | Sources legend, zero note, record inset |

## Design Specificity Verdict

LLM assessment: specific in language, interchangeable in form. What is authored lives in words and rules: Must finish, still fixable, "Teacher hasn't got it", the sheet's word in the sheet's colour with the matching rule, the ask-line + default-stroke answer grammar, "Canvas OK · HAC OK". Strip the copy and a generic admin shell remains: system font, white cards on a grey wash, default selects, blue underlined links, a scrolling tab strip. "The Teacher's Ledger" is stated but not visible; the status word at the head's right is the single authored visual move, and the thing to build on. Today most generic; Plan most specific; Assignments a table with authored column names that turns generic at phone width.

Deterministic scan: templates 43 (42 the recurring rgb(0,0,0)-at-line-0 false positive on stylesheet-less fragments, 1 plan_print side-tab restating app.css); stylesheet 10 (8 side-tab left rules, 1 border-accent-on-rounded, 1 advisory 22px on the chooser). In-page: Today clean; Plan (Alex) 13 (line-length on tab-hint 95, legend 127, insets 111–117, facts 90, a step li 117; side-tabs on the four rows and two changed-insets; column-overflow); Plan (Sam) 4; Assignments 3; kid mode 4. Touch at 390px coarse: .tally a 56px, .card > h3 a 44, .item-foot a 44, td.item > a 44, .answers button 44, .more-answers summary 44, .print-confirm summary 44. No console errors on any page. Agreement between the two: line length on the tab hint and legend; the first row below the fold on a phone. Detector-only: none new. Review-only: the phantom hidden rows (a real regression), the three counts for one list, the early-tier zero row's directive with no ask.

## Overall Impression

The four passes did what they set out to do: the sheet's colours are on every row, one primary per page, verbs on the answers, tier-scaled headings, a Plan without empty groups, Print now in the card. The review still finds the same shape underneath: a generic shell around authored words, with the count mismatch now moved rather than solved and the phone list needing a second pass. The single biggest opportunity is unchanged and now sharper: commit to the status word as a ledger stamp and make the North Star visible.

## What's Working

- The sheet's word in the sheet's colour with the matching rule: the row on screen is the row on the fridge; the one visual idea that belongs to this product alone.
- The answer grammar holds everywhere: question line, one heavier-stroked default, plain neighbours, dismissals behind "More answers", one filled button per page (Plan zero, Today one, Check-in one).
- Print now as a two-step in the card: summary steps back when open, the question names the printer, both buttons 44px, the log behind Details.

## Priority Issues

### Today
- [P1] Three numbers for one list: Today "3 … 1 planned · 2 more", Plan "Must finish 4", plan panel "3 not picked yet". Fix: the big numeral is the Plan's own count ("4 on the Must-finish list · 2 due by tomorrow"), "1 planned" moves to the family-plan line. Command: /impeccable clarify.
- [P1] "No sheet built today yet." beside "Last run OK 7:00 AM printed": the card counts only runs whose PDF file exists. Fix: the card and the bar read the same run; a printed run with a missing PDF says "Printed 7:00 AM · PDF not kept". Command: /impeccable harden.
- [P2] The refresh tick sits beside the wrong button. Fix: the tick under Preview/Print as "Refresh first, then preview or print". Command: /impeccable clarify.
- [P2] The tally is a 12-word underlined link, 78px tall on the phone. Fix: link = numeral + ≤4 words, breakdown in a muted sentence beneath; `.big` scaled from the tier root. Command: /impeccable distill.
- [P2] Secondary links at 35–38px on the phone (Open plan, Assignments, outcome-line, class links) while PRODUCT.md says nothing under 44px. Fix: decide the rule; if 44, padding-block 11px, and make "Open plan" the boxed nightly action. Command: /impeccable harden.

### Plan
- [P1] Four empty folds end a nine-year-old's page (Completed steps 0, Worth a look 0, Waiting on school 0, Other open work 0). Fix: a zero-count fold renders as one muted line, keeping ids for the parity tests. Command: /impeccable distill.
- [P1] The first tap is a full screen down on the phone (first answer at y=834 Sam kid mode, 907 parent, 730 Alex). Fix: Print plan into "Our next steps"' controls; Check Canvas again a text link inside the lead; tab-hint weight 400 with only the date bold. Command: /impeccable layout.
- [P1] (early tier) The row tells the child to ask and offers no ask: "Marked zero - ask about it" with answers I handed it in / today / tomorrow; and "When will you do it?" over a bold "I handed it in". Fix: early "Zero" → "Marked zero"; when the first answer is handed-in the prompt is "Is it handed in? If not, when?"; or add Ask the teacher to zero rows. Command: /impeccable clarify.
- [P2] Group head and item name typographically identical (20px/650 both on Sam). Fix: `.sec h4` in Pencil Grey at 600, the size kept for the tier rule. Command: /impeccable typeset.
- [P2] Finish before review: "Agree and wrap up" with the page's one fill precedes the review queue. Fix: queue before the form, or the halves bar gets Review and the fill moves to the end. Command: /impeccable layout.

### Assignments
- [P1] Phantom rows on every phone list: `display: flex` on rows overrode `[hidden]`, so each folded detail row drew as an empty 17–41px box and a screen reader met seven empty rows. Regression from #221. FIXED in #222 (`table.items tbody tr[hidden] { display: none }`, test added). Command: /impeccable harden.
- [P2] The phone header is three bold blue links with no sort cue, 140px tall on Sam's page. Fix: one line "Sort by: Due ▲ · Assignment · Where it stands" at `--type-small`, or a single sort select under the strip. Command: /impeccable adapt.
- [P2] Two badges, two sizes (`question` 44px, `in plan` 23px). Fix: same pill box; extend the link's hit area invisibly. Command: /impeccable polish.
- [P2] Hard-coded 13px on a 20px page: `.seg label`. FIXED in #222 (`var(--type-small)`). Command: /impeccable typeset.
- [P2] The default stroke recommends dismissal ("Let it go" bold on the child's page) and the detail loses its prompt (plan_ask requires has_word). Fix: default only when is_q or plan_ask; drop has_word from plan_ask. Command: /impeccable clarify.
- [P3] "Nothing to answer." as a 22.5px muted h3 over two red rows. Fix: omit at zero or a lead line "No questions from the app". Command: /impeccable clarify.

## Persona Red Flags

- Alex: first "Do it today" at y=730 under Print plan, a four-line bold tab-hint and a Check Canvas again box; Homework 4 detail exposes 13 controls and bolds "Let it go"; every row carries "New since Tue 9/29" on the check-in's own day; "Nothing handed in yet." then "When will you work on it?" is the same fact twice.
- Sam (a11y): 7 empty rows on the phone list (fixed in #222); 13px chips (fixed in #222); the kid-mode strip's overflow signalled only by a fade, four links off-screen; "Sam" and "Plan" two links to one URL; aria-sort, 44px answers and the focus ring are fine.
- Casey: Open plan and Assignments 38px beside the boxed weekly action; two early-tier rows fill a phone screen; the only Close in a 706px detail is at its top; the check-in halves bar is the one thing built for her thumb and it works.
- Priya: 3 on Today, 4 on the Plan, 3 not picked; "1 question to answer" leaves for /questions when the same row is on the Plan she is about to open; on the phone the bar drops "printed 7:00 AM" so "No sheet built today yet." stands alone.
- Maya: three lines of bold instruction before anything she can do; "Check Canvas again" before Canvas is explained; "Marked zero - ask about it" with no way to ask; "picked" is not in the vocabulary table; her page ends on four zero headings; her Assignments opens with "Nothing to answer." above two red rows. Good: "Late, but you can still fix it", "Teacher hasn't got it", the late-until sentence, "I'll do it today".

## Minor Observations

- Spaced hyphens in "Marked zero - ask about it" and "On paper - check if it's handed in".
- `.close-detail` on the phone falls to its own line because `.item-head .when` takes the full row.
- `.card > h3 a` at 44px leaves a void under the child's name; the 44px belongs on the row.
- Three timestamps in the desktop status bar; the clock adds nothing.
- `.checkin-layout.plan-only` caps cards at the measure, contradicting the Measure Rule; a good choice to record, not drift.
- "Our next steps" opens with four lines of numbers before the first step.
- Kid mode still offers "Print plan" to the child.
- Both of Alex's step cards say "School evidence changed" on the day they were created (seed); the sentence needs a "what changed" or it will be ignored.
- "Coming due later" folds a row with the same "Do it today" answers as the tonight rows.

## Questions to Consider

- If the sheet is the product, why does Today lead with three counts of the app's lists and not the sheet: what printed this morning, what tomorrow's will say?
- Should the early tier have one child page with the first answer inline on each row, instead of three tabs?
- The review queue exists for the weekly check-in; what would the nightly Plan look like if it ended with the last step?
- Would committing to the status word as a ledger stamp (ruled row, word, the family's line in the margin) make "The Teacher's Ledger" visible instead of only documented?
- PRODUCT.md says nothing under 44px; app.css argues 24px for secondary links and ships 35–38px. Which rule is the product's, and which test holds it?

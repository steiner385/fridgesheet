---
target: Assignments (the child's page)
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/home/tony/GitHub/.ccswitch/worktrees/fridgesheet/6ab5c602/fridgesheet/web/templates/kid.html"
target_fingerprint: "sha256:ad85fc0f73296e7c12febb23e682db5f0413bb99473386f78a02af7795f0f7eb"
target_path: /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/6ab5c602/fridgesheet/web/templates/kid.html
timestamp: 2026-09-29T12-32-28Z
slug: fridgesheet-web-templates-kid-html
---
Method: dual-agent (A: isolated design-review subagent · B: isolated detector-and-browser subagent). Browser evidence was headless (Playwright Chromium); no user-visible overlay existed.

## Design Health Score

### Today (fridgesheet/web/templates/dashboard.html) — 25/40, Acceptable

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Status bar says "Last run OK · printed" while the sheet card says "No sheet built today yet" |
| 2 | Match system / real world | 3 | "2 not done, due by tomorrow" on Sam's card links to two rows already overdue |
| 3 | User control and freedom | 2 | Print now is a native browser confirm; no cancel once the job runs |
| 4 | Consistency and standards | 2 | Name links to Check-in, the tally to Plan, the question to /questions; "3" becomes "Must finish 4" on arrival |
| 5 | Error prevention | 3 | "Refresh data first" sits between Refresh now and Preview, scope ambiguous |
| 6 | Recognition rather than recall | 3 | Five zero-count record links and "0 new since yesterday" dilute the signal |
| 7 | Flexibility and efficiency | 2 | The nightly cross-kid list is not here; two page loads to see tonight |
| 8 | Aesthetic and minimalist design | 3 | Three equal-weight cards; the sheet card as loud as a child's |
| 9 | Error recovery | 2 | Failures are a black job log inside the card, or "error 500" |
| 10 | Help and documentation | 2 | Nothing says what Preview produces or that Refresh takes 1–3 minutes |

### Plan (fridgesheet/web/templates/checkin.html + _must_finish.html + _plan_panel.html) — 26/40, Acceptable

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | "The school's list as of …" is excellent; Check Canvas again dumps a console log into the section |
| 2 | Match system / real world | 2 | "[Today] [Tomorrow] [It's handed in]" has no verb; Today is filled and unexplained |
| 3 | User control and freedom | 3 | Undo after an answer is good; Check Canvas again has no cancel and reloads |
| 4 | Consistency and standards | 2 | Four filled primaries on one page; red word on a blue ask card; "Waiting" means three things |
| 5 | Error prevention | 3 | "Today" (creates a step) sits a thumb-width from "It's handed in" (closes the row) |
| 6 | Recognition rather than recall | 3 | Section heads carry meaning; badges reintroduce the sheet's capitals on a step |
| 7 | Flexibility and efficiency | 2 | Every row answered separately; no "plan all of tonight" |
| 8 | Aesthetic and minimalist design | 2 | Sam's Plan renders eight empty containers under two real rows |
| 9 | Error recovery | 3 | "School evidence changed" inset exists but repeats identically per step |
| 10 | Help and documentation | 3 | One lead sentence per section, the pace sentence, the sources hint |

### Assignments (fridgesheet/web/templates/kid.html + _item_rows.html + _item.html) — 27/40, Acceptable

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | Count swaps out of band, live region announces, filters dim |
| 2 | Match system / real world | 3 | Early tier reads "0/10 · Canvas" here and "Marked zero - ask about it" on Plan for the same row |
| 3 | User control and freedom | 3 | Close, Not right?, Undo all exist |
| 4 | Consistency and standards | 2 | "Ask the teacher" appears twice in one open card |
| 5 | Error prevention | 2 | More exposes six flag buttons with no confirm; a ten-year-old is offered "Too late to submit" |
| 6 | Recognition rather than recall | 3 | Plain column heads; question / in plan badges help |
| 7 | Flexibility and efficiency | 3 | Sortable, filterable, class links |
| 8 | Aesthetic and minimalist design | 2 | Phone table wraps "Where it stands" to four lines; seven identical underlined class links |
| 9 | Error recovery | 3 | Same as Plan |
| 10 | Help and documentation | 3 | Legend under the table; the Record inset explains the zero |

## Design Specificity Verdict

LLM assessment: authored words inside a generic shell. Everything unmistakably this product lives in the vocabulary and in one component: the sheet's status word at the right of an item head, the facts → ask → one-tap-answer grammar, the family layer with its blue rule, the tiered phrasing, the status bar reading like a ledger header. Remove those and what remains is a FastAPI admin template. The North Star promises ruled paper; the screen shows a grey wash with no rule, margin or stamp. Plan is the most specific surface; Today the most generic; Assignments half and half.

Deterministic scan: templates scan 44 findings, 42 of them one false positive per file (pure-black text computed on stylesheet-less fragments). Stylesheet scan 13: eight side-tab left rules (.item, .notice, .note, .case, .conflict, .ours, .inset.warn, .done-line), one border-accent-on-rounded (.child-nav a[aria-current]), four design-system-font-size off the ramp (22px .who button and .sec-head h3.kid-head, 20px .card h3.report-title, 14px .filters label). In-page detector: Today clean; Plan (Alex) 18 findings (line-length 90–127 chars on .tab-hint, .lead, .legend.sources-hint, .facts, .inset; heading-rhythm on three quiet folds; five side-tabs; one column-overflow); Plan (Sam) 5 including flat-type-hierarchy (h3/h1 18px under body 20px); Assignments 3. Agreement: heading scale on the early tier, line length, first row below the fold. Detector-only: off-ramp sizes. False positives: the 42 colour findings; column-overflow ratios are environment-dependent.

## Overall Impression

The product's thinking is far ahead of its face. The rule table, the verdict grammar, the phrase table and the item card are genuinely authored. Around them sits an admin shell that treats the sheet as one settings card, spends red on things the school never recorded, and hands a nine-year-old the smallest headings and the most adult buttons on her page. Biggest opportunity: make the Plan look like the child's sheet section and let Today be a doorway to tonight rather than a dashboard.

## What's Working

- The item card's grammar (_item.html): head with the sheet's word pushed right, one sentence of facts, one bold ask, one-tap answers, the family layer, a folded Record, the Undo done-line. The same box on three pages.
- The phrase table as a mechanism: tiers change the words and not the rows, and the words are kinder without lying.
- One rule table made visible: the "School record so far" line with five linked counts, and the status bar naming both sources with their state.

## Priority Issues

### Today
- [P1] The headline number changes meaning on arrival. "3 not done, due by tomorrow" opens a Plan that says "Must finish 4"; Sam's "2 due by tomorrow" are already overdue. Fix: tally reads the same count as the section it opens; say "to finish". Command: /impeccable clarify.
- [P1] Print now is a browser dialog and a console log (hx-confirm, pre.log). Fix: inline two-step in the card naming pages and printer, progress as a sentence, log folded under Details, end on "Printed 7:02 AM · open the PDF". Command: /impeccable harden.
- [P2] Card anatomy puts the weekly button before the nightly tally. Fix: tally first and the card's primary target, links in the foot, drop "0 new since yesterday" when zero. Command: /impeccable distill.
- [P2] Touch floors miss on the phone: tally links 38px, child name links 22px, checkbox label 20px at 390px. Fix: add to the coarse-pointer 44px block. Command: /impeccable adapt.

### Plan
- [P1] The one-tap answers have no verb: "Nothing handed in yet." then [Today] [Tomorrow] [It's handed in] with Today filled. Fix: an ask line for plan rows ("When will you do it?") and verb labels ("Work on it today / tomorrow / It's already handed in"). Command: /impeccable clarify.
- [P1] Red is on things the school did not record: .item-head .when.word is always --warn 700 (app.css:490), so DUE TODAY, DUE TOMORROW, HAC — NO GRADE are red, the last on a blue ask card. Fix: colour the word by the row's tone; red only for tone red, ink for DUE words. Command: /impeccable colorize.
- [P1] Headings do not scale with the tier: .sec-head h3 18px (app.css:457) and .sec h4 15px (app.css:471) under the early 20px body. Detector agrees (flat-type-hierarchy). Fix: h3 at 1.125× --type-root, h4 at --type-root, and main h3/h4 likewise. Command: /impeccable typeset.
- [P1] Multiple filled primaries: every Must-finish row's first answer is .primary; Alex's page shows four. Fix: a default-answer style (ink text, 2px ink border, 600) and the fill reserved for Finish check-in. Command: /impeccable quieter.
- [P2] Empty containers outnumber content on Sam's Plan: three "No steps here yet." groups (_plan_panel.html:11-25) and four zero-count folds (checkin.html:36-46). Fix: render a state group only when it has a step; collapse zero folds to one line. Command: /impeccable distill.
- [P2] The first row is below the fold on a phone (about y=1150 at 390px): Print plan, tabs, check-in line, section head, 44px Check Canvas again, three-line lead (95 chars; tab hint 127). Fix: Print plan to the foot on the strip, Check Canvas again as a link inside a one-sentence lead. Command: /impeccable layout.

### Assignments
- [P1] Same row, two vocabularies: Plan says "Marked zero - ask about it"; the table says "0/10 · Canvas" (_item_row.html:17). Fix: the third column reads the tier's sheet word first and drops the source suffix on early/middle. Command: /impeccable clarify.
- [P1] The table does not survive the phone: at 390px the phrase wraps to four lines in a 110px column, Due to four lines, class links 35–39px. Fix: render _item_rows.html as .lines under 1024px. Command: /impeccable adapt.
- [P1] The opened detail is a form, not a card: 17 interactive things, "Ask the teacher" twice (_item.html:53-59, _flag_menu.html:9). Fix: More offers only flags not already offered as answers; Email and Open in Canvas inside Record. Command: /impeccable distill.
- [P2] Filters expose eleven-way selects (kid.html:22-28). Fix: Open / Everything / Class visible; Outcome and a five-state answer filter behind Narrow. Command: /impeccable distill.
- [P2] Seven identical underlined class links. Fix: underline on hover/focus only, or a chip that sets the Class filter. Command: /impeccable polish.

## Persona Red Flags

- Alex (power user): "It's handed in" is the third button while Today is filled; Check Canvas again is a 1–3 minute job with reload and no cancel; no multi-row answer.
- Sam (screen reader / keyboard / low vision): headings inside disclosure summaries; ▸/▾ glyphs read aloud (app.css:469, 504); 1px rule and control stroke 2.95:1 against white; phone table scrolls sideways with no cue.
- Casey (one-handed phone): Print now 1,600px down Today; first Plan row a screen and a half down; "Today" beside "It's handed in" at thumb width.
- Priya (nightly phone check): no cross-kid tonight list on Today; three pages; the number changes 3 → 4; no end state.
- Maya (nine, early tier): smallest headings; Print plan first under her name; tap "Today" with no sentence; four empty boxes; strip offers Trends and Changes; offered "Too late to submit", "Let it go", "Excused".

## Minor Observations

- Phone strip renders "Alex1" with no space before the count.
- "Add a task" is the only place the word task appears; everywhere else says step.
- "Waiting" is used four ways; the same fold is "Worth checking" (older) and "Worth a look" (early).
- Literal #fdecea twice in app.css (:88, :342), contrary to DESIGN.md's Don't.
- The "School evidence changed" inset is red and is the app's inference.
- In kid mode the strip's first two links go to the same URL.
- Sizes 22px, 20px, 14px are real steps the DESIGN.md ramp lacks.

## Questions to Consider

- If the sheet is the product, why doesn't Must finish look like the child's sheet section, with the answers underneath?
- Why does one child need three tabs?
- Is Today a dashboard or a doorway? Should it be Open work with the sheet's controls beneath?
- Parity of rows is the law; is parity of actions the open question?
- Does red belong on a child's screen at all?

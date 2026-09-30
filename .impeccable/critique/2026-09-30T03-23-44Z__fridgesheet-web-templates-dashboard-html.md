---
target: Today (the household page), re-critique after the Student Planner
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
target_identity: "file:/home/tony/GitHub/.ccswitch/worktrees/fridgesheet/6ab5c602/fridgesheet/web/templates/dashboard.html"
target_fingerprint: "sha256:8bd8c34ac36150a60a1c69f8fd0ca6fbb52a87170c14184515d3d0fe4f64817c"
target_path: /home/tony/GitHub/.ccswitch/worktrees/fridgesheet/6ab5c602/fridgesheet/web/templates/dashboard.html
timestamp: 2026-09-30T03-23-44Z
slug: fridgesheet-web-templates-dashboard-html
---
Method: dual-agent (A: isolated design-review subagent, 51 captures at 1440/390/200% zoom, family and kid mode · B: isolated detector-and-browser subagent: CLI scan, live-server overlay injected on all five pages, coarse-pointer measurements, contrast, console, keyboard). Re-critique after the Student Planner shipped on the Plan (#224), Today (#225), Assignments (#226) and the token source (#227). B's notification arrived before A finished; synthesis waited for A. No `.impeccable/critique/ignore.md`.

## Design Health Score

### Today (fridgesheet/web/templates/dashboard.html) — 27/40, Acceptable (was 27)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | The strip says TONIGHT · Sam 2 (overdue counted under tonight) while Sam's Plan prints "Nothing due tonight" in the DUE TONIGHT box |
| 2 | Match system / real world | 3 | Two voices on one spread: Alex's line offers "It's handed in", Sam's "I handed it in"; the parent taps a first-person answer for the child |
| 3 | User control and freedom | 2 | After an answer, Undo renders as a vertical column of letters on the phone (47×85 px older, 56×64 early); Cancel on the print two-step drops focus to body |
| 4 | Consistency and standards | 2 | The child's tier vocabulary leaks onto the household page; two Display numerals with different referents per box |
| 5 | Error prevention | 4 | The Print two-step: in place, names the printer, one filled Print, Cancel a link |
| 6 | Recognition rather than recall | 3 | "1 planned · 2 more on the list": which list needs the Plan's arithmetic |
| 7 | Flexibility and efficiency | 2 | Phone: first tappable answer at y=827 on an 844 px viewport; the sheet strip's four boxed controls (300 px) are paid on every visit |
| 8 | Aesthetic and minimalist design | 3 | Each kid box: two tally links, lines, family line, three links, a fold: five routes into one child's pages |
| 9 | Error recovery | 3 | Stale banner and request errors exist; nothing says what a failed print looked like once the job partial is gone |
| 10 | Help and documentation | 2 | "still fixable" and "on the list" undefined here |

### Plan (checkin.html + _must_finish.html + _plan_panel.html) — 29/40, Good (was 26)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | After "I handed it in" the line keeps its red highlighter beside a green tick and a struck name: three signals, two contradicting |
| 2 | Match system / real world | 4 | Day boxes, "Teacher hasn't got it", "When will you do it?", the late-window sentence |
| 3 | User control and freedom | 2 | Undo letter column on the phone (46×113 older, 50×136 early); desktop Undo fine |
| 4 | Consistency and standards | 3 | Step lines draw the checkbox but nothing ticks them; "Edit or complete step" is a page away |
| 5 | Error prevention | 4 | Dismissals excluded from the Plan; one request key per answer; Undo |
| 6 | Recognition rather than recall | 3 | "3 must-finish not picked yet" beside "Must finish 4" |
| 7 | Flexibility and efficiency | 2 | "Check Canvas again" is a 149×23 px button on the phone (`min-height: 0` under 1024 px) that starts a 1–3 minute job; Sam's first answer at y=1,120 in kid mode |
| 8 | Aesthetic and minimalist design | 2 | Sam's page: two empty printed boxes, "No steps here yet", four "nothing here yet" lines: six empties for two rows |
| 9 | Error recovery | 3 | Undo is the recovery and it is unreadable on the phone |
| 10 | Help and documentation | 3 | The facts sentence is the help; "Print plan" says nothing about what prints |

### Assignments (kid.html + _weeks.html + _week_line.html + _verdict_sections.html) — 28/40, Good (was 25)

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | The lead says "1 question about your work" over 5 ask lines and 24 buttons (Alex); "Nothing to answer." over 8 buttons (Sam) |
| 2 | Match system / real world | 4 | Weeks and day rows are how a child thinks about school; "Where it stands" is the one sort key that names nothing |
| 3 | User control and freedom | 3 | Close restores the line and focus (measured), but sits only at the top of a 757 px record on the phone |
| 4 | Consistency and standards | 2 | The opened record drops the line's tone and its highlighter word; the Waiting fold below uses the other line vocabulary (glyphs in a white box) |
| 5 | Error prevention | 2 | "More answers" holds "Too late to submit" and "Let it go" one tap away on a nine-year-old's line |
| 6 | Recognition rather than recall | 3 | "More answers" hides which; "Open" does not say what it excludes |
| 7 | Flexibility and efficiency | 3 | Sort, class and filters survive htmx; 7 head controls before the first line on Sam's phone (first line y=704, first answer y=992) |
| 8 | Aesthetic and minimalist design | 2 | 8 tappables per open line, 56 on Alex's page, 3,709 px on the phone |
| 9 | Error recovery | 3 | Lines come back on Close; answers have Undo; the list announces its count |
| 10 | Help and documentation | 3 | Sources hint under the pages; nothing explains the sort keys or the "open" set |

## Design Specificity Verdict

LLM assessment: authored, on all three. With the words removed the Plan is two ruled day boxes of checkbox lines with a highlighter stripe; Today is a five-cell week over one printed box per child; Assignments is a stack of ruled week boxes, the top one open, the ones below thinner. The planner line, the box grammar (1.5 px rule, label along the top edge, yellow stroke for "now") and the ruling are shared by all three, and the colour discipline holds: one filled blue on Today, none elsewhere. Where the world thins: inside Today's kid box (two Display numerals, a three-link nav row, a fold: the old card's furniture inside the planner's border), below the Plan's spread (a review queue in admin IA), and in Assignments' head (a filter bar) and its lines (every open line is a form). The shell around all three, rail, status bar and page head, is still the incumbent ledger and costs 150–190 px on every phone screen. Plan most specific; Assignments close behind; Today's spread is right and its box interior is not.

Deterministic scan: 17 findings on the eleven files (5 warnings, 12 advisories). Ten `design-system-color` advisories are the recurring rgb(0,0,0)-on-a-stylesheet-less-fragment false positive; the `repeating-stripes-gradient` advisory is the planner ruling (`.planner-main`, misattributed to base.html) and is the world, not drift; `border-accent-on-rounded` on `.child-nav a[aria-current]` is a false positive (no radius); the four `side-tab` warnings (`.notice`, `.note`, `.case`, `.conflict`) predate the world and none rendered on the five pages; `design-system-font-size` is the chooser's 22 px, off-surface. Nothing new from the three builds.

Visual overlays: injection succeeded on all five pages via the live server (port 8400, stopped afterwards); no user-visible tab, headless. Per page: Today 4 (two text-occlusion artefacts on closed folds, column-overflow, cream-palette, the ruling); Alex's Plan 14 (eight line-length findings at 127–165 characters: the check-in summary line, the "no earlier grades" inset, the Participation facts, the two "School evidence changed" notices, the sources legend); Sam's Plan 5; Alex's Assignments 9 (five line-length ~95–127; two occlusion artefacts); Sam's Assignments 5. Every occlusion target sits in a closed `<details>`, an artefact of Chromium keeping layout boxes for folded content. The line-length findings on the Plan are real: prose there runs to 1,070 px wide at 1440 (measured `p.facts` and `.ask-line` in `.sec.plan`); the same prose on Assignments is capped at 760 px.

Agreement between the two: the Plan's unbounded prose (A: the page "tails into the check-in's review queue"; B: eight line-length findings at up to 165 characters and 1,070 px paragraphs); the under-44 px "Check Canvas again" button and the 18 px kid-name links on Today (A measured them; B's coarse-pointer sweep lists exactly those, plus "Edit" at 23×18 on Assignments and "Browse all work" at 118×22 on the Plan); focus handling on Close (both: focus returns to the name) and on Cancel (both: focus to body). Detector-only: none material. Review-only: the Undo letter column (B's interaction pass ran at 1440 where Undo is fine; A measured it at 390 on all three surfaces); the two-voice spread on Today; the "TONIGHT" count contradiction; the record view losing its tone. Contrast (B, computed): nothing under 4.5:1 on the seeded pages, lowest MISSING on its highlighter at 5.02; A adds one pair B could not measure because no LATE row is seeded: `--late` #9a5b00 on `--hl-late` #ffe4b8 computes to 4.40:1 at the root and older tiers (early 5.18, middle 4.82), so the one LATE word on its stroke is under AA for a 16 px bold word.

## Overall Impression

The three surfaces are one world now, and the scores moved the way the roadmap said they would: Plan 26 → 29, Assignments 25 → 28, Today flat at 27. What used to be "authored words on a generic shell" is authored composition; what remains is the shell itself and three seams where the old product shows through: Today's box interior, the Plan's tail, and Assignments' lines-as-forms. The single biggest opportunity is one CSS rule: the shared `.done-line` breaks Undo into a vertical column of letters on every phone, on every surface, at the exact moment the signature interaction ends. After that, decide what "tonight" means once, and give Today one voice.

## What's Working

- The planner line is app-wide: Vocabulary is drawn by the same partial on Today, the Plan and Assignments with the same checkbox, the same DUE TODAY stroke, the same default-stroke answer, the same foot, the same strike and Undo. Learned once, known everywhere.
- The Print two-step is the model for every consequential action in the product: in place, names the printer, one filled button, Cancel a link, focus and announce correct except the Cancel landing.
- The weekly pages and the five-cell week strip are the two most product-specific compositions in the app, and both survive 390 px without sideways scroll, with the current week's word on the yellow stroke and the newest week first.
- Colour and contrast discipline held through three builds and the token extraction: no literal colours in the surfaces, one filled primary on one page, every seeded word-on-highlighter pair above 5:1.

## Priority Issues

### Every surface
- [P0] Undo is a vertical column of letters on the phone. What: `.done-line` is a flex row with `overflow-wrap: anywhere` inherited from `.item` and `form { margin-left: auto }`; at 390 px Undo measures 47×85 (Today, older), 56×64 (Today, early), 46×113 and 50×136 (Plan). Why: it is the only exit from the signature interaction, on all three surfaces, and it looks like a rendering fault. Fix: `.done-line form, .done-line button { flex: none; white-space: nowrap; overflow-wrap: normal; }` and `.done-line > span:not(.glyph) { flex: 1 1 auto; min-width: 0; }`. Command: /impeccable polish.
- [P1] Prose on the Plan is unbounded: `p.facts` and `.ask-line` run to 1,070 px inside `.sec.plan` and `.mf-spread` at 1440 (eight overlay line-length findings at 127–165 characters), while Assignments caps the same prose at 760 px. Fix: apply the Measure Rule to `.mf-section .item > p`, the plan panel's lines and the lead, as `.week .item > p` already does. Command: /impeccable layout.
- [P1] Small controls under the product's own floors: "Check Canvas again" 149×23 px (Plan, phone; `.sec-head .controls button { min-height: 0 }`), "Browse all work" 118×22 (Plan), "Edit" 23×18 on a step line (Assignments), the kid-name label links 36×18 / 32×18 (Today). Fix: 44 px for the button and the main links, 24 px with padding for the secondary ones, in the coarse-pointer block. Command: /impeccable harden.
- [P2] The LATE word on its highlighter is 4.40:1 at the root and older tiers (`--late` on `--hl-late`), under AA for a 16 px bold word; early and middle pass. Fix: darken `--late` at the root to about #8a5200 (the early value, 5.18:1) or lighten `--hl-late`; the printed sheet inherits the same token, so one change in tokens.py. Command: /impeccable colorize.

### Today
- [P1] "TONIGHT" means two things. What: the strip counts overdue-still-fixable under TONIGHT (Sam 2) while Sam's Plan prints "Nothing due tonight" in the DUE TONIGHT box. Why: the one number a parent carries to the next page is contradicted there. Fix: the tonight cell says the word beside the count ("Sam 2 late") or overdue gets its own cell left of the five days; never fold two outcomes into one date. Command: /impeccable clarify.
- [P1] Two voices on one spread. What: each kid box takes its child's tier for the ask line and the answers, so the parent sees "It's handed in" in Alex's box and "I handed it in" in Sam's, and taps first-person answers for a child. Fix: Today renders ask lines and answers in the parent's phrasing; the child's tier stays on the sheet's word only. Command: /impeccable clarify.
- [P2] On the phone the first screen is controls, not the planner: the sheet strip's four boxed controls are 300 px, the first line at y=658, the first answer at y=827. Fix: under 1024 px the strip collapses to its sentence plus one "Print or preview ▸" disclosure, and the week strip moves above it. Command: /impeccable adapt.

### Plan
- [P1] Empty day boxes cost the child her first screen on the phone: Sam's two empty boxes plus the lead push the first line to y=839 and the first answer to y=1,120 in kid mode. Fix: under 1024 px, when Tonight and Tomorrow are both empty, print them as one shared box ("TONIGHT · TOMORROW · Nothing due") or as single labelled lines; keep both on wide screens as the contract says. Command: /impeccable adapt.
- [P2] Step lines draw a checkbox nothing ticks; completing a step is a page away. Fix: a one-tap "Done" on each live step with the same strike and Undo. Command: /impeccable delight.
- [P2] The page tails into the check-in's review queue (Worth checking, Waiting on the school, Other open work, Previous agreements) under a planner, with four "nothing here yet" lines on Sam's page. Fix: on the Plan, one line ("2 more on the school's list · Browse all work") and Previous agreements behind the header line. Command: /impeccable distill.
- [P3] After "I handed it in" the struck line keeps its red highlighter at full strength beside a green tick. Fix: on a done-line the stroke drops to an outline until the record catches up. Command: /impeccable polish.

### Assignments
- [P1] The lead and the page disagree: "1 question about your work" over five ask lines and 24 buttons (Alex), "Nothing to answer." over eight buttons (Sam), because every open line carries the plan prompt and answers. Fix: only lines the app asks (`is_q`) get the ask line and answers; the rest get one "Plan it" link in the foot; then the lead is true and a settled week prints with no buttons in it. Command: /impeccable distill.
- [P1] The opened record leaves the world: `card_for` renders the detail without `tone` and `word`, so the checkbox rule turns grey and "Marked zero - ask about it" becomes plain 13 px grey. Fix: pass word, word tone and tone through the `?card=row-` detail so the head is identical between line and record. Command: /impeccable polish.
- [P2] Close sits only at the top of a 757 px record on the phone. Fix: repeat Close in the foot at detail density and keep the top one on the head row. Command: /impeccable adapt.
- [P2] The head on a child's phone: seven controls before the first line (first line y=704, first answer y=992 in kid mode, with two assignments and one class). Fix: under 1024 px fold Class and Sort into More filters when the child has one class, and print the sort line only with two or more open weeks. Command: /impeccable adapt.
- [P3] The Waiting and Settled folds under the pages use the glyph-in-a-white-box line density: the Only-Box Rule broken quietly at the foot. Fix: draw them as planner lines with a grey dashed checkbox. Command: /impeccable polish.

## Persona Red Flags

- Alex (impatient parent, phone at night): 827 px to the first answer on Today with "Refresh now" first under the thumb; Undo unreadable on every surface; 3,709 px of Assignments for seven open lines; "Edit" at 23×18.
- Sam (keyboard, screen reader, zoom): focus rings are consistent (3 px ballpoint) and Tab order is sane (rail, status, tabs, controls, sort, first name, first answer at Tab 17 on Assignments); Close returns focus to the name; Cancel on Print drops it to body; the drawn checkbox has no text equivalent, so "checked off" lives only in the announce string; the hidden Show radios are announced before the visible Class select; the `h3` sizes on the Plan jump 18 → 16 → 18 so the outline reads as two levels. No horizontal scroll at 200% zoom on any page.
- Casey (one thumb): the Print now summary is 8 px under Preview; "More answers" sits 8 px under the third answer at the same x, holding "Let it go"; three stacked answers at the early tier put the second where a thumb rests while scrolling.
- Priya (one number to trust): four numerals per child on Today (3, 1 planned, 2 more, 1 question) plus the strip's "Sam 2" that the Plan then denies; on Assignments, "7 open" and "1 question" before the one sentence she wants ("Done so far: 1 of 5 due · 1 on time").
- Maya (nine, kid mode, early tier): her Plan opens on two empty boxes and her first red row at y≈839; her Assignments opens on Show, Class, More filters and Sort by before the first line at 704; "Where it stands" is not her phrase; "More answers" is a fold she will open, and it holds "Let it go".

## Minor Observations

- Week-strip labels on the phone are 12 px bold uppercase, the smallest text on a parent's night page, and "nothing due" wraps in three cells.
- Both of Alex's steps carry the same "School evidence changed since this step was saved" inset; if it is always true after a refresh it is noise.
- Kid-mode desktop rail: "Not Sam?" is a 35 px link.
- The ruling behind the Plan's lead misregisters at the early tier (29 px pitch under a 20 px root).
- "Nothing due tonight" is 20 px muted under a 16 px label at the early tier, inverting the box's hierarchy.
- The sort chevron is about 9.6 px; readable only because weight and `aria-current` carry the state.
- "7 open" does not change when a filter narrows to nothing, and "Nothing matches these filters." then prints under an open THIS WEEK box that also says "Nothing due this week": two empties in a row.
- `aria-current="true"` on the sort links would be more precise as a sort token.
- The four side-tab rules the detector flags (`.notice`, `.note`, `.case`, `.conflict`) are still in app.css and appear on Settings, Reports, the step form and the print plan: the next surfaces to bring into the world.

## Questions to Consider

- If the sheet is the product, why does Today show the screen's list (must finish by tomorrow) rather than the sheet's (overdue first, then coming due) that prints at 7 am?
- Should a parent ever tap "I handed it in" for a child, or should Today offer only the parent's answers?
- Is Assignments the child's record, where the only tap is a name, or a second Plan?
- After "I handed it in", what is the truer planner: a red word at full strength on a struck line, or an outlined word until the school's record catches up?
- Why is Check-in a tab a nine-year-old sees on her own device at all?
- Would the shell (rail, status bar, page head) drawn in the world do more for every page than another pass on any one of them?

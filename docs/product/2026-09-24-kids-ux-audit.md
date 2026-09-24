# The child-facing pages against the published standards for children's UX

Date: 2026-09-24. Asked for by the maintainer: *"The child-facing UI still isn't what I want
it to be. Research latest accepted UI/UX standards for kids and audit our UI surfaces against
them."* This is the research, the audit, and a ranked list of what to change. It changes no
code.

## 1. Who the readers actually are

The household's children are in 5th, 7th and 9th grade: roughly 10, 12 and 14 years old. That
places them in the top band of every children's framework and the bottom of every teen one,
and it rules a lot of "design for kids" advice out. Skeuomorphic metaphors, audio feedback,
no-scroll layouts and 2 cm tap targets are guidance for 3–8-year-olds and do not apply.

What does apply, from the sources in section 2:

| reader | framework band | what the research says they do |
|---|---|---|
| 5th grade (10–11) | NN/g "older children" (9–12); RITEC's 8–12 study group | Read and scan, but skip any paragraph of instructions; reject anything pitched one grade too young *or* too old; cannot interpret an error message; expect a reaction to every tap; prefer touch to a mouse until about 9 |
| 7th grade (12–13) | NN/g older children / early teen overlap | The same, plus a sharp nose for being talked down to |
| 9th grade (14–15) | NN/g teens (13–17) | Read less than adults and below their nominal level; abandon on the first friction; want scannable, professional-looking pages; find the word "kids" repellent; mobile first |

The one sentence that governs the whole audit is NN/g's: *"There's no such thing as 'designing
for children' defined as everybody aged 3–12."* The app's three tiers already agree with that.
The question is whether each tier is right for its reader.

## 2. The standards, distilled

Twelve criteria, each traced to its source. Section 4 audits against these numbers.

| # | criterion | source and the specific finding |
|---|---|---|
| S1 | **Text size floor.** 12 pt (16 px) for 9–12-year-olds, 14 pt for younger; teens dislike small type as much as adults | NN/g children's report (4th ed.); NN/g teens |
| S2 | **Reading level matches grade.** Adult web copy targets grade 8–10; children's copy must sit at the reader's own grade, and teens do best at grade 6 or below | NN/g children; NN/g teens |
| S3 | **Short instructions.** Children skip paragraphs of instructions; teens want scannable chunks with white space | NN/g children (all three studies, 2001–2018); NN/g teens |
| S4 | **Tap targets.** 24×24 CSS px minimum (WCAG 2.2 SC 2.5.8, AA); 44–48 px is the comfortable size on every platform guideline; children should get *larger* than adults | WCAG 2.2; NN/g physical development |
| S5 | **Contrast** 4.5:1 for text, 3:1 for UI boundaries; **meaning never by colour alone** | WCAG 2.2 SC 1.4.3, 1.4.11, 1.4.1 |
| S6 | **Feedback on every action**, and forgiving interactions with an undo rather than punishment for a slip | NN/g children; Gelman, *Design for Kids* |
| S7 | **One navigation.** Redundant or multiple navigation schemes confuse children badly; parent-facing tools should be kept visibly apart from the child's space | NN/g children (text footers "bury" parent content); ICO Children's Code standard 3 (age-appropriate application) |
| S8 | **Errors a child can act on.** Children cannot root-cause; they retry, reload and then leave | NN/g children |
| S9 | **Consistency**, including consistency of voice: the same fact rendered the same way everywhere, and a page that does not bounce the reader between age registers | NN/g children |
| S10 | **Autonomy, competence, emotions.** UNICEF's RITEC-8 (787 children aged 8–12, 18 countries) names these as the well-being dimensions design most affects; a design must not *reduce* any of them. Self-regulated-learning studies (2025) find that offering choice raises homework completion, and that predictable structure lowers homework anxiety while chaos raises it | UNICEF RITEC-8 framework and Design Toolbox (2024); Springer *Social Psychology of Education* and *Metacognition and Learning* (2025); PMC 2024 homework-anxiety study |
| S11 | **Best interests, transparency, no manipulative nudges, child-friendly explanations.** The UK Children's Code's 15 standards, now embedded in UK GDPR Article 25 (Data (Use and Access) Act, June 2025). The nudge standard forbids nudging children toward choices against their interest and *permits* nudges toward it | ICO Age Appropriate Design Code; 5Rights *Child Rights by Design* (11 principles: agency, well-being, age-appropriate, participation, consultation) |
| S12 | **Design with children, not only for them.** The first principle of D4CR (*Gather and respect children's views*), of 5Rights (*Consultation*, *Participation*) and of RITEC's method | D4CR guide (10 principles, 2022 revision against UN General Comment 25); 5Rights; UNICEF |

Standards that do **not** bind this product, and why: the Children's Code's data standards
(minimisation, sharing, geolocation, profiling, connected toys) are met trivially because
nothing leaves the machine and no account exists; the advertising guidance (D4CR principle 9,
NN/g's largest single finding) is moot because there is none; the play-oriented RITEC
dimensions (creativity, relationships, identities) apply weakly to a homework tool. Those are
noted so they are not re-litigated, not because they were skipped.

## 3. How the audit was done

- Every child-facing surface named in the age-appropriate UI spec (`docs/superpowers/specs/2026-09-22-age-appropriate-ui-design.md` §6) plus the two the child actually lands on from the rail: **Assignments** (kid page), **Check-in**, **Plan**, **Plan print**, the **step form**, **Open work**, **Questions**, **Today**, and the **printed sheet**.
- Rendered against `tests/web_fixtures.py`'s snapshot, dates shifted so 2026-09-24 is "today", at 1280×800 and at 390×844 with touch, once per tier (`grades = { Alex = 9, Sam = 5 }`, then `Sam = 7`). `scripts/kids_ui_measure.py` is the script; it records body type size, the tier attribute, words in `<main>`, interactive elements, how many are under 24 px and under 44 px, the smallest rendered font, page height in screens, and horizontal overflow.
- Contrast ratios computed from the four palette blocks in `app.css` and the hard-coded check-in colours.
- Flesch–Kincaid grade computed for the phrase table per tier and for the fixed copy in each child template (crude: it treats template fragments as prose, so figures over about 10 mostly mean "long unbroken lines", not "hard words").
- Browser checks were Chromium only. No child was observed (see finding F1).

## 4. What already meets the bar

This is a stronger baseline than most children's products start from, and the findings in
section 5 should be read against it.

- **Contrast (S5).** Every text token clears 4.5:1 on both paper and wash in every tier; the early tier is the strongest (ink 18.3:1, muted 7.5:1, warn 7.8:1). White on the primary button is 6.4–7.7:1. The check-in's hard-coded greens and ambers all clear 6:1.
- **Colour never carries meaning alone (S5).** Red is always red *and* a word; `test_web_tier_css.py` and `test_web_a11y.py` hold it, and the printed sheet's legend restates every colour in words.
- **Type scale (S1, partly).** Body type at 20/18/16 px across the tiers exceeds NN/g's 12 pt floor for 9–12-year-olds. See F2 for what it does not reach.
- **Vocabulary (S2).** The phrase table reads at Flesch–Kincaid grade 0.3 (early), 0.7 (middle), 0.9 (older) over ~500 words. "Teacher hasn't got it" and "Can still fix" are exactly the simpler-true-statement the spec asked for, and `test_web_tier_parity.py` guarantees simplification never becomes concealment. That is the Children's Code's transparency standard done properly, which almost nobody does.
- **Feedback and forgiveness (S6).** Every one-tap answer swaps in a tick line with an **Undo**, moves focus to it, and announces it to a screen reader; a refused request prints the server's reason beside the button. The check-in defaults to a 40-minute budget and says, in one sentence, when the plan exceeds it: that is the "predictable structure" the anxiety research asks for.
- **Autonomy (S10, S11).** "Let it go", "Too late to submit", "Today" and "Tomorrow" are the child's choices, and the step's owner defaults to the child. Nothing nudges toward more screen time; the one nudge the app makes is toward planning a step, which is in the child's interest.
- **Tap targets on controls (S4).** Buttons, selects, inputs, rail links and check-in links are 44 px under a coarse pointer, and no page overflows horizontally at 390 px.
- **Errors (S8).** Form errors keep the typed values, land in a `role="alert"` with focus, and say what to change in a sentence.

## 5. Findings, ranked

Severity weighs how many of the three readers it affects and how directly the standard speaks
to it. "Where" names the file to open, not every line.

### F1. Nobody has watched the three readers use it — high (S12)

The persona work that produced the check-in and the tiers was explicit that it was simulated
(`docs/handoffs/2026-09-19-persona-ui-redesign.md`: *"These are simulated perspectives, not
user research"*). Every framework in section 2 puts consultation first, and NN/g's single most
repeated finding is that designers guess children's age band wrong.

**What to do.** Fifteen minutes per child, on their own phone, thinking aloud, five tasks:
(1) "Show me what you have to do tonight." (2) "This one says *Teacher hasn't got it*. What
does that mean? What would you do?" (3) "Say you'll do Cell diagram tomorrow." (4) "Find the
one you handed in on paper." (5) "What does this page think of you?" Task 5 is the RITEC
question. Record where they hesitate, what they read aloud versus skip, and what they call
things. Do this before any of F2–F10; it will reorder them.

### F2. The facts a child is asked to judge render at 12–13 px in every tier — high (S1, S9)

The tier raises body type to 20 px for the 5th grader, but the elements that hold the school's
evidence are pinned in pixels and do not move:

| element | size | where |
|---|---|---|
| `.school-evidence` (the "School record · due … Canvas: … HAC: …" block on every check-in card) | 13 px | `app.css` |
| `.q .what` (assignment name line on a question card), `.q .more`, `.record` | 13 px | `app.css` |
| `.eyebrow` (course name above each card), `p.legend`, `.stamp` | 12 px | `app.css` |
| `td .rel`, `td .at` ("4 days ago", "evening") | 13 px | `app.css` |
| the status header ("Refreshed Thu 9/24 7:50 AM · Canvas OK") | 13 px | `app.css` |

Measured: the smallest rendered font on every tiered page is 12 px on desktop and 12–13 px on
the phone, identical across early, middle and older. On the early check-in (phone screenshot)
the 20 px prose "What went well? What does the school record get wrong?" sits directly above a
13 px "Canvas: no submission recorded · 0/10", which is the line the child is being asked to
argue with. NN/g's floor for this age is 16 px.

**What to do.** Express the secondary sizes relative to the tier token rather than in pixels:
`font-size: max(14px, calc(var(--type-root) * .8))` for the 13 px class and `* .75` for the
12 px class, or simply add `[data-tier="early"] .school-evidence, ... { font-size: 16px }` and
the middle equivalent. `test_web_tier_css.py` can pin that no child-page class under
`[data-tier]` computes below 14 px.

### F3. The check-in front-loads four paragraphs of adult framing — high (S2, S3)

Before the first card, the check-in shows: the tab hint, the sources hint ("Canvas is where
teachers post and collect work; HAC (Home Access Center) is the official gradebook."), "What
went well? What does the school record get wrong? Choose a few next steps together.", "Start
with what's already been handed in, then decide what fits today.", "School records can lag
behind. Check the school record on each card before relying on a 'missing' mark or a grade.",
then the section heading and "These are possibilities, not tonight's obligations. Existing
commitments are in your plan." That is 80 words and six sentences before any content, and it
is byte-identical at every tier because template copy does not go through the phrase table.

Measured: 331 words in `<main>` for the early tier with two items; 567 for the older tier with
seven; the first actionable button is 239 px down on the phone but the review queue proper
starts 4.4 screens of scrolling from the finish button. NN/g: children skip instruction
paragraphs entirely; teens leave.

Two sentences in particular are adult register on a 5th grader's page: *"These are
possibilities, not tonight's obligations. Existing commitments are in your plan."* and the
zero note *"A zero can mean not graded yet, not handed in, or handed in on paper — ask before
assuming."* (grade 9 by Flesch–Kincaid).

**What to do.** One sentence of instruction per section, tiered through the phrase table like
everything else (`checkin.intro`, `checkin.queue_hint`, `evidence.zero`). Move "school records
can lag" into the "See the record" disclosure where the record is. The early sentence for the
zero note is *"A 0 can mean the teacher hasn't graded it yet. Ask."*, which is the same claim.

### F4. Inline links in tables and cards miss the 24 px target minimum — medium-high (S4)

The coarse-pointer rule gives buttons, selects and the named check-in links 44 px. It does not
reach plain links inside `main`, and the child pages are full of them:

| page (phone, touch) | targets under 24 px tall | examples |
|---|---|---|
| Assignments, older | 23 | assignment links 22 px stacked on course links 18 px with no gap; sortable headers 22 px; "See the record" summary 19 px; "Add a note · Plan a step" 18 px; "Not right?" |
| Today | 22 | "Open plan · Assignments" 20 px; the record line's five links at 13 px |
| Open work | 12 | the same row anatomy |
| Assignments, early | 4 | course links 18 px under the assignment link |

WCAG 2.5.8's spacing exception needs a 24 px circle around each target that touches no other
target's circle. A 22 px assignment link with an 18 px course link directly beneath it fails
that; so does "Add a note · Plan a step". NN/g would have these *larger* than adult, not
smaller.

**What to do.** Under `(pointer: coarse)`, give `table.items td.item > a` and the card's
`.more a` a `padding-block` that brings the box to 44 px, or drop the course link out of the
row (the Class filter and the detail card already reach the course page) so the assignment
link owns the whole cell height. The detail card's "See the record" summary should take the
same `min-height: 44px` its siblings already have.

### F5. The rail puts every parent tool one tap from the child, on the child's page — medium (S7, S11)

On a tiered page the left rail still lists Today, both children, Open work, Questions,
Reports, Schedules, Changes, Trends, Runs, Settings and Diagnostics: thirteen links, two of
which are another child's pages. On the phone that becomes a horizontal strip whose visible
items are "Today · Alex · Sam · O…", and the child's own three tabs (Check-in · Plan ·
Assignments) sit below it as a second navigation. Then "Jump to our next steps" and "Browse
all work" make a third. NN/g's finding on redundant navigation is one of the few that held
across all three of their studies; the Children's Code asks that a child not be able to wander
into an adult surface without noticing.

The spec (§6) already says the parent tools are not tiered "because no child opens them". The
rail is how a child opens them.

**What to do.** On a page that carries `data-tier`, collapse the rail to Today and this child's
tabs, with one "App" link that opens the parent groups. That hides navigation, not rows or
actions, so it does not breach the parity rule. Rename the rail group "Kids" (NN/g's teen
repellent word) to nothing: the names are the label.

### F6. The step form asks a 10-year-old nine questions to write down one step — medium (S3, S10)

"Plan a step" from any card lands on a form with Assignment or task, Family account, Agreed
next step, Who will do this, State, Planned date, Estimated minutes, **Order within this day
(lower goes first)** (required, numeric), and Recorded by. Three are the caregiver-handoff model
(state, position, recorded-by) and two are estimation. The one-tap Today/Tomorrow answers were
the right response to this (spec 2026-09-23 §6) but every card still carries the "Plan a step"
button-link into the long form, and on the plan page "Add a task" has no short path at all.

RITEC's autonomy dimension is about *feeling* in charge; a form whose field labels are
"State" and "Order within this day" belongs to the adult who runs the plan, not the child who
owns the step. The teen research is blunter: they leave.

**What to do.** Two tiers of form, the same fields for every reader: title, next step and day
above the fold; State, minutes, order and recorded-by under a `<details>` labelled "More
(who's helping, order, minutes)". That is progressive disclosure of *fields on one form*, not
of features, and it is the same at every tier, so it sits inside the spec's line. Default
"Order" to last and stop requiring it.

### F7. The child's page speaks to three different people — medium (S9, S10)

On one early-tier page: "Nothing to answer for Sam." (about the child, to a parent), "You
handed it in on 9/20" (to the child), "Recorded by · Mom, Dad, Grandma…" (to the parent),
"What we agreed" (to both), "Correct the school record" and "Your answer" (to whoever is
holding the phone). The check-in is dyadic by design, and "we" is right there. Assignments is
the child's page and should say "you" to the child; the caregiver fields should say who they
are for.

This matters more than it looks: NN/g's children reject content pitched at a different age
with the word "babies", and a 9th grader reading "Mom, Dad, Grandma…" as the placeholder in
*their* plan hears the same thing.

**What to do.** Decide one addressee per surface and put it in the phrase table's comments:
Assignments = the child ("you"); Check-in and Plan = "we"; the Recorded-by and Family-account
fields keep their labels but get a one-word eyebrow "For a grown-up helping". No change to what
is shown.

### F8. The pages show only what is wrong — medium (S10: competence)

The kid page lists problems, then "Settled by the records", then the table. The dashboard's
record line ("N on time · N late · N not done · N on paper") exists, and it is inside a
collapsed `<details>` on the parent's Today page. Nothing on any child surface states what
the child has done. The only positive sentence in the product, "Nothing open. Nice work.", is
reachable by a child with nothing open.

RITEC's competence dimension is "children's perceptions of their effectiveness"; the SRL
studies find progress visibility supports homework persistence. This is not a request for
gamification (NN/g and RITEC both warn against extrinsic reward loops) but for the true
sentence the data already supports: *"Handed in on time: 14 of 16 due so far."*

**What to do.** One line at the top of Assignments, from the existing `record` outcome
counts, phrased through the tier table, no colour, no badge. It is facts-only and passes the
no-fabrication test as written.

### F9. The primary button on a "waiting" card nudges the child to email the teacher — medium (S11)

`_answers.html` makes the first answer `primary`. For `teacher_grading` and `awaiting_grade`
the only answer is **Ask the teacher**, so the check-in renders a filled blue "Ask the teacher"
under "Essay draft · handed in 9/23, waiting for the teacher to grade it" and under a sentence
saying the app allows seven days. The visual hierarchy tells a 9th grader to chase a teacher
one day after submitting. The Children's Code's nudge standard is exactly about a design's
default steering a child toward an action that is not in their interest; the wording is
careful, the button weight is not.

**What to do.** In `_answers.html`, give `primary` only when the verdict state is `question`
or the first answer is a plan action; waiting cards get plain buttons. One template line.

### F10. The same due time renders two ways on one page — low-medium (S9)

The early tier's row says "9/20 evening · 4 days ago" (the `due_part` choice in
`_item_row.html`), while the check-in card for the same item says "due Sun 9/20 11:59pm"
(`_planning_evidence.html` uses `due_time` for every tier). Consistency is an NN/g criterion
in its own right, and the spec's own wording table promised "due tomorrow morning" at the
early tier.

**What to do.** `_planning_evidence.html` and `_question.html`'s `.what` line should make the
same `due_part` / `due_time` choice as the row; better, move that choice into one filter
(`due_words(view, tier)`) so the three templates cannot drift.

### F11. The printed sheet is the least age-appropriate surface and the one on the fridge — medium (S1, S2, S5)

`sheet.py` sets body cells at 8.5 pt, "asg" and "thru" lines at 7 pt, the legend at 7.5 pt,
and status words in coloured capitals: `HAC — NO GRADE`, `PAPER — CHECK`, with a "Via" column
reading `Hac · —`. The tiers do not apply to the sheet at all. A 5th grader reading the fridge
gets the adult vocabulary at half the size of the older tier's screen.

Two colour problems on top: per-kid heading colours cycle through the same hues the status
words use (Alex's heading blue is DUE TODAY blue; Sam's purple is PAPER — CHECK purple), so one
colour means two things on one page; and all-caps status text is measurably slower to read for
developing readers. Neither breaks "not colour alone", both cost the reader.

**What to do.** Per-kid sections already know the kid; pass the tier and use the phrase table
for the status word ("Teacher hasn't got it" fits the column at 9 pt). Raise cells to 9.5–10 pt
and the sub-lines to 8 pt; the sheet is one page for two children with room to spare. Spell
"asg" and "thru" out ("given", "credit until") and give kid headings a neutral ink colour so
colour is reserved for status. Keep the no-fill, ink-light constraint: this is text size and
words, not decoration.

### F12. Smaller items, one line each — low

- The filter option text "done, excused, let go, or too late to submit" and "asked the teacher or following up" is a sentence inside a `<select>`; the early tier should not see six selects at all under **More filters**, but if it does the options should be two words each.
- The sort arrows are 11–13 px glyphs; fine for a mouse, invisible on the 5th grader's phone. A bolder header on the active column would do.
- "See the record" and "Waiting, nothing to do yet (2)" are `<summary>` elements at 19–23 px on the phone; the coarse-pointer rule already covers other summaries and should cover these.
- "Fridge Sheet has no earlier grades from this class to go on, so it allows 7 days." appears on every card of a fresh install (three times on the fixture's older check-in). It is honest and it is 17 words of app reasoning per card; it belongs inside "See the record".
- The plan-print page's on-screen note *"Family accounts stay on screen; school inventory and other children are left out."* is for the printer, not the child; it can be a `title` on the print button or drop.

## 6. Recommendations in order

| order | finding | effort | who benefits |
|---|---|---|---|
| 1 | F1 watch the three children, five tasks each | an evening | everything below |
| 2 | F2 secondary text follows the tier (14 px floor) | CSS + one test | all three, most for 5th |
| 3 | F9 no primary on waiting cards | one line | 7th, 9th |
| 4 | F4 inline links reach 24 px (44 px under touch) | CSS | all three on phones |
| 5 | F3 one instruction sentence per section, tiered | phrase table + templates | 5th, 7th |
| 6 | F10 one due-words filter | small refactor | 5th |
| 7 | F8 one true sentence of competence on Assignments | template + phrase | all three |
| 8 | F5 rail collapses on tiered pages | template + CSS | all three; Children's Code |
| 9 | F6 step form in two stages | template | all three |
| 10 | F7 one addressee per surface | copy pass | all three |
| 11 | F11 the sheet takes the tier | `sheet.py` | 5th, on the fridge |
| 12 | F12 | as met | |

Items 2, 3, 4, 9 and 10 can each be a PR of their own with a test in the existing
`test_web_tier_*` family. Item 11 is the only one that touches the outcome contract's
neighbourhood (`docs/outcomes.md` "The printed sheet" row) and should carry its own spec.

## 7. Decisions this leaves with the maintainer

1. **Does the parity rule extend to navigation and form layout?** F5 and F6 read the spec as
   forbidding hidden *rows and actions* and permitting collapsed *navigation* and *secondary
   form fields* that are identical at every tier. If the rule is stricter than that, F5 and F6
   need another shape.
2. **Should the printed sheet be tiered at all?** It is the one surface that is per-household
   rather than per-child, and tiering it means two vocabularies on one page.
3. **Whose page is Assignments?** F7 assumes the child's. If it is the parent's triage table
   that a child also reads (which is how `all-work-table-ux.md` describes it), the addressee
   should be the parent and the child-facing surface is the check-in alone.

## Sources

- Nielsen Norman Group, *UX Design for Children (Ages 3–12)*, 4th ed. — https://www.nngroup.com/reports/children-on-the-web/
- Nielsen Norman Group, *Children's UX: Usability Issues in Designing for Young People* — https://www.nngroup.com/articles/childrens-websites-usability-issues/
- Nielsen Norman Group, *Designing for Kids: Cognitive Considerations* — https://www.nngroup.com/articles/kids-cognition/
- Nielsen Norman Group, *Design for Kids Based on Their Stage of Physical Development* — https://www.nngroup.com/articles/children-ux-physical-development/
- Nielsen Norman Group, *UX Design for Teenagers (Ages 13–17)* — https://www.nngroup.com/reports/teenagers-on-the-web/
- Nielsen Norman Group, *Teenager's UX: Designing for Teens* — https://www.nngroup.com/articles/usability-of-websites-for-teenagers/
- Smart Interface Design Patterns, *A Practical Guide To Design For Children* (citing Gelman, *Design for Kids*) — https://smart-interface-design-patterns.com/articles/design-guidelines-children/
- W3C, WCAG 2.2 (SC 2.5.8 Target Size (Minimum), 1.4.3, 1.4.11, 1.4.1, 3.3.7) — https://www.w3.org/TR/WCAG22/
- ICO, *Age appropriate design: a code of practice for online services* (the Children's Code) — https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/childrens-information/childrens-code-guidance-and-resources/age-appropriate-design-a-code-of-practice-for-online-services/
- Designing for Children's Rights Association, *The D4CR Design Guide* (10 principles) — https://childrensdesignguide.org/
- 5Rights Foundation, *Child Rights by Design* (11 principles) — https://childrightsbydesign.5rightsfoundation.com/
- UNICEF, *Responsible Innovation in Technology for Children*: the RITEC-8 framework and Design Toolbox (2024) — https://www.unicef.org/childrightsandbusiness/workstreams/responsible-technology/online-gaming/ritec-design-toolbox
- Joan Ganz Cooney Center, *Introducing the RITEC Design Toolbox* — https://joanganzcooneycenter.org/2024/11/13/ritec-design-toolbox-launch/
- *Students' self-regulation of homework behavior: do autonomy support and effort matter?*, Social Psychology of Education (2025) — https://link.springer.com/article/10.1007/s11218-025-10127-4
- *Teacher involvement and self-regulation in homework*, Metacognition and Learning (2025) — https://link.springer.com/article/10.1007/s11409-025-09431-3
- *Influence of parental structure and chaos on homework anxiety in elementary school students* (2024) — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11491404/

## 8. Status, end of 2026-09-24

The maintainer took the three decisions in section 7 as recommended: parity covers rows and
actions, not navigation or field layout; the sheet is tiered by vocabulary only; Assignments
is the child's page. Every finding except F1 then landed as its own PR, each with a failing
test first and a Playwright render at 390 px.

| finding | PR | what changed |
|---|---|---|
| F9 | #106 | waiting cards have no filled default |
| F2 | #107 | `--type-small` / `--type-tiny` tokens; secondary text follows the tier |
| F4 | #108 | row links, headers and disclosures reach 44 px under touch |
| F3 | #109 | one instruction sentence per section, through the phrase table |
| F10 | #110 | one `due_at` filter for every surface |
| F8 | #111 | "Done so far: 2 of 5 due · 1 on time." above the questions |
| F6 | #112 | step form asks three things first; the rest folds under More; Order optional |
| F5 | #113 | a tiered page's rail is Today, this child, and an App fold; "Kids" label gone |
| F7 | #114 | Assignments says "you"; Recorded-by says "a grown-up helping" |
| F11 | #115 | the sheet takes each kid's tier for status words, 10 pt, ink headings, "given" / "until" |
| F12 | #116 | short filter options, bold sorted column, pace sentence folded, printer note off the page |
| F1 | — | **still open, and the maintainer's to run**: five tasks per child, section 5 |

Re-measured with `scripts/kids_ui_measure.py` on the same fixture, phone (390×844, touch):

| page | targets under 24 px, before → after | smallest text inside `main`, early tier |
|---|---|---|
| Assignments, older | 23 → 2 (the two radios; their labels are 44 px) | 12 px → 14 px |
| Assignments, early | 4 → 2 | 12 px → 14 px |
| Open work | 12 → 0 | |
| Today | 22 → 3 (the two kid-name headings and a checkbox) | |
| Check-in, early | 0 → 0 | 13 px → 14 px |

Words before the first check-in card: 80 → 27 (early) and 29 (older). The step form shows
five fields and a More line where it showed nine fields. The printed sheet's smallest text
went from 7 pt to 8 pt and its body from 8.5 pt to 10 pt; two kids still fit one page.

What did not change, on purpose: the parity test still holds every row and every action at
every tier; a household with no grade set renders byte-for-byte what it rendered before,
apart from the tap-target padding under touch and the rail's dropped "Kids" label, which
apply to everyone.

# One section, one card: the standard for what a page is made of

Date: 2026-09-28. Status: design approved in discussion from rendered mockups; awaiting
review of this document. Asked for by the maintainer: *"there MUST be a better UI / layout /
organization for presenting the information in different sections of this page. it's a
problem throughout the app. the whole thing just feels disorganized / noisy still"*, and then:
*"look specifically at how the information is organized within the different assignment
cards/containers."*

The sequel to the page layout standard (`2026-09-26-page-layout-standard-design.md`). That
standard made the chrome identical on every page and stopped at "content: sections (h3) of
cards, tables, forms, charts". This one is the content column: what a section is, what a card
is, and where inside a card each fact goes. Mockups, throwaway HTML over the real stylesheet
with desktop and phone renderings, are in `2026-09-28-sections-and-items-mockups/`.

## 1. What was wrong

Measured on Doug's Assignments tab (screenshot of 2026-09-28) and traced to the templates.

- **Seven box styles on one page.** The question card (`.q`, 10 px radius), the settled lines
  (`.lines`, 10 px), the item detail (`.card`, 8 px), the record (`.record`, 8 px, wash), the
  Must-finish row (`.mf-row`, 8 px with a left rule), the plan panel (`.plan-panel`, 12 px,
  green) and the done-line (`.done-line`, 10 px, green). The eye cannot chunk a page whose
  containers all differ.
- **Four heading treatments.** `main h3` at 18 px; `.quiet-head` at 14 px muted; a bare
  `<details>` summary at body size; `.workspace-heading`. No rhythm to scan by.
- **One assignment drawn three times, nested.** A question is a card at the top, a table row,
  and, when the row opens, a `.card` with its own `<h2>` inside a wash-coloured row with the
  whole question card inside that. Three borders, two titles, two copies of the answers.
- **Four lines of prose before the first thing to do.** The tab hint, the sources hint, Done so
  far, then the section's hint.
- **A second colour system on Check-in and Plan.** Six hard-coded greens (`#286454`,
  `#214f43`, `#edf5f1`, `#45655e`, `#eef3ef`, `#aa7c32`) for the tabs, the plan panel and the
  rules, so the app has two accents depending on the tab.

Inside the cards:

- **Six containers draw an assignment, in six orders.** The class is an eyebrow above the
  title on three of them, after the title on one, a small line under it in the table. The due
  date is at the head's right on the question card, in the eyebrow line on Must finish, inside
  the evidence block on the review card, and absent from the plan step.
- **The same fact is said two or three times.** The question card's head says "Concert Band ·
  in class" and "due Sun 9/20"; its facts sentence opens "In class work, due Sun 9/20." Every
  record fold begins with the Canvas-and-HAC glossary sentence that is also under the tabs. The
  review card shows the source lines, then a note restating them in prose.
- **Five layers interleave with no hierarchy.** Identity, the school's record, the app's
  reading of it, the family's own layer and actions. The review card runs school, app, app,
  family, family, action, school, family, action.
- **One action, three names and three styles.** Plan a step is a text link on the question
  card, a button-link on the review card, "Add details" on Must finish, "Add a task" on the
  plan. The folds that show the school record are "See the record", "Details" and "School
  evidence", with overlapping contents. Provenance ("Recorded Sun 9/27 6:12 PM by Mom",
  "checked Mon 9/28 7:43 AM · changed Thu 9/24 4:14 PM") sits in the body at body size.

The root cause is that every spec since 9/26 invented its own section and its own card
because nothing said what they were.

## 2. Decisions taken in discussion

| Question | Decision |
|---|---|
| A component standard, one grouped list, or a polish pass? | **The standard.** One grouped list would reverse the 9/23 decision that questions are cards above the list, which the tier work builds on. Polish alone leaves Check-in looking like a different app |
| What organises a card? | **The check-in's three-layer rule** (school record, family account, agreed step, never written by one another), applied to what a card *shows* where. Each slot has an owner; a fact in two slots is a bug |
| The two hint sentences under the tabs | **Retired.** The line under the tabs is state, not instruction: Done so far on Assignments; the last check-in and what was agreed on Check-in and Plan. The section heads now do the hint's job. This supersedes kids' UX audit F3's tab hint |
| Kind and due date in the facts sentence | **Dropped**, in all three tiers together (the parity rule). The head is the one place for them |
| The glossary sentence (what Canvas and HAC are) | **Said once per page**, as the legend under the Assignments table and at the foot of the check-in's queue, never inside a record. The user guide keeps it |
| "Add details" on a Must-finish row | **Becomes "Plan a step"**, the same words as everywhere else. The done-line's "Add details" (editing the step a one-tap answer created) keeps its words: it edits, it does not plan |
| The left rule's colours | Accent means *needs an answer*; red means *the school says not in*; green means *done*; grey means *nothing to do*. Nothing conveyed by colour alone: each has a word beside it |
| Multi-column grids of cards | **Gone for items.** An item is full width in its column. `.cards` (Today's kid cards, Settings' topics) keeps its grid: those are topics, not items |

## 3. The section

The content column is a stack of sections, 32 px apart. Nothing inside a section adds to that
gap.

```
┌ .sec ──────────────────────────────────────────────────────────────┐
│ h3 Title  count            [the section's own controls, at right] │  .sec-head
│ One lead sentence, muted, bounded to the measure.                   │  .lead (optional)
├────────────────────────────────────────────────────────────────────┤
│ body: items, lines, a table in .table-wrap, a form, a chart         │
│   h4 sub-heads where the body is grouped (Due tonight, Planned)     │
└────────────────────────────────────────────────────────────────────┘
```

- **Head.** `<div class="sec-head">`: the `<h3>` (18 px, 650), an optional `.count` (small,
  muted, the number the heading is about), an optional `.lead` (one sentence, muted, wrapping
  under the head and bounded to the measure), and optional `.controls` at the right (the
  section's own buttons, links or filters: "Check Canvas again", "Add a task", the table's
  filter chips and class select).
- **Folded.** `<details class="sec">` whose `<summary>` holds the same `<h3>` and `.count`,
  drawn identically with a marker. Settled, Waiting, Coming due later, Completed steps,
  Previous agreements, Can't pair these.
- **Quiet.** `.sec.quiet`: the same head in muted ink, weight 600, the same size. There is no
  smaller heading. Replaces `.quiet-head` (14 px).
- **Sub-heads.** `<h4>` at 15 px inside a body that is grouped: Must finish's six groups, the
  plan's states, a kid's two lists on Questions.
- **Filters** belong to the section whose body they narrow, in its `.controls`. The
  Assignments table's Open / Everything chips, class select and More filters fold move from a
  free-standing form above the table into the "All assignments" head. The form keeps its
  `hx-get` and `#items` target.
- **The line under the tabs** (`.tab-hint`) is one line of state in body type: on Assignments,
  `copy.done_so_far` ("Done so far: 137 of 157 due · 74 on time.", omitted before anything is
  done); on Check-in and Plan, the last check-in, the next one, and what was agreed, which
  `.checkin-intro` shows today. `copy.tab_checkin`, `copy.tab_plan` and `copy.tab_all` are
  retired.

## 4. The card: one item, five slots

Every container that draws one assignment (or one family step about one) fills these slots in
this order and omits a slot that is empty. Each slot belongs to one layer.

```
┌ .item ─────────────────────────────────────────────────────────────┐
│ 1 HEAD   Name   class · kind · pts        [the one word about time] │  identity, once
│ 2 SAYS   One sentence: what the record means right now.             │  the app's reading
│ 3 ASK    The question?                                              │  the family's move
│          [primary] [second] [third]                                 │
│ 4 OURS   Our step · owner · when   |  Note, 9/22: …                 │  the family's layer
│ 5 FOOT   Record ▸ · History (3) ▸ · Notes (1) ▸ · Plan a step · More ▸   stamp │  quiet
└────────────────────────────────────────────────────────────────────┘
```

### 4.1 The slots

1. **Head** (`.item-head`). The name (`.name`, 650; a link when the card is not on the item's
   own page; the focus target), then `.meta` (small, muted): the class, the kind when it is
   paper or in class, the points when known. At the right, `.when`: **the one word about
   time**, which is the item's `standing` phrase, the same words the table's "Where it stands"
   column shows, so a card and its row agree by construction. Muted when it is a date ("due Sun
   9/20 11:59pm", "planned for today"); `.word` in `--warn` at body weight 700 when it is the
   sheet's word for school-recorded not-done (DUE TONIGHT, DUE TOMORROW, MISSING, ZERO); muted
   otherwise ("Waiting for a grade", "Following up since 9/23"). A detail adds `Close` after it.
2. **Says** (`.facts`). One sentence, the verdict's `facts.*` phrase, with kind and due date
   removed from the phrases that carried them (`facts.still_ungraded`, `facts.awaiting_grade`).
   On a Must-finish row with no question: the school's fact ("Nothing handed in yet.", "Canvas
   marked it missing on Thu 9/24.") and the late-credit sentence. On a family step: the step's
   `next_step` text. On a step the school has: the witness line. The pace sentence
   ("Fridge Sheet allows 7 days…") is never here; it is in the Record.
3. **Ask** (`.ask-line`, then `.answers`). The `ask.*` phrase when the verdict is a question,
   then `_answers.html` unchanged: one-tap POSTs, the first filled unless the card is waiting,
   `exclude` and `first` as today. A Must-finish row has answers with no ask line. A step the
   school has draws "Mark step complete" here.
4. **Ours** (`.ours`, small, with the family's rule at the left). The family's layer, one line
   each, only when present, in this order: the active step ("Our step: Finish before dinner ·
   Doug · today", with Edit); the note the family attached to its answer (`flag_text`); the
   latest note ("Note, Tue 9/22: …"). The answer itself is not repeated here: the head's word
   already says "Asked the teacher on 9/23" or "Marked done on 9/12". On a family step this
   slot is the step's own line: owner · minutes, and "not counted tonight" on a greyed step.
5. **Foot** (`.item-foot`, small, one wrapping line). The folds, always by these names and in
   this order, then the links, then the stamp at the far right in `--type-tiny`:
   - **Record ▸**: what each source holds, one block per source: the label, the facts, and on
     the next line the stamp ("checked Mon 9/28 7:43 AM · changed Thu 9/24 4:14 PM"); then the
     pace sentence when there is one; then the teacher's name with "Email with these facts"
     and "Open in Canvas". Replaces "See the record", "Details" and "School evidence" (the
     `_planning_evidence.html` block), which held the same facts in three arrangements.
   - **History (n) ▸**: the item's observation history, as the detail shows it today.
   - **Notes (n) ▸**: `_notes.html`, the list and the Add a note form. Replaces the "Add a
     note" link that fetched the whole detail into the card.
   - **Plan a step** (or **Plan another step** when one is active; **Edit or complete step**
     on a step's own card; **Edit** on a greyed step): a link, the same words everywhere.
   - **More ▸**: the flag menu (`_flag_menu.html`), for answers the questions do not offer.
   - **stamp** (`.stamp`): provenance. On a Must-finish row, "On Sunday's list" or "New since
     Sunday's check-in". On a step, "Agreed at the Sun 9/27 check-in · recorded by Mom" (or
     Edited since, Added since). Never in the body.

### 4.2 Three densities, one partial

`_item.html` renders every assignment surface, with `density` set by the includer:

| density | draws | used by |
|---|---|---|
| `line` | head only, in `.lines`: a glyph (✓ done, ◷ waiting), the name, the facts sentence muted, one action at the right (Not right?, Ask now, Email, Undo) | Settled, Waiting, Waiting on the teacher, the done-line after an answer |
| `card` | slots 1–5, the foot folded | the question sections (Assignments, Questions, Worth checking), Must finish, Our next steps, Other open work, Waiting on the school |
| `detail` | the same card with **Close** in the head and the Record open in place, above the foot | a table row's expansion (`/items/{id}`), and a card opened in place (`?card=`) |

The detail is what a row opens to *and* what a card becomes when opened: one surface, so
nothing is drawn twice and the row's wash-coloured cell holds one box, not a box in a box.
`_item_detail.html`'s `<h2>` goes; the name is the focus target as it is on the card. The
`?card=q-<id>` / `/items/{id}/question?slot=` round trip and the `qd-` slot prefix are
unchanged (the detail's answers still target their own slot).

Emphasis is the left rule and a word: `.item.ask` (accent: a question), `.item.red` (`--warn`:
the school records not done), `.item.ok` (`--ok`: done, or a step the school has),
`.item.grey` (muted ink: nothing to decide). The badge on a table row is one neutral style
(`.badge`): the word carries the meaning; `.qmark` and `.badge.plan` lose their colours.

### 4.3 What each container becomes

| today | becomes |
|---|---|
| `_question.html` (`.q.card`) | `_item.html` at `card` density |
| `_item_detail.html` (`.card` + h2 + embedded question) | `_item.html` at `detail` density |
| `_verdict_sections.html`'s `decided_line` and waiting lines | `_item.html` at `line` density inside `.lines` |
| `_answered.html` (`.done-line`) | `line` density with `.ok`, Undo at the right |
| `_must_finish.html`'s `.mf-row` | `card` density with `.red` / `.grey`, the sheet's word at the head's right, the stamp in the foot |
| `_plan_panel.html`'s `.plan-card` | `card` density: head = title, class, the Must-finish badge; says = the step; ours = owner · minutes; foot = Record, Edit or complete step, the agreed/edited stamp |
| the plan's `school-has-it` card | `card` density with `.ok.grey`: says = the witness line; answers = Mark step complete; ours adds "not counted tonight" |
| `checkin.html`'s `.review-card` in `.review-grid` | `card` density, full width, in the section's body |
| `_planning_evidence.html` | folded into the Record (source facts, pace); its "Your answer" and "Latest note" lines are slot 4; its zero note is slot 2 |
| `_record.html` (with the glossary sentence) | the Record fold's body, without the glossary |
| `questions.html`'s "Waiting on the teacher" `.lines` | `line` density |

## 5. Containers that are not items

- **`.card`** stays for a *topic*: Today's kid cards, "Today's sheet", Settings' topics, the
  report builder, "Agree and wrap up". Same radius, border and padding tokens as `.item`, no
  left rule. Its title is `<h3>` at 16 px as the layout standard says.
- **`.inset`** is the one style for anything quoted inside an item or a card: the Record's
  body, the family's account on a step, a witness line, the class's pace sentence above a
  paper group, the "school evidence changed" notice (`.inset.warn`). Replaces `.record`,
  `.family-account`, `.mf-paper`, `.witness`, `.review-note`, `.school-evidence`.
- **`.lines`** is the line density's container: the same box as `.item`, rows separated by
  rules, one action per row at the right.
- **Tables** are unchanged: `table.items` in `.table-wrap`, three columns on a work list.

## 6. Tokens and colour

`:root` gains `--radius: 8px` and the gap scale by name: `--s1: 4px`, `--s2: 8px`, `--s3:
12px`, `--s4: 16px`, `--s5: 24px`, `--s6: 32px`. Every radius in the stylesheet is
`var(--radius)` (the rail links and buttons keep 6 px; chips keep their pill). Every margin and
gap is a named step.

The check-in's green palette is retired. The current tab is `--accent`; `.button-link` is the
neutral button (paper, `--control` border, ink); `.notice` is wash with an accent rule; the
plan panel has no background. The tier palettes are untouched: a tier still redefines
`--accent`, `--warn` and `--ok`, and the item rules follow them.

## 7. Type

Unchanged from the layout standard's table. The section head is `h3` 18 px; the item name is
body size at 650; `.meta`, `.facts` on a line, the foot and `.ours` are `--type-small`; the
stamp and the Record's checked-and-changed lines are `--type-tiny`. The tier tokens move all
three with the body size, as today.

## 8. Phrasing

- Removed: `copy.tab_checkin`, `copy.tab_plan`, `copy.tab_all`, `copy.details`, and any key
  whose only use was a retired fold name.
- Changed, all three tiers together: `facts.still_ungraded` and `facts.awaiting_grade` lose
  "{kind} work, due {due}." (older: "Still no grade anywhere, longer than grading usually
  takes." / "No grade yet; grading paper takes time."). `a.add_details` on a Must-finish row's
  foot is replaced by the existing plan-a-step words; the done-line keeps `a.add_details`.
- Added: `copy.record` ("Record", three tiers), `copy.history`, `copy.notes` (with `{n}`),
  `copy.ours_step` ("Our step"), `copy.note_on` ("Note, {when}"), `copy.not_counted_tonight`.
- `copy.sources_hint` stays, drawn once per page: as `p.legend` under the Assignments table
  and at the foot of the check-in's queue, as today. It leaves `_record.html`.

The parity rule holds: no tier gains or loses a row, an action or a fact.

## 9. Mechanism

- **`static/app.css`**: the tokens (§6); `.sec`, `.sec-head`, `.lead`, `.count`, `.controls`,
  `details.sec > summary`, `.sec.quiet`; `.item` and its parts, the four rules; `.lines`;
  `.inset`; the neutral `.badge`; `tr.detail td` holding one `.item`; the retired rules removed
  (`.q*`, `.record`, `.mf-row*`, `.plan-panel`, `.plan-card`, `.review-card`, `.review-grid`,
  `.done-line`, `.section-head`, `.quiet-head`, `.workspace-heading`, `.school-evidence`,
  `.review-note`, `.family-account`, `.mf-paper`, `.witness`, `.qmark`'s colours, the greens).
  The coarse-pointer block names the new selectors (`.item-foot summary`, `.item-foot a`,
  `.lines .line > *`, `details.sec > summary`) at 44 px.
- **`templates/_item.html`** (new): the five slots, three densities, `slot` / `qid` as
  `_question.html` has them, `exclude` / `first` passed through to `_answers.html`.
  `_question.html`, `_item_detail.html`, `_planning_evidence.html`, `_record.html` and
  `_answered.html` become thin includes of it or go. `_source_facts.html` gains the
  stamp-on-its-own-line layout.
- **`templates/_section.html`** is not a partial: a section is three lines of markup and Jinja
  includes cannot take a body. The head markup is the convention; `tests/test_web_page_layout.py`
  holds it.
- **Templates changed**: `kid.html` (filters into the table's section head; the state line),
  `_verdict_sections.html`, `_item_rows.html` (the detail row holds one `.item`),
  `_item_row.html` (badges), `_child_nav.html` (the state line; no sources hint), `checkin.html`
  (sections; the queue as a single column of cards; `.checkin-intro` becomes the state line),
  `_must_finish.html`, `_plan_panel.html`, `questions.html`, `open.html` and `course.html`
  (section heads), `dashboard.html` (section head for the cards; the kid card's outcome line, today
  `p.record`, is renamed `.outcome-line` and keeps its rule, so `.record` has no second meaning), `plan_print.html` (its screen view uses the same
  classes; paper is unchanged).
- **Routes**: none change their contracts. `/items/{id}` renders the detail density;
  `/items/{id}/question?slot=` the card density.
- **`static/app.js`**: the detail row open/close targets `.item` instead of `.card`.
- **Docs**: `docs/product/features/section-and-card-standard.md` (one-pager, `parent:
  browser-app`, `related: page-layout-standard`); `docs/product/features/page-layout-standard.md`
  links to it; `docs/user-guide.md` keeps the glossary sentence and describes the card's slots
  in one paragraph; `docs/product/2026-09-24-kids-ux-audit.md` F3 gains a note that the tab
  hint is superseded.

## 10. Tests

`tests/test_web_section_and_card.py` (new), holding this standard as `test_web_page_layout.py`
holds the last one:

- the tokens exist and the stylesheet has no radius or gap that is not a token (a regex over
  `app.css` for `border-radius:` and `gap:` values that are literal pixels other than the
  documented exceptions);
- no template uses a retired class (the list in §9);
- every `<section` in a page template opens with `.sec-head` (or is a `details.sec` whose
  summary holds an `h3`); every `h3` inside `<main>` is a section head, a card title or a kid
  head;
- `_item.html` at each density, over the seeded household: a question renders slots 1, 2, 3, 5
  and no `.ours`; an item with a step renders `.ours` with the step and "Plan another step";
  a Must-finish row renders the sheet's word in `.when.word` and no ask line; a waiting card
  has no filled button; the detail renders the Record open, Close, and the name exactly once;
  the facts sentence never contains the due date or the kind;
- the head's `.when` text equals the same item's "Where it stands" cell;
- the glossary sentence appears at most once in any page's HTML;
- the foot's folds appear in the order Record, History, Notes, More.

Updated: `test_web_page_layout.py` (the tab-hint-before-sources-hint ordering becomes
state-line-before-first-section; the only-one-h2 rule now trivially holds),
`test_web_kid_questions.py` and `test_web_tone_layout.py` (class names; the three sections),
`test_kids_ux_small_items.py` (the fold order inside a card), `test_web_kid_table.py` (the
detail row's one `.item`), `test_web_checkin.py` and `test_web_checkin_verdicts.py` (class names;
"Plan a step" on a Must-finish row), `test_web_questions_page.py`, `test_phrasing.py` (the
removed and added keys), `test_web_tier_parity.py` (should pass unchanged; it compares rows and
actions across tiers). `scripts/layout_audit_measure.py` is rerun by hand at the end for the
first-content and target-size numbers; `scripts/kids_ui_measure.py` likewise.

## 11. Order of work

1. Tokens, `.sec`, `.item`, `.lines`, `.inset` in the stylesheet, beside the old rules.
2. `_item.html` and the Assignments tab (the page in the screenshot), with its tests.
3. Questions, then the done-line and the item detail everywhere.
4. Check-in and Plan (Must finish, the plan panel, the queue), then Today, Open work, the
   class page, the print pages' screen view.
5. Retire the old rules and classes; the no-retired-class test goes green last.
6. Docs, the browser measurements, the one-pager.

Each step ships on its own PR against the feature branch's standard, so the app is never half
in one system; the retired-class test is added at step 5.

## 12. Not in this design

- Which rows a page shows, and which answers a verdict offers (`docs/outcomes.md`, the
  verdict table, the parity rule). This moves markup, never rows or actions.
- The printed PDF sheet and the paper side of the two print pages.
- The status bar's wording (three timestamps on a wide screen; a candidate for its own small
  change).
- Charts, the report builder's form, Settings' forms and the Schedules controls: they take the
  tokens and the section head and nothing else.
- A design token file or a CSS preprocessor; one stylesheet, as today.

## 13. Risks

- **The tab hint's job.** Kids' UX audit F3 put one sentence of orientation under the tabs
  for the younger tiers. The section heads and their leads now carry it ("2 questions about
  your work · Answering one takes it off this list"). If the household's reading disagrees,
  the state line's slot can carry a hint again without touching the sections.
- **Every page moves at once.** The retired-class test forces the old system out; until step
  5 the two coexist, and a page in the old system still looks as it does today.
- **Phrase changes ripple into tests that assert wording.** `facts.still_ungraded` appears in
  tone and small-items tests; each is updated with its step, not in bulk.

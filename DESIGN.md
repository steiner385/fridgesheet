---
name: Fridge Sheet
description: A family's open schoolwork, decided once and set like a ledger, on screen and on the fridge.
colors:
  ballpoint-blue: "#1f5fa8"
  red-pen: "#b3261e"
  checkmark-green: "#2e7d32"
  amber-pencil: "#b8860b"
  amber-pencil-ink: "#9a5b00"
  purple-stamp: "#6b3fa0"
  ink: "#1c1c1c"
  pencil-grey: "#595959"
  stroke-grey: "#8a8a8a"
  ruled-grey: "#d9d9d9"
  paper-white: "#ffffff"
  ledger-paper: "#f4f4f2"
  red-pen-wash: "#fdecea"
  ink-early: "#10151b"
  pencil-grey-early: "#4a5568"
  ruled-grey-early: "#b9c6d4"
  ledger-paper-early: "#eef4fb"
  ballpoint-blue-early: "#0b5cab"
  red-pen-early: "#a3170f"
  checkmark-green-early: "#1d6b27"
  amber-pencil-ink-early: "#8a5200"
  purple-stamp-early: "#5f3594"
  ink-middle: "#161b22"
  pencil-grey-middle: "#5a6474"
  ruled-grey-middle: "#ccd5de"
  ledger-paper-middle: "#f1f5f9"
  ballpoint-blue-middle: "#14539b"
  red-pen-middle: "#a81d14"
  checkmark-green-middle: "#24702c"
  amber-pencil-ink-middle: "#915600"
  purple-stamp-middle: "#653a9a"
typography:
  display:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.2
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.3px"
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "18px"
    fontWeight: 650
    lineHeight: 1.3
  subtitle:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.35
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.4
  caption:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  print-heading:
    fontFamily: "Helvetica-Bold"
    fontSize: "16pt"
    fontWeight: 700
    lineHeight: 1.19
  print-cell:
    fontFamily: "Helvetica"
    fontSize: "10pt"
    fontWeight: 400
    lineHeight: 1.2
  print-small:
    fontFamily: "Helvetica"
    fontSize: "8.5pt"
    fontWeight: 400
    lineHeight: 1.24
rounded:
  swatch: "2px"
  stale: "4px"
  control: "6px"
  card: "8px"
  pill: "10px"
  chooser: "12px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  gutter: "24px"
  gutter-narrow: "16px"
components:
  button-secondary:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-secondary-hover:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.ballpoint-blue}"
    textColor: "{colors.paper-white}"
    typography: "{typography.subtitle}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-danger:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.red-pen}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  button-link:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
  input-text:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "4px 6px"
  badge:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  badge-current:
    backgroundColor: "{colors.ballpoint-blue}"
    textColor: "{colors.paper-white}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "1px 8px"
  card:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "12px 16px"
  item:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "12px 16px"
  inset:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.card}"
    padding: "8px 12px"
  notice:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.ink}"
    padding: "12px 16px"
  nav-link:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  nav-link-current:
    backgroundColor: "{colors.ledger-paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "6px 8px"
  chooser-button:
    backgroundColor: "{colors.paper-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.chooser}"
    padding: "18px"
    size: "22px"
---

# Design System: Fridge Sheet

<!-- Captured by /impeccable document on 2026-09-29 from fridgesheet/web/static/app.css,
     fridgesheet/sheet.py and fridgesheet/web/charts.py, then named with the maintainer.
     Scan mode: this records the incumbent system as shipped in 0.5, not a redesign. Where paper
     and screen disagree today, the Don'ts say which value is the target. -->

## Overview

**Creative North Star: "The Teacher's Ledger"**

Fridge Sheet is a gradebook made humane. Two school systems each tell part of the story, and the
product's whole job is to post one honest line per assignment and keep the short list of what can
still be fixed in front of a family. The visual system follows that job: the record is the hero,
the interface recedes into ruled paper, and warmth lives in the words rather than in decoration.
Everything on screen should look as if it could be printed and stuck to the fridge without losing
anything, because most of it is.

The feel is **calm, plain, trustworthy**. Nothing shouts. Red is rare and always means the school
recorded something as not in. Type is the system font, set at a comfortable size that grows for a
younger reader. Surfaces are paper on a lighter paper wash, separated by hairline rules. The same
page serves a parent at a desk, a parent on a phone at night, and a child of eight beside them, so
density and vocabulary flex through three reading tiers while the layout, the rows and the actions
never do.

Confirmed visual rejections: dashboard chrome, gradients as decoration, cards floating on shadows,
colour used as the only carrier of meaning, and any treatment a fifth grader's phone would make
invisible.

**Key Characteristics:**
- Ink on paper: near-black text on white cards over a warm-grey wash, hairline rules for structure.
- One accent (ballpoint blue) for the page's single main action, the current choice, and focus.
- Status is a word in a colour, never a colour alone: red pen for not-done, checkmark green for
  done, amber pencil for late, purple stamp for "check on paper".
- Three reading tiers redefine every token together, so the youngest reader gets a larger, calmer,
  higher-contrast page with the same rows.
- Flat at rest; depth from a rule and a wash, with subtle elevation permitted only for things that
  float over content.
- Plain and sturdy controls: 1px strokes, one filled primary per page, 44px targets on touch.

## Colors

A near-monochrome ledger with five ink colours, each of which means one thing and is always
accompanied by its word.

### Primary
- **Ballpoint Blue** (#1f5fa8): the page's one voice. The filled primary button ("Print now"),
  the current filter chip, the selected child tab's underline, links, the focus ring, and the
  left rule on an item that is asking the family a question. On the early tier it deepens to
  #0b5cab and on the middle tier to #14539b so it keeps contrast against the tinted wash.

### Secondary
- **Red Pen** (#b3261e): the school says it is not in. A zero, a missing mark, an overdue and
  still-fixable row, the danger button, the stale-data banner and a warn notice. Early #a3170f,
  middle #a81d14. Never used for emphasis that is not a school-recorded problem.
- **Checkmark Green** (#2e7d32): done. The done-line, a completed step's glyph, a source that
  answered "OK", an on-time series on Trends. Early #1d6b27, middle #24702c.

### Tertiary
- **Amber Pencil** (#b8860b): late, as a stroke: the late series on Trends. As a bold word beside
  a date it is too light (3.3:1), so on screen the word and the rule use **Amber Pencil Ink**
  (#9a5b00, 5.4:1; `--late`, early #8a5200, middle #915600). The printed sheet's LATE word is the
  target for the same token (see the Don'ts).
- **Purple Stamp** (#6b3fa0; `--check`, early #5f3594, middle #653a9a): "check on paper". The
  PAPER — CHECK, IN CLASS — CHECK and HAC — NO GRADE words on the sheet and, since 2026-09-29, on
  a Must-finish row's word and left rule; the follow-up marker under them; the fourth chart
  series. Work the school cannot see, so neither red nor green applies.

### Neutral
- **Ink** (#1c1c1c): all body text and headings. Early #10151b, middle #161b22.
- **Pencil Grey** (#595959): secondary text: meta lines, stamps, the status bar, muted section
  heads, the "nothing to do" item tone. Early #4a5568, middle #5a6474.
- **Stroke Grey** (#8a8a8a): the 1px stroke on buttons, selects and inputs. Darker than a rule so
  a control reads as a control.
- **Ruled Grey** (#d9d9d9): hairline rules, card borders, table row lines, the neutral left rule
  on an item. Early #b9c6d4, middle #ccd5de (tinted so the rule is still visible on the tinted
  wash).
- **Paper White** (#ffffff): every card, item, table, input and the rail. The surface a fact is
  written on.
- **Ledger Paper** (#f4f4f2): the page wash behind the cards, the hover on a nav link or button,
  an inset quoting the record, a badge's fill. Early #eef4fb, middle #f1f5f9: a faint blue cast
  for the younger tiers.
- **Red Pen Wash** (#fdecea; `--warn-wash`): the fill behind a warn notice or the stale banner,
  always paired with Red Pen text.

### Named Rules
**The Word Beside the Colour Rule.** Nothing is conveyed by colour alone. What is red is red *and*
says "not done", "0" or "Missing"; what is green is green *and* has a checkmark or the word
"done". This is the accessibility requirement and the age requirement at the same time.

**The One Voice Rule.** Ballpoint Blue fills at most one button per page, the page's main action,
and marks at most one current choice per control group. Everything else it touches is a stroke,
an underline, a rule or a link.

**The Red Pen Rule.** Red is reserved for what the school recorded as not in. A past due date is
not red on its own; the app's own inference ("No" under Handed in, "School evidence changed") is
bold or blue-ruled, not red; a budget overrun on a child's page is not red.

**The Sheet's Colour Rule.** The sheet's word on a row wears the colour the sheet prints it in,
from one table (`status_words.STATUS_TONE`, the same table as `sheet.STATUS_COLOR`): DUE words
Ballpoint Blue, LATE Amber Pencil Ink, PAPER — CHECK and HAC — NO GRADE Purple Stamp, MISSING
and ZERO Red Pen. The row's left rule takes the same colour. A row cannot be red on screen and
blue on the fridge.

**The Whole-Tier Rule.** A reading tier redefines every colour token at once, never some of them,
so no page inherits a colour nobody designed for that tier.

## Typography

**Display Font:** system-ui (with -apple-system, "Segoe UI", sans-serif)
**Body Font:** system-ui (the same stack)
**Print Font:** Helvetica (Helvetica-Bold, Helvetica-Oblique) in the PDF sheet

**Character:** The device's own text face, set plainly, with hierarchy carried by size and a
slightly heavy 650 weight on section titles rather than by a second family. It reads like a
well-set document, not like an app. The printed sheet uses Helvetica at sizes chosen for a child
reading standing at a fridge.

### Hierarchy
The frontmatter sizes are the root's. Headline, Title and Subtitle are set as multiples of the
tier root (`--type-root`: 16px at the root, 16 / 18 / 20px on the older / middle / early tiers),
so a heading is never smaller than the body it heads: Headline 1.5×, Title 1.125× (the Open work
per-child head 1.375×, a report title 1.25×), Subtitle 1×.
- **Display** (600, 28px): the Today card's big tally number and the kid chooser's heading. Numbers
  a household glances at from across the kitchen. The chooser's own buttons are 22px, the one
  size outside this ramp, on a page that has no tier.
- **Headline** (700, 1.5× root = 24px, -0.3px tracking): the page title in the page head, in the
  exact words of its rail link. One per page.
- **Title** (650, 1.125× root = 18px): a section's h3 in the section head, and `main h3`. The
  Open work page's per-child heads are 1.375× (22px).
- **Subtitle** (650, 1× root = 16px): h4 inside a section, a card's h3, the item name in an item
  head, the primary and default buttons' labels (600).
- **Body** (400, 15px/1.45 at the root): the default. The reading tiers raise the root to 16px
  (older), 18px (middle) and 20px (early), and every rem-free size below follows.
- **Label** (400, 13px, `--type-small`): meta lines, dates, the status bar, badges, chips, table
  sub-lines, the record inset, filters. Tiers raise it to 15px (middle) and 16px (early) so the
  lines a child is asked to judge are never the smallest text on their page.
- **Caption** (400, 12px, `--type-tiny`): stamps, legends under tables, provenance. 13px (middle),
  14px (early).
- **Print heading** (Helvetica-Bold 16pt/19), **print cell** (Helvetica 10pt/12, bold for the
  status word), **print small** (8.5pt/10.5) and **print tiny** (8pt/9.5) for the sheet's
  sub-lines. 10pt cells and 8pt sub-lines are the floor: two children still fit one page.

### Named Rules
**The Measure Rule.** Prose, intros and forms are bounded to 760px (`--measure`, about 75
characters at body size); tables, cards and charts fill the 1600px content column.

**The Never-Smallest Rule.** On a tiered page the secondary sizes and the headings move with the
body size. A fact a child must judge ("Canvas: no submission recorded · 0/10") is never rendered
at the page's smallest size, and the head of a section is never smaller than the sentence under it.

## Layout

One shell, one content column. On a wide screen a 220px rail sits at the left with the wordmark and
navigation; the status bar, an optional stale banner and the page stack in the second column. Under
1024px the rail becomes one horizontal strip that scrolls sideways under a right-edge fade, group
labels dropped, and the page starts about 100px down; a phone held sideways puts the strip and the
status bar on one row. Under 1280px the status bar drops its two reassurance items (the clock, a
run that succeeded) and two-column workspaces such as the check-in stack.

Every page is the same blocks in the same order: status bar, page head (crumb, title in the rail
link's words, actions at the right, one intro sentence bounded to the measure), notices, then the
content column, a ceiling of 1600px with 24px gutters (16px under the strip). The content column is
a stack of sections 32px apart. A section is an h3, a count, one lead sentence and its own controls
at the right; a folded section draws the same head as its summary. An assignment is one item box
with five slots (head, facts, ask line and answers, the family's layer, foot) at three densities:
card, detail and line. Anything quoted inside an item is one inset.

The spacing scale is 4px steps: 4, 8, 12, 16, 24, 32 (`--s1` to `--s6`). Cards sit on a
`repeat(auto-fit, minmax(280px, 1fr))` grid with 16px gaps so three cards fill a row; form fields on
a `minmax(220px, 1fr)` grid label-over-control. Tables are full width with 6px 8px cells, rising to
10px 8px on a coarse pointer and 12px 10px on the early tier. Under the strip breakpoint a work
list stops being a table: each row is one box (the assignment first, then when, then where it
stands) under a hairline, and the header row becomes a row of sort links. A section's controls
follow its lead there, and a page action is a text link rather than a box between the title and
the first row. A quiet fold carries 24px above its head and 12px below.

## Elevation & Depth

Flat at rest. Depth today comes from tone and rule only: a Paper White card on the Ledger Paper
wash with a 1px Ruled Grey border, an inset in wash inside a card, a hairline under each table row.
No shadow exists anywhere in the shipped stylesheet.

The maintainer has opened the door to subtle elevation *(2026-09-29)*: a light ambient shadow may
lift the few things that float over content, namely the sticky Save bar and check-in halves bar,
an opened row-actions menu, and the kid chooser's buttons. Nothing at rest in the content column
lifts.

### Shadow Vocabulary
- **Ambient lift** (`box-shadow: 0 2px 8px rgba(28, 28, 28, 0.08)`, provisional; not yet used in
  code): for a bar or menu that floats over scrolling content. Keep it this quiet or quieter.

### Named Rules
**The Paper Rule.** Surfaces are flat at rest. A shadow is a response to floating over content,
never a way to make a card look important.

## Shapes

Plain and sturdy stationery. Corners are gently rounded: 6px on controls (buttons, inputs, selects,
nav links), 8px on cards, items, insets and chart holders (`--radius`), 10px pills on badges, chips
and chart-key buttons, 12px on the kid chooser's large buttons, 4px on the stale banner. Strokes are
1px: Stroke Grey on controls so they read as controls, Ruled Grey on cards and rules. Emphasis on an
item is a 4px left rule in the status colour and a word, never a different shape or fill: blue asks,
red says not in, green done, grey nothing to do. Insets and the family's layer use a 3px left rule.
The wordmark's mark is a 28px square with 6px corners. The one gradient in the system is
functional, not decorative: the 32px fade at the right edge of the phone strip that says "more
links this way".

## Components

Plain and sturdy: each control is a 1px stroke on paper, one look at three weights, generous
targets, nothing filled until it matters.

### Buttons
- **Shape:** gently rounded (6px), 1px Stroke Grey border, inherits body type, 6px 12px padding
  (10px 14px and a 44px minimum height on a coarse pointer).
- **Secondary (default):** Paper White fill, Ink text. Hover: Ledger Paper fill.
- **Primary:** Ballpoint Blue fill and border, white text, 600 weight; hover brightens 10%. One per
  page: the action that spends paper or saves the form.
- **Danger:** Paper White fill, Red Pen text and border. The one that deletes.
- **Default answer:** the first answer on a row, the one to tap if the sentence above it is
  right: a 2px Ink stroke, 600 weight, 5px 11px padding so it stays level with its neighbours.
  Never the fill; a page keeps one filled primary.
- **Disabled:** 50% opacity, default cursor.
- **Link button:** no border or fill, Pencil Grey underlined text, for "Close" and "undo".
- **Button link (an `<a>` drawn as a button):** the secondary look with 8px 12px padding.
- **Chooser button:** the kid chooser's 22px text, 18px padding, 12px corners, Ruled Grey stroke;
  the grown-up's is 16px on the wash in Pencil Grey.

### Chips
- **Style:** Ledger Paper fill, 1px Ruled Grey border, 10px pill, 1px 8px padding, label type, Ink
  text. Badges, filter chips, the segmented Open/Everything choice and chart-key buttons share it.
- **State:** the one in force is filled Ballpoint Blue with white text; a linked badge's border
  turns Ballpoint Blue on hover; a chart series toggled off is Pencil Grey, struck through, its
  swatch at 30%. Outcome badges in the status bar take Checkmark Green or Red Pen text and border.

### Cards / Containers
- **Corner Style:** 8px.
- **Background:** Paper White on the Ledger Paper wash.
- **Shadow Strategy:** none; see Elevation.
- **Border:** 1px Ruled Grey. An item adds a 4px left rule in its tone colour.
- **Internal Padding:** 12px 16px for cards and items; 8px 12px for an inset; 0 16px for a lines
  list whose rows carry 8px vertical padding and a hairline between them.
- **Item tones:** `ask` and `due` Ballpoint Blue rule, `red` Red Pen rule, `late` Amber Pencil Ink
  rule, `check` Purple Stamp rule, `ok` Checkmark Green rule, `grey` Pencil Grey text with the
  neutral rule. The sheet's word at the head's right wears the same colour as the rule. A
  done-line is a line with a 4px green rule.

### Inputs / Fields
- **Style:** Paper White, 1px Stroke Grey, 6px corners, inherits body type, 4px 6px padding
  (10px 14px on touch). Textareas 60px minimum, 88px in the plan form. Labels sit over their
  controls at 550 weight with Pencil Grey 13px help text beneath.
- **Focus:** a 3px Ballpoint Blue outline offset 3px, on every focusable thing including hidden
  radio chips.
- **Checkbox / radio:** 24px square on a coarse pointer (WCAG 2.5.8).
- **Error / Disabled:** no distinct field error style exists; errors are said in a warn notice.

### Navigation
- **Rail:** Paper White, 1px Ruled Grey right border, 16px padding. The wordmark (mark plus
  "Fridge Sheet", 18px) then links at 6px 8px with 6px corners; uppercase 12px Pencil Grey group
  labels; the current link and hover take the Ledger Paper fill; a question count beside a child's
  name in Ballpoint Blue 600. On a child's page the rail folds everything but Today and that child
  under an "App" disclosure; in kid mode the rail is that child's tabs and a quiet "Not {name}?"
  foot link.
- **Strip (under 1024px):** the same links in one horizontally scrolling row with 8px 10px
  padding, hidden scrollbar, right-edge fade.
- **Child tabs:** 10px 14px links under a hairline; the current one carries a 3px Ballpoint Blue
  underline, blue 650 text.

### Status bar (signature)
One line of Pencil Grey label type under the rail's top edge: when the data was refreshed, each
source's state in Checkmark Green or Red Pen with the word "OK" or the error, the last run's
outcome as a badge, a running job, an available update, and the clock. Drops its reassurances on
narrow screens and never its warnings. Below it, when the data is older than the runner will
print from, a Red Pen Wash banner with Red Pen text and a "Refresh now" link.

### The item (signature)
The one box for one assignment at three densities. Head: the name (650), meta in Pencil Grey label
type (class, kind, points, due), the sheet's word pushed right in the sheet's colour (700). Facts:
one sentence from the verdict. Ask line (600) and answer buttons: the first answer in the default
stroke, the two answers that close a row for good ("Too late to submit", "Let it go") behind a
"More answers" fold inside the row unless one of them is the row's own first answer, identically at
every tier. The family's layer: one line each with a 3px Ballpoint Blue rule. Foot: disclosures
("the record", notes), "Plan a step", and a Caption-sized stamp pushed right; on the detail
density a "More" fold holding only the flags the answers above do not already offer.

### The printed sheet (signature, paper)
Landscape Letter, 0.5in margins, one section per child. Helvetica-Bold 16pt heading, 10pt cells
with the status word bold in its colour, 8.5pt and 8pt sub-lines for the "until" date, the
follow-up marker and notes, an 11pt checkbox per row, a legend at the foot. Overdue first, then
coming due, then two trailer counts. The reader is a child standing at a fridge.

## Do's and Don'ts

### Do:
- **Do** put the word beside the colour: every red, green, amber or purple value carries a word or
  glyph that says the same thing.
- **Do** keep one filled Ballpoint Blue button per page and make it the action that spends paper or
  saves the form.
- **Do** give every tappable thing 44px on a coarse pointer, and 24px to a checkbox or radio box.
- **Do** redefine every token when adding to a tier, and set secondary sizes from `--type-small`
  and `--type-tiny` so they move with the tier.
- **Do** bound prose and forms to `--measure` (760px) and let tables, cards and charts fill the
  column.
- **Do** build a new page from the same blocks: status bar, page head, notices, sections of
  `.sec` with `.sec-head`, and assignments as `_item.html` at card, detail or line density.
- **Do** use the 4px spacing scale (`--s1` to `--s6`) and the 6px / 8px / 10px radius set.

### Don't:
- **Don't** convey state by colour alone, and don't make a past due date red on its own; red is for
  what the school recorded as not in.
- **Don't** add shadows to cards, items or anything at rest; a shadow may lift only a sticky bar,
  an open menu or the chooser's buttons, and no heavier than the provisional ambient lift.
- **Don't** introduce a second value for a status colour. The printed sheet still uses #1A5FB4
  (blue), #1E7A3E (green), #B26A00 (amber) and #555555 (grey); the targets are Ballpoint Blue,
  Checkmark Green, Amber Pencil and Pencil Grey, and the unification belongs to the extract step.
- **Don't** use gradients, glows, or decorative imagery; the only gradient is the strip's fade.
- **Don't** add a fourth box style. Cards, items, insets and lines are the containers; the seven
  box styles they replaced were retired with tests.
- **Don't** hide a row or an action from a child by tier; fold navigation and secondary fields if
  you must, identically at every tier.
- **Don't** hard-code a colour in a template or in `sheet.py`, `charts.py` or `app.js`; every
  colour in this file is the token to reach for. `app.css` carries none outside its token blocks
  (held by `tests/test_web_colour_and_type.py`); `sheet.py` and `charts.py` are the drift to
  remove.
- **Don't** fill more than one button per page, and don't fill an answer: the first answer on a
  row is the default stroke.
